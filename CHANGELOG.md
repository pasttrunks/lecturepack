# Changelog

All notable changes to Lecture Pack are documented here.

## [1.0.0-unified] — 2026-07-15

Unified v1.0. Executed and verified on the native Windows machine
(Python 3.12.3, PySide6 6.11.1, opencv-python-headless 5.0.0). **53 tests pass.**

### Added
- **Product modes** — an *Output* selector (Study Pack / Transcript Only /
  Slides Only). Stage-gating in `JobController` (`STAGES_SKIPPED_BY_MODE`);
  mode-aware export selection in `ExportService`. Covered by
  `tests/test_product_modes.py` (real controller pipeline, mock ffmpeg/whisper).
- **Layered transcript wiring** — after transcription the controller writes
  `transcript/normalized.json` + `transcript/context_candidates.json` from the
  (previously unwired) `transcript_service`, and exports a paragraph-grouped
  `transcript.normalized.txt`. The raw layer is proven immutable by content hash.
- **Slide-detector precision guards** (`cv_engine.py`, preset-gated): bottom
  caption/overlay-band rejection and major-change future-persistence (fade/
  dissolve rejection). Calibrated on measured SSIM (real slides ≥ 0.975, mid-fade
  frame 0.778). New regression tests `tests/test_detection_targets.py`.

### Changed
- **Detector accuracy on the ground-truth fixture** (no masks): default
  **balanced** preset went from P=0.67 R=0.75 F1=0.71 → **P=1.00 R=1.00 F1=1.00**;
  detailed → P=0.89 R=1.00 F1=0.94. Both meet the acceptance targets.
- **Version consolidated to 1.0.0** across `__init__.py`, `constants.APP_VERSION`,
  `build_release.py`, and new-job manifests (previously 0.2.1 / 0.4.0 / 0.1.0).

### Fixed
- Guarded two fire-and-forget `QTimer.singleShot` handlers that cleared the
  transcript status label; a stale timer could fire after the widget was
  destroyed (`RuntimeError: Internal C++ object already deleted`).

### Verified on Windows
- Real whisper.cpp transcription (bundled `whisper-cli.exe` + `ggml-base.en`):
  42 s WAV → full token-level JSON, parsed through all three transcript layers
  with the raw content hash unchanged.
- PyInstaller onedir build + portable ZIP with SHA256SUMS and BUILD_MANIFEST.

---

## [0.4.x foundation] — branch `claude-v1-unified` (pre-1.0 increment)

Foundational, fully unit-tested services (standard-library only) laid down
before the Windows run.

### Added
- **Layered transcript service** (`lecturepack/services/transcript_service.py`):
  - Layer 1 immutable raw parse of whisper.cpp JSON (full and reduced shapes),
    with per-token confidence and a hash guard proving raw is never modified.
  - Layer 2 deterministic, non-generative normalization (whitespace/punctuation
    cleanup, hallucination-loop collapse, exact-duplicate merge, paragraph
    grouping) that never alters words, names, numbers, or facts.
  - Layer 3 optional, auditable **Context Repair** with an OpenAI-compatible
    local provider (LM Studio / Ollama), strict JSON-schema validation,
    invented-name guardrails, and fully reversible per-correction review.
  - Deterministic Context & Names proposals and sanitized whisper-prompt builder.
- **Detector ground-truth evaluation** (`lecturepack/services/detection_eval.py`)
  with construction-derived labels for the synthetic fixture
  (`tests/fixtures/ground_truth/synthetic_lecture.json`) and a runnable harness
  (`tests/scratch/run_detection_eval.py`).
- **Tests**: `tests/test_transcript_layers.py` (19) and
  `tests/test_detection_eval.py` (7) — all passing (standard-library only).
- Documentation: `docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md`,
  `docs/SLIDE_DETECTION_EVALUATION.md`, `docs/WINDOWS_RUN_HANDOFF.md`.

### Notes
- No existing source, tests, tags, or user data were modified or deleted.
- Safety checkpoint: tag `safety/start-v1-unified`; working branch
  `claude-v1-unified`; `v0.4.1-balanced-detection` left untouched at `aa19732`.
