# LecturePack 0.9.0-beta.15 (dist build) — Frustrated-Student UX Audit, ROUND 2

**Date:** 2026-08-05 (second independent pass, same day as Round 1)
**Target:** `dist\LecturePack-win32-x64\LecturePack.exe` (unpacked production candidate)
**Build under test:** 0.9.0-beta.15 · Electron 43.2.0 · Chrome/150 · branch `deepseek/beta15-pc-polish`
**Method:** Live launch on a **brand-new isolated `--data-dir` / `--results`** (true first run), Chrome DevTools Protocol (CDP) DOM inspection + synthetic clicks/keys, window-resize emulation, paste-link edge-case probing, and full production JSONL log analysis. Renderer crash site confirmed by reading `resources\ui\app.js` (read-only).
**Persona:** A frustrated student who just wants to turn a lecture into a study pack and has **zero patience** for dead buttons, scary error text, stuck progress bars, or status readouts that contradict each other.

> **Companion documents:** `ELECTRON_DIST_FRUSTRATED_STUDENT_AUDIT.md` (Round 1) and `ELECTRON_BETA15_FRUSTRATED_STUDENT_AUDIT.md` (portable zip). Round 1 concluded "almost every P0 is fixed; remaining issues cluster around the guided-demo/tour state machine." **Round 2 re-tested on a clean first run and pushed harder on invalid-state interactions** — mashing real buttons with no lecture loaded, feeding the link importer garbage, and resizing the window. That pressure exposed a **new class of defects Round 1 did not touch: the app is polished on the happy path but throws raw errors — and in one place an uncaught renderer crash — the moment a student clicks a real control in an invalid state.**

---

## 1. Executive summary

The happy path is genuinely good and **fully works end-to-end**: first-run renders the empty state + glowing demo card, the guided demo runs the real pipeline (2 slides + transcript + study workspace + exports), paste-a-link validates input and probes real URLs, and the production log shows a clean `bootstrap_complete → job_completed → export_done` arc with **zero errors on the happy path**.

But a frustrated student does not stay on the happy path. They click **Export** before they've loaded anything. They hit **Keep/Reject** on an empty Review screen. They paste a **broken link**. They mash **Esc**. And that's where this build bleeds:

- **Clicking Review Keep/Reject with no lecture loaded throws an uncaught `TypeError`** in the renderer (`app.js:4482/4495`) — a real crash, not a handled error. (N-1)
- **Every real control used with no job loaded spits a raw technical error toast** at the student: `Error invoking remote method 'lecturepack-production:command': Error: RuntimeError: no job is loaded`. This is the exact opposite of the friendly `FEATURE_UNAVAILABLE` pattern Round 1 praised. (N-2)
- **"Load sample jobs" — the most prominent recovery button on the empty first-run screen — is completely dead** on a fresh install. (N-3)
- **A failed no-job export leaves a phantom "Exporting… 3 of 5 · rendering slides PDF" bar stuck on screen forever.** (N-4)
- **The status readouts never reach a terminal state.** After the job is 100% done (card says **COMPLETE**), the sidebar still says **"Processing - 86%"** and the status bar still says **"Detecting slides"** — *forever*, even after a 12-second wait and a full tour walkthrough. (F-3, confirmed stuck)

**Verdict:** *The engine is real and the onboarding is finally visible, but the build is only "happy-path hardened." One more pass is needed to harden the **invalid-state** paths — guard the null derefs, translate raw errors into friendly messages, and make the status readouts actually settle — before this is safe to hand to students unattended.* The fixes are small and well-understood; this is polish, not reconstruction.

---

