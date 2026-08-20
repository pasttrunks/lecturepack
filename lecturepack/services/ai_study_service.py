"""AI-first Study orchestration on top of the existing Study V2 persistence.

Local media processing stays local. Only transcript segments, timestamps,
accepted-slide metadata, selected slide images, and compact relationship data
are sent to the LecturePack AI Gateway. The service performs a canonical
lecture-analysis pass followed by a single coherent material-generation pass;
optional vision and web calls are bounded evidence steps between them.
"""
from __future__ import annotations

import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from io import BytesIO
import json
import math
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
# Only true function words belong here. Words that are common in ONE lecture
# but meaningless for telling its concepts apart are handled far better by the
# per-pack IDF in _concept_idf, which adapts to the subject automatically.
_STOPWORDS = frozenset("""
about above after again against all also am an and any are aren't as at be because
been before being below between both but by can cannot could couldn't did didn't do
does doesn't doing don't down during each few for from further had hadn't has hasn't
have haven't having he her here hers herself him himself his how i'm if in into is
isn't it its itself let's may me might more most much must mustn't my myself no nor
not of off on once only or other ought our ours ourselves out over own same shall
shan't she should shouldn't so some such than that that's the their theirs them
themselves then there these they this those through to too under until up us very
was wasn't we were weren't what when where which while who whom why will with won't
would wouldn't you your yours yourself yourselves
""".split())
# Ordered longest-first within each family so the most specific suffix wins.
#
# "est" is deliberately ABSENT. It only ever catches superlatives, which are
# rarely the discriminating word in a question, and it mangles a long tail of
# ordinary nouns that merely end that way: forest -> for, interest -> inter,
# harvest -> harv, invest -> inv, protest -> prot. It also split every one of
# those from its own plural, since the plural takes the "s" branch instead.
_SUFFIXES = (
    "ations", "ation", "ements", "ement", "ments", "ment", "nesses", "ness",
    "ities", "ives", "ive", "ings", "ing", "ers", "ed", "es", "er", "s",
)
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
    # An answer the model itself labels as coming from its own knowledge must
    # not carry lecture citations. Two ways they used to appear:
    #
    #   * inheriting the retrieved concept's sources when the model returned
    #     none -- right for material the lecture DID cover, wrong here; and
    #   * the model attaching a real segment id anyway. Probing the deployed
    #     gateway, "When was Schliemann born?" came back "1822", correctly
    #     marked extra_context, but WITH a lecture source: the segment exists,
    #     so validation passes, and the UI would cite the lecture for a date the
    #     lecture never states.
    #
    # Both are dropped. The declaration is the model's own, so honouring it
    # costs nothing when it is accurate and prevents a false citation when it
    # is not. "mixed" is untouched: it legitimately carries both.
    declared = str(raw.get("provenance") or "").lower()
    if declared == "extra_context":
        lecture = []
    elif not lecture:
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
        vision_requests = analysis.get("vision_requests", []) if isinstance(analysis.get("vision_requests"), list) else []
        vision_jobs = []
        seen_slides = set()
        for item in vision_requests:
            if len(vision_jobs) >= _MAX_VISION_SLIDES or not isinstance(item, dict):
                break
            slide_id = str(item.get("slide_id") or "")
            if slide_id in seen_slides or slide_id not in slide_by_id:
                continue
            image = _slide_data_url(job, slide_id)
            if not image:
                continue
            seen_slides.add(slide_id)
            vision_jobs.append((slide_id, item, image))

        research_requests = analysis.get("research_requests", []) if isinstance(analysis.get("research_requests"), list) else []
        research_jobs = []
        seen_queries = set()
        for item in research_requests:
            if len(research_jobs) >= _MAX_WEB_REQUESTS or not isinstance(item, dict):
                break
            query = _text(item.get("query"), 500)
            if not query or query.casefold() in seen_queries:
                continue
            seen_queries.add(query.casefold())
            research_jobs.append((query, item))

        # Queued work must not dispatch after the user has cancelled. An
        # already-open request cannot be interrupted, but everything still
        # waiting for a pool slot can simply not start -- which is most of the
        # batch, and is what would otherwise keep spending free-tier quota on
        # a job nobody is waiting for.
        def _run_vision(slide_id: str, item: dict[str, Any], image: str):
            if cancelled and cancelled():
                return None, {}
            result, diagnostics = _call(client, "vision_slide", {
                **slide_by_id[slide_id],
                "reason": _text(item.get("reason"), 500),
                "image_data_url": image,
            })
            result["slide_id"] = slide_id
            return result, diagnostics

        def _run_enrichment(query: str, item: dict[str, Any]):
            if cancelled and cancelled():
                return None, {}
            result, diagnostics = _call(client, "web_enrichment", {
                "concept_id": _text(item.get("concept_id"), 80),
                "query": query,
                "reason": _text(item.get("reason"), 500),
            })
            sources = _validated_web_sources(result.get("sources"))
            if not sources:
                return None, diagnostics
            allowed_urls = {source["url"] for source in sources}
            facts = []
            for fact in result.get("facts", []) if isinstance(result.get("facts"), list) else []:
                if not isinstance(fact, dict):
                    continue
                url = _text(fact.get("url"), 2000)
                claim = _text(fact.get("claim"), 1600)
                if url not in allowed_urls or not claim:
                    continue
                fact_source = next(source for source in sources if source["url"] == url)
                facts.append({
                    "claim": claim,
                    "title": _text(fact.get("title"), 300) or fact_source["title"],
                    "url": url,
                })
            return {
                "concept_id": _text(item.get("concept_id"), 80),
                "summary": _text(result.get("summary"), 4000),
                "facts": facts[:12],
                "sources": sources,
            }, diagnostics

        vision_results = []
        enrichment_results = []
        # Both are independent, bounded evidence steps between the canonical
        # analysis and material generation -- running them one network call at
        # a time serialized up to (_MAX_VISION_SLIDES + _MAX_WEB_REQUESTS)
        # round trips. A shared thread pool runs them concurrently instead;
        # each call is still optional, so a GatewayError from one just drops
        # that item rather than the whole batch.
        if (vision_jobs or research_jobs) and not (cancelled and cancelled()):
            _emit(job, progress, "Reading selected lecture slides and checking public context",
                  46, last_successful_stage=last_successful)
            pool = ThreadPoolExecutor(max_workers=len(vision_jobs) + len(research_jobs))
            try:
                futures = {}
                for order, (slide_id, item, image) in enumerate(vision_jobs):
                    futures[pool.submit(_run_vision, slide_id, item, image)] = ("vision", order)
                for order, (query, item) in enumerate(research_jobs):
                    futures[pool.submit(_run_enrichment, query, item)] = ("enrichment", order)
                pending = set(futures)
                collected: list[tuple[str, int, Any]] = []
                while pending:
                    # Bounded waits rather than as_completed, so a user who
                    # cancels mid-flight is not stuck behind the slowest
                    # provider. The old sequential loop checked cancellation
                    # before every call and must not regress to one check.
                    done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
                    for future in done:
                        kind, order = futures[future]
                        try:
                            result, diagnostics = future.result()
                        except GatewayError:
                            # Vision and enrichment are both optional; the
                            # lecture-analysis and material passes remain
                            # valid without any single one of them.
                            continue
                        # A worker that bailed on cancellation returns no
                        # result and empty diagnostics; it must not overwrite
                        # a real route's diagnostics.
                        if result is not None:
                            latest_diagnostics = diagnostics
                            collected.append((kind, order, result))
                    if done:
                        # Without this the bar sat frozen for the whole
                        # evidence phase: the old sequential loops emitted
                        # per item, and collapsing them into one batch
                        # collapsed the progress with it.
                        _emit(job, progress,
                              "Reading selected lecture slides and checking public context",
                              46 + round((len(collected) / max(1, len(futures))) * 14),
                              last_successful_stage=last_successful)
                    if cancelled and cancelled():
                        for future in pending:
                            future.cancel()
                        return study_v2.load_content(job)
                # Completion order is a race. Sorting back to request order
                # keeps the generation prompt -- and therefore the pack --
                # reproducible for identical inputs.
                for kind, _order, result in sorted(
                        collected, key=lambda row: (row[0], row[1])):
                    if kind == "vision":
                        vision_results.append(result)
                        last_successful = "Selected slide interpretation"
                    else:
                        enrichment_results.append(result)
                        last_successful = "Optional web enrichment"
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

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
        # The pack is usable from here. Now grow it, one concept per request,
        # because a student revising cannot use three questions.
        return _expand_material(job, client, final,
                                progress=progress, cancelled=cancelled)
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


