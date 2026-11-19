\# Memoria · Kivora pipeline



\## 1. Decisiones con el agente



| # | Fase | Decisión | Propuesta por | Opciones | Motivo |
|---|---|---|---|---|---|
| 1 | 1 | Analizar en plan mode y escribir en modo manual (permiso por archivo) | Yo, siguiendo assignment.md y la recomendación de human in the loop del profesor | Auto mode / plan / manual | Revisar cada cambio antes de aceptarlo |
| 2 | 1 | Reglas de CLAUDE.md generales, no ligadas a fases | Yo (al revisar el plan del agente) | Reglas por fase / reglas generales | CLAUDE.md debe servir a cualquier sesión futura |
| 3 | 1 | No aprobar "don't ask again" para los comandos uv run ni git | Yo | Aprobar todos / aprobar uno a uno | Evitar que tasks.py deliver, git push o git reset se ejecuten sin control |
| 4 | 2 | D1: la devolución va al día de refunded\_at en Madrid; se aceptan netos negativos | Yo, sobre la propuesta del agente | Día de devolución / de compra / del fichero | Contabilidad registra el movimiento el día en que ocurre |
| 5 | 2 | D2: se rechaza la devolución que hace superar el total del pedido | Yo, sobre la propuesta del agente | Rechazar / aceptar hasta el límite / aceptar todo | Nunca devolver más de lo vendido y dejarlo trazado |
| 6 | 2 | D3: venta = contrato de daily\_sales; las devoluciones de no-ventas se rechazan | Yo, sobre la propuesta del agente | Solo ventas / todo pedido | Definición ya contratada |
| 7 | 2 | D4: qué va a rejected.csv | Yo, sobre la propuesta del agente | — | "No lo tiréis sin más" (KIV-101) |
| 8 | 2 | D5: corregir daily\_sales queda fuera de alcance | Yo | Corregir ahora / documentar | KIV-101 no lo pide y el plazo es corto |
| 9 | 2 | Tres controles de calidad en lugar de seis | Yo, al revisar la propuesta | 3 / 6 | Los dos del enunciado más la unicidad; el resto no suma |

\## 2. Configuración del agente



Archivos: `.claude/settings.json` (permisos y registro del hook, compartido con el equipo) y `.claude/hooks/protect_inputs.py`. Lo que no está ni en `allow` ni en `deny` (editar archivos, `git commit`, `uv sync`...) **pregunta** cada vez.

#### Tabla de protecciones

