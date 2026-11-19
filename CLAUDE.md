# Kivora pipeline

Pipeline diario de ventas de Kivora, una tienda online, en Python y SQLite.

- **Entrada:** `data/inbox/<día>/{orders,customers,payments}.csv` y, desde el 09-04, un
  `refunds.json` opcional. Conviven dos formatos de `refunds.json`: `amount` hasta el 09-07 y
  `refund_amount` + `reason` desde el 09-08 (KIV-102). Cada día trae solo registros nuevos o
  modificados. Las marcas de tiempo vienen en UTC.
- **Importes:** **no** vienen en EUR. Cada pedido trae su moneda y se convierte con
  `data/reference/fx_rates.csv`.
- **Código:** la carga está en `kivora/` y las transformaciones SQL en `sql/`. KIV-101 se
  calcula en Python (`kivora/customer_metrics.py`, `kivora/outputs.py`), no en SQL.
- **Salida:** `output/` (`daily_sales.csv`, `top_customers.csv`, `daily_customer_metrics.csv`,
  `rejected.csv`, `quality_report.json` y `warehouse.db`).
- **Reglas de negocio:** `docs/sources.md`, `docs/data-contracts/daily_sales.md` y
  `docs/specs/KIV-101/spec.md`.
- **Defectos conocidos del código actual:** `docs/analysis.md`.

## Comandos (verificados; siempre con `uv run`)

- Preparar el entorno: `uv sync`
- Ejecutar el pipeline: `uv run python tasks.py run`
- Tests (pytest): `uv run python tasks.py test`
- Comprobar la salida: `uv run python tasks.py check` (solo mira las columnas, que `gross_amount >= 0`
  y la estructura de `quality_report.json`)
- Oráculo de KIV-101: `uv run python tasks.py acceptance` (escenarios E1–E19 y S1–S8 de la spec
  sobre una copia temporal de los días 09-01..09-07; código 0 solo si pasan todos)
- Interfaz oficial: `uv run python -m kivora --inbox data/inbox --reference data/reference --out output`

## No se toca

- `data/inbox/` y `deliveries/`, nunca. Los problemas de los datos se resuelven en el pipeline.
- Las entregas solo se reciben con `uv run python tasks.py deliver N`, en un commit propio.
- La interfaz `python -m kivora` y sus opciones y valores por defecto.
- El código no se modifica sin una especificación aprobada en `docs/specs/`.
- Un test que contradice el contrato no se adapta en silencio: hay que decidirlo y justificarlo.
- El historial de Git: sin rebase, amend de commits publicados ni force-push.

## Cuándo está terminado un trabajo

- `uv run python tasks.py test`, `uv run python tasks.py check` y
  `uv run python tasks.py acceptance` en verde.
- Cada afirmación de la documentación tiene su evidencia: archivo:línea, o el comando y su resultado.
- La documentación afectada está actualizada.
- Los commits hechos por el agente conservan su línea `Co-Authored-By`.
