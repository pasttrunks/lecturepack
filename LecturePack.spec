# -*- mode: python ; coding: utf-8 -*-
# LecturePack v1.2.0 - PyInstaller onedir spec
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
        # Phase 2 theme files (loaded via __file__-relative path in ui/theme.py)
        (os.path.join(spec_root, 'lecturepack', 'ui', 'themes', '*.qss'),
         os.path.join('lecturepack', 'ui', 'themes')),
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
        'lecturepack.infrastructure.video_reader',
        'lecturepack.infrastructure.transcription_engines',
        'lecturepack.infrastructure.ollama_client',
        'lecturepack.infrastructure.process_tree',
        'lecturepack.infrastructure.secret_store',
        'lecturepack.infrastructure.whisper_detector',
        'lecturepack.services.export_service',
        'lecturepack.services.transcript_service',
        'lecturepack.services.transcript_formats',
        'lecturepack.services.detection_eval',
        'lecturepack.services.transcript_store',
        'lecturepack.services.groq_transcription',
        'lecturepack.services.ai_repair_service',
        'lecturepack.services.study_service',
        'lecturepack.services.transcription_backends',
        'lecturepack.acceptance',
        'lecturepack.ui.main_window',
        'lecturepack.ui.context_repair_dialog',
        'lecturepack.ui.pages.home_page',
        'lecturepack.ui.pages.process_page',
        'lecturepack.ui.pages.review_page',
        'lecturepack.ui.pages.transcript_page',
        'lecturepack.ui.pages.exports_page',
        'lecturepack.ui.pages.settings_page',
        'lecturepack.ui.pages.study_page',
        'lecturepack.ui.widgets.crop_selector',
        'lecturepack.ui.widgets.slide_grid',
        'lecturepack.ui.widgets.context_repair_panel',
        'lecturepack.ui.widgets.transcript_block',
        'lecturepack.ui.widgets.title_bar',
        'lecturepack.ui.widgets.animated_stacked',
        'lecturepack.ui.widgets.focus_mode',
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
        'tkinter', 'test', 'pdb',
        'IPython', 'jupyter', 'notebook',
    ],
    noarchive=False,
    optimize=0,
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
