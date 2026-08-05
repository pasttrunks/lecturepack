# LecturePack 0.9.0-beta.15 (dist build) — Frustrated-Student UX Audit

**Date:** 2026-08-05
**Target:** `dist\LecturePack-win32-x64\LecturePack.exe` (the unpacked production candidate)
**Build under test:** 0.9.0-beta.15, Electron/Chrome 150, branch `deepseek/beta15-pc-polish`
**Method:** Live launch with isolated `--results` / `--data-dir`, Chrome DevTools Protocol (CDP) DOM inspection + synthetic clicks, production JSONL log analysis, and source review of `production-main.js` and `electron-bridge.js`.
**Persona:** A frustrated student who just wants to turn a lecture recording into a study pack and has zero patience for dead buttons, stuck overlays, or status text that contradicts itself.

> **Companion document:** `ELECTRON_BETA15_FRUSTRATED_STUDENT_AUDIT.md` audited the earlier *portable zip* (Beta 15). This audit re-tests the **current dist build** on the same persona journey. The headline: **almost every P0 from the portable audit is now fixed.** The remaining problems are concentrated in one area — the guided-demo/tour state machine and overlay stacking.

---

## 1. Executive summary

This build is **dramatically better** than the portable Beta 15 that was audited yesterday. The first-run experience is no longer a dead end:

- The **empty state and the guided-demo card both render** on first launch.
- The **"Use demo video" card actually works** — it imports the bundled Polar Bears demo, runs the real pipeline, and produces slides + transcript + 13 export files.
- **"Paste a link" actually works** — it opens a real dialog, probes the URL with the packaged yt-dlp, and resolved a real YouTube link to *"Rick Astley – Never Gonna Give You Up (4K Remaster) · 3:33 · Rick Astley"* with a working **Download** button.
- The **Electron menu bar is hidden**, the **version is correct (0.9.0-beta.15)**, and every settings button that used to hang now returns a clear, honest message.
- **335 production log lines, zero errors/warnings.** Cold boot → sidecar ready → process → export is clean.

But a frustrated student who clicks the demo will still hit **one genuinely bad dead end**: the **guided tour gets stuck** telling them to "Add the demo video to continue" *after the demo has already run and its temporary files were deleted*. On top of that, a **"Group lecture" modal can appear unexpectedly** and stack over the tour, and the **status bar disagrees with itself** about whether the app is idle or processing.

**Verdict:** *Functionally ready for a supervised student beta; the guided-demo exit path and overlay stacking need one more polish pass before it's safe to hand to students unattended.* The engine is real and works end-to-end. The remaining issues are UX-state bugs, not engine bugs.

---

## 2. Test environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| App | LecturePack 0.9.0-beta.15 (`dist\LecturePack-win32-x64`) |
| Launch args | `--results=C:\LPFrustratedTest\results --data-dir=C:\LPFrustratedTest\data --remote-debugging-port=9222` |
| Window | 1360×860 default, viewport 1344×821, DPR 1 |
| Runtime | Chrome/150, UA `LecturePack/0.9.0-beta.15` |
| Backend | whisper.cpp · CPU AVX2 · ggml-base.en.bin (bundled) |
| Demo asset | Polar Bears 10s Demo (bundled) |
| Log | `production-2026-08-05T17-58-33-865Z.jsonl` — 339 lines, **0 errors / 0 warnings** |
| Shutdown | Clean: `shutdown` → `sidecar_exit code:0` → temp docs removed → `session_closed`; **zero leftover processes** (verified via tasklist for LecturePack/sidecar/ffmpeg/whisper) |

---

## 3. What got FIXED since the portable Beta 15 audit

These were the P0/P1 defects in `ELECTRON_BETA15_FRUSTRATED_STUDENT_AUDIT.md`. Verified against the live dist build:

