# Lecture Pack -- Test Plan

**Version:** 1.0  
**Date:** 2026-07-15

---

## 1. Test Framework

- **Framework:** pytest 8.x with pytest-qt for PySide6 widget testing
- **Test directory:** `tests/` at project root
- **Discovery scope:** `tests/*.py` and `tests/test_*.py` only (no recursive discovery)
- **Configuration:** `pytest.ini` at project root
- **Run command:** `pytest tests/ -v`

---

## 2. Synthetic Test Fixtures

### 2.1 Generator Script

`tests/fixtures/generate_test_video.py` creates short synthetic lecture videos using OpenCV, Pillow, and FFmpeg. No copyrighted material is needed. The generator accepts a `--variant` parameter.

### 2.2 Standard Test Video

| Time | Content | Expected Detection |
|---|---|---|
| 0:00-0:05 | Title slide (white on blue: "CS101 Lecture 3") | Slide 1 |
| 0:05-0:15 | Bullet slide ("Topic A", "Topic B") | Slide 2 (full change) |
| 0:15-0:20 | Same slide 2, mouse pointer moving | No new slide |
| 0:20-0:25 | Slide 2 + new bullet "Topic C" (progressive build) | Slide 3 (build) |
| 0:25-0:30 | Slide 3 (diagram, completely different) | Slide 4 (full change) |
| 0:30-0:33 | Fade transition from slide 3 to slide 4 | Stability check waits |
| 0:33-0:40 | Slide 4 (code listing) | Slide 5 |
| 0:40-0:45 | Slide 4 + fake webcam rectangle (bottom-right, colored noise) | No new slide |
| 0:45-0:50 | Slide 4 + changing caption text (bottom 10%) | No new slide |
| 0:50-0:55 | Slide 5 (progressive ink strokes / handwriting) | Slide 6 (annotation) |
| 0:55-1:00 | Slide 2 repeated (same content as 0:05) | Candidate, removed by dedup |
| 1:00-1:05 | Final slide | Slide 7 |

### 2.3 Audio Track

Generated tones or silence/noise patterns with distinct characteristics at known timestamps. No TTS engine dependency. Whisper will produce output (possibly garbled) sufficient for testing timestamp ordering and segment structure. A real speech fixture may be added manually later.

### 2.4 Expected Results

```json
{
    "expected_slide_count": 7,
    "expected_slides": [
        {"index": 1, "timestamp_range": [0.0, 5.0], "label": "title"},
        {"index": 2, "timestamp_range": [5.0, 15.0], "label": "bullets"},
        {"index": 3, "timestamp_range": [20.0, 25.0], "label": "build"},
        {"index": 4, "timestamp_range": [25.0, 33.0], "label": "diagram"},
        {"index": 5, "timestamp_range": [33.0, 50.0], "label": "code"},
        {"index": 6, "timestamp_range": [50.0, 55.0], "label": "annotation"},
        {"index": 7, "timestamp_range": [60.0, 65.0], "label": "final"}
    ],
    "expected_no_slide_in_ranges": [
        [15.0, 20.0, "pointer_motion"],
        [40.0, 45.0, "webcam_masked"],
        [45.0, 50.0, "caption_masked"]
    ],
    "expected_duplicate_at": [55.0, 60.0],
    "expected_transcript_segments_min": 5,
    "expected_transcript_ordered": true
}
```

### 2.5 Video Variants

| Variant | Description | Purpose |
|---|---|---|
| `standard_lecture` | Full test video (above) | Default integration tests |
| `webcam_lecture` | Same slides + persistent webcam | Webcam mask tests |
| `whiteboard_lecture` | Progressive handwriting, no discrete slides | Handwritten preset tests |
| `software_demo` | Rapidly changing screen content | Software demo preset tests |
| `minimal` | 10 seconds, 2 slides | Fast unit tests |
| `pathological` | Fast transitions, heavy compression, noise | Edge case / stress tests |

---

## 3. Test Assertions by Category

### 3.1 Source Inspection

| Test | Assertion |
|---|---|
| ffprobe inspection succeeds | `source.json` exists, contains valid `duration`, `width`, `height` |
| Invalid file rejected | Non-video file produces clear error, not crash |

### 3.2 Audio Extraction

| Test | Assertion |
|---|---|
| WAV produced | `lecture-16khz-mono.wav` exists |
| Correct format | Sample rate = 16000, channels = 1 |
| Duration matches | WAV duration matches source duration +/- 0.5 seconds |

### 3.3 Transcription

