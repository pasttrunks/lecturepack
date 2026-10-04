"""Focused tests for the packaged-app acceptance gate (no real packaged app needed).

These cover the acceptance gate's logic with mocks / a throwaway fake
executable. They deliberately do not launch the real Electron or sidecar
binaries, which live in Luna's active worktree.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "electron_packaged_acceptance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("electron_packaged_acceptance", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


m = _load_module()


def _load_ai_study_module():
    script_path = ROOT / "scripts" / "ai_study_packaged_acceptance.py"
    spec = importlib.util.spec_from_file_location("ai_study_packaged_acceptance", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


ai_study = _load_ai_study_module()


def _passing_checks(**overrides) -> dict:
    checks = {
        "app_launched": True,
        "sidecar_ready": True,
        "runtime_paths_ready": True,
        "job_started": True,
        "job_completed": True,
        "slides_generated": True,
        "transcript_generated": True,
        "export_completed": True,
        "export_file_count": 3,
        "first_exit_clean": True,
        "restore_passed": True,
        "orphan_processes": [],
        "renderer_failures": [],
        "bridge_errors": [],
        "unexpected_errors": [],
    }
    checks.update(overrides)
    return checks


def test_required_cli_arguments_and_safe_data_validation():
    with pytest.raises(SystemExit):
        m.parse_args([])
    with pytest.raises(SystemExit):
        m.parse_args(["--app-dir", "pkg"])
    with pytest.raises(SystemExit):
        m.parse_args(["--data-dir", "data"])

    args = m.parse_args(["--app-dir", "pkg", "--data-dir", "data"])
    assert args.app_dir == "pkg"
    assert args.data_dir == "data"
    assert args.timeout_seconds == 300.0
    assert args.keep_data is False

    allowed, reason = m.data_dir_status(str(Path("some-disposable-dir").resolve()))
    assert allowed is True
    assert reason == ""


def test_runner_refuses_normal_lecturepackdata():
    home = m._home()
    for candidate in (
        home / m.FORBIDDEN_DIRNAME,
        home / "Documents" / m.FORBIDDEN_DIRNAME,
        home / "Desktop" / m.FORBIDDEN_DIRNAME,
    ):
        allowed, reason = m.data_dir_status(str(candidate))
        assert allowed is False
        assert "LecturePackData" in reason

    # The CLI entry point must refuse to run on the normal location (exit 2).
    exit_code = m.main(["--app-dir", "pkg", "--data-dir", str(home / m.FORBIDDEN_DIRNAME)])
    assert exit_code == 2


def test_timeout_failure_produces_useful_result_not_hang():
    start = __import__("time").monotonic()
    with pytest.raises(TimeoutError):
        m.poll_until(lambda: False, timeout_s=0.2, interval_s=0.01, label="test-never")
    elapsed = __import__("time").monotonic() - start
    assert elapsed < 5.0  # bounded: it must not hang

    # A partial/timeout result still yields a structured machine-usable result.
    partial = _passing_checks(job_completed=False, export_file_count=0)
    result = m.score_result(partial)
    assert result["job_completed"] is False
    assert result["export_file_count"] == 0
    assert result["passed"] is False
    assert set(result) == set(m.ACCEPTANCE_KEYS)


def test_process_tree_cleanup_detection_with_mocked_processes():
    before = [
        {"name": "python.exe", "pid": 100},
        {"name": "explorer.exe", "pid": 200},
    ]
    after = [
        {"name": "python.exe", "pid": 100},          # same pid -> not orphan
        {"name": "explorer.exe", "pid": 200},
        {"name": "ffmpeg.exe", "pid": 900},          # new app-family pid -> orphan
        {"name": "LecturePackSidecar.exe", "pid": 901},
        {"name": "notepad.exe", "pid": 902},         # unrelated -> ignored
    ]
    orphans = m.detect_orphans(before, after)
    assert orphans == ["LecturePackSidecar.exe", "ffmpeg.exe"]

    assert m.detect_orphans(before, before) == []
    assert "python.exe" not in orphans


def test_expected_export_evidence_is_validated(tmp_path):
    job_dir = tmp_path / "jobs" / "job-1"
    export_dir = job_dir / "exports"
    export_dir.mkdir(parents=True)
    (export_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (export_dir / "study_pack.pdf").write_bytes(b"x")
    (export_dir / "slides").mkdir()
    (export_dir / "slides" / "001.png").write_bytes(b"x")

    evidence = m.validate_export(job_dir, export_dir)
    assert evidence["export_completed"] is True
    assert evidence["export_file_count"] == 3
    assert "manifest.json" in evidence["files"]
    assert "slides/001.png" in evidence["files"]

    existing_engine_export = tmp_path / "jobs" / "job-2" / "exports"
    existing_engine_export.mkdir(parents=True)
    (existing_engine_export / "study-pack.html").write_text("<html />", encoding="utf-8")
    assert m.validate_export(tmp_path / "jobs" / "job-2", existing_engine_export)["export_completed"] is True

    empty = m.validate_export(tmp_path / "missing", tmp_path / "missing" / "exports")
    assert empty["export_completed"] is False
    assert empty["export_file_count"] == 0


def test_sidecar_event_history_preserves_completion_evidence():
    session = m.JsonlSession(Path("unused-sidecar.exe"), [])
    session.messages.append({"event": "export_done", "job": "job-1"})

    observed = session.wait_event("export_done", timeout=0.01)

    assert observed["job"] == "job-1"


def test_packaged_gate_consumes_authoritative_health_checklist():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    gate = source[source.index("def _run_sidecar_gate"):source.index("def _close_app_window")]
    assert 'health.get("checks")' in gate
    assert 'health.get("passed") is True' in gate
    assert 'health.get("paths")' not in gate


def test_restart_restore_evidence_required_for_pass():
    # A host run that never restored a completed job must fail the gate.
    records = [
        {"event": "session_started"},
        {"event": "ready", "engine_loaded": True},
        {"event": "page_ready"},
    ]
    host = m.classify_host_evidence(records, exit_code=0)
    assert host["restore_passed"] is False
    checks = _passing_checks(restore_passed=host["restore_passed"])
    assert m.score_result(checks)["passed"] is False

    # With restore evidence present the gate can pass.
    records.append({"event": "job_restored", "job_id": "job-1", "status": "done"})
    host_ok = m.classify_host_evidence(records, exit_code=0)
    assert host_ok["restore_passed"] is True
    assert m.score_result(_passing_checks(restore_passed=True))["passed"] is True


def test_renderer_bridge_or_orphan_failure_forces_failure():
    assert m.score_result(_passing_checks())["passed"] is True

    renderer = m.classify_host_evidence(
        [{"event": "page_load_failed", "errorCode": -3}], exit_code=0
    )
    assert renderer["renderer_failures"]
    assert m.score_result(
        _passing_checks(renderer_failures=renderer["renderer_failures"])
    )["passed"] is False

    bridge = m.classify_host_evidence(
        [{"event": "console", "level": "error", "message": "unsupported command: nope"}],
        exit_code=0,
    )
    assert bridge["bridge_errors"]
    assert m.score_result(_passing_checks(bridge_errors=bridge["bridge_errors"]))["passed"] is False

    assert m.score_result(_passing_checks(orphan_processes=["ffmpeg.exe"]))["passed"] is False
    assert m.score_result(
        _passing_checks(unexpected_errors=["exit code 5"])
    )["passed"] is False


def test_result_json_deterministic_and_machine_readable():
    first = m.score_result(_passing_checks())
    second = m.score_result(_passing_checks())
    assert first == second
    assert list(first) == list(m.ACCEPTANCE_KEYS)

    parsed = json.loads(m.dump_result(first))
    assert isinstance(parsed, dict)
    assert parsed["passed"] is True

    failing = m.score_result(_passing_checks(job_started=False))
    assert m.dump_result(failing) != m.dump_result(first)
    assert set(json.loads(m.dump_result(failing))) == set(m.ACCEPTANCE_KEYS)


def test_ai_study_privacy_detector_distinguishes_https_from_windows_paths():
    demo = r"c:\lecturepackscratch\demo-lecture.mp4"
    web_payload = json.dumps({"url": "https://example.edu/study/source"}).casefold()
    path_payload = json.dumps({"path": r"C:\Users\student\lecture.mp4"}).casefold()

    assert ai_study.contains_local_path(web_payload, demo) is False
    assert ai_study.contains_local_path(path_payload, demo) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native window enumeration")
@pytest.mark.parametrize("main_present,post_succeeds", [(True, True), (False, True), (True, False)])
def test_native_close_ignores_helper_and_foreign_windows(monkeypatch, main_present, post_succeeds):
    import ctypes
    from types import SimpleNamespace

    # Preserve the failing real enumeration order: hidden Electron helper first.
    windows = {
        101: (42, False, "Chrome_WidgetWin_0", ""),
        102: (99, True, "Chrome_WidgetWin_1", "LecturePack"),
        103: (42, True, "IME", "Default IME"),
        104: (42, True, "Chrome_WidgetWin_1", "Other window"),
    }
    if main_present:
        windows[105] = (42, True, "Chrome_WidgetWin_1", "LecturePack")
    posted = []

    def enum_windows(callback, param):
        for hwnd in windows:
            if not callback(hwnd, param):
                break

    def owner(hwnd, pointer):
        pointer._obj.value = windows[hwnd][0]

    def text(hwnd, buffer, size, index):
        buffer.value = windows[hwnd][index]
        return len(buffer.value)

    def post(hwnd, message, wparam, lparam):
        posted.append((hwnd, message, wparam, lparam))
        return post_succeeds

    monkeypatch.setattr(ctypes.windll, "user32", SimpleNamespace(
        EnumWindows=enum_windows,
        GetWindowThreadProcessId=owner,
        IsWindowVisible=lambda hwnd: windows[hwnd][1],
        GetWindowTextW=lambda hwnd, buffer, size: text(hwnd, buffer, size, 3),
        GetClassNameW=lambda hwnd, buffer, size: text(hwnd, buffer, size, 2),
        PostMessageW=post,
    ))
    assert m._close_app_window(42) is (main_present and post_succeeds)
    assert posted == ([(105, 0x0010, 0, 0)] if main_present else [])


@pytest.mark.parametrize("close_found,timeout", [(False, False), (True, True)])
def test_forced_termination_is_explicit_even_if_exit_code_is_zero(monkeypatch, tmp_path, close_found, timeout):
    class Process:
        pid = 42
        returncode = None
        waits = 0

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1 and self.returncode is None:
                raise m.subprocess.TimeoutExpired("LecturePack.exe", timeout)
            self.returncode = 0
            return 0

    monkeypatch.setattr(m.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(m, "poll_until", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "snapshot_processes", lambda: [])
    monkeypatch.setattr(m, "_close_app_window", lambda pid: close_found)
    host, orphans, _ = m._run_host_once(tmp_path / "LecturePack.exe", tmp_path / "results", tmp_path / "data", 1, "test")
    assert host["first_exit_clean"] is False
    assert host["unexpected_errors"] == (["packaged app did not exit within 20s after main-window close"] if timeout else ["could not close the visible LecturePack main window"])
    assert orphans == []
