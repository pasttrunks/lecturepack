# LecturePack Electron Renderer Migration Spike

## Work-to-date report and SOL 5.6 decision handoff

**Report date:** 2026-08-03<br>
**Status:** Isolated renderer spike complete on the developer desktop; affected-laptop evidence pending<br>
**Decision boundary:** No full Electron migration, Beta 15, or real processing bridge has been approved

This document records the Electron work completed so far, the evidence that was collected, the limits of that evidence, and the exact information needed from the affected laptop before deciding what to do next. It is intended to be read together with the Static, Mocked, and Python JSONL result files by SOL 5.6.

The central rule is important: a clean run on the developer desktop does not prove that Electron fixes the affected laptop. The affected laptop is the acceptance authority.

## 1. Why this experiment was started

Beta 14 addressed a confirmed QtWebEngine workload defect, but the affected laptop still showed a multi-second interval in which the application content became almost completely black. The same failure could not be reproduced reliably on the development computer.

At that point, continuing to tune QtWebEngine flags, CSS, timers, or startup behavior had diminishing diagnostic value. Those changes could not distinguish among four materially different causes:

1. a Windows, Chromium, GPU, or display-surface problem;
2. frontend state or high-frequency DOM update pressure;
3. the Python/QWebChannel bridge or backend event flow; or
4. an interaction between the existing Qt shell and the renderer.

The experiment therefore isolates those variables in stages while reusing the real frontend. It is a diagnostic fork, not an automatic product migration.

The governing decision is recorded as **AD-23** in `docs/DECISIONS.md`.

## 2. Authorized scope and boundaries

### Exact goal

Determine whether the affected laptop behaves differently when the existing `app/ui` frontend is rendered in an isolated Electron window, first without any workload, then under a realistic mocked workload, and finally with a narrowly scoped Python engine handshake.

### Work that was authorized and completed

- An isolated, unversioned Electron harness under `electron-spike/`.
- Three selectable modes: Static, Mocked LecturePack, and Existing Python engine.
- A Windows x64 unpacked package that can be copied to another laptop.
- Local JSONL evidence for page failures, renderer exits, unresponsive windows, workload activity, resizing, theme changes, and Python-sidecar messages.
- Focused tests for mode declarations, signal coverage, process-boundary safety, static-page isolation, and JavaScript syntax.
- A fresh-laptop transfer folder with instructions.

### Files and areas intentionally left unchanged

- The original `app/ui/index.html`, `app/ui/app.css`, `app/ui/app.js`, `app/ui/bridge.js`, and fonts.
- The PySide6/QWebEngine product shell.
- `app/desktop/engine_adapter.py` and the existing Python engine implementation.
- Product release numbers and metadata.
- Installers, updaters, signing, release packaging, and deployment logic.
- Original lecture videos and source-derived media.
- React or any frontend redesign.

The existing UI and engine are copied as package resources for the experiment, but their source files are not rewritten by the spike.

### Explicit non-goals

- This is not Beta 15.
- This is not a complete Electron migration.
- This is not a replacement Python backend.
- This does not run a real lecture-processing job.
- This does not prove that Electron will solve the black interval.
- This does not authorize modifying the Qt shell before the affected-laptop gate is reviewed.

## 3. What was built

### 3.1 Isolated Electron shell

The harness creates a separate Electron process and browser window. It uses:

- Electron `43.2.0`;
- `@electron/packager` `20.0.4`;
- package version `0.0.0` and `private: true`;
- `contextIsolation: true`;
- `nodeIntegration: false`;
- `sandbox: true`;
- a narrow preload bridge for mode selection and opening the local results directory;
- no runtime network requests;
- no installer, updater, or release identity.

The launcher is deliberately simple. It lets the tester select a mode and explains what that mode does. Mode windows use the real existing frontend assets.

### 3.2 Mode 1 — Static page

Purpose: test the renderer surface and basic UI assets without frontend workload, bridge activity, or backend interaction.

Implementation:

- Reads the real `app/ui/index.html`.
- Removes all script tags from the static copy.
- Adds a local `<base>` URL so the existing CSS and fonts resolve from disk.
- Writes a temporary local HTML file and loads it with `window.loadFile(...)`.
- Injects only `static-theme.js`.
- Provides a minimal light/dark theme toggle.

It intentionally contains none of the following:

- `QWebChannel` or `lpBridge` use;
- Python;
- timers or intervals;
- `requestAnimationFrame`;
- processing logic;
- Demo logic;
- the existing application JavaScript workload.