def _stem(word: str) -> str:
    """Strip common English suffixes so 'derivatives' and 'derivative' match.

    Deliberately a light heuristic, not a real Porter stemmer: it only has to
    make morphological variants of the SAME word collide within one lecture's
    vocabulary. Over-stemming two genuinely different words into one term costs
    a slightly noisier score, never a wrong answer -- the model still receives
    the concept text and decides for itself.

    Known residue, accepted rather than chased. It is limited to words whose
    stem-minus-"es" itself ends in a sibilant, so the sibilant rule below
    cannot tell a real -es plural from an -e noun plus -s: "case"/"cases" and
    "house"/"houses" still miss. Telling those apart needs a lexicon this does
    not have. The Greek/Latin -sis/-ses family ("analysis"/"analyses") misses
    for the same reason; the obvious "ses" -> "sis" rule was rejected because
    it also rewrites "houses", "cases", "phases", "responses" and "causes"
    into nonsense.
    """
    if len(word) <= 3:
        return word
    if word.endswith(("ies", "ied")) and len(word) > 4:
        return word[:-3] + "i"
    for suffix in _SUFFIXES:
        # A trailing "s" is only a plural marker sometimes. Stripping it from
        # the -ss/-us/-is/-as families breaks core academic vocabulary against
        # its own plural: analysis/analyses, process/processes, class/classes,
        # mass, focus, status, bias, hypothesis.
        if suffix == "s" and word.endswith(("ss", "us", "is", "as")):
            continue
        if not word.endswith(suffix) or len(word) - len(suffix) < 3:
            continue
        if suffix == "es":
            # English adds "-es" only after a sibilant (process/processes,
            # box/boxes, church/churches). Everywhere else the plural is a
            # bare "-s" on a word that already ends in "e", and blindly
            # stripping "es" severed exactly the high-IDF domain nouns this
            # ranker leans on hardest: wave/waves, molecule/molecules,
            # force/forces, state/states, variable/variables, source/sources.
            root = word[:-2]
            word = root if root.endswith(("s", "x", "z", "ch", "sh")) else word[:-1]
            break
        word = word[:-len(suffix)]
        break
    if len(word) >= 4 and word.endswith("y"):
        word = word[:-1] + "i"
    return word


