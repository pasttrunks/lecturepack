# Phase 04: Visual Artifact Reliability - Pattern Map

**Mapped:** 2026-07-29  
**Files analyzed:** 7  
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/ui/app.js` | controller | event-driven | `app/ui/app.js` screen/theme/tour controllers | exact |
| `app/ui/app.css` | component | transform | `app/ui/app.css` token, responsive, spotlight rules | exact |
| `app/ui/index.html` | component | request-response | `app/ui/index.html` existing semantic overlay/settings markup | exact |
| `app/desktop/bridge.py` | bridge/service | request-response | `app/desktop/bridge.py` QSettings bootstrap payload | exact |
| `tests/test_ui_tokens_motion_responsive.py` | test | transform | existing token/DOM structural assertions | exact |
| `tests/test_webview_theme.py` | test | request-response | existing static cross-file theme assertions | exact |
| `tests/test_guided_tour.py` | test | event-driven | existing Node reducer + DOM/CSS integration assertions | exact |

## Pattern Assignments

### `app/ui/app.js` (controller, event-driven)

**Analog:** Its existing screen/theme controller and guided-tour controller.

**State and single-owner rendering pattern** (`app/ui/app.js:180-188`, `483-490`):

```javascript
screen: 'home', theme: 'dark', focus: false, onb: null, jobsEmpty: false,

function renderWorkspace() {
  renderPipeline();
  renderSlides();
  renderReviewTranscript();
  renderTranscript();
  renderStudy();
  renderChat();
  renderQuiz();
  renderExportPhase();
}
```

Keep the Phase 04 stability behavior in this existing `LP.state`/named-renderer model; narrowly update affected DOM rather than create a second UI state or replace page roots.

**Navigation/entrance ownership pattern** (`1843-1886`):

```javascript
function setScreen(name) {
  LP.motion.nav(function () {
    LP.state.screen = name;
    Array.prototype.forEach.call(document.querySelectorAll('main [data-screen]'), function (sec) {
      var show = sec.dataset.screen === name;
      if (show === !sec.hidden) return;
      sec.hidden = !show;
    });
    Array.prototype.forEach.call(document.querySelectorAll('.lp-nav'), function (b) {
      b.classList.toggle('active', b.dataset.nav === name);
    });
    LP.motion.indicator();
  });
}
```

Add the idempotent active-screen guard before `LP.motion.nav`; only a changed screen may cause the existing CSS entrance selector to apply. Keep the active-nav/indicator ordering intact.

**Atomic root theme + immediate persistence pattern** (`1888-1898`, `3018-3026`, `3896-3898`):

```javascript
function setTheme(theme) {
  LP.state.theme = theme;
  $('app').dataset.theme = theme;
  $('theme-label').textContent = theme === 'light' ? 'DARK' : 'LIGHT';
  $('btn-set-light').classList.toggle('active', theme === 'light');
  $('btn-set-dark').classList.toggle('active', theme === 'dark');
  lpBridge.call('set_setting', 'theme', theme);
}

$('btn-set-light').addEventListener('click', function () { setTheme('light'); });
$('btn-set-dark').addEventListener('click', function () { setTheme('dark'); });
```

Continue to use one `#app[data-theme]` mutation and the existing bridge call. Bootstrap default must become Light before visibility; settings events should use the same function rather than a competing theme path.

**Modal focus containment pattern** (`1982`, `2271-2275`):

```javascript
document.addEventListener('keydown', function (e) {
  if (!isBlocking()) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); return; }
  if (e.key === 'Tab' && isOpen()) { trapFocus(overlay(), e); e.stopImmediatePropagation(); return; }
  e.stopImmediatePropagation();
}, true);
```

Extend the established scoped `trapFocus` approach to the guided-tour real target/card controls; do not intercept focus globally when no overlay is active.

**Tour geometry/event pattern** (`2467-2521`; listener contract asserted in `tests/test_guided_tour.py:374-383`):

```javascript
function positionTourSpotlight() { /* measure live target and position CSS box/card */ }
function renderGuidedTour() { /* render current state and call positionTourSpotlight */ }
window.addEventListener('resize', positionTourSpotlight);
window.addEventListener('scroll', positionTourSpotlight, true);
```

