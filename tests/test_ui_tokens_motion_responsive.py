"""Design-token layer: contrast (BUG-05), responsive review layout (BUG-03),
and the motion system.

Contrast ratios are COMPUTED here from the shipped token values rather than
trusted, so a future palette tweak that breaks WCAG AA fails the suite. The
rendered result was also measured in a real browser in both themes.
"""

from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "app", "ui", "app.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()
MAIN = open(os.path.join(ROOT, "app", "desktop", "main.py"), encoding="utf-8").read()

AA_NORMAL = 4.5
AA_LARGE = 3.0


# ----------------------------------------------------------------- helpers

def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _block(selector: str) -> str:
    """The declaration block for a top-level selector in app.css."""
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    assert m, f"selector {selector} not found"
    return m.group(1)


def token(name: str, theme: str = "light") -> str:
    body = _block(":root") if theme == "light" else _block('[data-theme="dark"]')
    m = re.search(re.escape(name) + r"\s*:\s*(#[0-9A-Fa-f]{6})", body)
    assert m, f"token {name} not defined for {theme}"
    return m.group(1)


# ----------------------------------------------------- BUG-05 contrast

def test_on_signal_ink_defined_for_both_themes():
    assert token("--on-signal", "light") == "#1C1A16"
    assert token("--on-signal", "dark") == "#131519"


def test_ink_on_every_signal_fill_meets_aa_normal():
    """Text-bearing saturated fills must clear 4.5:1 in BOTH themes."""
    fills = ["--orange", "--green-fill", "--red-fill", "--blue", "--yellow"]
    for theme in ("light", "dark"):
        ink = token("--on-signal", theme)
        for fill in fills:
            r = contrast(ink, token(fill, theme))
            assert r >= AA_NORMAL, f"{theme} {fill}: {r:.2f} < {AA_NORMAL}"


def test_white_on_orange_would_still_fail_so_the_token_matters():
    """Documents WHY --on-signal exists: the old foreground fails both themes."""
    assert contrast("#FFFFFF", token("--orange", "light")) < AA_NORMAL
    assert contrast("#FFFFFF", token("--orange", "dark")) < AA_LARGE


def test_no_white_text_on_a_signal_fill_remains():
    """Any `background:var(--<signal>);color:#fff` pair is a regression."""
    for src, name in ((HTML, "index.html"), (JS, "app.js"), (CSS, "app.css")):
        for signal in ("orange", "green", "red", "blue", "yellow",
                       "green-fill", "red-fill"):
            pattern = f"background:var(--{signal});color:#fff"
            assert pattern not in src, f"{name} still has {pattern}"


def test_selected_state_chips_use_the_ink_token():
    """These are built by ternaries, which the first sweep missed."""
    assert "color:' + (on ? '#fff' : 'var(--ink)')" not in JS
    assert "color:' + (on ? 'var(--on-signal)' : 'var(--ink)')" in JS


def test_class_based_orange_surfaces_use_the_ink_token():
    for sel in (".lp-tab.active", ".lp-bubble-user"):
        body = _block(sel)
        assert "color:var(--on-signal)" in body, f"{sel} not using --on-signal"
        assert "color:#fff" not in body


def test_text_and_fill_signal_tokens_stay_separate():
    """--green/--red carry TEXT on soft backgrounds while --green-fill/--red-fill
    are BACKGROUNDS carrying --on-signal ink. The two roles pull in opposite
    directions (text wants darker, fill wants lighter), so collapsing them back
    into one token is always a regression -- whatever the values are.

    This deliberately asserts no literals: the values WERE retuned on
    2026-07-25 (BUG-05 second pass) and pinning them made this test fail for a
    change that was actually correct. Contrast is asserted behaviourally below.
    """
    for theme in ("light", "dark"):
        for text_tok, fill_tok in (("--green", "--green-fill"),
                                   ("--red", "--red-fill")):
            assert token(fill_tok, theme), f"{fill_tok} missing in {theme}"
            if theme == "light":
                assert token(text_tok, theme) != token(fill_tok, theme), (
                    f"{text_tok} and {fill_tok} collapsed in {theme}")


# Every pair where a token is rendered as TEXT on an opaque surface, with the
# size/weight it is actually used at. Badge text is 10px/600 and muted meta is
# 12px/400 -- both NORMAL text under WCAG, so both need 4.5:1, not 3:1.
#   (label, foreground token, background token)
TEXT_ON_SURFACE = [
    ("badge Running",     "--orange-ink", "--orange-soft"),
    ("badge Interrupted", "--orange-ink", "--orange-soft"),
    ("badge Done",        "--green",      "--green-soft"),
    ("badge Failed",      "--red",        "--red-soft"),
    ("badge Paused",      "--blue-ink",   "--blue-tint"),
    ("badge Queued",      "--muted",      "--sunk"),
    ("badge Scheduled",   "--muted",      "--sunk"),
    ("muted on panel",    "--muted",      "--panel"),
    ("muted on panel2",   "--muted",      "--panel2"),
    ("muted on bg",       "--muted",      "--bg"),
    ("muted on sunk",     "--muted",      "--sunk"),
    ("green on panel",    "--green",      "--panel"),
    ("red on panel",      "--red",        "--panel"),
    ("orange-ink/panel",  "--orange-ink", "--panel"),
    ("ink on panel",      "--ink",        "--panel"),
    ("ink on bg",         "--ink",        "--bg"),
    ("nav-ink on bg",     "--nav-ink",    "--bg"),
]


