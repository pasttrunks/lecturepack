"""
lecturepack.services.transcript_store
=====================================

Single home for reading transcript layers and for the *working layer* the
Transcript workspace edits (v1.1, Phase 3).

Layers on disk (job transcript dir):

    raw.json           Layer 1, immutable whisper.cpp output (never written)
    normalized.json    Layer 2, deterministic cleanup (never written here)
    edited.json        v1.0 text-override map {raw_id: text}. Still written
                       for backward compatibility with existing jobs, tests
                       and the review pane.
    working.json       v1.1 structural working layer: a full segment list
                       supporting split/merge/edit while every segment keeps
                       its raw origin ids. Chronological order is invariant.

All operations are pure functions over plain segment dicts:

    {"id": int, "start": float, "end": float, "text": str,
     "origin_ids": [int, ...], "edited": bool}

so undo/redo is a list-snapshot stack and everything is unit-testable
without Qt.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from lecturepack.infrastructure.file_manager import FileManager

WORKING_SCHEMA_VERSION = 2


# --------------------------------------------------------------------------- #
# Raw layer access (shared by UI + exports; previously duplicated)
# --------------------------------------------------------------------------- #

def load_raw_segments(job_paths: dict) -> List[dict]:
    """Parse raw.json (whisper.cpp) into plain segments; falls back to
    raw.txt. Raw ids are 1-based positions, matching the historical UI."""
    transcript_dir = job_paths["transcript"]
    raw_path = os.path.join(transcript_dir, "raw.json")
    data = FileManager.read_json_safe(raw_path, {})
    segments: List[dict] = []
    if isinstance(data, dict):
        transcription = data.get("result", {}).get("transcription", [])
        if not transcription and "transcription" in data:
            transcription = data["transcription"]
        for i, seg in enumerate(transcription or []):
            offsets = seg.get("offsets", {}) or {}
            segments.append({
                "id": i + 1,
                "start": offsets.get("from", 0) / 1000.0,
                "end": offsets.get("to", 0) / 1000.0,
                "text": (seg.get("text") or "").strip(),
            })
    if not segments:
        raw_txt = os.path.join(transcript_dir, "raw.txt")
        if os.path.exists(raw_txt):
            with open(raw_txt, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not (line.startswith("[") and "->" in line):
                        continue
                    try:
                        ts_part, text_part = line.split("]", 1)
                        t1, t2 = ts_part[1:].split("->")

                        def to_sec(s):
                            h, m, sec = s.strip().split(":")
                            return int(h) * 3600 + int(m) * 60 + float(sec)

                        segments.append({
                            "id": i + 1, "start": to_sec(t1), "end": to_sec(t2),
                            "text": text_part.strip(),
                        })
                    except Exception:
                        continue
    segments.sort(key=lambda s: (s["start"], s["id"]))
    return segments


def load_edited_overrides(job_paths: dict) -> Dict[str, str]:
    return FileManager.read_json_safe(
        os.path.join(job_paths["transcript"], "edited.json"), {}) or {}


def load_segment_confidence(job_paths: dict) -> Dict[int, Optional[float]]:
    """Per-raw-segment confidence from normalized.json (raw ids)."""
    norm = FileManager.read_json_safe(
        os.path.join(job_paths["transcript"], "normalized.json"), {}) or {}
    out: Dict[int, Optional[float]] = {}
    for seg in norm.get("segments", []):
        conf = seg.get("confidence")
        for rid in seg.get("source_ids", [seg.get("id")]):
            # normalized ids are 0-based whisper ids; the UI raw layer is
            # 1-based -- map accordingly.
            out[int(rid) + 1] = conf
    return out


# --------------------------------------------------------------------------- #
# Working layer
# --------------------------------------------------------------------------- #

def _working_path(job_paths: dict) -> str:
    return os.path.join(job_paths["transcript"], "working.json")


def derive_working_from_raw(raw_segments: List[dict],
                            edited: Optional[Dict[str, str]] = None) -> List[dict]:
    edited = edited or {}
    out = []
    for seg in raw_segments:
        text = edited.get(str(seg["id"]), seg["text"])
        out.append({
            "id": seg["id"], "start": seg["start"], "end": seg["end"],
            "text": text, "origin_ids": [seg["id"]],
            "edited": str(seg["id"]) in edited,
        })
    return out


def load_working(job_paths: dict) -> List[dict]:
    """The working layer, deriving it from raw (+v1.0 edited.json) when no
    working.json exists yet. Old jobs therefore load unchanged."""
    data = FileManager.read_json_safe(_working_path(job_paths), None)
    if isinstance(data, dict) and data.get("schema_version") == WORKING_SCHEMA_VERSION \
            and isinstance(data.get("segments"), list):
        segs = []
        for s in data["segments"]:
            try:
                segs.append({
                    "id": int(s["id"]), "start": float(s["start"]),
                    "end": float(s["end"]), "text": str(s.get("text", "")),
                    "origin_ids": [int(x) for x in s.get("origin_ids", [s["id"]])],
                    "edited": bool(s.get("edited", False)),
                })
            except (KeyError, TypeError, ValueError):
                continue
        segs.sort(key=lambda s: (s["start"], s["id"]))
        if segs:
            return segs
    return derive_working_from_raw(load_raw_segments(job_paths),
                                   load_edited_overrides(job_paths))


def save_working(job_paths: dict, segments: List[dict]) -> None:
    """Persist the working layer AND mirror plain text overrides into the
    legacy edited.json (only for segments that still map 1:1 onto a raw
    segment) so v1.0 consumers/tests keep functioning. raw.json is never
    touched."""
    ordered = sorted(segments, key=lambda s: (s["start"], s["id"]))
    FileManager.write_json_atomic(_working_path(job_paths), {
        "schema_version": WORKING_SCHEMA_VERSION,
        "segments": ordered,
    })
    raw = {s["id"]: s for s in load_raw_segments(job_paths)}
    legacy: Dict[str, str] = {}
    for seg in ordered:
        if len(seg.get("origin_ids", [])) == 1:
            rid = seg["origin_ids"][0]
            raw_seg = raw.get(rid)
            if raw_seg is not None and seg["text"].strip() != raw_seg["text"].strip():
                legacy[str(rid)] = seg["text"].strip()
    FileManager.write_json_atomic(
        os.path.join(job_paths["transcript"], "edited.json"), legacy)


# --------------------------------------------------------------------------- #
# Pure editing operations (all return NEW lists; raw is never involved)
# --------------------------------------------------------------------------- #

def _next_id(segments: List[dict]) -> int:
    return max((s["id"] for s in segments), default=0) + 1


def edit_text(segments: List[dict], seg_id: int, text: str) -> List[dict]:
    out = []
    for s in segments:
        if s["id"] == seg_id:
            s = dict(s)
            s["text"] = text
            s["edited"] = True
        out.append(s)
    return out


def split_segment(segments: List[dict], seg_id: int, char_index: int) -> Tuple[List[dict], Optional[int]]:
    """Split one segment at a character offset; the boundary time is
    interpolated proportionally. Returns (new_list, new_segment_id)."""
    out: List[dict] = []
    new_id = None
    nid = _next_id(segments)
    for s in segments:
        if s["id"] != seg_id:
            out.append(s)
            continue
        text = s["text"]
        i = max(1, min(len(text) - 1, char_index)) if len(text) > 1 else 0
        if i <= 0:
            out.append(s)
            continue
        left, right = text[:i].strip(), text[i:].strip()
        if not left or not right:
            out.append(s)
            continue
        dur = max(0.0, s["end"] - s["start"])
        cut = s["start"] + dur * (len(left) / max(1, len(text)))
        first = dict(s, text=left, end=round(cut, 3), edited=True)
        second = dict(s, id=nid, text=right, start=round(cut, 3), edited=True,
                      origin_ids=list(s["origin_ids"]))
        new_id = nid
        out.extend([first, second])
    return out, new_id


def merge_segments(segments: List[dict], ids: List[int]) -> List[dict]:
    """Merge contiguous (in list order) segments into one. Non-adjacent
    selections merge their own contiguous runs. Text joins with a space."""
    idset = set(ids)
    out: List[dict] = []
    run: List[dict] = []

    def flush():
        if not run:
            return
        if len(run) == 1:
            out.append(run[0])
        else:
            merged = dict(run[0])
            merged["end"] = run[-1]["end"]
            merged["text"] = " ".join(s["text"].strip() for s in run if s["text"].strip())
            merged["origin_ids"] = [oid for s in run for oid in s["origin_ids"]]
            merged["edited"] = True
            out.append(merged)
        run.clear()

    for s in segments:
        if s["id"] in idset:
            run.append(s)
        else:
            flush()
            out.append(s)
    flush()
    return out


def reset_segment(segments: List[dict], seg_id: int, raw_segments: List[dict]) -> List[dict]:
    """Restore one working segment's text from its first raw origin. A merged
    or split segment resets its text only (structure stays; use reset_all to
    rebuild the structure)."""
    raw = {s["id"]: s for s in raw_segments}
    out = []
    for s in segments:
        if s["id"] == seg_id:
            origin = raw.get(s["origin_ids"][0]) if s.get("origin_ids") else None
            if origin is not None:
                s = dict(s)
                if len(s["origin_ids"]) == 1:
                    s["text"] = origin["text"]
                    s["edited"] = False
                else:
                    s["text"] = " ".join(
                        raw[oid]["text"].strip() for oid in s["origin_ids"] if oid in raw)
                    s["edited"] = False
        out.append(s)
    return out


def reset_all(job_paths: dict) -> List[dict]:
    """Rebuild the working layer from raw, discarding structure and edits."""
    return derive_working_from_raw(load_raw_segments(job_paths), {})
