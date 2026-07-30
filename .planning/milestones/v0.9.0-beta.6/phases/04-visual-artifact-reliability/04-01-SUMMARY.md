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

Fresh profiles now start from Light theme state without bootstrap persistence echoes, saved themes are injected before the first visible window frame, and active navigation no longer replays the established screen entrance.

## Completed Tasks

1. Implemented Light/default theme ownership across the bridge, initial DOM, and idempotent JavaScript application path.
2. Added an active-screen guard around navigation motion and regression assertions for preserved motion/press tokens.
3. Added desktop load/readiness ownership so the sanitized saved theme is installed before the first `show()`, including a safe page-load failure fallback.
4. Lowered the desktop minimum size to support the Phase 4 compact viewport matrix while preserving the user's unrelated DLL bootstrap hunk unstaged.

## Verification

- Focused suite after the readiness correction: `48 passed in 0.74s`.
- Python compile gate: `python -m py_compile app/desktop/main.py app/desktop/bridge.py` passed.
- Full suite: `846 passed, 2 failed, 1 warning in 195.71s`; both failures require the absent external `LECTUREPACK_ONEDIR_FIXTURE` and are package-fixture gates, not Phase 4 regressions.

## Deviations from Plan

- [Rule 3 - Blocking issue] The compact viewport requirement needed a one-line `main.py` minimum-size change. It was selectively staged as a separate passing commit because the same file contained a user-owned, unrelated DLL-directory bootstrap hunk.
- The first readiness commit (`ab90555`) mispositioned methods while partially staging around a user-owned hunk. Corrective commit `fa107ee` restores valid placement; compile and focused tests pass. The malformed intermediate commit remains visible in history but is fully superseded.
- The full suite's only failures are the two expected packaged-fixture tests when `LECTUREPACK_ONEDIR_FIXTURE` is unset; Plan 04 retains the physical package gate.

## Key Files

- `app/desktop/bridge.py` — Light fallback for canonical bootstrap payload.
- `app/ui/app.js` — non-persisting bootstrap/settings application and active-screen guard.
- `app/ui/index.html` — Light initial root and matching settings selection.
- `tests/test_webview_theme.py` — bootstrap and idempotency coverage.
- `tests/test_ui_tokens_motion_responsive.py` — navigation and compact-viewport coverage.

## Self-Check: PASSED

- Task commits `644e9a0`, `73c0787`, `45cd202`, `8e6b64f`, `ab90555`, and corrective commit `fa107ee` exist.
- The user-owned DLL bootstrap remains unstaged in `app/desktop/main.py`.
- The focused suite passes all 48 tests and both changed Python modules compile.