Preserve the CSS spotlight and real-control interaction. Introduce a shared requestAnimationFrame-coalesced measurement/clamp scheduler here for resize, scroll, and DPI/layout changes; do not use SVG masking or restart a tour step.

### `app/ui/app.css` (component, transform)

**Analog:** Existing tokenized visual language and CSS spotlight.

**Preserved motion/token pattern** (`app/ui/app.css:21-55`, `137-167`):

```css
.lp-hit{transition:transform var(--motion-fast) var(--motion-spring),box-shadow var(--motion-fast) var(--motion-ease),background var(--motion-fast) var(--motion-ease)}
.lp-hit:hover{transform:translateY(-1px)}
.lp-hit:active{transform:translateY(1px)}

--motion-fast:90ms;
--motion-snap:110ms;
--motion-seat:140ms;
--motion-normal:160ms;
--motion-slow:220ms;
--motion-spring:cubic-bezier(.2,0,0,1);
```

Preserve these tokens, hard shadows, and transform-only press behavior. Phase 04 CSS adds reliability rules only; it must not introduce palette fades/crossfades or new animation vocabulary.

**Theme and navigation pattern** (`170-214`, `235-255`):

```css
[data-theme="dark"]{ --bg:#16191F; --panel:#1F242C; /* token override set */ }

main [data-screen]:not([hidden]){
  animation:lprail var(--motion-seat) var(--motion-spring) both}
```

Keep palettes in root custom-property scopes and let JavaScript alter only `data-theme`; the JS active-screen guard is what prevents this selector from replaying on backend updates.

**QtWebEngine-safe spotlight pattern** (`721-747`):

```css
#guided-tour-overlay{position:fixed;inset:0;z-index:170;pointer-events:none}
#tour-spotlight-box{position:fixed;left:0;top:0;width:0;height:0;
  box-shadow:0 0 0 9999px rgba(8,10,14,.65),0 0 25px rgba(255,122,0,.6);pointer-events:none}
#guided-tour-card{position:fixed;right:24px;bottom:24px;
  width:min(360px,calc(100vw - 32px));pointer-events:auto}
@media (max-width:640px){#guided-tour-card{left:16px;right:16px;bottom:16px;width:auto}}
```

Add tooltip/overflow and very-small-window rules beside these existing responsive/overlay rules. Overlay remains pointer-transparent; only card and lifted real target may receive interaction.

### `app/ui/index.html` (component, request-response)

**Analog:** Existing semantic settings and guided-tour markup.

**Long-value target markup** (`app/ui/index.html:488-493`):

```html
<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13px;margin-bottom:9px">
  <span style="color:var(--muted);white-space:nowrap">Installed model</span>
  <span id="ai-model-name" style="font:700 12px 'JetBrains Mono'">—</span>
</div>
```

Add minimal semantic hooks/ARIA (`tabindex`, `aria-describedby`, stable tooltip ID) to this existing display; tooltip content must not alter the field’s layout.

**Overlay markup pattern** (`568-590`):

```html
<div id="guided-tour-overlay" hidden aria-live="polite" aria-atomic="true">
  <div id="tour-spotlight-box" aria-hidden="true"></div>
  <section id="guided-tour-card" aria-labelledby="tour-title">
    <button id="btn-tour-exit" class="lp-hit lp-press-sm" type="button">Exit demo</button>
  </section>
</div>
```

Keep the existing IDs, card semantics, and real controls. Add only hooks needed for focus containment/tooltip behavior—no duplicate overlays or state markup.

### `app/desktop/bridge.py` (bridge/service, request-response)

**Analog:** Existing QSettings bootstrap payload and generic setting persistence.

**Bootstrap/default pattern** (`app/desktop/bridge.py:305-350`, especially `323`):

```python
return json.dumps({
    # ...other bootstrap state...
    "theme": self._settings.value("theme", "dark"),
})

def set_setting(self, key: str, value):
    self._settings.setValue(key, value)
```

Change only the canonical fallback to `"light"`; retain `QSettings` and the existing generic `set_setting` bridge path so a user selection persists immediately and startup gets the saved value before the view becomes visible.

