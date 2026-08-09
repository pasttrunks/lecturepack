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
- The Electron adapter now exposes the historical runtime-recheck/repair
  methods without crossing the deferred sidecar boundary. Recheck uses
  `health_check`; an unavailable in-place repair produces an explicit
  reinstall-required UI state instead of a renderer exception.
- Packaged sidecar includes PySide6 only as an internal backend dependency, with
  no Qt window or WebEngine view, plus FFmpeg, whisper.cpp, the bundled model,
  demo video, and frozen yt-dlp provider support.
- Portable ZIP, Inno Setup EXE, and SHA256 manifest were generated.
- The refreshed candidate excludes legacy Electron entrypoints and ignores
  nested build-time `node_modules`/`__pycache__` directories in the ASAR.

## Evidence

- Renderer/contract parity repairs are committed as `081cbea`, with the
  ownership-test stability follow-up `fa58eda`; runtime-boundary repair is
  committed as `30d87bf`.
- Focused bridge/study/runtime/release tests: `83 passed, 1 skipped`.
- Full suite with the disposable legacy onedir fixture:
  `1174 passed, 3 skipped, 1 warning`.
- Packaged acceptance result:
  `C:\LecturePackPhase9Results-luna-beta15-final5\acceptance-result.json`
  reports `passed: true`, 13 export files, `restore_passed: true`, empty
  renderer/bridge error lists, and `orphan_processes: []`.
- Packaged URL capability probe: `media_link_support` returned
  `available: true`, version `2026.07.04`, and the sidecar shut down with exit
  code 0.
- The final-candidate URL probe used the host shutdown drain and returned
  `ready: true`, `available: true`, and `exit_code: 0` from
  `C:\LecturePackPhase9UrlProbe-final5b-disposable`.
- `npm run validate`: passed; final ASAR audit found only
  `electron-bridge.js`, `production-main.js`, and `production-preload.js`
  among the Electron entrypoints.

## Artifacts

- Candidate:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\LecturePack-win32-x64`
- Portable:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Portable.zip`
- Setup:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Setup.exe`
- Hashes:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-SHA256SUMS.txt`

Portable SHA-256: `99668ac31498e1253054d84327a9e0916abcaba5f063c5561061c8cc66c3c605`
Setup SHA-256: `99c089612157dbaf51cf53c01e42ca2f43d90949ce2e1f4e595c6d726b63a65e`

## Remaining gate

Run the portable candidate on the affected laptop with a newly deleted data
directory: cold launch, import a real lecture, process to completion, review
slides/transcript, export Study Pack, close, reopen, confirm restoration, and
check ten-minute idle, resizing/theme switching, no flicker/black interval,
no renderer crash, and no orphan Python/FFmpeg/whisper processes. Do not call
the build Beta 15 until that manual result is recorded.

Updater, historical spike modes, and other contract operations marked
DEFERRED remain outside this handoff.

---

## Desktop QoL polish pass — 2026-08-09

**Branch:** `sol/qol2.0`
**Base HEAD:** `655975f9deccd557ae511a24b8f06ce0c0865c1e`

### Completed

- Conservative display-title cleanup now applies at normal `Job` creation;
  exact source path/filename remain unchanged, and manifest-backed rename is
  available inline and from lecture context menus.
- The header title opens the recent/current lecture switcher and continues to
  use the existing viewed-job state independently from the processing slot.
- The global processing strip shows authoritative percent, a guarded smoothed
  ETA, and queued count; Process navigation shows the active/waiting workload.
- State-aware renderer context menus reuse existing navigation, queue, retry,
  cancel, export, reveal, rename, and delete commands.
- Electron restores safe visible window bounds/maximized state. Existing
  per-job resume state is paired with the selected lecture/main screen and
  explicit navigation retains priority.
- Multi-line URL input queues sequential background transfers around the
  existing `MediaFetcher`. The compact Downloads panel supports collapse,
  active cancel, waiting removal, retry, details, and clearing completed rows;
  successful transfers enter the unchanged normal import path.

### Evidence

