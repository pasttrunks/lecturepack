---
phase: 03-empty-launch-guided-demo
plan: 03
subsystem: ui
tags: [guided-tour, onboarding, css-spotlight, settings-replay, real-demo-events, action-led-demo]
requires:
  - phase: 03-empty-launch-guided-demo
    provides: guided tour overlay, step navigation, and Settings replay
provides:
  - pointer-transparent CSS spotlight (`#tour-spotlight-box`) with no SVG mask
  - action-led guided onboarding tour that waits for real import, processing, and review events
  - source-derived Polar Bears thumbnail plus click/drag demo import affordance
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

Plan 03-03 delivers the Phase 3 frontend: a CSS-only guided spotlight, concise user-controlled action-led tour, Settings replay, and the Home card for the backend-owned isolated demo lifecycle. It does not claim packaged Qt click-through or Phase 3 UAT; those remain phase-level verification gates.

## Accomplishments
1. Added `#guided-tour-overlay` and `#tour-spotlight-box`. The layer and spotlight both use `pointer-events:none`; the only interactive surface is the compact control card. The visual cutout is a CSS border plus oversized box-shadow, avoiding the QtWebEngine SVG-mask hit-test failure.
2. Implemented the action-led flow: demo import waits for the tile click or custom-MIME drag/drop; processing waits for backend events; review waits for the existing Keep/Reject action; Study leads to Export. Next is disabled at each waiting gate, while Back applies only where it cannot bypass a real action. Navigation remains keyboard-accessible without stealing arrow keys from inputs/selects/textareas.
3. Added an always-visible **Exit demo** action during the tour, a first-healthy-launch non-blocking **Take guided tour** / **Skip to app** prompt, and the Settings replay action. Seen state is isolated in `localStorage` under `lecturepack.guided-tour.seen.v1`, never job data.
4. Added the draggable/clickable `Polar Bears 10s Demo.mp4` Home card with a 960×540 source-derived JPEG thumbnail. Its custom MIME drop is handled locally by the lecture drop area without invoking native import; click uses a reduced-motion-safe fly visual and then calls only `start_demo_job` / `end_demo_job` through the bridge. The card renders the backend's `demo_event` stage/progress stream.
5. `review_ready` is treated as a nonterminal live event and opens the real review controls. The UI reducer rejects mismatched operation/session events, ignores late events after cleanup, and preserves the existing retry/cancel acknowledgement isolation.
6. Replaced brittle source-only tests with Node-executed checks of shared tour/demo reducers, including action gates. The focused suite also verifies the local thumbnail is nonempty and QImage-decodable at 960×540. Focused verification: `80 passed in 3.32s`.

## Remaining verification

- Fresh packaged QtWebEngine click-through and Phase 3 conversational UAT are intentionally not claimed here.
