# RESEARCH.md — Phase 01: Packaging & Release

## Version Strings

**3 canonical locations** all report stale `"1.1.0"`:

| File | Line | Variable |
|------|------|----------|
| `lecturepack/__init__.py` | 2 | `__version__ = "1.1.0"` |
| `lecturepack/constants.py` | 4 | `APP_VERSION = "1.1.0"` |
| `build_release.py` | 28 | `VERSION = "1.1.0"` |

**Non-canonical:** `job_controller.py:48` `DETECTOR_VERSION = "v1.1.0-piped-1"` (cache fingerprint — should NOT be bumped for a version-only release); `ollama_client.py:258` `REPAIR_PROMPT_VERSION = "v1.1.0-a"` (likewise a cache key). `LecturePack.spec:2` header says `v0.2.0` (also stale).

**No single-source-of-truth.** Three separate files must be updated in sync. Approach: make `constants.APP_VERSION` import from `__init__.__version__`, then bump only `__init__.py`.

## PyInstaller Spec Audit

**Current hiddenimports in `LecturePack.spec:21-53`** — 18 lecturepack modules plus 9 third-party packages. **Approximately 19 modules are MISSING** from the spec:

| Missing Category | Modules |
|-----------------|---------|
| `ui/pages/` | `home_page`, `process_page`, `review_page`, `transcript_page`, `exports_page`, `settings_page`, `study_page` |
| `ui/widgets/` | `slide_grid`, `context_repair_panel` |
| `services/` | `transcript_store`, `groq_transcription`, `ai_repair_service`, `study_service`, `transcription_backends` |
| `infrastructure/` | `video_reader`, `transcription_engines`, `ollama_client`, `process_tree`, `secret_store` |

`optimize=1` is set on the EXE (line 62), which strips `assert` statements — silently neutering the selftest's sanity checks.

**Fix:** Add all missing modules to `hiddenimports`, change `optimize=0` (keep assert statements).

## build_release.py

5-step build:
1. Run PyInstaller (`--noconfirm --clean`) against `LecturePack.spec`
2. Copy external binaries: `ffmpeg.exe`/`ffprobe.exe` → `bin/`, `whisper-cli.exe` + CPU DLLs next to exe, optional Vulkan into `bin/vulkan/`
3. Copy docs: `README-FIRST.txt`, `THIRD_PARTY_NOTICES.txt`, `RELEASE_NOTES.md`
4. Create portable ZIP in `dist-release/`, skip `__pycache__`
5. Generate `SHA256SUMS.txt` and `BUILD_MANIFEST.json`

**Key:** The binary copy step presumes the v1.1 directory layout. No changes needed to the script structure — just version bump and spec audit.

## Test Count

**149 test functions** across 20 files. The 151→149 discrepancy likely comes from two tests removed or renamed during v1.2 development. Need to identify them during reconciliation.

Test distribution: `test_transcript_layers.py` (19), `test_ollama_and_repair.py` (16), `test_ui_v11.py` (14), `test_study_workflow.py` (13), `test_groq_transcription.py` (12), `test_stability_phase.py` (10), `test_study_workspace_v12.py` (9), `test_scheduler_and_engines.py` (9), `test_transcription_backend_contract.py` (9), `test_transcript_formats.py` (8), plus 10 smaller files.

## Self-Test Mechanism

`lecturepack/app.py:121-156` — triggered by `--selftest` CLI arg:
1. Sets `QT_QPA_PLATFORM=offscreen`
2. Imports cv2, numpy, PySide6, __version__, transcript_service, detection_eval
3. Creates QApplication with temp dir (never touches real data)
4. Constructs MainWindow, processes events
5. Exercises parse_raw_whisper_json + normalize_transcript on minimal fixture
6. Exits 0 on success, 1 on failure

**No existing test exercises `--selftest` in pytest.** Could be added as a smoke test.

## Pipeline Stages

7-stage as-built pipeline (from `constants.py:39-55`):
1. Inspect (ffprobe QProcess)
2. Extract Audio (FFmpeg QProcess)
3. Transcribe (whisper-cli QProcess, now also Groq backend)
4. Detect Slides (CV engine, merges old Extract Frames + Detect + Deduplicate)
5. Align (transcript-to-slide)
6. Review Ready (normalizes, context repair)
7. Export (user-triggered)

Product modes: `study_pack` (all 7), `transcript_only` (skips Detect), `slides_only` (skips Extract Audio + Transcribe).
