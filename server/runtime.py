"""One launch path for run.py, python -m server and direct server/app.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_VENV = PROJECT_ROOT.parent / ".venv"


def main():
    if Path(sys.prefix).resolve() != SHARED_VENV.resolve():
        interpreter = SHARED_VENV / "bin" / "python"
        if not interpreter.is_file():
            raise SystemExit(f"Project virtual environment not found: {SHARED_VENV}. No packages were installed.")
        os.execv(str(interpreter), [str(interpreter), str(PROJECT_ROOT / "run.py")])

    from .check_environment import inspect_environment

    missing = inspect_environment(include_dev=False, verbose=False)
    if missing:
        raise SystemExit("Missing runtime packages in the project environment: " + ", ".join(missing) + ". Run python -m server.check_environment from the project folder before installing anything.")

    import uvicorn

    from .config import load_settings

    settings = load_settings()
    print(f"Using project Python: {sys.executable}", flush=True)
    print(f"DevBridge: http://{settings.host}:{settings.port}", flush=True)
    uvicorn.run("server.app:app", host=settings.host, port=settings.port, access_log=False)
