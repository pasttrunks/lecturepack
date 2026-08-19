# Handoff — LecturePack v2.0.7: internal drag, the processing fix, and the polish merge

**Date:** 2026-08-18
**Branch:** `claude/lecturepack-universal-drag-drop-13c2d5` (NOT pushed, NOT tagged)
**Base:** `668c1d6` = v2.0.6
**Status:** release candidate built and gated locally; **awaiting the owner's go-ahead to publish**

## What this was

Three strands that turned out to be one: finishing the internal drag work, discovering
that processing was broken for every already-imported lecture, and absorbing a parallel
worktree's microinteraction polish (`antigravity/microinteractions-polish`).

## Commits

| Commit | What |
| --- | --- |
| `057b883` | internal drag rebuilt on a pointer-driven layer; every drop target lands |
| `45bff4b` | packaged drag acceptance gate; fixed the release gate that had been dead |
| `b4ddfef` | cherry-picked microinteraction polish (authorship preserved) |
| `e9ff280` | processing fix — the controller was never given its job |
| `5253959` | neobrutalist correction pass + CSS token guards |
| `7c2a7b8` | 2.0.7 version bump, changelog, ledger |
| `bc662d3` | acting on the independent pre-release review |

## The three findings that mattered

**DEF-033 — processing did nothing for every already-imported lecture.** The adapter owns
the job the workspace shows (`current_job`); the controller owns the job the pipeline runs
(`controller.job`). Separate objects, synced only by the internal queue-promotion path. So
`start_processing` resolved a job, logged its product mode, and died in `run_pipeline()`
with `Pipeline failed: No job loaded.` A fresh import masked it completely, because the
import path calls `set_job` itself — and the packaged acceptance gate imports before it
processes, so the coverage that existed exercised the one path that worked.

**DEF-035 — the fix for DEF-033 was itself silent data corruption.** Caught by the
independent review, not by me. The sync sat above the "another job is running" early
return, and the controller keeps no local copy of its job. Starting lecture B while A was
mid-pipeline redirected the running pipeline at B: A's stage writes and `save()` landed in
B, overwriting a real lecture. **My tests asserted the broken behaviour** — they forced
`is_processing()` true purely to reach an early return, then asserted `set_job` had been
called. Now below every early return, with a structural guard so a future third bail
cannot be added above it.

**DEF-031 — the release gate had been dead for four releases.** `packaged_visual_acceptance.py`
exited at `#btn-runtime-continue`, a button removed by `4cd98da`, before reaching a single
assertion — through 2.0.4, 2.0.5 and 2.0.6. The gate whose purpose is catching "shipped
dead in every build" failed in exactly that way.

## Verified

| Claim | Evidence |
| --- | --- |
| Suite green | 1885 passed, 7 skipped (all environmental) |
| Internal drag works on the FROZEN binary | `scripts/packaged_drag_acceptance.py`, 8/8 checks, trusted CDP pointer input |
| A drop persists to disk | job `065a6bb4` `group`: `None` → `"Heinrich Schliemann"` |
| Processing starts on an existing lecture | probe on the packaged app: `No job loaded` gone; `loaded backend: CPU` → `Pipeline complete` |
| Packaged smoke/repair/pruning | 33 passed with `LECTUREPACK_ONEDIR_FIXTURE` at a real build |
| Regression tests actually bite | DEF-033, DEF-035 and the CSS token guard each re-run with the fix removed; all fail as intended |
| Version surfaces agree | version.py, lecturepack.iss, electron-spike package.json + package-lock.json |

## NOT verified

- **No human has exercised this build by hand.** Every UI claim is machine-driven or traced
  to source.
- **The DEF-035 corruption scenario was never reproduced live** — it is confirmed by code
  path and pinned by tests, but nobody has actually started a second lecture mid-pipeline
  on the packaged app. That is the single most valuable manual check before shipping.
- Reduced-motion behaviour is asserted in CSS, not observed with the OS setting on.
- The odometer and equalizer fixes are reasoned from specificity and state names; not seen
  rendering.
- `prefers-reduced-motion` viewport-flash colours were restated statically; not eyeballed.

## Review

An independent Opus-class reviewer covered the whole `668c1d6..HEAD` surface. Nine
findings, seven CONFIRMED, all dispositioned in `bc662d3`; the two PLAUSIBLE ones
(pointer capture, `try/finally` around the drop action) were closed belt-and-braces
because either could strand `internalJobDragIds` and kill external file drop for the
session. Its own "could not verify" list is worth reading before the next pass: nothing
was exercised in the packaged app, and Qt WebEngine Web Audio behaviour is unconfirmed.

## Open

- **Publishing is unstarted by design** — nothing pushed, no tag, no GitHub release.
- `app/packaging/win_version_info.txt` goes dirty on every build (generated placeholder,
  tracked). Decide its fate.
- The source-run path crashes on a fresh data dir until the `first_run_checklist` unwrap
  lands (it is in `e9ff280`); `python app/desktop/main.py` still fails — it must be
  `python -m app.desktop.main`.
- `antigravity/microinteractions-polish` still holds three uncommitted Python patches
  (`show_when_ready`, the checklist skip-list, `production-main.js`). All are superseded;
  they should be reverted so that worktree stops fighting a bug that no longer exists.
- `scripts/open_app.ps1` is the supported way to launch a worktree's UI on a real build;
  it refuses to report success without a non-zero `MainWindowHandle`.

---

# RELEASED — v2.0.7, 2026-08-19

**https://github.com/pasttrunks/lecturepack/releases/tag/v2.0.7** — Latest, not a draft.
`main` = `dbcc4c2`, tag `v2.0.7` peels to the same commit.

