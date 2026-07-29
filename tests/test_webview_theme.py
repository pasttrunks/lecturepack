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
BRIDGE = open(os.path.join(ROOT, "app", "desktop", "bridge.py"), encoding="utf-8").read()
MAIN = open(os.path.join(ROOT, "app", "desktop", "main.py"), encoding="utf-8").read()


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


def test_theme_bootstrap_defaults_to_light_without_persisting_a_bootstrap_event():
    assert 'data-theme="light"' in HTML
    assert 'self._settings.value("theme", "light")' in BRIDGE
    assert "applyTheme('light', false);" in JS
    assert "if (persist) lpBridge.call('set_setting', 'theme', theme);" in JS
    assert "def initial_theme(self) -> str:" in BRIDGE


def test_theme_notifications_are_idempotent_and_do_not_echo_to_settings():
    assert "if (LP.state.theme === theme && $('app').dataset.theme === theme) return;" in JS
    assert "if (s.theme) applyTheme(s.theme, false);" in JS
    assert "if (b.theme) applyTheme(b.theme, false);" in JS


def test_main_injects_sanitized_saved_theme_before_first_show():
    assert "self.view.loadFinished.connect(self._apply_initial_theme_before_show)" in MAIN
    assert "theme = json.dumps(self.backend.initial_theme())" in MAIN
    assert "runJavaScript(script, self._finish_initial_theme)" in MAIN
    assert "win.show_when_ready()" in MAIN
    assert "win.show()" not in MAIN[MAIN.index("win = MainWindow()"):]
