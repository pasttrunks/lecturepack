# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LecturePack (Windows, onedir, windowed).

Build:  pyinstaller packaging/lecturepack.spec --noconfirm
Output: dist/LecturePack/LecturePack.exe  (+ bundled Qt/WebEngine + ui/)

onedir (not onefile) is deliberate: QtWebEngine ships a large helper process
and resource pack that onefile has to unpack to a temp dir on every launch,
which is slow. onedir keeps startup fast and pairs cleanly with the installer.
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

SPEC_DIR = os.path.abspath(os.path.dirname(SPECPATH))
REPO_ROOT = os.path.dirname(SPEC_DIR)  # the engine package `lecturepack` lives here
UI_DIR = os.path.join(SPEC_DIR, "ui")
ICON = os.path.join(SPEC_DIR, "packaging", "lecturepack.ico")

# The desktop shell (app/) imports the engine package (lecturepack/) from the
# repo root. Pull in every engine submodule so dynamically-imported stages
# (transcription engines, backends, cv_engine) are frozen too.
engine_hiddenimports = collect_submodules("lecturepack")
engine_datas = collect_data_files("lecturepack")

# IANA time-zone data for zoneinfo — Windows has no system zone db, so tz-aware
# scheduling (beta.3) needs the tzdata package's data files bundled.
tzdata_datas = collect_data_files("tzdata")

# yt-dlp powers "Import from a link". Its extractors are imported dynamically by
# name, so collect_submodules is required — without it only the core is frozen
# and every real URL fails at runtime. Optional: if yt-dlp isn't installed the
# build still succeeds and the app hides the paste-a-link button.
try:
    ytdlp_hiddenimports = collect_submodules("yt_dlp")
except Exception:
    ytdlp_hiddenimports = []

# Bundle the entire web UI (html/css/js/fonts) next to the exe under ui/.
ui_datas = []
for root, _dirs, files in os.walk(UI_DIR):
    for name in files:
        src = os.path.join(root, name)
        rel = os.path.relpath(root, SPEC_DIR)  # e.g. "ui" or "ui/fonts"
        ui_datas.append((src, rel))

# Phase 3's guided demo is a local, rights-clear media file.  It belongs in the
# frozen application next to the web UI, never in a user data directory.
DEMO_ASSET = os.path.join(SPEC_DIR, "assets", "demo", "demo_lecture.mp4")
if not os.path.isfile(DEMO_ASSET) or os.path.getsize(DEMO_ASSET) == 0:
    raise RuntimeError("missing required bundled guided-demo asset")
DEMO_THUMBNAIL = os.path.join(SPEC_DIR, "assets", "demo", "polar_bears_thumbnail.jpg")
if not os.path.isfile(DEMO_THUMBNAIL) or os.path.getsize(DEMO_THUMBNAIL) == 0:
    raise RuntimeError("missing required bundled guided-demo thumbnail")
demo_datas = [
    (DEMO_ASSET, os.path.join("assets", "demo")),
    (DEMO_THUMBNAIL, os.path.join("assets", "demo")),
]

# The guided demo runs the real local pipeline, so its pinned fast base.en
# model must be present in the PyInstaller payload as well as the post-build
# runtime bundle.  This is deliberately an approved local input, not a source
# artifact to commit.
DEMO_WHISPER_MODEL = os.path.join(REPO_ROOT, "models", "ggml-base.en.bin")
if not os.path.isfile(DEMO_WHISPER_MODEL) or os.path.getsize(DEMO_WHISPER_MODEL) == 0:
    raise RuntimeError("missing required bundled guided-demo Whisper model")
demo_model_datas = [(DEMO_WHISPER_MODEL, "models")]

a = Analysis(
    # Enter through the package wrapper, not desktop/main.py directly: a
    # PyInstaller entry script runs as __main__ with no package, so main.py's
    # relative imports (from . import ...) would crash at startup.
    [os.path.join(SPEC_DIR, "lecturepack_desktop.py")],
    pathex=[SPEC_DIR, REPO_ROOT],
    binaries=[],
    datas=ui_datas + demo_datas + demo_model_datas + engine_datas + tzdata_datas,
    hiddenimports=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "tzdata",
    ] + engine_hiddenimports + ytdlp_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtQuick3D", "PySide6.Qt3DCore"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LecturePack",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    icon=ICON,
    version=os.path.join(SPEC_DIR, "packaging", "win_version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LecturePack",
)
