# Phase 4: Visual Artifact Reliability - Research

**Researched:** 2026-07-29
**Domain:** QtWebEngine static HTML/CSS/JavaScript visual reliability
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Page animation replay
- **D-01:** Intentional page entrance animation runs after a real user navigation to a different page. Backend events, option changes, and state rendering never trigger it.
- **D-02:** Clicking the navigation control for the page already open does not replay its entrance animation.
- **D-03:** Closing the setup gate, guided-tour surface, dialog, dropdown, or other overlay leaves the underlying page exactly in place without entrance replay or layout jump.
- **D-04:** Live progress, logs, settings, and backend status update in place. Only the directly changed control may use its existing beta-5 micro-animation; the containing page does not animate.

#### Theme initialization and switching
- **D-05:** A fresh profile defaults to the existing Light theme.
- **D-06:** The saved theme is applied before the first visible frame. Startup does not visibly transition from one theme to another.
- **D-07:** A user-triggered Light/Dark change swaps the entire palette atomically. The theme button retains its existing embedded press animation, but elements do not independently tween colors and the whole window does not crossfade.
- **D-08:** If a setup gate, guided-tour step, or dialog is open, it and the underlying page change theme in the same frame.
- **D-09:** Theme selection persists immediately so the next launch can apply it before first paint; the global Save action is not required for theme persistence.

#### Long values and responsive layout
- **D-10:** Long local-model names stay on one line with ellipsis. The full value appears in a small anchored tooltip for both pointer hover and keyboard focus and disappears when that hover/focus leaves.
- **D-11:** Narrow layouts stack secondary controls below primary content and use vertical scrolling. Pages must not introduce horizontal scrolling or clip required actions.
- **D-12:** LecturePack has no Phase-4-imposed minimum window size. Layouts continue adapting down to very small windows, keeping every required control reachable rather than hiding functionality.

#### Tour, gate, resize, DPI, and focus
- **D-13:** While the window resizes, the tour spotlight continuously tracks the real target and the instruction card is kept within the current viewport.
- **D-14:** If a tour target is outside the visible area, the app scrolls only enough to reveal the real control before placing the spotlight.
- **D-15:** Moving between monitors or changing display scaling recalculates overlay geometry immediately without fading, restarting the step, or replaying page motion.
- **D-16:** The runtime setup gate remains modal. During a guided step, keyboard focus cycles through the highlighted real action and tour controls, with Exit always reachable; focus cannot leak into unrelated dimmed controls.

#### Locked visual preservation contract
- **D-17:** Preserve beta 5's animation timings, transitions, hard dark shadows, pressed/embedded control movement, palette, typography, and motion character. Fix only unintended artifacts and event-triggered replays.
- **D-18:** Do not use a full-viewport SVG mask for spotlights. Retain the QtWebEngine-safe CSS spotlight and real-control interaction established in Phase 3.

### the agent's Discretion
- Exact responsive breakpoints, stacking order, requestAnimationFrame/observer scheduling, and geometry-clamping implementation, provided all decisions above hold at every tested size and DPI.
- Exact tooltip offset and collision handling, provided the full value is available by both hover and keyboard focus without resizing the field.
- Exact visual-regression fixture structure and instrumentation used to prove no unintended animation, flash, overflow, or WebEngine console error.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 4 scope.
</user_constraints>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VIS-01 | Preserve beta-5 animation language, timing, transitions, shadows, and press effect. | Preserve the existing CSS vocabulary/tokens and assert them structurally plus beta-5 comparison evidence. |
| VIS-02 | Apply themes atomically without luminance flash or per-element color artifacts. | Root `data-theme` bootstrap and one root mutation with immediate bridge persistence. |
| VIS-03 | Backend/option updates never replay entrance motion or repaint/jump pages. | Make `setScreen` idempotent and restrict entrance application to actual screen changes. |
| VIS-04 | Ellipsize long model names and reveal complete value by hover and keyboard focus. | Reusable non-reflowing tooltip controller with focus/hover and viewport collision handling. |
| VIS-05 | Gate/tour/theme/resize/navigation have no flicker, overflow, focus trap, or WebEngine console error. | Coalesced geometry scheduler, focus containment tests, viewport/DPI fixture matrix, and console-error capture. |