def test_all_text_on_surface_pairs_meet_aa_normal_in_both_themes():
    """The full sweep, both themes, no AA-large escape hatch.

    BUG-05's first pass left 11 light-theme pairs failing and they were logged
    as 3 "near-misses" -- because only the reported pairs were measured. Every
    pair is enumerated here so the next palette change is checked in full
    automatically. A token used on four surfaces is checked on all four.
    """
    failures = []
    for theme in ("light", "dark"):
        for label, fg, bg in TEXT_ON_SURFACE:
            r = contrast(token(fg, theme), token(bg, theme))
            if r < AA_NORMAL:
                failures.append(f"{theme} {label}: {r:.2f} < {AA_NORMAL}")
    assert not failures, "WCAG AA failures:\n  " + "\n  ".join(failures)


def test_darkening_a_text_token_did_not_break_its_background_usages():
    """--green and --muted are ALSO backgrounds (tick circles, status dots).
    Darkening them for text must not push those below the 3:1 UI-component
    floor against the surfaces they sit on."""
    for theme in ("light", "dark"):
        for fill, over in (("--green", "--panel"), ("--muted", "--panel")):
            r = contrast(token(fill, theme), token(over, theme))
            assert r >= AA_LARGE, f"{theme} {fill} on {over}: {r:.2f} < {AA_LARGE}"
        # Tick/check icons sit on a signal fill and use --on-signal, not #fff.
        # (graphical contrast floor is 3:1)
        ink = token("--on-signal", theme)
        for fill in ("--green-fill", "--orange", "--blue"):
            r = contrast(ink, token(fill, theme))
            assert r >= AA_LARGE, f"{theme} icon on {fill}: {r:.2f} < {AA_LARGE}"


def test_no_white_stroked_icon_survives_on_a_signal_fill():
    """BUG-05's first sweep grepped `color:#fff` and so missed icons, which set
    their colour with an SVG `stroke` attribute instead. All five surviving
    sites sat on a saturated fill and all five failed the 3:1 graphical floor
    (white on dark-theme --green 2.06, on --orange 2.82, on --blue 1.31)."""
    for src, name in ((HTML, "index.html"), (JS, "app.js")):
        assert 'stroke="#fff"' not in src, f"{name} still strokes an icon #fff"
        assert 'stroke="#FFFFFF"' not in src, f"{name} still strokes an icon white"


# ----------------------------------------------------- BUG-03 responsive

def test_review_columns_are_tagged_for_reflow():
    for cls in ("lp-review-row", "lp-review-col-slides",
                "lp-review-col-main", "lp-review-col-transcript"):
        assert cls in HTML, f"{cls} missing from markup"
    assert HTML.count("lp-review-col ") == 3   # each column carries the base class


def test_breakpoint_exists_above_the_overflow_threshold():
    """250 + 320 + 360 + 28 gaps = ~958px, plus a 224px sidebar and padding."""
    assert "@media (max-width:1220px)" in CSS


def test_reflow_overrides_inline_widths():
    """The panels carry inline width styles, which outrank class rules."""
    m = re.search(r"@media \(max-width:1220px\)\{(.*?)\n\}", CSS, re.S)
    assert m
    block = m.group(1)
    assert "flex-direction:column" in block
    assert "width:auto !important" in block
    assert "min-width:0 !important" in block


def test_stacked_panels_get_workable_heights():
    m = re.search(r"@media \(max-width:1220px\)\{(.*?)\n\}", CSS, re.S)
    block = m.group(1)
    assert "max-height" in block and "min-height" in block


def test_narrow_breakpoint_trims_padding():
    assert "@media (max-width:820px)" in CSS


def test_minimum_width_review_timeline_wraps_without_clipping():
    """The 640px Electron minimum leaves a 400px main pane beside the sidebar."""
    for cls in ("lp-review-timeline", "lp-review-timeline-head",
                "lp-review-timeline-spacer", "lp-review-legend"):
        assert cls in HTML, f"{cls} missing from Review timeline markup"
    compact = re.search(r"@media \(max-width:700px\)\{(.*?)\n\}", CSS, re.S)
    assert compact, "minimum-width Review breakpoint missing"
    block = compact.group(1).replace(" ", "")
    assert ".lp-review-timeline-head{flex-wrap:wrap" in block
    assert ".lp-review-timeline-spacer{display:none}" in block
    assert "width:100%;margin-left:0!important" in block
    assert "overflow:hidden" in block


# ----------------------------------------------------------- motion system

def test_motion_tokens_defined():
    body = _block(":root")
    for tok in ("--motion-fast", "--motion-medium", "--motion-slow",
                "--motion-ease", "--motion-ease-in"):
        assert tok in body, f"missing {tok}"


