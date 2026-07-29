---
phase: 04
plan: 01
subsystem: desktop-ui
tags: [theme, navigation, reliability, pytest]
status: complete
requires: []
provides: [atomic-theme-bootstrap, idempotent-navigation]
affects: [app/desktop/main.py, app/desktop/bridge.py, app/ui/app.js]
---

# Phase 04 Plan 01: Visual Artifact Reliability Summary

Fresh profiles now start from Light theme state without bootstrap persistence echoes, and active navigation no longer replays the established screen entrance.

## Completed Tasks

1. Implemented Light/default theme ownership across the bridge, initial DOM, and idempotent JavaScript application path.
2. Added an active-screen guard around navigation motion and regression assertions for preserved motion/press tokens.
3. Lowered the desktop minimum size to support the Phase 4 compact viewport matrix while preserving the user's unrelated DLL bootstrap hunk unstaged.

## Verification

- Focused suite: `47 passed in 0.74s`.
- Full suite: exceeded the 124-second command timeout with no captured pytest result; this remains follow-up verification for the orchestrator.

## Deviations from Plan

- [Rule 3 - Blocking issue] The compact viewport requirement needed a one-line `main.py` minimum-size change. It was selectively staged as a separate passing commit because the same file contained a user-owned, unrelated DLL-directory bootstrap hunk.
- The full-suite command exceeded the execution timeout; no test failures were reported before timeout, but it cannot be claimed green.

## Key Files

- `app/desktop/bridge.py` — Light fallback for canonical bootstrap payload.
- `app/ui/app.js` — non-persisting bootstrap/settings application and active-screen guard.
- `app/ui/index.html` — Light initial root and matching settings selection.
- `tests/test_webview_theme.py` — bootstrap and idempotency coverage.
- `tests/test_ui_tokens_motion_responsive.py` — navigation and compact-viewport coverage.

## Self-Check: PASSED

- Task commits `644e9a0`, `73c0787`, `45cd202`, and `8e6b64f` exist.
- The user-owned DLL bootstrap remains unstaged in `app/desktop/main.py`.