- JS validation: `npm run validate` passed.
- Focused desktop/bridge/queue/import set: `108 passed`.
- Final full-suite run: `1303 passed, 1 skipped, 2 failed`. Both failures are
  legacy runtime-fixture gates: the Electron onedir intentionally does not have
  legacy-root `bin/ffmpeg.exe` or `smoke/runtime-smoke.wav`. All product and QoL
  tests passed.
- Electron packaged rebuild succeeded. Portable ZIP and hashes are under
  `C:\LecturePackScratch\builds\desktop-qol-pass`.
- Packaged acceptance: PASS for launch, sidecar/runtime readiness, processing,
  slides/transcript, 13 exports, restart restore, renderer/bridge errors, and
  orphan processes. Evidence:
  `C:\LecturePackScratch\results\desktop-qol-pass\acceptance-result.json`.
- Packaged UI check used
  `C:\LecturePackScratch\data\desktop-qol-pass-acceptance`: ugly local filename
  cleaned while source remained visible; rename survived restart; header
  switcher selected another lecture while its row showed `Processing 86%`;
  maximized bounds and Transcript screen restored after restart.
- Real batch check used two license-unrestricted Samplelib MP4 links. The UI
  confirmed `Download 2`, remained navigable on Transcript while the indicator
  showed `70% · 1 waiting`, and both completed files became normal imported jobs.
  Clean shutdown left no LecturePack, sidecar, yt-dlp, FFmpeg, or whisper process.

### Known limitations

- The legacy QtWebEngine visual-acceptance helper cannot attach its DevTools
  port to the Electron candidate; the Electron packaged acceptance gate passed.
- Cancel/retry is covered by focused regression tests but was not manually
  timed against the fast public sample transfers.

---

## QOL/Productivity stabilization re-audit — 2026-08-08

**Branch:** `kimi/qol-productivity-pass`

### Fixed

- Global transcript search is reachable from the header and Ctrl+K, waits for
  the selected lecture payload, then centers/highlights the exact timestamp.
- Queue all applies the selected batch mode/quality and starts the first job
  immediately when the active slot is idle; FIFO promotion remains unchanged.
- Windows taskbar progress keeps the authoritative overall percent instead of
  being overwritten by indeterminate pipeline events. The global strip now
  refreshes on every live status update.
- Resume state stores the transcript section's real scroll offset, saves on
  app close, and continues to honor explicit navigation overrides.
- Completed lectures opened from Ctrl+K route to Review; live/queued lectures
  route to Process.
- Search, palette, batch import, and the global processing strip now participate
  in native keyboard semantics, dialog labeling, live announcements, and the
  shared focus trap. The header no longer overflows at the 640px minimum width.

### Verification

- `npm run validate`: passed.
- Focused Electron/QOL suite: `96 passed`.
- Full suite: `1279 passed, 1 skipped`; the only two failures require the
  external `LECTUREPACK_ONEDIR_FIXTURE` and are unrelated to this pass.
- Packaged Electron acceptance: PASS for launch, sidecar/runtime readiness,
  real demo processing, slides, transcript, 13 exports, clean exit,
  relaunch/restore, no renderer/bridge/unexpected errors, and no orphan
  processes. Evidence:
  `C:\LecturePackScratch\results\qol-packaged-acceptance-20260808\acceptance-result.json`.

### Correct release artifact

- Portable Electron ZIP:
  `C:\LecturePackScratch\builds\qol-electron-release-20260808\LecturePack-0.9.0-beta.15-Portable.zip`
- SHA-256:
  `18780b972386d3d915bd7c650b5b43dce8c4f26e2cc887ac5a12f7cd78fd5caa`
- Manifest:
  `C:\LecturePackScratch\builds\qol-electron-release-20260808\LecturePack-0.9.0-beta.15-SHA256SUMS.txt`

`dist-release\LecturePack-portable-1.2.0.zip` is a legacy PyInstaller/Qt
artifact and does not contain the Electron QOL implementation. Do not use it
as the Phase 9/QOL candidate.

### Remaining manual gate

The affected-laptop fresh-data acceptance gate remains required before calling
the candidate Beta 15. This re-audit does not replace the separate physical
flicker/idle/resize observation.
