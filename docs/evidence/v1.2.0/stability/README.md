# Stability phase evidence

Scope: `fix: stability and minor workflow bugs`. This folder deliberately
contains no Study workspace, online provider, VAD/detector optimization,
packaging, release, tag, or publishing work.

## Native reproduction

Run from the repository root:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe docs\evidence\v1.2.0\stability\native_selection_repro.py before
```

The real PySide6 `MainWindow` is shown against an isolated temporary job. Row 0
is retained in an extended selection and row 25 is then made current.

- Before: current row 25, selected rows 0 and 25, but preview text was
  `00:00:00.000 · frame 0` because the first selected row drove the preview.
- After: current row 25, selected rows unchanged, and preview text is
  `00:04:10.000 · frame 6250`.
- `selection_before.png` / `selection_after.png` are native widget grabs.
- `selection_before.json` / `selection_after.json` preserve the exact observed
  current row, selected rows, preview label, scrollbar, and visibility state.

## Focused validation

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_ui_v11.py tests\test_ollama_and_repair.py `
  tests\test_scheduler_and_engines.py tests\test_packaging_and_safety.py `
  tests\test_stability_phase.py -q -s
```

Result: **55 passed in 95.10s**. Full output and machine-readable signature
details are in `focused_pytest_output.txt`.

Measured close latency with an active worker that ignores cancellation for
1.2 seconds:

- worker detach: 0.000038s
- Context Repair dialog close: 0.012972s
- main application window close: 0.004905s

Process-tree tests launched real Python parent/child trees through QProcess and
through both `FFmpegWrapper` and `WhisperWrapper`. Every owned root and child
exited. `taskkill` returned 0. A separately launched unrelated control process
remained alive until the test cleaned it up explicitly.

Re-export compared SHA-256, byte size, and nanosecond modification time for 13
protected artifacts: audio WAV, `candidates.json`, eight candidate PNGs, and
raw JSON/SRT/TXT transcript files. Every before/after tuple matched.

## Full regression suite

Command: `.\.venv\Scripts\python.exe -m pytest -q`

Result: **121 passed in 150.53s**. See `full_pytest_output.txt`.
