"""The drag lifecycle: external file drops, internal lecture drags, auto-scroll.

Three separate bugs live in this area historically, so each end is pinned:

* ``dragenter`` MUST be cancelled or Chromium never treats the page as a drop
  target and ``drop`` is never dispatched at all. That is the "drag and drop
  does not work anywhere" bug; the handlers were always correct and simply
  never ran.
* The native Windows path comes from ``webUtils.getPathForFile``. ``file.path``
  is non-standard and gone in modern Electron, so depending on it silently
  imports nothing.
* A drag that starts at the bottom of a long library could never reach the
  Process tab: the pointer is held down, so there is no way to scroll and the
  drag ends the moment the button is released. One auto-scroll manager owns
  that, for internal and external drags alike.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
PRELOAD = (ROOT / "electron-spike" / "production-preload.js").read_text(encoding="utf-8")


def _drag_scroll_source() -> str:
    start = APP.index("var dragScroll = (function () {")
    return APP[start:start + 4200]


# ------------------------------------------------------------------ external
def test_dragenter_is_cancelled_on_the_window_in_capture():
    """Without this no drop event is ever dispatched, anywhere in the app."""
    assert "window.addEventListener('dragenter', function (e) { e.preventDefault(); }, true);" in APP


def test_every_stage_of_the_external_drop_lifecycle_is_handled():
    for stage in ("dragenter", "dragover", "dragleave", "drop"):
        assert f"dz.addEventListener('{stage}'" in APP, f"dropzone is missing {stage}"
    for stage in ("dragover", "dragleave", "drop"):
        assert f"window.addEventListener('{stage}'" in APP, f"window is missing {stage}"


def test_the_native_path_comes_from_web_utils_not_file_dot_path():
    assert "webUtils" in PRELOAD
    assert "return webUtils.getPathForFile(file);" in PRELOAD
    # The renderer must go through the bridge, never touch file.path itself.
    assert "lpBridge.pathForFile" in APP
    assert "files[i].path" not in APP


def test_a_drop_that_carries_no_readable_path_explains_itself():
    """Explorer's Home/Recent views hand over nothing; silence read as broken."""
    body = APP[APP.index("function importDroppedFiles(files)"):][:2200]
    assert "if (!files || !files.length)" in body
    assert "if (!paths.length)" in body
    assert body.count("toast(") >= 2


# ------------------------------------------------------------------ internal
def test_internal_drag_accepts_unstarted_and_finished_lectures_but_not_running():
    ready = APP[APP.index("function _jobIsReady(j)"):][:600]
    assert "j.status === 'running'" in ready, "a running lecture must never be draggable"
    for status in ("queued", "ready", "unstarted", "imported"):
        assert f"{status}: true" in APP or f"'{status}'" in ready

    reprocessable = APP[APP.index("var REPROCESSABLE_STATUSES"):][:260]
    for status in ("done", "failed", "cancelled", "interrupted"):
        assert f"{status}: true" in reprocessable


def test_dropping_a_finished_lecture_on_process_asks_before_reprocessing():
    body = APP[APP.index("processQueueTargets.forEach"):][:2600]
    assert "_jobIsReprocessable" in body
    assert "confirmReprocess(ids)" in body
    assert "if (again && !agreed) return;" in body, "declining must not queue anything"


def test_internal_drag_state_is_cleared_when_the_drag_ends():
    body = APP[APP.index("$('jobs-grid').addEventListener('dragend'"):][:700]
    assert "internalJobDragIds = []" in body
    assert "lp-existing-drop-hover" in body


# --------------------------------------------------------------- auto-scroll
def test_there_is_exactly_one_auto_scroll_manager():
    assert APP.count("var dragScroll = (function () {") == 1
    # No ad-hoc scrolling bolted onto the individual drop targets.
    for owner in ("dz.addEventListener('dragover'", "processQueueTarget.addEventListener('dragover'"):
        body = APP[APP.index(owner):][:700]
        assert "scrollTop +=" not in body, f"{owner} grew its own scrolling"


def test_auto_scroll_is_driven_by_an_animation_frame_not_by_mouse_movement():
    """dragover only fires while the pointer MOVES. A user waiting at the edge
    holds still, so an event-driven velocity stalls exactly when it is needed."""
    src = _drag_scroll_source()
    assert "requestAnimationFrame(step)" in src
    assert "cancelAnimationFrame" in src


def test_auto_scroll_resolves_the_container_from_the_pointer():
    """Nested scrollers (the Process queue panes) then work with no extra wiring."""
    src = _drag_scroll_source()
    assert "document.elementFromPoint" in src
    assert "overflowY" in src and "scrollHeight" in src


def test_auto_scroll_handles_both_axes_and_respects_the_ends():
    src = _drag_scroll_source()
    assert "scrollTop" in src and "scrollLeft" in src
    assert "target.scrollTop <= 0" in src, "must not fight a container already at the top"
    assert "scrollHeight - target.clientHeight" in src


def test_auto_scroll_is_wired_once_globally_in_capture():
    assert "window.addEventListener('dragover', function (e) {\n      dragScroll.update(e.clientX, e.clientY);\n    }, true);" in APP


def test_every_drag_ending_stops_the_scroll():
    """A scroll that outlives its drag runs away with the page."""
    for ending in ("drop", "dragend", "dragleave", "mouseup", "keydown"):
        assert f"window.addEventListener('{ending}'" in APP, f"no teardown on {ending}"
    tail = APP[APP.index("window.addEventListener('drop', function () { dragScroll.stop(); }, true);"):][:900]
    assert "dragScroll.stop()" in tail
    assert "Escape" in tail, "Esc cancels a drag without firing drop"
