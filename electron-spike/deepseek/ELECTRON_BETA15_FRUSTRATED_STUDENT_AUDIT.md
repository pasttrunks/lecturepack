# LecturePack 0.9.0-beta.15 — Frustrated Student Audit

**Date:** 2026-08-04
**Target:** `dist/releases/0.9.0-beta.15/LecturePack-0.9.0-beta.15-Portable.zip` (extracted to `portable-test/LecturePack-win32-x64/`)
**Method:** Live launch with isolated `--results` / `--data-dir`, Chrome DevTools Protocol (CDP) DOM inspection, Windows UI Automation, production JSONL log analysis, and source-code review of `production-main.js`, `production-preload.js`, `electron-bridge.js`, `app/ui/index.html`, and `app/ui/app.js`.
**Persona:** A frustrated student who just downloaded the app, wants to transcribe a lecture, and has no patience for broken buttons, dead ends, or unexplained states.

---

## 1. Executive summary

The app boots cleanly: the sidecar starts, health check passes, and the UI renders. But the **first-run experience is a dead end**. A new user is greeted by:

- A **developer menu bar** (File / Edit / View / Window) that has no business in a consumer app.
- A home screen where **both the "No lectures yet" empty state AND the "Guided demo" card are hidden**, leaving only an empty "Recent jobs: 0" section and a dropzone.
- A **"Paste a link" button that is visible but does literally nothing** when clicked (the feature is deferred, but the button ships).
- A **"Use demo video" card that is visible but does nothing** when clicked (the `start_demo_job` bridge call is a no-op).
- A **"Check for updates" button that hangs on "Checking…"** forever.
- A **"Checking compute backend…" status that never resolves**.
- A **version number that reads "0.0.0"** instead of "0.9.0-beta.15".

The core processing pipeline (sidecar, FFmpeg, whisper.cpp) is real and boots correctly, but the **onboarding and discovery layer is broken**, which is exactly what a first-time student will hit.

---

## 2. Test environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| App | LecturePack 0.9.0-beta.15 (portable) |
| Launch args | `--results=C:\LPBeta15Test\results --data-dir=C:\LPBeta15Test\data --remote-debugging-port=9222` |
| Sidecar | `LecturePackSidecar.exe` (PyInstaller) — booted OK, health check passed |
| UI source | `resources/ui/` (index.html, app.js, app.css, bridge.js) |
| Demo video | `resources/assets/demo-lecture.mp4` (bundled) |

---

## 3. Defects (most severe first)

### D-1 — Critical — Onboarding — First-run home screen shows neither the empty state nor the demo card
**Evidence (CDP):**
```
homeDemo: false   (hidden)
homeEmpty: false  (hidden)
jobsCount: "0"
jobsGridChildren: 0
```
**What the user sees:** A dropzone, "Recent jobs: 0", and Archive/Restore/Select buttons that do nothing useful. No "No lectures yet" guidance, no "Use demo video" card, no step-by-step "Drop a video → Review slides → Study & export" walkthrough.

**Why it happens:** `home-demo` and `home-empty` both start with the `hidden` attribute in `index.html` (lines 123, 132). The app.js logic that should reveal one of them based on job count is not firing in the packaged app — likely because the `jobs_changed` event arrives before the renderer's boot sequence completes, or the reveal condition never matches.

**Fix:** On first launch with zero jobs, always show the `home-empty` state (with the 3-step walkthrough) AND the `home-demo` card. The demo card is the single best "try it now" affordance for a new user.

---

### D-2 — Critical — Functionality — "Use demo video" card is visible but dead
**Evidence (CDP):**
```
Demo card: exists, hidden: false, display: flex, draggable: true
After card.click(): onbHidden: true, detectedHidden: true  (nothing opened)
```
**Why it happens:** `electron-bridge.js` line 33 lists `start_demo_job: true` in `noopCalls`, so `lpBridge.startDemoJob()` resolves to `null` and nothing happens. The UI card is rendered unconditionally but the backend path is a no-op.

**Fix:** Either (a) wire `start_demo_job` to the real sidecar `import_video` command with `bundled_demo: true` (the sidecar already supports it per `electron-bridge.js` line 313), or (b) hide the demo card entirely until the feature is implemented. Shipping a visible, clickable card that does nothing is worse than not shipping it.

---

### D-3 — High — Functionality — "Paste a link" button is visible but dead
**Evidence (CDP):**
```
Paste a link: hidden: false, display: flex
After btn.click(): no toast, no dialog, no overlay, no state change
```
**Why it happens:** The README explicitly says "Paste Link/yt-dlp … deferred", but `index.html` line 87 renders `#btn-paste-link` without the `hidden` attribute (it has `hidden` in the markup but the production scope CSS or app.js removes it — the CDP check shows `hidden: false`). The bridge maps `import_media_url` / `probe_media_url` to sidecar commands, but the sidecar doesn't implement them, so clicking does nothing.

**Fix:** Hide `#btn-paste-link` until yt-dlp / link import is implemented. A visible button that silently does nothing is a trust-killer.

