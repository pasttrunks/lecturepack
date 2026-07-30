---
phase: 04
plan: 02
subsystem: desktop-ui
tags: [accessibility, responsive, guided-tour, reliability, pytest]
status: complete
requires: [04-01]
provides: [model-tooltip, compact-viewport-access, coalesced-tour-geometry, scoped-tour-focus]
affects: [app/ui/index.html, app/ui/app.css, app/ui/app.js]
tech-stack:
  added: []
  patterns: [ARIA-tooltip, requestAnimationFrame-geometry, CSS-spotlight, scoped-focus]
---

# Phase 04 Plan 02: Visual Artifact Reliability Summary

Long model names now stay ellipsized while exposing their exact inert value through a viewport-clamped ARIA tooltip, and the real guided-tour controls retain reliable geometry and focus through compact, scrolling, resized, and DPI-changed layouts.

## Completed Tasks

1. Added hover/focus model-value disclosure with `textContent`, ARIA linkage, safe empty-value handling, and responsive vertical-access rules without changing the committed 480x560 desktop minimum.
2. Added one rAF-coalesced tour geometry scheduler with minimal target reveal, post-scroll measurement, viewport clamping, visual-viewport listeners, and a tour-only focus set that keeps Exit reachable.
3. Preserved the pre-existing generic overlay Tab trap before applying the more restricted guided-tour policy so existing modal behavior remains compatible.

## Verification

- Task 1 focused suite: `51 passed in 0.85s` — `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py`
- Task 2 focused suite: `53 passed in 1.06s` plus `node --check app/ui/app.js`.
- Compatibility follow-up: `69 passed in 1.15s` — the focused suite plus `tests/test_webview_ui_fixes.py`.
- Full suite: `850 passed, 3 failed, 1 warning in 207.04s`. Two failures are the known missing `LECTUREPACK_ONEDIR_FIXTURE` packaged-runtime gates; the third exposed an existing overlay Tab-trap assertion and was fixed in `eed01e2`.

## Decisions Made

- Reused the existing CSS spotlight and real-control interaction model; no SVG mask, synthetic hit layer, dependency, or visual-system replacement was introduced.
- Kept geometry writes coalesced in a single animation frame and used `scrollIntoView({block: 'nearest', inline: 'nearest'})` only when the real target is outside the viewport.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored existing generic overlay Tab trapping alongside scoped tour focus**
- **Found during:** Full-suite verification after Task 2.
- **Issue:** The tour-specific focus handler changed the static generic overlay trap shape verified by `tests/test_webview_ui_fixes.py`.
- **Fix:** Run the established generic trap first, then apply the narrower tour target/card focus set while the tour is active.
- **Files modified:** `app/ui/app.js`
- **Commit:** `eed01e2`

## Known Stubs

None in the files changed by this plan.

## Self-Check: PASSED

- Task commits `3ad6020`, `d5a7658`, and `eed01e2` exist.
- All created/modified plan files exist; `app/desktop/main.py` was not staged or modified by this plan.
- The user-owned DLL-directory bootstrap hunk remains unstaged.
