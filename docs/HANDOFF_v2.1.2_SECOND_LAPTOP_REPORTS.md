# Handoff — LecturePack v2.1.2: five reports from a second laptop

**Date:** 2026-08-24
**Branch:** `claude/electrapack-ui-bugs-1866cc` (worktree `study-ai-performance-47ffd0`)
**Base:** 2.1.1 (`767ccaa`)
**Status:** code complete, **suite green (2015 passed / 23 skipped / 0 failed)**,
**packaged and self-test green**, **NOT tagged, NOT published — blocked by OBS-04**

---

## 1. What this release is

Five things reported after installing 2.1.1 on a second, previously-unused laptop, plus
one thing asked for while the work was in flight (installer branding).

**The pattern worth carrying forward is not the bugs. It is that two of the five were
already marked FIXED in this ledger.**

> **A fix verified at the function it changed is verified against the wrong thing.**

- **BUG-63 re-opens BUG-62.** Process *does* follow the running lecture. Three tests prove
  `followActiveProcessingJob` picks the right lecture. None of them asked whether it is
  *reachable* from the button a student actually presses — and from the Process nav, while
  already on Process, it was not: `setScreen` returned before ever reaching it.
- **BUG-65 re-opens BUG-08.** The per-lecture workspace works. `setActiveJob` really does
  clear the chat on every switch. It clears `LP.state.chat`, which belongs to the chat
  surface **Study V2 replaced**. The live Ask pane keeps its entire history in the DOM and
  nothing touched it. The user's words were "we made this fixed before, but I don't know
  how it got lost in the code" — it was never lost, it was applied to a dead surface.

When triaging anything reported as "we fixed this already", the first question is
**"which surface did that fix land on, and is it still the one on screen?"**

---

## 2. The five, and one addition

| # | What | Where |
| --- | --- | --- |
| BUG-63 | Process nav was a dead click when already on Process | `app/ui/app.js::setScreen` |
| BUG-64 | Every Study answer flashed the whole screen | `app/ui/app.js` record call sites |
| BUG-65 | Ask showed the previous lecture's conversation | `app/ui/app.js::setActiveJob` |
| BUG-66 | Meters did not correspond to the live log | `job_controller.py`, `cv_engine.py` |
| BUG-67 | Installer task checkbox clipped on a scaled display | `lecturepack.iss` — **not confirmed** |
| — | Branded installer wizard artwork | `make_wizard_images.py`, `lecturepack.iss` |

Full root causes are in `BUG_LIST.md`. Two things there are worth repeating here.

**BUG-66 had two holes of the same shape.** The log and the meters are fed by *different*
signals, and only Detect Slides and Export were ever wired to a progress signal at all.
Transcribe emitted **none** — the bar sat at 0 for most of a long run. Detect Slides hit
100% about two-thirds through, then deduplicated and re-decoded slides at full resolution
with the log streaming beside a pinned bar. Transcribe now derives its percent from live
segment end timestamps against the known source duration; slide detection reserves
`SCAN_PCT=85` / `DEDUP_PCT=92` and reports its tail on both decode paths.

**Neither bar invents a number.** With no usable duration or no timestamp, no percent is
claimed and the meter holds its last real value. A meter that guesses is the 2.1.0
"reported success for work it had not done" family wearing a different hat, and Inspect /
Extract Audio / Align are deliberately still silent for the same reason.

---

## 3. BUG-67 is OPEN. Do not close it.

The installer wizard's task checkbox was reported clipped and overlapping the line above.

**What was verified:** the page was compiled from an identical `[Setup]`/`[Tasks]` block,
launched and captured **at 96 DPI on 1920×1080 — it renders correctly.** The compiled
`Setup.exe` manifest was read directly: it declares `<dpiAware>true</dpiAware>` and nothing
else. System DPI awareness only, no `PerMonitorV2`. So the wizard is laid out for the DPI
at process start and bitmap-scaled afterwards, at which point fonts stop fitting the
control rectangles measured for them. That is consistent with the report, and **no `.iss`
directive can change that manifest.**

**What was NOT verified:** the symptom itself. It has never been reproduced here.
`WizardSizePercent=120` is a mitigation reasoned from a manifest, not a confirmed fix.
Closing a user-visible report on inspection is exactly what OBS-01 got wrong.

**It needs the reporter's laptop, at its real scaling, running the 2.1.2 installer.**

A near-miss worth keeping: `WizardResizable=yes` was set alongside it and then removed —
this Inno version compiles it to *"obsolete and ignored"*. It was caught only because the
probe build output was read for **warnings**, not just for "Successful compile". Read the
whole compile output.

---

## 4. Installer branding

`app/packaging/make_wizard_images.py` renders the app's mark (same proportions as
`make_icon.py`) on the dark shell colour with the aqua accent, at **all six of Inno's DPI
sizes** for both the welcome banner and the header icon. `.bmp` files are committed so
builds do not need Pillow. `DisableWelcomePage=no` because modern style hides the page the
banner lives on.

