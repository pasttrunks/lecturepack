"""The slide review viewer: thumbnails you can actually read.

Reviewing slides means deciding, for each of (in the reported case) 212
candidate frames, whether it belongs in the exported study pack. That judgement
needs a legible thumbnail. The shipped rail rendered them at 60x38px, or
82x52px in "Roomy" -- at which a lecture slide is an unreadable smear, and the
two density modes differed by 22px and a 1px font, so the control did not
visibly change density either.

The replacement: one adaptive layout with a full-width 16:9 thumbnail (roughly
four times the linear size), `contain` instead of `cover` so nothing is cropped,
and a real three-stop size control in the All slides overlay.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
CSS = (UI / "app.css").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
HTML = (UI / "index.html").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    """The declaration block of the first rule matching `selector` exactly."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"no CSS rule for {selector}"
    return match.group(1)


def test_the_rail_thumbnail_is_a_full_width_16_9_box():
    thumb = _rule(".lp-slide-rail-card .lp-slide-card-thumb")
    assert "width:100%" in thumb, "the thumbnail must span the rail, not sit at 60px"
    assert "aspect-ratio:16/9" in thumb
    # A fixed pixel height would defeat the point.
    assert not re.search(r"height:\s*\d+px", thumb)


def test_thumbnails_are_never_cropped():
    """object-fit:cover silently cut the edges off every slide."""
    for selector in (".lp-slide-rail-card .lp-slide-card-thumb img",
                     ".lp-all-slide-image img"):
        assert "object-fit:contain" in _rule(selector)


def test_the_fake_density_toggle_is_gone_everywhere():
    for artefact in ("data-slide-density", "lp-slide-density"):
        assert artefact not in HTML, f"{artefact} still in the markup"
        assert artefact not in CSS, f"{artefact} still in the stylesheet"
    assert "slideDensity" not in JS, "dead density state left behind"


def test_the_rail_adapts_instead_of_offering_named_modes():
    rule = _rule("#slide-list")
    assert "display:grid" in rule
    assert "repeat(auto-fill," in rule, (
        "the rail should adapt its column count, not switch between named modes"
    )
    # The inline flex layout that used to override the stylesheet must be gone.
    assert 'id="slide-list" style=' not in HTML


def test_long_slide_lists_skip_offscreen_work_with_a_matched_placeholder():
    """212 cards, no virtualisation."""
    card = _rule(".lp-slide-rail-card")
    assert "content-visibility:auto" in card
    size = re.search(r"contain-intrinsic-size:auto (\d+)px", card)
    assert size, "content-visibility without an intrinsic size makes scrolling jump"
    assert 80 <= int(size.group(1)) <= 105, (
        f"placeholder {size.group(1)}px does not match the measured card height"
    )
    assert "flex:0 0 22px" in _rule(".lp-slide-card-meta")


def test_the_rail_scans_rather_than_filling_itself_with_one_slide():
    """The big slide frame beside the rail is where a frame is judged.

    An earlier pass made the rail cards so large that only three fitted, which
    duplicated the frame's job and made sweeping 212 slides slower, not faster.
    Measured at 1280x800: 2 columns x 5 rows = 10 cards visible, thumbnails
    115x65 against the old 60x38.
    """
    rule = _rule("#slide-list")
    track = re.search(r"minmax\((\d+)px,1fr\)", rule)
    assert track, "the rail should auto-fill a track, not use fixed columns"
    assert 100 <= int(track.group(1)) <= 140, (
        f"a {track.group(1)}px track fits too few slides to scan with"
    )
    # The caption has no room for more than the timestamp at this size.
    hidden = _rule(".lp-slide-rail-card .lp-slide-card-status,\n"
                   ".lp-slide-rail-card .lp-slide-card-idx")
    assert "display:none" in hidden


def test_the_overlay_size_control_has_three_visibly_different_stops():
    tiles = {}
    for size in ("s", "m", "l"):
        rule = _rule(f'.lp-all-slides-grid[data-size="{size}"]')
        match = re.search(r"--tile:(\d+)px", rule)
        assert match, f"size {size} sets no tile width"
        tiles[size] = int(match.group(1))
    assert tiles["s"] < tiles["m"] < tiles["l"]
    # The old Compact/Roomy pair differed by 22px and looked identical. Each
    # step here must be a change you can actually see.
    assert tiles["m"] - tiles["s"] >= 60
    assert tiles["l"] - tiles["m"] >= 60


