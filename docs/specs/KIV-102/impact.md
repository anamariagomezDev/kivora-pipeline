# KIV-102 · Análisis de impacto: nuevo formato de `refunds.json`

Estado: **análisis, sin cambios de código.** Escrito antes de la especificación y del plan
(`assignment.md:230-234`). Datos: `data/inbox/` con las entregas 1 y 2 (días 2026-09-01 a
2026-09-10), commit `37a937b`.

## 1. El cambio

Según `docs/tickets/KIV-102.md`, desde el 2026-09-08 cada devolución trae `refund_amount` en lugar
de `amount` y un campo nuevo, `reason` (texto o `null`). Los ficheros antiguos no se reenvían, así
que en `data/inbox/` hay ficheros de los dos formatos.

Claves de cada fichero (script de comprobación en el anexo, apartado A.3):

| Día | Devoluciones | Claves | `reason = null` |
| --- | --- | --- | --- |
| 09-04 … 09-07 | 6 + 10 + 8 + 8 = 32 | `refund_id, order_id, refunded_at, amount, currency` | — |
| 09-08 | 5 | `refund_id, order_id, refunded_at, refund_amount, currency, reason` | R-1033 |
| 09-09 | 6 | ídem | — |
| 09-10 | 4 | ídem | — |

- Ningún fichero mezcla formatos: el formato cambia de un fichero a otro, nunca dentro del mismo.
- El único `refund_id` repetido en todo el inbox es R-1006 (09-05 y 09-06, formato antiguo). Ningún
  `refund_id` aparece en los dos formatos **en los datos actuales**.
- Las 15 devoluciones nuevas son R-1032 … R-1046.

## 2. Qué pasa hoy con los datos nuevos

### 2.1 El pipeline las rechaza todas sin avisar

```
$ uv run python tasks.py run
Días procesados: 10 (2026-09-01 .. 2026-09-10)
daily_customer_metrics: 175 filas; rejected: 21 registros
Controles de calidad: los 3 pasan
(código 0)
```

`rejected.csv` tiene 21 registros: los 6 de KIV-101 y **las 15 devoluciones nuevas, todas con
`invalid_record`**, con este `detail`:

```
$ grep -E '^refunds,.*,2026-09-(08|09|10),' output/rejected.csv
refunds,R-1032,invalid_record,2026-09-09,refunds.json#0: amount no numérico o <= 0: None
refunds,R-1033,invalid_record,2026-09-08,refunds.json#0: amount no numérico o <= 0: None
… (15 líneas, R-1032 … R-1046: 5 del 09-08, 6 del 09-09 y 4 del 09-10)
```

Cómo ocurre:

1. `kivora/ingest.py:14` fija `REFUND_FIELDS = [..., "amount", ...]` y `kivora/ingest.py:55` lee
   cada campo con `item.get(f)`. Si falta `amount`, la columna queda en `NULL` y no da error.
   `refund_amount` y `reason` solo se guardan dentro de `_raw` (`kivora/ingest.py:54`).
2. `kivora/customer_metrics.py:179-181` (`_refund_problem`) convierte `None` en «no numérico» y
   rechaza el registro con `invalid_record` (`kivora/customer_metrics.py:191-194`). El mensaje dice
   que el importe no es numérico, no que el campo falta.
3. Nada lo detecta:
   - el código de salida es 0;
   - los tres controles de `quality_report.json` pasan (`kivora/customer_metrics.py:275-286`):
     ninguno cuenta los rechazos;
   - `uv run python tasks.py check` → `OK` (`kivora/check.py` no mira las devoluciones);
   - `uv run python tasks.py test` → `24 passed`;
   - `uv run python tasks.py acceptance` → `50 PASS, 0 FAIL`, porque solo copia los días 01–07
     (`kivora/acceptance.py:32`);
   - `reference_calc.py` tiene el mismo fallo: lanza `KeyError` en `r["amount"]`
     (`docs/specs/KIV-101/reference_calc.py:68`), lo captura como `invalid_record` (`:69-70`) y
     coincide con el pipeline. Así que el diferencial no puede detectarlo:

     ```
     $ uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary
     ventas 213 bruto 25072.41 devuelto 1264.19 neto 23808.22 filas 175 solo_devolucion 11 neto_negativo 12
     rejected refunds R-1032 2026-09-09 invalid_record
     … (las mismas 15 devoluciones con invalid_record)
     ```

