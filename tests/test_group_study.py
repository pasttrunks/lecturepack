"""Studying a group of lectures as one subject.

The design decision worth protecting is that this is a REDUCE over work the
pipeline already did. Every lecture stores its own lecture_analysis when it is
processed, so a group of ten costs one request over ten small summaries rather
than ten transcripts read again. Tests here pin that shape, the cache that
makes a second session free, and the grounding rule that a group citation can
only name a lecture actually in the group.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lecturepack.services import group_study, study_v2


class _Job:
    def __init__(self, job_id: str, title: str):
        self.job_id = job_id
        self.manifest = {"title": title}


def _content(concepts, *, status="ready", generated_at="2026-08-15T00:00:00Z"):
    return {
        "study_status": status,
        "generated_at": generated_at,
        "lecture_analysis": {
            "lecture_summary": "summary",
            "concepts": [{"id": cid, "title": cid} for cid in concepts],
        },
        "concepts": [{"id": cid, "title": cid} for cid in concepts],
    }


@pytest.fixture
def library(monkeypatch):
    """Three ready lectures and one still processing."""
    packs = {
        "job-a": _content(["a1", "a2"]),
        "job-b": _content(["b1"]),
        "job-c": _content(["c1"]),
        "job-pending": {"study_status": "preparing", "lecture_analysis": {}, "concepts": []},
    }
    monkeypatch.setattr(study_v2, "load_content", lambda job: packs[job.job_id])
    monkeypatch.setattr(group_study.study_v2, "load_content", lambda job: packs[job.job_id])
    jobs = [_Job("job-a", "Week 1"), _Job("job-b", "Week 2"),
            _Job("job-c", "Week 3"), _Job("job-pending", "Week 4")]
    return jobs, packs


# ------------------------------------------------------------------ evidence

def test_only_lectures_with_a_finished_pack_are_included(library):
    jobs, _ = library
    members = group_study.collect_members(jobs)
    assert [m["job_id"] for m in members] == ["job-a", "job-b", "job-c"], (
        "a lecture still processing must not block studying the rest of the group"
    )


def test_the_request_carries_stored_analyses_not_transcripts(library):
    """The whole cost argument: one request over N small summaries."""
    jobs, _ = library
    evidence = group_study.build_evidence(group_study.collect_members(jobs))
    assert set(evidence) == {"lectures"}
    for lecture in evidence["lectures"]:
        assert set(lecture) == {"job_id", "title", "analysis"}
        assert "transcript" not in json.dumps(lecture)
    assert len(evidence["lectures"]) == 3


def test_every_lecture_is_labelled_so_a_citation_can_name_it(library):
    jobs, _ = library
    evidence = group_study.build_evidence(group_study.collect_members(jobs))
    assert [l["title"] for l in evidence["lectures"]] == ["Week 1", "Week 2", "Week 3"]
    assert all(l["job_id"] for l in evidence["lectures"])


def test_an_oversized_analysis_is_trimmed_to_valid_json(library, monkeypatch):
    """Truncating mid-JSON would send the model an unparseable document."""
    huge = {"lecture_summary": "s", "concepts": [
        {"id": f"c{i}", "title": "x" * 400} for i in range(200)]}
    members = [{"job_id": "job-a", "title": "Week 1", "generated_at": "t",
                "analysis": huge, "concepts": []}]
    lecture = group_study.build_evidence(members)["lectures"][0]
    assert isinstance(lecture["analysis"], dict)
    assert lecture["analysis"]["concepts"], "the concepts are what the reduce merges"
    assert len(json.dumps(lecture["analysis"])) < len(json.dumps(huge))


def test_a_group_is_bounded(library):
    members = [{"job_id": f"job-{i}", "title": str(i), "generated_at": "t",
                "analysis": {"concepts": [{"id": "x"}]}, "concepts": []}
               for i in range(40)]
    assert len(group_study.build_evidence(members)["lectures"]) == group_study.MAX_GROUP_LECTURES


# --------------------------------------------------------------------- cache

def test_the_second_session_costs_nothing(tmp_path, library):
    jobs, _ = library
    calls = []

    def call(task, payload):
        calls.append(task)
        return {"group_summary": "s", "concepts": [
            {"id": "g1", "title": "Shared", "job_ids": ["job-a", "job-b"]}]}

    first = group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call)
    second = group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call)
    assert first["ok"] and not first["cached"]
    assert second["ok"] and second["cached"]
    assert calls == ["group_analysis"], "a repeat session must not call the gateway again"
    assert second["analysis"] == first["analysis"]


def test_adding_a_lecture_rebuilds_the_map(tmp_path, library, monkeypatch):
    jobs, packs = library
    calls = []

    def call(task, payload):
        calls.append(len(payload["lectures"]))
        return {"group_summary": "s", "concepts": [
            {"id": "g1", "title": "Shared", "job_ids": ["job-a"]}]}

    group_study.prepare(str(tmp_path), "CL100", jobs[:2], None, call=call)
    group_study.prepare(str(tmp_path), "CL100", jobs[:3], None, call=call)
    assert calls == [2, 3], "a new lecture must not be studied through a stale map"


def test_reprocessing_a_lecture_rebuilds_the_map(tmp_path, library, monkeypatch):
    """Otherwise the group would keep quoting a transcript that no longer exists."""
    jobs, packs = library
    calls = []

    def call(task, payload):
        calls.append(task)
        return {"group_summary": "s", "concepts": [{"id": "g1", "job_ids": ["job-a"]}]}

    group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call)
    packs["job-b"] = _content(["b1", "b2"], generated_at="2026-08-16T00:00:00Z")
    group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call)
    assert len(calls) == 2


def test_two_groups_do_not_share_a_map(tmp_path, library):
    jobs, _ = library
    call = lambda task, payload: {"concepts": [{"id": "g1", "job_ids": ["job-a"]}]}
    group_study.prepare(str(tmp_path), "CL100", jobs[:2], None, call=call)
    other = group_study.prepare(str(tmp_path), "PHYS", jobs[:2], None, call=call)
    assert not other["cached"]


@pytest.mark.parametrize("junk", ["", "{", "[]", '{"schema_version": 99}'])
def test_a_damaged_cache_rebuilds_rather_than_raising(tmp_path, library, junk):
    jobs, _ = library
    members = group_study.collect_members(jobs)
    path = Path(group_study.analysis_path(str(tmp_path), "CL100"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(junk, encoding="utf-8")
    assert group_study.load_cached(str(tmp_path), "CL100", group_study.fingerprint(members)) is None


def test_force_bypasses_the_cache(tmp_path, library):
    jobs, _ = library
    calls = []
    call = lambda task, payload: (calls.append(task) or
                                  {"concepts": [{"id": "g1", "job_ids": ["job-a"]}]})
    group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call)
    group_study.prepare(str(tmp_path), "CL100", jobs, None, call=call, force=True)
    assert len(calls) == 2


# ----------------------------------------------------------------- grounding

def test_a_concept_attributed_to_a_lecture_outside_the_group_is_dropped(library):
    """It would send a student to a citation that does not exist."""
    jobs, _ = library
    members = group_study.collect_members(jobs)
    cleaned = group_study.normalize({"concepts": [
        {"id": "g1", "title": "Real", "job_ids": ["job-a", "job-elsewhere"]},
        {"id": "g2", "title": "Invented", "job_ids": ["job-elsewhere"]},
    ]}, members)
    assert [c["id"] for c in cleaned["concepts"]] == ["g1"]
    assert cleaned["concepts"][0]["job_ids"] == ["job-a"], "the unknown lecture is stripped"


def test_relationships_and_through_lines_cannot_reference_a_dropped_concept(library):
    jobs, _ = library
    members = group_study.collect_members(jobs)
    cleaned = group_study.normalize({
        "concepts": [{"id": "g1", "job_ids": ["job-a"]}],
        "relationships": [
            {"from_concept_id": "g1", "to_concept_id": "ghost", "relationship": "x"},
            {"from_concept_id": "g1", "to_concept_id": "g1", "relationship": "y"},
        ],
        "through_lines": [{"title": "t", "body": "b", "concept_ids": ["g1", "ghost"]}],
    }, members)
    assert len(cleaned["relationships"]) == 1
    assert cleaned["through_lines"][0]["concept_ids"] == ["g1"]


def test_an_empty_analysis_is_reported_rather_than_cached(tmp_path, library):
    jobs, _ = library
    result = group_study.prepare(str(tmp_path), "CL100", jobs, None,
                                 call=lambda task, payload: {"concepts": []})
    assert result["ok"] is False and result["reason"] == "empty_analysis"
    assert not Path(group_study.analysis_path(str(tmp_path), "CL100")).exists()


def test_a_group_with_nothing_ready_says_so(tmp_path, library, monkeypatch):
    jobs, packs = library
    monkeypatch.setattr(group_study.study_v2, "load_content",
                        lambda job: {"study_status": "preparing", "concepts": []})
    result = group_study.prepare(str(tmp_path), "CL100", jobs, None,
                                 call=lambda task, payload: pytest.fail("must not call"))
    assert result["ok"] is False and result["reason"] == "no_ready_lectures"


# ------------------------------------------------------------------- gateway

def test_the_task_is_allowlisted_and_defined():
    from lecturepack.services.ai_gateway import TASK_TYPES
    assert "group_analysis" in TASK_TYPES
    root = Path(__file__).resolve().parents[1]
    source = (root / "ai-gateway" / "src" / "tasks.js").read_text(encoding="utf-8")
    assert "group_analysis: object({" in source
    assert "group_analysis: 'You are given the finished analyses" in source
    assert "if (task === 'group_analysis') return 8000;" in source


def test_the_real_gateway_envelope_is_unwrapped(tmp_path, library):
    """A live answer arrives as {"result": ..., "diagnostics": ...}.

    This is the shape ``GatewayClient.request`` actually returns, and it is the
    one every mock in this suite got wrong: they returned a bare analysis, so
    the whole feature passed its tests while ``normalize`` looked for
    ``concepts`` on the envelope, found none, and reported ``empty_analysis``
    for every real request. Pin the real shape here or the mocks agree with
    each other and with nothing else.
    """
    jobs, _ = library

    class _Client:
        def __init__(self):
            self.calls = []

        def request(self, task, payload):
            self.calls.append(task)
            return {
                "result": {
                    "group_summary": "The subject as one thing",
                    "concepts": [
                        {"id": "g1", "title": "Shared", "job_ids": ["job-a", "job-b"]},
                    ],
                    "relationships": [],
                    "through_lines": [],
                    "gaps": [],
                },
                "diagnostics": {"request_id": "lp-test", "task_type": "group_analysis"},
            }

    client = _Client()
    result = group_study.prepare(str(tmp_path), "CL100", jobs, client)

    assert result["ok"] is True, result.get("reason")
    assert result["analysis"]["group_summary"] == "The subject as one thing"
    assert [c["title"] for c in result["analysis"]["concepts"]] == ["Shared"]
    assert client.calls == ["group_analysis"]


def test_a_bare_analysis_from_an_injected_call_still_works(tmp_path, library):
    """``prepare`` also accepts an injected ``call`` that returns no envelope."""
    jobs, _ = library
    bare = {"group_summary": "s", "concepts": [
        {"id": "g1", "title": "Shared", "job_ids": ["job-a", "job-b"]}]}
    result = group_study.prepare(str(tmp_path), "CL100", jobs, None,
                                 call=lambda task, payload: bare)
    assert result["ok"] is True
    assert result["analysis"]["concepts"][0]["title"] == "Shared"
