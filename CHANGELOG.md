# Changelog

All notable changes to Lecture Pack are documented here.

## [1.0.1-real-media-verified] — 2026-07-15

Treats v1.0.0 as an internal beta and adds the missing user-facing Context Repair
workflow, transcript usability, and — most importantly — **real-media verification
through the packaged application** (not just synthetic fixtures).

### Added
- **Context Repair workspace** (`ui/context_repair_dialog.py`): reviews proposed
  corrections with the raw (Layer 1), normalized (Layer 2) and proposed text
  side by side, changed words highlighted (proper names highlighted separately),
  reason + confidence, Accept / Reject / Edit, Accept-all-high-confidence,
  Reject-all, and filters (low confidence / proper names / numbers-dates /
  unresolved / accepted / rejected). Raw Whisper output is never overwritten;
  every action is reversible. Includes a **Context & Names** editor whose terms
  feed both the Whisper prompt and the proposals.
- **Deterministic offline Context Repair provider**
  (`DeterministicNameProvider`): proposes approved-name corrections by fuzzy
  match when no local LLM is configured. It can only ever propose names you
  approved — it cannot invent one.
- **Transcript usability**: a "Copy as" selector (`txt/md/json/jsonl/csv/srt/vtt`),
  Copy Slide / Copy Topic / Copy Selected / Copy Full, semantic sections with
  topic headings, and section/multi-format exports. `transcript_formats.py` is the
  single serializer/section source shared by the UI, exports, and acceptance driver.
- **New exports**: `transcript.md`, `.jsonl`, `.csv`, `.vtt`, `transcript.sections.md`.
- **Packaged acceptance driver** (`lecturepack/acceptance.py`, `--run-acceptance`):
  drives the whole pipeline headlessly from the frozen EXE with bundled binaries;
  supports `--mode` for product-mode verification.

### Verified on real media (native Windows, packaged EXE)
- **Packaged short-video pipeline** (`m2-res_1080p.mp4`): `LecturePack.exe
  --run-acceptance` exit 0 — bundled ffmpeg/whisper, all 11 export formats
  parse, ordered timestamps, Context Repair accept/reject reversible with raw
  hash preserved, restore after reopen, and re-export proven **not** to rerun
  audio/whisper/detection.
- **Context-aware transcription** (Egypt lecture excerpt, base.en): the Whisper
  `--prompt` did **not** fix "Mark Lainer"→*Mark Lehner* or "dolarite"→*dolerite*
  even with the correct terms in the prompt; post-hoc **Context Repair** proposed
  exactly those fixes (from approved names) for user review. Honest finding —
  prompting is a weak bias; review-based repair is more effective and preserves
  user control. (small.en not run — not present locally and not authorized to
  download.)
- **Detector on real lecture material**: calm section (5:00–7:00) scored
  **P=1.00 R=1.00 F1=1.00** (4/4 slide states, 0 false positives) against
  human-labeled ground truth from dense contact sheets; an embedded 6-min video
  section produced 13 distinct scene keyframes with **no** fade/caption/pointer
  clusters. See `docs/evidence/v1.0.1/`.

### Changed
- Version consolidated to **1.0.1**.

### Fixed / Safety
- `robocopy`-based timestamped backup of all existing jobs before any test; no
  job or candidate is ever deleted (regression-tested).

---

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