| Riesgo | Mecanismo | Tipo | Por qué ese tipo |
|---|---|---|---|
| Modificar los datos de entrada (`data/inbox/`, `data/reference/`, `deliveries/`) con las herramientas de edición | Hook `PreToolUse` `protect_inputs.py` sobre `Write\|Edit\|MultiEdit\|NotebookEdit` (`.claude/settings.json:41-45`), respaldado por `CLAUDE.md:24` | Hook (+ instrucción) | Los permisos filtran por herramienta y patrón, pero aquí hay que decidir por la ruta normalizada (relativa, absoluta, `..`, mayúsculas en Windows). El hook lo hace con código y es determinista; la instrucción sola se puede ignorar |
| Modificar los datos de entrada desde la shell (`Set-Content`, `Copy-Item`, `git checkout -- data/...`) | Ninguno automático: esos comandos no están en `allow`, así que piden permiso | Permiso (preguntar) | Limitación conocida: el hook no inspecciona comandos de shell. Reconocer rutas dentro de un comando arbitrario por patrones no es fiable; la red de seguridad es revisar cada petición |
| Recibir una entrega fuera de su fase | `deny` de `tasks.py deliver*` en Bash y PowerShell (`.claude/settings.json:24-25`); `CLAUDE.md:25` | Permiso (deny) | Es un comando concreto y reconocible por prefijo: el deny lo bloquea siempre. La entrega la ejecuto yo con `!`, en su commit propio |
| Subir o reescribir el historial | `deny` de `git push*`, `git reset --hard*`, `git rebase*` en Bash y PowerShell (`.claude/settings.json:26-28`, `30-32`); `CLAUDE.md:29` | Permiso (deny) + instrucción | Comandos con prefijo fijo: el permiso es la herramienta justa y no depende de que el agente lo recuerde |
| Borrar archivos | `deny` de `rm -rf*` en Bash y PowerShell y de `Remove-Item -Recurse*` en PowerShell (`.claude/settings.json:29`, `33-34`); el resto de `Remove-Item` no está permitido y pregunta | Permiso (deny / preguntar) | El borrado recursivo no tiene vuelta atrás, se prohíbe; el resto de borrados se aprueban uno a uno |
| Leer secretos | `deny` de `Read(./.env)` (`.claude/settings.json:35`); `settings.json` no contiene claves | Permiso (deny) | Bloquea la lectura con la herramienta Read aunque Read esté permitido en general (deny gana a allow). Leerlo por shell (`cat`, `Get-Content`) no está permitido y pregunta |
| Dar el trabajo por terminado sin verificar | Sección "Cuándo está terminado un trabajo" (`CLAUDE.md:31-34`) y `allow` de `test`, `check`, `acceptance` (`.claude/settings.json:8-11`, `15-18`) | Instrucción (+ permiso) | Es un criterio de cierre, no una acción que se pueda bloquear. Permitir esos comandos sin preguntar hace barato verificar. Se reforzará en la fase 4 con `acceptance` como señal de parada |
| Perder el control de lo que se ejecuta (comandos encadenados, scripts nuevos) | Lista `allow` corta: solo lectura, `tasks.py test/run/check/acceptance` y `git status/diff/log` (`.claude/settings.json:4-22`) | Permiso (allow) | Se permite sin preguntar solo lo que no modifica nada fuera de `output/` y se repite mucho (fases 1 y 2); lo demás pasa por mí |

#### Mecanismo de extensión: hook `protect_inputs.py`

- **Qué problema resuelve.** `CLAUDE.md:24` prohíbe tocar `data/inbox/` y `deliveries/`, y `data/reference/` (tipos de cambio) tampoco debe tocarse. Ante datos anómalos (como los de KIV-101), lo más rápido para un agente es "arreglar" el CSV en vez de tratar el caso en el pipeline; así los tests pasan pero el pipeline sigue sin tratar ese caso.
- **Por qué un hook.** Se ejecuta antes de cada `Write`, `Edit`, `MultiEdit` o `NotebookEdit`, recibe la ruta destino por stdin y la normaliza (relativa o absoluta, `..`, separadores y mayúsculas de Windows). Si cae dentro de una carpeta protegida sale con código 2 y el motivo en stderr, que Claude Code le muestra al agente. Si el JSON no se puede leer, bloquea (falla cerrado).
- **Qué aporta frente a pedírselo al agente.** Una instrucción en CLAUDE.md se puede ignorar u olvidar en una sesión larga o tras compactar el contexto; el hook es determinista: se ejecuta siempre, sea cual sea el modelo o la sesión, y no depende de que yo revise cada diff. Además le explica al agente el motivo y la alternativa (resolverlo en el pipeline).
- **Prueba real** (PowerShell, `$env:CLAUDE_PROJECT_DIR` = raíz del repo, `... | python .claude/hooks/protect_inputs.py; $LASTEXITCODE`):

| Entrada (`tool_input`) | Código de salida |
|---|---|
| `file_path: data/inbox/2026-09-01/orders.csv` (Write) | 2 (bloqueado) |
| `file_path: docs/report.md` (Edit) | 0 (permitido) |
| `file_path: docs\..\DATA\Reference\fx_rates.csv` | 2 |
| `file_path: <ruta absoluta>/deliveries/2/orders.csv` | 2 |
| `notebook_path: data/inbox/x.ipynb` (NotebookEdit) | 2 |
| `file_path: data/inbox_notes.md` (prefijo parecido, fuera de la carpeta) | 0 |
| stdin que no es JSON | 2 |

  En el primer intento todas las pruebas salían con 2, incluida `docs/report.md`: PowerShell 5.1 antepone un BOM UTF-8 al stdin y el hook no lo aceptaba. Si solo se hubiera mirado el caso del inbox, habría parecido que funcionaba. Se corrigió leyendo stdin como `utf-8-sig` y se repitieron las pruebas.
