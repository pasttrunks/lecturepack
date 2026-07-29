"""Security and real-controller boundary checks for Phase 3 guided demo."""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.desktop import engine_adapter
from app.desktop import paths as desktop_paths
from app.desktop.assets import session_job_frames_root
from app.desktop.paths import (
    cleanup_demo_session,
    create_demo_session_dir,
    demo_asset_path,
    demo_temp_root,
    sweep_demo_sessions,
)
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services import transcript_store


ROOT = Path(__file__).resolve().parents[1]


def _load_packaging_spec(monkeypatch):
    """Run the spec's data-list seam without invoking a PyInstaller build."""
    captured = {}
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda _name: []
    hooks.collect_submodules = lambda _name: []
    pyinstaller = ModuleType("PyInstaller")
    utils = ModuleType("PyInstaller.utils")
    pyinstaller.utils = utils
    utils.hooks = hooks

    class _Analysis:
        def __init__(self, _scripts, **kwargs):
            captured["datas"] = kwargs["datas"]
            self.pure = []
            self.zipped_data = []
            self.scripts = []
            self.binaries = []
            self.zipfiles = []
            self.datas = []

    monkeypatch.setitem(sys.modules, "PyInstaller", pyinstaller)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", utils)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    monkeypatch.setattr("PyInstaller.utils.hooks.collect_data_files", hooks.collect_data_files)
    monkeypatch.setattr("PyInstaller.utils.hooks.collect_submodules", hooks.collect_submodules)
    runpy.run_path(str(ROOT / "app" / "packaging" / "lecturepack.spec"), init_globals={
        "SPECPATH": str(ROOT / "app" / "packaging"), "Analysis": _Analysis,
        "PYZ": lambda *_args, **_kwargs: object(), "EXE": lambda *_args, **_kwargs: object(),
        "COLLECT": lambda *_args, **_kwargs: object(),
    })
    return captured["datas"]


@pytest.fixture
def isolated_temp(monkeypatch, tmp_path):
    monkeypatch.setattr("app.desktop.paths.tempfile.gettempdir", lambda: str(tmp_path))
    return tmp_path


def _session_id(n="1"):
    return n * 32


def test_demo_asset_is_real_short_av_media_and_packaged():
    """The frozen build manifest explicitly collects the real bundled asset."""
    asset = Path(demo_asset_path())
    assert asset == ROOT / "app" / "assets" / "demo" / "demo_lecture.mp4"
    assert asset.is_file() and asset.stat().st_size > 100_000
    ffprobe = shutil.which("ffprobe") or str(ROOT / "bin" / "ffprobe.exe")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-show_streams", "-of", "json", str(asset)],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(probe.stdout)
    assert abs(float(payload["format"]["duration"]) - 10.005) < 0.15
    kinds = {stream["codec_type"] for stream in payload["streams"]}
    assert {"video", "audio"} <= kinds
    spec = (ROOT / "app" / "packaging" / "lecturepack.spec").read_text(encoding="utf-8")
    assert "demo_lecture.mp4" in spec and "demo_datas" in spec


def test_packaging_spec_collects_validated_demo_model_and_frozen_lookup(monkeypatch, tmp_path):
    """The build seam collects base.en under models/, where frozen lookup reads it."""
    datas = _load_packaging_spec(monkeypatch)
    model = ROOT / "models" / "ggml-base.en.bin"
    assert (str(model), "models") in datas
    thumbnail = ROOT / "app" / "assets" / "demo" / "polar_bears_thumbnail.jpg"
    assert (str(thumbnail), os.path.join("assets", "demo")) in datas

    meipass = tmp_path / "_internal"
    (meipass / "ui").mkdir(parents=True)
    frozen_model = meipass / "models" / "ggml-base.en.bin"
    frozen_model.parent.mkdir()
    frozen_model.write_bytes(b"approved model fixture")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    adapter = engine_adapter.LecturePackAdapter.__new__(engine_adapter.LecturePackAdapter)
    adapter.config = SimpleNamespace(resource_dir=str(tmp_path / "wrong-root"))
    assert adapter._bundled_demo_model_path(adapter.config) == str(frozen_model)


