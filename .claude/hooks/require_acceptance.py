"""Hook Stop: no deja que el agente dé el trabajo por terminado con el oráculo en rojo.

Se registra en el evento Stop. Lee el JSON del evento por stdin y:

- si `stop_hook_active` es true (el agente ya está continuando por este hook),
  sale con 0 para no entrar en bucle;
- si `git status --porcelain` no muestra cambios en kivora/, tests/, tasks.py ni
  docs/specs/, sale con 0 (no ralentiza las respuestas que no tocan código);
- si los hay, ejecuta `uv run python tasks.py acceptance` en CLAUDE_PROJECT_DIR:
  si falla, escribe las líneas FAIL en stderr y sale con 2 (Claude Code impide la
  parada y se las muestra al agente para que siga corrigiendo); si pasa, sale con 0.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

WATCHED = ("kivora/", "tests/", "tasks.py", "docs/specs/")


def changed_paths(project_dir: Path) -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=project_dir, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    paths = []
    for line in out.splitlines():
        # "XY ruta" o "XY origen -> destino" (renombrados): cuentan las dos.
        for part in line[3:].split(" -> "):
            paths.append(part.strip().strip('"').replace("\\", "/"))
    return paths


def watched(path: str) -> bool:
    return any(path == w or (w.endswith("/") and path.startswith(w)) for w in WATCHED)


def main() -> int:
    try:
        # utf-8-sig: tolera el BOM que antepone PowerShell 5.1 al redirigir stdin.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # Aquí no se puede fallar cerrado sin riesgo de bucle: se avisa y se deja parar.
        print(f"require_acceptance: JSON de entrada no válido ({exc})", file=sys.stderr)
        return 0

    if event.get("stop_hook_active"):
        return 0

    project_dir = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    hits = [p for p in changed_paths(project_dir) if watched(p)]
    if not hits:
        return 0

    result = subprocess.run(
        ["uv", "run", "python", "tasks.py", "acceptance"],
        cwd=project_dir, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return 0

    output = result.stdout + result.stderr
    fails = [line for line in output.splitlines() if line.startswith("FAIL")]
    print(
        "No se puede dar el trabajo por terminado: `uv run python tasks.py acceptance` "
        f"falla (código {result.returncode}) con cambios en {', '.join(sorted(set(hits)))}.",
        file=sys.stderr,
    )
    print("\n".join(fails) if fails else output[-2000:], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
