# Lecture Pack -- Phase 0 Handoff

**Date:** 2026-07-15  
**Phase completed:** Phase 0 (Research and Implementation Planning)  
**Next phase:** Phase 1 (Project Foundation and Diagnostics)  
**Status:** Phase 0 complete. Awaiting authorization to begin Phase 1.

> [!CAUTION]
> **Do not begin Phase 2.** Phase 1 must pass all acceptance tests and receive explicit user approval before Phase 2 is authorized.

---

## 1. What Has Been Decided

### Architecture

- Layered architecture: UI, Controller, Service, Infrastructure.
- QProcess for external tools (FFmpeg, whisper-cli). QThread workers for internal processing (OpenCV, hashing, export).
- Per-stage state machine with atomic JSON writes for crash recovery.
- Plain files + JSON manifests. No database.
- Application-relative paths for bundled binaries. Never rely on system PATH.

### Technology Choices

| Choice | Decision | Rationale |
|---|---|---|
| GUI | PySide6 6.11.x, Qt Widgets | Specified in requirements |
| Transcription | whisper.cpp v1.9.1 (pinned) | MIT license, CPU + Vulkan support |
| CPU fallback | Primary path (always available) | No CUDA on target hardware |
| Vulkan | Optional accelerator (AMD Vega 56 supports Vulkan 1.3) | Requires building whisper.cpp from source with `-DGGML_VULKAN=ON` |
| Slide detection | Three-stage CV cascade (dHash + SSIM + histogram) | Deterministic, testable, no LLM dependency |
| Slides PDF | img2pdf (lossless) | No re-encoding of image data |
| Study-pack PDF | ReportLab (Platypus layout) | Pure Python, no native system deps (unlike WeasyPrint) |
| HTML study pack | Self-contained, base64 images | Offline-compatible, no local server needed |
| Packaging | PyInstaller standalone directory | Mature PySide6 hooks, bootloader exception allows proprietary apps |
| Image hashing | imagehash 4.x (BSD-2-Clause) | pHash, dHash, aHash, wHash in one library |
| SSIM | scikit-image (BSD-3-Clause) | Standard implementation of structural similarity |
| FFmpeg | 8.1.x LGPL essentials from gyan.dev, bundled | Guaranteed version compatibility |
| Default Whisper model | small.en (466 MB) | Best accuracy/speed balance (to be confirmed by Phase 2 benchmark) |
| Data directory | ~/LecturePackData (configurable) | User-accessible, not hidden in AppData |

### Schemas

All JSON schemas (manifest.json, source.json, settings.json, state.json, candidate metadata) are defined in `docs/IMPLEMENTATION_PLAN.md` Section 3.

### Slide Detection Algorithm

Fully specified in `docs/IMPLEMENTATION_PLAN.md` Section 4, including:
- Preprocessing pipeline (crop, mask, downscale, grayscale, blur, temporal median)
- Three-stage cascade with concrete thresholds
- Stability detection algorithm
- Change type classification
- Sequential and global deduplication
- Four preset parameter sets

### Licensing

All dependencies have permissive or LGPL licenses. A `THIRD_PARTY_LICENSES.txt` file must be created during Phase 5 with full attribution. Key requirement: use `opencv-python-headless` to avoid Qt DLL conflicts and unnecessary GPL entanglements.

---

## 2. What Remains Unimplemented

Everything. No code has been written. No packages have been installed. No Git repository exists. The workspace contains only these planning documents.

| Item | Target Phase |
|---|---|
| Git repository and project skeleton | Phase 1 |
| PySide6 application shell | Phase 1 |
| Settings and diagnostics screen | Phase 1 |
| Logging and configuration | Phase 1 |
| Synthetic test-video generator | Phase 1 |
| Video import and ffprobe inspection | Phase 2 |
| Audio extraction | Phase 2 |
| whisper.cpp execution and model management | Phase 2 |
| Progress, cancellation, resume | Phase 2 |
| Whisper model benchmark on target hardware | Phase 2 |
| Vulkan build attempt | Phase 2 |
| Slide detection pipeline | Phase 3 |
| Crop selector and mask painter | Phase 3 |
| Processing presets | Phase 3 |
| Slide review interface | Phase 4 |
| Transcript viewer and editor | Phase 4 |
| Transcript-to-slide alignment | Phase 4 |
| HTML and PDF study packs | Phase 5 |
| PyInstaller packaging | Phase 5 |
| First-run model download dialog | Phase 5 |
| Clean-machine installation test | Phase 5 |
| LM Studio integration | Phase 6 |

---

## 3. Exact Authorized Scope of Phase 1

### Goal

Set up the complete project infrastructure, development environment, and a functional PySide6 application shell with a working Settings & Diagnostics screen. Produce the synthetic test-video generator. Establish the Git repository with documented architecture and operating rules.

### What Phase 1 Does NOT Include

- No video import or processing
- No audio extraction or transcription
- No slide detection
- No export generation
- No LM Studio integration
- No model downloading
- No processing pipeline execution

---

## 4. Files Phase 1 May Create

```
LecturePack/
  .gitignore
  README.md
  LICENSE
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  pytest.ini

  lecturepack/
    __init__.py
    __main__.py
    app.py
    constants.py
    ui/
      __init__.py
      main_window.py
      settings_screen.py
      home_screen.py              (stub)
      setup_screen.py             (stub)
      slide_review_screen.py      (stub)
      transcript_review_screen.py (stub)
      export_screen.py            (stub)
    infrastructure/
      __init__.py
      config_manager.py
      file_manager.py
      log_manager.py
      ffmpeg_wrapper.py           (detection only)
      whisper_wrapper.py          (detection only)
    models/
      __init__.py
      manifest.py
      settings.py
    resources/
      icons/                      (placeholder icon)

  tests/
    __init__.py
    conftest.py
    fixtures/
      generate_test_video.py
    test_config_manager.py
    test_file_manager.py
    test_path_handling.py
    test_diagnostics.py
```

