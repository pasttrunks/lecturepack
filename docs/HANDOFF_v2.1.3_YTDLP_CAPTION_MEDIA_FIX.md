# Handoff — LecturePack v2.1.3: YouTube link import media path fix

**Date:** 2026-08-26
**Branch:** `fix/ytdlp-caption-media-path`
**Base:** 2.1.2 (`14f26aa`)
**Status:** code complete, **suite green (2014 passed / 26 skipped / 0 failed)**,
**packaged build and self-test green (12/12 checks passing)**

---

## 1. What this release is

Fixes BUG-68: when importing videos from links (e.g. YouTube), yt-dlp downloaded both the video file and caption tracks (.vtt/.srt). Because subtitle downloads completed after the video file, the download progress hook and fallback resolution took the .vtt file path as the media path.

This caused:
1. Poster generation to fail (ffmpeg could not generate a frame from a text .vtt file).
2. Video inspection to return 0 duration and 0x0 dimensions with unknown codec.
3. Audio extraction and slide detection to fail during processing.
4. The transcript to populate from captions, while the overall job showed "Failed".

## 2. Resolved Defects

| # | What | Where |
| --- | --- | --- |
| BUG-68 | Link downloads returned caption sidecar instead of video file | `lecturepack/services/media_fetch.py` |
| — | Extractor args client fallback for YouTube extraction | `lecturepack/services/media_fetch.py` |

## 3. Verification

- Full test suite: **2014 passed, 26 skipped, 0 failed**.
- Live download test against real lecture URL: verified downloading 24MB .mp4 and 175-segment .vtt captions cleanly.
- Packaged self-test: 12/12 checks passing (FFmpeg, ffprobe, Whisper runtime, Whisper smoke, bundled model, Rust Study Core, yt-dlp, yt-dlp-ejs, Deno JS runtime, controller).
- Packaged launch smoke: window appeared in 0.20s with clean exit.
- Updater test suite: 35/35 passing.
- Artifacts produced in `C:\LecturePackScratch\builds\release-2.1.3`:
  - `LecturePack-2.1.3-Portable.zip`
  - `LecturePack-2.1.3-Setup.exe`
  - `LecturePack-2.1.3-SHA256SUMS.txt`
  - `LecturePack-2.1.3-release-manifest.json`
