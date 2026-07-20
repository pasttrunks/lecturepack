# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LecturePack (Windows, onedir, windowed).

Build:  pyinstaller packaging/lecturepack.spec --noconfirm
Output: dist/LecturePack/LecturePack.exe  (+ bundled Qt/WebEngine + ui/)

onedir (not onefile) is deliberate: QtWebEngine ships a large helper process
and resource pack that onefile has to unpack to a temp dir on every launch,
which is slow. onedir keeps startup fast and pairs cleanly with the installer.
"""

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

SPEC_DIR = os.path.abspath(os.path.dirname(SPECPATH))
UI_DIR = os.path.join(SPEC_DIR, "ui")
ICON = os.path.join(SPEC_DIR, "packaging", "lecturepack.ico")

# Bundle the entire web UI (html/css/js/fonts) next to the exe under ui/.
ui_datas = []
for root, _dirs, files in os.walk(UI_DIR):
    for name in files:
        src = os.path.join(root, name)
        rel = os.path.relpath(root, SPEC_DIR)  # e.g. "ui" or "ui/fonts"
        ui_datas.append((src, rel))

a = Analysis(
    [os.path.join(SPEC_DIR, "desktop", "main.py")],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=ui_datas,
    hiddenimports=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
    ],
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
