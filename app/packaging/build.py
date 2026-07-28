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
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from lecturepack.infrastructure.runtime_inventory import (
    RuntimeInventoryError,
    canonical_inventory,
    inventory_for_root,
    resolve_inventory,
)
from lecturepack.infrastructure.runtime_validation import RuntimeValidator, SmokeEvidence
from lecturepack.infrastructure.whisper_path_staging import WhisperPathStaging

APP_DIR = Path(__file__).resolve().parent.parent
PKG_DIR = APP_DIR / "packaging"


def required_runtime_payload(
    runtime_root: Path, cpu_dll_names: tuple[str, ...] | list[str] = (),
) -> dict[str, Path]:
    """Map every canonical package entry to its destination below ``runtime_root``."""
    root = Path(runtime_root)
    return {entry: root / entry for entry in canonical_inventory(cpu_dll_names)}


def run_disposable_runtime_smoke(
    runtime_root: Path | None = None, timeout_ms: int = 30_000,
) -> SmokeEvidence:
    """Run the real bundled CLI under a bounded, argument-array-only smoke test."""
    if runtime_root is None:
        configured = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
        if not configured:
            raise AssertionError("clean onedir fixture is required for packaged smoke")
        runtime_root = Path(configured)
    root = Path(runtime_root)
    if not root.is_dir():
        raise AssertionError(f"clean onedir fixture is required but missing: {root}")
    try:
        required = resolve_inventory(root)
    except RuntimeInventoryError as exc:
        raise AssertionError(f"clean onedir fixture is invalid: {exc}") from exc

    validator = RuntimeValidator(timeout_ms=timeout_ms)
    for tool in (required["bin/ffmpeg.exe"], required["bin/ffprobe.exe"]):
        evidence = validator.run(str(tool), ["-version"])
        if not evidence.ok:
            raise AssertionError(f"{tool.name} smoke failed: {evidence}")
    with_staging = WhisperPathStaging(
        required["models/ggml-base.en.bin"], required["smoke/runtime-smoke.wav"],
        root / "smoke-output" / "transcript")
    staged_model, staged_wav, _ = with_staging.prepare()
    unexpected_artifacts: list[str] = []
    try:
        evidence = validator.run(
            str(required["bin/whisper-cli.exe"]),
            ["-m", staged_model, "-f", staged_wav, "-t", "1", "-nt"],
        )
    finally:
        # The smoke deliberately has no output-file argument.  Inspect the
        # complete private staging tree before cleanup so a CLI default output
        # beside the staged WAV cannot be hidden by the disposable directory.
        if with_staging.root is not None:
            expected_inputs = {Path(staged_model), Path(staged_wav)}
            unexpected_artifacts = [
                str(path.relative_to(with_staging.root))
                for path in with_staging.root.rglob("*")
                if path.is_file() and path not in expected_inputs
            ]
        with_staging.cleanup()
    if unexpected_artifacts:
        raise AssertionError(
            "whisper packaged smoke created unexpected output artifacts: "
            f"{unexpected_artifacts}; evidence: {evidence}"
        )
    if not evidence.ok:
        raise AssertionError(f"whisper packaged smoke failed: {evidence}")
    if not all(argument.isascii() for argument in evidence.argv[2:6]):
        raise AssertionError("whisper smoke native argv must use ASCII staging paths")
    return evidence


