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
4. Added `Backend.start_demo_job`/`end_demo_job` and a separate real `JobController` configured only against the demo workspace, with JSON-safe operation/session lifecycle events. Demo start is rejected while the normal controller is busy; controller/session-scoped forwarding ignores stale or cross-controller events and restores the prior selected job after cleanup. Successful processing now remains active at an identity-bearing `review_ready` action boundary and projects the real Review/Study payloads; only explicit exit, application exit, cancellation, or failure cleans the workspace.
5. Demo jobs explicitly persist the approved local settings before the controller runs: `whispercpp-cpu`, bundled `ggml-base.en.bin`, `fast` profile, and local Whisper backend. The authoritative PyInstaller spec validates and collects the approved local `models/ggml-base.en.bin` input under frozen `models/`; the ignored model binary itself is not committed.
6. The guided demo rejects export execution with a clear lifecycle event, ensuring no demo-owned `ExportWorker` can race explicit cleanup while the Export surface remains reachable. The authoritative package spec also validates and includes the source-derived `polar_bears_thumbnail.jpg` beside the MP4.
7. Created `tests/test_demo_session_isolation.py` verifying the bundled ~10-second A/V asset, package data seam and frozen model lookup, isolated real-controller invocation, persistent profile byte stability, review-ready retention/projection, explicit/app-exit/failure cleanup, export teardown safety, idempotency, cleanup protections, normal/demo signal separation, and real `JobController` request construction.
8. Added a process-local, thread-safe demo asset registration seam so `lpasset://job` and `lpasset://thumb` can resolve review frames from only the exact sentinel-owned `%TEMP%\LecturePack\demo_<session>\jobs\<job>` root. Registration validates session/job manifests and rejects traversal, outside roots, and reparse points; cleanup unregisters before deleting files.
9. Study payloads now include the source-derived deterministic transcript `summary` and `summarySource`, replacing prototype overview copy with real lecture content.
