"""Phase 3 checks for an empty healthy Home and persistent-library isolation."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.desktop.engine_adapter import LecturePackAdapter


def _adapter(tmp_path):
    config = MagicMock()
    config.data_dir = str(tmp_path)
    config.get.side_effect = lambda key, default="": default
    backend = MagicMock()
    adapter = LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = config
    adapter.queue.data_dir = str(tmp_path)
    return adapter, backend


def test_healthy_startup_opens_empty_home_but_keeps_library_visible(tmp_path, monkeypatch):
    """HOME-01/02: boot never chooses a job; existing cards still arrive."""
    jobs = tmp_path / "jobs"
    job_dir = jobs / "persisted-job"
    job_dir.mkdir(parents=True)
    (job_dir / "manifest.json").write_text(json.dumps({
        "title": "Existing lecture", "created_at": "2026-07-29T00:00:00Z",
    }), encoding="utf-8")
    (job_dir / "state.json").write_text(json.dumps({"overall_status": "completed", "stages": {}}), encoding="utf-8")
    (job_dir / "source.json").write_text("{}", encoding="utf-8")
    adapter, backend = _adapter(tmp_path)
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    monkeypatch.setattr(adapter, "_reconcile_jobs_on_startup", lambda: None)
    monkeypatch.setattr(adapter, "validate_vulkan", lambda: None)
    monkeypatch.setattr(adapter, "validate_cuda", lambda: None)
    monkeypatch.setattr(adapter, "cuda_pack_status", lambda: None)
    monkeypatch.setattr(adapter, "smart_study_status", lambda: None)

    adapter.on_ui_ready()

    backend.active_job.emit.assert_called_with(json.dumps({"id": "", "title": ""}))
    visible = json.loads(backend.jobs_changed.emit.call_args.args[0])
    assert [item["id"] for item in visible] == ["persisted-job"]
    assert adapter.current_job is None


def test_session_scoped_job_never_enters_persistent_library(tmp_path):
    """HOME-03: a session marker excludes only that job, not normal jobs."""
    jobs = tmp_path / "jobs"
    for job_id, session_scoped in (("normal-job", False), ("demo-job", True)):
        job_dir = jobs / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "manifest.json").write_text(json.dumps({
            "title": job_id, "created_at": "2026-07-29T00:00:00Z",
            "session_scoped": session_scoped,
        }), encoding="utf-8")
        (job_dir / "state.json").write_text("{}", encoding="utf-8")
        (job_dir / "source.json").write_text("{}", encoding="utf-8")

    adapter, _backend = _adapter(tmp_path)
    assert [item["id"] for item in adapter._list_jobs()] == ["normal-job"]
