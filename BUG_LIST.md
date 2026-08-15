# BUG_LIST.md — LecturePack bug ledger

**Purpose.** A durable, append-only record of **every bug we've ever discovered** in this
project: the symptom, the real root cause, **what we tried, what worked, what didn't**, and
the current status. When a new bug shows up, **scan this file first** — many "new" bugs are
old bugs recurring, or a fix that regressed. This is the institutional memory so we never
re-debug the same thing from scratch.

> **CLAUDE (every session on this project): read this file during the session-start ritual,
> right after the newest `HANDOFF-*.md`. Before touching any area that has a bug entry here
> (or any historically bug-prone area), check the relevant entry. When you fix a bug (new or
> old), or a fix regresses, UPDATE the matching entry (or add one) in the SAME session — don't
> let it drift.**

## How to use this file

- **New bug reported?** Search by area. Compare the symptom (and environment: build / OS)
  against existing entries. If it matches an entry marked ✅ FIXED, suspect a
  **regression** and reopen it — don't start debugging blind.
- **Note the build the bug was seen on.** A report against the *live/shipped* build is not
  evidence that an *unreleased* fix failed.
- **Status legend:** 🔴 OPEN · 🟠 PARTIAL / needs verification · ✅ FIXED (verified) ·
  🟡 FIXED (not yet verified on the real target) · ⚪️ DEFERRED (known, accepted for now).
- **Compiling ≠ fixed.** A behavioral fix is 🟡 until exercised on the real target, then ✅.

### Project-specific notes

- The shipped UI is **`app/ui/`** (WebEngine) driven by `app/desktop/bridge.py`. The old
  `lecturepack/ui/` PySide pages are dead code — a bug "in the UI" always means `app/ui/`.
- UI defects have two halves: the **markup** (`index.html`) and the **behaviour** (`app.js`).
  A markup-only fix is not a behavioural fix; verify in a browser or the real app.
- `~/LecturePackData` is the user's real data and is never a test target. Use
  `LECTUREPACK_DATA_DIR` to point a run at a disposable profile (added 2026-07-25).

---

## OPEN / ACTIVE

*(newest first)*

### BUG-41 — guided-demo overlay: the four dim regions OVERLAPPED, showing a hard seam   ✅ FIXED (verified in the packaged app)
- **Area:** `app/ui/app.js::positionTourSpotlight`, `app/ui/app.css` (3.8a guided tour).
- **Found:** 2026-08-12, from user screenshots of the packaged guided demo.
- **Symptom:** a hard vertical edge down the window on every tour step, and the
  *highlighted* control read as dim rather than lit. The seam always landed at
  `left + width` of the target — x≈1130 on Exports (right edge of *Export all*),
  x≈510 on Review (right edge of Keep/Reject), x≈1337 on Home (right edge of the
  dropzone).
- **Root cause:** the four regions must TILE the viewport but did not. `top` and
  `bottom` each span the full width; `left` spans only the target's height band;
  but `right` spanned the **full viewport height**. So both right-hand corners
  were painted twice (.65 over .65 ≈ .878) while the left-hand corners were
  painted once. That asymmetry *is* the seam, and it also meant the target was
  being judged against two different surround values.
- **Wrong first diagnosis (mine):** I read `#guided-tour-overlay{…background:
  rgba(8,10,14,.65)}` on line 748 and concluded the overlay double-dimmed the
  regions. Line **749** immediately overrides it to `transparent`. Two adjacent
  rules for the same selector: read the *whole* cascade before blaming it.
- **Rejected fix — do not retry:** replacing the four rects with one element
  carrying `box-shadow:0 0 0 100vmax` plus geometry transitions. It is cleaner
  and makes seams structurally impossible, but it re-creates **exactly** the
  design AD-20 removed. See BUG-42.
- **Fix:** give `right` the same height band as `left`:
  `setTourDimRect('tour-dim-right', left + width, top, viewportWidth - left - width, height)`.
- **Tests:** `test_spotlight_dim_regions_tile_the_viewport_without_overlapping`
  (structure) and `test_dim_regions_tile_exactly_for_real_target_geometry`, which
  executes the real rect arithmetic under Node and asserts no two regions overlap
  and `dim area + hole area == viewport area` for four viewport/target cases.
- **Verified (2026-08-12) in the packaged Electron renderer over CDP**, UI swapped into a
  copy of the `guided-demo-fix-20260811` candidate: at 1920x1009 the four regions tile
  the viewport EXACTLY -- 1,926,960 dim + 10,320 hole = 1,937,280 = vw*vh -- with **zero
  pairwise overlaps**, and the dim computes to a single `rgba(8,10,14,0.65)` rather than
  the doubled ~.88. Packaged acceptance is byte-identical to the baseline candidate.
- **Lesson:** "four regions around a hole" is a tiling problem. Assert the tiling
  (area covered exactly once), not the presence of four elements — the old test
  checked that all four ids existed, which the buggy code satisfied.
- **Files:** `app/ui/app.js`, `tests/test_polish_ui.py`.

### BUG-42 — the spread-shadow spotlight is BANNED by AD-20; do not reintroduce it   ⚪️ DEFERRED (known, accepted for now)
- **Area:** `app/ui/app.css` (guided tour), `docs/DECISIONS.md` AD-20.
- **Found:** 2026-08-12, while attempting to redesign the overlay (BUG-41).
- **Why this entry exists:** the spread-shadow spotlight is the *obvious* fix for
  the seam, it is what an external design review will recommend, and it is what
  the code originally did. It was removed on purpose and the reasons are not
  visible from the CSS.
- **History:** before `0207f08` (2026-08-02) the spotlight was
  `box-shadow:0 0 0 9999px rgba(8,10,14,.65)` + `transition` on left/top/width/
  height + `will-change:left,top,width,height`, with `filter:drop-shadow` on the
  arrow. **AD-20** replaced all of it with four static rects because beta.10 was
  smooth on the dev machine but *flickered and felt laggy on a separate
  clean-install Windows machine*. `--disable-gpu` did not change the symptom, so
  it is not GPU-specific and will not reproduce on the dev box.
- **Standing constraint:** no spread-shadow scrim (`9999px`/`100vmax`), no
  geometry transitions on tour elements, no `will-change`, no `filter:drop-shadow`
  on the arrow. Guarded by `test_spotlight_uses_static_scrim_and_geometry_without_
  expensive_effects` and restated in `test_css_spotlight_is_pointer_transparent_
  and_uses_a_static_scrim`.
- **Lesson:** a perf constraint that only reproduces on *other people's hardware*
  must be written down where the next person will hit it, or it gets "cleaned up"
  by someone whose machine is fast enough not to notice.
- **Files:** `app/ui/app.css`, `docs/DECISIONS.md`, `tests/test_flashing_reliability.py`.

### BUG-43 — DEMO·STUDY step targeted markup Study V2 had superseded   🟠 PARTIAL / needs verification
- **Area:** `app/ui/app.js::TOUR_PHASES.study`, `app/ui/index.html`.
- **Found:** 2026-08-12, from user screenshots.
- **Symptom:** the Study step rendered with **no dim, no ring and no arrow** —
  the only step with no spotlight at all — while its card told the user to "try
  the chat box", which was not on screen.
- **Root cause:** the step targeted `#demo-study-actions`, which lives inside
  `<div id="study-legacy" hidden>` (`index.html:422`). Study V2 owns the visible
  Study workspace now. `positionTourSpotlight` collapses on
  `target.closest('[hidden]')`, so the step correctly refused to point at a
  hidden node — and then had nothing to show.
- **Fix:** added `id="demo-study-actions-v2"` to the Study V2 overview action row
  and retargeted the step; retitled to "Your study workspace" with copy describing
  concepts/flashcards/quiz, which is what is actually on screen. Deliberately did
  **not** target the V2 Ask pane: it is behind a tab *and* depends on a model
  being loaded, so it can fail in the same "spotlight on nothing" way.
- **Tests:** `test_every_tour_target_exists_and_is_not_inside_a_hidden_ancestor`
  parses the markup and walks the real open-element stack for all five steps.
  Screen-level containers (`[data-screen]`) are exempt — every screen is `hidden`
  at rest and unhidden by the `setScreen()` the step itself declares.
- **Verified (2026-08-12), partially:** `#demo-study-actions-v2` is present in the packaged
  renderer and `#study-legacy` is confirmed `hidden` there, which is the root cause.
- **BLOCKER on full verification:** the end-to-end guided demo cannot be driven on this
  machine. A fresh profile lands on the first-run Runtime Setup gate, which is green-only
  by design (bypass buttons were deliberately removed) and cannot go green without the
  Whisper model and ffprobe, which are absent here. Packaged acceptance confirms it:
  `transcript_generated` FAIL on BOTH the fixed and the baseline candidate. Anyone with a
  complete runtime should replay the tour and confirm the Study step now lights up.
- **Lesson:** when a workspace is replaced (V2), every *external* reference into
  the old markup — tours, deep links, tests — is a silent dangling pointer. The
  legacy nodes still exist, so nothing throws.
- **Files:** `app/ui/app.js`, `app/ui/index.html`, `tests/test_guided_tour.py`.

### BUG-44 — the coach card covered the control it was describing   🟠 PARTIAL / needs verification
- **Area:** `app/ui/app.css#guided-tour-card`, `app/ui/app.js::positionTourCard`.
- **Found:** 2026-08-12, from user screenshots (DEMO·IMPORT, DEMO·EXPORTS).
- **Root cause:** the card was pinned `right:24px;bottom:24px` regardless of where
  the spotlight was, so on steps whose target sits low or right it sat on top of it.
- **Fix:** `positionTourCard()` anchors it below → above → right → left, first side
  it fits with a 16px gutter. When the target nearly fills the window and no side
  fits, it docks to the side with the most room rather than defaulting to a corner
  that buries the target. Static placement only — no transition (see BUG-42).
- **Tests:** `test_tour_card_is_anchored_beside_the_target_and_never_covers_it`
  runs the real function under Node against five viewport/target cases and asserts
  the card is on-screen, adjacent, and does not intersect the spotlight rect.
- **Verified (2026-08-12), mechanism only:** in the packaged renderer `--tour-card-x/y`
  drive the card's computed `left`/`top`, and the card does not intersect the hole.
  The live placement decision across all five steps is NOT verified -- see the blocker
  on BUG-43.
- **Files:** `app/ui/app.js`, `app/ui/app.css`, `tests/test_polish_ui.py`.

### BUG-45 — tour layer sat BELOW the model tooltip   ✅ FIXED (verified in the packaged app)
- **Area:** `app/ui/app.css`.
- **Found:** 2026-08-12, during the BUG-41 review.
- **Root cause:** `#guided-tour-overlay` was `z-index:170` while `.lp-model-tooltip`
  is `180`, so a model tooltip could render *over* the tour scrim. The tour's
  internal layers were also 0/1/2 — a flat scale with no room and no relationship
  to the app's own stacking.
- **Fix:** contiguous band — scrim 200 < lifted target 210 < ring 220 < arrow 230
  < card 240 — above the tooltip (180) and below the drag ghost (300).
- **Tests:** `test_css_spotlight_is_pointer_transparent_and_uses_a_static_scrim`
  now parses the z-indexes and asserts both the internal order and the clearances.
- **Verified (2026-08-12):** computed z-indexes in the packaged renderer are scrim 200,
  ring 220, arrow 230, card 240 -- above the model tooltip (180), below the drag ghost (300).
- **Files:** `app/ui/app.css`, `tests/test_guided_tour.py`.

