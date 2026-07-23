"""Authoritative job lifecycle state machine (pure, Qt-free, unit-tested).

Beta.3 introduces orchestration states that the old ``overall_status`` (which is
*derived* from per-stage statuses) cannot express: a job can be ``queued`` or
``scheduled`` or ``paused`` while its stages are all still ``pending``. This
module owns the authoritative lifecycle field, its legal transitions, and the
startup reconciliation policy. It has no Qt / filesystem / engine dependencies
so it can be exhaustively tested with plain pytest.

The controller/queue/UI layers read the sets and helpers here; they must never
hard-code state strings or transition rules of their own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Callable, Optional

# --- states ---------------------------------------------------------------- #
NEW = "new"
SCHEDULED = "scheduled"
QUEUED = "queued"
RUNNING = "running"
PAUSE_REQUESTED = "pause_requested"
PAUSED = "paused"
COMPLETED = "completed"
FAILED = "failed"
INTERRUPTED = "interrupted"
CANCELLED = "cancelled"

ALL_STATES = frozenset({
    NEW, SCHEDULED, QUEUED, RUNNING, PAUSE_REQUESTED, PAUSED,
    COMPLETED, FAILED, INTERRUPTED, CANCELLED,
})

# States that hold the single execution slot (only one job may be in one of
# these at a time — the one-active-job invariant).
ACTIVE_STATES = frozenset({RUNNING, PAUSE_REQUESTED})

# States shown in the Processing view. ``paused`` is shown there but holds no
# execution slot.
PROCESSING_VIEW = frozenset({RUNNING, PAUSE_REQUESTED, PAUSED})

# Jobs waiting to run / due later.
QUEUE_VIEW = frozenset({QUEUED})
SCHEDULED_VIEW = frozenset({SCHEDULED})

# "Needs attention" — left an active view, artifacts preserved, re-activatable.
ATTENTION_STATES = frozenset({FAILED, INTERRUPTED})

# Fully done (success or user-cancelled). Not re-activatable except by an
# explicit new run.
DONE_STATES = frozenset({COMPLETED, CANCELLED})

# Terminal for the purpose of "the run is over" (may still be retried/resumed
# out of FAILED/INTERRUPTED, which re-enters the queue).
TERMINAL_STATES = frozenset({COMPLETED, FAILED, INTERRUPTED, CANCELLED})


# --- legal transitions ----------------------------------------------------- #
# Encodes the beta.3 state-transition contract (plus the obvious cancel edges
# and terminal-race edges that a real pipeline needs). Anything not listed is
# illegal and raises IllegalTransition.
LEGAL_TRANSITIONS = {
    NEW: {SCHEDULED, QUEUED, CANCELLED},
    SCHEDULED: {QUEUED, PAUSED, CANCELLED},
    QUEUED: {RUNNING, PAUSED, SCHEDULED, CANCELLED},
    RUNNING: {PAUSE_REQUESTED, COMPLETED, FAILED, INTERRUPTED, CANCELLED},
    # A pause can lose the race with a stage finishing/failing, or the app can
    # die while the request is pending (-> interrupted, reconciled at startup).
    PAUSE_REQUESTED: {PAUSED, RUNNING, COMPLETED, FAILED, INTERRUPTED, CANCELLED},
    PAUSED: {QUEUED, SCHEDULED, RUNNING, CANCELLED},
    # Retry re-queues a failed job; resume/restart re-queues an interrupted one.
    FAILED: {QUEUED, CANCELLED},
    INTERRUPTED: {QUEUED, CANCELLED},
    # Done states are sinks (a fresh run creates a new job).
    COMPLETED: set(),
    CANCELLED: set(),
}


class IllegalTransition(ValueError):
    """Raised when a lifecycle transition is not permitted."""


def can_transition(frm: str, to: str) -> bool:
    """True iff ``frm -> to`` is a legal lifecycle edge. Self-transitions and
    unknown states are not legal."""
    if frm not in ALL_STATES or to not in ALL_STATES:
        return False
    return to in LEGAL_TRANSITIONS.get(frm, set())


def assert_transition(frm: str, to: str) -> None:
    if not can_transition(frm, to):
        raise IllegalTransition(f"illegal lifecycle transition: {frm!r} -> {to!r}")


def is_active(state: str) -> bool:
    """Holds the single execution slot."""
    return state in ACTIVE_STATES


def in_active_view(state: str) -> bool:
    """Appears in Home/Processing active sections (must be owned by the current
    session)."""
    return state in PROCESSING_VIEW


# --- session ownership ----------------------------------------------------- #
@dataclass(frozen=True)
class SessionOwner:
    """Per-launch ownership stamp. A job is 'owned' by the process that set
    the current session's id; jobs owned by a prior/dead session are eligible
    for reconciliation."""
    session_id: str = ""
    process_id: int = 0
    started_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "SessionOwner":
        d = d or {}
        try:
            pid = int(d.get("process_id", 0) or 0)
        except (TypeError, ValueError):
            pid = 0
        return cls(
            session_id=str(d.get("session_id", "") or ""),
            process_id=pid,
            started_at=str(d.get("started_at", "") or ""),
        )


def pid_alive(pid: int) -> bool:
    """Best-effort check that a process id is live. Conservative: on any
    uncertainty returns False so a stuck job is reclaimable rather than stranded
    forever. Never raises."""
    if not pid or pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def reconcile_on_load(
    lifecycle: str,
    owner: SessionOwner,
    current_session_id: str,
    is_pid_alive: Callable[[int], bool] = pid_alive,
) -> str:
    """Decide a job's lifecycle when (re)loaded from disk.

    A job in an ACTIVE state (running / pause_requested) can only legitimately
    be active if the *current* session owns it and its process is alive.
    Otherwise the owning session is dead and the job is reconciled to
    ``interrupted`` (artifacts preserved; user can resume/restart). This is the
    guard that prevents the naive "any running job -> interrupted" reset from
    clobbering a job the live session actually owns once concurrency exists.

    All other states are persistent and returned unchanged (``paused`` and
    ``queued`` and ``scheduled`` survive restarts by design).
    """
    if lifecycle not in ALL_STATES:
        # Unknown/legacy -> treat as interrupted only if it looks active,
        # else leave for the caller's backfill.
        return lifecycle
    if lifecycle in ACTIVE_STATES:
        owned_by_current = (
            bool(current_session_id)
            and owner.session_id == current_session_id
            and is_pid_alive(owner.process_id)
        )
        if owned_by_current:
            return lifecycle
        return INTERRUPTED
    return lifecycle


def backfill_from_overall_status(overall_status: str) -> str:
    """Derive an initial lifecycle for a pre-beta.3 job that only has the old
    derived ``overall_status``. Keeps upgrades from beta.2 loading cleanly."""
    mapping = {
        "pending": NEW,
        "running": RUNNING,  # reconcile_on_load will downgrade dead-session ones
        "completed": COMPLETED,
        "failed": FAILED,
        "cancelled": CANCELLED,
        "interrupted": INTERRUPTED,
    }
    return mapping.get(overall_status, NEW)
