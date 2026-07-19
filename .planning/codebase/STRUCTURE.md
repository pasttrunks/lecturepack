# Codebase Structure

**Analysis Date:** 2026-07-17

Repository root: `C:\Users\marsh\Documents\LecturePack`. Application package: `lecturepack/` (importable, also the PyInstaller entry). Runtime user data lives OUTSIDE the repo in `~/LecturePackData` (`lecturepack/constants.py:58`) — never touch it from code or tooling.

## Directory Layout

```
LecturePack/
├── lecturepack/            # Application package (the entire shippable app)
│   ├── __main__.py         # `python -m lecturepack` -> app.main()
│   ├── app.py              # Entry point: QApplication, MainWindow, CLI modes
│   ├── constants.py        # Stages, product modes, presets, backend keys, data dir default
│   ├── acceptance.py       # Headless end-to-end driver for the frozen EXE
│   ├── controllers/        # Layer 3: pipeline orchestration
│   │   └── job_controller.py
│   ├── models/             # Domain model (Job aggregate)
│   │   └── job.py
│   ├── services/           # Layer 2: business logic (mostly Qt-free)
│   │   ├── export_service.py
│   │   ├── transcript_service.py
│   │   ├── transcript_store.py
│   │   ├── transcript_formats.py
│   │   ├── transcription_backends.py
│   │   ├── groq_transcription.py
│   │   ├── ai_repair_service.py
│   │   ├── study_service.py
│   │   └── detection_eval.py
│   ├── infrastructure/     # Layer 1: processes, CV, files, config, secrets
│   │   ├── ffmpeg_wrapper.py
│   │   ├── whisper_wrapper.py
│   │   ├── whisper_detector.py
│   │   ├── transcription_engines.py
│   │   ├── cv_engine.py
│   │   ├── video_reader.py
│   │   ├── ollama_client.py
│   │   ├── secret_store.py
│   │   ├── process_tree.py
│   │   ├── config_manager.py
│   │   └── file_manager.py
│   └── ui/                 # Layer 4: PySide6 widgets (GUI thread only)
│       ├── main_window.py  # Shell: nav rail, command bar, page stack, QSettings
│       ├── theme.py        # QSS theme + selection_visuals (pure, testable)
│       ├── context_repair_dialog.py
│       ├── pages/          # One workspace per page (7)
│       │   ├── home_page.py        # stack index 0
│       │   ├── process_page.py     # stack index 1
│       │   ├── review_page.py      # stack index 2 (stable for legacy tests)
│       │   ├── transcript_page.py  # stack index 3
│       │   ├── exports_page.py     # stack index 4
│       │   ├── settings_page.py    # stack index 5
│       │   └── study_page.py       # stack index 6 (appended; nav order remapped)
│       └── widgets/        # Reusable composite widgets
│           ├── slide_grid.py
│           ├── context_repair_panel.py
│           └── crop_selector.py
├── tests/                  # pytest suite (config in pytest.ini)
├── docs/                   # Product/architecture/decision/handoff documents
│   └── evidence/           # Benchmark + validation evidence JSON
├── bin/                    # Bundled external binaries (ffmpeg, ffprobe, whisper.cpp)
│   └── Release/            # Full whisper.cpp CPU release (DLLs + tools)
├── models/                 # Bundled ggml whisper models (dev; packaged build resolves app-relative)
├── build_release.py        # Release build script (PyInstaller)
├── LecturePack.spec        # PyInstaller onedir spec (entry: lecturepack/app.py)
├── requirements.txt        # Runtime deps (PySide6, OpenCV-headless, scikit-image, ...)
├── requirements-dev.txt    # Dev/test deps
├── pytest.ini              # testpaths=tests, test_*.py
├── build/ , dist/ , dist-release/   # PyInstaller outputs (generated)
├── .planning/              # GSD planning + codebase maps (this directory)
└── AGENTS.md               # Mandatory operating rules for code changes
```

Runtime data directory (external, default `C:\Users\<user>\LecturePackData`, see `lecturepack/infrastructure/config_manager.py:33` and `lecturepack/infrastructure/file_manager.py:53-66`):

```
LecturePackData/
├── config.json             # App settings (ConfigManager)
├── jobs/<job-uuid>/
│   ├── manifest.json       # Identity + source pointer (schema 1)
│   ├── source.json         # ffprobe metadata (Inspect stage output)
│   ├── settings.json       # Per-job settings: preset, product_mode, whisper, slide_detection
│   ├── state.json          # Stage state machine (overall_status + per-stage status)
│   ├── candidates.json     # Slide candidates with accept/reject decisions
│   ├── stage_fingerprints.json  # Stage cache keys (sha256 of inputs)
│   ├── study.json          # User-authored bookmarks/notes/resume (schema 1)
│   ├── audio/lecture-16khz-mono.wav
│   ├── transcript/
│   │   ├── raw.json/.srt/.txt        # Layer 1, immutable provider output
│   │   ├── normalized.json           # Layer 2, deterministic cleanup
│   │   ├── context_candidates.json   # Layer 3 proposals
│   │   ├── corrections.json / corrected.json
│   │   ├── edited.json               # Legacy v1.0 text overrides (mirrored)
│   │   ├── working.json              # Working layer (schema 2, split/merge/edit)
│   │   ├── aligned.json              # Slide<->segment mapping (Align stage)
│   │   ├── ai_cache.json             # Context Repair response cache
│   │   └── groq-cache/<fingerprint>/ # Online chunk audio + responses (resumable)
│   ├── frames/
│   │   ├── candidates/ accepted/ rejected/   # Candidate PNGs by decision
│   │   └── thumbs/                      # WebP thumbnail cache
│   ├── exports/            # slides.pdf, transcript.*, study-pack.html/.pdf, study-data.json
│   └── logs/
├── archive/<job-uuid>/     # Archived jobs (FileManager.archive_job)
└── models/                 # Downloaded whisper models (user-level)
```

