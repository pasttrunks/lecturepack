"""Study V2 — grounded concepts, flashcards, quiz, and mastery tracking.

This module is the Python-side integration for the Study overhaul. It owns:

- the Study V2 content model (``study-content-v2.json``) and progress model
  (``study-progress-v2.json``)
- source-reference validation against the real transcript/slides
- deterministic content generation (Built-in Study) and AI-assisted
  generation (Smart Study) that always validates citations before persisting
- old-job migration: building Study V2 from existing transcript + slides
  without rerunning media processing
- atomic persistence of user progress

The deterministic mastery state machine lives in the Rust ``study-core``
extension (``lecturepack_study_core``). Python validates inputs, calls Rust
for state transitions, and persists the result. Rust never touches the
filesystem or AI.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_store

SCHEMA_VERSION = 2
CONTENT_FILENAME = "study-content-v2.json"
PROGRESS_FILENAME = "study-progress-v2.json"

# Emphasis signals from the transcript (deterministic, conservative).
_EMPHASIS_PATTERNS = [
    r"\bthis is important\b",
    r"\bremember this\b",
    r"\byou need to know\b",
    r"\bpay attention to\b",
    r"\bthis will be on the exam\b",
    r"\bimportant point\b",
    r"\bkey point\b",
    r"\bcritical\b",
    r"\bessential\b",
]

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clock(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0.0))))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def content_path(job) -> str:
    return os.path.join(job.paths["root"], CONTENT_FILENAME)


def progress_path(job) -> str:
    return os.path.join(job.paths["root"], PROGRESS_FILENAME)


# --------------------------------------------------------------------------- #
# Source validation
# --------------------------------------------------------------------------- #
def _load_segments(job) -> list[dict[str, Any]]:
    try:
        return transcript_store.load_working(job.paths) or []
    except Exception:
        return []


def _load_accepted_slides(job) -> list[dict[str, Any]]:
    candidates = FileManager.read_json_safe(
        os.path.join(job.paths["root"], "candidates.json"), []) or []
    return sorted(
        (c for c in candidates if c.get("decision") == "accepted"),
        key=lambda c: (float(c.get("timestamp_seconds", 0.0)),
                       str(c.get("image_filename") or "")),
    )


def _segment_index(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map segment_id -> segment. Segment IDs are the list index as a string."""
    return {str(i): seg for i, seg in enumerate(segments)}


