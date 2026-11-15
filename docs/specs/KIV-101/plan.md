# KIV-101 · Plan de implementación

- **Especificación:** `docs/specs/KIV-101/spec.md` (aprobada). Los identificadores R*, E* y S* son
  los suyos.
- **Estado:** borrador del agente, pendiente de revisión por Ana. En la fase 2 no se toca
  `kivora/`, `sql/` ni `tests/`.

## 1. Punto de partida (verificado leyendo el código)

- `kivora/pipeline.py:26-45`: crea `out/`, recrea `warehouse.db`, carga los datos en bruto
  (`ingest.load_inbox`), ejecuta `sql/staging.sql`, `daily_sales.sql` y `top_customers.sql` y exporta
  dos CSV con `SELECT *`.
- `kivora/ingest.py:19-34`: solo conoce `orders`, `customers` y `payments` (`SOURCES`,
  ingest.py:6-11); todo como TEXT, con la carpeta en `_day` y sin la posición de la fila. Un
  `refunds.json` hoy se ignora.
- `kivora/__main__.py:16-28`: las tres opciones y sus valores por defecto (interfaz fija, R18);
  siempre devuelve 0.
- `kivora/check.py:8-11, 29`: espera solo `daily_sales.csv` y `top_customers.csv` y hace
  `float(row["gross_amount"])` sobre **todas** las filas de cada fichero esperado.
- `tests/test_pipeline.py`: 4 tests sobre `daily_sales`; `test_gross_matches_source_total`
  (:66-75) reproduce los defectos de `daily_sales` (`docs/analysis.md` §3).
- `tasks.py:47-54, 97-104`: no hay tarea `acceptance`; `test` lanza `pytest -q` sin argumentos.
- `pyproject.toml`: Python ≥ 3.11 y `tzdata` ya declarado (necesario para `zoneinfo` en Windows).

## 2. Enfoque técnico

**La lógica nueva va en Python, no en SQL.** Motivos:

1. **Importes (R5).** SQLite no tiene tipo decimal: `CAST(... AS REAL)` es coma flotante binaria y
   `ROUND` sobre REAL no garantiza medio hacia arriba (por ejemplo, 2.675 se guarda como
   2.67499…). En Python, `decimal.Decimal` con `ROUND_HALF_UP` es exacto. `refunds.json` se lee con
   `json.load(..., parse_float=Decimal)`, para que los importes nunca pasen por `float`.
2. **Fechas (R6).** SQLite no tiene zonas horarias: solo podría aplicar un desfase fijo, que falla
   en invierno. `zoneinfo.ZoneInfo("Europe/Madrid")` aplica el horario de verano.
3. **Reglas con orden (R9, R11, R12).** El límite acumulado por pedido, la prioridad de motivos y
   la deduplicación por contenido se escriben y se prueban más claramente como funciones puras.
4. **Determinismo (R16).** El orden de las salidas se fija explícitamente en Python, sin depender
   del orden de las filas de SQLite.

**Estructura:**

- `kivora/ingest.py` amplía la carga en bruto: tabla `raw_refunds` y columna `_pos` (posición de la
  fila o del elemento en su fichero) en todas las tablas `raw_*`. Así se pueden aplicar los
  desempates de R2, R7 y R9 y se conserva la trazabilidad en `warehouse.db`.
- `kivora/customer_metrics.py` (nuevo): funciones puras, sin E/S, que reciben listas de
  diccionarios y devuelven ventas, devoluciones aceptadas, rechazos, filas de métricas y controles.
  Una función por regla: `latest_orders`, `classify_orders`, `classify_refunds`,
  `apply_refund_limit`, `build_metrics`, `quality_checks`.
- `kivora/outputs.py` (nuevo): escribe `daily_customer_metrics.csv`, `rejected.csv` y
  `quality_report.json` con el formato de spec §3.4, y guarda las mismas tablas en `warehouse.db`
  con los importes como TEXT.
- `kivora/pipeline.py` llama a lo anterior después de los SQL actuales. `daily_sales` y
  `top_customers` no cambian (fuera de alcance, spec §2).
- `kivora/acceptance.py` (nuevo) es el oráculo de `tasks.py acceptance`. Va junto a
  `kivora/check.py`, y es el único fichero de `kivora/` que puede contener ids de la muestra.