| Old ID | Old problem | Status now | Evidence |
|---|---|---|---|
| D-1 | Empty state + demo card hidden on first run | ✅ **FIXED** | `homeDemo.visible=true`, `homeEmpty.visible=true`, 3-step walkthrough + "Load sample jobs" all render |
| D-2 | "Use demo video" dead | ✅ **FIXED** | Click → real `import_video {bundled_demo:true}` → PROCESSING → 2 slides + transcript + 13 export files |
| D-3 | "Paste a link" dead | ✅ **FIXED** | Opens "Import from a link" dialog; yt-dlp probe resolved a real YouTube URL with title/duration/channel + Download button |
| D-4 | Raw Electron menu bar | ✅ **FIXED** | `production-main.js:527` sets `autoHideMenuBar: true` |
| D-5 | Version "0.0.0" | ✅ **FIXED** | `app-version` = "0.9.0-beta.15" |
| D-6 | "Check for updates" hangs | ✅ **FIXED** | Returns "Updates are not available in this build." |
| D-7 | "Checking compute backend…" stuck | ✅ **FIXED** | Shows "CPU · AVX2 ready"; Validate updates to "CUDA available but not selected — currently using CPU" |
| D-9 | CUDA install offer dangling | ✅ **FIXED** | `cuda-pack` is hidden; status reads "CUDA unavailable unless this build explicitly enables installation." |
| D-10 | "Test endpoint" silent | ✅ **FIXED** | Returns "Endpoint test succeeded." / "No API key stored." |
| D-11 | Smart Study empty message | ✅ **FIXED** | "Smart Study is optional; Built-in Study is ready." |
| D-14 | Dead "Save" button | ✅ **FIXED** | `btn-save` is now `hidden` (saving is automatic) |
| D-15 | "Test notification" silent | ✅ **FIXED** | "Test notification sent." |
| D-16 | Breadcrumb shows raw UUID | ✅ **FIXED** | `crumb-job` = "demo-lecture" (friendly name) |

**Architectural win:** `electron-bridge.js` now routes every deferred control to a **structured `FEATURE_UNAVAILABLE` response with a human-readable message** (`unavailableMessages`, lines 40–60) instead of a silent `null`. This single change is why none of the buttons "do nothing" anymore. *This is exactly the right pattern — keep it.*

---

## 4. Remaining / new defects (most severe first)

### F-1 — HIGH — Onboarding — Guided tour dead-ends after the demo finishes
**Evidence (CDP, final state):**
```
guided-tour-overlay: hidden=false, display=block
tour-step-label: "DEMO · IMPORT"
tour-title:      "Add the demo video"
tour-next btn:   "Add demo to continue"
demo-card-status:"Demo ended and its temporary files were removed."
```
**What the student sees:** They clicked the glowing demo, it ran beautifully, and now a tour card is still pinned to the screen saying **"Add the demo video — Add demo to continue"** while the demo card underneath says **"Demo ended and its temporary files were removed."** The tour is asking them to do something that is no longer possible. The only ways out are "Exit demo" or re-clicking "Try guided demo."

**Why it hurts:** This is the single most likely rage-quit moment. The demo is the *best* part of the app, and it ends in a contradiction. A student who followed every instruction correctly is now stuck on a step that can't be completed.

**Why it happens:** The tour state machine advances on demo *start* but does not reconcile the "demo ended / temp files removed" terminal state. The tour overlay and the demo-card status are driven by two different pieces of state that fall out of sync.

**Fix (P0):** When the demo job completes (or its temp files are cleaned up), either (a) auto-advance the tour to the review/export step, or (b) auto-dismiss the tour with a "Demo complete — nice work!" toast and a CTA to "Drop your own lecture." Never leave a "continue" button pointing at a deleted asset.

---

### F-2 — HIGH — UX — "Group lecture" modal appears unexpectedly and stacks over the tour
**Evidence (CDP):**
```
Visible overlays at the same time:
  1. guided-tour-overlay  ("DEMO · IMPORT …")
  2. .lp-modal-ov.lp-scrim ("Group lecture / COURSE / SUBJECT / Cancel / Save")
```
**What the student sees:** While navigating (in this case after interacting with Study/Smart Study controls), a **"Group lecture — COURSE / SUBJECT"** dialog popped up uninvited and dimmed the screen, *on top of* the already-present tour card. Two competing "please deal with me" layers at once.

**Why it hurts:** Modal dialogs are the highest-cost interruption in an app. One appearing without a clear trigger — and stacking on another overlay — reads as "the app is doing things I didn't ask for."

**Why it happens:** The grouping modal is wired to an event that can fire during the demo/first-job flow (likely job-completion auto-grouping or a Smart-Study setup side path). There is also no single "overlay manager," so the tour and the modal scrim are both allowed to be visible simultaneously.

**Fix (P0):** (1) Suppress auto-triggered grouping modals during the guided demo and when there is only one job. (2) Introduce a lightweight overlay/z-index manager so only one top-level overlay is visible at a time; queue the rest.

