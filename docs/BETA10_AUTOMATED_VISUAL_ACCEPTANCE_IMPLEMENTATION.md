# Beta 10 Automated Visual Acceptance Implementation

**Date:** 2026-08-02
**Branch:** `codex/phase4-visual-artifact-reliability`
**Baseline:** beta.9 commit `8a0671810e235b24aab9ad0805cfa6fed30fcb00`
**Release state:** beta.10 prepared locally; not tagged, uploaded, or published

## 1. Authorized task and boundaries

The authorized phase was **Automated visual acceptance and beta.10 gate**. The
goal was one small packaged-app acceptance runner that exercises the real
Windows executable, records the actual top-level window, reports visual and
DOM/render evidence, and gates beta.10 without publishing it automatically.

Permitted implementation surface:

- `scripts/packaged_visual_acceptance.py` — one standalone acceptance script.
- `app/ui/app.js` — only the two source-local visual causes reproduced by the
  runner.
- `tests/test_flashing_reliability.py` — regression coverage for those causes
  and the runner contract.
- `tests/test_release_trust.py`, `tests/test_runtime_repair.py`, and
  `.github/workflows/release.yml` — stale release-trust fixture/workflow
  corrections without weakening verification.
- Release metadata and documentation needed to prepare beta.10.

Non-goals were disabling animations, broad GPU changes, `will-change` changes,
framework migration, UI redesign, a general testing framework, or automatic
GitHub publication.

Unrelated pre-existing worktree changes were preserved and were not staged.

## 2. Acceptance runner

The runner is deliberately one Python file. It uses only dependencies already
available in the project environment plus Windows/Python standard-library
facilities:

- Launches `app/dist/LecturePack/LecturePack.exe` with a new
  `LECTUREPACK_DATA_DIR` and a new Qt WebEngine `--user-data-dir` for every
  run.
- Attaches to the packaged page through a small raw WebSocket Chrome DevTools
  Protocol client. No DOM screenshot is used as visual evidence.
- Drives the exact requested sequence: cold light, cold dark, first-run setup,
  the complete guided Demo, Home/Processing/History/Study Packs/Settings,
  repeated minimum-size resizing, theme toggles, native video import, real
  processing of `app/assets/demo/demo_lecture.mp4`, idle, and close/reopen.
- Automates the native Windows `Choose a lecture video` dialog with Win32
  enumeration, focus/thread attachment, the real filename edit control
  (`Edit#1148`), and the real Open button. The CDP click runs on a worker while
  the modal dialog is open so a normal Qt modal loop is not misreported as a
  renderer stall.
- Samples the actual application window through Win32 bounds and `mss` when
  available, with Pillow capture as a fallback. Action mode is 100 ms
  (`8–10 fps`); processing/idle mode is 600 ms (`about 1–2 fps`).
- Starts one desktop `gdigrab` FFmpeg recording when bundled FFmpeg is
  available, with an OpenCV sampled-video fallback. Flagged evidence remains a
  crop of the actual application window.

The pixel analyzer reports and saves timestamped evidence for black/white
whole-window frames, large whole-window changes outside short intentional
transitions, missing WebEngine surface during resize, UI stalls, sidebar
disappearance/overflow, and misaligned Demo target/spotlight/arrow geometry.

The CDP telemetry records theme changes and changes outside declared theme
windows, top-level DOM child-list replacements, Demo overlay identity
remounts, render-like `innerHTML`/`textContent` writes for pipeline/status/
jobs/slides/tour targets, and identical-data writes per target.

`result.json` includes launch timestamps, launch durations, resize request and
observed rectangles, frame-rate buckets, processing result, reopen result,
render/remount counters, theme diagnostics, all flags, and the recording path.

Run it from the repository root with:

```powershell
.\.venv\Scripts\python.exe scripts\packaged_visual_acceptance.py `
  --idle-seconds 300 --runs 3
```

## 3. Reproduced causes and smallest fixes

### 3.1 Demo processing spotlight geometry

The first real flagged Demo frame showed the processing target growing after
the spotlight had been measured. The target was `#pipeline-stages`; its bottom
extended below the spotlight. The smallest fix was a synchronous
`positionTourSpotlight()` call at the end of `renderPipeline()` while the
processing Demo phase is active. No animation or GPU setting was changed.

### 3.2 Reopen runtime overlay

The retained disposable profile proved `setup_acknowledged: true`. CDP then
showed `runtime_health_state: "HEALTHY"` and `bootstrap_pending: false`, while
the actual window still showed the checking overlay. The reducer kept its
prior `checking` state when an acknowledged healthy result arrived;
`RuntimeSetupGate.admit()` returned from its checking branch before closing
the overlay.

