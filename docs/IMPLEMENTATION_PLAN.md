# Lecture Pack -- Implementation Plan

**Version:** 1.0  
**Date:** 2026-07-15  
**Status:** Approved (Phase 0)

---

## 1. Source File Tree

```
lecturepack/
  __init__.py
  __main__.py                    # Entry point
  app.py                         # QApplication setup, main window
  constants.py                   # App-wide constants, paths, version

  ui/
    __init__.py
    main_window.py               # QMainWindow with stacked widget navigation
    home_screen.py               # Home / queue view
    setup_screen.py              # Lecture setup, crop/mask, preset
    slide_review_screen.py       # Slide review, keep/reject
    transcript_review_screen.py  # Transcript viewer
    export_screen.py             # Export controls
    settings_screen.py           # Settings & diagnostics
    widgets/
      __init__.py
      drop_target.py             # Drag-and-drop file widget
      progress_card.py           # Per-job progress indicator
      crop_selector.py           # QGraphicsView crop tool
      mask_painter.py            # QGraphicsView mask painter
      slide_thumbnail.py         # Slide thumbnail with keep/reject
      candidate_browser.py       # Rejected candidate gallery
      transcript_segment.py      # Single transcript segment widget

  controllers/
    __init__.py
    job_controller.py            # Pipeline state machine
    job_queue.py                 # Multi-job queue manager
    preset_manager.py            # Processing presets

  services/
    __init__.py
    video_inspector.py           # ffprobe wrapper
    audio_extractor.py           # FFmpeg audio extraction
    transcription_service.py     # whisper.cpp orchestration
    slide_detector.py            # CV-based slide detection
    alignment_engine.py          # Transcript-to-slide matching
    export_service.py            # PDF, HTML, transcript export
    llm_service.py               # LM Studio integration (optional)

  infrastructure/
    __init__.py
    ffmpeg_wrapper.py            # QProcess-based FFmpeg/ffprobe runner
    whisper_wrapper.py           # QProcess-based whisper-cli runner
    cv_engine.py                 # OpenCV frame operations
    hash_engine.py               # Perceptual hash computation
    pdf_engine.py                # ReportLab + img2pdf
    html_engine.py               # Jinja2 HTML generation
    config_manager.py            # Settings persistence
    file_manager.py              # Safe path handling, job directory management
    log_manager.py               # Logging configuration
    model_downloader.py          # First-run model download with progress

  models/
    __init__.py
    job.py                       # Job dataclass / state
    manifest.py                  # Manifest schema
    settings.py                  # Settings schema
    preset.py                    # Preset dataclass
    slide.py                     # Slide candidate dataclass
    transcript.py                # Transcript segment dataclass

  resources/
    icons/                       # Application icons
    templates/
      study_pack.html            # Jinja2 template for HTML study pack
      diagnostics_report.txt     # Template for diagnostic report
    presets/
      standard_lecture.json
      slides_with_webcam.json
      handwritten_whiteboard.json
      software_demo.json
```

### Project Root

```
LecturePack/
  lecturepack/                   # Source (above)
  tests/                         # Tests (see TEST_PLAN.md)
  docs/                          # Documentation (this folder)
  bin/                           # External binaries (gitignored)
  models/                        # Whisper models (gitignored)
  AGENTS.md
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  pytest.ini
  .gitignore
  README.md
  LICENSE
```

---

## 2. Dependency Matrix

### Python Dependencies

| Package | Version | License | Purpose |
|---|---|---|---|
| PySide6 | 6.11.x | LGPLv3 | Qt Widgets GUI |
| opencv-python-headless | 5.0.x | Apache 2.0 | Frame extraction, image comparison, histograms |
| scikit-image | 0.26.x | BSD-3-Clause | SSIM computation |
| Pillow | 12.x | MIT-CMU | Image I/O |
| imagehash | 4.3.x | BSD-2-Clause | Perceptual hashing (pHash, dHash) |
| img2pdf | 0.6.x | LGPL-3.0 | Lossless slide-to-PDF |
| ReportLab | 4.x | BSD-3-Clause | Study-pack PDF generation |
| Jinja2 | 3.x | BSD-3-Clause | HTML templating |
| openai | 1.x | Apache 2.0 | LM Studio client (Phase 6) |

