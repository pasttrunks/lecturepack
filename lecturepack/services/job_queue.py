"""Persistent job queue, scheduler, and cooperative-pause helpers (beta.3).

Pure orchestration logic — no Qt, no subprocess. The authoritative per-job state
lives in ``job_lifecycle``; this service owns the *ordering* and *timing*: a
single active slot, a FIFO queue with reorder/Run-Now/remove, tz-aware schedules
with missed-run policies, and the checkpoint math for resuming a paused/
interrupted job from the last completed stage. Everything persists atomically to
``<data_dir>/queue.json`` and survives restarts. The controller/adapter drive
the actual pipeline; they call in here to decide *what* runs next and *from which
stage*, and mirror the resulting lifecycle onto the Job.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models import job_lifecycle as lc

QUEUE_FILENAME = "queue.json"
SCHEMA_VERSION = 1

# Missed-schedule policies (applied only to schedules that came due while the
# app was CLOSED — reconciled at launch).
RUN_WHEN_OPENED = "run_when_opened"
SKIP_IF_MISSED = "skip_if_missed"
ASK = "ask"
MISSED_POLICIES = frozenset({RUN_WHEN_OPENED, SKIP_IF_MISSED, ASK})
DEFAULT_MISSED_POLICY = RUN_WHEN_OPENED


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobQueue:
    def __init__(self, data_dir: str, now_fn: Callable[[], datetime] = _utcnow):
        self.data_dir = data_dir
        self._now = now_fn
        self.path = os.path.join(data_dir, QUEUE_FILENAME)
        self.store = {
            "schema_version": SCHEMA_VERSION,
            "active": None,           # job_id currently holding the run slot
            "queue": [],              # ordered job_ids (FIFO; index 0 = next)
            "schedules": {},          # job_id -> {when, tz, missed_policy}
        }
        self.load()

    # -- persistence -------------------------------------------------------- #
    def load(self) -> None:
        data = FileManager.read_json_safe(self.path, None)
        if isinstance(data, dict):
            self.store.update({
                "active": data.get("active"),
                "queue": list(data.get("queue", [])),
                "schedules": dict(data.get("schedules", {})),
                "schema_version": data.get("schema_version", SCHEMA_VERSION),
            })

    def save(self) -> None:
        FileManager.write_json_atomic(self.path, self.store)

    # -- queue -------------------------------------------------------------- #
    def enqueue(self, job_id: str) -> int:
        """Append to the FIFO queue (idempotent). Returns queue position."""
        if job_id == self.store["active"]:
            return -1
        if job_id not in self.store["queue"]:
            self.store["queue"].append(job_id)
            self.save()
        return self.position(job_id)

    def remove(self, job_id: str) -> bool:
        changed = False
        if job_id in self.store["queue"]:
            self.store["queue"].remove(job_id)
            changed = True
        if job_id in self.store["schedules"]:
            del self.store["schedules"][job_id]
            changed = True
        if self.store["active"] == job_id:
            self.store["active"] = None
            changed = True
        if changed:
            self.save()
        return changed

    def position(self, job_id: str) -> Optional[int]:
        try:
            return self.store["queue"].index(job_id)
        except ValueError:
            return None

    def queued(self) -> list:
        return list(self.store["queue"])

    def reorder(self, job_id: str, new_index: int) -> bool:
        q = self.store["queue"]
        if job_id not in q:
            return False
        q.remove(job_id)
        new_index = max(0, min(new_index, len(q)))
        q.insert(new_index, job_id)
        self.save()
        return True

    def run_now(self, job_id: str) -> bool:
        """Jump a queued job to the front (runs next). Does not preempt an
        already-active job — the one-active invariant holds."""
        return self.reorder(job_id, 0)

    # -- one active slot ---------------------------------------------------- #
    @property
    def active(self) -> Optional[str]:
        return self.store["active"]

    def promote_next(self) -> Optional[str]:
        """Pop the front of the queue into the single active slot and return it.
        Returns None if a job is already active or the queue is empty (enforces
        one-active-job)."""
        if self.store["active"] is not None:
            return None
        if not self.store["queue"]:
            return None
        job_id = self.store["queue"].pop(0)
        self.store["active"] = job_id
        self.save()
        return job_id

    def finish_active(self, job_id: str = None) -> None:
        """Release the active slot (job completed/failed/cancelled/interrupted)."""
        if job_id is None or self.store["active"] == job_id:
            self.store["active"] = None
            self.save()

    def requeue_active(self, job_id: str = None) -> None:
        """Return the active job to the FRONT of the queue (e.g. resume of a
        paused job, or retry), releasing the slot."""
        jid = job_id or self.store["active"]
        if jid is None:
            return
        if self.store["active"] == jid:
            self.store["active"] = None
        if jid not in self.store["queue"]:
            self.store["queue"].insert(0, jid)
        self.save()

    # -- scheduling --------------------------------------------------------- #
    def schedule(self, job_id: str, when_local_iso: str, tz: str = "UTC",
                 missed_policy: str = DEFAULT_MISSED_POLICY) -> None:
        if missed_policy not in MISSED_POLICIES:
            missed_policy = DEFAULT_MISSED_POLICY
        self.store["schedules"][job_id] = {
            "when": when_local_iso,
            "tz": tz,
            "missed_policy": missed_policy,
        }
        self.save()

    def unschedule(self, job_id: str) -> bool:
        if job_id in self.store["schedules"]:
            del self.store["schedules"][job_id]
            self.save()
            return True
        return False

    def schedules(self) -> dict:
        return dict(self.store["schedules"])

    @staticmethod
    def _due_at(entry: dict) -> datetime:
        """Convert a stored schedule to an aware UTC datetime."""
        when = entry.get("when", "")
        dt = datetime.fromisoformat(when)
        if dt.tzinfo is None:
            tzname = entry.get("tz") or "UTC"
            if tzname == "local":
                # Interpret the naive wall-clock in the system local zone.
                return dt.astimezone().astimezone(timezone.utc)
            try:
                dt = dt.replace(tzinfo=ZoneInfo(tzname))
            except Exception:
                # tzdata missing or bad name: fall back to system local so a
                # user's schedule is never silently off by their UTC offset.
                return dt.astimezone().astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)

    def due(self, now: datetime = None) -> list:
        """job_ids whose scheduled time is at/after-due relative to ``now``."""
        now = now or self._now()
        out = []
        for jid, entry in self.store["schedules"].items():
            try:
                if self._due_at(entry) <= now:
                    out.append(jid)
            except Exception:
                continue
        return out

    def activate_due(self, now: datetime = None) -> list:
        """App is open and time arrived: move due schedules into the queue
        (on-time, so missed policy does not apply). Returns enqueued ids."""
        now = now or self._now()
        moved = []
        for jid in self.due(now):
            del self.store["schedules"][jid]
            if jid != self.store["active"] and jid not in self.store["queue"]:
                self.store["queue"].append(jid)
            moved.append(jid)
        if moved:
            self.save()
        return moved

    def reconcile_schedules_on_launch(self, now: datetime = None) -> dict:
        """At startup, resolve schedules that came due while the app was CLOSED
        using each entry's missed policy. Returns
        {"enqueued": [...], "skipped": [...], "ask": [...]}."""
        now = now or self._now()
        result = {"enqueued": [], "skipped": [], "ask": []}
        for jid in self.due(now):
            policy = self.store["schedules"][jid].get(
                "missed_policy", DEFAULT_MISSED_POLICY)
            if policy == SKIP_IF_MISSED:
                del self.store["schedules"][jid]
                result["skipped"].append(jid)
            elif policy == ASK:
                result["ask"].append(jid)  # leave schedule; UI decides
            else:  # RUN_WHEN_OPENED
                del self.store["schedules"][jid]
                if jid != self.store["active"] and jid not in self.store["queue"]:
                    self.store["queue"].append(jid)
                result["enqueued"].append(jid)
        if result["enqueued"] or result["skipped"]:
            self.save()
        return result


# --- cooperative pause / resume checkpoint math ---------------------------- #
def resume_stage(stage_order: list, stage_status: dict) -> Optional[str]:
    """Given the pipeline's stage order and each stage's status, return the
    first stage that is NOT verifiably completed — i.e. where a resume must
    restart. Completed stages are preserved; a paused/interrupted stage restarts
    from its beginning (no stage supports mid-stage resume). Returns None when
    every stage is completed."""
    for stage in stage_order:
        if stage_status.get(stage, {}).get("status") != "completed":
            return stage
    return None


def plan_resume(stage_order: list, stage_status: dict) -> dict:
    """Plan a resume: which stages are preserved vs. must re-run, and which
    partial (non-completed but 'running'/'interrupted') outputs are invalid and
    should be discarded before restarting."""
    preserved, rerun, discard_partials = [], [], []
    resume_from = resume_stage(stage_order, stage_status)
    hit = False
    for stage in stage_order:
        st = stage_status.get(stage, {}).get("status", "pending")
        if not hit and stage == resume_from:
            hit = True
        if not hit:
            preserved.append(stage)
        else:
            rerun.append(stage)
            if st in ("running", "interrupted", "pause_requested", "paused"):
                discard_partials.append(stage)
    return {
        "resume_from": resume_from,
        "preserved": preserved,
        "rerun": rerun,
        "discard_partials": discard_partials,
    }
