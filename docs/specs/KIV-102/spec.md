# KIV-102 · Especificación: dos formatos de `refunds.json`

Estado: **aprobada.** Las decisiones son de Ana, sobre la sección 5 de
`docs/specs/KIV-102/impact.md`. El 2026-11-19 pidió escribir esta especificación e implementarla
en la misma petición.
Esta especificación recoge **solo lo que cambia** respecto a `docs/specs/KIV-101/spec.md`. Todo lo
que no se nombra aquí (R1–R7, R10–R18, salidas, prioridades de `rejected.csv`, controles de
calidad, E1–E19 y S1–S8) sigue igual.

## 1. Objetivo

Leer bien las devoluciones de los dos formatos de `refunds.json` que conviven en `data/inbox/`
(`docs/tickets/KIV-102.md`). Las del formato nuevo se tratan con las mismas reglas que las del
antiguo, y las cifras ya entregadas a Finanzas (días 09-01 a 09-07) no cambian.

| Formato | Campo del importe | `reason` |
| --- | --- | --- |
| Antiguo (hasta el 09-07) | `amount` | no existe |
| Nuevo (desde el 09-08) | `refund_amount` | texto o `null` |

## 2. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| K1 | Se aceptan los dos formatos (opción A de `impact.md` §5) | Ana |
| K2 | El formato se detecta **por las claves de cada registro**, no por la fecha de la carpeta ni por fichero | Recomendación de `impact.md`, incluida en la opción A |
| K3 | Para comparar duplicados (R9) se usa el registro normalizado: `refund_id`, `order_id`, `refunded_at`, importe y `currency`. **`reason` no cuenta** | Ana |
| K4 | Un registro con `amount` y `refund_amount` a la vez, o sin ninguno de los dos, es `invalid_record`, aunque los dos importes coincidan | Ana |
| K5 | Un registro con formato desconocido **no** detiene el pipeline (opción D descartada). R1 no cambia | Ana |
| K6 | `reason` se guarda solo en `warehouse.db` (`raw_refunds.reason`); no aparece en ningún CSV de salida | Ana |
| K7 | `docs/specs/KIV-101/reference_calc.py` se adapta para normalizar igual, en el mismo commit que la implementación y justificado en su mensaje. Si fuera en un commit aparte, el diferencial quedaría en rojo entre los dos | Ana |
| K8 | El `detail` de `invalid_record` nombra el problema del importe y el campo concreto | Recomendación |
| K9 | `reason` ausente se guarda como `NULL`, igual que `reason: null` | Recomendación |
| K10 | Un control de calidad o aviso de rechazos masivos queda **fuera** de KIV-102: cambiaría la estructura de `quality_report.json` (KIV-101 §3.3). Queda anotado como pendiente | Recomendación |

## 3. Requisitos

### Nuevos

- **R19 (formato de cada registro).** Cada objeto de `refunds.json` se clasifica por las claves
  del importe que trae, con independencia del día y del resto del fichero:
  - solo `amount` → formato antiguo; el importe es `amount`;
  - solo `refund_amount` → formato nuevo; el importe es `refund_amount`;
  - las dos claves → **ambiguo**;
  - ninguna de las dos → **sin importe**.

  Cuenta que la clave esté presente, no su valor: `"refund_amount": null` es formato nuevo, con
  un importe vacío que se rechaza en R8. Un mismo fichero puede mezclar formatos.
- **R20 (registro normalizado).** Cada devolución se carga como `refund_id`, `order_id`,
  `refunded_at`, importe, `currency` y `reason`, con los valores tal como vienen en el fichero (los
  números como decimales exactos, igual que en KIV-101). `reason` es el valor de la clave si
  existe, en cualquier formato; si no existe, o vale `null`, queda vacío (`NULL`). En los registros
  ambiguos y sin importe, el importe normalizado queda vacío.
- **R21 (`reason`).** `reason` no interviene en ninguna regla (R8–R11), métrica ni control. Se
  guarda en la columna `reason` de la tabla `raw_refunds` de `warehouse.db`, y no aparece en
  `daily_customer_metrics.csv`, `rejected.csv`, `daily_sales.csv` ni `top_customers.csv`.

### Modificados

- **R8 (modificado).** La validación de la aparición que queda tras R9 usa el importe
  normalizado (R20) en lugar de `amount`. Las comprobaciones siguen el orden de KIV-101 y el
  importe se comprueba en la misma posición:
  1. si el registro es ambiguo → `invalid_record`, con `detail` «trae amount y refund_amount»;
  2. si no tiene importe → `invalid_record`, con `detail` «falta el importe (amount o
     refund_amount)»;
  3. si el importe no es numérico o es ≤ 0 → `invalid_record`, y el `detail` nombra el campo del
     que viene (`amount` o `refund_amount`).

  El resto de R8 no cambia, incluido que un `refund_id` vacío se rechaza antes de R9.
- **R9 (modificado).** El «contenido» que se compara entre las apariciones de un `refund_id` es la
  tupla normalizada (`refund_id`, `order_id`, `refunded_at`, importe, `currency`), con los valores
  como vienen en el fichero. Quedan fuera:
  - `reason`;
  - qué campo traía el importe, así que la misma devolución en los dos formatos es una copia;
  - cualquier otra clave del objeto.

  Las consecuencias (`duplicate_refund` para las copias, `conflicting_duplicate` para todas si
  difieren) no cambian. *Cambio de comportamiento respecto a KIV-101:* dos apariciones que solo
  difieran en `reason` o en una clave desconocida eran `conflicting_duplicate` y ahora son
  copias. Con los datos reales no hay ningún caso así (`impact.md` §1).

