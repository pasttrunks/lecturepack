# Handoff — LecturePack (guided demo + release hardening)

**Date:** 2026-08-12 03:29
**Written by:** Claude (Opus 5), documenting session 2026-08-12
**Branch:** `sol/polish-integration` · **HEAD:** `a2668e6` (was `a758885` at session start)
**Supersedes:** `docs/HANDOFF_v2.0.1_RELEASE_HARDENING.md` — that document still stands
for the eight guided-demo defects it recorded and for the v2.0.1 hardening work; this
one supersedes its *status claims*, because those eight are now logged in `BUG_LIST.md`
as 🟠 PARTIAL (see §7) and one of them (BUG-40) is proven not to have held.

---

## 1. What this project is

LecturePack turns a lecture recording into a study pack — slides, transcript, flashcards,
quiz — entirely on the user's machine, no account, no upload. It ships as a packaged
Electron app with a Python sidecar (PyInstaller). The shipped UI is **`app/ui/`**
(`index.html` + `app.js` + `app.css`, plain files, no build step) driven by
`app/desktop/bridge.py`. The legacy `lecturepack/ui/` PySide pages are dead code — a bug
"in the UI" always means `app/ui/`. This session was entirely about the **guided demo**:
the first-run walkthrough that is most users' first impression of the product.

## 2. Current state

- Working tree **clean**, five commits ahead of the session's starting point.
- **Nothing pushed, nothing released.** Manual approval still pending.
- A test build with the fixed UI lives at
  `C:\LecturePackScratch\builds\polish\seamfix-20260812\LecturePack-win32-x64\`.
  It is a **copy** of the `guided-demo-fix-20260811` candidate with the three changed
  `app/ui` files swapped in — the UI ships **unpacked** at `resources/ui/`, so no rebuild
  is needed to test renderer changes. The original candidate is untouched.
- A canonical signed release build is **not possible on this machine**: `deno` and
  `lecturepack_study_core` are absent, and `build_electron_release.py` checks for them.

### Commits this session

| Commit | What |
|---|---|
| `c134fdc` | Dim regions overlapped → seam; Study step retargeted |
| `acdb2e4` | Packaged verification record for the above |
| `5c6ec52` | Widened the tour step contract; demo entry point; footer waiting state |
| `3838ad0` | Step preconditions run once on entry; Review card docks (`present:'tip'`) |
| `a2668e6` | Review stacked column height; footer clearance |

## 3. What this session did

### 3.1 Set up the `claude-design` MCP server

Installed from `github.com/marvin-socialista/claude-design-mcp` to
`~/.claude/mcp-servers/claude-design-mcp`, registered at **user scope**. Note: the repo
imports `playwright` but does **not** list it in `package.json` dependencies — the
documented install fails at runtime without `npm install playwright`. It drives real
Chrome, so browser download can be skipped.

Used it three times this session (see §4 for what it got right and wrong). Design project:
*Lecturepack UI Design Discussion*, `9b5fc347-d3c7-4682-a656-86dd89690dbd`.

### 3.2 The seam (BUG-41)

**Symptom:** a hard vertical edge down the window on every tour step; the *highlighted*
control read as dim rather than lit.

**Root cause:** the four dim rects must tile the viewport and did not. `top`/`bottom` each
span the full width and `left` spans only the target's height band — but `right` spanned
the **full viewport height**, so both right-hand corners were painted twice
(.65 over .65 ≈ .878) while the left corners were painted once. The seam always landed at
`left + width` of the target: x≈1130 on Exports (right edge of *Export all*), x≈510 on
Review (right edge of Keep/Reject), x≈1337 on Home (right edge of the dropzone).

**Fix:** `setTourDimRect('tour-dim-right', left + width, top, viewportWidth - left - width, height)`.

**My first diagnosis was wrong** and is recorded in the ledger so nobody repeats it: I read
`#guided-tour-overlay{…background:rgba(8,10,14,.65)}` on `app.css:748` and concluded the
overlay double-dimmed the regions. **Line 749 overrides it to `transparent`.** Two adjacent
rules for the same selector — read the whole cascade before blaming it.

### 3.3 The Study step (BUG-43, then a second cause)

Originally targeted `#demo-study-actions`, which lives inside `<div id="study-legacy"
hidden>` — Study V2 replaced that workspace. The spotlight correctly collapses on
`target.closest('[hidden]')`, so the step rendered with **no dim, no ring, no arrow** while
its card told the user to use an off-screen chat box.

Retargeting to a new `#demo-study-actions-v2` exposed **two more causes** of the
full-width band seen in the packaged app:

1. That element was a **full-width flex row**, so the hole was a stripe, not a box.
   Now `display:inline-flex; align-self:flex-start` — it shrink-wraps its two buttons.