### BUG-33..BUG-40 — the guided-demo hardening pass (all 🟠 PARTIAL / needs verification)
> Fixed on `sol/polish-integration` up to `a758885`, but **downgraded from FIXED to
> PARTIAL on 2026-08-12 at the user's instruction**: none has been exercised on the
> packaged build since the final patch, and the guided demo has a history of a fix
> landing while the *observable* behaviour stayed broken (see BUG-41/43). Do not mark
> any of these ✅ without a packaged run.

- **BUG-33 — Runtime Setup showed all five checks as `Pending`.** Root cause was not
  the normalization: `Sidecar._packaged_self_test()` rebuilt its response dict and
  **dropped `health.checklist`**. Two earlier attempts missed it — normalizing packaged
  health in the bridge, then discovering PyInstaller was loading the *installed*
  `lecturepack` package instead of the worktree. Fix: preserve the checklist in the
  sidecar envelope + a renderer `checklistReady` guard. Last packaged result: 5 ready,
  state gate 24/24.
- **BUG-34 — "Try the demo lecture" did nothing.** The button animated
  `#glowing-demo-card`, which was inside hidden `#home-demo` with a zero-size rect, so
  it never emitted `animationend` and the callback that starts the tour never ran.
  Fix: detect hidden/zero-size cards and invoke the fallback directly. (Related: the
  old `minW/minH` fallback box made this worse by drawing a glow around empty space —
  see the note in `test_spotlight_hides_when_target_missing`.)
- **BUG-35 — Replay skipped the drag/drop/import step.** The replay handler called
  `startGuidedDemo()`, which advanced straight to `imported/running`, switched to
  Process and started the backend job. Fix: replay stops at `DEMO · IMPORT`; the user
  must click *Use demo* or drag the video.
- **BUG-36 — The bridge auto-started processing and auto-exported.** `startDemoJob()`
  sent `import_video` then `start_processing` with `auto_export:true`, so the demo
  exported and cleaned itself up before the user could review. Fix: `auto_export:false`.
