"""
lecturepack.services.transcript_service
========================================

Layered, auditable transcript model for Lecture Pack.

    Layer 1  RAW          Exact whisper.cpp output + metadata. IMMUTABLE.
    Layer 2  NORMALIZED   Deterministic, non-generative cleanup. Preserves the
                          speaker's words, segment ids, and timestamps.
    Layer 3  CONTEXT       Optional, auditable, reversible LLM-assisted repair of
             REPAIR        *likely transcription mistakes*. Never invents names or
                          facts, never summarizes in place, never mutates layers
                          1 or 2.

This module is pure standard library: no PySide6, no OpenCV, and no *mandatory*
network access. The optional OpenAI-compatible provider only uses urllib and is
only touched when a repair is actually requested.
"""

from __future__ import annotations

import json
import re
import hashlib
import difflib
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Iterable, Callable

TRANSCRIPT_SCHEMA_VERSION = 1
DEFAULT_LOW_CONFIDENCE = 0.60
DEFAULT_MIN_SIMILARITY = 0.50


class RawTranscriptImmutableError(RuntimeError):
    """Raised when code attempts to overwrite an existing raw transcript with
    different content."""


# ---------------------------------------------------------------------------
# Layer 1 -- Raw (immutable)
# ---------------------------------------------------------------------------

_SPECIAL_TOKEN = re.compile(r"^\s*(\[_.*_\]|<\|.*\|>)\s*$")


@dataclass
class Token:
    text: str
    t0_ms: int
    t1_ms: int
    p: Optional[float] = None

    def is_special(self) -> bool:
        return bool(_SPECIAL_TOKEN.match(self.text)) or not self.text.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "t0_ms": self.t0_ms, "t1_ms": self.t1_ms, "p": self.p}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Token":
        return Token(d.get("text", ""), int(d.get("t0_ms", 0)),
                     int(d.get("t1_ms", 0)), d.get("p"))


@dataclass
class RawSegment:
    id: int
    t0_ms: int
    t1_ms: int
    text: str
    tokens: List[Token] = field(default_factory=list)

    @property
    def confidence(self) -> Optional[float]:
        """Mean probability across non-special tokens, or None if unavailable."""
        ps = [t.p for t in self.tokens if t.p is not None and not t.is_special()]
        if not ps:
            return None
        return sum(ps) / len(ps)

    @property
    def min_token_p(self) -> Optional[float]:
        """Lowest non-special token probability, or None if unavailable. A very
        low minimum flags a garbled word (often a misheard name) even when the
        segment's mean confidence looks acceptable."""
        ps = [t.p for t in self.tokens if t.p is not None and not t.is_special()]
        return min(ps) if ps else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "t0_ms": self.t0_ms,
            "t1_ms": self.t1_ms,
            "text": self.text,
            "tokens": [t.to_dict() for t in self.tokens],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RawSegment":
        return RawSegment(
            int(d["id"]), int(d["t0_ms"]), int(d["t1_ms"]), d.get("text", ""),
            [Token.from_dict(t) for t in d.get("tokens", [])],
        )


@dataclass
class RawTranscript:
    """Layer 1. Treat as read-only after construction."""
    language: str
    segments: List[RawSegment]
    meta: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = TRANSCRIPT_SCHEMA_VERSION
    source_raw: Dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Stable hash over the linguistically meaningful raw content. Used to
        prove the raw layer was never modified by later stages."""
        payload = json.dumps(
            [[s.id, s.t0_ms, s.t1_ms, s.text] for s in self.segments],
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "language": self.language,
            "meta": self.meta,
            "content_hash": self.content_hash(),
            "segments": [s.to_dict() for s in self.segments],
            "source_raw": self.source_raw,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RawTranscript":
        return RawTranscript(
            language=d.get("language", ""),
            segments=[RawSegment.from_dict(s) for s in d.get("segments", [])],
            meta=d.get("meta", {}),
            schema_version=int(d.get("schema_version", TRANSCRIPT_SCHEMA_VERSION)),
            source_raw=d.get("source_raw", {}),
        )


def _ts_to_ms(value: Any) -> int:
    """Accept an int ms offset or a 'HH:MM:SS,mmm' timestamp string."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", value.strip())
        if m:
            h, mi, s, ms = (int(x) for x in m.groups())
            return ((h * 3600 + mi * 60 + s) * 1000) + ms
    return 0


