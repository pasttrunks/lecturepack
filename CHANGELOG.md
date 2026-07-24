# Changelog

All notable changes to Lecture Pack are documented here.

## [0.9.0-beta.3] — unreleased

Reliability, queueing, scheduling, notifications, and polish. Beta.3 retains the
bundled zero-setup local engine from beta.2.

### New
- **Persistent processing queue** — one active job at a time; additional jobs
  queue FIFO with reorder, Run Now, and remove. Survives restart.
- **Local scheduling** — schedule a lecture for a local date/time with a
  missed-schedule policy (run when the app next opens / skip / ask). No Windows
  service and no cloud scheduling; a schedule due while the app is closed is
  handled at the next launch.
- **Safe checkpoint-based pause & resume** — cooperative pause finishes the
  current step (or cleanly stops a restartable stage), preserves completed work,
  and resumes from the last valid checkpoint; survives an app restart. No unsafe
  process suspension.
- **Windows notifications** for processing complete, processing failed, and
  update available (focus-aware, de-duplicated, with click-through). Only while
  the app is open or minimized — nothing is sent when it is fully closed.
- **Windows taskbar progress**, and **keep-awake while processing** (display may
  still sleep; manual sleep/shutdown is never blocked).
- **Better completion panel** (real duration / word / segment / slide metrics)
  with Open Transcript, Review Slides, Start Studying, and folder shortcuts.
- **Stage-specific retry** that preserves completed upstream work.
- **Redacted diagnostics** (never include keys, credentials, or transcript text).
- Smoother animations that respect the OS **reduce-motion** setting.

### Reliability
- Fresh installs start with no stale jobs (packaging clean-state gate).
- Old-session `running` jobs are reconciled to **Interrupted** at startup and
  leave the active Home/Processing views, with Resume / Restart / View / Remove.
- Per-launch session ownership so reconciliation never clobbers a live job.
- Orphaned-running-job reset; frozen-EXE icon fix; Study Packs badge fix (from
  the post-beta.2 fixes).

## [0.9.0-beta.2] — 2026-07-23

Packaged-engine hotfix for beta.1's clean-machine failure.

### Fixed
- Bundled the complete CPU whisper runtime in the installer (ffmpeg, ffprobe,
  whisper-cli, whisper/ggml DLLs, and the `ggml-base.en.bin` model) and fixed
  frozen-mode binary path detection, so transcription works out of the box with
  no Python, GPU, or external tools.

## [0.9.0-beta.1] — 2026-07-21

First **public beta**. The core lecture workflow works immediately after
installation — no account, no API key, no Ollama, no separate model download.

### Core (works out of the box)
- Local transcription, slide extraction + review with a readable full-size
  preview, transcript viewer/editor, exports, notes, bookmarks, grouped
  lectures, and safe delete-to-Recycle-Bin.
- **Built-in Study** always works with no local AI: deterministic grounded
  quizzes and flashcards, plus a transcript-grounded, source-linked "Ask"
  that cites timestamps. Study controls are never dead when Ollama is absent.

### Smart Study (optional, private, local)
- One-action setup detects Ollama, offers two named presets —
  **Lightweight Study** and **Balanced Study** (recommended) — with a simple
  RAM-based recommendation, downloads the model with progress + cancel, runs a
  structured test request, and persists the choice. Raw model IDs and the
  endpoint live under **Advanced AI details**. If Ollama is missing, the app
  opens the official Ollama download page (it never downloads or runs a binary
  itself).
- Clear provider labels everywhere: **Built-in Study / Local AI / Online
  Enhanced**.

### Online transcription (optional)
- Groq **Online Fast** / **Online Accurate** modes with the key stored only in
  Windows Credential Manager. Online modes stay disabled until a key is set.

### Release
- Versioned `0.9.0-beta.1`; pre-release tags publish as GitHub pre-releases
  with installer + portable ZIP + SHA256SUMS. Installer preserves
  `LecturePackData` across upgrades and never deletes user lectures.

## [1.1.0-ui-speed-ollama] — 2026-07-16

Speed, a redesigned interface, a first-class transcript workspace, and safe
local-AI assistance. No existing job data is migrated destructively; v1.0 jobs
open unchanged.

### Performance
- **Two-pass slide detection decode**: one sequential FFmpeg analysis stream
  (cropped, downscaled, grayscale) replaces thousands of full-resolution
  random seeks; full-resolution frames are decoded only for final accepted
  candidates. Same decision algorithm, verified on synthetic and real-media
  ground truth (P=R=1.0 on the calm Egypt section, identical to v1.0.1).