### Dev Dependencies

| Package | Version | License | Purpose |
|---|---|---|---|
| pytest | 8.x | MIT | Test framework |
| pytest-qt | 4.x | MIT | PySide6 widget testing |
| PyInstaller | 6.x | GPL-2.0 + bootloader exception | Packaging |

### External Binaries

| Binary | Version | License | Source | Bundled? |
|---|---|---|---|---|
| ffmpeg.exe | 8.1.x | LGPL-2.1+ | gyan.dev Release Essentials | Yes |
| ffprobe.exe | 8.1.x | LGPL-2.1+ | Same | Yes |
| whisper-cli.exe | v1.9.1 | MIT | github.com/ggerganov/whisper.cpp/releases | Yes |

### Whisper Models (Downloaded at First Run)

| Model | File | Size | SHA-1 |
|---|---|---|---|
| base.en | ggml-base.en.bin | 142 MB | `137c40403d78fd54d454da0f9bd998f78703390c` |
| small.en | ggml-small.en.bin | 466 MB | `db8a495a91d927739e50b3fc1cc4c6b8f6c2d022` |
| large-v3-turbo | ggml-large-v3-turbo.bin | ~1.5 GB | Check upstream |
| large-v3-turbo-q8_0 | ggml-large-v3-turbo-q8_0.bin | ~874 MB | Check upstream |

Download source: `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-<model>.bin`

---

## 3. Data Schemas

### manifest.json

```json
{
    "schema_version": 1,
    "job_id": "uuid",
    "created_at": "ISO-8601",
    "app_version": "semver",
    "source": {
        "original_path": "string",
        "filename": "string",
        "fingerprint": {
            "file_size": "int (bytes)",
            "modified_time": "float (epoch)",
            "duration_ms": "int",
            "partial_hash": "sha256:hex"
        }
    },
    "title": "string",
    "tags": ["string"]
}
```

### source.json

```json
{
    "schema_version": 1,
    "probe_timestamp": "ISO-8601",
    "format": {
        "filename": "string",
        "duration_seconds": "float",
        "size_bytes": "int",
        "format_name": "string",
        "bit_rate": "int"
    },
    "video_stream": {
        "codec_name": "string",
        "width": "int",
        "height": "int",
        "avg_frame_rate": "string (fraction)",
        "display_aspect_ratio": "string"
    },
    "audio_stream": {
        "codec_name": "string",
        "sample_rate": "int",
        "channels": "int"
    },
    "creation_time": "ISO-8601 or null"
}
```

### settings.json

```json
{
    "schema_version": 1,
    "preset": "standard_lecture | slides_with_webcam | handwritten_whiteboard | software_demo",
    "whisper": {
        "model": "ggml-small.en.bin",
        "language": "en",
        "backend": "auto | cpu | vulkan",
        "prompt": "string (glossary, max 224 tokens)",
        "threads": 8
    },
    "slide_detection": {
        "sample_fps": "float",
        "crop_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "ignore_masks": [{"x": "float", "y": "float", "width": "float", "height": "float", "label": "string"}],
        "thresholds": {
            "dhash_reject": 3, "dhash_accept": 20,
            "ssim_reject": 0.92, "ssim_accept": 0.75,
            "hist_bhatt_accept": 0.25, "pixel_diff_accept": 0.15,
            "stability_window_sec": 1.5, "stability_ssim": 0.97,
            "stability_max_wait_sec": 5.0,
            "dedup_phash_threshold": 8, "build_spatial_threshold": 0.08,
            "temporal_median_frames": 5, "gaussian_blur_kernel": 3,
            "noise_floor_pixel_ratio": 0.02
        }
    },
    "export": {
        "output_directory": "string or null",
        "formats": ["slides_pdf", "transcript_txt", "transcript_srt", "transcript_json", "study_pack_html", "study_pack_pdf"]
    },
    "glossary": ["string"]
}
```

### state.json

