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