The smallest fix was to close the overlay before the checking-state return,
but only when `runtime_health_state === "HEALTHY"` and
`setup_acknowledged === true`. The acknowledgement guard is important: a clean
first launch still renders the five-row Setup checklist. The fix calls the
existing `closeOverlay()` motion path and does not remove or disable motion.

## 4. Release-trust fixture corrections

The fixture tests were stale, not the production trust path. The first three
fixture tests now use an explicit RFC 8032 Ed25519 public-key fixture constant;
the production compiled key assertion was updated to the current beta.9
public key. No production private key was added and no signature, archive
member, size, source, or hash check was weakened.

The release workflow now downloads the pinned `cryptography==49.0.0` wheel,
checks its exact SHA-256
(`e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e`), and
installs only from that verified wheel before the existing release build and
signed-runtime checks.

## 5. Verification evidence

### Focused tests

```text
46 passed, 1 warning
```

The warning is the existing `zipfile` duplicate-name warning from the archive
fault-matrix test; it is not suppressed.

### Full test suite

An initial unconfigured run produced 1,074 passed and two environment failures
because the packaged tests require `LECTUREPACK_ONEDIR_FIXTURE`. Running those
tests against the fresh onedir fixture produced `5 passed`. The final complete
command was:

```powershell
$env:LECTUREPACK_ONEDIR_FIXTURE = (Resolve-Path 'app\dist\LecturePack').Path
pytest -q
```

Final output:

```text
1077 passed, 1 skipped, 1 warning in 275.51s (0:04:35)
```

### Visual acceptance

The required three-run evidence is retained at:

```text
C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta10-gate-20260802\result.json
```

Aggregate result: `ok: true`.

| Run | Frames | Action-rate frames | Idle/processing frames | Error flags | Processing | Reopen | Resizes | Recording |
|---:|---:|---:|---:|---:|---|---|---:|---|
| 1 | 683 | 169 | 514 | 0 | pass | pass | 4 | present |
| 2 | 678 | 164 | 514 | 0 | pass | pass | 4 | present |
| 3 | 676 | 163 | 513 | 0 | pass | pass | 4 | present |

Across all three runs:

- zero unexpected black/white frames;
- zero large whole-window flash flags;
- zero resize-surface flags;
- zero sidebar flags;
- zero Demo alignment flags;
- zero UI-stall error flags;
- zero top-level DOM replacements;
- zero Demo overlay remounts;
- zero repeated theme-change diagnostics;
- processing completed with `source: "Complete"` and one job manifest;
- each run produced a real desktop screen recording.

Per-run render telemetry was `(render-like writes, identical-data writes,
top-level replacements, Demo remounts)`: run 1 `(153, 9, 0, 0)`, run 2
`(156, 9, 0, 0)`, and run 3 `(154, 9, 0, 0)`. Each run observed the same
minimum outer rectangle `[272, 55, 768, 954]` and normal rectangle
`[272, 55, 1648, 954]`; the sidebar remained visible with seven navigation
entries and no overflow flag. Intentional theme telemetry was exactly
`light → dark → light → dark` per run.

Recordings:

```text
C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta10-gate-20260802\run-01\screen-recording.mp4
C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta10-gate-20260802\run-02\screen-recording.mp4
C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta10-gate-20260802\run-03\screen-recording.mp4
```

There are no flagged frames in the passing run directories. The runner still
creates `flagged-frames` directories so a future failure has a stable location
for timestamped PNG evidence.

Each run used a fresh disposable LecturePack data directory and fresh WebEngine
profile on Windows 11 build 26200. This is clean application-profile
coverage; a separate Windows account/VM was not created during this session.

## 6. Beta.10 preparation state

After the gates above passed, the app version was bumped to
`0.9.0-beta.10`, the Windows version-resource metadata and changelog were
updated, and the installer/checksum build was run locally. No beta.10 tag was
created, no GitHub release was uploaded, and no publish workflow was started.

Prepared artifacts:

```text
C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\installer\LecturePack-0.9.0-beta.10-Portable.zip
C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\installer\LecturePack-0.9.0-beta.10-Setup.exe
C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\installer\LecturePack-0.9.0-beta.10-SHA256SUMS.txt
```

The checksum file records:

```text
0bd7fda64441cb14f8691ca01b7f458b673e93c41a1804f5997f6c44fe763871  LecturePack-0.9.0-beta.10-Portable.zip
b6d1ac5f2f65cce5fb2ff5f4d96c963ef5317134ea77cd5216eca121f3fc0dad  LecturePack-0.9.0-beta.10-Setup.exe
```

The handoff state is therefore **READY FOR USER AUTHORIZATION**. The next
authorized action would be review of the prepared installer/checksums followed
by whatever tag/publish decision the user explicitly approves.