def _terms(text: str) -> list[str]:
    """Tokenize to stemmed, stopword-free terms, preserving order for bigrams.

    The stopword test runs on the ORIGINAL word, never on its stem. Stemming
    first and filtering after silently annihilates real content words whose
    stem happens to collide with a function word -- "forest" -> "for",
    "shoulder" -> "should", "owner" -> "own", "outer" -> "out" -- which does
    not merely add noise, it deletes the most discriminating term in the query
    from both sides of the comparison. A forestry lecture could not be
    searched for "forest".
    """
    output = []
    for word in _WORD_RE.findall(str(text or "")):
        word = word.casefold()
        if word in _STOPWORDS:
            continue
        stem = _stem(word)
        if stem:
            output.append(stem)
    return output


def _bigrams(terms: list[str]) -> set[str]:
    return {f"{left} {right}" for left, right in zip(terms, terms[1:])}


def _concept_idf(documents: list[list[str]]) -> tuple[dict[str, float], float]:
    """Inverse document frequency over THIS pack's concepts.

    The pack is its own corpus, which is what makes this worth doing at ~24
    documents: a word appearing in every concept of a lecture ("cell",
    "market", "Rome") is precisely the word that cannot discriminate between
    them, and no general-purpose stopword list could know that. Function words
    are already removed; this removes the lecture's own boilerplate.
    """
    total = max(1, len(documents))
    frequency: dict[str, int] = {}
    for document in documents:
        for term in set(document):
            frequency[term] = frequency.get(term, 0) + 1
    # A query term absent from every concept is maximally rare, so it must
    # count in full against coverage rather than being silently ignored.
    rarest = math.log(1.0 + total / 1.0)
    return ({term: math.log(1.0 + total / (1.0 + count))
             for term, count in frequency.items()}, rarest)


# A title is the concept's NAME; matching it is stronger evidence than matching
# a word buried in a paragraph of explanation. Previously they scored the same.
_TITLE_WEIGHT = 2.0
_PHRASE_BONUS = 0.5
_MAX_PHRASE_BONUS = 1.0
_RELEVANCE_WEIGHT = 10.0
_PIN_BONUS = 1000.0


