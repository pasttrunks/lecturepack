"""Unit tests for the authoritative job lifecycle state machine.

Pure logic — no Qt, no filesystem. Covers legal/illegal transitions, the
one-active-job classification, session-ownership reconciliation, and the
beta.2 -> beta.3 backfill.
"""

import pytest

from lecturepack.models import job_lifecycle as lc


# --- transitions ----------------------------------------------------------- #
@pytest.mark.parametrize("frm,to", [
    (lc.NEW, lc.QUEUED),
    (lc.NEW, lc.SCHEDULED),
    (lc.SCHEDULED, lc.QUEUED),
    (lc.QUEUED, lc.RUNNING),
    (lc.QUEUED, lc.PAUSED),
    (lc.RUNNING, lc.PAUSE_REQUESTED),
    (lc.RUNNING, lc.COMPLETED),
    (lc.RUNNING, lc.FAILED),
    (lc.RUNNING, lc.INTERRUPTED),
    (lc.PAUSE_REQUESTED, lc.PAUSED),
    (lc.PAUSED, lc.QUEUED),
    (lc.PAUSED, lc.SCHEDULED),
    (lc.FAILED, lc.QUEUED),        # retry
    (lc.INTERRUPTED, lc.QUEUED),   # resume/restart
])
def test_legal_transitions(frm, to):
    assert lc.can_transition(frm, to)
    lc.assert_transition(frm, to)  # must not raise


@pytest.mark.parametrize("frm,to", [
    (lc.COMPLETED, lc.RUNNING),      # done is a sink
    (lc.CANCELLED, lc.QUEUED),       # done is a sink
    (lc.NEW, lc.RUNNING),            # must be queued first
    (lc.QUEUED, lc.COMPLETED),       # cannot complete without running
    (lc.RUNNING, lc.QUEUED),         # cannot re-queue a running job directly
    (lc.RUNNING, lc.RUNNING),        # self-transition
    (lc.PAUSED, lc.COMPLETED),       # paused isn't running
    ("bogus", lc.QUEUED),            # unknown state
    (lc.QUEUED, "bogus"),
])
def test_illegal_transitions(frm, to):
    assert not lc.can_transition(frm, to)
    with pytest.raises(lc.IllegalTransition):
        lc.assert_transition(frm, to)


def test_every_state_has_a_transition_entry():
    for s in lc.ALL_STATES:
        assert s in lc.LEGAL_TRANSITIONS, f"{s} missing from LEGAL_TRANSITIONS"
    # and every target is a real state
    for frm, tos in lc.LEGAL_TRANSITIONS.items():
        for to in tos:
            assert to in lc.ALL_STATES


# --- one-active-job classification ----------------------------------------- #
def test_active_state_classification():
    assert lc.is_active(lc.RUNNING)
    assert lc.is_active(lc.PAUSE_REQUESTED)
    # paused holds no execution slot
    assert not lc.is_active(lc.PAUSED)
    assert not lc.is_active(lc.QUEUED)
    assert not lc.is_active(lc.SCHEDULED)


def test_active_view_membership():
    assert lc.in_active_view(lc.RUNNING)
    assert lc.in_active_view(lc.PAUSED)
    assert not lc.in_active_view(lc.QUEUED)
    assert not lc.in_active_view(lc.INTERRUPTED)
    assert not lc.in_active_view(lc.COMPLETED)


def test_state_set_partitioning():
    # Attention and Done are disjoint; active states are disjoint from queue.
    assert not (lc.ATTENTION_STATES & lc.DONE_STATES)
    assert not (lc.ACTIVE_STATES & lc.QUEUE_VIEW)
    assert lc.PAUSED not in lc.ACTIVE_STATES


# --- session ownership ----------------------------------------------------- #
def test_session_owner_roundtrip():
    o = lc.SessionOwner(session_id="s1", process_id=1234, started_at="t")
    assert lc.SessionOwner.from_dict(o.to_dict()) == o


def test_session_owner_from_dict_tolerates_garbage():
    o = lc.SessionOwner.from_dict({"process_id": "not-an-int"})
    assert o.process_id == 0
    o2 = lc.SessionOwner.from_dict(None)
    assert o2.session_id == "" and o2.process_id == 0


def test_reconcile_dead_session_running_becomes_interrupted():
    owner = lc.SessionOwner(session_id="old-session", process_id=999999)
    out = lc.reconcile_on_load(
        lc.RUNNING, owner, current_session_id="new-session",
        is_pid_alive=lambda pid: False)
    assert out == lc.INTERRUPTED


def test_reconcile_pause_requested_dead_session_interrupted():
    owner = lc.SessionOwner(session_id="old", process_id=42)
    out = lc.reconcile_on_load(
        lc.PAUSE_REQUESTED, owner, current_session_id="new",
        is_pid_alive=lambda pid: True)  # alive but WRONG session
    assert out == lc.INTERRUPTED


def test_reconcile_current_session_alive_preserved():
    owner = lc.SessionOwner(session_id="cur", process_id=42)
    out = lc.reconcile_on_load(
        lc.RUNNING, owner, current_session_id="cur",
        is_pid_alive=lambda pid: True)
    assert out == lc.RUNNING  # not clobbered — the live owner keeps it


def test_reconcile_current_session_dead_pid_interrupted():
    # Same session id string but the pid is gone (e.g. crash + relaunch reusing
    # a persisted session id) -> reclaim.
    owner = lc.SessionOwner(session_id="cur", process_id=42)
    out = lc.reconcile_on_load(
        lc.RUNNING, owner, current_session_id="cur",
        is_pid_alive=lambda pid: False)
    assert out == lc.INTERRUPTED


@pytest.mark.parametrize("state", [
    lc.PAUSED, lc.QUEUED, lc.SCHEDULED, lc.COMPLETED,
    lc.FAILED, lc.INTERRUPTED, lc.CANCELLED, lc.NEW,
])
def test_reconcile_non_active_states_unchanged(state):
    owner = lc.SessionOwner(session_id="old", process_id=1)
    out = lc.reconcile_on_load(
        state, owner, current_session_id="new", is_pid_alive=lambda pid: False)
    assert out == state


def test_pid_alive_current_process_true_and_bogus_false():
    import os
    assert lc.pid_alive(os.getpid()) is True
    assert lc.pid_alive(0) is False
    assert lc.pid_alive(-5) is False


# --- backfill from legacy overall_status ----------------------------------- #
@pytest.mark.parametrize("overall,expected", [
    ("pending", lc.NEW),
    ("running", lc.RUNNING),
    ("completed", lc.COMPLETED),
    ("failed", lc.FAILED),
    ("cancelled", lc.CANCELLED),
    ("interrupted", lc.INTERRUPTED),
    ("weird-unknown", lc.NEW),
])
def test_backfill_from_overall_status(overall, expected):
    assert lc.backfill_from_overall_status(overall) == expected
