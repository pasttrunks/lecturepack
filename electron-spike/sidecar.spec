from pathlib import Path
import os

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ


SPIKE_ROOT = Path(SPECPATH).resolve()
REPO_ROOT = SPIKE_ROOT.parent
RUNTIME_ROOT = Path(os.environ.get("LECTUREPACK_RUNTIME_ROOT", str(REPO_ROOT))).expanduser().resolve()
OUT_NAME = "LecturePackSidecar"


def required(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"Required sidecar runtime file is missing: {path}")
    return path


ffmpeg = required(RUNTIME_ROOT / "bin" / "ffmpeg.exe")
ffprobe = required(RUNTIME_ROOT / "bin" / "ffprobe.exe")
whisper = required(RUNTIME_ROOT / "bin" / "Release" / "whisper-cli.exe")
model = required(RUNTIME_ROOT / "models" / "ggml-base.en.bin")
release_dir = RUNTIME_ROOT / "bin" / "Release"


# The sidecar ships the verified CPU whisper.cpp binary and its DLLs only.
# Vulkan/CUDA directories are intentionally outside this first migration slice.
runtime_datas = [
    (str(ffmpeg), "bin"),
    (str(ffprobe), "bin"),
    (str(whisper), "bin/Release"),
    (str(model), "models"),
]
runtime_datas.extend(
    (str(path), "bin/Release")
    for path in sorted(release_dir.glob("*.dll"))
)


hiddenimports = [
    "lecturepack.services.transcript_store",
    "lecturepack.services.transcript_service",
    "lecturepack.services.transcript_formats",
    "lecturepack.services.study_service",
    "lecturepack.infrastructure.whisper_detector",
    "lecturepack.infrastructure.whisper_path_staging",
]


a = Analysis(
    [str(SPIKE_ROOT / "python-sidecar.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
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