def test_session_workspace_is_sentinel_owned_and_sweep_is_idempotent(isolated_temp):
    path = Path(create_demo_session_dir(_session_id("a")))
    assert path.parent == Path(demo_temp_root())
    assert json.loads((path / ".lecturepack-demo-session.json").read_text()) == {
        "schema_version": 1, "session_id": _session_id("a"), "directory": path.name,
    }
    (path / "work.json").write_text("{}", encoding="utf-8")
    assert sweep_demo_sessions() == [str(path)]
    assert not path.exists()
    assert sweep_demo_sessions() == []


def test_cleanup_refuses_path_traversal_foreign_and_reparse_entries(isolated_temp, monkeypatch):
    root = Path(demo_temp_root())
    foreign = root / f"demo_{_session_id('b')}"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("must remain", encoding="utf-8")
    normal = root / "normal-job"
    normal.mkdir()
    assert not cleanup_demo_session(str(foreign))
    assert not cleanup_demo_session(str(normal))
    assert not cleanup_demo_session(str(root / ".." / "outside"))
    assert foreign.exists() and normal.exists()

    owned = Path(create_demo_session_dir(_session_id("c")))
    outside = root.parent / "outside-target"
    outside.mkdir()
    (outside / "keep.txt").write_text("must remain", encoding="utf-8")
    try:
        os.symlink(outside, owned / "linked-outside", target_is_directory=True)
    except (OSError, NotImplementedError):
        # Windows CI may deny symlink creation without Developer Mode.  Still
        # exercise the same fail-closed branch with a reparse-point boundary.
        reparse_like = owned / "reparse-like"
        reparse_like.mkdir()
        original = desktop_paths._is_reparse_point
        monkeypatch.setattr(
            desktop_paths, "_is_reparse_point",
            lambda candidate: Path(candidate) == reparse_like or original(Path(candidate)),
        )
    assert not cleanup_demo_session(str(owned), _session_id("c"))
    assert owned.exists() and (outside / "keep.txt").exists()


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _DemoController:
    """Real pipeline boundary double: external process work stays outside unit tests."""
    def __init__(self, config):
        self.config = config
        self.job = None
        self._active_stages = set()
        self.slide_worker = self.align_worker = self.export_worker = None
        self.ffmpeg_wrapper = SimpleNamespace(process=None)
        self.whisper_wrapper = SimpleNamespace(process=None)
        self.run_pipeline_calls = 0
        self.cancel_calls = 0
        for name in ("stage_started", "stage_progress", "stage_log", "stage_finished",
                     "stage_cached", "backend_info", "transcript_segment",
                     "pause_state_changed", "pipeline_completed", "pipeline_failed"):
            setattr(self, name, _Signal())

    def set_job(self, job):
        self.job = job

    def run_pipeline(self):
        self.run_pipeline_calls += 1

    def cancel(self):
        self.cancel_calls += 1


class _Config:
    def __init__(self, data_dir=None):
        self.data_dir = str(data_dir or "persistent")
        self.resource_dir = str(ROOT)
        self.settings = {"ffmpeg_exe": "ffmpeg", "whisper_exe": "whisper", "whisper_model": "model"}
        self.save_calls = 0

    def save(self):
        self.save_calls += 1

    def get(self, key, default=None):
        return self.settings.get(key, default)