- **BUG-37 — The overlay broke after entering Process/Review.** Cleanup removed the
  temporary demo job and cleared `active_job` while the renderer deliberately kept the
  tour active, leaving the overlay attached to an empty workspace. Fix: terminal
  cleanup/failure and viewed-job removal dismiss the tour and return Home. **A user
  screenshot dated 8/11 18:45 still shows this** (Keep/Reject spotlit over "No lecture
  loaded"); it predates the fix, so reproduce before concluding either way.
- **BUG-38 — The bridge retained stale demo identity.** `demoSession` was not cleared
  after terminal events, so later ordinary pipeline events could be read as events for
  the old demo. Fix: emit the terminal demo event first, *then* clear `demoSession`.
- **BUG-39 — Guided-tour eligibility was inconsistent for existing users.** Logic mixed
  renderer localStorage, job count and durable backend state, so the guided card could
  be hidden while the fallback button was visible. Fix: durable versioned `guided_tour`
  eligibility + the real `replay_guided_tour` command.
- **BUG-40 — Tour highlighting and geometry were unstable.** The target could appear
  dimmed along with the background; geometry risked flicker and invalid Process/Review
  targets. Fix attempted: "stable four-region dimming", lifted targets, guarded
  geometry, stale-animation protection. **This one did not hold** — the four regions
  overlapped and the target was still dimmed. See BUG-41.

### BUG-43 — group study could never have worked for a single user   ✅ FIXED (verified live)
- **Area:** `lecturepack/services/group_study.py` (`prepare`), plus the deployed gateway.
- **Found:** 2026-08-15, first time the reduce was ever run against the real gateway.
- **Severity:** P0. The headline feature of 2.0.2, broken 100% of the time.
- **Symptom:** studying a group always returned `empty_analysis`, after a full-price
  ~11-25s AI request. Nothing in the UI could work.
- **Root cause:** two independent faults, either one fatal.
  1. **The deployed Worker was stale** — 8 tasks, predating both `group_analysis` and
     `expand_concept_material`. Live calls returned HTTP 400 `unsupported_task`. The
     inherited handoff claimed both routes were "live"; they were not.
  2. **The envelope was never unwrapped.** `GatewayClient.request()` returns
     `{"result": …, "diagnostics": …}` — the documented contract, unwrapped correctly by
     `ai_study_service.py:689`. `prepare()` passed the whole envelope to `normalize()`,
     which looked for `concepts` at the top level, found none, dropped everything and
     reported `empty_analysis`. A *correct* AI answer was thrown away every time.
- **Why every test passed:** all of them mocked the client with a *bare* analysis, so the
  mocks agreed with each other and with nothing else. The suite pinned a contract the
  gateway does not have.
- **Fix:** `unwrap_result()` takes the analysis out of the envelope (accepting a bare
  analysis too, since `prepare` also takes an injected `call`). Gateway redeployed — now
  reports `configured_tasks: 10, required_tasks: 10`.
- **Verified:** live against the production gateway — `ok=True` in 10.9s, 4 concepts,
  4 relationships, 2 through-lines, 2 gaps, every citation grounded to a real job, second
  call served from cache in 0.01s. Two regression tests added to
  `tests/test_group_study.py` pinning the real envelope; confirmed they fail without the
  fix (`normalize(envelope)` → 0 concepts, `normalize(unwrap(envelope))` → 1).
- **Lesson:** a mock is a claim about someone else's contract, and an unverified claim.
  When every test for a feature builds its fixture from the same wrong assumption, the
  suite's agreement is worthless — it proves the mocks match each other. One live
  round-trip before shipping would have caught both faults in a minute; instead a
  headline feature was tagged, packaged and acceptance-tested while being incapable of
  working. Test at least one real round trip per external contract, and treat "deployed"
  in an inherited doc as a rumour until a live probe agrees.

### BUG-42 — the M3 adversarial suite tested nothing it claimed to   ✅ FIXED (verified)
- **Area:** `tests/test_m3_adversarial_challenge.py` (harness only; no product defect).
- **Found:** 2026-08-15, running the suite the teamwork agents left behind. 6 failures.
- **Severity:** false assurance. The suite was reported as milestone coverage for group
  study and the packaged binary; it was covering neither.
- **Symptom:** 6 failures that read like product bugs — `no_ready_lectures` for groups
  that plainly had ready lectures, and a packaged `.exe` that appeared not to answer
  `health_check` at all.
- **Root cause:** four independent wrong assumptions in the fixtures.
  1. The job fixture wrote `study-content.json`; `study_v2.load_content()` reads
     `study_v2.CONTENT_FILENAME` = `study-content-v2.json`. Every group came back empty,
     so four tests were asserting against `no_ready_lectures` instead of the behaviour
     in their own docstrings.
  2. The "unready" fixture used the status string `"pending"`, which is not a real
     status. `load_content()` normalises unknown statuses and, seeing concepts, promotes
     them to `STUDY_READY` — the unready lecture was ready.
  3. Clearing a group asserts `manifest["group"] == ""`, but `set_job_group()` pops the
     key so the job reverts to its derived default. Absence is the contract.
  4. The packaged test sent `{"id": …}`; the sidecar reads `request_id` (see
     `production-main.js`). With no id, `_respond()` returns early and emits nothing, so
     a perfectly healthy binary looked dead. The in-process tests never caught this
     because the fixture stubs `_respond` and skips that guard.
- **Fix:** fixtures use `study_v2.CONTENT_FILENAME` and `STUDY_PREPARING`, the clear-group
  assertion checks for absence, and every message uses the real `request_id` wire key.
  The packaged response wait is now deadline-based on a reader thread rather than a
  ten-line budget — `health_check` sits behind 20+ `bootstrap_progress` events, and a
  `readline` on a pipe cannot be interrupted if the sidecar never answers.
- **Verified:** 8 passed, including both tests driving the real packaged `.exe`. Full
  suite 1770 passed, 0 failed.
- **Lesson:** a fixture that hand-rolls a filename or a status string the product parses
  is a test that silently stops testing. Reference the product's own constant
  (`CONTENT_FILENAME`, `STUDY_*`) so a rename breaks the test loudly instead of quietly
  turning it green against nothing. And a fixture that stubs the transport (`_respond`)
  cannot prove the wire protocol — only the packaged end-to-end test can, which is
  exactly why its failure was the one telling the truth.

### BUG-32 — updater would install an UNVERIFIED installer (fail-open)   ✅ FIXED (verified)
- **Area:** `electron-spike/updater.js` (`check`, `download`, `expectedInstallerSha256`).
- **Found:** 2026-08-10 release-hardening audit of shipped v2.0.0. Not user-reported.
- **Severity:** security. Shipped in 2.0.0.
- **Symptom:** none visible — the updater reported "downloaded / ready to install".
- **Root cause:** `check()` wrapped the manifest fetch in `try { … } catch (_) { expectedSha256 = null; }`.
  `download()` then passed `update.expectedSha256 || undefined` to `fetchToFile`, which
  skips verification entirely when the digest is undefined. So a missing, unreachable,
  malformed or digest-less manifest silently produced an *unverified* installer that
  `install()` would happily launch. `expectedInstallerSha256()` also accepted a top-level
  `sha256`/`installer_sha256` bound to no filename, and matched any `*-Setup.exe` entry —
  so a digest published for a *different* installer was accepted.
- **Fix:** `verifyReleaseManifest()` is now the single trust gate: manifest must parse,
  version must equal the selected release, platform `win32`, arch `x64`, and an
  `installers[]` entry whose basename exactly matches the installer being downloaded with
  a valid 64-char digest. Unbound top-level shortcuts removed. `download()` refuses to run
  without a verified digest. No "proceed anyway" path exists.
- **Verified:** `tests/test_electron_updater.py` 23 passed; lifecycle probe proved
  missing/malformed/foreign-hash manifests, checksum mismatch and cancellation each leave
  zero leftover files; the real published v2.0.0 manifest still verifies with the correct
  digest; A→B acceptance installed 2.0.1 over 2.0.0 from verified bytes.
- **Lesson:** a `catch` that assigns a *permissive* default is a fail-open. When the
  catch-all sets `null` and the consumer treats `null` as "skip the check", the error path
  is the attack path.

### BUG-31 — packaged .exe reported the wrong version after any bump   ✅ FIXED (verified)
- **Area:** `electron-spike/package-win.mjs`.
- **Found:** 2026-08-10, while verifying the installed 2.0.1 build.
- **Symptom:** installed `LecturePack.exe` reported ProductVersion **2.0.0** while
  `version.py`, `package.json`, `package-lock.json` and the `.iss` all said 2.0.1.
- **Root cause:** `appVersion`, `ProductVersion` and `FileVersion` were hardcoded string
  literals `'2.0.0'` / `'2.0.0.0'`. Correct for exactly one release; every bump afterwards
  would ship a mis-stamped executable. No check covered it, because the existing version
  test only compared *declaration* files to each other.
- **Fix:** read the version from `electron-spike/package.json`; derive the four-part
  `FileVersion`. `scripts/verify_release_versions.py` now fails closed if any literal
  `x.y.z` reappears in that script.
- **Verified:** rebuilt candidate reports ProductVersion 2.0.1; the new guard was confirmed
  to fail when the literal was deliberately reintroduced.
- **Lesson:** "all version surfaces agree" must include *generated* surfaces, not just the
  files humans edit. A build script holding a literal is a version surface.

### BUG-30 — YouTube import silently degraded: no JS runtime, no EJS   ✅ FIXED (verified)
- **Area:** `lecturepack/services/media_fetch.py`, `electron-spike/sidecar.spec`,
  `lecturepack/services/packaged_health.py`.
- **Found:** 2026-08-10 release-hardening audit. Shipped degraded in 2.0.0.
- **Symptom:** none in diagnostics — the packaged self-test reported "Bundled yt-dlp is
  available". In reality YouTube extraction returned **11 formats instead of 14**.
- **Root cause:** modern yt-dlp solves YouTube JS challenges through its EJS system, which
  needs both the `yt_dlp_ejs` package and a real JS runtime process. 2.0.0 bundled
  neither. The health check only proved `import yt_dlp` succeeded, which says nothing about
  whether YouTube works. A stale `player_client: ["android"]` override also bypassed the
  JS-challenge path entirely, and yt-dlp was never told where the bundled FFmpeg lives.
- **Fix:** bundle Deno 2.9.5 (digest-pinned, verified at build time) and yt-dlp-ejs 0.8.0
  **including its minified solver JS**, which ships as package *data* — `collect_submodules`
  alone would have produced a build that imports cleanly and still fails. Removed the
  android override, set `ffmpeg_location`, disabled remote component fetching. Health split
  into `yt_dlp` / `yt_dlp_ejs` / `js_runtime`.
- **Verified:** packaged self-test reports `yt-dlp-ejs 0.8.0` and `deno 2.9.5`; live
  release probe downloaded a real public video end-to-end.
- **Lesson:** "the import succeeded" is not "the feature works". A health check that can
  only prove a module loads will report green through a totally broken feature.

### BUG-29 — legacy Qt workflow could publish the Electron installer's filename   ✅ FIXED (verified)
- **Area:** `.github/workflows/release.yml` (now `release-runtime-repair.yml`).
- **Found:** 2026-08-10 release-hardening audit.
- **Symptom:** the published `LecturePack-<v>-Setup.exe` was ambiguous — it could be either
  the Electron desktop app or the legacy Qt PyInstaller build.
- **Root cause:** that workflow ran `app/packaging/build.py` (which invokes Inno Setup) and
  uploaded `-Setup.exe`, `-SHA256SUMS.txt` and `-release-manifest.json` — exactly the
  Electron asset names. Meanwhile **no** workflow invoked
  `scripts/build_electron_release.py`, so the canonical path was manual. A contract test
  actively *required* this wrong behaviour.
- **Fix:** renamed the workflow, dropped the three desktop assets, forced `--no-installer`,
  removed the Inno Setup step so it cannot compile an installer, added a fail-closed guard.
  Added `release-electron.yml` as the sole authoritative desktop publisher.
- **Verified:** `tests/test_release_pipeline_authority.py` 17 passed; the audited public
  v2.0.0 Setup.exe was confirmed to be the Electron product.
- **Lesson:** two producers, one filename, is a latent supply-chain bug. Also: a test can
  encode the bug — check what a contract test is actually asserting before trusting it.

### BUG-28 — Study mode tabs were flat; no shadow, no press, square corners   ✅ FIXED (verified)
- **Area:** `app/ui/index.html` (inline "Study V1: a quiet workspace" block), `app/ui/app.css`.
- **Reported by:** owner, 2026-08-10, with a screenshot ("boxed look").
- **Root cause:** two layers. Nothing in `app.css` targeted `.study-mode-tab`, so they only
  got the generic `.lp-tab` hover edge. **And** an inline `<style>` block overrode
  background/border/radius/padding with `!important`, forcing square underline tabs — so a
  first fix that only added a shadow in `app.css` appeared to do nothing.
- **Fix:** the Study-shell overrides now use the standard button language (9px radius, 2px
  border, resting hard shadow, hover lift, press). Keyed in CSS because
  `setStudyV2Mode()` rewrites `className` wholesale and would drop a class added in markup.
- **Verified:** computed resting shadow is `rgb(36,31,25) 2px 2px 0` — identical to the
  reference button; hover/active rules resolve above the generic tab rules.
- **Lesson:** when a CSS fix "doesn't apply", look for an inline `!important` block before
  re-writing the rule. And check whether JS rewrites `className`.

### BUG-26 — imported video's thumbnail never appears on the job card   🔴 OPEN (known, shipped in 0.9.0-beta.5)
- **Area:** `app/ui/app.js` (`posterSrc` / `LP.posterRetry` / `posterHtml`) ↔
  `app/desktop/assets.py` (`resolve_poster`, `make_poster_now`).
- **Reported by:** owner, 2026-07-27, twice — on import of `CL100 - Day 3` (1.4 GB, h264)
  the card shows the placeholder icon and never resolves to a real frame.
  Owner classified it as minor and chose to release with it open.
- **What is NOT the problem (measured, so don't re-debug this part):** generation WORKS.
  `poster.webp` exists on disk for every imported job, including the failing one
  (`8978e4cf…/poster.webp`, 16,524 bytes, written 19:22). ffmpeg resolves
  (`config.ffmpeg_exe` exists). So this is a DISPLAY/refresh failure, not extraction.
- **Key evidence, and why it is confusing:** the CDP monitor logged
  `lpasset://poster/8978e4cf…/poster` → **404 / ERR_FILE_NOT_FOUND at 19:22:49**, i.e.
  *after* the file already existed on disk (mtime 19:22). A 404 for a file that exists
  points at the resolver or the URL, NOT at a timing race — which is what the first two
  fix attempts assumed.
- **Two attempted fixes that did NOT resolve it** (both still in the tree, both defensible
  on their own merits, neither sufficient):
  1. `_kick_poster` generates the poster on import instead of lazily (BUG-25 era), later
     switched to `fast=True` → `_extract_poster_at_start` (frame at t=0, no seek) because
     seeking 10% into a 692 MB file took longer than the UI would wait.
  2. `POSTER_RETRIES` raised 3 → 9 (budget ~4.2s → ~30s), since the old budget expired
     before a cold extract finished.
- **Two hypotheses NOT yet separated** (the app was closed before this could be settled):
  (a) **QtWebEngine served a cached `app.js`**, so the raised retry budget was never live —
      this profile has been relaunched many times and the handoff explicitly warns that
      WebEngine caches `app.css`/`app.js` hard. Check by reading `POSTER_RETRIES` /
      `LP.posterRetry.toString()` out of the live page BEFORE concluding anything.
  (b) **`resolve_poster` 404s even when the poster exists.** Worth auditing against the
      `_claim()` guard added for BUG-25: if the scheme handler's path reaches
      `make_poster_now` while the import thread still holds the claim, it now returns
      `_read_poster(dst)`, which is `None` until the file lands — turning a "generating"
      state into a hard 404. Verify whether `resolve_poster` shares that path.
- **Next step:** confirm which file the page actually loaded (rule out the cache) with a
  hard cache-bust or a fresh profile, then trace `resolve_poster` for the existing-file 404.
  Do NOT add a third timing/retry fix before the 404-on-existing-file is explained.
- **Files:** `app/ui/app.js`, `app/desktop/assets.py`.

## FIXED THIS SESSION

### BUG-27 - Size cuts produced a packaged build that could not start at all   FIXED (verified)

**Symptom.** The beta-7 Phase 1 post-cut packaged build died before showing a window. PyInstaller's
"Unhandled exception in script" dialog, twice in sequence as each blocker was cleared:

```
ImportError: DLL load failed while importing QtWebChannel: The specified module
             could not be found.                       (app/desktop/main.py:43)
ImportError: DLL load failed while importing QtWebEngineCore: The specified module
             could not be found.                       (app/desktop/main.py:44)
```

**Root cause.** `PRUNABLE_QT_COMPONENTS` in `app/packaging/build.py` listed `Qt6Qml.dll` and
`Qt6Quick.dll` as D-01 "provably unused" cut targets. They are not unused. Their PE import
tables say so plainly: `Qt6WebChannel.dll` imports `Qt6Qml.dll`, and `Qt6WebEngineCore.dll`
imports both `Qt6Qml.dll` and `Qt6Quick.dll`. The whole UI is WebEngine, so removing them
removes the app.

The reasoning error is worth preserving. The code comment above the list *already stated* that
these two "are native link-time dependencies of Qt6WebEngineCore" - it used that fact to explain
why PyInstaller's `Analysis.excludes` could not remove them, and then pruned them post-build
anyway. Being a link-time dependency is precisely the reason a file must stay.

**Why every gate missed it.**
- Unit tests passed: `test_prune_does_not_remove_required_qt_components` compared against a
  hand-written list of "required" DLLs that never mentioned Qt6Qml/Qt6Quick.
- The packaged runtime smoke passed: it exercises ffmpeg, ffprobe, and whisper-cli, not the Qt
  import chain. A packaged app can pass its runtime smoke and still be unable to start.
- `--assert-pruned` passed: it asserts the cut targets are *absent*, which they were. That is
  the goal, not the safety property.
- CONTEXT.md D-03 predicted exactly this shape: "a missing module surfaces only in the packaged
  build on a clean machine, which is the slowest environment available to iterate in." D-03
  rejected an aggressive Qt allowlist for that reason; the six-item list inherited the same risk
  and nobody re-applied the reasoning to it.

**Fix.** Both DLLs removed from `PRUNABLE_QT_COMPONENTS` (now four targets: `translations`, `qml`,
`Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll`). Cost of correctness: 11.4 MiB against ~800 MiB
reclaimed - 1.4% of the win.

**Structural guard (the part that matters).**
`test_pruned_components_are_not_imported_by_surviving_qt_dlls` in `tests/test_package_pruning.py`
computes the **transitive closure** of Qt DLLs reachable from what `app/desktop/main.py` actually
imports, and fails if any pruned target lands inside it. It asks the binaries instead of asking a
human's list, so a future addition to the prune list cannot reintroduce this class of bug.

A flat "is it referenced anywhere" scan was tried first and was wrong: `Qt6PdfQuick.dll`
references `Qt6Pdf.dll` and five `Qt6Quick3D*.dll` reference `Qt6Quick3DRuntimeRender.dll`, yet
pruning both those targets is fine because nothing the app loads reaches the referencing DLLs.
Only reachability from the real entry points separates "genuinely unused" from "load-bearing".
Requires `LECTUREPACK_ONEDIR_FIXTURE`; skips cleanly without a real packaged tree.

**Verified.** With both DLLs restored the packaged app launches: window titled "LecturePack" at
9.43 s on a cold fresh profile, status bar reporting `whisper.cpp - CPU AVX2 - ggml-base.en.bin`
(which also confirms D-05's deduplicated single model copy resolves in the real app). 22/22
`test_package_pruning.py` pass with the closure guard active against the real tree.

**Lesson.** A size cut is not verified by proving bytes are gone. It is verified by starting the
program. Add "launch the packaged build" to any packaging change, and never accept a component
inventory that was authored rather than derived from the binaries.


### BUG-25 — two `AssetResolver` instances could tear the same poster file   ✅ FIXED (unit-verified)
- **Area:** `app/desktop/assets.py`, `app/desktop/engine_adapter.py::_kick_poster`.
- **Found:** second independent pre-release review, 2026-07-27, on the same-session change
  that added instant poster generation on import.
- **Root cause:** `_kick_poster` constructed a NEW `AssetResolver` per import and called
  `make_poster_now` on a raw thread, bypassing that class's dedup (`self._pending` +
  `self._lock`). But `main.py:100` already owns a SECOND resolver wired to `jobs_changed` →
  `prewarm_posters`. The `_pending` guard is **per-instance**, so it cannot see the other
  resolver. Both computed the same destination via the pure `poster_path()`, and all three
  write sites used a **deterministic** temp name (`dst + ".tmp"`), so two concurrent
  generators wrote the same temp file — one could truncate while the other was mid-write,
  then both `os.replace()` it. Reachable in practice: `Job.__init__` writes `manifest.json`
  synchronously, so a freshly imported job is picked up by the very next `jobs_changed` for
  ANY unrelated reason (deleting/grouping another job, pause/resume, startup reconcile) while
  the import thread is still extracting.
- **Fix:** (a) `_tmp_for(dst)` gives every write a unique temp path (pid + uuid + extension),
  so each write is private and the `os.replace` stays atomic — the loser is simply discarded;
  (b) a **module-level** `_INFLIGHT` set + lock, shared by every resolver in the process, so a
  second caller returns the on-disk poster via `_read_poster` instead of launching a second
  ffmpeg over a multi-hundred-MB video mid-processing. `make_poster_now` claims/releases in a
  `try/finally`.
- **Verified:** unit level — `_tmp_for` returns distinct paths preserving the extension;
  `_claim` is exclusive and re-claimable after `_release`; `make_poster_now` releases in a
  `finally`. Not observed live (the owner had a real 63-minute lecture processing and a
  relaunch would have destroyed that run).
- **Lesson:** a per-instance dedup guard is not a dedup guard if the class is instantiated in
  more than one place. Before trusting `self._pending`-style state, grep for every
  construction site. And any "write temp then rename" needs a UNIQUE temp name — a
  deterministic one turns two safe writers into one torn file.
- **Files:** `app/desktop/assets.py`, `app/desktop/engine_adapter.py`.

### BUG-24 — new slide GRID replayed its entrance animation on every interaction   ✅ FIXED
- **Area:** `app/ui/app.js::renderSlides` (grid branch).
- **Found:** second independent pre-release review, 2026-07-27.
- **Root cause:** grid tiles were emitted with an unconditional `class="lp-hit lp-anim-in"`,
  and `renderSlides()` rebuilds `innerHTML` wholesale on every slide click, Next/Prev, view
  toggle — and, after the same session's Keep/Reject auto-advance, on every judgement click.
  So the entire grid re-played its 140ms slide-up entrance on every single interaction. The
  pre-existing list branch never carried the class, which is why only the new grid regressed.
- **Fix:** a `_gridEntrance` flag, armed on first paint and when the user switches INTO grid
  view, consumed once per render. Tiles animate on view entry only.
- **Lesson:** an entrance class baked into markup that is re-rendered wholesale becomes a
  per-render animation, not an entrance. Entrance state belongs outside the render output.
- **Files:** `app/ui/app.js`.

### BUG-23 — live-log stream saturated the main thread; window stopped accepting clicks   ✅ FIXED
- **Area:** `app/ui/app.js` `log_line` handler / `renderPipeline`.
- **Found:** owner, while processing a real 63-minute lecture, 2026-07-27 ("it just kind of
  stuck for a while, you can't click any buttons", around 42-50%).
- **Root cause:** the log buffer was capped at 500 lines, which bounded MEMORY but not WORK:
  every `log_line` event called `renderPipeline()`, re-rendering the whole panel including all
  500 buffered lines. During transcription and slide detection the backend streams log lines
  rapidly, so the cost was one full DOM rebuild PER LINE and the UI thread starved.
- **Fix:** `schedulePipelineRender()` coalesces to one render per `requestAnimationFrame`.
  Visible output is identical (a frame is the fastest anything can be seen) while N renders per
  frame collapse to one. `pipeline_changed` still renders directly, so title/meta/stages are
  never starved if a log frame is delayed.
- **Lesson:** capping a buffer bounds memory, not render cost. If a handler fires per streamed
  item, the render must be coalesced per frame, not per item.
- **Files:** `app/ui/app.js`.

### BUG-22 — `#focus-pill` slid in off-centre; its own inline centering fought the entrance keyframe   ✅ FIXED (verified in real Qt)
- **Area:** `app/ui/app.js::setFocus`, `app/ui/app.css` `.lp-anim-in-fast` / `.lp-out`.
- **Found:** independent pre-release review, 2026-07-27. Not user-reported.
- **Root cause:** THE SAME DEFECT CLASS ALREADY FIXED FOR THE TOAST (handoff §4.7), missed on
  this element. `#focus-pill` carries an inline `transform:translateX(-50%)` for horizontal
  centering. `setFocus(true)` applied `.lp-anim-in-fast` → `animation:lpseat-sm … both`, and
  `lpseat-sm{from{transform:translateY(3px)}}` declares only a `from`. With fill-mode `both`
  the `from` **replaces** the inline centering, so the pill rendered half its own width
  off-centre and slid sideways into place. The exit had the mirror bug: `.lp-out`'s
  `lpfadeout{to{…transform:translateY(4px)}}` declares only a `to`, so its implicit `from`
  was the inline centering — the pill drifted sideways while fading out.
- **Fix:** entrance switched to `.lp-anim-fade` (opacity-only, `lpsupport`); exit given an
  id-scoped opacity-only keyframe `lpfadeout-o` via `#focus-pill.lp-out`, so every other
  `.lp-out` user keeps the shared exit.
- **Verified:** in real Qt via CDP — entrance animation is `lpsupport`, and the computed
  transform is `matrix(1,0,0,1,-94.37,0)` **identical** mid-entrance and settled, i.e.
  centering never breaks. Exit resolves to `lpfadeout-o`.
- **Lesson (a repeat, so it is now a rule):** ANY element carrying an inline `transform` is
  incompatible with a keyframe that touches `transform` and declares only one endpoint — the
  missing endpoint silently resolves to the element's cascaded transform. Before applying a
  transform animation to an element, grep its markup for an inline `transform`. Fixing one
  instance (the toast) did not fix the class; there was a second one for a whole session.
- **Files:** `app/ui/app.js`, `app/ui/app.css`.

### BUG-21 — `LP.motion.close()`'s 300ms fallback timer could hide a just-REOPENED overlay   ✅ FIXED (verified in real Qt)
- **Area:** `app/ui/app.js::LP.motion.close`.
- **Found:** independent pre-release review, 2026-07-27.
- **Root cause:** `close()` armed `setTimeout(finish, 300)` as a safety net so a modal can
  never fail to close, and never cancelled it. Its `finished` guard is a **per-invocation**
  closure flag, so it cannot see a different invocation. Reopening a persistent element
  (`#focus-pill`, `#onb-overlay`, `#whatsnew-overlay`) inside that window let the PREVIOUS
  close's timer fire and run *its* `done()` — e.g. `hidden = true` on an element the user had
  just reopened, with no user action, up to 300ms later. Worse in the interrupted case:
  removing the class mid-animation generally does not fire `animationend`, so the stale
  timeout was the only thing that ever resolved it.
- **Fix:** keep the timer id and `clearTimeout` in `finish()`, plus a supersede check — a
  reopen removes the close class, so `!el.classList.contains(cls)` means "superseded", and
  `finish()` returns without calling `done()`.
- **Verified:** in real Qt — closed then reopened focus mode within 50ms, waited 500ms
  (outliving the 300ms timer): `#focus-pill.hidden === false`, focus state still `true`.
- **Lesson:** a "can never fail" fallback timer is itself state. If the element it acts on can
  be re-shown before it fires, it needs both a cancel and a still-relevant check; a
  per-invocation guard flag provably cannot catch a stale sibling invocation.
- **Files:** `app/ui/app.js`.

### BUG-20 — reduced-motion gap: the ACTIVE nav icon still jumped scale on hover   ✅ FIXED (verified in real Qt)
- **Area:** `app/ui/app.css` `@media (prefers-reduced-motion: reduce)`.
- **Found:** independent pre-release review, 2026-07-27.
- **Root cause:** the new nav-icon rules cover four states, but the reduce block neutralised
  only the `:not(.active)` pair. `.lp-nav.active:hover svg{transform:scale(1.22)}` was
  unneutralised, so the icon of the screen you are currently on still jumped 1.14 → 1.22 on
  hover under `prefers-reduced-motion: reduce` (instantly, since the transition was zeroed —
  but a visible jump nonetheless).
- **Fix:** pin `.lp-nav.active:hover svg` to the resting `scale(1.14)` under reduce, rather
  than `transform:none` — the active item must keep its resting emphasis, because that is
  STATE, not motion. Also closed a pre-existing sibling gap the same review flagged:
  `.lp-hit:hover`'s 1px lift had no reduce override (only `:active` did).
- **Verified:** via CDP `Emulation.setEmulatedMedia` — `matchMedia(...).matches === true`, and
  the active icon measures `scale(1.14)` both at rest and hovered.
- **Lesson:** when a rule set covers N states, the reduce block must cover N, not the obvious
  subset. `:not(.active)` selectors are the easy half to remember and the active/current
  variant is the easy half to forget.
- **Files:** `app/ui/app.css`.

### BUG-19 — `ReferenceError: reflectEngine is not defined` on every `settings_changed`   ✅ FIXED (verified in real Qt WebEngine; uncommitted, `feat/cuda-engine`)
- **Area:** `app/ui/app.js` — `wire()` / `wireBridge()` scope boundary.
- **Found:** 2026-07-26, as a side effect of Qt CDP verification during the UI/motion pass —
  **not** the bug that pass was looking for. Confirmed present in `HEAD`, so it predates
  that work. Flagged in `docs/HANDOFF-2026-07-26-2330-UIUX.md` §7 as a one-line note;
  investigated properly 2026-07-27 and turned out to be larger than the note implied.
- **Root cause:** `app/ui/app.js` is a single top-level IIFE containing two **sibling**
  functions — `wire()` (line 2109) and `wireBridge()` (line 2607); neither is nested in the
  other. `reflectEngine` and `reflectBackend` are function declarations **local to `wire()`**
  (2131, 2166), but the `settings_changed` handler is registered **inside `wireBridge()`**.
  `wire()` is not on that handler's scope chain, so the name was genuinely unbound →
  `ReferenceError`. Not a typo and not a missing guard — a scope error.
- **Wider than first reported (three things the handoff note missed):**
  1. **`reflectBackend` was broken identically**, but masked by
     `typeof reflectBackend === 'function'` — a guard that is *always false* here, so it
     silently no-op'd instead of throwing. Two sites: the `groq_status` handler (2851) and
     `settings_changed`. Net effect: the transcription-backend segmented control never
     reflected state pushed from Python; only a manual click updated it.
  2. **The throw killed the rest of the handler.** `bridge.js` `fire()` catches per-listener,
     so *other* listeners survived — but every statement after the throw point was dead on
     each full settings push: `transcription_backend`, `ollama_model` name/select,
     `actual_backend` → `#status-right`, `export_dir`, `update_status`.
  3. **It fired on every emit, not intermittently.** `app/desktop/engine_adapter.py`
     `_settings_payload()` always includes `"engine"` (defaults to `"auto"`, always truthy).
     Partial payloads with no `engine` key were the only ones surviving intact.
- **Fix:** exposed both `wire()`-local helpers on the pre-existing `LP` namespace as
  `LP.ui` — one new line at `app.js:2174`, immediately after `reflectBackend`'s closing brace
  — and routed all three `wireBridge()` call sites (2851, 2963, 2964) through `LP.ui` with an
  `&& LP.ui` guard. Ordering is safe: `boot()` calls `wire()` before `wireBridge()`, both long
  before any bridge signal arrives. The two in-scope callers inside `wire()` (2146, 2177) were
  left resolving lexically and untouched.
- **Expected behaviour change — NOT a regression.** Statements after the old throw point now
  execute. **Corrected scope after runtime measurement** — the first pass over-claimed "five
  dead statements". Checking `engine_adapter._settings_payload()` (line 972) against runtime
  behaviour, the full payload contains only `version, model_path, endpoint, engine,
  ollama_model, transcription_backend, export_dir`. So:
  - **Genuinely restored:** `transcription_backend` (the `#tbk-seg` segmented control) and
    `export_dir`. Plus `ollama_model` *when non-empty* — it defaults to `""`, which the
    `if (s.ollama_model)` guard skips, so on a fresh config it still writes nothing.
  - **Never actually blocked:** `actual_backend` (`#status-right`) and `update_status`. These
    are **not in the full payload at all**; they arrive on *partial* payloads (lines 1530,
    2861) which carry no `engine` key and therefore never hit the throw. Confirmed at runtime:
    after blanking them and firing a real full `settings_changed`, they correctly stayed
    blank while `export_dir` and the backend selector repainted.
- **Runtime verification (2026-07-27), real Qt WebEngine, not a browser stand-in:**
  `QtWebEngine/6.11.1 Chrome/140.0.0.0`, disposable `LECTUREPACK_DATA_DIR`, driven over CDP
  with a **stdlib-only raw-websocket client** (`websockets`/`websocket-client` are still not
  installed in the venv and `pip install` is off-limits).
  - Gated on `typeof LP.ui.reflectEngine === 'function'` before measuring, to prove the fixed
    `app.js` was actually loaded and not served from QtWebEngine's aggressive cache.
  - Blanked `#export-dir` etc. to `@@BLANKED@@` and scrambled the selector backgrounds to
    magenta, then fired a **real** `settings_changed` by clicking `#compute-cuda` (its own
    listener → `set_setting` → Python full payload). `export_dir` repopulated to the real
    path and both the compute and backend selectors repainted — if the `ReferenceError` still
    fired, they would have stayed blank/magenta.
  - **6 real round-trips: zero exceptions, zero console errors.** This result is meaningful
    because a **control test** first injected a deliberate uncaught error and a
    `console.error` and confirmed the CDP listener caught both — an unvalidated "0 errors"
    would have been unfalsifiable (an early attempt did report "0 events", which turned out
    to be an attach-before-`boot()` artifact, not a clean run).
  - **Counter-test:** bare `reflectEngine('cpu')` from an outer closure *still* throws
    `ReferenceError` — proving the `LP.ui` indirection is what fixed it, and independently
    re-confirming the scope diagnosis at runtime rather than only by reading.
  - Real data dir `C:\Users\marsh\LecturePackData` `LastWriteTime` byte-identical before and
    after (`2026-07-25T02:32:31.0839078-04:00`); all writes landed in the disposable dir.
- **Known follow-on, deliberately not fixed here:** `COMPUTE_IDS` is `{cpu, cuda, vulkan}`
  but the persisted engine default is `"auto"`. Now that `reflectEngine('auto')` actually
  runs, it matches no key and clears the highlight on all three compute buttons — Settings
  shows *no* engine selected on a fresh config instead of throwing. A design decision
  (should `auto` highlight something?), tracked by a `TODO` at the call site and deferred to
  its own PR rather than folded into a scope fix.
- **Lesson:** a `typeof x === 'function'` guard around a same-file helper **hides a scope bug
  as dead code**. `reflectEngine` threw loudly and got noticed; `reflectBackend` had the
  identical defect, was guarded, and sat silently broken for far longer. When one symbol in a
  block turns out to be cross-scope, audit **every** symbol that block references for
  reachability — and treat such a guard as a smell, not as safety.
- **Files:** `app/ui/app.js`.
- **Refs:** `docs/HANDOFF-2026-07-26-2330-UIUX.md` §7, §8 item 3.

### BUG-11 - Tray notifications and taskbar progress silently dead   FIXED (verified)
- **Area:** desktop shell (`app/desktop/main.py::MainWindow.__init__`)
- **Found:** beta.4 pre-release review (independent agent), 2026-07-25. Not user-reported
  - the features simply never fired, with no error.
- **Root cause:** the poster-prewarm commit inserted `_prewarm_posters` and `_ffmpeg_exe`
  **into the middle of `__init__`**. Everything below the insertion - tray-icon creation
  and `attach_window(self, self.tray)` - ended up **after `return ""` inside
  `_ffmpeg_exe`**, i.e. unreachable. `self.tray` was never assigned and `attach_window`
  never ran, so `notifier._tray` and `taskbar._hwnd` stayed `None`.
- **Impact:** a straight regression from beta.3, which shipped both as headline features.
  `_on_notification_clicked` was also unreachable.
- **Fix:** moved the block back inside `__init__` (after `setCentralWidget`, where
  `icon_path` is in scope), with a comment saying why it must stay there.
- **Lesson:** inserting a method mid-`__init__` orphans every statement after it. Python
  gives no warning - the code reads fine and the class still constructs.
- **Files:** `app/desktop/main.py`.

### BUG-12 - `storage_changed` never reached the UI (feature dead on arrival)   FIXED (verified)
- **Area:** `app/ui/bridge.js` SIGNALS list
- **Found:** beta.4 pre-release review, hours after BUG-04's fix was written.
- **Root cause:** `bridge.js` only connects Qt signals named in a hardcoded array.
  `storage_changed` was declared in `bridge.py`, emitted by the adapter and handled in
  `app.js` - but never listed, so it was never connected. Silent: no console error.
- **Fix:** added it, and **rewrote the guard test to derive the expected list from
  `bridge.py`** instead of checking four hardcoded `media_*` names. Mutation-checked:
  removing the entry now fails the test.
- **Verified live:** the sidebar reads `STORAGE 686 B - 227.5 GB free` on a real launch.
- **Files:** `app/ui/bridge.js`, `tests/test_media_link_adapter.py`.

### BUG-13 - Full `os.walk` of the data dir on every `jobs_changed`   FIXED (verified)
- **Area:** `app/desktop/engine_adapter.py::push_storage`
- **Found:** beta.4 pre-release review (self-suspected while writing BUG-04's fix).
- **Root cause:** `_push_jobs()` called `push_storage()` unconditionally, spawning a
  fresh daemon thread that walked the whole data root. There are 10 `_push_jobs()` call
  sites, and bursty flows (bulk delete, queue promotion, startup reconciliation) fire
  several in a row - N overlapping unbounded walks over tens of thousands of files,
  concurrent with the pipeline's own heavy I/O.
- **Fix:** 1.5s debounce (a burst collapses to one walk) + an in-flight guard + a dirty
  flag so a change arriving mid-walk re-measures once afterwards. The re-arm is a flag,
  NOT a recursive `push_storage()` call - a test proved that recurses to stack
  exhaustion when the timer fires synchronously.
- **Files:** `app/desktop/engine_adapter.py`, `tests/test_storage_signal.py`.

### BUG-14 - Recycle-bin delete silently escalated to permanent delete   FIXED (verified)
- **Area:** `app/desktop/engine_adapter.py` delete path - **data loss**
- **Found:** beta.4 pre-release review.
- **Root cause:** `except Exception: shutil.rmtree(...)` wrapped `send2trash`. ANY
  runtime failure - a file locked by an antivirus scan, a `MAX_PATH` overrun, a data dir
  on a network or removable volume - turned a delete the user confirmed as "move to
  Recycle Bin" into an unrecoverable one. Bulk delete multiplied it across a whole
  selection in one click.
- **Fix:** only `ImportError` (send2trash genuinely absent) justifies a hard delete. A
  runtime failure now **fails the operation** and leaves the lecture on disk - failing is
  recoverable, escalating is not.
- **Tests:** the existing test asserted the UNSAFE behaviour and was rewritten; added
  `test_runtime_send2trash_failure_preserves_the_lecture`.
- **Files:** `app/desktop/engine_adapter.py`, `tests/test_webview_jobs.py`.

### BUG-15 - Fresh install showed a fake lecture on Review/Transcript/Study   FIXED (verified)
- **Area:** `app/ui/app.js` demo data - **the worst user-facing find of the review**
- **Found:** beta.4 pre-release review; **reproduced in the real app** before fixing.
- **Symptom:** on a brand-new empty profile, Home correctly showed "No lecture loaded"
  and `RECENT JOBS 0`, but pressing **3 (Review)** showed a complete fabricated lecture:
  a "14 slides - 06:12" timeline, a slide list with accepted/rejected states, and a
  Great Pyramid of Giza transcript.
- **Root cause:** BUG-07 gated only `LP.data.jobs` behind `?preview=1`. The
  `pipeline`/`slides`/`reviewSegments`/`transcript`/`study` literals are also design-time
  demo content and stayed live. `active_job` cannot clear them, because
  `_load_latest_completed_job()` returns early **without emitting** when there is nothing
  to load. Timeline axis labels (`00:00/03:06/06:12`) were hardcoded in `index.html` too.
- **Fix:** one `PREVIEW` flag; `boot()` blanks the whole workspace via the existing
  `emptyWorkspace()` unless previewing; `resetJobChrome()` clears the axis labels and
  `renderSlides()` restores the origin once a lecture exists.
- **Verified:** real app, empty profile - Review now reads "No slides yet", 0 slides,
  empty transcript.
- **Files:** `app/ui/app.js`, `app/ui/index.html`.

### BUG-16 - Process "Source" card had no writer   FIXED (verified)
- **Area:** `app/ui/app.js` - same class as BUG-04
- **Found:** while fixing BUG-15 (grepped for other writer-less elements).
- **Root cause:** `proc-source-name` / `proc-source-meta` were written **only** by
  `resetJobChrome()`. BUG-04 spotted the missing writer and gave them honest idle values
  but never wired a real one - so the Source card read "No lecture loaded" plus a
  hardcoded `1920x1080 - 06:12 - H.264` *even while a lecture was processing*.
- **Fix:** `renderPipeline()` now writes both from the `pipeline_changed` payload.
- **Files:** `app/ui/app.js`, `tests/test_webview_ui_fixes.py`.

### BUG-17 - A failed download could import a PREVIOUS one and report success   FIXED
- **Area:** `lecturepack/services/media_fetch.py::_newest_media`
- **Found:** beta.4 pre-release review.
- **Root cause:** the fallback scans the **shared** `<data_dir>/downloads`, not a
  per-download dir. If yt-dlp did not report a filename, it returned the newest file
  present - the user's previous import - and the caller emitted `ok: True` and imported
  it. A destructive flow reporting success: a new job containing yesterday's lecture,
  with no error shown anywhere.
- **Fix:** a `not_before` timestamp floor, so only files written by this download qualify.
- **Files:** `lecturepack/services/media_fetch.py`, `tests/test_media_link_adapter.py`.

### BUG-18 - A cancelled link download still became a job   FIXED
- **Area:** `app/desktop/engine_adapter.py::import_media_url`
- **Found:** beta.4 pre-release review - which described it as a permanent wedge of
  `_media_busy`. **That part was wrong**: `_media_busy` is cleared in a `finally`. The
  real defect is below, found by re-verifying the claim instead of trusting it.
- **Root cause:** cancel is only observed from yt-dlp's progress hook. Arriving while no
  hook is firing (extractor resolution, a stalled socket, the final merge), the transfer
  ran to completion and reported `ok: True`, so the import proceeded behind the user.
- **Fix:** re-check `cancel.is_set()` after `download()` returns.
- **Files:** `app/desktop/engine_adapter.py`, `tests/test_media_link_adapter.py`.

### BUG-07 — Preview-mode demo job seed appears when no bridge is attached   ✅ FIXED (verified)
- **Area:** UI / preview mode (`app/ui/app.js` `LP.data.jobs` seed)
- **Reported / found:** 2026-07-25, while fixing BUG-04 (a DOM scan still matched
  `egypt_excerpt` after the markup was cleaned).
- **Symptom:** With no QWebChannel backend (static server / screenshot pipeline), three
  demo jobs render — `egypt_excerpt`, `m2-res_1080p`, `synthetic_lecture`.
- **Root cause:** intentional. `app.js:59-63` seeds `LP.data.jobs` so the UI is
  presentable without a backend; a live bridge overwrites it via `_list_jobs`
  (confirmed live: a real launch on an empty profile showed `RECENT JOBS 0`).
- **Attempts:** considered emptying the seed → **rejected**: it is what makes the README
  screenshot pipeline work, and it is unreachable in the packaged app once the bridge
  connects.
- **Current fix (2026-07-25, un-deferred before the beta.4 release):** the seed is now
  **opt-in** — it only populates when the URL carries `?preview=1`, exactly the escape
  hatch this entry predicted. Shipping fake job data that is one bridge-failure away from
  being user-visible is a foot-gun, and it had already cost one false positive (the DOM
  scan above). The screenshot pipeline keeps working by adding the flag; the packaged app
  can never produce it.
- **Verification:** live app on a throwaway profile showed 0 jobs (seed not user-visible)
  both before and after; the content-hygiene guard asserting `egypt_excerpt` is absent
  from the markup still passes; 684 tests pass.
- **Files:** `app/ui/app.js`.

### BUG-10 — Test suite opened real Qt windows that flashed on screen   ✅ FIXED (verified)
- **Area:** test infrastructure (`tests/conftest.py`, previously absent)
- **Reported / found:** 2026-07-25 **by the user**, who noticed "the LecturePack app
  opens for a bit and flashes away" during test runs and suspected it was running old UI.
- **Symptom:** native windows appeared and vanished during `pytest`, stealing focus.
- **Root cause:** there was **no `conftest.py` at all** and `pytest.ini` never set
  `QT_QPA_PLATFORM`. `pytest-qt`'s `qapp` fixture therefore built a real `QApplication`
  on the native Windows platform plugin, and three test modules call `.show()` on real
  widgets (`test_ui_v11.py`, `test_ui_phase2.py`, `test_stability_phase.py`).
  `test_adapter_startup.py`'s docstring *claimed* "an offscreen Qt app" — that claim was
  simply untrue, nothing enforced it.
- **The user's suspicion was correct.** The flashing window is the **old
  `lecturepack/ui/` PySide UI**, not the shipped WebEngine UI — `test_ui_v11.py` and
  `test_ui_phase2.py` import `lecturepack.ui.main_window.MainWindow`. Confirmed that this
  package is dead in production: **0 `lecturepack.ui` modules are frozen into the shipped
  exe** (inspected the PYZ), yet ~109 tests still reference it.
- **Current fix:** added `tests/conftest.py` setting `QT_QPA_PLATFORM=offscreen` at import
  time (before Qt loads), via `setdefault` so an explicit override still wins.
- **Verification:** the three window-showing modules + the two `qapp` modules pass
  offscreen (88 passed); full suite **677 passed**; and a continuous ~135s window poll
  spanning an entire run saw **zero** Qt/python windows (previously they appeared).
- **Dead-UI test cleanup — ATTEMPTED 2026-07-25, then DEFERRED on purpose.** Deleting
  `test_ui_v11.py` + `test_ui_phase2.py` (52 purely dead-UI tests) broke collection: they
  are load-bearing for live tests. `test_study_workspace_v12.py` and
  `tests/generate_study_evidence.py` import `_make_job` from `test_ui_v11`, and
  `test_stability_phase.py` loads `test_ui_v11.py` **by file path** via `importlib` to
  reuse that fixture — and itself builds a `MainWindow`. Doing this properly means
  extracting a shared fixture module and rewiring four files, and logically expands to
  deleting more window tests. That is entangled churn with zero user-visible benefit, so
  it was reverted rather than rushed immediately before cutting a release. Only ~52 of
  the ~109 referencing tests are purely dead-UI; the rest test live logic and merely
  import `lecturepack.ui` incidentally. **Do this as its own change, starting by moving
  `_make_job` into `tests/_ui_fixtures.py`.**
- **Files:** `tests/conftest.py`.

### BUG-09 — Link import hung forever: worker-thread signals never delivered   ✅ FIXED (verified)
- **Area:** desktop shell / thread marshalling (`app/desktop/engine_adapter.py::_emit_soon`)
- **Reported / found:** 2026-07-25, while doing the handoff TODO "drive the link-import
  flow once in the real app, end to end". Found on the **packaged beta.3 build**, then
  reproduced from source — it was never build-specific.
- **Symptom:** paste a URL → "Check link" → the modal sits on **"Looking it up…" forever**.
  No error, no timeout, **empty stderr**, no crash. Cancel still worked.
- **Why it survived this long:** the previous session verified the service
  (`MediaFetcher.probe`/`download`) directly, and verified the three modals in a browser
  with **no backend attached**. Both halves passed. The *only* thing never exercised was
  the seam between them — which is exactly where the bug was. The handoff honestly listed
  this flow under "NOT verified".
- **Root cause:** `_emit_soon` did `QTimer.singleShot(0, lambda: signal.emit(data))`.
  That overload starts the timer **in the calling thread**. Every caller is a plain
  `threading.Thread` worker with no Qt event loop, so the timer never fired, the functor
  never ran, and the signal was never emitted. The worker's own `try/except` had already
  completed successfully, so there was nothing to log — hence the silent hang.
- **Blast radius:** all three link-import signals — `media_probe`, `media_progress`,
  `media_done` — plus the post-download handoff at the `import_video` call site, which had
  the identical bare-`singleShot` shape. So even a successful download would never have
  become a job. **Link import could never have worked in any build.**
- **Not affected:** `_promote_next`'s bare `singleShot(0, _go)` is fine — it is reached
  from `_on_pipeline_completed`/`_on_pipeline_failed`, which are Qt slots connected to
  controller signals and therefore already run on the main thread. Checked before changing.
- **Current fix:** pass a main-thread QObject as the context argument —
  `QTimer.singleShot(0, self.backend, lambda: ...)`. Qt then runs the functor in that
  object's thread. Applied at both sites.
- **Verification:** proved the mechanism in isolation first (bare overload from a worker
  thread delivers **nothing**; context overload delivers) rather than assuming. Then drove
  the real app end to end against a throwaway `LECTUREPACK_DATA_DIR`: paste → **confirm
  card appeared** ("acceptance_clip · unknown length · Generic") → Download → file landed
  in `downloads/` at **168,518 bytes, byte-for-byte the source size** → job auto-created
  with `manifest.json` + a generated `poster.webp` → "New job" modal showed
  `640×360 · 00:12 · h264` matching the clip. Self-generated clip over local HTTP; no
  third-party content downloaded.
- **Tests:** `tests/test_emit_soon_threading.py` — a functional test that calls the real
  `_emit_soon` from a real worker thread, plus a static guard against the bare shape.
  **Mutation-checked:** reverting the fix fails both.
- **Files:** `app/desktop/engine_adapter.py`.

## DEFERRED (known, accepted for now)

*None — BUG-07 was un-deferred and fixed on 2026-07-25.*

### DEF-001 … DEF-014 — v2.0.2 polish audit sweep   ✅ FIXED (suite green, NOT hand-verified in the packaged app)
- **Area:** Study scope, Export, drag-and-drop, Subjects, Process, sidebar.
- **Reported / found:** 2026-08-15, master defect report against v2.0.2 (`4a0cca6`),
  produced by live CDP automation + source analysis. 0 critical, 5 high, 6 medium, 3 low.
- **Root causes — the recurring shape.** Three distinct patterns, worth remembering:
  1. **Scope-blind dispatch.** Every per-concept Study action hardcoded
     `job_id: LP.state.jobId`. In Subject scope the rendered concept is a *synthesized
     cross-lecture merge* whose id exists in no single lecture's store, so the backend
     answered `concept not found` (DEF-001). Fixed by stamping `origin_job_id` /
     `origin_concept_id` in `buildGroupStudyContent`, rendering them onto the card, and
     resolving through a new `studyItemOwner()` helper. **Passing only the owning job id
     would NOT have been enough — the merged concept id is also wrong.**
  2. **UI-state-only handlers.** `btn-export-again` flipped `LP.state.exportPhase` and
     never re-exported (DEF-002); the Process "Output mode" cards carried `.lp-hit`
     / `.lp-press-sm` and animated on click while being wired to nothing, *and* were
     hardcoded to "Study Pack" regardless of the job's real `product_mode` (DEF-011).
  3. **Parameters dropped at a boundary.** `electron-bridge.js` mapped both `export_all`
     and `export_one` to `{command:'export', payload:{}}`, so the requested format never
     left the renderer (DEF-003). A test *asserted* the empty payload, i.e. the defect was
     pinned by its own regression test — updated in `tests/test_renderer_spike.py`.
- **DEF-005 DID NOT REPRODUCE — do not "re-fix" it.** The report blamed `_jobIsReady`
  matching only `status === 'queued'` while unstarted lectures are `'ready'`/`'unstarted'`.
  Live A/B on the real profile (2026-08-15): the backend emits **`status: 'queued'`** for an
  unstarted lecture — the card's *badge* reads "Ready to process", which is a label, not the
  status. The OLD predicate already returned `true` and the card was already draggable.
  `_jobIsReady` was still widened to accept the other spellings defensively, but it fixed
  nothing observable. **A badge string is not a status value.**
- **Also fixed:** scope-switch to a single lecture cleared Study content without reloading it
  (DEF-004);
  `studyV2.scope.groupName` was not updated on subject rename, leaving a stale Overview
  headline (DEF-010); a hardcoded `+ '.500'` produced `00:01:12.000.500` (DEF-006); raw
  float seconds rendered in Subject cards (DEF-008); invalid link import gave no visible
  feedback (DEF-009 — added `.lp-input-invalid` + `.lp-shake`, reduced-motion-neutralized);
  `"1 lectures updated"` (DEF-012); citation pills and Study Stats clipped at the scroll
  boundary (DEF-007); sidebar storage text wrapped `free` onto its own line (DEF-014);
  README gained an authoritative export inventory (DEF-013).
- **TWO OF MY OWN FIXES WERE WRONG, AND ONLY THE LIVE RUN CAUGHT THEM.** Both passed the
  test suite and `node --check`:
  1. **`source_concept_ids` cannot be trusted for identity.** My first DEF-001 fix resolved a
     group concept's origin via `source_concept_ids` OR a title match. On real data the model
     is unreliable. Four cached group analyses of the SAME lecture on disk
     (`<data>/groups/*/group-analysis-v1.json`) returned the field three different ways —
     empty `[]`, correct, and **sibling ids** — while the concept TITLES were identical in
     all four. That is why identity keys on the title. In the broken run the model
     returns the sibling concept ids (group `concept_2` "Homeric Troy" listed
     `[concept_1, concept_3]`), so every concept resolved to `concept_1` — mastery would have
     been written to the WRONG concept, worse than the `concept not found` it replaced.
     Identity is now resolved by **title match only**; no match means no origin, and the call
     fails loudly instead of corrupting a row. The looser match is still allowed for
     *citations*, where a wrong pill is cosmetic. The gateway prompt asks for the merged-from
     ids (`ai-gateway/src/tasks.js:173`) but the model does not reliably comply.
  2. **An inline style silently killed a CSS rule.** `.study-concept{padding-bottom:16px}` in
     `app.css` never applied, because the card is built with an inline `padding:14px 16px`,
     which wins. The citation pills stayed flush on the border. Bottom padding is now set in
     the inline style where the card is generated. **Check for an inline `style=` before
     adding a rule for anything `app.js` builds as a string.**
- **Verification — driven live in the real app (2026-08-15).** Packaged shell from
  `electron-spike/dist/LecturePack-win32-x64`, copied to a scratch dir with `app/ui/*`
  swapped in and `electron-bridge.js` repacked into `app.asar`; `production-main.js` patched
  behind `LP_VERIFY_*` env vars to spawn the **source** sidecar so both halves were the
  changed code. Real profile `C:\Users\marsh\LecturePackData`. Driven over CDP
  (`--remote-debugging-port=9333`) with playwright.
  - **The runtime gate is NOT a blocker** — correcting an earlier note. `--resources-root`
    must point at **`C:\Users\marsh\Documents\LecturePack`**, which has `bin/ffmpeg.exe`,
    `bin/ffprobe.exe`, `bin/Release/whisper-cli.exe` and `models/ggml-base.en.bin`. Point it
    at the worktree and the sidecar reports `Missing packaged runtime` and returns **zero
    jobs** with every command answering `FEATURE_UNAVAILABLE` — which looks exactly like an
    empty profile. Check `engine_loaded` in the `ready` event before believing "no jobs".
  - **Confirmed live:** DEF-001 (3 concepts → 3 distinct origins; setting "Homeric Troy" to
    MASTERED persisted to `concept_2`; zero console errors), DEF-002 (real click rewrote
    **12 export files** on disk), DEF-003 (sidecar echoed `kind:"pdf"` then `kind:"html"`,
    `kind:""` for `export_all` — before the fix both were `""`), DEF-004 (scoping to the
    lecture that has content renders all 3 concepts, no empty-state error), DEF-006
    (`cur.time` really is `00:00:13.500`, so the old code rendered `00:00:13.500.500`),
    DEF-007 (~20px clearance at full scroll at 1500×950, 1280×800, 1180×720, 1024×660,
    including sizes where both columns genuinely overflow), DEF-008 (`Ready · 2:48` /
    `Ready · 5:10`, previously `168.321451` / `310`), DEF-009 (red border, red background,
    `aria-invalid="true"`), DEF-010 (after rename no visible node holds the old name),
    DEF-011 (three `DIV`s, no `lp-hit`/`lp-press-sm`, `cursor:auto`, highlight follows the
    job's real `product_mode`), DEF-012 (**"1 lecture updated"** and **"2 lectures updated"**
    from real renames — subject names restored afterwards), DEF-013 (a full export wrote
    exactly the 13 files now listed in README), DEF-014 (one line, 11px row).
  - **Not verified:** a per-format export that writes ONLY the requested file — no such path
    exists; `export_now()` always rebuilds the whole pack.
  - Full suite after the corrections: `1757 passed, 23 skipped`.
- **Files:** `app/ui/app.js`, `app/ui/app.css`, `app/ui/index.html`,
  `electron-spike/electron-bridge.js`, `electron-spike/python-sidecar.py`,
  `tests/test_renderer_spike.py`, `README.md`.

## FIXED

### BUG-05 — White text on saturated fills failed WCAG AA (systemic)   ✅ FIXED (verified)
- **Area:** UI / accessibility, design tokens (`app/ui/app.css`)
- **Reported / found:** 2026-07-25, UI/UX audit agent reported the orange CTA at 2.82:1.
  Build: source at `b288418` (same tokens as shipped 0.9.0-beta.3).
- **Symptom:** white text on the orange fill measured 2.82:1 — below the 4.5:1 AA floor and
  below 3:1 even as large text.
- **Wider than reported.** Computing every signal fill showed the audit found one instance
  of a systemic fault. White text failed on **five** fills, not one:
  orange 3.41 light / **2.82 dark**, red 4.67 / **2.75**, green 4.39 / **2.06**,
  blue **2.45** / 1.31, yellow **2.57** / 1.67. The 2.82 figure was the DARK theme.
- **Root cause:** `#fff` was the default foreground for every filled control, chosen for
  brand presence rather than contrast. It reached the DOM three different ways — inline
  styles, two CSS classes (`.lp-tab.active`, `.lp-bubble-user`), and ternaries in `app.js`
  that emit `'#fff'` only in the selected state. A single-pattern sweep missed the last two.
- **Attempts:** 1) darken `--orange` and keep white text → **rejected**: dilutes the brand
  colour and needs a different darkening per fill. 2) Retune `--green`/`--red` → **rejected
  after checking usage**: both are also TEXT colours on soft backgrounds (badges), so
  retuning them would have broken the badges. 3) Near-black ink on the fills plus separate
  `*-fill` tokens only where a fill carries text → **worked**, changes no existing value,
  and is truer to the refined-neobrutalist voice than white-on-colour.
- **Current fix:** `--on-signal` (`#1C1A16` light / `#131519` dark) is the foreground for
  every text-bearing fill; `--green-fill` / `--red-fill` exist so the shared `--green` /
  `--red` text tokens stay untouched. 24 call sites recoloured across `index.html`,
  `app.js` and `app.css`. Computed ratios: orange 5.09/6.48, red 4.96/6.65,
  green 5.91/8.87, blue 7.09/14.00, yellow 6.77/10.96 — all AA-normal in both themes.
- **Verification:** a browser sweep of EVERY element with text on an opaque background,
  weight/size-aware (AA-large only where genuinely large), in both themes:
  **dark theme 0 failures** (was 2.82 worst-case). Tests recompute the ratios from the
  shipped token values, so a future palette tweak that breaks AA fails the suite.
- **Second pass, 2026-07-25 (owner approved "fix them properly") — light theme now 0 too.**
  The three "remaining near-misses" were again **an under-count of a systemic fault**: a
  weight/size-aware sweep of the whole light palette found **11** failing pairs, not 3.
  `--muted` failed on *all four* surfaces it is used on (panel 3.84, panel2 3.50, bg 3.37,
  sunk 3.26 — the reported 4.35 was not even the worst case), and the `Done` 3.62,
  `Failed` 3.57, `Running`/`Interrupted` 4.02 and `Queued`/`Scheduled` 3.26 badges all
  failed as TEXT on their soft backgrounds, plus `--green` on `--panel` at 4.39.
  **Fix:** darkened four light-theme text tokens by the smallest hue- and
  saturation-preserving step (HLS lightness ×0.825–0.930) that clears 4.5:1 against every
  surface each is used on — `--muted` `#8A8173`→`#726A5F`, `--green` `#128A52`→`#107847`,
  `--red` `#D63A2C`→`#BA3024`, `--orange-ink` `#C6430E`→`#B83E0D`. Dark theme was already
  at 0 and is **untouched**. Checked the reverse direction too: `--green` and `--muted` are
  also used as *backgrounds* (white-tick circles, status dots, scrollbar thumb) — darkening
  only *increases* contrast there, so no usage regressed.
  **Note the earlier "no pre-existing value is changed" claim in `app.css` is now stale and
  was rewritten in place** — do not re-apply it.
- **Files:** `app/ui/app.css`, `app/ui/index.html`, `app/ui/app.js`.
- **Refs:** `docs/UI_UX_AUDIT_BETA3.md` defect 4.

### BUG-03 — Review screen's 3-column layout unreachable below ~1220px   ✅ FIXED (verified)
- **Area:** UI / responsive layout (`app/ui/app.css`, review screen)
- **Reported / found:** 2026-07-25, UI/UX audit agent. Build: source at `b288418`.
- **Symptom:** the review row is `250px` + `min-width:320px` + `360px` + 28px of gaps
  = ~958px, inside `.lp-main` (`overflow-x:hidden`) beside a 224px sidebar — so below
  ~1220px the "Transcript for selection" panel was clipped with **no way to scroll to
  it**. Unreachable content, not merely cramped.
- **Root cause:** `app.css` had **zero** `@media` breakpoints, so fixed track widths never
  reflowed, and `overflow-x:hidden` on the parent swallowed the overflow instead of
  producing a scrollbar.
- **Attempts:** 1) switch the parent to `overflow-x:auto` → **rejected**: a horizontal
  scrollbar in a workspace pane is worse than a reflow. 2) Stack into one scrollable
  column at a breakpoint → **worked**. 3) First attempt used plain class rules and had
  **no effect** — the three panels carry their widths as INLINE styles, which outrank class
  rules; `!important` is required here and is commented as such.
