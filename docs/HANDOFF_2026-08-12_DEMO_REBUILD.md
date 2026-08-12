# Handoff — LecturePack (demo rebuild, status bar, AI Study waiting state)

**Date:** 2026-08-12 14:51
**Written by:** Claude (Opus 5), documenting session 2026-08-12 (afternoon)
**Branch:** `sol/demo-rebuild` · **HEAD:** `7cda948`
**Based on:** `99729f2` (codex/ai-first-study, final) — rebased, not merged
**Supersedes:** nothing. Companion to `docs/HANDOFF_2026-08-12_GUIDED_DEMO.md`,
which covers the *earlier* session on `sol/polish-integration` (the spotlight-tour
bug hunt). That work is now superseded **in behaviour** by AD-47 below, but its
handoff is still the record of why.

---

## 1. What this project is

LecturePack turns a lecture recording into a study pack — slides, transcript,
flashcards, quiz. Packaged Electron app + Python sidecar. The shipped UI is
`app/ui/` (`index.html` + `app.js` + `app.css`, plain files, **no build step**).
This session rebuilt the first-run demo from scratch, consolidated the two
bottom bars, and made the AI Study waiting state legible.

## 2. Current state

- Working tree **clean**, 4 commits on top of codex's final commit.
- **Nothing pushed.** No release.
- Test build with all changes:
  `C:\LecturePackScratch\builds\demo\rebuild-20260812\LecturePack-win32-x64\`
  (a copy of the earlier candidate with `app/ui` + `app/assets/demo` swapped in).
- Branched from codex's `d611e0f`, later **rebased onto `99729f2`**. Codex's two
  newer commits (gateway deploy, NVIDIA routing) touch `ai-gateway/`,
  `lecturepack/services/`, scripts and docs — **not `app/ui/`** — so the only
  conflict was `docs/DECISIONS.md`, where we had both appended. Resolved by
  keeping codex's AD-46 exactly as it stands (it had removed a Resend reference
  in a later commit; I did not resurrect it) and appending only AD-47.

| Commit | What |
|---|---|
| `ab4b3d0` | Guided demo rebuilt as a self-contained screen (AD-47) |
| `4684270` | Two bottom bars consolidated into one status bar |
| `adc98af` | AI Study waiting state shows the stages the backend already sent |
| `7cda948` | Fix: the queued Study stage left the whole checklist idle |

## 3. What this session did

### 3.1 The guided demo, rebuilt (AD-47) — `ab4b3d0`

The previous session fixed **eight** bugs in the spotlight-tour demo and the
owner's verdict was still "the demo still sucks." That is the signal that the
premise, not the execution, was wrong.

A spotlight tour is a **second renderer for the app's layout**: it must
independently know where everything is, what mode it is in, and what is about to
move. Every one of those eight bugs was that coupling failing, and the class is
unbounded — Study V2 silently broke the tour and nobody noticed until a user
did. **"Must work 100% of the time" and "measures the live UI at runtime" are
incompatible requirements.**

The replacement is a **screen**, not an overlay: `data-screen="demo"`, five
chapters swapped with `[hidden]`. It measures nothing, mutates nothing outside
its own section, and has no scrim, spotlight, anchoring or z-index band.

It shows **pre-baked real output** of the bundled Polar Bears lecture:
`app/assets/demo/demo.data.js` plus real slide PNGs extracted at the timestamps
the detector actually chose. Real output, simply not recomputed. The pipeline
now runs **after** the walkthrough, from an explicit "Process this lecture for
real" button — running it up front needs ffprobe and a Whisper model, takes tens
of seconds, and a failure there reads as the *product* failing on a first
impression.

**The `file://` trap, found only by rendering it.** The first version loaded its
data with `fetch('../assets/demo/demo.json')`. The renderer is loaded via
Electron's `loadFile` — `file://` with web security on — where fetching a
sibling file is **blocked**. It would have degraded to the fallback on *every*
launch, packaged included, and it fails silently. Data now ships as a
`<script>`-loaded global (`window.LP_DEMO_DATA`), which removes the failure mode
rather than handling it.

### 3.2 Two bottom bars → one — `4684270`

