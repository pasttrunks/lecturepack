# Handoff — LecturePack v2.1.0: thirty findings, one recurring mistake

**Date:** 2026-08-23
**Branch:** `claude/lecturepack-2-10-release-6b5fb5`
**Base:** `e2ca2cf` = v2.0.9 (released 2026-08-20)
**Status:** code complete, suite green, **built and verified against the packaged build**;
NOT yet tagged, NOT yet published
**Source of work:** `C:\LecturePackScratch\results\stress-test-209\FINDINGS.md` (F-01 … F-38
plus Addendum A/B), an adversarial QA pass against the installed 2.0.9.

---

## 1. What this release is

The stress test filed 38 numbered findings; F-21…F-28 were never assigned, so the real
count is **30**. All 30 are addressed. Twenty-eight were real and are fixed, one (F-07) was
a misread and is recorded as not-a-defect, and one (F-32) could not be reproduced and got a
mitigation rather than a fix.

**The single most useful thing to carry forward is the pattern.** Nearly every P1 was the
same bug in different clothing:

> **the app reported success for work it had not done.**

- A transcript save that could not land returned `saved=true` (F-35).
- A subject rename that moved 2 of 3 lectures toasted "3 lectures updated" (F-30) —
  because the toast fired *before* the backend answered.
- An update check that succeeded reported the build could not update (F-34).
- A pipeline failure was announced to the renderer and never written to disk (F-17).
- A subject that failed to prepare kept the previous lecture's content on screen (F-29).

When triaging anything in this family, the first question is **"who confirmed this, and did
they wait for the answer?"** The second is **"is there a timer that can overwrite the real
result?"** — F-34 (4s) and F-36 (1500ms) were the same bug in two different screens, and
both had been shipping for releases.

---

## 2. Commits

| Commit | What |
| --- | --- |
| `dd08b76` | shell-level UI: breadcrumb, scroll affordance, disabled controls, Study empty state, storage line, footer stage label, cheat-sheet accuracy |
| `227a5e2` | three P1s that reported success falsely: transcript corrections, updater, subject rename |
| `6c6c601` | subject scope integrity, comprehension retries, grader self-contradiction, undo depth, multi-link import |
| `94cdb51` | light-theme contrast, drag auto-scroll, import feedback |
| `e0e70b6` | job lifecycle (failure persistence, running derivation, Process states), ffmpeg errors, export honesty, Vulkan validate |
| `ce00632` | 42 regression tests, bridge contract entry for `demo_session`, F-32 mitigation |
| *(this)* | 2.1.0 version bump, changelog, ledger, handoff |

---

## 3. Version

**2.1.0**, chosen by the owner over `2.10.0` and `2.0.10`.

This mattered enough to ask. `2.10` was the word used in the request, but shipping literal
`2.10.0` is a one-way door: in semver `2.10.0 > 2.1.0`, so a later `2.1.x` would be treated
as *older* by `updater.compareVersions` and never offered. `2.1.0` keeps every later number
available and is the honest signal for a release this size — thirty behaviour changes,
several touching persisted job state.

All four authoritative surfaces agree and `test_every_authoritative_version_surface_agrees`
passes: `app/desktop/version.py`, `app/packaging/lecturepack.iss`,
`electron-spike/package.json`, `electron-spike/package-lock.json` (two entries).

---

## 4. Verified

- **Full Python suite: 2002 passed, 7 skipped, 0 failed** (was 1937 at 2.0.9). The 7 skips
  are the documented build-asset gates — packaged onedir fixture, the 148 MB Whisper model,
  the opt-in live-AI smoke — all absent on a bare checkout.
- **`node --check`** clean on `app/ui/app.js`, `production-main.js`, `ai-gateway/src/tasks.js`.
- **The F-17 regression tests were confirmed FAILING against the unfixed line first.**
  Reverting the stickiness guard reproduces `'pending' == 'failed'` exactly, including
  across a reload. This is deliberate: 2.0.9's own handoff records a regression test that
  passed against broken code, and a green test on a broken line is worse than no test
  because it retires the suspicion. Do not trust a new concurrency or persistence test here
  until it has been seen to fail.
- **Driven in a real Chromium**, not just asserted against source. The renderer was served
  over HTTP and exercised through its own handlers:
  - breadcrumb renders `Home` alone, both lecture-segment nodes hidden;
  - home empty-state hints clear the footer by 9.3px at 1344×821;
  - Study with no lecture shows the empty state, ready panel not rendered, all six mode
    tabs disabled;
  - both export buttons resolve to the same neutral background, and clicking the disabled
    PDF button toasts "Load a lecture first — there is nothing to export yet.";
  - the format rows answer a click with "Every export writes all of these transcript
    formats." instead of toggling;
  - the cheat sheet fits (panel bottom 777 of 821) and says "Keep the slide and move on / J";
  - **undo depth proven behaviourally**: two keeps, one reject, undo, undo → all four
    slides back to `pending`, which was impossible before;
  - **WCAG sweep**: every visible text node across all eight screens plus the header,
    light theme, **zero AA failures**.