- **Current fix:** `@media (max-width:1220px)` turns `.lp-review-row` into a scrollable
  column and releases the inline widths; each stacked panel gets a workable min/max
  height. A second breakpoint at 820px trims screen padding.
- **Verification:** measured in a browser at three widths. **1024×768:** direction column,
  no horizontal overflow on the row OR the page, all three panels 749px wide, transcript
  within `.lp-main` and non-zero area, row scrollable. **768×900:** same, transcript 509px,
  padding 12px. **1440×900:** desktop layout intact — direction row, slides 250px,
  transcript 360px, no overflow (confirms the normal case did not regress).
- **Files:** `app/ui/app.css`, `app/ui/index.html` (review columns tagged).
- **Refs:** `docs/UI_UX_AUDIT_BETA3.md` defect 3.

### BUG-08 — Workspace screens showed other lectures' data (no owner)   ✅ FIXED (verified)
- **Area:** UI / state ownership (`app/ui/app.js`, `app/desktop/engine_adapter.py`)
- **Reported / found:** 2026-07-25, user observation while clicking through tabs with no
  lecture loaded. Build: source at `df1369c` (present in shipped 0.9.0-beta.3).
- **Symptom:** With no lecture loaded, Process / Review / Transcript / Study still showed
  content from previous jobs — some complete and relevant, some incomplete and
  irrelevant. The user could not tell which lecture any screen belonged to.
