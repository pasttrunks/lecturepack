"""Focused tests for Feature 6 (startup interruption recovery).

Exercises the sidecar's recover_interrupted_jobs handler: crash-interrupted
processing jobs are returned to the FIFO queue exactly once, queue order is
preserved, and DONE/FAILED/CANCELLED jobs are untouched. Duplicate queue
entries are impossible because the underlying enqueue is idempotent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"


class _FakeJob:
    def __init__(self, job_id, status):
        self.job_id = job_id
        self._status = status


class _FakeQueue:
    """Minimal stand-in for the JobQueue with just enough state."""
    def __init__(self, queued, active=None):
        self._queue = list(queued)
        self.active = active

    def queued(self):
        return list(self._queue)

    def enqueue(self, job_id):
        if job_id == self.active:
            return -1
        if job_id not in self._queue:
            self._queue.append(job_id)
        return self._queue.index(job_id)

    def schedules(self):
        return {}

    def queued_ids(self):
        return list(self._queue)


def _make_sidecar(queue, jobs, active=None):
    spec = importlib.util.spec_from_file_location(
        "lecturepack_electron_recovery_test", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.queue = queue
    sidecar.data_dir = ROOT / "tests" / "scratch" / "recovery"
    sidecar._job_objects = lambda: jobs
    sidecar._job_status = lambda job: job._status

    class FakeBackend:
        def enqueue_job(self, q, job_id):
            position = q.enqueue(job_id)
            return position

    sidecar.electron_backend = FakeBackend()
    sidecar._emit = lambda *a, **k: None
    return sidecar, module


def _capture_respond(sidecar, module):
    captured = {}
    def respond(request_id, command, **payload):
        captured.update(payload)
    sidecar._respond = respond
    return captured


def test_interrupted_job_is_requeued():
    queue = _FakeQueue([])
    jobs = [_FakeJob("jobA", "interrupted")]
    sidecar, module = _make_sidecar(queue, jobs)
    captured = _capture_respond(sidecar, module)
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    assert captured["recovered"] == 1
    assert captured["requeued"] == ["jobA"]
    assert queue.queued_ids() == ["jobA"]


def test_queue_order_is_preserved_and_queued_jobs_not_duplicated():
    queue = _FakeQueue(["alreadyQueued"])
    jobs = [_FakeJob("alreadyQueued", "interrupted"), _FakeJob("interruptB", "interrupted")]
    sidecar, module = _make_sidecar(queue, jobs)
    captured = _capture_respond(sidecar, module)
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    # alreadyQueued stays in place at the front; interruptB appends after it.
    assert queue.queued_ids() == ["alreadyQueued", "interruptB"]
    assert captured["recovered"] == 1
    assert captured["requeued"] == ["interruptB"]


def test_duplicate_enqueue_happens_exactly_once():
    queue = _FakeQueue([])
    jobs = [_FakeJob("jobA", "interrupted")]
    sidecar, module = _make_sidecar(queue, jobs)
    _capture_respond(sidecar, module)
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    # The idempotent enqueue means a second recovery run cannot duplicate.
    assert queue.queued_ids() == ["jobA"]


def test_terminal_jobs_are_untouched():
    queue = _FakeQueue([])
    jobs = [
        _FakeJob("doneA", "done"),
        _FakeJob("failedA", "failed"),
        _FakeJob("cancelledA", "cancelled"),
        _FakeJob("interruptA", "interrupted"),
    ]
    sidecar, module = _make_sidecar(queue, jobs)
    captured = _capture_respond(sidecar, module)
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    assert captured["recovered"] == 1
    assert captured["requeued"] == ["interruptA"]
    assert queue.queued_ids() == ["interruptA"]


def test_running_job_not_requeued():
    queue = _FakeQueue([])
    jobs = [_FakeJob("runningA", "running")]
    sidecar, module = _make_sidecar(queue, jobs)
    captured = _capture_respond(sidecar, module)
    sidecar._recover_interrupted_jobs(None, "recover_interrupted_jobs")
    assert captured["recovered"] == 0
    assert queue.queued_ids() == []


def _download_state_sidecar(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "lecturepack_electron_download_recovery_test", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.data_dir = tmp_path
    sidecar._download_lock = threading.Lock()
    sidecar._downloads = {}
    sidecar._download_order = []
    return sidecar


def test_interrupted_download_is_restored_as_retryable_failure(tmp_path):
    sidecar = _download_state_sidecar(tmp_path)
    sidecar._downloads = {
        "download-1": {
            "id": "download-1",
            "url": "https://example.invalid/lecture",
            "title": "Lecture",
            "status": "downloading",
            "pct": 37,
            "eta": 20,
            "speed": 100,
            "error": "",
        }
    }
    sidecar._download_order = ["download-1"]
    with sidecar._download_lock:
        sidecar._persist_downloads_locked()

    restored = _download_state_sidecar(tmp_path)
    restored._load_download_state()
    item = restored._downloads["download-1"]
    assert item["status"] == "failed"
    assert "Retry" in item["error"]
    assert restored._download_order == ["download-1"]


def test_completed_and_cancelled_download_state_survives_restart(tmp_path):
    sidecar = _download_state_sidecar(tmp_path)
    sidecar._downloads = {
        "done": {"id": "done", "url": "https://example.invalid/a", "status": "complete", "pct": 100},
        "stopped": {"id": "stopped", "url": "https://example.invalid/b", "status": "cancelled", "pct": 12},
    }
    sidecar._download_order = ["done", "stopped"]
    with sidecar._download_lock:
        sidecar._persist_downloads_locked()

    restored = _download_state_sidecar(tmp_path)
    restored._load_download_state()
    assert [restored._downloads[item]["status"] for item in restored._download_order] == ["complete", "cancelled"]