The tester manually resizes the window and switches themes. This mode is the cleanest available test of whether the affected laptop can display the reused frontend surface in Chromium/Electron at all.

### 3.3 Mode 2 — Mocked LecturePack frontend

Purpose: exercise the real frontend under representative state changes without involving Python, Qt, a lecture file, or real processing.

`mock-workload.js` is injected after the real UI loads. It uses the existing browser bridge signal shapes and emits:

- `bootstrap_progress`;
- `bootstrap_complete`;
- `jobs_changed`;
- `pipeline_changed`;
- `status_changed`;
- `log_line`;
- `slides_changed`;
- `transcript_changed`;
- `demo_event`.

The mock workload includes:

- setup progress and setup resolution;
- guided-Demo lifecycle transitions;
- 500 log rows;
- processing progress through the pipeline;
- repeated slide updates;
- repeated transcript updates;
- light/dark theme changes;
- repeated window resizes;
- metrics exposed through `window.__LECTUREPACK_SPIKE__.metrics`.

The default stress window is 600 seconds. The main process resizes the window every 1.5 seconds and toggles the theme every 1.8 seconds. The tester can still manually resize and interact with the window during the run.

This is the most important frontend stress mode because it keeps the real HTML, CSS, and JavaScript while replacing only the backend event source with deterministic local signals.

### 3.4 Mode 3 — Existing Python engine handshake

Purpose: determine whether Electron can start a separate local Python process, import the existing engine entry point, and exchange a small JSONL heartbeat protocol.

The sidecar:

- is `python-sidecar.py`;
- receives an argument array, not a shell command string;
- uses `shell: false`;
- imports `lecturepack` and `lecturepack.controllers.job_controller.JobController`;
- emits a `ready` message with engine and controller information;
- accepts `ping`, `describe`, and `shutdown` commands;
- emits `pong` responses;
- uses unbuffered local stdio;
- does not start a lecture-processing job.

The Electron window displays the sidecar state and emits the existing frontend bridge signal shapes after the handshake. The main process sends periodic pings while the mode is open.

Mode 3 is intentionally gated. It proves only:

```text
Electron renderer -> safe local process spawn -> Python sidecar
Python sidecar -> existing LecturePack engine import -> JSONL heartbeat
```

It does not prove that real processing, video handling, transcription, or long-running backend event transport is ready for Electron.

### 3.5 Local evidence logging

Each run creates a timestamped JSONL file. Evidence includes events such as:

- `session_started` and `session_closed`;
- `page_ready`;
- `page_load_failed`;
- `render_process_gone`;
- `renderer_unresponsive` and `renderer_responsive`;
- `resize`;
- `theme_toggle` and `theme_toggle_failed`;
- `page_metrics`;
- `sidecar_started`, `sidecar_message`, `sidecar_stderr`, and `sidecar_exit`;
- `sidecar_spawn_error`;
- `stress_window_complete`.

The default packaged location is:

```text
LecturePackRendererSpike\resources\renderer-spike-results\
```

The logs are local only. They are the primary evidence to return from the affected laptop.

## 4. Source and package file map

| Path | Role |
|---|---|
| `electron-spike/main.js` | Electron main process, launcher, mode windows, logging, stress timers, safe Python spawn, shutdown handling |
| `electron-spike/preload.js` | Narrow context-isolated bridge for selecting modes and opening local results |
| `electron-spike/launcher.html` | Three-mode launcher and scope explanation |
| `electron-spike/static-theme.js` | Static-mode-only theme toggle |
| `electron-spike/mock-workload.js` | Deterministic frontend workload and bridge signal generator |
| `electron-spike/python-mode.js` | Python-mode page adapter and sidecar status display |
| `electron-spike/python-sidecar.py` | Local JSONL sidecar that imports the existing engine and answers heartbeat commands |
| `electron-spike/package.json` | Private unversioned package and validation/package scripts |
| `electron-spike/package-lock.json` | Locked Electron/packager dependency graph |
| `electron-spike/package-win.mjs` | Produces the unpacked Windows x64 proof and copies required resources |
| `electron-spike/README.md` | Developer run instructions, package instructions, and decision gate |
| `tests/test_renderer_spike.py` | Eight focused structural and syntax tests |
| `docs/DECISIONS.md` | AD-23 decision record |
| `docs/HANDOFF_PHASE_6.md` | Phase handoff and current acceptance gate |
| `LecturePack-Renderer-Spike-Transfer/START-HERE.txt` | Fresh-laptop instructions and result collection guidance |

