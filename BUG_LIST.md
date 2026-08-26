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

### DEF-044 — the runtime-setup gate crashed on exactly the failure it exists to explain   🟡 FIXED (shipped in 2.0.9; the packaged build's own runtime is healthy, so the fixed path is still unexercised there)
- **Area:** `lecturepack/services/first_run_checklist.py::build_first_run_checklist`,
  reached from `app/desktop/bridge.py::get_bootstrap`.
- **Found:** 2026-08-20, by the user, on a source run of the 2.0.9 candidate.
- **Symptom:** "Runtime needs repair" with **no components listed**, **Retry doing
  nothing at all**, and diagnostics reading "No additional diagnostics are available."
  Three separate-looking faults, one cause.
- **Root cause:** `RuntimeBootstrapService.assess` has two early returns that describe a
  failure of the WHOLE payload rather than of any component — `{"inventory": …}` when
  the inventory resolver raises, and `{"active_runtime": …}` when the runtime root
  cannot be resolved. Neither is a canonical inventory entry, so `checklist_group_for`
  raised `ValueError` and took `get_bootstrap` down with it. The renderer therefore
  never received a bootstrap payload: the component list stayed empty (the markup even
  has a "could not be listed" empty state for it), and **Retry stayed dead because the
  button re-enables inside the `.then()` of a promise that never resolved**.
- **Why it matters:** this is the first-run path on a machine whose payload is missing
  or damaged — the exact audience the screen is written for.
- **Prior art in the same file:** a comment above the fix already described unwrapping a
  nested `components` map for this same class of shape mismatch. That guard did not
  cover a result whose `.components` IS the sentinel map.
- **Fix:** recognise the two sentinels before grouping and render all three payload rows
  as needs-attention carrying the real reason. The `ValueError` for a genuinely unknown
  entry is deliberately NOT relaxed — it is what stops a future inventory addition being
  silently dropped from the checklist.
- **Tests:** `test_whole_payload_failure_renders_a_checklist_instead_of_raising` and
  `test_an_unknown_inventory_entry_still_raises` (the guard must survive its own fix).
  Confirmed failing with the fix reverted.
- **Still open, separately:** "Repair all" from a **source run** starts a worker that
  fetches a published runtime for the current version. 2.0.9 is not published, so it
  cannot succeed from a checkout. Whether it behaves correctly in a packaged build is
  UNVERIFIED and needs the built app.
- **Lesson:** **an error-reporting screen must be tested against its own error paths.**
  Every test here fed the checklist a well-formed component map, which is the one shape
  the screen never sees in the situation it exists for.
- **Files:** `lecturepack/services/first_run_checklist.py`, `tests/test_first_run_checklist_ui.py`.

### DEF-043 — Space kept every OTHER slide and skipped the rest without showing them   ✅ FIXED (verified in a real browser)
- **Area:** `app/ui/app.js`, the Review keyboard macros (Space branch).
- **Found:** 2026-08-20, while adding undo to the same handler. Not reported by a
  user, and no test caught it.
- **Symptom:** triaging a deck with the fast-path key advanced TWO slides per press.
  Every second slide was never displayed, and its detector default was kept silently.
- **Root cause:** the two halves of the behaviour were added in different releases.
  `btn-keep` grew its own "advance after judging" step (beta.5); the Space branch was
  written later (`e9ff280`, 2.0.7) against a J that did *not* advance, so it clicked
  `btn-next-slide` itself. Once the button advanced too, the branch advanced twice.
  The comment above it still described the old world, which is how it survived review.
- **Why no test caught it:** every test asserted the *stamped state*, which was
  correct -- the slide Space landed on really was kept. Nothing asserted the cursor
  moved exactly one step, and that was the whole defect.
- **Fix:** delete the extra `btn-next-slide` click. J, K and Space all advance
  because the button does. The comment now says so, and says not to re-add it.
- **Test:** `test_space_advances_once_not_twice`, which asserts `btn-next-slide` is
  absent from the Space branch rather than asserting the resulting state.
- **Verified (2026-08-20)** by driving the real renderer over HTTP in Chromium: one
  Space press moves the cursor 0 -> 1, a second moves it 1 -> 2.
- **Lesson:** **when a behaviour is split across a button and a key that drives it,
  moving the behaviour into one moves it into both.** Assert the delta (one step),
  not the destination state.
- **Files:** `app/ui/app.js`, `tests/test_transient_layer_polish.py`.

### BUG-47 — the study content file had an unlocked read-modify-write; a student's Ask/Teach Me answer could be silently discarded   🟡 FIXED (shipped in 2.0.9; not yet exercised on a real pack against a live gateway)
- **Area:** `lecturepack/services/ai_study_service.py` (`_expand_material`,
  `_basic_partial_refresh`, `_partial_state`, `_record_interaction_error`),
  `lecturepack/services/study_v2.py::save_content_preserving_cache`.
- **Symptom (predicted, never observed in the wild):** a student uses Ask or Teach Me
  while the pack is still growing in the background; their cached answer vanishes. The
  next identical question costs a full gateway round trip again. Nothing errors.
- **Root cause:** `_expand_material` did `load_content` → gateway call (up to ~50s) →
  `save_content` **without holding `_job_lock` across that window**, while the pack was
  already `STUDY_READY` and live in the UI. `cache_concept_response` correctly takes
  `_job_lock` for its own read-modify-write, but that cannot help: the expansion loop's
  save writes back a `content` dict snapshotted before the student's write existed.
  Classic lost update — the lock protects each writer individually, not the interleaving.
- **Rejected fix — do not retry:** widening `_job_lock` across the gateway call. It makes
  the lost update impossible and blocks every UI read for ~50s. That is the trade the
  original entry warned about.
- **Fix:** merge-on-save. `save_content_preserving_cache` re-reads the file under the
  lock at save time and re-adds only the `cached_responses` keys the snapshot never saw,
  then drops any of those whose concepts are absent from the content being written. That
  last filter is what keeps a *purposeful* prune from being undone: a snapshot cannot
  distinguish "someone else added this key" from "I deleted this key", and
  `delete_concept` — the only caller that removes cached answers — removes the concept
  along with them. All four slow-window writers in `ai_study_service` use it.
- **Test:** `test_expansion_does_not_discard_an_answer_cached_while_it_ran` drives a real
  expansion pass whose gateway client caches an answer mid-call, exactly once.
  **The first version of this test passed against the unfixed code** — the shared fixture
  client returns one fixed card that the pack already contained, so dedup skipped every
  save and the hazard was never reached. It only became a real test once the client
  served unique material per call. Confirmed failing without the fix, passing with it.
- **Lesson:** **a lock per writer is not a transaction.** When the competing writer is
  the user, ordering cannot save you, and the fix belongs at save time, not lock scope.
  And: a concurrency test that passes on the broken code is testing nothing — always run
  it against the unfixed line.
- **Files:** `lecturepack/services/study_v2.py`, `lecturepack/services/ai_study_service.py`,
  `tests/test_ai_study_service.py`.

<!-- ===================================================================== -->
<!-- 2.1.0 — the 2.0.9 adversarial stress test (F-01 .. F-38)              -->
<!-- ===================================================================== -->

> **The theme of this whole batch.** Nearly every P1 here is the same bug wearing
> different clothes: **the app reported success for work it had not done.** A save that
> could not land said `saved=true`. A rename that moved two of three lectures said "3
> lectures updated". An update check that succeeded said the build could not update. A
> failure that happened was never written down. When triaging anything in this family,
> ask *"who confirmed this, and did they wait for the answer?"* before anything else.

### BUG-49 — transcript corrections were accepted, confirmed, and thrown away   🟡 FIXED (2.1.0)
- **Area:** `electron-spike/python-sidecar.py::_save_corrections`; `app/ui/app.js::renderReviewTranscript`.
- **Found:** 2026-08-22, stress test F-35. Reproduced end-to-end: edit → Save → survives
  navigation → **gone after restart**.
- **Symptom:** editing a transcript line and pressing Save corrections reported success,
  the text stayed on screen across navigation, and the edit was gone at the next launch.
  The "0 corrections" badge never incremented either.
- **Root cause:** the handler zips incoming row texts against the SAVED segments.
  `zip()` stops at the shorter side, so for any job whose backend transcript layers are
  empty it produced **zero pairs**: nothing was marked changed, `save_working` rewrote the
  empties, and the response still said `saved=true, changed=0`. The edit crossed the
  bridge and died at the zip. `edited.json` written as `{}` proves the round trip happened.
- **Fix:** a save that cannot land raises instead of claiming success — empty backend
  segments and a length mismatch are both errors now, not silent truncation. The renderer
  also stops offering the caret and the Save button on a lecture with no persisted
  transcript, so the failure is not reachable by accident.
- **Do NOT "fix" this by seeding the working layer from the rendered rows.** The renderer's
  rows can come from the demo fixture, which has no timings and is not this lecture's data;
  seeding from them would write fabricated content into a real transcript.
- **Tests:** `test_f35_saving_into_an_empty_transcript_raises`,
  `test_f35_the_caret_is_not_offered_without_a_saved_transcript`.

### BUG-50 — a failed job came back from a restart looking like it had never run   🟡 FIXED (2.1.0)
- **Area:** `lecturepack/models/job.py::set_stage_status`; `electron-spike/python-sidecar.py::_on_pipeline_failed`.
- **Found:** 2026-08-21, stress test F-17 (and the "Queued" third of F-16).
- **Symptom:** a job that failed with a visible error was presented after relaunch as a
  fresh "Queued / Ready to process", with no notification, doomed to fail identically.
- **Root cause — TWO independent holes, either sufficient on its own:**
  1. `set_stage_status` recomputes `overall_status` from the stage table, and
     `all_statuses` **deliberately excludes `STAGE_REVIEW_READY`**. A job that failed
     there set `failed` on that call, then the very next stage write recomputed over a
     table in which nothing had failed and fell into the `else`: `pending`.
  2. `_on_pipeline_failed` only ANNOUNCED the failure — it emitted `job_failed` and
     `status_changed`, both renderer-only — and never wrote it to the authoritative
     lifecycle, so startup reconciliation had nothing to preserve.
- **Fix:** a terminal verdict is sticky against recomputation (only real progress — a
  stage actually going `running`/`completed` — leaves it), and the sidecar persists the
  failed lifecycle **before** announcing it.
- **Worth carrying forward:** the three regression tests were confirmed FAILING against
  the unfixed line first, reproducing `'pending' == 'failed'` exactly. 2.0.9's handoff
  records a regression test that passed against broken code; this one was not trusted
  until it had been seen to fail.
- **Tests:** `test_f17_a_failure_on_review_ready_is_not_recomputed_away`,
  `test_f17_the_erased_failure_does_not_survive_a_reload`,
  `test_f17_a_cancelled_job_is_equally_sticky`,
  `test_f17_an_explicit_retry_can_still_leave_a_terminal_state`,
  `test_f17_the_sidecar_persists_the_failure_before_announcing_it`.

### BUG-51 — one lecture, three simultaneous contradictory statuses   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js`, the `pipeline_changed` handler.
- **Found:** 2026-08-21, stress test F-16.
- **Symptom:** Home banner "Processing", sidebar "Queued", Process "Ready to process ·
  0%", footer "IDLE", `queue.json` empty — for ONE job. Pause and Cancel both enabled and
  both inert.
- **Root cause:** the renderer decided a job was RUNNING from *"not every stage is
  done"*. That is a different fact: a job that has never started has all stages `pending`
  and satisfies it. Combined with BUG-50 (which reset failed jobs to pending) this
  painted dead jobs as live.
- **Fix:** running means a stage is actually `active`, with the job list's own status as
  the tiebreaker for a stale payload.
- **Tests:** `test_f16_running_means_a_stage_is_actually_active`.

### BUG-52 — renaming a subject split it, and the toast hid that it had   🟡 FIXED (2.1.0)
- **Area:** `electron-spike/python-sidecar.py::_set_jobs_group`; `app/ui/app.js::handleGroupRename`.
- **Found:** 2026-08-22, stress test F-30. Confirmed on disk across navigation.
- **Symptom:** renaming "tone" → "Renamed Tone Subject" toasted "(3 lectures updated)";
  only 2 moved, and the old subject persisted forever holding the third.
- **Root cause:** `_set_job_group` (singular) updates the loaded job's **in-memory**
  manifest after writing it; `_set_jobs_group` (plural) did not. Renaming a subject that
  contained the currently-open lecture wrote that manifest to disk and then had
  `_emit_job_payloads` serialise the stale in-memory copy straight back over it. The
  toast made it invisible: it fired *before* the backend answered, counting what was
  asked for rather than what happened.
- **Fix:** the bulk path updates the in-memory manifest too, and the toast waits for the
  real count and names the shortfall when there is one.
- **Tests:** `test_f30_bulk_group_write_updates_the_loaded_job_too`,
  `test_f30_the_rename_toast_reports_what_happened`.

### BUG-53 — subject-scope Study rendered a DIFFERENT lecture's content   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js::studyV2GroupLoad`.
- **Found:** 2026-08-22, stress test F-29. **This is BUG-08's wrong-lecture class
  recurring at subject altitude — check BUG-08 before touching scope code.**
- **Symptom:** the scope header correctly named the subject; the Study Guide, Quick Study
  and Flashcards below it showed an unrelated single lecture's material. Rebuild Map was
  a silent no-op.