`#proc-strip` was a full-width button pinned at `bottom:34px`, directly above
the status footer, showing the **same** running job: same stage name, a second
progress fill at a different width. 68px of stacked chrome that read as broken
because it *was* the same object rendered twice.

The strip is deleted. Its two unique contributions — job identity and a way to
open the job — became a single button inside the footer.

A full-width clickable bar was rejected on three counts: its accessible name
would sweep in `whisper.cpp · CPU AVX2 · ggml-base.en.bin`; the focus ring would
be a full-width rectangle around global chrome; and two-thirds of it is inert
spacer. One button, one tab stop, inset focus ring.

Height is a fixed 34px in **every** state (measured: idle 34, processing 34, no
horizontal overflow). A variable-height fixed footer reflows the main scroll
area, and this bar changes state constantly while processing.

**id remapping** — the renderer was rewired accordingly:

| Old | New | Note |
|---|---|---|
| `#status-label` | `#status-state` | state word only: Idle / Processing / Review ready / Ready to export / Failed |
| `#status-pct` | `#status-detail` | stage + % + ETA, in ONE place |
| `#proc-strip` | `#status-job` | the single button |
| `#proc-strip-name` | `#status-job-name` | |
| `#proc-strip-waiting` | `#status-queued` | strictly `+N queued` |
| `#proc-strip-bar` / `-meta` | *deleted* | folded into `#status-bar` / `#status-detail` |
| `#status-right` | *same* | **device info only** — it used to also carry stage text, which was the in-footer half of the duplication |

### 3.3 AI Study waiting state — `adc98af`, then `7cda948`

The preparing state was one static card on an empty screen and read as frozen.
**The UI was discarding data it already had**: `ai_study_service.py` emits seven
named stages with real percentages, and the renderer put the current one in a
small subtitle and threw the sequence away.

Now the whole sequence renders — complete / running / pending — with the stage
name promoted to the headline, a percentage, and an elapsed clock. **No backend
change was needed**; the data was already flowing through
`generation_metadata`, which also means none of codex's Python was touched.

"Checking public sources" gets the secondary/cyan treatment and an *Optional*
note. It is the only stage that leaves the machine, and that distinction is the
difference between "this app does web lookups" and "this app is doing one right
now" — the question a privacy-minded student is actually asking while waiting.

**Then the owner reported "stuck at 0% for 2 minutes", and it was my bug.**
Before the worker starts, `python-sidecar.py` emits an **eighth** stage,
`stage="Queued for Study AI", progress_percent=1`, which was missing from the
renderer's table. `studyPrepIndex` returned `-1`, every row drew as pending, and
a run that had genuinely started was pixel-identical to a hang.

Fixed twice over, and the second fix is the important one:
1. `Queued for Study AI` added to the table.
2. **An unrecognised stage now renders itself as running** instead of blanking
   the list. A new backend stage must never make a working run look broken —
   which is exactly how this happened.

`tests/test_demo_screen.py::test_study_prep_covers_every_stage_the_backend_emits`
now parses **both** `ai_study_service.py` and `python-sidecar.py` for emitted
stage strings (8 found) and asserts the renderer matches every one, so a stage
added on either side fails the suite.

## 4. Architecture & decisions

**AD-47** was added to `docs/DECISIONS.md` (see §3.1). **AD-20 still governs all
of this**: no spread-shadow scrims, no geometry transitions on tour/chrome
elements, no `will-change`, no `filter:drop-shadow`, no infinite keyframes on
large surfaces. Confirmed flicker on a clean-install Windows machine that does
**not** reproduce on the dev box.

### Rejected alternatives

| Rejected | Evidence |
|---|---|
| Keep fixing the spotlight tour | Eight fixes did not converge; each removed one instance of an unbounded class |
| Demo runs the pipeline live | Needs ffprobe + Whisper, tens of seconds, can fail — and failure reads as the product failing |
| `demo.json` via `fetch()` | Blocked under `file://`; would have silently degraded on every launch, packaged included |
| Full-width clickable status bar | Accessible name would include the engine string; full-width focus ring; mostly inert spacer |
| Variable-height status bar | Reflows the main scroll area on every state change |
| Inventing a spinner for AI Study | Real per-stage progress already existed; and an infinite animation on that surface is the AD-20 failure mode |