## Project Constraints (from AGENTS.md)

- Work only in approved Phase 4 files; do not change product code outside the authorized plan.
- Preserve functional milestones; run relevant tests and report actual `pytest` output before completion.
- Do not weaken/delete tests, add dependencies, replace the selected stack, or mix source-derived and AI-generated content.
- Make no network calls beyond permitted product behavior; never modify original lecture video or store credentials.
- Record consequential technical decisions in `docs/DECISIONS.md`; update Phase 4 handoff before a long-session stop.
- Use a dedicated phase branch from a clean tree, commit passing states, and never use destructive Git recovery.

## Summary

Phase 4 is a stabilization pass over the existing static WebEngine shell, not a redesign or framework migration. The authoritative seams are already present: `setScreen()` controls visibility and the navigation-only `lprail` entrance; `setTheme()` changes the root `#app[data-theme]`; CSS custom properties own the palette; and the CSS spotlight uses a pointer-transparent wrapper with real controls above it. [VERIFIED: codebase grep]

The confirmed risk is that these correct seams are currently too permissive: `setScreen()` has no active-screen early return, `setTheme()` persists only after DOM work and the static shell begins dark, `positionTourSpotlight()` only clamps top/left rather than the whole rectangle/card, and model path/name fields are raw text without a keyboard-accessible overflow affordance. Fix these central seams once; do not create a second state, theme, animation, or overlay system. [VERIFIED: codebase grep]

**Primary recommendation:** Make a small shared UI-stability layer in `app.js` that (1) treats a changed screen as the sole entrance trigger, (2) applies/persists root theme as one transaction, and (3) schedules overlay/tooltip geometry once per frame; pair it with targeted CSS rules and executable DOM/QtWebEngine regression coverage.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| First-frame and persisted theme | Frontend Server (Qt bridge/startup) | Browser / Client | Python supplies saved value before WebEngine is shown; client applies one root attribute. |
| In-session theme switch | Browser / Client | Frontend Server | The client changes the root attribute synchronously, then persists through the existing bridge. |
| Navigation / no entrance replay | Browser / Client | — | Screen visibility and animation selectors live solely in the shipped DOM/CSS. |
| Responsive layout / long-value tooltip | Browser / Client | — | CSS layout and DOM measurement own these visual constraints. |
| Tour/gate focus and DPI geometry | Browser / Client | Frontend Server | The DOM measures CSS-pixel geometry; Qt supplies the WebEngine viewport/DPI environment. |
| Regression and packaged visual evidence | API / Backend test harness | Browser / Client | pytest/QtWebEngine harness controls realistic profile, viewport, bridge, and console evidence. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Existing HTML/CSS/vanilla JS | shipped shell | Rendering, tokens, navigation, overlays | Locked shipping architecture; no dependency should be added. [VERIFIED: codebase grep] |
| PySide6 QtWebEngine | project-pinned 6.11.x | Desktop WebEngine composition and integration tests | Existing selected application stack. [VERIFIED: `.planning/PROJECT.md`] |
| pytest + pytest-qt | project-pinned 8.x / 4.x | Structural and WebEngine regression tests | Existing test stack. [VERIFIED: `.planning/PROJECT.md`] |

### Supporting