2. Study V2 **persists its last mode** (`studyV2.mode`, restored from `saved.lastMode`)
   and nothing re-measured when the mode was restored, so the spotlight kept the rect of a
   panel that had been replaced. `setStudyV2Mode` now calls `scheduleTourGeometry()`.

### 3.4 The step contract (the systemic fix)

All the demo defects shared one cause: the step table declared only
`screen/target/title/copy/next`, so it could not express "make this visible first",
"don't cover this", "there are two relevant things here", or "this container is
guaranteed shown". Every gap between declaration and reality became a geometry bug at
measure time. `TOUR_PHASES` entries now also carry:

| Field | Meaning |
|---|---|
| `prepare` | precondition run **once on step entry**, before measurement |
| `target` | selector **or array**, whose bounding union becomes the single hole |
| `keepClear` | regions the coach card must not cover |
| `reveals` | hidden containers this step guarantees are shown |
| `present` | `'card'` (default) or `'tip'` — narrow, docked, for dense screens |

### 3.5 The demo entry point

`#glowing-demo-card` said "Use demo video" and called `flyDemoTileToDropzone(startGuidedDemo)`
— it imported the video and **never started the tour**, leaving the tour reachable only
from the far less discoverable "Try the demo lecture" button inside the empty-state panel.
The tile now starts the tour on first run and reverts to a plain import once `tourSeen()`,
so the returning-user "just give me the demo video" path survives without a second
competing button.

### 3.6 Dead Study buttons — a bug I introduced and then fixed

`prepare()` was called at the top of `positionTourSpotlight`, which re-runs on **every rAF,
resize and scroll**. Study's precondition is `setStudyV2Mode('overview')`, so clicking
*Quick Study* or *Continue studying* switched the mode, which rescheduled geometry, which
forced the mode straight back within a frame. The clicks fired; their effect was reverted.
Symptom: the buttons look dead, with no error and no console output, until the tour exits.

`applyTourStepPrecondition()` now runs once per step, keyed on phase. **It is deliberately
not re-armed in `clearTourDim()`** — collapsing is exactly what happens when the student
leaves the overview, so re-arming there rebuilds the loop.

### 3.7 The footer

`friendlyProcessingLabel` collapsed `review ready` onto the label **"Preparing review"**,
and the demo parks at `review_ready`/86% permanently because `auto_export:false`. So the
footer read "Preparing review · 86%" with a frozen bar through Review, Study *and* Exports.

There are really **two** parked states at the same 86% — before the Keep/Reject decision
and after it — so a label fix alone would still be wrong on two of three steps. The label
now resolves from app state (`waitingHandoff()`): **"Review ready · N slides to keep or
reject"**, then **"Ready to export · Study pack not exported yet"**. The bar keeps the true
percentage and changes **material** (static hatch) rather than lying about magnitude.

Works for real jobs, not just the demo: `reviewDecisionTaken()` falls back to "every slide
carries an accepted/rejected state".

### 3.8 Review layout (a2668e6)

Reported as "Keep/Reject clipped by the footer". **Measured first, and the report was
wrong in a useful way** — clearance was exactly 18px at 1920×1009, 1600×900, 1400×820 and
1280×760. What reads as clipping is the spotlight ring's 22px glow bleeding across the
dimmed footer. `#demo-review-actions` now has a 10px bottom margin (28px clearance).

The same sweep found a **worse, unreported, pre-existing** defect: below the 1220px
breakpoint the panels stack, and there `#slide-list` collapsed to **zero height** — the
student was asked to keep or reject slides with no thumbnails on screen. `#slide-list` is
`flex:1` with a 0 basis and the column offered only `max-height:230px`; a max-height does
not make a height definite, so the basis resolved to 0. Changed to `height:230px` → the
list gets 134px at every stacked size. **This affects any user on a window narrower than
1220px, demo or not.**

## 4. Architecture & decisions

### AD-20 stands — the spread-shadow spotlight must not come back (BUG-42)

**The single most important thing in this document.** I implemented, and nearly shipped, a
redesign replacing the four dim rects with one element carrying
`box-shadow: 0 0 0 100vmax` plus geometry transitions. It was cleaner, it passed, and both
Claude Design and I independently reached it.

It is **exactly** what the code did before `0207f08` (2026-08-02). **AD-20** in
`docs/DECISIONS.md` removed it because beta.10 was smooth on the dev machine but
**flickered and felt laggy on a separate clean-install Windows machine**; `--disable-gpu`
changed nothing, so it is not GPU-specific and **will not reproduce here**. The tell was
three separate tests asserting `"transition:" not in spotlight`.