- **Root cause:** the UI had **no concept of an active lecture at all**. `LP.state`
  tracked `jobsEmpty` but never a job identity. Every workspace screen read one global
  scratchpad (`LP.data.pipeline/slides/transcript/study/quiz/flashcards`) that was
  (a) seeded with demo content at boot, (b) overwritten by whatever the backend last
  pushed, and (c) never cleared — `job_deleted` only fired a toast. So screens rendered
  a union of demo seed + last-opened job + partially-loaded data. A second, subtler half:
  nothing stamped payloads with an owner, so a slow signal from the PREVIOUS lecture that
  landed after a switch silently repainted its data over the new one.
- **Attempts:** 1) considered wiping all blobs on every job change → **rejected**: flickers,
  loses instant switch-back, and does not fix the late-signal race. 2) Owner + per-job
  cache + centrally stamped payloads → **worked**, and makes staleness unrepresentable
  rather than something to remember to clean up.
- **Current fix:** `LP.state.jobId` owns the workspace; per-lecture blobs cached in
  `LP.byJob`; `emptyWorkspace()` means "nothing loaded" is structurally empty;
  `setActiveJob()` snapshots the outgoing lecture and applies the incoming one (also
  resetting per-lecture view state: chat, quiz session, export phase). The backend is
  authoritative: `_set_active_job()` is the single place `current_job` changes and emits
  `active_job`; `_emit()` stamps every job-scoped payload with its owning job id, and
  `ownsPayload()` drops any payload belonging to another lecture.
