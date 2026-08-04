"""Electron backend operations for the LecturePack sidecar (Phase 9).

Pure orchestration logic that the JSONL sidecar delegates to. No Qt, no
subprocess. The authoritative per-job state lives in the existing ``Job``
model and ``job_lifecycle``; this module owns the operations the Electron UI
needs: safe job deletion, queue management, rename, grouping,
pause/resume/restart, and the queue promotion that keeps the one-active-job
invariant.

Every path-traversal-sensitive operation validates the job id against
``_SAFE_JOB_ID`` and resolves the real path directly under ``<data_dir>/jobs``
so a delete/group/rename can never touch an unrelated directory.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Any, Callable, Optional

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models import job_lifecycle as lc

# Reject unsafe job ids for any path-traversal-sensitive operation. A job id is
# a UUID-safe token; anything else is refused.
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

# Stage order used by resume/restart checkpoint math. Must match
# ``constants.STAGES`` (the controller's authoritative order).
STAGE_ORDER = [
    "Inspect",
    "Extract Audio",
    "Transcribe",
    "Detect Slides",
    "Align",
    "Review Ready",
    "Export",
]


def _human_size(num_bytes: float) -> str:
    """Human-readable byte size (e.g. ``12.3 MB``)."""
    num = float(num_bytes or 0.0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def _derive_group(title: str) -> str:
    """Best-effort course/subject label from a job title.

    Matches the historical Qt adapter's heuristic: the first token before a
    colon/dash, or the first two words, cleaned of lecture-y suffixes.
    """
    text = str(title or "").strip()
    if not text:
        return "Ungrouped"
    for sep in (":", "—", "-"):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            if head:
                return head[:40]
    words = [w for w in re.split(r"\s+", text) if w][:2]
    return " ".join(words)[:40] or "Ungrouped"


def _job_dir_guarded(data_dir: str, job_id: str) -> Optional[str]:
    """Return the absolute path of a real job dir directly under jobs/, or None.

    Rejects unsafe ids and anything resolving outside jobs/.
    """
    if not _SAFE_JOB_ID.match(job_id or ""):
        return None
    jobs_dir = os.path.join(data_dir, "jobs")
    job_dir = os.path.join(jobs_dir, job_id)
    if not os.path.isdir(job_dir):
        return None
    real = os.path.realpath(job_dir)
    if os.path.dirname(real) != os.path.realpath(jobs_dir):
        return None
    return real


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _load_manifest(data_dir: str, job_id: str) -> Optional[dict]:
    real = _job_dir_guarded(data_dir, job_id)
    if real is None:
        return None
    man = FileManager.read_json_safe(os.path.join(real, "manifest.json"), None)
    return man if isinstance(man, dict) else None


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #
def delete_one(data_dir: str, job_id: str) -> dict:
    """Remove a single job directory. Recycle-bin first, hard delete only when
    send2trash is genuinely absent. Never touches anything outside jobs/."""
    real = _job_dir_guarded(data_dir, job_id)
    if real is None:
        return {"ok": False, "id": job_id, "freed_bytes": 0,
                "error": f"unknown job {job_id}"}
    freed = _dir_size(real)
    try:
        from send2trash import send2trash
    except ImportError:
        shutil.rmtree(real, ignore_errors=False)
        method = "permanently"
    else:
        try:
            send2trash(real)
        except Exception as exc:  # noqa: BLE001 - a locked file must not hard-delete
            return {"ok": False, "id": job_id, "freed_bytes": 0,
                    "error": str(exc)[:200], "method": "none"}
        method = "recycle bin"
    return {"ok": True, "id": job_id, "freed_bytes": freed, "method": method}


def delete_job(data_dir: str, job_id: str) -> dict:
    """Delete one job; returns the job_deleted payload."""
    res = delete_one(data_dir, job_id)
    if not res["ok"]:
        return {"ok": False, "id": job_id, "error": res.get("error", "")}
    return {
        "ok": True,
        "id": job_id,
        "freed": _human_size(res["freed_bytes"]),
        "method": res["method"],
    }


def delete_jobs(data_dir: str, ids: list) -> dict:
    """Delete several jobs; one summary payload for the whole batch."""
    ids = [str(i) for i in (ids or []) if i]
    if not ids:
        return {"ok": False, "bulk": True, "count": 0, "error": "Nothing selected."}
    deleted, failed, freed = [], [], 0
    for job_id in ids:
        res = delete_one(data_dir, job_id)
        if res["ok"]:
            deleted.append(res["id"])
            freed += res["freed_bytes"]
        else:
            failed.append(job_id)
    return {
        "ok": bool(deleted),
        "bulk": True,
        "ids": deleted,
        "count": len(deleted),
        "failed": failed,
        "freed": _human_size(freed),
    }


# --------------------------------------------------------------------------- #
# Grouping and rename
# --------------------------------------------------------------------------- #
def set_job_group(data_dir: str, job_id: str, group: str) -> bool:
    """Write one job's group into its manifest. Returns True on success."""
    real = _job_dir_guarded(data_dir, job_id)
    if real is None:
        return False
    manifest_path = os.path.join(real, "manifest.json")
    man = FileManager.read_json_safe(manifest_path, None)
    if not isinstance(man, dict):
        return False
    group = (group or "").strip()
    if group:
        man["group"] = group
    else:
        man.pop("group", None)  # revert to derived default
    FileManager.write_json_atomic(manifest_path, man)
    return True


