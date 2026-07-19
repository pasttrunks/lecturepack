"""
lecturepack.services.transcript_formats
========================================

Deterministic serializers and semantic-section grouping shared by the transcript
workspace UI, the export service, and the packaged acceptance driver. Pure
standard library (no Qt / OpenCV) so it is fully unit-testable and reusable
inside the frozen app.

Segment shape used throughout is the plain dict:

    {"id": int, "start": float_seconds, "end": float_seconds, "text": str}

Chronological order is always preserved: every serializer sorts by (start, id)
before emitting, so copying a multi-slide / multi-segment selection is stable.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import List, Dict, Any, Optional


# --------------------------------------------------------------------------- #
# Timestamp helpers
# --------------------------------------------------------------------------- #

def _clamp(seconds: float) -> float:
    try:
        return max(0.0, float(seconds))
    except (TypeError, ValueError):
        return 0.0


def fmt_clock(seconds: float) -> str:
    """H:MM:SS style used for headings / markdown."""
    s = int(_clamp(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}"


def fmt_clock_ms(seconds: float) -> str:
    """HH:MM:SS.mmm style matching the app's historical plain-text transcript."""
    s = _clamp(seconds)
    whole = int(s)
    ms = int(round((s - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    h, rem = divmod(whole, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"


def fmt_srt(seconds: float) -> str:
    s = _clamp(seconds)
    whole = int(s)
    ms = int(round((s - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    h, rem = divmod(whole, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def fmt_vtt(seconds: float) -> str:
    return fmt_srt(seconds).replace(",", ".")


def normalize_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a cleaned, chronologically ordered copy with numeric start/end."""
    out = []
    for i, seg in enumerate(segments):
        out.append({
            "id": int(seg.get("id", i + 1)),
            "start": _clamp(seg.get("start", 0.0)),
            "end": _clamp(seg.get("end", seg.get("start", 0.0))),
            "text": (seg.get("text") or "").strip(),
        })
    out.sort(key=lambda s: (s["start"], s["id"]))
    return out


# --------------------------------------------------------------------------- #
# Serializers  (segments -> string)
# --------------------------------------------------------------------------- #

def to_plain(segments, include_timestamps: bool = True) -> str:
    """Plain text, one segment per line. With timestamps the historical
    ``[HH:MM:SS.mmm -> HH:MM:SS.mmm] text`` range format is preserved."""
    segs = normalize_segments(segments)
    lines = []
    for s in segs:
        if include_timestamps:
            end = s["end"] if s["end"] > s["start"] else s["start"]
            lines.append(f"[{fmt_clock_ms(s['start'])} -> {fmt_clock_ms(end)}] {s['text']}")
        else:
            lines.append(s["text"])
    return "\n".join(lines).strip()


def to_markdown(segments, include_timestamps: bool = True, title: Optional[str] = None) -> str:
    segs = normalize_segments(segments)
    lines = []
    if title:
        lines.append(f"# {title}\n")
    for s in segs:
        if include_timestamps:
            lines.append(f"- **[{fmt_clock(s['start'])}]** {s['text']}")
        else:
            lines.append(f"- {s['text']}")
    return "\n".join(lines).strip() + "\n"


def to_json(segments, include_timestamps: bool = True) -> str:
    segs = normalize_segments(segments)
    if not include_timestamps:
        segs = [{"id": s["id"], "text": s["text"]} for s in segs]
    return json.dumps(segs, ensure_ascii=False, indent=2)


def to_jsonl(segments, include_timestamps: bool = True) -> str:
    segs = normalize_segments(segments)
    rows = []
    for s in segs:
        row = s if include_timestamps else {"id": s["id"], "text": s["text"]}
        rows.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(rows) + ("\n" if rows else "")


def to_csv(segments, include_timestamps: bool = True) -> str:
    segs = normalize_segments(segments)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if include_timestamps:
        writer.writerow(["id", "start_sec", "end_sec", "start_clock", "text"])
        for s in segs:
            writer.writerow([s["id"], f"{s['start']:.3f}", f"{s['end']:.3f}",
                             fmt_clock(s["start"]), s["text"]])
    else:
        writer.writerow(["id", "text"])
        for s in segs:
            writer.writerow([s["id"], s["text"]])
    return buf.getvalue()


def to_srt(segments, include_timestamps: bool = True) -> str:
    segs = normalize_segments(segments)
    out = []
    for i, s in enumerate(segs, start=1):
        end = s["end"] if s["end"] > s["start"] else s["start"] + 2.0
        out.append(f"{i}\n{fmt_srt(s['start'])} --> {fmt_srt(end)}\n{s['text']}\n")
    return "\n".join(out)


def to_vtt(segments, include_timestamps: bool = True) -> str:
    segs = normalize_segments(segments)
    out = ["WEBVTT", ""]
    for i, s in enumerate(segs, start=1):
        end = s["end"] if s["end"] > s["start"] else s["start"] + 2.0
        out.append(f"{i}")
        out.append(f"{fmt_vtt(s['start'])} --> {fmt_vtt(end)}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out).strip() + "\n"


# Format registry: name -> (serializer, file extension)
FORMATTERS = {
    "txt": (to_plain, ".txt"),
    "markdown": (to_markdown, ".md"),
    "json": (to_json, ".json"),
    "jsonl": (to_jsonl, ".jsonl"),
    "csv": (to_csv, ".csv"),
    "srt": (to_srt, ".srt"),
    "vtt": (to_vtt, ".vtt"),
}


def serialize(fmt: str, segments, include_timestamps: bool = True) -> str:
    if fmt not in FORMATTERS:
        raise ValueError(f"unknown transcript format: {fmt}")
    func, _ext = FORMATTERS[fmt]
    return func(segments, include_timestamps=include_timestamps)


# --------------------------------------------------------------------------- #
# Semantic sections
# --------------------------------------------------------------------------- #

_HEADING_STOP = {
    "the", "a", "an", "and", "but", "or", "so", "to", "of", "in", "on", "at",
    "we", "you", "i", "it", "is", "are", "this", "that", "here", "there", "now",
    "then", "well", "okay", "ok", "um", "uh", "so", "just", "like",
}


def _derive_heading(segments: List[Dict[str, Any]], fallback: str) -> str:
    """A short, deterministic topic label from the section's first content words.
    Never invented -- taken verbatim from the transcript, trimmed to a few words."""
    text = " ".join(s.get("text", "") for s in segments).strip()
    words = re.findall(r"[A-Za-z0-9'\-]+", text)
    if not words:
        return fallback
    keep = []
    for w in words:
        keep.append(w)
        if len(keep) >= 6:
            break
    label = " ".join(keep)
    return label + ("…" if len(words) > len(keep) else "")


def build_sections(aligned_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group the aligned slide/transcript data into readable sections -- one per
    slide interval. Each section carries a heading, start/end time, the slide it
    belongs to, and its (chronologically ordered) segments.

    ``aligned_data`` is the structure ExportService writes to ``aligned.json``:
    a list of ``{slide_index, timestamp_seconds, timestamp_formatted,
    image_filename, segments:[{id,start,end,text}]}``.
    """
    sections = []
    for entry in aligned_data:
        segs = normalize_segments([
            s for s in entry.get("segments", []) if int(s.get("id", 0)) != -1
        ])
        start = entry.get("timestamp_seconds", segs[0]["start"] if segs else 0.0)
        end = segs[-1]["end"] if segs else start
        heading = _derive_heading(segs, f"Slide {entry.get('slide_index', '?')}")
        sections.append({
            "index": entry.get("slide_index"),
            "heading": heading,
            "start": _clamp(start),
            "end": _clamp(end),
            "slide_index": entry.get("slide_index"),
            "timestamp_formatted": entry.get("timestamp_formatted", fmt_clock(start)),
            "image_filename": entry.get("image_filename", ""),
            "segments": segs,
        })
    return sections


def sections_to_markdown(sections: List[Dict[str, Any]], include_timestamps: bool = True,
                         title: str = "Lecture Transcript") -> str:
    lines = [f"# {title}", ""]
    for sec in sections:
        rng = f" ({fmt_clock(sec['start'])}–{fmt_clock(sec['end'])})" if include_timestamps else ""
        lines.append(f"## Slide {sec['slide_index']}: {sec['heading']}{rng}")
        lines.append("")
        for s in sec["segments"]:
            if include_timestamps:
                lines.append(f"- **[{fmt_clock(s['start'])}]** {s['text']}")
            else:
                lines.append(f"- {s['text']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def search_segments(segments: List[Dict[str, Any]], query: str) -> List[int]:
    """Return the indices (into the normalized list) of segments containing the
    case-insensitive query. Used by the transcript search box."""
    q = (query or "").strip().lower()
    if not q:
        return []
    segs = normalize_segments(segments)
    return [i for i, s in enumerate(segs) if q in s["text"].lower()]
