# Electron packaged-app acceptance gate

An automated + human-readable **release gate** for the Phase 8 packaged
Electron LecturePack application. This is documentation and a test-only
harness: it does **not** modify the Electron host, the Python sidecar, the
renderer, the processing engine, the Qt app, or `LecturePackData`. It is meant
to be run against Luna Max's packaged build **as soon as it is available**.

## Branch

`deepseek/electron-packaged-acceptance` — runs in parallel with Luna's
production Electron work. It touches only three new files and never edits
production code, so it will not conflict with Luna's branch.

## Files added

| File | Purpose |
| --- | --- |
| `scripts/electron_packaged_acceptance.py` | The gate runner. Pure helpers + a real-run path that drives the packaged sidecar JSONL contract and the packaged `LecturePack.exe` evidence stream. |
| `tests/test_electron_packaged_acceptance.py` | 8 focused tests. No real packaged app required (mocks + a throwaway fake). |
| `docs/ELECTRON_PACKAGED_ACCEPTANCE.md` | This document. |

## What the gate verifies

The 12 packaged-app acceptance requirements:

1. Electron launches from the packaged directory.
2. The packaged Python sidecar becomes ready.
3. FFmpeg / FFprobe / whisper.cpp / bundled model resolve from packaged paths.
4. A bundled disposable demo video can be imported.
5. Real processing reaches completion.
6. Slides and transcript are generated.
7. Study Pack export completes and its files exist.
8. The app closes cleanly.
9. The app relaunches with the same disposable data directory.
10. The completed job restores as done.
11. No sidecar / FFmpeg / FFprobe / whisper / Python / Electron child process
   remains after shutdown.
12. Logs contain no renderer crash, page-load failure, unresponsive event,
   malformed bridge payload, unsupported command, or unhandled exception.

### How each requirement is checked

| # | Requirement | Mechanism |
| --- | --- | --- |
| 1 | App launches | Launch `LecturePack.exe --results --data-dir`, poll the `session_started` host-evidence record. |
| 2 | Sidecar ready | Read the sidecar `ready` event (`engine_loaded: true`) from host evidence **and** drive the bundled `LecturePackSidecar.exe` directly over JSONL. |
| 3 | Runtime paths ready | `health_check` response `paths.{ffmpeg,ffprobe,whisper,model}.exists` all true; backed by `runtime_paths_exist()` against the packaged `bin/` + `models/`. |
| 4 | Demo import | `import_video {path, bundled_demo: true}` over the JSONL contract. |
| 5 | Processing completes | Wait for the sidecar `job_completed` event within `--timeout-seconds`. |
| 6 | Slides + transcript | `get_slides` / `get_transcript` responses are non-empty. |
| 7 | Export completes + files exist | Wait for `export_done`, then `validate_export()` checks the `exports/` dir is non-empty and contains `manifest.json`. |
| 8 | Clean close | Send `WM_CLOSE` to the app window, wait for exit, record exit code 0. |
| 9 | Relaunch same data dir | Launch the app a second time with the same `--data-dir`. |
| 10 | Restore as done | Second launch must emit a `job_restored` host-evidence record. |
| 11 | No orphan processes | `snapshot_processes()` before/after each launch; `detect_orphans()` flags any new app-family PID. |
| 12 | Clean logs | `classify_host_evidence()` scans for `page_load_failed`, `render_process_gone`, `renderer_unresponsive`, bridge failures, and error markers (`unsupported command`, `malformed`, `invalid json`, `unhandled exception`). |

## Disposable-data protection

The runner **refuses** to operate on the normal user `LecturePackData`
location and exits `2` before doing anything:

- `~/LecturePackData`
- `~/Documents/LecturePackData`, `~/Desktop/LecturePackData`
- `%USERPROFILE%\LecturePackData`, `%APPDATA%\LecturePackData`,
  `%LOCALAPPDATA%\LecturePackData`
- `%APPDATA%\lecturepack\LecturePackData` (Electron userData default)
- Any directory literally named `LecturePackData` directly under a profile
  root.

It only ever runs against a disposable directory you pass with `--data-dir`.
Unless `--keep-data` is set, the disposable directory is removed after the run.

## Command for Luna