## Directory Purposes

**`lecturepack/`:**
- Purpose: The entire application; frozen into `LecturePack.exe` by `LecturePack.spec`.
- Contains: Python modules only (plus `__pycache__` locally).
- Key files: `app.py` (entry), `constants.py` (shared constants/presets), `acceptance.py` (packaged E2E driver).

**`lecturepack/controllers/`:**
- Purpose: Layer 3 — orchestration between UI and services.
- Contains: `job_controller.py` (stage state machine, parallel scheduler, cache fingerprints, cancel/fallback policy).
- Key files: `controllers/job_controller.py`.

**`lecturepack/services/`:**
- Purpose: Layer 2 — business logic. Most modules are deliberately Qt-free pure stdlib for testability and frozen-bundle import safety; Qt wrappers (`ExportWorker`, backend QObjects, `AiRepairWorker`) sit at the module edge.
- Contains: export/alignment, layered transcript model, working-layer store, serializers, provider-neutral transcription contract, Groq transport, AI repair orchestration, study data, detection evaluation.
- Key files: `services/transcript_service.py` (largest; layered model + repair engine), `services/export_service.py` (alignment + all export artifacts), `services/transcription_backends.py` (provider contract + registry).

**`lecturepack/infrastructure/`:**
- Purpose: Layer 1 — wrappers over external processes, CV, file I/O, config, secrets. Holds no application state.
- Contains: QProcess wrappers, QThread CV worker, FFmpeg pipe reader, engine/secret/config/file managers.
- Key files: `infrastructure/cv_engine.py` (slide detection), `infrastructure/video_reader.py` (two-pass decode), `infrastructure/file_manager.py` (atomic JSON + job dir layout), `infrastructure/process_tree.py` (scoped process termination).

**`lecturepack/ui/`:**
- Purpose: Layer 4 — all widgets, GUI thread only.
- Contains: shell (`main_window.py`), pages, reusable widgets, theme.
- Key files: `ui/main_window.py` (shell + page stack; page index constants at lines 54-58), `ui/pages/transcript_page.py` (largest page), `ui/widgets/slide_grid.py` (selection delegate + thumbnail loader).

**`tests/`:**
- Purpose: pytest suite plus manual validation helpers.
- Contains: `test_*.py` unit/integration suites (e.g. `test_scheduler_and_engines.py`, `test_transcription_backend_contract.py`, `test_study_workspace_v12.py`), evidence generators (`generate_*_evidence.py`), `validate_real_video.py` (manual real-media check).
- Key files: `tests/test_integration.py`, `tests/test_stability_phase.py`.