---

### F-3 — MEDIUM — UI — Status bar disagrees with itself
**Evidence (CDP, job already COMPLETE):**
```
status-label:  "IDLE"
status-right:  "Detecting slides"     ← stale
side-job-status:"Processing - 100%"    ← should say Complete/Ready
```
**What the student sees:** The job card says **COMPLETE**, the status chip says **IDLE**, the right-hand status still says **"Detecting slides"**, and the sidebar says **"Processing - 100%"**. Three sources of truth, three different answers.

**Why it hurts:** Students check "is it done yet?" constantly during long transcriptions. Contradictory status erodes trust in the one number they care about (progress).

**Fix (P1):** Drive all three readouts from one job-state reducer. On `job_completed`, force `status-right` to a friendly terminal label ("Ready" / "Complete") and `side-job-status` to "Complete." Never show "Processing - 100%" as a resting state.

---

### F-4 — MEDIUM — UX — Clicking a recent-job card doesn't open the lecture
**Evidence (CDP):** Clicking the `demo-lecture` card on Home kept `visibleScreens=["home"]`; the job loaded into the sidebar (`crumb-job="demo-lecture"`) but the main view didn't navigate.

**What the student sees:** They click their lecture on the home screen and… nothing visible happens. The lecture is "loaded" in a tiny sidebar widget, but they're still staring at the drop zone. They have to manually click Process/Review/Transcript in the nav.

**Why it hurts:** "Click the thing → open the thing" is the most basic expectation on a home/recent-items screen.

**Fix (P1):** On job-card click, navigate to the most useful screen for that job's state (Process if still processing, Review/Transcript if complete). At minimum, navigate to the workspace and show a loaded state.

---

### F-5 — LOW — UI — Overlay/z-index stacking (tour + modal + scrim coexist)
**Evidence:** Two overlays visible simultaneously (see F-2); 5 overlay-family nodes in the DOM, 2 visible at once.
**Fix (P2):** Part of the F-2 overlay manager. Define a single top-most layer and a scrim policy.

---

### F-6 — LOW — State — Runtime overlay still carries stale "Runtime needs repair" text
**Evidence (CDP):** `runtime-setup-overlay` is correctly `hidden`, but its `innerText` still contains "Runtime needs repair… Repair all / Retry / Open diagnostics."
**What it means:** The overlay is not shown (correct — the runtime is healthy and the health check passed), but the markup is left in a "gate" state. Harmless today, but if a future bug re-shows it, a healthy app would claim it needs repair.
**Fix (P2):** Reset the runtime overlay to its neutral/healthy copy once `bootstrap_complete` fires.

---

### F-7 — LOW — UX — Focus mode gives no visible feedback (needs confirmation)
**Evidence (CDP):** Clicking `btn-focus` produced no DOM class/attribute change. It may drive a native window/fullscreen behavior that CDP can't see, so this is **unconfirmed**.
**Fix (P3):** Confirm Focus toggles something perceptible (fullscreen / chrome hiding). If it does nothing in this build, hide it or return a FEATURE_UNAVAILABLE message like the other deferred controls.

---

### F-8 — INFO — Settings — model path & "Load sample jobs" notes
- **Model path:** The full `…\ggml-base.en.bin` path still renders in Settings, but it now sits behind an **"Advanced model details"** expander with a friendly "Whisper Base English model" label. This is an acceptable resolution of old D-8 — just confirm the expander is **collapsed by default**.
- **"Load sample jobs":** Present in the empty state. Could not be exercised in this session because a job already existed (the button hides once `jobs-count > 0`). Recommend a dedicated test with a fresh `--data-dir` to confirm it seeds sample jobs.

---

## 5. What works really well (keep all of this)

- **First-run home screen is now genuinely good.** "LOCAL · PRIVATE · NO ACCOUNT," a clear tagline, a glowing demo card, a 3-step empty-state walkthrough, and Paste/Browse affordances. This is a compelling first impression.
- **The guided demo is a killer onboarding feature** — a 10-second bundled lecture that runs the *real* pipeline. It just needs its exit path fixed (F-1).
- **Paste-a-link is real.** yt-dlp probing with title/duration/channel preview + an explicit "only fetch lectures you have the right to download" note is thoughtful and trustworthy.
- **The Study screen is rich:** Ask / Quiz / Flashcards / Notes, bookmarks, study stats, and a transparent Smart Study install choice (Lightweight ~1.4 GB vs Balanced ~2.5 GB, with a recommendation based on RAM). Great for the student persona.
- **Honest deferred features.** Every not-yet-built feature now says so in plain English instead of hanging. This is the single biggest trust win.
- **Clean runtime.** 335 log lines, zero errors/warnings; clean boot → sidecar ready → process → export → shutdown.
- **Storage widget** ("9.5 MB · 146.8 GB free") and the privacy footer ("100% local. No telemetry…") are nice trust-building touches.