### On the external design consults

Four consults this session (demo, status bar, AI waiting state, slide viewer).
The systemic calls were good — the "throw the spotlight away" verdict and the
widened step contract were both correct and are the reason this converged.

**But its root-cause claims were wrong three times out of four, and all three
were checkable in under a minute:**

1. Claimed the overlay's `background:.65` double-dimmed the scrim — line 749
   overrides it to `transparent`.
2. Claimed `[hidden]` loses to the study panels' inline `display:flex` —
   `app.css:8` is `[hidden]{display:none !important}`, which wins.
3. Claimed Grid never worked because `#slide-list` has inline `display:flex` and
   the rule never sets `display:grid` — [app.js:2463](app/ui/app.js:2463) sets
   `list.style.display = 'grid'` at render time.

**Rule for the next session: take the design, verify the diagnosis.** Every one
of those would have produced a plausible-looking fix that left the real cause in
place.

## 5. Verified

- **Demo screen**, real Chromium render: 5 chapters, 5 controls, data loads from
  the global, **zero page errors**. Slide frames visually match the Review
  screenshots exactly.
- **Demo in the packaged app** over CDP: tile reads "Take the 60-second tour",
  click opens the screen, **2 slides / 2 transcript lines load**. This is the
  check that would have caught the `fetch()` bug — it reports 0/0 when data
  fails to load.
- **Status bar**, measured: `#proc-strip` gone (0 in DOM), footer height 34px in
  both idle and processing, no horizontal overflow, no page errors. Rendered in
  processing and review-ready states.
- **AI Study stages**, rendered: 7 rows with correct complete/running/pending.
- **Stage coverage**, asserted in tests: all 8 backend-emitted stage strings
  match the renderer's table.
- **Tests**: zero regressions across the affected files. Remaining failures are
  the 4 codex documents as inherited (`test_tour_completion_card`,
  `test_job_cards_are_not_draggable`,
  `test_tour_spotlight_keeps_minimum_box_after_navigation`,
  `test_d01_zero_jobs_renders_all_first_run_surfaces`) plus
  `test_study_core_info_reports_rust` (Rust module not installed here).

**Baselines were measured from a filesystem copy** at
`C:\LecturePackScratch\baseline-d611e0f`, **not `git stash`** — worktrees share
one `.git`, and codex was working in this repo. Do not use `git stash` for
baselining while another agent is active.

## 6. NOT verified

- **The AI Study stage checklist has never been seen against a live run.** It is
  verified by simulated render and by static stage-string coverage only. A live
  run was started at the end of this session (see §7) and had not produced
  output when the session ended.
- **The full test suite was not run** after the last three commits — only the
  affected files. It was skipped deliberately: two full runs cost ~10 minutes
  and were competing with codex for the machine.
- The demo's **"Process this lecture for real"** hand-off has not been exercised
  end to end (it needs a complete Whisper runtime).
- Nothing tested on a **second machine**. Given AD-20, that is exactly where the
  flicker constraint does or does not hold.

## 7. Known issues / residual risks

- **OPEN QUESTION — is AI Study actually working?** The owner reported it
  sitting at 0% for two minutes. `7cda948` explains why it *looked* dead, but
  not necessarily why it was slow. Facts established: stage strings are
  unchanged by codex's NVIDIA work; `_emit(..., 5)` fires *before* any network
  call, so 0–1% means still queued rather than a slow gateway; and
  `ai_gateway.py` has a **175-second timeout**, which matches the reported
  ~2-minute wait. A live run was in flight at session end — **rerun it.**
- **The slide viewer is unfixed** — see §8. Measured defect: the rail is 250px
  and the grid asks for `minmax(min(100%,128px),1fr)`, so
  `grid-template-columns` resolves to a **single 246px column**. "Grid" has
  never been a grid at this width; the toggle produces two variants of one list.
  Second defect: selection tints the whole panel blue and is styled louder than
  *rejected*, which is the state that actually changes the export.
- The `code-review-graph` post-commit hook throws `UnicodeEncodeError` on every
  commit (cp1252 encoding its own Rich panel). Harmless, noisy.