- **Límite.** Solo cubre las herramientas de edición; las escrituras desde Bash/PowerShell dependen del permiso (preguntar) y de mi revisión.



\## 3. Ciclo de iteración



| # | Fase | Objetivo | Propuesta del agente | Mi revisión | Feedback dado | Cambio y resultado comprobado | Pendiente |
|---|---|---|---|---|---|---|---|
| 1 | 1 | Analizar el pipeline sin modificar código (KIV-100) | Análisis en plan mode con evidencias archivo:línea, recálculo según el contrato y casos sintéticos A–F | Contraste independiente de las cifras clave (7840.72 frente a 7905.15, K-10053, K-10002, GB 09-01, US 09-02) | Errores: "15 de 20 combinaciones" (son 16), frase invertida sobre K-10002, regla de CLAUDE.md ligada a fases | Recalculó con un comando: coinciden 4, no coinciden 16 | — |
| 2 | 1 | Corregir el plan antes de escribir | Al reanudar la sesión, recuperó el plan antiguo (sin correcciones) y lo dio por aprobado | Lo detuve en la petición de permiso, antes de que escribiera ningún archivo | Reenvié las tres correcciones | Aplicó las tres correcciones | — |
| 3 | 1 | Revisar docs/analysis.md antes de crearlo | Vista previa del archivo | Revisé la vista previa | Faltaba la fila de "python run.py" y había una fila de la tabla de tests truncada | Añadió la fila y el apartado "Lo que no se comprueba". El agente afirmó que la fila ya estaba en su borrador; en la vista previa que revisé no aparecía | — |
| 4 | 1 | Revisar CLAUDE.md y KIV-100.md | Reemplazo de CLAUDE.md, respuesta a Irene y verificaciones (run, test, check, interfaz, SHA-256) | Revisé el diff y las verificaciones | Regla de Co-Authored-By imprecisa y una ruta local de mi equipo en analysis.md | Aplicó los dos retoques y comprobó que no quedaban rutas locales | — |
| 5 | 1 | Commit de los entregables | Commit con mensaje en español y Co-Authored-By | Revisé el comando antes de aprobarlo | El primer intento falló en PowerShell 5.1 por las comillas del mensaje (sin crear commit) | Repetido con git commit -F: commit d7279ee, 3 archivos, git status limpio | Tag phase-1 |
| 6 | 2 | Detectar ambigüedades de KIV-101 | Inventario de anomalías con casos y comandos, y 20 ambigüedades con opciones y recomendación | Contraste independiente: 156 ventas, 18490.74, 12 netos negativos, R-1009 | Tomé 5 decisiones de negocio (D1–D5) y reduje los controles de 6 a 3 | El agente confirmó las decisiones y sus consecuencias | — |
| 7 | 2 | Escribir la especificación | spec.md (R1–R18, E1–E19, S1–S8, A1–A20) y reference\_calc.py | Contrasté las 21 filas de E1–E17, los totales y los rechazos con mi propio cálculo: coinciden | Mi mensaje llegó cortado y el agente no asumió mis decisiones; pedí guardar el script en el repositorio; el orden de prioridad del documento no coincidía con el script | Commit 1f2c8a1 con la especificación aprobada | — |
| 8 | 2 | Caso límite refund\_id vacío | El agente detectó que un refund\_id vacío daría conflicting\_duplicate | Revisé el caso sintético | Decidí corregirlo antes del plan | Commit 82f1ca0; además corrigió que un null se convertía en "None" | — |
| 9 | 2 | Plan de implementación | Borrador con T0–T12, riesgos y T10 (comprobar que los tests fallan con el código roto) | Revisión crítica del borrador | P1: acceptance se rompería con la entrega 2; P2: faltaba la fase 3 y los tags; P3: comportamientos fuera de la especificación; P4: contrato innecesario; P5: faltaba exportar la sesión y registrar las vueltas | Commit 09ddd1b con la sección "Revisión del plan" | Fase 3 |
| 10 | 4 | Bloque 1 (T1+T3): oráculo y tests en rojo | `kivora/acceptance.py` (copia temporal de 09-01..09-07, E1–E19, diferencial con `reference_calc.py`, S1–S8) y 20 tests (19 funciones, una con dos casos) en `tests/test_customer_metrics.py` | Revisé con mi tutor el rojo del bloque 1, el verde del bloque 3 y la tabla de defectos de T10; aprobé cada commit | Rojo esperado: `20 failed, 4 passed`; acceptance `19 PASS, 11 FAIL` (E1–E18 pasan sobre la salida de `reference_calc.py`, lo que valida el oráculo). Los S1–S6 decían "código 0", que era confuso: el fallo era que faltaba `rejected.csv` | Mensaje aclarado ("código 0, rejected.csv no existe"); commit d3fc9d7 | — |
| 11 | 4 | Bloque 2 (T2+T4–T6): carga, pedidos, EUR, Madrid y devoluciones | `ingest.py` con `raw_refunds`, `_pos` e `InputError`; reglas en `kivora/customer_metrics.py` | Revisé con mi tutor el rojo del bloque 1, el verde del bloque 3 y la tabla de defectos de T10; aprobé cada commit | El permiso `deny` `PowerShell(Remove-Item -Recurse*)` de la fase 3 bloqueó un comando que borraba una carpeta temporal | Repetido sin borrar (en el scratchpad). `daily_sales.csv` igual byte a byte; `raw_refunds` = 32; S7 manual → código 2; la sonda da 156 ventas, 18490.74, 1264.19 y los 6 rechazos de E18. Test `19 failed, 5 passed`, acceptance `20 PASS, 10 FAIL`; commit 4df50db | — |
| 12 | 4 | Bloque 3 (T7–T9): métricas, salidas, controles, `check` e integración | `build_metrics`, `quality_checks`, `kivora/outputs.py`, `pipeline.run` y `check.py` | Revisé con mi tutor el rojo del bloque 1, el verde del bloque 3 y la tabla de defectos de T10; aprobé cada commit | Ninguno: verde en la primera ejecución | `24 passed`; `50 PASS, 0 FAIL`; `check` OK; sin ids de la muestra fuera de `acceptance.py`; commit 0031c6c | — |
| 13 | 4 | Bloque 4 (T10): ¿detectan los tests el código roto? | Tres defectos introducidos a mano, uno cada vez, y deshechos sin commit | Revisé con mi tutor el rojo del bloque 1, el verde del bloque 3 y la tabla de defectos de T10; aprobé cada commit | Los defectos 1 y 2 **no** los detecta `acceptance` (50/50): solo los tests unitarios. Ver la tabla de T10 en la sección 4 | Cada defecto hace fallar al menos un test; tras deshacerlos, `git diff` vacío, `24 passed` y `50 PASS` | — |
| 14 | 5 | Impacto de KIV-102 antes de tocar código | `impact.md`: componentes afectados (archivo:línea), comportamiento actual (15 devoluciones nuevas como `invalid_record` con todo en verde), riesgo de `conflicting_duplicate` demostrado con un caso sintético, cinco opciones y recomendación A | Pedí el análisis sin código y con comandos. Se denegó un comando encadenado que incluía `rm -rf` | El agente lo dividió en pasos sin borrar nada. Al verificar la opción B vio que había escrito «fallarían 8 escenarios» sin comprobarlo; simulado, eran 10 (E2, E6–E11, E13, E14, E18) | Corregido antes del commit `7c79eb9`, que solo incluye `impact.md` | — |
| 15 | 5 | Decidir la sección 5 de `impact.md` | Cinco decisiones abiertas, con una recomendación en cada una | Decidí: opción A, `reason` fuera de R9, dos importes o ninguno = `invalid_record`, sin opción D, `reason` solo en `warehouse.db`, adaptar `reference_calc.py` | El resto, con la recomendación del agente: `detail` claro, `reason` ausente = `NULL`, control de rechazos masivos fuera de alcance | El agente confirmó la lista antes de escribir nada | — |
| 16 | 5 | Especificación y plan de KIV-102 | `spec.md` solo con lo que cambia (K1–K10, R19–R21, R8 y R9 modificados, E20–E25, S9–S12) y `plan.md` en cuatro commits | Aprobé el commit en la petición de permiso | — | Commit `513334f`; `24 passed`, `50 PASS, 0 FAIL` | — |
| 17 | 5 | Tests y oráculo en rojo | 8 tests nuevos y `acceptance` ampliado a 09-01..09-10 (E20–E25, «[referencia]», diferencial 01–10, S9–S12) | Aprobé el commit en la petición de permiso | El rojo coincidió con el previsto en el plan | Commit `d1780d8`: `8 failed, 24 passed`; `55 PASS, 13 FAIL`. Pasan en rojo E25, S11 y el diferencial 01–10, porque pipeline y referencia compartían el fallo | — |
| 18 | 5 | Implementación y oráculo | Normalización en `ingest.py`; R8 y R9 en `customer_metrics.py`; `reference_calc.py` adaptado sin importar `kivora/` | Pedí implementación y oráculo en el mismo commit (el agente había propuesto commits separados) | El agente ajustó K7 en la spec y el plan | Commit `ca68d77`: `32 passed`; `68 PASS, 0 FAIL` (los 50 de KIV-101 siguen); `check` OK; `run` 186 filas y 8 rechazos | — |
| 19 | 5 | Documentación de KIV-102 | Respuesta del ticket a Finanzas, secciones 3–5 de esta memoria, `sources.md`, nota en la spec de KIV-101 y `CLAUDE.md` | Aprobé el commit en la petición de permiso | — | Commit de documentación; `test` y `acceptance` en verde | Tag `phase-5` (lo pongo yo) |