def set_jobs_group(data_dir: str, ids: list, group: str) -> int:
    """Group several jobs at once; returns the number successfully grouped."""
    count = 0
    for job_id in [str(i) for i in (ids or []) if i]:
        if set_job_group(data_dir, job_id, group):
            count += 1
    return count


def rename_job(data_dir: str, job_id: str, title: str) -> dict:
    """Rename a job (persisted in its manifest). Returns the new title."""
    real = _job_dir_guarded(data_dir, job_id)
    if real is None:
        raise FileNotFoundError(f"job not found: {job_id}")
    manifest_path = os.path.join(real, "manifest.json")
    man = FileManager.read_json_safe(manifest_path, None)
    if not isinstance(man, dict):
        raise ValueError(f"bad manifest for job {job_id}")
    title = str(title or "").strip()
    if not title:
        raise ValueError("title must not be empty")
    man["title"] = title[:200]
    FileManager.write_json_atomic(manifest_path, man)
    return {"ok": True, "job_id": job_id, "title": man["title"]}


# --------------------------------------------------------------------------- #
# Queue operations
# --------------------------------------------------------------------------- #
def enqueue_job(queue: Any, job_id: str) -> int:
    """Append to the FIFO queue (idempotent). Returns queue position (-1 if
    already active)."""
    return queue.enqueue(job_id)


def reorder_queue(queue: Any, job_id: str, index: int) -> bool:
    return queue.reorder(job_id, int(index))


def run_now(queue: Any, job_id: str) -> bool:
    return queue.run_now(job_id)


def remove_from_queue(queue: Any, job_id: str) -> bool:
    return queue.remove(job_id)


def schedule_job(queue: Any, job_id: str, when: str, tz: str,
                 missed_policy: str) -> None:
    queue.schedule(job_id, when, tz or "local", missed_policy or "run_when_opened")


def unschedule_job(queue: Any, job_id: str) -> bool:
    return queue.unschedule(job_id)


# --------------------------------------------------------------------------- #
# Pause / resume / restart / retry
# --------------------------------------------------------------------------- #
def pause_job(controller: Any) -> bool:
    """Cooperatively pause the active job. Returns True if accepted."""
    try:
        return bool(controller.request_pause())
    except Exception:
        return False


def resume_job(job: Any, controller: Any) -> None:
    """Resume a paused/interrupted job from its checkpoint."""
    try:
        if job.get_lifecycle() in (lc.PAUSED, lc.INTERRUPTED):
            job.set_lifecycle(lc.QUEUED)
        job.set_lifecycle(lc.RUNNING)
    except lc.IllegalTransition:
        pass
    controller.resume()


def restart_job(job: Any) -> None:
    """Reset every stage to pending so the pipeline restarts from the top."""
    for stage in STAGE_ORDER:
        job.set_stage_status(stage, "pending")


def retry_stage(job: Any, controller: Any, stage: str) -> None:
    """Retry a single failed stage, preserving completed upstream work."""
    controller.retry_stage(stage)


# --------------------------------------------------------------------------- #
# Startup reconciliation
# --------------------------------------------------------------------------- #
def reconcile_jobs_on_startup(data_dir: str, session_id: str,
                              job_factory: Callable[[str, str], Any]) -> None:
    """Sweep every persisted job through session-aware reconciliation so a job
    left 'running'/'pause_requested' by a dead session becomes 'interrupted'
    (artifacts preserved). Loading each Job with the current session id
    triggers reconcile_on_load, which persists the corrected lifecycle. Never
    deletes or restarts anything."""
    jobs_dir = os.path.join(data_dir, "jobs")
    if not os.path.isdir(jobs_dir):
        return
    for job_id in os.listdir(jobs_dir):
        if not os.path.isfile(os.path.join(jobs_dir, job_id, "state.json")):
            continue
        try:
            job_factory(job_id, session_id)
        except Exception:
            continue