| Library / API | Version | Purpose | When to Use |
|--------------|---------|---------|-------------|
| `requestAnimationFrame` | browser built-in | Coalesce read/measure/write geometry before the next repaint | Resize, scroll, monitor/DPI-driven spotlight and tooltip placement. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame] |
| `ResizeObserver` | browser built-in | Observe relevant element/container size changes | Observe the app root/tour card if window resize alone misses layout-driven size changes; queue writes in rAF to avoid observer loops. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver] |
| CSS `text-overflow` | browser built-in | Ellipsis constrained single-line text | Long model display fields only, with a separate accessible tooltip. [CITED: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/text-overflow] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CSS spotlight | Full-viewport SVG mask | Rejected by locked D-18 and existing QtWebEngine hit-test evidence. [VERIFIED: Phase 3 tests] |
| Root custom-property theme | Per-component inline colors/classes | Rejected: permits multi-frame palette disagreement and violates D-07/D-08. [VERIFIED: locked context] |
| Existing DOM + pytest harness | UI library / third-party tooltip | Rejected: adds an unapproved dependency and a second styling/motion system. [VERIFIED: AGENTS.md + UI-SPEC] |

**Installation:** None. This phase must not install external packages.

## Architecture Patterns

### System Architecture Diagram

```text
Saved config / runtime setup state
            |
            v
Qt startup/bridge ──> pre-visible root theme ──> #app[data-theme] CSS variables
            ^                                       |
            | immediate persistence                  v
Header/Settings theme actions ─────────────────> gate, tour, page, controls (same frame)

Navigation intent ──> setScreen(next) ──> only changed screen becomes visible ──> lprail entrance
Backend/options ─────────────────────────────────────> targeted text/value/control mutation only

resize/scroll/DPI/target layout ──> scheduleGeometry() ──> rAF measure live rects
                                                   ├──> minimum reveal scroll
                                                   ├──> clamped spotlight/arrow
                                                   └──> clamped tour card / tooltip
```

### Recommended Project Structure

```text
app/ui/
├── index.html     # semantic hooks/ARIA only; no duplicate state
├── app.css        # existing tokens, responsive rules, tooltip and overlay geometry
└── app.js         # root theme, idempotent navigation, shared rAF geometry scheduler
tests/
├── test_ui_tokens_motion_responsive.py  # CSS/token/structural guards
├── test_webview_theme.py                # theme first-paint and atomic-switch seams
└── test_guided_tour.py                  # spotlight/focus/resize reducer and DOM checks
```

### Pattern 1: Navigation is the only entrance trigger

**What:** Return before rendering/animation work when `name === LP.state.screen`; for a different name, mutate visibility and active nav once in the existing `LP.motion.nav` callback. Never re-add a root animation class or replace a `main [data-screen]` element on backend events. [VERIFIED: `app/ui/app.js` and `app/ui/app.css`]

**Why:** The selector `main [data-screen]:not([hidden])` automatically animates when a screen is newly unhidden; hide/show of the current screen or DOM replacement is enough to replay it. Current `setScreen()` does not guard the already active target. [VERIFIED: codebase grep]

### Pattern 2: Theme transaction with first-paint ownership

**What:** Split theme application from persistence: `applyTheme(theme)` performs the synchronous root `data-theme`, labels, and settings-button mutation; `setTheme(theme, {persist})` applies once then immediately calls the bridge only for a user request. Startup must receive/default Light before the WebEngine first visible frame (not after a `settings_changed` event). [VERIFIED: locked D-05 through D-09]

**Example:**

```javascript
function applyTheme(theme) {
  if (LP.state.theme === theme && $('app').dataset.theme === theme) return;
  LP.state.theme = theme;
  $('app').dataset.theme = theme; // one palette authority
  $('theme-label').textContent = theme === 'light' ? 'DARK' : 'LIGHT';
  $('btn-set-light').classList.toggle('active', theme === 'light');
  $('btn-set-dark').classList.toggle('active', theme === 'dark');
}
function setTheme(theme, persist) {
  applyTheme(theme);
  if (persist && lpBridge.connected()) lpBridge.call('set_setting', 'theme', theme);
}
```

The code preserves a direct control’s existing press interaction while preventing independent palette transitions. Do not animate `color`, `background-color`, `border-color`, or `box-shadow` across the global theme switch. [VERIFIED: locked D-07]

### Pattern 3: Coalesced live-geometry placement

