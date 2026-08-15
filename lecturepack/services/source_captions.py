"""Reuse a downloaded video's own captions instead of transcribing it again.

CAPTIONS, not a "transcript", and the difference decides the design. The three
terms are routinely conflated:

  * a transcript is plain text with NO time codes;
  * subtitles are time-synced and may be a TRANSLATION of the speech;
  * captions are time-synced text of what is actually said, in the video's own
    language, and may also mark non-speech sound.

This pipeline needs timestamps -- slides are aligned to spoken time and Study
cites lines by their moment in the lecture -- so a plain transcript is useless
here no matter how clean it is. It also needs the original language, or the
words would not match the audio, which is why a translated track is discarded
upstream in media_fetch rather than adopted. What is left is captions, which is
exactly what the pipeline wants.

Sound cues such as "[MUSIC]" are a caption convention rather than speech, so
they are stripped: leaving them in would let Study quote "[APPLAUSE]" back at a
student as though the lecturer had said it.

A lecture pulled from a public video site usually ships with captions already.
Running whisper.cpp over it anyway is the slowest stage of the pipeline
repeating work that has already been done, so when a downloaded video brings
captions with it they are converted into the exact shape whisper.cpp writes and
the Transcribe stage is satisfied from them.

This applies ONLY to downloaded videos. A locally imported file has no caption
sidecar, so it takes the normal transcription path with nothing to detect --
the scoping is structural rather than a flag that could drift.

Local transcription remains the failsafe: if no captions were published, or the
file is malformed, or it yields too little text to be a real transcript, this
module reports nothing usable and the pipeline transcribes as before.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any


# `00:01:02.345 --> 00:01:05.000 align:start position:0%` and the 'MM:SS.mmm'
# short form some writers emit. Cue settings after the second stamp are ignored.
_CUE = re.compile(
    r"^(?P<start>(?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
# Karaoke timing and styling spans: `<00:00:01.234>`, `<c.colorE5E5E5>`, `</c>`.
_TAGS = re.compile(r"<[^>]*>")
_SPEAKER = re.compile(r"^\s*(?:-\s*)?\[[^\]]{1,40}\]\s*")

# Below this a "transcript" is a title card or a stray caption line, not a
# lecture -- fall through to real transcription rather than ship a stub.
MIN_USABLE_SEGMENTS = 5
MIN_USABLE_CHARS = 400


def _timestamp_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return -1.0
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60.0 + number
    return seconds


def _clean(text: str) -> str:
    text = _TAGS.sub("", text)
    text = html.unescape(text)
    text = _SPEAKER.sub("", text)
    return " ".join(text.split())


def parse_vtt(content: str) -> list[dict[str, Any]]:
    """WebVTT (or SRT) text -> [{start, end, text}] in seconds.

    Auto-generated captions roll: each cue repeats the tail of the one before
    so the viewer sees a scrolling pair of lines. Pasting those straight through
    doubles most of the transcript, so a line already emitted is not emitted
    again.
    """
    segments: list[dict[str, Any]] = []
    emitted: list[str] = []
    start = end = -1.0
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if start < 0 or end < start:
            buffer = []
            return
        lines = []
        for raw_line in buffer:
            line = _clean(raw_line)
            # Drop a line already carried by an earlier cue (the rolling
            # duplicate), but keep a legitimate repeat that is far from it.
            if not line or line in emitted[-3:]:
                continue
            lines.append(line)
            emitted.append(line)
        buffer = []
        text = " ".join(lines).strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})

    for raw_line in (content or "").splitlines():
        line = raw_line.strip("﻿").rstrip()
        match = _CUE.match(line.strip())
        if match:
            flush()
            start = _timestamp_seconds(match.group("start"))
            end = _timestamp_seconds(match.group("end"))
            continue
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.upper().startswith("WEBVTT") or ":" in stripped[:12] and stripped.split(":", 1)[0] in {
            "Kind", "Language", "NOTE", "STYLE", "REGION",
        }:
            continue
        if stripped.isdigit() and not buffer:
            continue          # SRT cue index
        buffer.append(line)

    flush()
    return segments


def to_whisper_raw(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape captions exactly like whisper.cpp's raw.json.

    Writing the same file the transcriber writes means every consumer -- the
    transcript store, editing, export, Study grounding -- keeps working with no
    knowledge that the words came from captions.
    """
    return {
        "transcription": [
            {
                "timestamps": {},
                "offsets": {
                    "from": int(round(float(segment["start"]) * 1000)),
                    "to": int(round(float(segment["end"]) * 1000)),
                },
                "text": " " + str(segment["text"]).strip(),
            }
            for segment in segments
        ],
    }


def is_usable(segments: list[dict[str, Any]]) -> bool:
    """Enough text to be a lecture transcript rather than a title card."""
    if len(segments) < MIN_USABLE_SEGMENTS:
        return False
    return sum(len(str(s.get("text", ""))) for s in segments) >= MIN_USABLE_CHARS


def find_caption_file(directory: str) -> str:
    """Pick the best caption sidecar yt-dlp wrote next to the media.

    Publisher-written captions beat machine-generated ones, so a file whose
    language tag carries the auto marker loses to one that does not; English
    beats other languages because the rest of the pipeline is English-tuned.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return ""
    candidates = [name for name in names if name.lower().endswith((".vtt", ".srt"))]
    if not candidates:
        return ""

    def rank(name: str) -> tuple[int, int, int]:
        lowered = name.lower()
        auto = 1 if ("orig" in lowered or "-auto" in lowered or ".a." in lowered) else 0
        english = 0 if re.search(r"\.en(?:[-.]|\.)", lowered) or ".en." in lowered else 1
        return (auto, english, len(name))

    candidates.sort(key=rank)
    return os.path.join(directory, candidates[0])


def load_segments(path: str) -> list[dict[str, Any]]:
    """Read and parse a caption file; never raises for a bad file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return parse_vtt(handle.read())
    except OSError:
        return []
