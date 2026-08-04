# LecturePack 0.9.0-beta.15 — Combined Audit Report

> **A frustrated student's journey through the app, documented with two independent toolchains:**
> **CDP (Chrome DevTools Protocol)** + **windows-use 0.8.1 (Windows UI Automation)**

![Method Legend](https://img.shields.io/badge/Method-CDP%20%2B%20UIA-ff6e40)
![Status](https://img.shields.io/badge/Status-Not%20ready%20for%20beta-e74c3c)
![Version](https://img.shields.io/badge/Version-0.9.0--beta.15-3498db)

---

## 📋 Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Two Audits, Reconciled](#2-the-two-audits-reconciled)
3. [Test Environment](#3-test-environment)
4. [The Student's Journey](#4-the-students-journey)
5. [Defect Register (D-1 → D-17)](#5-defect-register)
6. [What Works Well](#6-what-works-well)
7. [Interactive Graph Map](#7-interactive-graph-map)
8. [Root-Cause Analysis](#8-root-cause-analysis)
9. [Recommended Fixes (Priority Order)](#9-recommended-fixes)
10. [Optional Add-ons](#10-optional-add-ons)
11. [Verdict](#11-verdict)
12. [Artifacts & Evidence](#12-artifacts--evidence)

---

## 1. Executive Summary

The app **boots cleanly** and the **core engine genuinely works end-to-end** — but the **first-run experience is a maze of dead buttons, hidden states, and infinite spinners**.

A new student is greeted by:

- 🚫 A **developer menu bar** (File / Edit / View / Window) in a consumer app
- 🚫 A home screen where **both** the "No lectures yet" empty state **and** the "Use demo video" card are **hidden**
- 🚫 A **"Paste a link" button that does literally nothing**
- 🚫 A **"Check for updates" button that hangs forever**
- 🚫 A **version number that reads "0.0.0"**
- ✅ But *beneath* the broken onboarding: a **fully functional** import → transcribe → slides → export engine

> **The verdict: the app is not broken — it is hidden.** The P0 fixes are all small and would unlock a genuinely working product.

---

## 2. The Two Audits, Reconciled

| | **Audit 1 — CDP (original)** | **Audit 2 — windows-use / UIA (this pass)** |
|---|---|---|
| **Toolchain** | Chrome DevTools Protocol (DOM-level) | `windows_use.uia` (native Windows UI Automation) + CDP |
| **What it sees** | The DOM as JavaScript sees it | The native accessibility tree (what a screen reader sees) |
| **Strengths** | Reliable DOM click triggering, deep state inspection | Native window/dialog/folder interaction, accessibility evidence |
| **Confirmed** | D-1 → D-15 (15 defects) | D-1, D-2, D-3, D-4, D-13, D-14 (via UIA tree) + D-16, D-17 (new) |
| **Core flow tested** | ❌ Could not (no native dialog access) | ✅ **Full import → process → export verified** |

**Every defect D-1 → D-17 is now corroborated by at least one toolchain, and the core workflow is proven functional.**

---

## 3. Test Environment

| Item | Value |
|---|---|
| **OS** | Windows 11 |
| **App** | LecturePack 0.9.0-beta.15 (portable) |
| **Launch args (CDP pass)** | `--results=C:\LPBeta15Test\results --data-dir=C:\LPBeta15Test\data --remote-debugging-port=9222` |
| **Launch args (UIA pass)** | `--results=C:\LPBeta15WinTest\results --data-dir=C:\LPBeta15WinTest\data --remote-debugging-port=9222` |
| **Sidecar** | `LecturePackSidecar.exe` (PyInstaller) — booted OK, health check passed |
| **Real test video** | "Heinrich Schliemann: The Boogeyman of Archaeology" — 2:48, 5.7 MB, 1920×1080, h264/aac |
| **UI source** | `resources/ui/` (index.html, app.js, app.css, bridge.js) |

---

## 4. The Student's Journey

### 🏠 Step 1 — First Launch (Home screen)

```
┌─────────────────────────────────────────────────────────────┐
│ LecturePack  [Focus] [DARK] [Save] [Export]                 │
├──────────────┬──────────────────────────────────────────────┤
│ No lecture   │  LOCAL · PRIVATE · NO ACCOUNT                │
│ loaded       │                                              │
│ Idle         │  Turn lecture recordings into study packs.   │
│              │                                              │
│ LIBRARY      │  ┌──────────────────────────────────────┐    │
│   Home       │  │  Drop a lecture video anywhere       │    │
│ WORKSPACE    │  │  .mp4 · .mkv · .mov · .m4v · .webm   │    │
│   Process    │  │  [Paste a link]  [Browse for video]  │    │
│   Review     │  └──────────────────────────────────────┘    │
│   Transcript │                                              │
│   Study      │  RECENT JOBS  0   [Archive][Restore][Select] │
│ OUTPUT       │                                              │
│   Exports    │                                              │
│   Settings   │                                              │
├──────────────┴──────────────────────────────────────────────┤
│ ● IDLE                                    whisper.cpp · CPU  │
└─────────────────────────────────────────────────────────────┘
```

**What a student sees:** A working dropzone, "Recent jobs: 0", and Archive/Restore/Select buttons that do nothing. **No** "No lectures yet" guidance. **No** "Use demo video" card. **No** 3-step walkthrough.

### 🖱️ Step 2 — Attempts to get started

| The student clicks… | What happens |
|---|---|
| **"Paste a link"** | ❌ **Nothing.** (D-3 — feature deferred, button ships) |
| **"Use demo video"** | ❌ **Nothing.** (D-2 — `start_demo_job` is a no-op) |
| **"Check for updates"** | ❌ **Spins forever.** (D-6) |
| **"Browse for video"** | ✅ **Native file dialog opens!** (this is the one that works) |

> ⚠️ **The one button that works ("Browse for video") is the least discoverable** — the flashy demo card and paste-link CTA are the dead ones.

### ✅ Step 3 — The (hidden) working engine

When a student *does* use "Browse for video" and picks a lecture, the app proves itself:

```
Import → Inspect → Extract Audio → Transcribe → Detect Slides → Align → Export → ✅ Complete
 (2:48 video processed in ~48 seconds)
```

- **Accurate transcription** (whisper.cpp): *"Hello everyone. Welcome back to another video from History with Daena. Today I'm going to be delving into Heinrich Schliemann, the boogeyman of archaeology..."*
- **24 slides detected** from the 2:48 video
- **133 export files** in 10+ formats
- The app **auto-navigates** to the Process screen showing all stages ✓

---

## 5. Defect Register

### 🔴 Critical (P0)

#### D-1 — First-run home shows neither empty state nor demo card
**Observed (CDP + UIA):** `home-demo` and `home-empty` both hidden (`homeDemoHidden: true`, `homeEmptyHidden: true`). The UIA tree contains neither group.
**Root cause:** Both cards start `hidden` in `index.html`; the reveal logic never fires in the packaged app.
**Fix:** On zero jobs, always show the empty-state walkthrough AND the demo card.

#### D-2 — "Use demo video" card is visible but dead
**Observed (CDP + UIA):** Card exists & visible; clicking does nothing. UIA tree shows no demo card (hidden).
**Root cause:** `start_demo_job` is in `electron-bridge.js` `noopCalls` (line 33).
**Fix:** Wire it to the real `import_video` with `bundled_demo: true`, or hide the card.

### 🟠 High (P0/P1)

#### D-3 — "Paste a link" button is visible but dead
**Observed (CDP + UIA):** `pasteLinkHidden: false`, `display: flex`; click → no state change. UIA tree shows the button.
**Root cause:** `import_media_url` / `probe_media_url` not implemented in the sidecar.
**Fix:** Hide until yt-dlp / link import works.

#### D-4 — Raw Electron menu bar (File/Edit/View/Window)
**Observed (UIA):** `MenuBarControl` with `File / Edit / View / Window` at top of window.
**Root cause:** `production-main.js` never calls `Menu.setApplicationMenu(null)` or `autoHideMenuBar: true`.
**Fix:** Add `autoHideMenuBar: true` to the `BrowserWindow`.

#### D-5 — Version displays "0.0.0"
**Observed (CDP):** `app-version: "0.0.0"`.
**Root cause:** `LP.data.version` defaults to `'0.0.0'` (app.js line 229) and is never populated.
**Fix:** Inject the packaged version via the bridge.

#### D-6 — "Check for updates" hangs on "Checking…"
**Observed (CDP):** Status never resolves.
**Root cause:** `check_updates` is in `noopCalls`.
**Fix:** Implement or show "not available in this build".

#### D-7 — "Checking compute backend…" never resolves
**Observed (CDP):** `vulkan-status` stuck on "Checking…".
**Root cause:** `validate_vulkan` / `validate_cuda` are no-ops.
**Fix:** Use the real health_check CPU/AVX2 info.

### 🟡 Medium (P1/P2)

#### D-8 — Full technical whisper model path shown to user
**Observed (CDP):** 200+ char absolute path displayed.
**Fix:** Friendly label with path in an "Advanced" section.

#### D-9 — "Install CUDA acceleration" offered though GPU packaging is deferred
**Observed (CDP):** NVIDIA GPU detected → install offer shown.
**Fix:** Suppress until the install flow works.

#### D-10 — "Test endpoint" button does nothing visible
**Observed (CDP):** No feedback.
**Root cause:** `test_endpoint` is a no-op.
**Fix:** Implement or show "not available".

#### D-11 — "Set up Smart Study" shows empty message
**Observed (CDP):** `ss-settings-msg` empty.
**Fix:** Provide a clear message.

#### D-12 — Runtime setup overlay internally set to "gate" but hidden
**Observed (CDP):** `activeState: "gate"` with overlay hidden — a silent failure.
**Fix:** Show the repair overlay or clear the stale state.

### 🟢 Low (P2)

#### D-13 — Archive/Restore/Select visible with zero jobs
**Observed (UIA):** All three buttons visible with `jobs-count` = 0.
**Fix:** Hide the action bar when there are no jobs.

#### D-14 — "Save" button in header does nothing
**Observed (UIA):** `btn-save` visible; click → no state change.
**Root cause:** `save_project` is a no-op.
**Fix:** Hide or wire it.

#### D-15 — "Test notification" button gives no feedback
**Observed (CDP):** No visible result.
**Root cause:** `test_notification` is a no-op.
**Fix:** Implement a real desktop notification.

### 🆕 New in this pass (UIA)

#### D-16 — Breadcrumb shows raw job UUID instead of a friendly name
**Observed (UIA + CDP):** `crumb-job: "e90eadf6-1047-41dd-a4e1-34c966b01be1"`.
**Fix:** Show the job's friendly name, not the UUID.

#### D-17 — Status bar shows technical pipeline strings
**Observed (CDP):** `status-right: "detector decode: piped"`.
**Fix:** Map internal states to friendly labels.

---

## 6. What Works Well

- ✅ **Cold launch is clean** — sidecar boots, health check passes, no leftover processes
- ✅ **Browse for video opens a real native file dialog**
- ✅ **Full pipeline works** — import → transcribe → slides → export in ~48s for a 2:48 video
- ✅ **Accurate transcription** (whisper.cpp) with proper timestamps
- ✅ **24 slides detected** from a real lecture
- ✅ **133 export files** in 10+ formats (slides.pdf, study-pack.html/pdf, transcript in txt/srt/vtt/md/json/csv/jsonl/sections.md/normalized.txt)
- ✅ **"Open folder" opens native File Explorer**
- ✅ **Full navigation works** with a real job (Review, Transcript, Study, Exports)
- ✅ **Groq key error handling** is clear and actionable
- ✅ **Theme toggle works**
- ✅ **Visually polished UI** (orange accent, Space Grotesk, JetBrains Mono, card-based layout)

---

## 7. Interactive Graph Map

> Open [`ELECTRON_BETA15_GRAPH_MAP.html`](ELECTRON_BETA15_GRAPH_MAP.html) for the full interactive visualization.
> It maps every defect to its root cause and the working engine underneath.

---

## 8. Root-Cause Analysis

### The `noopCalls` epidemic

The single largest cluster of defects traces to one object in `electron-bridge.js`:

```js
var noopCalls = {
  acknowledge_setup: true,  browse_model: true,      cancel_update_download: true,
  check_updates: true,      clear_skipped_version: true, end_demo_job: true,
  exit_application: true,   get_post_completion: true,   get_updater_state: true,
  install_downloaded_update: true, install_update: true, log_tour_trace: true,
  open_release_page: true,  save_project: true,      set_auto_check: true,
  set_update_channel: true, skip_update_version: true, start_demo_job: true,
  start_update_download: true, whatsnew_seen: true,  ...
};
```

**Every command in this list resolves to `null`** — the UI renders the button, the click fires the bridge call, the promise resolves to `null`, and nothing happens. That is the root cause of **D-2, D-3, D-6, D-7, D-10, D-14, D-15**.

### The "hidden" engine

Beneath the no-op layer, the real engine is wired correctly:
- `browse_video` → `dialog.showOpenDialog` → `import_video` ✅
- `start_processing` → `start_job` → full pipeline ✅
- `export_all` / `export_one` → `export` → 133 files ✅

**The product is 80% working but ~20% of the first-run surface is dead buttons.**

---

## 9. Recommended Fixes

| Priority | Fix | Effort | Defects |
|---|---|---|---|
| **P0** | Show empty state + demo card on first launch | Small | D-1 |
| **P0** | Wire `start_demo_job` OR hide demo card | Small | D-2 |
| **P0** | Hide "Paste a link" until implemented | Trivial | D-3 |
| **P0** | Hide Electron menu bar | Trivial | D-4 |
| **P1** | Populate real version number | Small | D-5 |
| **P1** | Fix "Check for updates" hang | Small | D-6 |
| **P1** | Fix "Checking compute backend…" hang | Small | D-7 |
| **P1** | Friendly model path display | Small | D-8 |
| **P1** | Suppress CUDA offer | Small | D-9 |
| **P2** | Endpoint test or "not available" | Small | D-10 |
| **P2** | Smart Study setup message | Small | D-11 |
| **P2** | Fix runtime gate state | Medium | D-12 |
| **P2** | Hide Archive/Restore/Select with 0 jobs | Trivial | D-13 |
| **P2** | Hide or wire Save button | Trivial | D-14 |
| **P2** | Test notification feedback | Small | D-15 |
| **P2** | Friendly breadcrumb name | Small | D-16 |
| **P2** | Friendly status strings | Small | D-17 |

---

## 10. Optional Add-ons

1. **First-run welcome modal** — 3-step "Here's what LecturePack does" with a prominent demo CTA
2. **Drag-and-drop import from Explorer** — the `onb-overlay` "Release to import" state exists but is untested
3. **Processing time estimate** — "~X min for a Y-minute lecture"
4. **Background processing indicator** — system tray / taskbar progress
5. **Export destination picker** — instead of always `~/LecturePackData/…/exports`
6. **"What happens to my data?" explainer** — "Your videos never leave this machine"
7. **Sample lecture library** — 2-3 short samples in different subjects

---

## 11. Verdict

### **Not ready for student-facing beta — but the engine is real.**

| Dimension | Rating |
|---|---|
| Core engine (import/transcribe/slides/export) | ✅ **Excellent** — works end-to-end, fast, accurate |
| First-run onboarding | ❌ **Broken** — dead buttons, hidden states, infinite spinners |
| Trust & polish | ⚠️ **Mixed** — polished UI undermined by visible dead controls |
| Overall | 🟡 **Frustrating** — a working product hidden behind a broken door |

**The P0 fixes (D-1 → D-4) are all small and would transform the first-run experience from "broken" to "compelling", unlocking the genuinely working engine underneath.**

---

## 12. Artifacts & Evidence

### CDP pass (original)
- Production logs: `C:\LPBeta15Test\results\production-*.jsonl`
- CDP scripts: `lp_test_import.js`, `lp_test_nav.js`, `lp_test_demo.js`, `lp_test_settings.js`
- Screenshots: `lp_screenshot.png`, `lp_after_skip.png`

### UIA pass (windows-use 0.8.1)
- UIA scripts: `lp_win_discover.py`, `lp_win_deep.py`, `lp_win_interact.py`, `lp_win_browse.py`, `lp_win_nav.py`, `lp_win_open_folder.py`, `lp_win_job_state.py`, `lp_win_check_dialog.py`
- UIA tree dumps: `lp_win_tree.txt`, `lp_win_dom_tree.txt`, `lp_win_texts.txt`, `lp_win_job_tree.txt`
- Interaction results: `lp_win_interact_results.txt`, `lp_win_nav_results.txt`
- CDP command files: `lp_cmds_*.json`
- Screenshots: `lp_shots/lp_win_process_done.png`, `lp_shots/lp_win_transcript.png`, `lp_shots/lp_win_exports_done.png`
- Production log: `C:\LPBeta15WinTest\results\production-2026-08-04T21-42-45-795Z.jsonl`
- Job data: `C:\LPBeta15WinTest\data\jobs\e90eadf6-1047-41dd-a4e1-34c966b01be1\`