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


def _find_iscc():
    """Locate ISCC.exe when it isn't on PATH (common Inno Setup 6 install dirs)."""
    import os
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


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


def check_clean_state(dist_app: Path) -> list:
    """Return a list of packaging-cleanliness violations for a built onedir.

    Beta.3 §3: a fresh install must start with ZERO jobs. Fail the build if the
    output bundles any user/job/dev state, and confirm the core engine is
    actually present (a silent bundle_engine regression otherwise only surfaces
    at runtime on a user's machine). Pure/inspectable so it can be unit-tested
    against a synthetic tree.
    """
    import fnmatch

    violations = []
    dist_app = Path(dist_app)

    forbidden_name_globs = ["*config.json", "*.job.json", "*.db",
                            "*.sqlite", "*.sqlite3"]
    forbidden_dir_names = {"jobs", "exports", "thumbs", "LecturePackData",
                           "study_packs"}

    for path in dist_app.rglob("*"):
        rel = path.relative_to(dist_app)
        parts = set(rel.parts)
        # Qt ships its own JSON assets under _internal — allowlist those only.
        under_internal = "_internal" in parts
        if path.is_dir():
            if path.name in forbidden_dir_names:
                violations.append(f"forbidden dir bundled: {rel}")
            continue
        name = path.name
        for pat in forbidden_name_globs:
            if fnmatch.fnmatch(name, pat):
                violations.append(f"forbidden file bundled: {rel}")
        # Any stray top-level/app JSON (not a Qt _internal asset) is suspect —
        # this is how a job manifest/state.json would leak in.
        if name.endswith(".json") and not under_internal:
            violations.append(f"unexpected json bundled: {rel}")

    # Required engine payload must be present AND non-empty.
    required = [
        "LecturePack.exe",
        "bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/whisper-cli.exe",
        "bin/whisper.dll", "bin/ggml.dll", "bin/ggml-base.dll",
        "models/ggml-base.en.bin",
    ]
    for r in required:
        p = dist_app / r
        if not p.is_file() or p.stat().st_size == 0:
            violations.append(f"missing/empty required payload: {r}")
    if not list((dist_app / "bin").glob("ggml-cpu-*.dll")):
        violations.append("missing CPU backend DLLs: bin/ggml-cpu-*.dll")

    return violations


def validate_clean_state(dist_app: Path = None) -> None:
    """Build gate wrapping check_clean_state — abort the build on any violation."""
    if dist_app is None:
        dist_app = APP_DIR / "dist" / "LecturePack"
    violations = check_clean_state(dist_app)
    if violations:
        sys.exit("CLEAN-STATE GATE FAILED —\n  " + "\n  ".join(violations))
    print("Clean-state gate OK — no job/dev data bundled; engine payload present.")


def bundle_engine() -> None:
    """Copy the CORE transcription engine into the PyInstaller output so the
    installed app works out of the box: FFmpeg, whisper.cpp CPU (+ its DLLs),
    and the base.en model. GPU packs (Vulkan/CUDA) stay optional/on-demand and
    are deliberately excluded to keep the installer lean.
    """
    repo = APP_DIR.parent
    dist_app = APP_DIR / "dist" / "LecturePack"
    dst_bin = dist_app / "bin"
    dst_models = dist_app / "models"
    dst_bin.mkdir(parents=True, exist_ok=True)
    dst_models.mkdir(parents=True, exist_ok=True)

    def _copy(src: Path, dst: Path):
        if not src.exists() or src.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — missing or empty {src}")
        shutil.copy2(src, dst)
        if not dst.exists() or dst.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — copy produced empty {dst}")

    # FFmpeg / FFprobe
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        _copy(repo / "bin" / name, dst_bin / name)

    # whisper.cpp CPU: the CLI + only the DLLs it needs (skip the other tools:
    # parakeet/wchess/server/stream/tests/SDL2).
    rel = repo / "bin" / "Release"
    wanted = ["whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll"]
    wanted += sorted(p.name for p in rel.glob("ggml-cpu-*.dll"))
    for name in wanted:
        _copy(rel / name, dst_bin / name)

    # Core model — base.en (the "works immediately" default).
    _copy(repo / "models" / "ggml-base.en.bin", dst_models / "ggml-base.en.bin")

    # App icon — copied next to the EXE so main.py can load it at runtime.
    ico_src = APP_DIR / "packaging" / "lecturepack.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, dist_app / "lecturepack.ico")

    print(f"Bundled core engine: ffmpeg + {len(wanted)} whisper files + ggml-base.en.bin")


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

    # Bundle the core engine so the installed app transcribes out of the box.
    bundle_engine()

    # Clean-state gate: fresh install must ship zero jobs/dev data, and the
    # engine payload must actually be present (beta.3 §3).
    validate_clean_state()

    # Portable ZIP is independent of Inno Setup — always produced.
    make_portable_zip(version)

    if args.no_installer:
        write_sha256sums(version)
        validate_release_assets(version, require_installer=False)
        return

    iscc = shutil.which("ISCC") or shutil.which("iscc") or _find_iscc()
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