- **Two bugs found DURING verification (both fixed):** `renderTimeline` indexed
  `slides[v]` unconditionally, so an empty workspace threw and aborted the whole
  `renderWorkspace()` pass — which is why the sidebar kept naming an inactive lecture;
  and `job_deleted` deleted the cache entry *before* deactivating, so `setActiveJob`'s
  snapshot put it straight back.
- **Verification:** driven in a browser through the real signal path — activating a
  lecture wipes the demo seed and names it in the sidebar/breadcrumb; switching lectures
  shows 0 carried blocks/slides; **a late payload from the previous lecture is rejected**
  (data and title unchanged); switching back restores the cached workspace instantly;
  deleting the active lecture empties the workspace and drops its cache entry; deleting an
  inactive one leaves the active alone; a failed delete is a no-op; orphan log lines are
  dropped; app-wide state (theme, export formats) survives switches. 24 tests.
  **NOT verified in the packaged app** (needs a rebuild).
- **Files:** `app/ui/app.js`, `app/ui/bridge.js`, `app/desktop/engine_adapter.py`,
  `app/desktop/bridge.py`.

### BUG-01 — Global shortcuts fire through an open modal   ✅ FIXED (verified)
- **Area:** UI / keyboard handling (`app/ui/app.js`)
- **Reported / found:** 2026-07-25, UI/UX audit agent; independently re-verified by
  reading the handler. Build: source at `b288418` (same logic as 0.9.0-beta.3, so the
  **shipped beta.3 build has this bug**).
