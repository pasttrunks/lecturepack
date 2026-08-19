"""A queued lecture must actually start when nothing else is running.

DEF-036. Reported as "nothing processes": drop a lecture on Process (or press the
queue's play button) and it sits at "Queued" forever while the footer says Idle and
Process says "No lecture loaded".

Cause: the queueing calls only ever touched the QUEUE.

    enqueue_job -> queue.enqueue(id); _push_queue()
    run_now     -> queue.run_now(id)  # == reorder(id, 0); _push_queue()

and the only thing that ever promoted a queued job into the active slot was
`_promote_next`, which is called exclusively when a job ENDS -- completion,
failure, cancel. On an already-idle app there was no ending job, so nothing ever
drained the queue. "Process now" was especially misleading: with nothing running
there is no "next" to be first in, so it reordered a list of one and returned.

Why the packaged drag gate missed it: it asserted the drop was ANNOUNCED
("queued for processing") and that app state changed. Both were true. It never
asserted the lecture actually started, which is the only thing the user wanted.
"""

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class _Queue:
    """Mirrors JobQueue's one-active-slot contract."""

    def __init__(self, queued=None, active=None):
        self.store = {"queue": list(queued or []), "active": active}
        self.pushed = 0

    @property
    def active(self):
        return self.store["active"]

    def queued(self):
        return list(self.store["queue"])

    def enqueue(self, job_id):
        if job_id not in self.store["queue"]:
            self.store["queue"].append(job_id)

    def run_now(self, job_id):
        if job_id in self.store["queue"]:
            self.store["queue"].remove(job_id)
            self.store["queue"].insert(0, job_id)

    def promote_next(self):
        if self.store["active"] is not None:
            return None
        if not self.store["queue"]:
            return None
        self.store["active"] = self.store["queue"].pop(0)
        return self.store["active"]

    def finish_active(self, job_id=None):
        if job_id is None or self.store["active"] == job_id:
            self.store["active"] = None


class _Controller:
    def __init__(self, active_stages=(), current_stage=None):
        self._active_stages = list(active_stages)
        self.current_stage = current_stage
        self.job = None
        self.set_job_calls = []

    def set_job(self, job):
        self.set_job_calls.append(job)
        self.job = job


class _Job:
    def __init__(self, job_id, source="C:/lectures/whatever.mp4"):
        self.job_id = job_id
        self.settings = {}
        self.manifest = {"title": job_id}
        if source:
            self.manifest["source"] = {"original_path": source}

    def save(self):
        pass


def _adapter(queue, controller, *, jobs=None, deferred=None):
    from desktop.engine_adapter import LecturePackAdapter

    a = LecturePackAdapter.__new__(LecturePackAdapter)
    a.queue = queue
    a.controller = controller
    a.current_job = None
    a._pending_job = None
    a.started = []
    a._reload_job = lambda jid: (jobs or {}).get(jid)
    a._slide_detection_preset = lambda: "balanced"
    a._push_queue = lambda: setattr(queue, "pushed", queue.pushed + 1)
    a._push_jobs = lambda: None
    a._set_active_job = lambda job: setattr(a, "current_job", job)
    a._mode_for_job = lambda job: "study"
    a.start_processing = lambda mode, preserve_preset=False: a.started.append(
        (mode, preserve_preset)
    )
    a.is_processing = lambda: bool(controller._active_stages)
    return a


@pytest.fixture(autouse=True)
def _run_deferred(monkeypatch):
    """QTimer.singleShot defers the start onto the Qt loop; run it inline."""
    from desktop import engine_adapter

    monkeypatch.setattr(
        engine_adapter.QTimer, "singleShot", staticmethod(lambda ms, fn: fn())
    )


def test_dropping_a_lecture_on_process_starts_it():
    """The reported bug: dropping a lecture on Process queued it and stopped."""
    job = _Job("job-a")
    queue = _Queue()
    controller = _Controller()
    a = _adapter(queue, controller, jobs={"job-a": job})

    a.queue_jobs(json.dumps({"job_ids": ["job-a"]}))

    assert a.started == [("study", True)], "the queued lecture never started"
    assert queue.active == "job-a"
    assert controller.set_job_calls == [job], "the pipeline was started without its job"


