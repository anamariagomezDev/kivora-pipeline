# KIV-101 · Especificación: devoluciones y métricas diarias por cliente

- **Ticket:** `docs/tickets/KIV-101.md`
- **Estado:** aprobada por Ana tras revisión (fase 2). No se ha modificado código.
- **Nota de estado (2026-11-19).** Lo anterior describe la fase 2 y se mantiene como registro.
  Hoy KIV-101 está implementada (`kivora/customer_metrics.py`, `kivora/outputs.py`). R8 y R9
  están modificados por KIV-102 (`docs/specs/KIV-102/spec.md`), y R2 y el R9 de KIV-102 tienen
  una nota de la revisión independiente (`docs/review.md`, H1 y H2). Todos los escenarios de §5 y
  §6 se ejecutan con `uv run python tasks.py acceptance`: S7 y S8 también (contra lo que dice §6,
  escrito antes de implementarlos), además de S14, añadido tras la revisión. Con el código en
  `d450965`, el resultado es 70 PASS, 0 FAIL.
- **Decisiones:** Ana, a partir de la propuesta del agente (sección [Aclaraciones](#aclaraciones)).
- **Datos de referencia:** `data/inbox/2026-09-01` … `2026-09-07` y `data/reference/fx_rates.csv`
  (EUR 1.0, GBP 1.17, USD 0.92).

## 1. Objetivo

Añadir al pipeline las devoluciones (`refunds.json`) y producir para Finanzas una tabla diaria por
cliente, `daily_customer_metrics`, que cuadre con contabilidad: en EUR, sin pedidos contados dos
veces y sin perder ningún registro en silencio. Todo pedido o devolución que no se use queda en
`rejected.csv` con su motivo, y el resultado de los controles de calidad en `quality_report.json`.

## 2. Fuera de alcance

- **Corregir `daily_sales` y `top_customers`.** Siguen generándose como hoy, con los defectos
  documentados en `docs/analysis.md` (fecha UTC, sin conversión de divisas, duplicidad tras el JOIN
  con pagos, país vacío). Es un defecto conocido que se trata aparte (A18).
- **Cuadrar lo cobrado con el total del pedido.** No hay control de que la suma de pagos `captured`
  coincida con `total_amount` (A2, riesgo aceptado: K-10151 tiene 64.00 capturados y un total de 58.50).
- **Coherencia temporal** entre `refunded_at` y `created_at` (una devolución anterior a su pedido no
  se rechaza).
- **El cambio de formato de `refunds.json`** (KIV-102).
- Cambiar la interfaz `python -m kivora` o sus opciones.

## 3. Salidas

Todas en la carpeta `--out`. El pipeline nunca escribe en `--inbox` ni en `--reference`.

### 3.1 `daily_customer_metrics.csv`

Grano: una fila por (`metric_date`, `customer_id`) con al menos una venta o una devolución aceptada.

| Columna | Tipo / formato | Definición |
| --- | --- | --- |
| `metric_date` | fecha `AAAA-MM-DD` | Día natural en `Europe/Madrid` (R6) |
| `customer_id` | texto | Cliente |
| `country` | texto | País actual del cliente, ISO alfa-2 en mayúsculas; `UNKNOWN` si vacío o si el cliente no existe (R7) |
| `orders_count` | entero ≥ 0 | Ventas del cliente ese día (R4) |
| `gross_amount` | decimal, 2 decimales | Suma de las ventas en EUR (R5) |
| `refunded_amount` | decimal, 2 decimales | Suma de las devoluciones aceptadas en EUR, por día de devolución (R6, R11) |
| `net_amount` | decimal, 2 decimales, puede ser negativo | `gross_amount − refunded_amount` |
| `refunds_count` | entero ≥ 0 | Devoluciones aceptadas ese día |
| `last_purchase_date` | fecha `AAAA-MM-DD` o vacío | Última fecha de venta del cliente **≤ `metric_date`**; vacío si no hay ninguna |

Orden de filas: `metric_date`, `customer_id` (ascendente, comparación de texto).

### 3.2 `rejected.csv`

Un registro por cada aparición de pedido o devolución que no se ha usado.

| Columna | Definición |
| --- | --- |
| `source` | `orders` o `refunds` |
| `record_id` | `order_id` o `refund_id` |
| `reason` | Uno de la lista cerrada de abajo |
| `inbox_day` | Carpeta de `--inbox` de la que procede el registro rechazado |
| `detail` | Texto explicativo determinista (no se valida su contenido) |

Lista cerrada de `reason`, en **orden de prioridad** (un registro se rechaza solo por el primero que
cumpla):

| source | reason | Cuándo |
| --- | --- | --- |
| orders | `invalid_record` | Falta un campo obligatorio, fecha no ISO 8601, `total_amount` no numérico o ≤ 0, `status` fuera de `confirmed`/`cancelled` |
| orders | `unknown_currency` | La moneda no está en `fx_rates.csv` |
| orders | `not_sale_cancelled` | La última versión está cancelada |
| orders | `not_sale_unpaid` | Ningún pago `captured` |
| refunds | `invalid_record` | `refund_id` vacío (tras quitar espacios): se rechaza directamente, cada aparición por separado, sin pasar por la detección de duplicados |
| refunds | `conflicting_duplicate` | El mismo `refund_id` llega con contenido distinto (se rechazan todas sus apariciones, sin validarlas) |
| refunds | `duplicate_refund` | Copia idéntica de la primera aparición de ese `refund_id` (las copias se rechazan aunque la primera aparición resulte inválida) |
| refunds | `invalid_record` | La primera aparición tiene un campo obligatorio vacío, `refunded_at` no ISO 8601 o `amount` no numérico o ≤ 0 |
| refunds | `unknown_currency` | La moneda no está en `fx_rates.csv` |
| refunds | `order_not_found` | El `order_id` no está en ningún `orders.csv` |
| refunds | `order_not_sale` | El pedido existe pero no es venta (rechazado por cualquiera de los motivos de `orders`) |
| refunds | `currency_mismatch` | Moneda distinta de la del pedido |
| refunds | `refund_exceeds_order` | Con ella, lo devuelto del pedido supera su total (R11) |

**No van** a `rejected.csv` las copias exactas de pedidos ni sus versiones antiguas: es el
funcionamiento normal descrito en `docs/sources.md` y el pedido sí se usa (una vez).

Orden de filas: `source`, `record_id`, `inbox_day`, `reason`.

### 3.3 `quality_report.json`

```json
{
  "checks": [
    {"name": "net_equals_gross_minus_refunded", "passed": true, "failed_records": 0},
    {"name": "refunds_within_order_total", "passed": true, "failed_records": 0},
    {"name": "unique_keys_and_orders", "passed": true, "failed_records": 0}
  ]
}
```

| Control | Granularidad | `failed_records` cuenta |
| --- | --- | --- |
| `net_equals_gross_minus_refunded` | Fila de `daily_customer_metrics` | Filas donde `net_amount ≠ gross_amount − refunded_amount` |
| `refunds_within_order_total` | Pedido | Pedidos cuya suma de devoluciones **aceptadas**, en su moneda, supera `total_amount` |
| `unique_keys_and_orders` | Fila y pedido | Claves (`metric_date`, `customer_id`) repetidas + `order_id` que se agregan más de una vez |

`passed` es `true` si y solo si `failed_records = 0`. Los controles se calculan sobre la salida
producida, no sobre la entrada. Por R11, el segundo actúa como salvaguarda: con datos correctos
siempre pasa; los excesos de la entrada se ven en `rejected.csv`.

### 3.4 Formato y determinismo

- CSV en UTF-8 sin BOM, separador `,`, fin de línea `\n`, con cabecera aunque no haya filas.
- Importes con exactamente dos decimales y punto (`-21.83`, `0.00`); sin notación científica.
- JSON en UTF-8, sangría de 2 espacios, claves en el orden mostrado, `\n` final.
- Ninguna salida contiene marcas de tiempo de ejecución, rutas absolutas ni nada que dependa del
  orden del sistema de ficheros: dos ejecuciones sobre la misma entrada producen ficheros idénticos
  byte a byte.

## 4. Requisitos

Generales: no dependen de ningún identificador, fecha ni moneda concretos de la muestra.

**Entrada**

- **R1.** Se leen todas las carpetas de `--inbox` en orden de nombre. En cada una, `orders.csv`,
  `customers.csv`, `payments.csv` y, si existe, `refunds.json`. Un `refunds.json` ausente o `[]`
  aporta cero devoluciones. Un `refunds.json` que no es JSON válido detiene el pipeline con un
  mensaje que nombra el fichero y código de salida ≠ 0 (A19). Las salidas se calculan siempre sobre
  todo el `--inbox`, de modo que un registro que llega en una entrega posterior se tiene en cuenta en
  la ejecución siguiente.

  *Nota (revisión del plan, P3):* los CSV se leen como `utf-8-sig`, de modo que un BOM inicial no
  altera el nombre de la primera columna. No se valida que falten columnas: el formato de entrada
  está garantizado.

**Pedidos**

- **R2.** De cada `order_id` se usa solo la última versión: mayor `updated_at`; si empata, la de la
  carpeta posterior y, dentro de ella, la fila posterior. Copias y versiones antiguas no se agregan
  ni se rechazan.

  *Nota (2026-11-19, revisión independiente, `docs/review.md` H2, aprobada por Ana):* `updated_at`
  se compara **como instante**, no como texto, para que las fracciones de segundo y los desfases
  horarios ordenen bien (`…10:00:00.500Z` es posterior a `…10:00:00Z`). Un `updated_at` vacío o que
  no es ISO 8601 con zona queda por debajo de cualquier fecha válida; si esa versión acaba siendo la
  última, R3 la rechaza. Lo comprueban S14 y `tests/test_customer_metrics.py`.
- **R3.** La última versión se valida (campos obligatorios no vacíos tras quitar espacios, fechas
  ISO 8601, `total_amount` numérico > 0, `status` válido, moneda en `fx_rates.csv` comparada en
  mayúsculas). Si falla, el pedido se rechaza con `invalid_record` o `unknown_currency`.
- **R4.** Un pedido válido es **venta** si su última versión no está cancelada y tiene al menos un
  pago `captured` (de cualquier día). Si no, se rechaza con `not_sale_cancelled` o
  `not_sale_unpaid`. Cada venta cuenta **una vez**, tenga los pagos que tenga.
- **R5.** El importe en EUR de cada venta y de cada devolución es `importe × rate_to_eur` con
  aritmética decimal (no binaria), redondeado a 2 decimales con medio hacia arriba **registro a
  registro**. Las sumas se hacen sobre los importes ya redondeados. El bruto de una venta es el
  `total_amount` de su última versión.
- **R6.** La fecha de una venta es el día natural en `Europe/Madrid` de `created_at`; la de una
  devolución, el de `refunded_at`. Se usa la base de datos de zonas horarias (horario de verano
  incluido), no un desfase fijo. La carpeta de llegada no interviene.

**Clientes**

- **R7.** De cada cliente se usa la última fila recibida (carpeta posterior, fila posterior). El
  país se normaliza (sin espacios, en mayúsculas); si queda vacío, o el cliente no está en ningún
  `customers.csv`, es `UNKNOWN`. Una venta nunca se rechaza por su cliente. Todas las filas de un
  cliente llevan su país actual.

**Devoluciones**

Las devoluciones se tratan en este orden: primero las que no tienen `refund_id` (R8), después
los duplicados (R9), después la validación de la aparición que queda (R8), después el pedido (R10)
y por último el límite (R11).

- **R8.** Una devolución con `refund_id` vacío (tras quitar espacios) se rechaza directamente con
  `invalid_record`, cada aparición por separado, y no entra en R9. De cada `refund_id` no vacío,
  solo la aparición que queda tras R9 se valida: `order_id`, `refunded_at` y `currency` no vacíos, `refunded_at` ISO 8601, `amount` numérico > 0 y
  moneda en `fx_rates.csv`. Si falla: `invalid_record` o `unknown_currency`.
- **R9.** Antes de validar, las devoluciones con `refund_id` no vacío se agrupan por `refund_id`
  (sin espacios). Si todas las
  apariciones de un `refund_id` tienen contenido idéntico, se queda la primera (carpeta anterior,
  posición anterior) y cada copia se rechaza con `duplicate_refund`. Si el contenido difiere, se
  rechazan todas con `conflicting_duplicate` y ninguna pasa a R8. Dos devoluciones con distinto
  `refund_id` son siempre distintas.

  *Nota (KIV-102):* R8 y R9 están modificados por `docs/specs/KIV-102/spec.md`. Aceptan los dos
  formatos de `refunds.json` (`amount` o `refund_amount`) y comparan el registro normalizado, sin
  `reason`.
- **R10.** Una devolución cuyo pedido no existe se rechaza con `order_not_found`; si el pedido
  existe pero no es venta, con `order_not_sale`; si su moneda no es la del pedido, con
  `currency_mismatch`.
- **R11.** Las devoluciones restantes de cada pedido se procesan en orden de (`refunded_at`,
  `refund_id`). Se acepta una si la suma de las ya aceptadas más ella, **en la moneda del
  pedido**, no supera `total_amount`; si lo supera, se rechaza **entera** con
  `refund_exceeds_order` y se sigue con la siguiente.
- **R12.** Cada registro rechazado genera una fila en `rejected.csv` con el primer motivo según la
  prioridad de 3.2.

**Métricas**

- **R13.** Hay una fila por cada (`metric_date`, `customer_id`) con al menos una venta o una
  devolución aceptada; las filas solo con devoluciones llevan `orders_count = 0` y
  `gross_amount = 0.00`. No hay filas sin actividad. `metric_date` puede ser un día sin carpeta en
  `--inbox` (una venta a las 23:30 UTC del último día cae al día siguiente).
- **R14.** Las columnas se calculan como en 3.1. `net_amount` puede ser negativo.

**Calidad, formato y ejecución**

- **R15.** `quality_report.json` contiene exactamente los tres controles de 3.3, en ese orden.
- **R16.** Las salidas cumplen el formato y el orden de 3.1–3.4 y son deterministas.
- **R17.** Con entrada legible, el pipeline termina con código 0 aunque haya rechazos o falle algún
  control.
- **R18.** La interfaz `uv run python -m kivora --inbox --reference --out` no cambia, y siguen
  generándose `daily_sales.csv`, `top_customers.csv` y `warehouse.db`.

## 5. Escenarios de aceptación con los datos reales

**Cómo se han calculado.** Con el cálculo de referencia `docs/specs/KIV-101/reference_calc.py`
([Anexo A](#anexo-a--cálculo-de-referencia)), que aplica estos requisitos de forma independiente del
pipeline. Desde la raíz del repositorio:

```bash
# totales y rechazos (E18)
uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary
# todas las filas esperadas de los escenarios E1–E17
uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference \
  2026-09-01,C009 2026-09-02,C021 2026-09-04,C021 2026-09-04,C014 2026-09-04,C010 \
  2026-09-01,C007 2026-09-04,C032 2026-09-04,C011 2026-09-06,C011 2026-09-05,C022 \
  2026-09-07,C022 2026-09-05,C028 2026-09-04,C002 2026-09-05,C002 2026-09-07,C027 \
  2026-09-07,C020 2026-09-04,C020 2026-09-04,C018 2026-09-06,C006 2026-09-02,C024 \
  2026-09-04,C022 2026-09-03,C021 2026-09-05,C014
```

Las dos últimas claves (`2026-09-03,C021` y `2026-09-05,C014`) no deben aparecer en la salida
(E2 y E11).

La columna **Evidencia en la entrada** es el `grep` (Git Bash, desde la raíz) que muestra los
registros de origen. Las filas esperadas siguen el orden de columnas de 3.1.

| ID | Caso | Evidencia en la entrada | Resultado esperado | Requisitos |
| --- | --- | --- | --- | --- |
| E1 | Pedido duplicado en el mismo fichero | `grep -h '^K-10059,' data/inbox/*/orders.csv` → 2 filas idénticas (C009, 45.90 EUR, 09-01) | `2026-09-01,C009,ES,1,45.90,0.00,45.90,0,2026-09-01`; K-10059 no está en `rejected.csv` | R2, R4, R13 |
| E2 | Pedido reenviado otro día, con devolución | `grep '^K-10060,' data/inbox/*/orders.csv` → en 09-02 y 09-03 (C021, 67.25 GBP); `grep -A3 '"R-1017"' data/inbox/*/refunds.json` → 33.62 GBP el 09-04 | `2026-09-02,C021,GB,1,78.68,0.00,78.68,0,2026-09-02`; no hay fila `2026-09-03,C021`; `2026-09-04,C021,GB,1,203.83,39.34,164.49,1,2026-09-04` (K-10075: 174.21 GBP = 203.83; R-1017 = 39.34 una sola vez) | R2, R5, R11, R15 (control 3) |
| E3 | Versión cancelada (K-10149) | `grep '^K-10149,' data/inbox/*/orders.csv` → `confirmed` 09-04, `cancelled` 09-05 (C014, 75.00 EUR, pago P-30159 `captured`) | `2026-09-04,C014,ES,2,244.19,0.00,244.19,0,2026-09-04` (K-10082 23.74 + K-10087 220.45, sin K-10149); `orders,K-10149,not_sale_cancelled,2026-09-05` | R2, R4, R12 |
| E4 | Versión con importe cambiado (K-10151) | `grep '^K-10151,' data/inbox/*/orders.csv` → 64.00 el 09-04, 58.50 el 09-05 (C010) | `2026-09-04,C010,ES,2,258.32,0.00,258.32,0,2026-09-04` (K-10076 199.82 + K-10151 **58.50**); K-10151 no está en `rejected.csv` | R2, R5 |
| E5 | Cliente sin país | `grep -E '^C0(07\|32),' data/inbox/*/customers.csv` → `country` vacío | `2026-09-01,C007,UNKNOWN,2,246.66,0.00,246.66,0,2026-09-01` (K-10009 166.04 + K-10066 80.62); `2026-09-04,C032,UNKNOWN,1,139.44,0.00,139.44,0,2026-09-04` (K-10081) | R7 |
| E6 | Devolución parcial | `grep -A3 '"R-1001"' data/inbox/*/refunds.json` → K-10068 (C011, 89.90 EUR), 20.0 EUR el 09-04 | `2026-09-04,C011,ES,1,49.04,20.00,29.04,1,2026-09-04` (compra K-10077 49.04) | R6, R11, R14 |
| E7 | Varias devoluciones del mismo pedido | `grep -B1 '"K-10068"' data/inbox/*/refunds.json` → R-1001 (20.0, 09-04) y R-1007 (15.5, 09-06): 35.50 ≤ 89.90 | Las dos aceptadas, cada una en su día: E6 y `2026-09-06,C011,ES,2,164.64,15.50,149.14,1,2026-09-06` (K-10109 100.45 + K-10117 64.19) | R6, R11 |
| E8 | Devolución sin pedido | `grep -A1 '"R-1003"' data/inbox/*/refunds.json` → K-19999, 25.0 EUR; `grep -c '^K-19999,' data/inbox/*/orders.csv` → 0 en todos | `refunds,R-1003,order_not_found,2026-09-05` | R10, R12 |
| E9 | Devoluciones que superan el pedido | `grep '^K-10148,' data/inbox/*/orders.csv` → C022, 100.00 USD; `grep -B1 -A2 '"K-10148"' data/inbox/*/refunds.json` → R-1004 60.0 USD (09-05) y R-1009 50.0 USD (09-07) | R-1004 aceptada: `2026-09-05,C022,US,2,85.59,55.20,30.39,1,2026-09-05`; R-1009 rechazada: `refunds,R-1009,refund_exceeds_order,2026-09-07`; `2026-09-07,C022,US,1,56.19,0.00,56.19,0,2026-09-07`; `refunds_within_order_total` con `failed_records = 0` | R11, R12, R15 |
| E10 | Devolución duplicada | `grep -n '"R-1006"' data/inbox/*/refunds.json` → en 09-05 y 09-06, idénticas (K-10157, C028, 12.0 EUR, `2026-09-05T16:20:00Z`) | `2026-09-05,C028,ES,1,39.21,12.00,27.21,1,2026-09-05` (12.00 una vez); `refunds,R-1006,duplicate_refund,2026-09-06` | R9, R12 |
| E11 | Devolución de pedido cancelado | `grep -A3 '"K-10149"' data/inbox/*/refunds.json` → R-1005, 75.0 EUR el 09-05 | `refunds,R-1005,order_not_sale,2026-09-05`; no hay fila `2026-09-05,C014` | R10, R12 |
| E12 | Pedido que cambia de día en Madrid | `grep -E '^K-1014[34],' data/inbox/*/orders.csv` → K-10143 (C002, `2026-09-04T22:30:35Z`, 188.26 EUR) y K-10144 (C027, `2026-09-06T23:50:14Z`, 94.09 EUR) | `2026-09-04,C002,ES,2,405.40,…` (K-10078 202.96 + K-10085 202.44, sin K-10143); `2026-09-05,C002,ES,2,263.75,0.00,263.75,0,2026-09-05` (K-10143 188.26 + K-10099 75.49); `2026-09-07,C027,ES,3,409.09,0.00,409.09,0,2026-09-07` (K-10125 208.85 + K-10128 106.15 + K-10144 94.09) | R6 |
| E13 | Devolución que cambia de día en Madrid y fila solo con devoluciones | `grep -B1 -A3 '"R-1008"' data/inbox/*/refunds.json` → K-10152 (C020), 20.0 EUR, `2026-09-06T22:40:00Z`, en el fichero del 09-06 | `2026-09-07,C020,ES,0,0.00,20.00,-20.00,1,2026-09-06` (no suma al 09-06; `last_purchase_date` = K-10111 del 09-06) | R6, R13, R14 |
| E14 | Fila solo con devoluciones de una compra antigua | `grep -A3 '"R-1014"' data/inbox/*/refunds.json` → K-10001 (C020, comprado el 09-01), 21.83 EUR el 09-04 | `2026-09-04,C020,ES,0,0.00,21.83,-21.83,1,2026-09-01` (`last_purchase_date` no mira al futuro: C020 vuelve a comprar el 09-05) | R13, R14 |
| E15 | Varios pagos capturados | `grep -E ',K-1014[56],' data/inbox/*/payments.csv` → K-10145: 84.00 + 126.00 GBP; K-10146: 53.80 + 80.70 EUR | `2026-09-04,C018,GB,1,245.70,0.00,245.70,0,2026-09-04` (210.00 GBP × 1.17, una venta); `2026-09-06,C006,ES,1,134.50,0.00,134.50,0,2026-09-06` | R4, R5, R15 (control 3) |
| E16 | Pedido sin pago capturado | `grep ',K-10062,' data/inbox/*/payments.csv` → dos `failed` (C024, 99.00 EUR) | `2026-09-02,C024,ES,1,197.51,0.00,197.51,0,2026-09-02` (solo K-10020); `orders,K-10062,not_sale_unpaid,2026-09-02` | R4, R12 |
| E17 | Conversión de moneda y redondeo por registro | `grep -E '^K-10(070\|079\|148),' data/inbox/*/orders.csv` → C022, 179.88 + 73.56 + 100.00 USD el 09-04 | `2026-09-04,C022,US,3,325.17,0.00,325.17,0,2026-09-04` (165.49 + 67.68 + 92.00; redondear solo el total daría 325.16) | R5 |
| E18 | Totales y rechazos | `… --summary` | 156 ventas; bruto 18490.74; devuelto 1264.19; neto 17226.55; 126 filas, 11 solo con devoluciones, 12 con neto negativo. `rejected.csv` tiene exactamente 6 filas: K-10062 `not_sale_unpaid`, K-10149 `not_sale_cancelled`, R-1003 `order_not_found`, R-1005 `order_not_sale`, R-1006 `duplicate_refund` (09-06), R-1009 `refund_exceeds_order`. Los tres controles con `passed: true` y `failed_records: 0` | R12–R15 |
| E19 | Determinismo e interfaz | Ejecutar dos veces `uv run python -m kivora --inbox data/inbox --reference data/reference --out <dir>` en dos `<dir>` distintos | Código 0; los tres ficheros nuevos con el mismo SHA-256 en las dos ejecuciones; `data/inbox/` sin cambios (`git status --porcelain data/` vacío); siguen existiendo `daily_sales.csv`, `top_customers.csv` y `warehouse.db` | R16, R17, R18 |

## 6. Escenarios sintéticos

Para casos que la muestra no trae. Se construyen en una carpeta temporal **fuera del repositorio**;
nunca en `data/inbox/`. S1–S6 se han verificado con el cálculo de referencia
(`uv run python -I docs/specs/KIV-101/reference_calc.py <tmp>/inbox data/reference --summary` y
sin `--summary` para las filas); S7 y S8 no se han ejecutado.

**Base S (un día, `2026-09-01`).** `customers.csv`: `C1,Cliente Uno,ES,2025-01-01`. Pedidos, todos
`confirmed` y con un pago `captured` por su importe:

| order_id | customer_id | created_at | currency | total_amount |
| --- | --- | --- | --- | --- |
| K-1 | C1 | 2026-09-01T10:00:00Z | EUR | 10.00 |
| K-2 | C1 | 2026-09-01T11:00:00Z | JPY | 1000 |
| K-3 | C1 | 2026-09-01T12:00:00Z | EUR | 0.00 |
| K-4 | *(vacío)* | 2026-09-01T13:00:00Z | EUR | 15.00 |
| K-5 | C9 | 2026-09-01T14:00:00Z | EUR | 20.00 |

`refunds.json`: R-2 (K-1, 500 JPY), R-3 (K-1, −5.0 EUR), R-4 (`order_id` vacío, 3.0 EUR) y dos
devoluciones sin `refund_id`, distintas entre sí: `refund_id` = `""` (K-1, 1.0 EUR,
`2026-09-01T16:00:00Z`) y `refund_id` = `"  "` (K-1, 2.0 EUR, `2026-09-01T16:10:00Z`).

| ID | Caso | Resultado esperado | Requisitos |
| --- | --- | --- | --- |
| S1 | Moneda desconocida | `orders,K-2,unknown_currency`; `refunds,R-2,unknown_currency` | R3, R8 |
| S2 | Importe ≤ 0 | `orders,K-3,invalid_record`; `refunds,R-3,invalid_record` | R3, R8 |
| S3 | Campo obligatorio vacío | `orders,K-4,invalid_record`; `refunds,R-4,invalid_record`; las dos devoluciones sin `refund_id` dan **dos** filas `refunds,,invalid_record` (no `conflicting_duplicate`) y no suman a K-1 | R3, R8, R9 |
| S4 | Cliente inexistente | `2026-09-01,C9,UNKNOWN,1,20.00,0.00,20.00,0,2026-09-01` (la venta no se pierde) | R7 |
| S1–S4 | Conjunto | `daily_customer_metrics.csv` = `2026-09-01,C1,ES,1,10.00,0.00,10.00,0,2026-09-01` y la fila de S4; 8 filas en `rejected.csv`; código 0 | R12, R13, R17 |

**Base T (dos días).** Pedido K-1 (C1, 10.00 EUR, `captured`) el `2026-09-01`.
`2026-09-01/refunds.json`: R-5 (K-1, 2.0 EUR, `2026-09-01T15:00:00Z`) y R-6 (K-1, 3.0 **GBP**).
`2026-09-02/refunds.json`: R-5 con el mismo contenido salvo `amount` 4.0.

| ID | Caso | Resultado esperado | Requisitos |
| --- | --- | --- | --- |
| S5 | Mismo `refund_id` con contenido distinto | `refunds,R-5,conflicting_duplicate` en `2026-09-01` y en `2026-09-02` | R9 |
| S6 | Moneda distinta de la del pedido | `refunds,R-6,currency_mismatch` | R10 |
| S7 | `refunds.json` que no es JSON válido | Código ≠ 0 y mensaje que nombra el fichero | R1 |
| S8 | Día sin `refunds.json` o con `[]` | Mismo resultado que sin devoluciones ese día, código 0 | R1 |
| S14 | Pedido K-1 (C1, EUR, `captured`): en `2026-09-01`, `updated_at` `2026-09-01T10:00:00.500Z` y 12.00; en `2026-09-02`, `updated_at` `2026-09-01T10:00:00Z` y 99.00 (añadido tras la revisión, H2). Se comprueba sobre la salida y sobre `reference_calc.py` | `2026-09-01,C1,ES,1,12.00,0.00,12.00,0,2026-09-01`; ningún rechazo | R2 |

## Aclaraciones

Cada ambigüedad del ticket y de los datos, con las opciones, la decisión y el motivo. **Decidido
por:** Ana, a partir de la propuesta del agente. Donde Ana precisó o cambió la propuesta, se indica.

**A1. Qué cuenta como pedido (`orders_count`, `gross_amount`).**
Opciones: (a) venta según el contrato de `daily_sales` (última versión, no cancelada, ≥ 1 pago
`captured`); (b) todo pedido recibido. Con (b), C024 sumaría el 09-02 los 99.00 EUR de K-10062, que
no se cobraron. **Decisión:** (a) (D3). **Motivo:** es la definición ya contratada y la que cuadra
con lo cobrado. → R4.

**A2. Bruto: `total_amount` de la última versión o suma de pagos capturados.**
Difieren en K-10151 (58.50 frente a 64.00). **Decisión:** `total_amount` de la última versión, sin
control de cuadre con los pagos (riesgo aceptado: no entra entre los tres controles de A16;
confirmado expresamente por Ana).
**Motivo:** es el importe del pedido vigente; el cuadre con cobros es otro análisis. → R5, §2.

**A3. Día de una compra.**
Opciones: día en `Europe/Madrid` o día UTC de `created_at`. K-10144 (`2026-09-06T23:50:14Z`) cae el
09-07 o el 09-06. **Decisión:** Madrid, con `zoneinfo`. **Motivo:** coherencia con el contrato de
`daily_sales`; un desfase fijo fallaría en invierno (+1). → R6.

**A4. Día al que se atribuye una devolución.**
Opciones: (a) día de `refunded_at` en Madrid: aparecen filas solo con devoluciones y netos negativos
(C020 el 09-04: −21.83), pero los días pasados no cambian; (b) día de la compra: sin netos
negativos, pero reescribe cifras ya publicadas (el 09-01 de C020 cambia el 09-04); (c) día del
fichero: R-1008 contaría el 09-06 aunque en Madrid es el 09-07. **Decisión:** (a), en
`Europe/Madrid`; se aceptan netos negativos (D1, precisión de Ana). **Motivo:** contabilidad
registra el movimiento el día que ocurre. → R6, R14.

**A5. Filas sin compras.**
Opciones: crear la fila con `orders_count = 0`, o no. Sin ella se perderían devoluciones (11 filas,
como E14). **Decisión:** crearla; no hay filas sin actividad. **Motivo:** que la tabla cuadre con
las devoluciones aceptadas. → R13.

**A6. `last_purchase_date`.**
Opciones: (a) última venta ≤ `metric_date`; (b) última de todo el histórico; (c) solo la del día.
Para C020 el 09-04: (a) 09-01, (b) 09-06, (c) vacío. **Decisión:** (a), solo ventas, día en Madrid;
vacío si no hay ninguna. **Motivo:** estable y sin mirar al futuro. → §3.1, R14.

**A7. `refunds_count`.**
Opciones: contar todas o solo las aceptadas. **Decisión:** solo las aceptadas, por `refund_id`
distinto, en su día de devolución. **Motivo:** coherente con `refunded_amount`. → §3.1.

**A8. Devoluciones de pedidos que no son venta.**
Opciones: (a) rechazar (`order_not_sale`); (b) contarlas: C014 tendría −75.00 el 09-05 por R-1005
sin que su compra cuente. **Decisión:** (a) (D3). **Motivo:** el bruto tampoco cuenta; aceptarla
descuadraría. → R10.

**A9. Lo devuelto supera lo comprado (K-10148: 110 de 100 USD).**
Opciones: (a) rechazar entera la devolución que lo hace superar (devuelto total 1264.19 EUR);
(b) aceptarla hasta el límite (1300.99 EUR, importes distintos de la fuente); (c) aceptarlo todo y
que avise el control (1310.19 EUR); (d) rechazar todas las del pedido. **Decisión:** (a), en orden de
`refunded_at` y `refund_id`, comparando en la moneda del pedido (D2, precisión de Ana).
**Motivo:** no se parte ningún registro, queda trazado y el redondeo a EUR no interviene. → R11.

**A10. Devoluciones duplicadas.**
Opciones: con el mismo `refund_id` y contenido idéntico, ignorar la copia o anotarla; con contenido
distinto, quedarse con la última o rechazar todas. **Decisión:** usar la primera y anotar las copias
como `duplicate_refund` (R-1006); si el contenido difiere, `conflicting_duplicate` para todas;
distinto `refund_id` es distinta devolución (D4). **Motivo:** Finanzas quiere saber qué se descartó;
ante un conflicto no hay forma fiable de elegir. → R9.

**A11. Devoluciones sin pedido.**
Opciones: rechazar o retener hasta que llegue el pedido. **Decisión:** rechazar con
`order_not_found`; como se recalcula todo `--inbox`, si el pedido llega después se acepta en esa
ejecución. **Motivo:** simple y sin estado. → R1, R10.

**A12. Moneda de la devolución.**
Opciones: convertir con su moneda aunque no sea la del pedido, o rechazar. **Decisión:** se
convierte con su propia moneda; si no coincide con la del pedido, `currency_mismatch`; si no está en
la tabla, `unknown_currency`. **Motivo:** sin la misma moneda no se puede aplicar A9. → R8, R10.

**A13. Redondeo.**
Opciones: por registro o sobre la suma; medio hacia arriba o al par; decimal o binario. C004 el
09-02 da 691.50 o 691.52; C022 el 09-04, 325.17 o 325.16. **Decisión:** aritmética decimal, medio
hacia arriba, por registro; `net = gross − refunded` sobre valores redondeados; siempre dos
decimales. **Motivo:** igual que el contrato de `daily_sales` y exacto en el control 1. → R5, §3.4.

**A14. País de la fila.**
Opciones: (a) país actual; (b) el vigente cada día. Además: vacío o cliente inexistente.
**Decisión:** (a); vacío o inexistente → `UNKNOWN`, sin rechazar la venta; normalizar espacios y
mayúsculas. **Motivo:** el grano es cliente y día, así que un cambio de país no duplica filas; no se
pierde importe. → R7.

**A15. Qué va a `rejected.csv`.**
Opciones: incluir o no los pedidos que no son venta, las copias y las versiones antiguas; una fila
por motivo o una por registro. **Decisión:** lista cerrada de §3.2 con prioridad, una fila por
aparición de registro con el primer motivo, columnas extra `inbox_day` y `detail`; las copias y
versiones antiguas de pedidos no van (D4). **Motivo:** "no se ha podido usar" incluye lo que no es
venta; lo que se usa una vez no es un rechazo. → §3.2, R12.

**A16. Controles de calidad.**
Opciones: qué controles y a qué nivel. "Lo devuelto no supera lo comprado" por fila cliente-día
fallaría en 12 filas sin error real (por A4) y no detectaría K-10148. **Decisión:** exactamente tres
(§3.3): neto por fila, devuelto ≤ total por pedido y unicidad de claves y pedidos en una sola
entrada; salida 0 aunque fallen (precisión de Ana; que el control 3 sea una sola entrada,
confirmado expresamente por Ana). **Motivo:** controlar al nivel donde la regla
tiene sentido. → R15, R17.

**A17. Determinismo.**
Opciones: qué fijar (orden, codificación, formato). **Decisión:** lo indicado en §3.4. **Motivo:**
Plataforma considera un error dos ficheros distintos sobre los mismos datos. → R16.

**A18. Alcance respecto a `daily_sales`.**
Opciones: corregirlo ahora o dejarlo. **Decisión:** fuera de alcance; se documenta como defecto
conocido (D5, precisión de Ana). La definición de venta de esta tabla es la del contrato, así que
la suma de `gross_amount` (18490.74) no coincidirá con la de `daily_sales.csv` mientras este no se
corrija. **Motivo:** el ticket solo pide la tabla nueva. → §2, R18.

**A19. Registros y ficheros mal formados.**
Opciones: ignorar, rechazar o detenerse. **Decisión:** `refunds.json` ausente o `[]` = cero
devoluciones; registros inválidos → `invalid_record`; JSON roto → error con código ≠ 0.
**Motivo:** inventar o vaciar en silencio un día entero es peor que parar. → R1, R3, R8.

**A20. Días fuera del rango de `--inbox`.**
Opciones: generar la fila o recortar al último día con carpeta. **Decisión:** generarla.
**Motivo:** la fecha sale del dato, no de la carpeta. → R13.

## Anexo A · Cálculo de referencia

`docs/specs/KIV-101/reference_calc.py` es una implementación independiente de estos requisitos,
de solo lectura, con la que se han obtenido las cifras de §5 y §6. No forma parte del pipeline ni
lo importa. Es la base prevista para la tarea `acceptance` de la fase 4.

- `--summary`: totales y lista de rechazos.
- Una o varias claves `AAAA-MM-DD,cliente` (o un `customer_id` suelto): las filas esperadas de
  `daily_customer_metrics`, en el orden de columnas de §3.1. Sin argumentos, todas las filas.

Resultado de `uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary`:

```text
ventas 156 bruto 18490.74 devuelto 1264.19 neto 17226.55 filas 126 solo_devolucion 11 neto_negativo 12
rejected orders K-10062 2026-09-02 not_sale_unpaid
rejected orders K-10149 2026-09-05 not_sale_cancelled
rejected refunds R-1003 2026-09-05 order_not_found
rejected refunds R-1005 2026-09-05 order_not_sale
rejected refunds R-1006 2026-09-06 duplicate_refund
rejected refunds R-1009 2026-09-07 refund_exceeds_order
```

Limitaciones conocidas: no produce `quality_report.json` ni ficheros de salida, no comprueba S7 (un
JSON roto lanza la excepción de `json.load`) y no fija el formato byte a byte de §3.4.
