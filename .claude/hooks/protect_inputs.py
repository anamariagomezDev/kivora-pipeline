"""Hook PreToolUse: impide que el agente escriba en los datos de entrada.

Se registra para Write|Edit|MultiEdit|NotebookEdit. Lee el JSON del evento por
stdin y, si la ruta destino cae dentro de una carpeta protegida, sale con
código 2 y deja el motivo en stderr (Claude Code bloquea la llamada y se lo
muestra al agente). En cualquier otro caso sale con 0.
"""

import json
import os
import sys
from pathlib import Path

PROTECTED = ("data/inbox", "data/reference", "deliveries")


def target_path(tool_input: dict) -> str:
    return tool_input.get("file_path") or tool_input.get("notebook_path") or ""


def is_protected(raw: str, project_dir: Path) -> str | None:
    path = Path(raw)
    if not path.is_absolute():
        path = project_dir / path
    # resolve() normaliza "..", "." y separadores; strict=False porque el
    # archivo puede no existir todavía (Write crea archivos nuevos).
    resolved = Path(os.path.normcase(path.resolve(strict=False)))
    root = Path(os.path.normcase(project_dir.resolve(strict=False)))
    for rel in PROTECTED:
        protected = Path(os.path.normcase(root / rel))
        if resolved == protected or protected in resolved.parents:
            return rel
    return None


def main() -> int:
    try:
        # utf-8-sig: tolera el BOM que antepone PowerShell 5.1 al redirigir stdin.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # Ante una entrada ilegible, mejor bloquear que dejar pasar.
        print(f"protect_inputs: JSON de entrada no válido ({exc})", file=sys.stderr)
        return 2

    raw = target_path(event.get("tool_input") or {})
    if not raw:
        return 0

    project_dir = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    hit = is_protected(raw, project_dir)
    if hit:
        print(
            f"Bloqueado: '{raw}' está dentro de {hit}/, que no se modifica nunca "
            "(CLAUDE.md, 'No se toca'). Los problemas de los datos se resuelven "
            "en el pipeline; las entregas solo con 'tasks.py deliver N'.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