- **Root cause:** only the `res.ok` branch replaced `studyV2.content`. A failed prepare, a
  subject with no ready lectures, or a null response all left the previously-open
  LECTURE's content on screen under the SUBJECT's header. A null response also returned
  early without clearing `loading`, so the scope sat on "Collecting member lectures"
  forever — which is what made Rebuild Map look dead.
- **Fix:** content is dropped on the way IN, so an unpainted subject is visibly empty
  rather than convincingly wrong. Null is handled as the failure it is, and Rebuild Map
  reports both outcomes.
- **Tests:** `test_f29_entering_a_subject_drops_the_previous_lecture_content`,
  `test_f29_rebuild_map_reports_both_outcomes`.

### BUG-54 — the updater declared the build incapable of updating   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js`, the `btn-check-updates` handler.
- **Found:** 2026-08-22, stress test F-34. **Same message class as DEF-020/BUG-31
  (2.0.4–2.0.6). Different cause — do not assume the old fix regressed.**
- **Symptom:** Settings → Updates said "Updates are not available in this build." on a
  production install with auto-check enabled.
- **Root cause — TWO independent, either sufficient:**
  1. **Contract mismatch.** `checkForUpdates()` in `production-main.js` answers
     `{ok, status:'uptodate'|'available'|'error'|'untrusted'}`. The renderer tested
     `result.available` and `result.phase`, both always `undefined`, and fell through to
     the build-is-incapable string on EVERY outcome including success. The `update_state`
     EVENT does carry `phase` and painted the right answer a moment before the promise
     overwrote it.
  2. **A timer that raced the answer.** An unconditional 4s `setTimeout` called
     `settle()` with that same string regardless of what had already happened;
     `settle()` guarded against a *superseded* check but not against one that had already
     *answered*. A GitHub round trip routinely exceeds 4s.
- **Fix:** `settle()` is one-shot, the vocabulary is the host's, the timeout is 20s and
  says it timed out, and "no update exists" is no longer worded as "this build cannot
  update" — different facts, only one of which is a reason to stop looking.
- **Tests:** `test_f34_the_check_reads_the_contract_the_host_actually_speaks`,
  `test_f34_no_timer_may_overwrite_an_answer_that_already_arrived`.

### BUG-55 — multi-link import discarded every link but the first   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js::mediaUrls` + the Check link handler; `python-sidecar.py::_probe_media_url`.
- **Found:** 2026-08-21, stress test F-15.
- **Symptom:** (a) newline-separated links produced no visible response at all;
  (b) space-separated links were accepted but the confirm step read "Download 1".
- **Root cause:** (b) `mediaUrls` split on newlines only, and the validity test
  `/^https?:\/\/.+/` has a `.+` that spans a space — so `"https://a https://b"` passed as
  ONE url. (a) was not a dead button: the probe does a network lookup **per link** on a
  background thread, nothing disabled the button, showed progress, or bounded the wait,
  so a slow two-link probe was indistinguishable from nothing happening.
- **Note on the evidence:** the report cited a HAR capture showing zero network requests
  as proof the button was dead. That was a false lead — `probe_media_url` crosses the
  IPC bridge to the sidecar and never appears in a renderer HAR. Do not re-derive this.
- **Fix:** split on any whitespace and require `\S+`; the sidecar splits the same way.
  Check link shows "Checking…", refuses re-entry, and reports a timeout.
- **Tests:** `test_f15_links_separated_by_any_whitespace_are_separate_links`,
  `test_f15_a_slow_probe_is_visible_and_bounded`.

### BUG-56 — the guided-demo lecture deleted itself with no warning   🟡 FIXED (2.1.0)
- **Area:** `python-sidecar.py::_cleanup_demo_session` (behaviour unchanged); `app/ui/app.js`.
- **Found:** 2026-08-21, stress test F-20 (filed P2, flagged P0-candidate).
- **Symptom:** a processed and hand-triaged demo lecture vanished from the library
  mid-session. No confirmation (the normal delete flow has one), no recycle-bin trace.
- **Root cause:** **working as designed** — the demo job is temporary and the tour deletes
  it on completion. Nothing ever said so, so from the student's side it was data loss.
- **Fix:** the deletion stays; the silence does not. Job summaries carry `is_demo`, the
  card is badged "Demo · temporary", and the removal is announced. `demo_session` also had
  to be declared in the bridge contract — it was fired to the renderer but not declared,
  so subscribing to it failed `test_every_frontend_signal_is_in_contract`.
- **Tests:** `test_f20_the_demo_lecture_announces_that_it_is_temporary`,
  `test_f20_demo_session_is_a_declared_contract_signal`.

### BUG-57 — a disabled control kept its signal fill and answered clicks with silence   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js::setCtl`; `app/ui/app.css::.lp-ctl-off`.
- **Found:** 2026-08-21, stress test F-06.
- **Symptom:** with no lecture, "Export PDF" rendered vivid orange (adjacent "Export HTML"
  correctly dimmed) and clicking it did nothing at all.
- **Root cause:** `setCtl` faded to 45% opacity only. A saturated orange fill at 45% is
  still the brightest thing on a cream screen. And Chromium does not dispatch `click` on
  a disabled button *and* does not show its `title` — so the reason, which existed, was
  unreachable by every route.
- **Fix:** disabled controls drop to the neutral surface BEFORE fading, and one delegated
  listener finds the control under the pointer and says the reason out loud.
- **Trap for the next person:** the first attempt hit-tested with `elementsFromPoint`.
  `pointer-events:none` removes an element from hit testing entirely, so it never found
  the control. It geometry-tests `[data-ctl-tip]` rects instead, and verifies nothing is
  covering them.
- **Tests:** `test_f06_disabled_controls_lose_their_signal_fill`,
  `test_f06_a_disabled_control_says_why_when_clicked`.

### BUG-58 — Study with no lecture showed the design-time placeholder chrome   🟡 FIXED (2.1.0)
- **Area:** `app/ui/app.js::studyV2Load` / `studyV2ShowEmpty`; `app/ui/index.html`.
- **Found:** 2026-08-21, stress test F-03. **This is the BUG-04/BUG-15 placeholder class
  again — the third time. Any screen whose renderer early-returns is a candidate.**
- **Symptom:** on an empty library, Study showed "READY TO STUDY / Your progress 0%" with
  two ENABLED CTAs; "Continue studying" landed on an empty Flashcards tab reading "This
  lecture has no flashcards yet" when there was no lecture at all.
- **Root cause:** `studyV2Load()` returns early when there is no job, so nothing ever
  overwrote the markup `index.html` ships with.
- **Fix:** a real empty state, with the mode tabs disabled and every panel hidden.
- **Tests:** `test_f03_study_has_a_real_empty_state`.

### DEF-045 — undo was one run deep and said "yet"   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js`, the Review stamp/undo closure. Stress test F-11.
- **Root cause:** a single `stampRun`; once a Ctrl+Z consumed it the next answered
  "Nothing to undo yet." while a wrong reject from 30s earlier stayed applied.
- **Fix:** completed runs go on a stack and unwind newest-first — the only SAFE order,
  because a later run can re-stamp a slide an earlier one touched, so LIFO is what makes
  each run's remembered previous state the right one to restore. Verified live in a real
  Chromium: two keeps, one reject, undo, undo → all four slides back to pending.
- **Tests:** `test_undo_reaches_past_the_most_recent_run`.

### DEF-046 — the footer pinned a finished stage name forever   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::renderProcessingStatus` / `restoreStatusRight`. Stress test F-10.
- **Root cause:** the footer's right slot is the runtime's identity; a running stage
  borrows it. Nothing gave it back, so Review sat at "Ready to export" with "Detecting
  slides" beside it for the rest of the session.
- **Fix:** only a live stage may write there; the slot is restored the moment nothing runs.

### DEF-047 — "ffmpeg exited with status ExitStatus.NormalExit and code -22"   ✅ FIXED (2.1.0)
- **Area:** `lecturepack/infrastructure/ffmpeg_wrapper.py::_handle_finished`. Stress test F-18.
- **Root cause:** a Qt enum's repr and an errno, shown to a student as a toast. The actual
  cause was a link-imported video with **no audio track** (yt-dlp fetched video-only).
- **Fix:** the wrapper probes for an audio stream before extracting and says so in words;
  the raw text is kept as `last_error_detail` for the log. `friendlyErrorMessage` also maps
  the old string, because jobs that failed under earlier builds still carry it on disk.

### DEF-048 — the Exports panel offered two formats that do not exist   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::exportFormats`. Stress test F-33/F-06/F-27.
- **Root cause:** DOCX and TSV were offered and `export_service.py` has never written
  either — no code path exists. And the toggles gated nothing: `align_and_export` writes
  its whole set and never reads the selection, so unticking VTT still produced
  `transcript.vtt`.
- **Fix:** the list is an accurate inventory of the seven transcript files an export
  writes, and says so instead of pretending to be a picker. The test cross-checks each
  advertised key against `export_service.py`, so adding a format to the UI without
  writing it fails.

### DEF-049 — validating Vulkan produced no verdict of any kind   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::setComputeReadyFallback`. Stress test F-36.
- **Root cause:** **the same shape as BUG-54's 4s timer.** A 1500ms `setTimeout` fired
  unconditionally after Validate and replaced the still-pending check with "CPU · AVX2
  ready" — a line that says nothing about Vulkan. Engine detection routinely exceeds 1.5s.
- **Fix:** the fallback waits 15s, says the check did not answer rather than implying one
  was made, and any real response always yields a verdict — including the
  `vulkan_benchmark_ok` state the config already tracked and never showed.

### DEF-050 — four light-theme labels failed WCAG AA   ✅ FIXED (2.1.0)
- **Area:** `app/ui/index.html`. Stress test F-37.
- **Root cause:** a FILL token used as ink. `--orange` measures 3.41:1 and `--blue`
  2.15:1 on the light background. `--orange-ink` (4.94) and `--blue-ink` (5.81) already
  existed for exactly this.
- **Fix:** four call sites repointed. Dark is unaffected (7.58 / 13.48). A programmatic
  sweep of every visible text node across all eight screens plus the header returns zero
  AA failures in light theme.

### DEF-051 — scrollable regions read as clipped   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.css`. Stress test F-04 + F-05, one root cause.
- **Root cause:** the scrollbar thumb was fully transparent until the pointer entered the
  pane, so anything below the fold looked severed rather than scrollable — the cheat
  sheet's last row and the home empty state's step hints were both cut mid-glyph.
- **Fix:** the thumb rests at `--line` and brightens on approach. The cheat sheet also
  became a column (title fixed, list scrolls, gutter reserved) and the home empty card
  gave back 16px so its hints clear the footer at the default window size.

### DEF-052 — the Process screen had no state for jobs that stopped   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::renderProcessJobState`. Stress test F-19.
- **Root cause:** no branch for interrupted/failed/cancelled; it fell through to hiding
  its banner. Paging the job switcher onto an interrupted lecture therefore showed
  NOTHING, which is indistinguishable from the switcher refusing to land on it. Home
  offered Resume/Restart; Process offered silence.
- **Fix:** those states get a banner that names them and a Restart that works.

### DEF-053 — the import banner lied during file selection   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::beginBrowseImport` / `setImporting`. Stress test F-13.
- **Root cause:** `browse_video`'s promise does not settle until the native dialog
  closes, so "Importing video…" span the whole selection and vanished silently on cancel.
- **Fix:** the banner says what is actually happening, and cancelling says so.

### DEF-054 — files the app refused were dropped on the floor   ✅ FIXED (2.1.0)
- **Area:** `electron-spike/production-main.js::importMultiplePaths`. Stress test F-14.
- **Root cause:** `expandImportPaths` records exactly why each path was rejected and
  `importMultiplePaths` **destructured that array away**. Four files in, two lectures out,
  nothing said about the other two.
- **Fix:** the reasons reach the renderer and are listed in the batch modal. The sidecar's
  per-file `failures` (reached the pipeline and failed it) are merged with the host's
  `skipped` (never forwarded at all) — both are files the student sent and did not get back.

### DEF-055 — the comprehension check allowed exactly one attempt   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::renderStudyTeach`. Stress test F-31.
- **Root cause:** grading disabled the textarea AND the button and wiped what was typed.
  One accidental Enter burned the attempt for that concept.
- **Correction to the original report:** F-31 claimed it "grades an EMPTY submission".
  It does not and cannot — the client blocks empty answers and the server rejects them.
  A parallel session reproduced the 0% headlessly with the tester's real answer text: it
  was a genuine grade of a rubric-incomplete answer. Do not chase the empty-submit theory.
- **Fix:** the answer survives the re-render, the field stays editable, the button invites
  another go, and an empty submit says so instead of reading as a dead button.

### DEF-056 — the grader called a statement wrong that its own ideal answer states   ✅ FIXED (2.1.0)
- **Area:** `ai-gateway/src/tasks.js`, the `grade_short_answer` instruction. Addendum A1.
- **Root cause:** with a rubric-incomplete answer the feedback called the student's
  "transparent fur" statement incorrect while its own `ideal_answer` field said
  "fur is transparent hollow hair over black skin". Scoring was defensible; the wording
  was not, and feedback that contradicts itself costs trust in every later grade.
- **Fix:** the instruction forbids it explicitly — credit what appears in `ideal_answer`,
  then name only what was actually missing.

