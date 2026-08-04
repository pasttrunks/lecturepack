"""Focused tests for Phase 9 Feature Group 4: study and AI backends."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack import electron_study as es  # noqa: E402
from lecturepack.services import study_presets as sp  # noqa: E402


# ---- study presets ------------------------------------------------------- #
def test_preset_list_ordered():
    presets = sp.preset_list()
    assert [p["key"] for p in presets] == [sp.PRESET_LIGHTWEIGHT, sp.PRESET_BALANCED]


def test_model_for_preset():
    assert sp.model_for_preset(sp.PRESET_LIGHTWEIGHT) == "qwen3:1.7b"
    assert sp.model_for_preset(sp.PRESET_BALANCED) == "qwen3:4b"
    assert sp.model_for_preset("custom", "my-model") == "my-model"


def test_preset_for_model():
    assert sp.preset_for_model("qwen3:4b") == sp.PRESET_BALANCED
    assert sp.preset_for_model("other") == sp.PRESET_CUSTOM
    assert sp.preset_for_model("") == ""


def test_recommend_preset_ram_buckets():
    assert sp.recommend_preset(0)["recommended"] == sp.PRESET_BALANCED
    assert sp.recommend_preset(8)["recommended"] == sp.PRESET_LIGHTWEIGHT
    assert sp.recommend_preset(8)["default_builtin"] is True
    assert sp.recommend_preset(16)["recommended"] == sp.PRESET_BALANCED
    assert sp.recommend_preset(32)["recommended"] == sp.PRESET_BALANCED
    assert sp.recommend_preset(32)["allow_advanced_models"] is True


# ---- built-in answer ----------------------------------------------------- #
def test_builtin_answer_finds_keyword():
    segments = [
        {"start": 0.0, "text": "Welcome to physics lecture one."},
        {"start": 10.0, "text": "Today we discuss quantum mechanics."},
        {"start": 20.0, "text": "Quantum entanglement is fascinating."},
    ]
    answer = es.builtin_answer("What is quantum?", segments)
    assert "quantum" in answer.lower()
    assert "Built-in Study" in answer


def test_builtin_answer_no_match():
    segments = [{"start": 0.0, "text": "Welcome to class."}]
    answer = es.builtin_answer("What is chemistry?", segments)
    assert "couldn't find" in answer.lower()


# ---- fallback quiz / flashcards ------------------------------------------ #
def test_generate_quiz_fallback():
    questions = es.generate_quiz_fallback(["term-a", "term-b", "term-c"], 3,
                                          [{"text": "sentence"}])
    assert len(questions) == 3
    for q in questions:
        assert q["question"]
        assert len(q["options"]) >= 2
        assert q["answer"]


def test_generate_flashcards_fallback():
    cards = es.generate_flashcards_fallback(["term-a", "term-b"], 2, [])
    assert len(cards) == 2
    assert cards[0]["term"] == "term-a"
    assert cards[0]["definition"]


# ---- normalization ------------------------------------------------------- #
def test_normalize_quiz():
    raw = [
        {"question": "Q1", "options": ["a", "b"], "answer": "a"},
        {"question": "Q2", "options": ["c", "d"], "answer": "c"},
        {"question": "Q3", "options": ["e", "f"], "answer": "e"},
    ]
    out = es.normalize_quiz(raw, 2)
    assert len(out) == 2
    assert out[0]["question"] == "Q1"


def test_normalize_quiz_rejects_bad():
    assert es.normalize_quiz("not a list", 5) == []
    assert es.normalize_quiz([{"question": "no options"}], 5) == []


def test_normalize_flashcards():
    raw = [
        {"term": "T1", "definition": "D1"},
        {"term": "T2", "definition": "D2"},
        {"term": "T3", "definition": "D3"},
    ]
    out = es.normalize_flashcards(raw, 2)
    assert len(out) == 2
    assert out[0]["term"] == "T1"


# ---- smart study payload ------------------------------------------------- #
class _FakeConfig:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


def test_smart_study_payload_builtin_when_no_ollama():
    cfg = _FakeConfig({"ollama": {"enabled": False}})
    payload = es.smart_study_payload(cfg, ollama={"available": False}, installed=[])
    assert payload["ready"] is False
    assert payload["provider"] == sp.PROVIDER_BUILTIN
    assert payload["presets"]


def test_smart_study_payload_ready_when_model_installed():
    cfg = _FakeConfig({"ollama": {"enabled": True, "model": "qwen3:4b"},
                       "study_preset": sp.PRESET_BALANCED})
    payload = es.smart_study_payload(cfg, ollama={"available": True},
                                     installed=["qwen3:4b"])
    assert payload["ready"] is True
    assert payload["provider"] == sp.PROVIDER_LOCAL
    assert payload["preset"] == sp.PRESET_BALANCED