## 2. Test environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| App | LecturePack 0.9.0-beta.15 (`dist\LecturePack-win32-x64`) |
| Launch args | `--results=C:\LPFrustratedR2\results --data-dir=C:\LPFrustratedR2\data --remote-debugging-port=9222` |
| Data dir | **Fresh / empty** (true first run — Round 1 reused a populated dir) |
| Window | 1360×860 default (viewport 1344×821, DPR 1); also emulated **760×820** for responsiveness |
| Runtime | Chrome/150, UA `LecturePack/0.9.0-beta.15`, Electron 43.2.0 |
| Backend | whisper.cpp · CPU AVX2 · ggml-base.en.bin (bundled) |
| Demo asset | Polar Bears 10s Demo (bundled) |
| Log | `production-2026-08-05T18-23-05-602Z.jsonl` — **301 lines** |
| Log event mix | `job_completed` ×1, `export_done` ×2, `bootstrap_complete` ×1 (happy path ✅) · `error` ×16, renderer `console` L3 ×2 (all from invalid-state clicks ⚠️) |

---

## 3. Confirmed FIXED / IMPROVED since Round 1

| Item | Round 1 status | Round 2 finding |
|---|---|---|
| **F-1 — Guided tour dead-end** | Tour stuck at "DEMO · IMPORT / Add demo to continue" pointing at a deleted asset | ✅ **Largely fixed.** The tour now advances cleanly: `IMPORT → PROCESSING ("Watch real processing") → REVIEW ("Make one review choice") → STUDY ("Ask about the lecture") → EXPORTS ("See export options") → closes`. Clicking **Keep** correctly advances REVIEW→STUDY. It no longer dead-ends. **Residual issues remain** — see N-7, N-8, and §6 note. |
| **F-7 — Focus mode unconfirmed** | No DOM change; possibly native behavior CDP can't see | ⛔ **Confirmed dead.** Clicking Focus produced **no** class/attribute/window-size change and no perceptible effect. It's a no-op button. See N-10. |
| **F-8 — "Load sample jobs" untestable** | Couldn't test (a job already existed) | ⛔ **Confirmed dead on a fresh dir.** jobsCount stays `0`, no toast, no change. See N-3. |
| **F-2 — "Group lecture" modal stacking** | Modal appeared uninvited over the tour | ⚪ **Not reproduced** this session. The modal never appeared uninvited across the full demo + tour + navigation. Likely trigger-dependent; keep the Round 1 fix (overlay manager + suppress during demo) but this run didn't re-trigger it. |

---

## 4. NEW defects (most severe first)

### N-1 — **P0 / HIGH** — Uncaught renderer crash: Review Keep/Reject with no lecture loaded
**Evidence (production log, 2 uncaught exceptions):**
```
event:"console", level:3, "Uncaught TypeError: Cannot set properties of undefined (setting 'state')", line:4482, ui/app.js
event:"console", level:3, "Uncaught TypeError: Cannot set properties of undefined (setting 'state')", line:4495, ui/app.js
```
**Root cause (read from `resources\ui\app.js`, read-only):**
```js
$('btn-keep').addEventListener('click', function () {
  var s = LP.data.slides[LP.state.viewingSlide];
  s.state = 'accepted';            // ← 4482: s is undefined when no job/slides
  ...
});
$('btn-reject').addEventListener('click', function () {
  var s = LP.data.slides[LP.state.viewingSlide];
  s.state = 'rejected'; s.sel = false;   // ← 4495: same null deref
```
With no job loaded, `LP.data.slides` is empty, so `s` is `undefined` and `s.state = …` throws. **The irony:** the *advance* logic three lines below is carefully guarded against empty decks ("Guarded so a 1-slide deck (or an empty one) cannot divide by zero"), but the null deref directly above it is not.

**Why it hurts:** This is a genuine crash, not a handled error. An uncaught exception can leave the UI in a partially-updated state and is exactly the kind of thing that makes a student think "this app is broken." It's also the easiest class of bug to ship past QA because it only fires off the happy path.

**Fix (P0, trivial):** Null-guard both handlers and disable the controls when there's nothing to judge:
```js
var s = LP.data.slides[LP.state.viewingSlide];
if (!s) return;               // no slide selected / no job loaded
```
Better: set `btn-keep`/`btn-reject`/`btn-prev-slide`/`btn-next-slide`/`btn-save-corrections`/`btn-repair` to `disabled` whenever `LP.data.slides.length === 0`. Add a global `window.onerror`/`unhandledrejection` handler that logs and shows a friendly toast instead of letting exceptions surface raw.