### DEF-057 — drag auto-scroll died at the bottom of the window   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::dragScroll.update`. Stress test F-38.
- **Correction to the original report:** F-38 concluded auto-scroll "does not exist".
  It does, it is wired into the pointer path, and it uses `scrollTop +=` rather than the
  `scrollBy` that was grepped for. Do not re-derive this.
- **Root cause:** the container is resolved FROM THE POINTER and the edge zone reaches
  72px BEYOND the container's rect — so the last part of the gesture, where the user
  pushes past the bottom of the list, puts the pointer over the status footer. The footer
  scrolls nothing, the document scroller does not either, `containerAt` returned null, and
  scrolling stopped exactly where it was needed.
- **Fix:** keep working the container the gesture was already on; the existing bounds test
  releases it.

### DEF-058 — the breadcrumb read "Home > Home"   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::setCrumbJob`. Stress test F-01/F-02/F-08.
- **Root cause:** the trail is `[Lecture] > Screen` and the lecture segment fell back to
  the literal string "Home" — duplicated on Home, and naming a nonexistent lecture
  everywhere else. `demo` was also missing from `CRUMBS` and rendered as its own lowercase
  route id beside eight capitalised siblings.
- **Fix:** one writer; the segment and its separator hide when no lecture is loaded. The
  test enumerates `data-screen` attributes from the markup, so a new screen without a
  label fails.

### DEF-059 — the cheat sheet misstated the bindings it exists to teach   ✅ FIXED (2.1.0)
- **Area:** `app/ui/app.js::SHORTCUT_GROUPS`. Stress test F-12.
- **Root cause:** J and K stamp AND advance (they have since `btn-keep` grew its own
  advance, DEF-043), and the sheet said they only stamp.

### DEF-060 — the sidebar storage figure truncated mid-word   ✅ FIXED (2.1.0)
- **Area:** `app/ui/index.html`. Stress test F-09. The 2.0.3 wrap fix traded wrap for
  truncation; the caption and the figure shared one 190px row. They stack now.

### F-32 — suspected whole-app crash on an AI call   🟠 MITIGATED, NOT REPRODUCED (2.1.0)
- **Area:** `electron-spike/production-main.js`.
- **Symptom (reported):** around the first Teach Me invocation every LecturePack process
  vanished and relaunched with fresh PIDs. Not reproducible; an external kill could not be
  ruled out.
- **What was found:** the main process had **no process-level error handler at all**. An
  unhandled promise rejection terminates the process outright on modern Node, so any
  rejection on an async host path would take the whole app down instantly leaving nothing
  in the log — precisely the shape of an unreproducible whole-app disappearance.
- **Action:** `unhandledRejection` and `uncaughtException` are logged rather than fatal.
  **This is a mitigation, not a root-cause fix.** If it recurs, the log will now carry the
  stack the original report could not produce. Leave this entry open until then.

### BUG-59 — the "authoritative" release workflow has never once succeeded   🔴 OPEN (found 2.1.0)
- **Area:** `.github/workflows/release-electron.yml`.
- **Found:** 2026-08-23, dispatching it for the 2.1.0 release.
- **Symptom:** the run dies at "Build the Electron release candidate" with
  `Required sidecar runtime file is missing: D:\lecturepack\lecturepackinfmpeg.exe`.
- **Root cause:** the packaged sidecar needs `bin/` (ffmpeg, ffprobe, whisper-cli, the ggml
  DLLs, deno) and `models/ggml-base.en.bin` — roughly 150 MB of third-party binaries that
  are **deliberately gitignored** (`.gitignore:21-22`). A CI checkout therefore has none of
  them, and the workflow contains **no step that fetches or restores them**. It cannot
  succeed as written, on any commit, ever.
- **Evidence it never has:** all five runs of this workflow are failures
  (2026-08-15 x2, 2026-08-19 x2, 2026-08-23). v2.0.9's four assets were published
  2026-08-20 with no successful run behind them, so they were uploaded from a local build.
- **Why this matters more than it looks:** the file's own header calls it "THE single
  authoritative LecturePack desktop application release path" and "the ONLY workflow
  permitted to publish" the four assets. A reader trusts that. In reality every release
  including 2.0.9 has been hand-built and uploaded with `gh release create`, which means
  the signing step, the FINAL-hashes-from-signed-bytes step, and the four-asset assertion
  have never actually run for a shipped build. **This is the same class as the acceptance
  gate fixed earlier in 2.1.0: a gate that cannot pass, whose red is indistinguishable
  from a real regression.**
- **Fix (not done — needs a decision that is not the agent's to make):** either give CI the
  runtime (a release asset it downloads and checksums, a self-hosted runner, or a private
  bucket + secret), or delete the workflow and make `RELEASING.md` describe the local build
  that is actually used. Do not leave it claiming authority it does not have.
- **Until then:** 2.1.0 was built locally and published with `gh release create`, exactly as
  2.0.9 was. The local build was verified further than any prior release — packaged
  self-test 12/12, packaged acceptance 16/16, launch smoke, and the packaged UI confirmed
  byte-identical to source.

### BUG-63 — the Process nav was a dead click for anyone already on Process   🟢 FIXED (2.1.2)
- **Area:** `app/ui/app.js::setScreen`. **Re-opens BUG-62**, which is marked FIXED (2.1.1)
  and whose fix is still present and still correct — it just never ran on this path.
- **Reported:** 2026-08-24, from a fresh 2.1.1 install on a second laptop.
- **Symptom:** click a queued lecture (which navigates to Process showing that lecture),
  then press Process in the sidebar to get back to the lecture actually running. Nothing
  happens. The screen stays on "Waiting to process · Position 2" and there is no way back
  to the running lecture except hunting through the library.
- **Root cause:** `setScreen` opened with `if (LP.state.screen === name) return;`. BUG-62's
  follow was placed inside the body that runs *after* that guard, so it only fires when the
  screen CHANGES. Arriving at Process by clicking a queue row leaves you on Process, so
  every subsequent press of the Process nav was swallowed whole.
- **The lesson, and it is the same one OBS-01 taught in reverse:** BUG-62 was verified by
  three tests, all of which assert on `followActiveProcessingJob` and on the carries-a-job
  flag. Not one of them asked whether the function is *reachable* from the button the user
  actually presses. A fix verified only at the function it changed is verified against the
  wrong thing.
- **Fix:** the early return now runs the same follow, behind the same
  `_screenChangeCarriesJob` guard, before returning. Entrance motion still does not replay
  — which is the only reason the early return exists.
- **Tests:** `test_bug63_*` (three). Confirmed FAILING against 2.1.1's source first.

### BUG-64 — every Study answer flashed the whole screen   🟢 FIXED (2.1.2)
- **Area:** `app/ui/app.js` — the `study_v2_record_quiz` / `study_v2_record_flashcard`
  call sites, and the new `studyV2RefreshProgress`.
- **Reported:** 2026-08-24. Seen on the cached guided-demo lecture, where no AI call is
  involved at all — which is what makes it unmistakably a render problem, not latency.
- **Symptom:** click a quiz option and the whole Study screen blanks and repaints; the
  "Correct" verdict appears only *after* the flash, so the answer reads as unstable.
- **Root cause:** both record calls chained `.then(function () { studyV2Load(); })`.
  `studyV2Load` re-fetches all Study CONTENT and then re-renders the scope header, the
  generation state, the overview and the active mode pane from scratch. The click handler
  had already written the verdict into `#study-quiz-feedback` synchronously; the reload
  wiped it and painted it again a moment later. Recording an answer changes PROGRESS, and
  content was being reloaded to collect it.
- **Attempts:** 1) debouncing the reload → **rejected**: it makes the flash later, not
  absent, and a slower wrong repaint is harder to reason about. 2) A progress-only refresh
  that never touches the pane the student is interacting with → **worked**.
- **Fix:** `studyV2RefreshProgress()` fetches the same status payload, updates
  `studyV2.progress`/`summary`, and repaints the overview **only when the overview is the
  visible pane**. It keeps `studyV2Load`'s in-flight owner guard, so a late response for
  the previous lecture still cannot repaint this one. The three Quick Study record sites
  were already fire-and-forget and are unchanged.
- **Tests:** `test_bug64_*` (three), including a count of all five record sites so a new
  one cannot quietly reintroduce the reload.

### BUG-65 — Ask showed the PREVIOUS lecture's conversation   🟢 FIXED (2.1.2)
- **Area:** `app/ui/app.js::setActiveJob`, new `askFeedSnapshot` / `restoreAskFeed`.
  **Re-opens BUG-08.**
- **Reported:** 2026-08-24, with the note "we made this fixed before, but I don't know how
  it got lost in the code". It was never lost. It was fixed on a different surface.
- **Symptom:** ask a question about lecture A, open lecture B, and B's Ask pane still shows
  A's conversation. A brand-new lecture should be blank and a previously-used one should
  show its own history.
- **Root cause:** BUG-08 built the per-lecture workspace — `LP.byJob`, `snapshotWorkspace`,
  `applyWorkspace`, owner-stamped payloads — and `setActiveJob` clears `LP.state.chat` on
  every switch. But `LP.state.chat` belongs to the **old** chat surface (`#chat-feed`) that
  Study V2 replaced. The live Ask pane is `#study-ask-feed`, whose entire history lives in
  the DOM and in nothing else: `studyAskSend` appends markup, `appendStudyAskText` mutates
  the last bubble. Nothing snapshotted it and nothing cleared it, so it simply stayed on
  screen across the switch. **The fix was still there, applied to a surface that had
  stopped being used** — which is exactly what "it got lost in the code" feels like from
  the outside.
- **Fix:** the feed is snapshotted into the outgoing lecture's `LP.byJob` blob and restored
  from the incoming one. Stored as markup rather than as a message model **because every
  control inside the feed — suggestion chips, source chips, copy buttons — is bound by
  delegation** (on `#study-ask-feed` or on `document`), so restored markup is fully live.
  A test asserts that property; if a per-element listener is ever added inside the feed,
  this has to become a real message model. A "Thinking…" bubble left mid-stream is rewritten
  as interrupted before it is stored, so a restored feed never shows a permanent
  "Thinking…", and `askStreaming` is cleared on the switch. With NO lecture the feed stays
  bare — suggestion chips inviting "Explain this lecture simply" with nothing loaded would
  be BUG-58 again.
- **Tests:** `test_bug65_*` (five).

### BUG-66 — the progress meters did not correspond to the live log   🟢 FIXED (2.1.2)
- **Area:** `lecturepack/controllers/job_controller.py`,
  `lecturepack/infrastructure/cv_engine.py`.
- **Reported:** 2026-08-24 — "it's detecting slides in the live log, but the slide meter is
  not moving; it's transcribing, and the transcribe meter is not moving."
- **Symptom:** the log streams while the meter beside it sits still, so the app looks hung
  during the two longest stages of a run.
- **Root cause — two separate holes, same shape.** The log and the meters are fed by
  different signals (`stage_log` vs `stage_progress`) and **only Detect Slides and Export
  were ever wired to a `progress` signal at all**:
  1. **Transcribe emitted no `stage_progress` whatsoever.** The bar sat at 0 for the entire
     stage — on a long lecture, for most of the run.
  2. **Detect Slides reached 100% roughly two-thirds of the way through its work.** The
     sampling scan owned the whole 0–100 range; deduplication and the full-resolution
     capture pass ran afterwards, emitting `status_message` the whole time against a bar
     already pinned at 100.
- **Fix:**
  1. `_emit_transcribe_progress` derives a percentage from live segment end timestamps
     against the known source duration. It is monotonic (the chunked online backend
     interleaves segments), clamped to 99 (`_on_stage_finished` writes the 100), and
     **claims nothing when the duration is unknown or a segment carries no timestamp** —
     the bar holds its last real value rather than showing a guess. A meter that invents a
     number is the "reported success for work it had not done" family from 2.1.0.
  2. `cv_engine` reserves headroom: `SCAN_PCT = 85` for the sampling scan, `DEDUP_PCT = 92`
     for deduplication, and the capture pass reports per written frame up to 100. Applied
     to both decode paths (FFmpeg and the legacy cv2 fallback).
- **Not fixed here:** Inspect, Extract Audio and Align still report no percentage. They are
  short enough that no one has reported them, and inventing progress for them would be the
  same defect this entry is about.
- **Tests:** `test_bug66_*` (six), driving the controller directly. Confirmed FAILING
  against 2.1.1 first.

### BUG-68 — yt-dlp link download returned caption sidecar (.vtt) as the media file   🟢 FIXED (2.1.3)
- **Area:** `lecturepack/services/media_fetch.py::MediaFetcher.download`, `_path_from_info`, progress hook.
- **Reported:** 2026-08-25 — video download with published captions succeeded and showed transcript in the Transcript screen, but pipeline processing failed on Inspect/Extract Audio/Detect Slides with "Audio extraction failed: This video has no audio track" and 0x0 video dimensions.
- **Symptom:** YouTube videos with captions populated the transcript, but the job failed during pipeline processing. The video had 0x0 dimensions, no thumbnail poster, audio extraction failed, and slide detection produced 0 slides.
- **Root cause:** yt-dlp's download progress hook fires for every downloaded component, including subtitle tracks (`.vtt`, `.srt`). Because subtitle downloads finish *after* the video track, `hook(d)` with `status == "finished"` set `state["path"] = d.get("filename")`, overwriting the video file path with the `.en-orig.vtt` caption path. `_path_from_info(info)` similarly lacked filtering against `SIDECAR_SUFFIXES`. As a result, `MediaFetcher.download()` returned the `.vtt` file as the job's video source. Downstream FFprobe, FFmpeg audio extraction, and OpenCV slide detection were executed against a `.vtt` subtitle file rather than the downloaded media file.
- **Fix:** Filter out files matching `SIDECAR_SUFFIXES` in the download progress hook, in `_path_from_info`, and in `download()`'s fallback path so only legitimate media files are ever returned as the download result.
- **Tests:** `test_download_hook_and_info_never_return_caption_sidecar` in `tests/test_source_captions.py`.