### 2.2 Cifras: qué falta

Lo he comparado con una simulación (anexo, apartado A.2): una copia de `data/inbox/` en el
scratchpad donde se renombra `refund_amount` a `amount` y se conserva `reason`, procesada con la
interfaz oficial `python -m kivora`. Esa copia muestra lo que daría el pipeline si leyera bien el
formato nuevo con las reglas de KIV-101.

| Métrica (`daily_customer_metrics`) | 01–07 (entregado a Finanzas) | Hoy, 01–10 | 01–10 con el formato nuevo bien leído | Diferencia |
| --- | --- | --- | --- | --- |
| Ventas | 156 | 213 | 213 | 0 |
| Bruto | 18 490,74 | 25 072,41 | 25 072,41 | 0 |
| **Devuelto** | 1 264,19 | **1 264,19** | **1 576,04** | **−311,85** |
| **Neto** | 17 226,55 | **23 808,22** | **23 496,37** | **+311,85** |
| `refunds_count` (suma) | 28 | 28 | 41 | −13 |
| Filas cliente-día | 126 | 175 | 186 | −11 |
| Filas solo con devoluciones | 11 | 11 | 22 | −11 |
| Filas con neto negativo | 12 | 12 | 24 | −12 |
| `rejected.csv` | 6 | 21 | 8 | +13 |

Con el formato nuevo bien leído, de las 15 devoluciones nuevas:

- **13 se aceptan** y suman 311,85 €: 112,06 € el 09-08, 102,87 € el 09-09, 86,97 € el 09-10 y
  9,95 € el 09-11. R-1036 es del `2026-09-10T23:10:00Z`, que en Madrid ya es el 11 (R6).
- **2 se rechazan por un motivo real**, que hoy queda oculto bajo `invalid_record`:
  - `R-1034 order_not_found`: el pedido K-19998 no está en ningún `orders.csv`;
  - `R-1035 refund_exceeds_order`: 70,0 + 20,0 supera los 80,00 EUR de K-10155 (ya tenía R-1013).

Filas que hoy faltan o están mal (hoy → con el formato nuevo bien leído):

```
2026-09-08 C003  —  →  ES,0,0.00,4.54,-4.54,1,2026-09-06
2026-09-08 C006  —  →  ES,0,0.00,26.94,-26.94,1,2026-09-07
2026-09-08 C018  —  →  GB,0,0.00,36.86,-36.86,1,2026-09-05
2026-09-08 C022  —  →  US,0,0.00,33.72,-33.72,1,2026-09-07
2026-09-08 C029  —  →  DE,0,0.00,10.00,-10.00,1,2026-09-07
2026-09-09 C005  —  →  ES,0,0.00,23.35,-23.35,1,2026-09-08
2026-09-09 C007  —  →  UNKNOWN,0,0.00,40.94,-40.94,1,2026-09-08
2026-09-09 C015  —  →  ES,0,0.00,35.00,-35.00,1,2026-09-08
2026-09-09 C023  ES,1,118.01,0.00,118.01,0  →  ES,1,118.01,3.58,114.43,1
2026-09-10 C001  —  →  FR,0,0.00,17.30,-17.30,1,2026-09-07
2026-09-10 C025  —  →  GB,0,0.00,41.44,-41.44,1,2026-09-08
2026-09-10 C027  ES,1,14.71,0.00,14.71,0  →  ES,1,14.71,28.23,-13.52,1
2026-09-11 C031  —  →  ES,0,0.00,9.95,-9.95,1,2026-09-09
```

### 2.3 Las cifras ya entregadas a Finanzas no cambian

