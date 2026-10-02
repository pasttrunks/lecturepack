from pathlib import Path
import hashlib
import importlib.util
import os
import sys

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


SPIKE_ROOT = Path(SPECPATH).resolve()
REPO_ROOT = SPIKE_ROOT.parent
# PyInstaller is invoked with the locked canonical virtualenv, which also has
# an installed `lecturepack` package. Put this checkout first so the frozen
# sidecar contains the exact source revision being packaged rather than a
# stale site-packages copy from another worktree/release.
sys.path.insert(0, str(REPO_ROOT))
RUNTIME_ROOT = Path(os.environ.get("LECTUREPACK_RUNTIME_ROOT", str(REPO_ROOT))).expanduser().resolve()
OUT_NAME = "LecturePackSidecar"
OFFICIAL_BUILD = os.environ.get("LECTUREPACK_OFFICIAL_BUILD") == "1"

# Pinned JavaScript runtime for yt-dlp's EJS system.
#
# Modern yt-dlp cannot fully extract YouTube without an external JS runtime,
# and Deno is upstream's default. Bundling it means a customer never installs
# Deno, Node or Python. The digest is the SHA-256 of deno.exe unpacked from
# Deno's official deno-x86_64-pc-windows-msvc.zip for this version, whose own
# published .sha256sum was verified at the time of pinning.
DENO_VERSION = "2.9.5"
DENO_SHA256 = "98f8c2a2d470e4ccb04c935c86ff8050817d877762aec5eaeeb9e409ccb3b9fd"


def required(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"Required sidecar runtime file is missing: {path}")
    return path


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


ffmpeg = required(RUNTIME_ROOT / "bin" / "ffmpeg.exe")
ffprobe = required(RUNTIME_ROOT / "bin" / "ffprobe.exe")
whisper = required(RUNTIME_ROOT / "bin" / "Release" / "whisper-cli.exe")
model = required(RUNTIME_ROOT / "models" / "ggml-base.en.bin")
smoke_wav = required(REPO_ROOT / "app" / "packaging" / "assets" / "runtime-smoke.wav")
release_dir = RUNTIME_ROOT / "bin" / "Release"
msvc_runtime_dir = Path(os.environ.get(
    "LECTUREPACK_MSVC_RUNTIME_DIR",
    str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"),
)).expanduser().resolve()


# The sidecar ships the verified CPU whisper.cpp binary and its DLLs only.
# Vulkan/CUDA directories are intentionally outside this first migration slice.
runtime_datas = [
    (str(ffmpeg), "bin"),
    (str(ffprobe), "bin"),
    (str(whisper), "bin/Release"),
    (str(model), "models"),
    (str(smoke_wav), "smoke"),
]
runtime_datas.extend(
    (str(path), "bin/Release")
    for path in sorted(release_dir.glob("*.dll"))
)

# Bundled Deno for yt-dlp's EJS YouTube support. Verified against the pinned
# digest at build time so an official installer can never ship an unexpected
# native runtime, and so URL import never downloads a runtime onto a customer
# machine on first use.
deno = RUNTIME_ROOT / "bin" / "deno.exe"
if deno.is_file():
    actual_deno_sha = sha256_of(deno)
    if actual_deno_sha != DENO_SHA256:
        raise SystemExit(
            f"Bundled Deno does not match the pinned digest for {DENO_VERSION}.\n"
            f"  expected: {DENO_SHA256}\n"
            f"  actual:   {actual_deno_sha}\n"
            f"  path:     {deno}"
        )
    runtime_datas.append((str(deno), "bin"))
elif OFFICIAL_BUILD:
    raise SystemExit(
        "Official LecturePack build requires the bundled JavaScript runtime for "
        f"YouTube support: {deno}\n"
        f"Download deno-x86_64-pc-windows-msvc.zip for Deno {DENO_VERSION}, verify "
        "its published .sha256sum, and unpack deno.exe into bin/."
    )

# whisper.cpp imports MSVCP140 directly. PyInstaller carries VCRUNTIME140 for
# Python but does not reliably discover this child-process dependency.
# App-local deployment keeps portable and per-user installs independent of a
# machine-wide VC++ redistributable.
msvcp140 = msvc_runtime_dir / "msvcp140.dll"
if msvcp140.is_file():
    runtime_datas.append((str(msvcp140), "."))
elif OFFICIAL_BUILD:
    raise SystemExit(
        "Official LecturePack build requires the app-local MSVC runtime: "
        f"{msvcp140}"
    )


