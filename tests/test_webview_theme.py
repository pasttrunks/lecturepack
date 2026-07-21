"""Dark-theme secondary palette guard (§10).

Dark mode should use deep-blue/navy secondary surfaces with cyan text — not large
bright-cyan filled controls with white text (which are jarring / low-contrast).
These are static text assertions over the UI sources (no Qt needed).
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "app", "ui", "app.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()


def test_secondary_tokens_defined_for_both_themes():
    # one definition in :root (light), one in [data-theme="dark"]
    assert CSS.count("--secondary-surface:") >= 2
    for tok in ("--secondary-surface-hover", "--secondary-surface-active",
                "--secondary-border", "--secondary-text", "--secondary-icon",
                "--secondary-muted"):
        assert tok in CSS, f"missing token {tok}"


def test_dark_secondary_uses_spec_deep_blue():
    dark = CSS.split('[data-theme="dark"]', 1)[1]
    assert "--secondary-surface:#12303F" in dark
    assert "--secondary-text:#9DE8EE" in dark
    assert "--secondary-border:#2D7186" in dark


def test_no_bright_cyan_fill_with_white_text():
    # the jarring pattern: a bright --blue fill paired with white text
    bad = "background:var(--blue);color:#fff"
    for name, src in (("app.css", CSS), ("index.html", HTML), ("app.js", JS)):
        assert bad not in src, f"{name} still has a bright-cyan fill + white text"


def test_theme_button_active_uses_secondary_surface():
    assert ".lp-theme-btn.active{border-color:var(--secondary-border)" in CSS


def test_accent_swatches_removed():
    assert "Accent" not in HTML  # inert accent swatch row is gone
