# Handoff — LecturePack v2.0.1 release hardening

**Date:** 2026-08-10
**Branch:** `codex/v2.0.1-release-hardening` (pushed)
**Tag:** `v2.0.1` → `2c7051afdc95527f572092a5d916e7e262501b86` (pushed)
**Base:** `v2.0.0` (`6afbe04`) — immutable, untouched throughout.

## What this was

A hardening pass over the shipped 2.0.0 release. No feature work. It started with an
audit of the **actual public GitHub release** (not just the tag), then fixed what that
audit and the follow-on review exposed.

## Audit of public v2.0.0 — passed, no P0 stop

Downloaded the real assets and verified them:

| Asset | SHA-256 |
| --- | --- |
| `LecturePack-2.0.0-Setup.exe` | `5c36408b31af79221329ca8e3ad54d547a319d4dba077b4be9b925676c648be6` |
| `LecturePack-2.0.0-Portable.zip` | `1d9dad5fab6213311615d799cf727b51ab78baa0faaecc85aeee3f091c455510` |

Published `SHA256SUMS.txt`, the release manifest and the release notes all agree with the
actual bytes. The installer was confirmed to be the **Electron** product (`LecturePack.exe`
+ `resources/app.asar` + `resources.pak`); PySide6/Qt appears only under
`resources/LecturePackSidecar/_internal` as the documented sidecar dependency. Packaged
self-test passed; the Polar Bears demo matched its canonical SHA.

Machine-readable result: `C:\LecturePackScratch\results\v2.0.1-hardening\v2.0.0-public-audit.json`.

**One correction worth remembering:** an early pass wrongly reported yt-dlp as absent from
the package. It is present — pure-Python modules live inside the PyInstaller PYZ archive,
so a filename search of the zip misses them. Check the self-test, not the file listing.

## Defects found and fixed

All five are recorded in `BUG_LIST.md` as **BUG-28** … **BUG-32** with root causes and
lessons. Summary:

- **BUG-32 (security, shipped in 2.0.0)** — the updater would install an *unverified*
  installer. A `catch` set `expectedSha256 = null` and the consumer treated `null` as
  "skip verification".
- **BUG-31** — `package-win.mjs` hardcoded the version, so the built `.exe` reported 2.0.0
  while every declaration file said 2.0.1.
- **BUG-30** — YouTube import silently degraded (11 formats instead of 14): no JS runtime,
  no EJS package, and a health check that only proved `import yt_dlp` succeeded.
- **BUG-29** — the legacy Qt workflow published the Electron installer's filename, and a
  contract test *required* that wrong behaviour.
- **BUG-28** — Study tabs were flat; the second-layer cause was an inline `!important`
  block that made the first fix look like a no-op.

## Verification performed

| Gate | Result |
| --- | --- |
| Python suite (pinned release env, onedir fixture) | **1452 passed, 0 failed, 0 skipped** |
| Rust Study Core | 11 passed |
| `npm run validate` | pass (now also checks `updater.js`) |
| Packaged self-test | 12/12 |
| Packaged UI acceptance | **29/29**, 11 screenshots, 0 orphans |
| Clean-machine acceptance | pass (Unicode/space paths, 13-file export) |
| Negative failure matrix | pass |
| A→B update 2.0.0 → 2.0.1 | pass, data preserved, 0 orphans |
| Live URL-import probe | pass |

## Things a future session needs to know

1. **The packaged acceptance gate needs a LONG media fixture.** `--long` is not satisfied by
   the 10-second bundled demo: the gate waits for an ETA label, and the renderer only shows
   one after 20+ seconds elapsed with 20+ seconds remaining. A short clip transcribes faster
   than that, and the run fails with *"timed out waiting for live progress and ETA on long
   workload"* — which looks like a product bug but is a fixture problem.
   Use `scripts/make_acceptance_fixtures.py`, which loops the **same** demo to ~21 minutes.
   The shipped package still contains exactly one video (the 10s demo).

2. **Building in a deep worktree breaks Inno Setup.** One bundled file
   (`lxml/isoschematron/.../iso_schematron_skeleton_for_xslt1.xsl`) reaches 262 characters
   under this worktree path and exceeds Windows' 260-char limit; ISCC aborts with
   "The system cannot find the path specified" and no line number. Workaround: stage the
   candidate to a short path (`C:\LPB\cand`) and pass `/DSourceDir` there. CI checks out to
   a short path and does not hit this.

3. **The release venv is not the dev venv.** `.venv` in the worktree is built from
   `requirements-release.txt` plus the maturin-built Study Core wheel. Running the suite
   with system Python produces 3 failures that are purely environmental (missing Rust core
   and packaged fixtures) — they are **not** regressions. Confirmed by running the same
   files against untouched `v2.0.0`.

4. **PyYAML is a test dependency, not a shipped one.** `test_release_pipeline_authority.py`
   guards the P0 release separation; it used `importorskip` and silently skipped in the
   release env. It is now a hard import with PyYAML in `requirements-dev.txt`.

## Remaining / not done

- **Authenticode signing: NOT AVAILABLE.** No credentials exist in the repo. The release
  workflow has the correct order wired (build → sign → *then* hashes/manifest) and records
  this string when no certificate is present. Windows will show SmartScreen.
- **`main` was not touched.** It is still beta-era (`459faf5`, 0.9.0-beta.5) and does not
  contain `v2.0.0`. Like 2.0.0, this release is tagged off the release branch. Making this
  branch the new stable `main` is a separate, deliberate merge.
- **A→B scope limit.** `scripts/updater_ab_acceptance.py` drives the updater *module*, not a
  running Electron window, so "active work blocks the install" and "the old app exits
  cleanly on its own" are covered only by unit-level tests of `installDownloadedUpdate()`.
- **No `LICENSE` file exists** in the repo, though the project claims MIT. Worth adding.

## Disposable paths used

Everything under `C:\LecturePackScratch\` (`builds/`, `results/`, `logs/`, `data/`) plus the
short staging path `C:\LPB\cand`. `C:\Users\marsh\LecturePackData` was never targeted — every
command used an explicit disposable `--data-dir`.
