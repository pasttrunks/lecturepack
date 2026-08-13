"""AI-first Study orchestration on top of the existing Study V2 persistence.

Local media processing stays local. Only transcript segments, timestamps,
accepted-slide metadata, selected slide images, and compact relationship data
are sent to the LecturePack AI Gateway. The service performs a canonical
lecture-analysis pass followed by a single coherent material-generation pass;
optional vision and web calls are bounded evidence steps between them.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import urlsplit
import uuid

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import study_v2
from lecturepack.services.ai_gateway import GatewayClient, GatewayError, sanitize_diagnostics


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]{1,}")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_PROVENANCE = {"lecture", "extra_context", "web_verified", "mixed"}
_MAX_VISION_SLIDES = 3
_MAX_WEB_REQUESTS = 3
_MAX_ANALYSIS_CHARS = 2_300_000
_SAFE_STUDY_STATUSES = {
    study_v2.STUDY_PREPARING,
    study_v2.STUDY_READY,
    study_v2.STUDY_FAILED,
    study_v2.STUDY_BASIC,
}
_SAFE_GENERATION_STAGES = {
    "Queued for Study AI",
    "Preparing lecture evidence",
    "Understanding the lecture",
    "Connecting lecture sections",
    "Reading selected lecture slides",
    "Checking optional public context",
    "Building the study system",
    "Validating sources and saving",
    "Study materials ready",
    "Study AI needs attention",
    "Basic Study ready",
}


class StudyContentError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "invalid_study_content")


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _request_id() -> str:
    return f"lp-{uuid.uuid4()}"


def _emit(job, callback: ProgressCallback | None, stage: str, percent: int,
          *, request_id: str = "", last_successful_stage: str = "") -> None:
    content = study_v2.update_generation_state(
        job,
        stage=stage,
        progress_percent=percent,
        request_id=request_id,
        last_successful_stage=last_successful_stage,
    )
    if callback:
        callback({
            "job_id": getattr(job, "job_id", ""),
            "status": content.get("study_status"),
            "stage": stage,
            "progress_percent": max(0, min(100, int(percent))),
        })


def _segments(job) -> list[dict[str, Any]]:
    return study_v2._load_segments(job)  # one authoritative working layer


def _slides(job) -> list[dict[str, Any]]:
    return study_v2._load_accepted_slides(job)


def _local_slide_text(slide: dict[str, Any]) -> str:
    for key in ("ocr_text", "slide_text", "extracted_text", "text"):
        if slide.get(key):
            return _text(slide.get(key), 5000)
    return ""


def build_lecture_bundle(job) -> dict[str, Any]:
    """Build a path-free, video-free source bundle for gateway analysis."""
    segments = _segments(job)
    if not segments:
        raise StudyContentError(
            "transcript_unavailable",
            "Study AI needs a completed transcript before it can prepare materials.")
    transcript = []
    for index, segment in enumerate(segments):
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        transcript.append({
            "segment_id": str(index),
            "start_ms": max(0, int(start * 1000)),
            "end_ms": max(0, int(end * 1000)),
            "text": _text(segment.get("text"), 12000),
        })
    slide_rows = []
    for index, slide in enumerate(_slides(job)):
        timestamp = float(slide.get("timestamp_seconds", 0.0) or 0.0)
        slide_id = str(slide.get("image_filename") or index)
        nearby = [
            item["segment_id"] for item in transcript
            if abs((item["start_ms"] / 1000.0) - timestamp) <= 18.0
        ][:8]
        slide_rows.append({
            "slide_id": slide_id,
            "timestamp_ms": max(0, int(timestamp * 1000)),
            "local_text": _local_slide_text(slide),
            "nearby_segment_ids": nearby,
        })
    return {
        "lecture": {
            "title": _text(getattr(job, "manifest", {}).get("title"), 300) or "Lecture",
            "duration_ms": max(0, int(float(
                getattr(job, "source", {}).get("duration", 0.0) or 0.0) * 1000)),
            "transcript_segment_count": len(transcript),
            "accepted_slide_count": len(slide_rows),
        },
        "transcript": transcript,
        "slides": slide_rows,
    }


def _analysis_bundles(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    if len(json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))) <= _MAX_ANALYSIS_CHARS:
        return [bundle]
    chunks = []
    current = []
    current_size = 0
    for segment in bundle["transcript"]:
        size = len(json.dumps(segment, ensure_ascii=False))
        if current and current_size + size > 900_000:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += size
    if current:
        chunks.append(current)
    output = []
    for index, transcript in enumerate(chunks):
        start_ms = transcript[0]["start_ms"]
        end_ms = transcript[-1]["end_ms"]
        relevant_slides = [
            slide for slide in bundle["slides"]
            if start_ms - 30000 <= slide["timestamp_ms"] <= end_ms + 30000
        ]
        output.append({
            "lecture": bundle["lecture"],
            "chunk": {"index": index + 1, "count": len(chunks)},
            "transcript": transcript,
            "slides": relevant_slides,
        })
    return output


def _material_evidence_bundle(bundle: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Select compact pass-two evidence from canonical-analysis citations.

    Long lectures are analyzed hierarchically, so sending the full transcript
    again during material generation would defeat both the hierarchy and the
    gateway request cap. Keep cited segments plus immediate neighbors, with a
    bounded fallback sample when the analysis contains no usable IDs.
    """
    segment_ids: list[str] = []
    slide_ids: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            segment_id = str(value.get("segment_id") or "")
            slide_id = str(value.get("slide_id") or "")
            if segment_id and segment_id not in segment_ids:
                segment_ids.append(segment_id)
            if slide_id and slide_id not in slide_ids:
                slide_ids.append(slide_id)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(analysis)
    transcript = bundle.get("transcript", [])
    selected_indexes: set[int] = set()
    for segment_id in segment_ids:
        try:
            index = int(segment_id)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(transcript):
            selected_indexes.update(
                candidate for candidate in (index - 1, index, index + 1)
                if 0 <= candidate < len(transcript))
    if not selected_indexes:
        selected_indexes.update(range(min(len(transcript), 80)))
    selected_transcript = []
    size = 0
    for index in sorted(selected_indexes):
        row = transcript[index]
        row_size = len(json.dumps(row, ensure_ascii=False))
        if selected_transcript and size + row_size > 1_200_000:
            break
        selected_transcript.append(row)
        size += row_size
    slides = [
        slide for slide in bundle.get("slides", [])
        if str(slide.get("slide_id") or "") in slide_ids
    ]
    return {
        "lecture": bundle.get("lecture", {}),
        "transcript": selected_transcript,
        "slides": slides,
        "evidence_selection": "canonical citations with adjacent context",
    }


