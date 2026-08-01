"""Phase 2 Plan 2: normal-import job lifecycle regression tests.

Proves that on a clean install (no manual config.set("whisper_exe", ...) /
"ffmpeg_exe" / "ffprobe_exe") the existing job persistence machinery
(job_lifecycle.py, job_queue.py, _list_jobs, _push_jobs, _set_active_job,
_reconcile_jobs_on_startup) works exactly as designed, now that Plan 01's
runtime-path fix lets start_processing()'s whisper gate resolve via
EngineRegistry.resolve() instead of a raw (empty, on a clean install)
config read.

These tests deliberately do NOT call config.set("whisper_exe"/"ffmpeg_exe"/
"ffprobe_exe", ...). Instead they rely on:
  - FFmpegWrapper.detect_binaries()'s own dev-tree fallback (bin/ffmpeg.exe,
    bin/ffprobe.exe already exist in this repo), and
  - EngineRegistry._cpu_exe()'s dev-tree fallback (bin/Release/whisper-cli.exe
    already exists in this repo), and
  - ConfigManager.persist_runtime_health(bundled_model=...), which is the real
    one-time migration path that seeds whisper_model on a clean install.

controller.run_pipeline() is mocked in every test that reaches start_processing
so no real whisper-cli.exe/ffmpeg.exe subprocess is spawned; this file proves
the *lifecycle bookkeeping* around a real pipeline call, not the pipeline
itself (that is covered by test_product_modes.py / test_integration.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.desktop import engine_adapter
from lecturepack import constants
from lecturepack.infrastructure.config_manager import ConfigManager as RealConfigManager
from lecturepack.models import job_lifecycle as lc
from lecturepack.models.job import Job

ROOT = Path(__file__).resolve().parents[1]
VIDEO = str(ROOT / "tests" / "fixtures" / "synthetic_lecture.mp4")
MODEL = str(ROOT / "models" / "ggml-base.en.bin")


def _build_adapter(tmp_path, monkeypatch):
    """A real LecturePackAdapter wired to a real (tmp_path-scoped) ConfigManager
    and a real JobController -- never the real ~/LecturePackData profile, and
    never a manually-set whisper/ffmpeg exe path in config.
    """
    monkeypatch.setattr(engine_adapter, "ConfigManager",
                        lambda: RealConfigManager(str(tmp_path)))
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(
        backend, runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    return adapter, backend


def _seed_clean_install_whisper_model(adapter):
    """Simulate Plan 01's boot-time seeding of whisper_model -- the ONLY thing
    a clean install needs beyond the dev-tree exe fallbacks above. Never calls
    config.set("whisper_exe"/"ffmpeg_exe"/"ffprobe_exe", ...) directly.
    """
    adapter.config.persist_runtime_health(
        {"components": {"whisper": {"ok": True}}}, bundled_model=MODEL)


def _emitted_payloads(signal_mock) -> list[dict]:
    return [json.loads(c.args[0]) for c in signal_mock.emit.call_args_list]


# --------------------------------------------------------------- Task 1 -----

def test_import_video_emits_active_job_with_correct_identity(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)

    adapter.import_video(VIDEO)

    job = adapter.current_job
    assert job is not None
    payloads = _emitted_payloads(backend.active_job)
    assert payloads, "active_job signal never emitted"
    last = payloads[-1]
    assert last["id"] == job.job_id
    assert last["title"] == "synthetic_lecture"
    assert last["title"]


def test_import_then_start_transitions_through_lifecycle(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    _seed_clean_install_whisper_model(adapter)
    monkeypatch.setattr(adapter.controller, "run_pipeline", MagicMock())

    adapter.import_video(VIDEO)
    job = adapter.current_job
    assert job.get_lifecycle() == lc.NEW

    transitions = []
    real_set_lifecycle = job.set_lifecycle

    def _tracking_set_lifecycle(new_state, owner=None):
        real_set_lifecycle(new_state, owner=owner)
        transitions.append(new_state)

    monkeypatch.setattr(job, "set_lifecycle", _tracking_set_lifecycle)

    adapter.start_processing("study")

    # NEW -> QUEUED -> RUNNING, in that order, with no IllegalTransition
    # silently swallowed along the way.
    assert transitions == [lc.QUEUED, lc.RUNNING]
    assert job.get_lifecycle() == lc.RUNNING
    assert adapter.controller.run_pipeline.call_count == 1

    # SC-03: the job is visible in _list_jobs while genuinely running (the
    # real controller would have set exactly this stage status by now).
    job.set_stage_status(constants.STAGE_TRANSCRIBE, "running")
    rows = {r["id"]: r for r in adapter._list_jobs()}
    assert rows[job.job_id]["status"] == "running"
    assert rows[job.job_id]["stage"] == constants.STAGE_TRANSCRIBE


def test_pipeline_failure_leaves_job_in_failed_state(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    _seed_clean_install_whisper_model(adapter)
    monkeypatch.setattr(adapter.controller, "run_pipeline", MagicMock())

    adapter.import_video(VIDEO)
    job = adapter.current_job
    adapter.start_processing("study")
    assert job.get_lifecycle() == lc.RUNNING

    backend.reset_mock()
    adapter.controller.pipeline_failed.emit("mocked tool failure")

    assert job.get_lifecycle() == lc.FAILED
    rows = {r["id"]: r for r in adapter._list_jobs()}
    assert rows[job.job_id]["status"] == "failed"
    # jobs_changed fired as part of the failure path -- not silently cleared.
    assert backend.jobs_changed.emit.called


def test_push_jobs_includes_job_through_all_status_transitions(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    _seed_clean_install_whisper_model(adapter)
    monkeypatch.setattr(adapter.controller, "run_pipeline", MagicMock())

    adapter.import_video(VIDEO)
    job = adapter.current_job

    rows = {r["id"]: r for r in adapter._list_jobs()}
    assert rows[job.job_id]["status"] == "pending"

    adapter.start_processing("study")
    job.set_stage_status(constants.STAGE_TRANSCRIBE, "running")
    rows = {r["id"]: r for r in adapter._list_jobs()}
    assert rows[job.job_id]["status"] == "running"

    adapter._on_pipeline_completed()
    assert job.get_lifecycle() == lc.COMPLETED
    rows = {r["id"]: r for r in adapter._list_jobs()}
    assert rows[job.job_id]["status"] == "done"


def test_demo_signals_do_not_corrupt_normal_workspace(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    adapter.import_video(VIDEO)
    normal_job = adapter.current_job

    called = []

    class _OtherController:
        pass

    # A signal claiming to come from a controller that is not self.controller
    # is blocked outright, regardless of demo-session state.
    adapter._forward_normal(_OtherController(), lambda *a: called.append(a), "x")
    assert called == []

    # Even the real controller's own signal is blocked while a demo owns the
    # workspace (engine_adapter.py:792-795's second guard condition).
    adapter._demo_session = {"session_id": "fake-demo"}
    adapter._forward_normal(adapter.controller, lambda *a: called.append(a), "y")
    assert called == []

    # Once the demo ends, the real controller's signal is forwarded again.
    adapter._demo_session = None
    adapter._forward_normal(adapter.controller, lambda *a: called.append(a), "z")
    assert called == [("z",)]

    # Throughout, the normal workspace's active job was never touched.
    assert adapter.current_job is normal_job


# --------------------------------------------------------------- Task 2 -----

def test_set_active_job_emits_signal_with_id_and_title(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    job = Job(adapter.config.data_dir, video_path=VIDEO)

    adapter._set_active_job(job)

    payload = _emitted_payloads(backend.active_job)[-1]
    assert payload["id"] == job.job_id
    assert payload["title"] == "synthetic_lecture"
    assert payload["title"]


def test_on_ui_ready_triggers_push_jobs(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    for name in ("_probe_ollama_async", "validate_vulkan", "validate_cuda",
                 "cuda_pack_status", "_emit_groq_status", "smart_study_status"):
        monkeypatch.setattr(adapter, name, lambda *a, **k: None)

    adapter.import_video(VIDEO)
    job = adapter.current_job
    backend.reset_mock()

    adapter.on_ui_ready()

    assert backend.jobs_changed.emit.called
    payload = _emitted_payloads(backend.jobs_changed)[-1]
    ids = {row["id"] for row in payload}
    assert job.job_id in ids


def test_reconcile_jobs_on_startup_demotes_stale_running_to_interrupted(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    job = Job(adapter.config.data_dir, video_path=VIDEO)
    job.state["lifecycle"] = lc.RUNNING
    job.state["session"] = lc.SessionOwner(
        session_id="dead-session-from-a-prior-launch", process_id=999_999_937,
    ).to_dict()
    job.save()
    assert job.get_lifecycle() == lc.RUNNING
    # This session id is guaranteed not to match the adapter's own.
    assert adapter._session_id != "dead-session-from-a-prior-launch"

    adapter._reconcile_jobs_on_startup()

    reloaded = Job(adapter.config.data_dir, job_id=job.job_id,
                   current_session_id=adapter._session_id)
    assert reloaded.get_lifecycle() == lc.INTERRUPTED


def test_list_jobs_returns_complete_job_with_done_status(tmp_path, monkeypatch):
    adapter, backend = _build_adapter(tmp_path, monkeypatch)
    job = Job(adapter.config.data_dir, video_path=VIDEO)
    job.set_lifecycle(lc.QUEUED)
    job.set_lifecycle(lc.RUNNING, owner=lc.SessionOwner(
        session_id=adapter._session_id, process_id=os.getpid()))
    job.set_lifecycle(lc.COMPLETED)

    rows = {r["id"]: r for r in adapter._list_jobs()}

    row = rows[job.job_id]
    assert row["status"] == "done"
    assert row["id"] and row["name"] and row["status"]