---

## 6. Recommended fixes (priority order)

| Priority | Fix | Effort |
|---|---|---|
| P0 | **F-1** Reconcile tour state when the demo ends — never leave "Add demo to continue" pointing at a deleted asset | Medium |
| P0 | **F-2** Suppress auto-triggered "Group lecture" modal during demo/first-job; add an overlay manager | Medium |
| P1 | **F-3** Single source of truth for status; friendly terminal labels | Small |
| P1 | **F-4** Job-card click navigates to the appropriate screen | Small |
| P2 | **F-5** Overlay/z-index stacking policy (part of F-2) | Small |
| P2 | **F-6** Reset runtime overlay to healthy copy after bootstrap | Trivial |
| P3 | **F-7** Confirm/hide Focus mode behavior | Trivial |
| P3 | **F-8** Confirm model-path expander collapsed by default; test "Load sample jobs" on a fresh data dir | Trivial |

---

## 7. Optional add-ons (high value for students)

1. **Demo completion celebration.** When the guided demo finishes, show a "Your first study pack is ready 🎉" moment with two buttons: **"Open my study pack"** and **"Drop my own lecture."** Turns the current dead end (F-1) into the app's best conversion moment.
2. **Processing time estimate.** Before starting a real lecture, show "~X min for a Y-minute lecture on this machine." Students need to know whether a 90-minute lecture is a coffee break or a library session.
3. **Background/tray progress.** A taskbar progress bar or tray state so a student can minimize and keep working while a long lecture transcribes.
4. **"What happens to my data?" first-run note.** The privacy footer is great; promote it to a one-line reassurance on the home screen ("Your recordings never leave this computer").
5. **Sample lecture library.** Extend "Load sample jobs" to 2–3 short lectures in different subjects so a student can explore the full Review/Study/Export flow without hunting for their own video.
6. **Keyboard shortcuts + Esc-to-close.** Ensure every overlay (including the tour and the grouping modal) closes on `Esc`, and document a few shortcuts (⌘/Ctrl+O import, ⌘/Ctrl+E export).
7. **Export destination picker.** Let the student choose where the Study Pack lands instead of always the data dir.

---

## 8. Test artifacts

- CDP harness: `lp_cdp_test.js` (Desktop)
- Audit scripts: `lp_frustrated_audit.js`, `lp_frustrated_audit2.js` (Desktop)
- Command files: `lp_cmds_frustrated_1.json`, `lp_cmds_final.json` (Desktop)
- Raw results: `lp_audit_results.json`, `lp_audit_results2.json` (Desktop)
- Log analysis: `lp_log_analysis.txt`, `lp_log_flow.txt` (Desktop)
- Screenshots: `lp_shots/frustrated_1_first_launch.png`, `lp_shots/frustrated_audit_final.png`, `lp_shots/frustrated_audit2_final.png`, `lp_shots/frustrated_final_state.png` (Desktop)
- Production log: `C:\LPFrustratedTest\results\production-2026-08-05T17-58-33-865Z.jsonl`
- Job data + exports: `C:\LPFrustratedTest\data\jobs\…\exports\` (13 files: slides.pdf, study-pack.html/pdf, transcript.{txt,srt,vtt,md,json,csv,…})

---

## 9. Verdict

**The engine is real, the onboarding is finally visible, and the app works end-to-end.** This dist build resolves essentially every P0/P1 from the portable Beta 15 audit. What's left is a tight cluster of **UX-state bugs around the guided demo**: a tour that dead-ends after the demo finishes (F-1), an unexpectedly-triggered grouping modal that stacks over it (F-2), contradictory status readouts (F-3), and job cards that don't open on click (F-4).

A frustrated student today will get *much* further than yesterday — they'll successfully run the demo and even paste a real link — but they'll still stall at the demo's exit. **Fix F-1 and F-2 (both medium effort) and this is ready for an unattended student beta.** The foundation is solid; this is polish, not reconstruction.