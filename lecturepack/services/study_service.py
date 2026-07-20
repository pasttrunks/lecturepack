"""Persistent user study data and deterministic Study-page summaries.

``study.json`` is deliberately separate from source-derived candidates and
transcript layers.  This module is the only writer for bookmarks, short notes,
and the per-job resume position; overview content is derived on demand.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
import re
from typing import Any

from lecturepack.constants import STAGE_TRANSCRIBE
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_formats as tf
from lecturepack.services import transcript_store


SCHEMA_VERSION = 1
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been",
    "before", "being", "but", "can", "could", "did", "does", "each",
    "for", "from", "had", "has", "have", "here", "how", "into", "its",
    "just", "more", "most", "not", "now", "only", "other", "our", "out",
    "over", "said", "same", "should", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "too", "under", "very", "was", "were", "what",
    "when", "where", "which", "while", "who", "will", "with", "would",
    "you", "your",
}


def study_path(job) -> str:
    return os.path.join(job.paths["root"], "study.json")


def empty_study_data() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "bookmarked_slides": {},
        "bookmarked_sections": {},
        "last_position": {},
        "chat_messages": [],
        "quiz": {},
        "flashcards": {},
    }


def load_study_data(job) -> dict[str, Any]:
    data = FileManager.read_json_safe(study_path(job), {}) or {}
    if not isinstance(data, dict):
        data = {}
    result = dict(data)
    result["schema_version"] = SCHEMA_VERSION
    for key in ("bookmarked_slides", "bookmarked_sections", "last_position"):
        if not isinstance(result.get(key), dict):
            result[key] = {}
    if not isinstance(result.get("chat_messages"), list):
        result["chat_messages"] = []
    for key in ("quiz", "flashcards"):
        if not isinstance(result.get(key), dict):
            result[key] = {}
    return result


def save_study_data(job, data: dict[str, Any]) -> None:
    clean = dict(data)
    clean["schema_version"] = SCHEMA_VERSION
    FileManager.write_json_atomic(study_path(job), clean)


def _updated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def slide_key(candidate: dict[str, Any]) -> str:
    filename = str(candidate.get("image_filename") or "").strip()
    if filename:
        return filename
    return f"time:{float(candidate.get('timestamp_seconds', 0.0)):.3f}"


def section_key(section: dict[str, Any]) -> str:
    index = section.get("index", section.get("slide_index", "?"))
    return f"{index}:{float(section.get('start', 0.0)):.3f}"


def get_slide_entry(job, candidate: dict[str, Any]) -> dict[str, Any]:
    return dict(load_study_data(job)["bookmarked_slides"].get(slide_key(candidate), {}))


def set_slide_study(job, candidate: dict[str, Any], *, bookmarked: bool,
                    note: str = "") -> dict[str, Any]:
    data = load_study_data(job)
    entries = data["bookmarked_slides"]
    key = slide_key(candidate)
    note = (note or "").strip()[:500]
    if bookmarked or note:
        entries[key] = {
            "image_filename": str(candidate.get("image_filename") or ""),
            "timestamp_seconds": float(candidate.get("timestamp_seconds", 0.0)),
            "timestamp_formatted": str(candidate.get("timestamp_formatted") or ""),
            "bookmarked": bool(bookmarked),
            "note": note,
            "updated_at": _updated_at(),
        }
    else:
        entries.pop(key, None)
    save_study_data(job, data)
    return dict(entries.get(key, {}))


def set_section_bookmark(job, section: dict[str, Any], bookmarked: bool) -> None:
    data = load_study_data(job)
    entries = data["bookmarked_sections"]
    key = section_key(section)
    if bookmarked:
        entries[key] = {
            "index": section.get("index"),
            "slide_index": section.get("slide_index"),
            "start": float(section.get("start", 0.0)),
            "heading": str(section.get("heading") or "Untitled section"),
            "updated_at": _updated_at(),
        }
    else:
        entries.pop(key, None)
    save_study_data(job, data)


def save_position(job, *, page: str, timestamp_seconds: float = 0.0,
                  section: dict[str, Any] | None = None) -> None:
    data = load_study_data(job)
    pos = {
        "page": str(page),
        "timestamp_seconds": max(0.0, float(timestamp_seconds)),
        "updated_at": _updated_at(),
    }
    if section is not None:
        pos["section_key"] = section_key(section)
    data["last_position"] = pos
    save_study_data(job, data)


def load_chat_messages(job) -> list[dict[str, Any]]:
    return list(load_study_data(job)["chat_messages"])


def append_chat_message(job, role: str, text: str) -> None:
    data = load_study_data(job)
    data["chat_messages"].append({
        "role": str(role), "text": str(text), "updated_at": _updated_at(),
    })
    save_study_data(job, data)


def clear_chat_messages(job) -> None:
    data = load_study_data(job)
    data["chat_messages"] = []
    save_study_data(job, data)


def load_quiz(job) -> dict[str, Any]:
    return dict(load_study_data(job)["quiz"])


def save_quiz(job, questions: list[dict[str, Any]]) -> None:
    data = load_study_data(job)
    data["quiz"] = {"questions": questions, "updated_at": _updated_at()}
    save_study_data(job, data)


def load_flashcards(job) -> dict[str, Any]:
    return dict(load_study_data(job)["flashcards"])


def save_flashcards(job, cards: list[dict[str, Any]]) -> None:
    data = load_study_data(job)
    data["flashcards"] = {"cards": cards, "updated_at": _updated_at()}
    save_study_data(job, data)


def load_sections(job) -> list[dict[str, Any]]:
    aligned = FileManager.read_json_safe(
        os.path.join(job.paths["transcript"], "aligned.json"), []) or []
    try:
        sections = tf.build_sections(aligned)
    except Exception:
        sections = []
    overrides = FileManager.read_json_safe(
        os.path.join(job.paths["transcript"], "section_overrides.json"), {}) or {}
    for section in sections:
        override = overrides.get(str(section.get("index")))
        if isinstance(override, dict):
            section["heading"] = override.get("heading", section["heading"])
            section["heading_source"] = override.get("source", "user")
        else:
            section["heading_source"] = "deterministic"
    return sections


def _key_terms(segments: list[dict[str, Any]], limit: int = 10) -> list[str]:
    display: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for segment in segments:
        for word in _WORD_RE.findall(str(segment.get("text") or "")):
            normalized = word.casefold()
            if normalized in _STOP_WORDS:
                continue
            counts[normalized] += 1
            display.setdefault(normalized, word)
    ranked = sorted(counts, key=lambda word: (-counts[word], word))[:limit]
    return [display[word] for word in ranked]


def _summary(segments: list[dict[str, Any]]) -> str:
    text = " ".join(str(s.get("text") or "").strip() for s in segments).strip()
    if not text:
        return "No transcript is available yet."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = " ".join(sentences[:3]).strip()
    return result[:600] + ("…" if len(result) > 600 else "")


def build_overview(job) -> dict[str, Any]:
    segments = transcript_store.load_working(job.paths)
    sections = load_sections(job)
    candidates = FileManager.read_json_safe(
        os.path.join(job.paths["root"], "candidates.json"), []) or []
    accepted = sorted(
        (c for c in candidates if c.get("decision") == "accepted"),
        key=lambda c: (float(c.get("timestamp_seconds", 0.0)),
                       str(c.get("image_filename") or "")),
    )
    confidence = transcript_store.load_segment_confidence(job.paths)
    needs_review = sum(1 for value in confidence.values()
                       if value is not None and value < 0.6)
    data = load_study_data(job)
    backend = (job.state.get("stages", {}).get(STAGE_TRANSCRIBE, {})
               .get("backend_used") or "Unknown")
    return {
        "title": job.manifest.get("title", "Untitled lecture"),
        "duration_seconds": float(job.source.get("duration", 0.0) or 0.0),
        "product_mode": job.get_product_mode(),
        "backend": backend,
        "summary": _summary(segments),
        "summary_source": "deterministic transcript extract",
        "key_terms": _key_terms(segments),
        "sections": sections,
        "accepted_slides": accepted,
        "accepted_slide_count": len(accepted),
        "transcript_segment_count": len(segments),
        "needs_review_count": needs_review,
        "bookmarked_slides": data["bookmarked_slides"],
        "bookmarked_sections": data["bookmarked_sections"],
        "last_position": data["last_position"],
    }


def export_payload(job) -> dict[str, Any]:
    """JSON-safe export with explicit provenance labels."""
    overview = build_overview(job)
    return {
        "schema_version": SCHEMA_VERSION,
        "title": overview["title"],
        "source_derived": {
            "summary": overview["summary"],
            "summary_source": overview["summary_source"],
            "key_terms": overview["key_terms"],
        },
        "user_authored": {
            "bookmarked_slides": overview["bookmarked_slides"],
            "bookmarked_sections": overview["bookmarked_sections"],
            "last_position": overview["last_position"],
        },
    }
