"""Dragging a finished lecture onto Process runs it again.

Drag-to-queue existed but was gated on ``_jobIsReady`` -- status 'queued',
meaning imported-but-never-processed. A library of finished lectures therefore
had no draggable card at all, and the sidecar refused the drop too, so the
feature read as simply broken. Both ends now accept a finished lecture, behind
one explicit opt-in.

The properties worth protecting:

* OPT-IN. Re-running replaces slides, transcript and Study pack. Without the
  ``reprocess`` flag the sidecar must behave exactly as it always did.
* NEVER A LIVE JOB. Running/paused work is not resettable at any price.
* NO PARTIAL RESET. If the queue rejects the job, the finished job must keep
  its completed stages rather than be left wiped and unqueued.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_PATH = ROOT / "electron-spike" / "python-sidecar.py"
APP = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def _sidecar():
    spec = importlib.util.spec_from_file_location("lp_sidecar_reprocess", SIDECAR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Job:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.stages: dict[str, str] = {}
        self.saves = 0

    def set_stage_status(self, stage, status, error=""):
        self.stages[stage] = status

    def save(self):
        self.saves += 1


class _Queue:
    def __init__(self):
        self.active = None
        self.items: list[str] = []
        self.reject = False

    def queued(self):
        return list(self.items)


def _harness(status: str, *, reject: bool = False, reset_raises: bool = False):
    module = _sidecar()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    job = _Job("job-1")
    queue = _Queue()
    queue.reject = reject
    sidecar.queue = queue
    sidecar._job_objects = lambda: [job]
    sidecar._job_status = lambda j: status
    sidecar._push_queue = lambda: None
    sidecar._emit_job_payloads = lambda: None
    sidecar._maybe_resume_queue = lambda: None
    removed: list[str] = []

    def enqueue(_queue, job_id):
        if reject:
            return -1
        _queue.items.append(job_id)
        return len(_queue.items) - 1

    def restart(j):
        if reset_raises:
            raise RuntimeError("disk full")
        for stage in ("Extract", "Transcribe", "Slides"):
            j.set_stage_status(stage, "pending")

    sidecar.electron_backend = SimpleNamespace(
        enqueue_job=enqueue,
        restart_job=restart,
        remove_from_queue=lambda _q, job_id: removed.append(job_id),
    )
    replies: list[dict] = []
    sidecar._respond = lambda request_id, command, **payload: replies.append(payload)
    return sidecar, job, queue, replies, removed


def _call(sidecar, **payload):
    sidecar._queue_existing_jobs("req", "queue_jobs", {"job_ids": ["job-1"], **payload})


@pytest.mark.parametrize("status", ["done", "failed", "cancelled", "interrupted"])
def test_a_finished_lecture_is_skipped_without_the_opt_in(status):
    sidecar, job, queue, replies, _ = _harness(status)
    _call(sidecar)
    assert replies[-1]["count"] == 0
    assert replies[-1]["skipped"] == [{"job_id": "job-1", "reason": status}]
    assert queue.items == []
    assert job.stages == {}, "nothing may be reset when the caller did not ask"


@pytest.mark.parametrize("status", ["done", "failed", "cancelled", "interrupted"])
def test_the_opt_in_queues_it_and_resets_every_stage(status):
    sidecar, job, queue, replies, _ = _harness(status)
    _call(sidecar, reprocess=True)
    assert replies[-1]["count"] == 1
    assert queue.items == ["job-1"]
    assert set(job.stages.values()) == {"pending"}, "it must re-enter the queue as unprocessed work"
    assert job.saves == 1


@pytest.mark.parametrize("status", ["running", "paused", "pause_requested"])
def test_live_work_is_never_reset_even_with_the_opt_in(status):
    sidecar, job, queue, replies, _ = _harness(status)
    _call(sidecar, reprocess=True)
    assert replies[-1]["count"] == 0
    assert replies[-1]["skipped"] == [{"job_id": "job-1", "reason": status}]
    assert job.stages == {}
    assert queue.items == []


def test_an_unprocessed_lecture_still_queues_normally():
    sidecar, job, queue, replies, _ = _harness("queued")
    _call(sidecar)
    assert replies[-1]["count"] == 1
    assert job.stages == {}, "an unprocessed job has nothing to reset"


def test_a_rejected_queue_leaves_the_finished_job_intact():
    sidecar, job, queue, replies, _ = _harness("done", reject=True)
    _call(sidecar, reprocess=True)
    assert replies[-1]["skipped"] == [{"job_id": "job-1", "reason": "queue_rejected"}]
    assert job.stages == {}, "a job that never made it into the queue keeps its results"
    assert job.saves == 0


def test_a_failed_reset_rolls_the_job_back_out_of_the_queue():
    """Otherwise a lecture sits in the queue advertising completed stages."""
    sidecar, job, queue, replies, removed = _harness("done", reset_raises=True)
    _call(sidecar, reprocess=True)
    assert replies[-1]["count"] == 0
    assert replies[-1]["skipped"] == [{"job_id": "job-1", "reason": "reset_failed"}]
    assert removed == ["job-1"]


# ------------------------------------------------------------------ renderer

def test_the_renderer_confirms_before_asking_for_a_reprocess():
    assert "function confirmReprocess(ids)" in APP
    body = APP.split("function confirmReprocess(ids)", 1)[1].split("\n  function ", 1)[0]
    assert "replaces their existing slides, transcript and Study pack" in body
    assert "danger: true" in body, "the destructive action must read as destructive"
    assert "resolve(false)" in body and "resolve(true)" in body
    # The flag is never sent unprompted.
    assert "if (opts && opts.reprocess) request.reprocess = true;" in APP
    drop = APP.split("function dropLecturesOnProcess(ids, host)", 1)[1][:1200]
    assert "if (again && !agreed) return;" in drop
    assert "queueExistingJobIds(ids, { reprocess: again })" in drop


def test_the_bridge_forwards_the_reprocess_flag():
    """mapCall rebuilds every payload from NAMED keys instead of passing the
    renderer's object through, so an unlisted key is dropped in silence. That
    is how this shipped broken the first time: sidecar accepted the flag,
    renderer sent it, and the bridge between them deleted it -- with an ok:true
    response and a 'reason: done' skip that looked like a deliberate refusal.
    """
    bridge = (ROOT / "electron-spike" / "electron-bridge.js").read_text(encoding="utf-8")
    mapping = bridge.split("if (name === 'queue_jobs'", 1)[1].split("if (name === 'get_bootstrap'", 1)[0]
    assert "reprocess: payload.reprocess === true" in mapping, (
        "the flag must survive the renderer -> sidecar hop"
    )
    assert "queue_existing_jobs" in mapping, "both queue commands take the same path"


def test_reprocessable_is_separate_from_ready():
    """_jobIsReady still drives Start/Options; widening it would have put a
    Start button on every finished lecture."""
    assert "function _jobIsReprocessable(j)" in APP
    ready = APP.split("function _jobIsReady(j) {", 1)[1].split("}", 1)[0]
    assert "done" not in ready
    reprocessable = APP.split("var REPROCESSABLE_STATUSES = ", 1)[1].split(";", 1)[0]
    for status in ("done", "failed", "cancelled", "interrupted"):
        assert status in reprocessable
    assert "!_jobInQueue(j.id)" in APP.split("function _jobIsReprocessable(j)", 1)[1][:200]
    # Dragging consults the union; nothing else does.
    assert "return _jobIsReady(j) || _jobIsReprocessable(j);" in APP
