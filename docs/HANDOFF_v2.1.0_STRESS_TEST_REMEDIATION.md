# Handoff — LecturePack v2.1.0: thirty findings, one recurring mistake

**Date:** 2026-08-23
**Branch:** `claude/lecturepack-2-10-release-6b5fb5`
**Base:** `e2ca2cf` = v2.0.9 (released 2026-08-20)
**Status:** code complete, suite green, **NOT yet built, NOT yet tagged, NOT yet published**
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

## 5. NOT verified — read this before shipping

- **Nothing has been built or packaged.** No installer, no portable zip, no hashes, no
  manifest. `RELEASING.md` steps 4–14 (Rust Study Core, sidecar package, installer,
  packaged self-test, updater E2E, gates, tag, publish) are all outstanding.
- **No fix has been exercised against the packaged app.** Everything above is the suite,
  the source, and the renderer in a plain browser. The stress test that found these ran
  against an *installed* build; the remediation has not.
- **The three backend data fixes have not run against a real job on a real gateway.**
  BUG-49 (transcript save), BUG-50 (failure persistence) and BUG-52 (subject rename) are
  driven deterministically by tests. That is not the same as observing them in the app.
  These are the three to exercise first in any packaged verification.
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