**Only the banner and header icon can be themed.** The wizard body is drawn with system
colours; a fully dark wizard needs a custom VCL style (`.vsf`) that cannot be authored from
this toolchain. Do not spend time trying to force it with colour directives.

---

## 5. Verified

- **Full Python suite: 2015 passed, 23 skipped, 0 failed** (was 2011 at 2.1.1).
- **`node --check`** clean on `app/ui/app.js`.
- **The new regression tests were confirmed FAILING against 2.1.1's source first** — 15 of
  18 fail when the three changed source files are reverted to `HEAD`. The 3 that still pass
  are invariant guards (entrance motion, feed delegation, segment relay), which is correct.
- **The installer compiles clean** from the real `.iss`, warnings included, and the branded
  welcome page was launched and captured.
- All four authoritative version surfaces agree at 2.1.2.

- **The packaged build succeeded** and its embedded self-test is green: FFmpeg, ffprobe,
  Whisper runtime/smoke/model, Rust Study Core, yt-dlp, yt-dlp-ejs, Deno, data directory,
  controller. Rust Study Core: `cargo test --release`, 11 passed.
- **Artifact hashes were recomputed from the bytes on disk** and agree with both
  SHA256SUMS and the updater's release manifest.

### NOT verified
- **The acceptance gate does not pass reliably — see 5b / OBS-04. That is why nothing is
  published.**
- BUG-66 has still never been watched against a **real lecture**; the acceptance run uses
  the bundled demo video. The meters are the whole point of that fix and no human has seen
  them move.
- BUG-63/64/65 have not been exercised by hand in the packaged app.
- BUG-67, as above.
- Updater E2E (RELEASING.md step 9) and the clean-machine script (step 10) were not run.

---

## 5b. The publish is BLOCKED — OBS-04

The 2.1.2 artifacts are built and their self-test is green, but
`scripts/electron_packaged_acceptance.py` **fails 2 runs in 4** on the same build with
`packaged app exit code 1`. Every other check passes in every run, including
`restore_passed`. The harness posts `WM_CLOSE`, waits 20s and then kills — and a Windows
kill is exit code 1 — so the failure means "the app did not finish quitting in time", not
"the app errored". Evidence points at the quit outliving the bound while an update check is
in flight; not proven. Full detail in `BUG_LIST.md` under OBS-04.

It is **not** a 2.1.2 regression: this release changed the renderer and the engine, not the
shutdown path. But at a 50% failure rate, 2.1.1's recorded "packaged acceptance 16/16" is
what a single lucky run of a coin flip looks like. **Run this gate repeatedly before
believing it.**

Artifacts are at `C:\LecturePackScratch\builds\release-2.1.2` (installer, portable zip,
SHA256SUMS, release manifest; hashes verified against the bytes on disk).

**AUTHENTICODE SIGNING: NOT AVAILABLE.**

---

## 6. Next session

1. **OBS-04 first — it is the gate that decides whether anything may ship.** Instrument
   `requestQuit()`/`app.quit()` and run the acceptance gate ten times. Decide whether the
   quit is genuinely slow or the harness bound is too tight; do not raise the bound before
   knowing which.
2. Run a **real lecture** end to end and watch the two meters against the log. That is the
   only way BUG-66 gets confirmed. (RELEASING.md steps 4-6 are already done: the 2.1.2
   artifacts exist and are hash-verified.)
3. Exercise BUG-63/64/65 in the packaged app: queue two lectures and press the Process nav;
   answer a demo quiz question; ask something in two lectures and switch between them.
4. Have the reporter run the 2.1.2 installer on the laptop that showed BUG-67.
5. Tag and publish. Note BUG-59: the release workflow has never once succeeded, so this is
   a local build plus `gh release create`.

---

## 7. Known traps

1. **`setScreen`'s early return is load-bearing for motion.** It exists so re-selecting a
   screen does not replay the entrance animation. BUG-63 gave it a body; it must still
   return before `LP.motion.nav`. A test pins that ordering.
2. **The Ask feed is stored as markup, and that is only safe because every control inside
   it is bound by DELEGATION** (on `#study-ask-feed` or on `document`). A test asserts it.
   The moment a per-element listener is added inside the feed, the snapshot has to become a
   real message model.
3. **`studyV2Load()` is a full content reload.** It is the right call on screen entry and
   the wrong call after any interaction. Anything that only needs progress should use
   `studyV2RefreshProgress()`.
4. **Read ISCC's full output.** "Successful compile" can sit directly under a warning that
   your directive was ignored.
5. **Do not automate the live desktop with `SendKeys` to inspect the wizard.** It was used
   here to page through the installer and one keystroke batch landed in an unrelated
   foreground window. Build the probe and have a human look, or capture the first page only
   (no navigation needed for the welcome page). This is OBS-03's cousin: there is still no
   safe harness for driving native UI in this project.
