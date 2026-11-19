# Fuentes de datos

La tienda online de Kivora deja cada día una carpeta en `data/inbox/` con el
nombre del día (`data/inbox/2026-09-01/`). Cada carpeta trae los registros
nuevos o modificados de ese día, no una foto completa.

Todas las marcas de tiempo vienen en **UTC**, en formato ISO 8601 con `Z`
(`2026-09-01T22:10:00Z`). Los importes usan punto decimal.

`data/inbox/` es lo que envía la tienda y **no se modifica nunca**: los
problemas del origen se resuelven en el pipeline.

## `orders.csv`

| Campo | Descripción |
| --- | --- |
| `order_id` | Identificador del pedido |
| `customer_id` | Cliente |
| `created_at` | Momento en que se hizo el pedido (UTC) |
| `updated_at` | Momento de la última modificación del pedido (UTC) |
| `status` | `confirmed` o `cancelled` |
| `currency` | Moneda del pedido (ISO 4217) |
| `total_amount` | Importe total, en la moneda del pedido |

Cuando un pedido cambia, la tienda lo vuelve a enviar el día del cambio, con
el mismo `order_id` y un `updated_at` posterior.

## `customers.csv`

| Campo | Descripción |
| --- | --- |
| `customer_id` | Identificador del cliente |
| `name` | Nombre |
| `country` | País (ISO 3166-1 alfa-2). Puede venir vacío |
| `signup_date` | Fecha de alta |

Trae las altas y las modificaciones del día.

## `payments.csv`

| Campo | Descripción |
| --- | --- |
| `payment_id` | Identificador del pago |
| `order_id` | Pedido al que corresponde |
| `paid_at` | Momento del intento de pago (UTC) |
| `method` | `card`, `paypal` o `bizum` |
| `status` | `captured` (cobrado) o `failed` |
| `amount` | Importe del pago, en la moneda del pedido |

Un pedido puede tener más de un pago.

## `refunds.json`

Desde el 2026-09-04. Una lista JSON; cada elemento es una devolución. Los días sin
devoluciones no traen el fichero (ticket `docs/tickets/KIV-101.md`).

| Campo | Descripción |
| --- | --- |
| `refund_id` | Identificador de la devolución |
| `order_id` | Pedido al que corresponde |
| `refunded_at` | Momento de la devolución (UTC, ISO 8601 con `Z`) |
| `amount` | Importe devuelto (número), en la moneda del pedido. Solo en el formato antiguo |
| `refund_amount` | Importe devuelto (número), en la moneda del pedido. Solo en el formato nuevo |
| `currency` | Moneda (ISO 4217) |
| `reason` | Motivo de la devolución, texto libre o `null`. Solo en el formato nuevo |

Desde el 2026-09-08 llega el formato nuevo (`docs/tickets/KIV-102.md`): `refund_amount` en lugar
de `amount`, y `reason`. Los ficheros anteriores no se reenvían, así que conviven los dos
formatos.

Cómo lo trata el pipeline (`docs/specs/KIV-101/spec.md` R1, R8–R11, y
`docs/specs/KIV-102/spec.md` R19–R21):

- Fichero ausente o `[]`: cero devoluciones ese día. Si no es JSON válido, el pipeline se
  detiene con código 2 y un mensaje que nombra el fichero (`kivora/ingest.py:57`,
  `kivora/__main__.py:30`).
- El formato se detecta registro a registro, por la clave del importe (`kivora/ingest.py:44`).
  Un registro con `amount` y `refund_amount`, o sin ninguno, va a `rejected.csv` como
  `invalid_record`.
- Los importes se leen como decimales exactos (`parse_float=Decimal`), nunca como `float`.
- Puede llegar la misma devolución en dos días, también en formatos distintos. Se compara
  `refund_id`, `order_id`, `refunded_at`, importe y `currency` (no `reason`). La copia idéntica
  se descarta como `duplicate_refund`; si el contenido difiere, todas sus apariciones se rechazan
  como `conflicting_duplicate`.
- `reason` se guarda solo en `warehouse.db` (`raw_refunds.reason`).
- Cada devolución no usada va a `rejected.csv` con su motivo.

## `data/reference/fx_rates.csv`

Tabla fija de tipos de cambio a euros.

| Campo | Descripción |
| --- | --- |
| `currency` | Moneda (ISO 4217) |
| `rate_to_eur` | Euros por unidad de la moneda: `importe_eur = importe × rate_to_eur` |
