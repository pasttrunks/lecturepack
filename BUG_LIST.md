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

*None open.*

## DEFERRED (known, accepted for now)

### BUG-07 — Preview-mode demo job seed appears when no bridge is attached   ⚪️ DEFERRED
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
- **Current fix:** none needed; accepted as preview-mode behaviour. If it ever becomes
  user-visible in a real launch (e.g. a bridge-connect race showing demo cards for a
  frame), reopen as a real bug and gate the seed behind a `?preview=1` flag instead.
- **Verification:** live app on a throwaway profile showed 0 jobs — seed not user-visible.
- **Files:** `app/ui/app.js:57-63`.

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
- **Remaining (pre-existing, not caused by this fix):** three light-theme near-misses on
  SOFT backgrounds at 10-12px — `Done` badge 3.62, `Running` 4.02, muted meta 4.35 (light
  `--muted` on `--panel` is 3.84). These are AA-large-only. Fixing them means darkening
  `--muted` and the badge inks, which shifts a lot of surface, so it is left for an owner
  decision rather than changed unilaterally (`app.css` is marked "do not improve values").
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
- **Remaining work (tracked, not a regression):** there is still **no backend signal for
  disk usage** — `grep` found no `storage`/`disk_usage` in `bridge.py` or
  `engine_adapter.py`. The widget stays hidden until one is added; wire
  `storage-widget`/`storage-label`/`storage-bar` when it is.
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
7. **Inline styles beat class rules.** The design markup carries layout as inline styles,
   so any responsive override of it needs `!important` (BUG-03). A media query that "does
   nothing" is usually this.
