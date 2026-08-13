"""Two reported defects at the front door: black thumbnails and a silent drop.

Both were found by measuring, not by reading code.

THUMBNAILS. `_generate_poster` grabbed frame ZERO. Real lectures -- recordings
and downloaded videos alike -- almost always fade in from black or open on a
title card, so the poster was generated correctly and was a picture of nothing:
four of five cards in a reported queue were black rectangles. Measured on the
user's own files with ffmpeg: "The Conman Who Discovered Troy" (46 min) had a
mean luma of 0.0 at frame zero and 110.1 after seeking in. Two other lectures
were already fine (229, 245) and stayed fine.

SILENT DROP. `importDroppedFiles` returned in silence when the drop carried no
file at all, so the window swallowed it and drag-and-drop read as completely
dead. Windows delivers nothing when the drag starts in a virtual shell view --
Explorer's Home/Recent list, Gallery, or an undownloaded cloud placeholder --
because those entries have no path to hand over. The reported video shows a
drag starting from exactly that view.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def _poster() -> str:
    body = SIDECAR.split("def _generate_poster(", 1)[1]
    return body.split("\n    @staticmethod", 1)[0]


def test_the_poster_is_not_taken_from_frame_zero():
    poster = _poster()
    args = poster.split("process.start(ffmpeg, [", 1)[1].split("])", 1)[0]
    assert '"-ss"' in args, "frame zero is black on most real lectures"
    # -ss must precede -i, or ffmpeg decodes from the start and the seek is slow.
    assert args.index('"-ss"') < args.index('"-i"')


def test_the_seek_lands_in_content_for_both_short_and_long_lectures():
    poster = _poster()
    assert "duration * 0.10" in poster
    # Clamped: 10% of a 90s clip is too early, 10% of a 2h lecture too late.
    assert "min(30.0, max(2.0," in poster
    # A missing or unparsable duration must still produce a poster.
    assert "else 3.0" in poster
    assert "except (TypeError, ValueError)" in poster


def test_the_frame_is_chosen_rather_than_taken_blind():
    """A hard cut to black at the seek point would otherwise win anyway."""
    poster = _poster()
    assert '"thumbnail,scale=' in poster, (
        "the thumbnail filter picks the most representative frame of the batch"
    )


def test_a_poster_failure_still_cannot_block_the_import():
    poster = _poster()
    assert "except Exception:" in poster
    assert "waitForFinished" in poster, "a hung ffmpeg must not wedge the import"


def _dropped() -> str:
    body = APP_JS.split("function importDroppedFiles(", 1)[1]
    return body.split("\n  function ", 1)[0]


def test_a_drop_carrying_no_file_explains_itself():
    fn = _dropped()
    empty = fn.split("if (!files || !files.length)", 1)
    assert len(empty) == 2, "the empty-drop case must be handled on its own"
    # It must not be the old silent `return`.
    branch = empty[1][:400]
    assert "toast(" in branch, "a swallowed drop is indistinguishable from a broken app"
    assert "Browse for video" in branch, "say what to do instead"


def test_the_unresolvable_path_case_names_the_likely_cause():
    fn = _dropped()
    branch = fn.split("if (!paths.length)", 1)[1][:400]
    assert "toast(" in branch
    assert "Recent" in branch, "name the Explorer view that sends nothing"


@pytest.mark.parametrize("guard", ["importingFile", "!files"])
def test_the_reentrancy_guard_survived_the_change(guard):
    """An in-flight import must still not be interrupted by a second drop."""
    fn = _dropped()
    assert guard in fn
    # importingFile is checked before anything else, so a second drop during an
    # import returns quietly rather than toasting a confusing message.
    assert fn.index("importingFile") < fn.index("!files")