**Standing constraint:** no spread-shadow scrim (`9999px`/`100vmax`), no geometry
transitions on tour elements, no `will-change`, no `filter:drop-shadow` on the arrow.
Guarded by `test_spotlight_uses_static_scrim_and_geometry_without_expensive_effects` and
restated in `test_css_spotlight_is_pointer_transparent_and_uses_a_static_scrim`.

### Rejected alternatives

| Rejected | Evidence that killed it |
|---|---|
| Single-element spread-shadow spotlight | AD-20 — confirmed flicker on non-dev hardware |
| `clip-path`/`mask` full-viewport hole | `app.css:743` documents that QtWebEngine hit-tests a full-viewport mask *through* `pointer-events:none` |
| Union hole for Import as **disjoint** rects | Four-rect tiling expresses exactly one rectangle; disjoint holes need 8+ rects and reintroduce the seam class. Used a **bounding** union instead |
| Targeting the Study V2 **Ask** pane (matches "try the chat box" copy) | It is behind a tab *and* needs a model loaded — it can fail in the same "spotlight on nothing" way. Retargeted to the always-present overview actions and changed the copy instead |
| Footer CTA button ("2 slides to review →") | The footer is entirely non-interactive today; a button there lands outside `tourFocusable()`'s trap and is keyboard-unreachable during the demo |
| Jumping the progress bar to 100% when parked | Export genuinely has not run — it would be a lie. Bar holds the true value, material changes |
| Blanket-exempting conditional containers from the hidden-ancestor test | BUG-34 was a zero-size card inside one of them. Steps declare `reveals:` explicitly instead |

### On the external design review

Claude Design's **systemic** contribution was genuinely good — the widened step contract in
§3.4 is its design, and it is why these fixes fell out instead of piling up. It also caught
a real z-index collision I had missed (`.lp-model-tooltip` at 180 sat above the tour at
170).

**But two of its headline root causes were wrong, and both were checkable in under a
minute.** It claimed the overlay's `background:.65` double-dimmed the regions (line 749
overrides it), and it claimed `[hidden]` loses to the panels' inline `display:flex`
(`app.css:8` is `[hidden]{display:none !important}`, which wins). Had I taken either at
face value I would have shipped a redundant `!important` and left the real causes in place.
**Verify every root-cause claim from a subagent or external tool against the file before
acting on it.**

## 5. Verified

- **Full suite, repeatedly:** `1448 passed, 26 failed, 2 skipped`. **Zero regressions**
  against the `a758885` baseline (27 failed); `test_spotlight_hides_when_target_missing`
  now passes. Method: capture `FAILED` lines, `git stash` the changes, re-run, `comm` the
  two sorted sets. Do this rather than eyeballing a count — an added test changes the
  total and hides a regression.
- **Packaged Electron renderer over CDP** (fixed UI swapped into a copy of the
  `guided-demo-fix-20260811` candidate):
  - Dim regions tile 1920×1009 **exactly** — 1,926,960 dim + 10,320 hole = 1,937,280 =
    vw×vh — with **zero pairwise overlaps**, dim computing to a single `rgba(8,10,14,0.65)`
    rather than the doubled ≈.88. (BUG-41 ✅)
  - Computed z-order: scrim 200 < lifted 210 < ring 220 < arrow 230 < card 240, above the
    model tooltip (180), below the drag ghost (300). (BUG-45 ✅)
  - `--tour-card-x/y` drive the card's computed `left`/`top`; card does not intersect the
    hole.
- **Packaged acceptance** (`scripts/electron_packaged_acceptance.py`) on the fixed build is
  **identical to the baseline candidate**, line for line, with `renderer_failures: []`,
  `bridge_errors: []`, `first_exit_clean: True`.
- **Review layout sweep** across 8 window sizes: clearance 18→28px; stacked `listH` 0→134.
- **Manual, by the user, in the packaged app:** the seam is gone, the Study step lights up,
  the footer reads "Review ready · 86%".

## 6. NOT verified

- **The guided demo end-to-end has never been driven by automation.** A fresh profile lands
  on the first-run Runtime Setup gate, which is green-only by design (bypass buttons were
  deliberately removed) and cannot go green without the Whisper model and ffprobe, which
  are absent here. Packaged acceptance confirms the environment gap: `transcript_generated`
  FAIL on **both** the fixed and the baseline candidate.
- The `present:'tip'` Review card, the `keepClear` placement, the union Import hole and the
  entry-point relabel are verified by **executed geometry and static assertions only** —
  the user has seen earlier builds of the tour but not signed off on these.
- **Nothing tested on a second machine.** Given AD-20, the flicker constraint is precisely
  the thing that does not reproduce on this hardware. A clean-install machine run is the
  only real check that the tour still performs.
- No canonical signed build, no installer, no updater path exercised.

## 7. Known issues / residual risks

