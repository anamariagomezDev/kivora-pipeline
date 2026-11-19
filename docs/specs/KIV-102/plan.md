# KIV-102 · Plan de implementación

Especificación: `docs/specs/KIV-102/spec.md`. Análisis previo: `docs/specs/KIV-102/impact.md`.
Cada paso es un commit propio, con mensaje en español y `Co-Authored-By`. Después de cada commit
se ejecutan `uv run python tasks.py test` y `uv run python tasks.py acceptance`. No se hace push ni
tag.

## Estrategia

La normalización se hace **en la carga** (`kivora/ingest.py`). `customer_metrics` recibe siempre
el mismo registro, sea cual sea el formato. Así el cambio se concentra en un punto y las reglas
R10–R18 no se tocan. En `customer_metrics.py` solo cambian dos cosas: qué se compara en R9 y la
validación del importe en R8.

## Pasos

### T1 · Especificación y plan (commit 1)

- `docs/specs/KIV-102/spec.md` y este `plan.md`.
- Verificación: `test` → `24 passed`; `acceptance` → `50 PASS, 0 FAIL` (no cambia el código).

### T2 · Tests y oráculo en rojo (commit 2)

- **`tests/test_customer_metrics.py`**: sección nueva «KIV-102» al final, con un helper
  `refund_v2(...)` y un test por regla. No se modifica ningún test existente.

  | Test | Qué fija | Por qué falla hoy |
  | --- | --- | --- |
  | `test_new_format_refund_is_accepted` | `refund_amount` con `reason` en USD → aceptada y convertida (R19, R20) | Sale `invalid_record` |
  | `test_new_format_reason_null_is_accepted` | `reason: null` → aceptada (R20) | `invalid_record` |
  | `test_mixed_formats_in_one_file` | Antiguo y nuevo en el mismo fichero → las dos aceptadas (R19) | La nueva se rechaza |
  | `test_same_refund_in_both_formats_is_one_refund` | Copia en los dos formatos → `duplicate_refund`; distinto importe entre formatos → `conflicting_duplicate` (R9) | Hoy las dos son `conflicting_duplicate` |
  | `test_reason_does_not_count_for_duplicates` | Dos copias nuevas que solo difieren en `reason` → `duplicate_refund` (R9) | `conflicting_duplicate` |
  | `test_both_amount_fields_is_invalid_record` | `amount` y `refund_amount` → `invalid_record` con `detail` claro (R8, R19) | Se acepta con `amount` |
  | `test_missing_or_bad_amount_names_the_field` | Sin importe y `refund_amount` ≤ 0 → `invalid_record`; el `detail` nombra el campo (R8) | El `detail` dice «amount no numérico: None» |
  | `test_reason_only_in_warehouse` | `raw_refunds.reason` en `warehouse.db`; el texto no aparece en ningún CSV (R21) | No existe la columna `reason` |

- **`kivora/acceptance.py`**:
  - copia aparte de 09-01..09-10 (`DAYS_KIV102`);
  - escenarios E20–E25 sobre la salida, y E20–E24 también sobre `reference_calc.py`
    («[referencia]»), para validar el oráculo igual que en KIV-101;
  - diferencial sobre 09-01..09-10;
  - S9–S12, con un helper `rf2()` para el formato nuevo.

  E1–E19 y S1–S8 no se tocan. `acceptance` deja de exigir solo los días 01–07: si faltan los días
  08–10, los escenarios de KIV-102 dan FAIL con un mensaje claro.
- Rojo esperado:
  - `test`: los 8 tests nuevos fallan y los 24 anteriores pasan;
  - `acceptance`: fallan E20–E24, sus «[referencia]», S9, S10 y S12;
  - pasan E25 (las cifras de 01–07 ya no cambian hoy), S11 (hoy ya sale `invalid_record`) y el
    diferencial de 01–10, porque pipeline y referencia comparten el fallo (`impact.md` §2.1).

### T3 · Implementación y `reference_calc.py` (commit 3)

- **`kivora/ingest.py`**:
  - `REFUND_FIELDS` pasa a ser `refund_id, order_id, refunded_at, amount, currency, reason`, donde
    `amount` es el importe normalizado;
  - columna nueva `_format` con el campo del importe: `amount`, `refund_amount`, `both` o `none`;
  - `_raw` se conserva solo como traza;
  - función `normalize_refund(item)` (R19, R20).
- **`kivora/customer_metrics.py`**:
  - `deduplicate_refunds` compara la tupla `REFUND_CONTENT` en vez de `_raw` (R9);
  - `_refund_problem` comprueba `_format` y nombra el campo en el `detail` (R8).
- **`docs/specs/KIV-101/reference_calc.py`**: misma normalización, escrita de forma
  independiente. Firma de R9 sobre los cinco campos e importe desde la clave única. Va en este
  mismo commit, como pidió Ana, y se justifica en su mensaje (K7).
- Verificación:
  - `test` → `32 passed`;
  - `acceptance` → los 50 PASS de KIV-101 más los nuevos, 0 FAIL;
  - `check` → OK;
  - `run` → 186 filas y 8 rechazos.

### T4 · Documentación (commit 4)

- `docs/tickets/KIV-102.md`: notas del equipo y respuesta a Finanzas.
- `docs/report.md`:
  - §5, cambio de esquema: estrategia y justificación;
  - §3, una fila por vuelta;
  - §4, trazabilidad de R19–R21 y de R8/R9 modificados.
- `docs/sources.md`: los dos formatos de `refunds.json`.
- `CLAUDE.md` («Entrada»): una línea sobre los dos formatos.
- `docs/specs/KIV-101/spec.md`: una nota en R8/R9 que remite a KIV-102. Lo demás de la spec
  aprobada no se toca.

## Riesgos

| Riesgo | Mitigación |
| --- | --- |
| Regresión de KIV-101 al cambiar la comparación de R9 (`impact.md` §4.4) | E10, S5 y `test_duplicate_and_conflicting_refunds` siguen sin cambios y deben pasar |
| El oráculo se adapta con el mismo error que el pipeline | `reference_calc.py` se escribe sin importar código de `kivora/`; los «[referencia]» de E20–E24 validan el oráculo contra los esperados literales de la spec, que salen de la simulación de `impact.md` |
| El cambio del esquema de `raw_refunds` (`reason`, `_format`) en `warehouse.db` | No es una salida con contrato; `daily_sales` y `top_customers` no leen `raw_refunds` (`impact.md` §3.1) |
| Un rechazo masivo sigue sin avisar (K10) | Fuera de alcance; anotado en la spec y en el ticket |
