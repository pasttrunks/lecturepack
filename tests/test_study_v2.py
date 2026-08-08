"""Focused tests for the Study V2 overhaul: grounded concepts, mastery,
flashcards, quiz, quick study, and old-job migration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.services import study_v2  # noqa: E402


# ---- source-reference validation ---------------------------------------- #
def test_validate_source_ref_valid_segment():
    segments = [{"start": 10.0, "end": 15.0, "text": "Hello world"}]
    ref = {"segment_id": "0"}
    validated = study_v2.validate_source_ref(ref, segments, [])
    assert validated is not None
    assert validated["start_ms"] == 10000
    assert validated["end_ms"] == 15000
    assert validated["preview"] == "Hello world"


def test_validate_source_ref_rejects_fake_segment():
    segments = [{"start": 10.0, "end": 15.0, "text": "Hello"}]
    ref = {"segment_id": "999"}
    assert study_v2.validate_source_ref(ref, segments, []) is None


def test_validate_source_ref_rejects_fake_slide():
    segments = [{"start": 10.0, "end": 15.0, "text": "Hello"}]
    slides = [{"image_filename": "slide-1.png", "timestamp_seconds": 12.0}]
    ref = {"segment_id": "0", "slide_id": "fake-slide"}
    # A proposed slide that doesn't exist rejects the whole reference.
    assert study_v2.validate_source_ref(ref, segments, slides) is None


def test_validate_sources_drops_invalid():
    segments = [{"start": 0.0, "end": 5.0, "text": "A"}]
    refs = [{"segment_id": "0"}, {"segment_id": "999"}]
    out = study_v2.validate_sources(refs, segments, [])
    assert len(out) == 1
    assert out[0]["segment_id"] == "0"


# ---- content generation (Built-in Study) --------------------------------- #
def test_generate_deterministic_content_grounded():
    class FakeJob:
        paths = {"root": "/tmp", "transcript": "/tmp/transcript"}

    # Monkeypatch the segment loader to return real segments.
    study_v2._load_segments = lambda job: [
        {"start": 0.0, "end": 5.0, "text": "The discovery of Troy was important."},
        {"start": 5.0, "end": 10.0, "text": "Schliemann excavated at Hisarlik."},
        {"start": 10.0, "end": 15.0, "text": "This is important for archaeology."},
    ]
    study_v2._load_accepted_slides = lambda job: []
    content = study_v2.generate_deterministic_content(FakeJob())
    assert content["concepts"]
    assert content["flashcards"]
    assert content["quiz"]
    # Every concept has a real source reference.
    for concept in content["concepts"]:
        assert concept["sources"]
        assert concept["sources"][0]["segment_id"] is not None
    # Emphasis detected on the "this is important" segment.
    emphasized = [c for c in content["concepts"] if c.get("emphasis")]
    assert emphasized


# ---- old-job migration --------------------------------------------------- #
def test_ensure_study_v2_generates_from_existing_assets(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root), "transcript": str(root / "transcript")}

    job = FakeJob(tmp_path)
    # No study-content-v2.json yet.
    assert not os.path.exists(study_v2.content_path(job))
    study_v2._load_segments = lambda job: [
        {"start": 0.0, "end": 5.0, "text": "The discovery of Troy was important."},
    ]
    study_v2._load_accepted_slides = lambda job: []
    content = study_v2.ensure_study_v2(job)
    assert content["concepts"]
    # Now persisted.
    assert os.path.exists(study_v2.content_path(job))
    # Second call reuses the cached content.
    content2 = study_v2.ensure_study_v2(job)
    assert content2["concepts"] == content["concepts"]


# ---- mastery via Rust core ----------------------------------------------- #
def test_record_flashcard_result_updates_mastery(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root)}

    job = FakeJob(tmp_path)
    progress = study_v2.record_flashcard_result(job, "f1", ["c1"], True)
    assert progress["concepts"]["c1"]["mastery"] == "LEARNING"
    assert "f1" in progress["flashcard_results"]


def test_record_quiz_wrong_sets_needs_review(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root)}

    job = FakeJob(tmp_path)
    progress = study_v2.record_quiz_result(job, "q1", ["c1"], False)
    assert progress["concepts"]["c1"]["mastery"] == "NEEDS_REVIEW"
    assert len(progress["quiz_attempts"]) == 1


def test_repeated_successes_master(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root)}

    job = FakeJob(tmp_path)
    study_v2.record_flashcard_result(job, "f1", ["c1"], True)
    study_v2.record_flashcard_result(job, "f2", ["c1"], True)
    progress = study_v2.load_progress(job)
    assert progress["concepts"]["c1"]["mastery"] == "MASTERED"


def test_study_core_info_reports_rust():
    info = study_v2.study_core_info()
    assert info["available"] is True
    assert info["implementation"] == "rust"
    assert info["version"] == "0.1.0"


# ---- quick study --------------------------------------------------------- #
def test_build_quick_study_session_prioritizes_weak(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root)}

    job = FakeJob(tmp_path)
    # Create content with a weak concept.
    content = {
        "schema_version": 2,
        "concepts": [
            {"id": "c1", "title": "Troy", "explanation": "x", "sources": [], "emphasis": "emphasized"},
            {"id": "c2", "title": "Legacy", "explanation": "y", "sources": [], "emphasis": None},
        ],
        "flashcards": [
            {"id": "f1", "front": "Q", "back": "A", "concept_ids": ["c1"], "sources": []},
        ],
        "quiz": [
            {"id": "q1", "question": "Q", "qtype": "mc", "options": ["a", "b"],
             "correct_index": 0, "explanation": "e", "concept_ids": ["c1"], "sources": []},
        ],
    }
    study_v2.save_content(job, content)
    # Mark c1 as needs review.
    study_v2.record_quiz_result(job, "q1", ["c1"], False)
    session = study_v2.build_quick_study_session(job)
    assert session["items"]
    assert session["items"][0]["concept_id"] == "c1"


# ---- edit / delete ------------------------------------------------------- #
def test_delete_concept_removes_related_items(tmp_path):
    class FakeJob:
        def __init__(self, root):
            self.paths = {"root": str(root)}

    job = FakeJob(tmp_path)
    content = {
        "schema_version": 2,
        "concepts": [
            {"id": "c1", "title": "Troy", "explanation": "x", "sources": [], "emphasis": None},
        ],
        "flashcards": [
            {"id": "f1", "front": "Q", "back": "A", "concept_ids": ["c1"], "sources": []},
        ],
        "quiz": [
            {"id": "q1", "question": "Q", "qtype": "mc", "options": ["a", "b"],
             "correct_index": 0, "explanation": "e", "concept_ids": ["c1"], "sources": []},
        ],
    }
    study_v2.save_content(job, content)
    assert study_v2.delete_concept(job, "c1") is True
    loaded = study_v2.load_content(job)
    assert loaded["concepts"] == []
    assert loaded["flashcards"] == []
    assert loaded["quiz"] == []