**What:** One scheduler de-duplicates resize/scroll/visual-viewport/observer events. In its rAF callback: first minimally reveal the real target if needed; then re-read `getBoundingClientRect`; finally write spotlight, arrow, card, or tooltip positions. Clamp both edges using the actual viewport dimensions. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver]

**Example:**

```javascript
let geometryFrame = null;
function scheduleGeometry() {
  if (geometryFrame !== null) return;
  geometryFrame = requestAnimationFrame(() => {
    geometryFrame = null;
    const target = currentTourTarget();
    if (!target) return;
    target.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const rect = target.getBoundingClientRect(); // remeasure after reveal
    placeSpotlight(clampRect(rect, 7));
    placeTourCard(clampCard($('guided-tour-card'), 16));
  });
}
```

Do not resize an observed element from its own `ResizeObserver` callback without guarding/equivalent rAF scheduling: MDN documents that this can emit a loop error and visible broken layout. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver]

### Pattern 4: Non-reflowing accessible long-value tooltip

**What:** Give each truncated model display a stable `tabindex="0"`, programmatic tooltip relationship (`aria-describedby`), and one shared tooltip element. On `mouseenter`/`focusin`, populate exact `textContent`, position inside the viewport in rAF, and show it; on `mouseleave`/`focusout` hide it unless focus/hover moved into the tooltip. Use `white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0`. [CITED: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/text-overflow]

**Anti-patterns to Avoid**

- **Re-rendering a page root for a live value:** re-matches the entrance selector and violates VIS-03; mutate the single label/value instead.
- **Initial `data-theme="dark"` followed by a light setting event:** guarantees a fresh-profile dark-to-light first-paint flash; bootstrap Light before visibility.
- **Setting only spotlight left/top:** the right/bottom edges can escape after small viewports/DPI changes; clamp a complete rectangle and card.
- **Using `title` as the only tooltip:** it does not meet the locked explicit hover-and-keyboard tooltip behavior and gives no collision control.
- **Adding focus traps without an explicit allowed set:** gate and tour have different policies; scope their handlers/listeners and always retain an Exit route.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Palette propagation | A per-node palette updater | Existing root `data-theme` plus CSS custom properties | One source changes all surfaces, including overlays, coherently. |
| Overlay dimming/click interception | SVG mask or synthetic hit layer | Existing CSS shadow spotlight + pointer-transparent overlay and real controls | QtWebEngine-safe and preserves real interaction. |
| Frame scheduling | Timers per resize/scroll event | `requestAnimationFrame` coalescing | Aligns geometry writes with repaint. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame] |
| Element-size detection | Polling layout dimensions | `ResizeObserver`, with rAF/loop guard | Reports element box changes without polling. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver] |

**Key insight:** Phase 4 needs fewer mechanisms, not more. Existing state owners are correct; the plan should make their ordering/idempotence observable and testable.

## Common Pitfalls

### Pitfall 1: Treating any navigation call as a navigation change
**What goes wrong:** Active-tab re-click, overlay closure, or reducer refresh hides/unhides the same section and restarts `lprail`.
**Avoid:** Compare the requested page to `LP.state.screen` before calling motion/visibility code; test active-nav click and each overlay close path.

### Pitfall 2: Persistence event re-enters theme application
**What goes wrong:** A user theme action persists, backend broadcasts `settings_changed`, and UI code performs redundant work or a visible intermediate palette.
**Avoid:** Use an idempotent `applyTheme`; startup gets theme pre-visible; persistence acknowledgement can safely be a no-op.

### Pitfall 3: Geometry feedback loops and stale measurement
**What goes wrong:** Resize callback changes measured geometry, logs a ResizeObserver loop/WebEngine console error, or places the overlay from a pre-scroll rectangle.
**Avoid:** Coalesce to rAF, remeasure after minimum `scrollIntoView`, and do not observe/mutate the same size cyclically. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver]