\## 4. Trazabilidad

Requisito de `docs/specs/KIV-101/spec.md` → escenario (E\* con datos reales y S\* sintéticos, comprobados por `uv run python tasks.py acceptance`) → test de `tests/test_customer_metrics.py` → código. Resultado al cerrar KIV-101: `24 passed` y `50 PASS, 0 FAIL`. Con KIV-102 (tabla al final de esta sección): `uv run python tasks.py test` → `32 passed`; `uv run python tasks.py acceptance` → `68 PASS, 0 FAIL`. Las filas R8 y R9 de esta tabla las modifica KIV-102.

| R | Qué exige | Escenarios | Tests (`tests/test_customer_metrics.py`) | Código |
|---|---|---|---|---|
| R1 | Leer todo `--inbox`; `refunds.json` ausente o `[]` = nada; JSON roto → error que nombra el fichero | S7, S8 | `test_malformed_refunds_json_raises_input_error` (:357), `test_day_without_refunds_or_empty_list` (:368) | `kivora/ingest.py:57`, `kivora/__main__.py:30` |
| R2 | Última versión; desempate por carpeta y fila | E1, E2, E3, E4 | `test_dedup_exact_copies_and_versions` (:116), `test_latest_version_tie_breaks_by_folder_then_row` (:234) | `kivora/customer_metrics.py:90` |
| R3 | Validación del pedido (`invalid_record`, `unknown_currency`) | S1, S2, S3 | `test_null_and_missing_values` (:139), `test_currency_mismatch_and_unknown_currency` (:297), `test_non_positive_amounts` (:314) | `kivora/customer_metrics.py:118` |
| R4 | Venta = no cancelada y ≥ 1 pago `captured`; cuenta una vez | E3, E15, E16 | `test_dedup_exact_copies_and_versions` (:116), `test_no_duplicates_after_joins` (:215), `test_refund_of_order_that_is_not_a_sale` (:279) | `kivora/customer_metrics.py:84`, `:118` |
| R5 | EUR con `Decimal`, medio hacia arriba, por registro | E2, E15, E17 | `test_net_amount` (:196) | `kivora/customer_metrics.py:54` |
| R6 | Día en `Europe/Madrid` con horario de verano | E12, E13 | `test_madrid_date_with_daylight_saving` (:334, verano e invierno), `test_multiple_refunds_same_order` (:170) | `kivora/customer_metrics.py:41` |
| R7 | País actual normalizado; `UNKNOWN`; la venta no se pierde | E5, S4 | `test_null_and_missing_values` (:139), `test_no_duplicates_after_joins` (:215) | `kivora/customer_metrics.py:76` |
| R8 | `refund_id` vacío → `invalid_record` por aparición; validación de la devolución | S1, S2, S3 | `test_null_and_missing_values` (:139), `test_non_positive_amounts` (:314), `test_currency_mismatch_and_unknown_currency` (:297) | `kivora/customer_metrics.py:149`, `:193` |
| R9 | Duplicados por `refund_id`: copia → `duplicate_refund`; distinto → `conflicting_duplicate` | E10, S5 | `test_duplicate_and_conflicting_refunds` (:263) | `kivora/customer_metrics.py:149` |
| R10 | `order_not_found`, `order_not_sale`, `currency_mismatch` | E8, E11, S6 | `test_refund_without_order` (:186), `test_refund_of_order_that_is_not_a_sale` (:279), `test_currency_mismatch_and_unknown_currency` (:297) | `kivora/customer_metrics.py:193` |
| R11 | Límite por pedido en su moneda; se rechaza entera la que lo supera | E6, E7, E9 | `test_partial_refund` (:159), `test_multiple_refunds_same_order` (:170), `test_refund_exceeds_order` (:249) | `kivora/customer_metrics.py:226` |
| R12 | Una fila en `rejected.csv` por registro, con el primer motivo | E3, E8–E11, E16, E18 | todos los que comprueban `rejected(out)` (p. ej. :116, :186, :263, :279) | `kivora/customer_metrics.py:118`, `:149`, `:193`, `:226` |
| R13 | Fila por (día, cliente) con venta o devolución; filas solo con devoluciones | E13, E14 | `test_multiple_refunds_same_order` (:170), `test_last_purchase_date_does_not_look_ahead` (:344) | `kivora/customer_metrics.py:254` |
| R14 | Columnas de §3.1; neto puede ser negativo; `last_purchase_date` sin mirar al futuro | E6, E13, E14 | `test_net_amount` (:196), `test_last_purchase_date_does_not_look_ahead` (:344) | `kivora/customer_metrics.py:254` |
| R15 | Los tres controles, en orden | E18 (controles), E2 y E15 (control 3), E9 (control 2) | `test_net_amount` (:196), `test_refund_exceeds_order` (:249), `test_no_duplicates_after_joins` (:215), `test_outputs_are_deterministic` (:395) | `kivora/customer_metrics.py:283` |
| R16 | Formato y determinismo byte a byte | E19 | `test_outputs_are_deterministic` (:395) | `kivora/outputs.py:36` |
| R17 | Código 0 con entrada legible aunque haya rechazos | S1–S4 (conjunto), ejecución | — (los tests llaman a `run()`, no miran el código de salida) | `kivora/__main__.py:30` |
| R18 | Interfaz y salidas antiguas sin cambios | E19 | los 4 de `tests/test_pipeline.py`, sin modificar | `kivora/__main__.py`, `sql/` sin cambios |

