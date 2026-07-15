# Lecture Pack -- Product Specification

**Version:** 1.0  
**Date:** 2026-07-15  

---

## 1. Purpose

Lecture Pack converts locally stored university lecture videos into study materials. The typical input is an MP4 lecture approximately one hour long. The application generates:

1. A timestamped lecture transcript
2. A PDF containing the professor's actual slides recovered from the video
3. Individual high-resolution slide images
4. A combined study pack matching each slide with the professor's explanation during that slide
5. A review interface for correcting detected slides before export
6. Optional locally generated study notes using a local Qwen model through LM Studio

All core processing runs locally without paid APIs, subscriptions, cloud processing, accounts, telemetry, or usage limits. The local LLM is optional. Transcription and slide extraction work when LM Studio is closed.

---

## 2. Target Hardware

| Component | Specification |
|---|---|
| CPU | Intel Core i7-9700F (8C/8T, 3.0-4.7 GHz, AVX2) |
| GPU | AMD Radeon RX Vega 56, 8 GB HBM2 |
| RAM | 24 GB DDR4 |
| Storage | SSD |
| OS | Windows (desktop) |

The application must not assume an NVIDIA GPU, CUDA, ROCm, or Apple Silicon. University lectures are usually in English, but the architecture must not permanently prevent support for other Whisper languages later.

---

## 3. Technology Stack

| Component | Choice |
|---|---|
| Language | Python 3.11 |
| GUI framework | PySide6 (Qt Widgets) |
| Process isolation | QProcess for external tools, QThread workers for internal processing |
| Testing | pytest |
| Media processing | FFmpeg 8.x, ffprobe, OpenCV 5.x (headless), Pillow 12.x |
| Image hashing | imagehash 4.x (pHash, dHash, aHash, wHash) |
| Slide similarity | scikit-image (SSIM) |
| Slides-only PDF | img2pdf (lossless) |
| Study-pack PDF | ReportLab (Platypus layout) |
| HTML templating | Jinja2 |
| Transcription | whisper.cpp v1.9.1 as external executable |
| Transcript output | Timestamped JSON, SRT, TXT |
| CPU fallback | Mandatory (primary path) |
| Vulkan acceleration | Optional (supported where stable) |
| Optional AI | LM Studio OpenAI-compatible endpoint (localhost:1234) |
| Packaging | PyInstaller (standalone directory mode) |

---

## 4. Privacy and Safety Requirements

| # | Rule |
|---|---|
| P1 | No telemetry, advertising, or analytics |
| P2 | No network requests except first-run model downloads and localhost LM Studio |
| P3 | Never upload videos, audio, transcripts, or slides |
| P4 | Never access university portals or store credentials |
| P5 | Never modify or delete the original video |
| P6 | Never execute transcript content as commands |
| P7 | All external process paths safely escaped (spaces, non-ASCII) |

---

## 5. Core User Workflow

1. Open Lecture Pack
2. Drag one or more local lecture videos into the application
3. Select a lecture
4. View a preview frame
5. Optionally draw a slide-content crop region and ignore masks for webcams, captions, logos, controls, or sidebars
6. Choose a processing preset
7. Start processing
8. Monitor progress across 8 stages: inspect, extract audio, transcribe, extract frames, detect slides, deduplicate, align, export
9. Review detected slides
10. Remove false slides or restore rejected candidates
11. Export final materials
12. Reopen the lecture later without repeating completed work

The application supports canceling and safely resuming a job.

---

## 6. Interface Screens

### 6.1 Home / Processing Queue

- Drag-and-drop target for video files
- Add Video button
- List of lectures with status, progress, and stage
- Controls: Start, Cancel, Resume, Open, Remove from Library
- Removing a lecture does not delete the original video

### 6.2 Lecture Setup

- Video metadata display
- Preview frame with QGraphicsView-based crop selector and mask painter
- Processing preset selector (4 presets)
- Transcript language and Whisper model selection
- Output location picker
- Advanced settings (threshold overrides, sample FPS, glossary)

### 6.3 Slide Review

- Scrollable slide thumbnails with keep/reject toggle
- Full-size preview with timestamp
- Edit slide start timestamp
- Merge duplicate slides
- Rejected candidate browser with restore function
- Regenerate exports without retranscription

### 6.4 Transcript Review

- Timestamped segments with inline editing
- Search with next/previous match
- Raw vs. edited transcript toggle
- Click timestamp to open video at that point
- Flag uncertain transcription
- Edits saved to `edited.json`, raw transcript preserved

### 6.5 Export

- Checklist of export formats with status indicators
- Export Selected and Open Output Folder buttons
- Progress per format

### 6.6 Settings and Diagnostics