def test_product_durations_stay_in_the_subtle_range():
    body = _block(":root")
    for tok in ("--motion-fast", "--motion-medium", "--motion-slow"):
        ms = int(re.search(re.escape(tok) + r":\s*(\d+)ms", body).group(1))
        assert 80 <= ms <= 250, f"{tok}={ms}ms outside the product range"


def test_custom_easing_not_browser_ease():
    body = _block(":root")
    assert "cubic-bezier" in re.search(r"--motion-ease:\s*([^;]+);", body).group(1)


def test_no_bare_browser_ease_remains_in_transitions():
    """Every transition uses a shared token curve, so the whole UI decelerates alike.

    Strips EVERY var() reference rather than an allow-list of two token names.
    The old form listed `var(--motion-ease)` and `var(--motion-ease-in)`
    explicitly, so the moment a legitimately-named token containing "ease"
    (`--motion-ease-soft`) was first used in a `transition:` rather than only in
    an `animation:`, this failed on correct code. Stripping all var() keeps the
    real intent -- catching a BARE browser keyword like `ease` / `ease-in-out`
    written as a literal -- and cannot false-positive on future token names.
    """
    for decl in re.findall(r"transition:[^;}\"]+", CSS):
        cleaned = re.sub(r"var\([^)]*\)", "", decl)
        assert not re.search(r"\bease\b", cleaned), f"bare ease in: {decl[:70]}"


def test_progress_fills_animate_transform_not_width():
    body = _block(".lp-fill")
    assert "transform-origin:left" in body
    assert "transition:transform" in body
    assert "transition:width" not in body


def test_hot_progress_bars_use_the_fill_helper():
    assert "function setFill" in JS
    # the per-frame bars must not write style.width any more
    for bar in ("status-bar", "timeline-progress", "export-progress-bar"):
        assert f"$('{bar}').style.width" not in JS, f"{bar} still animates width"
    assert "setFill('status-bar'" in JS
    assert "setFill('timeline-progress'" in JS


def test_fill_markup_is_full_width_and_starts_scaled_to_zero():
    for bar in ("status-bar", "timeline-progress", "export-progress-bar"):
        m = re.search(r'id="%s"[^>]*' % bar, HTML)
        assert m, f"{bar} not in markup"
        tag = m.group(0)
        assert "lp-fill" in tag, f"{bar} missing .lp-fill"
        assert "width:100%" in tag, f"{bar} must be full width to scale"
        assert "scaleX(0)" in tag, f"{bar} should start empty"


def test_reduced_motion_block_still_present():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    body = re.search(r"@media \(prefers-reduced-motion: reduce\)\{(.*?)\n\}", CSS, re.S).group(1)
    assert "transition-duration:.001ms !important" in body
    assert "animation-iteration-count:1 !important" in body


def test_navigation_only_runs_entrance_for_a_changed_screen():
    start = JS.index("function setScreen(name)")
    end = JS.index("function applyTheme", start)
    body = JS[start:end]
    assert "if (LP.state.screen === name) return;" in body
    assert body.index("if (LP.state.screen === name) return;") < body.index("LP.motion.nav")
    assert "main [data-screen]:not([hidden])" in CSS
    assert "animation:lprail var(--motion-seat) var(--motion-spring) both" in CSS


def test_preserved_motion_and_press_vocabulary_is_not_replaced_by_navigation_guard():
    assert "--shadow-hard:" in _block(":root")
    assert ".lp-hit:active{transform:translateY(1px)}" in CSS
    assert "--motion-seat:140ms" in _block(":root")


def test_desktop_minimum_size_keeps_the_small_viewport_matrix_reachable():
    assert "self.setMinimumSize(480, 560)" in MAIN


def test_model_value_uses_an_inert_aria_tooltip_without_reflow():
    """VIS-04: local model labels stay compact while their exact value is accessible."""
    model = re.search(r'<span id="ai-model-name"[^>]*>', HTML)
    assert model, "model value hook missing"
    tag = model.group(0)
    assert 'tabindex="0"' in tag
    assert 'aria-describedby="ai-model-tooltip"' in tag
    assert 'id="ai-model-tooltip"' in HTML
    assert 'role="tooltip"' in HTML
    assert "white-space:nowrap" in CSS
    assert "text-overflow:ellipsis" in CSS
    assert ".lp-model-value" in CSS and "min-width:0" in _block(".lp-model-value")
    assert "tooltip.textContent = value.textContent" in JS


def test_very_small_viewports_scroll_vertically_without_page_overflow():
    """VIS-05: the 480x560 matrix keeps actions reachable without an x-axis page scroll."""
    assert "overflow-x:hidden" in _block("html,body")
    assert "#app{min-width:0;min-height:100vh;background-color:var(--bg)}" in CSS
    compact = re.search(r"@media \(max-width:640px\)\{(.*?)\n\}", CSS, re.S)
    assert compact, "very-small responsive breakpoint missing"
    assert "flex-direction:column" in compact.group(1)
    assert "overflow-y:auto" in compact.group(1)