Los siete tests mínimos de `assignment.md` §4 son los de las líneas :116, :139, :159, :170, :186, :196 y :215.

**Tests frente a código roto (T10).** Cada defecto se introdujo a mano en `kivora/customer_metrics.py`, se ejecutaron `tasks.py test` y `tasks.py acceptance`, y se deshizo sin commit (`git diff` vacío al terminar):

| Defecto | Test que falla | `acceptance` |
|---|---|---|
| Sin desempate de última versión (solo `updated_at`, gana la primera fila) | `test_latest_version_tie_breaks_by_folder_then_row` (1 failed, 23 passed) | 50 PASS: la muestra no trae dos versiones distintas con el mismo `updated_at` |
| UTC+2 fijo en vez de `Europe/Madrid` | `test_madrid_date_with_daylight_saving[2026-12-01T22:30:00Z-2026-12-01]` (1 failed, 23 passed) | 50 PASS: en septiembre Madrid está en UTC+2 |
| Sin deduplicar `refund_id` | `test_duplicate_and_conflicting_refunds` (1 failed, 23 passed) | 4 FAIL: E10 (R-1006 contado dos veces, 24.00), E18 (devuelto 1276.19), diferencial y S5 |

Conclusión: `acceptance` no basta como única red de seguridad. Dos de los tres defectos solo los detectan los tests sintéticos, porque los datos de la muestra no ejercitan esos casos.

