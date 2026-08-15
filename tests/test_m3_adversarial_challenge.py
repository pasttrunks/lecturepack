"""Adversarial stress-test suite for Milestone 3: Release Verification and Hardening.

Aggressively tests:
1. Sidecar IPC handlers (set_job_group, set_jobs_group, study_v2_group_prepare) under malformed/adversarial inputs.
2. Group analysis caching, fingerprinting, boundary conditions, and invalidation dynamics.
3. Live packaged candidate binary (LecturePackSidecar.exe) under adverse directory paths and interactive JSONL commands.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace
import uuid
import pytest

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services import group_study, study_v2
from lecturepack import electron_backend


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SCRIPT = ROOT / "electron-spike" / "python-sidecar.py"
PACKAGED_SIDECAR = (
    ROOT
    / "electron-spike"
    / "dist"
    / "LecturePack-win32-x64"
    / "resources"
    / "LecturePackSidecar"
    / "LecturePackSidecar.exe"
)


def _load_sidecar_module():
    spec = importlib.util.spec_from_file_location("lecturepack_m3_sidecar", SIDECAR_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_sidecar_fixture(data_root: Path, *, mock_gateway_fn=None):
    module = _load_sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._engine_error = ""
    sidecar.data_dir = data_root
    sidecar.session_id = "test-session-m3"
    sidecar.current_job = None
    sidecar.Job = Job
    sidecar.electron_backend = electron_backend
    sidecar.group_study = group_study
    sidecar.study_v2 = study_v2

    emitted = []
    responses = []
    sidecar._emit = lambda event: emitted.append(event)
    sidecar._respond = lambda request_id, command, **kwargs: responses.append({
        "event": "response",
        "response_to": request_id,
        "command": command,
        **kwargs,
    })

    client = SimpleNamespace()
    if mock_gateway_fn is not None:
        client.request = mock_gateway_fn
    else:
        client.request = lambda task, payload: {
            "group_summary": "Standard test group summary",
            "concepts": [
                {
                    "id": "c_glob_1",
                    "title": "Global Concept",
                    "job_ids": [m["job_id"] for m in payload.get("lectures", [])],
                },
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }
    sidecar._ai_gateway_client = client
    sidecar._study_workers_lock = threading.Lock()
    sidecar._gateway_client = lambda: client

    sidecar._job_objects = module.Sidecar._job_objects.__get__(sidecar)
    sidecar._emit_job_payloads = lambda: None
    sidecar._set_job_group = module.Sidecar._set_job_group.__get__(sidecar)
    sidecar._set_jobs_group = module.Sidecar._set_jobs_group.__get__(sidecar)
    sidecar._study_v2_group_prepare = module.Sidecar._study_v2_group_prepare.__get__(sidecar)
    sidecar._handle_command = module.Sidecar._handle_command.__get__(sidecar)

    return sidecar, emitted, responses, client


def _create_test_job(
    data_root: Path,
    job_id: str,
    title: str,
    *,
    group: str = "",
    status: str = "ready",
    concepts: list[dict] | None = None,
    generated_at: str = "2026-08-15T00:00:00Z",
) -> Path:
    job_dir = data_root / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "job_id": job_id,
        "title": title,
        "group": group,
        "created_at": "2026-08-15T00:00:00Z",
        "stages": {"Review Ready": {"status": "completed"}},
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    concept_list = concepts or [
        {
            "id": f"c_{job_id}_1",
            "title": f"Concept 1 in {title}",
            "summary": "Summary text",
            "sources": [{"segment_id": "seg_1", "start_ms": 1000}],
        }
    ]

    # Must be a status load_content() recognises. An unknown string is
    # normalised away -- a pack with concepts would be promoted to READY,
    # which is the opposite of what an "unready" fixture is asking for.
    study_status = (
        study_v2.STUDY_READY if status == "ready"
        else study_v2.STUDY_BASIC if status == "basic"
        else study_v2.STUDY_PREPARING)
    content = {
        "study_status": study_status,
        "generated_at": generated_at,
        "concepts": concept_list,
        "lecture_analysis": {
            "lecture_summary": f"Summary of {title}",
            "concepts": concept_list,
        },
        "flashcards": [],
        "quiz": [],
    }
    # Must match study_v2.CONTENT_FILENAME -- load_content() reads that exact
    # name, so a hand-rolled filename here silently yields an empty group.
    (job_dir / study_v2.CONTENT_FILENAME).write_text(json.dumps(content, indent=2), encoding="utf-8")
    return job_dir


# ========================================================================= #
# 1. Sidecar IPC Handlers Edge Cases
# ========================================================================= #

def test_set_job_group_malformed_and_edge_inputs(tmp_path: Path):
    """Test set_job_group with invalid IDs, empty values, special characters, and non-existent jobs."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _create_test_job(data_root, "job_valid_1", "Lecture 1", group="OLD_GROUP")

    sidecar, emitted, responses, _ = _setup_sidecar_fixture(data_root)

    # 1. Missing / None payload
    sidecar._handle_command({"request_id": "req_1", "command": "set_job_group", "payload": {}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["job_id"] == ""

    # 2. Non-existent job ID
    sidecar._handle_command({"request_id": "req_2", "command": "set_job_group", "payload": {"job_id": "job_non_existent", "group": "CS101"}})
    assert responses[-1]["ok"] is False

    # 3. Path traversal attack in job_id
    sidecar._handle_command({"request_id": "req_3", "command": "set_job_group", "payload": {"job_id": "../../windows/system32", "group": "HACK"}})
    assert responses[-1]["ok"] is False

    # 4. Valid job with unicode group
    sidecar._handle_command({"request_id": "req_4", "command": "set_job_group", "payload": {"job_id": "job_valid_1", "group": "🌟 Machine Learning 🚀"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == "🌟 Machine Learning 🚀"

    # Verify manifest updated on disk
    manifest = json.loads((data_root / "jobs" / "job_valid_1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["group"] == "🌟 Machine Learning 🚀"

    # 5. Clear group (empty string)
    sidecar._handle_command({"request_id": "req_5", "command": "set_job_group", "payload": {"job_id": "job_valid_1", "group": ""}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == ""
    manifest = json.loads((data_root / "jobs" / "job_valid_1" / "manifest.json").read_text(encoding="utf-8"))
    # Clearing removes the key entirely so the job reverts to its derived
    # default group -- absence is the contract, not an empty string.
    assert "group" not in manifest


def test_set_jobs_group_malformed_and_batch_edge_inputs(tmp_path: Path):
    """Test set_jobs_group with various array shapes, stringified JSON, null items, and path traversal."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _create_test_job(data_root, "job_batch_1", "Batch 1")
    _create_test_job(data_root, "job_batch_2", "Batch 2")

    sidecar, emitted, responses, _ = _setup_sidecar_fixture(data_root)

    # 1. Null / empty ids
    sidecar._handle_command({"request_id": "req_b1", "command": "set_jobs_group", "payload": {"ids": None, "group": "CS101"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["count"] == 0

    # 2. Stringified JSON with mix of valid, invalid, None, and path traversal
    mixed_ids = json.dumps(["job_batch_1", None, "", "../traversal", "job_batch_2", "ghost_job"])
    sidecar._handle_command({"request_id": "req_b2", "command": "set_jobs_group", "payload": {"ids": mixed_ids, "group": "MATH201"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["count"] == 2
    assert responses[-1]["group"] == "MATH201"

    # Verify both valid jobs got updated
    m1 = json.loads((data_root / "jobs" / "job_batch_1" / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((data_root / "jobs" / "job_batch_2" / "manifest.json").read_text(encoding="utf-8"))
    assert m1["group"] == "MATH201"
    assert m2["group"] == "MATH201"

    # 3. Invalid non-JSON string for ids
    sidecar._handle_command({"request_id": "req_b3", "command": "set_jobs_group", "payload": {"ids": "{not a valid list}", "group": "FAIL"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["count"] == 0


def test_study_v2_group_prepare_missing_unready_and_empty_groups(tmp_path: Path):
    """Test study_v2_group_prepare with missing groups, unready members, and edge conditions."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    # Job 1: Ready in Group A
    _create_test_job(data_root, "job_a1", "Group A Lecture 1", group="Group A", status="ready")
    # Job 2: Unready / Pending in Group A
    _create_test_job(data_root, "job_a2", "Group A Lecture 2", group="Group A", status="pending")
    # Job 3: Ready in Group B
    _create_test_job(data_root, "job_b1", "Group B Lecture 1", group="Group B", status="ready")

    sidecar, emitted, responses, client = _setup_sidecar_fixture(data_root)

    # 1. Missing / Empty group parameter
    sidecar._handle_command({"request_id": "req_p1", "command": "study_v2_group_prepare", "payload": {"group": "   "}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "missing_group"

    # 2. Non-existent group
    sidecar._handle_command({"request_id": "req_p2", "command": "study_v2_group_prepare", "payload": {"group": "NonExistentGroup"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "no_ready_lectures"
    assert responses[-1]["members"] == []

    # 3. Group with only unready members
    _create_test_job(data_root, "job_unready_1", "Unready Lec", group="UnreadyGroup", status="pending")
    sidecar._handle_command({"request_id": "req_p3", "command": "study_v2_group_prepare", "payload": {"group": "UnreadyGroup"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "no_ready_lectures"

    # 4. Group with 1 ready member and 1 unready member
    sidecar._handle_command({"request_id": "req_p4", "command": "study_v2_group_prepare", "payload": {"group": "Group A"}})
    assert responses[-1]["ok"] is True
    assert len(responses[-1]["members"]) == 1
    assert responses[-1]["members"][0]["job_id"] == "job_a1"
    assert responses[-1]["cached"] is False


def test_study_v2_group_prepare_gateway_error_and_malformed_response(tmp_path: Path):
    """Test group prepare behavior when the AI gateway raises an exception or returns bad schema."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _create_test_job(data_root, "job_gw_1", "GW Lecture 1", group="GW_Group", status="ready")

    # 1. Gateway raises RuntimeError
    def failing_gateway(task, payload):
        raise RuntimeError("Gateway connection timed out")

    sidecar, emitted, responses, _ = _setup_sidecar_fixture(data_root, mock_gateway_fn=failing_gateway)
    sidecar._handle_command({"request_id": "req_err1", "command": "study_v2_group_prepare", "payload": {"group": "GW_Group"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "prepare_failed"
    assert "Gateway connection timed out" in responses[-1]["error"]

    # 2. Gateway returns empty concepts list
    def empty_concepts_gateway(task, payload):
        return {"group_summary": "Empty", "concepts": []}

    sidecar, emitted, responses, _ = _setup_sidecar_fixture(data_root, mock_gateway_fn=empty_concepts_gateway)
    sidecar._handle_command({"request_id": "req_err2", "command": "study_v2_group_prepare", "payload": {"group": "GW_Group"}})
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "empty_analysis"


# ========================================================================= #
# 2. Group Analysis Caching and Invalidation Boundary Conditions
# ========================================================================= #

def test_group_cache_invalidation_lifecycle(tmp_path: Path):
    """Stress test full cache invalidation lifecycle: hits, member edits, additions, deletions, and force flag."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    _create_test_job(data_root, "lec_1", "Lec 1", group="Physics", generated_at="2026-08-15T01:00:00Z")
    _create_test_job(data_root, "lec_2", "Lec 2", group="Physics", generated_at="2026-08-15T01:00:00Z")

    gateway_call_count = 0
    def counting_gateway(task, payload):
        nonlocal gateway_call_count
        gateway_call_count += 1
        return {
            "group_summary": f"Physics synthesis v{gateway_call_count}",
            "concepts": [
                {
                    "id": "c_p1",
                    "title": "Quantum Spin",
                    "job_ids": [m["job_id"] for m in payload.get("lectures", [])],
                }
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, emitted, responses, _ = _setup_sidecar_fixture(data_root, mock_gateway_fn=counting_gateway)

    # Initial call: should call gateway (count = 1) and save cache
    sidecar._handle_command({"id": "c1", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert gateway_call_count == 1

    # Second call: exact same members: should HIT cache (cached = True, gateway_call_count = 1)
    sidecar._handle_command({"id": "c2", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is True
    assert gateway_call_count == 1

    # Third call: with force=True: should BYPASS cache (cached = False, gateway_call_count = 2)
    sidecar._handle_command({"id": "c3", "command": "study_v2_group_prepare", "payload": {"group": "Physics", "force": True}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert gateway_call_count == 2

    # Fourth call without force: should HIT the freshly saved cache
    sidecar._handle_command({"id": "c4", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is True
    assert gateway_call_count == 2

    # Update lec_1 generated_at timestamp (simulating re-processing / re-generation): cache must INVALIDATE
    _create_test_job(data_root, "lec_1", "Lec 1", group="Physics", generated_at="2026-08-15T02:00:00Z")
    sidecar._handle_command({"id": "c5", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert gateway_call_count == 3

    # Add a third lecture to the group: cache must INVALIDATE
    _create_test_job(data_root, "lec_3", "Lec 3", group="Physics", generated_at="2026-08-15T02:30:00Z")
    sidecar._handle_command({"id": "c6", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert len(responses[-1]["members"]) == 3
    assert gateway_call_count == 4

    # Delete lec_2: cache must INVALIDATE
    shutil.rmtree(data_root / "jobs" / "lec_2")
    sidecar._handle_command({"id": "c7", "command": "study_v2_group_prepare", "payload": {"group": "Physics"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert len(responses[-1]["members"]) == 2
    assert gateway_call_count == 5


def test_corrupted_group_cache_file_graceful_recovery(tmp_path: Path):
    """Test that a corrupt, truncated, or incompatible schema cache file is transparently rebuilt without error."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _create_test_job(data_root, "lec_bio_1", "Biology 1", group="Biology")

    sidecar, emitted, responses, client = _setup_sidecar_fixture(data_root)

    # Prepare initially to create cache file
    sidecar._handle_command({"id": "b1", "command": "study_v2_group_prepare", "payload": {"group": "Biology"}})
    assert responses[-1]["ok"] is True

    # Find the cache file on disk
    cache_path = Path(group_study.analysis_path(str(data_root), "Biology"))
    assert cache_path.is_file()

    # Corrupt the cache file with garbage bytes
    cache_path.write_bytes(b"CORRUPTED_NOT_JSON_{{{")

    # Re-running prepare should ignore the garbage cache and re-create it cleanly
    sidecar._handle_command({"id": "b2", "command": "study_v2_group_prepare", "payload": {"group": "Biology"}})
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False

    # Check cache file is now valid JSON again
    repaired_doc = json.loads(cache_path.read_text(encoding="utf-8"))
    assert repaired_doc["schema_version"] == 1
    assert repaired_doc["group"] == "Biology"


# ========================================================================= #
# 3. Packaged Candidate Binary (LecturePackSidecar.exe) Empirical Verification
# ========================================================================= #

@pytest.mark.skipif(not PACKAGED_SIDECAR.is_file(), reason="Packaged candidate binary not found")
def test_packaged_binary_self_test_in_adverse_directories(tmp_path: Path):
    """Verify LecturePackSidecar.exe executes self-test in spaced and unicode directory paths."""
    resources_root = PACKAGED_SIDECAR.parent

    # 1. Custom data dir with spaces
    spaced_data_dir = tmp_path / "Lecture Pack Data With Spaces"
    cmd_spaced = [
        str(PACKAGED_SIDECAR),
        "--resources-root", str(resources_root),
        "--data-dir", str(spaced_data_dir),
        "--self-test",
    ]
    proc_spaced = subprocess.run(cmd_spaced, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc_spaced.returncode == 0, f"Self-test failed with spaced path: {proc_spaced.stderr}"

    lines_spaced = [json.loads(line) for line in proc_spaced.stdout.strip().splitlines() if line.strip().startswith("{")]
    ready_event = next((ev for ev in lines_spaced if ev.get("event") == "ready"), None)
    self_test_event = next((ev for ev in lines_spaced if ev.get("event") == "self_test"), None)

    assert ready_event is not None
    assert ready_event["protocol_version"] == 1
    assert ready_event["engine_loaded"] is True
    assert self_test_event is not None
    assert self_test_event["passed"] is True
    assert self_test_event["startup_ok"] is True

    # 2. Custom data dir with Unicode characters
    unicode_data_dir = tmp_path / "LecturePack_データ_テスト"
    cmd_unicode = [
        str(PACKAGED_SIDECAR),
        "--resources-root", str(resources_root),
        "--data-dir", str(unicode_data_dir),
        "--self-test",
    ]
    proc_unicode = subprocess.run(cmd_unicode, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc_unicode.returncode == 0, f"Self-test failed with unicode path: {proc_unicode.stderr}"

    lines_unicode = [json.loads(line) for line in proc_unicode.stdout.strip().splitlines() if line.strip().startswith("{")]
    self_test_u = next((ev for ev in lines_unicode if ev.get("event") == "self_test"), None)
    assert self_test_u is not None
    assert self_test_u["passed"] is True


def _await_response(proc, request_id: str, *, timeout: float = 60.0):
    """Drain the sidecar's stdout until its answer to ``request_id`` arrives.

    The sidecar interleaves a long stream of ``bootstrap_progress`` events with
    command responses -- ``health_check`` alone sits behind 20+ of them -- so a
    fixed line budget reads as "the binary never answered". Reading happens on a
    worker thread because ``readline`` on a pipe cannot be interrupted, and a
    sidecar that answers nothing would otherwise hang the suite forever.
    """
    found: list[dict] = []

    def _drain():
        while True:
            line = proc.stdout.readline()
            if not line:
                return
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (event.get("event") == "response"
                    and event.get("response_to") == request_id):
                found.append(event)
                return

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    reader.join(timeout)
    return found[0] if found else None


@pytest.mark.skipif(not PACKAGED_SIDECAR.is_file(), reason="Packaged candidate binary not found")
def test_packaged_binary_interactive_jsonl_session(tmp_path: Path):
    """Verify LecturePackSidecar.exe runs interactively over JSONL stdio pipes with IPC commands."""
    resources_root = PACKAGED_SIDECAR.parent
    data_dir = tmp_path / "live_sidecar_data"

    # Pre-create a job in data_dir
    _create_test_job(data_dir, "live_job_1", "Live Lecture", group="OldGroup")

    cmd = [
        str(PACKAGED_SIDECAR),
        "--resources-root", str(resources_root),
        "--data-dir", str(data_dir),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    try:
        # Step 1: Read ready handshake
        ready_line = proc.stdout.readline()
        ready_event = json.loads(ready_line)
        assert ready_event.get("event") == "ready"
        assert ready_event.get("engine_loaded") is True

        # Step 2: Send health_check
        proc.stdin.write(json.dumps({"request_id": "req_hc", "command": "health_check"}) + "\n")
        proc.stdin.flush()

        hc_resp = _await_response(proc, "req_hc")
        assert hc_resp is not None
        assert hc_resp.get("command") == "health_check"

        # Step 3: Send set_job_group over real JSONL pipe
        proc.stdin.write(json.dumps({
            "request_id": "req_sjg",
            "command": "set_job_group",
            "payload": {"job_id": "live_job_1", "group": "NEW_LIVE_GROUP"}
        }) + "\n")
        proc.stdin.flush()

        sjg_resp = _await_response(proc, "req_sjg")
        assert sjg_resp is not None
        assert sjg_resp.get("ok") is True
        assert sjg_resp.get("group") == "NEW_LIVE_GROUP"

        # Step 4: Send shutdown command
        proc.stdin.write(json.dumps({"request_id": "req_sd", "command": "shutdown"}) + "\n")
        proc.stdin.flush()

        proc.wait(timeout=10)
        assert proc.returncode == 0

        # Verify disk state was updated
        manifest = json.loads((data_dir / "jobs" / "live_job_1" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["group"] == "NEW_LIVE_GROUP"

    finally:
        if proc.poll() is None:
            proc.kill()