### `tests/test_ui_tokens_motion_responsive.py` (test, transform)

**Analog:** Existing source-loaded structural invariants and direct token parsing (`1-52`, `188-289`).

```python
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "app", "ui", "app.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()

def test_progress_fills_animate_transform_not_width():
    body = _block(".lp-fill")
    assert "transform-origin:left" in body
    assert "transition:width" not in body
```

Extend this file with explicit VIS-01/VIS-03/VIS-04 structural guards: preserved timings/press tokens, idempotent navigation/animation-event reducer seam, no horizontal overflow CSS rules, and tooltip ARIA/non-reflow hooks.

### `tests/test_webview_theme.py` (test, request-response)

**Analog:** Existing compact cross-file static theme contract (`11-45`).

```python
CSS = open(os.path.join(ROOT, "app", "ui", "app.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()

def test_theme_button_active_uses_secondary_surface():
    assert ".lp-theme-btn.active{border-color:var(--secondary-border)" in CSS
```

Extend this same file (rather than creating a new framework) with WebEngine/bridge startup coverage: fresh Light bootstrap before visibility, one root `data-theme` mutation, and immediate one-value persistence on user action.

### `tests/test_guided_tour.py` (test, event-driven)

**Analog:** Existing Node-executed pure reducer model plus source-level DOM/CSS assertions (`1-35`, `352-419`).

```python
def test_css_spotlight_is_pointer_transparent_and_has_no_svg_mask():
    assert 'id="guided-tour-overlay"' in html
    assert "<mask" not in html.lower()
    assert "#guided-tour-overlay{position:fixed;inset:0;z-index:170;pointer-events:none}" in css
    assert "pointer-events:auto!important" in css
```

```python
assert "window.addEventListener('resize', positionTourSpotlight)" in js
assert "window.addEventListener('scroll', positionTourSpotlight, true)" in js
assert 'id="btn-tour-exit"' in html
```

Extend these reducers/DOM checks with focus-cycle containment, reachable Exit, rAF geometry scheduling, target reveal, card/spotlight viewport clamping, and resize/scroll/DPI tracking. Preserve the no-SVG assertion.

## Shared Patterns

### Theme lifecycle
**Sources:** `app/desktop/bridge.py:323,339`; `app/ui/index.html:16`; `app/ui/app.js:1888-1898,3896-3951,3998`  
**Apply to:** bridge default, initial HTML root, JS bootstrap, all theme controls.

Use one persisted QSettings value and one root `#app[data-theme]` mutation. Fresh profile resolves to Light before WebEngine visibility; user action persists through `set_setting` immediately. Do not create per-control theme classes or wait for global Save.

### Page-motion ownership
**Sources:** `app/ui/app.js:1845-1886`; `app/ui/app.css:241-255`  
**Apply to:** navigation, all backend/state render paths, overlay closures.

Only `setScreen` for a genuinely different name may trigger `LP.motion.nav`/the `lprail` selector. All status/progress/options/overlay updates mutate their local surfaces in place.

### Overlay geometry and focus
**Sources:** `app/ui/app.js:1982,2467-2521`; `app/ui/app.css:721-747`; `app/ui/index.html:568-590`  
**Apply to:** guided tour, setup gate, tooltip.

Measure real DOM geometry, schedule writes per animation frame, clamp inside the viewport, and trap focus only while the relevant overlay is active. CSS dimmer stays pointer-transparent; do not introduce SVG masks.

### Test style
**Sources:** `tests/test_ui_tokens_motion_responsive.py:1-289`; `tests/test_webview_theme.py:11-45`; `tests/test_guided_tour.py:352-419`  
**Apply to:** all Phase 04 verification.

Extend the three existing files with source/DOM assertions, Node reducers, and QtWebEngine integration helpers. Capture console errors in the WebEngine fixture; no parallel test framework.

## No Analog Found

None. Every planned responsibility extends an existing shipping seam.

## Metadata

**Analog search scope:** `app/ui/`, `app/desktop/`, `tests/`  
**Files scanned:** 7 primary files plus related UI bridge/markup sources  
**Pattern extraction date:** 2026-07-29
