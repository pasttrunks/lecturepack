"""Adversarial stress-test suite for Milestone 1: Group Study Sidecar IPC Command and Caching.

This test suite aggressively probes:
1. Pathological and boundary inputs to `_study_v2_group_prepare` and `group_study.prepare`.
2. Job discovery edge cases (missing manifests, corrupt JSON, malformed state, mixed job health).
3. Cache invalidation, corruption resilience, and rapid sequential calls.
4. Grounding and schema normalization with adversarial LLM responses.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import threading
from types import SimpleNamespace
import pytest

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services import group_study, study_v2
from lecturepack import electron_backend


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"


def _sidecar_module():
    spec = importlib.util.spec_from_file_location("lecturepack_polish_sidecar", SIDECAR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_sidecar(data_root: Path, *, mock_gateway_fn=None):
    module = _sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._engine_error = ""
    sidecar.data_dir = data_root
    sidecar.session_id = "test-session"
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
            "group_summary": "Synthesized group summary",
            "concepts": [
                {
                    "id": "c_global_1",
                    "title": "Global Concept 1",
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
    sidecar._study_v2_group_prepare = module.Sidecar._study_v2_group_prepare.__get__(sidecar)
    sidecar._handle_command = module.Sidecar._handle_command.__get__(sidecar)

    return sidecar, emitted, responses, client


def _create_lecture_job(
    data_root: Path,
    job_id: str,
    title: str,
    *,
    group: str | None = "",
    status: str = "ready",
    concepts: list[str] | None = None,
    corrupt_manifest: bool = False,
    missing_manifest: bool = False,
    corrupt_content: bool = False,
    missing_content: bool = False,
    generated_at: str = "2026-08-15T00:00:00Z",
) -> Path:
    job_dir = data_root / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if not missing_manifest:
        if corrupt_manifest:
            (job_dir / "manifest.json").write_text("{corrupt json", encoding="utf-8")
        else:
            manifest = {
                "job_id": job_id,
                "title": title,
                "created_at": "2026-08-15T00:00:00Z",
            }
            if group is not None:
                manifest["group"] = group
            (job_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    (job_dir / "state.json").write_text(
        json.dumps({"overall_status": "completed", "lifecycle": "completed"}),
        encoding="utf-8",
    )

    if not missing_content:
        if corrupt_content:
            (job_dir / "study-content-v2.json").write_text("NOT_JSON", encoding="utf-8")
        else:
            concept_list = concepts or ["c1", "c2"]
            content = {
                "study_status": status,
                "generated_at": generated_at,
                "lecture_analysis": {
                    "lecture_summary": f"Summary of {title}",
                    "concepts": [{"id": cid, "title": cid} for cid in concept_list],
                },
                "concepts": [{"id": cid, "title": cid} for cid in concept_list],
            }
            (job_dir / "study-content-v2.json").write_text(json.dumps(content), encoding="utf-8")

    return job_dir


# ==============================================================================
# SECTION 1: Pathological and Boundary Inputs
# ==============================================================================

@pytest.mark.parametrize("bad_group", [
    "",
    "   ",
    "\t\n\r ",
    None,
    False,
])
def test_pathological_empty_group_inputs(tmp_path, bad_group):
    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)
    payload = {}
    if bad_group is not None:
        payload["group"] = bad_group

    sidecar._handle_command({
        "request_id": "req-bad-group",
        "command": "study_v2_group_prepare",
        "payload": payload,
    })

    assert len(responses) == 1
    resp = responses[0]
    assert resp["ok"] is False
    assert resp["reason"] == "missing_group"
    assert "group is required" in resp.get("error", "")


@pytest.mark.parametrize("unicode_group, job_title", [
    ("计算机科学 101", "计算机科学 101: 算法导论"),
    ("日本語の勉強", "日本語の勉強: 文法第一課"),
    ("علوم الحاسوب", "علوم الحاسوب: هياكل البيانات"),
    ("München & Gödel 101", "München & Gödel 101: Logik"),
    ("🚀 Rocket Science 🌟", "🚀 Rocket Science 🌟: Propulsion"),
    ("GROSS", "groß: Introduction"),  # German sharp S casefolding
    ("SPACES   AND   TABS", "spaces   and   tabs: Lecture 1"),
])
def test_unicode_cjk_emoji_and_special_group_names(tmp_path, unicode_group, job_title):
    _create_lecture_job(tmp_path, "job-uni", job_title, group=unicode_group)

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-uni",
        "command": "study_v2_group_prepare",
        "payload": {"group": unicode_group},
    })

    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == unicode_group
    assert len(responses[-1]["members"]) == 1

    # Verify cache file path does not crash on Windows file systems
    cache_path = Path(group_study.analysis_path(str(tmp_path), unicode_group))
    assert cache_path.is_file()
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["group"] == unicode_group


def test_extremely_long_group_name_does_not_break_filesystem(tmp_path):
    long_group = "A" * 5000 + " 101: Extended " + "B" * 5000
    _create_lecture_job(tmp_path, "job-long", long_group, group=long_group)

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-long",
        "command": "study_v2_group_prepare",
        "payload": {"group": long_group},
    })

    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == long_group
    assert len(responses[-1]["members"]) == 1

    cache_path = Path(group_study.analysis_path(str(tmp_path), long_group))
    assert cache_path.is_file()


@pytest.mark.parametrize("traversal_name", [
    "../../../../etc/passwd",
    "..\\..\\..\\Windows\\System32",
    "COM1",
    "NUL",
    "PRN",
    "AUX",
    "CON",
])
def test_path_traversal_and_reserved_windows_names(tmp_path, traversal_name):
    _create_lecture_job(tmp_path, "job-trav", f"{traversal_name}: Lecture", group=traversal_name)

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-trav",
        "command": "study_v2_group_prepare",
        "payload": {"group": traversal_name},
    })

    assert responses[-1]["ok"] is True
    # Group directory is hashed slug so it never creates reserved/traversing folders
    cache_path = Path(group_study.analysis_path(str(tmp_path), traversal_name))
    assert cache_path.is_file()
    assert cache_path.is_relative_to(tmp_path / "groups")


# ==============================================================================
# SECTION 2: Library Job Discovery and Health Edge Cases
# ==============================================================================

def test_discovery_with_missing_and_corrupt_manifests_does_not_crash(tmp_path):
    # Valid job
    _create_lecture_job(tmp_path, "job-valid", "Biology 101: Cells", group="Biology")
    # Missing manifest
    _create_lecture_job(tmp_path, "job-no-manifest", "Biology 101: Genetics", missing_manifest=True)
    # Corrupt manifest
    _create_lecture_job(tmp_path, "job-bad-manifest", "Biology 101: Ecology", corrupt_manifest=True)
    # Corrupt study content
    _create_lecture_job(tmp_path, "job-bad-content", "Biology 101: Evolution", group="Biology", corrupt_content=True)
    # Missing study content
    _create_lecture_job(tmp_path, "job-no-content", "Biology 101: Plants", group="Biology", missing_content=True)

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-discovery",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Biology"},
    })

    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == "Biology"
    # Only job-valid should successfully be included as a ready member
    assert len(responses[-1]["members"]) == 1
    assert responses[-1]["members"][0]["job_id"] == "job-valid"


def test_mixed_lecture_readiness_states(tmp_path):
    # Ready status: included
    _create_lecture_job(tmp_path, "job-ready-1", "Math: Calculus", group="Math", status="ready")
    # Basic status: included
    _create_lecture_job(tmp_path, "job-basic", "Math: Algebra", group="Math", status="basic")
    # Preparing status: excluded
    _create_lecture_job(tmp_path, "job-prep", "Math: Geometry", group="Math", status="preparing")
    # Failed status: excluded
    _create_lecture_job(tmp_path, "job-failed", "Math: Stats", group="Math", status="failed")

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-math",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Math"},
    })

    assert responses[-1]["ok"] is True
    # Both "ready" and "basic" are valid member readiness statuses; preparing and failed are excluded
    assert len(responses[-1]["members"]) == 2
    assert {m["job_id"] for m in responses[-1]["members"]} == {"job-ready-1", "job-basic"}


def test_lecture_analysis_missing_concepts_key_is_skipped(tmp_path):
    job_dir = _create_lecture_job(tmp_path, "job-no-concepts", "CS: Algorithms", group="CS")
    content = {
        "study_status": "ready",
        "generated_at": "2026-08-15T00:00:00Z",
        "lecture_analysis": {
            "lecture_summary": "Summary without concepts",
            "concepts": [],  # Empty concepts
        },
        "concepts": [],
    }
    (job_dir / "study-content-v2.json").write_text(json.dumps(content), encoding="utf-8")

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-cs",
        "command": "study_v2_group_prepare",
        "payload": {"group": "CS"},
    })

    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "no_ready_lectures"


def test_more_than_twelve_members_bounded(tmp_path):
    # Create 15 ready lectures for one group
    for i in range(15):
        _create_lecture_job(tmp_path, f"job-{i:02d}", f"Series: Lecture {i}", group="Series")

    requested_payloads = []

    def mock_gw(task, payload):
        requested_payloads.append(payload)
        return {
            "group_summary": "15 lecture summary",
            "concepts": [
                {
                    "id": "c1",
                    "title": "C1",
                    "job_ids": [m["job_id"] for m in payload.get("lectures", [])],
                }
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=mock_gw)

    sidecar._handle_command({
        "request_id": "req-series",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Series"},
    })

    assert responses[-1]["ok"] is True
    # Sidecar returns all matching member metadata (15)
    assert len(responses[-1]["members"]) == 15
    # But evidence payload to LLM is strictly capped to MAX_GROUP_LECTURES (12)
    assert len(requested_payloads[0]["lectures"]) == 12


# ==============================================================================
# SECTION 3: Cache Invalidation, Corruption, and Rapid Sequential Calls
# ==============================================================================

@pytest.mark.parametrize("corrupt_content", [
    "",
    "   ",
    "{corrupt json",
    "[]",
    '"string instead of dict"',
    "12345",
    "true",
    '{"schema_version": 999}',
    '{"schema_version": 1, "fingerprint": "wrong_fp", "analysis": {}}',
    '{"schema_version": 1, "fingerprint": "CORRECT", "analysis": null}',
    '{"schema_version": 1, "fingerprint": "CORRECT", "analysis": "not_dict"}',
])
def test_corrupted_cache_file_gracefully_heals_and_regenerates(tmp_path, corrupt_content):
    _create_lecture_job(tmp_path, "job-cache", "Art: Painting", group="Art")

    call_count = 0

    def mock_gw(task, payload):
        nonlocal call_count
        call_count += 1
        return {
            "group_summary": f"Art Summary {call_count}",
            "concepts": [{"id": "c1", "title": "C1", "job_ids": ["job-cache"]}],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, emitted, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=mock_gw)

    # 1. First run: generates initial cache
    sidecar._handle_command({
        "request_id": "req-1",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Art"},
    })
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert call_count == 1

    cache_file = Path(group_study.analysis_path(str(tmp_path), "Art"))
    assert cache_file.is_file()

    # 2. Corrupt the cache file directly
    if "CORRECT" in corrupt_content:
        members = group_study.collect_members(sidecar._job_objects())
        fp = group_study.fingerprint(members)
        corrupt_content = corrupt_content.replace("CORRECT", fp)
    cache_file.write_text(corrupt_content, encoding="utf-8")

    # 3. Second run: detects corruption, ignores broken cache, and regenerates
    sidecar._handle_command({
        "request_id": "req-2",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Art"},
    })
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert call_count == 2
    assert responses[-1]["analysis"]["group_summary"] == "Art Summary 2"

    # 4. Third run: uses newly fixed cache
    sidecar._handle_command({
        "request_id": "req-3",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Art"},
    })
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is True
    assert call_count == 2


def test_fingerprint_changes_when_lecture_timestamp_updates(tmp_path):
    job_dir = _create_lecture_job(tmp_path, "job-1", "Chem: Reactions", group="Chem", generated_at="2026-08-15T00:00:00Z")

    call_count = 0

    def mock_gw(task, payload):
        nonlocal call_count
        call_count += 1
        return {
            "group_summary": f"Chem Summary {call_count}",
            "concepts": [{"id": "c1", "title": "C1", "job_ids": ["job-1"]}],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, _, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=mock_gw)

    # Initial call
    sidecar._handle_command({"request_id": "req-1", "command": "study_v2_group_prepare", "payload": {"group": "Chem"}})
    assert call_count == 1
    assert responses[-1]["cached"] is False

    # Second call without changes: cached
    sidecar._handle_command({"request_id": "req-2", "command": "study_v2_group_prepare", "payload": {"group": "Chem"}})
    assert call_count == 1
    assert responses[-1]["cached"] is True

    # Update job's generated_at timestamp (simulating re-processed lecture)
    content = json.loads((job_dir / "study-content-v2.json").read_text(encoding="utf-8"))
    content["generated_at"] = "2026-08-16T12:00:00Z"
    (job_dir / "study-content-v2.json").write_text(json.dumps(content), encoding="utf-8")

    # Third call: cache invalidation triggered because member fingerprint changed
    sidecar._handle_command({"request_id": "req-3", "command": "study_v2_group_prepare", "payload": {"group": "Chem"}})
    assert call_count == 2
    assert responses[-1]["cached"] is False
    assert responses[-1]["analysis"]["group_summary"] == "Chem Summary 2"


def test_rapid_sequential_prepare_calls(tmp_path):
    _create_lecture_job(tmp_path, "job-rapid-1", "Econ 101: Micro", group="Econ")
    _create_lecture_job(tmp_path, "job-rapid-2", "Econ 102: Macro", group="Econ")

    call_count = 0

    def mock_gw(task, payload):
        nonlocal call_count
        call_count += 1
        return {
            "group_summary": f"Econ Global {call_count}",
            "concepts": [
                {"id": "gc1", "title": "Supply Demand", "job_ids": ["job-rapid-1", "job-rapid-2"]}
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, _, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=mock_gw)

    # 30 rapid sequential requests
    for i in range(30):
        sidecar._handle_command({
            "request_id": f"req-seq-{i}",
            "command": "study_v2_group_prepare",
            "payload": {"group": "Econ", "force": (i == 10)},
        })

    assert len(responses) == 30
    assert all(r["ok"] is True for r in responses)
    assert all(r["group"] == "Econ" for r in responses)
    assert all(len(r["members"]) == 2 for r in responses)
    # First call was uncached, 1-9 were cached, 10 was forced uncached, 11-29 were cached
    assert call_count == 2
    assert responses[0]["cached"] is False
    assert responses[1]["cached"] is True
    assert responses[10]["cached"] is False
    assert responses[11]["cached"] is True


# ==============================================================================
# SECTION 4: Grounding and Adversarial Response Normalization
# ==============================================================================

def test_normalization_strips_hallucinated_jobs_and_cascading_references(tmp_path):
    _create_lecture_job(tmp_path, "job-real-1", "AI: Neural Nets", group="AI")
    _create_lecture_job(tmp_path, "job-real-2", "AI: Transformers", group="AI")

    # LLM hallucinates an ungrounded lecture "job-fake-99" and bogus concept "c_fake"
    def hallucinating_gw(task, payload):
        return {
            "group_summary": "AI Summary",
            "concepts": [
                {
                    "id": "c_real",
                    "title": "Attention Mechanism",
                    "job_ids": ["job-real-2", "job-fake-99"],  # Cites real and fake
                },
                {
                    "id": "c_hallucinated",
                    "title": "Quantum AI",
                    "job_ids": ["job-fake-99"],  # Cites ONLY fake
                },
            ],
            "relationships": [
                {"from_concept_id": "c_real", "to_concept_id": "c_real", "relationship": "reflexive"},
                {"from_concept_id": "c_real", "to_concept_id": "c_hallucinated", "relationship": "bridges"},
                {"from_concept_id": "c_hallucinated", "to_concept_id": "c_real", "relationship": "invalid"},
            ],
            "through_lines": [
                {"title": "Evolution", "body": "...", "concept_ids": ["c_real", "c_hallucinated"]},
                {"title": "Pure hallucination", "body": "...", "concept_ids": ["c_hallucinated"]},
            ],
            "gaps": [
                {"title": "Gap 1", "concept_ids": ["c_real"]},
                {"title": "Gap 2", "concept_ids": ["c_hallucinated"]},
            ],
        }

    sidecar, _, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=hallucinating_gw)

    sidecar._handle_command({
        "request_id": "req-grounding",
        "command": "study_v2_group_prepare",
        "payload": {"group": "AI"},
    })

    assert responses[-1]["ok"] is True
    analysis = responses[-1]["analysis"]

    # 1. c_hallucinated must be dropped
    concept_ids = [c["id"] for c in analysis["concepts"]]
    assert concept_ids == ["c_real"]

    # 2. c_real's job_ids must strip job-fake-99
    assert analysis["concepts"][0]["job_ids"] == ["job-real-2"]

    # 3. Relationships to/from c_hallucinated must be dropped
    assert len(analysis["relationships"]) == 1
    assert analysis["relationships"][0]["from_concept_id"] == "c_real"
    assert analysis["relationships"][0]["to_concept_id"] == "c_real"

    # 4. Through-lines must have c_hallucinated stripped
    assert analysis["through_lines"][0]["concept_ids"] == ["c_real"]
    assert analysis["through_lines"][1]["concept_ids"] == []

    # 5. Gaps must have c_hallucinated stripped
    assert analysis["gaps"][0]["concept_ids"] == ["c_real"]
    assert analysis["gaps"][1]["concept_ids"] == []


def test_completely_empty_or_malformed_llm_response_handled_cleanly(tmp_path):
    _create_lecture_job(tmp_path, "job-1", "Lit 101: Poetry", group="Lit")

    # Gateway returns invalid data structures
    for bad_return in [
        {},
        {"concepts": []},
        {"group_summary": "summary only, no concepts"},
        {"concepts": [{"id": "c1", "job_ids": ["job-not-in-group"]}]},
    ]:
        sidecar, emitted, responses, _ = _setup_sidecar(tmp_path, mock_gateway_fn=lambda t, p: bad_return)

        sidecar._handle_command({
            "request_id": "req-bad-llm",
            "command": "study_v2_group_prepare",
            "payload": {"group": "Lit", "force": True},
        })

        assert responses[-1]["ok"] is False
        assert responses[-1]["reason"] == "empty_analysis"
        assert responses[-1]["cached"] is False
        assert responses[-1]["analysis"] is None
        assert not Path(group_study.analysis_path(str(tmp_path), "Lit")).exists()