```json
{
    "schema_version": 1,
    "job_id": "uuid",
    "overall_status": "pending | running | interrupted | completed | failed | cancelled",
    "last_updated": "ISO-8601",
    "stages": {
        "inspect":        {"status": "...", "started_at": "...", "completed_at": "...", "error": "..."},
        "extract_audio":  {"status": "..."},
        "transcribe":     {"status": "...", "backend_used": "cpu|vulkan", "model_used": "...", "progress_percent": 0},
        "extract_frames": {"status": "..."},
        "detect_slides":  {"status": "..."},
        "deduplicate":    {"status": "..."},
        "align":          {"status": "..."},
        "export":         {"status": "..."}
    },
    "source_fingerprint_verified": "bool"
}
```

### Candidate Frame Metadata (per-frame JSON)

```json
{
    "schema_version": 1,
    "frame_number": "int",
    "timestamp_seconds": "float",
    "timestamp_formatted": "HH:MM:SS.mmm",
    "scores_vs_last_accepted": {
        "dhash_hamming": "int",
        "phash_hamming": "int",
        "ssim": "float",
        "histogram_bhattacharyya": "float",
        "pixel_diff_ratio": "float"
    },
    "decision": "accepted | rejected | duplicate",
    "decision_stage": "stage1_fast | stage2_ssim | stage3_tiebreaker",
    "decision_reason": "string",
    "change_type": "full_slide_change | progressive_build | annotation | noise",
    "stability_wait_seconds": "float",
    "stability_frame_captured": "int",
    "stability_ssim_final": "float",
    "spatial_change_ratio": "float",
    "dedup_status": "kept | removed_duplicate",
    "dedup_similar_to": "int or null",
    "dedup_phash_distance": "int or null",
    "slide_index": "int or null",
    "output_filename": "string or null"
}
```

---

## 4. Slide Detection Algorithm

### Preprocessing

1. Crop to user-defined region (normalized 0.0-1.0 coordinates)
2. Apply ignore masks (zero out masked pixel regions)
3. Downscale to 480px width, maintain aspect ratio
4. Convert to grayscale
5. Gaussian blur (3x3 kernel, configurable)
6. Temporal median filter (buffer of N=5 frames, per-pixel median removes transient pointers/lasers)

### Three-Stage Cascade

**Stage 1 -- dHash Fast Screen:**
- Compute dHash Hamming distance between current cleaned frame and last accepted frame
- H <= dhash_reject (3): REJECT (near-duplicate)
- H >= dhash_accept (20): ACCEPT (obvious change) -> stability check
- Otherwise: continue to Stage 2

**Stage 2 -- SSIM Confirmation:**
- Compute SSIM on downscaled grayscale ROI (excluding masked areas)
- SSIM >= ssim_reject (0.92): REJECT
- SSIM <= ssim_accept (0.75): ACCEPT -> stability check
- Otherwise: continue to Stage 3

**Stage 3 -- Tiebreaker:**
- Compute Bhattacharyya distance (cv2.compareHist, HISTCMP_BHATTACHARYYA)
- Compute pixel diff ratio (count(absdiff > 30) / total_pixels)
- B > 0.25 AND P > 0.15: ACCEPT
- B < 0.10 AND P < 0.02: REJECT
- Otherwise: CANDIDATE (lean accept, mark for review)

### Stability Detection

After ACCEPT, wait for content to stabilize:
- Check every 0.25 seconds
- Require N consecutive checks with SSIM >= 0.97 between consecutive checks
- N = stability_window_sec / 0.25 (default: 6 checks = 1.5 seconds)
- Maximum wait: 5 seconds (prevents infinite loops)
- Capture the frame at the point stability is confirmed

### Change Type Classification

| Type | Criteria |
|---|---|
| Full slide change | SSIM < 0.70 AND dHash > 18 |
| Progressive build | 0.70 <= SSIM <= 0.92 AND dHash 4-18 AND spatial_change < 0.30 |
| Annotation | 0.85 <= SSIM <= 0.95 AND spatial_change < 0.10 |
| Noise | SSIM > 0.92 AND dHash <= 3 |

### Deduplication

1. **Sequential (during detection):** Compare each accepted candidate against last accepted via dHash. Distance < 5 = duplicate, reject.
2. **Global (post-detection):** Compare all accepted slides pairwise via pHash. Distance < threshold = cluster. Keep chronologically latest frame per cluster.