- **Symptom:** With the new-job modal open, pressing a digit key changed the screen
  *behind* the modal — measured: pressing `5` switched the underlying screen to "study"
  while the overlay stayed open — leaving the user on an unexpected screen after dismiss.
- **Root cause:** the global `keydown` handler (`app.js:1822-1834`) guarded only against
  `INPUT`/`TEXTAREA`/`contentEditable` and `Escape`. It had **no concept of an open
  overlay**, so the `1`–`7` screen map and the `F` focus toggle stayed live. The handler's
  own comment read "prototype behavior" — it shipped as written for the prototype.
- **Attempts:** 1) considered per-modal `stopPropagation` → **rejected**: overlays are a
  mix of static `[hidden]` divs and dynamically created `.lp-modal-ov` nodes, so each new
  modal would have to remember to opt in. 2) Central guard in the one global handler →
  **worked**, and covers future modals by default.
- **Current fix:** `topOverlay()` returns the highest-z-index open overlay; the keydown
  handler returns early whenever one exists (`app/ui/app.js`, keydown handler + helpers
  near `setOnb`).
- **Verification:** **verified live in a browser** — with an overlay open, dispatching
  `key:'5'` left the active screen at `home` (`screenBefore === screenAfter === "home"`,
  overlay still open). Plus `tests/test_webview_ui_fixes.py` asserts the guard precedes
  the shortcut map.