- The old spotlight-tour code (`positionTourSpotlight`, the four `#tour-dim-*`
  rects, card anchoring, focus trap, `flyDemoTileToDropzone`) is now
  **unreachable but still present**. Left deliberately so its tests keep
  passing; deleting it is a separate, mechanical change.

## 8. TODO / next steps

1. **★ HIGHEST VALUE — rerun the AI Study diagnosis.** Relaunch with
   `--remote-debugging-port=9366`, process a lecture, and watch the stage
   events. This answers both "is the checklist correct against a live run" and
   "is the gateway actually responding." Script: `watch_study.mjs` (§10).
2. **Build the slide viewer redesign.** The consult is complete and in the
   Claude Design chat; its *diagnosis* is wrong (§4) but its design stands:
   delete the Grid/List toggle, rail becomes one list with a density control,
   grid becomes a full-window "All slides" overlay at
   `repeat(auto-fill,minmax(168px,1fr))`, and the state loudness is inverted so
   REJECTED is loudest and SELECTED is a checkbox with no fill.
3. Run the **full suite** once the machine is free.
4. Exercise "Process this lecture for real" on a complete runtime.
5. Delete the dead spotlight-tour code and its tests.
6. Merge `sol/demo-rebuild` into codex's line, then release prep.

## 9. Skills-folder retrospective

Skills folder: `C:\Users\marsh\OneDrive\Desktop\Projects & Technical Docs\Claude share\Claude share`
(the global `CLAUDE.md` path was corrected earlier today, and `templates/` was
added to the startup ritual).

Anti-patterns **93–96** were promoted in the morning session. This session
produced two more candidates, **not yet promoted** — promote them next session:

**PROMOTE TO SKILLS FOLDER — 97.** *A design consult's DIAGNOSIS is a hypothesis;
only its DESIGN is the deliverable.* Across four consults, the systemic
recommendations were right every time and the root-cause claims were wrong three
times out of four — each wrong in a way that would have produced a plausible fix
leaving the real cause in place (an overridden CSS line, an `!important` that
already won, a `display` set at runtime by JS). All three were falsifiable in
under a minute with one grep. Take the design; verify the diagnosis yourself.

**PROMOTE TO SKILLS FOLDER — 98.** *`git stash` is repo-global; never use it to
baseline while another agent works in the same repository.* Worktrees share one
`.git`, including `refs/stash`. Baselining by stashing your own changes is a
standard trick that becomes a collision risk the moment a second agent is
active. Copy the tree to a temp directory and restore files there with
`git show <ref>:<path>` — pure reads, no shared-state writes.

## 10. How to run / debug

```bash
"C:/LecturePackScratch/builds/demo/rebuild-20260812/LecturePack-win32-x64/LecturePack.exe"
```

**Redeploy renderer changes without rebuilding** — the UI ships unpacked:

```bash
cp app/ui/app.js app/ui/app.css app/ui/index.html "C:/LecturePackScratch/builds/demo/rebuild-20260812/LecturePack-win32-x64/resources/ui/"
```

Demo assets live beside it in `resources/assets/demo/` (`demo.data.js`,
`hero.png`, `slide_01.png`, `slide_02.png`) — **copy those too** if they change.

**Drive it over CDP.** Launch with `--remote-debugging-port=9366`, then
`chromium.connectOverCDP` (playwright is at
`~/.claude/mcp-servers/claude-design-mcp/node_modules`). Scripts from this
session live in that same directory: `watch_study.mjs` (drives a real run and
logs every stage transition), `open_demo.mjs`, `bar_check.mjs`,
`prep_check.mjs`, `slides_measure.mjs`, `render_demo.mjs`.

**Kill stray `LecturePack` processes first.** The app is single-instance; a
second launch silently fails to attach, the sidecar never starts, and the
runtime gate stays pending — which looks exactly like a broken demo. This cost
time twice today.

- **Data:** `C:\Users\marsh\LecturePackData` (real profile; the runtime gate is
  satisfied there). A fresh `--data-dir` cannot get past setup on this machine —
  no Whisper model.
- **Regression method:** diff the sorted `FAILED` set against a **filesystem
  copy** baseline, not `git stash` (§5).
