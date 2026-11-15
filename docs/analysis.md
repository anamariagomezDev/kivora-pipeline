# Análisis del pipeline (KIV-100)

Análisis de la fase 1: cómo funciona hoy el pipeline, con sus defectos. No se ha modificado
código. Cada afirmación lleva su evidencia:

- **[E]** comprobado ejecutando (se indica el comando y su resultado).
- **[L]** deducido leyendo el código (se indica archivo:línea).

Datos analizados: `data/inbox/` del 2026-09-01 al 2026-09-03 y `data/reference/fx_rates.csv`.

## Método y reproducibilidad

| Qué | Comando | Resultado |
| --- | --- | --- |
| Ejecutar el pipeline | `uv run python tasks.py run` | `Días procesados: 3 (2026-09-01 .. 2026-09-03)`, `Pedidos en staging: 68` |
| Determinismo | `uv run python -m kivora --out <tmp>/run1` y `--out <tmp>/run2`, después `sha256sum` de los tres `daily_sales.csv` | Los tres iguales: `cc4f4698481b2501ff67d9cec963b6026d909866ff4accd78eb4e07253f220f4` |
| Tests | `uv run python tasks.py test` | `4 passed` |
| Comprobaciones | `uv run python tasks.py check` | `OK: output/ tiene los ficheros y columnas esperados` |
| Consultas a la salida | `sqlite3.connect("file:output/warehouse.db?mode=ro", uri=True)` desde `uv run python` | Ver secciones 1 y 2 |

**Valores según el contrato.** Se recalcularon en Python a partir de los CSV de `data/inbox/`:
se toma la última versión de cada pedido por `updated_at`, se exige un pago `captured`, se
excluyen los cancelados, la fecha se calcula con `zoneinfo("Europe/Madrid")`, el país vacío
pasa a `UNKNOWN` y el importe se convierte a EUR pedido a pedido con `fx_rates.csv`,
redondeado a 2 decimales. El script es el bloque de código del Anexo A.

**Casos sintéticos.** Algunos defectos no se activan con los datos actuales. Para esos se
ejecutó `kivora.pipeline.run` sobre carpetas temporales con un solo pedido, fuera del
repositorio y nunca sobre `data/inbox/`. Están en el Anexo B.

## 1. Qué hace el pipeline, paso a paso

1. `uv run python tasks.py run` lanza `python -m kivora` (tasks.py:42-44), que llama a
   `kivora.pipeline.run(inbox, reference, out)` con los valores por defecto `data/inbox`,
   `data/reference` y `output` (`kivora/__main__.py:19-27`).
2. Crea `out/` y borra `out/warehouse.db` si existe, así que cada ejecución empieza de cero
   (pipeline.py:27-32). [L]
3. `ingest.load_inbox` recorre las carpetas de día en orden y carga `orders.csv`,
   `customers.csv` y `payments.csv` en `raw_orders`, `raw_customers` y `raw_payments`. Todas
   las columnas se guardan como TEXT, sin limpiar nada, y la carpeta de origen va en `_day`
   (ingest.py:19-34). Si falta un CSV, se salta sin avisar (ingest.py:27-28). Cualquier otro
   fichero se ignora, porque solo se leen las fuentes de `SOURCES` (ingest.py:6-11). [L]
4. `ingest.load_reference` carga `fx_rates.csv` en `ref_fx_rates` (ingest.py:37-42). [L]
5. `sql/staging.sql`: [L]
   - `stg_orders`: `SELECT DISTINCT` sobre todas las columnas, `total_amount` pasado a REAL y
     `order_date = substr(created_at, 1, 10)`, que es la fecha **UTC** (staging.sql:5-15).
   - `stg_customers`: `SELECT DISTINCT` (staging.sql:18-24).
   - `stg_payments`: sin deduplicar (staging.sql:27-35).
6. `sql/daily_sales.sql` une los pedidos con sus pagos `captured` y con los clientes (los dos
   JOIN son INNER), filtra `status <> 'cancelled'`, agrupa por `order_date` y `country` y
   calcula `COUNT(*)` y `ROUND(SUM(total_amount), 2)`. No usa `ref_fx_rates`
   (daily_sales.sql:5-19). [L]
7. `sql/top_customers.sql` aplica la misma lógica, agrupada por cliente, con `LIMIT 10`
   (top_customers.sql:3-16). Tampoco convierte divisas. [L]