- **Concurrent pipeline**: transcription and slide detection run in parallel
  after audio extraction (resource-aware; can be disabled in Settings).
- **whisper.cpp Vulkan engine** (optional, `bin/vulkan/`): whisper.cpp v1.9.1
  built with the ggml Vulkan backend for AMD/cross-vendor GPUs. On the
  reference AMD RX Vega 56 it transcribes the 6-minute excerpt in 33.3 s vs
  48.7 s CPU. Auto-selected only after the machine benchmark confirms it is
  faster; the verified CPU binary remains the default and fallback.
- **Stage cache keys**: completed stages re-run automatically when the
  source file, crop/ignore regions, detector version, engine/model, glossary
  or VAD settings changed — and are reported as "Cached" otherwise.
- **Deferred min-time acceptance** in the detector: a slide change that
  passes every content check but lands inside the min-time gate is accepted
  when the gate opens instead of being re-detected seconds late.
- Candidate thumbnails are cached as WebP (~10× smaller than the PNGs) and
  decoded off the GUI thread.

### Interface (new shell)
- Navigation rail (Home · Process · Review · Transcript · Exports · Settings),
  top command bar (job switcher, product mode, Save, Export, status) and a
  status bar showing stage, elapsed time, progress and the ACTUAL loaded
  engine/backend/model. Light and dark themes; window geometry, splitter
  positions, list/grid mode and last page persist between sessions.
- **Review**: slide timeline (compact list or thumbnail grid) + large preview
  + transcript for the selection. Selected slides are unmistakable: ≥3 px
  accent outline, contrasting background, checkmark badge, keyboard focus
  ring, auto scroll-into-view, and a live selection count. Ctrl-click
  toggles, Shift-click selects ranges, Ctrl+A selects all, Delete rejects
  (never deletes files), R restores, Ctrl+Z undoes. Context menu: Keep,
  Reject, Restore, Export selected, Copy image, Open source timestamp.
- **Transcript workspace** (independent of slide review):
  - *Full Transcript*: readable document with section headings, optional
    timestamps, search highlighting, timestamp links that select the
    matching slide, one-click full copy.
  - *Segments*: grid (#, start, end, duration, confidence, status, text)
    with a separate editor for the active segment, split at cursor, merge,
    reset, save, undo/redo. Sorting/filtering never changes chronological
    export order. Structural edits live in a new working layer
    (`working.json`); raw whisper output remains immutable and the legacy
    `edited.json` is still mirrored for old tools.
  - *Sections*: conservative topic sections; headings are renameable and AI
    suggestions are explicitly marked "(AI)" and editable.
  - *Context Repair* tab (also reachable from Review).
- **Stage-by-stage progress** with per-stage elapsed time and ETA, cached/
  skipped markers, collapsible log drawer, and a Cancel that actually kills
  worker processes.

### Local AI (Ollama) — optional, never required
- Fault-isolated Ollama client: finite connect/generation timeouts, streamed
  cancellation, strict JSON-schema constrained requests (temperature 0,
  thinking disabled), typed errors, and a disk response cache keyed by
  transcript hash + context + model + prompt version.
- Context Repair proposals via a worker thread — **never on the GUI thread**
  (fixes the v1.0.1 crash) — with progress, cancel, and an inline recoverable
  error bar (Retry / Use deterministic repair only / Open Ollama settings /
  Copy diagnostics). An Ollama crash, timeout, unload or bad response can no
  longer take the app down; exports never wait for AI.
- Settings → AI (Ollama): availability/version check, model list from
  `/api/tags` with parameter size/quantization/disk size, Test Model,
  keep-alive control, per-job enable. Recommended default on this machine:
  `qwen3:1.7b` (benchmarked; see evidence).
- AI may propose spelling/proper-name fixes, section headings and summaries;
  it can never modify the raw transcript, silently apply anything, or block
  exports.

### Reliability
- Cancel now escalates `terminate()` to `kill()` (Windows console processes
  ignore WM_CLOSE — in v1.0 a cancelled whisper-cli kept running) and a
  cancellation latch prevents late process exits from restarting the
  pipeline; replaced detector workers are reaped safely (fixes a native
  crash under cancel).

### Tests
- 106 automated tests (36 new): selection visuals (including a pixel-level
  accent-outline check), Ctrl/Shift-click, transcript views/copy formats/
  search sync/split/merge/undo, Ollama fault isolation against a scripted
  fake server (10 failure modes), scheduler concurrency and cancellation,
  stage cache keys, engine registry fallback policy, old-job compatibility.

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