---

### N-2 — **P1 / HIGH** — Raw error toasts leak to students on invalid-state clicks
**Evidence (CDP toasts, no job loaded):**
| Button clicked | Toast shown to the student |
|---|---|
| Export PDF / Export HTML / Export all | `Error invoking remote method 'lecturepack-production:command': Error: RuntimeError: no job is loaded` |
| Process → Pause / Cancel | `RuntimeError: no job is loaded` |
| Review → Keep / Reject / Save corrections | `RuntimeError: no job is loaded` |
| Review → Repair | `Error invoking remote method 'lecturepack-production:command': Error: Sidecar command failed: repair_selection` |

**What the student sees:** A big toast full of jargon — "invoking remote method," "lecturepack-production:command," "RuntimeError." Screenshot: `audit_r2_shots/04_exports_no_lecture.png`.

**Why it hurts:** Round 1 (correctly) praised the new `FEATURE_UNAVAILABLE` pattern for making *deferred* features fail gracefully. But that pattern only covers *not-yet-built* features. These are **real, built features** clicked in an *invalid state* — and they bypass the friendly-message layer entirely, surfacing the raw IPC rejection string. The result is worse than a dead button: it's a button that scolds you in engineer-speak.

**Fix (P1):** Two layers. (1) **Prevent:** disable Export/Process/Review controls when `jobsCount === 0` / no active job (greyed + tooltip "Load a lecture first"). (2) **Catch:** route these rejections through the same human-readable mapper used for `FEATURE_UNAVAILABLE`, so `no job is loaded` → "Load a lecture first — there's nothing to export yet." Never render the raw `Error invoking remote method …` string to the UI.

---

### N-3 — **P1 / HIGH** — "Load sample jobs" is a dead button on a fresh install
**Evidence (CDP, fresh `--data-dir`):**
```
loadJobsBefore: { exists:true, visible:true, text:"Load sample jobs" }
[click]
loadJobsAfter:  { jobsCount:"0", cardCount:0, cards:[] }   // nothing happened
reconfirm (4s wait): { before:"0", after:"0", changed:false, toasts:[], overlays:[] }
```
**What the student sees:** On the empty first-run screen, under the 3-step walkthrough, there's a "Load sample jobs" button — the obvious thing to click when you don't have a lecture handy. They click it. **Nothing.** No toast, no spinner, no jobs. It looks and feels broken.

**Why it hurts:** This is the *primary recovery affordance* for a student who has no video yet. Round 1 flagged it as "untestable" (F-8); on a clean first run it's simply **dead**. A dead button on the very first screen is a top rage-quit trigger.

