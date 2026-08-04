# LecturePack Phase 9 Handoff

**Branch:** `luna/phase9-product-app`
**Date:** 2026-08-04
**Status:** Desktop implementation and packaged acceptance complete; affected-laptop gate pending

## Completed

- Production Electron shell uses the existing HTML/CSS/JavaScript UI, a
  context-isolated preload, and the packaged JSONL Python sidecar.
- DeepSeek commits integrated: `a218438`, `115c66d`, `a897690`, `fed6b29`,
  `cc82367`, `2e43eba`, and `3d09f06`.
- Renderer adapter maps implemented queue, local/URL import, settings, study,
  AI/provider, runtime, notification, review, and export operations to exact
  contract payloads. DEFERRED operations remain untouched.
- Renderer queue handling now preserves the contract's active/rows/schedules
  envelope, consumes study-progress checkpoints, refreshes jobs after deletes,
  and keeps title-based grouping visible when no explicit group is stored.
- `jobs_changed` remains a direct array at the renderer boundary; `ai_token`
  remains plain text; sidecar JSONL uses ASCII-safe escaping.
- Packaged sidecar includes PySide6 only as an internal backend dependency, with
  no Qt window or WebEngine view, plus FFmpeg, whisper.cpp, the bundled model,
  demo video, and frozen yt-dlp provider support.
- Portable ZIP, Inno Setup EXE, and SHA256 manifest were generated.

## Evidence

- Focused bridge/study/runtime/release tests: `81 passed, 1 skipped` in the
  final focused batch.
- Full suite with the disposable legacy onedir fixture:
  `1172 passed, 3 skipped, 1 warning`.
- Packaged acceptance result:
  `C:\LecturePackPhase9Results-luna-beta15-final\acceptance-result.json`
  reports `passed: true`, 13 export files, `restore_passed: true`, empty
  renderer/bridge error lists, and `orphan_processes: []`.
- Packaged URL capability probe: `media_link_support` returned
  `available: true`, version `2026.07.04`, and the sidecar shut down with exit
  code 0.

## Artifacts

- Candidate:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\LecturePack-win32-x64`
- Portable:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Portable.zip`
- Setup:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Setup.exe`
- Hashes:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-SHA256SUMS.txt`

## Remaining gate

Run the portable candidate on the affected laptop with a newly deleted data
directory: cold launch, import a real lecture, process to completion, review
slides/transcript, export Study Pack, close, reopen, confirm restoration, and
check ten-minute idle, resizing/theme switching, no flicker/black interval,
no renderer crash, and no orphan Python/FFmpeg/whisper processes. Do not call
the build Beta 15 until that manual result is recorded.

Updater, historical spike modes, and other contract operations marked
DEFERRED remain outside this handoff.