### BUG-67 — the installer's task checkbox was clipped on a scaled display   🟠 MITIGATED, NOT CONFIRMED (2.1.2)
- **Area:** `app/packaging/lecturepack.iss` — but the defect is in Inno Setup's own Setup
  binary, not in this project's code.
- **Reported:** 2026-08-24 — the "Create a desktop shortcut" checkbox and its label on the
  installer's "Select Additional Tasks" page rendered running into the line above it, with
  only part of the text visible.
- **What was actually verified, and what was not.** The page was compiled from an .iss
  carrying the identical `[Setup]`/`[Tasks]` block, launched, and captured **at 96 DPI on a
  1920×1080 display: it renders correctly.** So this is a scaling failure, and it has NOT
  been reproduced. The compiled `Setup.exe` manifest was read directly and declares
  `<dpiAware>true</dpiAware>` **and nothing else** — system DPI awareness only, no
  `PerMonitorV2`. The wizard is therefore laid out for the DPI in force when the process
  started and bitmap-scaled by Windows afterwards, at which point fonts no longer fit the
  control rectangles measured for them. That is consistent with the report. **No `.iss`
  directive can change that manifest.**
- **Mitigation:** `WizardSizePercent=120` gives every caption headroom over its measured
  width — Inno's own documented remedy for text that does not fit. `WizardResizable=yes`
  was tried alongside it and **removed**: this Inno version compiles it to "obsolete and
  ignored" (the wizard is resizable regardless). It was caught only because the probe build
  was read for warnings rather than just for "Successful compile". A directive that
  produces nothing but a build warning is worse than none, because the ledger would have
  recorded a mitigation that was never in force.
- **Also addressed while here:** the wizard now carries LecturePack's own artwork
  (`make_wizard_images.py` → `wizard-large-*.bmp` / `wizard-small-*.bmp`, the mark from
  `make_icon.py` on the dark shell colour) at **all six of Inno's DPI sizes**. That is not
  only cosmetic: the same system-DPI-awareness limit that clips captions also resamples any
  artwork Inno was not given at the right size. Only the banner and header icon can be
  themed — the wizard body uses system colours, and a fully dark wizard needs a custom VCL
  style (.vsf) that this toolchain cannot author. Verified by launching the compiled probe
  and capturing the welcome page.
- **This entry stays OPEN.** A mitigation reasoned from a manifest is not a confirmed fix,
  and closing a user-visible report on inspection is precisely what OBS-01 got wrong. It
  needs the reporter's laptop, at its real scaling, running the 2.1.2 installer.
- **Tooling gap, related to OBS-03:** driving the wizard here required `SendKeys` against
  the live desktop, and one keystroke batch landed in an unrelated foreground window. Do
  not automate the real desktop again for this; build the probe and have a human look.
- **Tests:** `test_bug67_the_wizard_is_not_sized_to_the_millimetre` pins the two directives.

### BUG-60 — a queued lecture could not be dragged ANYWHERE   🟢 FIXED (2.1.1)
- **Area:** `app/ui/app.js::_jobIsDraggable`. **Supersedes OBS-01**, which was filed on
  2026-08-23 as "seen once, not reproduced" with a note offering the queue rule as the
  *benign* explanation. **The benign explanation was the bug.** A second report with a
  screen recording made it obvious in minutes.
- **Symptom:** with lectures queued, nothing in the library could be dragged — cards would
  not lift, subject cards accepted nothing, and the Subjects screen's whole purpose (moving
  a lecture between subjects) was dead. Only the processing queue's own reorder rows still
  worked, because those are a different drag kind.
- **Root cause:** `_jobIsDraggable` was `_jobIsReady(j) || _jobIsReprocessable(j)`, and
  **both** of those end in `&& !_jobInQueue(j.id)`. That test belongs to "can this be
  QUEUED", which is a Process-target question. Filing a lecture under a subject is a label
  change with nothing to do with the pipeline. Queue two lectures — i.e. use the app the
  way it is meant to be used — and the entire library went inert with nothing on screen
  saying why.
- **Fix:** `_jobIsDraggable` is now `!!j && !!j.id`. The old predicate survives as
  `_jobIsQueueable` and the **Process drop target** refuses what it cannot queue, in words,
  at hover time ("… is already in the queue").
- **Proven before and after** against the shipped 2.1.0 renderer with two queued jobs:
  before, both Home cards rendered with no `data-lp-drag` and no grip; after, both carry
  `lecture` and a grip, and so do the Subjects rows, with the subject cards lit as targets.
- **Tests:** `test_bug60_being_queued_does_not_make_a_lecture_undraggable` and the three
  beside it in `tests/test_v211_drag_and_process_focus.py`.
- **The lesson, which is the reusable part:** OBS-01 reasoned from source that the drag
  path was byte-identical to 2.0.9 and concluded there was probably no bug. The code WAS
  identical — the defect predates 2.1.0 — but "unchanged" is not "correct", and a
  user-visible report should not be closed on a diff. It was also unreproducible only
  because the test harness could not drive a drag at all (see below), which should have
  been read as "I cannot test this" rather than "this is probably fine".

### BUG-61 — the drag shuddered because the list was rebuilt underneath it   🟢 FIXED (2.1.1)
- **Area:** `app/ui/app.js::renderQueue` / `renderJobs` / `renderSubjects`.
- **Symptom:** dragging in the processing queue stuttered and flickered badly — described
  as "the frames shutter". Worst in the queue, which is where dragging still worked.
- **Root cause:** the queue re-renders on every `queue_changed` / `pipeline_changed` tick,
  which while a lecture is transcribing is several times a second. Each rebuild discarded
  the carried row, the insert indicator and the candidate highlights and recreated them a
  frame later. The proxy survives (it lives on `<body>`), so what the eye sees is the LIST
  flickering out from under a card that stays put.
- **Fix:** `deferWhileDragging()` — while `LPDrag.dragging()` is true a render records
  itself and returns; `finish()` flushes them once the gesture ends, after `active` is
  cleared. Nothing is lost: a drag lasts a second or two.
- **Tests:** `test_bug61_lists_are_not_rebuilt_during_a_drag`,
  `test_bug61_deferred_renders_run_when_the_drag_ends`.

### BUG-62 — Process did not show the lecture that was actually processing   🟢 FIXED (2.1.1)
- **Area:** `app/ui/app.js::setScreen` / new `followActiveProcessingJob`.
- **Symptom:** opening Process from the sidebar showed whichever lecture happened to be
  selected — often an idle one — so the student had to click around to find the lecture
  that was actually running.
- **Fix:** direct navigation to Process follows the running job (falling back to the head
  of the queue). Navigation that CARRIES a chosen lecture — clicking a card, clicking a
  queue row — is left alone, because there the student named the lecture they wanted and is
  entitled to its real state, "Waiting to process · Position 2" included. `_screenChangeCarriesJob`
  distinguishes the two, and is cleared in a `finally`.
- **Tests:** `test_bug62_*` (three).

### OBS-04 — the packaged acceptance gate fails ~50% of runs on shutdown   🔴 OPEN (found 2.1.2)
- **Found:** 2026-08-24, running the release gate against the 2.1.2 packaged build before
  publishing. **This blocked the 2.1.2 publish.**
- **Symptom:** `scripts/electron_packaged_acceptance.py` reports
  `unexpected_errors: ['packaged app exit code 1']` and `overall FAIL`, while **every other
  check passes** — app_launched, sidecar_ready, job_started/completed, slides, transcript,
  export (13 files), first_exit_clean, restore_passed, no orphans, no renderer failures, no
  bridge errors. Only the second (restore) session's process exit code is wrong.
- **Rate: 2 failures in 4 consecutive runs**, same build, same machine, nothing else
  changed. It is a coin flip, not a state-dependent failure.
- **Where the exit code comes from:** the harness posts `WM_CLOSE`, waits 20s, then
  `proc.kill()` — and a Windows kill *is* exit code 1. So "exit code 1" means "the app did
  not finish quitting within 20 seconds", not "the app returned an error".
- **Evidence, and it points at the quit outliving the bound:**
  - Failing run 1: the session log's last line is `update_none` — the process was killed
    with an update check having just completed and no `session_closed` ever written.
  - Failing run 2: `session_closed` **was** written cleanly, and the process was still
    killed. So the session tears down fine and the *process* lingers afterwards.
  - Passing runs: identical logs, ending in `sidecar_exit` → `production_document_removed`
    → `session_closed`.
  - `requestQuit()` chains `stopSession` then `app.quit()`. Nothing sets a non-zero exit
    anywhere in `production-main.js`. The most likely holder is an in-flight update check —
    `update_check_started` fires seconds before shutdown in these runs — keeping the event
    loop alive past the bound. **Not proven.**
- **This is NOT a 2.1.2 regression.** 2.1.2 changed the renderer and the engine; the
  shutdown path in `production-main.js` is untouched by this release.
- **But it does cast doubt backwards.** The 2.1.1 handoff records "packaged acceptance
  16/16". At a 50% failure rate, **one green run is what a coin flip looks like.** A gate
  that is only ever run once cannot distinguish "passes" from "passed this time". Treat any
  single-run acceptance result in this project's history as unconfirmed.
- **Next:** decide whether the app is slow to quit (a real product nit — quitting should
  not wait on a network call) or whether the harness's 20s bound is simply too tight for a
  cold machine. Instrument `requestQuit()`/`app.quit()` with timestamps and run the gate
  ten times. **Do not "fix" this by raising the timeout until it is known which of the two
  it is** — raising the bound on a genuinely slow quit hides it from the only gate that
  looks.
- **Process lesson:** run this gate more than once before believing it. It was run four
  times here only because the first run failed; had the first run passed, 2.1.2 would have
  been published over a gate that fails half the time.

### OBS-02 — the taskbar icon shows the Electron logo   🟠 NOT A CODE DEFECT (investigated 2.1.1)
- **Reported as:** "the LecturePack icon on the taskbar is still the Electron logo, we
  changed this hundreds of times."
