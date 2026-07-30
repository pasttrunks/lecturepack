# Phase 4: Visual Artifact Reliability - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 preserves LecturePack beta 5's intentional visual identity while removing unwanted flash, flicker, entrance-animation replay, overflow, focus traps, and layout instability from the beta-6 shell, setup gate, guided tour, themes, navigation, and responsive states. It does not redesign the application, replace its motion language, add new product capabilities, or weaken the existing hard shadows and embedded press effects.

</domain>

<decisions>
## Implementation Decisions

### Page animation replay
- **D-01:** Intentional page entrance animation runs after a real user navigation to a different page. Backend events, option changes, and state rendering never trigger it.
- **D-02:** Clicking the navigation control for the page already open does not replay its entrance animation.
- **D-03:** Closing the setup gate, guided-tour surface, dialog, dropdown, or other overlay leaves the underlying page exactly in place without entrance replay or layout jump.
- **D-04:** Live progress, logs, settings, and backend status update in place. Only the directly changed control may use its existing beta-5 micro-animation; the containing page does not animate.

### Theme initialization and switching
- **D-05:** A fresh profile defaults to the existing Light theme.
- **D-06:** The saved theme is applied before the first visible frame. Startup does not visibly transition from one theme to another.
- **D-07:** A user-triggered Light/Dark change swaps the entire palette atomically. The theme button retains its existing embedded press animation, but elements do not independently tween colors and the whole window does not crossfade.
- **D-08:** If a setup gate, guided-tour step, or dialog is open, it and the underlying page change theme in the same frame.
- **D-09:** Theme selection persists immediately so the next launch can apply it before first paint; the global Save action is not required for theme persistence.

### Long values and responsive layout
- **D-10:** Long local-model names stay on one line with ellipsis. The full value appears in a small anchored tooltip for both pointer hover and keyboard focus and disappears when that hover/focus leaves.
- **D-11:** Narrow layouts stack secondary controls below primary content and use vertical scrolling. Pages must not introduce horizontal scrolling or clip required actions.
- **D-12:** LecturePack has no Phase-4-imposed minimum window size. Layouts continue adapting down to very small windows, keeping every required control reachable rather than hiding functionality.

### Tour, gate, resize, DPI, and focus
- **D-13:** While the window resizes, the tour spotlight continuously tracks the real target and the instruction card is kept within the current viewport.
- **D-14:** If a tour target is outside the visible area, the app scrolls only enough to reveal the real control before placing the spotlight.
- **D-15:** Moving between monitors or changing display scaling recalculates overlay geometry immediately without fading, restarting the step, or replaying page motion.
- **D-16:** The runtime setup gate remains modal. During a guided step, keyboard focus cycles through the highlighted real action and tour controls, with Exit always reachable; focus cannot leak into unrelated dimmed controls.

### Locked visual preservation contract
- **D-17:** Preserve beta 5's animation timings, transitions, hard dark shadows, pressed/embedded control movement, palette, typography, and motion character. Fix only unintended artifacts and event-triggered replays.
- **D-18:** Do not use a full-viewport SVG mask for spotlights. Retain the QtWebEngine-safe CSS spotlight and real-control interaction established in Phase 3.

### the agent's Discretion
- Exact responsive breakpoints, stacking order, requestAnimationFrame/observer scheduling, and geometry-clamping implementation, provided all decisions above hold at every tested size and DPI.
- Exact tooltip offset and collision handling, provided the full value is available by both hover and keyboard focus without resizing the field.
- Exact visual-regression fixture structure and instrumentation used to prove no unintended animation, flash, overflow, or WebEngine console error.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and phase scope
- `AGENTS.md` — Mandatory phase discipline, preservation, testing, documentation, and Git rules.
- `.planning/PROJECT.md` — Beta-6 milestone goals, constraints, non-goals, and visual-preservation promise.
- `.planning/REQUIREMENTS.md` — VIS-01 through VIS-05 acceptance contract.
- `.planning/ROADMAP.md` — Phase 4 boundary, success criteria, and Phase 5 approval gate.
- `.planning/MILESTONE-CONTEXT.md` — Milestone-wide locked product and visual decisions.
- `.planning/research/ARCHITECTURE.md` — Canonical beta-6 architecture research referenced by the roadmap.

