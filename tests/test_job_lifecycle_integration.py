"""Integration tests: the Job model's lifecycle persistence + startup
reconciliation against real on-disk state (tmp dirs, no Qt)."""

import os

from lecturepack.models.job import Job
from lecturepack.models import job_lifecycle as lc


def _new_job(tmp_path, session=None):
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    return Job(str(tmp_path / "data"), video_path=str(video),
               current_session_id=session)


def test_fresh_job_starts_new(tmp_path):
    j = _new_job(tmp_path)
    assert j.get_lifecycle() == lc.NEW
    assert j.state["session"] == {}


def test_backfill_lifecycle_for_pre_beta3_job(tmp_path):
    j = _new_job(tmp_path)
    jid = j.job_id
    # Simulate a beta.2 state.json: no lifecycle/session, only overall_status.
    j.state.pop("lifecycle", None)
    j.state.pop("session", None)
    j.state["overall_status"] = "completed"
    j.save()

    reopened = Job(str(tmp_path / "data"), job_id=jid, current_session_id="s")
    assert reopened.get_lifecycle() == lc.COMPLETED


def test_running_job_from_dead_session_reconciled_to_interrupted(tmp_path):
    j = _new_job(tmp_path)
    jid = j.job_id
    j.state["lifecycle"] = lc.RUNNING
    j.state["session"] = {"session_id": "old-session", "process_id": 999999}
    # a stage was mid-run when the app died
    first_stage = next(iter(j.state["stages"]))
    j.state["stages"][first_stage]["status"] = "running"
    j.save()

    reopened = Job(str(tmp_path / "data"), job_id=jid,
                   current_session_id="new-session")
    assert reopened.get_lifecycle() == lc.INTERRUPTED
    assert reopened.state["session"] == {}
    assert reopened.get_stage_status(first_stage) == "interrupted"


def test_running_job_owned_by_live_current_session_preserved(tmp_path):
    j = _new_job(tmp_path)
    jid = j.job_id
    j.state["lifecycle"] = lc.RUNNING
    j.state["overall_status"] = "pending"  # keep legacy field out of the way
    j.state["session"] = {"session_id": "cur", "process_id": os.getpid()}
    j.save()

    reopened = Job(str(tmp_path / "data"), job_id=jid, current_session_id="cur")
    # The live owner keeps its running job — NOT clobbered.
    assert reopened.get_lifecycle() == lc.RUNNING


def test_paused_and_queued_survive_restart(tmp_path):
    for state in (lc.PAUSED, lc.QUEUED, lc.SCHEDULED):
        sub = tmp_path / state
        sub.mkdir()
        j = _new_job(sub)
        jid = j.job_id
        j.state["lifecycle"] = state
        j.save()
        reopened = Job(str(sub / "data"), job_id=jid, current_session_id="new")
        assert reopened.get_lifecycle() == state


def test_set_lifecycle_validates_and_persists(tmp_path):
    j = _new_job(tmp_path)
    jid = j.job_id
    owner = lc.SessionOwner(session_id="cur", process_id=os.getpid())

    j.set_lifecycle(lc.QUEUED)
    j.set_lifecycle(lc.RUNNING, owner=owner)
    assert j.state["session"]["session_id"] == "cur"

    # persisted?
    mid = Job(str(tmp_path / "data"), job_id=jid, current_session_id="cur")
    assert mid.get_lifecycle() == lc.RUNNING

    j.set_lifecycle(lc.COMPLETED)
    assert j.get_lifecycle() == lc.COMPLETED
    assert j.state["session"] == {}  # ownership released on terminal


def test_set_lifecycle_rejects_illegal_edge(tmp_path):
    import pytest
    j = _new_job(tmp_path)
    with pytest.raises(lc.IllegalTransition):
        j.set_lifecycle(lc.COMPLETED)  # new -> completed is illegal