**Test existente que fija un defecto (T11).** `tests/test_pipeline.py:66-75` (`test_gross_matches_source_total`) suma `total_amount` sin convertir divisas ni usar la última versión, así que contradice el contrato de `daily_sales` (`docs/analysis.md` §3). No se ha adaptado: `daily_sales` está fuera de alcance (D5) y el test sigue pasando sin cambios (`git diff --stat tests/test_pipeline.py` vacío). Habrá que reescribirlo cuando se corrija `daily_sales`.

**KIV-102** (`docs/specs/KIV-102/spec.md`):

| R | Qué exige | Escenarios | Tests (`tests/test_customer_metrics.py`) | Código |
|---|---|---|---|---|
| R19 | Formato por las claves de cada registro: `amount`, `refund_amount`, las dos o ninguna | E20–E24, S9–S12 | `test_new_format_refund_is_accepted` (:446), `test_mixed_formats_in_one_file` (:468), `test_both_amount_fields_is_invalid_record` (:507) | `kivora/ingest.py:44` |
| R20 | Registro normalizado; `reason` ausente o `null` = `NULL` | E20, S12 | `test_new_format_reason_null_is_accepted` (:458), `test_reason_only_in_warehouse` (:539) | `kivora/ingest.py:17`, `:44` |
| R21 | `reason` solo en `warehouse.db` | S12 | `test_reason_only_in_warehouse` (:539) | `kivora/ingest.py:17`, `:21` |
| R8 (mod.) | Dos importes o ninguno → `invalid_record`; el `detail` nombra el campo | S10, S11 | `test_both_amount_fields_is_invalid_record` (:507), `test_missing_or_bad_amount_names_the_field` (:520) | `kivora/customer_metrics.py:182-189` |
| R9 (mod.) | Duplicados sobre el registro normalizado, sin `reason` | S9, E10 (sin cambios) | `test_same_refund_in_both_formats_is_one_refund` (:479), `test_reason_does_not_count_for_duplicates` (:495), `test_duplicate_and_conflicting_refunds` (:263, sin cambios) | `kivora/customer_metrics.py:24`, `:161` |
| — | Las cifras de 01–07 no cambian | E25 | — | — |
| — | Oráculo con la misma normalización | E20–E24 «[referencia]», diferencial 01–10 | — | `docs/specs/KIV-101/reference_calc.py:27` (`ramt`), `:64`, `:76`, `:87` |



