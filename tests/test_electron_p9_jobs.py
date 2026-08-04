"""Focused tests for Phase 9 Feature Group 1: job management and queue."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.infrastructure.file_manager import FileManager  # noqa: E402
from lecturepack import electron_backend as eb  # noqa: E402
from lecturepack.services.job_queue import JobQueue  # noqa: E402


@pytest.fixture
def data_dir(tmp_path: Path) -> str:
    (tmp_path / "jobs").mkdir()
    return str(tmp_path)


def _make_job(data_dir: str, job_id: str, title: str = "Lecture") -> str:
    job_dir = Path(data_dir) / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    FileManager.write_json_atomic(
        str(job_dir / "manifest.json"),
        {"job_id": job_id, "title": title, "created_at": "2026-01-01T00:00:00"},
    )
    FileManager.write_json_atomic(
        str(job_dir / "state.json"),
        {"lifecycle": "new", "overall_status": "pending", "stages": {}},
    )
    (job_dir / "source.json").write_text("{}", encoding="utf-8")
    return str(job_dir)


# ---- safe deletion ------------------------------------------------------ #
def test_delete_one_rejects_unsafe_job_id(data_dir: str):
    res = eb.delete_one(data_dir, "../../outside")
    assert res["ok"] is False


def test_delete_one_rejects_missing_job(data_dir: str):
    assert eb.delete_one(data_dir, "does-not-exist")["ok"] is False


def test_delete_one_never_touches_unrelated_directories(data_dir: str):
    _make_job(data_dir, "job-a")
    _make_job(data_dir, "job-b")
    unrelated = Path(data_dir) / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep", encoding="utf-8")

    assert eb.delete_one(data_dir, "job-a")["ok"] is True
    assert not (Path(data_dir) / "jobs" / "job-a").exists()
    assert (Path(data_dir) / "jobs" / "job-b").exists()
    assert (unrelated / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_delete_job_payload_shape(data_dir: str):
    _make_job(data_dir, "job-a")
    payload = eb.delete_job(data_dir, "job-a")
    assert payload["ok"] is True
    assert payload["id"] == "job-a"
    assert "freed" in payload
    assert payload["method"] in ("recycle bin", "permanently")


def test_delete_jobs_bulk_payload(data_dir: str):
    _make_job(data_dir, "job-a")
    _make_job(data_dir, "job-b")
    payload = eb.delete_jobs(data_dir, ["job-a", "job-b", "missing"])
    assert payload["ok"] is True
    assert payload["bulk"] is True
    assert payload["count"] == 2
    assert set(payload["ids"]) == {"job-a", "job-b"}
    assert payload["failed"] == ["missing"]


def test_delete_jobs_empty_selection(data_dir: str):
    payload = eb.delete_jobs(data_dir, [])
    assert payload["ok"] is False
    assert payload["count"] == 0


# ---- grouping and rename ------------------------------------------------ #
def test_set_job_group_persists_manifest(data_dir: str):
    _make_job(data_dir, "job-a", title="Physics 101: Lecture 1")
    assert eb.set_job_group(data_dir, "job-a", "Physics") is True
    man = FileManager.read_json_safe(
        str(Path(data_dir) / "jobs" / "job-a" / "manifest.json"), {})
    assert man["group"] == "Physics"


def test_set_job_group_clears_group(data_dir: str):
    _make_job(data_dir, "job-a")
    eb.set_job_group(data_dir, "job-a", "Physics")
    assert eb.set_job_group(data_dir, "job-a", "") is True
    man = FileManager.read_json_safe(
        str(Path(data_dir) / "jobs" / "job-a" / "manifest.json"), {})
    assert "group" not in man


def test_set_job_group_rejects_unsafe_id(data_dir: str):
    assert eb.set_job_group(data_dir, "../evil", "Physics") is False


def test_set_jobs_group_counts(data_dir: str):
    _make_job(data_dir, "job-a")
    _make_job(data_dir, "job-b")
    assert eb.set_jobs_group(data_dir, ["job-a", "job-b", "missing"], "Physics") == 2


def test_rename_job(data_dir: str):
    _make_job(data_dir, "job-a", title="Old Title")
    result = eb.rename_job(data_dir, "job-a", "New Title")
    assert result["ok"] is True
    assert result["title"] == "New Title"
    man = FileManager.read_json_safe(
        str(Path(data_dir) / "jobs" / "job-a" / "manifest.json"), {})
    assert man["title"] == "New Title"


def test_rename_job_rejects_empty_title(data_dir: str):
    _make_job(data_dir, "job-a")
    with pytest.raises(ValueError):
        eb.rename_job(data_dir, "job-a", "   ")


def test_rename_job_rejects_unsafe_id(data_dir: str):
    with pytest.raises(FileNotFoundError):
        eb.rename_job(data_dir, "../evil", "New Title")


# ---- queue operations --------------------------------------------------- #
def test_queue_enqueue_reorder_run_now_remove(data_dir: str):
    for jid in ("job-a", "job-b", "job-c"):
        _make_job(data_dir, jid)
    q = JobQueue(data_dir)

    assert eb.enqueue_job(q, "job-a") == 0
    assert eb.enqueue_job(q, "job-b") == 1
    assert eb.enqueue_job(q, "job-c") == 2
    assert q.queued() == ["job-a", "job-b", "job-c"]

    assert eb.reorder_queue(q, "job-c", 0) is True
    assert q.queued() == ["job-c", "job-a", "job-b"]

    assert eb.run_now(q, "job-b") is True
    assert q.queued() == ["job-b", "job-c", "job-a"]

    assert eb.remove_from_queue(q, "job-c") is True
    assert q.queued() == ["job-b", "job-a"]


def test_queue_schedule_unschedule(data_dir: str):
    _make_job(data_dir, "job-a")
    q = JobQueue(data_dir)
    eb.schedule_job(q, "job-a", "2026-12-31T23:59:00", "local", "run_when_opened")
    assert "job-a" in q.schedules()
    assert eb.unschedule_job(q, "job-a") is True
    assert "job-a" not in q.schedules()


def test_queue_restores_persisted_state(data_dir: str):
    _make_job(data_dir, "job-a")
    _make_job(data_dir, "job-b")
    q1 = JobQueue(data_dir)
    eb.enqueue_job(q1, "job-a")
    eb.enqueue_job(q1, "job-b")

    q2 = JobQueue(data_dir)
    assert q2.queued() == ["job-a", "job-b"]


def test_queue_promote_next_one_active_invariant(data_dir: str):
    _make_job(data_dir, "job-a")
    _make_job(data_dir, "job-b")
    q = JobQueue(data_dir)
    eb.enqueue_job(q, "job-a")
    eb.enqueue_job(q, "job-b")

    assert q.promote_next() == "job-a"
    assert q.active == "job-a"
    assert q.promote_next() is None
    q.finish_active("job-a")
    assert q.promote_next() == "job-b"