8. Exporta `daily_sales.csv` y `top_customers.csv` con `SELECT *` (pipeline.py:14, 17-23,
   38-39). [E] Escribe `daily_sales.csv`, `top_customers.csv` y `warehouse.db` en `output/`.
9. Aparte, `tasks.py check` (kivora/check.py) solo comprueba que los ficheros existen, que
   tienen las columnas esperadas y que `gross_amount >= 0` (check.py:8-30). [E] `OK`.

**Lo que hay en los datos** [E] (consultas a `output/warehouse.db`):

- `raw_orders` tiene 70 filas y `stg_orders` 68, con 68 `order_id` distintos.
- Hay dos repeticiones:
  - K-10059 aparece dos veces, idéntico, en el 2026-09-01.
  - K-10060 se reenvía idéntico el 2026-09-02 y el 2026-09-03.
- Ningún pedido cambia de versión. Los 68 están en `confirmed`.
- Monedas: EUR 53, GBP 8 y USD 7.
- Los clientes C007 y C019 tienen `country = ''`.
- Ningún pedido tiene más de un pago `captured`.
- K-10062 (C024, 99.00 EUR, 2026-09-02) no tiene ningún pago `captured`.
- No hay pagos sin pedido ni pedidos sin cliente.

## 2. ¿Cumple `daily_sales` su contrato?

**No.** [E] La salida suma **7840.72** en 67 ventas. Según el contrato debería sumar
**7905.15** en 67 ventas. De las 20 combinaciones día-país que aparecen en la salida o en el
recálculo, **16 no coinciden**. Solo coinciden 09-01 FR, 09-01 PT, 09-02 DE y 09-03 FR
(comando en el Anexo A: `claves totales: 20 | coinciden: 4 | no coinciden: 16`).

| Punto del contrato | ¿Se cumple? | Evidencia |
| --- | --- | --- |
| Grano: una fila por día y país (contrato:9) | En la forma sí (`GROUP BY`, daily_sales.sql:18), pero los días y los países salen mal (ver las filas siguientes) | [E] 16 filas, ninguna clave repetida |
| `sales_date` es el día en Europe/Madrid (contrato:15) | **No**: se usa la fecha UTC (staging.sql:14) | [E] Cuatro pedidos de después de las 22:00 UTC caen en el día equivocado (lista bajo la tabla) |
| `country = UNKNOWN` si falta (contrato:16) | **No**: sale vacío | [E] La fila `2026-09-01,,3,314.95` suma K-10005 (C019, 68.29), K-10009 (C007, 166.04) y K-10066 (C007, 80.62). También salen vacías `2026-09-02,,1,173.58` (K-10032, C019) y `2026-09-03,,1,81.25` (K-10067, C019) |
| Venta = no cancelada y con al menos un pago `captured` (contrato:22-25) | Con los datos actuales, sí: K-10062 (dos pagos `failed`) queda fuera [E]. Pero el filtro mira todas las versiones del pedido, no la última (fila siguiente) | daily_sales.sql:12-17 [L] |
| Se usa la última versión del pedido (contrato:22) | **No**: `DISTINCT` solo elimina copias idénticas (staging.sql:6). Los datos actuales no lo activan | [E] Caso A: un pedido cancelado en su segunda versión sigue contando (`2026-09-01,ES,1,10.0`, debería dar 0). Caso B: un pedido cuyo importe pasa de 10 a 12 cuenta dos veces (`2,22.0`, debería dar `1,12.00`) |
| Conversión a EUR con `fx_rates.csv` (contrato:31-33) | **No**: ningún SQL usa `ref_fx_rates` (daily_sales.sql:10) | [E] **K-10002** (C021, 2026-09-01, 163.17 GBP) se suma como 163.17 sin convertir, cuando el contrato da 190.91 EUR. La fila 09-01 GB da 325.25 y debería dar 380.54. La fila 09-02 US da 615.08 y debería dar 691.50 |
| Una moneda que no está en la tabla no se usa y se informa de ella (contrato:34-35) | **No** | [E] Caso F: un pedido de 1000 JPY sale como `2026-09-01,ES,1,1000.0` y no se avisa de nada |
| Cada venta cuenta una sola vez, tenga los pagos que tenga (contrato:27) | **No**: `COUNT(*)` y `SUM` se calculan después del JOIN con los pagos, que multiplica las filas (daily_sales.sql:9-14). Los datos actuales no lo activan | [E] Caso C: un pedido de 10.00 con dos pagos `captured` da `orders_count=2, gross_amount=20.0` |
| Otros puntos de la definición | El JOIN con los clientes es INNER (daily_sales.sql:15-16): la venta de un cliente que no está en `customers` desaparece. Si un cliente se reenvía con otro país, su venta cuenta una vez en cada país | [E] Caso E: con el cliente ausente, la salida queda vacía. Caso D: si C1 pasa de ES a FR, la misma venta sale en ES y en FR |
| `gross_amount` con dos decimales (contrato:18) | **No** en el formato: se exporta como REAL | [E] `2026-09-01,PT,1,201.0` en `output/daily_sales.csv` |
| La suma de `gross_amount` coincide con las ventas en EUR (contrato:39-40) | **No** | [E] 7840.72 frente a 7905.15 |
| Dos ejecuciones dan el mismo fichero (contrato:41) | **Sí** | [E] El mismo SHA-256 en tres ejecuciones (ver Método); hay `ORDER BY` en daily_sales.sql:19 |