### Preset Parameters

| Parameter | Standard | Webcam | Handwritten | Software Demo |
|---|---|---|---|---|
| Sample FPS | 1.0 | 1.0 | 2.0 | 3.0 |
| dHash reject | <= 3 | <= 3 | <= 2 | <= 2 |
| dHash accept | >= 20 | >= 20 | >= 12 | >= 8 |
| SSIM reject | >= 0.92 | >= 0.92 | >= 0.95 | >= 0.88 |
| SSIM accept | <= 0.75 | <= 0.75 | <= 0.80 | <= 0.82 |
| Hist Bhatt accept | > 0.25 | > 0.25 | > 0.15 | > 0.10 |
| Pixel diff accept | > 0.15 | > 0.15 | > 0.08 | > 0.05 |
| Stability window | 1.5s | 1.5s | 2.0s | 0.75s |
| Stability SSIM | 0.97 | 0.97 | 0.96 | 0.95 |
| Max wait | 5s | 5s | 8s | 3s |
| Dedup pHash | 8 | 8 | 12 | 6 |
| Build threshold | 0.08 | 0.08 | 0.04 | 0.02 |
| Median frames | 5 | 5 | 3 | 1 |
| Blur kernel | 3 | 3 | 3 | 0 |
| Default masks | bottom 10% | webcam + bottom 10% | none | bottom 8% |

---

## 5. Development Phases

### Phase 1 -- Project Foundation and Diagnostics

Deliverables: Git repo, AGENTS.md, docs, pyproject.toml, PySide6 shell, settings/diagnostics screen, logging, config management, file manager, sample manifest, synthetic test-video generator, automated tests. Tag: `v0.1.0-foundation`.

### Phase 2 -- Transcription MVP

Deliverables: Video import, ffprobe, audio extraction, whisper.cpp execution, model download, progress, cancellation, resume, crash recovery, backend detection, glossary. Tag: `v0.2.0-transcription`.

### Phase 3 -- Slide Extraction MVP

Deliverables: Crop selector, mask painter, frame sampling, three-stage cascade, stability detection, deduplication, all presets, slides PDF. Tag: `v0.3.0-slides`.

### Phase 4 -- Review and Alignment

Deliverables: Slide review UI, transcript viewer, alignment engine, re-export without retranscription. Tag: `v0.4.0-review`.

### Phase 5 -- Study-Pack Export and Packaging

Deliverables: HTML study pack, PDF study pack, PyInstaller packaging, first-run setup, clean-machine test, user docs. Tag: `v0.5.0-release`.

### Phase 6 -- Optional Qwen Module

Deliverables: LM Studio connection, study notes, citations, graceful offline. Tag: `v0.6.0-ai`.

---

## 6. Acceptance Criteria

See `docs/TEST_PLAN.md` for detailed assertions. See `docs/RISK_REGISTER.md` for known risks. See the planning artifact for the full per-phase acceptance criteria table.

---

## 7. whisper.cpp Research Findings

| Question | Answer |
|---|---|
| Pinned version | v1.9.1 (released 2026-06-19) |
| Official Vulkan Windows binary? | No. Only CPU and CUDA builds in release assets. |
| Vulkan build method | CMake with `-DGGML_VULKAN=ON`, requires VS2022 + LunarG Vulkan SDK |
| AMD Vega 56 Vulkan support | Yes, Vulkan 1.3 via Adrenalin drivers (confirmed) |
| CPU performance (i7-9700F) | small.en: RTF < 1.0 (~45-60 min for 1-hour lecture). Estimate; benchmark in Phase 2. |
| Models to benchmark | base.en, small.en, large-v3-turbo, large-v3-turbo-q8_0 |
| Backend detection | Parse stderr for `ggml_vulkan` and `whisper_backend_init_gpu` patterns |
| Glossary support | `--prompt` flag, max 224 tokens, soft bias |
| Cancellation | whisper-cli handles Ctrl+C. Partial output preserved. |
| Model download | HTTPS from HuggingFace, SHA-1 verification, resumable |
