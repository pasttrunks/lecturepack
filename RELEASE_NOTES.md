# LecturePack v0.2.0 - Release Notes

**Release Date:** July 2026
**Tag:** `v0.2.0-portable-release`
**Previous Release:** `v0.1.0-working-mvp`

---

## What's New in v0.2.0

### Portable Distribution
- **PyInstaller onedir build** - self-contained portable package, no Python install needed
- **Bundled binaries** - ffmpeg, ffprobe, and whisper.cpp included in the package
- **Smart binary detection** - app auto-detects bundled binaries, system PATH, or user-configured paths
- **Diagnostics bar** - visual status indicators for all dependencies on the setup screen
- **Start button gating** - processing disabled until required dependencies (FFmpeg + Whisper) are confirmed

### Persistent Configuration
- **Configurable paths** - ffmpeg, ffprobe, whisper.exe, and model paths are saved to `config.json` and persist across sessions
- **Auto-detection on startup** - app scans for bundled binaries and system PATH on every launch
- **Data directory** - job data stored in `~/LecturePackData/` (configurable)

### Improved UX
- **Nonblocking diagnostics** - no popup warnings on launch; status shown inline
- **Version in title bar** - application version displayed in window title
- **Drag-and-drop video selection** - drag video files directly onto the setup screen

---

## Validated Features

This release was validated against a real 71.7-minute lecture recording (CL100 - Day 2 - Egypt and Archaeology):

| Feature | Status | Notes |
|---------|--------|-------|
| Video inspection | Verified | 1024x768, 4300.4s, H.264 |
| Audio extraction | Verified | 16kHz mono WAV via ffmpeg |
| Transcription | Verified | base.en model, 630 lines, 49KB |
| Slide detection | Verified | 128 candidates (67 well-spaced + 61 dense cluster) |
| Alignment | Verified | Transcript segments aligned to slides |
| Review UI | Verified | Accept/reject workflow functional |
| PDF export | Verified | 82MB slides PDF |
| HTML study pack | Verified | 109MB self-contained HTML |

---

## Known Limitations

### Whisper Transcription
- **Proper nouns and technical terms** - The `base.en` model may mishear specialized vocabulary. Examples from validation:
  - "Abu Simbel" misheard
  - "Tutankhamun" transcription errors
  - This is inherent to the model, not a bug in LecturePack
- **Recommendation:** Use the `medium.en` or `large-v3` model for better accuracy (requires more RAM and disk)

### Slide Detection
- **Dense transition clusters** - When many slides appear in rapid succession (< 1.5s apart), the detector may count each individual transition as a separate candidate
- **Validation finding:** 61 of 128 candidates fell in a 6-minute dense cluster (29:06-35:21); 48/59 consecutive pairs show distinct pixel changes but may represent micro-animations rather than new slides
- **Recommendation:** Review candidates visually and reject false positives in the Review UI

### Platform
- **Windows only** - This is a Windows x64 build
- **No GPU acceleration** - Whisper runs on CPU only (SSE4.2+ required)
- **Unsigned binary** - Windows SmartScreen may warn on first launch

---

## Binary Sizes

| File | Size |
|------|------|
| ffmpeg.exe | 82.5 MB |
| ffprobe.exe | 82.3 MB |
| whisper-cli.exe | 0.5 MB |
| whisper.dll | 1.3 MB |
| ggml-base.dll | 0.6 MB |
| ggml-cpu-*.dll (9 variants) | ~0.8 MB each |
| **Total ZIP** | ~270 MB (estimated) |

---

## Build Information

- **Python:** 3.12.3
- **PyInstaller:** 6.21.0
- **PySide6:** 6.11.1
- **FFmpeg:** 7.0.1 (gyan.dev essentials, GPL build)
- **whisper.cpp:** Latest release build
- **Platform:** Windows 10/11 x64

---

## Upgrade from v0.1.0

If upgrading from v0.1.0 (source-only release):
1. Download and extract the new portable ZIP
2. Your existing job data in `~/LecturePackData/` is fully compatible
3. Copy your `config.json` from the old installation, or let the app auto-detect paths

---

## License

See `THIRD_PARTY_NOTICES.txt` for complete third-party license information.

The FFmpeg binary included in this distribution is compiled with GPL-licensed
code (libx264, libx265). Under the GPL, source code availability must be
offered if this package is redistributed.
