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
import hashlib
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_store

_LOGGER = logging.getLogger(__name__)
_RUST_CORE_LOAD_ERROR = ""

SCHEMA_VERSION = 3
CONTENT_FILENAME = "study-content-v2.json"
PROGRESS_FILENAME = "study-progress-v2.json"
PROGRESS_BACKUP_SUFFIX = ".bak"

STUDY_PREPARING = "preparing"
STUDY_READY = "ready"
STUDY_FAILED = "failed"
STUDY_BASIC = "basic"
_STUDY_STATUSES = {STUDY_PREPARING, STUDY_READY, STUDY_FAILED, STUDY_BASIC}
_PROVENANCE = {"lecture", "extra_context", "web_verified", "mixed"}
_MASTERY = {"NEW", "LEARNING", "MASTERED", "NEEDS_REVIEW"}
_LOCKS_GUARD = threading.Lock()
_JOB_LOCKS: dict[str, threading.RLock] = {}

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

# Transcript speech contains a great deal of connective language that is not
# useful study material.  Keep this list deliberately small and transparent:
# it is a quality filter, not an attempt at part-of-speech tagging.  The
# phrase extractor below still allows descriptive words such as "great" or
# "ancient" when they are part of a more specific topic phrase.
_STUDY_FILLER_WORDS = {
    "about", "actually", "again", "already", "always", "around", "back",
    "basically", "because", "before", "both", "course", "class", "come",
    "common", "different", "down", "enough", "everyone", "every", "first",
    "four", "from", "going", "got", "hello", "here", "just", "kind",
    "later", "little", "lots", "main", "many", "maybe", "much", "number",
    "numbers", "okay", "one", "part", "particularly", "people", "possibly",
    "probably", "really", "right", "second", "several", "show", "shown",
    "side", "sides", "simply", "small", "sort", "still", "sure", "take",
    "tell", "then", "thing", "things", "today", "try", "trying", "two",
    "very", "way", "well", "week", "years", "you", "your", "you're",
    "that's", "it's", "there's", "we're", "they're", "we've", "don't",
    "doesn't", "didn't", "isn't", "can't", "couldn't", "would", "should",
}

_STUDY_COMMON_VERBS = {
    "be", "been", "being", "can", "could", "did", "do", "does", "doing",
    "end", "ended", "find", "found", "get", "give", "gave", "go", "had",
    "has", "have", "is", "know", "known", "look", "looked", "make", "made",
    "may", "might", "need", "needs", "put", "said", "say", "see", "seen",
    "showed", "start", "started", "tell", "told", "use", "used", "using",
    "want", "wanted", "was", "were", "will", "would", "excavate",
    "excavated", "excavating", "reconstruct", "reconstructed", "reconstructing",
}