def _retrieved_context(job, prompt: str, *, concept_id: str = "") -> tuple[dict[str, Any], list[str]]:
    """Rank the pack's concepts against a prompt and gather their evidence.

    Scoring is IDF-weighted coverage of the query's terms, not raw word
    overlap. The previous version counted set intersection of raw casefolded
    words at 4 points each against an importance term worth at most 5, so a
    single shared filler word ("different", "between") outweighed a full step
    of importance, and a concept could rank top-4 purely on stopword noise.
    """
    content = study_v2.load_content(job)
    concepts = content.get("concepts", [])
    query = _terms(prompt)
    # Order-preserving dedupe: repeating a word must not double its weight.
    query = [term for index, term in enumerate(query) if term not in query[:index]]
    query_bigrams = _bigrams(_terms(prompt))

    titles = [_terms(concept.get("title")) for concept in concepts]
    explanations = [_terms(concept.get("explanation")) for concept in concepts]
    idf, rarest = _concept_idf(
        [title + explanation for title, explanation in zip(titles, explanations)])
    weight = sum(idf.get(term, rarest) for term in query)

    ranked = []
    for index, concept in enumerate(concepts):
        title_terms = set(titles[index])
        body_terms = set(explanations[index])
        relevance = 0.0
        if weight > 0:
            matched = 0.0
            for term in query:
                term_idf = idf.get(term, rarest)
                if term in title_terms:
                    matched += term_idf * _TITLE_WEIGHT
                elif term in body_terms:
                    matched += term_idf
            relevance = matched / weight
        if query_bigrams:
            # Per field, never over the concatenation: joining the two lists
            # manufactures one bigram from the last title word plus the first
            # explanation word, a phrase that appears in no real text.
            phrases = _bigrams(titles[index]) | _bigrams(explanations[index])
            relevance += min(
                _MAX_PHRASE_BONUS,
                len(query_bigrams & phrases) * _PHRASE_BONUS)
        # Importance is normalized to 0..1 so it breaks ties between similarly
        # relevant concepts instead of competing with relevance outright.
        importance = max(1, min(5, int(concept.get("importance") or 3)))
        score = relevance * _RELEVANCE_WEIGHT + (importance - 1) / 4.0
        if concept_id and str(concept.get("id") or "") == concept_id:
            score += _PIN_BONUS
        ranked.append((score, -index, concept))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    # Always up to four, as before: the pinned concept plus neighbours give the
    # model context even when nothing matches lexically.
    selected = [item[2] for item in ranked[:4]]
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
    study_v2.save_content_preserving_cache(job, content)


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
    study_v2.save_content_preserving_cache(job, content)
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
    study_v2.save_content_preserving_cache(job, merged)
    return study_v2.load_content(job)


def _dependent_items(content: dict[str, Any], key: str, concept_id: str) -> list[dict[str, Any]]:
    return [item for item in content.get(key, [])
            if concept_id in (item.get("concept_ids") or [])]


# How much material a lecture should end up with, and the ceiling that keeps
# Quick Study's 5/10/20-minute sessions genuinely different from each other.
EXPAND_CARDS_PER_CONCEPT = 3
EXPAND_QUIZ_PER_CONCEPT = 2
EXPAND_MAX_CARDS = 24
EXPAND_MAX_QUIZ = 20
# How many concepts get their Teach Me answer pre-fetched. Kept well under
# study_v2's 24-entry response cache, which Ask shares.
EXPAND_PREWARM_CONCEPTS = 6


def study_priority_order(concepts: list[dict[str, Any]]) -> list[str]:
    """The order a student meets concepts in: most important, then by title.

    This is the single definition of that order. quick_study_material's
    five/ten/twenty-minute selections and the Teach Me pre-warm must agree on
    it, and previously did not: models rarely spread the `importance` field, so
    in the common case every concept ties and the ONLY thing separating them is
    the tiebreak. Without it the pre-warm picked concepts in normalizer order
    while the student was shown them alphabetically -- so the cache was paid
    for and never hit.
    """
    return [str(item.get("id") or "") for item in sorted(
        concepts,
        key=lambda item: (-max(1, min(5, int(item.get("importance") or 3))),
                          str(item.get("title") or "").casefold()),
    ) if item.get("id")]


