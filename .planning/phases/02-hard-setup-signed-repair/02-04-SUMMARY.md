---
phase: 02-hard-setup-signed-repair
plan: 04
subsystem: ui
tags: [runtime-setup, signed-repair, webengine, accessibility, bridge]
requires:
  - phase: 02-hard-setup-signed-repair
    provides: operation-bound repair events and authenticated metadata offers
provides:
  - non-dismissible runtime setup and repair overlay
  - consent-bound UI repair controls and repair event subscription
  - admitted-only normal entry with modal input containment
affects: [packaged-ui-validation, phase-02-05]
tech-stack:
  added: []
  patterns: [authenticated-offer-before-confirmation, active-operation event filtering, inert modal containment]
key-files:
  created: [tests/test_setup_gate_repair.py]
  modified: [app/ui/index.html, app/ui/app.js, app/ui/bridge.js]
key-decisions:
  - "The UI formats only the backend-authenticated four-archive byte total and never estimates download size."
  - "Normal UI bridge activity begins only after the canonical bootstrap result is not SETUP_REQUIRED."
patterns-established:
  - "Runtime setup uses the existing lp-scrim, lp-pop, lp-press, lp-fill, LP.motion, and focus helpers."
  - "Repair events are accepted only for the current operation and only until one terminal result."
requirements-completed: [REPR-01, REPR-02, REPR-03, REPR-08, REPR-09, REPR-10]
coverage:
  - id: D1
    description: "Semantic runtime setup overlay exposes every locked state, one scaleX progressbar, responsive layout, and beta-5 interaction primitives."
    requirement: REPR-01
    verification:
      - kind: automated_ui
        ref: "python -m pytest tests/test_setup_gate_repair.py -q"
        status: pass
    human_judgment: true
    rationale: "Packaged visual preservation across both themes, DPI, and reduced motion requires manual inspection."
  - id: D2
    description: "Repair metadata and commands are consent-bound through exact bridge slots, while stale events and background input are contained."
    requirement: REPR-03
    verification:
      - kind: integration
        ref: "python -m pytest tests/test_setup_gate_repair.py tests/test_media_link_adapter.py -q"
        status: pass
    human_judgment: false
metrics:
  duration: 6min
  completed: 2026-07-28
status: complete
---

# Phase 02 Plan 04: Runtime Setup Gate Summary

**A beta-5-style blocking runtime-repair overlay that consumes authenticated offers, rejects stale repair events, and releases normal entry only after admitted health.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-28T15:38:28-04:00
- **Completed:** 2026-07-28T15:44:01-04:00
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added the full-viewport, non-dismissible setup overlay with all seven locked states, a single compositor progress bar, diagnostics disclosure, accessible live regions, and responsive action behavior.
- Registered `repair_event` and exposed narrow wrappers for exact metadata-offer, confirmation, cancellation, assessment, and diagnostics bridge slots.
- Added a single runtime gate controller that filters stale/terminal events, keeps the underlying app inert, traps keyboard/pointer/scroll input, and delays normal bridge activity until canonical admission permits it.

## Task Commits

1. **Task 1: Add semantic beta-5 setup overlay structure and bridge event surface** — `88dba0f` (test), `11e0094` (feat)
2. **Task 2: Implement deterministic gate reducer, input containment, and repair transitions** — `97f5aca` (feat)

## Files Created/Modified

- `app/ui/index.html` — semantic setup gate panels, actions, live regions, disclosure, and responsive overlay styling.
- `app/ui/app.js` — `RuntimeSetupGate` reducer, bootstrap gating, input containment, authenticated-offer rendering, and repair-event handling.
- `app/ui/bridge.js` — `repair_event` registration and narrow repair command wrappers.
- `tests/test_setup_gate_repair.py` — DOM, bridge, authenticated-offer, progress, and containment contract coverage.

## Decisions Made

- Reused the established beta-5 overlay, button, focus, motion, and fill primitives instead of creating a second visual or focus system.
- The confirmation view enables only when the bridge supplies a matching authenticated offer with valid version, source, affected components, and checked byte total.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Matched the UI offer adapter to the Phase 02-03 repair-event payload.**
- **Found during:** Task 2
- **Issue:** The worker sends `official_source`, an affected-components array, and the checked numeric byte total; treating those as already formatted strings left confirmation disabled for valid offers.
- **Fix:** Adapted those fields only for safe display, preserving the backend-authenticated byte total without recomputing or estimating it.
- **Files modified:** `app/ui/app.js`
- **Verification:** `python -m pytest tests/test_setup_gate_repair.py tests/test_media_link_adapter.py -q` — 26 passed.
- **Committed in:** `97f5aca`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** Required for valid authenticated offers to reach explicit confirmation; no scope expansion.

## Issues Encountered

- The full suite requires a physical clean packaged runtime fixture. With `LECTUREPACK_ONEDIR_FIXTURE` unset, its single packaged-smoke test fails as expected; this is the known prerequisite, not a UI regression.

## Audit Follow-up

- Corrected idempotent inert snapshot/restore behavior across every gate transition, including bootstrap-pending input blocking and canonical healthy release.
- Focus now targets the required state control rather than the persistent Exit header; diagnostics Back restores its invoking control.
- Failed events classified offline now enter the restricted offline state with assertive announcement; admitted remains polite.
- Copy/save diagnostics now parse bridge responses and announce failure without closing diagnostics.
- Added an executable Node reducer seam test alongside focused assertions for lifecycle, focus, input guard, long-label, and accessibility contracts.

**Audit correction commit:** `bb986c1`.

**Final re-audit correction:** `ce5f3d9` makes the shared runtime-gate reducer execute offer/confirm/cancel/offline/failure/diagnostics/back/admitted/retry transitions in Node coverage, uses assertive admitted announcements, and restores the captured pre-gate focus after healthy entry.

## Known Stubs

None.

## User Setup Required

Set `LECTUREPACK_ONEDIR_FIXTURE` to a verified clean packaged runtime to run the packaged smoke test.

## Next Phase Readiness

The desktop repair protocol now has its gated UI consumer. Plan 02-05 can gather the required packaged visual and clean-machine evidence.

## Self-Check: PASSED

- Runtime setup UI files and `tests/test_setup_gate_repair.py` exist.
- Task commits `88dba0f`, `11e0094`, and `97f5aca` exist in git history.
- Focused verification passed: `3 passed` for the setup-gate suite and `23 passed` for the bridge signal regression.
- Audit-focused verification passed: `56 passed` across setup-gate, bridge, responsive/motion, and theme suites.
- Final reducer sequence passed: `gate → confirm → repairing → cancel → gate → offline → failed → diagnostics/back → ready`, including stale/duplicate-terminal suppression and retry-pending state.
- Full verification reached `790 passed, 1 failed`; the sole failure is the documented unset `LECTUREPACK_ONEDIR_FIXTURE` prerequisite.

---
*Phase: 02-hard-setup-signed-repair*
*Completed: 2026-07-28*