**Qué no se hace:** no se cambian las opciones de `python -m kivora`, no se corrige
`daily_sales`, no se lee nada fuera de `--inbox` y `--reference` y no se escribe fuera de `--out`.

## 3. Tareas

Orden pensado para tener primero la señal de parada (el oráculo) y los tests en rojo, y después
implementar regla a regla. Cada tarea es un commit, con `Co-Authored-By` en los del agente.

### T0 · Línea base

- **Qué:** registrar el estado inicial antes de tocar nada.
- **Archivos:** ninguno.
- **Verificación:**
  - `uv run python tasks.py test` → `4 passed`.
  - `uv run python tasks.py check` → `OK: output/ tiene los ficheros y columnas esperados`.
  - `uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary` →
    `ventas 156 bruto 18490.74 devuelto 1264.19 neto 17226.55 filas 126 …` y 6 rechazos.

### T1 · Tarea `acceptance` (oráculo)

- **Qué:**
  - `tasks.py`: nueva tarea `acceptance` que llama a `_module("kivora.acceptance")`.
  - `kivora/acceptance.py`:
    1. Ejecuta `python -m kivora --inbox data/inbox --reference data/reference --out <tmp>/run1` y
       `.../run2` como subprocesos y exige código 0.
    2. Comprueba que existen los tres ficheros, con las columnas de spec §3.1–3.3.
    3. Comprueba las filas literales de E1–E17, las ausencias de E2 y E11 y los totales y rechazos
       de E18. Esos valores van escritos en el módulo, cada uno con su id E*.
    4. Hace una comparación diferencial completa: las 126 filas de `daily_customer_metrics.csv` y
       `(source, record_id, inbox_day, reason)` de `rejected.csv` deben ser iguales a la salida de
       `docs/specs/KIV-101/reference_calc.py`.
    5. Construye S1–S8 en carpetas temporales y comprueba sus resultados. En S7 espera un código
       distinto de 0 y el nombre del fichero en el mensaje.
    6. Comprueba E19: el mismo SHA-256 en run1 y run2 para los tres ficheros nuevos, y el mismo
       hash del árbol `data/inbox/` antes y después.
    7. Imprime `PASS`/`FAIL` por escenario y termina con 0 solo si pasan todos.
- **Archivos:** `tasks.py`, `kivora/acceptance.py`.
- **Cubre:** E1–E19, S1–S8 (la verificación; la implementación viene después).
- **Verificación:**
  - Ahora, `uv run python tasks.py acceptance` → código ≠ 0, con `FAIL` porque faltan los tres
    ficheros. Es el rojo esperado.
  - Para validar el propio oráculo, la parte de filas literales se ejecuta también sobre la salida
    de `reference_calc.py` y debe pasar.
- **Uso posterior:** es la condición de parada del agente en la fase 4 (hook `Stop` o skill, fase 3).

### T2 · Carga de `refunds.json` y posición de fila

- **Qué:**
  - `ingest.py`: tabla `raw_refunds` (`refund_id`, `order_id`, `refunded_at`, `amount`,
    `currency`, `_day`, `_pos`), todo como TEXT, con los importes guardados tal cual (texto del
    `Decimal`). Columna `_pos` en todas las `raw_*`.
  - Un fichero ausente o con `[]` no carga nada. Si el JSON es inválido, o no es una lista, se lanza
    `InputError("<ruta>: ...")`.
  - `__main__.py`: captura `InputError`, imprime el mensaje en stderr y devuelve 2. Las opciones no
    cambian.
  - Los SQL actuales leen columnas explícitas, así que añadir `_pos` no los afecta.
- **Archivos:** `kivora/ingest.py`, `kivora/__main__.py`.
- **Cubre:** R1, R18, S7, S8.
- **Verificación:**
  - `uv run python tasks.py test` → los 4 tests existentes siguen pasando.
  - `uv run python tasks.py run` → `daily_sales.csv` igual byte a byte que en T0 (`sha256sum`).
  - Consulta `SELECT COUNT(*) FROM raw_refunds` sobre `output/warehouse.db` → 32.
  - S7 a mano sobre una carpeta temporal → código 2 y la ruta del fichero en el mensaje.

### T3 · Tests nuevos en rojo