### Prior-phase UI contracts
- `.planning/phases/03-empty-launch-guided-demo/03-CONTEXT.md` — Guided-tour behavior, setup admission, demo interaction, and visual constraints inherited from Phase 3.
- `docs/HANDOFF_PHASE_03.md` — Current shipped Phase 3 selectors, packaged-UAT evidence, and handoff state.
- `.planning/phases/03-empty-launch-guided-demo/03-VERIFICATION.md` — Verified tour, gate, isolation, and packaged behavior that Phase 4 must not regress.

### Product and architecture
- `docs/PRODUCT_SPEC.md` — Canonical product behavior, accessibility, local-first, and safety expectations.
- `docs/ARCHITECTURE.md` — UI-to-backend boundaries and QtWebEngine desktop composition.
- `docs/DECISIONS.md` — Locked architectural decisions and required location for new consequential decisions.
- `docs/IMPLEMENTATION_PLAN.md` — Existing file map and implementation sequence; reconcile stale wording with newer Phase 4 decisions.

### Shipping UI and regression evidence
- `app/ui/index.html` — Real beta-5-derived shell, settings fields, setup gate, tour controls, and inline layout structure.
- `app/ui/app.css` — Authoritative tokens, shadows, press states, animation vocabulary, theme palettes, and CSS spotlight implementation.
- `app/ui/app.js` — Navigation, rendering, theme, tour geometry, backend update, and overlay integration points.
- `tests/test_ui_tokens_motion_responsive.py` — Existing motion, token, contrast, and responsive invariants.
- `tests/test_webview_theme.py` — Existing Light/Dark theme contracts.
- `tests/test_guided_tour.py` — Existing CSS spotlight, pointer behavior, focus controls, and resize hooks.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/ui/app.css`: already centralizes the intentional beta-5 vocabulary in motion tokens, hard shadows, press states, entrance/exit keyframes, theme variables, focus-visible rules, and reduced-motion guards.
- `app/ui/app.js`: already owns `setTheme`, navigation/render paths, runtime gate state, guided-tour positioning, and scroll/resize hooks; Phase 4 should stabilize these paths rather than introduce a second UI state system.
- `#tour-spotlight-box`, `#guided-tour-card`, and the Phase 3 lifted real demo-card pattern: provide a QtWebEngine-safe pure-CSS overlay model without an SVG hit surface.
- `LECTUREPACK_DATA_DIR` and packaged fixture seams: support fresh-profile Light-theme/startup verification without touching user data.

### Established Patterns
- CSS custom properties are the single theme source; visual changes should be atomic at the root theme attribute rather than piecemeal inline transitions.
- `.lp-anim-*`, `.lp-stagger`, and explicit navigation rendering are the intentional entrance system. Dynamic data updates must avoid replacing/reclassing page roots in ways that restart those keyframes.
- `.lp-hit`, `.lp-press`, `.lp-press-sm`, and hard-shadow variables are locked interaction character, not artifacts to remove.
- Pointer-transparent overlay layers plus pointer-enabled real controls preserve interaction in QtWebEngine.

### Integration Points
- Initial HTML/root theme attribute -> bootstrap settings -> first visible WebEngine frame.
- Header and Settings theme buttons -> one atomic root-theme mutation -> immediate bridge persistence.
- Navigation handlers -> page visibility/render lifecycle -> explicit entrance-animation trigger.
- Backend signals and option handlers -> narrowly scoped DOM updates with no page-root animation restart.
- Settings model path/name fields -> ellipsis/focus/hover tooltip behavior.
- Window/scroll/DPI changes -> tour target measurement, viewport clamping, and minimal target reveal.
- Runtime setup gate and guided tour -> distinct modal/focus policies tested through keyboard navigation.

</code_context>

<specifics>
## Specific Ideas

- The target is the same polished beta-5 app after bugs are removed—not a calmer, flatter, or simplified redesign.
- Theme startup should feel as though the chosen theme was always present; Light is the fresh-profile default.
- Even extremely small windows must retain access to every required action through stacking and vertical scrolling.
- Tour movement follows real controls and display scaling without decorative fades or step restarts.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 4 scope.

</deferred>

---

*Phase: 04-visual-artifact-reliability*
*Context gathered: 2026-07-29*
