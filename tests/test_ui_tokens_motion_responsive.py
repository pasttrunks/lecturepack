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


def test_shared_signal_tokens_were_not_retuned():
    """--green/--red are also TEXT colours on soft backgrounds; retuning them
    for fills would have broken the badges, hence the separate *-fill tokens."""
    assert token("--green", "light") == "#128A52"
    assert token("--red", "light") == "#D63A2C"
    assert token("--green-fill", "light") != token("--green", "light")
    assert token("--red-fill", "light") != token("--red", "light")


def test_badge_text_on_soft_background_still_readable_as_large_text():
    """Known gap: 10px badges only reach AA-large in the light theme."""
    r = contrast(token("--green", "light"), token("--green-soft", "light"))
    assert r >= AA_LARGE


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
    """Every transition uses the shared curve, so the whole UI decelerates alike."""
    for decl in re.findall(r"transition:[^;}\"]+", CSS):
        cleaned = decl.replace("var(--motion-ease-in)", "").replace("var(--motion-ease)", "")
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