def _safe_image_path(job, slide_id: str) -> Path | None:
    base = Path(job.paths["candidates"]).resolve()
    candidate = (base / str(slide_id)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _slide_data_url(job, slide_id: str) -> str:
    path = _safe_image_path(job, slide_id)
    if path is None:
        return ""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((1280, 1280))
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            raw = output.getvalue()
        if len(raw) <= 2_000_000:
            return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        try:
            raw = path.read_bytes()
            if len(raw) <= 2_000_000 and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}:
                mime = "image/png" if path.suffix.casefold() == ".png" else (
                    "image/webp" if path.suffix.casefold() == ".webp" else "image/jpeg")
                return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
        except OSError:
            return ""
    return ""


def _validated_lecture_sources(raw: Any, segments: list, slides: list) -> list[dict[str, Any]]:
    refs = raw if isinstance(raw, list) else []
    normalized = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        item = {
            "segment_id": str(ref.get("segment_id") or ""),
            "slide_id": str(ref.get("slide_id") or ""),
        }
        validated = study_v2.validate_source_ref(item, segments, slides)
        if validated and validated not in normalized:
            normalized.append(validated)
    return normalized


def _validated_web_sources(raw: Any, *,
                           allowed_urls: set[str] | None = None) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for source in raw if isinstance(raw, list) else []:
        if not isinstance(source, dict):
            continue
        url = _text(source.get("url"), 2000)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            continue
        if allowed_urls is not None and url not in allowed_urls:
            continue
        if url in seen:
            continue
        seen.add(url)
        output.append({
            "title": _text(source.get("title"), 300) or parsed.netloc,
            "url": url,
            "claim": _text(source.get("claim") or source.get("content"), 1200),
        })
    return output


def _web_url_allowlist(value: Any) -> set[str]:
    """Collect already-verified HTTPS URLs from normalized evidence only."""
    urls: set[str] = set()

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            if item.get("url"):
                url = _text(item.get("url"), 2000)
                parsed = urlsplit(url)
                if (parsed.scheme == "https" and parsed.netloc
                        and not parsed.username and not parsed.password):
                    urls.add(url)
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    return urls


def _provenance(value: Any, lecture_sources: list, web_sources: list) -> str:
    requested = str(value or "").lower()
    if lecture_sources and web_sources:
        return "mixed"
    if web_sources:
        return "web_verified"
    if lecture_sources:
        return "lecture"
    return requested if requested in _PROVENANCE else "extra_context"


def _stable_id(prefix: str, preferred: Any, seed: str, used: set[str]) -> str:
    candidate = str(preferred or "")
    if _SAFE_ID_RE.fullmatch(candidate) and candidate not in used:
        used.add(candidate)
        return candidate
    import hashlib

    slug = re.sub(r"[^a-z0-9]+", "-", seed.casefold()).strip("-")[:36] or "item"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    candidate = f"{prefix}-{slug}-{digest}"
    counter = 2
    while candidate in used:
        candidate = f"{prefix}-{slug}-{digest}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _grounding(raw: dict[str, Any], segments: list, slides: list,
               *, inherited: dict[str, Any] | None = None,
               allowed_web_urls: set[str] | None = None) -> dict[str, Any]:
    inherited = inherited or {}
    lecture = _validated_lecture_sources(
        raw.get("lecture_sources", raw.get("sources")), segments, slides)
    web = _validated_web_sources(
        raw.get("web_sources"), allowed_urls=allowed_web_urls)
    # Inheriting the concept's citations when the model returned none is right
    # for material the lecture DID cover -- but not when the model has just told
    # us the answer came from its own knowledge. Borrowing them there produced
    # answers like "not mentioned in the provided lecture context" stamped with
    # three "From lecture · Slide" chips: a citation for a claim no lecture
    # source supports. Honour the declaration instead.
    declared = str(raw.get("provenance") or "").lower()
    if not lecture and declared != "extra_context":
        lecture = list(inherited.get("lecture_sources") or inherited.get("sources") or [])
    if not web:
        web = list(inherited.get("web_sources") or [])
    return {
        "sources": lecture,
        "lecture_sources": lecture,
        "web_sources": web,
        "provenance": _provenance(raw.get("provenance"), lecture, web),
    }


def _mapped_concept_ids(raw: Any, id_map: dict[str, str], valid: set[str]) -> list[str]:
    output = []
    for value in raw if isinstance(raw, list) else []:
        concept_id = id_map.get(str(value), str(value))
        if concept_id in valid and concept_id not in output:
            output.append(concept_id)
    return output


def _normalize_fact_items(raw: Any, segments: list, slides: list,
                          id_map: dict[str, str], concepts_by_id: dict[str, dict[str, Any]],
                          *, label_key: str = "label",
                          allowed_web_urls: set[str] | None = None) -> list[dict[str, Any]]:
    output = []
    valid_ids = set(concepts_by_id)
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        label = _text(item.get(label_key) or item.get("term") or item.get("title"), 240)
        detail = _text(item.get("detail") or item.get("definition") or item.get("body"), 1600)
        if not label or not detail:
            continue
        concept_ids = _mapped_concept_ids(item.get("concept_ids"), id_map, valid_ids)
        inherited = concepts_by_id.get(concept_ids[0], {}) if concept_ids else {}
        grounding = _grounding(
            item, segments, slides, inherited=inherited,
            allowed_web_urls=allowed_web_urls)
        if not grounding["sources"] and not grounding["web_sources"]:
            continue
        output.append({
            "label": label,
            "detail": detail,
            "concept_ids": concept_ids,
            **grounding,
        })
    return output