**`docs/`:**
- Purpose: Governing documents referenced by `AGENTS.md` (spec, architecture, decisions, implementation plan, handoffs) and evidence JSON.
- Key files: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/PRODUCT_SPEC.md`.

**`bin/`:**
- Purpose: Bundled external binaries, resolved app-relative at runtime (never PATH-first).
- Contains: `ffmpeg.exe`, `ffprobe.exe`, `Release/` (whisper.cpp CPU build: `whisper-cli.exe` + `ggml*.dll`). Optional Vulkan build goes in `bin/vulkan/` (`infrastructure/transcription_engines.py:125`).
- Key files: `bin/ffmpeg.exe`, `bin/Release/whisper-cli.exe`.

## Key File Locations

**Entry Points:**
- `lecturepack/__main__.py`: `python -m lecturepack` shim.
- `lecturepack/app.py`: `main()` GUI entry + `--selftest` / `--run-acceptance` / `--run-packaged-validation` CLI modes.
- `LecturePack.spec`: PyInstaller build definition (entry `lecturepack/app.py`).

**Configuration:**
- `lecturepack/constants.py`: Stages, product modes, presets, backend keys, `DEFAULT_DATA_DIR`.
- `lecturepack/infrastructure/config_manager.py`: App settings (`config.json`), binary/model autodetect, diagnostics.
- `pytest.ini`: Test discovery config.
- `requirements.txt` / `requirements-dev.txt`: Dependencies (adding one requires justification in `docs/DECISIONS.md` per `AGENTS.md`).

**Core Logic:**
- `lecturepack/controllers/job_controller.py`: Pipeline orchestration.
- `lecturepack/models/job.py`: Job aggregate + state transitions.
- `lecturepack/infrastructure/cv_engine.py`: Slide detection algorithm.
- `lecturepack/services/transcript_service.py`: Layered transcript model + Context Repair engine.
- `lecturepack/services/export_service.py`: Alignment + export generation.

**Testing:**
- `tests/`: All automated tests.
- `lecturepack/acceptance.py`: Packaged end-to-end driver.
- `docs/TEST_PLAN.md`: Test strategy.

## Naming Conventions

**Files:**
- Snake_case modules throughout: `job_controller.py`, `transcript_store.py`, `slide_grid.py`.
- UI pages: `<name>_page.py` in `ui/pages/`; reusable widgets: descriptive snake_case in `ui/widgets/` (no suffix).
- Wrappers/adapters: `<tool>_wrapper.py` (`ffmpeg_wrapper.py`, `whisper_wrapper.py`), `<thing>_<role>.py` (`transcription_backends.py`, `transcription_engines.py`).
- Tests: `test_<area>.py` mirroring the subject (`test_transcript_layers.py` ↔ `services/transcript_service.py`).

**Code:**
- Classes: PascalCase (`JobController`, `SlideDetectorWorker`, `BackendRegistry`).
- Functions/variables: snake_case; private helpers prefixed `_` (`_stage_fingerprint`, `_run_piped`).
- Constants: UPPER_SNAKE in `constants.py` or module level (`STAGE_TRANSCRIBE`, `DETECTOR_VERSION`, `BACKEND_LOCAL_WHISPERCPP`).
- Qt workers: `<Role>Worker(QThread)` (`ExportWorker`, `AiRepairWorker`, `_GroqWorker`); signals named by event (`stage_started`, `backend_detected`, `result_ready`).
- JSON artifacts: snake_case filenames with `schema_version` fields (`working.json` schema 2, `study.json` schema 1).

**Directories:**
- Singular lowercase for package layers (`services/`, `controllers/`, `models/`, `infrastructure/`); plural for content collections (`ui/pages/`, `ui/widgets/`, `tests/`, `docs/`).
- Per-job runtime subdirs fixed by `FileManager.get_job_paths`: `audio/ transcript/ frames/{candidates,accepted,rejected,thumbs}/ exports/ logs/`.

## Where to Add New Code

**New pipeline stage:**
- Constant in `lecturepack/constants.py` (append to `STAGES` — order is persisted in existing `state.json` files, so append or handle migration), scheduler branch in `lecturepack/controllers/job_controller.py:run_next_stage`, worker/service under `lecturepack/services/` or `lecturepack/infrastructure/`, tests in `tests/`.

**New transcription provider:**
- Adapter implementing `TranscriptionBackend` in `lecturepack/services/transcription_backends.py` (or a new `services/<provider>_transcription.py` for transport, mirroring `services/groq_transcription.py`), registered via `BackendRegistry` (`transcription_backends.py:399-423`). Declare honest `BackendCapabilities` (is_local, uploads_audio, requires_secret). Do NOT put provider HTTP/retry logic in `JobController`.

**New service-layer logic:**
- Qt-free module in `lecturepack/services/`; expose Qt wrappers (workers/signals) only at the edge. Persist through `FileManager.write_json_atomic` with a `schema_version`.

**New UI workspace:**
- Page in `lecturepack/ui/pages/<name>_page.py` exposing signals upward; register in `ui/main_window.py` (`PAGES`, `PAGE_*` index, `NAV_PAGE_ORDER`) — append the stack index to keep existing indices stable (Study was appended at index 6 for this reason).

**New reusable widget:**
- `lecturepack/ui/widgets/`; keep painting logic factored into pure helpers (like `ui/theme.py:selection_visuals`) so it is unit-testable.

**New infrastructure wrapper:**
- `lecturepack/infrastructure/`; QProcess-based, `shell=False`, `CREATE_NO_WINDOW` on Windows, termination via `process_tree` exact-PID helpers only.

**Utilities / shared helpers:**
- Cross-layer JSON/file helpers: `lecturepack/infrastructure/file_manager.py`. Transcript segment helpers: `lecturepack/services/transcript_store.py` / `transcript_formats.py` (pure functions over plain segment dicts).

## Special Directories

**`bin/` and `models/`:**
- Purpose: Bundled binaries and whisper models.
- Generated: No (binaries downloaded from upstream releases; see `THIRD_PARTY_NOTICES.txt`).
- Committed: Yes (required for dev runs and packaging).

**`build/`, `dist/`, `dist-release/`:**
- Purpose: PyInstaller intermediate/final outputs.
- Generated: Yes (`build_release.py`).
- Committed: No (gitignored build artifacts; release bundles may be kept locally).

**`.planning/`:**
- Purpose: GSD planning state and codebase maps (including this file).
- Generated: Partially (by GSD tooling).
- Committed: Per project GSD convention.

**`~/LecturePackData` (external):**
- Purpose: All runtime user data: config, jobs, models, logs.
- Generated: Yes (created by `ConfigManager.resolve_data_dir`).
- Committed: No — never inside the repo; code and tooling must treat it as user-owned and read-only except through app flows (`AGENTS.md` safety rules).

---

*Structure analysis: 2026-07-17*