def test_start_demo_invokes_isolated_real_controller_and_never_mutates_profile(
        monkeypatch, tmp_path, isolated_temp):
    """A real Job is created from the asset, but external tools are mocked at their boundary."""
    profile = tmp_path / "profile"
    profile.mkdir()
    library = profile / "library.json"
    config_file = profile / "config.json"
    library.write_bytes(b'{"jobs":["normal"]}')
    config_file.write_bytes(b'{"theme":"dark"}')
    before = {p: p.read_bytes() for p in (library, config_file)}
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(profile))
    adapter.config.settings["data_directory"] = str(profile)
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)

    result = adapter.start_demo_job()

    assert result["ok"] and Path(result["workspace"]).parent == Path(demo_temp_root())
    demo = adapter._demo_session
    assert demo["controller"].run_pipeline_calls == 1
    assert demo["job"].manifest["source"]["original_path"] == str(Path(demo_asset_path()).resolve())
    assert demo["job"].manifest["session_scoped"] is True
    assert Path(demo["job"].paths["root"]).is_relative_to(Path(result["workspace"]))
    expected_whisper = {
        "model": str(ROOT / "models" / "ggml-base.en.bin"),
        "profile": "fast", "engine": "whispercpp-cpu",
        "transcription_backend": "local-whispercpp",
    }
    assert expected_whisper.items() <= demo["job"].settings["whisper"].items()
    assert {p: p.read_bytes() for p in (library, config_file)} == before
    event = json.loads(backend.demo_event.emit.call_args.args[0])
    assert event["operation_id"] == result["operation_id"] and event["session_id"] == result["session_id"]

    again = adapter.start_demo_job()
    assert again["idempotent"] is True and again["session_id"] == result["session_id"]
    ended = adapter.end_demo_job("tour_exit")
    assert ended["ok"] and demo["controller"].cancel_calls == 1
    assert not Path(result["workspace"]).exists()
    assert adapter._demo_session is None
    assert {p: p.read_bytes() for p in (library, config_file)} == before