def normalize_generated_content(job, raw: dict[str, Any], analysis: dict[str, Any],
                                vision: list[dict[str, Any]],
                                enrichment: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate AI output into the schema already consumed by Rust and UI."""
    if not isinstance(raw, dict):
        raise StudyContentError("invalid_material_shape", "Study AI returned invalid material data.")
    segments = _segments(job)
    slides = _slides(job)
    used_ids: set[str] = set()
    id_map: dict[str, str] = {}
    raw_concept_by_id: dict[str, dict[str, Any]] = {}
    allowed_web_urls = _web_url_allowlist([
        {"sources": item.get("sources", [])}
        for item in enrichment if isinstance(item, dict)
    ])
    concepts = []
    for item in raw.get("concepts", []) if isinstance(raw.get("concepts"), list) else []:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"), 240)
        explanation = _text(item.get("explanation"), 5000)
        if not title or not explanation:
            continue
        grounding = _grounding(
            item, segments, slides, allowed_web_urls=allowed_web_urls)
        if not grounding["sources"] and not grounding["web_sources"]:
            continue
        old_id = str(item.get("id") or "")
        first_source = grounding["sources"][0].get("segment_id", "") if grounding["sources"] else ""
        concept_id = _stable_id("c", old_id, f"{title}|{first_source}", used_ids)
        if old_id:
            id_map[old_id] = concept_id
        raw_concept_by_id[concept_id] = item
        concepts.append({
            "id": concept_id,
            "title": title,
            "importance": max(1, min(5, int(item.get("importance") or 3))),
            "explanation": explanation,
            "related_concept_ids": [],
            "emphasis": _text(item.get("emphasis"), 80) or None,
            **grounding,
        })
    if not concepts:
        raise StudyContentError(
            "ungrounded_material",
            "Study AI did not return any concepts with valid lecture or web sources.")
    valid_ids = {item["id"] for item in concepts}
    concepts_by_id = {item["id"]: item for item in concepts}
    for normalized in concepts:
        source = raw_concept_by_id.get(normalized["id"], {})
        normalized["related_concept_ids"] = _mapped_concept_ids(
            source.get("related_concept_ids"), id_map, valid_ids)

    def inherit_for(ids: list[str]) -> dict[str, Any]:
        return concepts_by_id.get(ids[0], {}) if ids else {}

    flashcards = []
    used_card_ids: set[str] = set()
    for item in raw.get("flashcards", []) if isinstance(raw.get("flashcards"), list) else []:
        if not isinstance(item, dict):
            continue
        front = _text(item.get("front"), 800)
        back = _text(item.get("back"), 3000)
        concept_ids = _mapped_concept_ids(item.get("concept_ids"), id_map, valid_ids)
        if not front or not back or not concept_ids:
            continue
        grounding = _grounding(
            item, segments, slides, inherited=inherit_for(concept_ids),
            allowed_web_urls=allowed_web_urls)
        flashcards.append({
            "id": _stable_id("f", item.get("id"), f"{concept_ids[0]}|{front}", used_card_ids),
            "front": front,
            "back": back,
            "difficulty": _text(item.get("difficulty"), 40) or "core",
            "concept_ids": concept_ids,
            **grounding,
        })

    quiz = []
    used_question_ids: set[str] = set()
    for item in raw.get("quiz", []) if isinstance(raw.get("quiz"), list) else []:
        if not isinstance(item, dict):
            continue
        question = _text(item.get("question"), 1000)
        concept_ids = _mapped_concept_ids(item.get("concept_ids"), id_map, valid_ids)
        if not question or not concept_ids:
            continue
        qtype = str(item.get("qtype") or "multiple_choice").lower().replace("-", "_").replace(" ", "_")
        if qtype in {"mc", "mcq"}:
            qtype = "multiple_choice"
        if qtype in {"truefalse", "tf"}:
            qtype = "true_false"
        if qtype not in {"multiple_choice", "true_false", "short_answer"}:
            qtype = "multiple_choice"
        options = [_text(value, 700) for value in item.get("options", []) if _text(value, 700)]
        correct_index: int | None
        if qtype == "short_answer":
            options = []
            correct_index = None
        else:
            if qtype == "true_false" and len(options) < 2:
                options = ["True", "False"]
            options = options[:6]
            try:
                correct_index = int(item.get("correct_index"))
            except (TypeError, ValueError):
                correct_index = -1
            if len(options) < 2 or correct_index < 0 or correct_index >= len(options):
                continue
        grounding = _grounding(
            item, segments, slides, inherited=inherit_for(concept_ids),
            allowed_web_urls=allowed_web_urls)
        quiz.append({
            "id": _stable_id("q", item.get("id"), f"{concept_ids[0]}|{question}", used_question_ids),
            "question": question,
            "qtype": qtype,
            "options": options,
            "correct_index": correct_index,
            "accepted_answers": [_text(value, 800) for value in item.get("accepted_answers", []) if _text(value, 800)][:8],
            "rubric": _text(item.get("rubric"), 1800),
            "explanation": _text(item.get("explanation"), 2000),
            "concept_ids": concept_ids,
            **grounding,
        })
    if not flashcards or not quiz:
        raise StudyContentError(
            "incomplete_material",
            "Study AI did not return a usable set of flashcards and quiz questions.")

    study_guide = []
    for item in raw.get("study_guide", []) if isinstance(raw.get("study_guide"), list) else []:
        if not isinstance(item, dict):
            continue
        heading = _text(item.get("heading"), 300)
        body = _text(item.get("body"), 6000)
        concept_ids = _mapped_concept_ids(item.get("concept_ids"), id_map, valid_ids)
        if not heading or not body or not concept_ids:
            continue
        grounding = _grounding(
            item, segments, slides, inherited=inherit_for(concept_ids),
            allowed_web_urls=allowed_web_urls)
        study_guide.append({
            "heading": heading, "body": body, "concept_ids": concept_ids, **grounding,
        })
    if not study_guide:
        study_guide = [{
            "heading": concept["title"],
            "body": concept["explanation"],
            "concept_ids": [concept["id"]],
            "sources": concept["sources"],
            "lecture_sources": concept["lecture_sources"],
            "web_sources": concept["web_sources"],
            "provenance": concept["provenance"],
        } for concept in concepts]

    quick_raw = raw.get("quick_study_material") if isinstance(raw.get("quick_study_material"), dict) else {}
    priority = [item["id"] for item in sorted(
        concepts, key=lambda item: (-int(item.get("importance") or 3), item["title"].casefold()))]
    quick = {}
    for key, count in (("five_minute", 3), ("ten_minute", 6), ("twenty_minute", 10), ("full", len(priority))):
        selected = _mapped_concept_ids(quick_raw.get(key), id_map, valid_ids)
        for concept_id in priority:
            if concept_id not in selected:
                selected.append(concept_id)
        quick[key] = selected[:count]

    teach_me = []
    for item in raw.get("teach_me_foundations", []) if isinstance(raw.get("teach_me_foundations"), list) else []:
        if not isinstance(item, dict):
            continue
        concept_ids = _mapped_concept_ids(
            item.get("concept_ids") or [item.get("concept_id")], id_map, valid_ids)
        if not concept_ids:
            continue
        grounding = _grounding(
            item, segments, slides, inherited=inherit_for(concept_ids),
            allowed_web_urls=allowed_web_urls)
        teach_me.append({
            "concept_id": concept_ids[0],
            "concept_ids": concept_ids,
            "explanation": _text(item.get("explanation"), 4000),
            "analogy": _text(item.get("analogy"), 3000),
            "check_question": _text(item.get("check_question"), 1000),
            "rubric": _text(item.get("rubric"), 1800),
            **grounding,
        })

    relationships = []
    for item in analysis.get("relationships", []) if isinstance(analysis.get("relationships"), list) else []:
        if not isinstance(item, dict):
            continue
        source = id_map.get(str(item.get("from_concept_id") or ""), str(item.get("from_concept_id") or ""))
        target = id_map.get(str(item.get("to_concept_id") or ""), str(item.get("to_concept_id") or ""))
        relation = _text(item.get("relationship"), 800)
        if source in valid_ids and target in valid_ids and relation:
            relationships.append({
                "from_concept_id": source,
                "to_concept_id": target,
                "relationship": relation,
            })

    return {
        "schema_version": study_v2.SCHEMA_VERSION,
        "study_status": study_v2.STUDY_READY,
        "generation_metadata": {},
        "lecture_summary": _text(raw.get("lecture_summary") or analysis.get("lecture_summary"), 8000),
        "lecture_analysis": {
            "lecture_summary": _text(analysis.get("lecture_summary"), 8000),
            "concepts": [{
                "id": item["id"], "title": item["title"],
                "importance": item["importance"],
                "explanation": item["explanation"],
                "related_concept_ids": item["related_concept_ids"],
                "sources": item["sources"],
                "web_sources": item["web_sources"],
                "provenance": item["provenance"],
            } for item in concepts],
            "relationships": relationships,
        },
        "concepts": concepts,
        "key_terms": _normalize_fact_items(
            raw.get("key_terms"), segments, slides, id_map, concepts_by_id,
            allowed_web_urls=allowed_web_urls),
        "people": _normalize_fact_items(
            raw.get("people"), segments, slides, id_map, concepts_by_id,
            allowed_web_urls=allowed_web_urls),
        "dates": _normalize_fact_items(
            raw.get("dates"), segments, slides, id_map, concepts_by_id,
            allowed_web_urls=allowed_web_urls),
        "study_guide": study_guide,
        "flashcards": flashcards,
        "quiz": quiz,
        "misconceptions": _normalize_fact_items(
            raw.get("misconceptions"), segments, slides, id_map, concepts_by_id,
            allowed_web_urls=allowed_web_urls),
        "quick_study_material": quick,
        "teach_me_foundations": teach_me,
        "slide_interpretations": vision,
        "enrichment": enrichment,
        "cached_responses": [],
        "provider": "gateway",
        "generated_at": None,
    }


def _call(client: GatewayClient, task: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.request(task, payload, request_id=_request_id())
    return response["result"], response["diagnostics"]


def prepare_ai_study(job, client: GatewayClient, *,
                     progress: ProgressCallback | None = None,
                     cancelled: CancelCallback | None = None) -> dict[str, Any]:
    """Run canonical analysis, optional evidence, and material generation."""
    last_successful = "Local lecture processing"
    latest_diagnostics: dict[str, Any] = {}
    try:
        if cancelled and cancelled():
            return study_v2.load_content(job)
        _emit(job, progress, "Preparing lecture evidence", 5,
              last_successful_stage=last_successful)
        bundle = build_lecture_bundle(job)
        chunks = _analysis_bundles(bundle)
        analyses = []
        for index, chunk in enumerate(chunks):
            if cancelled and cancelled():
                return study_v2.load_content(job)
            pct = 12 + round((index / max(1, len(chunks))) * 18)
            _emit(job, progress, "Understanding the lecture", pct,
                  last_successful_stage=last_successful)
            result, latest_diagnostics = _call(client, "lecture_analysis", chunk)
            analyses.append(result)
            last_successful = "Lecture analysis"
        if len(analyses) == 1:
            analysis = analyses[0]
        else:
            if cancelled and cancelled():
                return study_v2.load_content(job)
            _emit(job, progress, "Connecting lecture sections", 34,
                  last_successful_stage=last_successful)
            analysis, latest_diagnostics = _call(client, "lecture_analysis", {
                "lecture": bundle["lecture"],
                "chunk_analyses": analyses,
                "instruction": "Merge these analyses into one canonical lecture map while preserving the original source IDs.",
            })
            last_successful = "Canonical lecture analysis"

        slide_by_id = {str(slide.get("slide_id")): slide for slide in bundle["slides"]}
        vision_results = []
        vision_requests = analysis.get("vision_requests", []) if isinstance(analysis.get("vision_requests"), list) else []
        seen_slides = set()
        for item in vision_requests:
            if cancelled and cancelled():
                return study_v2.load_content(job)
            if len(vision_results) >= _MAX_VISION_SLIDES or not isinstance(item, dict):
                break
            slide_id = str(item.get("slide_id") or "")
            if slide_id in seen_slides or slide_id not in slide_by_id:
                continue
            image = _slide_data_url(job, slide_id)
            if not image:
                continue
            seen_slides.add(slide_id)
            try:
                _emit(job, progress, "Reading selected lecture slides", 42 + len(vision_results) * 3,
                      last_successful_stage=last_successful)
                result, latest_diagnostics = _call(client, "vision_slide", {
                    **slide_by_id[slide_id],
                    "reason": _text(item.get("reason"), 500),
                    "image_data_url": image,
                })
                result["slide_id"] = slide_id
                vision_results.append(result)
                last_successful = "Selected slide interpretation"
            except GatewayError:
                # Vision is optional. The lecture-analysis and material passes
                # remain valid without it.
                continue

        enrichment_results = []
        research_requests = analysis.get("research_requests", []) if isinstance(analysis.get("research_requests"), list) else []
        seen_queries = set()
        for item in research_requests:
            if cancelled and cancelled():
                return study_v2.load_content(job)
            if len(enrichment_results) >= _MAX_WEB_REQUESTS or not isinstance(item, dict):
                break
            query = _text(item.get("query"), 500)
            if not query or query.casefold() in seen_queries:
                continue
            seen_queries.add(query.casefold())
            try:
                _emit(job, progress, "Checking optional public context", 54 + len(enrichment_results) * 3,
                      last_successful_stage=last_successful)
                result, latest_diagnostics = _call(client, "web_enrichment", {
                    "concept_id": _text(item.get("concept_id"), 80),
                    "query": query,
                    "reason": _text(item.get("reason"), 500),
                })
                sources = _validated_web_sources(result.get("sources"))
                if sources:
                    allowed_urls = {source["url"] for source in sources}
                    facts = []
                    for fact in result.get("facts", []) if isinstance(result.get("facts"), list) else []:
                        if not isinstance(fact, dict):
                            continue
                        url = _text(fact.get("url"), 2000)
                        claim = _text(fact.get("claim"), 1600)
                        if url not in allowed_urls or not claim:
                            continue
                        source = next(item for item in sources if item["url"] == url)
                        facts.append({
                            "claim": claim,
                            "title": _text(fact.get("title"), 300) or source["title"],
                            "url": url,
                        })
                    enrichment_results.append({
                        "concept_id": _text(item.get("concept_id"), 80),
                        "summary": _text(result.get("summary"), 4000),
                        "facts": facts[:12],
                        "sources": sources,
                    })
                    last_successful = "Optional web enrichment"
            except GatewayError:
                # Enrichment is optional and must never make Study fail.
                continue

        if cancelled and cancelled():
            return study_v2.load_content(job)
        _emit(job, progress, "Building the study system", 70,
              last_successful_stage=last_successful)
        material, latest_diagnostics = _call(client, "study_material_generation", {
            "lecture": _material_evidence_bundle(bundle, analysis),
            "canonical_analysis": analysis,
            "selected_slide_interpretations": vision_results,
            "verified_web_enrichment": enrichment_results,
        })
        last_successful = "Study material generation"
        if cancelled and cancelled():
            return study_v2.load_content(job)
        _emit(job, progress, "Validating sources and saving", 94,
              request_id=latest_diagnostics.get("request_id", ""),
              last_successful_stage=last_successful)
        normalized = normalize_generated_content(
            job, material, analysis, vision_results, enrichment_results)
        if cancelled and cancelled():
            return study_v2.load_content(job)
        final = study_v2.replace_ai_content(
            job, normalized,
            diagnostics={**latest_diagnostics, "last_successful_stage": last_successful})
        if progress:
            progress({
                "job_id": getattr(job, "job_id", ""),
                "status": study_v2.STUDY_READY,
                "stage": "Study materials ready",
                "progress_percent": 100,
            })
        return final
    except GatewayError as exc:
        # A job may be deleted/reset while a provider request is in flight.
        # Cancellation is not a generation failure and must never recreate
        # the removed job merely to persist failure diagnostics.
        if cancelled and cancelled():
            return study_v2.load_content(job)
        diagnostics = dict(exc.diagnostics)
        diagnostics["last_successful_stage"] = last_successful
        study_v2.mark_generation_failed(
            job, code=exc.code, message=str(exc), diagnostics=diagnostics)
        if progress:
            progress({
                "job_id": getattr(job, "job_id", ""),
                "status": study_v2.STUDY_FAILED,
                "stage": "Study AI needs attention",
                "progress_percent": 0,
                "error": str(exc),
            })
        raise
    except StudyContentError as exc:
        if cancelled and cancelled():
            return study_v2.load_content(job)
        diagnostics = sanitize_diagnostics({
            **latest_diagnostics,
            "error_category": exc.code,
            "last_successful_stage": last_successful,
        })
        study_v2.mark_generation_failed(
            job, code=exc.code, message=str(exc), diagnostics=diagnostics)
        if progress:
            progress({
                "job_id": getattr(job, "job_id", ""),
                "status": study_v2.STUDY_FAILED,
                "stage": "Study AI needs attention",
                "progress_percent": 0,
                "error": str(exc),
            })
        raise


def _retrieved_context(job, prompt: str, *, concept_id: str = "") -> tuple[dict[str, Any], list[str]]:
    content = study_v2.load_content(job)
    tokens = {word.casefold() for word in _WORD_RE.findall(prompt)}
    ranked = []
    for index, concept in enumerate(content.get("concepts", [])):
        cid = str(concept.get("id") or "")
        haystack = " ".join((str(concept.get("title") or ""), str(concept.get("explanation") or "")))
        words = {word.casefold() for word in _WORD_RE.findall(haystack)}
        score = len(tokens & words) * 4 + int(concept.get("importance") or 3)
        if concept_id and cid == concept_id:
            score += 100
        ranked.append((score, -index, concept))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    selected = [item[2] for item in ranked[:4] if item[0] > 0]
    if not selected:
        selected = [item[2] for item in ranked[:3]]
    concept_ids = [str(item.get("id") or "") for item in selected if item.get("id")]
    segments = _segments(job)
    evidence = []
    seen = set()
    for concept in selected:
        for source in concept.get("sources", []) or []:
            sid = str(source.get("segment_id") or "")
            if not sid or sid in seen:
                continue
            try:
                index = int(sid)
                segment = segments[index]
            except (IndexError, TypeError, ValueError):
                continue
            seen.add(sid)
            evidence.append({
                "segment_id": sid,
                "start_ms": int(float(segment.get("start", 0.0) or 0.0) * 1000),
                "end_ms": int(float(segment.get("end", 0.0) or 0.0) * 1000),
                "text": _text(segment.get("text"), 1800),
            })
            if len(evidence) >= 10:
                break
    return {
        "lecture_summary": _text(content.get("lecture_summary"), 5000),
        "concepts": selected,
        "transcript_evidence": evidence,
        "verified_web_enrichment": content.get("enrichment", [])[:4],
    }, concept_ids


def _normalize_interactive_grounding(job, result: dict[str, Any],
                                     inherited_concept_ids: list[str]) -> dict[str, Any]:
    segments = _segments(job)
    slides = _slides(job)
    content = study_v2.load_content(job)
    valid_ids = {str(item.get("id") or "") for item in content.get("concepts", [])}
    concept_ids = [str(value) for value in result.get("concept_ids", []) or []
                   if str(value) in valid_ids]
    if not concept_ids:
        concept_ids = [value for value in inherited_concept_ids if value in valid_ids]
    inherited = next((item for item in content.get("concepts", [])
                      if item.get("id") in concept_ids), {})
    allowed_web_urls = _web_url_allowlist([
        {"sources": item.get("sources", [])}
        for item in content.get("enrichment", []) if isinstance(item, dict)
    ] + [
        {"web_sources": item.get("web_sources", [])}
        for item in content.get("concepts", []) if isinstance(item, dict)
    ])
    grounding = _grounding(
        result, segments, slides, inherited=inherited,
        allowed_web_urls=allowed_web_urls)
    return {"concept_ids": concept_ids, **grounding}


def ask(job, client: GatewayClient, prompt: str) -> dict[str, Any]:
    prompt = _text(prompt, 2000)
    if not prompt:
        raise ValueError("prompt is required")
    context, concept_ids = _retrieved_context(job, prompt)
    cached = study_v2.find_cached_response(job, "ask", prompt, concept_ids)
    if cached:
        return {**cached, "cached": True}
    try:
        result, diagnostics = _call(client, "ask", {
            "question": prompt,
            "retrieved_context": context,
        })
    except GatewayError as exc:
        _record_interaction_error(job, "ask", exc)
        raise
    answer = _text(result.get("answer"), 10000)
    if not answer:
        raise StudyContentError("empty_answer", "Study AI did not return an answer.")
    normalized = {
        "answer": answer,
        **_normalize_interactive_grounding(job, result, concept_ids),
        "diagnostics": diagnostics,
    }
    # The lookup key must use the same locally retrieved concept set before
    # and after the gateway call. The model may cite a narrower subset in its
    # answer, but that must not turn identical follow-up opens into cache misses.
    study_v2.cache_concept_response(job, "ask", prompt, concept_ids, normalized)
    return normalized


def teach_me(job, client: GatewayClient, concept_id: str) -> dict[str, Any]:
    concept_id = str(concept_id or "")
    content = study_v2.load_content(job)
    concept = next((item for item in content.get("concepts", [])
                    if str(item.get("id") or "") == concept_id), None)
    if concept is None:
        raise ValueError("concept not found")
    prompt = f"teach:{concept_id}"
    cached = study_v2.find_cached_response(job, "teach_me", prompt, [concept_id])
    if cached:
        return {**cached, "cached": True}
    context, _ = _retrieved_context(job, concept.get("title", ""), concept_id=concept_id)
    try:
        result, diagnostics = _call(client, "teach_me", {
            "concept": concept,
            "retrieved_context": context,
        })
    except GatewayError as exc:
        _record_interaction_error(job, "teach_me", exc)
        raise
    normalized = {
        "explanation": _text(result.get("explanation"), 6000),
        "analogy": _text(result.get("analogy"), 4000),
        "check_question": _text(result.get("check_question"), 1200),
        "rubric": _text(result.get("rubric"), 2200),
        **_normalize_interactive_grounding(job, result, [concept_id]),
        "diagnostics": diagnostics,
    }
    if not normalized["explanation"] or not normalized["check_question"]:
        raise StudyContentError("invalid_teach_response", "Study AI did not return a complete teaching step.")
    study_v2.cache_concept_response(job, "teach_me", prompt, [concept_id], normalized)
    return normalized


def grade_short_answer(job, client: GatewayClient, *, question: str,
                       answer: str, rubric: str, concept_ids: list[str]) -> dict[str, Any]:
    answer = _text(answer, 4000)
    if not answer:
        raise ValueError("answer is required")
    context, retrieved_ids = _retrieved_context(
        job, question, concept_id=str((concept_ids or [""])[0]))
    try:
        result, diagnostics = _call(client, "grade_short_answer", {
            "question": _text(question, 1600),
            "student_answer": answer,
            "rubric": _text(rubric, 2400),
            "retrieved_context": context,
        })
    except GatewayError as exc:
        _record_interaction_error(job, "grade_short_answer", exc)
        raise
    try:
        score = max(0.0, min(1.0, float(result.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0
    # The verdict and the score can disagree: a provider returned
    # correct=false with score=1.0, which the UI rendered as the nonsense
    # "Keep working · 100%" next to feedback explaining what was missing.
    # The boolean is the explicit judgement and matched the feedback, so it
    # stays authoritative -- but a number we cannot trust is not shown at all
    # rather than adjusted to fit, which would be inventing a grade.
    correct = bool(result.get("correct", score >= 0.7))
    consistent = correct == (score >= 0.7)
    return {
        "correct": correct,
        "score": score if consistent else None,
        "feedback": _text(result.get("feedback"), 3000),
        "ideal_answer": _text(result.get("ideal_answer"), 3000),
        **_normalize_interactive_grounding(job, result, retrieved_ids),
        "diagnostics": diagnostics,
    }


def _record_interaction_error(job, task: str, error: Exception) -> None:
    content = study_v2.load_content(job)
    metadata = content.setdefault("generation_metadata", {})
    code = str(getattr(error, "code", "study_interaction_failed"))[:80]
    metadata["last_interaction_error"] = {
        "task_type": task,
        "code": code,
        "message": str(error)[:500],
        "diagnostics": sanitize_diagnostics(getattr(error, "diagnostics", {})),
    }
    study_v2.save_content(job, content)


def diagnostics(job) -> dict[str, Any]:
    content = study_v2.load_content(job)
    metadata = content.get("generation_metadata") if isinstance(
        content.get("generation_metadata"), dict) else {}
    raw = dict(metadata.get("diagnostics") or {})
    error = metadata.get("last_error") if isinstance(metadata.get("last_error"), dict) else {}
    if error:
        raw["error_category"] = str(
            error.get("code") or raw.get("error_category") or "")[:80]
    raw["last_successful_stage"] = str(
        metadata.get("last_successful_stage") or raw.get("last_successful_stage") or "")[:160]
    result = sanitize_diagnostics(raw)
    status = str(content.get("study_status") or "")
    stage = str(metadata.get("stage") or "")
    result["study_status"] = status if status in _SAFE_STUDY_STATUSES else ""
    result["generation_stage"] = stage if stage in _SAFE_GENERATION_STAGES else ""
    return result


def affected_concept_ids(job, changed_segment_ids: list[str]) -> list[str]:
    changed = {str(value) for value in changed_segment_ids}
    output = []
    for concept in study_v2.load_content(job).get("concepts", []):
        if any(str(source.get("segment_id") or "") in changed
               for source in concept.get("sources", []) or []):
            concept_id = str(concept.get("id") or "")
            if concept_id and concept_id not in output:
                output.append(concept_id)
    return output


def _partial_state(job, callback: ProgressCallback | None, *, status: str,
                   completed: int, total: int, error: Exception | None = None) -> None:
    content = study_v2.load_content(job)
    metadata = content.setdefault("generation_metadata", {})
    partial = {
        "status": status,
        "completed": completed,
        "total": total,
        "updated_at": study_v2._now_iso(),
    }
    if error is not None:
        code = str(getattr(error, "code", "concept_refresh_failed"))[:80]
        partial["last_error"] = {
            "code": code,
            "message": str(error)[:500],
            "diagnostics": sanitize_diagnostics(getattr(error, "diagnostics", {})),
        }
    metadata["partial_refresh"] = partial
    study_v2.save_content(job, content)
    if callback:
        callback({
            "job_id": getattr(job, "job_id", ""),
            "status": content.get("study_status"),
            "stage": "Refreshing edited concepts" if status == "preparing" else (
                "Edited concepts refreshed" if status == "ready" else "Concept refresh needs attention"),
            "progress_percent": 100 if status == "ready" else round(completed / max(1, total) * 100),
            "refresh_status": status,
        })


def _basic_partial_refresh(job, changed_segment_ids: list[str], *,
                           cancelled: CancelCallback | None = None) -> dict[str, Any]:
    old = study_v2.load_content(job)
    if cancelled and cancelled():
        return old
    affected = set(affected_concept_ids(job, changed_segment_ids))
    if not affected:
        return old
    fresh = study_v2.generate_deterministic_content(job)
    if cancelled and cancelled():
        return study_v2.load_content(job)
    changed = {str(value) for value in changed_segment_ids}
    fresh_ids = {
        str(concept.get("id") or "") for concept in fresh.get("concepts", [])
        if any(str(source.get("segment_id") or "") in changed
               for source in concept.get("sources", []) or [])
    }
    merged = dict(old)
    merged["concepts"] = [
        item for item in old.get("concepts", []) if item.get("id") not in affected
    ] + [item for item in fresh.get("concepts", []) if item.get("id") in fresh_ids]

    def merge_dependents(key: str) -> list[dict[str, Any]]:
        kept = [item for item in old.get(key, [])
                if not affected.intersection(set(item.get("concept_ids", []) or []))]
        added = [item for item in fresh.get(key, [])
                 if fresh_ids.intersection(set(item.get("concept_ids", []) or []))]
        return kept + added

    for key in ("flashcards", "quiz", "study_guide", "teach_me_foundations"):
        merged[key] = merge_dependents(key)
    ordered_ids = [item.get("id") for item in sorted(
        merged["concepts"], key=lambda item: (-int(item.get("importance") or 3), str(item.get("title") or "")))]
    merged["quick_study_material"] = {
        "five_minute": ordered_ids[:3],
        "ten_minute": ordered_ids[:6],
        "twenty_minute": ordered_ids[:10],
        "full": ordered_ids,
    }
    merged["study_status"] = study_v2.STUDY_BASIC
    merged["provider"] = "builtin"
    merged.setdefault("generation_metadata", {})["basic_reason"] = "user_selected"
    merged["generation_metadata"]["partial_refresh"] = {
        "status": "ready", "completed": len(affected), "total": len(affected),
        "updated_at": study_v2._now_iso(),
    }
    if cancelled and cancelled():
        return study_v2.load_content(job)
    study_v2.preserve_mastery_for_replacement(job, old, merged)
    study_v2.save_content(job, merged)
    return study_v2.load_content(job)


def _dependent_items(content: dict[str, Any], key: str, concept_id: str) -> list[dict[str, Any]]:
    return [item for item in content.get(key, [])
            if concept_id in (item.get("concept_ids") or [])]


def _regenerate_one(job, client: GatewayClient, content: dict[str, Any],
                    concept_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    concept = next((item for item in content.get("concepts", [])
                    if str(item.get("id") or "") == concept_id), None)
    if concept is None:
        raise ValueError("concept not found")
    context, _ = _retrieved_context(job, concept.get("title", ""), concept_id=concept_id)
    result, request_diagnostics = _call(client, "regenerate_concept", {
        "concept": concept,
        "dependent_flashcards": _dependent_items(content, "flashcards", concept_id),
        "dependent_quiz": _dependent_items(content, "quiz", concept_id),
        "dependent_study_guide": _dependent_items(content, "study_guide", concept_id),
        "retrieved_context": context,
    })
    raw_concept = result.get("concept") if isinstance(result.get("concept"), dict) else {}
    raw_concept = dict(raw_concept)
    raw_concept["id"] = concept_id
    synthetic = {
        "lecture_summary": content.get("lecture_summary", ""),
        "concepts": [raw_concept],
        "key_terms": [], "people": [], "dates": [], "misconceptions": [],
        "study_guide": result.get("study_guide_fragments") or _dependent_items(content, "study_guide", concept_id),
        "flashcards": result.get("flashcards") or _dependent_items(content, "flashcards", concept_id),
        "quiz": result.get("quiz") or _dependent_items(content, "quiz", concept_id),
        "quick_study_material": {
            "five_minute": [concept_id], "ten_minute": [concept_id],
            "twenty_minute": [concept_id], "full": [concept_id],
        },
        "teach_me_foundations": _dependent_items(content, "teach_me_foundations", concept_id),
    }
    normalized = normalize_generated_content(
        job, synthetic, {"relationships": []},
        content.get("slide_interpretations", []), content.get("enrichment", []))
    replacement = normalized["concepts"][0]
    replacement["id"] = concept_id
    for key in ("flashcards", "quiz", "study_guide", "teach_me_foundations"):
        for item in normalized.get(key, []):
            item["concept_ids"] = [concept_id if value == replacement.get("id") else value
                                   for value in item.get("concept_ids", [])]
            if key == "teach_me_foundations":
                item["concept_id"] = concept_id

    merged = dict(content)
    merged["concepts"] = [
        replacement if item.get("id") == concept_id else item
        for item in content.get("concepts", [])
    ]
    for key in ("flashcards", "quiz", "study_guide", "teach_me_foundations"):
        kept = [item for item in content.get(key, [])
                if concept_id not in (item.get("concept_ids") or [])]
        merged[key] = kept + normalized.get(key, [])
    analysis = dict(merged.get("lecture_analysis") or {})
    analysis["concepts"] = [
        replacement if item.get("id") == concept_id else item
        for item in analysis.get("concepts", [])
    ]
    merged["lecture_analysis"] = analysis
    return merged, request_diagnostics


def regenerate_affected(job, client: GatewayClient,
                        changed_segment_ids: list[str], *,
                        progress: ProgressCallback | None = None,
                        concept_ids: list[str] | None = None,
                        cancelled: CancelCallback | None = None) -> dict[str, Any]:
    """Refresh only concepts whose citations overlap edited transcript rows."""
    content = study_v2.load_content(job)
    if cancelled and cancelled():
        return content
    targets = list(concept_ids or affected_concept_ids(job, changed_segment_ids))
    targets = [value for index, value in enumerate(targets)
               if value and value not in targets[:index]]
    if not targets:
        return content
    if content.get("study_status") == study_v2.STUDY_BASIC:
        result = _basic_partial_refresh(
            job, changed_segment_ids, cancelled=cancelled)
        if cancelled and cancelled():
            return study_v2.load_content(job)
        if progress:
            progress({
                "job_id": getattr(job, "job_id", ""),
                "status": study_v2.STUDY_BASIC,
                "stage": "Edited Basic Study concepts refreshed",
                "progress_percent": 100,
                "refresh_status": "ready",
            })
        return result
    latest_diagnostics: dict[str, Any] = {}
    if cancelled and cancelled():
        return study_v2.load_content(job)
    _partial_state(job, progress, status="preparing", completed=0, total=len(targets))
    try:
        merged = content
        for index, concept_id in enumerate(targets):
            if cancelled and cancelled():
                return study_v2.load_content(job)
            merged, latest_diagnostics = _regenerate_one(
                job, client, merged, str(concept_id))
            if cancelled and cancelled():
                return study_v2.load_content(job)
            _partial_state(
                job, progress, status="preparing",
                completed=index + 1, total=len(targets))
        merged.setdefault("generation_metadata", {})["partial_refresh"] = {
            "status": "ready", "completed": len(targets), "total": len(targets),
            "updated_at": study_v2._now_iso(),
        }
        if cancelled and cancelled():
            return study_v2.load_content(job)
        result = study_v2.replace_ai_content(
            job, merged,
            diagnostics={**latest_diagnostics, "last_successful_stage": "Partial concept regeneration"})
        if cancelled and cancelled():
            return study_v2.load_content(job)
        _partial_state(job, progress, status="ready", completed=len(targets), total=len(targets))
        return result
    except (GatewayError, StudyContentError) as exc:
        if cancelled and cancelled():
            return study_v2.load_content(job)
        _record_interaction_error(job, "regenerate_concept", exc)
        _partial_state(
            job, progress, status="failed", completed=0,
            total=len(targets), error=exc)
        raise
