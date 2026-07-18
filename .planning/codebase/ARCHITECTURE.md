<!-- refreshed: 2026-07-17 -->
# Architecture

**Analysis Date:** 2026-07-17

LecturePack is a Windows desktop application (PySide6 / Python 3, packaged with PyInstaller onedir via `LecturePack.spec`) that turns lecture recordings into slide decks, transcripts, and study packs. The authoritative design doc is `docs/ARCHITECTURE.md`; this file describes the as-built code, which matches that doc plus its v1.0.1/v1.1/v1.2 addenda.

## System Overview

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Layer 4 — UI (PySide6 Qt Widgets, GUI thread only)                        │
├──────────────┬──────────────┬──────────────┬──────────────┬───────────────┤
│ MainWindow   │ Pages        │ Widgets      │ Dialogs      │ Theme         │
│ `ui/main_    │ `ui/pages/`  │ `ui/widgets/ │ `ui/context_ │ `ui/theme.py` │
│ window.py`   │ (7 pages)    │              │ repair_      │               │
│              │              │              │ dialog.py`   │               │
└──────────────┴──────┬───────┴──────────────┴──────────────┴───────────────┘
                      │ signals only (Qt Signal/Slot)
                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Layer 3 — Controller (orchestration, stage state machine, schedulers)     │
│ `controllers/job_controller.py`  (JobController, AlignWorker)             │
└──────┬───────────────────────────┬───────────────────────────┬────────────┘
       │                           │                           │
       ▼                           ▼                           ▼
┌─────────────────┐  ┌──────────────────────────┐  ┌─────────────────────────┐
│ Layer 2 —       │  │ Layer 2 — Transcript/    │  │ Layer 2 — AI / Online   │
│ Pipeline        │  │ Study services           │  │ services                │
│ `services/      │  │ `services/transcript_    │  │ `services/ai_repair_    │
│ export_service. │  │ service.py` (layered     │  │ service.py`             │
│ py`             │  │  model + repair engine)  │  │ `services/groq_         │
│ `services/      │  │ `services/transcript_    │  │ transcription.py`       │
│ detection_eval. │  │ store.py` (working layer)│  │ `services/transcription_│
│ py`             │  │ `services/transcript_    │  │ backends.py` (provider- │
│                 │  │ formats.py` (serializers)│  │  neutral contract)      │
│                 │  │ `services/study_         │  │                         │
│                 │  │ service.py`              │  │                         │
└───────┬─────────┘  └────────────┬─────────────┘  └───────────┬─────────────┘
        │                         │                            │
        ▼                         ▼                            ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Layer 1 — Infrastructure (no application state)                           │
│ `infrastructure/ffmpeg_wrapper.py`    (QProcess ffmpeg/ffprobe)           │
│ `infrastructure/whisper_wrapper.py`   (QProcess whisper-cli)              │
│ `infrastructure/cv_engine.py`         (SlideDetectorWorker QThread, CV)   │
│ `infrastructure/video_reader.py`      (FFmpeg rawvideo pipe streaming)    │
│ `infrastructure/transcription_engines.py` (CPU/Vulkan engine registry)    │
│ `infrastructure/ollama_client.py`     (stdlib localhost LLM client)       │
│ `infrastructure/secret_store.py`      (Windows Credential Manager)        │
│ `infrastructure/config_manager.py` / `file_manager.py` / `process_tree.py`│
│ `infrastructure/whisper_detector.py`  (CLI capability probe)              │
└───────┬─────────────────────┬──────────────────────┬──────────────────────┘
        │                     │                      │
        ▼                     ▼                      ▼
┌───────────────┐  ┌────────────────────┐  ┌─────────────────────────────────┐
│ External      │  │ External data dir  │  │ Optional network (opt-in only)  │
│ processes     │  │ `~/LecturePackData`│  │ Groq API · Ollama localhost     │
│ ffmpeg.exe    │  │ jobs/<uuid>/...    │  │ (default build is fully offline)│
│ ffprobe.exe   │  │ config.json        │  │                                 │
│ whisper-cli   │  │ models/            │  │                                 │
│ (`bin/`)      │  │ (`constants.py:58`)│  │                                 │
└───────────────┘  └────────────────────┘  └─────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `MainWindow` | Application shell: nav rail, command bar, page stack (indices 0–6), QSettings persistence, controller wiring, drag-drop import, v1.0-compat aliases | `lecturepack/ui/main_window.py` |
| Pages | One workspace per page: Home (jobs), Process (setup+live pipeline), Review (slide decisions + transcript edits), Transcript (4-tab workspace), Exports, Settings, Study | `lecturepack/ui/pages/*.py` |
| `JobController` | Owns the stage state machine, parallel stage group (Transcribe ∥ Detect Slides), stage cache fingerprints, cancel latch, retired-worker reaping, online→local fallback | `lecturepack/controllers/job_controller.py` |
| `Job` | Aggregate of manifest/source/settings/state JSON for one job; atomic save; stage status transitions; product-mode and preset resolution | `lecturepack/models/job.py` |
| `FFmpegWrapper` | Async audio extraction via QProcess; synchronous ffprobe metadata probe; binary auto-detection | `lecturepack/infrastructure/ffmpeg_wrapper.py` |
| `WhisperWrapper` | Async whisper-cli QProcess; per-binary CLI flag detection; runtime CPU/Vulkan backend probing from stderr | `lecturepack/infrastructure/whisper_wrapper.py` |
| `SlideDetectorWorker` | QThread slide detection: two-pass piped decode (FFmpeg analysis pipe + native-res capture) with legacy cv2 seek fallback; major/progressive-build decision paths; dedup | `lecturepack/infrastructure/cv_engine.py` |
| `AnalysisFrameStream` / `FrameCursor` | Single FFmpeg rawvideo pipe producing cropped/downscaled/grayscale analysis frames; sliding-window cursor for look-ahead probes | `lecturepack/infrastructure/video_reader.py` |
| `BackendRegistry` | Provider-neutral transcription adapters (local whisper.cpp, Groq fast/accurate); unknown selection fails closed to local | `lecturepack/services/transcription_backends.py` |
| `EngineRegistry` | Selects the local whisper.cpp binary (CPU verified default, optional Vulkan build, `auto` policy gated on recorded benchmark) | `lecturepack/infrastructure/transcription_engines.py` |
| `transcript_service` | Layered transcript model (raw → normalized → context repair → corrections), pure stdlib | `lecturepack/services/transcript_service.py` |
| `transcript_store` | Working-layer persistence (`working.json` schema 2) + split/merge/edit pure functions; mirrors legacy `edited.json` | `lecturepack/services/transcript_store.py` |
| `transcript_formats` | Serializers (txt/md/json/jsonl/csv/srt/vtt) + semantic section grouping, pure stdlib | `lecturepack/services/transcript_formats.py` |
| `ExportService` / `ExportWorker` | Slide↔transcript alignment (`aligned.json`) and all export artifacts (slides.pdf, transcript.*, study-pack.html/.pdf, study-data.json) | `lecturepack/services/export_service.py` |
| `study_service` | Single writer for user-authored `study.json` (bookmarks, notes, resume position); deterministic Study overview derivation | `lecturepack/services/study_service.py` |
| `groq_transcription` | Chunk planning, exact-PID FLAC encoding, stdlib multipart client, retry/resume cache, ordered merge, canonical output publication | `lecturepack/services/groq_transcription.py` |
| `AiRepairWorker` | QThread Context Repair proposal generation with absolute exception boundary and per-job disk cache | `lecturepack/services/ai_repair_service.py` |
| `OllamaClient` / `OllamaRepairProvider` | Stdlib streaming client for localhost Ollama; typed errors; adapter into `ContextRepairEngine` guardrails | `lecturepack/infrastructure/ollama_client.py` |
| `ConfigManager` | `config.json` persistence, binary/model autodetect, PyInstaller-aware resource dirs, diagnostics | `lecturepack/infrastructure/config_manager.py` |
| `FileManager` | Atomic JSON writes (`.tmp` + `os.replace`), BOM-tolerant reads, job directory layout, archive/restore/zip | `lecturepack/infrastructure/file_manager.py` |
| `process_tree` | Scoped termination of owned process trees (exact-PID `taskkill /PID <pid> /T /F`; never name-based) | `lecturepack/infrastructure/process_tree.py` |
| `WindowsCredentialStore` | Only API-key persistence path (ctypes → CredRead/CredWrite); no plaintext fallback | `lecturepack/infrastructure/secret_store.py` |
| `run_packaged_acceptance` | Headless end-to-end driver for the frozen EXE (`--run-acceptance`) | `lecturepack/acceptance.py` |

## Pattern Overview

**Overall:** Strict 4-layer desktop architecture (UI → Controller → Service → Infrastructure) with a per-job staged pipeline driven by a Qt signal-based state machine. Persistence is plain files + JSON manifests — no database (`docs/DECISIONS.md` AD-3).

**Key Characteristics:**
- Each layer calls only the layer directly below it (`docs/ARCHITECTURE.md` §1). The UI never calls infrastructure directly; services never reference widgets; infrastructure holds no application state.
- All long-running work is off the GUI thread: `QProcess` for external CLI tools, `QThread` worker objects for in-process compute. Communication is signals-only in both directions.
- Every stage of the pipeline is independently tracked, resumable, and cache-fingerprinted; crash recovery reclassifies `running` → `interrupted` and resumes from the first incomplete stage.
- Source-derived artifacts (raw transcript, candidate frames) are immutable; user/AI edits live in separate, reversible layers.

## Layers

**UI Layer:**
- Purpose: Render workspaces, collect user input, reflect controller state.
- Location: `lecturepack/ui/`
- Contains: `main_window.py` (shell + page stack), `pages/` (7 workspaces), `widgets/` (reusable: `slide_grid.py`, `context_repair_panel.py`, `crop_selector.py`), `theme.py` (QSS + `selection_visuals` pure function), `context_repair_dialog.py` (thin dialog hosting the repair panel).
- Depends on: Controller (`JobController`), services (`transcript_store`, `transcript_formats`, `study_service`), `FileManager` (read-only convenience).
- Used by: Nothing above it. Instantiated only by `lecturepack/app.py:main()`.

**Controller Layer:**
- Purpose: Pipeline orchestration and cross-cutting scheduling policy.
- Location: `lecturepack/controllers/job_controller.py`
- Contains: `JobController` (QObject) and `AlignWorker` (QThread shim around `ExportService.align_and_export`).
- Depends on: Services and infrastructure wrappers; `models/job.py` for state.
- Used by: `MainWindow` only.

**Service Layer:**
- Purpose: Business logic: alignment/exports, layered transcript model, provider-neutral transcription contract, Groq transport, AI repair orchestration, study data.
- Location: `lecturepack/services/`
- Contains: `export_service.py`, `transcript_service.py`, `transcript_store.py`, `transcript_formats.py`, `transcription_backends.py`, `groq_transcription.py`, `ai_repair_service.py`, `study_service.py`, `detection_eval.py`.
- Depends on: Infrastructure (`FileManager`, `ollama_client`, `transcription_engines`, `process_tree`).
- Used by: Controller and UI. Note: `transcript_service`, `transcript_store`, `transcript_formats`, `study_service`, `detection_eval`, `groq_transcription` are deliberately Qt-free (importable in the frozen bundle and unit tests); `export_service` and `transcription_backends` are Qt-coupled by design (QThread/QObject signals).

**Infrastructure Layer:**
- Purpose: External process wrappers, CV engine, file I/O primitives, config, secrets, capability detection.
- Location: `lecturepack/infrastructure/`
- Contains: `ffmpeg_wrapper.py`, `whisper_wrapper.py`, `cv_engine.py`, `video_reader.py`, `transcription_engines.py`, `whisper_detector.py`, `ollama_client.py`, `secret_store.py`, `config_manager.py`, `file_manager.py`, `process_tree.py`.
- Depends on: Standard library + third-party binaries/libraries only.
- Used by: Services and controller.

**Models:**
- Purpose: Job aggregate (the only domain model).
- Location: `lecturepack/models/job.py`
- Depends on: `constants.py`, `FileManager`.

## Data Flow

### Primary Request Path — processing a lecture

1. User drops/browses a video → `HomePage.video_chosen` → `MainWindow` creates `Job(data_dir, video_path=...)` which calls `FileManager.init_job_dir` and writes `manifest.json` / `settings.json` / `state.json` (`lecturepack/models/job.py:31-84`).
2. `ProcessPage` collects settings (product mode, preset, whisper model/engine, crop region, glossary) into `job.settings`; `MainWindow` calls `controller.set_job(job)` then `run_pipeline()` (`lecturepack/controllers/job_controller.py:182`).
3. `JobController.run_next_stage()` (`job_controller.py:289`) walks `constants.STAGES`, skips stages completed with a valid cache fingerprint (`_stage_cache_valid`, `job_controller.py:275`), auto-completes stages excluded by the product mode (`STAGES_SKIPPED_BY_MODE`, `job_controller.py:13-17`), and launches the next stage — or the parallel group Transcribe + Detect Slides (`job_controller.py:327-345`).
4. Stage execution:
   - **Inspect** — synchronous `FFmpegWrapper.inspect_video` (ffprobe `subprocess.run`), metadata merged into `source.json` (`job_controller.py:404-419`).
   - **Extract Audio** — `FFmpegWrapper.start_audio_extraction` QProcess → `audio/lecture-16khz-mono.wav` (`infrastructure/ffmpeg_wrapper.py:108`).
   - **Transcribe** — `BackendRegistry.resolve(requested)` → `TranscriptionBackend.start(TranscriptionRequest)`; local path delegates to `WhisperWrapper` QProcess writing `transcript/raw.{json,srt,txt}` (`job_controller.py:437-493`, `services/transcription_backends.py:127-199`).
   - **Detect Slides** — `SlideDetectorWorker` QThread; pass 1 streams analysis frames from one FFmpeg pipe (`video_reader.AnalysisFrameStream`), pass 2 captures full-res PNGs at accepted timestamps; writes `frames/candidates/*.png` and emits candidate dicts persisted to `candidates.json` (`job_controller.py:697-709`).
   - **Align** — `AlignWorker` → `ExportService.align_and_export()` writes `transcript/aligned.json` (`services/export_service.py:19-132`).
   - **Review Ready** — bookkeeping stage completed immediately (`job_controller.py:359`).
5. After a successful Transcribe, `_build_normalized_transcript` (`job_controller.py:619-657`) deterministically writes `transcript/normalized.json` and `transcript/context_candidates.json` via `services/transcript_service`. Failure here never fails the pipeline.
6. On each stage completion the controller records a SHA-256 stage fingerprint into `stage_fingerprints.json` (`job_controller.py:266-273`); changed inputs silently invalidate the affected stage on the next run.
7. **Export** never auto-runs: `export_now()` (triggered from the Exports page or review toolbar) starts `ExportWorker` which regenerates `exports/` from current decisions (`job_controller.py:724-738`).

### Review / study flow (post-pipeline)

1. `MainWindow._load_review_data()` (`ui/main_window.py:377`) loads candidates + working transcript into `ReviewPage` and `TranscriptPage`.
2. Slide keep/reject/restore decisions mutate `candidates.json` decisions and move PNGs between `frames/candidates|accepted|rejected/` — reversible, nothing deleted (`ui/pages/review_page.py`).
3. Text edits/split/merge go through `transcript_store` pure functions → `working.json` (schema 2) + mirrored legacy `edited.json` (`services/transcript_store.py:151-252`).
4. Bookmarks/notes/resume position go through `study_service` → `study.json` (schema 1); `StudyPage` rebuilds its overview deterministically from working transcript + `aligned.json` + section overrides (`services/study_service.py:181`).
5. Re-export reads current layers; upstream stages are never rerun.

### Context Repair flow (optional, fault-isolated)

1. `ContextRepairPanel` / `ContextRepairDialog` requests proposals (`ui/widgets/context_repair_panel.py`).
2. Deterministic provider (`DeterministicNameProvider`, `transcript_service.py:562`) runs synchronously — pure CPU, cannot fail on I/O. The Ollama provider always runs inside `AiRepairWorker` (QThread) with a typed exception boundary (`services/ai_repair_service.py`).
3. Proposals become a reversible `CorrectionSet` (`corrections.json`); accepted corrections materialize `corrected.json`. `raw.json` and `normalized.json` are never written by this flow.
4. Responses are cached per job in `transcript/ai_cache.json` keyed by prompt-version + model + content hash.

### Online (Groq) transcription flow (opt-in)

1. Requires per-job `online_privacy_accepted` and an API key in Windows Credential Manager (`infrastructure/secret_store.py`); otherwise the backend fails closed with typed `GroqError` kinds (`services/transcription_backends.py:239-246`).
2. `_GroqWorker` (QThread) plans overlapping chunks, encodes FLAC via an exact-PID FFmpeg subprocess, uploads with a stdlib multipart client + `ThreadPoolExecutor` (concurrency ≤ 4), caches each chunk response under `transcript/groq-cache/<fingerprint>/responses/`, then merges in order (`transcription_backends.py:202-345`, `services/groq_transcription.py`).
3. Canonical `raw.{json,srt,txt}` are written only after a complete merge. On eligible failure the controller may start exactly one Private Local fallback into a `.fallback-pending` prefix, promoted as a unit on success; the parallel slide-detection branch is never cancelled (`job_controller.py:543-617`).

**State Management:**
- No database and no ORM. All state is JSON files written atomically by `FileManager.write_json_atomic` (`infrastructure/file_manager.py:7-15`).
- App settings: `<data_dir>/config.json` (`ConfigManager`). UI geometry/splitters/last page: `QSettings("LecturePack","LecturePack")` (`ui/main_window.py:128`). Secrets: Windows Credential Manager only.
- In-memory shared state lives on `MainWindow` (`current_job`, `controller`) and `JobController`; pages receive the job and emit signals upward rather than sharing stores.

## Key Abstractions

**Job / job directory:**
- Purpose: One lecture's complete working state on disk; the `Job` class is a thin aggregate over four JSON files plus a path map.
- Examples: `lecturepack/models/job.py`, path map in `infrastructure/file_manager.py:53-66`.
- Pattern: Aggregate root + atomic JSON persistence. All stage statuses flow through `Job.set_stage_status` (`models/job.py:129`) which recomputes `overall_status`.

**Stage state machine:**
- Purpose: Ordered, resumable pipeline with per-stage status (`pending|running|completed|failed|cancelled|interrupted|skipped`-via-product-mode) and content-based cache invalidation.
- Examples: `constants.STAGES` (`lecturepack/constants.py:39-55`), scheduler in `controllers/job_controller.py:289-402`.
- Pattern: State machine + parallel stage group (Transcribe ∥ Detect Slides) with a group-error join and a user-cancel latch that prevents late worker events from resurrecting the pipeline.

**Provider-neutral transcription backend:**
- Purpose: The controller knows only `start/progress/finished/cancel`; providers (local whisper.cpp, Groq fast/accurate) are adapters behind a stable contract.
- Examples: `TranscriptionBackend`, `BackendCapabilities`, `TranscriptionRequest`, `TranscriptionResult`, `CancellationToken`, `BackendRegistry` in `lecturepack/services/transcription_backends.py:30-440`.
- Pattern: Adapter + registry; `BackendRegistry.resolve` fails closed to the local backend for unknown keys (`transcription_backends.py:431-437`).

**Transcription engine (local binary selection):**
- Purpose: Orthogonal to provider: which whisper.cpp binary runs locally (verified CPU vs optional Vulkan build).
- Examples: `EngineRegistry.resolve` policy (`infrastructure/transcription_engines.py:159-193`); runtime backend proof parsed from stderr (`infrastructure/whisper_wrapper.py:173-194`).
- Pattern: Registry + policy (`auto` prefers Vulkan only when present AND recorded benchmark says faster).

**Layered transcript model:**
- Purpose: Keep source-derived and user/AI-authored content strictly separated and auditable.
- Examples: Layer 1 `raw.json` (immutable) → Layer 2 `normalized.json` (deterministic) → Context candidates/corrections → `working.json` (user edits, schema 2). Implemented across `services/transcript_service.py`, `services/transcript_store.py`.
- Pattern: Immutable base layer + derived layers + pure-function transformations (Qt-free, unit-testable).

**Product modes:**
- Purpose: Gate stages and export artifacts per job intent.
- Examples: `constants.PRODUCT_MODES` (`constants.py:24-36`); gating map `STAGES_SKIPPED_BY_MODE` (`job_controller.py:13-17`); mode-aware exports (`export_service.py:19-35`).

**Presets:**
- Purpose: Named slide-detection parameter bundles (`conservative`/`balanced`/`detailed`) including v1.0 precision guards.
- Examples: `constants.PRESETS` (`constants.py:80-116`), consumed via `Job.get_preset_settings` (`models/job.py:159-163`).

## Entry Points

**GUI application:**
- Location: `lecturepack/app.py:main()` (invoked via `lecturepack/__main__.py` → `python -m lecturepack`, or the frozen `LecturePack.exe` built from `LecturePack.spec`).
- Triggers: User launch.
- Responsibilities: Create `QApplication`, `ConfigManager()`, `MainWindow(config)`, exec loop. Binary autodetect happens in `MainWindow.__init__` (`ui/main_window.py:149-150`).

**`--selftest`:**
- Location: `lecturepack/app.py:121-156` (`run_selftest`).
- Triggers: `LecturePack.exe --selftest` (packaging validation).
- Responsibilities: Offscreen Qt, temp throwaway data dir (never the user's), import-all + construct `MainWindow`, print PASS/FAIL, exit 0/1.

**`--run-acceptance`:**
- Location: `lecturepack/app.py:159-184` → `lecturepack/acceptance.py:run_packaged_acceptance`.
- Triggers: `LecturePack.exe --run-acceptance <video> <model> <data_dir> [out_json] [--names a,b,c] [--mode ...]`.
- Responsibilities: Drive the real pipeline end-to-end in the frozen build, record a structured JSON evidence report, exit 0/1.

**`--run-packaged-validation`:**
- Location: `lecturepack/app.py:6-119`. Developer-only scripted UI check; hardcodes personal paths — do not reuse as a template (see Anti-Patterns).

**Tests:**
- Location: `tests/` (pytest, config `pytest.ini`), plus `tests/validate_real_video.py` for manual real-media validation.

## Architectural Constraints

- **Threading:** All widgets and all controller signal handlers run on the Qt GUI thread. External tools run as `QProcess` (async) except the ffprobe inspect which is a fast synchronous `subprocess.run` (`infrastructure/ffmpeg_wrapper.py:73`). In-process compute runs on `QThread` workers (`SlideDetectorWorker`, `AlignWorker`, `ExportWorker`, `AiRepairWorker`, `_GroqWorker`, `ThumbnailLoader`). `AnalysisFrameStream` additionally owns one plain `threading.Thread` draining the FFmpeg pipe's stderr (`infrastructure/video_reader.py`). Groq uploads use a `ThreadPoolExecutor` inside `_GroqWorker` (max 4 workers).
- **Process spawning:** Never `shell=True`. Windows console windows suppressed via `CREATE_NO_WINDOW`. Termination is scoped to exact owned PIDs (`taskkill /PID <pid> /T /F`) — image-name killing is forbidden (`infrastructure/process_tree.py`).
- **Global state:** Module-level mutable state is limited to `WhisperCapabilityDetector._cache` (static capability cache, `infrastructure/whisper_detector.py:8`) and `ai_repair_service._DETACHED_WORKERS` (detached-worker lifetime set, `services/ai_repair_service.py:41`). Everything else hangs off `MainWindow`/`JobController`/`Job` instances.
- **Singletons:** One `JobController` per `MainWindow`; one `ConfigManager` created in `app.main()` and shared. `Job` is replaced wholesale when switching lectures.
- **Paths:** Data dir defaults to `~/LecturePackData` (`constants.DEFAULT_DATA_DIR`) and is user-configurable; all job I/O must stay under it. Binaries resolve application-relative (PyInstaller `_MEIPASS`-adjacent for the frozen app, project root in dev) — never rely on system PATH as the primary source (`infrastructure/config_manager.py:9-20`).
- **Secrets:** API keys exist only in Windows Credential Manager; they never pass through `ConfigManager`, job JSON, or logs (`infrastructure/secret_store.py:1-6`).
- **Network:** Offline by default. The only sanctioned endpoints are localhost Ollama (`http://localhost:11434`) and, after explicit per-job privacy acceptance, `https://api.groq.com/openai/v1/audio/transcriptions` (`services/groq_transcription.py:28`).
- **Immutability:** The original lecture video is never modified; `raw.json` is never rewritten by post-processing layers (enforced by convention + `RawTranscriptImmutableError`, `services/transcript_service.py:34`).
- **Circular imports:** None observed. Heavy/optional imports are deferred inside functions (e.g. `from lecturepack.services.groq_transcription import ...` inside `_GroqWorker.run`, `transcription_backends.py:231`) to keep module import cheap in the frozen bundle.

## Anti-Patterns

### God-object shell with v1.0-compat alias surface

**What happens:** `lecturepack/ui/main_window.py` is ~1260 lines / 57 KB: it builds the shell, owns all cross-page navigation and job lifecycle, and exposes v1.0 attribute aliases (`slides_view`, `transcript_table`, `crop_selector`, ...) that forward into the new pages for legacy tests/tools.
**Why it's wrong:** Any page or shell change touches the same file; the alias layer obscures which object truly owns a widget and encourages new code to keep bypassing the page encapsulation.
**Do this instead:** Add behavior to the owning page in `ui/pages/` and route cross-page intents through page signals (e.g. `ReviewPage.study_data_changed`, `StudyPage.navigate_requested`). Touch the alias block in `main_window.py` only when a legacy consumer genuinely requires it.

### Hardcoded personal paths in a shipped entry point

**What happens:** `run_packaged_validation` in `lecturepack/app.py:13-16,75` hardcodes `C:\Users\marsh\LecturePackData`, a specific job UUID, and a OneDrive video path.
**Why it's wrong:** It only runs on one machine, can touch real user data, and sets a bad precedent for "validation" code living in the production entry module.
**Do this instead:** Use the parameterized `--run-acceptance` driver (`lecturepack/acceptance.py`) for new end-to-end checks; treat `run_packaged_validation` as frozen legacy.

### Qt coupling inside the service layer (selective)

**What happens:** `services/export_service.py` defines `ExportWorker(QThread)` and `services/transcription_backends.py` defines `QObject` backends with Qt signals, while sibling modules (`transcript_service`, `transcript_store`, `transcript_formats`, `study_service`, `groq_transcription`) are deliberately Qt-free.
**Why it's wrong:** The Qt-free rule is the project's testability boundary; letting it erode further would make services un-importable in headless/unit contexts and in the frozen bundle's validation paths.
**Do this instead:** Keep new service logic Qt-free (pure functions/dataclasses). Put Qt wrappers (workers, signal adapters) at the service edge, mirroring how `AiRepairWorker` wraps the stdlib-only `ollama_client`.

### Controller absorbing provider/policy detail

**What happens:** `JobController` (~784 lines) owns scheduling, cache fingerprints, backend resolution, engine resolution, the online→local fallback state machine, and pending-prefix promotion (`controllers/job_controller.py:543-617`).
**Why it's wrong:** Fallback and fingerprint policy already leak provider-aware detail into the orchestrator; adding another provider here would multiply that coupling.
**Do this instead:** Extend providers through `BackendRegistry.register` and `BackendCapabilities` (`services/transcription_backends.py:419-423`) and keep provider-specific retry/resume inside the adapter (the Groq adapter is the template). Only the neutral start/result/cancel contract belongs in the controller.

## Error Handling

**Strategy:** Layer-appropriate containment — infrastructure raises typed exceptions, services translate them into typed results/signals, the controller records them into `state.json`, and the UI renders recoverable error states. Nothing external is allowed to crash the GUI thread.

**Patterns:**
- Typed exception hierarchies with machine-readable `kind`: `GroqError` (`services/groq_transcription.py:37`), `OllamaError` family (`infrastructure/ollama_client.py:39-60`), `SecretStoreError` (`infrastructure/secret_store.py:19`).
- Result objects instead of exceptions across thread boundaries: `TranscriptionResult(success, error_code, retryable, fallback_allowed)` (`services/transcription_backends.py:83-97`).
- Absolute exception boundary in QThread workers: `AiRepairWorker` catches everything and emits a recoverable failure state (`services/ai_repair_service.py`); `AlignWorker` emits `finished(False, str(e))` (`controllers/job_controller.py:37-44`).
- Path/secret sanitization before persistence or display: `_safe_error` (`transcription_backends.py:117-124`), `_safe_provider_message` (`groq_transcription.py:92`).
- Optional layers degrade instead of failing the pipeline: normalization errors are logged and skipped (`controllers/job_controller.py:655-657`); missing/corrupt JSON reads return defaults via `FileManager.read_json_safe`.
- Stage failures stop the sibling branch of the parallel group cleanly and surface as `pipeline_failed` (`controllers/job_controller.py:383-400`).

## Cross-Cutting Concerns

**Logging:** Human-readable progress via `JobController.stage_log(stage, text)` routed to the Process page log drawer and status bar; structured evidence for packaged runs is written by `lecturepack/acceptance.py`. There is no central log framework — per-job artifacts under `jobs/<uuid>/logs/` and `logs/app.log` in the data dir per `docs/ARCHITECTURE.md` §10.

**Validation:** ffprobe metadata gates the pipeline start (`_run_inspect` raises on missing video); settings load is defensive (`Job.load` backfills defaults for pre-v1.0 jobs, `models/job.py:86-115`); `read_json_safe` tolerates UTF-8 BOMs from hand-edited files (`infrastructure/file_manager.py:17-28`).

**Authentication:** None for the app itself. The single external credential (Groq API key) lives in Windows Credential Manager and is read only at request time (`infrastructure/secret_store.py`); a per-job `online_privacy_accepted` flag must be set before any upload (`controllers/job_controller.py:484-486`).

**Cancellation:** Cooperative everywhere: QProcess trees via exact-PID taskkill, QThread workers via checked flags/tokens (`CancellationToken`, `SlideDetectorWorker._is_cancelled`), HTTP streams via cancel events. A latched `_user_cancelled` flag in the controller guarantees late worker completions never restart the pipeline (`controllers/job_controller.py:150-180,361-371`).

---

*Architecture analysis: 2026-07-17*