---

### D-4 — High — UI — Default Electron menu bar (File / Edit / View / Window) is visible
**Evidence (UI Automation):**
```
Button: File, Edit, View, Window  (at top of window, y≈117)
```
**Why it happens:** `production-main.js` never calls `Menu.setApplicationMenu(null)` or `autoHideMenuBar: true` in the `BrowserWindow` options.

**Fix:** Add `autoHideMenuBar: true` to the `BrowserWindow` constructor (line 455) and/or `Menu.setApplicationMenu(null)` in `app.whenReady()`. A consumer app should never show the raw Electron menu.

---

### D-5 — High — Settings — Version displays "0.0.0" instead of "0.9.0-beta.15"
**Evidence (CDP):**
```
app-version: "0.0.0"
```
**Why it happens:** `app.js` reads the version from a bridge call (`get_app_version` or similar) that is not implemented in `electron-bridge.js`'s `noopCalls` or `mapCall`. The `LP.data.version` defaults to `'0.0.0'` (app.js line 229) and is never updated.

**Fix:** Populate the version from the packaged `package.json` (available in the main process) and expose it via the preload bridge, or inject it into the production document at build time.

---

### D-6 — High — Settings — "Check for updates" hangs on "Checking…" forever
**Evidence (CDP):**
```
After clicking btn-check-updates: update-status text = "Checking…" (never resolves)
```
**Why it happens:** `check_updates` is in `noopCalls` (electron-bridge.js line 20), so the promise resolves to `null` and the UI's "Checking…" state is never cleared.

