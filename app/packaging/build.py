"""Build LecturePack into a Windows installer.

Steps:
  1. Read the version from desktop/version.py.
  2. Stamp packaging/win_version_info.txt with it.
  3. Run PyInstaller (onedir, windowed)  -> dist/LecturePack/
  4. Run Inno Setup (ISCC)               -> dist/installer/LecturePack-Setup-<v>.exe

Usage (from app/):
    python packaging/build.py            # full build
    python packaging/build.py --no-installer   # skip Inno Setup (exe only)

Requires: pip install -r requirements.txt -r requirements-build.txt
Inno Setup 6 (ISCC.exe) on PATH for the installer step. On the CI runner the
release workflow installs it via Chocolatey.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
PKG_DIR = APP_DIR / "packaging"


def read_version() -> str:
    text = (APP_DIR / "desktop" / "version.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        sys.exit("could not find __version__ in desktop/version.py")
    return m.group(1)


def stamp_version_info(version: str) -> None:
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    tup = f"({parts[0]}, {parts[1]}, {parts[2]}, 0)"
    path = PKG_DIR / "win_version_info.txt"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"filevers=\([^)]*\)", f"filevers={tup}", text)
    text = re.sub(r"prodvers=\([^)]*\)", f"prodvers={tup}", text)
    text = re.sub(r"'FileVersion', '[^']*'", f"'FileVersion', '{version}'", text)
    text = re.sub(r"'ProductVersion', '[^']*'", f"'ProductVersion', '{version}'", text)
    path.write_text(text, encoding="utf-8")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=APP_DIR, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-installer", action="store_true", help="build the exe but skip Inno Setup")
    args = ap.parse_args()

    version = read_version()
    print(f"Building LecturePack {version}")

    # Clean prior output.
    for d in ("build", "dist"):
        shutil.rmtree(APP_DIR / d, ignore_errors=True)

    stamp_version_info(version)

    run([sys.executable, "-m", "PyInstaller", str(PKG_DIR / "lecturepack.spec"), "--noconfirm"])

    exe = APP_DIR / "dist" / "LecturePack" / "LecturePack.exe"
    if not exe.exists():
        sys.exit(f"expected {exe} — PyInstaller build failed")
    print(f"Built {exe}")

    if args.no_installer:
        return

    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        print("WARNING: ISCC (Inno Setup) not found on PATH — skipping installer.")
        print("Install Inno Setup 6 and re-run, or use --no-installer.")
        return

    run([iscc, f"/DAppVersion={version}", str(PKG_DIR / "lecturepack.iss")])
    print(f"Installer: dist/installer/LecturePack-Setup-{version}.exe")


if __name__ == "__main__":
    main()