- **Files:** `app/ui/app.js`.
- **Refs:** `docs/UI_UX_AUDIT_BETA3.md` defect 1.

### BUG-02 — Modals have no focus trap; Tab escapes behind the overlay   ✅ FIXED (verified)
- **Area:** UI / accessibility (`app/ui/app.js`)
- **Reported / found:** 2026-07-25, UI/UX audit agent. Build: source at `b288418`
  (present in shipped beta.3).
- **Symptom:** Tabbing inside the new-job modal moved focus to the header's Save button
  *behind* the still-open overlay — keyboard users could activate hidden controls.
- **Root cause:** no focus-trap logic existed anywhere in `app.js`; overlays were plain
  divs with no `role="dialog"`/`aria-modal`, so the browser's natural tab order walked
  straight through them into the page.
- **Attempts:** trap implemented in the same central keydown guard added for BUG-01 →
  worked; no per-modal wiring needed.
- **Current fix:** `trapFocus(scope, e)` cycles Tab/Shift-Tab within the top overlay and
  pulls focus back in if it is outside; `focusFirst()` moves focus into an overlay on
  open (wired into `setOnb` and `lpModal`); overlays now carry `role="dialog"` +
  `aria-modal="true"`. `visibleFocusable()` skips `[hidden]` and zero-box elements so the
  trap can't focus something invisible.
- **Verification:** **verified live in a browser** — focus on the overlay's last control,
  dispatch Tab → `defaultPrevented === true` and focus wrapped to
  `BUTTON#btn-whatsnew-close`, still inside the overlay (6 focusables detected). Plus
  regression tests.
- **Files:** `app/ui/app.js`, `app/ui/index.html`.
- **Refs:** `docs/UI_UX_AUDIT_BETA3.md` defect 2.

### BUG-04 — Fresh profiles show a fake in-progress job and fake storage   ✅ FIXED (verified)
- **Area:** UI / empty states (`app/ui/index.html`)
- **Reported / found:** 2026-07-25, found by **driving the real desktop app** against a
  disposable profile (`LECTUREPACK_DATA_DIR`) — not by the static audit. Build: source at
  `b288418`; the same markup shipped in 0.9.0-beta.3, so **real beta.3 users see this on
  first launch**.
- **Symptom:** On a brand-new profile with zero jobs the app displayed
  `egypt_excerpt • Transcribing 62%` with a blinking orange activity dot, a breadcrumb
  naming that lecture, `STORAGE 340 MB`, and a footer progress bar at `62% · ~3m left` —
  while `RECENT JOBS` correctly read `0`. A first-run user is told a lecture they never
  imported is mid-transcription.
- **Root cause:** design-time placeholder content was hardcoded in `index.html` and never
  cleared. Two distinct failure modes:
  (a) `side-job-name` / `crumb-job` / `status-pct` / `status-bar` are only written when a
  status event carrying those fields arrives (`app.js:1903-1907`); with zero jobs no event
  ever fires, so the placeholders persist indefinitely.
  (b) `storage-label` (`340 MB`) and `proc-source-name` (`egypt_excerpt.m4v`) are
  **never written by `app.js` at all** — grepped every id, no writer exists. So the
  storage figure was wrong for *every* user in *every* state, permanently.
- **Attempts:** 1) considered clearing the values only in JS → **insufficient**: the
  placeholders would still paint on first frame before `boot()` runs. Fixed the shipped
  markup *and* added a JS reset. 2) Considered inventing a storage number client-side →
  **rejected**: fabricating a figure is the bug, not the fix. The widget is hidden until a
  backend actually reports disk usage (no such signal exists yet — see below).
- **Current fix:** `index.html` now ships idle values (`No lecture loaded` / `Idle` /
  `Home`, empty progress text, `width:0%`, no `lpblink` on the idle dot) and the storage
  widget ships `hidden`. `resetJobChrome()` in `app.js` re-applies the idle state as the
  first statement of `boot()`.
- **Remaining work — DONE 2026-07-25.** The missing backend signal now exists:
  `storage_changed` on `bridge.py`, fed by `LecturePackAdapter.push_storage()`, which
  walks the data dir on a worker thread (thousands of files would stutter the Qt main
  thread) and emits `{ok, used, used_h, free_h, pct}` after every `jobs_changed`.
  `pct` is usage as a fraction of the space *available to LecturePack* (used/(used+free)),
  not whole-disk usage — the latter would be a figure about the user's SSD, not this app.
  The honesty rule is preserved and tested: `ok:false` (demo adapter, or a failed walk)
  keeps the widget **hidden** rather than showing a guess. The bar markup was also fixed —
  it shipped `width:0%` while `setFill()` drives `scaleX`, so it could never have rendered.
  Covered by `tests/test_storage_signal.py` (7 tests).
- **Verification:** **verified live in a browser** — all of `side-job-name`,
  `proc-source-name`, `crumb-job`, `status-label` read their idle values,
  `status-pct` empty, `status-bar` `width:0%`, `storage-widget.hidden === true`. Plus
  regression tests. **NOT re-verified in the packaged app** (the published beta.3 binary
  predates these fixes; needs a rebuild).
- **Files:** `app/ui/index.html`, `app/ui/app.js`.

### BUG-06 — Scheduler silently accepts a time in the past   ✅ FIXED (verified)
- **Area:** UI / scheduling (`app/ui/app.js` `scheduleJobDialog`)
- **Reported / found:** 2026-07-25, UI/UX audit agent (code read — the agent could not
  drive it live because the static preview's queue is empty). Build: source at `b288418`.
- **Symptom:** The `datetime-local` input had no `min`, and the Schedule handler only
  checked for an empty value, so a past date/time was accepted with no feedback. What
  happens next depends on the missed-schedule policy, i.e. the user's intent is silently
  reinterpreted.
- **Root cause:** missing validation, both the declarative hint and the handler check.
- **Attempts:** adding `min` alone → **rejected as insufficient**: `min` is advisory and
  typed input bypasses it, so the handler must re-check.
- **Current fix:** input carries `min="<local now>"` and the Schedule action rejects
  `when < localNowValue()` with a "Pick a time in the future" toast. `localNowValue()`
  formats **local** time deliberately — `toISOString()` would shift the floor by the UTC
  offset and wrongly reject (or accept) up to a half-day window.
- **Verification:** regression tests assert the `min` attribute, the handler re-check, and
  that `localNowValue` never uses `toISOString`. **Not exercised against a live queue**
  (needs a real job to schedule) — the guard is client-side and independent of the queue,
  but the end-to-end schedule path remains on the human-validation list.
- **Files:** `app/ui/app.js`.
- **Refs:** `docs/UI_UX_AUDIT_BETA3.md` defect 5.

---

## Cross-cutting lessons (patterns, not single bugs)

1. **Design-time placeholder content is a shipping hazard in this UI.** `index.html` is
   authored as a full static mock so the screenshot pipeline works, which means *every*
   visible string is a real default that ships. When adding an element, decide its
   **empty state** immediately and make sure something actually writes it — BUG-04 had
   two ids (`storage-label`, `proc-source-name`) with **no writer anywhere in the
   codebase**. A quick audit for this class: for each `id="…"` in `index.html`, grep
   `app.js` for a writer; ids with none are permanent hardcoded values.
2. **A single global `keydown` handler needs a modal-state concept.** BUG-01 and BUG-02
   were the same root omission. Any new overlay inherits correct behaviour only because
   the guard is centralised in `topOverlay()` — keep it that way instead of adding
   per-modal key handling.
3. **The static preview and the real app fail differently.** The static audit could not
   see BUG-04 (needs a live bridge to prove `RECENT JOBS 0` next to a fake job chip), and
   the live app could not easily show BUG-03/BUG-05 (needs computed styles at several
   widths). Both passes are needed; neither alone is coverage.
4. **Client-side `min`/`max` on inputs is advisory.** Always re-validate in the handler
   (BUG-06), and build date floors from local-time components, never `toISOString()`.
5. **State with no owner rots.** BUG-04 and BUG-08 were the same disease at two
   altitudes: UI state that no single thing owns will drift into showing something false.
   Any new screen data must answer "which lecture does this belong to, and what does it
   look like when there is none?" before it ships. The enforcement points now exist —
   `WORKSPACE_KEYS` + `emptyWorkspace()` for ownership, `_emit()` stamping +
   `ownsPayload()` for freshness — so extend those rather than adding a parallel path.
6. **A contrast finding is usually systemic, not local.** BUG-05 was reported as one
   button and turned out to be five fills across both themes, reaching the DOM three
   different ways (inline styles, CSS classes, and selected-state ternaries). When one
   colour pair fails, compute the whole palette before fixing, and grep for every way the
   foreground can be set - a single-pattern sweep silently left 9 elements failing.
   **This recurred.** The follow-up pass was handed a tidy list of "3 remaining
   near-misses" and found **11** - and the reported figure (muted at 4.35) was not even
   the worst case (3.26). A previously-measured count is a *lower bound*, never a work
   list: re-run the full sweep from the token values every time, before and after. Two
   further rules earned here: (a) enumerate each token's *worst* surface, not the one it
   was reported on - `--muted` sits on four; (b) check the **reverse** direction before
   darkening a text token, because the same token is often also a background elsewhere.
7. **Verifying both halves is not verifying the seam.** BUG-09 sat behind a service that
   was tested directly and a UI that was tested with no backend. Both passed; the feature
   was 100% dead. When a handoff says "X and Y verified separately, the integration was
   never driven", treat that as a **red flag naming the most likely bug site**, not as a
   minor coverage gap. Drive the seam once, for real, before calling a feature done.
8. **A silent hang with empty stderr means the code never ran, not that it failed.**
   If a worker's `try/except` is broad and *nothing* is logged, stop looking for a
   swallowed exception and ask what never got invoked. For Qt: `QTimer.singleShot(0, fn)`
   without a context QObject starts the timer in the CALLING thread, so from a plain
   `threading.Thread` it never fires. Always pass a main-thread context object when
   marshalling out of a worker — and prove the mechanism in a 10-line script before
   trusting a fix for it.
9. **Inline styles beat class rules.** The design markup carries layout as inline styles,
   so any responsive override of it needs `!important` (BUG-03). A media query that "does
   nothing" is usually this.
