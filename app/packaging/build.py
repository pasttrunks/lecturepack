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
    # The Windows version resource needs a numeric 4-tuple, so extract only the
    # leading numeric components (e.g. "0.9.0-beta.1" -> 0, 9, 0).
    nums = re.findall(r"\d+", version)
    parts = (nums + ["0", "0", "0"])[:3]
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


def validate_release_assets(version: str, require_installer: bool = True) -> None:
    """Release gate: fail the build if the updater's required assets are absent.

    The in-app updater downloads exactly these names and verifies them against
    SHA256SUMS, so a release missing any of them (or a checksum file that does
    not list both binaries) would be undiscoverable/uninstallable.
    """
    out = APP_DIR / "dist" / "installer"
    portable = out / f"LecturePack-{version}-Portable.zip"
    sums = out / f"LecturePack-{version}-SHA256SUMS.txt"
    setup = out / f"LecturePack-{version}-Setup.exe"
    required = [portable, sums] + ([setup] if require_installer else [])
    missing = [p.name for p in required if not p.exists() or p.stat().st_size == 0]
    if missing:
        sys.exit(f"RELEASE GATE FAILED — missing/empty updater assets: {missing}")
    text = sums.read_text(encoding="utf-8")
    for asset in ([portable, setup] if require_installer else [portable]):
        if asset.name not in text:
            sys.exit(f"RELEASE GATE FAILED — {sums.name} does not list {asset.name}")
    print(f"Release gate OK — validated: {[p.name for p in required]}")


def make_portable_zip(version: str) -> Path:
    """Zip the PyInstaller onedir output into a portable archive."""
    import zipfile

    src = APP_DIR / "dist" / "LecturePack"
    out_dir = APP_DIR / "dist" / "installer"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"LecturePack-{version}-Portable.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, Path("LecturePack") / path.relative_to(src))
    print(f"Portable: dist/installer/{zip_path.name}")
    return zip_path


def write_sha256sums(version: str) -> Path:
    """Write SHA256SUMS.txt over every artifact in dist/installer."""
    import hashlib

    out_dir = APP_DIR / "dist" / "installer"
    sums_path = out_dir / f"LecturePack-{version}-SHA256SUMS.txt"
    lines = []
    for path in sorted(out_dir.iterdir()):
        if path.is_file() and path.name != sums_path.name and path.suffix in (".exe", ".zip"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checksums: dist/installer/{sums_path.name}")
    return sums_path


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

    # Portable ZIP is independent of Inno Setup — always produced.
    make_portable_zip(version)

    if args.no_installer:
        write_sha256sums(version)
        validate_release_assets(version, require_installer=False)
        return

    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        print("WARNING: ISCC (Inno Setup) not found on PATH — skipping installer.")
        print("Install Inno Setup 6 and re-run, or use --no-installer.")
        write_sha256sums(version)
        return

    run([iscc, f"/DAppVersion={version}", str(PKG_DIR / "lecturepack.iss")])
    print(f"Installer: dist/installer/LecturePack-{version}-Setup.exe")

    # Checksums last so they cover the installer + portable ZIP.
    write_sha256sums(version)
    validate_release_assets(version, require_installer=True)


if __name__ == "__main__":
    main()
