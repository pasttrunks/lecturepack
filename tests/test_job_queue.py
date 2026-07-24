"""Unit tests for lecturepack/services/job_queue.py — FIFO queue, one-active
invariant, reorder/Run-Now/remove, persistence across restart, tz-aware
scheduling with missed policies, and resume-checkpoint math. Pure logic with an
injected clock."""

from datetime import datetime, timedelta, timezone

import pytest

from lecturepack.services.job_queue import (
    JobQueue, RUN_WHEN_OPENED, SKIP_IF_MISSED, ASK, resume_stage, plan_resume,
)


class Clock:
    def __init__(self, dt):
        self.dt = dt
    def __call__(self):
        return self.dt


def _q(tmp_path, dt=None):
    dt = dt or datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    return JobQueue(str(tmp_path), now_fn=Clock(dt))


# --- FIFO / order ---------------------------------------------------------- #
def test_fifo_enqueue_and_position(tmp_path):
    q = _q(tmp_path)
    q.enqueue("a"); q.enqueue("b"); q.enqueue("c")
    assert q.queued() == ["a", "b", "c"]
    assert q.position("b") == 1
    assert q.position("zzz") is None


def test_enqueue_idempotent(tmp_path):
    q = _q(tmp_path)
    q.enqueue("a"); q.enqueue("a")
    assert q.queued() == ["a"]


def test_reorder_and_run_now(tmp_path):
    q = _q(tmp_path)
    for j in ["a", "b", "c"]:
        q.enqueue(j)
    q.reorder("c", 0)
    assert q.queued() == ["c", "a", "b"]
    q.run_now("b")
    assert q.queued() == ["b", "c", "a"]


def test_remove(tmp_path):
    q = _q(tmp_path)
    for j in ["a", "b", "c"]:
        q.enqueue(j)
    assert q.remove("b") is True
    assert q.queued() == ["a", "c"]
    assert q.remove("nope") is False


# --- one-active invariant -------------------------------------------------- #
def test_promote_next_enforces_single_active(tmp_path):
    q = _q(tmp_path)
    q.enqueue("a"); q.enqueue("b")
    assert q.promote_next() == "a"
    assert q.active == "a"
    assert q.queued() == ["b"]
    # a is active -> cannot promote a second job
    assert q.promote_next() is None
    q.finish_active("a")
    assert q.active is None
    assert q.promote_next() == "b"


def test_promote_next_empty_queue(tmp_path):
    q = _q(tmp_path)
    assert q.promote_next() is None


def test_requeue_active_puts_it_front(tmp_path):
    q = _q(tmp_path)
    q.enqueue("a"); q.enqueue("b")
    q.promote_next()  # a active
    q.requeue_active()  # resume/retry -> front of queue
    assert q.active is None
    assert q.queued() == ["a", "b"]


# --- persistence / restart ------------------------------------------------- #
def test_queue_survives_restart(tmp_path):
    q = _q(tmp_path)
    for j in ["a", "b", "c"]:
        q.enqueue(j)
    q.promote_next()  # a active, [b, c] queued
    reopened = _q(tmp_path)
    assert reopened.active == "a"
    assert reopened.queued() == ["b", "c"]


# --- scheduling ------------------------------------------------------------ #
def test_due_when_time_passed(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("past", (now - timedelta(minutes=5)).isoformat(), tz="UTC")
    q.schedule("future", (now + timedelta(hours=1)).isoformat(), tz="UTC")
    assert q.due(now) == ["past"]


def test_timezone_aware_due(tmp_path):
    # 08:00 America/New_York (EDT, UTC-4) == 12:00 UTC.
    now = datetime(2026, 7, 23, 12, 1, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("ny", "2026-07-23T08:00:00", tz="America/New_York")
    assert q.due(now) == ["ny"]
    # one minute before it is due:
    before = datetime(2026, 7, 23, 11, 59, tzinfo=timezone.utc)
    assert q.due(before) == []


def test_activate_due_moves_to_queue(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("s1", (now - timedelta(minutes=1)).isoformat(), tz="UTC")
    moved = q.activate_due(now)
    assert moved == ["s1"]
    assert q.queued() == ["s1"]
    assert "s1" not in q.schedules()


def test_missed_policy_run_when_opened(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("j", (now - timedelta(days=1)).isoformat(), tz="UTC",
               missed_policy=RUN_WHEN_OPENED)
    res = q.reconcile_schedules_on_launch(now)
    assert res["enqueued"] == ["j"]
    assert q.queued() == ["j"]


def test_missed_policy_skip(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("j", (now - timedelta(days=1)).isoformat(), tz="UTC",
               missed_policy=SKIP_IF_MISSED)
    res = q.reconcile_schedules_on_launch(now)
    assert res["skipped"] == ["j"]
    assert q.queued() == []
    assert "j" not in q.schedules()


def test_missed_policy_ask_leaves_schedule(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("j", (now - timedelta(days=1)).isoformat(), tz="UTC",
               missed_policy=ASK)
    res = q.reconcile_schedules_on_launch(now)
    assert res["ask"] == ["j"]
    assert "j" in q.schedules()  # left for the UI to prompt
    assert q.queued() == []


def test_schedule_persists_across_restart(tmp_path):
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    q = _q(tmp_path, dt=now)
    q.schedule("j", "2026-08-01T09:00:00", tz="America/New_York",
               missed_policy=ASK)
    reopened = _q(tmp_path, dt=now)
    assert reopened.schedules()["j"]["tz"] == "America/New_York"
    assert reopened.schedules()["j"]["missed_policy"] == ASK


# --- resume checkpoint math ------------------------------------------------ #
STAGES = ["Inspect", "Extract Audio", "Transcribe", "Detect Slides", "Align",
          "Review Ready", "Export"]


def test_resume_stage_first_incomplete():
    status = {
        "Inspect": {"status": "completed"},
        "Extract Audio": {"status": "completed"},
        "Transcribe": {"status": "interrupted"},
    }
    assert resume_stage(STAGES, status) == "Transcribe"


def test_resume_stage_all_complete_returns_none():
    status = {s: {"status": "completed"} for s in STAGES}
    assert resume_stage(STAGES, status) is None


def test_plan_resume_preserves_completed_and_discards_partial():
    status = {
        "Inspect": {"status": "completed"},
        "Extract Audio": {"status": "completed"},
        "Transcribe": {"status": "interrupted"},
        "Detect Slides": {"status": "pending"},
    }
    plan = plan_resume(STAGES, status)
    assert plan["resume_from"] == "Transcribe"
    assert plan["preserved"] == ["Inspect", "Extract Audio"]
    assert "Transcribe" in plan["rerun"]
    assert plan["discard_partials"] == ["Transcribe"]