The package copies these existing resources without changing their source:

```text
LecturePackRendererSpike\resources\ui\
LecturePackRendererSpike\resources\lecturepack\
LecturePackRendererSpike\resources\python-sidecar.py
```

## 5. Packaging and transfer artifact

The portable Windows proof was built with `npm run package:win`. It is an unpacked Electron directory, not an installer.

The handoff folder is:

```text
C:\Users\marsh\Documents\LecturePack\LecturePack-Renderer-Spike-Transfer\
```

Its structure is:

```text
LecturePack-Renderer-Spike-Transfer\
├── START-HERE.txt
└── LecturePackRendererSpike\
    ├── LecturePackRendererSpike.exe
    ├── resources\app.asar
    ├── resources\ui\
    ├── resources\lecturepack\
    └── resources\python-sidecar.py
```

Transfer-artifact facts:

- approximately 367 MB;
- 219 files including the instructions;
- Windows x64;
- no `node_modules`;
- no developer-machine result logs in the clean handoff copy;
- no credentials;
- no original lecture videos;
- no Python runtime;
- no separate Node.js installation required for Static or Mocked mode.

The executable and `resources\app.asar` SHA-256 hashes were checked against the packaged build after the clean copy. The clean transfer folder was not smoke-run afterward so that it would remain free of developer-generated result files; an identical copied package was smoke-run before the clean handoff copy.

Run the transfer copy from a writable location such as Desktop or Downloads. Do not put it under `C:\Program Files`, because the default result directory is inside the unpacked package resources.

## 6. Validation completed on the developer desktop

### 6.1 Source validation

Dependency installation completed successfully with no reported npm vulnerabilities.

JavaScript syntax validation:

```text
npm run validate

> lecturepack-renderer-spike@0.0.0 validate
> node --check main.js && node --check preload.js && node --check mock-workload.js && node --check python-mode.js && node --check static-theme.js
```

Focused tests:

```text
pytest -q tests/test_renderer_spike.py
8 passed in 0.34s
```

The tests cover:

- private/unversioned package metadata;
- all three mode declarations;
- static-mode isolation from bridge and workload hooks;
- local-file loading for existing assets;
- safe argument-array process spawning;
- mock signal coverage and 500-log requirement;
- Python sidecar import boundary and absence of shell/subprocess use;
- JavaScript syntax parsing with Node.

### 6.2 Direct Python sidecar smoke

Using the developer machine’s explicit Python 3.12 executable, the sidecar emitted the expected sequence:

```text
ready: engine_loaded=true, engine=lecturepack, version=1.2.0,
       controller=lecturepack.controllers.job_controller.JobController
pong
description
shutdown
```

This proved the local sidecar protocol and existing engine import on the development environment only.

### 6.3 Packaged-mode smoke results

| Mode | Result | Evidence |
|---|---|---|
| Static | Exit code 0 | Page ready, no page-load failure, no remaining Electron processes |
| Mocked | Exit code 0 | 500 logs, 41 pipeline updates, 16 slide updates, 12 transcript updates, 5 Demo events, 11 setup/bootstrap events, 7 resizes, 6 theme toggles, zero workload errors, zero unresponsive events, no page-load failure, no remaining Electron processes |
| Python | Functional handshake; bounded process exit code 1 | `engine_loaded: true`, engine version `1.2.0`, `JobController` imported, one ping, zero sidecar stderr, no page-load failure, no remaining processes |

The Python smoke exit code of 1 is expected for the bounded test. The test intentionally sends sidecar shutdown/cleanup and then terminates the Electron process with a signal so a packaged helper cannot remain alive. It is not evidence that the engine import failed. The functional evidence is the `ready` payload, the `pong`, zero stderr, no page failure, and no leftover process.

### 6.4 Transfer-copy smoke

An identical copied package was launched directly from the transfer layout before the clean handoff copy was made:

- Static exit code 0;
- Mocked exit code 0;
- Python handshake succeeded with the expected bounded signal exit;
- the executable and `app.asar` matched the packaged build;
- no Node modules were present;
- the clean handoff copy excludes developer result logs.

## 7. Fresh-laptop test procedure

The affected laptop should be tested in this order.

### Mode 1 — Static page

