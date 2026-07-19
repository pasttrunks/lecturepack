# Technology Stack

**Analysis Date:** 2026-07-17

## Languages

**Primary:**
- Python 3.12.3 (CPython, MSC v.1938 64-bit AMD64) — entire application. Version proven by `dist-release/BUILD_MANIFEST.json` (`"python": "3.12.3 ... [MSC v.1938 64 bit (AMD64)]"`) and the dev venv `.venv/Scripts/python.exe --version`.

**Secondary:**
- None in repo source. Shipped product embeds native C/C++ binaries (FFmpeg, whisper.cpp/ggml) that are invoked as subprocesses, not linked.

## Runtime

**Environment:**
- CPython 3.12.3 on Windows x64 (`win32`). The code is Windows-only in practice: `ctypes` + `Advapi32.dll` in `lecturepack/infrastructure/secret_store.py`, `subprocess.CREATE_NO_WINDOW` in `lecturepack/infrastructure/ffmpeg_wrapper.py`, and a `System32\vulkan-1.dll` probe in `lecturepack/infrastructure/transcription_engines.py`.
- Dev interpreter: `.venv/` (gitignored) at repo root.

**Package Manager:**
- pip 24.0 (inside `.venv`).
- Dependency manifests: `requirements.txt` (8 runtime pins, all `>=` floors) and `requirements-dev.txt` (2 test pins).
- Lockfile: missing — no `pyproject.toml`, `setup.py`, `Pipfile`, or constraints file. The installed venv is the de-facto lock (see exact versions below).

## Frameworks

**Core:**
- PySide6 6.11.1 (`PySide6`, `PySide6_Addons`, `PySide6_Essentials`, `shiboken6` all 6.11.1) — Qt Widgets desktop GUI. Entry point `lecturepack/app.py` → `QApplication` + `MainWindow`; spec collects `PySide6.QtWidgets/QtCore/QtGui/QtSvg/QtSvgWidgets` in `LecturePack.spec`.
- Concurrency model: `QProcess` for external CLI tools, `QThread` workers for in-process CV/export — decision AD-1 in `docs/DECISIONS.md`.

**Testing:**
- pytest 9.1.1 + pytest-qt 4.5.0 (`requirements-dev.txt`); config `pytest.ini` (`testpaths = tests`).
- pywinauto 0.6.9 + comtypes 1.4.16 + pywin32 312 present in venv (Windows GUI automation, used for packaged-build UI evidence generation, e.g. `tests/generate_ui_evidence.py`).

**Build/Dev:**
- PyInstaller 6.21.0 — onedir windowed build via `LecturePack.spec` (entry `lecturepack/app.py`, `console=False`, UPX on, `optimize=1`).
- `build_release.py` — release orchestrator: PyInstaller → copies `bin/` binaries → docs → portable ZIP `LecturePack-portable-<ver>.zip` → `SHA256SUMS.txt` + `BUILD_MANIFEST.json` into `dist-release/`.

## Key Dependencies

Exact installed versions (`.venv` pip freeze); floors in `requirements.txt`:

**Critical:**
- `opencv-python-headless` 5.0.0.93 (`>=4.8.0`) — slide-detection CV engine `lecturepack/infrastructure/cv_engine.py` and `video_reader.py` (FFmpeg rawvideo pipe; legacy cv2 seek fallback).
- `numpy` 2.5.1 (transitive) — frame math throughout CV engine.
- `scikit-image` 0.26.0 (`>=0.22.0`) — SSIM metric in slide-detection scoring (`0.4·ssim_dist + 0.3·dhash + 0.3·pixel_diff`).
- `ImageHash` 4.3.2 (`>=4.3.0`) — dHash screening + pHash dedup in slide pipeline.
- `Pillow` 12.3.0 (`>=10.0.0`) — image I/O, thumbnails (WebP loader in `lecturepack/ui/widgets/slide_grid.py`).
- `reportlab` 5.0.0 (`>=4.0.0`) — study-pack PDF generation (`lecturepack/services/export_service.py`; AD-6).
- `img2pdf` 0.6.3 (`>=0.5.0`) + `pikepdf` 10.10.0 — slides-only PDF (AD-6).
- `Jinja2` 3.1.6 (`>=3.1.0`) + `MarkupSafe` 3.0.3 — self-contained HTML study pack with base64 images (AD-7).

**Infrastructure:**
- `pyinstaller` 6.21.0 + `pyinstaller-hooks-contrib` 2026.6 + `pefile`/`altgraph`/`pywin32-ctypes` — packaging only.
- `scipy` 1.18.0, `imageio` 2.37.3, `tifffile`, `PyWavelets`, `lazy-loader`, `networkx` — transitive of scikit-image.
- No HTTP client library: all network I/O uses stdlib `urllib.request` (`lecturepack/services/groq_transcription.py`, `lecturepack/infrastructure/ollama_client.py`) — deliberate (AD-13 rejected the Groq SDK).