def parse_raw_whisper_json(data: Dict[str, Any],
                           meta: Optional[Dict[str, Any]] = None) -> RawTranscript:
    """Parse a whisper.cpp JSON payload into an immutable RawTranscript.

    Handles both real whisper.cpp ``--output-json-full`` (top-level
    ``transcription`` with per-token ``tokens``/``p``) and the reduced
    ``result.transcription`` shape used by some builds and the test mock.
    """
    if not isinstance(data, dict):
        raise ValueError("whisper JSON payload must be an object")

    trans = data.get("transcription")
    if trans is None:
        trans = data.get("result", {}).get("transcription", [])
    if not isinstance(trans, list):
        trans = []

    language = (
        data.get("result", {}).get("language")
        or data.get("params", {}).get("language")
        or ""
    )

    segments: List[RawSegment] = []
    for idx, seg in enumerate(trans):
        offsets = seg.get("offsets", {}) or {}
        stamps = seg.get("timestamps", {}) or {}
        t0 = _ts_to_ms(offsets.get("from", stamps.get("from", 0)))
        t1 = _ts_to_ms(offsets.get("to", stamps.get("to", t0)))
        tokens: List[Token] = []
        for tk in seg.get("tokens", []) or []:
            toff = tk.get("offsets", {}) or {}
            tokens.append(Token(
                text=tk.get("text", ""),
                t0_ms=_ts_to_ms(toff.get("from", t0)),
                t1_ms=_ts_to_ms(toff.get("to", t1)),
                p=tk.get("p", tk.get("probability")),
            ))
        segments.append(RawSegment(id=idx, t0_ms=t0, t1_ms=t1,
                                   text=seg.get("text", ""), tokens=tokens))

    return RawTranscript(language=language, segments=segments,
                         meta=dict(meta or {}), source_raw=data)


# ---------------------------------------------------------------------------
# Layer 2 -- Normalized (deterministic, non-generative)
# ---------------------------------------------------------------------------

@dataclass
class NormalizedSegment:
    id: int
    t0_ms: int
    t1_ms: int
    text: str
    source_ids: List[int] = field(default_factory=list)
    confidence: Optional[float] = None
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NormalizedSegment":
        return NormalizedSegment(
            int(d["id"]), int(d["t0_ms"]), int(d["t1_ms"]), d.get("text", ""),
            list(d.get("source_ids", [])), d.get("confidence"),
            list(d.get("flags", [])),
        )


@dataclass
class NormalizedTranscript:
    language: str
    segments: List[NormalizedSegment]
    paragraphs: List[List[int]] = field(default_factory=list)
    raw_content_hash: str = ""
    schema_version: int = TRANSCRIPT_SCHEMA_VERSION

    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "language": self.language,
            "raw_content_hash": self.raw_content_hash,
            "paragraphs": self.paragraphs,
            "segments": [s.to_dict() for s in self.segments],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NormalizedTranscript":
        return NormalizedTranscript(
            language=d.get("language", ""),
            segments=[NormalizedSegment.from_dict(s) for s in d.get("segments", [])],
            paragraphs=[list(p) for p in d.get("paragraphs", [])],
            raw_content_hash=d.get("raw_content_hash", ""),
            schema_version=int(d.get("schema_version", TRANSCRIPT_SCHEMA_VERSION)),
        )


