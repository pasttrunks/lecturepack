---
phase: 03-empty-launch-guided-demo
plan: 02
subsystem: desktop
tags: [demo-asset, session-isolation, temp-sweep]
requires:
  - phase: 03-empty-launch-guided-demo
    provides: demo session isolation and temporary folder sweep
provides:
  - rights-clear synthetic demo video asset (`app/assets/demo/demo_lecture.mp4`)
  - isolated demo session temp directory manager (`create_demo_session_dir`)
  - idempotent demo session cleanup sweep (`sweep_demo_sessions`)
affects: [phase-03-03]
key-files:
  created: [app/assets/demo/demo_lecture.mp4, tests/test_demo_session_isolation.py]
  modified: [app/desktop/paths.py]
requirements-completed: [DEMO-05, DEMO-07, DEMO-08]
metrics:
  duration: 5min
  completed: 2026-07-28
status: complete
---

# Phase 03 Plan 02 Summary

Plan 03-02 delivers the synthetic demo media asset (`DEMO-05`), isolated temp workspace manager (`DEMO-07`), and idempotent cleanup sweep (`DEMO-08`).

## Accomplishments
1. Packaged rights-clear synthetic demo video under `app/assets/demo/demo_lecture.mp4`.
2. Created sentinel-owned `create_demo_session_dir` in `app/desktop/paths.py` to route demo execution into `%TEMP%\LecturePack\demo_<session_id>` without following traversal, links, or reparse points.
3. Implemented validated, idempotent cleanup for startup sweep and demo terminal paths; foreign and malformed `demo_*` entries are left untouched.
4. Added `Backend.start_demo_job`/`end_demo_job` and a separate real `JobController` configured only against the demo workspace, with JSON-safe operation/session lifecycle events. Demo start is rejected while the normal controller is busy; controller/session-scoped forwarding ignores stale or cross-controller events and restores the prior selected job after cleanup.
5. Demo jobs explicitly persist the approved local settings before the controller runs: `whispercpp-cpu`, bundled `ggml-base.en.bin`, `fast` profile, and local Whisper backend.
6. Created `tests/test_demo_session_isolation.py` verifying the bundled ~10-second A/V asset and package manifest, isolated real-controller invocation, persistent profile byte stability, terminal cleanup, idempotency, cleanup protections, normal/demo signal separation, and real `JobController` request construction.