1. Copy the entire `LecturePack-Renderer-Spike-Transfer` folder to Desktop or Downloads.
2. Open `LecturePackRendererSpike`.
3. Double-click `LecturePackRendererSpike.exe`.
4. Choose **Mode 1 · Static page**.
5. Leave it open for ten minutes.
6. Resize repeatedly across small and large window sizes.
7. Switch between light and dark theme.
8. Record any black frame, blank region, flicker, white flash, frozen window, or renderer crash.

Mode 1 has no automated workload timers. The absence of automatic activity is intentional.

### Mode 2 — Mocked LecturePack

1. Close the Static window.
2. Start the executable again.
3. Choose **Mode 2 · Mocked LecturePack**.
4. Leave it open for the default ten-minute stress window.
5. Let the automated resize and theme activity run.
6. Also perform normal manual resize and theme interactions if convenient.
7. Record the first visible symptom, approximate time, and whether the window later recovers.

Mode 2 is the key frontend workload test. It exercises the actual UI while keeping Python and real processing out of the path.

### Mode 3 — Existing Python engine

Mode 3 can be tested on the laptop if a compatible Python environment is installed. The transfer folder contains the sidecar script and bundled `lecturepack` source, but it does not contain a Python interpreter or the external package dependencies.

The project dependency set is defined by the developer checkout’s `requirements.txt`, including PySide6 and the existing image/PDF/utility packages. A fresh laptop with only Windows will not pass Mode 3 until that environment is installed.

If `python.exe` is on PATH, start the executable and choose **Mode 3 · Existing Python engine**. If a specific interpreter must be selected, run from PowerShell:

```powershell
cd C:\Path\To\LecturePack-Renderer-Spike-Transfer\LecturePackRendererSpike
.\LecturePackRendererSpike.exe --mode=python --python="C:\Path With Spaces\python.exe"
```

Successful Mode 3 indicators are:

```text
PYTHON SIDECAR · ENGINE IMPORTED
PYTHON SIDECAR · LIVE · ping 1
```

This is an import/heartbeat check only. It does not start a lecture job.

## 8. How to collect and export results

The normal packaged result directory is:

```text
C:\Path\To\LecturePack-Renderer-Spike-Transfer\LecturePackRendererSpike\resources\renderer-spike-results\
```

The launcher’s **Open local results** button is currently unreliable as a post-run export mechanism. The launcher closes when a mode starts, while the button depends on the launcher process state and an in-memory results path. This does not mean the JSONL evidence is missing.

Use File Explorer to copy the `static-*.jsonl`, `mock-*.jsonl`, and `python-*.jsonl` files, or use PowerShell:

```powershell
$results = "C:\Path\To\LecturePack-Renderer-Spike-Transfer\LecturePackRendererSpike\resources\renderer-spike-results"
$files = Get-ChildItem -LiteralPath $results -Filter *.jsonl -File
$zip = Join-Path $env:USERPROFILE "Desktop\lecturepack-renderer-results.zip"
Compress-Archive -Path $files.FullName -DestinationPath $zip -Force
Write-Output $zip
```

Attach that ZIP to the SOL 5.6 conversation. Do not resend the 367 MB executable folder unless the result files are missing or the package itself needs inspection.

If the result directory does not exist, first confirm that the spike was run from a writable location. Running under `C:\Program Files` can prevent the default local evidence directory from being created.

## 9. What SOL 5.6 should extract from the logs

For each mode, determine:

- whether `page_ready` occurred;
- whether any `page_load_failed` event occurred;
- whether any `render_process_gone` event occurred;
- whether any `renderer_unresponsive` event occurred;
- whether the window later emitted `responsive`;
- whether `session_closed` was recorded;
- how long the mode remained open;
- for Mocked mode, whether the expected workload counts were reached;
- for Python mode, whether `ready.engine_loaded` was true, whether `pong` occurred, and whether `sidecar_stderr` or `sidecar_spawn_error` occurred.

The most useful laptop report includes the following environment details:

- laptop identifier and whether it is the previously affected machine;
- Windows version/build;
- display scaling percentage;
- internal versus external monitor;
- GPU model and driver version if available;
- whether the laptop was on battery or external power;
- whether the symptom appeared during resize, theme change, workload activity, or idle time;
- approximate timestamp of the first symptom;
- screenshots or a short screen recording if available.

Do not infer a renderer conclusion from a missing Python log if Python was not installed. That is an environment prerequisite failure, not a renderer result.

