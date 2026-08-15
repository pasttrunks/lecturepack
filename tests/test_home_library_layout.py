"""Home shows more lectures at once, and grouping is visible.

Reported: "the home layout only showcases one video one by one in a straight
line, I feel like we could showcase more videos and also make grouping more
apparent."

Two causes, both in the shipped code:

* the processing queue was a flex COLUMN, one full-width row per job, so five
  queued lectures filled the viewport; and the recent-jobs grid was pinned to
  `repeat(3,1fr)` at every window width; and
* the group header was suppressed whenever there was only one group -- the
  common case -- so grouping was invisible exactly when a student was first
  learning that lectures have groups at all.

The column rule is a FIXED floor rather than a viewport expression. A `17vw`
floor was tried and measured backwards: the grid sits in a container capped
near 1048px, so a 1920px window produced three columns while 1280px produced
four. Card size must follow its container, which 1fr already does.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "ui" / "app.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "app" / "ui" / "index.html").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    idx = CSS.index(selector + "{")
    return CSS[idx + len(selector) + 1:CSS.index("}", idx)]


def test_a_group_is_a_box_not_a_heading_over_a_run_of_cards():
    group = _rule(".lib-group")
    assert "border:2px solid" in group
    assert "background:var(--panel2)" in group, (
        "the group ground must differ from the --panel cards sitting on it"
    )
    head = _rule(".lib-group-head")
    assert "background:var(--sunk)" in head
    assert "position:sticky" in head, "the group label should survive scrolling"


def test_the_group_header_is_rendered_even_for_a_single_group():
    """The old build hid it exactly when it mattered most."""
    render = APP_JS.split("order.sort(", 1)[1].split("$('jobs-count')", 1)[0]
    assert "lib-group-code" in render
    assert "single" not in render, (
        "a single group must still be labelled; that suppression was the bug"
    )
    assert "lib-group-count" in render


def test_the_column_count_adapts_instead_of_being_pinned_to_three():
    grid = _rule(".lib-grid")
    assert "repeat(auto-fill,minmax(min(100%,var(--card)),1fr))" in grid
    assert "repeat(3,1fr)" not in APP_JS, "the hard-coded 3-column grid is gone"
    # min(100%, ...) is what stops a wide floor overflowing a narrow container.
    assert "min(100%" in grid


def test_the_card_floor_is_a_fixed_length_not_a_viewport_expression():
    grid = _rule(".lib-grid")
    card = re.search(r"--card:([^;]+);", grid)
    assert card is not None
    value = card.group(1).strip()
    assert "vw" not in value, (
        "a vw floor measured backwards: 1920 gave 3 columns, 1280 gave 4"
    )
    assert re.fullmatch(r"\d+px", value), f"expected a plain length, got {value}"
    assert 180 <= int(value.rstrip("px")) <= 220


def test_the_queue_is_a_grid_and_keeps_its_order_legible():
    assert 'id="queue-list" class="lib-grid"' in HTML, (
        "the inline flex column used to override the stylesheet"
    )
    render = APP_JS.split("list.innerHTML = q.map(", 1)[1].split("}).join('');", 1)[0]
    # A wrapping grid only keeps its order if the order is written down.
    assert "q-pos" in render
    assert "(i + 1)" in render


@pytest.mark.parametrize("action,label", [
    ("up", "Move up"), ("down", "Move down"), ("remove", "Remove from queue"),
])
def test_queue_reorder_controls_survive_the_rewrite(action, label):
    """Drag must never be the only path, and glyph buttons need real names."""
    render = APP_JS.split("list.innerHTML = q.map(", 1)[1].split("}).join('');", 1)[0]
    assert f"'{action}'" in render
    assert label in render, "a glyph-only button needs an accessible name"
    assert 'aria-label="' in render


def test_the_disabled_ends_are_disabled_rather_than_hidden():
    """A control that disappears at the ends makes the row shift between cards."""
    render = APP_JS.split("list.innerHTML = q.map(", 1)[1].split("}).join('');", 1)[0]
    assert "i === 0" in render and "i === q.length - 1" in render
    assert "disabled" in render
    assert "[disabled]" in _rule(".q-actions button") or "disabled" in CSS


def test_the_home_library_obeys_AD_20():
    block = CSS.split("--- Home library:", 1)[1].split("\n.lp-slide-rail-head", 1)[0]
    rules = block.split("*/", 1)[1]
    for banned in ("transition", "animation", "will-change", "backdrop-filter", "filter:"):
        assert banned not in rules, f"AD-20: {banned} must not appear here"


def test_the_queue_thumbnail_is_not_cropped():
    assert "object-fit:contain" in _rule(".q-thumb img")
    assert "aspect-ratio:16/9" in _rule(".q-thumb")