_WS = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_MULTI_PUNCT = re.compile(r"([,.;:!?])\1{2,}")
_WORD = re.compile(r"\w+|[^\w\s]", re.UNICODE)
# A word (loop candidate) repeated 3+ times in a row.
_LOOP = re.compile(r"\b(\w+)((?:\s+\1\b){2,})", re.IGNORECASE)


def _collapse_intra_loops(text: str, max_repeat: int = 2) -> str:
    """Collapse a run of an identical word repeated more than ``max_repeat``
    times (a classic whisper hallucination loop, e.g. 'you you you you' -> 'you
    you'). Operates by targeted substitution so surrounding punctuation, spacing
    and contractions such as "today's" or tokens like "O(n)" are left untouched.
    Nothing is invented or reworded."""
    def repl(m: "re.Match") -> str:
        first = m.group(1)
        return " ".join([first] * max_repeat)

    prev = None
    out = text
    while prev != out:
        prev = out
        out = _LOOP.sub(repl, out)
    return out


def _clean_text(text: str) -> str:
    t = text.strip()
    t = _WS.sub(" ", t)
    t = _SPACE_BEFORE_PUNCT.sub(r"\1", t)
    t = _MULTI_PUNCT.sub(r"\1", t)
    t = _collapse_intra_loops(t)
    t = _WS.sub(" ", t).strip()
    return t


def normalize_transcript(raw: RawTranscript,
                         low_confidence: float = DEFAULT_LOW_CONFIDENCE,
                         min_token_confidence: float = 0.40,
                         pause_gap_ms: int = 2500) -> NormalizedTranscript:
    """Produce the deterministic normalized layer.

    Guarantees:
      * Never changes a word, name, number or fact.
      * Only cleans whitespace/punctuation, collapses consecutive hallucination
        loops, and merges *exact consecutive duplicate* segments.
      * Preserves original segment ids (via ``source_ids``) and timestamps.
    """
    norm: List[NormalizedSegment] = []
    for seg in raw.segments:
        cleaned = _clean_text(seg.text)
        if not cleaned:
            continue

        conf = seg.confidence
        low_min = seg.min_token_p
        flags: List[str] = []
        if (conf is not None and conf < low_confidence) or \
                (low_min is not None and low_min < min_token_confidence):
            flags.append("low_confidence")
        if _collapse_intra_loops(seg.text) != seg.text:
            flags.append("loop_cleaned")

        prev = norm[-1] if norm else None
        if prev is not None and prev.text.lower() == cleaned.lower():
            prev.t1_ms = max(prev.t1_ms, seg.t1_ms)
            prev.source_ids.append(seg.id)
            if "dup_merged" not in prev.flags:
                prev.flags.append("dup_merged")
            continue

        norm.append(NormalizedSegment(
            id=seg.id, t0_ms=seg.t0_ms, t1_ms=seg.t1_ms, text=cleaned,
            source_ids=[seg.id], confidence=conf, flags=flags,
        ))

    paragraphs: List[List[int]] = []
    current: List[int] = []
    for i, seg in enumerate(norm):
        current.append(seg.id)
        gap = 0
        if i + 1 < len(norm):
            gap = norm[i + 1].t0_ms - seg.t1_ms
        ends_sentence = seg.text.endswith((".", "!", "?"))
        if gap >= pause_gap_ms or (ends_sentence and gap >= 800):
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    return NormalizedTranscript(
        language=raw.language, segments=norm, paragraphs=paragraphs,
        raw_content_hash=raw.content_hash(),
    )


# ---------------------------------------------------------------------------
# Context & Names (deterministic proposal, no LLM)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "The", "A", "An", "And", "But", "Or", "So", "In", "On", "At", "To", "Of",
    "For", "With", "As", "By", "We", "You", "I", "He", "She", "It", "They",
    "This", "That", "These", "Those", "Here", "There", "Now", "Then", "Thank",
    "Today", "Let", "Our", "My", "Your", "Their", "His", "Her", "Its", "Hello",
    "When", "While", "Will", "Welcome",
}
_CAP_TOKEN = re.compile(r"\b([A-Z][A-Za-z][A-Za-z'\-]+)\b")


