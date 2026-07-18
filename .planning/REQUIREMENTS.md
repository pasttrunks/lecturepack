# REQUIREMENTS.md — LecturePack

Extracted from: intel/requirements.md, intel/decisions.md, intel/constraints.md, docs/PRODUCT_SPEC.md, docs/ARCHITECTURE.md, codebase/CONCERNS.md

---

## Functional Requirements

### REQ-core-conversion

- **Source:** docs/PRODUCT_SPEC.md §1
- **Description:** Lecture Pack converts locally stored university lecture videos into study materials: timestamped transcript, slides PDF, individual slide images, combined study pack, review interface, and optional local AI study notes.
- **Acceptance:** All core processing runs locally without paid APIs, subscriptions, cloud processing, accounts, telemetry, or usage limits. Local LLM is optional.
- **Scope:** Core product purpose
- **Phase:** 1 (verified, not built)

### REQ-privacy-safety

- **Source:** docs/PRODUCT_SPEC.md §4
- **Description:** P1: No telemetry/analytics. P2: No network except first-run model downloads and localhost LM Studio/Ollama. P3: Never upload videos/audio/transcripts/slides. P4: Never access university portals or store credentials. P5: Never modify/delete original video. P6: Never execute transcript content as commands. P7: All external process paths safely escaped.
- **Acceptance:** All seven privacy rules verified by automated and manual tests.
- **Scope:** Privacy, safety, data protection
- **Phase:** 1 (verified, not built)

### REQ-transcription

- **Source:** docs/PRODUCT_SPEC.md §8
- **Description:** Inspect source via ffprobe, extract 16 kHz mono WAV, run whisper.cpp outside UI process, capture progress/logs, export timestamped JSON/SRT/TXT, preserve raw output, allow separate edited transcript, stop cleanly on cancel, resume without repeating audio extraction, report CPU/Vulkan backend, support configurable glossary, never silently correct names/numbers.
- **Acceptance:** All 12 transcription requirements verified per TEST_PLAN.md Section 3.3.
- **Scope:** Transcription pipeline
- **Phase:** 1 (verified, not built)

### REQ-slide-extraction

- **Source:** docs/PRODUCT_SPEC.md §9
- **Description:** Deterministic CV pipeline (no LLM). Three-stage cascade: dHash fast screen, SSIM confirmation, histogram+pixel diff tiebreaker. Preprocessing (crop, mask, downscale, grayscale, blur, temporal median filter). Stability detection. Change type classification. Sequential and global deduplication. Full metadata recording.
- **Acceptance:** All slide detection assertions per TEST_PLAN.md Section 3.4 met.
- **Scope:** Slide detection
- **Phase:** 1 (verified, not built)

### REQ-alignment

- **Source:** docs/PRODUCT_SPEC.md §10
- **Description:** Deterministic timestamp overlap alignment. Each slide has display interval, each segment has time range. Segment assigned to slide with greatest temporal overlap. Boundary: assign to earlier slide. Every slide gets ≥1 segment; every segment maps to exactly 1 slide.
- **Acceptance:** Alignment assertions per TEST_PLAN.md Section 3.5 met.
- **Scope:** Transcript-to-slide alignment
- **Phase:** 1 (verified, not built)

### REQ-export-formats

- **Source:** docs/PRODUCT_SPEC.md §11
- **Description:** Export formats: Slides PDF (img2pdf), Slides folder, Transcript TXT, Transcript SRT, Transcript JSON, HTML study pack (Jinja2, base64, offline), PDF study pack (ReportLab).
- **Acceptance:** All export assertions per TEST_PLAN.md Section 3.6 met.
- **Scope:** Export pipeline
- **Phase:** 1 (verified, not built)

### REQ-job-lifecycle

- **Source:** docs/PRODUCT_SPEC.md §5
- **Description:** Support canceling and safely resuming a job. Per-stage state tracking. Crash recovery via atomic writes. Resume skips completed stages. Original video never copied into job directory.
- **Acceptance:** Job lifecycle assertions per TEST_PLAN.md Section 3.7 met.
- **Scope:** Job management, persistence
- **Phase:** 1 (verified, not built)

