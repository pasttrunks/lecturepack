# LecturePack

Turn a lecture recording into a synchronized, editable study workspace — completely locally on your Windows machine. No cloud. No account. No upload.

![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Qt6-41CD52?logo=qt&logoColor=white)
![Windows](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)


---

## What It Does

LecturePack ingests a recorded university lecture video and produces a complete study package:

1. **Inspect** video metadata via ffprobe
2. **Extract** audio to 16 kHz mono (bundled FFmpeg)
3. **Transcribe** with whisper.cpp (CPU or optional Vulkan GPU)
4. **Detect slides** with an adaptive computer-vision pipeline
5. **Align** transcript segments to slide intervals
6. **Review** — correct slides and transcript, approve or reject context repairs
7. **Export** — slides PDF, HTML study pack, transcripts in 7+ formats

All processing runs **locally**. The optional Context Repair LLM only talks to an endpoint you configure (Ollama, LM Studio, or any OpenAI-compatible server on localhost).

---

## Features

### Premium Glassmorphic Dark UI

Frameless window with Catppuccin Mocha dark theme, custom title bar, animated page transitions, and a sleek glassmorphic design language built entirely in Qt Widgets.

### Spatial Study Workspace

A bidirectional sync workspace: accepted-slide grid on the left, block transcript on the right. Click a slide to jump to the transcript; click a transcript block to highlight the matching slide. Overview card with bookmarks, key terms, and topic navigation.

![Study Workspace](assets/focus_mode.png)

### Focus & Flow Mode

Fade the nav rail, command bar, and status bar to full transparency — leaving only your study content. Press `Esc` to exit.

### Incremental Streaming Transcription

Whisper.cpp output is parsed incrementally via `QProcess`, streaming live transcript segments to the UI as they arrive. No waiting for the full run to finish.

### Layered Persistence

A four-layer transcript model that **never silently overwrites** what Whisper produced:

| Layer | Description |
|-------|-------------|
| **Raw** | Immutable whisper.cpp output, guarded by SHA-256 hash |
| **Normalized** | Deterministic cleanup — whitespace, hallucination collapse, paragraph grouping. Never changes words, names, or facts |
| **Context Proposals** | Optional, reversible corrections from a local LLM or deterministic approved-name matching |
| **User-Approved** | Only the corrections you explicitly accept, applied to a fresh projection |

### Provider-Neutral Backends

A pluggable transcription registry. Ships with `LocalWhisperCppBackend` (private, local) and `GroqTranscriptionBackend` (online, optional). Approved adapters register beside the local default — the job controller only sees the neutral start/progress/result/cancel contract.

### Concurrent Pipeline

Transcription and slide detection run **concurrently** after audio extraction. On the reference PC (AMD RX Vega 56), a 6-minute excerpt dropped from **156 s to 48 s** (−69%).

### Product Modes

| Mode | Produces |
|------|----------|
| **Study Pack** (default) | Slides PDF, HTML study pack, all transcript formats |
| **Transcript Only** | Transcript formats (no slide detection) |
| **Slides Only** | Slides PDF (no audio / whisper) |

---

## Quick Start

### Development Setup

```bash
# Clone
git clone https://github.com/your-user/LecturePack.git
cd LecturePack

# Create venv and install
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# Run
python -m lecturepack.app
```

### Run Tests

```bash
.venv\Scripts\python.exe -m pytest
```

### Build Portable Package

```bash
python build_release.py
```

### Portable Install (No Python Required)

1. Download `LecturePack-portable-X.Y.Z.zip` from the release
2. Verify the checksum against `SHA256SUMS.txt`
3. Extract anywhere (spaces in path are fine)
4. Run `LecturePack.exe`
5. Point the app at a Whisper model (e.g. `ggml-base.en.bin`) on first run

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  UI Layer — PySide6 Qt Widgets (main thread)     │
│  Home · Study · Process · Review · Transcript ·  │
│  Exports · Settings                              │
├──────────────────────────────────────────────────┤
│  Controller Layer — JobController (state machine) │
│  Presets · Stage orchestration · Cancel/resume   │
├──────────────────────────────────────────────────┤
│  Service Layer                                    │
│  TranscriptionService · SlideDetector ·          │
│  AlignmentEngine · ExportService · StudyService  │
├──────────────────────────────────────────────────┤
│  Infrastructure Layer                             │
│  FFmpegWrapper · WhisperWrapper · CVEngine ·     │
│  ConfigManager · FileManager · SecretStore       │
├──────────────────────────────────────────────────┤
│  External Processes                               │
│  ffmpeg/ffprobe.exe · whisper-cli.exe · Ollama   │
└──────────────────────────────────────────────────┘
```

### Thread & Process Model

- **QProcess** for external CLI tools (FFmpeg, whisper-cli) — non-blocking, integrates with Qt event loop, captures stdout/stderr via signals
- **QThread** workers for internal Python processing (OpenCV, hashing, ReportLab) — emit progress signals consumed by the UI
- **Cancellation**: QProcess uses `terminate()` (WM_CLOSE); QThread workers check a cancellation flag between iterations

### Data Layout

```
~/LecturePackData/
  config.json
  jobs/<job-uuid>/
    manifest.json, source.json, settings.json, state.json
    audio/, transcript/, frames/, exports/, logs/
    study.json
  models/
  logs/app.log
```

---

## Optional: Local AI (Ollama)

With [Ollama](https://ollama.com) installed, LecturePack can propose transcript corrections and section headings (recommended: `qwen3:1.7b`). Proposals are schema-validated, cached, generated off the GUI thread, and **never auto-accepted**. Without Ollama, the deterministic offline provider still works.

Setup: [docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md)

---

## Documentation

| Document | Description |
|----------|-------------|
| [PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) | Full product specification |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layered architecture, thread model, pipeline |
| [DECISIONS.md](docs/DECISIONS.md) | All technical decisions with rationale |
| [STUDY_WORKSPACE.md](docs/STUDY_WORKSPACE.md) | Study workspace design and behavior |
| [PERFORMANCE_AND_BACKENDS.md](docs/PERFORMANCE_AND_BACKENDS.md) | Benchmarks and engine selection |
| [TRANSCRIPTION_AND_CONTEXT_REPAIR.md](docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md) | Layered transcript model |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

---

## Limitations

- Automatic transcription is **not perfect**. `base.en` mishears proper nouns and technical terms; the Whisper `--prompt` only weakly biases these. Context Repair helps but is a *proposal* you review — it is not ground truth.
- Slide detection targets *lecture slides*; embedded video content yields scene keyframes, not "slides"; the Conservative preset intentionally under-captures.
- Windows x64 only. Unsigned binary — SmartScreen may warn on first launch.

---

## Privacy

All processing is local. Job data lives under `~/LecturePackData`. No telemetry, analytics, advertising, or network requests beyond first-run model downloads and localhost endpoints you configure. See [docs/PRIVACY_AND_DATA.md](docs/PRIVACY_AND_DATA.md).

---

## License

MIT License. See [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) for bundled binary licenses (FFmpeg is GPL; whisper.cpp is MIT).

---

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a PR. The safety rules are strict — never delete `LecturePackData`, never modify original lecture videos, and always preserve layered persistence.