Las cifras de la respuesta de KIV-101 (`docs/tickets/KIV-101.md:76-96`) son las de los días
01–07. He comparado fila a fila `metric_date <= 2026-09-07` en tres salidas: la de los días 01–07,
la de hoy y la simulada. **No hay ninguna fila distinta.** Las tres dan 156 ventas, 18 490,74 € de
bruto, 1 264,19 € devueltos, 17 226,55 € de neto, 126 filas y los mismos 6 rechazos. Tiene
sentido: las devoluciones nuevas son del 09-08 en adelante y R6 las asigna a su propio día
(D1, `docs/report.md:14`). Lo que cambia son los días **08 a 11**: si hoy se entregaran, el importe
devuelto saldría a 0,00 € y el neto inflado en 311,85 €.

## 3. Componentes afectados

### 3.1 Código del pipeline

| Archivo:línea | Qué hace hoy | Impacto |
| --- | --- | --- |
| `kivora/ingest.py:14-16` | `REFUND_FIELDS` con `amount`; `REFUND_COLUMNS` añade `_raw` | **Directo.** No conoce `refund_amount` ni `reason`. Es el lugar natural para normalizar los dos formatos |
| `kivora/ingest.py:54-55` | `_raw` = el objeto JSON entero, canónico; `item.get(f)` por campo | **Directo.** Un campo que falta queda en `NULL` sin avisar. `_raw` incluye `refund_amount` y `reason`, lo que afecta a R9 (riesgo 4.1) |
| `kivora/ingest.py:64`, `:76-78` | Crea y rellena `raw_refunds` | Esquema de `raw_refunds` en `warehouse.db`: hoy `refund_id, order_id, refunded_at, amount, currency, _raw, _day, _pos` (comprobado con `pragma table_info`). Si se añade `reason`, cambia la tabla |
| `kivora/customer_metrics.py:21` | `REFUND_REQUIRED` (sin el importe; se valida aparte) | Indirecto |
| `kivora/customer_metrics.py:146-168` | R8/R9: agrupa por `refund_id` y compara `_raw` (`:158`) | **Directo.** Con dos formatos, el mismo contenido da un `_raw` distinto → `conflicting_duplicate` (riesgo 4.1) |
| `kivora/customer_metrics.py:171-182` | `_refund_problem`: `row["amount"]` (`:179-181`) | **Directo.** Aquí nacen los 15 `invalid_record`; el `detail` no dice que falta el campo |
| `kivora/customer_metrics.py:218-235` | R11: `row["amount"]` (`:225`) | **Directo**: lee el campo antiguo |
| `kivora/customer_metrics.py:275-286` | Tres controles de calidad | No cambia, pero ningún control detecta un rechazo masivo (riesgo 4.3) |
| `kivora/pipeline.py:49-51` | Pasa `raw_refunds` a `compute` | Sin cambios si la normalización se hace en `ingest` |
| `kivora/outputs.py`, `kivora/check.py`, `kivora/__main__.py` | Escriben y validan las salidas; interfaz | **No se ven afectados.** Columnas de salida iguales; la interfaz no se toca (CLAUDE.md) |
| `sql/*.sql` | `daily_sales`, `top_customers`, staging | **No se ven afectados**: no leen `raw_refunds` (`sql/staging.sql:34` es el `amount` de `payments`) |
| `tasks.py` | Tareas `run`, `test`, `check`, `acceptance`, `deliver` | No se ven afectados |

### 3.2 Tests y oráculo

| Archivo:línea | Impacto |
| --- | --- |
| `tests/test_customer_metrics.py:44-46` | Los helpers `refund()` y `write_refunds()` solo generan el formato antiguo (30 apariciones en el fichero). Los tests siguen siendo válidos si se mantiene el formato antiguo. **No hay ningún test con `refund_amount`, `reason` ni formatos mezclados** |
| `tests/test_pipeline.py` | No se ve afectado (no usa devoluciones) |
| `kivora/acceptance.py:32` | `DAYS` = 09-01..09-07: E1–E19 no ven los días nuevos. Bien para no reescribir KIV-101 (`docs/specs/KIV-101/plan.md:325`), pero hoy el oráculo no detecta nada de KIV-102 |
| `kivora/acceptance.py:307-309` | `rf()` de S1–S8 solo genera el formato antiguo |
| `kivora/acceptance.py:249-257` | El diferencial compara con `reference_calc.py`: si este no se adapta, cualquier escenario nuevo con `refund_amount` dará diferencias |
| `docs/specs/KIV-101/reference_calc.py:33` | `json.load` con `utf-8` y `float` (el pipeline usa `utf-8-sig` y `Decimal`) |
| `docs/specs/KIV-101/reference_calc.py:56` | Firma de R9 = el objeto JSON entero: mismo riesgo 4.1 |
| `docs/specs/KIV-101/reference_calc.py:68`, `:80` | `r["amount"]` → `KeyError` → `invalid_record`. Este riesgo ya estaba previsto en `docs/specs/KIV-101/plan.md:307` |

