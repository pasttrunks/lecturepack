"""Focused tests for the packaged-app acceptance gate (no real packaged app needed).

These cover the acceptance gate's logic with mocks / a throwaway fake
executable. They deliberately do not launch the real Electron or sidecar
binaries, which live in Luna's active worktree.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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

    empty = m.validate_export(tmp_path / "missing", tmp_path / "missing" / "exports")
    assert empty["export_completed"] is False
    assert empty["export_file_count"] == 0


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