\## 5. Cambio de esquema

**Qué cambió.** Desde el 2026-09-08 `refunds.json` trae `refund_amount` en lugar de `amount` y un campo nuevo, `reason` (texto o `null`). Los ficheros antiguos no se reenvían: en `data/inbox/` hay ficheros de los dos formatos (`docs/tickets/KIV-102.md`).

**Qué pasaba sin tocar nada.** Las 15 devoluciones nuevas salían como `invalid_record`, con código 0, los tres controles en verde y `test`, `check` y `acceptance` en verde. Se perdían 311,85 € devueltos. `reference_calc.py` tenía el mismo fallo, así que el diferencial tampoco lo veía (`docs/specs/KIV-102/impact.md` §2.1). Es la lección principal: un cambio de esquema que convierte los registros en rechazos no hace fallar nada si los controles no miran los rechazos.

**Estrategia: aceptar los dos formatos, normalizando en la carga.**

- **Dónde.** En `kivora/ingest.py:44` (`normalize_refund`). El resto del pipeline recibe siempre el mismo registro, y las reglas R10–R18 no se tocan. En `customer_metrics.py` solo cambian la comparación de R9 y la validación del importe de R8.
- **Cómo se detecta el formato.** Por las claves de cada registro, no por la fecha de la carpeta ni por fichero. Así sirve con reenvíos tardíos en el formato antiguo, con reprocesos y con ficheros que mezclen formatos.
- **Registros ambiguos.** Con los dos importes o sin ninguno son `invalid_record`, con un `detail` que lo dice. No se adivina cuál vale.
- **Duplicados.** Se comparan sobre el registro normalizado (`refund_id`, `order_id`, `refunded_at`, importe y `currency`). La misma devolución en los dos formatos es una copia, no un conflicto: el riesgo 4.1 de `impact.md`, demostrado con un caso sintético.
- **`reason`.** Se guarda en `warehouse.db` (`raw_refunds.reason`) para no perder información de la fuente. No entra en ninguna regla ni en ningún CSV, porque no cambia ninguna cifra.

