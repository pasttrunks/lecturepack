"""start_processing must hand the resolved job to the CONTROLLER, not just resolve it.

The adapter owns the job the workspace shows (``current_job``); the controller owns
the job the pipeline runs (``controller.job``). They are separate objects, and only
the internal queue-promotion path (``_promote_next``) ever synced them.

So starting an already-imported lecture from a Home card resolved a job, logged its
product mode, and then died inside ``run_pipeline()`` with
"Pipeline failed: No job loaded." A fresh import masked it, because the import path
had already called ``set_job`` itself -- which is why the packaged acceptance run
(import -> process) passed while starting an existing lecture failed.

Observed in the packaged app, from its own log:

    [review]  opened job Heinrich Schliemann ...
    [engine]  Product mode: Study Pack (slides + transcript)
    [error]   Pipeline failed: No job loaded.

These tests pin the sync at the single point every caller goes through.
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

    def set_job(self, job):
        self.set_job_calls.append(job)
        self.job = job


class _FakeJob:
    def __init__(self, job_id="job-a"):
        self.job_id = job_id
        self.settings = {}
        self.saved = 0
        self._lifecycle = None

    def get_lifecycle(self):
        from lecturepack.models import job_lifecycle as _lc
        return self._lifecycle if self._lifecycle is not None else _lc.NEW

    def set_lifecycle(self, value):
        self._lifecycle = value

    def save(self):
        self.saved += 1


class _FakeQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, job_id):
        self.enqueued.append(job_id)


def _adapter(controller, job, current_job=None):
    """A real LecturePackAdapter with only what start_processing's early path touches.

    Allocated without ``__init__`` deliberately: constructing the real adapter drags
    in Qt wiring, the engine registry and the runtime bootstrap, none of which this
    contract depends on. ``LecturePackAdapter.__new__`` rather than
    ``object.__new__`` because it is a QObject subclass.
    """
    from desktop.engine_adapter import LecturePackAdapter

    a = LecturePackAdapter.__new__(LecturePackAdapter)
    a._demo_session = None
    a._pending_job = job
    a.current_job = current_job
    a.controller = controller
    a.queue = _FakeQueue()
    a.logs = []
    # Force the "another job is running" branch: it returns early, AFTER the
    # controller sync, so the contract can be checked without running a pipeline.
    a.is_processing = lambda: True
    a._slide_detection_preset = lambda: "balanced"
    a._log = lambda tag, text, kind=None: a.logs.append((tag, text))
    a._push_queue = lambda: None
    a._push_jobs = lambda: None
    return a


def test_start_processing_gives_the_controller_the_resolved_job():
    """The bug: a job resolved here never reached the controller."""
    controller = _FakeController(job=None)
    job = _FakeJob("job-a")
    adapter = _adapter(controller, job)

    adapter.start_processing("study")

    assert controller.job is job, (
        "start_processing resolved a job but left controller.job unset -- "
        "run_pipeline() would fail with 'No job loaded.'"
    )
    assert controller.set_job_calls == [job]


def test_start_processing_syncs_when_the_controller_holds_a_different_job():
    """A stale controller job is worse than none: the wrong lecture would run."""
    stale = _FakeJob("job-stale")
    controller = _FakeController(job=stale)
    job = _FakeJob("job-b")
    adapter = _adapter(controller, job)

    adapter.start_processing("study")

    assert controller.job is job
    assert controller.set_job_calls == [job]


def test_restarting_the_same_job_does_not_reset_controller_state():
    """Guarded on job_id: set_job re-syncs whisper/backend state, so calling it
    again mid-run on the SAME job would disturb a live pipeline for nothing."""
    job = _FakeJob("job-c")
    controller = _FakeController(job=job)
    # current_job left None so the queue-behind branch still returns early; the
    # point here is the guard, which compares against controller.job.
    adapter = _adapter(controller, job, current_job=None)

    adapter.start_processing("study")

    assert controller.set_job_calls == [], "re-synced a controller that already had this job"
    assert controller.job is job


def test_no_job_resolved_still_reports_and_does_not_touch_the_controller():
    controller = _FakeController(job=None)
    adapter = _adapter(controller, None, current_job=None)

    adapter.start_processing("study")

    assert controller.set_job_calls == []
    assert any("No video selected" in text for _tag, text in adapter.logs)
