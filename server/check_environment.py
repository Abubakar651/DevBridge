"""Inspect this interpreter's environment. This command never installs packages."""

import argparse
import importlib.metadata
import sys
from pathlib import Path

RUNTIME_PACKAGES = ("fastapi", "uvicorn", "httpx", "pydantic", "requests")
SHARED_VENV = Path(__file__).resolve().parents[2] / ".venv"


def inspect_environment(*, include_dev=False, verbose=True):
    missing = []
    for package in (*RUNTIME_PACKAGES, *(("pytest",) if include_dev else ())):
        try:
            version = importlib.metadata.version(package)
            if verbose:
                print(f"{package}: {version} (installed)")
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
            if verbose:
                print(f"{package}: not installed")
    return missing


def main(include_dev=False):
    print(f"Interpreter: {sys.executable}")
    print(f"Virtual environment: {sys.prefix}")
    print(f"Expected project environment: {SHARED_VENV}")
    missing = inspect_environment(include_dev=include_dev)
    if Path(sys.prefix).resolve() != SHARED_VENV.resolve():
        print("Use .venv/bin/python to inspect the project environment. Nothing was installed.")
        return 1
    if missing:
        print("Only these packages are missing: " + ", ".join(missing))
        if missing == ["pytest"]:
            print("pytest is optional test tooling; it is not needed to run the application.")
        return 1
    print("All requested packages are installed in the project environment. No installation needed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="Also inspect optional pytest tooling.")
    raise SystemExit(main(parser.parse_args().dev))
