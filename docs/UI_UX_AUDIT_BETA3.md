# LecturePack UI/UX Audit — 0.9.0-beta.3 WebEngine UI

Date: 2026-07-25
Target: `app/ui/index.html` + `app/ui/app.js` + `app/ui/app.css` + `app/ui/bridge.js`, served statically at `http://localhost:8778` (no QWebChannel backend — `bridge.js` confirmed to fall back to a null backend and the UI's own demo/mock data, per its own header comment).
Method: DOM/computed-style inspection and scripted interaction via `javascript_tool` and real keyboard events via `computer` (the Browser pane could not composite a visible frame in this session — `computer{action:"screenshot"}` errored with "the Browser pane is not displayed" — so all findings below are evidence-based from `getComputedStyle`, `getBoundingClientRect`, and DOM state, not visual screenshots, per the task's own guidance).

## 1. Summary metrics

- Features enumerated from code/docs: 19 (Home/new-job, Processing queue, Local scheduling, Process screen + pause/resume/cancel, Interrupted/Needs-attention cards, Completion panel, Review/slides, Transcript workspace, Study/Ask, Quiz, Flashcards, Notes, Bookmarks, Exports, Settings→Whisper model, Settings→Compute engine, Settings→Smart Study, Settings→Transcription (Groq), Settings→Notifications, Settings→Updates, Appearance/theme, Focus mode)
- Features actually exercised interactively: 12 (Home/empty-state toggle, navigation across all 7 screens, theme toggle, New-job overlay open/close, keyboard shortcuts 1-7/F/Escape, Tab-order/focus-visible, Review slide-list/transcript mock rendering, Study/Ask chat send, Settings DOM present-check, viewport reflow at 3 widths, contrast measurement, What's-new/queue/scheduled empty-state DOM)
- Features enumerated but NOT interactively exercised (no live backend, or gated behind demo data the static mock doesn't populate): Processing queue reorder/Run Now (queue is empty in the demo — `queue-list` had 0 children), Local scheduling dialog (only reachable from a queued job's action menu, which the demo never populates), pause/resume live transitions, retry-stage, notifications Test button, Groq key test, Smart Study install flow, CUDA pack install, update download/install — all correctly fall back to `toast('Preview mode — ...')` where wired, confirming graceful no-backend handling rather than a crash.
- Defects found: **5** — Critical: 1, High: 2, Medium: 1, Low: 1
- Interactions executed: ~35 scripted DOM/keyboard operations (nav clicks ×7, theme toggles ×3, Tab presses ×19 total across two runs, Escape ×1, digit-key shortcut ×1, contrast computations ×2 themes, viewport resizes ×4, overflow measurements on 4 screens, empty-state toggle ×2, chat-send fuzz with 500-char input)

## 2. Coverage table

| Feature | Verdict | Reason |
|---|---|---|
| Home / recent jobs grid | PASS | Renders 1 mock job card; empty-state toggle (`btn-show-empty` / `btn-load-jobs`) verified round-trip correctly (`home-empty.hidden` flips true→false→true, `jobs-grid` repopulates to 1 child) |
| New-job overlay (drop/browse) | DEFECT | See D-1, D-2 |
| Processing queue (reorder/Run Now/remove) | UNVERIFIABLE-STATICALLY | `queue-list` has 0 children in the static demo; no queued job exists to interact with |
| Local scheduling (datetime + missed policy) | DEFECT (code-level) | See D-4; UI unreachable live because no queued job to trigger `scheduleJobDialog` |
| Process screen (stages, pause/resume/cancel) | PASS (static) | DOM renders 7 pipeline stage rows and a completion panel from mock data; live pause/resume transition not testable without backend |
| Interrupted / Needs-attention cards | UNVERIFIABLE-STATICALLY | No interrupted job exists in the demo dataset |
| Completion panel (metrics + actions) | PASS (static) | `cm-*` elements present and populated by mock data (`app.js`) |
| Review (slides, timeline, transcript-for-selection) | DEFECT | See D-3 (layout overflow/clipping at 1024×768 and 768px width) |
| Transcript workspace | PASS (static) | 4 transcript blocks render from mock data at 1280×800 |
| Study — Ask/chat | PASS | Sending a 500-char fuzzed message did not throw, feed re-rendered (4 children), input cleared after send |
| Study — Quiz / Flashcards | PASS (static) | `quiz-root`/`flash-root` populate with mock config controls (question count, difficulty, etc.) |
| Study — Notes | NOT EXERCISED | Present in DOM (`notes-area` textarea) but not fuzzed this pass |
| Study — Bookmarks | PASS (static) | 2 mock bookmarks render |
| Exports | PASS (static) | PDF/HTML cards, 8 transcript-format toggles, "Export all" idle/running/done states all present in DOM |
| Settings — Whisper model / Compute engine | PASS (static) | Controls present; CUDA/Vulkan validate buttons wired to `lpBridge.call`, no-op safely with no backend |
| Settings — Smart Study | PASS (static) | Onboarding banner markup present, gated by `hidden` |
| Settings — Transcription (Groq) | PASS (static) | Key input, Test/Remove buttons present; no live key test possible without backend |
| Settings — Notifications (6 toggles + Test) | PASS (static) | All 6 checkboxes (`notif-complete/failed/update/study/sound/unfocused`) present with correct `data-notif` keys matching `app.js` `wireBridge`/settings sync code |
| Settings — Updates / What's new | PASS (static) | Overlay markup, skip/remind-later/install actions present |
| Theme toggle (light/dark) | DEFECT | See D-4 (contrast), otherwise toggling itself works correctly and persists via `data-theme` attribute |
| Focus mode | NOT EXERCISED | `btn-focus`/`focus-pill` present; not click-tested this pass |
| Keyboard shortcuts (1-7, F, Escape) | DEFECT | See D-1 (fire even while a modal is open) |
| Responsive layout (1280×800 / 1024×768 / 768w) | DEFECT | See D-3; confirmed via `app.css` grep that the only `@media` query in the whole stylesheet is `prefers-reduced-motion` — there are zero responsive breakpoints |

## 3. Defects (most severe first)

### D-1 — Critical — UX-logic — Global keyboard shortcuts fire behind an open modal
**File:** `app/ui/app.js:1821-1834` (the `window.addEventListener('keydown', ...)` handler registered in the wiring function)

**Repro:**
1. On Home, click `#btn-browse` to open the New-job overlay (`#onb-overlay`).
2. Confirm the overlay is open: `document.getElementById('onb-overlay').hidden === false`.
3. Press the `5` key (not focused in an input/textarea).

**Evidence measured:**
- Before key press: `{"overlayOpen":true,"screenBefore":["home"]}`
- After pressing `5`: `{"overlayOpen":true,"screenAfter":["study"]}`

The main content behind the modal navigated to the Study screen while the New-job dialog remained visually on top and `hidden===false`. The handler at `app.js:1830` only excludes the case where `e.target` is an `INPUT`/`TEXTAREA`/contenteditable (`editing`); it never checks whether `LP.state` currently has a modal/overlay open. Any of the 7 digit shortcuts or `F` (focus mode) will silently change what's underneath an open dialog, which the user only discovers after closing it — a state-corruption trap, worse for screen-reader/keyboard-only users who can't see the modal is still open.

**Fix:** In the keydown handler, early-return (after the Escape branch) when `!$('onb-overlay').hidden || !$('whatsnew-overlay').hidden` (or maintain a generic `LP.state.modalOpen` flag checked here), mirroring the way Escape already closes both overlays.

### D-2 — High — a11y — New-job modal has no focus trap
**File:** `app/ui/app.js` (`setOnb`, referenced at lines 1064, 1585-1586; no focus-containment logic found anywhere in the file — `Grep` for `trapFocus`/`focus-trap` returned no matches)

**Repro:**
1. Open the New-job overlay via `#btn-browse`.
2. Press `Tab` 6 times.

**Evidence measured:** `{"activeId":"btn-save","activeTag":"BUTTON","insideModal":false,"overlayHidden":false}` — keyboard focus left the modal and landed on the header's Save button, which sits underneath the still-open, still-visible overlay (`overlayHidden:false`). A sighted mouse user would click through the semi-transparent scrim onto a control they can't see is disabled/behind-modal; a keyboard-only user has no way to tell focus jumped out of the dialog they're trying to fill in.

**Fix:** Standard modal focus trap: on open, capture the previously-focused element and move focus to the first focusable node inside `#onb-panel`; on `Tab`/`Shift+Tab` at the panel's last/first focusable element, wrap focus back inside the panel instead of letting it escape to `document`; restore focus to the trigger element on close.

### D-3 — High — spacing / responsive — Review screen clips its transcript panel completely off-screen below 1280px width
**File:** `app/ui/index.html:207-240` (the three-column flex row: slide list `width:250px` at line 209, preview column `min-width:320px` at line 219, transcript column `width:360px;flex:none` at line 231) combined with `app/ui/index.html:67` (`main.lp-main{...overflow-x:hidden}`)

**Repro:**
1. Navigate to Review.
2. Resize viewport to 1024×768 (one of the three widths explicitly required by this audit).

**Evidence measured (1024×768):** `main.scrollWidth = 978`, `main.clientWidth = 800` → 178px of content is clipped, not scrollable, because `overflow-x` on `.lp-main` is `hidden` (confirmed via `getComputedStyle(main).overflowX === "hidden"`).

**Evidence measured (768×1024, the mobile-ish width named in the brief):** `main.scrollWidth = 978`, `main.clientWidth = 544` → the transcript-for-selection column's bounding rect was measured at `left:842, right:1202` while the visible viewport is only 768px wide and the container clips overflow-x — the entire "Transcript for selection" panel (search box, transcript blocks, Save corrections/Repair buttons) is unreachable by any means (no horizontal scrollbar exists because `overflow-x:hidden`).

**At 1280×800 (the third required width) there is no overflow** (`scrollWidth === clientWidth === 1056`), so the screen only works correctly at the single largest tested width. `app.css` has exactly one `@media` rule in the entire file (`prefers-reduced-motion`) — there is no responsive breakpoint anywhere, so this isn't specific to Review; it's a design-wide gap that Review's fixed 250+320(min)+360px columns simply happen to expose first.

**Fix:** Either (a) let the three Review columns shrink with `min-width:0` and a real `flex-basis` instead of hard `width`s, with a lower floor, or (b) change `.lp-main{overflow-x:hidden}` to `auto` so at minimum the content becomes reachable via horizontal scroll below the design-target width, or (c) add a breakpoint that stacks the three columns vertically under ~1100px.

### D-4 — Medium — a11y — Primary action buttons fail WCAG AA text contrast
**File:** `app/ui/app.css:40` (`--orange:#EF5A1E` light / `app/ui/app.css:55` `--orange:#FF6C36` dark) used as the background for white (`#fff`) text on `#btn-export-top`, `#btn-browse`, and the inline "study packs" highlight span (`app/ui/index.html:33-35, 72, 79`)

**Repro:** Compute contrast for `#btn-export-top` computed `color`/`backgroundColor` in both themes.

**Evidence measured:** `{"color":"rgb(255,255,255)","bg":"rgb(255,108,54)","ratio":"2.82"}` (measured identically on two separate reads after the light-theme toggle had settled). A ratio of 2.82:1 fails WCAG AA for normal text (needs 4.5:1) **and** fails the large-text/bold threshold (needs 3:1) that this 13.5-15px bold button label would need to qualify for. This affects the app's primary CTA (Export) and the Home page's main "Browse for video" button — the two most-used controls in the app.

**Fix:** Either darken the orange (e.g. toward `--orange-ink` `#C6430E`/`#FF8A5C`) for button fills, or switch the fill/text pairing so the accent is used as a border/icon color with a higher-contrast solid fill behind white text.

### D-5 — Low — UX-logic — Schedule dialog accepts past dates and times with no validation
**File:** `app/ui/app.js:261-286` (`scheduleJobDialog`), specifically line 265 (`<input id="sched-when" type="datetime-local" ...>` has no `min` attribute — contrast with `quiz-count-custom`/`flash-count-custom` inputs elsewhere in the same file which do set `min`/`max`, e.g. lines 731 and 880) and line 278-279 (`onClick` only checks `if (!when) { toast('Pick a date and time'); return true; }` — no comparison against `Date.now()`).

**Evidence:** Static code read (I could not drive this dialog live: it is only invoked from a queued job's action menu at `app.js:1574`, and the static demo's `queue-list` has 0 children, so there is no queued job to click "Schedule" on — this part is `UNVERIFIABLE-STATICALLY` for live interaction, but the missing validation is directly visible in the source and not in question).

**Fix:** Add `min="<current local datetime>"` to the `sched-when` input and a client-side guard in the `Schedule` action handler that toasts a specific "Pick a time in the future" message when `new Date(when) <= new Date()`, before calling `schedule_job`.

## 4. Not covered / needs a live backend or human eyes

- **Processing queue interactions** (FIFO reorder, Run Now, remove) — the static demo's `queue-list` renders 0 items; there is no code path in the shipped UI to synthesize a fake queue without a backend `queue_changed` signal.
- **Local scheduling live flow** — dialog only reachable via a queued job's menu (see D-5); missed-schedule policy behavior (run-on-open / skip / ask) needs the actual Python bridge and app restart semantics.
- **Pause/resume/retry-stage** live transitions, and the **Interrupted/Needs-attention** cards — these require a real job stuck mid-pipeline or a reconciled "running→Interrupted" state at startup, neither of which exist in the static mock.
- **Notifications** — the "Test notification" button, and all 6 toggles' actual effect on OS notifications, require the desktop shell (`app/desktop/bridge.py` `Backend`) and cannot be triggered from a static page.
- **Groq online transcription** — key storage (Windows Credential Manager), "Test key", and actual online transcription require network + real credentials; explicitly out of scope per the task's prohibited-actions rules (no credential entry) and per the static-server limitation.
- **Smart Study / Ollama install flow, CUDA pack install, app auto-update download/install** — all gated behind real external processes (Ollama detection, GitHub release checks, binary downloads) that only exist with the desktop shell running.
- **Visual/pixel-level review** (actual screenshots) — the Browser pane in this session could not composite a frame (`computer{action:"screenshot"}` errored: "the Browser pane is not displayed, so the page is not compositing frames"). All spacing/contrast findings above are backed by `getComputedStyle`/`getBoundingClientRect` numbers, not a human visual pass; a sighted follow-up pass on the running desktop app is recommended to catch purely visual issues (icon alignment, subpixel rendering, animation smoothness) that DOM measurement can't see.
- **Focus mode** (`#btn-focus`/`#focus-pill`), **Study → Notes** fuzzing, and **drag-and-drop file import** onto the dropzone were not exercised this pass due to time budget, not because they're unreachable — a follow-up pass should cover them.
- **Old `lecturepack/ui/` PySide pages** — correctly excluded per instructions; not tested.