### Pitfall 4: Responsive fixes cover only the review row
**What goes wrong:** Existing 1220/820px review reflow passes while Settings rows, gate actions, tour actions, or a long model name still cause horizontal overflow or hide the action.
**Avoid:** Add representative fixtures for Home, Settings, gate, and each tour stage at desktop, existing breakpoints, 640px, and very-small viewport; assert `scrollWidth <= clientWidth` on page containers and visibility/focusability of required actions.

### Pitfall 5: Tooltip fixes alter layout or accessibility
**What goes wrong:** Full model name expands its field, an overlay blocks the source, or mouse-only behavior leaves keyboard users without the value.
**Avoid:** Fixed/absolute tooltip outside normal flow, source remains ellipsized, hover + focus show, leave + blur hide, collision clamp, and DOM assertions for ARIA relationship.

## Code Examples

### Clamped rectangle calculation

```javascript
function clampRect(rect, pad) {
  const vw = window.innerWidth, vh = window.innerHeight;
  const width = Math.min(rect.width + pad * 2, Math.max(0, vw - 12));
  const height = Math.min(rect.height + pad * 2, Math.max(0, vh - 12));
  return {
    left: Math.max(6, Math.min(vw - width - 6, rect.left - pad)),
    top: Math.max(6, Math.min(vh - height - 6, rect.top - pad)),
    width, height,
  };
}
```

Source pattern: live `getBoundingClientRect()` plus rAF prior to repaint. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame]

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Root View Transition/crossfade | Existing mechanical, transform-only `lprail` entrance | Preserve the beta-5 visual language without luminance flash. [VERIFIED: `app/ui/app.css`] |
| Full-screen masking overlay | Existing CSS box-shadow spotlight with real target controls | Avoid QtWebEngine hit-test failure. [VERIFIED: Phase 3 test] |
| Window-only spotlight update | rAF-coalesced geometry with element/viewport awareness | Required for resize, scroll, layout, and DPI reliability. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | QtWebEngine exposes `ResizeObserver`/`requestAnimationFrame` with Chromium-compatible behavior in the pinned runtime. | Standard Stack / geometry | Use window resize/scroll fallback and verify in packaged WebEngine before relying on observer-only updates. |
| A2 | The startup bridge can provide a saved theme before the first WebEngine frame without a new architecture layer. | Theme pattern | If not, planner must make first-frame theme bootstrap an explicit desktop/bridge task, not a post-load UI patch. |

## Open Questions — Resolved

1. **Pre-visible theme path — RESOLVED.** `index.html` statically starts `#app` with `data-theme="dark"`; `bridge.py:get_bootstrap()` currently defaults QSettings to dark; `app.js` calls it only after `lpBridge.ready`, then calls `setTheme`; and `main.py` loads the page before immediately calling `win.show()`. This is post-load/post-visible and cannot satisfy VIS-02. The implementation path is an explicit pre-visible bootstrap in the existing `app/desktop/main.py` owner: obtain the canonical bridge/QSettings theme (default Light), inject or otherwise apply the correct root theme before the view is shown, and gate `win.show()` on that readiness. This preserves the existing desktop/bridge architecture rather than introducing another theme system. [VERIFIED: current source seam inspection]
2. **Supported viewport/DPI matrix — RESOLVED.** Automated CSS/WebEngine coverage uses 1360x860 desktop/default, 1220px, 820px, 640px, and 480x560 very-small fixtures plus continuous arbitrary-resize assertions. Physical packaged Windows evidence covers 100%, 125%, and 150% display scaling. D-12 also requires removing or relaxing the current `MainWindow.setMinimumSize(1080,680)` constraint in `app/desktop/main.py`; otherwise the 480x560 fixture is not physically reachable. [VERIFIED: existing CSS breakpoints, D-12, and current desktop minimum-size seam]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | pytest / Qt test harness | ✓ | 3.12.3 | — |
| Node.js | existing guided-tour reducer tests | ✓ | v24.13.0 | Tests skip only if absent; no fallback for executing reducer assertions. |
| PySide6 QtWebEngine | true WebEngine/manual visual checks | project dependency | pinned 6.11.x | Structural pytest checks remain available; packaged check required for final visual evidence. |