### 3.3 Documentación

| Archivo:línea | Qué hay que cambiar |
| --- | --- |
| `docs/sources.md:52-74` | Tabla de campos de `refunds.json` (`:62` `amount`): añadir el formato nuevo, desde qué día aplica y cómo conviven |
| `docs/specs/KIV-101/spec.md:25` | Deja KIV-102 fuera de alcance: la spec de KIV-102 debe enlazarlo |
| `docs/specs/KIV-101/spec.md:74`, `:168` | Las reglas de `invalid_record` y R8 nombran `amount` |
| `docs/specs/KIV-101/spec.md:172-173` | R9 compara «contenido»: hay que definir qué es contenido con dos formatos |
| `docs/specs/KIV-101/plan.md:307`, `:325` | Riesgos previstos: marcarlos como tratados en KIV-102 |
| `docs/report.md:88-102` | Trazabilidad R1/R8/R9/R11: añadir los requisitos de KIV-102 |
| `docs/tickets/KIV-102.md` | Secciones «Notas del equipo de datos» y «Respuesta», hoy vacías |
| `CLAUDE.md` (sección «Entrada») | Mencionar que conviven dos formatos de `refunds.json` |

## 4. Riesgos

### 4.1 La misma devolución en los dos formatos → `conflicting_duplicate`

R9 compara el objeto JSON entero (`kivora/ingest.py:54`, `kivora/customer_metrics.py:158`). Si
una devolución del 09-07 se reenvía en el formato nuevo, el contenido es idéntico pero las claves
son otras, así que el pipeline rechaza **las dos** apariciones y la devolución se pierde.
Demostrado con un fichero sintético en el scratchpad y las funciones reales `read_refunds` y
`deduplicate_refunds` (anexo, apartado A.3):

```
2026-09-07 amount= 5.0  _raw= {"amount": "5.0", "currency": "EUR", "order_id": "K-1", "refund_id": "R-9", ...}
2026-09-08 amount= None _raw= {"currency": "EUR", "order_id": "K-1", "reason": null, "refund_amount": "5.0", ...}
candidatas: 0 | rechazos: [('R-9', 'conflicting_duplicate', '2026-09-07'), ('R-9', 'conflicting_duplicate', '2026-09-08')]
```

Hoy no ocurre (sección 1), pero la tienda ya reenvió una devolución una vez (R-1006, E10). Si
solo se renombra el campo y se sigue comparando `_raw`, el riesgo continúa. La comparación tiene
que hacerse sobre el registro normalizado. Falta decidir:

- si `reason` cuenta como contenido. En el formato antiguo no existe; si cuenta, una copia
  antigua frente a una nueva con motivo sería siempre un conflicto;
- si `reason` ausente equivale a `reason: null`;
- si dos copias en formato nuevo que solo difieren en `reason` son la misma devolución.

### 4.2 Registros ambiguos

- Un objeto **con `amount` y `refund_amount` a la vez**: ¿cuál vale? ¿Y si no coinciden?
- Un objeto **sin ninguno de los dos**: hoy da `invalid_record` con un mensaje engañoso.
- Un fichero con **formatos mezclados**: no pasa hoy, pero nada lo impide.
- Elegir el formato **por la fecha de la carpeta** (≥ 09-08) en vez de por las claves de cada
  registro fallaría con reenvíos tardíos en el formato antiguo o con reprocesos.

### 4.3 Fallo silencioso

La pérdida de 311,85 € pasa con código 0, tres controles en verde, `check`, `test` y
`acceptance` en verde (sección 2.1). Hay dos riesgos:

