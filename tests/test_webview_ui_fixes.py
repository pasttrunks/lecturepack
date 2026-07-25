"""Regression guards for the beta.3 UI/UX audit findings (see BUG_LIST.md).

BUG-01  global shortcuts must not act while an overlay is open
BUG-02  overlays must trap Tab
BUG-04  no design-time placeholder job chrome may ship in index.html
BUG-06  the scheduler must refuse a past date/time

Static text assertions over the UI sources (no Qt needed), matching the style of
test_webview_theme.py. The behavioural half of BUG-01/02/04 was verified live in
a browser; these guards stop the markup/logic from silently regressing.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()


def _element_text(html: str, element_id: str) -> str:
    """Inner text of the (single-line) element carrying ``id=element_id``."""
    m = re.search(r'id="%s"[^>]*>(.*?)<' % re.escape(element_id), html, re.S)
    assert m, f"element #{element_id} not found"
    return m.group(1).strip()


# --------------------------- BUG-04 ---------------------------------------

def test_no_fake_job_name_in_shipped_markup():
    """A fresh profile must not claim a lecture the user never imported."""
    # (The only permitted mention is the explanatory comment about the old bug.)
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
    assert "egypt_excerpt" not in body


def test_job_chrome_ships_idle_placeholders():
    assert _element_text(HTML, "side-job-name") == "No lecture loaded"
    assert _element_text(HTML, "proc-source-name") == "No lecture loaded"
    assert _element_text(HTML, "crumb-job") == "Home"
    assert _element_text(HTML, "status-label") == "Idle"


def test_no_fake_progress_in_shipped_markup():
    """No blinking activity dot or non-zero progress before a job exists."""
    assert _element_text(HTML, "status-pct") == ""
    assert _element_text(HTML, "proc-status-meta") == ""
    bar = re.search(r'id="status-bar"[^>]*style="([^"]*)"', HTML).group(1)
    assert "width:0%" in bar
    # the footer chip must not animate while idle
    chip = re.search(r'id="status-dot"[^>]*style="([^"]*)"', HTML).group(1)
    assert "lpblink" not in chip


def test_storage_widget_hidden_until_backend_reports():
    """It shipped a hardcoded 340 MB that no code ever wrote -- must start hidden."""
    m = re.search(r'<div id="storage-widget"([^>]*)>', HTML)
    assert m, "storage widget not found"
    assert "hidden" in m.group(1)
    assert _element_text(HTML, "storage-label") in ("—", "-", "")


def test_boot_resets_placeholder_chrome():
    assert "function resetJobChrome" in JS
    assert re.search(r"function boot\(\)\s*\{\s*resetJobChrome\(\);", JS)


# --------------------------- BUG-01 / BUG-02 -------------------------------

def test_shortcut_handler_defers_to_open_overlay():
    """The digit/F map must be unreachable while an overlay owns the keyboard."""
    handler = JS.split("window.addEventListener('keydown'", 1)[1]
    guard = handler.index("topOverlay()")
    shortcuts = handler.index("var map = {")
    assert guard < shortcuts, "overlay guard must precede the shortcut map"


def test_overlay_helpers_exist():
    for fn in ("function topOverlay", "function trapFocus",
               "function focusFirst", "function visibleFocusable"):
        assert fn in JS, f"missing {fn}"


def test_tab_is_trapped_when_overlay_open():
    handler = JS.split("window.addEventListener('keydown'", 1)[1]
    assert re.search(r"if \(overlay\) \{\s*if \(e\.key === 'Tab'\) trapFocus\(overlay, e\);",
                     handler)


def test_trap_focus_prevents_default_at_both_edges():
    body = JS.split("function trapFocus", 1)[1].split("\n  }", 1)[0]
    assert body.count("e.preventDefault()") >= 3   # empty, forward wrap, back wrap
    assert "e.shiftKey" in body


def test_modals_are_marked_as_dialogs():
    assert HTML.count('role="dialog"') >= 2
    assert HTML.count('aria-modal="true"') >= 2
    assert "ov.setAttribute('role', 'dialog')" in JS      # dynamic lpModal


def test_select_elements_count_as_editing_context():
    """Typing in the scheduler's <select> must not trigger screen shortcuts."""
    m = re.search(r"var editing = /([A-Z|]+)/\.test\(tag\)", JS)
    assert m and "SELECT" in m.group(1)


# --------------------------- BUG-06 ---------------------------------------

def test_scheduler_input_has_min_attribute():
    assert 'type="datetime-local" min="' in JS
    assert "localNowValue()" in JS


def test_scheduler_rejects_past_time_in_handler():
    """`min` is advisory -- typed input bypasses it, so the handler must recheck."""
    handler = JS.split("function scheduleJobDialog", 1)[1]
    assert re.search(r"if \(when < localNowValue\(\)\)", handler)
    assert "Pick a time in the future" in handler


def test_local_now_value_uses_local_time_not_utc():
    body = JS.split("function localNowValue", 1)[1].split("\n  }", 1)[0]
    assert "getFullYear" in body and "getHours" in body
    assert "toISOString" not in body, "toISOString would shift by the UTC offset"