- **Qué:** `tests/test_customer_metrics.py` con datos sintéticos en `tmp_path`, nunca sobre
  `data/inbox/`. Los helpers `write_day` y `write_refunds` permiten días con o sin `refunds.json`.
  Los siete tests mínimos de `assignment.md` §4, y para cada uno el defecto que debe detectar:

  | # | Test | Datos | Espera | Falla si… |
  | --- | --- | --- | --- | --- |
  | 1 | `test_dedup_exact_copies_and_versions` | K-1 duplicado exacto; K-2 de 10.00 → 12.00 en el día 2; K-3 `confirmed` → `cancelled` | K-1 cuenta 1; K-2 cuenta 1 con 12.00; K-3 en `rejected.csv` como `not_sale_cancelled`; ni K-1 ni K-2 en `rejected.csv` | se usa `DISTINCT` en vez de la última versión, o se rechazan las copias |
  | 2 | `test_null_and_missing_values` | cliente con `country` vacío; pedido de un cliente inexistente; pedido sin `customer_id`; dos devoluciones sin `refund_id` | `UNKNOWN` en las dos primeras ventas; `invalid_record` para el pedido; **dos** filas `invalid_record` para las devoluciones | el país sale vacío, se pierde la venta o salen `conflicting_duplicate` |
  | 3 | `test_partial_refund` | venta de 10.00; devolución de 3.00 | `refunded_amount 3.00`, `net_amount 7.00`, `refunds_count 1` | se descuenta el total del pedido o no se resta |
  | 4 | `test_multiple_refunds_same_order` | venta de 10.00 el día 1; devoluciones de 2.00 (día 2) y 3.00 (día 3) | dos filas solo con devoluciones, cada una en su día, con `orders_count 0` | se suman en el día de la compra o se queda solo una |
  | 5 | `test_refund_without_order` | devolución de un `order_id` que no existe | `refunds,…,order_not_found`; ninguna fila de métricas | se descarta en silencio o crea una fila |
  | 6 | `test_net_amount` | venta en USD (100.00 + 73.56 → 92.00 + 67.68); devolución de 179.88 USD → 165.49 en otro día | `net = gross − refunded` exacto; una fila con neto negativo; redondeo por registro | se redondea la suma, se usa `float` o se fuerza `net ≥ 0` |
  | 7 | `test_no_duplicates_after_joins` | venta con 2 pagos `captured` y 1 `failed`; cliente reenviado dos veces con otro país; una devolución | una fila (`orders_count 1`, un solo importe, una devolución), país = el último; control `unique_keys_and_orders` con `failed_records 0` | el JOIN con pagos o clientes multiplica las filas |

  Tests adicionales, uno por regla de la especificación:
  - `refund_exceeds_order`: 6 + 5 sobre 10; se rechaza la segunda, y una tercera de 4 se acepta (R11).
  - `duplicate_refund` y `conflicting_duplicate` (R9).
  - `order_not_sale` para un pedido cancelado y para uno sin pago capturado (R10).
  - `currency_mismatch` y `unknown_currency`.
  - `amount ≤ 0`.
  - El cambio de día en Madrid en verano (`22:30Z` → día siguiente) **y en invierno**
    (`2026-12-01T22:30:00Z` → mismo día), porque un +2 fijo fallaría (R6).
  - `last_purchase_date` en una fila solo con devoluciones, sin mirar al futuro (R14).
  - `refunds.json` mal formado → `InputError`; día sin `refunds.json` (R1).
  - Determinismo: dos ejecuciones dan los mismos bytes (R16).
  - `--inbox` sin cambios después de ejecutar.
- **Archivos:** `tests/test_customer_metrics.py` (y un `tests/conftest.py` si los helpers se
  comparten).
- **Cubre:** R1–R17 a nivel unitario; los siete casos de `assignment.md` §4.
- **Verificación:** `uv run python tasks.py test` → los 4 tests antiguos pasan y los nuevos fallan
  porque aún no existen los ficheros. El rojo se registra en la memoria.

### T4 · Pedidos: última versión, validación y ventas

- **Qué:** `latest_orders` (R2: mayor `updated_at`, desempate por `_day` y `_pos`) y
  `classify_orders` (R3, R4, con los motivos de pedidos en su orden de prioridad), clientes (R7) y
  pagos `captured`.
- **Archivos:** `kivora/customer_metrics.py`.
- **Cubre:** R2, R3, R4, R7; E1, E3, E4, E5, E15, E16; S1–S4 (parte de pedidos).
- **Verificación:** `uv run python -m pytest -q tests/test_customer_metrics.py -k "dedup or null or joins"`
  → pasan.