### Sin cambios que conviene recordar

- R1: solo un JSON inválido detiene el pipeline (K5).
- R6: la fecha de la devolución es la de `refunded_at` en `Europe/Madrid`, en cualquier formato.
- R11: el límite por pedido suma las devoluciones aceptadas de los dos formatos.

## 4. Escenarios de aceptación con los datos reales (días 09-01 a 09-10)

Se comprueban con `uv run python tasks.py acceptance` sobre una copia temporal de los días
09-01 a 09-10. Los esperados salen de la simulación de `impact.md` §2.2 y se recalculan con
`reference_calc.py` adaptado:

```bash
uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference --summary
uv run python -I docs/specs/KIV-101/reference_calc.py data/inbox data/reference \
  2026-09-08,C029 2026-09-11,C031 2026-09-10,C031
```

| ID | Caso | Evidencia en la entrada | Resultado esperado | Requisitos |
| --- | --- | --- | --- | --- |
| E20 | Formato nuevo con `reason: null` | `grep -A5 '"R-1033"' data/inbox/*/refunds.json` → K-10214 (C029, 85.12 EUR, comprado el 09-07), `refund_amount` 10.0 EUR, `2026-09-08T12:12:00Z`, `reason: null` | `2026-09-08,C029,DE,0,0.00,10.00,-10.00,1,2026-09-07`; R-1033 no está en `rejected.csv` | R19, R20, R21, R8 |
| E21 | Formato nuevo sin pedido | `grep -A1 '"R-1034"' data/inbox/*/refunds.json` → K-19998; `grep -c '^K-19998,' data/inbox/*/orders.csv` → 0 en todos | `refunds,R-1034,order_not_found,2026-09-09` | R19, R10 |
| E22 | Límite del pedido con los dos formatos | `grep '^K-10155,' data/inbox/*/orders.csv` → C026, 80.00 EUR; R-1013 (`amount` 70.0, 09-07) y R-1035 (`refund_amount` 20.0, 09-09) | R-1013 aceptada; `refunds,R-1035,refund_exceeds_order,2026-09-09`; `refunds_within_order_total` con `failed_records = 0` | R19, R11 |
| E23 | Formato nuevo que cambia de día en Madrid | `grep -A5 '"R-1036"' data/inbox/*/refunds.json` → K-10215 (C031, comprado el 09-09), 9.95 EUR, `2026-09-10T23:10:00Z` | `2026-09-11,C031,ES,0,0.00,9.95,-9.95,1,2026-09-09`; no hay fila `2026-09-10,C031` | R6, R13 |
| E24 | Totales y rechazos de 09-01..09-10 | `… --summary` | 213 ventas; bruto 25072.41; devuelto 1576.04; neto 23496.37; 186 filas, 22 solo con devoluciones, 24 con neto negativo. `rejected.csv` tiene exactamente 8 filas: las 6 de E18 más R-1034 `order_not_found` y R-1035 `refund_exceeds_order`. Los tres controles pasan | R8–R12, R15, R19 |
| E25 | Las cifras de 09-01..09-07 no cambian | Ejecución sobre 09-01..09-07 y sobre 09-01..09-10 | Las filas con `metric_date <= 2026-09-07` son idénticas en las dos ejecuciones | R6, D1 |

Además, el **diferencial** con `reference_calc.py` se amplía a la copia de 09-01..09-10: deben
coincidir todas las filas de `daily_customer_metrics.csv` y todos los rechazos.

## 5. Escenarios sintéticos

Se construyen en carpetas temporales, fuera del repositorio. Base: pedido K-1 (C1, 10.00 EUR,
`confirmed`, pago `captured`) el `2026-09-01`. Las devoluciones son de K-1, en EUR, con
`refunded_at` `2026-09-01T15:00:00Z` salvo que se diga otra cosa.

| ID | Entrada | Resultado esperado | Requisitos |
| --- | --- | --- | --- |
| S9 | 09-01: R-7 con `amount` 2.0. 09-02: R-7 con `refund_amount` 2.0 y `reason` «talla incorrecta» | **Una** devolución: `2026-09-01,C1,ES,1,10.00,2.00,8.00,1,2026-09-01`; `refunds,R-7,duplicate_refund,2026-09-02` y ningún `conflicting_duplicate` | R9, R19 |
| S10 | R-8 con `amount` 1.0 **y** `refund_amount` 1.0 | `refunds,R-8,invalid_record`; no suma a K-1 | R8, R19 |
| S11 | R-9 sin `amount` ni `refund_amount` | `refunds,R-9,invalid_record`; no suma a K-1 | R8, R19 |
| S12 | Un solo fichero: R-10 con `amount` 1.0, R-11 con `refund_amount` 2.0 y `reason: null`, R-12 con `refund_amount` 3.0 y `reason` «cambio de opinión» | Las tres aceptadas: `2026-09-01,C1,ES,1,10.00,6.00,4.00,3,2026-09-01`. En `warehouse.db`, `raw_refunds.reason` vale `NULL`, `NULL` y «cambio de opinión»; ese texto no aparece en ningún CSV de salida | R19, R20, R21 |

## 6. Fuera de alcance

- Un control o aviso de rechazos masivos (K10).
- Corregir `daily_sales` (D5 de KIV-101).
- Validar o normalizar el texto de `reason`.