---

## 4b. Verified against the PACKAGED build (added after the first pass)

The first draft of this handoff listed the packaged verification as outstanding. It is not.

- **Release build produced**: installer 372.7 MB, portable zip 481.3 MB, SHA256SUMS,
  release-manifest.json. All four in `dist/releases/2.1.0/`.
- **Packaged self-test: 12/12 green**, including `study_core.ok == true` against a freshly
  built Rust core.
- **Packaged launch smoke**: window shown after 0.61s.
- **Packaged UI is byte-identical to source** (`app.js`, `app.css`, `index.html`,
  `bridge.js` all `cmp`-clean), so every renderer fix is in the shipped payload.
- **Full packaged acceptance gate: PASS on all 16 checks** — real import, real processing,
  transcript generated, export completed with 13 files, clean exit, relaunch, job restored,
  no orphan processes, no renderer failures, no bridge errors.
- **BUG-49 (transcript corrections) proven in the packaged build.** Drove the frozen
  sidecar through a real run, then saved corrections: `working.json` holds both segments
  with `edited=true` and the probe's marker text, `edited.json` mirrors both overrides,
  the edit **survived a full restart**, and the corrections badge read 2 — the counter
  F-35 reported as permanently stuck. A deliberately mismatched row count was refused
  with "the transcript on screen no longer matches the saved one (1 lines shown,
  2 saved)" instead of silently truncating.
- **DEF-056 (grader self-contradiction) proven against the LIVE production gateway**, using
  Addendum A1's exact repro. Before: `score=0` with feedback calling the student's
  transparent-fur statement incorrect while `ideal_answer` said the same thing. Now:
  `score=0.33` (1 of 3 rubric points, which the instruction always asked for and was not
  getting) and feedback that credits what was right and names only the two rubric points
  actually missing. No contradiction.
- **Updater ordering for the real upgrade path**: `2.0.9 -> 2.1.0` compares `-1`, so an
  installed 2.0.9 is offered this build. `2.1.0` also leaves `2.2.0` and `2.10.0` ordering
  correctly for later.

### The acceptance gate was broken, not the build

The gate failed on first run: `transcript_generated`, `export_completed`,
`export_file_count` and `restore_passed` all FAIL. **None of that was a regression.** The
gate imported its fixture with `bundled_demo: True`, which marks the job as a guided-demo
job — and a guided-demo job is deleted the instant its pipeline completes, by design
(`_cleanup_demo_session`, the behaviour BUG-56 makes visible rather than removes). The gate
was then asking for the transcript and export directory of a job the app had already
deleted, so those checks could never pass however healthy the build was.

Proven by driving the packaged sidecar both ways: `bundled_demo=False` yields 2 transcript
segments and 13 export files; `bundled_demo=True` yields no job directory at all. The gate
now imports as an ordinary video — it is a test of the packaged RUNTIME, not of the guided
demo — and passes 16/16.

This is worth remembering: a release gate that cannot pass is worse than no gate, because
its red is indistinguishable from a real regression. It had presumably never been run
green; 2.0.9's handoff records steps 4–14 as outstanding.

---

## 5. NOT verified — read this before shipping

- **Steps 11–14 of `RELEASING.md` are outstanding**: tag, push, publish the GitHub
  release, and confirm an installed 2.0.9 actually offers the update. The artifacts exist
  and the version comparison is proven; what has NOT happened is a real feed round trip.
- **BUG-50 (failure persistence) and BUG-52 (subject rename) have not run in the packaged
  app.** Both are covered by tests — BUG-50's were confirmed failing against the unfixed
  line — but neither has been observed end to end in the built product. BUG-49 has, so
  these two are what remains of that category.
- **Nothing that needs a human eye has been judged.** Whether the new copy reads well,
  whether the demo badge lands, whether the disabled-control toast is helpful rather than
  noisy — none of that is machine-checkable, and it is what the retest script is for.
- **The installer cannot be built from this worktree directly.** Its path is ~48 characters
  longer than the normal repo root and Inno Setup hits MAX_PATH mid-compression — the exact
  hazard `lecturepack.iss`'s own header warns about. Build through a short junction
  (`mklink /J C:\lp210src <dist>`); this is how 2.1.0's installer was produced.
- **F-32 is mitigated, not fixed.** See the ledger entry. If the app vanishes again, the
  log will now carry the stack; until then the root cause is unknown.
