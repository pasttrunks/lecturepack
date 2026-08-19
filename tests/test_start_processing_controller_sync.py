"""start_processing must hand the pipeline its job -- and ONLY when it starts one.

Two bugs live in this one line of sync, and the second was caused by the fix for
the first.

DEF-033. The adapter owns the job the workspace shows (``current_job``); the
controller owns the job the pipeline runs (``controller.job``). Separate objects,
and only ``_promote_next`` ever synced them, so starting an already-imported
lecture resolved a job, logged its product mode, then died inside
``run_pipeline()``:

    [review]  opened job Heinrich Schliemann ...
    [engine]  Product mode: Study Pack (slides + transcript)
    [error]   Pipeline failed: No job loaded.

DEF-035. The first fix synced too early -- above the "another job is running,
queue this one" return. The controller keeps NO local copy of its job:
``run_next_stage`` and ``_handle_backend_detected`` read and WRITE through
``self.job`` for the whole run. So starting lecture B while A was mid-pipeline
pointed the running pipeline at B, and A's stage writes, ``set_stage_status`` and
``save()`` landed in B -- a real lecture, silently overwritten. Nothing failed
loudly; B's slides/transcript/Study pack were simply wrong afterwards.

The original tests asserted the broken behaviour: they forced ``is_processing()``
true precisely to reach an early return, then asserted ``set_job`` HAD been
called. A test can pin a bug as firmly as it pins a fix.
"""

import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class _FakeController:
    def __init__(self, job=None):
        self.job = job
        self.set_job_calls = []
        self.run_calls = 0

    def set_job(self, job):
        self.set_job_calls.append(job)
        self.job = job

    def run_pipeline(self):
        self.run_calls += 1


class _FakeJob:
    def __init__(self, job_id="job-a"):
        self.job_id = job_id
        self.settings = {}
        self.manifest = {"title": job_id}
        self.saved = 0
        self._lifecycle = None

    def get_lifecycle(self):
        from lecturepack.models import job_lifecycle as _lc
        return self._lifecycle if self._lifecycle is not None else _lc.NEW

    def set_lifecycle(self, value, owner=None):
        self._lifecycle = value

    def save(self):
        self.saved += 1


class _FakeQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, job_id):
        self.enqueued.append(job_id)


class _FakeWin:
    def __init__(self):
        self.started = 0

    def on_job_started(self):
        self.started += 1


def _adapter(controller, job, current_job=None, *, processing=False):
    """A real LecturePackAdapter with only what start_processing touches.

    Allocated without ``__init__``: constructing the real adapter drags in Qt
    wiring, the engine registry and the runtime bootstrap, none of which this
    contract depends on. ``LecturePackAdapter.__new__`` because it is a QObject.
    """
    from desktop.engine_adapter import LecturePackAdapter

    a = LecturePackAdapter.__new__(LecturePackAdapter)
    a._demo_session = None
    a._pending_job = job
    a.current_job = current_job
    a.controller = controller
    a.queue = _FakeQueue()
    a.win = _FakeWin()
    a.logs = []
    a.emitted = []
    a._stages = []
    a._pipeline_start = None
    a.is_processing = lambda: processing
    a._slide_detection_preset = lambda: "balanced"
    a._log = lambda tag, text, kind=None: a.logs.append((tag, text))
    a._emit = lambda name, payload=None: a.emitted.append((name, payload))
    a._push_queue = lambda: None
    a._push_jobs = lambda: None
    a._render_pipeline = lambda title=None, meta=None: None
    a._bundled_demo_model_path = lambda cfg: ""
    a._session_id = "test-session"          # stamped into the RUNNING lifecycle owner
    a.config = type("_Cfg", (), {"get": staticmethod(lambda k, d=None: d)})()
    return a


# "slides" keeps needs_whisper False, so the run path is reachable without a
# resolvable whisper exe or model -- the sync point sits below that bail.
RUNS = "slides"


def test_a_started_lecture_reaches_the_controller():
    """DEF-033: the pipeline ran against nothing."""
    controller = _FakeController(job=None)
    job = _FakeJob("job-a")
    adapter = _adapter(controller, job)

    adapter.start_processing(RUNS)

    assert controller.job is job
    assert controller.set_job_calls == [job]
    assert controller.run_calls == 1, "the pipeline should have been started"


def test_queueing_behind_a_running_job_must_not_touch_the_controller():
    """DEF-035, the regression that matters: this is silent data corruption.

    A is mid-pipeline. The user starts B. B must be queued and the RUNNING
    pipeline must keep writing to A -- if controller.job becomes B, A's stage
    output overwrites B's real slides, transcript and Study pack.
    """
    running = _FakeJob("job-A-running")
    controller = _FakeController(job=running)
    incoming = _FakeJob("job-B-incoming")
    adapter = _adapter(controller, incoming, current_job=running, processing=True)

    adapter.start_processing(RUNS)

    assert controller.job is running, (
        "a running pipeline was redirected at the lecture the user started second; "
        "its stage writes and save() would land in the wrong lecture"
    )
    assert controller.set_job_calls == []
    assert controller.run_calls == 0
    assert adapter.queue.enqueued == ["job-B-incoming"], "B should have been queued"


def test_restarting_the_same_job_does_not_reset_controller_state():
    """set_job re-syncs whisper/backend state, so re-calling it on the SAME job
    would disturb a live run for nothing."""
    job = _FakeJob("job-c")
    controller = _FakeController(job=job)
    adapter = _adapter(controller, job)

    adapter.start_processing(RUNS)

    assert controller.set_job_calls == []
    assert controller.job is job
    assert controller.run_calls == 1


def test_no_job_resolved_still_reports_and_does_not_touch_the_controller():
    controller = _FakeController(job=None)
    adapter = _adapter(controller, None, current_job=None)

    adapter.start_processing(RUNS)

    assert controller.set_job_calls == []
    assert controller.run_calls == 0
    assert any("No video selected" in text for _tag, text in adapter.logs)


def test_the_sync_sits_below_every_early_return():
    """Structural guard: the ordering IS the fix.

    Pinned as source order too, because the behavioural test above can only cover
    the early returns it can reach -- a third bail added above the sync later
    would reintroduce DEF-035 silently.
    """
    import inspect
    from desktop.engine_adapter import LecturePackAdapter

    src, _ = inspect.getsourcelines(LecturePackAdapter.start_processing)
    sync_at = next(i for i, line in enumerate(src) if "self.controller.set_job(job)" in line)
    returns_above = [i for i, line in enumerate(src[:sync_at]) if line.strip() == "return"]
    run_at = next(i for i, line in enumerate(src) if "self.controller.run_pipeline()" in line)

    assert returns_above, "expected the early-return bails to precede the sync"
    assert sync_at < run_at, "the controller must be synced before the pipeline runs"
    assert not [
        i for i, line in enumerate(src[sync_at:run_at], start=sync_at)
        if line.strip() == "return"
    ], "a return between the sync and run_pipeline would leave the controller redirected"
