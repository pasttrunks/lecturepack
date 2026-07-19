# LecturePack v1.2 stability phase handoff

## Phase boundary

- Authorized phase: `fix: stability and minor workflow bugs`
- Starting commit: `65c52eb` (`docs: normalize baseline evidence logs`)
- Ending implementation checkpoint: `5ea9af5`
  (`fix: stability and minor workflow bugs`)
- Branch: `v1.2-hybrid-study`
- Non-goals honored: no Study workspace, Groq/Gemini, API-key work, VAD,
  detector optimization, packaging, release, tag, push, or publishing.

## Changed files

Product code:

- `lecturepack/controllers/job_controller.py`
- `lecturepack/infrastructure/config_manager.py`
- `lecturepack/infrastructure/ffmpeg_wrapper.py`
- `lecturepack/infrastructure/process_tree.py` (new)
- `lecturepack/infrastructure/whisper_wrapper.py`
- `lecturepack/services/ai_repair_service.py`
- `lecturepack/ui/main_window.py`
- `lecturepack/ui/pages/review_page.py`
- `lecturepack/ui/widgets/slide_grid.py`

Tests and fixtures:

- `tests/test_ui_v11.py`
- `tests/test_stability_phase.py` (new)
- `tests/fixtures/process_tree_parent.py` (new)

Documentation/evidence:

- `docs/DECISIONS.md` (AD-10)
- `docs/evidence/v1.2.0/stability/` (native captures, JSON results,
  process post-check, focused/full pytest logs, reproduction helper)

## Bugs reproduced

1. Extended slide selection used `selectedItems()[0]` for scroll and preview.
   With rows 0 and 25 selected and row 25 current, the preview incorrectly
   stayed on frame 0.
2. `AiRepairWorker.detach_and_stop()` called `QThread.wait(5000)`. A mocked
   active provider that ignored cancellation blocked close for 1.118 seconds
   in the focused failing test.
3. `MainWindow.closeEvent()` did not call `JobController.cancel()`.
4. FFmpeg/Whisper cancellation killed only the direct QProcess; descendant
   helpers were not covered by the contract.
5. The actual backend signal was transient. It was neither written to job
   state nor restored when the job reopened, and a later capability probe could
   overwrite the status display.
6. UTF-8 BOM loading already worked, but a partial legacy config with
   `backend: vulkan` did not migrate to the current `engine` key or materialize
   the current defaults.

Chronological sorting, Ctrl/Shift/Ctrl+A/Delete/R/Ctrl+Z, and re-export
isolation were verified with focused tests; their existing product behavior
was already correct, so no unnecessary source rewrite was made.

## Fixes implemented

- Current QListWidget item now drives scroll and preview; selected-set
  semantics remain unchanged.
- Context Repair close now sets cooperative cancellation and returns
  immediately. Detached workers are strongly retained until their QThread
  actually finishes, preventing premature thread destruction.
- Main-window close now cancels the active controller before other worker
  teardown.
- Windows external-tool cleanup uses the exact QProcess root PID with
  `taskkill /PID <pid> /T /F`. No executable-name killing is used.
- Whisper's runtime backend signal is saved in
  `state.json/stages/Transcribe/backend_used`, re-emitted on job load, and
  preferred over binary capability text.
- Config loading deep-merges current defaults, migrates legacy backend names,
  tolerates BOM input, preserves unknown keys, canonicalizes the config, and
  survives restart.

## Before/after evidence

- Before JSON: `docs/evidence/v1.2.0/stability/selection_before.json`
  - current row 25
  - selected rows `[0, 25]`
  - preview `00:00:00.000 · frame 0`
- After JSON: `docs/evidence/v1.2.0/stability/selection_after.json`
  - current row 25
  - selected rows `[0, 25]`
  - preview `00:04:10.000 · frame 6250`
- Native widget screenshots: `selection_before.png` and `selection_after.png`.
- Consolidated machine-readable record: `results.json`.

## Focused test result

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_ui_v11.py tests\test_ollama_and_repair.py `
  tests\test_scheduler_and_engines.py tests\test_packaging_and_safety.py `
  tests\test_stability_phase.py -q -s
```

Result: `55 passed in 95.10s`.

The canceled slow-stream fake server printed expected connection-aborted
diagnostics after the client closed its test connection; pytest reported no
failures. Full captured output is in `focused_pytest_output.txt`.

## Full pytest output

Command: `.\.venv\Scripts\python.exe -m pytest -q`

Actual result:

```text
collected 121 items
121 passed in 150.53s (0:02:30)
```

Full captured output: `docs/evidence/v1.2.0/stability/full_pytest_output.txt`.

## Process-tree cleanup evidence

- Exact-PID helper tree: root PID 9180 terminated; owned child terminated;
  unrelated control process remained alive; taskkill return code 0.
- FFmpeg wrapper: root PID 18796 and child PID 2804 terminated; return code 0.
- Whisper wrapper: root PID 5544 and child PID 12356 terminated; return code 0.
- Main-window close: active Whisper root PID 12012 and child PID 10748
  terminated; return code 0.
- Post-test read-only process check found every recorded PID absent and no
  Python process running `process_tree_parent.py`.

Evidence: `focused_pytest_output.txt`, `results.json`, and
`process_cleanup_postcheck.json`.

## Close-latency result

Measured with an active worker that intentionally ignored cancellation for
1.2 seconds:

- worker detach: 0.000038s
- Context Repair dialog close: 0.012972s
- main application window close: 0.004905s

The worker finished safely afterward; no live QThread was destroyed.

## Settings migration result

A BOM-prefixed legacy config containing `backend: vulkan`, a theme value, and
an unknown future key was loaded. It migrated to `engine: vulkan`, added the
current defaults/schema version, retained the unknown key, saved, and reloaded
with the same effective values after a settings change.

## Backend display result

`Vulkan (Vulkan0)` emitted by the wrapper was persisted to
`stages.Transcribe.backend_used`. A new `Job` instance and controller displayed
`loaded backend: Vulkan (Vulkan0)`. A separate test proved a subsequent binary
capability result does not overwrite a persisted actual backend (`CPU`).

## Re-export signature proof

Before and after `export_now()`, the test compared SHA-256, byte size, and
nanosecond modification time for 13 protected artifacts:

- extracted WAV
- `candidates.json`
- eight candidate PNGs
- raw transcript JSON, SRT, and TXT

Every tuple matched. Transcription, audio extraction, and slide detection did
not rerun. Exact tuples are in `focused_pytest_output.txt`.

## Known limitations

- Provider cancellation remains cooperative. The window closes immediately,
  while a request stalled inside an OS read may wind down in the background
  under the existing finite timeout. Detached worker ownership remains valid
  until completion.
- PID-tree force termination is Windows-specific; the non-Windows fallback
  retains terminate/kill behavior. LecturePack's supported runtime is Windows.
- Packaged-executable validation was intentionally not performed because
  packaging and release work were explicit non-goals for this phase.

## Final Git status

Immediately after checkpoint `5ea9af5`, `git status --short` was empty. The
only subsequent change is this documentation-only handoff; it is committed
separately so the implementation checkpoint hash above remains exact.