@dataclass
class EntityCandidate:
    term: str
    count: int
    evidence: str  # "filename", "repeated", or "filename+repeated"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def propose_entity_candidates(norm: NormalizedTranscript,
                              filename: str = "",
                              min_count: int = 2) -> List[EntityCandidate]:
    """Deterministically propose likely proper-noun/topic terms from repeated
    capitalized transcript tokens and the source filename. These are *proposals*
    for the Context & Names panel -- shown to the user for approval and never
    auto-applied to the transcript."""
    counts: Dict[str, int] = {}
    for seg in norm.segments:
        for m in _CAP_TOKEN.findall(seg.text):
            if m in _STOPWORDS:
                continue
            counts[m] = counts.get(m, 0) + 1

    file_terms = set()
    if filename:
        base = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
        for tok in re.split(r"[^A-Za-z0-9]+", base):
            if len(tok) >= 3 and tok[:1].isupper() and tok not in _STOPWORDS:
                file_terms.add(tok)

    out: List[EntityCandidate] = []
    seen = set()
    for term, c in counts.items():
        if c >= min_count or term in file_terms:
            ev = "repeated" if c >= min_count else ""
            if term in file_terms:
                ev = (ev + "+filename").strip("+") if ev else "filename"
            out.append(EntityCandidate(term=term, count=c, evidence=ev))
            seen.add(term.lower())
    for term in file_terms:
        if term.lower() not in seen:
            out.append(EntityCandidate(term=term, count=0, evidence="filename"))
    out.sort(key=lambda e: (-e.count, e.term.lower()))
    return out


def build_whisper_prompt(course_title: str = "",
                         names: Optional[Iterable[str]] = None,
                         glossary: str = "",
                         max_words: int = 150) -> str:
    """Build a sanitized, length-limited initial prompt for whisper.cpp from
    approved context. Mirrors WhisperWrapper sanitization so callers can preview
    exactly what will be passed to ``--prompt``."""
    parts: List[str] = []
    if course_title:
        parts.append(course_title)
    if names:
        parts.append(", ".join(str(n) for n in names))
    if glossary:
        parts.append(glossary)
    raw = ". ".join(p for p in parts if p).strip()
    sanitized = "".join(c for c in raw if c.isalnum() or c in " ,.-_'")
    words = sanitized.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words).strip()


# ---------------------------------------------------------------------------
# Layer 3 -- Context Repair (optional, auditable, reversible)
# ---------------------------------------------------------------------------

@dataclass
class Correction:
    segment_id: int
    original_text: str
    corrected_text: str
    reason: str = ""
    confidence: float = 0.0
    status: str = "proposed"   # proposed | accepted | rejected | needs_review
    source: str = "context_repair"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Correction":
        return Correction(
            int(d["segment_id"]), d.get("original_text", ""),
            d.get("corrected_text", ""), d.get("reason", ""),
            float(d.get("confidence", 0.0)), d.get("status", "proposed"),
            d.get("source", "context_repair"),
        )