- **BUG-33..BUG-40 are 🟠 PARTIAL**, downgraded at the user's instruction on 2026-08-12.
  BUG-40 ("stable four-region dimming") demonstrably did **not** hold — it became BUG-41.
  Do not mark any of them ✅ without a packaged run.
- **26 pre-existing suite failures**, unchanged from baseline: missing `ffprobe`, Whisper
  model, Deno, Study Core, and demo fixtures. Not regressions; not investigated this session.
- `docs/BETA11_RENDERING_HOTFIX_IMPLEMENTATION.md` + AD-20 are load-bearing and easy to
  miss. BUG-42 exists to point at them.
- The `code-review-graph` MCP post-commit hook throws `UnicodeEncodeError` on every commit
  (cp1252 encoding its own Rich panel). Harmless — the graph updates fine — but noisy.
- Two Claude Design recommendations **not** taken, both defensible: demoting
  "Try the demo lecture" to a pointer rather than a second actuator, and a `hint:` field
  giving `#dropzone` a lower-weight dashed treatment instead of the union hole.

## 8. TODO / next steps

1. **★ HIGHEST VALUE — run the guided demo end-to-end on a machine with a complete runtime**
   (Whisper model + ffprobe), and ideally a clean-install machine that is not the dev box,
   which also re-tests AD-20's flicker constraint. This is the only thing standing between
   the five 🟡/🟠 ledger entries and ✅.
2. Confirm the Review thumbnails are visible below 1220px (§3.8) — the one fix here that
   affects users outside the demo.
3. Decide on the two deferred Claude Design recommendations (§7).
4. Re-run the full suite once the fixture/runtime gaps are closed, to see how many of the
   26 are environmental vs real.
5. Only then: canonical signed build → `pre-release-review` → push.

## 9. Skills-folder retrospective

Skills folder found at **`C:\Users\marsh\OneDrive\Desktop\Projects & Technical Docs\Claude share\Claude share`**
— note this is **not** the path in the global `CLAUDE.md`
(`…\Desktop\UB\ECO182\Claude share\Claude share`), which no longer exists. **Update that
path in `~/.claude/CLAUDE.md`.** Found by searching for the folder *name*, which is exactly
the fallback the global instructions describe.

Promoted four entries to `lessons/anti-patterns.md` (93–96) and logged them in
`lessons/CHANGELOG.md`:

- **93** — Check the decision record before "cleaning up" an awkward-looking design; a
  guard test that specific is a scar, not a style preference.
- **94** — Step preconditions run on entry, never inside a per-frame measurement path;
  the symptom is a dead-looking button with no error.
- **95** — `max-height` does not make a height definite; a `flex:1` child against it
  resolves to zero.
- **96** — Measure the reported symptom before fixing it; a scripted viewport sweep over
  CDP answers "is it real, at which sizes, and what else is broken" in one pass.

No playbook defaults were beaten and no rule produced a worse outcome this session. The
project's own session-start rule (read `BUG_LIST.md` before touching a bug-prone area) is
what surfaced AD-20 — it worked exactly as intended.

## 10. How to run / debug

```bash
# Test build with the fixed UI (original candidate untouched)
"C:/LecturePackScratch/builds/polish/seamfix-20260812/LecturePack-win32-x64/LecturePack.exe"
```

**Redeploy renderer changes without rebuilding** — the UI ships unpacked:

```bash
cp app/ui/app.js app/ui/app.css app/ui/index.html \
  "C:/LecturePackScratch/builds/polish/seamfix-20260812/LecturePack-win32-x64/resources/ui/"
```

**Packaged acceptance:**

```bash
python scripts/electron_packaged_acceptance.py --app-dir "<build>/LecturePack-win32-x64" --data-dir "<tmp>/data" --results-dir "<tmp>/results" --demo-video app/assets/demo/demo_lecture.mp4 --timeout-seconds 420
```

**Drive the packaged renderer over CDP** — this is how the geometry above was verified.
Launch with `--remote-debugging-port=9333`, then `chromium.connectOverCDP` (playwright is
at `~/.claude/mcp-servers/claude-design-mcp/node_modules`). Probe scripts from this session:
`verify_tour.mjs`, `measure_review.mjs`, `sweep_review.mjs` in that directory. Use
`Emulation.setDeviceMetricsOverride` to sweep window sizes. **Kill stray `LecturePack`
processes first** — the app is single-instance and a second launch silently fails to
attach, which once made a clean acceptance run look like a regression.

- **Data:** `C:\Users\marsh\LecturePackData` (real profile — the runtime gate is satisfied
  there, so the demo can actually run; a fresh `--data-dir` cannot get past setup here).
- **Regression method:** always diff the sorted `FAILED` set against a stashed baseline.