**Por qué no las otras opciones** (`impact.md` §5):

- Aceptar solo el formato nuevo dejaba el devuelto de 01–07 a 0,00 € y hacía fallar 10 escenarios de KIV-101 (simulado en `impact.md` A.4).
- Elegir el formato por fecha es frágil ante reenvíos.
- Detener el pipeline ante un formato desconocido cambia R1 y deja a Finanzas sin cifras por un solo registro.

**Cambios de comportamiento asumidos:**

- Dos apariciones que solo difieren en `reason` o en una clave desconocida eran `conflicting_duplicate` y ahora son copias (R9 modificado). En los datos reales no hay ningún caso.
- `raw_refunds` en `warehouse.db` tiene dos columnas nuevas, `reason` y `_format`. No es una salida con contrato, y `daily_sales` y `top_customers` no la leen.

**El oráculo también cambia.** `reference_calc.py` es de la spec de KIV-101. Adaptarlo es cambiar el oráculo de una spec aprobada, así que se decidió explícitamente (K7): se adaptó sin importar código de `kivora/`, en el mismo commit que la implementación (`ca68d77`), y los esperados literales de E20–E24 (que salen de la simulación de `impact.md`, no del pipeline) se comprueban también sobre la referencia.

**Evidencia.**

| Paso | Commit | `test` | `acceptance` |
|---|---|---|---|
| Análisis de impacto | `7c79eb9` | 24 passed | 50 PASS, 0 FAIL |
| Spec y plan | `513334f` | 24 passed | 50 PASS, 0 FAIL |
| Tests en rojo | `d1780d8` | 8 failed, 24 passed | 55 PASS, 13 FAIL |
| Implementación | `ca68d77` | 32 passed | 68 PASS, 0 FAIL |

Con los datos reales, en `daily_customer_metrics`:

- 13 devoluciones nuevas aceptadas, por 311,85 €;
- R-1034 rechazada con `order_not_found` y R-1035 con `refund_exceeds_order`;
- las filas de 01–07 idénticas (E25).

**Pendiente.** Ningún control avisa de un rechazo masivo (K10). Añadirlo cambia la estructura de `quality_report.json`, que es parte del contrato de KIV-101, así que queda para un ticket propio.



\## 6. Revisión



\_(fase 6)\_



\## 7. Qué haría distinto



\_(fase 6)\_