**Missing dependencies with no fallback:** None identified for planning. Physical packaged WebEngine verification remains a Phase 4 approval-gate requirement.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing configuration) + pytest-qt / existing Node reducer execution |
| Config file | `pytest.ini` |
| Quick run command | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` |
| Full suite command | `python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIS-01 | Motion tokens, hard shadows/press classes, navigation-only entrance vocabulary preserved | structural + screenshot/manual comparison | focused UI command | Partial — extend `test_ui_tokens_motion_responsive.py` |
| VIS-02 | Fresh profile Light before visible frame; user switch one root mutation/instant persistence/overlay coherence | bridge/WebEngine integration | focused UI command | ❌ Wave 0 |
| VIS-03 | active-nav, backend, option, and overlay-close paths cannot replay entrance | DOM/reducer integration | focused UI command | ❌ Wave 0 |
| VIS-04 | ellipsis, hover/focus tooltip, full exact text, collision/no reflow | DOM/WebEngine interaction | focused UI command | ❌ Wave 0 |
| VIS-05 | no page horizontal overflow, tour/gate focus containment, resize/scroll/DPI geometry, no console errors | QtWebEngine integration + manual packaged matrix | focused UI command + packaged checklist | Partial — extend `test_guided_tour.py` |

### Sampling Rate

- **Per task commit:** focused UI command above.
- **Per wave merge:** `python -m pytest -q`.
- **Phase gate:** full suite green; beta-5 comparison evidence; physical/manual supported-size and DPI matrix with WebEngine console capture.

### Wave 0 Gaps

- [ ] Extend the three existing UI test files with explicit VIS-01..VIS-05 IDs; do not create a parallel UI test framework.
- [ ] Add a deterministic JS/DOM harness seam that records `animationstart` on page roots and proves only changed-page navigation can generate it.
- [ ] Add bridge/startup test proving fresh profile emits/applies Light before view visibility and a user action immediately persists one theme value.
- [ ] Add QtWebEngine viewport/DPI fixture/helper that asserts no horizontal overflow, required-action visibility, focus containment, and collected console errors for gate/tour/theme scenarios.
- [ ] Add model-tooltip interaction tests for mouse and keyboard focus, exact full value, `aria-describedby`, and viewport bounds.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No accounts/auth in scope. |
| V3 Session Management | no | Guided-demo identity is inherited from Phase 3; do not modify it. |
| V4 Access Control | no | Local single-user desktop UI; no new privilege boundary. |
| V5 Input Validation | yes | Treat backend-provided model/path values as text (`textContent`), never HTML; do not execute transcript/lecture content. [VERIFIED: AGENTS.md] |
| V6 Cryptography | no | No cryptographic change. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Backend/model value inserted as HTML | Tampering | Continue using `textContent` / existing `esc()` only where markup is deliberate. |
| Overlay intercepts unintended controls | Elevation of Privilege | Pointer-transparent overlay; focus allowed list for active modal/tour; real control remains target. |

## Sources

### Primary (HIGH confidence)
- Repository/UI contracts: `04-CONTEXT.md`, `04-UI-SPEC.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `MILESTONE-CONTEXT.md`, Phase 3 handoff/verification, and current `app/ui/*` / tests. [VERIFIED: codebase grep]

### Secondary (MEDIUM confidence)
- [MDN ResizeObserver](https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver) — resize lifecycle, loop hazard, rAF mitigation.
- [MDN requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame) — callback before next repaint and coalescing rationale.
- [MDN text-overflow](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/text-overflow) — standard ellipsis property.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — locked existing stack/no new packages.
- Architecture: HIGH — direct current-code and locked-context evidence.
- Pitfalls: HIGH — direct CSS/JS seam analysis plus official browser API documentation.

**Research date:** 2026-07-29
**Valid until:** 2026-08-28 (stable codebase/UI domain; refresh after any WebEngine/PySide upgrade)
