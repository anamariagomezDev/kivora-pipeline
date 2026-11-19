# Revisión independiente (fase 6, paso B)

- **Quién revisó:** un subagente `general-purpose` nuevo de Claude Code, sin el contexto de la
  conversación principal. Solo podía leer y ejecutar comandos de lectura o de test, y no modificó
  nada: `git status --porcelain` seguía vacío al terminar y HEAD seguía en `c230f99`.
- **Encargo:** revisar `assignment.md`, las specs de KIV-101 y KIV-102, `kivora/`, `tests/`,
  `tasks.py`, `README.md`, `CLAUDE.md` y `.claude/`, ejecutar `test` y `acceptance` y buscar cinco
  tipos de problema: (1) código que no cumple la spec; (2) reglas ajustadas a la muestra; (3)
  riesgos de determinismo o de modificar la entrada; (4) tests que pasarían con código roto; (5)
  documentación que no coincide con el código. Solo hallazgos con evidencia.
- **Estado al revisar:** `test` daba 32 passed y `acceptance` daba 68 PASS, 0 FAIL. Los dos en
  verde, con los 13 hallazgos de abajo.
- **Decisiones:** Ana. Los motivos son los suyos.

| id | hallazgo | quién lo encontró | gravedad | decisión | motivo |
|---|---|---|---|---|---|
| H1 | R9 compara el importe como texto: `amount: 2.0` y `refund_amount: 2.00` son `conflicting_duplicate` en el pipeline y copia en `reference_calc.py` (float) | subagente revisor independiente | alta | aceptado | Comparar el importe como Decimal en R9, en el pipeline y en `reference_calc.py`, con un test de 2.0 frente a 2.00 y una nota en la spec de KIV-102 |
| H2 | R2 compara `updated_at` como texto: `…10:00:00.500Z` < `…10:00:00Z` y gana la versión antigua; los desfases horarios fallan igual. La referencia tiene el mismo fallo | subagente revisor independiente | media | aceptado | Comparar con `parse_ts` en los dos, con un test de fracciones de segundo |
| H3 | Los controles de calidad no pueden fallar con el código actual y ningún test comprueba que detecten algo; R17 no se prueba | subagente revisor independiente | media | aceptado | Test directo de `quality_checks` con datos malos (`failed_records > 0`, `passed: false`) y test de R17 |
| H4 | `protect_inputs.py` no cubre Bash/PowerShell; los `deny` por prefijo se pueden esquivar; los hooks usan el `python` del sistema y fallan abiertos si no está | subagente revisor independiente | media | rechazado | Limitación ya documentada en `docs/report.md` §2; la cubren los permisos (preguntar) y la revisión humana |
| H5 | El hook Stop solo mira cambios sin commitear y no vigila `sql/` | subagente revisor independiente | media | parcial | Se añade `sql/` a `WATCHED`. Lo de los cambios ya commiteados queda como limitación documentada |
| H6 | `_as_text` iguala `refund_id: 7` y `"7"`, y `amount: "2.0"` y `2.0`; la referencia no | subagente revisor independiente | baja | rechazado | `docs/sources.md` garantiza importes numéricos |
| H7 | La referencia acepta fechas sin zona (no determinista entre máquinas); faltan tests de fechas sin zona, mal formadas y `status` no válido | subagente revisor independiente | baja | rechazado | `docs/sources.md` garantiza fechas ISO con `Z` |
| H8 | Días sin alguno de los CSV o subcarpetas ajenas se procesan en silencio | subagente revisor independiente | baja | rechazado | La plataforma garantiza la estructura del inbox. Queda como mejora futura |
| H9 | Tests de `daily_sales` que pasan con el código roto y contradicen el contrato | subagente revisor independiente | baja | rechazado | Decisión D5 documentada en `docs/analysis.md`; un `xfail` estricto haría fallar la suite |
| H10 | La descripción de `acceptance` está desfasada en CLAUDE.md, README y `tasks.py` (no menciona KIV-102 ni los días 08–10) | subagente revisor independiente | baja | aceptado | Actualizar las descripciones |
| H11 | README desactualizado (salidas, días, tickets, estructura) | subagente revisor independiente | baja | aceptado | README completo: qué produce, cómo se ejecuta, cómo se prueba y cómo se trabaja con el agente |
| H12 | La spec de KIV-101 dice «No se ha modificado código» y «S7 y S8 no se han ejecutado» | subagente revisor independiente | baja | aceptado | Nota de estado con fecha en la spec de KIV-101, sin reescribir lo decidido |
| H13 | CLAUDE.md no protege `data/reference/`, aunque AGENTS.md y el hook sí | subagente revisor independiente | baja | aceptado | Añadir `data/reference/` a «No se toca» en CLAUDE.md |

Resumen: 7 aceptados (H1, H2, H3, H10, H11, H12, H13), 1 parcial (H5) y 5 rechazados (H4, H6,
H7, H8, H9).

## Aplicación

- **Código (`d450965`).**
  - H1: `kivora/customer_metrics.py` (`_content`) y `reference_calc.py` (`akey`, `parse_float=Decimal`).
  - H2: `_instant_key` en el pipeline y `tkey` en la referencia.
  - H3: `test_quality_checks_detect_bad_data` y `test_failed_check_still_exits_with_zero`.
  - H5: `sql/` en `WATCHED`.
  - Notas fechadas en R9 (KIV-102) y R2 (KIV-101), y escenarios S13 y S14 en el oráculo. Los dos
    se comprueban sobre la salida y sobre la referencia.
  - Evidencia: antes del cambio, los tests nuevos de H1 y H2 daban `5 failed`. Después,
    `uv run python tasks.py test` da `40 passed` y `acceptance` da `70 PASS, 0 FAIL`.
  - Prueba de mutación: con la comparación como texto en el pipeline, S13 y S14 fallan
    (`salida: …99.00…`). Con la referencia mutada, fallan en la referencia (`referencia: …`).
- **Documentación (commit siguiente).**
  - H10: descripción de `acceptance` en `CLAUDE.md`, `README.md`, `tasks.py` y `AGENTS.md`.
  - H11: `README.md` reescrito.
  - H12: nota de estado en `docs/specs/KIV-101/spec.md`.
  - H13: `data/reference/` en «No se toca» de `CLAUDE.md`.
  - `docs/report.md` §2: `sql/` en el hook y la limitación de H5.

## Lectura

- Los dos hallazgos de código más graves (H1 y H2) no los veía el oráculo. Tanto el pipeline
  como `reference_calc.py` compartían el error (H2) o la muestra no traía el caso (H1). Un
  diferencial solo vale lo que valen la referencia y los datos con los que se ejecuta.
- H3 es un test que pasaría con código roto: la suite comprobaba que los controles salen en
  verde, nunca que puedan salir en rojo.
- El revisor intentó escribir un script en el scratchpad, no tuvo permiso y no lo reintentó: la
  restricción de solo lectura funcionó.