**Pedidos con el día equivocado (hora UTC frente a hora de Madrid)** [E]:

| order_id | customer_id | Importe | `created_at` (UTC) | Día en Madrid | Día en la salida |
| --- | --- | ---: | --- | --- | --- |
| K-10053 | C003 | 107.92 EUR | 2026-09-01T22:10:55Z | 2026-09-02 | 2026-09-01 |
| K-10054 | C004 | 136.57 USD | 2026-09-01T23:35:33Z | 2026-09-02 | 2026-09-01 (es la única venta de la fila US del 09-01) |
| K-10055 | C016 | 104.83 EUR | 2026-09-02T22:47:11Z | 2026-09-03 | 2026-09-02 |
| K-10056 | C008 | 91.34 GBP | 2026-09-03T23:05:49Z | 2026-09-04 | 2026-09-03 (el día 09-04 no aparece en la salida) |

Arreglo por defecto, en una línea: usar la última versión por `updated_at`, deduplicar por
pedido antes de agregar, fecha en Madrid, `UNKNOWN` para el país vacío y conversión FX por
pedido, informando de las monedas desconocidas.

### Diferencias día × país [E]

| sales_date | country | orders_count salida | orders_count contrato | gross_amount salida | gross_amount contrato |
| --- | --- | ---: | ---: | ---: | ---: |
| 2026-09-01 | *(vacío)* | 3 | 0 | 314.95 | 0 |
| 2026-09-01 | ES | 15 | 14 | 1675.06 | 1567.14 |
| 2026-09-01 | FR | 1 | 1 | 17.92 | 17.92 |
| 2026-09-01 | GB | 3 | 3 | 325.25 | 380.54 |
| 2026-09-01 | PT | 1 | 1 | 201.0 | 201.00 |
| 2026-09-01 | UNKNOWN | 0 | 3 | 0 | 314.95 |
| 2026-09-01 | US | 1 | 0 | 136.57 | 0 |
| 2026-09-02 | *(vacío)* | 1 | 0 | 173.58 | 0 |
| 2026-09-02 | DE | 1 | 1 | 106.02 | 106.02 |
| 2026-09-02 | ES | 11 | 11 | 1375.74 | 1378.83 |
| 2026-09-02 | GB | 3 | 3 | 351.17 | 410.87 |
| 2026-09-02 | UNKNOWN | 0 | 1 | 0 | 173.58 |
| 2026-09-02 | US | 5 | 6 | 615.08 | 691.50 |
| 2026-09-03 | *(vacío)* | 1 | 0 | 81.25 | 0 |
| 2026-09-03 | ES | 17 | 18 | 2105.55 | 2210.38 |
| 2026-09-03 | FR | 1 | 1 | 16.84 | 16.84 |
| 2026-09-03 | GB | 2 | 1 | 148.67 | 67.08 |
| 2026-09-03 | UNKNOWN | 0 | 1 | 0 | 81.25 |
| 2026-09-03 | US | 1 | 1 | 196.07 | 180.38 |
| 2026-09-04 | GB | 0 | 1 | 0 | 106.87 |
| **Total** | | **67** | **67** | **7840.72** | **7905.15** |

