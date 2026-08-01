"""Clean release build: venv from locked requirements, then build.

Creates (or refreshes) a dedicated .venv-release at the repo root,
installs the exact dependencies from app/requirements.txt and
app/requirements-build.txt, then runs app/packaging/build.py inside
that venv. Any extra arguments are forwarded to build.py.

Usage:
    python scripts/release_build.py              # full build
    python scripts/release_build.py --no-installer
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV = REPO / ".venv-release"
APP = REPO / "app"


def _venv_python() -> Path:
    return VENV / "Scripts" / "python.exe"


def _run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main() -> int:
    if not _venv_python().is_file():
        print(f"Creating release venv at {VENV}")
        _run([sys.executable, "-m", "venv", str(VENV)])

    py = str(_venv_python())

    _run([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    _run([
        py, "-m", "pip", "install",
        "-r", str(APP / "requirements.txt"),
        "-r", str(APP / "requirements-build.txt"),
        "--quiet",
    ])

    build_cmd = [py, str(APP / "packaging" / "build.py")] + sys.argv[1:]
    _run(build_cmd, cwd=str(APP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