## Bundled Native Binaries (not pip)

Gitignored (`bin/`, `models/` in `.gitignore`) but required at runtime; resolved app-relative via `sys._MEIPASS`/exe dir, never PATH-first (AD-4):

| Binary | Version | Location | Source / License |
|---|---|---|---|
| `ffmpeg.exe` | 7.0.1 per `THIRD_PARTY_NOTICES.txt` (gyan.dev "essentials", `--enable-gpl`); note `docs/ARCHITECTURE.md` §8 states 8.1.x — docs disagree, notices file is the shipped-artifact record | `bin/ffmpeg.exe` (82.5 MB) | gyan.dev, GPL/LGPL |
| `ffprobe.exe` | same build | `bin/ffprobe.exe` (82.3 MB) | same |
| `whisper-cli.exe` (CPU) | whisper.cpp v1.9.1 | `bin/Release/whisper-cli.exe` + `whisper.dll`, `ggml.dll`, `ggml-base.dll`, 9× `ggml-cpu-*.dll` variant backends | ggml-org/whisper.cpp, MIT |
| `whisper-cli.exe` (Vulkan) | whisper.cpp v1.9.1, `GGML_VULKAN + GGML_BACKEND_DL`, Vulkan SDK 1.4.350.0 | `bin/vulkan/whisper-cli.exe` + `libwhisper.dll`, `ggml-vulkan.dll` (71.7 MB), MinGW runtime DLLs | same, optional GPU engine |
| Whisper models | `ggml-base.en.bin` (141 MB), `ggml-small.en-q8_0.bin` (252 MB), `ggml-small.en.bin` (465 MB) | `models/` (dev); user-supplied in release | HuggingFace `ggerganov/whisper.cpp`, MIT |

Engine selection policy (`auto` → Vulkan if benchmarked faster, else CPU) lives in `lecturepack/infrastructure/transcription_engines.py` (`EngineRegistry`); runtime backend is proven by parsing whisper.cpp stderr in `lecturepack/infrastructure/whisper_wrapper.py` (`_probe_backend`). Release copies binaries per `build_release.py` (`WHISPER_BINS`, `WHISPER_CPU_DLLS`, `VULKAN_BINS`, `FFMPEG_BINS`).

## Configuration

**Environment:**
- No `.env` file present and none used. No environment variables required for normal operation. `QT_QPA_PLATFORM=offscreen` is set by the headless self-test in `lecturepack/app.py` (`run_selftest`).
- App settings: JSON only — `~/LecturePackData/config.json` via `lecturepack/infrastructure/config_manager.py` (`ConfigManager.DEFAULT_SETTINGS`: binary paths, `engine`, `vulkan_benchmark_ok`, `parallel_pipeline`, `groq_concurrency`, `groq_max_upload_bytes`, `online_fallback_local`, `dark_theme`, `ollama`). Per-job state as JSON manifests (`state.json`, `settings.json`, `stage_fingerprints.json`) under `~/LecturePackData/jobs/<uuid>/`. AD-3: plain files, no database.
- UI layout persistence: `QSettings("LecturePack", "LecturePack")` in `lecturepack/ui/main_window.py:128` (Windows registry).
- Secrets: never in config — Windows Credential Manager only (see INTEGRATIONS.md).

**Build:**
- `LecturePack.spec` (PyInstaller spec; hiddenimports enumerate every app module + `cv2/numpy/PIL/imagehash/img2pdf/reportlab/jinja2/skimage`; excludes tkinter/IPython/jupyter).
- `build_release.py`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`.

## Platform Requirements

**Development:**
- Windows 10/11 x64, Python 3.12, `.venv` with both requirements files. Binaries in `bin/` and models in `models/` must be obtained separately (gitignored). FFmpeg/whisper fall back to system PATH only for ffmpeg/ffprobe in dev (`ffmpeg_wrapper.detect_binaries`).
- Run: `.venv\Scripts\python.exe -m lecturepack` or `python lecturepack/app.py`; tests: `.venv\Scripts\python.exe -m pytest`.

**Production:**
- Portable ZIP (`dist-release/LecturePack-portable-1.1.0.zip`, ~385 MB, unsigned — SmartScreen warning expected per `README.md`). No installer, no Python needed on target. A Whisper `.bin` model is **not** bundled — user points the app at one on first run (`docs/WINDOWS_PORTABLE_INSTALL.md`).
- Optional: Vulkan runtime (`vulkan-1.dll`, ships with GPU drivers) for GPU transcription; Ollama for local-AI features.

**Version note:** `lecturepack/constants.py` and `build_release.py` report app version **1.1.0** (branch `v1.1.0-ui-speed-ollama`); the codebase already contains v1.2-scope code (provider-neutral transcription seam, Groq backends, Study workspace) documented in `docs/ARCHITECTURE.md` "v1.2" sections with evidence under `docs/evidence/v1.2.0/`.

---

*Stack analysis: 2026-07-17*