### REQ-study-workspace

- **Source:** docs/ARCHITECTURE.md v1.2 Study workspace, AD-11
- **Description:** Default landing page for completed jobs with three-column layout, deterministic overview derived from working transcript/aligned.json/candidates, bookmarks, notes, resume position. User-authored state in atomic study.json (schema 1). Exports include user annotations with proper escaping.
- **Acceptance:** Study workspace tests pass; old jobs load without study.json gracefully.
- **Scope:** v1.2 Study workspace
- **Phase:** 1 (verified, not built)

### REQ-provider-neutral-transcription

- **Source:** AD-12, docs/ARCHITECTURE.md v1.2
- **Description:** Service-layer TranscriptionBackend QObject contract with capabilities, request, result, progress, cancellation, structured error data. BackendRegistry resolves provider-level choices and fails closed to Private Local. Local cache fingerprints byte-identical to v1.1 for local.
- **Acceptance:** Backend contract tests pass; unknown selection fails to Private Local.
- **Scope:** v1.2 transcription architecture
- **Phase:** 1 (verified, not built)

### REQ-groq-transcription

- **Source:** AD-13, docs/ARCHITECTURE.md v1.2
- **Description:** Two provider adapters: groq-fast (whisper-large-v3-turbo) and groq-accurate (whisper-large-v3). Windows Credential Manager for API key. Per-job consent required. 23 MiB upload ceiling. FLAC audio only. Chunked upload with overlap de-duplication, retry, caching. Fallback to Private Local on failure. Preserves valid prior transcript.
- **Acceptance:** Contract/fake-server tests pass. Live validation deferred (no API key).
- **Scope:** v1.2 online transcription
- **Phase:** 1 (verified, not built)

### REQ-stability

- **Source:** AD-10, docs/ARCHITECTURE.md v1.2
- **Description:** Non-blocking UI shutdown: detach Context Repair workers immediately on close. Route app close through JobController.cancel(). PID-scoped process-tree termination via taskkill /PID /T /F. Persist runtime backend_used in state.json.
- **Acceptance:** Stability tests pass; close latency <50ms; owned PIDs terminated, unrelated processes survive.
- **Scope:** v1.2 process lifecycle
- **Phase:** 1 (verified, not built)

### REQ-architecture-layers

- **Source:** docs/ARCHITECTURE.md §1
- **Description:** Four-layer architecture enforced: UI (PySide6), Controller (JobController), Service (transcription, slide detection, export, alignment, LLM, study), Infrastructure (FFmpeg/whisper wrappers, CV engine, file I/O, config, secrets). Each layer calls only the layer directly below. UI never calls infrastructure directly. Services never reference UI widgets.
- **Acceptance:** The strict adjacent-layer rule remains the target. Phase 1
  release validation compares exact current violation identities with the
  committed `25e9dd1` baseline and permits no new violation; it discloses the 47
  existing violations across 62 cross-layer edges and makes no strict-conformance
  claim. Phase 2 owns eliminating that baseline debt and must reach zero
  violations.
- **Scope:** System architecture
- **Phase:** 1 (no-regression release gate), 2 (strict-conformance remediation)

### REQ-test-framework

- **Source:** docs/TEST_PLAN.md, .planning/codebase/TESTING.md
- **Description:** pytest with pytest-qt. Synthetic test fixtures via generate_test_video.py. Mock executable shims for ffmpeg/ffprobe/whisper. Nine assertion categories. Integration tests through real JobController with mock executables. UI tests via pytest-qt with pixel-level assertions.
- **Acceptance:** Full test suite passes; all patterns from TESTING.md followed.
- **Scope:** Testing infrastructure
- **Phase:** 1

---

## Release/Packaging Requirements (NEW for v1.2)

### REQ-version-bump

- **Source:** codebase/CONCERNS.md (tech debt)
- **Description:** Update version strings from stale 1.1.0 to 1.2.0 consistently across: lecturepack/__init__.py (__version__), lecturepack/constants.py (APP_VERSION), build_release.py (VERSION), and LecturePack.spec header. Consider single-source-of-truth via __init__.__version__.
- **Acceptance:** All version reporting locations show 1.2.0; new jobs created with v1.2 carry correct manifest version.
- **Scope:** Packaging, version management
- **Phase:** 1