Phase 1 may also update:
- `AGENTS.md` (if refinements are needed based on implementation experience)
- `docs/DECISIONS.md` (to log any new decisions made during Phase 1)

Phase 1 must NOT modify:
- `docs/PRODUCT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/TEST_PLAN.md`
- `docs/RISK_REGISTER.md`
- Any files outside the `LecturePack/` directory

---

## 5. Phase 1 Acceptance Tests

| # | Criterion | Evidence Required |
|---|---|---|
| P1-1 | `pytest tests/ -v` passes with 0 failures | Full pytest output |
| P1-2 | Application launches and shows main window | Screenshot |
| P1-3 | Settings screen displays FFmpeg/whisper-cli detection status | Screenshot |
| P1-4 | Diagnostics report can be generated and copied to clipboard | Screenshot + clipboard content |
| P1-5 | Paths with spaces handled correctly | `test_path_handling.py` passes |
| P1-6 | Sample job directory created with valid manifest.json | `test_file_manager.py` passes |
| P1-7 | Synthetic test video generated successfully | `generate_test_video.py` runs, output is a playable file |
| P1-8 | Git repository has clean initial commit | `git log --oneline` output |
| P1-9 | Git tag `v0.1.0-foundation` exists | `git tag -l` output |
| P1-10 | All docs present (SPEC, ARCHITECTURE, DECISIONS, TEST_PLAN) | File listing |

### Test File Details

| Test File | What It Covers |
|---|---|
| `test_config_manager.py` | Load/save config, default values, missing config file, corrupt JSON |
| `test_file_manager.py` | Create job directory, valid manifest, safe path escaping |
| `test_path_handling.py` | Windows paths with spaces, non-ASCII characters, long paths |
| `test_diagnostics.py` | FFmpeg detection (mocked), whisper-cli detection (mocked), diagnostic report generation |

---

## 6. Known Technical Risks

| Risk | Impact | Phase | Mitigation |
|---|---|---|---|
| Vulkan build unstable on Vega 56 | CPU fallback always available | Phase 2 | Test with probe; silently fall back |
| Slide detection thresholds don't generalize | Users may need to adjust presets | Phase 3 | Configurable thresholds, review screen, full metadata |
| CPU transcription too slow for recommended model | User waits longer than expected | Phase 2 | Benchmark 4 models; user picks speed/accuracy tradeoff |
| PyInstaller packaging breaks with full deps | App doesn't run on clean machines | Phase 5 | Clean-machine test mandatory; Nuitka fallback |
| ReportLab PDF quality insufficient | Study pack looks unprofessional | Phase 5 | Dedicated template; WeasyPrint fallback |

See `docs/RISK_REGISTER.md` for the full register.

---

## 7. Commands and Dependencies Requiring Verification

These items have been researched but cannot be fully verified until implementation begins:

| Item | What to Verify | When |
|---|---|---|
| `pip install PySide6==6.11.1` | Installs cleanly on Python 3.11 | Phase 1 |
| `pip install opencv-python-headless` | No Qt DLL conflicts with PySide6 | Phase 1 |
| `pip install scikit-image` | Compatible with Python 3.11 and OpenCV 5.x | Phase 1 |
| `pip install imagehash` | Works with Pillow 12.x | Phase 1 |
| `pip install img2pdf` | Works with Pillow 12.x | Phase 1 (or Phase 3) |
| `pip install reportlab` | Installs cleanly, no native deps | Phase 1 (or Phase 5) |
| FFmpeg essentials build from gyan.dev | ffmpeg.exe and ffprobe.exe run correctly | Phase 1 |
| whisper-cli.exe from v1.9.1 release | Runs on target hardware, produces valid output | Phase 2 |
| Vulkan build of whisper.cpp | Compiles with VS2022 + Vulkan SDK; runs on Vega 56 | Phase 2 |
| `vulkaninfo` on target machine | Confirms Vulkan 1.3 conformance | Phase 1 (diagnostics) |
| Whisper model download from HuggingFace | Download completes, SHA-1 matches | Phase 2 |
| PyInstaller packaging | Produces working standalone on clean machine | Phase 5 |

---

## 8. Warning

> [!CAUTION]
> **Phase 1 authorization does not include Phase 2 work.** Do not:
> - Import or process actual video files
> - Extract audio or run transcription
> - Download Whisper models
> - Execute the slide detection pipeline
> - Generate study pack exports
> - Connect to LM Studio
>
> Phase 1 ends with a working application shell, diagnostics screen, test infrastructure, and Git repository. Everything else requires separate phase authorization.

---

## 9. Reference Documents

| Document | Path | Contents |
|---|---|---|
| Agent rules | `AGENTS.md` | Mandatory operating constraints |
| Product spec | `docs/PRODUCT_SPEC.md` | What the product does |
| Architecture | `docs/ARCHITECTURE.md` | How the product is structured |
| Implementation plan | `docs/IMPLEMENTATION_PLAN.md` | File tree, schemas, algorithm, phases |
| Test plan | `docs/TEST_PLAN.md` | Fixtures, assertions, per-phase tests |
| Decisions | `docs/DECISIONS.md` | Why specific choices were made |
| Risks | `docs/RISK_REGISTER.md` | Known risks with mitigations |
| Planning artifact | Antigravity conversation artifacts | Full Phase 0 research and analysis |
