# AGENTS.md

Instrucciones para agentes de programación distintos de Claude Code. La fuente de verdad es
[`CLAUDE.md`](CLAUDE.md): contexto del proyecto, reglas de negocio y criterio de "terminado".
Si este archivo y `CLAUDE.md` discrepan, manda `CLAUDE.md`.

## Comandos (verificados; siempre con `uv run`)

- Preparar el entorno: `uv sync`
- Ejecutar el pipeline: `uv run python tasks.py run`
- Tests: `uv run python tasks.py test`
- Comprobar la salida: `uv run python tasks.py check`
- Oráculo de KIV-101 y KIV-102: `uv run python tasks.py acceptance` (código 0 solo si pasan todos)
- Interfaz oficial: `uv run python -m kivora --inbox data/inbox --reference data/reference --out output`

Un trabajo está terminado cuando `test`, `check` y `acceptance` están en verde.

## No se toca

- `data/inbox/`, `data/reference/` y `deliveries/`, nunca. Los problemas de los datos se
  resuelven en el pipeline.
- Las entregas solo se reciben con `uv run python tasks.py deliver N`, en un commit propio.
- La interfaz `python -m kivora` y sus opciones y valores por defecto.
- El código no se modifica sin una especificación aprobada en `docs/specs/`.
- Un test que contradice el contrato no se adapta en silencio: se decide y se justifica.
- El historial de Git: sin rebase, amend de commits publicados ni force-push.