**Fix (P1):** Either (a) wire it to actually seed 2–3 short sample jobs (ideal — see Optional add-on #5 in Round 1), or (b) if it's not implemented, route it through `FEATURE_UNAVAILABLE` ("Sample lectures aren't bundled in this build yet — try the guided demo instead") or hide it. A button that does literally nothing is the worst of the three options.

---

### N-4 — **P1 / MEDIUM** — Phantom stuck "Exporting… 3 of 5" progress bar after a failed no-job export
**Evidence (screenshot `audit_r2_shots/04_exports_no_lecture.png`):** After clicking Export PDF/HTML/all with no job, the export panel shows a live progress bar: **"Exporting… 3 of 5 · rendering slides PDF"** — even though the underlying command immediately errored (`no job is loaded`) and nothing is actually exporting.

**Why it hurts:** The student clicks Export, gets a scary error toast *and* a progress bar that starts moving and then **never finishes**. "Is it still working? Should I wait?" — the two worst feelings to combine. The progress UI entered the "exporting" state but never got the memo that the export failed.

**Fix (P1):** On export error, reset the export-progress widget to its idle/empty state (or show a clear "Export failed — load a lecture first" terminal state). The progress bar should only ever reflect a real, in-flight export.

---

### N-5 — **P2 / MEDIUM** — Stale error toasts linger across screens and don't auto-dismiss
**Evidence (CDP):** Minutes after the no-job button mashing, while probing the **paste-link** dialog (a totally unrelated task), the toast list still contained `RuntimeError: no job is loaded` alongside the link-validation message. Toasts are not auto-dismissing and are not cleared on navigation.

**Why it hurts:** A stale error from five minutes ago floating over a new task makes the app feel haunted — "why is it still mad at me?" It also stacks with new toasts, compounding the noise.

**Fix (P2):** Auto-dismiss toasts after ~4–5s, cap the visible stack, and clear transient error toasts on screen change. Reserve persistent toasts for genuinely persistent conditions.

---

### N-6 — **P2 / MEDIUM** — Raw yt-dlp errors leak to the UI on bad links
**Evidence (CDP + screenshot `audit_r2_shots/12_paste_dead_url.png`):** Pasting an unreachable URL and clicking **Check link** renders, in red, directly under the input:
```
[generic] video: Unable to download webpage: [Errno 11001] getaddrinfo failed
(caused by TransportError('[Errno 11001] getaddrinfo failed'))
```
**Contrast (what's good):** Garbage (`asdf not a url`) and empty input both produce a **friendly inline** message — "Enter a full http(s) link." So the validation layer exists and works; it just doesn't catch *downstream* yt-dlp failures.

**Why it hurts:** "getaddrinfo failed / TransportError / Errno 11001" is meaningless to a student. They don't know if the link is bad, their Wi-Fi is down, or the app is broken.

**Fix (P2):** Map common yt-dlp stderr patterns to friendly copy: DNS/`getaddrinfo` → "We couldn't reach that link — check the URL and your internet connection."; `Unsupported URL` → "That site isn't supported for link import — try a direct video file or YouTube link."; `Private video`/`Sign in` → "That video needs a sign-in, so it can't be imported." Keep the raw error behind an expandable "details" for power users.

---

### N-7 — **P2 / MEDIUM** — Esc does NOT dismiss the guided tour (but does dismiss modals)
**Evidence (CDP):** With the tour overlay visible, dispatching `Escape` left it visible (`escDismisses:false`). The same `Escape` **did** close the paste-link modal (`escCloses:true` in stage 2). Behavior is **inconsistent** across overlay types.

**Why it hurts:** Frustrated students mash Esc to make popups go away. When the tour ignores Esc, the student feels trapped in a forced walkthrough. Inconsistency (works here, not there) is its own trust-eroder.

**Fix (P2):** Make Esc dismiss the tour exactly like the modals (ideally with a one-time "Leave the tour? You can restart it from Home" confirm if mid-step). Part of the single overlay-manager recommendation from Round 1 (F-2/F-5).

---

### N-8 — **P3 / LOW** — Tour spotlight orphans when the student navigates off-script
**Evidence (screenshot `audit_r2_shots/08_study_with_job.png`):** While the tour sat at "DEMO · REVIEW / Make one review choice," navigating to the **Study** screen left the tour's orange spotlight box pointing at **empty space** (bottom-left, where Keep *had* been on the Review screen), and the tour kept nagging "Make one review choice" instead of adapting to where the student actually went.

**Why it hurts:** A highlight ring around nothing looks glitchy, and a tour that scolds you for exploring is the opposite of welcoming.

**Fix (P3):** Hide the spotlight when its target isn't mounted/visible, and make the tour reactive — if the student manually navigates to the *next* logical screen, advance the tour to match rather than insisting on the scripted step.

---

### N-9 — **P3 / LOW** — Study assistant leaks placeholder Q&A when no lecture is loaded
**Evidence (CDP, fresh first run, 0 jobs):** The Study screen's assistant showed a sample conversation — *"How did they align it to north without a compass? They watched a star rise and set, then bisected the angle… The transcript covers this at 01:12."* — while the header read **"0 topics · 0 slides · 0 bookmarks"** and the overview said "A study overview will appear here after your lecture is ready."

**Good news:** With a real job loaded, the placeholder is correctly replaced by real content (`hasPyramidPlaceholder:false`, real polar-bear transcript). So this is **specifically an empty-state leak**.

**Why it hurts:** A student who hasn't loaded anything sees a random Q&A about pyramids and thinks "whose lecture is this? Is this mine?" Placeholder content in a live empty state reads as a bug.

**Fix (P3):** When there's no active job, render a neutral assistant empty state ("Ask about your lecture once it's ready") instead of the demo conversation. Keep the demo Q&A strictly behind the guided demo.

---

### N-10 — **P3 / LOW** — Focus mode is a confirmed no-op
**Evidence (CDP):** Clicking `btn-focus` produced **no** change to `body.className`, `documentElement.className`, or window inner size; the button label stayed "Focus." (Upgrades Round 1's F-7 from "unconfirmed" to **confirmed dead**.)

**Fix (P3):** Implement Focus (hide chrome / enter a distraction-free mode) or hide the button / route it through `FEATURE_UNAVAILABLE` like the other deferred controls. A no-op toggle is worse than none.

---

### N-11 — **P3 / LOW** — Keyboard shortcuts not wired
**Evidence (CDP):** `Ctrl+O` opened nothing (`openedSomething:false`). Round 1's optional add-on #6 (shortcuts + Esc-to-close) is only half-done: Esc-to-close works for modals (✅) but no app shortcuts are bound.

**Fix (P3):** Wire a small set (`Ctrl/Cmd+O` import, `Ctrl/Cmd+E` export, `Esc` close-all) and surface them in a `?` / shortcuts overlay — or don't advertise them until they exist.

---

### N-12 — **INFO** — Minor narrow-width cosmetic clip
**Evidence (screenshot `audit_r2_shots/13_narrow_760.png`):** At 760px the layout holds up well — **no horizontal overflow** (`overflowX:false`, no overflowing elements) — but the "Browse for video" button text clips slightly at the drop-card edge. Cosmetic only.

**Fix (P3):** Allow the drop-card CTA row to wrap, or reduce button padding at narrow widths.

---

## 5. Verified STILL PRESENT from Round 1

### F-3 — **P1 / HIGH** — Status readouts never settle (confirmed *stuck*, upgraded severity)
**Evidence (CDP, captured repeatedly — after completion, after a 12s wait, and after a full tour walkthrough):**
```
Job card (Home):        "COMPLETE"                      ← correct
status-label:           "IDLE"
status-right:           "Detecting slides"              ← stale, never resolves
side-job-status:        "Processing - 86%"              ← stale, stuck at 86% forever
```
Screenshots: `07_demo_after_complete.png`, `08_study_with_job.png`, `13_narrow_760.png` (all show card=COMPLETE vs sidebar=Processing-86% vs status=Detecting slides simultaneously).

**Why it's worse than Round 1 described:** Round 1 called this "disagrees with itself." Round 2 confirms it **never reaches a terminal state** — the sidebar and status-right are frozen mid-pipeline (`86%`, `Detecting slides`) indefinitely, even though the job is fully done (2 slides, transcript, study, exports all work). The one number a student watches during a long transcription is permanently untrustworthy.

**Fix (P1):** Drive all readouts from one job-state reducer. On `job_completed`, force `status-right` → "Ready" and `side-job-status` → "Complete." Never rest on "Processing - 86%" or "Detecting slides."

### F-4 — **P1 / MEDIUM** — Clicking a recent-job card doesn't open the lecture
**Evidence (CDP):** Clicking the `demo-lecture` card kept `visibleScreens:["home"]` (`navigates:false`). The job loads into the sidebar but the main view doesn't move.

**Fix (P1):** On job-card click, navigate to the most useful screen for that job's state (Review/Study if complete, Process if running).

---

## 6. A note on the tour's new ending (F-1 residual)

The tour now *completes* (good), but the ending is a letdown. The final EXPORTS step reads: *"See export options — Exporting unlocks for your own processed lecture. This temporary demo only shows where those options live."* Then it closes. There's **no "🎉 Your first study pack is ready" moment**, and the framing ("this temporary demo only shows where those options live") tells the student they can't actually keep what they just made. Meanwhile the demo card on Home insists **"Demo ended and its temporary files were removed"** — even while the student is actively reviewing 2 slides, reading the transcript, and opening the study workspace from that same "removed" demo. The message and reality contradict.

**Fix:** End the tour on a celebration with two CTAs — **"Open my study pack"** and **"Drop my own lecture"** — and reconcile the demo-card copy with the fact that the demo's outputs are still fully explorable. (This is exactly Round 1's Optional add-on #1; still unimplemented.)

---

## 7. What works really well (keep all of this)

- **First-run home screen is excellent.** "LOCAL · PRIVATE · NO ACCOUNT," a clear tagline, glowing demo card, 3-step walkthrough, Paste/Browse affordances, and a "Load sample jobs" option. Compelling first impression. (`01_first_run.png`)
- **The guided demo is a killer onboarding feature** — a 10-second bundled lecture that runs the *real* pipeline and now *completes* its tour. Just needs the celebration ending (§6).
- **Paste-a-link input validation is friendly** for garbage/empty input ("Enter a full http(s) link."), and real URLs probe with title/duration/channel. Only the downstream yt-dlp errors leak (N-6).
- **Smart Study upsell is honest and helpful** — Lightweight ~1.4 GB vs Balanced ~2.5 GB with a RAM-based recommendation and a clear "Continue with Built-in Study" escape. (`08_study_with_job.png`)
- **Study / Review / Transcript / Exports all work with a real job** — real transcript segments, 2 accepted slides, working export buttons, study stats. (`07`, `08`)
- **Responsive at 760px** — no horizontal overflow; sidebar collapses cleanly. (`13_narrow_760.png`)
- **Esc closes modals** consistently (just not the tour — N-7).
- **Clean happy-path log** — `bootstrap_complete → job_completed → export_done`, zero errors until invalid-state mashing.
- **Dark theme default + working theme toggle**, storage widget, and the privacy footer are nice trust-builders.

---

## 8. Recommended fixes (priority order)

| Priority | ID | Fix | Effort |
|---|---|---|---|
| **P0** | N-1 | Null-guard Review Keep/Reject (`if (!s) return;`) + disable review controls when `slides.length===0`; add a global error handler | **Trivial** |
| **P1** | N-2 | Disable Export/Process/Review controls with no job; route invalid-state rejections through the friendly-message mapper (never show raw IPC strings) | Small |
| **P1** | N-3 | Wire "Load sample jobs" to seed samples, or `FEATURE_UNAVAILABLE`/hide it | Small |
| **P1** | N-4 | Reset/clear the export-progress widget on export error | Small |
| **P1** | F-3 | Single source of truth for status; settle to "Ready"/"Complete" on `job_completed` | Small |
| **P1** | F-4 | Job-card click navigates to the appropriate screen | Small |
| **P2** | N-5 | Auto-dismiss toasts (~4–5s), cap stack, clear on navigation | Small |
| **P2** | N-6 | Map yt-dlp stderr to friendly messages (raw behind "details") | Small |
| **P2** | N-7 | Esc dismisses the tour (consistent with modals); part of the overlay manager | Small |
| **P2** | §6 | Tour completion celebration + reconcile "files removed" copy | Medium |
| **P3** | N-8 | Hide orphaned spotlight; make tour reactive to manual nav | Medium |
| **P3** | N-9 | Neutral Study-assistant empty state when no job | Trivial |
| **P3** | N-10 | Implement or hide Focus mode | Trivial |
| **P3** | N-11 | Wire or stop advertising keyboard shortcuts | Trivial |
| **P3** | N-12 | Fix narrow-width "Browse for video" clip | Trivial |

**The big theme:** Round 1's fixes hardened the *happy path* and the *deferred-feature* paths. Round 2 shows the **invalid-state paths** are the remaining soft spot. The unifying fix is a **guard-and-translate layer**: (1) disable controls that aren't valid in the current state, and (2) translate *every* backend/IPC rejection into friendly copy before it reaches a toast. That one pattern clears N-1, N-2, N-4, N-6, and most of the student-facing scariness in a single stroke.

---

## 9. Optional add-ons (high value for students)

1. **Demo completion celebration** (still top of the list). Turn the tour's end into "Your first study pack is ready 🎉" with **"Open my study pack"** / **"Drop my own lecture."** Converts the current anticlimax into the best moment in the app.
2. **A real sample-lecture library.** Make "Load sample jobs" seed 2–3 short lectures in different subjects so students can explore Review/Study/Export without hunting for their own video. (Fixes N-3 the *good* way.)
3. **Processing-time estimate** before starting a real lecture ("~X min for a Y-minute lecture on this machine").
4. **Background/tray progress** so a student can minimize during a long transcription.
5. **Friendly error copy deck.** A single `errors.json` mapping every backend/IPC/yt-dlp error to student-friendly text + a "details" expander. Pays off across N-2/N-4/N-6.
6. **Keyboard shortcuts + a `?` overlay**, with universal Esc-to-close (modals *and* tour).
7. **Export destination picker** (choose where the Study Pack lands).
8. **"What happens to my data?"** one-liner promoted to the home screen ("Your recordings never leave this computer").

---

## 10. Test artifacts

- **Audit report (this file):** `deepseek/ELECTRON_DIST_FRUSTRATED_STUDENT_AUDIT_R2.md`
- **Screenshots:** `deepseek/audit_r2_shots/` — `01_first_run` · `02_after_load_sample_jobs` · `03_nav_screens` · `04_exports_no_lecture` (raw error toast + phantom "Exporting… 3 of 5") · `05_focus_mode` · `06_demo_tour_start` · `07_demo_after_complete` (F-3 contradiction) · `08_study_with_job` (orphaned tour spotlight) · `09_tour_after_keep` · `10_tour_final` · `11_paste_garbage` · `12_paste_dead_url` (raw yt-dlp error) · `13_narrow_760`
- **CDP harness:** `lp_cdp_helpers.js` (Desktop)
- **Stage scripts:** `lp_r2_stage1.js` … `lp_r2_stage5.js` (Desktop)
- **Raw results:** `lp_r2_stage1_results.json` … `lp_r2_stage5_results.json` (Desktop)
- **Production log:** `C:\LPFrustratedR2\results\production-2026-08-05T18-23-05-602Z.jsonl` (301 lines)
- **Crash site (read-only):** `resources\ui\app.js:4480–4495`
- **Job data + exports:** `C:\LPFrustratedR2\data\jobs\…`

---

## 11. Verdict

**The engine is real, the onboarding is finally visible, and the happy path works end-to-end.** Round 1's P0s are fixed, and the guided tour now completes instead of dead-ending. But Round 2's harder, more adversarial poking reveals that **this build is only happy-path hardened.** The moment a frustrated student clicks a real control in an invalid state — Export with no lecture, Keep/Reject on an empty Review screen, a broken link, Esc on the tour — the app responds with raw engineer-speak errors, a stuck progress bar, a dead "Load sample jobs" button, and in one place an **uncaught renderer crash** (`app.js:4482/4495`).

None of this is hard to fix, and most of it collapses into one pattern: **guard the invalid state (disable the control) and translate every backend rejection into friendly copy.** Do that, settle the status readouts (F-3), and give the tour a real ending — and this is ready for an unattended student beta. The foundation is solid; what's left is a focused invalid-state hardening pass, not reconstruction.