def _prewarm_concept_ids(concepts: list[dict[str, Any]], limit: int) -> list[str]:
    return study_priority_order(concepts)[:max(0, limit)]


def _dedup_key(item: dict[str, Any], *fields: str) -> str:
    for field in fields:
        text = _text(item.get(field), 400).strip().casefold()
        if text:
            return " ".join(text.split())
    return ""


def _normalize_expansion(job, raw: dict[str, Any], concept_id: str) -> dict[str, Any]:
    """Validate expansion items through the same path generated content takes.

    Nothing from a provider is trusted here any more than at generation time:
    ids are re-issued, citations are re-validated against the real transcript
    and slides, and anything ungrounded is dropped -- so an appended card
    cannot carry a source the lecture does not have.
    """
    content = study_v2.load_content(job)
    concept = next((item for item in content.get("concepts", [])
                    if str(item.get("id") or "") == concept_id), None)
    if concept is None:
        return {"flashcards": [], "quiz": []}
    # Pin every item to the concept it was written for BEFORE normalising.
    # normalize_generated_content maps concept_ids through its own id table and
    # drops anything unmapped, so a provider-invented id would silently discard
    # the whole expansion and then trip its "no usable material" guard.
    def _pinned(items: Any) -> list[dict[str, Any]]:
        output = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                pinned = dict(item)
                pinned["concept_ids"] = [concept_id]
                output.append(pinned)
        return output

    synthetic = {
        "lecture_summary": content.get("lecture_summary", ""),
        "concepts": [dict(concept)],
        "key_terms": [], "people": [], "dates": [], "misconceptions": [],
        "study_guide": [],
        "flashcards": _pinned(raw.get("flashcards")),
        "quiz": _pinned(raw.get("quiz")),
        "quick_study_material": {
            "five_minute": [concept_id], "ten_minute": [concept_id],
            "twenty_minute": [concept_id], "full": [concept_id],
        },
        "teach_me_foundations": [],
    }
    normalized = normalize_generated_content(
        job, synthetic, {"relationships": []},
        content.get("slide_interpretations", []), content.get("enrichment", []))
    # normalize_generated_content re-issues concept ids; point the new items at
    # the concept they were actually written for.
    for key in ("flashcards", "quiz"):
        for item in normalized.get(key, []):
            item["concept_ids"] = [concept_id]
    return {"flashcards": normalized.get("flashcards", []),
            "quiz": normalized.get("quiz", [])}


