"""Focused orchestration tests for the production AI-first Study path."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.services import ai_study_service, study_v2  # noqa: E402
from lecturepack.services.ai_gateway import GatewayError  # noqa: E402


SEGMENTS = [
    {"start": 0.0, "end": 7.0,
     "text": "Polar bear fur is transparent while the skin beneath it is black."},
    {"start": 7.0, "end": 14.0,
     "text": "Polar bears are marine mammals adapted to Arctic sea ice."},
    {"start": 14.0, "end": 22.0,
     "text": "Sea ice loss changes hunting access and energy use."},
]


class _Job:
    def __init__(self, root: Path):
        self.job_id = "job-ai-study"
        self.paths = {
            "root": str(root),
            "candidates": str(root / "candidates"),
            "transcript": str(root / "transcript"),
        }
        self.manifest = {"title": "Polar Bears"}
        self.source = {
            "duration": 22.0,
            "path": str(root / "original-video-must-not-be-sent.mp4"),
        }
        (root / "candidates").mkdir(parents=True, exist_ok=True)
        (root / "transcript").mkdir(parents=True, exist_ok=True)


def _slides():
    return [
        {"image_filename": f"slide-{index}.png", "timestamp_seconds": float(index * 5),
         "decision": "accepted", "ocr_text": f"Arctic evidence {index}"}
        for index in range(1, 5)
    ]


def _analysis():
    return {
        "lecture_summary": "The lecture explains polar-bear adaptations and sea-ice pressure.",
        "concepts": [
            {"id": "c1", "title": "Transparent fur", "importance": 5,
             "explanation": "Transparent hairs scatter light over black skin.",
             "lecture_sources": [{"segment_id": "0"}]},
            {"id": "c2", "title": "Sea-ice adaptation", "importance": 4,
             "explanation": "Marine-mammal behavior depends on sea ice.",
             "lecture_sources": [{"segment_id": "1"}]},
        ],
        "relationships": [{
            "from_concept_id": "c1", "to_concept_id": "c2",
            "relationship": "Both are Arctic adaptations.",
        }],
        "vision_requests": [
            {"slide_id": f"slide-{index}.png", "reason": "diagram evidence"}
            for index in range(1, 5)
        ],
        "research_requests": [
            {"concept_id": "c2", "query": f"polar bear sea ice evidence {index}",
             "reason": "verify current context"}
            for index in range(1, 5)
        ],
    }


def _materials(*, replacement: bool = False):
    c1_explanation = (
        "Transparent guard hairs scatter visible light while dark skin absorbs energy."
        if replacement else
        "Polar-bear hairs are transparent rather than white; black skin lies underneath."
    )
    return {
        "lecture_summary": "Polar bears combine physical and behavioral Arctic adaptations.",
        "concepts": [
            {"id": "c1", "title": "Transparent fur", "importance": 5,
             "explanation": c1_explanation,
             "related_concept_ids": ["c2"],
             "lecture_sources": [{"segment_id": "0", "slide_id": "slide-1.png"}]},
            {"id": "c2", "title": "Sea-ice adaptation", "importance": 4,
             "explanation": "Polar bears are marine mammals whose hunting depends on sea ice.",
             "related_concept_ids": ["c1"],
             "lecture_sources": [{"segment_id": "1"}],
             "web_sources": [{"title": "Arctic evidence", "url": "https://example.org/arctic",
                              "claim": "Sea ice shapes hunting access."}]},
        ],
        "key_terms": [{"label": "guard hair", "detail": "A transparent outer hair.",
                       "concept_ids": ["c1"], "lecture_sources": [{"segment_id": "0"}]}],
        "people": [],
        "dates": [],
        "misconceptions": [{"label": "White pigment", "detail": "The fur is not white pigment.",
                            "concept_ids": ["c1"], "lecture_sources": [{"segment_id": "0"}]}],
        "study_guide": [
            {"heading": "Color and insulation", "body": c1_explanation,
             "concept_ids": ["c1"], "lecture_sources": [{"segment_id": "0"}]},
            {"heading": "Life on sea ice", "body": "Sea ice supports hunting behavior.",
             "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "1"}]},
        ],
        "flashcards": [
            {"id": "f1", "front": "Why does polar-bear fur look white?",
             "back": "Transparent hairs scatter light above black skin.",
             "concept_ids": ["c1"], "lecture_sources": [{"segment_id": "0"}]},
            {"id": "f2", "front": "Why are polar bears marine mammals?",
             "back": "Their feeding ecology and movement depend on Arctic seas and ice.",
             "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "1"}]},
        ],
        "quiz": [
            {"id": "q1", "question": "What is the fur pigment?", "qtype": "multiple_choice",
             "options": ["Transparent", "White", "Black"], "correct_index": 0,
             "explanation": "The hairs are transparent.", "concept_ids": ["c1"],
             "lecture_sources": [{"segment_id": "0"}]},
            {"id": "q2", "question": "Polar bears are marine mammals.", "qtype": "true_false",
             "options": ["True", "False"], "correct_index": 0,
             "explanation": "The lecture identifies them as marine mammals.",
             "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "1"}]},
            {"id": "q3", "question": "Explain one sea-ice dependency.", "qtype": "short_answer",
             "accepted_answers": ["Sea ice gives access to hunting areas."],
             "rubric": "Connect sea ice to hunting access or energy use.",
             "explanation": "Sea ice affects hunting.", "concept_ids": ["c2"],
             "lecture_sources": [{"segment_id": "2"}]},
        ],
        "quick_study_material": {
            "five_minute": ["c1"], "ten_minute": ["c1", "c2"],
            "twenty_minute": ["c1", "c2"], "full": ["c1", "c2"],
        },
        "teach_me_foundations": [{
            "concept_id": "c1", "concept_ids": ["c1"],
            "explanation": c1_explanation,
            "analogy": "Think of clear fibers scattering light like snow crystals.",
            "check_question": "Why can transparent fur look white?",
            "rubric": "Mention transparent hairs and scattered light.",
            "lecture_sources": [{"segment_id": "0"}],
        }],
    }


class _Client:
    def __init__(self, *, fail_vision: bool = False, malformed: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self.fail_vision = fail_vision
        self.malformed = malformed

    def request(self, task, payload, request_id=None):
        self.calls.append((task, copy.deepcopy(payload)))
        if task == "lecture_analysis":
            result = _analysis()
        elif task == "vision_slide":
            if self.fail_vision:
                raise GatewayError("vision_unavailable", "Selected slide vision is unavailable.")
            result = {"description": "The slide contrasts clear fur with dark skin.",
                      "lecture_sources": [{"slide_id": payload["slide_id"]}]}
        elif task == "web_enrichment":
            result = {"summary": "Current public context.", "sources": [{
                "title": "Arctic evidence", "url": "https://example.org/arctic",
                "claim": "Sea ice shapes hunting access.",
            }]}
        elif task == "study_material_generation":
            result = {"concepts": [{"title": "broken"}]} if self.malformed else _materials()
        elif task == "ask":
            result = {"answer": "The lecture links sea ice to hunting access.",
                      "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "2"}]}
        elif task == "teach_me":
            result = {"explanation": "Sea ice acts as a hunting platform.",
                      "analogy": "It is like a moving bridge to prey.",
                      "check_question": "Why does losing sea ice matter?",
                      "rubric": "Connect access to prey with energy cost.",
                      "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "2"}]}
        elif task == "grade_short_answer":
            result = {"correct": True, "score": 0.91,
                      "feedback": "Equivalent wording captures hunting access.",
                      "ideal_answer": "Sea ice provides access to hunting areas.",
                      "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "2"}]}
        elif task == "regenerate_concept":
            material = _materials(replacement=True)
            result = {
                "concept": material["concepts"][0],
                "flashcards": [material["flashcards"][0]],
                "quiz": [material["quiz"][0]],
                "study_guide_fragments": [material["study_guide"][0]],
            }
        else:  # pragma: no cover - test fixture contract
            raise AssertionError(f"unexpected task: {task}")
        return {
            "result": result,
            "diagnostics": {
                "request_id": request_id or "lp-test", "task_type": task,
                "attempted_routes": [f"{task}-primary"],
            },
        }


@pytest.fixture
def lecture(monkeypatch, tmp_path):
    job = _Job(tmp_path)
    slides = _slides()
    monkeypatch.setattr(study_v2, "_load_segments", lambda _job: copy.deepcopy(SEGMENTS))
    monkeypatch.setattr(study_v2, "_load_accepted_slides", lambda _job: copy.deepcopy(slides))
    # Tiny valid PNGs are enough to exercise bounded selective vision.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c4944415408d763f8ffff3f0005fe02fe0def46b80000000049454e44ae426082")
    for slide in slides:
        (Path(job.paths["candidates"]) / slide["image_filename"]).write_bytes(png)
    return job


def _prepare(job, client=None):
    client = client or _Client()
    content = ai_study_service.prepare_ai_study(job, client)
    return content, client


def test_two_pass_generation_is_automatic_quality_shape_and_video_path_free(lecture):
    content, client = _prepare(lecture)
    tasks = [task for task, _payload in client.calls]
    assert tasks[0] == "lecture_analysis"
    assert tasks[-1] == "study_material_generation"
    outbound = json.dumps([payload for _task, payload in client.calls])
    assert "original-video-must-not-be-sent" not in outbound
    assert content["study_status"] == study_v2.STUDY_READY
    assert len(content["concepts"]) == 2
    assert len(content["flashcards"]) == 2
    assert {item["qtype"] for item in content["quiz"]} == {
        "multiple_choice", "true_false", "short_answer"}


def test_long_lecture_uses_hierarchical_analysis_and_compact_pass_two(monkeypatch, lecture):
    long_segments = [
        {"start": float(index * 5), "end": float(index * 5 + 5),
         "text": (f"Segment {index} explains Arctic adaptation. " + "evidence " * 1800)}
        for index in range(100)
    ]
    monkeypatch.setattr(study_v2, "_load_segments", lambda _job: copy.deepcopy(long_segments))
    monkeypatch.setattr(ai_study_service, "_MAX_ANALYSIS_CHARS", 100_000)
    client = _Client()
    ai_study_service.prepare_ai_study(lecture, client)
    analysis_calls = [payload for task, payload in client.calls if task == "lecture_analysis"]
    assert len(analysis_calls) >= 3  # at least two chunks plus canonical merge
    material_payload = next(payload for task, payload in client.calls
                            if task == "study_material_generation")
    evidence = material_payload["lecture"]["transcript"]
    assert len(evidence) < len(long_segments)
    assert len(json.dumps(material_payload)) < 1_500_000


def test_provenance_timestamps_slides_and_web_links_survive_persistence(lecture):
    content, _client = _prepare(lecture)
    c1, c2 = content["concepts"]
    assert c1["lecture_sources"][0]["start_ms"] == 0
    assert c1["lecture_sources"][0]["slide_id"] == "slide-1.png"
    assert c2["web_sources"][0]["url"] == "https://example.org/arctic"
    reloaded = study_v2.load_content(lecture)
    assert reloaded["concepts"] == content["concepts"]


def test_unverified_model_urls_are_removed_from_materials_and_interactions(lecture):
    class UrlInjectingClient(_Client):
        def request(self, task, payload, request_id=None):
            response = super().request(task, payload, request_id=request_id)
            if task == "study_material_generation":
                response["result"]["concepts"][1]["web_sources"].append({
                    "title": "Invented", "url": "https://fake.invalid/claim",
                    "claim": "Unverified model URL",
                })
            if task == "ask":
                response["result"]["web_sources"] = [{
                    "title": "Invented", "url": "https://fake.invalid/answer",
                    "claim": "Unverified interactive URL",
                }]
            return response

    content, client = _prepare(lecture, UrlInjectingClient())
    assert "fake.invalid" not in json.dumps(content)
    answer = ai_study_service.ask(lecture, client, "How does sea ice affect hunting?")
    assert "fake.invalid" not in json.dumps(answer)
    assert [source["url"] for source in answer["web_sources"]] == [
        "https://example.org/arctic"]


def test_selective_vision_and_web_enrichment_are_bounded(lecture):
    _content, client = _prepare(lecture)
    assert len([task for task, _payload in client.calls if task == "vision_slide"]) == 3
    assert len([task for task, _payload in client.calls if task == "web_enrichment"]) == 3


def test_study_succeeds_when_optional_vision_is_unavailable(lecture):
    content, client = _prepare(lecture, _Client(fail_vision=True))
    assert content["study_status"] == study_v2.STUDY_READY
    assert content["concepts"]
    assert any(task == "study_material_generation" for task, _payload in client.calls)


def test_malformed_ungrounded_provider_output_fails_safely(lecture):
    with pytest.raises(ai_study_service.StudyContentError):
        _prepare(lecture, _Client(malformed=True))
    failed = study_v2.load_content(lecture)
    assert failed["study_status"] == study_v2.STUDY_FAILED
    assert failed["generation_metadata"]["last_error"]["code"] in {
        "ungrounded_material", "incomplete_material"}


def test_failed_routes_can_use_basic_then_retry_to_ready(lecture):
    class FailingClient:
        def request(self, task, payload, request_id=None):
            raise GatewayError(
                "ai_routes_failed", "Study AI could not complete this request.",
                status=503,
                diagnostics={"request_id": request_id, "task_type": task,
                             "attempted_routes": ["analysis-primary", "analysis-secondary"],
                             "provider_codes": ["provider_unavailable", "provider_timeout"],
                             "provider_status": [503, 504], "retry_count": 1},
            )

    with pytest.raises(GatewayError):
        ai_study_service.prepare_ai_study(lecture, FailingClient())
    failed = study_v2.load_content(lecture)
    assert failed["study_status"] == study_v2.STUDY_FAILED
    assert failed["generation_metadata"]["diagnostics"]["attempted_routes"] == [
        "analysis-primary", "analysis-secondary"]
    assert failed["generation_metadata"]["diagnostics"]["provider_status"] == [503, 504]
    assert failed["generation_metadata"]["diagnostics"]["retry_count"] == 1
    basic = study_v2.use_basic_study(lecture)
    assert basic["study_status"] == study_v2.STUDY_BASIC
    retried = ai_study_service.prepare_ai_study(lecture, _Client())
    assert retried["study_status"] == study_v2.STUDY_READY


def test_provider_failure_after_job_cancellation_is_not_persisted(lecture):
    cancelled = {"value": False}

    class LateFailureClient:
        def request(self, task, payload, request_id=None):
            cancelled["value"] = True
            raise GatewayError(
                "provider_timeout", "The cancelled request finished late.",
                status=504,
                diagnostics={"request_id": request_id, "task_type": task},
            )

    result = ai_study_service.prepare_ai_study(
        lecture, LateFailureClient(),
        cancelled=lambda: cancelled["value"],
    )

    assert result["study_status"] == study_v2.STUDY_PREPARING
    assert result["generation_metadata"].get("last_error") is None


def test_existing_and_manual_mastery_survive_ai_replacement(lecture):
    old = study_v2.generate_deterministic_content(lecture)
    old["concepts"][0]["id"] = "old-id"
    old["concepts"][0]["title"] = "Transparent fur"
    study_v2.save_content(lecture, old)
    study_v2.set_manual_mastery(lecture, "old-id", "MASTERED")
    content, _client = _prepare(lecture)
    assert content["concepts"][0]["title"] == "Transparent fur"
    progress = study_v2.load_progress(lecture)
    assert progress["concepts"]["c1"]["mastery"] == "MASTERED"
    assert progress["concepts"]["c1"]["manual"] is True
    study_v2.set_manual_mastery(lecture, "c2", "NEEDS_REVIEW")
    assert study_v2.load_progress(lecture)["concepts"]["c2"]["mastery"] == "NEEDS_REVIEW"


def test_short_answer_grading_accepts_semantically_equivalent_wording(lecture):
    _content, client = _prepare(lecture)
    result = ai_study_service.grade_short_answer(
        lecture, client,
        question="Explain one sea-ice dependency.",
        answer="The ice lets bears reach prey even though my wording differs.",
        rubric="Connect sea ice to hunting access.",
        concept_ids=["c2"],
    )
    assert result["correct"] is True
    assert result["score"] == pytest.approx(0.91)
    assert "Equivalent wording" in result["feedback"]


def test_ask_and_teach_me_send_only_retrieved_lecture_context(lecture):
    _content, client = _prepare(lecture)
    answer = ai_study_service.ask(lecture, client, "How does sea ice affect hunting?")
    lesson = ai_study_service.teach_me(lecture, client, "c2")
    ask_payload = next(payload for task, payload in client.calls if task == "ask")
    teach_payload = next(payload for task, payload in client.calls if task == "teach_me")
    assert answer["concept_ids"] == ["c2"]
    assert lesson["check_question"]
    assert ask_payload["retrieved_context"]["transcript_evidence"]
    assert teach_payload["retrieved_context"]["concepts"]
    assert "history" not in ask_payload and "provider" not in ask_payload


def test_transcript_refresh_changes_only_affected_concept_and_preserves_mastery(lecture):
    content, _client = _prepare(lecture)
    untouched = copy.deepcopy(next(item for item in content["concepts"] if item["id"] == "c2"))
    study_v2.set_manual_mastery(lecture, "c1", "MASTERED")
    client = _Client()
    refreshed = ai_study_service.regenerate_affected(
        lecture, client, ["0"], concept_ids=["c1"])
    assert [task for task, _payload in client.calls] == ["regenerate_concept"]
    assert next(item for item in refreshed["concepts"] if item["id"] == "c2") == untouched
    assert "guard hairs scatter" in next(
        item for item in refreshed["concepts"] if item["id"] == "c1")["explanation"]
    assert study_v2.load_progress(lecture)["concepts"]["c1"]["mastery"] == "MASTERED"


def test_concept_linked_cache_reopens_without_new_request_and_is_bounded(lecture):
    _content, client = _prepare(lecture)
    first = ai_study_service.ask(lecture, client, "How does sea ice affect hunting?")
    before = len([task for task, _payload in client.calls if task == "ask"])
    second = ai_study_service.ask(lecture, client, "How does sea ice affect hunting?")
    assert second["cached"] is True
    assert second["answer"] == first["answer"]
    assert len([task for task, _payload in client.calls if task == "ask"]) == before
    for index in range(30):
        ai_study_service.ask(lecture, client, f"Explain sea ice hunting angle {index}")
    cache = study_v2.load_content(lecture)["cached_responses"]
    assert len(cache) == 24
    assert all("prompt" not in item for item in cache)


def test_basic_study_is_explicit_and_quick_study_uses_no_ai(lecture):
    basic = study_v2.use_basic_study(lecture)
    assert basic["study_status"] == study_v2.STUDY_BASIC
    assert basic["generation_metadata"]["basic_reason"] == "user_selected"
    session = study_v2.build_quick_study_session(lecture, minutes=5)
    assert session["duration_minutes"] == 5
    assert len(session["items"]) <= 5
    assert all(
        item["kind"] != "quiz" or next(
            question for question in basic["quiz"] if question["id"] == item["id"]
        )["qtype"] != "short_answer"
        for item in session["items"]
    )


def test_malformed_partial_regeneration_settles_failed_state(lecture, monkeypatch):
    _prepare(lecture, _Client())
    targets = ai_study_service.affected_concept_ids(lecture, ["0"])
    assert targets

    def fail_regeneration(*_args, **_kwargs):
        raise ai_study_service.StudyContentError(
            "invalid_partial_material", "The targeted Study material was invalid.")

    monkeypatch.setattr(ai_study_service, "_regenerate_one", fail_regeneration)
    with pytest.raises(ai_study_service.StudyContentError):
        ai_study_service.regenerate_affected(
            lecture, _Client(), ["0"], concept_ids=targets)

    metadata = study_v2.load_content(lecture)["generation_metadata"]
    assert metadata["partial_refresh"]["status"] == "failed"
    assert metadata["last_interaction_error"]["code"] == "invalid_partial_material"


def test_copied_diagnostics_revalidate_local_metadata(lecture):
    content = study_v2.load_content(lecture)
    content["study_status"] = study_v2.STUDY_FAILED
    content["generation_metadata"] = {
        "stage": "private transcript disguised as a stage",
        "last_successful_stage": "private lecture words",
        "last_error": {"code": "private transcript code"},
        "diagnostics": {"attempted_routes": ["ask-primary@openrouter:server/model"]},
    }
    study_v2.save_content(lecture, content)

    diagnostics = ai_study_service.diagnostics(lecture)
    serialized = json.dumps(diagnostics)
    assert diagnostics["study_status"] == study_v2.STUDY_FAILED
    assert diagnostics["generation_stage"] == ""
    assert diagnostics["last_successful_stage"] == ""
    assert diagnostics["error_category"] == ""
    assert "private transcript" not in serialized
