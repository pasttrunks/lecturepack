---
phase: 03-empty-launch-guided-demo
plan: 01
subsystem: desktop
tags: [empty-home, active-job, library-isolation]
requires:
  - phase: 03-empty-launch-guided-demo
    provides: empty Home startup and library session isolation
provides:
  - empty Home boot initialization
  - active_job signal payload contract ({id: "", title: ""})
  - session-scoped library persistence filtering
affects: [phase-03-02, phase-03-03]
key-files:
  created: [tests/test_empty_home.py]
  modified: [app/desktop/engine_adapter.py]
requirements-completed: [HOME-01, HOME-02, HOME-03]
metrics:
  duration: 5min
  completed: 2026-07-28
status: complete
---

# Phase 03 Plan 01 Summary

Plan 03-01 delivers empty Home boot startup (`HOME-01`), explicit library job opening (`HOME-02`), and session-scoped job filtering (`HOME-03`).

## Accomplishments
1. Updated `on_ui_ready` in `app/desktop/engine_adapter.py` to initialize `active_job` with empty payload `{"id": "", "title": ""}` so healthy launches start on an empty Home screen.
2. Verified that jobs flagged with `session_scoped: true` are excluded from persistent library payloads while normal existing jobs remain visible and require explicit selection.
3. Created `tests/test_empty_home.py` validating empty boot, existing-job visibility, and session isolation.
