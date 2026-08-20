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
        elif task == "expand_concept_material":
            # The post-ready enrichment pass. Returns ONE new card and question
            # so the expansion path is exercised; the front/question differ from
            # the generated pack, or dedup would drop them and the append would
            # never be tested.
            result = {
                "flashcards": [{
                    "id": "fc-extra", "front": "How does sea ice loss change hunting cost?",
                    "back": "Longer swims raise energy spent per kill.",
                    "difficulty": "hard", "concept_ids": ["c2"],
                    "lecture_sources": [{"segment_id": "2"}],
                }],
                "quiz": [{
                    "id": "qz-extra",
                    "question": "Why does a longer swim reduce hunting success?",
                    "qtype": "short_answer", "options": [], "correct_index": 0,
                    "accepted_answers": ["It costs more energy than the prey returns."],
                    "rubric": "Link distance to energy cost.",
                    "explanation": "Energy spent travelling is not recovered.",
                    "concept_ids": ["c2"], "lecture_sources": [{"segment_id": "2"}],
                }],
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
    # study_material_generation is the last call that BUILDS the pack. An
    # enrichment pass of per-concept expand_concept_material calls follows it,
    # once the pack is already marked ready -- a single generation call returns
    # close to the schema minimum, and the route budget forbids asking for more
    # in one request. See _expand_material. Each concept also gets a teach_me
    # call in the same pass, pre-warming the cache so a student's later
    # "Teach Me" click is instant instead of a fresh gateway round trip.
    assert "study_material_generation" in tasks
    generation = tasks.index("study_material_generation")
    assert generation > tasks.index("lecture_analysis")
    assert set(tasks[generation + 1:]) <= {"expand_concept_material", "teach_me"}
    assert tasks.count("teach_me") <= ai_study_service.EXPAND_PREWARM_CONCEPTS
    outbound = json.dumps([payload for _task, payload in client.calls])
    assert "original-video-must-not-be-sent" not in outbound
    assert content["study_status"] == study_v2.STUDY_READY
    assert len(content["concepts"]) == 2
    # Generation returns two cards; the expansion pass appends what it can on
    # top, deduplicated by meaning. The pack is therefore larger than the
    # generator alone produced -- which is the entire point of the pass.
    assert len(content["flashcards"]) > 2
    assert any(card["front"].startswith("How does sea ice loss")
               for card in content["flashcards"]), "expansion output was not appended"
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


def test_generation_prewarms_teach_me_so_the_first_click_costs_no_request(lecture):
    # The expansion pass warms teach_me for every concept. That warming writes
    # to the same content file the expansion loop later re-saves, so an
    # ordering slip silently drops the cache and the student pays a full
    # gateway round trip on the click this exists to make instant.
    content, client = _prepare(lecture)
    warmed = [payload["concept"]["id"] for task, payload in client.calls
              if task == "teach_me"]
    # Bounded on purpose: warming every concept doubles this pass's request
    # count and would evict itself from study_v2's 24-entry shared cache.
    assert 0 < len(warmed) <= ai_study_service.EXPAND_PREWARM_CONCEPTS
    assert len(warmed) == len(set(warmed)), "a concept was warmed twice"
    before = len(warmed)
    for concept_id in warmed:
        lesson = ai_study_service.teach_me(lecture, client, concept_id)
        assert lesson["cached"] is True, f"{concept_id} was warmed but not cached"
    assert len([task for task, _payload in client.calls
                if task == "teach_me"]) == before


def _ranked(lecture, concepts, prompt, **kwargs):
    content = study_v2.load_content(lecture)
    content["concepts"] = concepts
    study_v2.save_content(lecture, content)
    context, _ids = ai_study_service._retrieved_context(lecture, prompt, **kwargs)
    return [item["id"] for item in context["concepts"]]


def _concept(cid, title, explanation, importance=3):
    return {
        "id": cid, "title": title, "importance": importance,
        "explanation": explanation, "related_concept_ids": [],
        "sources": [{"segment_id": "0"}], "lecture_sources": [{"segment_id": "0"}],
        "web_sources": [], "provenance": "lecture",
    }


def test_retrieval_is_not_dominated_by_filler_words(lecture):
    # The old ranker scored raw word overlap at 4 points each with no IDF and
    # no stopword removal, so a concept sharing only "the difference between"
    # beat the concept the question is actually about.
    concepts = [
        _concept("c-noise", "Administrative notes",
                 "The difference between the sections is not important for the exam.",
                 importance=5),
        _concept("c-real", "Thermohaline circulation",
                 "Density differences drive the deep ocean conveyor.", importance=1),
    ]
    ranked = _ranked(lecture, concepts, "What is the difference between the thermohaline currents?")
    assert ranked[0] == "c-real", (
        "filler-word overlap outranked the concept the question names")


def test_retrieval_matches_morphological_variants_and_prefers_titles(lecture):
    concepts = [
        _concept("c-body", "Field notes",
                 "We briefly mention that glaciation shaped these valleys."),
        _concept("c-title", "Glaciation", "Ice sheets advance and retreat over time."),
    ]
    # "glaciers" must reach "glaciation"/"glaciation" via stemming, and a title
    # hit must outrank the same word buried in an explanation.
    assert _ranked(lecture, concepts, "how did glaciers form this landscape")[0] == "c-title"


@pytest.mark.parametrize("word", ["forest", "shoulder", "owner", "outer", "outing"])
def test_content_words_whose_stem_is_a_stopword_are_not_annihilated(word):
    # Stemming first and filtering stopwords after deleted these outright:
    # forest -> "for", shoulder -> "should", owner -> "own". Not noise --
    # total loss of the query's most discriminating term, on BOTH sides, so a
    # forestry lecture could not be searched for "forest".
    assert ai_study_service._terms(word), f"{word!r} vanished from retrieval"


@pytest.mark.parametrize("singular,plural", [
    ("forest", "forests"), ("interest", "interests"), ("harvest", "harvests"),
    ("process", "processes"), ("class", "classes"), ("mass", "masses"),
    ("focus", "focuses"), ("glacier", "glaciers"), ("study", "studies"),
    ("derivative", "derivatives"),
    # The -e nouns below are the HIGH-IDF domain terms of a science lecture --
    # exactly the words the IDF ranker leans on hardest. Stripping a bare "es"
    # severed every one of them from its own plural, so "how do waves
    # propagate" scored zero against a concept titled "Wave".
    ("molecule", "molecules"), ("particle", "particles"), ("wave", "waves"),
    ("state", "states"), ("force", "forces"), ("value", "values"),
    ("variable", "variables"), ("source", "sources"), ("gene", "genes"),
    # Genuine -es plurals must keep working: the rule keys on the sibilant.
    ("box", "boxes"), ("church", "churches"),
])
def test_singular_and_plural_reach_the_same_term(singular, plural):
    # A word must match its own plural or retrieval silently halves its recall.
    assert ai_study_service._terms(singular) == ai_study_service._terms(plural)


def test_retrieval_finds_a_forest_lecture_by_its_subject(lecture):
    # End-to-end version of the annihilation bug, through the real ranker.
    concepts = [
        _concept("c-other", "Course admin", "Reminders about the exam timetable."),
        _concept("c-forest", "Forest succession",
                 "Pioneer species colonise cleared ground before canopy trees."),
    ]
    assert _ranked(lecture, concepts, "how does a forest regrow")[0] == "c-forest"


def test_prewarm_targets_the_concepts_the_student_is_shown_first():
    # Models rarely spread `importance`, so an all-tied pack is the common
    # case and the tiebreak is then the ONLY thing ordering them. The concepts
    # stored in normalizer order below deliberately do NOT match the
    # alphabetical order the student is shown.
    concepts = [_concept(f"c{index}", title, "Body text.", importance=3)
                for index, title in enumerate(
                    ["Zebra", "Alpha", "Mango", "Beta", "Yak", "Cobra", "Delta"])]
    priority = ai_study_service.study_priority_order(concepts)
    assert priority[0] == "c1", "Alpha sorts first once the tiebreak applies"
    assert priority != [item["id"] for item in concepts], (
        "fixture must not already be in priority order, or it proves nothing")
    warmed = ai_study_service._prewarm_concept_ids(concepts, 3)
    assert warmed == priority[:3]
    # The concept stored first ("Zebra") must NOT be warmed: that is exactly
    # what the untiebroken version got wrong.
    assert "c0" not in warmed


def test_prewarm_still_respects_real_importance_over_the_title_tiebreak():
    concepts = [_concept("c-low", "Aardvark", "Body.", importance=1),
                _concept("c-high", "Zebra", "Body.", importance=5)]
    assert ai_study_service._prewarm_concept_ids(concepts, 1) == ["c-high"]


def test_retrieval_pins_the_requested_concept_regardless_of_wording(lecture):
    concepts = [
        _concept("c-off", "Completely unrelated", "Nothing to do with the query at all."),
        _concept("c-pinned", "Obscure topic", "Sparse text."),
    ]
    ranked = _ranked(
        lecture, concepts, "words that match the other concept entirely",
        concept_id="c-pinned")
    assert ranked[0] == "c-pinned", "an explicit concept pin must always win"


def test_retrieval_survives_a_prompt_that_is_entirely_stopwords(lecture):
    concepts = [
        _concept("c-a", "Alpha", "First body.", importance=2),
        _concept("c-b", "Beta", "Second body.", importance=5),
    ]
    # Every term is filtered out, so there is no signal to rank on. It must
    # still return concepts (importance-ordered) rather than nothing at all.
    ranked = _ranked(lecture, concepts, "what is it about the")
    assert ranked[0] == "c-b"
    assert set(ranked) == {"c-a", "c-b"}


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


def test_expansion_does_not_discard_an_answer_cached_while_it_ran(lecture):
    """BUG-47: background growth held a snapshot across a ~50s gateway call.

    The pack is already ready and live in the UI during that window, so a
    student's Ask can land in the content file before the expansion writes its
    snapshot back. It used to be overwritten -- silently, and only visible as
    the same question costing a second full round trip.
    """
    content, _client = _prepare(lecture)

    class _StudentAsksMidExpansion(_Client):
        """Ask exactly once, during the first expansion call.

        Once, not every call: a student who re-asks on every iteration would
        keep re-writing the entry and mask the lost update.
        """

        asked = False
        served = 0

        def request(self, task, payload, request_id=None):
            if task != "expand_concept_material":
                return super().request(task, payload, request_id)
            if not self.asked:
                self.asked = True
                study_v2.cache_concept_response(
                    lecture, "ask", "asked while the pack was still growing",
                    ["c2"], {"answer": "cached mid-expansion"})
            # Unique material per call, so the expansion actually appends and
            # SAVES. The shared fixture returns one fixed card, which the pack
            # built in _prepare already contains -- dedup would skip every
            # save and the test would pass without exercising the hazard.
            self.served += 1
            index = self.served
            response = super().request(task, payload, request_id)
            card = response["result"]["flashcards"][0]
            card["id"] = f"fc-extra-{index}"
            card["front"] = f"Extra card {index}: what does sea ice cost?"
            question = response["result"]["quiz"][0]
            question["id"] = f"qz-extra-{index}"
            question["question"] = f"Extra question {index}: why is the swim costly?"
            return response

    client = _StudentAsksMidExpansion()
    ai_study_service._expand_material(lecture, client, content)

    cache = study_v2.load_content(lecture)["cached_responses"]
    assert any(item["response"].get("answer") == "cached mid-expansion"
               for item in cache), "the student's cached answer was overwritten"


def test_preserving_save_does_not_resurrect_cache_for_a_deleted_concept(lecture):
    """The merge cannot resurrect what delete_concept pruned.

    A snapshot cannot say whether a key missing from it was added by someone
    else (keep it) or deleted by the snapshot's own author (do not). The one
    caller that deletes cached answers -- delete_concept -- deletes the concept
    with them, so the merge drops any entry whose concepts are gone.
    """
    _content, _client = _prepare(lecture)
    study_v2.cache_concept_response(
        lecture, "ask", "about the concept being deleted", ["c2"], {"answer": "stale"})
    assert study_v2.delete_concept(lecture, "c2") is True

    survivor = study_v2.load_content(lecture)
    study_v2.save_content_preserving_cache(lecture, survivor)
    cache = study_v2.load_content(lecture)["cached_responses"]
    assert all("c2" not in item.get("concept_ids", []) for item in cache)