`top_customers` arrastra los mismos fallos de divisas y de duplicidad. [E] El primero es
C004 con 947.72, casi todo en USD sin convertir. Esta tabla no tiene contrato.

## 3. Qué comprueban de verdad los tests

[E] `uv run python tasks.py test` → `4 passed`. Los cuatro pasan aunque el contrato no se cumple.

| Test | Qué comprueba de verdad | ¿Pasaría con el código incorrecto? |
| --- | --- | --- |
| `test_pipeline_generates_daily_sales` (tests/test_pipeline.py:41-44) | Que la salida tiene al menos una fila | Sí, con casi cualquier error |
| `test_sales_dates_are_iso` (:47-50) | Solo el formato `\d{4}-\d{2}-\d{2}` | Sí: la fecha UTC tiene el formato bueno aunque el día sea incorrecto (K-10053) |
| `test_exact_duplicate_orders_counted_once` (:53-63) | Que una fila repetida exactamente cuenta una vez. Solo mira `rows[0]` | Sí: con los casos A, B y C seguiría pasando |
| `test_gross_matches_source_total` (:66-75) | Que el total de la salida es igual a la suma de los pedidos pagados de la fuente | **Sí, y ya pasa con el código incorrecto** (motivo bajo la tabla) |

`test_exact_duplicate_orders_counted_once` no cubre ni las versiones con otro `updated_at`
ni los pedidos con varios pagos `captured`.

El cálculo esperado de `test_gross_matches_source_total` repite los errores del código:

- No convierte divisas: suma `float(o[6])` tal cual (:73).
- Deduplica por fila completa con `tuple(o.values())` y no se queda con la última versión del pedido (:72).
- [E] Por eso pasa con 7840.72, cuando el contrato da 7905.15.

### Lo que no se comprueba

- El cambio de día en Madrid a partir de las 22:00 UTC.
- `UNKNOWN` para el país vacío.
- La última versión del pedido (cancelado o con el importe cambiado).
- Un pedido con dos pagos `captured`.
- La conversión a EUR y su redondeo.
- El aviso de moneda desconocida.
- Una venta sin cliente, o un cliente que cambia de país.
- Los dos decimales de `gross_amount`.
- El determinismo.
- `top_customers`.

Los tests usan fixtures de pytest (`tmp_path`) y no son `unittest.TestCase`, así que solo se
ejecutan con pytest (ver sección 4).

## 4. ¿Es fiable la documentación?

**El `CLAUDE.md` heredado no es fiable.** De sus cinco afirmaciones, cuatro son falsas y
solo una es correcta. Se ha reemplazado.

| Línea | Afirmación del CLAUDE.md heredado | ¿Es cierta? | Evidencia |
| --- | --- | --- | --- |
| :7 | Ejecutar el pipeline: `python run.py` | **Falsa** | [E] `uv run python run.py` → `can't open file '.../run.py': [Errno 2] No such file or directory`, exit 2. Lo correcto es `uv run python tasks.py run` |
| :8 | Tests: `python -m unittest discover tests` | **Falsa** | [E] `Ran 0 tests in 0.000s`, `NO TESTS RAN`, exit 5. Lo correcto es `uv run python tasks.py test` (pytest, tasks.py:47-49) |
| :12 | Los importes ya vienen en euros | **Falsa** | `orders.csv` trae `currency` (docs/sources.md:22-23) y `fx_rates.csv` tiene GBP 1.17 y USD 0.92. [E] Hay 15 pedidos en GBP o USD (por ejemplo, K-10002). Es justo el error que tiene el código |
| :13 | Las consultas SQL están en `queries/` | **Falsa** | [E] `ls queries` → `No such file or directory`. Están en `sql/` (pipeline.py:10) |
| :14 | La salida se escribe en `output/` | Cierta | Es el valor por defecto (`kivora/__main__.py:23`) |

Además, no dice que hay que usar `uv run`, qué no se puede tocar ni cuándo un trabajo está
terminado.

**El resto de la documentación es fiable en general, con matices:**

- README:47-50 y 74-77: los comandos y la interfaz son correctos. [E] `run`, `test` y
  `check` funcionan, y los valores por defecto están en `kivora/__main__.py:19-24`.
