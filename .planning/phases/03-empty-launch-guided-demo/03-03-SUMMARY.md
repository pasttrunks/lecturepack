---
phase: 03-empty-launch-guided-demo
plan: 03
subsystem: ui
tags: [guided-tour, onboarding, css-spotlight, settings-replay, real-demo-events]
requires:
  - phase: 03-empty-launch-guided-demo
    provides: guided tour overlay, step navigation, and Settings replay
provides:
  - pointer-transparent CSS spotlight (`#tour-spotlight-box`) with no SVG mask
  - 4-step user-controlled guided onboarding tour state machine
  - real isolated demo card bound to identity-bearing backend lifecycle events
  - persistent Exit demo action, keyboard controls, and Settings replay
affects: [phase-04-visual-reliability]
key-files:
  created: [tests/test_guided_tour.py]
  modified: [app/ui/index.html, app/ui/app.css, app/ui/app.js, app/ui/bridge.js]
requirements-completed: [DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-06]
metrics:
  completed: 2026-07-29
status: implementation-complete-awaiting-phase-verification
---

# Phase 03 Plan 03 Summary

Plan 03-03 delivers the Phase 3 frontend: a CSS-only guided spotlight, concise user-controlled four-step tour, Settings replay, and the Home card for the backend-owned isolated demo lifecycle. It does not claim packaged Qt click-through or Phase 3 UAT; those remain phase-level verification gates.

## Accomplishments
1. Added `#guided-tour-overlay` and `#tour-spotlight-box`. The layer and spotlight both use `pointer-events:none`; the only interactive surface is the compact control card. The visual cutout is a CSS border plus oversized box-shadow, avoiding the QtWebEngine SVG-mask hit-test failure.
2. Implemented the exact four main-app steps: import, process, review, and export. Navigation is user-controlled with Back/Next and ArrowLeft/ArrowRight, while inputs/selects/textareas retain their normal arrow-key behavior.
3. Added an always-visible **Exit demo** action during the tour, a first-healthy-launch non-blocking **Take guided tour** / **Skip to app** prompt, and the Settings replay action. Seen state is isolated in `localStorage` under `lecturepack.guided-tour.seen.v1`, never job data.
4. Added the `Polar Bears 10s Demo.mp4` Home card. It calls only `start_demo_job` / `end_demo_job` through the bridge and renders the backend's `demo_event` stage/progress stream. The UI reducer rejects events with a mismatched operation/session identity and ignores late events after cleanup.
5. Replaced brittle source-only tests with Node-executed checks of the shared tour and demo reducers. The reducer explicitly ignores delayed slot successes after cancelling/cleanup and preserves live progress for an idempotent same-identity result; a mismatched pre-adopted identity is ignored. Focused verification: `76 passed in 2.27s`.

## Remaining verification

- Fresh packaged QtWebEngine click-through and Phase 3 conversational UAT are intentionally not claimed here.