- **No Authenticode signing.** Unchanged — no valid credentials exist in this repo.
- **The gateway prompt change (DEF-056) has not been run against the live model.** The
  instruction forbids the self-contradiction; whether the routed model honours it needs one
  real grading call with a deliberately rubric-incomplete answer.

---

## 6. Traps found while doing this — do not re-learn them

1. **`pointer-events:none` removes an element from `elementsFromPoint` too.** The first
   attempt at F-06's click-to-explain hit-tested for the disabled control and never found
   it. It geometry-tests `[data-ctl-tip]` rects now and separately confirms nothing is
   covering them.
2. **A renderer HAR does not capture bridge IPC.** F-15 cited "zero network requests" as
   proof the Check link button was dead. `probe_media_url` crosses the IPC bridge to the
   sidecar and never appears in a renderer HAR. The button was alive and slow.
3. **F-38's "auto-scroll does not exist" was wrong.** It exists and is wired into the
   pointer path; the code inspection grepped for `scrollBy` and it uses `scrollTop +=`.
   The real bug was that the container is resolved from the pointer, and the pointer ends
   up over the footer.
4. **F-31's "grades an EMPTY submission" was wrong** and is contradicted by code on both
   sides. The 0% was a real grade of a rubric-incomplete answer.
5. **JS string literals built in `app.js` must not contain unescaped single quotes.** Three
   separate edits broke `node --check` on `font:500 12px 'Space Grotesk'` inside a
   single-quoted JS string. The codebase's own convention is the unquoted CSS form
   (`font:500 12px Space Grotesk`) in JS-built markup — follow it.
6. **`set_stage_status` excludes `STAGE_REVIEW_READY` from its recomputation.** That
   exclusion is load-bearing elsewhere; the fix was to make terminal states sticky, not to
   change the exclusion. Anything else that derives status from that table has the same
   hazard.

---

## 7. Next session

1. `RELEASING.md` from step 4. Build the Rust Study Core, package the sidecar, build the
   installer and portable zip, run the packaged self-test.
2. Exercise BUG-49, BUG-50 and BUG-52 against the packaged build with a real lecture —
   these are the three whose fixes touch persisted state and have never run outside a test.
3. Re-run the stress test's own top-10 against the packaged build. The findings document
   is a ready-made acceptance script.
4. Updater E2E from an installed 2.0.9 → 2.1.0.
5. Tag and publish.

---

## 8. 2.1.1 — the four things reported against the shipped 2.1.0 (2026-08-23)

Reported with a screen recording after 2.1.0 shipped.

- **BUG-60, the important one.** A queued lecture could not be dragged ANYWHERE.
  `_jobIsDraggable` was `_jobIsReady || _jobIsReprocessable`, and both end in
  `&& !_jobInQueue(j.id)` — a Process-target question applied to every drag. Queue
  anything and the whole library went inert. **This supersedes OBS-01, which I filed the
  day before as "seen once, not reproduced" while offering the queue rule as the *benign*
  explanation. The benign explanation was the bug.** OBS-01 reasoned from a diff, found the
  drag path byte-identical to 2.0.9, and concluded there was probably nothing wrong. The
  code *was* identical — the defect predates 2.1.0 — but unchanged is not correct, and a
  user-visible report must not be closed on a diff. It was unreproducible only because
  nothing can drive a drag against this app (OBS-03), which should have been read as "I
  cannot test this", not "this is probably fine".
- **BUG-61** — the gesture shuddered because the queue rebuilt itself under the pointer
  several times a second while a lecture transcribed. Renders defer during a drag now.
- **BUG-62** — Process opens on the lecture that is actually running. Navigation carrying a
  chosen lecture is left alone, guarded by `_screenChangeCarriesJob`; the ordering it
  depends on inside `setScreen` is now pinned by a test.
- **OBS-02, the taskbar icon: NOT a code defect.** Every app-side surface is correct (exe
  icon, seven-size .ico, shipped resource, window icon visible in the user's own recording,
  AUMID set pre-window and matching the installer shortcuts, shortcuts using the target's
  icon). Windows is serving a cached icon keyed to an identity string that has never
  changed, which is precisely why changing code for it repeatedly never worked. **Do not
  change code for this again** unless it appears on a clean machine.

Verified: suite 2011 passed / 7 skipped / 0 failed; packaged self-test 12/12; packaged
acceptance **16/16 including app_launched and restore_passed**; launch smoke 0.61s; UI
byte-identical to source; hashes agree across installer, SHA256SUMS and updater manifest.

**Testing note for next time:** the acceptance gate and launch smoke both fail with
`app_launched=False` / "exited after 0.6s with code 0" if a copy of LecturePack is already
running — `requestSingleInstanceLock` hands off and exits. That is correct behaviour, not a
build failure. Close the app before running either.
