# LecturePack beta.11 Rendering Hotfix

**Date:** 2026-08-02
**Branch:** `codex/beta11-rendering-hotfix`
**Starting point:** beta.10 release commit `dd2b6337d277c97dbdf25daa12485851489f4090`
**Purpose:** produce a small packaged candidate for testing the clean-install Windows flicker/lag report.

## Scope and non-goals

The report was smooth behavior on the development machine but flickering and
lag in the packaged application on a separate clean-install machine.
`--disable-gpu` did not improve that installation, so this change does not add
GPU flags, GPU detection, or a graphics-mode setting.

The change preserves the existing UI design and normal button/card/dialog/
navigation animations. It does not introduce a framework, a visual-testing
framework, broad `will-change` usage, or an animation-wide disable.

## Source changes

### 1. Opaque native and WebEngine surfaces

`app/desktop/main.py` now explicitly keeps the `QMainWindow` and
`QWebEngineView` non-translucent and auto-filled. `_sync_page_background()`
computes one active light/dark `QColor` and applies it to:

- the native window and view `QPalette.Window`/`QPalette.Base` roles;
- `QMainWindow` and `QWebEngineView` background styles;
- `QWebEnginePage.setBackgroundColor()`.

`app/ui/app.css` applies the same `var(--bg)` as an opaque `background-color`
to `html`, `body`, and `#app`, with no background image. This makes the first
paint and resize clear surface match the active theme instead of exposing a
compositor clear color.

### 2. Demo spotlight compositor cost

The previous spotlight used a `9999px` spread box-shadow as the full-window
dimmer, a drop-shadow filter on the arrow, and CSS transitions on spotlight
geometry. The implementation now has:

- one fixed, pointer-transparent translucent scrim on `#guided-tour-overlay`;
- one fixed highlight border on `#tour-spotlight-box`;
- one fixed arrow on `#tour-arrow`.

The border and arrow are repositioned only through the existing
`requestAnimationFrame` geometry scheduler when the tour target, scroll, or
window/viewport geometry changes. There is no animated spotlight `top`, `left`,
`width`, or `height`, no blur/drop-shadow filter, and no large spread shadow.
The instruction card and existing tour interaction behavior remain unchanged.

### 3. Processing repaint pressure

`app/ui/app.js` keeps pipeline and status data live but coalesces visible
processing writes into a shared 250 ms scheduler, followed by one
`requestAnimationFrame` callback. This caps visible processing updates at four
per second without delaying processing or persistence.

The renderer now:

- skips an identical serialized pipeline/status snapshot;
- updates existing stage rows, labels, markers, progress fills, and classes;
- appends new log rows through a `DocumentFragment`;
- preserves the log scroll position when the user is at the bottom;
- schedules the Demo processing spotlight measurement after stage DOM growth;
- keeps terminal job-state release immediate in the bridge handler.

The backend duplicate payload/progress suppression from beta.10 is unchanged.

### 4. Regression and evidence bookkeeping

Stale beta10 assertions were updated to describe the new, stronger contracts:
opaque native surfaces, static spotlight geometry, four-Hz processing rendering,
and the guarded status-name update. `scripts/packaged_visual_acceptance.py`
now records the actual Git `HEAD` in its JSON rather than an inherited beta.9
constant.

`docs/DECISIONS.md` contains AD-20 with the decision, alternatives, and
rationale. `docs/HANDOFF_PHASE_4.md` records the phase handoff and remaining
cross-machine validation boundary.

## Verification

### Static and focused checks

```text
node --check app/ui/app.js
python -m py_compile app/desktop/main.py
pytest -q tests/test_flashing_reliability.py tests/test_guided_tour.py tests/test_webview_theme.py
33 passed
```

The focused suite includes the opaque-surface contract, live-DOM processing
contract, static spotlight contract, and existing backend duplicate-progress
checks.

### Full test suite

The complete repository suite was run with the existing local test/build
environments and the ignored runtime fixtures supplied through local junctions
(`bin` and `models`). No dependency or source runtime fixture was modified.

```text
pytest -q --durations=20
1079 passed, 1 skipped, 1 warning in 276.47s (0:04:36)
```

The single warning is the existing deliberate duplicate ZIP-entry warning in
`tests/test_runtime_repair.py`; it is not a failure.

### Packaged runtime

The freshly built onedir was used as `LECTUREPACK_ONEDIR_FIXTURE`:

```text
pytest -q tests/test_runtime_packaged_repair.py tests/test_runtime_packaged_smoke.py
5 passed in 82.97s
```

This exercised the real packaged FFmpeg/FFprobe/Whisper payload and signed
repair proof against a copied disposable runtime.

### Actual-window visual acceptance

The one-run local acceptance used the packaged executable, a disposable data
directory/profile, actual Windows top-level window screenshots, and the short
bundled polar-bear demo video. It covered cold light launch, cold dark launch,
first-run setup, Demo overlays/arrows, navigation, repeated resize, theme
toggle, real video processing, idle hook, and close/reopen.

Evidence directory:

```text
C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta11-gate-20260802
```

The run produced `result.json` and `run-01/screen-recording.mp4`. The result
reported:

- `ok: true`, 191 actual window frames: 171 action-rate and 20 slow-rate;
- zero flagged frames, zero unexpected black/white frames, and zero resize
  surface-disappearance flags;
- zero top-level DOM replacements and zero Demo overlay remounts;
- four intentional theme changes, no repeated/unexpected theme changes;
- all four resize cycles kept the sidebar visible with 7 visible navigation
  items at both minimum and normal sizes;
- packaged processing completed and wrote one disposable job manifest;
- launch times: 3.281 s cold light, 1.812 s cold dark, 1.812 s reopen.

The full five-minute idle duration and three-run cross-machine/VM acceptance
remain tester-side validation for the separately affected clean-install
computer. This local run is evidence that the candidate launches and exercises
the complete path on the development Windows machine; it is not a claim that
the second machine has already been verified.

## Packaged artifacts

Build command:

```text
python app/packaging/build.py
```

The build completed PyInstaller collection, canonical runtime bundling,
Qt-pruning, clean-state validation, portable ZIP creation, Inno Setup
installer creation, and checksum generation.

Artifacts under `app/dist/installer/`:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `LecturePack-0.9.0-beta.11-Portable.zip` | 503,899,909 bytes | `4d430ab548df8ef08b63ff3ad3cdb743439dc2460ba110801c7335fa45de8a41` |
| `LecturePack-0.9.0-beta.11-Setup.exe` | 384,679,830 bytes | `2375424b4c147fab44674cfb7a1a05c13db5016b8ec26ed9b53826bf290ced4d` |

`LecturePack-0.9.0-beta.11-SHA256SUMS.txt` lists both hashes. The binary
artifacts are generated and intentionally not committed to Git; they are the
assets for the beta.11 GitHub pre-release.

## Release handoff

Before publishing, verify that the final commit is the one used for the
candidate source, create the immutable tag `v0.9.0-beta.11` exactly once, push
the branch/tag, publish the GitHub pre-release with the three artifacts, then
download the published assets and compare their SHA-256 values to the table
above. Do not move the tag after publication.