| Test | Assertion |
|---|---|
| Output files created | `raw.json`, `raw.srt`, `raw.txt` all exist and are non-empty |
| Timestamps ordered | All segments have `start < end`, sorted by start time |
| No overlapping segments | No segment's range entirely contains another's |
| Backend reported | `state.json` contains `"backend_used"` field with value `"cpu"` or `"vulkan"` |

### 3.4 Slide Detection

| Test | Assertion |
|---|---|
| Correct count | Accepted slide count >= 5 and <= 12 |
| Pointer ignored | No accepted slide has timestamp solely in [15.0, 20.0] |
| Webcam masked | No accepted slide triggered solely by webcam region change |
| Duplicate detected | Slide at [55.0, 60.0] removed by dedup or marked duplicate |
| Build captured | With standard preset, build at [20.0, 25.0] produces a slide |
| Valid intervals | Every slide has `start_time < end_time` |
| Metadata complete | Every candidate has a `.json` file with all score fields |

### 3.5 Alignment

| Test | Assertion |
|---|---|
| All slides mapped | Every accepted slide has >= 1 linked transcript segment |
| All segments mapped | Every transcript segment is linked to exactly 1 slide |
| Boundary handling | Segment spanning two slides assigned to the one with greater overlap |

### 3.6 Exports

| Test | Assertion |
|---|---|
| Slides PDF valid | `slides.pdf` > 0 bytes, is valid PDF (parseable header) |
| HTML valid | `study-pack.html` > 1 KB, contains expected slide count as `<img>` tags |
| SRT valid | `transcript.srt` contains correct number of entries |
| Re-export fast | Re-exporting does not invoke whisper-cli (check log) |

### 3.7 Job Lifecycle

| Test | Assertion |
|---|---|
| Cancel safe | After cancel mid-transcription: `state.json` shows `"cancelled"`, completed stages remain `"completed"`, no corrupt files |
| Resume reuses | After resume: audio extraction not repeated (FFmpeg audio command absent from log) |
| Crash recovery | Job with `"running"` status reclassified as `"interrupted"` on restart |
| Original unchanged | Source video file size and mtime unchanged after full pipeline |

### 3.8 Path Handling

| Test | Assertion |
|---|---|
| Paths with spaces | Full pipeline works with path `C:\Users\test user\Lecture Pack Data\jobs\test` |
| Non-ASCII paths | Job directory with Unicode characters in path does not crash |
| Long paths | Paths near Windows MAX_PATH handled or reported clearly |

### 3.9 Configuration

| Test | Assertion |
|---|---|
| Config load/save | Round-trip: save config, reload, values match |
| Missing config | Missing `config.json` produces defaults, does not crash |
| Invalid config | Corrupt JSON produces defaults with warning, does not crash |

---

## 4. Testing by Phase

### Phase 1

| Test File | Coverage |
|---|---|
| `test_config_manager.py` | Config load, save, defaults, missing file, corrupt file |
| `test_file_manager.py` | Job directory creation, manifest validation, path safety |
| `test_path_handling.py` | Spaces, non-ASCII, long paths |
| `test_diagnostics.py` | FFmpeg detection (mock), whisper-cli detection (mock), report generation |

### Phase 2

| Test File | Coverage |
|---|---|
| `test_video_inspector.py` | ffprobe with synthetic video |
| `test_audio_extractor.py` | WAV extraction, format verification |
| `test_transcription_service.py` | whisper-cli execution, output parsing, backend detection |
| `test_resume_cancel.py` | Cancellation, resume, crash recovery |

### Phase 3

| Test File | Coverage |
|---|---|
| `test_slide_detector.py` | All slide detection assertions from Section 3.4 |
| `test_presets.py` | Each preset produces results within expected ranges |

### Phase 4

| Test File | Coverage |
|---|---|
| `test_alignment_engine.py` | Alignment assertions from Section 3.5 |
| Additional `test_resume_cancel.py` | Re-export without retranscription |

### Phase 5

| Test File | Coverage |
|---|---|
| `test_export_service.py` | All export assertions from Section 3.6 |
| Integration test | End-to-end pipeline with synthetic video |

### Phase 6

| Test File | Coverage |
|---|---|
| `test_llm_service.py` | Connection test, graceful offline, content separation |

---

## 5. Test Execution Rules

1. Tests must pass before any phase is reported as complete.
2. The actual `pytest` output must be included in completion evidence.
3. Tests must not be weakened, deleted, or mocked to force passage.
4. Mocks are acceptable for external tools in unit tests, but integration tests must use real binaries where available.
5. The synthetic test video generator is part of the test infrastructure and must be maintained alongside the tests.
6. Screenshots or recordings must accompany UI-related acceptance criteria.
