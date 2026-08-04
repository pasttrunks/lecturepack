# Phase 6 Handoff — Renderer Spike

**Date:** 2026-08-03  
**Status:** Spike built and locally packaged; affected-laptop gate pending  
**Scope:** Unversioned Electron renderer experiment only

## Completed

- Added `electron-spike/` with a launcher and three selectable modes.
- Static mode derives a script-free page from the real `app/ui` and keeps only
  a minimal light/dark theme toggle.
- Mock mode drives the real browser bridge signal shapes with setup progress,
  Demo lifecycle events, 500 logs, pipeline progress, slide/transcript updates,
  theme switching, and resize stress.
- Python mode starts a local argument-array stdio sidecar that imports
  `lecturepack.controllers.job_controller.JobController` and answers heartbeats.
  It intentionally does not start a lecture-processing job.
- `npm run package:win` produces an unpacked Windows proof with one
  `LecturePackRendererSpike.exe`, the existing `app/ui`, the existing
  `lecturepack/` package, and the sidecar script as extra resources.
- Added `tests/test_renderer_spike.py` and decision entry AD-23.

## Verification

```text
npm run validate
> node --check main.js && node --check preload.js && node --check mock-workload.js && node --check python-mode.js && node --check static-theme.js
```

```text
pytest -q tests/test_renderer_spike.py
8 passed in 0.37s
```

Current packaged smoke results on the development computer:

- Static: exit 0, page ready, no page-load failure, no remaining Electron
  processes.
- Mocked: exit 0, 500 logs, 41 pipeline updates, 16 slide updates, 12
  transcript updates, 5 Demo events, 11 setup events, 7 resizes, 6 theme
  toggles, zero workload errors, zero unresponsive events, no page-load
  failure, no remaining Electron processes.
- Python: `engine_loaded: true`, LecturePack engine version `1.2.0`,
  `JobController` imported, one ping, zero sidecar stderr, no page-load
  failure, no remaining Electron processes. The bounded smoke uses intentional
  signal termination after sidecar cleanup and therefore reports exit code 1.

## Remaining gate

Copy/run the unpacked proof on the laptop that exhibits the black interval.
Run Mode 1 manually, then Mode 2 for ten minutes with the default stress
settings. Preserve the JSONL file under `renderer-spike-results/`.

Do not add real processing commands to Mode 3, start an Electron migration,
make Beta 15, or change the Qt shell until that affected-laptop result is
reviewed and the user explicitly approves the next boundary.
