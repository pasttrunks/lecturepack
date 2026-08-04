# LecturePack Electron production app core

This folder contains the Phase 8 production-only Electron candidate. It reuses
the existing HTML/CSS/JavaScript interface, Python engine, persisted job
format, JSONL IPC, and packaged CPU runtime. The Qt application remains in the
repository as a fallback; the old static, mocked, and diagnostic Electron
modes are historical source evidence and are not included in the production
package.

## First real path

The production candidate supports:

1. Electron cold launch and packaged sidecar bootstrap.
2. Local video import.
3. Processing-option selection before starting.
4. Real FFmpeg, whisper.cpp CPU transcription, and slide detection.
5. Live status, pipeline progress, and logs.
6. Slides and transcript review.
7. Study Pack export.
8. Cancel and clean shutdown.
9. Completed-job restore after reopening.

Updater, installer migration, Paste Link/yt-dlp, Ollama/Groq, React, UI
redesign, Qt removal, GPU packaging, and secondary settings are deferred.

## Run from source

From PowerShell:

```powershell
Set-Location C:\Users\marsh\Documents\LecturePack\electron-spike
npm install
npm run validate
npm start
```

The source run uses the locked project `.venv` only as a developer fallback
when a packaged sidecar is not present. A customer laptop does not need Python
or PySide6.

## Sidecar contract

The headless sidecar uses JSONL over stdin/stdout with request IDs. Commands:

```text
health_check
list_jobs
import_video
start_job
cancel_job
get_job
get_slides
get_transcript
export
set_setting
shutdown
```

UI-facing events:

```text
ready
bootstrap_progress
jobs_changed
pipeline_changed
status_changed
log_line
slides_changed
transcript_changed
error
```

The sidecar uses `QCoreApplication` only. It creates no Qt window or WebEngine
view. PySide6 is bundled only because the existing controller still uses
QtCore services; it is not installed on the customer computer.

## Build the portable candidate

From `electron-spike`:

```powershell
npm run package:sidecar
npm run package:win
```

The unpacked candidate is:

```text
C:\Users\marsh\Documents\LecturePack\electron-spike\dist\LecturePack-win32-x64\
```

Transfer that entire directory. Do not transfer only `LecturePack.exe` or
only `app.asar`; the executable depends on the complete `resources` directory,
including the UI, engine resources, and PyInstaller sidecar runtime.

The production executable is:

```text
dist\LecturePack-win32-x64\LecturePack.exe
```

It accepts `--results=<directory>` and `--data-dir=<directory>` for isolated
acceptance evidence. It does not use the old `--mode` argument.

## Laptop gate

Use new empty directories for the first run:

```powershell
New-Item -ItemType Directory -Force C:\LecturePackPhase8Results
New-Item -ItemType Directory -Force C:\LecturePackPhase8Data
.\LecturePack.exe `
  --results="C:\LecturePackPhase8Results" `
  --data-dir="C:\LecturePackPhase8Data"
```

Complete cold launch, local import, option selection, real processing,
slides/transcript review, Study Pack export, normal close, and second-launch
restore. Verify ten-minute idle, resizing, theme changes, no flicker or black
interval, no renderer crash, and no leftover Python, FFmpeg, whisper, or
sidecar process.

Copy back the `production-*.jsonl` files and the completed job directory under
`C:\LecturePackPhase8Data\jobs\` for review. Do not call this Beta 15 until
the affected-laptop gate passes.

See [`docs/ELECTRON_PRODUCTION_APP_CORE.md`](../docs/ELECTRON_PRODUCTION_APP_CORE.md)
for the complete contract, evidence, and acceptance checklist.
