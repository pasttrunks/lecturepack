"""2.1.1 — the four things reported against the shipped 2.1.0 build.

Static-source assertions in the established style: the shipped UI has no build
step, so app.js IS the artifact.

The drag defect here was originally filed as OBS-01 "seen once, not reproduced"
with a note suggesting the benign reading. That was wrong, and the correction
matters more than the fix: the "benign" explanation WAS the bug. Anything
filed as unreproduced should be re-examined the moment a second report arrives
with more detail.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def block(text: str, start: str, end: str) -> str:
    assert start in text, start
    rest = text.split(start, 1)[1]
    assert end in rest, end
    return rest.split(end, 1)[0]


# --------------------------------------------------------------------------- #
# BUG-60 — a queued lecture could not be dragged anywhere
# --------------------------------------------------------------------------- #
def test_bug60_being_queued_does_not_make_a_lecture_undraggable() -> None:
    """_jobIsDraggable used to be _jobIsQueueable, and BOTH halves of that end
    in `&& !_jobInQueue(j.id)`. Queue two lectures -- i.e. use the app the way
    it is meant to be used -- and the whole library went inert.

    Verified against the shipped 2.1.0 renderer before the fix: with two
    queued jobs, both Home cards rendered with NO data-lp-drag and NO grip.
    After the fix both carry `lecture` and a grip, on Home and in Subjects.
    """
    fn = block(JS, "function _jobIsDraggable(j)", "\n  }")
    assert "_jobInQueue" not in fn, (
        "draggability is gated on the queue again; filing a lecture under a "
        "subject is a label change and has nothing to do with the pipeline"
    )
    assert "_jobIsQueueable" not in fn, "the two predicates are conflated again"
    assert "return !!j && !!j.id;" in fn


def test_bug60_the_queueable_predicate_still_exists_and_still_excludes_the_queue() -> None:
    """Separating the two must not have loosened what Process accepts."""
    fn = block(JS, "function _jobIsQueueable(j)", "\n  }")
    assert "_jobIsReady(j) || _jobIsReprocessable(j)" in fn
    # Both halves still exclude anything already in the queue.
    for name in ("_jobIsReady", "_jobIsReprocessable"):
        body = block(JS, "function %s(j)" % name, "\n  }")
        assert "_jobInQueue" in body, name


def test_bug60_the_process_target_now_does_the_refusing() -> None:
    """A queued lecture can be picked up, so the Process target has to say no
    itself instead of relying on the card having been unliftable."""
    fn = block(JS, "if (desc.drop === 'process') {", "if (desc.drop === 'group') {")
    assert "_jobIsQueueable" in fn
    assert "paintProxy('bad')" in fn
    assert "is already in the queue" in fn


def test_bug60_subject_rows_use_the_same_predicate() -> None:
    """Subjects is the screen whose whole purpose is moving lectures between
    subjects; it must not have its own rule."""
    assert "var mDraggable = _jobIsDraggable(m);" in JS


# --------------------------------------------------------------------------- #
# BUG-61 — the drag shuddered because the list was rebuilt underneath it
# --------------------------------------------------------------------------- #
def test_bug61_lists_are_not_rebuilt_during_a_drag() -> None:
    """The queue re-renders on every queue_changed / pipeline_changed tick,
    which while a lecture transcribes is several times a second. Each rebuild
    threw away the carried row, the insert indicator and the candidate
    highlights, then recreated them a frame later -- the list flickering out
    from under a proxy that stays put."""
    for fn_name in ("renderQueue", "renderJobs", "renderSubjects"):
        # The guard must be the FIRST thing the renderer does, so look at the
        # opening few lines rather than the whole body.
        head = JS.split("function %s() {" % fn_name, 1)[1][:600]
        assert "deferWhileDragging('" in head, fn_name
    guard = block(JS, "function deferWhileDragging(key, fn)", "\n  }")
    assert "LPDrag.dragging()" in guard


def test_bug61_deferred_renders_run_when_the_drag_ends() -> None:
    """A deferral that never flushes is a worse bug than the flicker."""
    finish = block(JS, "    function finish() {\n      // A scroll that outlives", "\n    }")
    assert "flushDeferredRenders()" in finish
    # It must run AFTER active is cleared, or the renders defer themselves again.
    assert finish.index("active = null") < finish.index("flushDeferredRenders()")


# --------------------------------------------------------------------------- #
# BUG-62 — Process did not show the lecture that was actually running
# --------------------------------------------------------------------------- #
def test_bug62_process_follows_the_running_job_on_direct_navigation() -> None:
    fn = block(JS, "function followActiveProcessingJob()", "\n  }")
    assert "j.status === 'running'" in fn
    assert "next.id === LP.state.jobId" in fn, "must not re-select what is already shown"
    assert "silent: true" in fn, (
        "following the work is the app navigating, not the student; it must not "
        "overwrite their remembered per-lecture view state"
    )


def test_bug62_an_explicitly_chosen_lecture_is_not_overridden() -> None:
    """Clicking a queued lecture must land on THAT lecture and show its real
    state, queue position included -- not jump to whatever is running."""
    assert "_screenChangeCarriesJob = true;" in JS
    assert "if (!_screenChangeCarriesJob) followActiveProcessingJob();" in JS
    # The flag must be cleared even if setScreen throws.
    sel = block(JS, "if (opts.screen) {", "\n    }")
    assert "finally" in sel


def test_bug62_falls_back_to_the_head_of_the_queue() -> None:
    """Nothing running still beats showing an unrelated idle lecture."""
    fn = block(JS, "function followActiveProcessingJob()", "\n  }")
    assert "LP.data.queue" in fn