hiddenimports = [
    "send2trash",
    "lecturepack.services.transcript_store",
    "lecturepack.services.transcript_service",
    "lecturepack.services.transcript_formats",
    "lecturepack.services.study_service",
    "lecturepack.services.study_v2",
    "lecturepack.services.ai_gateway",
    "lecturepack.services.ai_study_service",
    "lecturepack.services.packaged_health",
    # Belt-and-braces. PyInstaller's modulegraph does follow function-level
    # imports, and the build xref confirms it already collects this one, so the
    # entry is not load-bearing today. It is declared anyway because the caption
    # pass swallows every exception: were the module ever to go missing, the
    # only symptom would be downloaded lectures quietly transcribing from
    # scratch, with nothing in any log to say the feature had stopped working.
    "lecturepack.services.source_captions",
    # Same reasoning: the demo Study cache is imported inside a function whose
    # failure path is "build the pack the slow way", so a missing module would
    # show up only as the guided demo taking minutes again.
    "lecturepack.services.demo_study_cache",
    "lecturepack.infrastructure.whisper_detector",
    "lecturepack.infrastructure.whisper_path_staging",
]

# The Rust Study Core native extension (lecturepack_study_core.pyd) is a
# build-time dependency. It is built with maturin and installed into the
# project venv; PyInstaller collects it as a binary so the packaged sidecar
# can import it without customer Rust.
_study_core_candidate = REPO_ROOT / ".venv" / "Lib" / "site-packages" / "lecturepack_study_core" / "lecturepack_study_core.cp312-win_amd64.pyd"
if not _study_core_candidate.is_file():
    _study_core_candidate = Path(sys.prefix) / "Lib" / "site-packages" / "lecturepack_study_core" / "lecturepack_study_core.cp312-win_amd64.pyd"

_study_core_pyd = Path(os.environ.get(
    "LECTUREPACK_STUDY_CORE_PYD",
    str(_study_core_candidate),
)).expanduser().resolve()
if _study_core_pyd.is_file():
    binaries = [(str(_study_core_pyd), "lecturepack_study_core")]
else:
    if OFFICIAL_BUILD:
        raise SystemExit(
            "Official LecturePack build requires lecturepack_study_core.pyd: "
            f"{_study_core_pyd}"
        )
    binaries = []
try:
    # yt-dlp resolves extractors by name at runtime. Collecting its extractor
    # modules is required for URL import to work without customer Python.
    hiddenimports += collect_submodules("yt_dlp")
except Exception as exc:
    if OFFICIAL_BUILD:
        raise SystemExit(f"Official LecturePack build requires yt-dlp: {exc}") from exc
    # A build environment without the optional URL provider still produces a
    # valid local-file candidate; the sidecar reports link import unavailable.
    pass
if OFFICIAL_BUILD and importlib.util.find_spec("yt_dlp") is None:
    raise SystemExit("Official LecturePack build requires importable yt-dlp")

# yt-dlp's EJS support package. Without it yt-dlp cannot solve YouTube's
# JavaScript challenges even when a runtime is present, so an official build
# that omits it would ship visibly degraded YouTube support.
try:
    hiddenimports += collect_submodules("yt_dlp_ejs")
    # The actual challenge solver is shipped as minified JavaScript data
    # (yt/solver/*.js), not as Python modules, so it must be collected
    # separately or the packaged build would import cleanly and still fail.
    _ejs_data = collect_data_files("yt_dlp_ejs", includes=["**/*.js"])
    if OFFICIAL_BUILD and not _ejs_data:
        raise SystemExit(
            "Official LecturePack build found no yt-dlp-ejs solver JavaScript; "
            "YouTube JS challenges would fail at runtime."
        )
    runtime_datas += _ejs_data
except SystemExit:
    raise
except Exception as exc:
    if OFFICIAL_BUILD:
        raise SystemExit(
            f"Official LecturePack build requires yt-dlp-ejs: {exc}\n"
            "Install it with: pip install -U \"yt-dlp[default]\""
        ) from exc
if OFFICIAL_BUILD and importlib.util.find_spec("yt_dlp_ejs") is None:
    raise SystemExit("Official LecturePack build requires importable yt-dlp-ejs")


a = Analysis(
    [str(SPIKE_ROOT / "python-sidecar.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=runtime_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=OUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=OUT_NAME,
)