## 10. Decision matrix

| Affected-laptop observation | Most likely boundary implicated | Recommended next decision |
|---|---|---|
| Static mode itself becomes black, blank, or flickers | Windows/Chromium/GPU/display surface or broad Electron rendering compatibility | Investigate the laptop’s Windows, display, GPU, and Chromium conditions before any migration decision |
| Static is smooth, Mocked mode flickers or becomes unresponsive | Frontend state/update pressure, DOM workload, or mock event handling | Inspect frontend update batching, lifecycle transitions, and high-frequency signal consumers |
| Static and Mocked are smooth, Python cannot start | Python path, interpreter, dependency, or permissions problem | Fix the test environment; do not classify this as an Electron renderer failure |
| Static and Mocked are smooth, Python imports and pings successfully | Renderer and basic local bridge are plausible on the affected laptop | Prepare a separately approved migration design; keep real processing out until that design is reviewed |
| Static, Mocked, and Python handshake are smooth, but a future real-processing adapter fails | Backend/IPC contract, processing lifecycle, or engine integration | Investigate the bridge/backend seam; do not revert to renderer speculation without evidence |
| Any mode produces a renderer exit or unresponsive event | Runtime stability issue requiring event/timestamp correlation | Preserve the JSONL and correlate the exact visible symptom with the event timeline |

The only result that can move the current gate is the affected laptop’s result. The development desktop results establish that the experiment is internally functional; they do not establish that the laptop defect is solved.

## 11. Current limitations and known issues

1. **Mode 3 is intentionally incomplete.** It imports the engine and exchanges heartbeats only. Real processing has not been ported.
2. **The transfer folder does not bundle Python.** Static and Mocked modes are portable; Mode 3 requires a compatible external Python environment.
3. **The Open local results button is a UX defect.** Use the results path and ZIP command above.
4. **Static mode has no automated stress.** Manual resize/theme activity is required by design.
5. **The package is an unpacked proof.** It is not signed and is not an installer or release artifact.
6. **The bounded Python smoke reports exit code 1 intentionally.** Read the JSONL handshake and cleanup evidence rather than treating that signal exit alone as a functional failure.
7. **No affected-laptop results are included in this report yet.** The laptop evidence must be appended or attached before choosing a migration path.

## 12. Deferred work and approval gates

The following work remains deferred until the affected-laptop Static and Mocked results are reviewed:

- adding a real processing command to the Python sidecar;
- designing the production Electron/Python bridge;
- replacing or retiring the Qt shell;
- changing the product frontend architecture;
- creating Beta 15;
- creating an installer or updater;
- changing release metadata;
- moving from an experiment to a migration phase.

If the affected laptop passes Static and Mocked smoothly, the next step should be a new, explicit migration phase with its own architecture contract, bridge contract, rollback plan, packaging plan, and acceptance tests. It should not be implemented by extending this diagnostic spike informally.

If Static or Mocked fails, follow the decision matrix and keep the experiment diagnostic. Do not assume that a different desktop shell is the remedy until the failing boundary is identified.

## 13. Suggested SOL 5.6 result summary format

```text
Laptop:
Windows/build:
GPU/driver:
Display/scaling:
Run location:

Mode 1 - Static:
- Start/end time:
- Manual resize/theme performed:
- Black frames or flicker:
- Blank/frozen/unresponsive behavior:
- JSONL filename:

Mode 2 - Mocked:
- Start/end time:
- Ten-minute stress completed:
- Black frames or flicker:
- Blank/frozen/unresponsive behavior:
- JSONL filename:

Mode 3 - Python:
- Python executable/version:
- Dependencies installed:
- ENGINE IMPORTED shown:
- LIVE/ping shown:
- Import/spawn/stderr error:
- JSONL filename:

Decision recommendation:
- Static boundary:
- Frontend workload boundary:
- Python/bridge boundary:
- Proposed next approved phase:
```

## 14. Bottom line

The Electron work so far is a controlled renderer experiment, not a migration. It reuses the real frontend, separates static rendering from frontend workload and Python transport, produces portable Windows evidence, and leaves the existing Qt application and engine intact.

The next decision should be made from the affected laptop’s three JSONL runs and observed behavior. Until those results are reviewed, the correct status is:

```text
Electron spike: locally validated
Affected laptop: pending evidence review
Real processing bridge: not implemented
Full Electron migration: not approved
Beta 15: not started
```
