"""Unit tests for transcript_formats: serializers, sections, search, ordering."""
import json
import csv
import io
from lecturepack.services import transcript_formats as tf


SEGS = [
    {"id": 2, "start": 5.0, "end": 7.5, "text": "Second segment about Egypt."},
    {"id": 1, "start": 0.0, "end": 4.0, "text": "First segment."},
    {"id": 3, "start": 8.0, "end": 12.0, "text": "Third segment mentions Tutankhamun."},
]


def test_normalize_orders_and_cleans():
    out = tf.normalize_segments(SEGS)
    assert [s["id"] for s in out] == [1, 2, 3]  # sorted by start
    assert all(isinstance(s["start"], float) for s in out)


def test_plain_and_timestamps_toggle():
    with_ts = tf.to_plain(SEGS, include_timestamps=True)
    without = tf.to_plain(SEGS, include_timestamps=False)
    assert "[00:00:00.000 -> 00:00:04.000]" in with_ts  # historical range format
    assert "[" not in without
    # chronological: First appears before Second
    assert with_ts.index("First") < with_ts.index("Second") < with_ts.index("Third")


def test_json_jsonl_csv_roundtrip():
    j = json.loads(tf.to_json(SEGS))
    assert [s["id"] for s in j] == [1, 2, 3]
    lines = [json.loads(l) for l in tf.to_jsonl(SEGS).splitlines() if l.strip()]
    assert len(lines) == 3
    rows = list(csv.reader(io.StringIO(tf.to_csv(SEGS))))
    assert rows[0][0] == "id"
    assert len(rows) == 4  # header + 3


def test_srt_vtt_shape():
    srt = tf.to_srt(SEGS)
    assert "00:00:00,000 --> 00:00:04,000" in srt
    vtt = tf.to_vtt(SEGS)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:04.000" in vtt


def test_serialize_registry_all_formats():
    for fmt in ["txt", "markdown", "json", "jsonl", "csv", "srt", "vtt"]:
        s = tf.serialize(fmt, SEGS, include_timestamps=True)
        assert isinstance(s, str) and s.strip()


def test_search_segments():
    hits = tf.search_segments(SEGS, "egypt")
    assert hits == [1]  # normalized index 1 == the 5.0s segment
    assert tf.search_segments(SEGS, "") == []


def test_build_sections():
    aligned = [
        {"slide_index": 1, "timestamp_seconds": 0.0, "timestamp_formatted": "00:00:00.000",
         "image_filename": "s1.png",
         "segments": [{"id": 1, "start": 0.0, "end": 4.0, "text": "Intro to the pyramids"}]},
        {"slide_index": 2, "timestamp_seconds": 5.0, "timestamp_formatted": "00:00:05.000",
         "image_filename": "s2.png",
         "segments": [{"id": 2, "start": 5.0, "end": 7.5, "text": "Now Tutankhamun and Abu Simbel"}]},
    ]
    sections = tf.build_sections(aligned)
    assert len(sections) == 2
    assert sections[0]["slide_index"] == 1
    assert sections[0]["heading"]  # non-empty topic label derived from text
    assert sections[1]["start"] == 5.0
    md = tf.sections_to_markdown(sections, include_timestamps=True, title="Lecture")
    assert md.startswith("# Lecture")
    assert "## Slide 1" in md and "## Slide 2" in md


def test_sections_skip_placeholder_segments():
    aligned = [{"slide_index": 1, "timestamp_seconds": 0.0, "timestamp_formatted": "0",
                "image_filename": "", "segments": [
                    {"id": -1, "start": 0.0, "end": 1.0, "text": "[No dialogue spoken]"}]}]
    sections = tf.build_sections(aligned)
    assert sections[0]["segments"] == []  # placeholder id -1 dropped