def run_disposable_packaged_repair_proof(
    fixture_root: Path, timeout_ms: int = 30_000,
) -> dict[str, object]:
    """Exercise signed repair against a copied current-code onedir only.

    The caller must supply an actual PyInstaller onedir.  The package is copied
    below a hostile Unicode-and-space path before its canonical inventory is
    published, deliberately damaged, repaired from exact signed fixture URLs,
    and re-admitted.  No source runtime file is modified.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.infrastructure.release_trust import ReleaseTrustVerifier, official_release_urls
    from lecturepack.infrastructure.runtime_generation import RuntimeGenerationStore
    from lecturepack.infrastructure.runtime_inventory import resolve_inventory
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService
    from lecturepack.services.runtime_repair import RuntimeRepairService

    source = Path(fixture_root).resolve()
    executable = source / "LecturePack.exe"
    if not executable.is_file():
        raise AssertionError(f"clean onedir fixture is required but missing executable: {executable}")
    resolve_inventory(source)
    version = read_version()
    builder_path = REPO_DIR / "scripts" / "build_signed_runtime_release.py"
    spec = importlib.util.spec_from_file_location("build_signed_runtime_release", builder_path)
    if spec is None or spec.loader is None:
        raise AssertionError("signed runtime release builder is unavailable")
    release_builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release_builder)

    class FixtureTransport:
        def __init__(self, values: dict[str, bytes]) -> None:
            self.values = values
            self.requests: list[str] = []

        def get(self, url: str) -> bytes:
            self.requests.append(url)
            return self.values[url]

    with tempfile.TemporaryDirectory(prefix="LecturePack packaged proof ") as temporary:
        workspace = Path(temporary)
        installed = workspace / "installed 漢 runtime"
        shutil.copytree(source, installed)
        profile = workspace / "writable data profile"
        config = ConfigManager(str(profile))
        config.resource_dir = str(installed)
        store = RuntimeGenerationStore(config.resolve_data_dir())

        def assess(root: Path):
            return RuntimeBootstrapService(config, runtime_root=root).assess(trigger="repair")

        payload = resolve_inventory(installed)
        previous = store.publish_from_directory(payload, admit=lambda root: assess(root).state == "HEALTHY")
        damaged = previous.root / "bin" / "ffmpeg.exe"
        damaged.write_bytes(b"damaged packaged component")
        damaged_admission = RuntimeBootstrapService(config).assess()
        if damaged_admission.state != "SETUP_REQUIRED":
            raise AssertionError("damaged active package did not require setup")

        release_directory = workspace / "signed release assets"
        private_key = Ed25519PrivateKey.generate()
        release_builder.build_signed_runtime_release(
            app_version=version,
            runtime_root=installed,
            output_directory=release_directory,
            private_key_hex=private_key.private_bytes_raw().hex(),
        )
        urls = official_release_urls(version)
        values = {url: (release_directory / name).read_bytes() for name, url in urls.items()}
        verifier = ReleaseTrustVerifier(version, private_key.public_key().public_bytes_raw().hex())
        repair = RuntimeRepairService(
            version,
            FixtureTransport(values),
            verifier=verifier,
            admission_evidence={"bin/ffmpeg.exe": "Media tools"},
            generation_store=store,
            bootstrap_assessor=assess,
        )
        repair.begin_repair_offer("repair-current-onedir")
        repair.perform_repair("repair-current-onedir")
        repaired = store.read_active()
        if repaired is None:
            raise AssertionError("signed repair did not select an active generation")
        evidence = run_disposable_runtime_smoke(repaired.root, timeout_ms=timeout_ms)
        admission = RuntimeBootstrapService(config).assess()

        broken_values = dict(values)
        archive_url = next(url for url in urls.values() if url.endswith("Runtime-ffmpeg.zip"))
        broken_values[archive_url] = broken_values[archive_url][:-1] + b"!"
        rollback = RuntimeRepairService(
            version,
            FixtureTransport(broken_values),
            verifier=verifier,
            admission_evidence={"bin/ffmpeg.exe": "Media tools"},
            generation_store=store,
            bootstrap_assessor=assess,
        )
        rollback.begin_repair_offer("rollback")
        try:
            rollback.perform_repair("rollback")
        except Exception:
            pass
        rollback_active = store.read_active()

        cancelled = RuntimeRepairService(
            version,
            FixtureTransport(values),
            verifier=verifier,
            admission_evidence={"bin/ffmpeg.exe": "Media tools"},
            generation_store=store,
            bootstrap_assessor=assess,
        )
        cancelled.begin_repair_offer("cancel")
        cancelled.cancel("cancel")
        try:
            cancelled.perform_repair("cancel")
        except Exception:
            pass
        cancelled_active = store.read_active()

        return {
            "fixture_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "previous_generation": previous.generation_id,
            "repaired_active_generation": repaired.generation_id,
            "admission_state": admission.state,
            "damaged_admission_state": damaged_admission.state,
            "rollback_generation": rollback_active.generation_id if rollback_active else None,
            "cancel_generation": cancelled_active.generation_id if cancelled_active else None,
            "smoke_evidence": {
                "argv": evidence.argv,
                "exit_code": evidence.exit_code,
                "duration_ms": evidence.duration_ms,
                "stdout": evidence.stdout,
                "stderr": evidence.stderr,
            },
        }


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
                           "study_packs", "downloads"}

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

    if not (dist_app / "LecturePack.exe").is_file() or (dist_app / "LecturePack.exe").stat().st_size == 0:
        violations.append("missing/empty required payload: LecturePack.exe")
    try:
        resolve_inventory(dist_app, inventory_for_root(dist_app))
    except RuntimeInventoryError as exc:
        violations.append(str(exc))

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

    def _copy(src: Path, dst: Path):
        if not src.exists() or src.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — missing or empty {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if not dst.exists() or dst.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — copy produced empty {dst}")

    rel = repo / "bin" / "Release"
    cpu_dll_names = tuple(sorted(path.name for path in rel.glob("ggml-cpu-*.dll")))
    source_payload: dict[str, Path] = {}
    for entry in canonical_inventory(cpu_dll_names):
        if entry in {"bin/ffmpeg.exe", "bin/ffprobe.exe"}:
            source_payload[entry] = repo / entry
        elif entry.startswith("bin/"):
            source_payload[entry] = rel / Path(entry).name
        elif entry == "models/ggml-base.en.bin":
            source_payload[entry] = repo / entry
        else:
            source_payload[entry] = PKG_DIR / "assets" / Path(entry).name
    for entry, destination in required_runtime_payload(dist_app, cpu_dll_names).items():
        _copy(source_payload[entry], destination)

    # App icon — copied next to the EXE so main.py can load it at runtime.
    ico_src = APP_DIR / "packaging" / "lecturepack.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, dist_app / "lecturepack.ico")

    print(f"Bundled canonical CPU runtime: {len(source_payload)} payload files")


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
