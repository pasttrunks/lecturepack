"""Build the Electron portable and Windows Setup artifacts.

The Electron release path is separate from the historical Qt PyInstaller
builder. It packages the production Electron host, the packaged headless
sidecar, the existing engine resources, and the UI into one candidate before
creating a portable ZIP and (when Inno Setup is available) a per-user Setup
EXE. No shell command strings are used for external tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPIKE_ROOT = ROOT / "electron-spike"
PACKAGE_JSON = SPIKE_ROOT / "package.json"
PACKAGING_SCRIPT = ROOT / "app" / "packaging" / "lecturepack.iss"
DEFAULT_ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"


def read_version() -> str:
    with PACKAGE_JSON.open("r", encoding="utf-8") as handle:
        value = json.load(handle).get("version", "")
    if not value:
        raise RuntimeError(f"Electron package version is missing: {PACKAGE_JSON}")
    return str(value)


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(part) for part in argv))
    subprocess.run(argv, cwd=str(cwd), env=env, check=True, shell=False)


def node_tool(name: str) -> str:
    """Resolve Windows command shims for shell-free subprocess execution."""
    candidates = [name]
    if os.name == "nt":
        candidates = [f"{name}.cmd", f"{name}.exe", name]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return name


def candidate_dir() -> Path:
    return SPIKE_ROOT / "dist" / "LecturePack-win32-x64"


def validate_candidate(root: Path) -> None:
    required = [
        root / "LecturePack.exe",
        root / "resources" / "app.asar",
        root / "resources" / "LecturePackSidecar" / "LecturePackSidecar.exe",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Electron candidate is incomplete: {missing}")


def validate_packaged_self_test(root: Path) -> dict[str, object]:
    """Run the authoritative packaged health contract without development tools."""
    validate_candidate(root)
    sidecar_dir = root / "resources" / "LecturePackSidecar"
    sidecar = sidecar_dir / "LecturePackSidecar.exe"
    with tempfile.TemporaryDirectory(prefix="lecturepack-release-selftest-") as temporary:
        completed = subprocess.run(
            [
                str(sidecar),
                "--resources-root", str(sidecar_dir),
                "--data-dir", temporary,
                "--self-test",
            ],
            cwd=str(sidecar_dir),
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    records = []
    for line in completed.stdout.splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    result = next((record for record in reversed(records) if record.get("event") == "self_test"), None)
    if completed.returncode != 0 or not result or result.get("passed") is not True:
        raise RuntimeError(
            "Official packaged self-test failed: "
            f"exit={completed.returncode}; stdout={completed.stdout[-4000:]}; stderr={completed.stderr[-4000:]}"
        )
    checks = {str(check.get("id")): check for check in result.get("checks", [])}
    rust = checks.get("study_core", {})
    yt_dlp = checks.get("yt_dlp", {})
    if rust.get("ok") is not True:
        raise RuntimeError("Official packaged self-test did not prove the Rust Study Core")
    if yt_dlp.get("ok") is not True:
        raise RuntimeError("Official packaged self-test did not prove yt-dlp")
    return result


def make_portable_zip(source: Path, destination: Path) -> Path:
    validate_candidate(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=False,
    ) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))
    return destination


def find_iscc(configured: str | None) -> Path | None:
    candidates = []
    if configured:
        candidates.append(Path(configured))
    on_path = shutil.which("ISCC.exe")
    if on_path:
        candidates.append(Path(on_path))
    candidates.extend([
        DEFAULT_ISCC,
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ])
    for candidate in candidates:
        if candidate.name == "ISCC.exe" and candidate.is_file():
            return candidate.resolve()
    return None


def build_installer(iscc: Path, version: str, source: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    run([
        str(iscc),
        f"/DAppVersion={version}",
        f"/DSourceDir={source.resolve()}",
        f"/DOutputDir={output.resolve()}",
        str(PACKAGING_SCRIPT),
    ], ROOT)
    installer = output / f"LecturePack-{version}-Setup.exe"
    if not installer.is_file():
        raise RuntimeError(f"Inno Setup completed without producing {installer}")
    return installer


def write_sha256sums(version: str, output: Path) -> Path:
    artifacts = sorted(path for path in output.iterdir() if path.is_file() and path.suffix.lower() in {".zip", ".exe"})
    if not artifacts:
        raise RuntimeError(f"No Electron release artifacts found in {output}")
    sums = output / f"LecturePack-{version}-SHA256SUMS.txt"
    lines = []
    for path in artifacts:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return sums


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyinstaller", help="locked PyInstaller executable used for the sidecar")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="directory containing bin/ and models/ used to build the packaged sidecar",
    )
    parser.add_argument("--iscc", help="Inno Setup compiler path")
    parser.add_argument("--output-dir", type=Path, help="release artifact directory")
    parser.add_argument("--skip-sidecar", action="store_true")
    parser.add_argument("--skip-installer", action="store_true")
    args = parser.parse_args(argv)

    version = read_version()
    output = (args.output_dir or (SPIKE_ROOT / "dist" / "releases" / version)).resolve()
    output.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment["LECTUREPACK_OFFICIAL_BUILD"] = "1"
    if args.pyinstaller:
        environment["LECTUREPACK_PYINSTALLER"] = str(Path(args.pyinstaller).resolve())
    if args.runtime_root:
        environment["LECTUREPACK_RUNTIME_ROOT"] = str(args.runtime_root.resolve())
    if not args.skip_sidecar:
        run([node_tool("npm"), "run", "package:sidecar"], SPIKE_ROOT, environment)
    run([node_tool("node"), "package-win.mjs"], SPIKE_ROOT, environment)

    candidate = candidate_dir()
    validate_candidate(candidate)
    self_test = validate_packaged_self_test(candidate)
    portable = make_portable_zip(candidate, output / f"LecturePack-{version}-Portable.zip")
    installer = None
    if not args.skip_installer:
        iscc = find_iscc(args.iscc)
        if iscc is None:
            raise RuntimeError("Inno Setup 6 ISCC.exe was not found; pass --skip-installer or --iscc")
        installer = build_installer(iscc, version, candidate, output)
    sums = write_sha256sums(version, output)

    result = {
        "version": version,
        "candidate": str(candidate),
        "portable": str(portable),
        "installer": str(installer) if installer else None,
        "sha256sums": str(sums),
        "self_test": self_test,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