- Dependency detection: FFmpeg, ffprobe, whisper-cli versions and status
- GPU/CPU information and Vulkan availability
- Whisper model management (download, delete, select default)
- Path settings (model folder, export folder, data directory)
- LM Studio endpoint configuration with connection test
- Run Diagnostics, Copy Report, Open Log Folder

---

## 7. Processing Presets

| Preset | Description |
|---|---|
| Standard Lecture Slides | Mostly static full-screen slides. Conservative change detection. |
| Slides with Webcam | Static slides with a professor webcam region to mask. |
| Handwritten / Digital Whiteboard | Progressive handwriting preserved more often. Lower thresholds, higher sample rate. |
| Software Demonstration | Lower confidence in auto-detection. More frequent candidate frames. |

---

## 8. Transcription Requirements

1. Inspect source via ffprobe
2. Extract 16 kHz mono WAV audio via FFmpeg
3. Run whisper.cpp outside the UI process
4. Capture progress and logs
5. Export timestamped JSON, SRT, TXT
6. Preserve original raw model output
7. Allow a separately edited transcript
8. Stop cleanly when canceled
9. Resume without repeating audio extraction
10. Report whether CPU or Vulkan was used
11. Support configurable course glossary (passed as Whisper `--prompt`)
12. Never silently correct formulas, numbers, proper names, medical/financial/scientific terms, or abbreviations

---

## 9. Slide Extraction Requirements

Deterministic CV pipeline (no LLM). Three-stage cascade:

1. **dHash fast screen:** Hamming distance classifies obvious duplicates and obvious changes
2. **SSIM confirmation:** Structural similarity on downscaled grayscale ROI
3. **Histogram + pixel diff tiebreaker:** For ambiguous cases

Additional processing:
- Frame preprocessing: crop, mask, downscale to 480px, grayscale, Gaussian blur
- Temporal median filter (removes pointer/laser/transient elements)
- Stability detection (waits for transitions to complete before capture)
- Change type classification (full change, progressive build, annotation, noise)
- Sequential and global deduplication via perceptual hash
- Full metadata recording for every sampled frame

---

## 10. Transcript-to-Slide Alignment

Deterministic timestamp overlap. Each slide has a display interval [start, end]. Each transcript segment has a time range [start, end]. A segment is assigned to the slide whose display interval has the greatest temporal overlap with the segment's range. Boundary behavior: if a segment spans two slides equally, assign to the earlier slide. Every slide gets at least one segment; every segment maps to exactly one slide.

---

## 11. Export Formats

| Format | Method | Notes |
|---|---|---|
| Slides PDF | img2pdf | Lossless image embedding, no re-encoding |
| Slides folder | File copy | Accepted PNGs copied to export directory |
| Transcript TXT | Plain text | One segment per line, prefixed with timestamp |
| Transcript SRT | Standard SRT | Numbered entries with timestamps |
| Transcript JSON | Structured JSON | Segment ID, start, end, text, confidence |
| HTML study pack | Jinja2 template | Self-contained, base64 images, offline, searchable |
| PDF study pack | ReportLab | Slides + transcript, automatic pagination |

---

## 12. Optional LM Studio Module (Phase 6)

- Disabled by default
- Localhost endpoint only
- User explicitly initiates every AI generation
- Shows which transcript segments and slides were provided
- AI-generated content stored separately from source-derived content
- Labels AI-generated content clearly
- Instructs model to use only supplied lecture material
- Preserves citations to slide numbers and timestamps
- Never overwrites transcripts or slide images
- Handles LM Studio being closed without crashing
- No autonomous agents

---

## 13. Explicit Non-Goals for First Release

University login, video downloading, DRM bypassing, cloud accounts, mobile apps, browser extensions, live recording, live transcription, speaker diarization, PowerPoint reconstruction, perfect OCR, translation, Notion upload, cloud sync, user accounts, multi-user collaboration, web server, Electron, automatic flashcards before core pipeline is reliable, LLM watching complete videos, plugin marketplace, theme customization beyond light/dark, complex animations, custom auto-updater.

---

## 14. Job Data Structure

```
LecturePackData/
  jobs/<job-uuid>/
    manifest.json          # Job identity and source fingerprint
    source.json            # ffprobe video metadata
    settings.json          # Processing settings used
    state.json             # Per-stage completion state
    audio/lecture-16khz-mono.wav
    transcript/raw.json, raw.srt, raw.txt, edited.json
    frames/candidates/, accepted/, rejected/
    exports/slides.pdf, transcript.txt, transcript.srt, study-pack.html, study-pack.pdf
    logs/processing.log, ffmpeg.log, whisper.log
```

The original video is never copied into the job directory. A source fingerprint (file size + mtime + partial SHA-256 of first/last 64 KB + ffprobe duration) detects whether the original file has changed.