- otro cambio de esquema futuro se colaría igual;
- añadir un control nuevo a `quality_report.json` cambia su estructura. Esa estructura la fijan
  `kivora/check.py:19` y `kivora/acceptance.py:39-40`, y es parte del contrato de KIV-101
  (spec §3.3), así que habría que decidirlo aparte.

### 4.4 Regresiones de KIV-101

Si se cambia R9 para comparar campos normalizados en vez de `_raw`, cambia también el
comportamiento con el formato antiguo: por ejemplo, dos copias que solo difieran en un campo
desconocido dejarían de ser un conflicto. E10 y S5 deben seguir pasando igual, y conviene añadir
un test que fije el comportamiento elegido.

### 4.5 El oráculo es parte del cambio

`reference_calc.py` está en `docs/specs/KIV-101/`. Si se adapta, cambia el oráculo de una spec ya
aprobada; si no se adapta, el diferencial de cualquier escenario nuevo falla. Hay que decidirlo y
justificarlo (CLAUDE.md: «un test que contradice el contrato no se adapta en silencio»).

### 4.6 `reason` es texto libre

`reason` viene en UTF-8 con tildes («cambio de opinión», «llegó tarde»). No se usa en ninguna
métrica. Si se lleva a `warehouse.db` o a `rejected.csv`, hay que cuidar la codificación y la
determinación de la salida (E19).

## 5. Opciones

| Opción | Qué supone | Efecto en las cifras | Valoración |
| --- | --- | --- | --- |
| **A. Aceptar los dos formatos, normalizando en la carga** | `read_refunds` detecta el formato **por las claves de cada registro** y produce un registro canónico (`amount` ← `amount` o `refund_amount`; `reason` opcional, ausente = `null`). R9 compara el registro canónico. Un registro con los dos campos de importe, o sin ninguno, va a `invalid_record` con un `detail` claro | 13 devoluciones más (311,85 €); 01–07 sin cambios | **Recomendada** |
| B. Solo el formato nuevo | Se exige `refund_amount` | Los registros de 09-04..09-07 pasarían a `invalid_record`. En 01–07: devuelto 0,00 € (antes 1 264,19 €), neto 18 490,74 € y 115 filas en lugar de 126. Cambiarían cifras ya entregadas a Finanzas y fallarían E2, E6–E11, E13, E14 y E18 (anexo, apartado A.4) | Descartada: los ficheros antiguos no se reenvían |
| C. Formato según la fecha de la carpeta | Antiguo antes del 09-08, nuevo desde el 09-08 | Igual que A con los datos de hoy | Frágil (riesgo 4.2) |
| D. Detener el pipeline ante un formato desconocido | `InputError` si un registro no encaja en ningún formato | — | Complementaria de A, no alternativa. Cambia R1 (hoy solo se detiene con JSON inválido), así que habría que decidirlo |
| E. No hacer nada | — | −311,85 € de devoluciones desde el 09-08, sin aviso | Descartada |

**Recomendación: A.** Motivos:

- conserva el histórico sin cambiar nada de lo ya entregado (sección 2.3);
- trata el formato nuevo con las mismas reglas R8–R11;
- quita el riesgo 4.1 al comparar duplicados sobre el registro normalizado;
- deja el cambio en un solo punto, la carga, sin tocar `customer_metrics` más que en la
  comparación de R9 y el `detail`.

Lo que debe fijar la spec (para que lo decida Ana):

1. Si `reason` entra en la comparación de R9. Propongo **que no entre**: no afecta a ninguna
   cifra y así una copia antigua y una nueva de la misma devolución son la misma.
2. Qué hacer con los registros ambiguos (sección 4.2). Propongo `invalid_record` con un `detail`
   que nombre el campo.
3. Si `reason` se guarda en `raw_refunds` (`warehouse.db`). Propongo que sí, como columna `TEXT`.
   No se exporta a ningún CSV.
4. Si se añade un control o un aviso de rechazos masivos (riesgo 4.3). Propongo dejarlo fuera
   de KIV-102 y anotarlo.
