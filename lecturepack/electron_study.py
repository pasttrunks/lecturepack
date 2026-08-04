"""Electron study/AI backend operations for the sidecar (Phase 9 FG4).

Pure orchestration around the existing lecturepack study services and the
Ollama/Groq infrastructure clients. No Qt UI. Failure-safe: every operation
returns a structured payload and never raises through to the caller.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from lecturepack.services import study_presets as sp


def _normalize_quiz(questions: Any, count: int) -> list:
    if not isinstance(questions, list):
        return []
    out = []
    for q in questions[:count]:
        if not isinstance(q, dict):
            continue
        q_text = q.get("question") or q.get("q") or ""
        options = q.get("options") or q.get("choices") or []
        answer = q.get("answer") or q.get("correct") or ""
        if q_text and options:
            out.append({"question": q_text, "options": options, "answer": answer})
    return out


def _normalize_flashcards(cards: Any, count: int) -> list:
    if not isinstance(cards, list):
        return []
    out = []
    for c in cards[:count]:
        if not isinstance(c, dict):
            continue
        term = c.get("term") or c.get("front") or c.get("q") or ""
        definition = c.get("definition") or c.get("back") or c.get("a") or ""
        if term and definition:
            out.append({"term": term, "definition": definition})
    return out


_COMMON_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been being this that "
    "these those it its as at by from what which who whom how why when where does do "
    "did can could should would will about into over under than then them they you "
    "your our his her their my me we he she i".split())


def _sentences(segments: list) -> list:
    out = []
    for s in segments or []:
        text = str(s.get("text") or "").strip()
        if text:
            out.append(text)
    return out


def _fallback_quiz_questions(terms: list, count: int, sentences: list) -> list:
    """Deterministic fallback quiz from key terms (Built-in Study)."""
    import random
    rng = random.Random(0)
    questions = []
    pool = [t for t in (terms or []) if t]
    for i in range(count):
        if not pool:
            break
        term = pool[i % len(pool)]
        options = [term]
        distractors = [t for t in pool if t != term][:3]
        while len(distractors) < 3 and len(pool) > 1:
            distractors.append(pool[len(distractors) % len(pool)])
        rng.shuffle(distractors)
        options.extend(distractors[:3])
        questions.append({
            "question": f"What is '{term}'?",
            "options": options,
            "answer": term,
        })
    return questions


def _fallback_flashcards(terms: list, count: int, sentences: list) -> list:
    cards = []
    for i, term in enumerate((terms or [])[:count]):
        cards.append({"term": term, "definition": f"Key term from this lecture: {term}"})
    return cards


def builtin_answer(prompt: str, segments: list) -> str:
    """Extractive, lecture-only answer used when no local AI model is set."""
    terms = [w for w in re.findall(r"[a-z0-9]{3,}", (prompt or "").lower())
             if w not in _COMMON_STOPWORDS]
    scored = []
    for s in segments or []:
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(t) for t in terms) if terms else 0
        if score > 0:
            scored.append((score, float(s.get("start", 0.0) or 0.0), text))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:3]
    if not top:
        return ("Built-in Study couldn't find that in this lecture's transcript. "
                "Try different keywords, or set up Smart Study in Settings for "
                "conversational answers.")
    lines = [f"• [{_fmt_mmss(start)}] {text}" for _score, start, text in top]
    return ("Built-in Study — from the lecture transcript:\n\n"
            + "\n\n".join(lines)
            + "\n\nSet up Smart Study in Settings for conversational, "
              "AI-written answers.")


def _fmt_mmss(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0.0))))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def generate_quiz_fallback(terms: list, count: int, segments: list) -> list:
    return _fallback_quiz_questions(terms, count, _sentences(segments))


def generate_flashcards_fallback(terms: list, count: int, segments: list) -> list:
    return _fallback_flashcards(terms, count, _sentences(segments))


def normalize_quiz(questions: Any, count: int) -> list:
    return _normalize_quiz(questions, count)


def normalize_flashcards(cards: Any, count: int) -> list:
    return _normalize_flashcards(cards, count)


def smart_study_payload(config: Any, ollama: Optional[dict] = None,
                        installed: Optional[list] = None,
                        state: str = "idle", message: str = "",
                        pct: Optional[float] = None) -> dict:
    """Build a full Smart Study snapshot payload."""
    o = dict(config.get("ollama", {}) or {}) if config else {}
    model = o.get("model", "")
    ram = sp.usable_ram_gb()
    installed = installed or []
    ready = bool(o.get("enabled") and model and model in installed
                 and ollama and ollama.get("available"))
    return {
        "state": state,
        "message": message,
        "percent": pct,
        "ram_gb": ram,
        "recommendation": sp.recommend_preset(ram),
        "presets": sp.preset_list(),
        "preset": _study_preset(config),
        "model": model,
        "enabled": bool(o.get("enabled")),
        "ready": ready,
        "smart_study_ready": bool(config.get("smart_study_ready", False)) if config else False,
        "ollama": ollama or {"available": False},
        "installed_models": installed,
        "provider": sp.PROVIDER_LOCAL if ready else sp.PROVIDER_BUILTIN,
    }


def _study_preset(config: Any) -> str:
    stored = config.get("study_preset", "") if config else ""
    if stored in (sp.PRESET_LIGHTWEIGHT, sp.PRESET_BALANCED, sp.PRESET_CUSTOM):
        return stored
    o = dict(config.get("ollama", {}) or {}) if config else {}
    return sp.preset_for_model(o.get("model", ""))