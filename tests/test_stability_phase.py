"""Focused v1.2 stability and minor-workflow regression tests."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess

from lecturepack.constants import STAGE_EXPORT, STAGE_TRANSCRIBE
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.services.ai_repair_service import AiRepairWorker
from lecturepack.ui.main_window import MainWindow, PAGE_REVIEW


FIXTURES = Path(__file__).parent / "fixtures"
VIDEO = str((FIXTURES / "synthetic_lecture.mp4").resolve())
MOCK_WHISPER = str((FIXTURES / "mock_whisper.py").resolve())
MOCK_FFMPEG = str((FIXTURES / "mock_ffmpeg.py").resolve())
MOCK_FFPROBE = str((FIXTURES / "mock_ffprobe.py").resolve())


@pytest.fixture()
def window(qtbot, tmp_path):
    # Reuse the established v1.1 native-window fixture builder so these tests
    # exercise the same review/transcript surfaces as the existing UI suite.
    import importlib.util
    fixture_path = Path(__file__).with_name("test_ui_v11.py")
    spec = importlib.util.spec_from_file_location("stability_ui_fixture", fixture_path)
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    _make_job = fixture_module._make_job
    data_dir, job = _make_job(tmp_path)
    config = ConfigManager(data_dir)
    win = MainWindow(config)
    qtbot.addWidget(win)
    win.current_job = job
    win.controller.set_job(job)
    win._load_review_data()
    win.stack.setCurrentIndex(PAGE_REVIEW)
    win.show()
    qtbot.waitExposed(win)
    return win


def _process_exists(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, timeout=5, check=False)
    return str(pid) in result.stdout


def _read_pid_file(path: Path, timeout_seconds: float = 3.0) -> int:
    """Wait through Windows/AV create-and-scan races for a complete PID."""
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = path.read_text(encoding="ascii").strip()
            if value.isdigit():
                return int(value)
        except (OSError, UnicodeError) as exc:
            last_error = exc
        time.sleep(0.02)
    raise AssertionError(f"PID file did not become readable: {last_error}")


def _minimal_norm():
    return {
        "schema_version": 1,
        "raw_content_hash": "stability-test",
        "segments": [{
            "id": 1, "start": 0.0, "end": 1.0, "text": "test",
            "origin_ids": [1], "edited": False,
        }],
    }


def _start_blocking_worker(tmp_path, seconds=1.2):
    worker = AiRepairWorker(str(tmp_path), [], _minimal_norm())
    worker._run_inner = lambda: time.sleep(seconds)
    thread = worker.start()
    return worker, thread


def _sig(path: Path):
    data = path.read_bytes()
    stat = path.stat()
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _protected_artifacts(job):
    paths = [Path(job.paths["audio"]) / "lecture-16khz-mono.wav",
             Path(job.paths["root"]) / "candidates.json"]
    paths.extend(sorted(Path(job.paths["transcript"]).glob("raw.*")))
    paths.extend(sorted(Path(job.paths["candidates"]).glob("*")))
    return [p for p in paths if p.is_file()]


def _controller(data_dir):
    config = ConfigManager(str(data_dir))
    config.set("whisper_exe", MOCK_WHISPER)
    config.set("whisper_model", "ggml-base.bin")
    controller = JobController(config)
    controller.ffmpeg_wrapper.ffmpeg_path = MOCK_FFMPEG
    controller.ffmpeg_wrapper.ffprobe_path = MOCK_FFPROBE
    return config, controller


def test_config_bom_and_legacy_settings_migrate_and_survive_restart(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    config_path = data / "config.json"
    legacy = {"backend": "vulkan", "dark_theme": True,
              "custom_future_key": {"keep": True}}
    config_path.write_text("\ufeff" + json.dumps(legacy), encoding="utf-8")

    first = ConfigManager(str(data))
    assert first.get("engine") == "vulkan"
    assert first.get("parallel_pipeline") is True
    assert first.get("custom_future_key") == {"keep": True}
    first.set("dark_theme", False)

    second = ConfigManager(str(data))
    assert second.get("engine") == "vulkan"
    assert second.get("dark_theme") is False
    assert second.get("custom_future_key") == {"keep": True}
    assert second.get("schema_version") == 1


def test_backend_actual_value_persists_and_reloads(qtbot, tmp_path):
    config = ConfigManager(str(tmp_path / "data"))
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller = JobController(config)
    controller.set_job(job)

    controller.whisper_wrapper.backend_detected.emit("Vulkan (Vulkan0)")
    qtbot.wait(20)
    persisted = FileManager.read_json_safe(job.state_path, {})
    assert persisted["stages"][STAGE_TRANSCRIBE]["backend_used"] == "Vulkan (Vulkan0)"

    reopened = Job(str(tmp_path / "data"), job_id=job.job_id)
    messages = []
    controller.backend_info.connect(messages.append)
    controller.set_job(reopened)
    assert messages[-1] == "loaded backend: Vulkan (Vulkan0)"


def test_main_window_displays_persisted_actual_backend(window, qtbot):
    window.current_job.state["stages"][STAGE_TRANSCRIBE]["backend_used"] = "CPU"
    window.current_job.save()
    window.controller.set_job(window.current_job)
    assert window.sb_engine.text() == "loaded backend: CPU"
    # A capability probe describes the binary; it must not overwrite the
    # backend proven by an actual run.
    window._on_whisper_detection_finished("whisper-cli.exe", {
        "backend": "Vulkan", "version": "1.9.1", "flags": set()})
    assert window.sb_engine.text() == "loaded backend: CPU"


def test_context_repair_detach_is_nonblocking(qtbot, tmp_path):
    worker, thread = _start_blocking_worker(tmp_path)
    qtbot.wait(80)
    started = time.perf_counter()
    worker.detach_and_stop()
    elapsed = time.perf_counter() - started
    print(f"worker_detach_seconds={elapsed:.6f}")
    assert elapsed < 0.15
    qtbot.waitUntil(thread.isFinished, timeout=3000)
    thread.wait(100)


def test_context_repair_dialog_close_is_nonblocking(window, qtbot, tmp_path):
    from lecturepack.ui.context_repair_dialog import ContextRepairDialog
    dialog = ContextRepairDialog(window.current_job, window.config_manager, window)
    qtbot.addWidget(dialog)
    worker, thread = _start_blocking_worker(tmp_path)
    dialog.panel._worker = worker
    dialog.show()
    qtbot.wait(80)
    started = time.perf_counter()
    dialog.close()
    elapsed = time.perf_counter() - started
    print(f"dialog_close_seconds={elapsed:.6f}")
    assert elapsed < 0.15
    qtbot.waitUntil(thread.isFinished, timeout=3000)
    thread.wait(100)


def test_main_window_close_cancels_pipeline_and_repair_nonblocking(
        window, qtbot, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(window.controller, "cancel", lambda: calls.append("cancel"))
    worker, thread = _start_blocking_worker(tmp_path)
    window.transcript_page._repair_panel._worker = worker
    qtbot.wait(80)
    started = time.perf_counter()
    window.close()
    elapsed = time.perf_counter() - started
    print(f"app_close_seconds={elapsed:.6f}")
    assert calls == ["cancel"]
    assert elapsed < 0.15
    qtbot.waitUntil(thread.isFinished, timeout=3000)
    thread.wait(100)


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
def test_main_window_close_terminates_active_whisper_tree(
        window, qtbot, tmp_path, monkeypatch):
    child_pid_file = tmp_path / "app-close-child.pid"
    monkeypatch.setenv("LECTUREPACK_TREE_PID_FILE", str(child_pid_file))
    wrapper = window.controller.whisper_wrapper
    wrapper.whisper_exe_path = str(FIXTURES / "process_tree_parent.py")
    wrapper.start_transcription(
        str(tmp_path / "audio.wav"), str(tmp_path / "model.bin"),
        str(tmp_path / "raw"))
    assert wrapper.process.waitForStarted(3000)
    qtbot.waitUntil(child_pid_file.exists, timeout=3000)
    parent_pid = int(wrapper.process.processId())
    child_pid = _read_pid_file(child_pid_file)
    window.controller.current_stage = STAGE_TRANSCRIBE
    window.controller._active_stages = {STAGE_TRANSCRIBE}

    window.close()
    qtbot.waitUntil(lambda: not _process_exists(parent_pid), timeout=5000)
    qtbot.waitUntil(lambda: not _process_exists(child_pid), timeout=5000)
    assert wrapper.last_cancel_report["finished"] is True
    print("app_close_cleanup=" + json.dumps(
        {**wrapper.last_cancel_report, "child_pid": child_pid}, sort_keys=True))


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
def test_owned_process_tree_terminated_but_unrelated_process_survives(qtbot, tmp_path):
    from lecturepack.infrastructure.process_tree import terminate_qprocess_tree

    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    qprocess = QProcess()
    child_pid_file = tmp_path / "child.pid"
    qprocess.start(sys.executable, [str(FIXTURES / "process_tree_parent.py"),
                                    str(child_pid_file)])
    try:
        assert qprocess.waitForStarted(3000)
        qtbot.waitUntil(child_pid_file.exists, timeout=3000)
        child_pid = _read_pid_file(child_pid_file)
        parent_pid = int(qprocess.processId())
        assert _process_exists(parent_pid) and _process_exists(child_pid)

        report = terminate_qprocess_tree(qprocess)
        print("process_tree_report=" + json.dumps(report, sort_keys=True))
        assert report["root_pid"] == parent_pid
        qtbot.waitUntil(lambda: not _process_exists(parent_pid), timeout=5000)
        qtbot.waitUntil(lambda: not _process_exists(child_pid), timeout=5000)
        assert _process_exists(unrelated.pid), "unrelated process must never be killed"
    finally:
        if qprocess.state() == QProcess.ProcessState.Running:
            qprocess.kill()
            qprocess.waitForFinished(2000)
        unrelated.kill()
        unrelated.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
@pytest.mark.parametrize("wrapper_kind", ["ffmpeg", "whisper"])
def test_real_wrappers_terminate_their_owned_trees(
        qtbot, tmp_path, monkeypatch, wrapper_kind):
    child_pid_file = tmp_path / f"{wrapper_kind}-child.pid"
    monkeypatch.setenv("LECTUREPACK_TREE_PID_FILE", str(child_pid_file))
    parent_script = str(FIXTURES / "process_tree_parent.py")

    if wrapper_kind == "ffmpeg":
        from lecturepack.infrastructure.ffmpeg_wrapper import FFmpegWrapper
        wrapper = FFmpegWrapper()
        wrapper.ffmpeg_path = parent_script
        wrapper.start_audio_extraction(VIDEO, str(tmp_path / "out.wav"))
    else:
        from lecturepack.infrastructure.whisper_wrapper import WhisperWrapper
        wrapper = WhisperWrapper(parent_script)
        wrapper.start_transcription(
            str(tmp_path / "audio.wav"), str(tmp_path / "model.bin"),
            str(tmp_path / "raw"))

    assert wrapper.process.waitForStarted(3000)
    qtbot.waitUntil(child_pid_file.exists, timeout=3000)
    parent_pid = int(wrapper.process.processId())
    child_pid = _read_pid_file(child_pid_file)
    assert _process_exists(parent_pid) and _process_exists(child_pid)
    wrapper.cancel()
    qtbot.waitUntil(lambda: not _process_exists(parent_pid), timeout=5000)
    qtbot.waitUntil(lambda: not _process_exists(child_pid), timeout=5000)
    assert wrapper.last_cancel_report["root_pid"] == parent_pid
    assert wrapper.last_cancel_report["finished"] is True
    print(f"{wrapper_kind}_cleanup=" + json.dumps(
        {**wrapper.last_cancel_report, "child_pid": child_pid}, sort_keys=True))


def test_reexport_preserves_audio_transcript_and_candidate_signatures(qtbot, tmp_path):
    _, controller = _controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)
    with qtbot.waitSignal(controller.pipeline_completed, timeout=120000):
        controller.run_pipeline()

    protected = _protected_artifacts(job)
    assert protected
    before = {str(path): _sig(path) for path in protected}
    with qtbot.waitSignal(controller.stage_finished, timeout=120000,
                          check_params_cb=lambda stage, ok, error: stage == STAGE_EXPORT):
        controller.export_now()
    after = {str(path): _sig(path) for path in protected}
    print("reexport_signatures=" + json.dumps(
        {"artifact_count": len(before), "before": before, "after": after},
        sort_keys=True))
    assert after == before