@pytest.mark.parametrize("terminal", ["error", "cancel"])
def test_every_demo_terminal_path_sweeps_only_its_session(
        monkeypatch, tmp_path, isolated_temp, terminal):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    adapter = engine_adapter.LecturePackAdapter(MagicMock(), runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    started = adapter.start_demo_job()
    workspace = Path(started["workspace"])
    demo = adapter._demo_session
    if terminal == "error":
        adapter._on_demo_pipeline_failed(
            demo["controller"], demo["session_id"], demo["operation_id"], "mocked tool failure")
    else:
        adapter.end_demo_job("cancelled")
    assert not workspace.exists()
    assert adapter._demo_session is None


def test_success_projects_review_and_study_then_waits_for_explicit_exit(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    review = MagicMock()
    study = MagicMock()
    monkeypatch.setattr(adapter, "_push_review_data", review)
    monkeypatch.setattr(adapter, "_push_study_data", study)
    started = adapter.start_demo_job()
    demo = adapter._demo_session
    workspace = Path(started["workspace"])

    adapter._on_demo_pipeline_completed(
        demo["controller"], demo["session_id"], demo["operation_id"])

    assert workspace.exists()
    assert adapter._demo_session is demo and adapter.current_job is demo["job"]
    assert session_job_frames_root(demo["job"].job_id) == demo["job"].paths["frames"]
    review.assert_called_once_with()
    study.assert_called_once_with()
    event = json.loads(backend.demo_event.emit.call_args.args[0])
    assert event == {
        "operation": "guided_demo", "operation_id": started["operation_id"],
        "session_id": started["session_id"], "job_id": started["job_id"],
        "status": "review_ready", "stage": "review_ready", "progress": 100,
    }
    assert adapter._list_jobs() == []

    adapter.end_demo_job("tour_exit")
    assert not workspace.exists() and adapter._demo_session is None
    assert session_job_frames_root(demo["job"].job_id) is None


def test_app_exit_and_demo_export_guard_cleanup_without_export_worker(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    monkeypatch.setattr(adapter, "_push_review_data", lambda: None)
    monkeypatch.setattr(adapter, "_push_study_data", lambda: None)
    monkeypatch.setattr(engine_adapter, "ExportWorker",
                        lambda _job: pytest.fail("demo export must not construct ExportWorker"))
    started = adapter.start_demo_job()
    workspace = Path(started["workspace"])

    adapter.export_all(["pdf"])

    assert workspace.exists() and adapter._export_worker is None
    event = json.loads(backend.demo_event.emit.call_args.args[0])
    assert event["status"] == "export_unavailable" and event["stage"] == "export"
    adapter.end_demo_job("app_exit")
    assert not workspace.exists() and adapter._demo_session is None


def test_cleanup_failure_still_revokes_session_asset_registration(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    adapter = engine_adapter.LecturePackAdapter(MagicMock(), runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    started = adapter.start_demo_job()
    demo = adapter._demo_session
    assert session_job_frames_root(demo["job"].job_id) is not None
    monkeypatch.setattr(engine_adapter, "cleanup_demo_session", lambda *_args: False)

    adapter.end_demo_job("tour_exit")

    assert session_job_frames_root(demo["job"].job_id) is None
    assert Path(started["workspace"]).exists()  # cleanup refused, access still revoked


def test_busy_end_request_revokes_assets_before_workspace_cleanup(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    adapter = engine_adapter.LecturePackAdapter(MagicMock(), runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    started = adapter.start_demo_job()
    demo = adapter._demo_session
    demo["controller"]._active_stages.add("export")
    scheduled = []
    monkeypatch.setattr(engine_adapter.QTimer, "singleShot",
                        lambda *_args: scheduled.append(_args))

    result = adapter.end_demo_job("tour_exit")

    assert result["ok"] is True and result["status"] == "cancelling"
    assert session_job_frames_root(demo["job"].job_id) is None
    assert Path(started["workspace"]).exists()
    assert adapter._demo_session is demo and scheduled
    demo["controller"]._active_stages.clear()
    adapter._finish_demo_cleanup("tour_exit")
    assert not Path(started["workspace"]).exists()


def test_cancel_exception_still_revokes_assets_and_attempts_cleanup(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    adapter = engine_adapter.LecturePackAdapter(MagicMock(), runtime_health_result=MagicMock(state="HEALTHY"))
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.win = MagicMock()
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    started = adapter.start_demo_job()
    demo = adapter._demo_session

    def cancel_raises():
        raise RuntimeError("cancel failed")

    demo["controller"].cancel = cancel_raises
    result = adapter.end_demo_job("tour_exit")

    assert result["ok"] is False and result["status"] == "cleanup_pending"
    assert result["error"] == "cancel failed"
    assert session_job_frames_root(demo["job"].job_id) is None
    assert not Path(started["workspace"]).exists()
    assert adapter._demo_session is None


def test_normal_busy_rejects_demo_without_mutating_workspace_or_profile(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    profile = tmp_path / "profile"
    profile.mkdir()
    snapshot = profile / "library.json"
    snapshot.write_bytes(b'{"jobs":["normal"]}')
    adapter.config = _Config(str(profile))
    adapter.current_job = SimpleNamespace(job_id="normal-job", manifest={"title": "Normal"})
    adapter.controller._active_stages.add("transcribe")

    result = adapter.start_demo_job()

    assert result == {
        "ok": False, "status": "normal_processing",
        "error": "Finish or cancel the current lecture before starting the guided demo.",
    }
    assert adapter._demo_session is None
    assert adapter.current_job.job_id == "normal-job"
    assert snapshot.read_bytes() == b'{"jobs":["normal"]}'
    assert list(Path(demo_temp_root()).glob("demo_*")) == []


def test_controller_scoped_callbacks_restore_prior_job_and_ignore_late_signals(
        monkeypatch, tmp_path, isolated_temp):
    monkeypatch.setattr(engine_adapter, "ConfigManager", _Config)
    monkeypatch.setattr(engine_adapter, "JobController", _DemoController)
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter(backend, runtime_health_result=MagicMock(state="HEALTHY"))
    prior = SimpleNamespace(job_id="normal-job", manifest={"title": "Normal"})
    adapter.config = _Config(str(tmp_path / "profile"))
    adapter.current_job = prior
    adapter._pending_job = prior
    adapter._stages = [{"name": "old", "label": "Old", "color": "x", "state": "done", "pct": 100}]
    monkeypatch.setattr(adapter, "push_storage", lambda: None)
    monkeypatch.setattr(adapter, "_push_review_data", lambda: None)
    monkeypatch.setattr(adapter, "_push_study_data", lambda: None)

    started = adapter.start_demo_job()
    demo = adapter._demo_session
    normal = adapter.controller
    event_count = backend.demo_event.emit.call_count
    # A normal-controller signal while a demo owns the UI is ignored entirely.
    normal.stage_started.slots[0]("normal-stage")
    assert backend.demo_event.emit.call_count == event_count
    # The demo's own signal is forwarded and tagged with its session.
    demo["controller"].stage_started.slots[0]("demo-stage")
    assert json.loads(backend.demo_event.emit.call_args.args[0])["session_id"] == started["session_id"]

    adapter.end_demo_job("tour_exit")
    assert adapter.current_job is prior and adapter._pending_job is prior
    event_count = backend.demo_event.emit.call_count
    active_job_count = backend.active_job.emit.call_count
    # Queued signals from the disposed demo must not repaint or end anything.
    demo["controller"].stage_started.slots[0]("late-stage")
    demo["controller"].pipeline_completed.slots[0]()
    assert backend.demo_event.emit.call_count == event_count
    assert backend.active_job.emit.call_count == active_job_count
    assert adapter.current_job is prior and adapter._demo_session is None


def test_real_job_controller_consumes_pinned_demo_whisper_settings(tmp_path, monkeypatch):
    """Mock only the external backend; exercise JobController's request construction."""
    config = ConfigManager(str(tmp_path / "demo"))
    model = ROOT / "models" / "ggml-base.en.bin"
    config.set("whisper_model", str(model))
    job = Job(str(tmp_path / "demo"), video_path=str(Path(demo_asset_path())))
    job.settings["whisper"].update({
        "model": str(model), "profile": "fast", "engine": "whispercpp-cpu",
        "transcription_backend": "local-whispercpp",
    })
    job.save()
    controller = JobController(config)
    controller.set_job(job)
    captured = []

    class _Backend:
        def capabilities(self):
            return SimpleNamespace(is_local=True, label="Local", key="local-whispercpp")

        def start(self, request):
            captured.append(request)

    backend = _Backend()
    monkeypatch.setattr(controller.transcription_backends, "resolve", lambda _key: (backend, "test"))
    monkeypatch.setattr(controller, "_set_transcription_backend", lambda _backend: None)
    monkeypatch.setattr(controller.engine_registry, "resolve",
                        lambda key: SimpleNamespace(key=key, label="CPU", reason="explicit"))

    controller._run_transcribe()

    assert captured[0].model == str(model)
    assert captured[0].local_engine == "whispercpp-cpu"


def test_study_payload_includes_polar_transcript_summary_and_provenance(tmp_path):
    video = tmp_path / "polar.mp4"
    video.write_bytes(b"source")
    job = Job(str(tmp_path / "data"), video_path=str(video))
    transcript_store.save_working(job.paths, [
        {"id": 1, "start": 0.0, "end": 3.0,
         "text": "Polar bears rely on sea ice to hunt seals."},
        {"id": 2, "start": 3.0, "end": 7.0,
         "text": "Their habitat changes as Arctic ice melts."},
    ])
    backend = MagicMock()
    adapter = engine_adapter.LecturePackAdapter.__new__(engine_adapter.LecturePackAdapter)
    adapter.backend = backend
    adapter.current_job = job
    adapter._demo_session = None
    adapter._review_ids = []

    adapter._push_study_data()

    payload = json.loads(backend.study_changed.emit.call_args.args[0])
    assert "Polar bears rely on sea ice" in payload["summary"]
    assert payload["summarySource"] == "deterministic transcript extract"
