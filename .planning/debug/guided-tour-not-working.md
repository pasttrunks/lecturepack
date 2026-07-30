# Debugging Session: Guided Tour Overlay Not Displaying

**Date:** 2026-07-28
**Symptom:** Clicking "Replay guided tour" in Settings did not render the guided tour overlay on screen.
**Status:** RESOLVED (Fix implemented & build in progress)

## Root Cause Analysis
1. In `app/ui/index.html`, `#guided-tour-overlay` was placed inside `#runtime-setup-overlay`.
2. `#runtime-setup-overlay` has the `hidden` attribute by default on every healthy launch.
3. In CSS, parent containers with `[hidden]` hide all child elements regardless of inner style changes (`display: flex`).
4. As a result, toggling `overlay.hidden = false` in Javascript had no effect because the parent container `#runtime-setup-overlay` remained hidden.

## Fix Applied
1. Moved `#guided-tour-overlay` outside of `#runtime-setup-overlay` directly into the `#app` root container in `app/ui/index.html`.
2. Explicitly updated `GuidedTour.show()` and `GuidedTour.hide()` in `app/ui/app.js` to toggle `overlay.style.display = 'flex'` and `overlay.style.display = 'none'` alongside `overlay.hidden`.
3. Verified DOM hierarchy with pytest (`tests/test_guided_tour.py` passed 2/2).
4. Triggered fresh PyInstaller compilation (`python packaging/build.py --no-installer`).
