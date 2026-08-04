# Phase 7 Handoff - Electron Migration Vertical Slice

**Date:** 2026-08-03  
**Status:** Phase 7.1 contract repair implemented and packaged; affected-laptop gate pending  
**Decision:** AD-25 (repair), building on AD-24

## Completed

- Added the explicit `electron` `migration` mode to the isolated spike.
- Added a headless JSONL sidecar around the existing `JobController` using
  `QCoreApplication` only.
- Added request IDs and the first command/event contract.
- Added a PyInstaller onedir build from the locked `.venv`.
- Added a bundled demo video containing the existing synthetic visuals and
  spoken fixture audio; source fixtures were not modified.
- Added the Electron adapter for the existing `app/ui` and a safe process-tree
  shutdown guard.
- Added persisted job restore and Study Pack export evidence.
- Repaired the renderer-facing `jobs_changed` shape to be the direct job
  summary array expected by `app/ui/app.js`.
- Locally intercepted theme `set_setting` calls so stress toggles do not send
  unsupported requests to the sidecar.
- Kept an active job `running` until its Export stage completes, and made the
  touched transport labels ASCII-safe.
- Preserved the previous static, mock, and diagnostic Python modes as
  historical evidence; they are not the new migration path.

## Evidence

- `pytest tests\\test_renderer_spike.py -q`: **14 passed in 1.96s**.
- Source sidecar: real FFmpeg, whisper.cpp, slide detection, transcript,
  Study Pack export, clean shutdown, and second-launch `done` restore.
- Packaged sidecar: same real path and `_internal` runtime resolution.
- Packaged Electron host: first real run and second restore run both exited 0;
  no page-load failure, renderer-gone event, or migration bootstrap failure.
- Package commands completed:
  `npm run validate`, `npm run package:sidecar`, and `npm run package:win`.
- The rebuilt portable directory contains the repaired bridge and packaged
  sidecar at `dist\\LecturePackRendererSpike-win32-x64`.
- Final packaged Phase 7.1 smoke: exit code 0, 437 JSONL records, 5 theme
  toggles, 7 `jobs_changed` events progressing `queued` -> `running` ->
  `done`, one `export_done`, zero error records, and clean sidecar tree
  termination.

Detailed contract, commands, counts, and laptop instructions are in
[`ELECTRON_MIGRATION_VERTICAL_SLICE.md`](ELECTRON_MIGRATION_VERTICAL_SLICE.md).

## Remaining work and gate

The affected laptop has not yet been tested from this turn. On that laptop,
copy the unpacked `electron-spike\\dist\\LecturePackRendererSpike-win32-x64`
directory, run `--mode=migration --duration-seconds=600` with separate
`--results` and `--data-dir` directories, complete the guided Demo and real
processing path, close, relaunch, and inspect the process list.

Do not expand the bridge, build Beta 15, migrate the installer/updater, or
change the Qt shell until that gate is reviewed and explicitly passes.
