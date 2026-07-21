"""Flashcard backend: deterministic fallback, normalization, persistence.

Mirrors the quiz backend tests. AI path is covered by the study-assistant worker
tests; here we exercise the WebView adapter fallback + save/restore with no Ollama.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402
from lecturepack.services import study_service  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    def __init__(self):
        for n in ("log_line", "flashcards_changed", "flashcards_status"):
            setattr(self, n, _Signal())


def _last(sig):
    return json.loads(sig.emissions[-1])


# --------------------------------------------------------- pure logic
_SENTS = [
    "The Ziggurat was a massive terraced temple at the center of the city.",
    "Scribes recorded laws and trade in Cuneiform on clay tablets.",
    "Hammurabi issued one of the earliest written legal codes.",
    "The Euphrates river fed the irrigation canals of the plain.",
]
_TERMS = ["Ziggurat", "Cuneiform", "Hammurabi", "Euphrates"]


def test_fallback_flashcards_grounded_in_transcript():
    cards = ea._fallback_flashcards(_TERMS, 4, _SENTS)
    assert len(cards) == 4
    assert {c["term"] for c in cards} == set(_TERMS)
    for c in cards:
        # the definition is the actual lecture sentence mentioning the term
        assert c["term"].lower() in c["definition"].lower()


def test_fallback_flashcards_empty():
    assert ea._fallback_flashcards([], 5, _SENTS) == []
    assert ea._fallback_flashcards(_TERMS, 5, []) == []  # nothing to ground on
    # junk stopword terms are dropped
    assert ea._fallback_flashcards(["one", "see"], 5, _SENTS) == []


def test_normalize_flashcards_aliases_and_cap():
    raw = [
        {"front": "T1", "back": "D1"},
        {"q": "T2", "a": "D2"},
        {"term": "T3"},                 # dropped (no definition)
        {"term": "T4", "definition": "D4"},
    ]
    out = ea._normalize_flashcards(raw, count=10)
    assert [c["term"] for c in out] == ["T1", "T2", "T4"]
    assert out[0] == {"term": "T1", "definition": "D1"}
    assert len(ea._normalize_flashcards([{"term": "x", "definition": "y"}] * 5, count=2)) == 2


# ------------------------------------------------------- adapter generate/persist
@pytest.fixture
def adapter(tmp_path, monkeypatch):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.config.set("ollama", {})
    a.backend = _FakeBackend()
    a.current_job = Job(str(tmp_path), video_path="lecture.mp4")
    monkeypatch.setattr(study_service, "build_overview",
                        lambda job: {"key_terms": _TERMS})
    monkeypatch.setattr(ea.transcript_store, "load_working",
                        lambda paths: [{"text": s} for s in _SENTS])
    return a


def test_generate_flashcards_fallback_when_ai_off(adapter):
    adapter.generate_flashcards(json.dumps({"count": 4}))
    changed = _last(adapter.backend.flashcards_changed)
    assert changed["provider"] == "Built-in Study"
    assert len(changed["cards"]) == 4
    assert _last(adapter.backend.flashcards_status)["state"] == "ready"
    stored = study_service.load_study_data(adapter.current_job)["flashcards"]
    assert len(stored["cards"]) == 4


def test_generate_flashcards_no_job(tmp_path):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a.current_job = None
    a.generate_flashcards(json.dumps({"count": 3}))
    assert _last(a.backend.flashcards_status)["state"] == "error"


def test_save_and_restore_flashcard_session(adapter):
    adapter.generate_flashcards(json.dumps({"count": 3}))
    adapter.backend.flashcards_changed.emissions.clear()
    session = {"index": 1, "known": {"0": 1}, "unsure": {"2": 1}, "bookmarks": {}, "order": [0, 1, 2]}
    adapter.save_flashcard_session(json.dumps(session))
    adapter._emit_stored_flashcards(adapter.current_job)
    replayed = _last(adapter.backend.flashcards_changed)
    assert replayed["session"] == session
    assert len(replayed["cards"]) == 3