def test_a_large_tile_cannot_overflow_a_narrow_window():
    rule = _rule(".lp-all-slides-grid")
    assert "minmax(min(100%,var(--tile)),1fr)" in rule, (
        "a 380px tile in a 320px pane must degrade to one column, not overflow"
    )
    assert "overflow-x:hidden" in rule


@pytest.mark.parametrize("size", ["s", "m", "l"])
def test_the_size_control_is_wired_and_remembered(size):
    assert f'data-slide-size="{size}"' in HTML
    assert "aria-pressed" in HTML.split('id="slide-size"', 1)[1][:600]
    assert "LP.state.slideSize" in JS
    assert "lecturepack.slideSize" in JS, "the choice should survive a restart"


def test_the_selection_box_is_lifted_out_of_the_card_flow():
    """Caught by measuring the real layout, not by reading the CSS.

    Turning the card into a column made the selection box -- a SIBLING of the
    caption, not a child -- lay out as a third row hanging below it. It now
    floats over the thumbnail. The rule must outrank
    `.lp-slide-card[data-state="rejected"] .lp-slide-check`, which sets
    position:relative; an equal-specificity selector silently lost to it and
    the box dropped back into flow on rejected cards only.
    """
    rule = _rule("#slide-list .lp-slide-rail-card .lp-slide-check")
    assert "position:absolute" in rule
    assert "margin-left:0" in rule, "the old auto margin would still push it"
    # Top-LEFT: the rejected corner flag owns the top-right.
    assert "left:6px" in rule and "top:6px" in rule


def test_the_scroll_placeholder_matches_the_measured_card_height():
    """Measured in Chromium: 91px at 1280 wide, 94px at 640.

    These are not estimates -- a placeholder that disagrees with the real height
    makes the scrollbar drift as rows stream in across 212 slides.
    """
    assert "contain-intrinsic-size:auto 92px" in _rule(".lp-slide-rail-card")


def test_a_rejected_slide_is_legible_without_colour():
    """Colour alone fails for a colour-blind student and in greyscale."""
    card = _rule('.lp-slide-card[data-state="rejected"]')
    assert "position:relative" in card
    # Corner flag, struck-through timestamp: two non-colour cues.
    assert re.search(r'\.lp-slide-card\[data-state="rejected"\]::after', CSS)
    assert "text-decoration:line-through" in _rule(
        '.lp-slide-card[data-state="rejected"] .lp-slide-card-time')


def test_a_rejected_thumbnail_stays_readable_enough_to_undo():
    """Dimming is applied to the wrapper ONLY.

    Applying it to the <img> as well multiplies (.55 x .55 = .30) and the
    rejected slide becomes unreadable -- which is exactly when you need to see
    it, because you are deciding whether to undo the rejection.
    """
    wrap = _rule('.lp-slide-rail-card[data-state="rejected"] .lp-slide-card-thumb')
    opacity = re.search(r"opacity:\.(\d+)", wrap)
    assert opacity, "the rejected thumbnail is not dimmed at all"
    assert int(opacity.group(1)[:2].ljust(2, "0")) >= 50, "dimmed past legibility"
    assert not re.search(
        r'\.lp-slide-card\[data-state="rejected"\][^{]*img\s*\{[^}]*opacity', CSS), (
        "opacity on the image as well as the wrapper multiplies"
    )


def test_the_new_slide_styling_obeys_AD_20():
    """No compositor-expensive effects: confirmed flicker on clean-install Windows."""
    rules = "\n".join(
        _rule(sel) for sel in (
            ".lp-slide-rail-card",
            ".lp-slide-rail-card .lp-slide-card-thumb",
            ".lp-slide-card-meta",
            "#slide-list",
            ".lp-all-slides-grid",
            "#slide-size button",
        ))
    for banned in ("transition", "animation", "will-change",
                   "filter:", "backdrop-filter"):
        assert banned not in rules, f"AD-20: {banned} must not appear here"