**Fix:** Either implement the update check (GitHub Releases API — the What's New overlay already references it) or show a clear "Updates are not available in this build" message instead of an infinite spinner.

---

### D-7 — High — Settings — "Checking compute backend…" never resolves
**Evidence (CDP):**
```
vulkan-status: "Checking compute backend…"  (stuck)
cuda-status: ""  (empty)
```
**Why it happens:** `validate_vulkan` / `validate_cuda` are in `noopCalls` (electron-bridge.js lines 213-214), so the status text is set to "Checking…" and never updated.

**Fix:** Implement the backend detection (the sidecar's `health_check` already reports CPU/AVX2) or show a static, accurate status like "CPU · AVX2" without the fake "Checking…" state.

---

### D-8 — Medium — Settings — Full technical whisper model path shown to user
**Evidence (CDP):**
```
setting-model-path: "C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\portable-test\LecturePack-win32-x64\resources\LecturePackSidecar\_internal\models\ggml-base.en.bin"
```
**Why it happens:** The settings screen renders the absolute path to the bundled model. This is a 200+ character path that means nothing to a student.

**Fix:** Show a friendly label ("Bundled model · ggml-base.en.bin") with the full path only in an expandable "Advanced" section.

---

### D-9 — Medium — Settings — "Install CUDA acceleration" offered even though GPU packaging is deferred
**Evidence (CDP):**
```
cuda-pack-msg: "NVIDIA GPU detected. Install optional CUDA acceleration for faster transcription."
cuda-pack: visible (not hidden)
```
**Why it happens:** The sidecar's `cuda_pack_status` reports an NVIDIA GPU is present, and the UI shows the install offer. But the README says "GPU packaging … deferred", so the install flow likely can't complete.

**Fix:** Either implement the CUDA pack install or suppress the offer until it works. A "Downloading…" progress bar that never completes is worse than no offer.

---

### D-10 — Medium — Settings — "Test endpoint" button does nothing visible
**Evidence (CDP):**
```
After clicking btn-test-endpoint: no status text change, no toast
```
**Why it happens:** `test_endpoint` is in `noopCalls` (electron-bridge.js line 198), so the promise resolves to `null` and the UI has no feedback.

**Fix:** Implement the endpoint test (a simple HTTP GET to `http://localhost:11434`) or show "Not available in this build".

---

### D-11 — Medium — Settings — "Set up Smart Study" shows empty message
**Evidence (CDP):**
```
After clicking btn-ss-setup: ss-settings-msg text = "" (empty)
```
**Why it happens:** `smart_study_status` returns a payload, but the UI's setup flow doesn't populate the message element when the result is empty.

**Fix:** Provide a clear message ("Smart Study is not available in this build" or "Ollama not detected — install it to enable Smart Study").

---

### D-12 — Medium — Runtime — Runtime setup overlay internally set to "gate" (needs repair) but hidden
**Evidence (CDP):**
```
runtime-setup-overlay: hidden: true
activeState: "gate"  (the "Runtime needs repair" state)
```
**Why it happens:** The overlay's internal state machine is set to `gate` (meaning "Runtime needs repair") but the overlay itself is hidden. This suggests the runtime assessment found something it considers broken, but the UI never surfaces it — a silent failure.

**Fix:** Either show the repair overlay when the assessment fails, or clear the `gate` state when the runtime is actually healthy (the health check passed, so the gate state is likely stale).

---

### D-13 — Low — UX — "Archive", "Restore", "Select" buttons visible with zero jobs
**Evidence (CDP):**
```
Buttons: Archive, Restore, Select  (visible on home screen with 0 jobs)
```
**Why it happens:** The recent-jobs action bar renders unconditionally even when `jobs-grid` is empty.

**Fix:** Hide the Archive/Restore/Select action bar when there are no jobs.

---

### D-14 — Low — UX — "Save" button in header does nothing meaningful
**Evidence (CDP):**
```
Button: Save  (in header, always visible)
```
**Why it happens:** `save_project` is in `noopCalls` (electron-bridge.js line 29). The Save button is always visible but has no effect.

**Fix:** Hide the Save button or wire it to a real save action (e.g., persist current notes/corrections).

---

### D-15 — Low — UX — "Test notification" button gives no feedback
**Evidence (CDP):**
```
After clicking btn-test-notification: no visible result
```
**Why it happens:** `test_notification` is in `noopCalls` (electron-bridge.js line 213).

**Fix:** Implement a real desktop notification or show a toast confirming the test.

---

## 4. What works well

- **Cold launch is clean.** Sidecar boots, health check passes, no renderer crash, no leftover processes on shutdown (verified in production logs: `sidecar_exit code:0`).
- **Navigation works.** All 7 screens (Home, Process, Review, Transcript, Study, Exports, Settings) navigate correctly with proper breadcrumbs.
- **Groq key error handling is good.** "No API key stored — set one first." is clear and actionable.
- **Theme toggle works.** Light/dark switching is functional.
- **The UI is visually polished.** The design language (orange accent, Space Grotesk, JetBrains Mono, card-based layout) is cohesive and modern.
- **The processing pipeline is real.** FFmpeg, whisper.cpp, and slide detection are genuinely bundled and the sidecar contract is well-defined.

---

## 5. Recommended fixes (priority order)

| Priority | Fix | Effort |
|---|---|---|
| P0 | Show empty state + demo card on first launch (D-1) | Small |
| P0 | Wire `start_demo_job` to real sidecar import OR hide demo card (D-2) | Small |
| P0 | Hide "Paste a link" until implemented (D-3) | Trivial |
| P0 | Hide Electron menu bar (D-4) | Trivial |
| P1 | Populate real version number (D-5) | Small |
| P1 | Fix "Check for updates" hang (D-6) | Small |
| P1 | Fix "Checking compute backend…" hang (D-7) | Small |
| P1 | Friendly model path display (D-8) | Small |
| P1 | Suppress CUDA offer until implemented (D-9) | Small |
| P2 | Implement endpoint test or show "not available" (D-10) | Small |
| P2 | Smart Study setup message (D-11) | Small |
| P2 | Fix runtime gate state (D-12) | Medium |
| P2 | Hide Archive/Restore/Select with zero jobs (D-13) | Trivial |
| P2 | Hide or wire Save button (D-14) | Trivial |
| P2 | Test notification feedback (D-15) | Small |

---

## 6. Optional add-ons (not bugs, but high-value for students)

1. **First-run welcome modal** — A 3-step "Here's what LecturePack does" with a prominent "Try the 10-second demo" CTA. The current guided tour exists but is easy to skip past.
2. **Drag-and-drop file import from Explorer** — The dropzone exists, but dragging a file from Windows Explorer onto the window should be tested end-to-end (the `onb-overlay` "Release to import" state exists but I couldn't trigger it via CDP).
3. **Processing time estimate** — Before starting a job, show "Estimated time: ~X min for a Y-minute lecture" based on the model and CPU. Students need to know if a 90-minute lecture will take 2 minutes or 2 hours.
4. **Background processing indicator** — A system tray icon or taskbar progress that shows when a job is running while the app is minimized.
5. **Export destination picker** — Let the user choose where exports go instead of always `~/LecturePackData/…/exports`.
6. **"What happens to my data?" explainer** — The privacy section exists in Settings, but a first-run explainer ("Your videos never leave this machine") would build trust immediately.
7. **Sample lecture library** — Beyond the single demo video, offer 2-3 short sample lectures (different subjects) so students can try the full flow without hunting for their own video.

---

## 7. Test artifacts

- Production logs: `C:\LPBeta15Test\results\production-*.jsonl` (3 sessions, all clean boots/shutdowns)
- CDP test scripts: `lp_test_import.js`, `lp_test_nav.js`, `lp_test_demo.js`, `lp_test_settings.js` (on Desktop)
- UI Automation scripts: `lp_ui_inspect.ps1`, `lp_click_skip.ps1`, `lp_click_browse.ps1`
- Screenshots: `lp_screenshot.png`, `lp_after_skip.png` (on Desktop)

---

## 8. Verdict

**Not ready for student-facing beta.** The core engine is real and boots cleanly, but the first-run experience is a maze of dead buttons, hidden states, and infinite spinners. A frustrated student will click "Paste a link" (nothing), click "Use demo video" (nothing), click "Check for updates" (spins forever), and conclude the app is broken. The P0 fixes (D-1 through D-4) are all small and would transform the first-run experience from "broken" to "compelling."