### T5 · Importes en EUR y fecha en Madrid

- **Qué:** `to_eur(amount, currency)` con `Decimal` y `ROUND_HALF_UP` por registro (R5), y
  `madrid_date(ts)` con `zoneinfo` (R6). Los valores ISO con `Z` se interpretan como UTC; si no
  tienen zona, son `invalid_record`.
- **Archivos:** `kivora/customer_metrics.py`.
- **Cubre:** R5, R6; E12, E17.
- **Verificación:** `uv run python -m pytest -q tests/test_customer_metrics.py -k "net or madrid"`
  → pasan (verano e invierno).

### T6 · Devoluciones

- **Qué:** `classify_refunds`, en el orden de spec §4 (antes de R8):
  1. `refund_id` vacío → `invalid_record`;
  2. agrupación por `refund_id` (R9);
  3. validación de la aparición que queda (R8);
  4. pedido (R10);
  5. `apply_refund_limit` por (`refunded_at`, `refund_id`), en la moneda del pedido (R11).
- **Archivos:** `kivora/customer_metrics.py`.
- **Cubre:** R8–R12; E6–E11, E13; S1–S6.
- **Verificación:** `uv run python -m pytest -q tests/test_customer_metrics.py -k refund` → pasan.

### T7 · Agregación por cliente y día

- **Qué:** `build_metrics`: unión de las claves de ventas y de devoluciones aceptadas (R13), sumas
  de importes redondeados, `net`, `refunds_count`, país actual y `last_purchase_date`, calculada con
  las fechas de venta de cada cliente ordenadas y `bisect` (no O(n²), por los volúmenes
  desconocidos).
- **Archivos:** `kivora/customer_metrics.py`.
- **Cubre:** R13, R14; E5, E13, E14, E18 (totales).
- **Verificación:** `uv run python tasks.py test` → todos los tests de T3 en verde salvo los de
  ficheros y determinismo.

### T8 · Salidas, controles e integración

- **Qué:**
  - `kivora/outputs.py`:
    - CSV en UTF-8 sin BOM, `\n`, cabecera siempre e importes con `f"{d:.2f}"` sobre `Decimal`.
    - Orden de filas de spec §3.1/§3.2.
    - `quality_report.json` con `indent=2`, las claves en orden y `\n` final.
    - Tablas `daily_customer_metrics` y `rejected` en `warehouse.db`.
  - `quality_checks`: los tres controles de §3.3, calculados sobre la salida.
  - `detail` de `rejected.csv`: `"<fichero>#<_pos>: <explicación>"`, para distinguir las filas que
    coinciden en el resto de columnas (por ejemplo, dos devoluciones sin `refund_id`).
  - `pipeline.run`: llama a todo después de los SQL actuales y amplía el mensaje final con los
    ficheros nuevos.
- **Archivos:** `kivora/outputs.py`, `kivora/customer_metrics.py`, `kivora/pipeline.py`.
- **Cubre:** R12, R15, R16, R17, R18; E18, E19.
- **Verificación:**
  - `uv run python tasks.py test` → todo verde.
  - `uv run python tasks.py acceptance` → todo `PASS`, código 0.

### T9 · `check` con las salidas nuevas

- **Qué:** `kivora/check.py`:
  - añadir los tres ficheros nuevos con sus columnas;
  - aplicar `gross_amount >= 0` solo a los ficheros que tienen esa columna. Hoy fallaría con
    `KeyError` sobre `rejected.csv`;
  - para `quality_report.json`, comprobar solo su estructura.
  - **No** se exige `net_amount >= 0`: puede ser negativo (D1).
- **Archivos:** `kivora/check.py`.
- **Cubre:** R16 (forma).
- **Verificación:** `uv run python tasks.py run` y después `uv run python tasks.py check` → `OK`.

### T10 · Comprobar que los tests detectan el código roto

- **Qué:** para cada uno de los siete tests mínimos, introducir a mano el defecto de la columna
  "Falla si…" de T3 y confirmar que el test falla. Por ejemplo: quitar el desempate de la última
  versión, cambiar `ROUND_HALF_UP` por `ROUND_HALF_EVEN`, fijar UTC+2, unir con todos los pagos o no
  deduplicar `refund_id`. Después se deshace el cambio (`git checkout -- kivora/`), sin commit del
  defecto.
