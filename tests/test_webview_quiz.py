"""Quiz backend: deterministic no-AI fallback, normalization, and persistence.

The AI path (Ollama) is covered by the existing study-assistant worker tests; here
we exercise the WebView adapter's fallback + save/restore, which must work with no
Ollama at all. Runs against a temp data dir with build_overview monkeypatched.
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
        for n in ("log_line", "quiz_changed", "quiz_status"):
            setattr(self, n, _Signal())


# ------------------------------------------------------- pure fallback logic
_SENTS = [
    "The Ziggurat was a massive terraced temple at the center of the city.",
    "Scribes recorded laws and trade in Cuneiform on clay tablets.",
    "Hammurabi issued one of the earliest written legal codes.",
    "The Euphrates river fed the irrigation canals of the plain.",
    "Babylon grew into the dominant power of the region.",
]
_TERMS = ["Ziggurat", "Cuneiform", "Hammurabi", "Euphrates", "Babylon"]


def test_fallback_quiz_is_grounded_cloze():
    qs = ea._fallback_quiz_questions(_TERMS, 5, _SENTS)
    assert len(qs) == 5
    for q in qs:
        assert q["question"].startswith("Fill in the blank:")
        assert "_____" in q["question"]
        assert 2 <= len(q["options"]) <= 4
        correct = q["options"][q["correct_index"]]
        assert correct in _TERMS
        # the blanked sentence must NOT contain any distractor (answer unambiguous)
        wrong = [o for i, o in enumerate(q["options"]) if i != q["correct_index"]]
        low = q["question"].lower()
        assert all(w.lower() not in low for w in wrong)


def test_fallback_correct_index_varies():
    qs = ea._fallback_quiz_questions(_TERMS, 5, _SENTS)
    assert len({q["correct_index"] for q in qs}) > 1


def test_fallback_drops_stopword_terms():
    qs = ea._fallback_quiz_questions(["one", "see", "it's", "Ziggurat"], 5, _SENTS)
    for q in qs:
        assert q["options"][q["correct_index"]] == "Ziggurat"


def test_fallback_empty_without_terms_or_sentences():
    assert ea._fallback_quiz_questions([], 5, _SENTS) == []
    assert ea._fallback_quiz_questions(_TERMS, 5, []) == []


def test_normalize_quiz_repairs_and_caps():
    raw = [
        {"question": "Q1", "options": ["a", "b", "c"], "correct_index": 9, "explanation": "e"},
        {"question": "", "options": ["a", "b"], "correct_index": 0},          # dropped (no text)
        {"question": "Q3", "options": ["only"], "correct_index": 0},           # dropped (<2 opts)
        {"question": "Q4", "options": ["a", "b"], "correct_index": 1, "explanation": ""},
    ]
    out = ea._normalize_quiz(raw, count=10)
    assert [q["question"] for q in out] == ["Q1", "Q4"]
    assert out[0]["correct_index"] == 2  # clamped into range
    capped = ea._normalize_quiz([raw[0]] * 5, count=2)
    assert len(capped) == 2


# ----------------------------------------------------- adapter generate/persist
@pytest.fixture
def adapter(tmp_path, monkeypatch):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a.current_job = Job(str(tmp_path), video_path="lecture.mp4")  # creates a job dir
    monkeypatch.setattr(study_service, "build_overview",
                        lambda job: {"key_terms": _TERMS})
    # grounded fallback needs a transcript to build cloze questions from
    monkeypatch.setattr(ea.transcript_store, "load_working",
                        lambda paths: [{"text": s} for s in _SENTS])
    return a


def _last(sig):
    return json.loads(sig.emissions[-1])


def test_generate_quiz_fallback_when_ai_off(adapter):
    adapter.config.set("ollama", {})  # AI off
    adapter.generate_quiz(json.dumps({"count": 4}))
    changed = _last(adapter.backend.quiz_changed)
    assert changed["provider"] == "Built-in (no AI)"
    assert len(changed["questions"]) == 4
    assert _last(adapter.backend.quiz_status)["state"] == "ready"
    # persisted in study.json
    stored = study_service.load_study_data(adapter.current_job)["quiz"]
    assert len(stored["questions"]) == 4


def test_generate_quiz_no_job(tmp_path):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a.current_job = None
    a.generate_quiz(json.dumps({"count": 3}))
    assert _last(a.backend.quiz_status)["state"] == "error"


def test_save_and_restore_quiz_session(adapter):
    adapter.config.set("ollama", {})
    adapter.generate_quiz(json.dumps({"count": 3}))
    adapter.backend.quiz_changed.emissions.clear()
    session = {"index": 2, "answers": {"0": 1, "1": 0}, "finished": False}
    adapter.save_quiz_session(json.dumps(session))
    # _emit_stored_quiz replays both questions and the saved session
    adapter._emit_stored_quiz(adapter.current_job)
    replayed = _last(adapter.backend.quiz_changed)
    assert replayed["session"] == session
    assert len(replayed["questions"]) == 3
