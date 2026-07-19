================================================================================
                     LECTURE PACK v0.2.0 - PORTABLE RELEASE
                           READ THIS FILE FIRST
================================================================================

Welcome to LecturePack! This application processes lecture videos into
organized study materials: slide PDFs, searchable transcripts, HTML study
packs, and SRT subtitles.

================================================================================
QUICK START
================================================================================

1. EXTRACT the ZIP to any folder (e.g., C:\Tools\LecturePack\)

2. DOUBLE-CLICK "LecturePack.exe" to launch

3. The diagnostics bar at the top shows which dependencies were found:
   - FFmpeg: Green = found, Red = missing
   - FFprobe: Green = found, Red = missing
   - Whisper: Green = found, Red = missing
   - Model: Green = found, Red = missing

4. IF DEPENDENCIES ARE RED:
   - The app will attempt to auto-detect binaries from the bin/ folder
   - You can manually browse to set paths in the Whisper Settings section
   - The "Start Processing" button is disabled until FFmpeg + Whisper are OK

5. SELECT A VIDEO: drag-and-drop or click "Browse" to pick your lecture video

6. CLICK "Start Processing" - the app will process your video through all stages

7. REVIEW slides, reject/restore as needed, then EXPORT your study materials

================================================================================
WHAT'S INCLUDED
================================================================================

  LecturePack/
  +-- LecturePack.exe          Main application
  +-- bin/
  |   +-- ffmpeg.exe           Audio/video processing (GPL, see THIRD_PARTY_NOTICES.txt)
  |   +-- ffprobe.exe          Video metadata inspection
  +-- ggml*.dll                Whisper.cpp runtime libraries
  +-- whisper-cli.exe          Speech-to-text engine
  +-- whisper.dll              Whisper core library
  +-- README-FIRST.txt         This file
  +-- THIRD_PARTY_NOTICES.txt  License notices for all included software
  +-- RELEASE_NOTES.md         Version history and known limitations
  +-- SHA256SUMS.txt           File integrity checksums
  +-- BUILD_MANIFEST.json      Build metadata

================================================================================
WHAT'S NOT INCLUDED (BY DESIGN)
================================================================================

  - Whisper model files (.bin) - Download separately from:
    https://huggingface.co/ggerganov/whisper.cpp/tree/main
    Recommended: ggml-base.en.bin (English, ~142 MB)
    Place the .bin file anywhere, then set its path in Whisper Settings.

  - Source video files - You provide your own lecture recordings

================================================================================
SYSTEM REQUIREMENTS
================================================================================

  - Windows 10 or later (64-bit)
  - 4 GB RAM minimum (8 GB recommended for longer lectures)
  - ~2 GB free disk space for processing a 1-hour lecture
  - A modern CPU with SSE4.2 support (most CPUs from 2010+)

================================================================================
IMPORTANT LICENSE NOTES
================================================================================

  This software bundles FFmpeg compiled with GPL-enabled codecs (libx264,
  libx265, etc.). Under the GPL, if you redistribute this package, you must
  also make source code for FFmpeg available or offer to provide it.

  See THIRD_PARTY_NOTICES.txt for full license details of all components.

  The LecturePack application itself is provided as-is without warranty.

================================================================================
KNOWN LIMITATIONS (v0.2.0)
================================================================================

  1. Whisper base.en model may mishear proper nouns and technical terms
     (e.g., Egyptian names, archaeological terminology)

  2. Slide detection may over-count in dense slide-transition clusters
     (manual review of candidates is recommended)

  3. No GPU acceleration - whisper.cpp runs on CPU only in this build

  4. First launch may trigger Windows SmartScreen warning - click
     "More info" then "Run anyway" (this is a known unsigned-binary issue)

================================================================================
GETTING HELP
================================================================================

  - Check RELEASE_NOTES.md for version-specific information
  - File issues at: https://github.com/anomalyco/LecturePack/issues

================================================================================
