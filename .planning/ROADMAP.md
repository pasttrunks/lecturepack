# Roadmap: LecturePack v0.9.0-beta.7

## Overview

Beta 6 was certified complete on 2026-07-29 without measuring package size, launch time,
or running on a physical clean machine. On 2026-07-30 the owner installed it on a clean
device and found five defects the release gate should have caught: an oversized package,
a ~2 minute invisible launch, no protection against duplicate instances, a setup gate that
never appears on a healthy first run, and a blank taskbar icon.

Beta 7 closes those five defects with the smallest verified changes, preserving beta 6's
runtime contract, signed-repair architecture, processing behavior, updater behavior, and
existing user data.

## Phases

**Phase Numbering:** New milestone; numbering resets to Phase 1.

- [ ] **Phase 1: Clean-Device Footprint & First Launch** - Measure and cut package size, make first launch visibly responsive and single-instance, show a first-run setup checklist before the demo, and fix the taskbar icon.
- [ ] **Phase 2: Real Lecture Import & Processing** - Fix normal lecture importing and processing so that local videos and URL imports reliably use the bundled transcription runtime, persist jobs through their lifecycle, and all three output modes (Transcript Only, Slides Only, Study Pack) complete successfully.

## Phase Details

### Phase 1: Clean-Device Footprint & First Launch

**Goal**: A clean Windows device installs a materially smaller LecturePack, sees visible feedback within seconds of one click, cannot start a second instance, is shown a Ready / Needs Attention checklist before any demo offer, and sees the correct icon in the window and taskbar.

**Depends on**: Nothing (first beta-7 phase; builds on the shipped beta-6 runtime contract)

**Success Criteria** (what must be TRUE):

  1. Installer size and installed size are recorded as separate measured numbers from one freshly built `Setup.exe`, with the largest packaged contributors listed. The reported-vs-measured discrepancy (owner saw ~800 MB / ~900 MB; dev tree measures 841 MB ZIP / 1.9 GB installed) is resolved and explained, not averaged.
  2. `ggml-base.en.bin` is present exactly once in the packaged output; `translations/`, `qml/`, the Quick/Quick3D DLLs, and `Qt6Pdf.dll` are absent. Offline processing (FFmpeg, ffprobe, Whisper CPU CLI + DLLs, `ggml-base.en.bin`, `runtime-smoke.wav`) still passes the packaged runtime smoke.
  3. One click on a cold clean profile produces visible on-screen feedback in a few seconds, and the remaining runtime validation reports honest itemized progress rather than an unexplained wait. One cold and one warm launch are measured and recorded.
  4. Launching LecturePack while an instance is running raises the existing window instead of starting a second process; the guard acts before the slow validation path.
  5. A fresh profile shows the setup checklist with Ready / Needs Attention per requirement before the guided demo is offered, and offers the demo only after the user continues or deliberately skips. No component that is already bundled is downloaded or reinstalled.
  6. The LecturePack icon appears in the window title bar and the Windows taskbar for the installed build.