def _expand_material(job, client: GatewayClient, content: dict[str, Any], *,
                     progress: ProgressCallback | None = None,
                     cancelled: CancelCallback | None = None) -> dict[str, Any]:
    """Grow a ready Study pack one concept at a time.

    A single generation call returns close to the schema minimum -- typically
    two flashcards and three questions -- which is not a revision pack, and it
    is why the 5/10/20-minute Quick Study sessions all returned the same
    handful of items: the pool was smaller than the smallest target.

    Asking the generator for a bigger pack in ONE call is not an option. Its
    route budget is fixed (50s NVIDIA inside a 175s client deadline), and
    raising the ask past it produced provider_timeout followed by
    provider_invalid_shape from truncated JSON -- Study AI failed outright.

    So the pack grows across SEPARATE requests instead. Each one is a
    regenerate_concept call: its own timeout, its own 3500-token ceiling, and
    small enough that it cannot blow either. This runs AFTER the pack is marked
    ready, so the student can already use it and it fills in behind them; a
    failure here leaves the ready pack untouched rather than failing Study.
    """
    concepts = [str(item.get("id") or "")
                for item in content.get("concepts", []) if item.get("id")]
    if not concepts:
        return content

    seen_cards = {_dedup_key(c, "front") for c in content.get("flashcards", [])}
    seen_quiz = {_dedup_key(q, "question") for q in content.get("quiz", [])}
    added_cards = added_quiz = 0

    # Pre-warm Teach Me for the concepts a student reaches first, NOT for all
    # of them. Warming every concept doubles the request count of this pass
    # against the same free-tier budget that feeds route cooldown, lengthens
    # the pass it runs inside, and is speculative work for concepts that may
    # never be opened. The cap also matters for correctness: study_v2 keeps
    # only the newest 24 cached responses, shared with the Ask cache, so
    # warming a 24-concept pack would evict entries as fast as it wrote them.
    prewarm = set(_prewarm_concept_ids(
        content.get("concepts", []), EXPAND_PREWARM_CONCEPTS))

    for index, concept_id in enumerate(concepts):
        if cancelled and cancelled():
            return study_v2.load_content(job)
        if concept_id in prewarm:
            try:
                # Warm the "Teach Me" cache so a student's click is a local
                # cache hit (study_v2.find_cached_response inside teach_me)
                # instead of a fresh gateway round trip.
                #
                # This MUST run before the load_content below. teach_me caches
                # by loading and re-saving the content file itself, so warming
                # it after the snapshot is taken means the save at the end of
                # this iteration writes the pre-warm content back and silently
                # drops the cache entry that was just written.
                teach_me(job, client, concept_id)
            except Exception:  # noqa: BLE001 - best-effort; never blocks growth
                pass
            if cancelled and cancelled():
                return study_v2.load_content(job)
        content = study_v2.load_content(job)
        have_cards = len(_dependent_items(content, "flashcards", concept_id))
        have_quiz = len(_dependent_items(content, "quiz", concept_id))
        total_cards = len(content.get("flashcards", []))
        total_quiz = len(content.get("quiz", []))
        # Nothing to gain for this concept, or the pack is already full.
        if (have_cards >= EXPAND_CARDS_PER_CONCEPT and have_quiz >= EXPAND_QUIZ_PER_CONCEPT):
            continue
        if total_cards >= EXPAND_MAX_CARDS and total_quiz >= EXPAND_MAX_QUIZ:
            break

        concept = next((item for item in content.get("concepts", [])
                        if str(item.get("id") or "") == concept_id), None)
        if concept is None:
            continue
        context, _ = _retrieved_context(job, concept.get("title", ""), concept_id=concept_id)
        try:
            # NOT regenerate_concept: that rewrites the dependents it is given,
            # so with none it returns none and cannot grow anything. Measured
            # against the live gateway before this task existed: five concepts,
            # +0 cards and +0 questions each.
            raw, _ = _call(client, "expand_concept_material", {
                "concept": concept,
                "existing_flashcards": [
                    {"front": card.get("front", ""), "back": card.get("back", "")}
                    for card in _dependent_items(content, "flashcards", concept_id)],
                "existing_quiz": [
                    {"question": item.get("question", "")}
                    for item in _dependent_items(content, "quiz", concept_id)],
                "retrieved_context": context,
            })
            # Normalisation is inside the try on purpose: it enforces the same
            # whole-pack guards as generation and raises StudyContentError when
            # an expansion is unusable, which must skip a concept rather than
            # tear down a pack that is already ready.
            merged = _normalize_expansion(job, raw, concept_id)
        except Exception:  # noqa: BLE001 - bonus pass over an already-ready pack
            # Deliberately every error class, not just the gateway's. This runs
            # after the pack is marked ready, so the only thing a failure here
            # can achieve is taking away material the student already has.
            continue

        fresh_cards = [card for card in merged.get("flashcards", [])
                       if _dedup_key(card, "front") not in seen_cards]
        fresh_quiz = [item for item in merged.get("quiz", [])
                      if _dedup_key(item, "question") not in seen_quiz]
        if not fresh_cards and not fresh_quiz:
            continue

        for card in fresh_cards[:max(0, EXPAND_MAX_CARDS - total_cards)]:
            seen_cards.add(_dedup_key(card, "front"))
            content.setdefault("flashcards", []).append(card)
            added_cards += 1
        for item in fresh_quiz[:max(0, EXPAND_MAX_QUIZ - total_quiz)]:
            seen_quiz.add(_dedup_key(item, "question"))
            content.setdefault("quiz", []).append(item)
            added_quiz += 1

        study_v2.save_content_preserving_cache(job, content)
        if progress:
            progress({
                "job_id": getattr(job, "job_id", ""),
                "status": study_v2.STUDY_READY,
                "stage": "Adding more practice material",
                "progress_percent": 100,
                # The renderer reloads on refresh_status ready, so each concept
                # appears as it lands instead of all at the end.
                "refresh_status": "ready",
                "expanded": {"flashcards": added_cards, "quiz": added_quiz,
                             "concept": index + 1, "of": len(concepts)},
            })

    return study_v2.load_content(job)


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