| Asset | Size | SHA-256 |
| --- | --- | --- |
| `LecturePack-2.0.7-Setup.exe` | 372.7 MB | `7379ee44e3ce1c70ab8e2f4969ae16559eb6f32951983dc545956e763986a7af` |
| `LecturePack-2.0.7-Portable.zip` | 481.3 MB | `8f6e2e33d0970de5e54a926cbba1187f9e5c283d7addf385c5633ee6ab106bc4` |
| `LecturePack-2.0.7-SHA256SUMS.txt` | — | — |
| `LecturePack-2.0.7-release-manifest.json` | — | — |

## Read this before you touch the shipped app again

**The published product is the ELECTRON shell. Its engine is
`electron-spike/python-sidecar.py`, NOT `app/desktop/`.** The PySide6 app under
`app/` is the dev/test vehicle. A fix made only in `app/desktop/` does not ship.

This cost most of a session. The bug reported as "nothing processes" was fixed twice
in `app/desktop/engine_adapter.py` — correctly, and it does fix the app you launch
locally — before anyone asked what the installer actually contains. The sidecar has
its own queue implementation, and the only defect it shared was `_run_now` not
resuming an idle queue, which would have shipped the new ▶ button inert.

`app/ui` DOES ship: `package-win.mjs` passes it through `extraResource` to
`resources/ui`. Verified md5-identical in the shipped bundle. `tests/test_sidecar_queue_resumes.py`
pins that, because if it ever drifts, no UI work in a release reaches users and
nothing says so.

## How to cut a release (nothing here is in CI)

`.github/workflows/release-electron.yml` is named "authoritative" and **has never
succeeded** — 3 runs, all failures, including this release's attempt. It cannot
work as written, for three independent reasons. Every release since 2.0.3 was a
local build.

Build from a SHORT path. Inno Setup fails with "The system cannot find the path
specified" on the deep `.claude/worktrees/...` location: nested sidecar payload
paths (`resources/LecturePackSidecar/_internal/lxml/isoschematron/...`) exceed
MAX_PATH. `C:\lp-rel` works.

    git worktree add C:\lp-rel v2.0.7

Then provision four things the repo does not carry:

1. **Runtime payload** (~390 MB, gitignored) copied in at the repo root:
   `bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/Release/whisper-cli.exe` (note the
   `Release/` subdirectory — `sidecar.spec` requires it there), `models/ggml-base.en.bin`.
   **This is CI blocker #1**: no download step, no cache, no LFS.
2. **`.venv` with pyinstaller** — `package-sidecar.mjs` hardcodes
   `.venv\Scripts\pyinstaller.exe`. CI works around this with a `--pyinstaller`
   flag that `build_electron_release.py` does not pass. **CI blocker #2.**
       python -m venv .venv && .venv\Scripts\python -m pip install -r requirements-release.txt
3. **`node_modules`** — `cd electron-spike && npm ci`
4. **The Rust Study Core `.pyd`** — `sidecar.spec` hard-requires
   `.venv\Lib\site-packages\lecturepack_study_core\lecturepack_study_core.cp312-win_amd64.pyd`.
   The workflow only runs `cargo test --release` and never installs it into a
   Python environment. **CI blocker #3.**
       cd rust\study-core && ..\..\.venv\Scripts\maturin develop --release

Then `python scripts/build_electron_release.py`, and publish with
`gh release create v<version> <the four assets>`.

## Verified on the shipped bundle before publishing

- Media: ONLY `resources/assets/demo-lecture.mp4` and the sidecar's
  `smoke/runtime-smoke.wav`. No lecture data at all — no manifests, no `jobs/`, no
  transcripts. Pinned for the PyInstaller tree by
  `tests/test_shipped_payload_has_no_user_data.py`.
- Icon: all 7 entries of `app/packaging/lecturepack.ico` (16→256px) present in the
  Electron exe's `RT_ICON` resources, compared by SHA-256 — and separately in the
  PyInstaller exe.
- `SHA256SUMS.txt` matches the actual bytes.
- Build tree pristine at the tag (`git status --porcelain -uno` empty).
- Packaged self-test: every runtime component healthy.

## NOT verified

- **Nobody has run this installer.** The build's own self-test passed and the
  PyInstaller equivalent was driven end-to-end, but the published `Setup.exe` was
  not installed and launched before publishing.
- **The published bytes were not re-downloaded and re-hashed.** Local hashes match
  what was uploaded; GitHub's copy is trusted. The v2.0.1 pass did download and
  verify — worth repeating here.
- **Not Authenticode-signed.** No signing credentials on this machine, so SmartScreen
  will warn on first run. Stated in the release notes rather than left to discovery.
- **The DEF-035 concurrency case was never reproduced live** in either product: start
  a second lecture while one is mid-pipeline. Pinned by tests and guarded in the
  sidecar (`_activate_job` refuses to swap a live controller job), never exercised
  by a human.
- Reduced motion, the odometer and the equalizer are reasoned from CSS specificity
  and state names, not observed rendering.

## Leftovers

- `C:\lp-rel` is a registered git worktree holding ~1.5 GB of build output. Remove
  with `git worktree remove C:\lp-rel --force` when done.
- `%TEMP%\LecturePackData-dragtest` — 646 MB copy of the real library, used for
  testing. Safe to delete.
- `app/packaging/win_version_info.txt` still goes dirty on every build (tracked
  generated placeholder).
- The three superseded Python patches in `antigravity/microinteractions-polish`
  should be reverted; they fight bugs that no longer exist.