**Plans:** 8/8 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Footprint measurement script, seeded `01-EVIDENCE.md`, and the pre-cut baseline from one fresh installer (wave 1)
- [x] 01-02-PLAN.md — Additively restore installer asset publication in `release.yml`, with a contract test derived from `expected_asset_names()` (wave 1, D-22)
- [x] 01-03-PLAN.md — Persisted setup-acknowledged flag, the five-item checklist verdict service, and parallelized full validation (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-04-PLAN.md — Post-build Qt pruning, `ggml-base.en.bin` dedupe with a proven resolution chain, and the `resources/` findings report (wave 2)
- [x] 01-05-PLAN.md — Single-instance guard with a fixed raise sentinel, AppUserModelID process identity, and a non-silent icon path (wave 2)
- [x] 01-06-PLAN.md — Deferred bootstrap assessment on a worker thread with itemized progress, and the extended `get_bootstrap()` contract (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-07-PLAN.md — The `checking` and `checklist` overlay states in the existing WebEngine UI, with the acknowledgement and demo-gate wiring (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-08-PLAN.md — One post-cut build, the after-cuts size table and reconciliation, and the installed-build physical evidence gate (wave 4)

**Known blocker carried in, not caused here:** commit `a6164b1` (beta-6 Phase 2 Plan 05) replaced the installer-publishing release job with one that publishes only six signed runtime assets. The in-app updater requires `Setup.exe` + `SHA256SUMS.txt`, which CI no longer produces, so the updater cannot consume a current-workflow release. Planning must decide whether restoring installer publication belongs in this phase or its own slice — and this phase may not claim "updater behavior preserved" while it stands. See `01-CONTEXT.md` `<updater_regression>`.

Cross-cutting constraints: preserve existing user data, existing processing behavior, and beta-6 updater behavior; do not weaken the AD-19 signed-manifest repair contract or the AD-18 ASCII native-staging boundary; do not use a splash screen to conceal an unresolved startup delay; keep the setup checklist in the existing WebEngine UI vocabulary.

Canonical references: `.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md`, `.planning/milestones/v0.9.0-beta.6/README.md`, `.planning/milestones/v0.9.0-beta.6/MILESTONE-CONTEXT.md`, `docs/DECISIONS.md` (AD-18, AD-19), `BUG_LIST.md`.

**Approval/evidence gate**: Measured size table (before/after, per contributor); measured cold and warm launch times on a clean profile; packaged runtime smoke passing after the size cuts; single-instance and first-run-routing tests; one packaged clean-profile launch with the icon visible.

**UI hint**: yes

### Phase 2: Real Lecture Import & Processing

**Goal**: Fix normal lecture importing and processing so that local videos and URL imports reliably use the bundled transcription runtime, jobs persist through their full lifecycle, and all three output modes complete successfully. Demo processing already works — the gap is between demo and normal import paths.

**Depends on**: Phase 1 (packaged build with correct runtime bundling and setup checklist)

**Reported Behavior** (what a user sees today on a clean install with beta-6):

  1. Paste Link / yt-dlp path is missing or disconnected.
  2. Thumbnail is not generated after adding a local video.
  3. Study Pack and Transcript Only report Whisper executable or model not configured, even though Settings shows `ggml-base.en.bin`.
  4. Slides Only processes, but transcription modes fail.
  5. Imported lecture disappears from Recent/Active jobs.
  6. Top-left indicator says Idle; clicking it opens an empty processing timeline.
  7. Source says "No lecture loaded" after a lecture was added.
  8. Demo processing succeeds despite normal transcription failing.
  9. Output mode and slide-sensitivity controls shown during processing — unclear if they affect the running job.

**Success Criteria** (what must be TRUE):

  1. Demo still works.
  2. A normal local video remains loaded in Source after import.
  3. Its job remains visible in Recent/Active throughout queued, processing, failed, and completed states.
  4. Transcript Only completes on a normal local video.
  5. Slides Only completes on a normal local video.
  6. Study Pack completes on a normal local video.
  7. Settings and the processing controller agree on the same Whisper executable and model paths, resolved from one shared runtime-resolution result.
  8. A thumbnail appears after a valid local video is accepted; failure to generate a thumbnail does not remove the job.
  9. The top-left indicator opens the correct job timeline.
  10. Paste Link creates a normal persisted job for one supported URL, with a clear error on failure instead of silent no-op.
  11. Pre-processing options (output mode, slide sensitivity) appear before processing unless they genuinely support live adjustment; selected values are locked into the job at start.

**Work Items**:

  1. Reproduce using the packaged beta-6 app and a normal local video.
  2. Trace demo import vs normal import from source selection through job creation, config resolution, processing, and view updates. State the confirmed root cause.
  3. Unify runtime resolution: Setup, Settings, job preflight, and the processing controller use one shared result. Verify runnable paths for ffmpeg, ffprobe, whisper-cli, required DLLs, and ggml-base.en.bin.
  4. Fix job lifecycle: keep imported lecture in Source, create and persist job before navigating to Processing, keep job visible in Recent/Active, make top-left indicator reflect actual job.
  5. Fix thumbnail generation after local video import.
  6. Reconnect or implement Paste Link / yt-dlp URL import with clear error handling.
  7. Verify all three output modes complete.
  8. Resolve pre-processing settings timing (lock at start vs live adjustment).
  9. Preserve failed jobs and their errors.

**Testing**:

  - Focused regression tests for the confirmed config mismatch, job persistence, source state, and thumbnail trigger.
  - One real packaged video for acceptance testing.
  - Full existing test suite run at phase completion.

Cross-cutting constraints: preserve existing user data; do not break demo processing; do not weaken the AD-19 signed-manifest repair contract or AD-18 ASCII staging boundary; maintain the runtime bundling from Phase 1.

Canonical references: `app/desktop/engine_adapter.py`, `app/desktop/bridge.py`, `app/ui/app.js`, `lecturepack/infrastructure/runtime_inventory.py`, `lecturepack/services/first_run_checklist.py`, `BUG_LIST.md`.

**Plans:** 3 plans

Plans:
**Wave 1**

- [ ] 02-01-PLAN.md — Runtime path auto-population: seed exe paths via persist_runtime_health, fix start_processing gate to use EngineRegistry.resolve, fix _kick_poster ordering (SC-01, SC-04, SC-05, SC-06, SC-07, SC-08)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 02-02-PLAN.md — Job lifecycle verification: regression tests for normal-import lifecycle, Source retention, active job indicator, failed job persistence (SC-02, SC-03, SC-09)
- [ ] 02-03-PLAN.md — Settings lock + Paste Link: lock slide sensitivity during normal processing, verify Paste Link end-to-end wiring (SC-10, SC-11)

**Approval/evidence gate**: All three output modes completing on a real local video in the packaged build; job lifecycle visible throughout; demo still passing; Paste Link creating a persisted job.

**UI hint**: yes

## Progress

**Execution Order:** Phase 1 → Phase 2.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Clean-Device Footprint & First Launch | 8/8 | In Progress |  |
| 2. Real Lecture Import & Processing | 0/3 | Not Started |  |