- **Everything on the app side is already correct, verified on the machine showing it:**
  - the built `LecturePack.exe` carries the LecturePack icon (extracted and rendered — the
    orange rounded square), and its version resource reads LecturePack / 2.1.0;
  - `app/packaging/lecturepack.ico` is a well-formed ICO with all seven sizes
    (16/24/32/48/64/128/256, 32bpp PNG);
  - `resources/lecturepack.ico` ships in the packaged tree and `applicationIcon()` resolves
    it, so `BrowserWindow` gets an explicit icon — and the **window title bar in the user's
    own recording shows the correct icon**;
  - `app.setAppUserModelId('LecturePack.LecturePack')` runs before any window is created,
    and the installer's `[Icons]` entries set the **same** AppUserModelID;
  - both Start Menu shortcuts point at the running 2.1.0 exe with `IconLocation=,0`
    (i.e. the target's own icon).
- **Therefore:** Windows is serving a cached icon. `%LOCALAPPDATA%\Microsoft\Windows  Explorer\iconcache_*.db` were last written before the current build. The taskbar icon
  for an AUMID-grouped app is cached per identity, and the identity string has never
  changed, so an icon cached during an early build persists across every rebuild. **That
  is exactly why changing it in code "hundreds of times" never took.**
- **Do NOT keep changing code for this.** The remedy is on the machine: clear the Explorer
  icon cache and restart `explorer.exe`, or install to a fresh path. If it is ever seen on
  a **clean** machine, that is a different bug and this entry does not apply.

### OBS-03 — nothing can drive a real drag against the packaged build   🔴 OPEN, TOOLING GAP
- Raised while chasing BUG-60, and the reason OBS-01 was mis-filed as unreproducible.
- The renderer served over plain HTTP never wires the drag layer: the runtime setup gate
  blocks boot without a bridge and marks the app shell `pointer-events:none`
  (`app.js` ~L5287), which **fakes the exact symptom** and is a false lead. Synthetic
  `PointerEvent`s do not start a drag even with the gate released. The packaged app refuses
  `--remote-debugging-port`, so CDP is unavailable.
- BUG-60 was ultimately proven by driving `jobs_changed`/`queue_changed` through the real
  bridge stub and asserting on the RENDERED attributes — good enough for "can it lift",
  useless for "does the gesture feel right".
- **Until this is closed, any drag report has to be judged from a recording.** Fixing it —
  a debug-port build flag, or a headless harness that boots the renderer with a stub
  bridge — would pay for itself the next time.

### F-07 — NOT A DEFECT (verified 2026-08-22)
- Reported as a missing space in guided-demo step 3 ("...that slide.Fix a mis-heard...").
  The space is present in `index.html`, in the packaged copy, and **in the reporter's own
  screenshot** (`m1-19-demo-step3.png`). Misread. Recorded so it is not "fixed" later.

### BUG-48 — every atomic JSON write shared one temp file name   🟡 FIXED (shipped in 2.0.9)
- **Area:** `lecturepack/infrastructure/file_manager.py::write_json_atomic`,
  `lecturepack/services/reset_service.py::reset_data_root`.
- **Found:** 2026-08-20, as the "related" note on BUG-47.
- **Symptom (predicted):** rare corruption or a silently reverted save of any JSON state
  the app owns — `config.json`, `queue.json`, a job manifest, Study content.
- **Root cause:** the temp path was a fixed `filepath + ".tmp"`. `os.replace` is atomic,
  but the *scratch file* was a shared resource: two writers to the same path (the sidecar
  and the UI process both persist job state) interleave their partial writes into one
  buffer, and the loser's rename can publish half of the winner's bytes. Per-job locks do
  not help — they are per-process.
- **Fix:** `tempfile.mkstemp` in the destination directory, so every writer gets its own
  buffer; the rename stays atomic. `reset_data_root` now sweeps both the new
  `.<name>.<random>.tmp` shape and the historical `<name>.tmp` left by older builds.
- **Tests:** `test_atomic_json_writes_do_not_share_one_temp_file`,
  `test_reset_sweeps_both_shapes_of_leftover_atomic_temp_file`.
- **Files:** `lecturepack/infrastructure/file_manager.py`,
  `lecturepack/services/reset_service.py`, `tests/test_polish_backend.py`.

### DEF-040 — the new stemmer DELETED content words whose stem is a stopword   ✅ FIXED (caught in review; every test still passed)
- **Area:** `lecturepack/services/ai_study_service.py::_terms`.
- **Symptom:** a forestry lecture could not be retrieved by the word "forest"; an
  anatomy lecture not by "shoulder"; property law not by "owner".
- **Root cause:** `_terms` stemmed FIRST and filtered stopwords AFTER. The suffix strip
  turns `forest`→`for`, `shoulder`→`should`, `owner`→`own`, `outer`→`out` — all of which
  are stopwords, so the term was dropped entirely. Symmetric on both sides (query *and*
  concept text), so it produced no error and no empty result — just a silently missing
  match on the query's single most discriminating word.
- **Fix:** test the ORIGINAL word against `_STOPWORDS`, never its stem.
- **Lesson:** **order matters between a normalizer and a filter.** Stem-then-filter tests
  a word the user never typed. The same fix incidentally closed a second leak in the
  other direction (`after`→`aft`, `only`→`onli` were surviving the filter).
- **Files:** `lecturepack/services/ai_study_service.py`, `tests/test_ai_study_service.py`.

### DEF-041 — Teach Me pre-warmed concepts the student never sees first   ✅ FIXED
- **Area:** `lecturepack/services/ai_study_service.py::_expand_material`.
- **Root cause:** the pre-warm sorted by `-importance` with **no tiebreak**, while
  `quick_study_material` sorts by `(-importance, title.casefold())`. Models rarely spread
  the `importance` field, so in the common case every concept ties at 3 and the tiebreak
  is the *only* thing ordering them — pre-warm got normalizer order, the student got
  alphabetical. Disjoint sets: the cache was paid for and never hit.
- **Fix:** one authoritative `study_priority_order()` used by both.
- **Lesson:** **two places that must agree on an order must share the function, not the
  intent.** A tiebreak is not a detail when the primary key is usually tied.
- **Files:** `lecturepack/services/ai_study_service.py`, `tests/test_ai_study_service.py`.

### DEF-042 — the stemmer severed exactly the words the ranker relies on most   ✅ FIXED
- **Area:** `lecturepack/services/ai_study_service.py::_stem`.
- **Symptom:** "how do waves propagate" scored **zero** relevance against a concept
  titled "Wave".
- **Root cause:** blindly stripping `-es` gave `waves`→`wav` while `wave`→`wave`. This hit
  `molecule`, `particle`, `force`, `state`, `value`, `variable`, `source`, `gene` — the
  **high-IDF domain nouns** of a science lecture, i.e. precisely the terms IDF weights
  most heavily. I had first dismissed these as "low-IDF words in practice"; that was
  wrong, and review caught it.
- **Fix:** English adds `-es` only after a sibilant. Strip `es` when the root ends
  `s/x/z/ch/sh` (`process`, `box`, `church`), otherwise strip only the `s` and keep the
  silent `e` (`wave`, `molecule`).
- **Residue (documented, accepted):** `case`/`cases`, `house`/`houses`, and the
  `-sis`/`-ses` family still miss — separating those needs a lexicon. The tempting
  `ses`→`sis` rule was rejected: it also mangles `houses`, `phases`, `responses`, `causes`.
- **Lesson:** **when you dismiss a class of misses as unimportant, check the weighting
  first.** The dismissal was backwards — these were the heaviest-weighted terms, not the
  lightest.
- **Files:** `lecturepack/services/ai_study_service.py`, `tests/test_ai_study_service.py`.

### DEF-037 — parallelizing the evidence phase broke Cancel   ✅ FIXED (found by adversarial review of my own diff, not by tests)
- **Area:** `lecturepack/services/ai_study_service.py` (`prepare_ai_study`).
- **Symptom:** pressing Cancel during "Reading selected lecture slides…" appeared to do
  nothing for up to ~30s. Nothing errored; the job just ignored the user.
- **Root cause:** collapsing the sequential vision/enrichment loops into a thread pool
  removed the per-call `cancelled()` check. The old code tested cancellation before every
  one of up to 6 calls and returned immediately. The new code checked once before
  dispatching, and `with ThreadPoolExecutor(...)` calls `shutdown(wait=True)` on exit —
  so cancel had to wait out the slowest in-flight provider.
- **Fix:** `wait(..., timeout=1.0, return_when=FIRST_COMPLETED)` in a loop instead of
  `as_completed`, re-checking `cancelled()` each pass and cancelling pending futures;
  explicit `shutdown(wait=False, cancel_futures=True)`.
- **Also fixed in the same pass:** `as_completed` yields in *race* order, so the slide
  interpretations sent to `study_material_generation` were ordered nondeterministically —
  identical input could produce a different pack. Results are now sorted back into
  request order before use.
- **Lesson:** **making something concurrent silently deletes every check that used to sit
  between the sequential steps.** Cancellation, progress, and ordering all lived in that
  gap. When converting a loop to a pool, enumerate what the loop body did *besides* the
  work itself.
- **Files:** `lecturepack/services/ai_study_service.py`.

### DEF-038 — the Teach Me pre-warm cost more than it saved   ✅ FIXED (bounded)
- **Area:** `lecturepack/services/ai_study_service.py` (`_expand_material`).
- **Symptom:** an optimization added to make Study *faster* that made the post-ready pass
  roughly twice as long and doubled gateway requests.
- **Root cause:** it warmed **every** concept, one serial gateway call each, inside a pass
  that already makes one call per concept. A 12-concept lecture went from 12 calls to 24.
  Worse, `study_v2` keeps only the newest **24** cached responses and Ask shares that
  cache — so warming a large pack evicted its own entries as fast as it wrote them, and
  burned free-tier budget (which is what trips `prioritizeHealthyRoutes` cooldown and
  degrades every other task) on concepts the student may never open.
- **Fix:** `EXPAND_PREWARM_CONCEPTS = 6`, highest-importance first, with a cancellation
  check after each warm.
- **Lesson:** **speculative caching is only a win when the hit rate is high and the cache
  can hold the result.** Both conditions have to be checked against the real cache bound,
  not assumed. "Pre-cache everything" quietly inverted the goal of the change.
- **Files:** `lecturepack/services/ai_study_service.py`, `tests/test_ai_study_service.py`.

### DEF-039 — Gemini's relaxed JSON mode was applied to ALL OpenAI-compatible routes   ✅ FIXED (test added)
- **Area:** `ai-gateway/src/providers.js`.
- **Root cause:** the fix for Gemini's `PROVIDER_INVALID_JSON` keyed the `json_object`
  fallback on `route.provider === 'openai_compatible'`. That is a *provider type*, not a
  vendor: `safeRoute` accepts arbitrary `openai_compatible` routes from `AI_ROUTE_CONFIG`
  with any endpoint. A Groq / Together / vLLM route added later would silently lose strict
  `json_schema` enforcement — which those hosts DO support — and start returning
  free-form JSON, i.e. more `provider_invalid_shape`, the exact failure being fixed.
- **Fix:** key on the host (`generativelanguage.googleapis.com`) via an explicit
  `GEMINI_JSON_OBJECT_HOSTS` set.
- **Note:** the schema still reaches the model under `json_object` — `buildMessages`
  embeds it in the system prompt. Enforcement is prompt-level rather than constrained
  decoding; that is the accepted trade, not an oversight.
- **Lesson:** a workaround for one vendor must be scoped to that vendor. `provider` here
  means "wire protocol", and quirks are per-host.
- **Files:** `ai-gateway/src/providers.js`, `ai-gateway/tests/gateway.test.mjs`.

### DEF-035 — every OpenRouter route was dead: `openrouter/free` is not a model id   ✅ FIXED (real slugs verified against the live OpenRouter catalog)
- **Area:** `ai-gateway/wrangler.toml`, `ai-gateway/wrangler.toml.example`.
- **Symptom:** none visible. That is the point — OpenRouter was configured as the primary
  route for `web_enrichment` and `group_analysis` and as the fallback for everything else,
  and every one of those calls 4xx'd and fell through to the next provider. The gateway's
  fallback logic is good enough that the app still worked, so the whole provider was
  silently contributing nothing while appearing configured.
- **Root cause:** `openrouter/free` was set for all nine OpenRouter model vars. It is not a
  real model id — OpenRouter has no such slug. Checked against `openrouter.ai/api/v1/models`:
  the genuinely free models today are `nvidia/nemotron-3.5-lightning:free` (1M context),
  `dots-studio/dots-3-note-preview:free` (512K), `liquid/lfm-2.5-2.6b:free`, and two
  poolside coding models.
- **Second defect in the same lines:** primary and fallback were the *same* string, so
  `resolveRoutes` deduped the fallback away entirely (it filters on
  `provider|failureDomain|model`). Even a valid id would have yielded one route, not two.
  Primary and fallback are now deliberately different models.
- **Not fixed:** `OPENROUTER_VISION_MODEL` still holds the placeholder. No verified free
  OpenRouter model accepts image input, and NVIDIA + Gemini both precede this slot in
  `vision_slide`'s route order, so the slot is effectively unreachable. Left explicit
  rather than pointed at a paid model.
- **Lesson:** a config string that is never validated and sits behind a working fallback
  chain can be wrong for the entire life of the project without producing one symptom.
  **Model ids belong in the "verify against the provider's live catalog" bucket, and the
  free catalog churns — re-check it, don't trust this entry's list to stay true.**
- **Files:** `ai-gateway/wrangler.toml`, `ai-gateway/wrangler.toml.example`.

### DEF-036 — the Teach Me pre-warm cache was wiped by the loop that created it   ✅ FIXED (regression test confirmed to fail without the fix)
- **Area:** `lecturepack/services/ai_study_service.py` (`_expand_material`).
- **Symptom:** a "pre-cache Teach Me during generation" optimization that measurably did
  nothing — the student still paid a full gateway round trip on first click, while the app
  had already spent one request per concept warming a cache it then destroyed.
- **Root cause:** a lost update, entirely self-inflicted and introduced in the same change.
  `_expand_material` snapshots `content = study_v2.load_content(job)` at the top of each
  iteration and re-saves that dict at the bottom. `teach_me()` caches by *independently*
  loading and re-saving the content file (`study_v2.cache_concept_response`). Warming
  after the snapshot meant the iteration's closing `save_content` wrote back a dict that
  predated the cache entry, silently dropping it.
- **Fix:** warm before the snapshot is taken. One-line reorder; the comment at the call
  site states the constraint so it cannot be "tidied" back.
- **Verified:** the fix was re-broken on purpose and
  `test_generation_prewarms_teach_me_so_the_first_click_costs_no_request` fails
  (`KeyError: 'cached'`) without it. 18/18 pass with it.
- **Lesson:** **any helper that persists state independently is unsafe to call between a
  load and its matching save.** This pattern (snapshot → mutate → save) is all over
  `_expand_material` and `regenerate_affected`; anything called inside that window must be
  read-only or run outside it. The failure is invisible — no error, no log, just a feature
  that quietly does nothing.
- **Files:** `lecturepack/services/ai_study_service.py`, `tests/test_ai_study_service.py`.

### DEF-033 — processing did nothing for EVERY already-imported lecture   ✅ FIXED (verified on the packaged binary; 4 tests, checked they fail without the fix)
- **Area:** `app/desktop/engine_adapter.py` (`start_processing`),
  `lecturepack/controllers/job_controller.py` (the `self.job` it reads).
- **Symptom (user):** "it fails to run processing." Pressing Start on any lecture already
  in the library did nothing visible.
- **Root cause:** the adapter owns the job the WORKSPACE shows (`current_job`); the
  controller owns the job the PIPELINE runs (`controller.job`). Two separate objects, and
  only the internal queue-promotion path (`_promote_next`) ever synced them. So
  `start_processing` resolved a job, logged its product mode, and then died inside
  `run_pipeline()`. From the packaged app's own log:

      [review]  opened job Heinrich Schliemann ...
      [engine]  Product mode: Study Pack (slides + transcript)
      [error]   Pipeline failed: No job loaded.

- **Why it survived so long:** a fresh import masked it completely — the import path calls
  `set_job` itself. The packaged acceptance gate imports a video and then processes it, so
  the gate exercised the ONE path that worked. Coverage existed and pointed the wrong way.
- **Fix:** sync the controller inside `start_processing`, at the single point every caller
  passes through, guarded on `job_id` so re-starting the same job cannot reset controller
  state mid-run. Not at the call sites: that is what left the UI path out in the first place.
- **Lesson:** when two objects both hold "the current X", the bug is not if they diverge but
  when. And a gate that only ever drives the happy path certifies the happy path.
- **Files:** `app/desktop/engine_adapter.py`, `tests/test_start_processing_controller_sync.py`.

### DEF-034 — the microinteraction polish shipped outside the design system   ✅ FIXED (guarded by tests)
- **Area:** `app/ui/app.css` (drag proxy, drop stamp, drop insert, timeline tick, edge
  flashes, slide loupe), `app/ui/app.js` (Review key macros).
- **Where it came from:** a parallel worktree (`antigravity/microinteractions-polish`).
  The behaviour was good and was kept — cherry-picked, authorship preserved — but it was
  written against no design system at all.
- **Five defects, all invisible in a screenshot:**
  1. `box-shadow: var(--shadow)` on the slide loupe. That token does not exist. CSS drops
     an undefined custom property silently, so the loupe shipped with NO shadow and nothing
     reported it.
  2. `drop-shadow(0 14px 22px rgba(0,0,0,.28))` on the carried drag card — the only blurred
     shadow in a file that has hard tokens (`--shadow-hard`, `--shadow-ink`) and otherwise
     zero blur. It read as a different application.
  3. Drop-stamp rings in `rgba(0,0,0,.35)`, which all but vanish on a dark ground.
  4. Glows (`0 0 8px`) on the drop-insert bar and the snapped timeline tick. Glows belong to
     `#glowing-demo-card`, which is named for it.
  5. Hardcoded `#2ecc71` / `#e74c3c` in the keep/reject flashes, bypassing the palette and
     BUG-05's contrast work.
  Plus 222 lines of animation CSS with ZERO `prefers-reduced-motion` neutralization, which
  §8 of app.css calls out by name as an incomplete change, and four bare `ease` keywords
  instead of the shared token curve.
- **Fix:** hard offsets in `--shadow-ink`, palette tokens throughout, a reduced-motion block
  that keeps colour (information) and drops motion, and
  `tests/test_css_tokens_defined.py` — which fails on any `var(--token)` app.css does not
  define (JS-owned tokens discovered from `setProperty` calls rather than hand-listed) and
  on any blurred shadow outside the deliberately-glowing selectors. Verified it fails when
  the loupe bug is reintroduced.
- **Also fixed:** `Space` in Review was an exact duplicate of `J` — same button, same flash,
  no advance — so triaging a deck re-stamped the first slide forever. It now keeps and
  advances. Arrow keys were added for navigation so the macros are additive; every macro
  drives the existing on-screen control rather than reimplementing it, so a macro cannot
  drift from what its button does.
- **Lesson:** an undefined CSS token is not an error, it is a silent no-op — the one class of
  visual bug that survives review by looking almost right. Assert the vocabulary, not the
  appearance.
- **Files:** `app/ui/app.css`, `app/ui/app.js`, `tests/test_css_tokens_defined.py`.

### DEF-031 — the packaged visual acceptance GATE was itself dead, and had been for four releases   ✅ FIXED (both gates now run to completion on the frozen binary)
- **Area:** `scripts/packaged_visual_acceptance.py`, plus a new
  `scripts/packaged_drag_acceptance.py`.
- **Symptom:** every run of the release gate died at the first-run setup step with
  `RuntimeError: UI element not found: #btn-runtime-continue`, before it reached a single
  assertion. A gate that exits early looks indistinguishable from a gate that found nothing.
- **Root cause:** `4cd98da` ("polish setup tour and lecture interactions") removed
  `#btn-runtime-continue` from the runtime-setup overlay. The overlay now clears via
  `#btn-runtime-done`; `#btn-runtime-confirm` ("Confirm & repair") stays **disabled** on a
  machine whose checks are already ready. The gate was never updated, so it referenced an id
  that no longer existed anywhere in the tree.
- **Why it matters more than the drag bug it was hiding.** This is the gate whose entire
  purpose is to catch "shipped dead in every build" — the DEF-025 failure mode. It was
  broken by a UI rename and stayed broken, silently, while three releases (2.0.4, 2.0.5,
  2.0.6) went out. **The verifier failed in exactly the way the thing it verifies fails.**
- **Fix:** click `#btn-runtime-done`, and wait for it to be enabled rather than assuming.
  The new drag gate additionally asserts its OWN aim before trusting a negative result
  (see DEF-032) so a dead harness can never again be read as a dead feature.
- **Lesson:** a gate needs a canary. An early exit and a clean pass are the same exit code
  to anyone not reading the log, so a gate must assert that it reached its assertions.
  Grepping for an id costs seconds; four releases of false confidence do not.
- **Files:** `scripts/packaged_visual_acceptance.py`, `scripts/packaged_drag_acceptance.py`.

### DEF-032 — DEF-026 was verified on the PACKAGED binary, and the harness lied twice first   ✅ FIXED (8/8 checks green on the frozen exe)
- **Area:** `scripts/packaged_drag_acceptance.py` (new).
- **Why this exists:** DEF-026 was only ever executed in a real browser
  (`electron-spike/production-main.js` loading `app/ui` from the worktree). DEF-025 proves
  that is not enough — it shipped dead in EVERY build having passed browser checks. The
  internal drag needed to be driven on the frozen executable.
- **How:** CDP `Input.dispatchMouseEvent`, not JS-dispatched events. Chromium synthesises
  **trusted** pointer events from it, so the `pointerdown`/`pointermove`/`pointerup` layer
  sees what a hand produces. A `new PointerEvent()` from `Runtime.evaluate` proves nothing:
  an untrusted event can drive a listener a real gesture never reaches. The gesture moves in
  18 steps, because one jump would skip both the lift threshold and the `pointermove`
  auto-scroll — the DEF-023 regression path — and pass while the gesture is broken.
- **Two false negatives the harness produced before it was right, both of which looked
  exactly like "the drag is dead in the packaged app":**
  1. **Aimed off-screen.** The press point came from `getBoundingClientRect` on a card below
     the fold. CDP input is dispatched at VIEWPORT coordinates, so it went into nothing.
     `elementFromPoint` returned `null` — that null was the whole diagnosis.
  2. **Pressed a modal scrim.** The first drop correctly raised the reprocess confirmation;
     its scrim then covered the page, so the second gesture pressed `.lp-modal-ov`.
  Both now fail loudly: the gate refuses to press a point outside the viewport or one where
  nothing is hit-testable, and it reports what is under the press point on every gesture.
- **Verified on the packaged binary:** card lifts (`body.lp-drag-in-flight` +
  `.lp-drag-proxy` mounted), the Process target arms, the drop is announced
  ("demo lecture queued for processing"), app state changes, reprocess asks before replacing
  existing work, and a drop on nothing says so out loud ("Can't drop here — was not moved").
- **Lesson:** a negative result from a harness is a claim about the harness until its aim is
  proven. Both false negatives would have been filed as a fourth instance of the drag bug.
  Assert the probe before believing the probe.
- **Files:** `scripts/packaged_drag_acceptance.py`.

### DEF-029 — internal drag moved to a POINTER-driven layer so the carried card can have physics   ✅ FIXED (driven with real mouse input in the running app)
- **Area:** `app/ui/app.js` (`LPDrag` input layer, `buildProxy`/`updateAt`/`commit`/`abandon`),
  `app/ui/app.css` (`.lp-drag-proxy` and friends).
- **Why, and the constraint nobody can engineer around.** The owner asked for a 3-5° tilt,
  `scale(1.03)`, an elevated shadow and a magnetic spring snap. **None of that is reachable
  with native HTML5 drag**: the drag preview is a bitmap the OS composites, outside CSS
  entirely. `setDragImage` can only hand it a static snapshot. So the input layer — and only
  the input layer — is now pointer-driven, drawing the carried card ourselves.
- **The proposed library would NOT have solved this.** `@atlaskit/pragmatic-drag-and-drop`
  is itself a wrapper over native HTML5 DnD, so it cannot style the drag preview either; and
  `app/ui` has no build step (plain files loaded by BOTH the Electron host and Qt WebEngine),
  so adopting it means adding a bundler to packaging. It would have cost a toolchain and
  delivered none of the headline items. Rejected on those grounds, with the owner informed.
- **Two input paths is inherent, not a design failure.** OS file drops can ONLY arrive as
  native drag events, so the window-level `dragover`/`drop` handlers still own them and were
  left untouched. Internal drags are suppressed on the native path (`dragstart` →
  `preventDefault` for any `[data-lp-drag]`) and `draggable="true"` was removed from every
  internal source, so the two paths can never both run for one press.
- **What was preserved unchanged:** the registry, the refusal reasons, the status strip, the
  insertion bar, the candidate highlighting, and every action (`set_jobs_group`,
  `reorder_queue`, `queue_jobs`). Only the input layer moved.
- **REGRESSION CAUGHT AND FIXED IN THE SAME CHANGE — DEF-023 by a new route.** Drag
  auto-scroll was wired to the native `dragover`, which a pointer drag never fires, so a
  lecture lifted at the bottom of a long library silently could not reach the Process tab
  again. `onPointerMove` now drives the SAME `dragScroll` manager (never a second one) and
  `finish()` stops it. Pinned by `test_the_pointer_drag_path_still_auto_scrolls`.
- **Hit-testing is geometric, not event-target based:** the proxy is `pointer-events:none`
  and `updateAt` uses `document.elementFromPoint`, so the carried card cannot shadow the
  target underneath it.
- **Refusal had to move onto the carried card.** With no OS cursor to paint `no-drop`, a
  refused target now also marks the proxy (`.is-bad`, dashed red) — the strip alone is at the
  bottom of the window where a user aiming a card is not looking.
- **Compositor discipline (AD-20's actual concern):** the proxy is ONE fixed element, it
  exists only while a drag is in flight, and it transitions `transform`/`opacity` only —
  both compositor properties, so the snap cannot trigger layout. Targets and the resting UI
  still animate no geometry whatsoever, which the test suite asserts separately.
- **Verified with REAL mouse input** (CDP `Input.dispatchMouseEvent`, not synthetic
  DragEvents): computed proxy transform `matrix(1.02808, 0.06288, -0.06288, 1.02808, …)` —
  i.e. the tilt and scale are genuinely applied — source card at `opacity: 0.4`, 4 candidates
  lit, `cursor: grabbing`, armed target `DOCUMENTARIES`, and on release `CL100 3→2 /
  DOCUMENTARIES 1→2` with `day24Group = "DOCUMENTARIES"`, proxy gone, zero leftover classes.

### DEF-030 — spec items delivered alongside the drag layer   ✅ FIXED
- **6-dot grip.** Two bars read as a slider or a pause glyph; the 2×3 dot grid is the shape
  users already associate with dragging. Extended to Subjects-view lecture rows, which are
  now drag sources themselves — moving a lecture between subjects is what that screen is for.
  Gated on the same `_jobIsDraggable` predicate, so a grip never appears on a row that would
  refuse to lift.
- **Text selection policy.** Cards were selectable, so a press-and-move painted the accidental
  blue highlight across a lecture title. Cards are `user-select:none`; holding Ctrl/Cmd adds
  `body.lp-text-select` and hands selection back; the transcript is exempt with
  `user-select:text !important` because it exists to be read and quoted.
- **Full-window OS-drop overlay.** The app advertises "drop a lecture video anywhere", so the
  affordance is now the window itself: a fixed full-bleed veil with an inset orange frame and
  a nudging arrow, deliberately a DIFFERENT visual language from the internal-drag vocabulary
  (a frame, not a ring around one element) because "anywhere works" is the message. Created
  on demand and `position:fixed`, so it costs nothing until a file is over the window.
- **Multi-select deck.** Now that the carried object is ours to draw, a real deck is possible:
  up to three offset faces plus an orange count badge. Offset only, never fanned at an angle —
  a fan implies an order the selection does not have.
- **Audio cues, OFF by default.** Synthesised with WebAudio (two short envelopes) rather than
  shipped as `.wav` assets, so nothing can go missing from a build. Default silence is
  deliberate: this app runs for hours in a library, and a click on every lift is charming for
  ten minutes and intolerable by the afternoon. Persisted under
  `lecturepack.drag.sound`.
- **NOT built, with reasons given:** an "expanding ghost container" that parts cards to show an
  insertion slot (geometry animation — jitters at boundaries, and the insertion bar already
  does the job), and Exports as a drop target (the owner chose to keep the sidebar to Process
  only rather than have a drag write files with no confirmation step).

### DEF-028 — the lecture card was congested, and the drag work made it worse   ✅ FIXED (measured in the running app)
- **Area:** `app/ui/app.js` (`_jobCardHtml`, new `_jobDisplayName`), `app/ui/app.css`
  (`.lp-drag-grip`, `.lp-drag-ghost-card`).
- **Symptom:** reported with a screenshot as "don't you think this UI layout looks too
  congested". A grey unstyled tooltip covered the poster, and the drag grip appeared to sit
  inside the subject badge.
- **Three defects I introduced with DEF-026, all measured rather than guessed:**
  1. **The grip landed inside the subject badge.** Grip at (11,11); `.lp-subject-badge` at
     (11,14) and 159px wide. Moved to the bottom-left of the poster, the only region
     carrying nothing but the video frame. It is a small `--panel` chip now, not bare bars,
     so it stays legible over an arbitrary video frame.
  2. **TWO native tooltips.** One on the card, one on the grip, stacking over the very
     thumbnail they described. Both removed: the status strip names the verb on lift and
     every valid target lights up, which teaches the gesture better than a hover-only
     tooltip ever could. The grip is also revealed on hover/focus instead of at rest.
  3. **`.lp-drag-ghost-card` re-declared `position:relative`,** silently overriding the base
     `position:fixed`. The ghost stayed off-screen only because of its `left` offset while
     still reserving a 172px block in the layout flow for the duration of every drag.
- **Two PRE-EXISTING collisions the measurement exposed** (present before this session, on a
  247px card): the subject badge spanned x 11-170 while the status badge spanned x 155-236 —
  ~15px of overlap, guaranteed to worsen with a longer subject name — and the status badge
  sat underneath the hover menu button at x 176-203.
- **Fix (owner chose the fuller option):** the subject badge moved OFF the poster into the
  card body as a kicker line above the heading. This removes the collision by construction
  instead of by tuning offsets: the poster now carries only status (top-right), the menu (on
  hover) and the grip (bottom-left), and no subject-name length can reintroduce it.
  `selecting`/`chosen` moved above the body build, because the kicker must not be reachable
  while the card's job is to be ticked.
- **The card said its own name three times** — heading, then the source filename (the same
  words plus `.mp4`), then the duration. The filename line is gone; `j.file` survives only
  as a fallback so a card with no `meta` is not left blank.
- **The yt-dlp id is stripped from the DISPLAYED heading only.** `j.name` is untouched
  because rename, search and the drag label all read it, and the full string stays on the
  heading's `title` so nothing becomes unrecoverable.
- **WHY THE OBVIOUS IMPLEMENTATION WAS WRONG.** A shape-based regex cannot do this job. The
  importer rewrites `_` as a space when deriving a display name, so the stored name really
  ends `[ OQbKAx9878]` **with a space** — the first attempt matched `[A-Za-z0-9_-]{8,}` and
  silently did nothing, which the packaged app proved. Loosening the class to allow spaces
  then ate legitimate brackets like `[Lecture Notes]`. The fix anchors on the id the SOURCE
  FILENAME carries: the filename is unmangled, so a real id has no space in it while a
  bracket the user chose does. That is the discriminator, and it has no false positives.
  A name with no matching file keeps its brackets — the safe direction to err.
- **Verified:** all four thumbnail elements measured pairwise in the running app —
  `COLLISIONS: none`, down from two overlapping pairs. Heading renders
  "Heinrich Schliemann The Boogeyman of Archaeology"; body is subject / heading / duration.
  Card height 288 -> 267. The display-name rule is executed in Node over 7 cases including
  the real shipped string, `[Lecture Notes]`, `[2024]`, no-file, and id-only. Suite 1858
  passed / 7 skipped.

### DEF-026 — internal drag "did not work": one gesture existed and every other drop failed SILENTLY   ✅ FIXED (verified on the PACKAGED binary with trusted pointer input)
- **Area:** `app/ui/app.js` (new `LPDrag` registry), `app/ui/app.css` (drag vocabulary).
  Sibling of DEF-025 (external drop) and DEF-023 (drag auto-scroll) — same feature, third
  distinct defect. External file drop was working when this was reported.
- **Symptom (user, on the shipped build):** "drag and drop still doesn't work internally, it
  does work externally." Dragging a lecture card anywhere except the Process target did
  nothing at all — no movement, no message, no refusal.
- **Root cause, part 1 — the cursor lied.** The window-level `dragover` called
  `e.preventDefault()` BEFORE it checked whether the drag was internal. That cancel is what
  makes the whole window accept an external video on any screen, but it also advertised
  every pixel as a valid drop target for an internal lecture drag, while exactly ONE element
  had a drop handler. The user got a droppable cursor everywhere and a result nowhere. A
  promise-then-nothing is indistinguishable from a broken feature.
- **Root cause, part 2 — one gesture, hardcoded.** Internal drag was a single
  lecture-card→Process path with listeners bound to elements. `renderJobs()` and
  `renderQueue()` both rebuild their containers with `innerHTML` on every poll, so
  per-element drag listeners cannot survive; any new surface would have needed its own copy
  of the whole lift/paint/teardown dance.
- **Root cause, part 3 — the dropzone ate the events.** `dz`'s internal-drag guards called
  `stopPropagation()` (aimed at the window handler), which also stopped the event reaching
  any delegated listener. Dragging a lecture across the dropzone went completely dark.
- **Fix.** One delegated registry (`LPDrag`): targets DECLARE themselves with `data-lp-drop`,
  sources with `data-lp-drag`, all five drag events are delegated from `document`. The window
  and dropzone guards now bail out BEFORE cancelling, so anywhere the registry has not
  claimed a target the browser paints its own `no-drop` cursor. Two new gestures on top:
  lecture → subject heading (files it, via the existing `set_jobs_group`), and queue row
  reorder (via the existing `reorder_queue`).
- **The anti-silent-failure rule, now structural.** A persistent bottom status strip is live
  for the whole drag, names the verb and destination, and on a refused or failed release it
  STAYS for 1.2s with the reason. It is also the `aria-live` region, so the sighted and
  screen-reader strings are the same object and cannot drift. Every registry entry is
  required by test to carry a refusal `reason`.
- **A no-op reorder was the same bug in miniature — caught only by executing it.** The
  reorder branch originally cancelled the event and THEN checked whether the drop would
  change anything, so releasing a row onto its own position gave a droppable cursor and did
  nothing. Structural tests passed; a real `DragEvent` in a browser caught it. It now refuses
  BEFORE `preventDefault` and says "already in this position". Pinned by
  `test_a_no_op_reorder_is_refused_with_a_reason_not_silently`, which asserts the ORDER of
  the two statements.
- **Deliberately NOT made draggable:** slides (order is derived from timestamps — a reorder
  gesture would let the user express something the data cannot store), slide keep/reject (a
  checkbox is faster than an aimed drag across 200+ items), and study sources (selection with
  no destination). "Universal" here means the vocabulary is universal, not that everything is
  draggable; a card draggable to nowhere useful is this very bug in a new costume.
- **Accessibility:** both new gestures are accelerators over controls that already shipped
  (queue ↑/↓ buttons and context-menu Move Up/Down; the card Group action and bulk Group
  dialog). `test_drag_never_becomes_the_only_route_to_a_capability` fails if those disappear.
- **Verified:** 1829 passed / 23 skipped. Real `DragEvent`s dispatched in Chromium against
  the actual delegated handlers: valid transfer, wrong-kind refusal (not cancelled, so
  no-drop shows), empty space, valid reorder with insertion bar, no-op refusal, hysteresis
  across a refusal, multi-select lifting every card, and external file drop still cancelled
  window-wide. Computed styles confirmed in BOTH themes. **Not** yet exercised in the
  packaged Qt WebEngine app.

### DEF-027 — a stray blue focus ring boxed the "Setting things up" heading   ✅ FIXED (cause removed, not suppressed)
- **Area:** `app/ui/index.html` (runtime state headings), `app/ui/app.js` (gate focus map),
  `app/ui/app.css` (`:focus-visible` backstop).
- **Symptom:** on the blocking Runtime setup modal, a 2px blue rectangle wrapped the
  `Setting things up` heading and cleared on the next click. It read as a rendering fault.
- **Root cause:** the four state headings carried `tabindex="-1"` and were programmatically
  `.focus()`ed on every state change to steer a screen reader. Chromium counts programmatic
  focus as `:focus-visible`, so the global focus ring painted a box around static text.
- **The focus call bought nothing.** Every state change ALREADY announces into
  `#runtime-live-polite` / `#runtime-live-assertive`. The focus move was pure redundancy — and
  actively hostile beyond the cosmetics: it yanked focus off whatever button a keyboard user
  was on, five times, while the checks ran.
- **Fix.** Focus targets are interactive controls only (`diagnostics` → `btn-runtime-copy`,
  `checklist` → `btn-runtime-done` once green). `checking` and `ready` move focus nowhere —
  they contain nothing focusable and `#app` is `inert` while the gate is open, so no stray Tab
  can escape. `tabindex="-1"` removed from all four headings so one re-added `.focus()` line
  cannot bring the ring back. Backstop for the general class:
  `[data-programmatic-focus]:focus-visible{outline:none}`.
- **Note:** suppressing the outline alone would have treated the symptom and left the
  focus-stealing bug in place. The mechanism was wrong, not just its paint.
- **Verified:** structurally the ring cannot paint (nothing is focused, so `:focus-visible`
  never matches) and the four headings are no longer focusable. Suite green. The allowlist in
  `test_every_overlay_id_has_a_writer_in_app_js_except_the_static_label` grew 2 → 6 with the
  reason recorded, since those headings are now correctly static markup rather than BUG-04
  hardcoded values. **Not** eyeballed in a packaged build.

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

*BUG-07 was un-deferred and fixed on 2026-07-25. Two items deferred 2026-08-15:*

### DEF-015 — recurring cross-lecture concepts record mastery in ONE lecture   ⚪️ DEFERRED (known, accepted for now)
- **Area:** Study / subject scope (`app/ui/app.js`, `buildGroupStudyContent`).
- Not a regression — subject-scope mastery never worked at all before 2.0.3. A concept
  with `coverage: "recurring"` latches to the FIRST matching lecture in `c.job_ids` order,
  so mastery is written and read there only. The subject view is self-consistent (read and
  write share the origin), but the other lectures' own Study screens still show it as New.
- **Fixing it** means fanning the write out to every matching origin. Safe for mastery;
  **do NOT generalise that to delete**, which cascades into flashcards/quiz/guide. Do it
  deliberately, not as a drive-by.

### DEF-016 — "Export PDF" and "Export HTML" are the same operation   ⚪️ DEFERRED (known, accepted for now)
- **Area:** Export (`lecturepack/controllers/job_controller.py:873`).
- The requested `kind` now survives renderer → bridge → sidecar, but `export_now()` takes
  no format and always rebuilds the whole pack. The UI copy ("Rebuilding the study pack to
  refresh the PDF…") is honest about this. A true per-format export is a FEATURE.
- `tests/test_renderer_spike.py` carries a comment so a green test is never misread as
  end-to-end format support.

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
### DEF-025 — EVERY external file drop threw ReferenceError and died silently   ✅ FIXED (reproduced on the shipped binary)
- **Area:** `app/ui/app.js`. Shipped broken in at least 2.0.2 through 2.0.5.
- **Symptom:** dropping a video did nothing. No import, no error, no toast, no visible
  failure of any kind. Reported with a screen recording; the user fell back to Browse.
- **Root cause:** `importDroppedVideo` was declared INSIDE `wire()`, while its only caller
  `importDroppedFiles` is at module scope. Every drop threw
  `ReferenceError: importDroppedVideo is not defined` and the handler died before it ever
  reached the import. Confirmed by running the SHIPPED 2.0.4 installer under CDP and
  reading the renderer console.
- **WHY EVERY EARLIER INVESTIGATION MISSED IT.** The dragenter/dragover/drop handlers, the
  preload's `webUtils.getPathForFile`, the internal-drag machinery and the main-process
  guards are ALL correct and were each verified in turn. The lifecycle was never the
  problem; the very last step was unreachable. Checking that events fire is not the same
  as checking that the work happens.
- **AND THE TEST ACTIVELY HID IT.** `tests/test_renderer_spike.py` asserted
  `"importDroppedVideo" in ui` — a substring check. The name was in the file (as both a
  declaration and a call), so the test passed for months while every drop threw. It now
  asserts the DECLARATION is at module scope (`"\n  function importDroppedVideo("`) and is
  mutation-checked: re-nesting the function fails the test.
- **Fix:** hoisted `importDroppedVideo` and `friendlyImportError` out of `wire()` to module
  scope. Both are pure functions over module state (`importingFile`, `lpBridge`, `toast`,
  `setOnb`, `setImporting`), so nothing else had to move.
- **Verified on a real build with real files:** a browser-level file drag now resolves the
  true native path (`C:\Users\...\demo-lecture.mp4` and a OneDrive path with an `&` in it)
  and creates the job. Internal lecture drag re-verified in the same run: cards
  `draggable=true`, the job-ids MIME payload is set, and the Process target accepts both
  `dragover` and `drop`.
- **THE LESSON:** a substring assertion proves a NAME exists, never that the code runs.
  For anything reachable only at runtime, assert the shape that makes it reachable — or
  drive it for real.

### DEF-023 — a drag could never scroll, so half the library was unreachable   ✅ FIXED (verified live)
- **Area:** `app/ui/app.js` (new `dragScroll` manager).
- **Symptom:** a drag started at the bottom of a long library could not reach the Process
  tab at the top. The pointer is held down, so the wheel is the only other way to move,
  and releasing to scroll ends the drag. There was no auto-scroll code at all.
- **Design:** ONE manager, wired once on `window` in capture, rather than a copy inside
  `#dropzone`, `#jobs-grid` and each Process target. The scroll container is resolved from
  the POINTER (`elementFromPoint` then the nearest scrollable ancestor), so nested
  scrollers work with no extra registration; both axes are handled.
- **THE NON-OBVIOUS PART:** the loop must be `requestAnimationFrame`, not event-driven.
  `dragover` fires only while the pointer MOVES, so a velocity computed from events stalls
  the instant the user holds still at the edge — which is exactly what a user does while
  waiting for the list to come to them.
- **Teardown on every ending:** `drop`, `dragend`, a `dragleave` with no `relatedTarget`,
  `mouseup`, and Escape. A scroll that outlives its drag runs away with the page.
- **Verified live over CDP:** holding still at the top edge scrolled 720px, the bottom
  edge 819px, and the scroll stopped on drop, on leaving the edge, and on Escape.

### DEF-024 — deleting a lecture removed the directory while it was still in use   ✅ FIXED (mutation-checked)
- **Area:** `electron-spike/python-sidecar.py` (`_delete_job` / `_delete_jobs`).
- **Three holes, all user-visible:**
  1. **The id stayed in the QUEUE.** `queue.json` kept a row for a lecture that no longer
     existed and the scheduler could promote it. Nothing ever called `queue.remove()`.
  2. **An ACTIVE lecture was deleted out from under its own workers.** `delete_job` ran
     immediately; the controller still owned the job and its QThread workers were still
     writing. On Windows the removal fails on the open handle, and the worker then writes
     into a directory that is going away.
  3. **Deleting the active lecture emitted NOTHING.** `_emit_job_payloads()` returns early
     when `current_job is None`, and the old code cleared `current_job` *before* calling
     it — so Home, Process and Review all kept rendering the deleted job.
- **The order is the fix:** tombstone → dequeue (before any removal, so the scheduler
  cannot promote a job being deleted) → cancel the controller → **wait** on each worker
  (terminate only if wedged) → detach them → `set_job(None)` → clear `current_job` →
  remove the directory → emit `jobs_changed` + `queue_changed`.
- **Tombstones:** deleted ids are recorded and `_emit` drops any later event carrying one,
  so a stage that was mid-flight when the delete landed cannot resurrect the lecture. The
  deletion events themselves (`job_deleted`/`jobs_changed`/`queue_changed`/`active_job`)
  are explicitly exempt, or the delete would silence its own confirmation.
- **Renderer:** `LP.byJob` is pruned on `jobs_changed`; a deleted lecture's slides and
  transcript used to sit in memory for the rest of the session.
- **Mutation-checked:** making the teardown a no-op fails 10 of the 18 new tests.

### DEF-022 — DEF-019's fix was SILENTLY DELETED one release later   ✅ FIXED (guarded by a test now)
- **Area:** Packaging (`app/packaging/lecturepack.iss`). Caught by the independent
  pre-release review for 2.0.4, not by any test.
- **What happened:** the `[InstallDelete]` section added for 2.0.3 (DEF-019) was gone from
  the working tree by the time 2.0.4 was being cut. An unrelated concurrent edit to the
  same file (fast-compression support) rewrote it from an older copy, and a blanket
  `git add -A` swept that revert into an unrelated commit ("the update dialog showed no
  version and no release notes") whose message never mentions the installer.
- **Why nothing caught it:** 1772 tests were green. No test asserted the section existed,
  and the whole class of bug is invisible to fresh installs — only the A→B upgrade gate
  finds it, and that runs at release time, after the code is already committed.
- **Fixed:** section restored from the v2.0.3 tag, and
  `tests/test_installer_iscc_path.py::test_installer_removes_the_previous_payload_before_installing`
  now asserts it is present, lists all four re-shipped directories, and refuses any target
  outside `{app}`.
- **THE LESSONS.** (1) `git add -A` is not safe when anything else is editing the tree;
  stage deliberately, or read `git diff --stat <lasttag>..HEAD` and account for EVERY file
  before committing. (2) A fix that only exists as a line in a config file, with no test
  asserting it, is one careless edit from being gone — and the ledger entry saying "FIXED"
  will still be there, lying.
- **Also fixed in the same pass** (same review): `scripts/build_electron_release.py` lost
  its `sums = write_sha256sums(...)` call, so the full release build crashed with
  `NameError` after ~10 minutes of compression and never wrote the published
  `SHA256SUMS.txt`; and `package-sidecar.mjs` made PyInstaller's `--clean` opt-in, so the
  OFFICIAL build path was the unclean one and could inherit stale freeze artifacts. Both
  now have tests in `tests/test_release_pipeline_authority.py`.

### DEF-020 — the update dialog showed no version and no release notes   ✅ FIXED (verified live)
- **Area:** `electron-spike/production-main.js` → `app/ui/app.js`.
- **Symptom:** the live 2.0.2 dialog read `v2.0.2 → v`, "No release notes.", and a literal
  `vundefined available`, while the release it offered had 3113 characters of notes.
- **Root cause:** `update_available` and `update_state` were sent as
  `{event, payload: JSON.stringify({...})}`. `electron-bridge.js` `deliver()` strips
  `event` and **re-serializes whatever is left**, so the renderer received
  `{"payload":"{...}"}`. Every field was `undefined`. `update_state` was broken the same
  way, which silently killed every update status message. Every other event puts its
  fields at the top level; these two were the only exceptions.
- **THE LESSON:** the transport re-wraps the message. Do not hand it a pre-serialized
  envelope — put the fields at the top level and let it serialize once.
- **Also:** the updater carries the raw git tag (`v2.0.3`) while the UI prepends its own
  `v`; the version is normalized before it goes on the wire. The renderer no longer
  concatenates a possibly-absent version (that produced `vundefined`) and formats the size
  with `fmtBytes`. Release notes are Markdown rendered as flat bullets, so `_wnNoteLines`
  strips heading/bullet/emphasis markers and drops fenced blocks.
- **Update DECISIONS were never affected** — `parseVersionPart` accepts `^v?` and compares
  semver. Proven, not assumed: a global rollout matrix in `tests/test_electron_updater.py`
  asserts every shipped version (0.9.0-beta.3 → 2.0.2) is offered the current stable, an
  up-to-date user is never offered their own version (the nag loop a lexicographic compare
  would cause, since `"v2.0.3" > "2.0.3"` as strings), updates never go backwards, 2.0.10
  beats 2.0.9, stable users never see a prerelease, and a release with no installer asset
  fails closed.

### DEF-021 — installing an update over the RUNNING app failed silently   ✅ FIXED
- **Area:** `electron-spike/production-main.js` (`installDownloadedUpdate`, `requestQuit`).
- **Symptom / repro:** installing 2.0.3 over a **running** 2.0.2 exits with Inno code 5 and
  installs NOTHING — every 2.0.2-only package was still present afterwards. The user clicks
  "Download and Install", the app closes, and they reopen on the old version having been
  told nothing.
- **Root cause:** the installer was spawned detached and the app quit *afterwards*. Windows
  cannot replace a running `.exe`, and the app plus its sidecar still held
  `resources\LecturePackSidecar` open.
- **PRE-EXISTING, not caused by DEF-019's `[InstallDelete]`** — verified: the 2.0.2
  installer fails identically over a running 2.0.2.
- **Fixed:** the installer is deferred to `requestQuit()` and launched only after
  `stopSession()` has shut the sidecar down, bounded by `INSTALLER_SHUTDOWN_GRACE_MS` so a
  hung shutdown cannot swallow the update, and consumed exactly once so a re-entrant quit
  cannot launch two installers.
- **Severity honesty:** the repro forced the worst case with `/VERYSILENT`. The shipped
  flow shows the Inno wizard, so a human's click latency usually covers the app's exit —
  the failure is real but intermittent, which is why it was never reported.
- **Still not deterministic:** the `.iss` has no `AppMutex`/`CloseApplications`, so Inno
  neither detects nor waits for a running LecturePack. The ordering fix removes the
  guaranteed collision; adding `AppMutex` would remove the residual race.

### DEF-019 — the installer never removed anything, so UPGRADING broke link import   ✅ FIXED (verified by the gate that caught it)
- **Area:** Packaging (`app/packaging/lecturepack.iss`). Found by RELEASING.md step 14
  (`scripts/updater_ab_acceptance.py`) during the 2.0.3 release.
- **Symptom:** a FRESH install of 2.0.3 passed all 12 self-test checks, but installing
  2.0.3 **over** 2.0.2 produced `yt_dlp: false — yt-dlp import failed`, i.e. YouTube/link
  import silently dead for every existing user. Fresh installs were perfectly healthy, so
  no fresh-install test could ever have caught it.
- **Root cause:** `[Files]` copies with `ignoreversion recursesubdirs createallsubdirs`,
  which updates and adds but **never removes**, and there was no `[InstallDelete]` section
  at all. Every file an older build shipped and a newer one does not survived forever. The
  2.0.3 sidecar was frozen from a clean venv built strictly from `requirements-release.txt`,
  so it ships fewer packages than 2.0.2 did; 12 stale packages (Cryptodome, certifi,
  cryptography 49.0.0, websockets, pywin32, yaml, brotli, …) were left behind and broke
  `import yt_dlp`.
- **Fix:** an `[InstallDelete]` section that clears the directories the installer fully
  re-ships (`resources\LecturePackSidecar`, `resources\ui`, `resources\assets`, `locales`)
  before `[Files]` runs. User data lives in `LecturePackData`, never under `{app}`, so
  nothing there is at risk.
- **THE LESSON:** *an upgrade is not an install.* This class of bug is invisible to every
  fresh-install test and to the entire Python suite; only a real A→B run over a previous
  stable finds it. Do not skip step 14 — it earned its "REQUIRED" on this release.
- **Verified:** A→B gate exits 0 — 2.0.2 detects 2.0.3, SHA-256 verified, all 12 checks
  green including `yt_dlp`, 2.0.2's data marker survived, no orphan processes; and a fresh
  install of the SAME fixed installer still passes all 12.

### DEF-017 — subject-scope mastery never round-tripped; write was fixed, read was not   ✅ FIXED (verified live)
- **Area:** Study / subject scope. Found by the **independent pre-release review**, not by
  the author — after the author had already "verified DEF-001 live". Read the next bullet.
- **Symptom:** in Subject scope, setting a concept's mastery appeared to work and then
  snapped straight back to New; the subject progress bar sat at 0% forever.
- **Root cause — a half-fixed defect is still a defect.** DEF-001 corrected the WRITE to
  target `origin_job_id`/`origin_concept_id`, but the READ stayed
  `conceptMastery(c.id)` against `studyV2.progress` — and `studyV2GroupLoad` **never
  assigns `studyV2.progress` at all**, so it held whatever single lecture was loaded last,
  keyed in a different id space. Fixed by carrying each member's progress in
  `group_study.collect_members` and re-keying it onto the group ids
  (`buildGroupStudyProgress`). Safe on both counts: `fingerprint()` keys only on
  `job_id`+`generated_at` so the AI cache is not invalidated, and `build_evidence()` sends
  only `job_id`/`title`/`analysis` so progress never leaves the machine.
- **WHY THE AUTHOR'S OWN LIVE TEST MISSED IT — the trap to remember.** The Study screen
  restores its last scope selection. Clicking "Study Subject" landed on a **single
  lecture**, not "All lectures in this subject", while still looking like subject scope.
  On this profile the group concept ids happened to equal the member ids
  (`concept_1..3`) with one member lecture, so single-lecture behaviour was
  indistinguishable from working group behaviour. **Assert
  `#study-scope-lecture-select.value === 'all'` before believing any subject-scope
  result.** The same trap invalidated the first attempt at the DEF-018 guard test.
- **Verified:** in true group scope, set → persisted → survived leaving and re-entering
  the screen; console clean.

### DEF-018 — concept actions failed silently, and could hit the WRONG concept   ✅ FIXED (verified live)
- **Area:** Study concept actions (`app/ui/app.js`). Also found by the pre-release review.
- **Two defects in one path:**
  1. **A rejected call RESOLVES.** `lpBridge.call(...)` resolves with `{ok:false}` on a
     backend rejection; only transport errors reject. `set_mastery`/`edit`/`delete` used
     `.then(studyV2Load).catch(...)`, so a refusal took the **then** branch: the select
     silently reverted, and a confirmed DELETE did nothing while reporting nothing. Only
     `regenerate` checked `ok`. All five now check it. **`.catch()` is not error handling
     for this bridge.**
  2. **The unresolvable-owner fallback was unsafe.** `studyItemOwner` fell back to
     `{job_id: LP.state.jobId, id: displayedId}`. A group concept id is a free-form model
     string and per-lecture ids are short and sequential (`c7`, `concept_2`), so a
     collision would have set mastery on — or DELETED, with its cascade into
     flashcards/quiz/guide — an unrelated concept in whatever lecture was active, and
     reported success. It now returns `null` in group scope and every caller refuses with
     an explanation. The fallback remains in single-lecture scope, where the displayed id
     IS the stored id.
- **Verified:** with owner attributes stripped to simulate a merged/renamed title, both
  mastery and delete refused with the explanatory toast and the store was byte-identical
  afterwards — 3 concepts, 14 flashcards, 10 quiz items intact.

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
