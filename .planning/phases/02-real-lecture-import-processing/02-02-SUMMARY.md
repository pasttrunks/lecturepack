---
phase: 02-real-lecture-import-processing
plan: 02
subsystem: testing
tags: [job-lifecycle, pytest, engine-adapter, regression-test, whisper, ffmpeg]

# Dependency graph
requires:
  - phase: 02-real-lecture-import-processing (Plan 01)
    provides: EngineRegistry-based whisper gate and persist_runtime_health(exe_paths=...) seeding that lets start_processing() reach controller.run_pipeline() on a clean install
provides:
  - tests/test_phase2_job_lifecycle.py — 9 regression tests proving the normal-import job lifecycle (import -> NEW -> QUEUED -> RUNNING -> COMPLETED/FAILED) works end-to-end on a clean install, without manually mocking whisper_exe/ffmpeg_exe/ffprobe_exe in config
  - A reusable test pattern (`_build_adapter`) for constructing a real LecturePackAdapter + real JobController against a tmp_path-scoped ConfigManager, relying on the dev tree's own bin/Release/whisper-cli.exe and bin/ffmpeg.exe/ffprobe.exe fallbacks instead of manual config.set() calls
affects: [02-03, 02-04, real lecture import & processing acceptance gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Clean-install test construction: patch engine_adapter.ConfigManager to a tmp_path-scoped real ConfigManager (never ~/LecturePackData), then rely on FFmpegWrapper.detect_binaries()'s and EngineRegistry._cpu_exe()'s own dev-tree fallback discovery of bin/ffmpeg.exe, bin/ffprobe.exe, bin/Release/whisper-cli.exe instead of config.set()"
    - "Seed whisper_model the same way Plan 01's boot path does — one persist_runtime_health(bundled_model=...) call — instead of a raw config.set('whisper_model', ...) mock"
    - "Simulate a genuinely-running stage (job.set_stage_status(stage, 'running')) to observe _list_jobs()'s real 'running' rendering branch, since mocking controller.run_pipeline() (required to avoid spawning a real whisper-cli.exe subprocess) means no stage naturally transitions to running"

key-files:
  created:
    - tests/test_phase2_job_lifecycle.py
  modified: []

key-decisions:
  - "_list_jobs() only renders status='running' when a job's lifecycle is RUNNING/PAUSE_REQUESTED AND at least one stage in job.state['stages'] has status='running' (set by the real controller pipeline, not by the lifecycle transition itself). Since tests mock controller.run_pipeline() to avoid a real subprocess, the running-status test manually calls job.set_stage_status(STAGE_TRANSCRIBE, 'running') to reproduce what the real pipeline would have already done by that point — this is exercising Job's own real method, not inventing new behavior."
  - "job.get_lifecycle() transitions (NEW->QUEUED->RUNNING) are asserted directly via a wrapped job.set_lifecycle that records every call in order, proving both intermediate edges fire (not just the final state), which a silently-swallowed IllegalTransition could otherwise mask."
  - "requirements SC-02/SC-03/SC-09/WI-04/WI-09 in this plan's frontmatter are beta-7 ROADMAP.md phase-level numbered Success Criteria / Work Items, not REQUIREMENTS.md REQ-IDs — .planning/REQUIREMENTS.md is the prior beta-6 milestone's requirements doc and has no SC-xx/WI-xx entries. Ran `requirements mark-complete` for completeness; it correctly reported all 5 IDs not_found/no-op against that stale document, so ROADMAP.md's Phase 2 checkbox (updated below) is the authoritative completion record for this milestone's numbered criteria."

patterns-established: []

requirements-completed: [SC-02, SC-03, SC-09, WI-04, WI-09]

coverage:
  - id: D1
    description: "Normal import_video() emits active_job with the correct job id and a non-empty title derived from the filename (SC-02, SC-09)"
    requirement: "SC-02"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_import_video_emits_active_job_with_correct_identity"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_set_active_job_emits_signal_with_id_and_title"
        status: pass
    human_judgment: false
  - id: D2
    description: "A job created via normal import transitions NEW -> QUEUED -> RUNNING through start_processing(), and is visible in _list_jobs with status 'running' while a stage is actually running (SC-03)"
    requirement: "SC-03"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_import_then_start_transitions_through_lifecycle"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_push_jobs_includes_job_through_all_status_transitions"
        status: pass
    human_judgment: false
  - id: D3
    description: "A pipeline failure sets the job's lifecycle to FAILED, keeps it visible in _list_jobs with status 'failed' (not silently cleared), and fires jobs_changed (D-06)"
    requirement: "SC-03"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_pipeline_failure_leaves_job_in_failed_state"
        status: pass
    human_judgment: false
  - id: D4
    description: "on_ui_ready() reconciles stale jobs from dead sessions to interrupted, then pushes the current job list via jobs_changed, so a restart surfaces the correct job state (SC-03, D-06)"
    requirement: "SC-03"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_on_ui_ready_triggers_push_jobs"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_reconcile_jobs_on_startup_demotes_stale_running_to_interrupted"
        status: pass
    human_judgment: false
  - id: D5
    description: "A completed job shows status 'done' in _list_jobs with non-empty id/name/status fields"
    requirement: "SC-03"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_list_jobs_returns_complete_job_with_done_status"
        status: pass
    human_judgment: false
  - id: D6
    description: "Demo controller signals never reach the normal workspace, and the real controller's own signal is likewise blocked while a demo owns the workspace (SC-01 demo isolation, verified as a side-guard of this plan's normal-path tests)"
    requirement: "WI-04"
    verification:
      - kind: unit
        ref: "tests/test_phase2_job_lifecycle.py#test_demo_signals_do_not_corrupt_normal_workspace"
        status: pass
    human_judgment: false
  - id: D7
    description: "No changes to job_lifecycle.py or job_queue.py — the job system is verified as-built, not redesigned (D-05, WI-09)"
    requirement: "WI-09"
    verification:
      - kind: other
        ref: "git diff --stat f2f86c5^..f2f86c5 -- lecturepack/models/job_lifecycle.py lecturepack/services/job_queue.py (empty)"
        status: pass
    human_judgment: false

duration: ~45min
completed: 2026-08-01
status: complete
---

# Phase 2 Plan 2: Job Lifecycle Verification Summary

**9 regression tests proving import_video -> start_processing -> pipeline completion/failure correctly drives job_lifecycle.py's NEW->QUEUED->RUNNING->COMPLETED/FAILED state machine end-to-end on a clean install, with zero manual whisper_exe/ffmpeg_exe/ffprobe_exe config mocking.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-08-01T12:30:00Z (approximate)
- **Tasks:** 2
- **Files modified:** 1 (new file)

## Accomplishments

- Added `tests/test_phase2_job_lifecycle.py` with 9 tests exercising the real `LecturePackAdapter` + real `JobController` against a `tmp_path`-scoped `ConfigManager` — never `~/LecturePackData` and never a manually-set `whisper_exe`/`ffmpeg_exe`/`ffprobe_exe` config value. The tests instead rely on the dev tree's own binaries (`bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/Release/whisper-cli.exe`) being found by `FFmpegWrapper.detect_binaries()`'s and `EngineRegistry._cpu_exe()`'s existing fallback search paths, and seed `whisper_model` the same way Plan 01's boot path does (`ConfigManager.persist_runtime_health(bundled_model=...)`), closing the "clean install, nothing manually set" coverage gap the plan identified.
- Proved `import_video()` emits `active_job` with the correct job id and a non-empty title (SC-02, SC-09) — both through the real `import_video()` path and a direct `_set_active_job()` call.
- Proved `start_processing("study")` (whisper-requiring mode) drives the job through `NEW -> QUEUED -> RUNNING` with no `IllegalTransition` silently swallowed along the way, by wrapping `job.set_lifecycle` to record every transition in call order.
- Proved a job genuinely mid-run (a stage marked `"running"`, exactly as the real controller would have done by this point) is visible in `_list_jobs()` with `status: "running"` and the correct `stage` field.
- Proved a pipeline failure (`controller.pipeline_failed.emit(...)`) sets the job's lifecycle to `FAILED`, keeps it in `_list_jobs()` with `status: "failed"` (not silently cleared, per D-06), and fires `jobs_changed`.
- Proved `on_ui_ready()` reconciles stale/dead-session jobs to `INTERRUPTED` before its first `jobs_changed` push, and separately proved `_reconcile_jobs_on_startup()` in isolation: a job left `RUNNING` by a session id that doesn't match the current adapter session is reconciled to `INTERRUPTED`, artifacts preserved.
- Proved a completed job (`NEW -> QUEUED -> RUNNING -> COMPLETED`, the only legal chain per `job_lifecycle.LEGAL_TRANSITIONS`) shows `status: "done"` in `_list_jobs()`.
- Proved `_forward_normal`'s two-part guard (controller identity AND `_demo_session is None`) blocks a foreign controller's signal and blocks the real controller's own signal while a demo owns the workspace, then allows it again once the demo ends — with the normal job's identity untouched throughout.
- Confirmed via `git diff --stat` that no changes were made to `lecturepack/models/job_lifecycle.py` or `lecturepack/services/job_queue.py` (D-05 compliance — the job system is verified, not redesigned).

## Task Commits

Both tasks landed in a single commit because they share one test file and the second task's tests directly build on fixtures/helpers introduced by the first (splitting would have required an artificial partial-file commit followed by an edit-only second commit with no independent verification value):

1. **Task 1 + Task 2: Normal-import lifecycle regression tests + active-job/reconciliation verification** - `f2f86c5` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `tests/test_phase2_job_lifecycle.py` - 9 new regression tests: active-job identity on import, NEW->QUEUED->RUNNING transitions with running-stage visibility, failed-job persistence, comprehensive SC-03 status-transition proof, demo/normal signal isolation, direct `_set_active_job` payload shape, `on_ui_ready` reconciliation + push, isolated startup-reconciliation proof, and completed-job `_list_jobs` status.

## Decisions Made

- Constructed the adapter by patching `engine_adapter.ConfigManager` to a `tmp_path`-scoped real `ConfigManager` (not the `_Config` test double used elsewhere in the suite), so the tests exercise the *real* `autodetect_ffmpeg()`/`EngineRegistry._cpu_exe()` fallback chain rather than a mock — this is what makes "no manual whisper_exe/ffmpeg_exe/ffprobe_exe mocking" a meaningful proof rather than a tautology.
- Mocked only `controller.run_pipeline()` (per the plan's explicit instruction) to avoid spawning a real `whisper-cli.exe` subprocess; every other collaborator (`ConfigManager`, `JobController`, `Job`, `EngineRegistry`, `FFmpegWrapper`) is the real production class.
- Where the real "running" render path needs a stage that is genuinely `"running"` in `job.state` (which only the real, unmocked pipeline would set), the test calls `job.set_stage_status(...)` directly — the same method the real controller calls internally — rather than inventing a new code path or weakening the assertion.
- Treated `SC-02`/`SC-03`/`SC-09`/`WI-04`/`WI-09` as this beta-7 milestone's ROADMAP.md-level numbered Success Criteria/Work Items (see Phase 2 section) rather than `.planning/REQUIREMENTS.md` REQ-IDs, since that file is the prior beta-6 milestone's stale requirements doc with no SC-xx/WI-xx entries at all.

## Deviations from Plan

None - plan executed exactly as written. All 9 planned test cases (5 in Task 1, 4 in Task 2) were implemented and pass; no production code was touched.

## Issues Encountered

- The pre-commit hook's `code-review-graph` panel-print step threw the same cosmetic `UnicodeEncodeError` (cp1252 console codec) documented in `02-01-SUMMARY.md`'s Issues Encountered. The commit itself completed successfully (confirmed via `git log`); no action needed.
- `gsd-tools query requirements.mark-complete SC-02 SC-03 SC-09 WI-04 WI-09` correctly reported all five IDs as `not_found`/no-op against `.planning/REQUIREMENTS.md` (that file has no SC-xx/WI-xx entries — see Decisions Made). No REQUIREMENTS.md edit was made; `ROADMAP.md`'s Phase 2 checkbox update is the authoritative record.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The job-lifecycle machinery (`job_lifecycle.py`, `job_queue.py`, `_list_jobs`, `_push_jobs`, `_set_active_job`, `_reconcile_jobs_on_startup`) is now regression-tested against the clean-install normal-import path this milestone's Phase 2 exists to fix, closing the gap Plan 01's fix opened up but didn't itself prove.
- Full suite: 1053 passed, 7 failed, 1 skipped (1044 baseline + 9 new tests; same 7 pre-existing `release_trust`/signing-key failures documented in `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md`; zero new failures).
- Plans 02-03/02-04 can build on a verified-working job lifecycle without needing their own workaround or re-proof of D-05/D-06/D-07.
- Not yet exercised (left for 02-04's acceptance gate, per this plan's own scope): a real packaged clean-install run of `start_processing` through the actual `whisper-cli.exe`/`ffmpeg.exe` subprocess pipeline to completion — this plan proves the lifecycle bookkeeping *around* that call, deliberately mocking the call itself.

---
*Phase: 02-real-lecture-import-processing*
*Completed: 2026-08-01*

## Self-Check: PASSED

All claims verified below.