```powershell
python scripts/electron_packaged_acceptance.py `
  --app-dir   "C:\path\to\dist\LecturePack-win32-x64" `
  --data-dir  "C:\LecturePackPhase8Data-disposable" `
  --results-dir "C:\LecturePackPhase8Results" `
  --demo-video "C:\path\to\dist\LecturePack-win32-x64\resources\assets\demo-lecture.mp4" `
  --timeout-seconds 600 `
  --keep-data
```

- `--app-dir` **required** — packaged Electron directory containing
  `LecturePack.exe`.
- `--data-dir` **required** — disposable directory; must **not** be the user
  `LecturePackData`.
- `--results-dir` optional — where the JSON + text summary are written
  (defaults to a temp dir).
- `--demo-video` optional — bundled demo video; auto-discovered under
  `--app-dir` if omitted.
- `--timeout-seconds` optional (default 300) — bound on each wait.
- `--keep-data` optional — keep the disposable data dir after the run.
- `--sidecar` optional — explicit `LecturePackSidecar.exe` path
  (auto-discovered otherwise).

Exit codes: `0` = passed, `1` = a gate failed (see the JSON), `2` = unsafe
data dir / argument error.

## Expected output files

Two files are written to `--results-dir`:

- `acceptance-result.json` — the canonical machine-readable result:
  ```json
  {
    "app_launched": true,
    "sidecar_ready": true,
    "runtime_paths_ready": true,
    "job_started": true,
    "job_completed": true,
    "slides_generated": true,
    "transcript_generated": true,
    "export_completed": true,
    "export_file_count": 0,
    "first_exit_clean": true,
    "restore_passed": true,
    "orphan_processes": [],
    "renderer_failures": [],
    "bridge_errors": [],
    "unexpected_errors": [],
    "passed": true
  }
  ```
- `acceptance-summary.txt` — the same data as a human-readable PASS/FAIL table
  with notes.

The packaged app also writes its own `production-*.jsonl` evidence stream into
the same `--results-dir`; the gate reads those records but does not delete
them.

## Focused tests

`tests/test_electron_packaged_acceptance.py` (8 tests, all passing, no real
packaged app needed):

1. Required CLI arguments + safe disposable-data validation.
2. The runner refuses the normal `LecturePackData` directory (exit 2).
3. Timeout failures produce a useful result instead of hanging.
4. Process-tree cleanup detection works with mocked process data.
5. Expected export evidence is validated (manifest + files).
6. Restart/restore evidence is required for a pass.
7. Any renderer failure, bridge error, or orphan process causes failure.
8. Result JSON is deterministic and machine-readable.

## Real packaged run

Luna's packaged `dist/LecturePack-win32-x64/` and `transfer/` renderer build
currently live inside Luna's **active** worktree on this branch, so the gate
was **not** run against them — running it would race Luna's build process.
Stop after the harness + focused tests are complete; Luna runs the command
above once her build is stable and outside her active worktree.

## Observability blockers

The gate is designed to need **no new production hooks**. It reuses two
existing observability surfaces:

1. The packaged host's `production-*.jsonl` evidence stream (`--results`):
   `session_started`, `sidecar_message` (`ready`, `job_restored`), and the
   failure events `page_load_failed`, `render_process_gone`,
   `renderer_unresponsive`, `page_message_failed`, `console`, `sidecar_stderr`.
2. The sidecar's JSONL stdin/stdout contract: `health_check`, `import_video`,
   `start_job`, `get_slides`, `get_transcript`, `export`, `shutdown` and the
   `ready` / `job_completed` / `export_done` events.

If a future build does **not** emit `job_restored` on the second launch
(requirement 10), record it as a blocker and request the smallest possible
hook: a single `job_restored` record in `production-main.js` `restoreJob()`
(the function already exists and logs nothing today). No other hooks are
required.

## Important integration notes

- **No production edits.** This branch adds three files only. It does not
  cherry-pick or merge Luna's branch, and it does not edit files with
  uncommitted parallel changes.
- **No CDP / screen scraping.** The gate reads JSONL evidence and the sidecar
  contract; it does not require DevTools Protocol unless Luna's packaged app
  already exposes it.
- **No arbitrary long sleeps.** Every wait is a bounded `poll_until()` against
  a concrete file or evidence record; a timeout becomes a structured partial
  result, never a hang.
- **No new dependencies.** Standard library only (`subprocess`, `ctypes`,
  `json`, `pathlib`, `queue`, `threading`).
- **Deterministic result.** `score_result()` always returns the canonical key
  set in a fixed order, so `acceptance-result.json` is stable across runs for
  the same inputs.