class CorrectionSet:
    """A reversible set of proposed corrections over a normalized transcript.

    The normalized layer is never mutated. ``reviewed_segments`` returns a fresh
    view where only ACCEPTED corrections are applied, so rejecting a correction
    is a pure no-op and the original text is always recoverable."""

    def __init__(self, corrections: Optional[List[Correction]] = None):
        self.corrections: List[Correction] = corrections or []

    def _by_segment(self, segment_id: int) -> List[Correction]:
        return [c for c in self.corrections if c.segment_id == segment_id]

    def accept(self, segment_id: int) -> None:
        for c in self._by_segment(segment_id):
            if c.status in ("proposed", "needs_review", "rejected"):
                c.status = "accepted"

    def reject(self, segment_id: int) -> None:
        for c in self._by_segment(segment_id):
            c.status = "rejected"

    def accept_all(self, include_needs_review: bool = False) -> None:
        for c in self.corrections:
            if c.status == "proposed" or (include_needs_review and c.status == "needs_review"):
                c.status = "accepted"

    def reject_all(self) -> None:
        for c in self.corrections:
            c.status = "rejected"

    def reviewed_segments(self, norm: NormalizedTranscript) -> List[NormalizedSegment]:
        """Return normalized segments with only accepted corrections applied.
        Does not mutate ``norm``."""
        accepted = {c.segment_id: c for c in self.corrections if c.status == "accepted"}
        out: List[NormalizedSegment] = []
        for seg in norm.segments:
            text = seg.text
            flags = list(seg.flags)
            if seg.id in accepted:
                text = accepted[seg.id].corrected_text
                flags.append("context_repaired")
            out.append(NormalizedSegment(seg.id, seg.t0_ms, seg.t1_ms, text,
                                         list(seg.source_ids), seg.confidence, flags))
        return out

    def pending(self) -> List[Correction]:
        return [c for c in self.corrections if c.status in ("proposed", "needs_review")]

    def to_dict(self) -> Dict[str, Any]:
        return {"schema_version": TRANSCRIPT_SCHEMA_VERSION,
                "corrections": [c.to_dict() for c in self.corrections]}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CorrectionSet":
        return CorrectionSet([Correction.from_dict(c) for c in d.get("corrections", [])])