- README:26 dice "El pipeline funciona". Se ejecuta, pero no cumple el contrato (sección 2).
- README:64 "Comprobaciones básicas" es exacto: `check` solo mira las columnas y que
  `gross_amount >= 0` (check.py:24-30). No valida el contrato.
- `docs/sources.md` coincide con los datos: fechas en UTC con `Z`, reenvíos con el mismo
  `order_id`, el país puede venir vacío y un pedido puede tener varios pagos.
- Los comentarios del código engañan:
  - `sql/staging.sql:1` dice "types and duplicates", pero solo elimina duplicados exactos.
  - `sql/daily_sales.sql:2` cita el contrato, pero no lo cumple.

## Anexo A · Recálculo según el contrato

Se ejecuta con `uv run python -` desde la raíz, después de `uv run python tasks.py run`:

```python
import csv, sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
mad = ZoneInfo("Europe/Madrid")
fx = {r["currency"]: Decimal(r["rate_to_eur"]) for r in csv.DictReader(open("data/reference/fx_rates.csv", encoding="utf-8"))}
orders, cust, paid = {}, {}, set()
for d in sorted(Path("data/inbox").iterdir()):
    for r in csv.DictReader(open(d/"orders.csv", encoding="utf-8")):
        if r["order_id"] not in orders or r["updated_at"] > orders[r["order_id"]]["updated_at"]:
            orders[r["order_id"]] = r
    for r in csv.DictReader(open(d/"customers.csv", encoding="utf-8")):
        cust[r["customer_id"]] = r
    for r in csv.DictReader(open(d/"payments.csv", encoding="utf-8")):
        if r["status"] == "captured": paid.add(r["order_id"])
exp = defaultdict(lambda: [0, Decimal(0)])
for o in orders.values():
    if o["status"] == "cancelled" or o["order_id"] not in paid: continue
    day = datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")).astimezone(mad).date().isoformat()
    k = (day, cust.get(o["customer_id"], {}).get("country") or "UNKNOWN")
    exp[k][0] += 1
    exp[k][1] += (Decimal(o["total_amount"]) * fx[o["currency"]]).quantize(Decimal("0.01"), ROUND_HALF_UP)
act = {(r[0], r[1]): (r[2], Decimal(str(r[3]))) for r in sqlite3.connect("file:output/warehouse.db?mode=ro", uri=True).execute("select * from daily_sales")}
keys = sorted(set(exp) | set(act))
same = [k for k in keys if act.get(k, (0, Decimal(0))) == tuple(exp.get(k, (0, Decimal(0))))]
print("claves totales:", len(keys), "| coinciden:", len(same), "| no coinciden:", len(keys) - len(same))
print("coinciden:", same)
```

Resultado:

```text
claves totales: 20 | coinciden: 4 | no coinciden: 16
coinciden: [('2026-09-01', 'FR'), ('2026-09-01', 'PT'), ('2026-09-02', 'DE'), ('2026-09-03', 'FR')]
```

## Anexo B · Casos sintéticos [E]

Cada caso es una carpeta temporal fuera del repositorio con un pedido `K-1` del cliente `C1`
(ES), creado el `2026-09-01T10:00:00Z`, de 10.00 EUR y con el pago `P-1` `captured`, salvo
lo que se indica en cada fila. Se ejecutó `kivora.pipeline.run(inbox, "data/reference", out)`.

| Caso | Entrada | `daily_sales.csv` obtenido | Según el contrato |
| --- | --- | --- | --- |
| A | El 09-02 llega K-1 con `updated_at=2026-09-02T09:00:00Z` y `status=cancelled` | `2026-09-01,ES,1,10.0` | ninguna fila |
| B | El 09-02 llega K-1 con un `updated_at` posterior y `total_amount=12.00` | `2026-09-01,ES,2,22.0` | `2026-09-01,ES,1,12.00` |
| C | Un segundo pago `P-2` `captured` para K-1 | `2026-09-01,ES,2,20.0` | `2026-09-01,ES,1,10.00` |
| D | El 09-02 llega C1 con `country=FR` | `2026-09-01,ES,1,10.0` y `2026-09-01,FR,1,10.0` | una sola fila |
| E | `customers.csv` no trae a C1 | *(sin filas)* | la venta debe aparecer |
| F | K-1 en JPY (1000), moneda que no está en `fx_rates.csv` | `2026-09-01,ES,1,1000.0` | no se usa y se informa de ella |