5. Cómo se adapta el oráculo (riesgo 4.5). Propongo adaptar `reference_calc.py` al formato nuevo
   en su propio commit, justificado, y añadir a `acceptance` escenarios sintéticos de KIV-102.
   Por ejemplo: formato nuevo, `reason: null`, los dos formatos en días distintos con el mismo
   `refund_id`, un registro con los dos campos de importe. Además, uno sobre los días 08–10 con
   los totales de la sección 2.2, sin tocar E1–E19.

## 6. Cifras para Finanzas

- **Las cifras del 1 al 7 de septiembre no cambian** (sección 2.3): 156 ventas, 18 490,74 € de
  bruto, 1 264,19 € devueltos, 17 226,55 € de neto.
- **Del 8 al 11 de septiembre, hoy el pipeline daría un importe devuelto de 0,00 €**, porque
  pierde 13 devoluciones válidas por 311,85 €. Corregido con la opción A:
  - devuelto: 09-08 112,06 €; 09-09 102,87 €; 09-10 86,97 €; 09-11 9,95 €;
  - neto total 01–10: 23 496,37 € en lugar de 23 808,22 €;
  - 11 filas cliente-día nuevas, solo con devoluciones; C023 (09-09) y C027 (09-10) cambian de neto.
- Dos devoluciones nuevas no se usarán por motivos de negocio, no de formato: R-1034 (pedido
  K-19998 inexistente) y R-1035 (superaría el total de K-10155).
- `reason` no cambia ninguna cifra.

## Anexo · Cómo reproducirlo

### A.1 Comportamiento actual

```
uv run python tasks.py run
grep -E '^refunds,.*,2026-09-(08|09|10),' output/rejected.csv        # 15 líneas invalid_record
uv run python tasks.py test; uv run python tasks.py check; uv run python tasks.py acceptance   # todo en verde
uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary
```

### A.2 Simulación del formato nuevo bien leído

Se ejecuta fuera del repositorio, en una carpeta temporal `$TMP`. Copia `data/inbox/` sin
modificarlo:

```python
# $TMP/v2/inbox = copia de data/inbox con refund_amount -> amount (reason se conserva)
import json, shutil; from pathlib import Path
src, dst = Path("data/inbox"), Path(TMP) / "v2" / "inbox"
shutil.copytree(src, dst)
for f in dst.glob("*/refunds.json"):
    data = json.loads(f.read_text(encoding="utf-8"))
    for r in data:
        if "refund_amount" in r: r["amount"] = r.pop("refund_amount")
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
```

```
uv run python -m kivora --inbox $TMP/v2/inbox --reference data/reference --out $TMP/v2/out
# → daily_customer_metrics: 186 filas; rejected: 8 registros; los 3 controles pasan
uv run python -m kivora --inbox $TMP/base/inbox --reference data/reference --out $TMP/base/out
# $TMP/base/inbox = copia de los días 09-01..09-07 → 126 filas; rejected: 6
```

Las tablas de la sección 2.2 salen de sumar `daily_customer_metrics.csv` de `$TMP/base/out`,
`output/` y `$TMP/v2/out`, y de comparar las filas por (`metric_date`, `customer_id`).

### A.3 Riesgo 4.1 y claves por fichero

Se escriben dos `refunds.json` sintéticos en `$TMP/dup/` (R-9 en formato antiguo el 09-07 y en
formato nuevo el 09-08). Se leen con `kivora.ingest.read_refunds` y se pasan a
`kivora.customer_metrics.deduplicate_refunds`, sin modificar ningún archivo del repositorio. Las
claves de cada fichero salen de `json.loads` sobre `data/inbox/*/refunds.json` y un `Counter`
por conjunto de claves.

### A.4 Opción B simulada

Copia de los días 09-01..09-07 en `$TMP/optB/inbox` con `amount` renombrado (equivale a un
pipeline que solo acepta `refund_amount`). Se procesa con `python -m kivora` y sobre la salida
se ejecutan `kivora.acceptance.check_literal_scenarios` y `totals`:

```
{'ventas': 156, 'bruto': 18490.74, 'devuelto': 0.00, 'neto': 18490.74, 'filas': 115, 'solo_devolucion': 0, 'neto_negativo': 0}
FAIL: ['E2', 'E6', 'E7', 'E8', 'E9', 'E10', 'E11', 'E13', 'E14', 'E18']
```
