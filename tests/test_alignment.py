"""Acceptance coverage for transcript-to-slide alignment through ExportService."""
import json
import os

from lecturepack.constants import PRODUCT_MODE_TRANSCRIPT_ONLY
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.services.export_service import ExportService


def _align(tmp_path, slide_starts, segments, *, duration=30.0):
    """Build a synthetic job, run the public export path, and return aligned.json."""
    data_dir = tmp_path / "data"
    video_path = tmp_path / "lecture.mp4"
    video_path.touch()
    job = Job(str(data_dir), video_path=str(video_path))
    job.source["duration"] = duration
    job.settings["product_mode"] = PRODUCT_MODE_TRANSCRIPT_ONLY
    job.save()

    candidates = [
        {
            "frame_number": index,
            "timestamp_seconds": float(start),
            "timestamp_formatted": f"00:00:{int(start):02d}.000",
            "decision": "accepted",
            "image_filename": "",
        }
        for index, start in enumerate(slide_starts)
    ]
    FileManager.write_json_atomic(
        os.path.join(job.paths["root"], "candidates.json"), candidates)
    raw = {
        "result": {
            "transcription": [
                {
                    "offsets": {
                        "from": int(segment["start"] * 1000),
                        "to": int(segment["end"] * 1000),
                    },
                    "text": segment["text"],
                }
                for segment in segments
            ]
        }
    }
    FileManager.write_json_atomic(
        os.path.join(job.paths["transcript"], "raw.json"), raw)

    ExportService(job).align_and_export()
    aligned_path = os.path.join(job.paths["transcript"], "aligned.json")
    with open(aligned_path, encoding="utf-8") as handle:
        return json.load(handle)


def test_alignment_assigns_segment_to_greatest_overlap(tmp_path):
    aligned = _align(
        tmp_path,
        [0.0, 10.0],
        [{"start": 8.0, "end": 14.0, "text": "larger overlap on slide two"}],
        duration=20.0,
    )

    assert [segment["id"] for segment in aligned[0]["segments"]] == [-1]
    assert [segment["id"] for segment in aligned[1]["segments"]] == [1]


def test_alignment_equal_overlap_tie_goes_to_earlier_slide(tmp_path):
    aligned = _align(
        tmp_path,
        [0.0, 10.0],
        [{"start": 8.0, "end": 12.0, "text": "exactly equal overlap"}],
        duration=20.0,
    )

    assert [segment["id"] for segment in aligned[0]["segments"]] == [1]
    assert [segment["id"] for segment in aligned[1]["segments"]] == [-1]


def test_alignment_gives_every_slide_a_segment(tmp_path):
    aligned = _align(
        tmp_path,
        [0.0, 10.0, 20.0],
        [{"start": 1.0, "end": 2.0, "text": "dialogue on the first slide"}],
        duration=30.0,
    )

    assert all(slide["segments"] for slide in aligned)
    assert aligned[0]["segments"][0]["id"] == 1
    assert all(slide["segments"] == [{
        "id": -1,
        "start": float(index * 10),
        "end": float((index + 1) * 10),
        "text": "[No dialogue spoken during this slide]",
    }] for index, slide in enumerate(aligned[1:], start=1))


def test_alignment_maps_every_source_segment_exactly_once(tmp_path):
    aligned = _align(
        tmp_path,
        [0.0, 10.0, 20.0],
        [
            {"start": 1.0, "end": 3.0, "text": "segment one"},
            {"start": 9.0, "end": 13.0, "text": "segment two"},
            {"start": 24.0, "end": 26.0, "text": "segment three"},
        ],
        duration=30.0,
    )

    source_ids = [1, 2, 3]
    aligned_ids = [
        segment["id"]
        for slide in aligned
        for segment in slide["segments"]
        if segment["id"] != -1
    ]
    assert sorted(aligned_ids) == source_ids
    assert all(aligned_ids.count(source_id) == 1 for source_id in source_ids)
