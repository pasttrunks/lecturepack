"""Deleting a lecture must release it before removing it from disk.

The delete path used to call ``electron_backend.delete_job`` immediately. That
left three holes, all of which a user hits:

* The id stayed in the QUEUE. ``queue.json`` kept a row for a lecture that no
  longer existed, and the scheduler could promote it.
* An ACTIVE lecture was deleted while the controller still owned it and its
  QThread workers were still writing. On Windows the directory removal fails on
  the open handle, and the worker then writes into a directory that is going
  away.
* ``_emit_job_payloads`` returns early when there is no current job, so deleting
  the active lecture emitted NOTHING and Home/Process/Review kept rendering the
  job that had just been removed.

A deleted id is also tombstoned, so a worker event still in flight cannot
resurrect the lecture in the renderer.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIDECAR_PATH = ROOT / "electron-spike" / "python-sidecar.py"
APP = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def _sidecar_module():
    spec = importlib.util.spec_from_file_location("lp_sidecar_delete", SIDECAR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Job:
    def __init__(self, job_id: str):
        self.job_id = job_id


class _Worker:
    """Stands in for a QThread stage worker."""

    def __init__(self, running: bool = True, wedged: bool = False):
        self._running = running
        self._wedged = wedged
        self.waited: list[int] = []
        self.terminated = False

    def isRunning(self):
        return self._running

    def wait(self, ms):
        self.waited.append(ms)
        if not self._wedged:
            self._running = False
        return not self._running

    def terminate(self):
        self.terminated = True
        self._running = False


class _Controller:
    def __init__(self, job=None, workers=None):
        self.job = job
        self.cancelled = 0
        self.set_job_calls: list[object] = []
        workers = workers or {}
        self.slide_worker = workers.get("slide")
        self.align_worker = workers.get("align")
        self.export_worker = workers.get("export")

    def cancel(self):
        self.cancelled += 1

    def set_job(self, job):
        self.set_job_calls.append(job)
        self.job = job


class _Queue:
    """Mirrors JobQueue.remove(): queue rows, schedules and the active slot."""

    def __init__(self, queued=None, schedules=None, active=None):
        self.items = list(queued or [])
        self.schedules = dict(schedules or {})
        self.active_id = active
        self.saves = 0

    def queued(self):
        return list(self.items)

    def active(self):
        return self.active_id

    def remove(self, job_id):
        changed = False
        if job_id in self.items:
            self.items.remove(job_id)
            changed = True
        if job_id in self.schedules:
            del self.schedules[job_id]
            changed = True
        if self.active_id == job_id:
            self.active_id = None
            changed = True
        if changed:
            self.saves += 1
        return changed


def _harness(jobs, *, current=None, controller=None, queue=None, ok=True):
    module = _sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.data_dir = Path("/tmp/lp-delete-tests")
    sidecar.queue = queue if queue is not None else _Queue()
    sidecar.current_job = current
    sidecar.current_stage = "Transcribe" if current is not None else ""
    sidecar.controller = controller
    sidecar._deleted_job_ids = set()
    sidecar._cancel_study_jobs = lambda ids: None
    sidecar._summary = lambda job: {"id": job.job_id}
    sidecar._emit_job_payloads = lambda: None
    sidecar._respond = lambda *a, **k: None

    remaining = list(jobs)
    deleted: list[str] = []
    emitted: list[dict] = []
    pushed = {"count": 0}

    sidecar._job_objects = lambda: list(remaining)
    sidecar._push_queue = lambda: pushed.__setitem__("count", pushed["count"] + 1)

    real_emit_guard = module.Sidecar._is_tombstoned

    def emit(payload):
        # Exercise the REAL tombstone guard, not a stub.
        if real_emit_guard(sidecar, payload):
            return
        emitted.append(payload)

    sidecar._emit = emit

    def delete_job(_data_dir, job_id):
        if not ok:
            return {"ok": False, "error": "locked"}
        deleted.append(job_id)
        for job in list(remaining):
            if job.job_id == job_id:
                remaining.remove(job)
        return {"ok": True, "job_id": job_id}

    def delete_jobs(_data_dir, ids):
        if not ok:
            return {"ok": False, "error": "locked"}
        for job_id in ids:
            delete_job(_data_dir, job_id)
        return {"ok": True, "deleted": list(ids)}

    sidecar.electron_backend = SimpleNamespace(delete_job=delete_job, delete_jobs=delete_jobs)
    return sidecar, SimpleNamespace(
        deleted=deleted, emitted=emitted, pushed=pushed, remaining=remaining
    )


def _events(state):
    return [e.get("event") for e in state.emitted]


# ------------------------------------------------------------ simple deletes
@pytest.mark.parametrize("status_label", ["idle", "completed", "failed"])
def test_delete_an_inactive_lecture_removes_it_and_refreshes_the_library(status_label):
    sidecar, state = _harness([_Job("a"), _Job("b")])
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})

    assert state.deleted == ["a"]
    assert "jobs_changed" in _events(state)
    assert state.pushed["count"] == 1, "queue_changed must follow every delete"


def test_delete_a_queued_lecture_drops_it_from_the_queue():
    queue = _Queue(queued=["a", "b"])
    sidecar, state = _harness([_Job("a"), _Job("b")], queue=queue)
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})

    assert queue.queued() == ["b"], "a deleted id must not survive in queue.json"
    assert state.deleted == ["a"]


def test_delete_a_scheduled_lecture_drops_its_schedule():
    queue = _Queue(queued=["a"], schedules={"a": "2026-01-01T00:00:00Z"})
    sidecar, _ = _harness([_Job("a")], queue=queue)
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})

    assert queue.schedules == {}
    assert queue.queued() == []


def test_dequeue_happens_before_the_directory_is_removed():
    """Otherwise the scheduler can promote a job mid-delete."""
    order: list[str] = []
    queue = _Queue(queued=["a"])
    real_remove = queue.remove
    queue.remove = lambda jid: (order.append("dequeue"), real_remove(jid))[1]
    sidecar, _ = _harness([_Job("a")], queue=queue)
    real_delete = sidecar.electron_backend.delete_job
    sidecar.electron_backend.delete_job = lambda d, j: (order.append("rmdir"), real_delete(d, j))[1]

    sidecar._delete_job(None, "delete_job", {"job_id": "a"})
    assert order == ["dequeue", "rmdir"]


# ------------------------------------------------------------- active delete
def test_deleting_the_active_lecture_cancels_drains_and_detaches_first():
    job = _Job("live")
    slide = _Worker(running=True)
    export = _Worker(running=True)
    controller = _Controller(job=job, workers={"slide": slide, "export": export})
    queue = _Queue(queued=["live"], active="live")
    sidecar, state = _harness([job], current=job, controller=controller, queue=queue)

    sidecar._delete_job(None, "delete_job", {"job_id": "live"})

    assert controller.cancelled == 1, "the controller must be cancelled"
    assert slide.waited and export.waited, "workers must be waited on, not just asked"
    assert not slide.isRunning() and not export.isRunning()
    assert controller.set_job_calls == [None], "the controller must release the job"
    assert sidecar.current_job is None
    assert sidecar.current_stage == ""
    assert queue.queued() == [] and queue.active() is None
    assert state.deleted == ["live"]
    assert "active_job" in _events(state)
    assert "jobs_changed" in _events(state), "the library must refresh without a current job"
    assert state.pushed["count"] == 1


def test_a_wedged_worker_is_terminated_rather_than_blocking_the_delete():
    job = _Job("live")
    stuck = _Worker(running=True, wedged=True)
    controller = _Controller(job=job, workers={"align": stuck})
    sidecar, state = _harness([job], current=job, controller=controller)

    sidecar._delete_job(None, "delete_job", {"job_id": "live"})

    assert stuck.terminated is True
    assert state.deleted == ["live"]


def test_workers_are_detached_so_a_stale_handle_cannot_be_reused():
    job = _Job("live")
    controller = _Controller(job=job, workers={"slide": _Worker(), "align": _Worker()})
    sidecar, _ = _harness([job], current=job, controller=controller)

    sidecar._delete_job(None, "delete_job", {"job_id": "live"})

    assert controller.slide_worker is None
    assert controller.align_worker is None


def test_deleting_a_different_lecture_leaves_the_active_one_running():
    live = _Job("live")
    controller = _Controller(job=live, workers={"slide": _Worker()})
    sidecar, state = _harness([live, _Job("other")], current=live, controller=controller)

    sidecar._delete_job(None, "delete_job", {"job_id": "other"})

    assert controller.cancelled == 0
    assert sidecar.current_job is live
    assert state.deleted == ["other"]


# --------------------------------------------------------------- bulk delete
def test_bulk_delete_of_queued_lectures_clears_every_queue_row():
    queue = _Queue(queued=["a", "b", "c"])
    sidecar, state = _harness([_Job("a"), _Job("b"), _Job("c")], queue=queue)

    sidecar._delete_jobs(None, "delete_jobs", {"ids": ["a", "c"]})

    assert queue.queued() == ["b"]
    assert sorted(state.deleted) == ["a", "c"]
    assert state.pushed["count"] == 1


def test_bulk_delete_including_the_active_lecture_tears_the_controller_down():
    live = _Job("live")
    controller = _Controller(job=live, workers={"slide": _Worker()})
    queue = _Queue(queued=["live", "waiting"], active="live")
    sidecar, state = _harness(
        [live, _Job("waiting")], current=live, controller=controller, queue=queue
    )

    sidecar._delete_jobs(None, "delete_jobs", {"ids": ["live", "waiting"]})

    assert controller.cancelled == 1
    assert controller.set_job_calls == [None]
    assert sidecar.current_job is None
    assert queue.queued() == [] and queue.active() is None
    assert sorted(state.deleted) == ["live", "waiting"]


def test_bulk_delete_accepts_a_json_string_of_ids():
    queue = _Queue(queued=["a", "b"])
    sidecar, state = _harness([_Job("a"), _Job("b")], queue=queue)

    sidecar._delete_jobs(None, "delete_jobs", {"ids": '["a"]'})

    assert state.deleted == ["a"]
    assert queue.queued() == ["b"]


# ----------------------------------------------------------------- tombstone
def test_a_late_worker_event_for_a_deleted_lecture_is_dropped():
    """The bug this prevents: a stage that was mid-flight when the delete landed
    emits progress afterwards and the lecture reappears in the library."""
    sidecar, state = _harness([_Job("a")])
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})
    before = len(state.emitted)

    sidecar._emit({"event": "status_changed", "job_id": "a", "status": "Transcribing"})
    sidecar._emit({"event": "slides_changed", "job": "a", "slides": []})
    sidecar._emit({"event": "log_line", "id": "a", "text": "still working"})

    assert len(state.emitted) == before, "a deleted lecture must not emit anything further"


def test_tombstones_never_suppress_events_for_a_live_lecture():
    sidecar, state = _harness([_Job("a"), _Job("b")])
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})
    before = len(state.emitted)

    sidecar._emit({"event": "status_changed", "job_id": "b", "status": "Transcribing"})

    assert len(state.emitted) == before + 1


def test_tombstones_never_suppress_the_deletion_events_themselves():
    sidecar, state = _harness([_Job("a")])
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})

    events = _events(state)
    assert "job_deleted" in events
    assert "jobs_changed" in events


def test_a_failed_delete_does_not_claim_the_library_changed():
    sidecar, state = _harness([_Job("a")], ok=False)
    sidecar._delete_job(None, "delete_job", {"job_id": "a"})

    assert "jobs_changed" not in _events(state)
    assert state.pushed["count"] == 0


# ------------------------------------------------------- renderer-side state
def test_renderer_prunes_the_workspace_cache_for_removed_lectures():
    """LP.byJob held a deleted lecture's slides/transcript for the whole session."""
    handler = APP[APP.index("lpBridge.on('jobs_changed'"):][:1600]
    assert "Object.keys(LP.byJob)" in handler
    assert "delete LP.byJob[id]" in handler