### REQ-packaging-spec-audit

- **Source:** codebase/CONCERNS.md (tech debt), docs/DECISIONS.md AD-8
- **Description:** Audit and update LecturePack.spec hiddenimports against the current module tree. All v1.2 modules (transcription_backends, groq_transcription, study_service, ai_repair_service, transcript_store, secret_store, process_tree, video_reader, ollama_client, transcription_engines, whisper_detector, study_page, slide_grid, context_repair_panel, crop_selector) must be present. Remove or fix optimize=1 which strips assert statements used by selftest.
- **Acceptance:** PyInstaller build succeeds; packaged EXE passes --selftest with no import errors.
- **Scope:** PyInstaller packaging, build system
- **Phase:** 1

### REQ-packaged-build

- **Source:** AD-8, docs/WINDOWS_PORTABLE_INSTALL.md
- **Description:** Produce a self-contained onedir Windows package via build_release.py. Package must include LecturePack.exe, _internal/, bundled whisper-cli (CPU and Vulkan builds), ffmpeg/ffprobe, and documentation. Models NOT bundled (user-supplied). SHA256SUMS.txt and BUILD_MANIFEST.json generated.
- **Acceptance:** Portable ZIP builds; extracted EXE initializes; --selftest passes; no SmartScreen-related fatal errors.
- **Scope:** Release build
- **Phase:** 1

### REQ-test-suite-pass

- **Source:** AGENTS.md, intel/constraints.md (test-execution-rules)
- **Description:** Full pytest suite passes with 0 failures, 0 errors, 0 warnings that indicate regressions. Test count reconciled (address drift between 149 collected and 151 recorded). Actual pytest output recorded.
- **Acceptance:** `python -m pytest -v` produces clean pass output with documented test count.
- **Scope:** Quality gate
- **Phase:** 1

### REQ-self-test

- **Source:** docs/ARCHITECTURE.md §selftest, lecturepack/app.py
- **Description:** Application headless self-test (LecturePack.exe --selftest or python -m lecturepack --selftest) completes successfully: offscreen Qt, temp data dir, import-all, MainWindow construction, exit 0.
- **Acceptance:** Self-test prints PASS and exits 0 with no import, QThread, or QSS errors.
- **Scope:** Quality gate
- **Phase:** 1

---

## Test Coverage Requirements (NEW for v1.2)

### REQ-test-reconciliation

- **Source:** codebase/CONCERNS.md (test count drift)
- **Description:** Identify and reconcile the discrepancy between 149 collected test functions and the 151 recorded in the latest handoff. Determine which tests were removed, renamed, or never existed. Document the actual test count.
- **Acceptance:** Actual test count documented; discrepancy explained or resolved.
- **Phase:** 1

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-core-conversion | Phase 1 | Pending |
| REQ-privacy-safety | Phase 1 | Pending |
| REQ-transcription | Phase 1 | Pending |
| REQ-slide-extraction | Phase 1 | Pending |
| REQ-alignment | Phase 1 | Pending |
| REQ-export-formats | Phase 1 | Pending |
| REQ-job-lifecycle | Phase 1 | Pending |
| REQ-study-workspace | Phase 1 | Pending |
| REQ-provider-neutral-transcription | Phase 1 | Pending |
| REQ-groq-transcription | Phase 1 | Pending |
| REQ-stability | Phase 1 | Pending |
| REQ-architecture-layers | Phase 1 / Phase 2 | Phase 1 no-regression gate pending; Phase 2 debt open |
| REQ-test-framework | Phase 1 | Complete |
| REQ-version-bump | Phase 1 | Complete |
| REQ-packaging-spec-audit | Phase 1 | Complete |
| REQ-packaged-build | Phase 1 | Pending |
| REQ-test-suite-pass | Phase 1 | Pending |
| REQ-self-test | Phase 1 | Pending |
| REQ-test-reconciliation | Phase 1 | Pending |