LLMComplete = Callable[[str, str], str]


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible chat client for a *local* endpoint such as
    LM Studio or Ollama (``/v1/chat/completions``). Uses only urllib. Entirely
    optional -- the app is fully functional with no provider configured."""

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None,
                 timeout: float = 60.0, temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        import urllib.request
        url = self.base_url + "/v1/chat/completions"
        body = json.dumps({
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


SYSTEM_PROMPT = (
    "You correct speech-to-text transcription errors. You are given numbered "
    "transcript segments. For each segment that contains a LIKELY TRANSCRIPTION "
    "MISTAKE (a misheard word, a wrong homophone, a garbled proper noun that "
    "matches the provided context/glossary), return a correction.\n"
    "STRICT RULES:\n"
    "1. Preserve the speaker's meaning and wording. Fix only mishearings.\n"
    "2. NEVER invent names, facts, dates, numbers, or statements.\n"
    "3. NEVER summarize, shorten, translate, or rephrase for style.\n"
    "4. Only use proper nouns that appear in the provided Approved Names/Glossary "
    "or already in the segment.\n"
    "5. Keep segment ids and timestamps unchanged.\n"
    "6. If a segment is fine, do not return a correction for it.\n"
    "Respond with STRICT JSON only, no prose, in this exact shape:\n"
    '{"corrections":[{"segment_id":<int>,"corrected_text":<str>,'
    '"reason":<str>,"confidence":<0..1>}]}'
)


@dataclass
class RepairConfig:
    chunk_size: int = 12
    overlap: int = 2
    min_similarity: float = DEFAULT_MIN_SIMILARITY
    low_confidence_only: bool = False


class ContextRepairEngine:
    """Builds prompts, calls the (optional) provider, and validates responses
    into a reversible CorrectionSet. All safety guardrails live in
    ``parse_and_validate`` so they are unit-testable without any network."""

    def __init__(self, provider: Optional[Any] = None,
                 approved_names: Optional[Iterable[str]] = None,
                 course_title: str = "", glossary: str = "",
                 config: Optional[RepairConfig] = None):
        self.provider = provider
        self.approved_names = {n.strip() for n in (approved_names or []) if n.strip()}
        self.course_title = course_title
        self.glossary = glossary
        self.config = config or RepairConfig()

    def _allowed_vocab(self, original_text: str) -> set:
        allowed = {w.lower() for w in _WORD.findall(original_text)}
        for n in self.approved_names:
            for w in _WORD.findall(n):
                allowed.add(w.lower())
        for w in _WORD.findall(self.glossary):
            allowed.add(w.lower())
        return allowed

    def build_user_prompt(self, segments: List[NormalizedSegment]) -> str:
        lines = []
        if self.course_title:
            lines.append(f"Topic/Course: {self.course_title}")
        approved = sorted(self.approved_names)
        if approved:
            lines.append("Approved Names: " + ", ".join(approved))
        if self.glossary:
            lines.append("Glossary: " + self.glossary)
        lines.append("Segments:")
        for s in segments:
            lines.append(f"[{s.id}] {s.text}")
        return "\n".join(lines)

    def chunk(self, norm: NormalizedTranscript) -> List[List[NormalizedSegment]]:
        segs = norm.segments
        size = max(1, self.config.chunk_size)
        overlap = max(0, min(self.config.overlap, size - 1))
        chunks: List[List[NormalizedSegment]] = []
        i = 0
        while i < len(segs):
            chunks.append(segs[i:i + size])
            if i + size >= len(segs):
                break
            i += size - overlap
        return chunks

    def parse_and_validate(self, response_text: str,
                           segment_index: Dict[int, NormalizedSegment]) -> List[Correction]:
        """Parse a provider response into validated Corrections.

        Rejects, safely and silently, anything that is not valid JSON in the
        expected shape, references an unknown segment id, is a no-op/empty, or is
        a wild rewrite (length / similarity guard); and downgrades to
        ``needs_review`` any correction introducing a proper-noun-like token not
        present in the original or approved lists.
        """
        out: List[Correction] = []
        try:
            data = json.loads(response_text)
        except (ValueError, TypeError):
            return out
        if not isinstance(data, dict):
            return out
        items = data.get("corrections")
        if not isinstance(items, list):
            return out

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                seg_id = int(item["segment_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if seg_id not in segment_index:
                continue
            corrected = item.get("corrected_text")
            if not isinstance(corrected, str) or not corrected.strip():
                continue

            original = segment_index[seg_id].text
            corrected = corrected.strip()
            if corrected == original:
                continue

            ol = max(1, len(original))
            if not (0.4 * ol <= len(corrected) <= 2.5 * ol):
                continue

            ratio = difflib.SequenceMatcher(
                None, original.lower(), corrected.lower()).ratio()
            if ratio < self.config.min_similarity:
                continue

            reason = item.get("reason", "")
            reason = reason if isinstance(reason, str) else ""
            try:
                conf = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            conf = max(0.0, min(1.0, conf))

            allowed = self._allowed_vocab(original)
            status = "proposed"
            for cap in _CAP_TOKEN.findall(corrected):
                if cap in _STOPWORDS:
                    continue
                if cap.lower() not in allowed and cap not in self.approved_names:
                    status = "needs_review"
                    break

            out.append(Correction(
                segment_id=seg_id, original_text=original,
                corrected_text=corrected, reason=reason, confidence=conf,
                status=status,
            ))
        return out

    def propose(self, norm: NormalizedTranscript) -> CorrectionSet:
        """Run the full repair pass. Requires a provider. Returns a
        CorrectionSet of proposals; nothing is applied automatically."""
        if self.provider is None:
            raise RuntimeError("Context Repair requires a configured LLM provider")
        all_corr: List[Correction] = []
        for chunk in self.chunk(norm):
            index = {s.id: s for s in chunk}
            user = self.build_user_prompt(chunk)
            try:
                resp = self.provider.complete(SYSTEM_PROMPT, user)
            except Exception:
                continue
            all_corr.extend(self.parse_and_validate(resp, index))
        best: Dict[int, Correction] = {}
        for c in all_corr:
            if c.segment_id not in best or c.confidence > best[c.segment_id].confidence:
                best[c.segment_id] = c
        return CorrectionSet(sorted(best.values(), key=lambda c: c.segment_id))
