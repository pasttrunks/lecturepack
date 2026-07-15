# -*- mode: python ; coding: utf-8 -*-
# LecturePack v0.2.0 - PyInstaller onedir spec
# Build: pyinstaller LecturePack.spec

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

spec_root = os.path.abspath(SPECPATH)

# Collect PySide6 data files (platform plugins, etc.)
pyside6_datas = collect_data_files('PySide6', includes=['**/*.dll', '**/*.qm', '**/*.pyd'])

a = Analysis(
    [os.path.join(spec_root, 'lecturepack', 'app.py')],
    pathex=[spec_root],
    binaries=[],
    datas=[
        (os.path.join(spec_root, 'lecturepack', 'constants.py'), 'lecturepack'),
    ] + pyside6_datas,
    hiddenimports=[
        'lecturepack',
        'lecturepack.app',
        'lecturepack.constants',
        'lecturepack.models.job',
        'lecturepack.controllers.job_controller',
        'lecturepack.infrastructure.config_manager',
        'lecturepack.infrastructure.file_manager',
        'lecturepack.infrastructure.ffmpeg_wrapper',
        'lecturepack.infrastructure.whisper_wrapper',
        'lecturepack.infrastructure.cv_engine',
        'lecturepack.services.export_service',
        'lecturepack.ui.main_window',
        'lecturepack.ui.widgets.crop_selector',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'cv2',
        'numpy',
        'PIL',
        'imagehash',
        'img2pdf',
        'reportlab',
        'jinja2',
        'skimage',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'test', 'pydoc', 'pdb',
        'IPython', 'jupyter', 'notebook',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LecturePack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LecturePack',
)