- **Archivos:** ninguno en el resultado final; la tabla de defectos y resultados va a
  `docs/report.md`.
- **Cubre:** el requisito de `assignment.md` §4 ("un test que pasaría con el código roto no
  cuenta").
- **Verificación:** cada defecto da al menos un test en rojo; al deshacerlo, `tasks.py test` vuelve a
  verde.

### T11 · Tests existentes

- **Qué:** los 4 tests de `tests/test_pipeline.py` se dejan **sin cambios**. Con D5, `daily_sales`
  queda fuera de alcance y no se modifica, así que siguen pasando.
  `test_gross_matches_source_total` contradice el contrato de `daily_sales`: no convierte divisas
  ni usa la última versión (`docs/analysis.md` §3). Según `CLAUDE.md` no se adapta en silencio: se
  documenta en `docs/report.md` como test que fija un defecto conocido, para reescribirlo cuando se
  corrija `daily_sales`.
- **Archivos:** ninguno (solo documentación).
- **Verificación:** `uv run python tasks.py test` → los 4 pasan sin modificación (`git diff --stat
  tests/test_pipeline.py` vacío).

### T12 · Documentación y respuesta a Finanzas

- **Qué:**
  - `docs/sources.md`: sección `refunds.json`.
  - Nuevo contrato `docs/data-contracts/daily_customer_metrics.md`, que resume spec §3.
  - `README.md` y `CLAUDE.md`: salidas nuevas y comando `uv run python tasks.py acceptance`.
  - `docs/report.md`: ciclo de iteración, trazabilidad R → E/S → test, tabla de T10 y decisión de T11.
  - Respuesta en `docs/tickets/KIV-101.md`, en lenguaje de negocio, con las cifras de E18.
- **Archivos:** los citados.
- **Verificación:** cada afirmación nueva con su archivo:línea o comando (regla de `CLAUDE.md`);
  `uv run python tasks.py test`, `check` y `acceptance` en verde como cierre de la fase 4.

## 4. Riesgos y mitigación

| Riesgo | Mitigación |
| --- | --- |
| Que un importe pase por `float` (JSON, SQLite REAL o `round()`) y cambie un céntimo | `parse_float=Decimal`; importes como TEXT en SQLite; solo `quantize(ROUND_HALF_UP)`; test 6 y defecto de T10 |
| Que la fecha use un desfase fijo y falle en invierno | `zoneinfo` más `tzdata` (ya en `pyproject.toml`); test de invierno en T3 |
| Ajustarse a la muestra (ids o fechas en el código) | Reglas generales en la especificación; tests sintéticos; antes de cerrar, `grep -rnE "K-1[0-9]{4}\|R-10[0-9]{2}" kivora/ sql/` sin resultados salvo en `kivora/acceptance.py` |
| Que el oráculo y el pipeline compartan el mismo error, porque los escribe el mismo agente | Filas literales de E1–E18 contrastadas por Ana con un cálculo independiente; S1–S8 con resultado razonado a mano; T10 |
| Salida no determinista (orden de diccionarios o ficheros, `\r\n` en Windows) | Orden explícito en §3.1/§3.2; `newline=""` y `lineterminator="\n"`; SHA-256 de dos ejecuciones en `acceptance` |
| Romper `daily_sales` o la interfaz | No se tocan `sql/`, `top_customers` ni las opciones; T2 compara `daily_sales.csv` byte a byte con T0; los 4 tests antiguos siguen igual |
| `check` falla con los ficheros nuevos (`KeyError` en `rejected.csv`) | T9 |
| Filas de `rejected.csv` imposibles de distinguir | `detail` con fichero y posición (T8) |
| CSV de entrada con BOM o columnas que faltan | Leer con `utf-8-sig`; una columna obligatoria que falta en un fichero es `InputError` con la ruta (como S7). Se propone en la revisión: no está en la especificación |
| Volúmenes mayores en los datos desconocidos | `last_purchase_date` con `bisect`; sin bucles cuadráticos |
| Que el agente siga trabajando con `acceptance` en rojo, o lo dé por terminado sin ejecutarlo | `acceptance` como condición de parada (hook `Stop` o skill en la fase 3); criterio de terminado de `CLAUDE.md` |
| Modificar `data/inbox/` sin querer | El pipeline solo escribe en `--out`; hash de `data/inbox/` en `acceptance`; permisos de la fase 3 |