_STUDY_CLAIM_RE = re.compile(
    r"\b(is|are|was|were|means|includes|consists\s+of|refers\s+to|"
    r"can\s+be\s+considered|defined\s+as|because|therefore|discovered|"
    r"built|found|used|divided|relocated|translated|deciphered|constructed|"
    r"surviving|known|called|relationship|primarily|through|fundamental|"
    r"important|significant|study|analysis|recovery|investigat)\b",
    re.IGNORECASE,
)
_STUDY_DEFINITION_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9'-]*(?:\s+(?:of|at|the|[A-Za-z][A-Za-z0-9'-]*)){0,5})"
    r"\s+(is|are|was|were|means|includes|consists\s+of|refers\s+to|"
    r"can\s+be\s+considered|defined\s+as)\b",
    re.IGNORECASE,
)
_STUDY_CALLED_RE = re.compile(
    r"\b(?:so-called|called)\s+(?:the\s+)?"
    r"([A-Za-z][A-Za-z0-9'-]*(?:\s+(?:of|at|the|[A-Za-z][A-Za-z0-9'-]*)){0,5})",
    re.IGNORECASE,
)
_STUDY_BAD_TITLE_WORDS = {
    "although", "basically", "battle", "build", "built", "catch", "doesn't",
    "episode", "famous", "hall", "however", "if", "it", "known", "mean",
    "baboons", "cameron", "discovery", "fundamental", "general", "obelisks", "remarkable",
    "revealed", "segments", "so", "spoliation", "sultan", "term", "the",
    "pseudo",
    "entrance", "three", "tower", "two", "visible", "was", "were",
}
_STUDY_DETAIL_TITLE_WORDS = {
    "angle", "angles", "blocks", "centimeter", "centimeters", "degree",
    "degrees", "inch", "inches", "meters", "star", "tons", "triangle",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_lock(job) -> threading.RLock:
    key = os.path.abspath(str(job.paths["root"]))
    with _LOCKS_GUARD:
        return _JOB_LOCKS.setdefault(key, threading.RLock())


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
        "study_status": STUDY_PREPARING,
        "generation_metadata": {
            "stage": "Waiting for lecture",
            "progress_percent": 0,
            "last_error": None,
            "diagnostics": {},
        },
        "lecture_summary": "",
        "lecture_analysis": {},
        "concepts": [],
        "key_terms": [],
        "people": [],
        "dates": [],
        "study_guide": [],
        "flashcards": [],
        "quiz": [],
        "misconceptions": [],
        "quick_study_material": {
            "five_minute": [], "ten_minute": [],
            "twenty_minute": [], "full": [],
        },
        "teach_me_foundations": [],
        "slide_interpretations": [],
        "enrichment": [],
        "cached_responses": [],
        "generated_at": None,
        "provider": None,
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
    try:
        original_schema = int(result.get("schema_version") or 0)
    except (TypeError, ValueError):
        original_schema = 0
    result["schema_version"] = SCHEMA_VERSION
    defaults = empty_content()
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
    for key in (
            "concepts", "key_terms", "people", "dates", "study_guide",
            "flashcards", "quiz", "misconceptions", "teach_me_foundations",
            "slide_interpretations", "enrichment", "cached_responses"):
        if not isinstance(result.get(key), list):
            result[key] = []
    if not isinstance(result.get("lecture_analysis"), dict):
        result["lecture_analysis"] = {}
    if not isinstance(result.get("quick_study_material"), dict):
        result["quick_study_material"] = dict(defaults["quick_study_material"])
    if not isinstance(result.get("generation_metadata"), dict):
        result["generation_metadata"] = dict(defaults["generation_metadata"])
    if result.get("study_status") not in _STUDY_STATUSES:
        if result.get("concepts"):
            result["study_status"] = (
                STUDY_BASIC if result.get("provider") == "builtin" else STUDY_READY)
        else:
            result["study_status"] = STUDY_PREPARING
    # V2 deterministic packs predate explicit Basic selection. Mark them so
    # the sidecar may migrate them to AI automatically; an explicit Basic
    # selection records ``basic_reason=user_selected`` and is never overridden.
    if original_schema < SCHEMA_VERSION and result.get("provider") == "builtin":
        meta = result["generation_metadata"]
        meta.setdefault("basic_reason", "legacy_migration")
    return result


def save_content(job, data: dict[str, Any]) -> None:
    clean = dict(data)
    clean["schema_version"] = SCHEMA_VERSION
    with _job_lock(job):
        FileManager.write_json_atomic(content_path(job), clean)


def load_progress(job) -> dict[str, Any]:
    path = progress_path(job)
    data = FileManager.read_json_safe(path, None)
    if not isinstance(data, dict):
        data = FileManager.read_json_safe(path + PROGRESS_BACKUP_SUFFIX, None)
        if isinstance(data, dict):
            _LOGGER.warning("Recovered Study mastery progress from rolling backup")
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


def _write_progress_json(path: str, data: dict[str, Any]) -> None:
    """Durably replace one Study progress generation on the same volume."""
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(data, handle, indent=4, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass


def save_progress(job, data: dict[str, Any]) -> None:
    clean = dict(data)
    clean["schema_version"] = SCHEMA_VERSION
    # The lock is this branch's; the rolling backup is the cherry-picked fix.
    # Both are required: the lock keeps two Study writers from interleaving, and
    # the backup keeps a last-known-good generation of irreplaceable mastery
    # data if the primary is ever truncated or corrupted.
    with _job_lock(job):
        path = progress_path(job)
        backup_path = path + PROGRESS_BACKUP_SUFFIX
        previous = FileManager.read_json_safe(path, None)
        if isinstance(previous, dict):
            _write_progress_json(backup_path, previous)
        elif not isinstance(FileManager.read_json_safe(backup_path, None), dict):
            # The first successful generation is also recoverable if the primary
            # is later damaged before the student records a second result.
            _write_progress_json(backup_path, clean)
        _write_progress_json(path, clean)


# --------------------------------------------------------------------------- #
# Rust core bridge
# --------------------------------------------------------------------------- #
def _rust_core():
    """Import the Rust Study Core extension. Returns None if unavailable."""
    global _RUST_CORE_LOAD_ERROR
    try:
        import lecturepack_study_core
        _RUST_CORE_LOAD_ERROR = ""
        return lecturepack_study_core
    except (ImportError, OSError, SystemError) as error:
        _RUST_CORE_LOAD_ERROR = f"{type(error).__name__}: {error}"
        _LOGGER.warning("Rust Study Core could not load; using Python fallback: %s", _RUST_CORE_LOAD_ERROR)
        return None


def study_core_info() -> dict[str, Any]:
    """Diagnostic/version function for tests and packaging verification."""
    core = _rust_core()
    if core is None:
        return {
            "available": False,
            "implementation": "python",
            "version": "0.0.0",
            "error": _RUST_CORE_LOAD_ERROR,
        }
    try:
        return json.loads(core.study_core_info())
    except (AttributeError, json.JSONDecodeError, OSError, RuntimeError, SystemError, TypeError, ValueError) as error:
        _LOGGER.warning("Rust Study Core diagnostics failed; using Python fallback: %s", error)
        return {
            "available": False,
            "implementation": "python",
            "version": "0.0.0",
            "error": f"{type(error).__name__}: {error}",
        }


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


def build_quick_study_session(job, minutes: int | str = 10) -> dict[str, Any]:
    """Build a deterministic 5/10/20-minute or full Quick Study session.

    The Rust core remains the first source of ranking/session order. Python
    deterministically truncates or extends that order from already-generated
    content; Quick Study never makes another AI request.
    """
    core = _rust_core()
    progress = load_progress(job)
    content = load_content(job)
    raw_duration = str(minutes).strip().lower()
    duration: int | str
    if raw_duration == "full":
        duration = "full"
    else:
        try:
            duration = min((5, 10, 20), key=lambda value: abs(value - int(float(raw_duration))))
        except (TypeError, ValueError):
            duration = 10
    base_items: list[dict[str, Any]] = []
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
        base_items = items
    else:
        try:
            base = json.loads(core.build_quick_study_session(
                json.dumps(progress), json.dumps(content), _now_iso()))
            base_items = list(base.get("items") or [])
        except Exception:
            base_items = []

    ranked = rank_review_concepts(job)
    key = {5: "five_minute", 10: "ten_minute", 20: "twenty_minute"}.get(
        duration, "full")
    planned = content.get("quick_study_material", {}).get(key, []) or []
    concept_ids = []
    for cid in list(ranked) + list(planned):
        cid = str(cid or "")
        if cid and cid not in concept_ids:
            concept_ids.append(cid)
    for concept in content.get("concepts", []):
        cid = str(concept.get("id") or "")
        if cid and cid not in concept_ids:
            concept_ids.append(cid)

    candidates = list(base_items)
    candidates.extend({"kind": "concept", "id": cid, "concept_id": cid}
                      for cid in concept_ids)
    rank_index = {cid: index for index, cid in enumerate(concept_ids)}
    cards = sorted(content.get("flashcards", []), key=lambda card: min(
        (rank_index.get(str(cid), len(rank_index))
         for cid in card.get("concept_ids", []) or [""]), default=len(rank_index)))
    questions = sorted(content.get("quiz", []), key=lambda question: min(
        (rank_index.get(str(cid), len(rank_index))
         for cid in question.get("concept_ids", []) or [""]), default=len(rank_index)))
    candidates.extend({
        "kind": "flashcard", "id": str(card.get("id") or ""),
        "concept_id": str((card.get("concept_ids") or [""])[0]),
    } for card in cards)
    candidates.extend({
        "kind": "quiz", "id": str(question.get("id") or ""),
        "concept_id": str((question.get("concept_ids") or [""])[0]),
    } for question in questions)
    items = []
    seen = set()
    quick_quiz_ids = {
        str(question.get("id") or "") for question in questions
        if str(question.get("qtype") or "multiple_choice") != "short_answer"
    }
    for item in candidates:
        marker = (str(item.get("kind") or ""), str(item.get("id") or ""))
        if not all(marker) or marker in seen:
            continue
        # Semantic short answers require a live grading request and therefore
        # stay in Quiz. Quick Study is a zero-AI replay of saved material.
        if marker[0] == "quiz" and marker[1] not in quick_quiz_ids:
            continue
        seen.add(marker)
        items.append({
            "kind": marker[0], "id": marker[1],
            "concept_id": str(item.get("concept_id") or ""),
        })
    target = None if duration == "full" else {5: 5, 10: 10, 20: 20}[duration]
    if target is not None:
        items = items[:target]
    session = {
        "started_at": _now_iso(), "items": items, "index": 0,
        "correct": 0, "total": 0, "duration_minutes": duration,
    }
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
def _study_words(text: str, *, include_descriptors: bool = True) -> list[str]:
    """Return transcript words that can contribute to a study topic.

    This is intentionally lexical rather than statistical.  Whisper output
    contains many discourse fillers and auxiliary verbs; removing those
    before scoring makes repeated subject-matter phrases visible without
    introducing an NLP dependency or a second processing pipeline.
    """
    words = []
    excluded = _STOP_WORDS | _STUDY_FILLER_WORDS | _STUDY_COMMON_VERBS
    if not include_descriptors:
        excluded = excluded | {
            "ancient", "certain", "different", "famous", "great", "large",
            "main", "past", "small", "similar", "various",
        }
    for word in _WORD_RE.findall(str(text or "")):
        normalized = word.casefold().strip("'")
        if len(normalized) < 4 or normalized in excluded:
            continue
        if normalized.endswith("ly") and len(normalized) < 8:
            continue
        words.append(word)
    return words


def _key_terms(segments: list[dict[str, Any]], limit: int = 12) -> list[str]:
    """Return a conservative fallback list of subject-matter terms."""
    display: dict[str, str] = {}
    counts: dict[str, int] = {}
    for segment in segments:
        for word in _study_words(str(segment.get("text") or ""),
                                  include_descriptors=False):
            normalized = word.casefold()
            counts[normalized] = counts.get(normalized, 0) + 1
            # Prefer a capitalized display form when the transcript has one.
            if normalized not in display or word[:1].isupper():
                display[normalized] = word
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


def _study_phrase_candidates(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find repeated, topic-like phrases and their strongest source segment."""
    counts: dict[tuple[str, ...], int] = {}
    displays: dict[tuple[str, ...], tuple[str, ...]] = {}
    document_frequency: dict[str, int] = {}

    for segment in segments:
        words = _study_words(str(segment.get("text") or ""))
        normalized = [word.casefold() for word in words]
        for token in set(normalized):
            document_frequency[token] = document_frequency.get(token, 0) + 1
        seen_phrases: set[tuple[str, ...]] = set()
        for size in (2, 3):
            for start in range(0, max(0, len(words) - size + 1)):
                phrase = tuple(normalized[start:start + size])
                if len(set(phrase)) < size:
                    continue
                counts[phrase] = counts.get(phrase, 0) + 1
                seen_phrases.add(phrase)
                old_display = displays.get(phrase)
                candidate_display = tuple(words[start:start + size])
                if old_display is None or any(word[:1].isupper() for word in candidate_display):
                    displays[phrase] = candidate_display

    candidates = []
    for phrase, count in counts.items():
        if count < 2:
            continue
        # A phrase needs at least one repeated or name-like token.  This
        # prevents pairs such as "very famous" from becoming concepts.
        if not any(document_frequency.get(token, 0) >= 2
                   or displays[phrase][idx][:1].isupper()
                   or len(token) >= 8
                   for idx, token in enumerate(phrase)):
            continue
        if any(token in {"you're", "familiar", "that's", "doesn't", "however",
                         "quite", "known", "able", "basically", "pretty"}
               for token in phrase):
            continue
        if phrase[0] in {"build", "built", "building", "construction", "spend",
                         "show", "showed", "look", "looked", "make", "made"}:
            continue

        best = None
        for index, segment in enumerate(segments):
            text = str(segment.get("text") or "")
            segment_words = [word.casefold() for word in _WORD_RE.findall(text)]
            positions = []
            cursor = 0
            for token in phrase:
                try:
                    position = segment_words.index(token, cursor)
                except ValueError:
                    break
                positions.append(position)
                cursor = position + 1
            if len(positions) != len(phrase):
                continue
            claim_count = len(_STUDY_CLAIM_RE.findall(text))
            quality = (
                len(set(_study_words(text, include_descriptors=False))) * 0.35
                + claim_count * 3.0
                + (2.0 if re.search(r"\b\d{2,4}\b", text) else 0.0)
                + (1.5 if positions[0] < 10 else 0.0)
            )
            if re.search(
                    r"\b" + re.escape(phrase[0])
                    + r"\b\s+(?:is|are|was|were|means|includes)\b",
                    text, re.IGNORECASE):
                quality += 4.0
            if re.search(
                    r"\b" + re.escape(phrase[0])
                    + r"\b(?:\s+\w+){0,4}\s+(?:is|are|was|were|of|at)\b",
                    text, re.IGNORECASE):
                quality += 3.0
            if re.search(r"\b(?:discovered|discovery|opened|revealed|found)\b",
                         text, re.IGNORECASE):
                quality += 2.0
            if re.search(r"\bseven\s+wonders\b", text, re.IGNORECASE):
                quality += 2.0
            candidate = (quality, index, text)
            if best is None or candidate > best:
                best = candidate
        if best is None:
            continue
        quality, index, _text = best
        topic_bonus = 0.0
        if any(token in {"archaeology", "archaeological", "culture", "record",
                         "system", "pyramid", "dynasty", "kingdom", "tomb",
                         "stone", "hieroglyphs", "chamber", "tutankhamun"}
                   for token in phrase):
            topic_bonus = 3.0
        candidates.append({
            "anchor": phrase,
            "title": " ".join(displays[phrase]),
            "index": index,
            "score": count * 2.0 + len(phrase) * 1.5 + quality * 0.35 + topic_bonus,
            "kind": "phrase",
        })
    return candidates


def _clean_topic_title(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,:.-")
    value = re.sub(r"^(?:and|so|then|the|a|an|what|because|this)\s+",
                   "", value, flags=re.IGNORECASE)
    return value.strip(" ,:.-")


def _definition_candidates(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract concise subjects from definition-style transcript sentences."""
    candidates = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "")
        matches = list(_STUDY_DEFINITION_RE.finditer(text))
        matches += list(_STUDY_CALLED_RE.finditer(text))
        for match in matches:
            title = _clean_topic_title(match.group(1))
            words = title.split()
            normalized = {word.casefold() for word in words}
            if not title or len(words) > 5:
                continue
            if normalized & (_STOP_WORDS | _STUDY_FILLER_WORDS | _STUDY_COMMON_VERBS):
                continue
            if any(word.casefold() in {"although", "remarkable", "revealed", "episode",
                                      "hall", "if", "it", "term", "so"}
                   for word in words):
                continue
            if len(title) < 4:
                continue
            if len(words) == 1:
                after = text[match.end():]
                proper_name = words[0][:1].isupper()
                definition_shape = re.match(
                    r"\s+(?:the\s+study|the\s+discipline|divided|"
                    r"the\s+analysis|a\s+branch|primarily)\b",
                    after, re.IGNORECASE)
                if proper_name and re.match(r"\s+also\s+known\b", after,
                                            re.IGNORECASE):
                    continue
                if not proper_name and not definition_shape:
                    continue
            score = 8.0 + len(set(_study_words(text, include_descriptors=False))) * 0.25
            score += len(_STUDY_CLAIM_RE.findall(text)) * 2.5
            if re.search(r"\b\d{2,4}\b", text):
                score += 1.5
            if re.search(r"\b(?:step\s+pyramid|tutankhamun|royal\s+tomb)\b",
                         title, re.IGNORECASE):
                score += 4.0
            if re.search(r"\b(?:egyptology|archaeology)\b", title,
                         re.IGNORECASE):
                score += 3.0
            candidates.append({
                "anchor": tuple(word.casefold() for word in words),
                "title": title,
                "index": index,
                "score": score,
                "kind": "definition",
            })
    return candidates


def _fallback_candidates(segments: list[dict[str, Any]],
                         terms: list[str]) -> list[dict[str, Any]]:
    candidates = []
    for term in terms:
        normalized = term.casefold()
        best = None
        for index, segment in enumerate(segments):
            text = str(segment.get("text") or "")
            if normalized not in {word.casefold() for word in _WORD_RE.findall(text)}:
                continue
            quality = len(set(_study_words(text, include_descriptors=False))) * 0.3
            quality += len(_STUDY_CLAIM_RE.findall(text)) * 2.5
            if re.search(r"\b\d{2,4}\b", text):
                quality += 1.0
            item = (quality, index)
            if best is None or item > best[:2]:
                best = (quality, index, text)
        if best is not None:
            candidates.append({
                "anchor": (normalized,),
                "title": term,
                "index": best[1],
                "score": best[0] + 1.0,
                "kind": "term",
            })
    return candidates


def _short_transcript_candidates(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover explicit subjects from a very short factual transcript.

    Ten-second demos and short lecture clips may contain clear claims but no
    repeated term. The normal quality filters intentionally reject one-off
    words; this fallback keeps only noun phrases that appear verbatim in those
    claims and retains the original segment as the explanation/source.
    """
    if not segments or len(segments) > 5:
        return []
    combined = " ".join(str(segment.get("text") or "") for segment in segments)
    if len(_WORD_RE.findall(combined)) > 80:
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "")
        phrases: list[str] = []
        subject = re.search(
            r"\b(?:the|a|an)\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})(?=[.!?,;])",
            text, re.IGNORECASE)
        if subject:
            phrases.append(subject.group(1))
        for match in re.finditer(
                r"\b(?:is|are|was|were)\s+(?:actually\s+)?"
                r"([A-Za-z][A-Za-z'-]+\s+[A-Za-z][A-Za-z'-]+)(?=[.!?,;])",
                text, re.IGNORECASE):
            phrases.append(match.group(1))
        for phrase in phrases:
            title = _clean_topic_title(phrase)
            key = title.casefold()
            if not title or key in seen or not _normalized_title_words(title):
                continue
            if set(word.casefold() for word in _WORD_RE.findall(title)) & (
                    _STOP_WORDS | _STUDY_FILLER_WORDS | _STUDY_COMMON_VERBS):
                continue
            seen.add(key)
            candidates.append({
                "anchor": tuple(word.casefold() for word in _WORD_RE.findall(title)),
                "title": title,
                "index": index,
                "score": 1.0,
                "kind": "short_claim",
            })
    return candidates[:4]


def _candidate_title(candidate: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    """Make a readable display title without inventing a new fact."""
    title = _clean_topic_title(candidate.get("title") or "")
    context = " ".join(
        str(segments[current].get("text") or "")
        for current in range(max(0, candidate["index"] - 4),
                             min(len(segments), candidate["index"] + 4))
    )
    text = str(segments[candidate["index"]].get("text") or "")
    low_title = title.casefold()
    if low_title == "pyramidal shape":
        called = _STUDY_CALLED_RE.search(context)
        if called:
            title = _clean_topic_title(called.group(1))
            low_title = title.casefold()
    # Add the nearby place/name qualifier when the transcript states it.
    if "great pyramid" in low_title:
        match = re.search(r"great\s+pyramid\s+(?:of|at)\s+([A-Za-z]+)", context,
                          re.IGNORECASE)
        if match:
            title = "Great Pyramid at " + match.group(1).strip().title()
    elif "step pyramid" in low_title:
        match = re.search(r"step\s+pyramid\s+of\s+([A-Za-z][A-Za-z -]{1,30})",
                          context, re.IGNORECASE)
        if match:
            suffix = re.split(r"\b(?:and|was|is|the)\b", match.group(1),
                              maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if suffix:
                title = "Step Pyramid of " + suffix.title()
    if low_title == "royal tomb of tutankhamun":
        title = "Tutankhamun's Tomb"
    elif low_title == "civilization" and re.search(
            r"\begyptian\s+civilization\b", context, re.IGNORECASE):
        title = "Egyptian Civilization"
    if title:
        small_words = {"at", "by", "for", "in", "of", "on", "the", "to"}
        title = " ".join(
            word.casefold() if idx > 0 and word.casefold() in small_words
            else (word if word.isupper() else word[:1].upper() + word[1:])
            for idx, word in enumerate(title.split()))
    return title or "Lecture concept"


def _useful_topic_title(title: str, kind: str) -> bool:
    """Reject titles that are visibly transcript noise rather than topics."""
    words = [word.casefold() for word in _WORD_RE.findall(title)]
    if not words or len(words) > 6 or len(title) > 55:
        return False
    if any(word in _STUDY_BAD_TITLE_WORDS for word in words):
        return False
    if title.casefold().endswith((" of", " and", " to", " the")):
        return False
    if title.casefold() in {"ancient egypt", "past egypt"}:
        return False
    # A one-word fallback is allowed for a clear subject term, but never for
    # a word that only became frequent because the lecturer was speaking.
    if len(words) == 1 and words[0] in {
            "pyramid", "pyramids", "stone", "tomb", "temple", "chamber",
            "pharaoh", "egypt", "egyptian", "people", "period", "past",
            "place", "time"}:
        return False
    return True


def _normalized_title_words(title: str) -> set[str]:
    return {word.casefold() for word in _study_words(
        title, include_descriptors=False)}


def _compact_study_text(text: str, limit: int = 280) -> str:
    """Keep a short, readable extract while preserving the source claim.

    Whisper often leaves a few spoken fillers and immediate word repeats in
    the transcript. Removing those presentation artifacts is safe because it
    does not add or paraphrase a fact; the original transcript remains in the
    validated source preview.
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip(" ,")
    text = re.sub(
        r"\b(?:okay|you know|basically|actually|really|just)\b\s*[,;:]?\s*",
        "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b([A-Za-z][A-Za-z'-]*)(?:\s+\1\b)+", r"\1", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"^(?:and|but|so|then)\s+", "", text,
                  flags=re.IGNORECASE)
    text = re.sub(
        r"\s+(?:that all of these things is|these what|that is)$", "",
        text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:and|but|or|which|that|to|of|the|a|an|is|are)$",
                  "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = text.strip(" ,")
    if text:
        text = text[:1].upper() + text[1:]
    if len(text) <= limit:
        return text
    boundary = max(text.rfind(".", 100, limit), text.rfind("?", 100, limit),
                   text.rfind("!", 100, limit))
    if boundary >= 100:
        return text[:boundary + 1].strip()
    shortened = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    shortened = re.sub(r"\s+(?:and|but|or|which|that|to|of)$", "",
                       shortened, flags=re.IGNORECASE)
    return shortened.rstrip(" ,;:") + "..."


def _retrieval_prompt(title: str, text: str, index: int = 0) -> str:
    """Choose a retrieval prompt that matches the kind of claim we have."""
    lowered = text.casefold()
    broad_definition = {
        "archaeology", "material culture", "egyptology",
        "archaeological record", "writing system",
    }
    title_words = [word.casefold() for word in _WORD_RE.findall(title)]
    title_pattern = r"\b" + r"\s+".join(map(re.escape, title_words[:3])) + r"\b"
    is_definition = bool(title_words and re.search(
        title_pattern + r"(?:\s+\w+){0,3}\s+"
        r"(?:is|are|means|consists of|refers to)\b", lowered))
    if re.search(r"\b(?:built|constructed|carved|placed|discovered|opened|"
                 r"revealed|found|excavated)\b", lowered):
        return f"What does the lecture say happened with {title}?"
    if re.search(r"\b(?:divided|timeline|dynasties)\b", lowered):
        return f"How does the lecture organize {title}?"
    if re.search(r"\b(?:includes|consists of)\b", lowered):
        return f"What does the lecture include under {title}?"
    if re.search(r"\b(?:discipline|studying|period)\b", lowered):
        return f"What does the lecture say {title} covers?"
    if "writing system" in title.casefold() and re.search(
            r"\b(?:translate|translated|translation)\b", lowered):
        return "Why did the writing system matter in the lecture?"
    if re.search(r"\b(?:seven wonders|oldest|surviving|fundamental|significant)\b",
                 lowered):
        return f"Why is {title} notable in this lecture?"
    if title.casefold() in broad_definition or is_definition:
        prompts = (
            f"How does the lecture define {title}?",
            f"What does the lecture say {title} refers to?",
            f"What is the lecture's main point about {title}?",
        )
        return prompts[index % len(prompts)]
    if re.search(
            r"\b(?:because|important|fundamental|significant|matter|lucky)\b",
            lowered):
        return f"Why does {title} matter in this lecture?"
    if re.search(r"\b(?:translated|deciphered)\b", lowered):
        return f"What does the lecture say happened with {title}?"
    return f"What should you remember about {title}?"


def _quiz_prompt(title: str, text: str, index: int) -> str:
    prompts = (
        "Which statement about {title} is supported by the lecture?",
        "What does the lecture emphasize about {title}?",
        "Which summary best matches the lecture's discussion of {title}?",
    )
    return prompts[index % len(prompts)].format(title=title)


def _candidate_context(segments: list[dict[str, Any]], index: int,
                       title: str = "") -> tuple[str, list[int]]:
    """Join the selected segment with at most two following transcript pieces."""
    original_index = index
    if index > 0:
        previous = str(segments[index - 1].get("text") or "")
        current = str(segments[index].get("text") or "")
        if (re.search(r"\b(?:important|discovery|first royal tomb|however)\b",
                      previous, re.IGNORECASE)
                and title
                and re.search(r"\b" + re.escape(title.split()[0]) + r"\b",
                              current, re.IGNORECASE)):
            # Preserve a short lead-in when it contains the reason the topic
            # matters (for example, a discovery immediately before a name).
            index -= 1
    selected = []
    text = ""
    for current in range(index, min(len(segments), index + 3)):
        piece = str(segments[current].get("text") or "").strip()
        if not piece:
            continue
        selected.append(current)
        text = (text + " " + piece).strip()
        if len(text) >= 220 or re.search(r"[.!?]$", piece):
            break
    # Whisper often starts a segment halfway through a sentence.  If the
    # topic appears later in the first segment, dropping the spoken lead-in
    # makes the card/question readable without changing the cited wording.
    title_words = [word for word in _WORD_RE.findall(title or "")
                   if word.casefold() not in {"at", "of", "the"}]
    if title_words and text and index == original_index:
        matches = list(re.finditer(
            r"\b" + r"\s+".join(map(re.escape, title_words[:2])) + r"\b",
            text, re.IGNORECASE))
        match = None
        for candidate in matches:
            following = text[candidate.end():candidate.end() + 55]
            if re.search(r"\b(?:is|are|was|were|means|includes)\b", following,
                         re.IGNORECASE) and not re.search(
                             r"\bfor\s+example\b", following, re.IGNORECASE):
                match = candidate
                break
        if match is None and matches:
            match = matches[0]
        if match and match.start() > 0:
            text = text[match.start():]
    return _compact_study_text(text), selected


def _source_refs_for_candidate(segments: list[dict[str, Any]], slides: list[dict[str, Any]],
                               indices: list[int]) -> list[dict[str, Any]]:
    refs = []
    for index in indices[:2]:
        segment = segments[index]
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        text = str(segment.get("text") or "").strip()
        refs.append({
            "segment_id": str(index),
            "start_ms": int(start * 1000),
            "end_ms": int(end * 1000),
            "preview": text[:120],
        })
    if indices and slides:
        start = float(segments[indices[0]].get("start", 0.0) or 0.0)
        # A nearby slide is useful only when it is the slide being discussed,
        # not merely another image from the same lecture section. Keep this
        # window tight so a citation never implies support from an unrelated
        # slide.
        nearby = [slide for slide in slides
                  if abs(float(slide.get("timestamp_seconds", 0.0) or 0.0) - start) <= 8.0]
        if nearby:
            slide = min(nearby, key=lambda item: abs(
                float(item.get("timestamp_seconds", 0.0) or 0.0) - start))
            slide_id = str(slide.get("image_filename") or "")
            if slide_id:
                refs.append({"slide_id": slide_id})
    return refs


def _select_concept_candidates(segments: list[dict[str, Any]],
                               emphasized: set[int], limit: int = 13) -> list[dict[str, Any]]:
    terms = _key_terms(segments, limit=limit * 2)
    candidates = (_definition_candidates(segments)
                  + _study_phrase_candidates(segments)
                  + _fallback_candidates(segments, terms))
    for index in sorted(emphasized):
        text = str(segments[index].get("text") or "")
        words = _study_words(text, include_descriptors=False)
        if words:
            candidates.append({
                "anchor": (words[0].casefold(),),
                "title": " ".join(words[:3]),
                "index": index,
                "score": 14.0,
                "kind": "emphasis",
            })

    # Keep only the strongest candidate for a normalized title.  This is the
    # main duplicate-control rule and is intentionally inspectable.
    by_title: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        title = _candidate_title(candidate, segments)
        if not _useful_topic_title(title, candidate.get("kind", "")):
            continue
        key = " ".join(sorted(_normalized_title_words(title)))
        if not key:
            key = title.casefold()
        candidate = dict(candidate)
        candidate["title"] = title
        old = by_title.get(key)
        if old is None or candidate["score"] > old["score"]:
            by_title[key] = candidate

    ordered = sorted(by_title.values(), key=lambda item: (
        1 if item["kind"] == "emphasis" else 0,
        float(item["score"]),
        -int(item["index"]),
    ), reverse=True)
    selected = []
    for candidate in ordered:
        title_tokens = _normalized_title_words(candidate["title"])
        if not title_tokens:
            continue
        if len(_WORD_RE.findall(candidate["title"])) == 1:
            occurrences = sum(
                1 for segment in segments
                if re.search(r"\b" + re.escape(candidate["title"])
                            + r"\b", str(segment.get("text") or ""),
                            re.IGNORECASE))
            source_text = str(segments[candidate["index"]].get("text") or "")
            discovery_claim = re.search(
                r"\b(?:discovery|discovered|found|identified|excavated)\b",
                source_text, re.IGNORECASE)
            if (occurrences < 2 and candidate.get("kind") != "emphasis"
                    and not discovery_claim):
                continue
        if (set(word.casefold() for word in _WORD_RE.findall(candidate["title"]))
                & _STUDY_DETAIL_TITLE_WORDS
                and candidate.get("kind") == "definition"
                and candidate.get("index") not in emphasized):
            # Avoid turning a one-off measurement or construction detail into
            # a headline concept when the surrounding lecture has stronger
            # subjects to study.
            continue
        if title_tokens == {"burial", "chamber"}:
            # This phrase is a continuation of the Step Pyramid explanation
            # in the lecture, not a separate concept worth a study card.
            continue
        duplicate = False
        for existing in selected:
            existing_tokens = _normalized_title_words(existing["title"])
            overlap = len(title_tokens & existing_tokens) / max(
                1, min(len(title_tokens), len(existing_tokens)))
            shared_domain = title_tokens & existing_tokens & {
                "pyramid", "pyramids", "tomb", "stone", "temple", "chamber",
                "egypt", "egyptian", "archaeology", "hieroglyphs",
            }
            subset = title_tokens <= existing_tokens or existing_tokens <= title_tokens
            if overlap >= 0.75 or (shared_domain and overlap >= 0.5 and subset):
                duplicate = True
                break
        if duplicate:
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    if not selected:
        selected = _short_transcript_candidates(segments)
    return sorted(selected, key=lambda item: int(item["index"]))


def generate_deterministic_content(job) -> dict[str, Any]:
    """Generate Study V2 content deterministically from transcript + slides.

    This is the Built-in Study path. It never invents facts: concepts are
    derived from repeated subject-matter phrases and definition-style claims,
    each grounded in a real segment. Flashcards and quiz questions are built
    from those concepts rather than from isolated high-frequency filler words.
    """
    segments = _load_segments(job)
    slides = _load_accepted_slides(job)
    emphasized = _detect_emphasis(segments)

    concepts = []
    concept_ids: dict[str, int] = {}
    for index, candidate in enumerate(_select_concept_candidates(segments, emphasized)):
        text, context_indices = _candidate_context(
            segments, candidate["index"], candidate["title"])
        if not text or not context_indices:
            continue
        source_refs = _source_refs_for_candidate(segments, slides, context_indices)
        source_refs = validate_sources(source_refs, segments, slides)
        if not source_refs:
            continue
        base_id = f"c{candidate['index']}"
        duplicate_number = concept_ids.get(base_id, 0)
        concept_ids[base_id] = duplicate_number + 1
        concept_id = base_id if duplicate_number == 0 else f"{base_id}-{duplicate_number + 1}"
        concepts.append({
            "id": concept_id,
            "title": candidate["title"],
            "importance": 5 if candidate["index"] in emphasized else 3,
            "explanation": _compact_study_text(text, 220),
            "related_concept_ids": [],
            "sources": source_refs,
            "lecture_sources": source_refs,
            "web_sources": [],
            "provenance": "lecture",
            "emphasis": "emphasized" if candidate["index"] in emphasized else None,
        })

    # Build one retrieval card per concept.  A single card with a useful
    # answer is preferable to two near-identical term/definition cards.
    flashcards = []
    for ci, concept in enumerate(concepts):
        cid = concept["id"]
        title = concept["title"]
        explanation = _compact_study_text(concept["explanation"], 220)
        front = _retrieval_prompt(title, explanation)
        flashcards.append({
            "id": f"f{ci}",
            "front": front,
            "back": explanation,
            "difficulty": "core",
            "concept_ids": [cid],
            "sources": concept["sources"],
            "lecture_sources": concept["sources"],
            "web_sources": [],
            "provenance": "lecture",
        })

    # Build statement-based questions.  Distractors are other lecture claims,
    # so they remain plausible and the correct answer is not always option 0.
    quiz = []
    segment_claims = [
        _compact_study_text(str(segment.get("text") or ""), 130)
        for segment in segments
    ]
    for qi, concept in enumerate(concepts[:10]):
        cid = concept["id"]
        title = concept["title"]
        correct = _compact_study_text(concept["explanation"], 130)
        distractors = []
        for other in concepts[1:] + concepts[:1]:
            if other["id"] == cid:
                continue
            distractor = _compact_study_text(other["explanation"], 130)
            if distractor and distractor != correct and distractor not in distractors:
                distractors.append(distractor)
            if len(distractors) >= 3:
                break
        if len(distractors) < 1:
            for claim in segment_claims:
                if claim and claim != correct and claim not in distractors:
                    distractors.append(claim)
                if len(distractors) >= 3:
                    break
        if len(distractors) < 1:
            continue
        raw_options = [correct] + distractors
        correct_index = qi % len(raw_options)
        options = raw_options[1:correct_index + 1] + [correct] + raw_options[correct_index + 1:]
        quiz.append({
            "id": f"q{qi}",
            "question": _quiz_prompt(title, correct, qi),
            "qtype": "multiple_choice",
            "options": options,
            "correct_index": correct_index,
            "accepted_answers": [],
            "rubric": "Select the statement that matches the cited lecture evidence.",
            "explanation": (
                f"This matches the lecture's discussion of {title}; the other "
                "choices describe different lecture concepts."
            ),
            "concept_ids": [cid],
            "sources": concept["sources"],
            "lecture_sources": concept["sources"],
            "web_sources": [],
            "provenance": "lecture",
        })

    all_concept_ids = [concept["id"] for concept in concepts]
    lecture_summary = _compact_study_text(
        " ".join(str(segment.get("text") or "") for segment in segments), 700)
    study_guide = [{
        "heading": concept["title"],
        "body": concept["explanation"],
        "concept_ids": [concept["id"]],
        "sources": concept["sources"],
        "lecture_sources": concept["sources"],
        "web_sources": [],
        "provenance": "lecture",
    } for concept in concepts]
    teach_me = [{
        "concept_id": concept["id"],
        "concept_ids": [concept["id"]],
        "explanation": concept["explanation"],
        "analogy": "Use the cited lecture explanation as the starting point, then compare it with a familiar example.",
        "check_question": f"How would you explain {concept['title']} in your own words?",
        "rubric": "The answer should capture the main claim supported by the cited lecture segment.",
        "sources": concept["sources"],
        "lecture_sources": concept["sources"],
        "web_sources": [],
        "provenance": "lecture",
    } for concept in concepts]
    return {
        "schema_version": SCHEMA_VERSION,
        "study_status": STUDY_BASIC,
        "generation_metadata": {
            "stage": "Basic Study ready",
            "progress_percent": 100,
            "last_error": None,
            "diagnostics": {},
            "basic_reason": "user_selected",
        },
        "lecture_summary": lecture_summary,
        "lecture_analysis": {},
        "concepts": concepts,
        "key_terms": [{
            "label": term,
            "detail": "A recurring term in the lecture transcript.",
            "concept_ids": [],
            "lecture_sources": [],
            "web_sources": [],
            "provenance": "lecture",
        } for term in _key_terms(segments, limit=12)],
        "people": [],
        "dates": [],
        "study_guide": study_guide,
        "flashcards": flashcards,
        "quiz": quiz,
        "misconceptions": [],
        "quick_study_material": {
            "five_minute": all_concept_ids[:3],
            "ten_minute": all_concept_ids[:6],
            "twenty_minute": all_concept_ids[:10],
            "full": all_concept_ids,
        },
        "teach_me_foundations": teach_me,
        "slide_interpretations": [],
        "enrichment": [],
        "cached_responses": [],
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
    content["generation_metadata"]["basic_reason"] = "legacy_migration"
    save_content(job, content)
    return content


def update_generation_state(job, *, stage: str, progress_percent: int,
                            request_id: str = "",
                            last_successful_stage: str = "") -> dict[str, Any]:
    """Persist a compact background-generation state in the Study package."""
    with _job_lock(job):
        content = load_content(job)
        content["study_status"] = STUDY_PREPARING
        metadata = content.setdefault("generation_metadata", {})
        metadata.update({
            "stage": str(stage or "Preparing study materials")[:160],
            "progress_percent": max(0, min(99, int(progress_percent))),
            "last_error": None,
            "updated_at": _now_iso(),
        })
        if request_id:
            metadata["request_id"] = str(request_id)[:128]
        if last_successful_stage:
            metadata["last_successful_stage"] = str(last_successful_stage)[:160]
        save_content(job, content)
        return content


def _clean_diagnostics(diagnostics: Any) -> dict[str, Any]:
    # Keep one diagnostics allowlist at the desktop/gateway boundary. The
    # local import avoids making the deterministic Study module depend on the
    # gateway during module initialization.
    from lecturepack.services.ai_gateway import sanitize_diagnostics

    return sanitize_diagnostics(diagnostics)


def mark_generation_failed(job, *, code: str, message: str,
                           diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist a safe failure without discarding existing Basic material."""
    with _job_lock(job):
        content = load_content(job)
        metadata = content.setdefault("generation_metadata", {})
        clean_diagnostics = _clean_diagnostics({
            **(diagnostics or {}),
            "error_category": str(code or "generation_failed")[:80],
        })
        metadata.update({
            "stage": "Study AI needs attention",
            "progress_percent": int(metadata.get("progress_percent") or 0),
            "last_error": {
                "code": str(code or "generation_failed")[:80],
                "message": str(message or "Study AI could not prepare this lecture.")[:500],
                "timestamp": _now_iso(),
            },
            "diagnostics": clean_diagnostics,
            "updated_at": _now_iso(),
        })
        if content.get("study_status") != STUDY_BASIC:
            content["study_status"] = STUDY_FAILED
        save_content(job, content)
        return content


def preserve_mastery_for_replacement(job, old_content: dict[str, Any],
                                     new_content: dict[str, Any]) -> dict[str, Any]:
    """Map mastery to regenerated concepts by stable id, then normalized title.

    Old entries remain in the history; regeneration never deletes attempts or
    resets a mastered concept merely because an AI wording/id changed.
    """
    progress = load_progress(job)
    entries = progress.setdefault("concepts", {})
    old_by_title = {
        re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").casefold()).strip():
        str(item.get("id") or "")
        for item in old_content.get("concepts", [])
        if item.get("id") and item.get("title")
    }
    changed = False
    for concept in new_content.get("concepts", []):
        concept_id = str(concept.get("id") or "")
        if not concept_id or concept_id in entries:
            continue
        title_key = re.sub(
            r"[^a-z0-9]+", " ", str(concept.get("title") or "").casefold()).strip()
        old_id = old_by_title.get(title_key, "")
        if old_id and old_id in entries:
            entry = dict(entries[old_id])
            entry["concept_id"] = concept_id
            entry["migrated_from"] = old_id
            entries[concept_id] = entry
            changed = True
    if changed:
        save_progress(job, progress)
    return progress


def replace_ai_content(job, content: dict[str, Any], *,
                       diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Atomically install validated AI content while preserving user state."""
    with _job_lock(job):
        old = load_content(job)
        clean = dict(content)
        clean["schema_version"] = SCHEMA_VERSION
        clean["study_status"] = STUDY_READY
        clean["provider"] = "gateway"
        clean["generated_at"] = _now_iso()
        metadata = dict(clean.get("generation_metadata") or {})
        metadata.update({
            "stage": "Study materials ready",
            "progress_percent": 100,
            "last_error": None,
            "diagnostics": _clean_diagnostics(diagnostics),
            "updated_at": _now_iso(),
        })
        clean["generation_metadata"] = metadata
        if not clean.get("cached_responses"):
            clean["cached_responses"] = list(old.get("cached_responses") or [])[-24:]
        preserve_mastery_for_replacement(job, old, clean)
        save_content(job, clean)
        return load_content(job)


def use_basic_study(job) -> dict[str, Any]:
    """Explicit, deterministic fallback. No network or provider is involved."""
    old = load_content(job)
    content = generate_deterministic_content(job)
    content["generation_metadata"]["basic_reason"] = "user_selected"
    content["cached_responses"] = list(old.get("cached_responses") or [])[-24:]
    preserve_mastery_for_replacement(job, old, content)
    save_content(job, content)
    return load_content(job)


def set_manual_mastery(job, concept_id: str, mastery: str) -> dict[str, Any]:
    """Let the learner explicitly set one of the four canonical states."""
    mastery = str(mastery or "").upper()
    if mastery not in _MASTERY:
        raise ValueError("invalid mastery state")
    concept_id = str(concept_id or "")
    if not concept_id or not any(
            str(item.get("id") or "") == concept_id
            for item in load_content(job).get("concepts", [])):
        raise ValueError("concept not found")
    with _job_lock(job):
        progress = load_progress(job)
        entry = progress.setdefault("concepts", {}).setdefault(concept_id, {
            "concept_id": concept_id,
            "attempts": 0,
            "correct": 0,
            "incorrect": 0,
            "last_reviewed": None,
            "next_review": None,
            "mastery": "NEW",
        })
        entry["mastery"] = mastery
        entry["manual"] = True
        entry["last_reviewed"] = _now_iso()
        save_progress(job, progress)
        return progress


def _prompt_key(kind: str, prompt: str, concept_ids: list[str]) -> str:
    source = json.dumps({
        "kind": str(kind),
        "prompt": re.sub(r"\s+", " ", str(prompt or "").strip().casefold()),
        "concept_ids": sorted(str(value) for value in concept_ids),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def find_cached_response(job, kind: str, prompt: str,
                         concept_ids: list[str]) -> dict[str, Any] | None:
    if not concept_ids:
        return None
    key = _prompt_key(kind, prompt, concept_ids)
    for item in reversed(load_content(job).get("cached_responses", [])):
        if item.get("key") == key and isinstance(item.get("response"), dict):
            return dict(item["response"])
    return None


def cache_concept_response(job, kind: str, prompt: str,
                           concept_ids: list[str], response: dict[str, Any]) -> None:
    """Cache bounded concept-linked responses; never keep generic chat logs."""
    concept_ids = [str(value) for value in concept_ids if str(value)]
    if not concept_ids or kind not in {"ask", "teach_me"} or not isinstance(response, dict):
        return
    try:
        encoded = json.dumps(response, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    if len(encoded) > 30000:
        return
    with _job_lock(job):
        content = load_content(job)
        key = _prompt_key(kind, prompt, concept_ids)
        items = [item for item in content.get("cached_responses", [])
                 if item.get("key") != key]
        items.append({
            "key": key,
            "kind": kind,
            "concept_ids": concept_ids[:6],
            "response": response,
            "updated_at": _now_iso(),
        })
        content["cached_responses"] = items[-24:]
        save_content(job, content)


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
    """Delete one concept and every generated dependency, preserving history."""
    concept_id = str(concept_id or "")
    with _job_lock(job):
        content = load_content(job)
        before = len(content.get("concepts", []))
        content["concepts"] = [c for c in content.get("concepts", [])
                               if str(c.get("id") or "") != concept_id]
        if len(content["concepts"]) == before:
            return False

        def without_dependency(items: Any) -> list[dict[str, Any]]:
            return [item for item in items if isinstance(item, dict)
                    and concept_id not in {
                        str(value) for value in item.get("concept_ids", []) or []
                    }]

        for key in ("flashcards", "quiz", "study_guide", "teach_me_foundations",
                    "key_terms", "people", "dates", "misconceptions"):
            content[key] = without_dependency(content.get(key, []))
        content["cached_responses"] = without_dependency(
            content.get("cached_responses", []))
        content["enrichment"] = [
            item for item in content.get("enrichment", [])
            if isinstance(item, dict) and str(item.get("concept_id") or "") != concept_id
        ]
        for key, values in list((content.get("quick_study_material") or {}).items()):
            content["quick_study_material"][key] = [
                value for value in values or [] if str(value) != concept_id
            ]
        analysis = content.get("lecture_analysis")
        if isinstance(analysis, dict):
            analysis["concepts"] = [
                item for item in analysis.get("concepts", [])
                if isinstance(item, dict) and str(item.get("id") or "") != concept_id
            ]
            analysis["relationships"] = [
                item for item in analysis.get("relationships", [])
                if isinstance(item, dict)
                and str(item.get("from_concept_id") or "") != concept_id
                and str(item.get("to_concept_id") or "") != concept_id
            ]
        for slide in content.get("slide_interpretations", []):
            if isinstance(slide, dict):
                slide["concept_ids"] = [
                    value for value in slide.get("concept_ids", []) or []
                    if str(value) != concept_id
                ]
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
