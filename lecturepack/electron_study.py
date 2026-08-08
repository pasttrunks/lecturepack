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
    "your our his her their my me we he she i explain simply simple lecture key "
    "concepts quiz tell summarize summary overview please".split())


def _prompt_terms(prompt: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]{3,}", (prompt or "").lower())
            if word not in _COMMON_STOPWORDS]


def _is_overview_prompt(prompt: str) -> bool:
    normalized = " ".join(re.findall(r"[a-z0-9]+", (prompt or "").lower()))
    return ("key concepts" in normalized or "summary" in normalized
            or "overview" in normalized
            or ("explain" in normalized and "lecture" in normalized))


def _is_quiz_prompt(prompt: str) -> bool:
    return bool(re.search(r"\bquiz\b", (prompt or "").lower()))


_OVERVIEW_HINTS = (
    "define", "definition", "study", "consists", "includes", "important",
    "fundamental", "significant", "called", "focus", "today",
)


def _overview_matches(segments: list, limit: int = 4) -> list[tuple]:
    scored = []
    for index, segment in enumerate(segments or []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(hint) for hint in _OVERVIEW_HINTS)
        if index < 8 and re.search(r"\b(archaeolog|egypt|history|science|course)\w*\b", low):
            score += 1
        if score <= 0:
            continue
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        scored.append((score, start, index, end, text))
    early = [item for item in scored if 25.0 <= item[1] <= 180.0]
    if len(early) < min(3, max(1, limit)):
        early = [item for item in scored if item[1] <= 180.0]
    if len(early) >= min(3, max(1, limit)):
        scored = early
    scored.sort(key=lambda item: (item[1], -item[0]))
    return scored[:max(1, limit)]


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


def _legacy_builtin_answer(prompt: str, segments: list) -> str:
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


def _legacy_builtin_sources(prompt: str, segments: list, limit: int = 3) -> list[dict[str, Any]]:
    """Return real transcript anchors used by the extractive Study answer.

    The renderer turns these into timestamp buttons.  IDs and timestamps are
    derived from the loaded transcript only; an unmatched question returns no
    citation instead of inventing one.
    """
    terms = [w for w in re.findall(r"[a-z0-9]{3,}", (prompt or "").lower())
             if w not in _COMMON_STOPWORDS]
    scored = []
    for index, segment in enumerate(segments or []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(term) for term in terms) if terms else 0
        if score <= 0:
            continue
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        scored.append((score, start, index, end, text))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{
        "segment_id": str(index),
        "start_ms": int(start * 1000),
        "end_ms": int(end * 1000),
        "preview": text[:120],
    } for _score, start, index, end, text in scored[:max(1, limit)]]


def builtin_answer(prompt: str, segments: list,
                   content: Optional[dict] = None) -> str:
    """Return a grounded answer without pretending transcript excerpts are AI prose."""
    terms = _prompt_terms(prompt)
    if _is_quiz_prompt(prompt):
        return "The quiz is ready for this lecture. Open the Quiz tab to test yourself."
    if _is_overview_prompt(prompt) and content:
        concepts = [item for item in content.get("concepts", [])
                    if isinstance(item, dict) and item.get("title")
                    and item.get("explanation")][:4]
        if concepts:
            lines = [f"- {item['title']}: {item['explanation']}" for item in concepts]
            return "Built-in Study - key ideas from this lecture:\n\n" + "\n\n".join(lines)
    if _is_overview_prompt(prompt):
        overview = _overview_matches(segments, 3)
        if overview:
            lines = [f"- [{_fmt_mmss(start)}] {text}" for _score, start, _index, _end, text in overview]
            return "Built-in Study - key ideas from the lecture transcript:\n\n" + "\n\n".join(lines)

    scored = []
    for segment in segments or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(term) for term in terms) if terms else 0
        if score > 0:
            scored.append((score, float(segment.get("start", 0.0) or 0.0), text))
    scored.sort(key=lambda item: (-item[0], item[1]))
    top = scored[:3]
    if not top:
        return ("Built-in Study couldn't find that in this lecture's transcript. "
                "Try asking about a specific lecture term.")
    lines = [f"- [{_fmt_mmss(start)}] {text}" for _score, start, text in top]
    return "Built-in Study - relevant transcript excerpts:\n\n" + "\n\n".join(lines)


def builtin_sources(prompt: str, segments: list, limit: int = 3,
                    content: Optional[dict] = None) -> list[dict[str, Any]]:
    """Return real transcript anchors for a Study Ask answer."""
    terms = _prompt_terms(prompt)
    if _is_overview_prompt(prompt) and content:
        by_id = {str(index): segment for index, segment in enumerate(segments or [])}
        refs = []
        seen = set()
        for concept in content.get("concepts", []):
            if not isinstance(concept, dict):
                continue
            for source in concept.get("sources", []) or []:
                if not isinstance(source, dict) or source.get("segment_id") is None:
                    continue
                segment_id = str(source["segment_id"])
                if segment_id in seen or segment_id not in by_id:
                    continue
                segment = by_id[segment_id]
                start_ms = source.get("start_ms")
                if start_ms is None:
                    start_ms = float(segment.get("start", 0.0) or 0.0) * 1000
                end_ms = source.get("end_ms")
                if end_ms is None:
                    end_ms = float(segment.get("end", float(start_ms) / 1000) or float(start_ms) / 1000) * 1000
                refs.append({
                    "segment_id": segment_id,
                    "start_ms": int(start_ms),
                    "end_ms": int(end_ms),
                    "preview": source.get("preview") or str(segment.get("text") or "")[:120],
                })
                seen.add(segment_id)
                if len(refs) >= max(1, limit):
                    return refs
        if refs:
            return refs

    if _is_overview_prompt(prompt):
        return [{
            "segment_id": str(index),
            "start_ms": int(start * 1000),
            "end_ms": int(end * 1000),
            "preview": text[:120],
        } for _score, start, index, end, text in _overview_matches(segments, limit)]

    scored = []
    for index, segment in enumerate(segments or []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(term) for term in terms) if terms else 0
        if score <= 0:
            continue
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        scored.append((score, start, index, end, text))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{
        "segment_id": str(index),
        "start_ms": int(start * 1000),
        "end_ms": int(end * 1000),
        "preview": text[:120],
    } for _score, start, index, end, text in scored[:max(1, limit)]]


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