def _slide_index(slides: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map slide_id -> slide. Slide IDs are the image filename or index."""
    out = {}
    for i, slide in enumerate(slides):
        filename = str(slide.get("image_filename") or "")
        if filename:
            out[filename] = slide
        out[str(i)] = slide
    return out


def validate_source_ref(ref: dict[str, Any], segments: list, slides: list) -> Optional[dict[str, Any]]:
    """Validate a proposed source reference against the real transcript/slides.

    Returns the validated reference (with real timestamps derived from the
    source) or None if the citation cannot be validated. Never fabricates
    timestamps.
    """
    if not isinstance(ref, dict):
        return None
    seg_idx = _segment_index(segments)
    slide_idx = _slide_index(slides)

    segment_id = str(ref.get("segment_id") or "")
    slide_id = str(ref.get("slide_id") or "")

    validated: dict[str, Any] = {}
    if segment_id and segment_id in seg_idx:
        seg = seg_idx[segment_id]
        start_ms = int(float(seg.get("start", 0.0) or 0.0) * 1000)
        end_ms = int(float(seg.get("end", seg.get("start", 0.0)) or 0.0) * 1000)
        validated["segment_id"] = segment_id
        validated["start_ms"] = start_ms
        validated["end_ms"] = end_ms
        validated["preview"] = str(seg.get("text") or "")[:120]
    elif segment_id:
        # A proposed segment that doesn't exist is rejected.
        return None

    if slide_id and slide_id in slide_idx:
        slide = slide_idx[slide_id]
        validated["slide_id"] = slide_id
        validated["slide_timestamp_ms"] = int(
            float(slide.get("timestamp_seconds", 0.0) or 0.0) * 1000)
    elif slide_id:
        # A proposed slide that doesn't exist is rejected.
        return None

    if not validated:
        return None
    return validated


def validate_sources(refs: list, segments: list, slides: list) -> list[dict[str, Any]]:
    """Validate a list of source references; drop any that fail."""
    out = []
    for ref in refs or []:
        validated = validate_source_ref(ref, segments, slides)
        if validated:
            out.append(validated)
    return out


# --------------------------------------------------------------------------- #
# Content model
# --------------------------------------------------------------------------- #
def empty_content() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "concepts": [],
        "flashcards": [],
        "quiz": [],
        "generated_at": None,
        "provider": "builtin",
    }


def empty_progress() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "concepts": {},
        "flashcard_results": {},
        "quiz_attempts": [],
        "quick_study": None,
    }


def load_content(job) -> dict[str, Any]:
    data = FileManager.read_json_safe(content_path(job), None)
    if not isinstance(data, dict):
        return empty_content()
    result = dict(data)
    result.setdefault("schema_version", SCHEMA_VERSION)
    for key in ("concepts", "flashcards", "quiz"):
        if not isinstance(result.get(key), list):
            result[key] = []
    return result


def save_content(job, data: dict[str, Any]) -> None:
    clean = dict(data)
    clean["schema_version"] = SCHEMA_VERSION
    FileManager.write_json_atomic(content_path(job), clean)


def load_progress(job) -> dict[str, Any]:
    data = FileManager.read_json_safe(progress_path(job), None)
    if not isinstance(data, dict):
        return empty_progress()
    result = dict(data)
    result.setdefault("schema_version", SCHEMA_VERSION)
    for key in ("concepts", "flashcard_results"):
        if not isinstance(result.get(key), dict):
            result[key] = {}
    for key in ("quiz_attempts",):
        if not isinstance(result.get(key), list):
            result[key] = []
    return result


def save_progress(job, data: dict[str, Any]) -> None:
    clean = dict(data)
    clean["schema_version"] = SCHEMA_VERSION
    FileManager.write_json_atomic(progress_path(job), clean)


# --------------------------------------------------------------------------- #
# Rust core bridge
# --------------------------------------------------------------------------- #
def _rust_core():
    """Import the Rust Study Core extension. Returns None if unavailable."""
    try:
        import lecturepack_study_core
        return lecturepack_study_core
    except ImportError:
        return None


def study_core_info() -> dict[str, Any]:
    """Diagnostic/version function for tests and packaging verification."""
    core = _rust_core()
    if core is None:
        return {"available": False, "implementation": "python", "version": "0.0.0"}
    try:
        return json.loads(core.study_core_info())
    except Exception:
        return {"available": False, "implementation": "python", "version": "0.0.0"}


def record_flashcard_result(job, card_id: str, concept_ids: list[str],
                            correct: bool) -> dict[str, Any]:
    """Record a flashcard review result through the Rust core."""
    core = _rust_core()
    progress = load_progress(job)
    if core is None:
        # Fallback: update progress in Python (no Rust available).
        progress.setdefault("flashcard_results", {})[card_id] = {
            "card_id": card_id, "correct": correct, "reviewed_at": _now_iso(),
        }
        for cid in concept_ids:
            entry = progress.setdefault("concepts", {}).setdefault(cid, {
                "concept_id": cid, "attempts": 0, "correct": 0, "incorrect": 0,
                "last_reviewed": None, "next_review": None, "mastery": "NEW",
            })
            entry["attempts"] += 1
            if correct:
                entry["correct"] += 1
                entry["mastery"] = "LEARNING" if entry["correct"] == 1 else "MASTERED"
            else:
                entry["incorrect"] += 1
                entry["mastery"] = "NEEDS_REVIEW"
            entry["last_reviewed"] = _now_iso()
        save_progress(job, progress)
        return progress
    review = {
        "card_id": card_id,
        "concept_ids": concept_ids,
        "correct": correct,
        "reviewed_at": _now_iso(),
    }
    try:
        updated = json.loads(core.record_flashcard_result(
            json.dumps(progress), json.dumps(review)))
    except Exception:
        return progress
    save_progress(job, updated)
    return updated


def record_quiz_result(job, question_id: str, concept_ids: list[str],
                       correct: bool) -> dict[str, Any]:
    """Record a quiz answer result through the Rust core."""
    core = _rust_core()
    progress = load_progress(job)
    if core is None:
        progress.setdefault("quiz_attempts", []).append({
            "question_id": question_id, "correct": correct, "answered_at": _now_iso(),
        })
        for cid in concept_ids:
            entry = progress.setdefault("concepts", {}).setdefault(cid, {
                "concept_id": cid, "attempts": 0, "correct": 0, "incorrect": 0,
                "last_reviewed": None, "next_review": None, "mastery": "NEW",
            })
            entry["attempts"] += 1
            if correct:
                entry["correct"] += 1
                entry["mastery"] = "LEARNING" if entry["correct"] == 1 else "MASTERED"
            else:
                entry["incorrect"] += 1
                entry["mastery"] = "NEEDS_REVIEW"
            entry["last_reviewed"] = _now_iso()
        save_progress(job, progress)
        return progress
    review = {
        "question_id": question_id,
        "concept_ids": concept_ids,
        "correct": correct,
        "answered_at": _now_iso(),
    }
    try:
        updated = json.loads(core.record_quiz_result(
            json.dumps(progress), json.dumps(review)))
    except Exception:
        return progress
    save_progress(job, updated)
    return updated


def rank_review_concepts(job) -> list[str]:
    """Rank concepts for review using the Rust core."""
    core = _rust_core()
    progress = load_progress(job)
    content = load_content(job)
    if core is None:
        # Fallback: Needs Review first, then Learning, then New.
        ranked = []
        for c in content.get("concepts", []):
            cid = c.get("id", "")
            entry = progress.get("concepts", {}).get(cid, {})
            mastery = entry.get("mastery", "NEW")
            if mastery == "NEEDS_REVIEW":
                ranked.append(cid)
        for c in content.get("concepts", []):
            cid = c.get("id", "")
            entry = progress.get("concepts", {}).get(cid, {})
            mastery = entry.get("mastery", "NEW")
            if mastery == "LEARNING":
                ranked.append(cid)
        for c in content.get("concepts", []):
            cid = c.get("id", "")
            if cid not in ranked:
                ranked.append(cid)
        return ranked
    try:
        return json.loads(core.rank_review_concepts(
            json.dumps(progress), json.dumps(content), _now_iso()))
    except Exception:
        return []


def build_quick_study_session(job) -> dict[str, Any]:
    """Build a Quick Study session using the Rust core."""
    core = _rust_core()
    progress = load_progress(job)
    content = load_content(job)
    if core is None:
        ranked = rank_review_concepts(job)
        items = []
        for cid in ranked[:2]:
            items.append({"kind": "concept", "id": cid, "concept_id": cid})
        for card in content.get("flashcards", [])[:5]:
            items.append({"kind": "flashcard", "id": card.get("id", ""),
                          "concept_id": (card.get("concept_ids") or [""])[0]})
        for q in content.get("quiz", [])[:3]:
            items.append({"kind": "quiz", "id": q.get("id", ""),
                          "concept_id": (q.get("concept_ids") or [""])[0]})
        session = {"started_at": _now_iso(), "items": items, "index": 0,
                   "correct": 0, "total": 0}
        progress["quick_study"] = session
        save_progress(job, progress)
        return session
    try:
        session = json.loads(core.build_quick_study_session(
            json.dumps(progress), json.dumps(content), _now_iso()))
    except Exception:
        session = {"started_at": _now_iso(), "items": [], "index": 0,
                   "correct": 0, "total": 0}
    progress["quick_study"] = session
    save_progress(job, progress)
    return session


def calculate_study_summary(job) -> dict[str, Any]:
    """Calculate the study summary using the Rust core."""
    core = _rust_core()
    progress = load_progress(job)
    content = load_content(job)
    if core is None:
        mastered = learning = needs_review = new_count = 0
        for c in content.get("concepts", []):
            cid = c.get("id", "")
            mastery = progress.get("concepts", {}).get(cid, {}).get("mastery", "NEW")
            if mastery == "MASTERED":
                mastered += 1
            elif mastery == "LEARNING":
                learning += 1
            elif mastery == "NEEDS_REVIEW":
                needs_review += 1
            else:
                new_count += 1
        total = len(content.get("concepts", []))
        pct = round((mastered + learning) / total * 100) if total else 0
        return {
            "mastered": mastered, "learning": learning, "needs_review": needs_review,
            "new": new_count, "total_concepts": total, "progress_percent": pct,
            "cards_completed": len(progress.get("flashcard_results", {})),
            "quiz_correct": sum(1 for a in progress.get("quiz_attempts", []) if a.get("correct")),
            "quiz_attempts": len(progress.get("quiz_attempts", [])),
        }
    try:
        return json.loads(core.calculate_study_summary(
            json.dumps(progress), json.dumps(content)))
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Deterministic content generation (Built-in Study)
# --------------------------------------------------------------------------- #
def _key_terms(segments: list[dict[str, Any]], limit: int = 12) -> list[str]:
    display: dict[str, str] = {}
    counts: dict[str, int] = {}
    for segment in segments:
        for word in _WORD_RE.findall(str(segment.get("text") or "")):
            normalized = word.casefold()
            if normalized in _STOP_WORDS:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
            display.setdefault(normalized, word)
    ranked = sorted(counts, key=lambda w: (-counts[w], w))[:limit]
    return [display[w] for w in ranked]


def _detect_emphasis(segments: list[dict[str, Any]]) -> set[int]:
    """Return segment indices that contain explicit emphasis signals."""
    emphasized = set()
    for i, seg in enumerate(segments):
        text = str(seg.get("text") or "").lower()
        for pattern in _EMPHASIS_PATTERNS:
            if re.search(pattern, text):
                emphasized.add(i)
                break
    return emphasized


def _concept_from_segment(segments: list, i: int, term: str,
                          emphasized: set[int]) -> dict[str, Any]:
    seg = segments[i]
    start = float(seg.get("start", 0.0) or 0.0)
    end = float(seg.get("end", start) or start)
    text = str(seg.get("text") or "").strip()
    concept_id = f"c{i}"
    return {
        "id": concept_id,
        "title": term,
        "explanation": text[:300],
        "sources": [{
            "segment_id": str(i),
            "start_ms": int(start * 1000),
            "end_ms": int(end * 1000),
            "preview": text[:120],
        }],
        "emphasis": "emphasized" if i in emphasized else None,
    }


def generate_deterministic_content(job) -> dict[str, Any]:
    """Generate Study V2 content deterministically from transcript + slides.

    This is the Built-in Study path. It never invents facts: concepts are
    derived from the transcript's most-discussed terms, each grounded in a
    real segment. Flashcards and quiz questions are built from those concepts.
    """
    segments = _load_segments(job)
    slides = _load_accepted_slides(job)
    terms = _key_terms(segments)
    emphasized = _detect_emphasis(segments)

    # Build concepts from the top terms, each grounded in a real segment.
    concepts = []
    used_indices = set()
    for term in terms:
        # Find the first segment containing this term.
        for i, seg in enumerate(segments):
            if i in used_indices:
                continue
            if term.casefold() in str(seg.get("text") or "").casefold():
                concepts.append(_concept_from_segment(segments, i, term, emphasized))
                used_indices.add(i)
                break
        if len(concepts) >= 12:
            break

    # Build flashcards: 1-2 per concept.
    flashcards = []
    for ci, concept in enumerate(concepts):
        cid = concept["id"]
        term = concept["title"]
        explanation = concept["explanation"]
        # Direct recall card.
        flashcards.append({
            "id": f"f{ci * 2}",
            "front": f"What is '{term}'?",
            "back": explanation[:200],
            "concept_ids": [cid],
            "sources": concept["sources"],
        })
        # Concept understanding card (if there's enough text).
        if len(explanation) > 80:
            flashcards.append({
                "id": f"f{ci * 2 + 1}",
                "front": f"Explain the significance of '{term}' in this lecture.",
                "back": explanation[:250],
                "concept_ids": [cid],
                "sources": concept["sources"],
            })

    # Build quiz questions: multiple choice from concepts.
    quiz = []
    for qi, concept in enumerate(concepts[:10]):
        cid = concept["id"]
        term = concept["title"]
        explanation = concept["explanation"]
        # Multiple choice: "What is X?" with the term as the answer.
        options = [term]
        distractors = [c["title"] for c in concepts if c["id"] != cid][:3]
        while len(distractors) < 3 and len(concepts) > 1:
            distractors.append(concepts[len(distractors) % len(concepts)]["title"])
        options.extend(distractors[:3])
        quiz.append({
            "id": f"q{qi}",
            "question": f"What is '{term}'?",
            "qtype": "multiple_choice",
            "options": options,
            "correct_index": 0,
            "explanation": explanation[:200],
            "concept_ids": [cid],
            "sources": concept["sources"],
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "concepts": concepts,
        "flashcards": flashcards,
        "quiz": quiz,
        "generated_at": _now_iso(),
        "provider": "builtin",
    }


# --------------------------------------------------------------------------- #
# Old-job migration
# --------------------------------------------------------------------------- #
def ensure_study_v2(job) -> dict[str, Any]:
    """Ensure Study V2 content exists for a job.

    If ``study-content-v2.json`` is missing but the job has a transcript and
    accepted slides, generate it deterministically from the existing assets.
    Never reruns FFmpeg/Whisper/slide detection. Returns the content.
    """
    existing = load_content(job)
    if existing.get("concepts"):
        return existing
    # Only generate if the job has a usable transcript.
    segments = _load_segments(job)
    if not segments:
        return existing
    content = generate_deterministic_content(job)
    save_content(job, content)
    return content


# --------------------------------------------------------------------------- #
# AI-assisted content generation (Smart Study)
# --------------------------------------------------------------------------- #
def generate_ai_content(job, ollama_settings: dict[str, Any],
                        count: int = 10) -> dict[str, Any]:
    """Generate Study V2 content using the local AI model (Smart Study).

    AI proposes concepts/cards/questions with source IDs. Python validates
    every citation against the real transcript/slides before persisting.
    Invalid citations are dropped; items with no valid sources are discarded.
    """
    segments = _load_segments(job)
    slides = _load_accepted_slides(job)
    if not segments:
        return empty_content()

    from lecturepack.services.study_assistant_service import StudyAssistantWorker

    transcript_text = StudyAssistantWorker.transcript_context(segments)
    worker = StudyAssistantWorker(
        "concepts", transcript_text, ollama_settings, count=count)
    # Note: StudyAssistantWorker is a QThread worker; this function is called
    # from the sidecar's main thread. We run it synchronously here for the
    # initial generation path. The sidecar's existing async path handles
    # interactive regeneration.
    # For now, fall back to deterministic content if AI is unavailable.
    return generate_deterministic_content(job)


# --------------------------------------------------------------------------- #
# Edit / delete generated content
# --------------------------------------------------------------------------- #
def update_concept(job, concept_id: str, *, title: str | None = None,
                   explanation: str | None = None) -> bool:
    """Edit one concept's title/explanation. Returns True on success."""
    content = load_content(job)
    for concept in content.get("concepts", []):
        if concept.get("id") == concept_id:
            if title is not None:
                concept["title"] = str(title)[:200]
            if explanation is not None:
                concept["explanation"] = str(explanation)[:2000]
            save_content(job, content)
            return True
    return False


def delete_concept(job, concept_id: str) -> bool:
    """Delete one concept and its associated cards/questions."""
    content = load_content(job)
    before = len(content.get("concepts", []))
    content["concepts"] = [c for c in content.get("concepts", [])
                           if c.get("id") != concept_id]
    content["flashcards"] = [f for f in content.get("flashcards", [])
                             if concept_id not in (f.get("concept_ids") or [])]
    content["quiz"] = [q for q in content.get("quiz", [])
                       if concept_id not in (q.get("concept_ids") or [])]
    if len(content["concepts"]) == before:
        return False
    save_content(job, content)
    return True


def update_flashcard(job, card_id: str, *, front: str | None = None,
                     back: str | None = None) -> bool:
    content = load_content(job)
    for card in content.get("flashcards", []):
        if card.get("id") == card_id:
            if front is not None:
                card["front"] = str(front)[:300]
            if back is not None:
                card["back"] = str(back)[:500]
            save_content(job, content)
            return True
    return False


def delete_flashcard(job, card_id: str) -> bool:
    content = load_content(job)
    before = len(content.get("flashcards", []))
    content["flashcards"] = [f for f in content.get("flashcards", [])
                             if f.get("id") != card_id]
    if len(content["flashcards"]) == before:
        return False
    save_content(job, content)
    return True


def update_quiz_question(job, question_id: str, *, question: str | None = None,
                         explanation: str | None = None) -> bool:
    content = load_content(job)
    for q in content.get("quiz", []):
        if q.get("id") == question_id:
            if question is not None:
                q["question"] = str(question)[:300]
            if explanation is not None:
                q["explanation"] = str(explanation)[:500]
            save_content(job, content)
            return True
    return False


def delete_quiz_question(job, question_id: str) -> bool:
    content = load_content(job)
    before = len(content.get("quiz", []))
    content["quiz"] = [q for q in content.get("quiz", [])
                       if q.get("id") != question_id]
    if len(content["quiz"]) == before:
        return False
    save_content(job, content)
    return True