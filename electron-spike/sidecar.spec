from pathlib import Path
import importlib.util
import os

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_submodules


SPIKE_ROOT = Path(SPECPATH).resolve()
REPO_ROOT = SPIKE_ROOT.parent
RUNTIME_ROOT = Path(os.environ.get("LECTUREPACK_RUNTIME_ROOT", str(REPO_ROOT))).expanduser().resolve()
OUT_NAME = "LecturePackSidecar"
OFFICIAL_BUILD = os.environ.get("LECTUREPACK_OFFICIAL_BUILD") == "1"


def required(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"Required sidecar runtime file is missing: {path}")
    return path


ffmpeg = required(RUNTIME_ROOT / "bin" / "ffmpeg.exe")
ffprobe = required(RUNTIME_ROOT / "bin" / "ffprobe.exe")
whisper = required(RUNTIME_ROOT / "bin" / "Release" / "whisper-cli.exe")
model = required(RUNTIME_ROOT / "models" / "ggml-base.en.bin")
smoke_wav = required(REPO_ROOT / "app" / "packaging" / "assets" / "runtime-smoke.wav")
release_dir = RUNTIME_ROOT / "bin" / "Release"


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


hiddenimports = [
    "send2trash",
    "lecturepack.services.transcript_store",
    "lecturepack.services.transcript_service",
    "lecturepack.services.transcript_formats",
    "lecturepack.services.study_service",
    "lecturepack.services.study_v2",
    "lecturepack.services.packaged_health",
    "lecturepack.infrastructure.whisper_detector",
    "lecturepack.infrastructure.whisper_path_staging",
]

# The Rust Study Core native extension (lecturepack_study_core.pyd) is a
# build-time dependency. It is built with maturin and installed into the
# project venv; PyInstaller collects it as a binary so the packaged sidecar
# can import it without customer Rust.
_study_core_pyd = Path(os.environ.get(
    "LECTUREPACK_STUDY_CORE_PYD",
    str(REPO_ROOT / ".venv" / "Lib" / "site-packages" / "lecturepack_study_core" /
        "lecturepack_study_core.cp312-win_amd64.pyd"),
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