def test_process_now_on_an_idle_app_starts_the_job():
    """'Process now' reordered a list of one and did nothing observable."""
    job = _Job("job-b")
    queue = _Queue(queued=["job-b"])
    controller = _Controller()
    a = _adapter(queue, controller, jobs={"job-b": job})

    a.run_now("job-b")

    assert a.started == [("study", True)]
    assert queue.active == "job-b"


def test_a_running_pipeline_is_never_disturbed():
    """One-active-job holds: queueing behind a live run must not start a second."""
    queue = _Queue()
    controller = _Controller(active_stages=["transcribe"])
    a = _adapter(queue, controller, jobs={"job-c": _Job("job-c")})

    a.queue_jobs(json.dumps({"job_ids": ["job-c"]}))

    assert a.started == [], "a second pipeline was started on top of a running one"
    assert queue.active is None
    assert queue.store["queue"] == ["job-c"], "the job should be waiting its turn"


def test_between_stages_still_counts_as_running():
    """_active_stages empties BETWEEN stages, so is_processing() alone reads idle
    mid-run -- current_stage closes that window."""
    queue = _Queue()
    controller = _Controller(active_stages=[], current_stage="detect")
    a = _adapter(queue, controller, jobs={"job-d": _Job("job-d")})

    a.queue_jobs(json.dumps({"job_ids": ["job-d"]}))

    assert a.started == [], "started a job in the gap between two stages of another"
    assert queue.store["queue"] == ["job-d"]


def test_a_held_active_slot_blocks_promotion():
    """promote_next() refuses while a slot is held; nothing should start."""
    queue = _Queue(active="job-running")
    controller = _Controller()
    a = _adapter(queue, controller, jobs={"job-e": _Job("job-e")})

    a.queue_jobs(json.dumps({"job_ids": ["job-e"]}))

    assert a.started == []
    assert queue.active == "job-running"


def test_an_unloadable_job_stays_queued_and_holds_no_slot():
    """Checked BEFORE promotion, so nothing is stranded and nothing is lost.

    Promoting first and bailing after would either leave the active slot held --
    wedging every later job behind an unreadable one -- or drop the job out of the
    queue entirely, which loses it silently.
    """
    queue = _Queue()
    controller = _Controller()
    a = _adapter(queue, controller, jobs={})     # _reload_job returns None
    a.logs = []
    a._log = lambda tag, text, kind=None: a.logs.append((tag, text))

    a.queue_jobs(json.dumps({"job_ids": ["job-missing"]}))

    assert a.started == []
    assert queue.active is None, "the active slot was left held"


def test_enqueue_job_stays_a_pure_queue_primitive():
    """enqueue_job must NOT start anything.

    Auto-starting from here was the first attempt and it was wrong: enqueue_job is
    also used for jobs merely being placed in line -- including ones with no source
    yet -- so it ran inspect on a stub and blew up the adapter startup test. The
    intent to RUN lives on queue_jobs and run_now.
    """
    queue = _Queue()
    controller = _Controller()
    a = _adapter(queue, controller, jobs={"job-f": _Job("job-f")})

    a.enqueue_job("job-f")

    assert a.started == []
    assert queue.active is None
    assert queue.store["queue"] == ["job-f"]


def test_a_job_with_no_source_video_is_not_started():
    """Auto-start must not launch a pipeline that can only crash.

    run_pipeline dies in the inspect stage on manifest["source"], so starting a
    sourceless job turns a queued item into an error the user never asked for.
    The slot is released so the rest of the queue still moves.
    """
    queue = _Queue()
    controller = _Controller()
    a = _adapter(queue, controller, jobs={"job-g": _Job("job-g", source=None)})
    a.logs = []
    a._log = lambda tag, text, kind=None: a.logs.append((tag, text))

    a.queue_jobs(json.dumps({"job_ids": ["job-g"]}))

    assert a.started == []
    assert queue.active is None, "a sourceless job kept the active slot"
    assert queue.store["queue"] == ["job-g"], "the job was dropped from the queue"
    assert any("no source" in text.lower() for _t, text in a.logs), "failed silently"
