---
phase: 01-clean-device-footprint-first-launch
plan: 07
subsystem: ui
tags: [ui, webengine, reducer, first-run-checklist, accessibility, startup]

# Dependency graph
requires:
  - phase: 01-clean-device-footprint-first-launch
    provides: "Plan 01-03's FIRST_RUN_CHECKLIST_ITEMS/VERDICT_READY/VERDICT_NEEDS_ATTENTION and ConfigManager.setup_acknowledged(); Plan 01-06's get_bootstrap() extended payload (bootstrap_pending, validation_path, setup_acknowledged, checklist), bootstrap_progress/bootstrap_complete signals, and acknowledge_setup() slot"
provides:
  - "RuntimeSetupGateModel gains checking/checklist states, four new snapshot fields, and progress()/acknowledge()/toChecklist() transitions -- the seven pre-existing states and their tests are byte-identical"
  - "#runtime-setup-overlay gains the checking and checklist <section> markup with all ten new element ids, each with a real writer in app.js (BUG-04 audit passes)"
  - "firstRunRow()/renderChecking()/renderChecklist() render the five canonical rows from FIRST_RUN_ROWS, badges coloured entirely via the audited .lp-state[data-state] class rule"
  - "startNormalBridgeActivity() gated on bootstrap_pending (never a runtime_health_state string) behind a once-flag shared across both admission paths"
  - "acknowledge() wired to both Continue and Skip, calling acknowledge_setup and closing via a new shared closeOverlay() helper; syncDemoAdmission() now requires the acknowledged flag (D-17)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Anti-flicker pacing resolved lazily from the real --motion-normal custom property (no new one-off duration), applied identically under reduced motion"
    - "Badge inline style restricted to layout-only longhands (border-width/style/radius, padding, font, white-space, flex) so the .lp-state[data-state] class rule supplies colour -- an inline colour declaration would beat any class rule regardless of specificity"
    - "Shared closeOverlay() helper factored out of closeReady() so acknowledge() reuses the identical restore-inert-and-return-focus sequence"

key-files:
  created:
    - tests/test_first_run_checklist_ui.py
  modified:
    - app/ui/app.js
    - app/ui/index.html

key-decisions:
  - "The anti-flicker hold and per-row resolution timers live in the DOM controller (not the reducer): the reducer's progress() transition holds no timer and applies checkProgress immediately; RuntimeSetupGate.progress() paces only the re-render of a flip to 'resolved'. This is safe because nothing else re-renders the checking rows while state==='checking' except this one paced entry point."
  - "The checklist row container needed flex-wrap:wrap and the label needed flex:1;min-width:0 beyond the plan's literal enumerated cssText list -- both are necessary for the two-line clamp and the needs-attention advisory sentence to actually render correctly inside a flex row, rather than overflowing or squeezing onto one line."
  - "runtime-checking-heading, runtime-checklist-heading, and runtime-checklist-body ship with tabindex=-1 / an id (per the plan's markup) but are deliberately never the state's focus target and never rewritten by JS -- documented inline in render()'s targets-map comment rather than silently omitted, satisfying both the BUG-04 writer audit and the plan's own Focal Point rule (Exit/Continue are the real focus targets)."
  - "acknowledge() is idempotent via both a state guard (state !== 'checklist') and an explicit acknowledgeInFlight re-entrancy flag, since native button-disable alone only protects against real click events, not a hypothetical programmatic re-invocation."

patterns-established:
  - "checkingRowSentence()/clearCheckingTimers() as the controller-owned pacing primitives any future itemized-progress state can reuse."

requirements-completed: []

coverage:
  - id: D1
    description: "RuntimeSetupGateModel extended with checking/checklist states, four new snapshot fields, and progress()/acknowledge()/toChecklist() transitions; all seven pre-existing states and their tests are unchanged (D-11)"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist_ui.py (Task 1 section, 14 tests) plus tests/test_setup_gate_repair.py (6 tests, unmodified)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Overlay markup gains the checking/checklist sections with all ten new element ids, each with a real writer in app.js (BUG-04 audit); badges coloured only via the audited .lp-state[data-state] class rule; app/ui/app.css has a net change of zero lines"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist_ui.py (Task 2 section, 15 tests, including the writer-audit test and the badge-property-allowlist test)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Bootstrap routing gated on bootstrap_pending with a once-flag for startNormalBridgeActivity(); acknowledge()/closeReady()/syncDemoAdmission() implement D-12/D-16/D-17; completion routes through the same admit() as the initial bootstrap"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist_ui.py (Task 3 section, 13 tests) plus tests/test_guided_tour.py, tests/test_webview_settings_bridge.py, tests/test_demo_session_isolation.py (unmodified, all pass)"
        status: pass
    human_judgment: true
    rationale: "The four UI-SPEC backstop rows (reduced-motion timing, focus/keyboard containment, real-width layout, whisper slow-notice text) require a real packaged Qt WebEngine session and are explicitly deferred to Plan 01-08's installed-build session, not claimed here."

# Metrics
duration: ~50min
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 7: First-Run Checklist UI (checking/checklist states) Summary

**Two new reducer states (`checking`, `checklist`) layered onto the existing `RuntimeSetupGateModel`/`RuntimeSetupGate` overlay — itemized honest progress for the five D-13 checks, then a calm Ready/Needs-Attention checklist gating the guided demo — with zero new CSS and zero regression across the seven pre-existing failure-gate states.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-07-31T13:33:05Z (first task commit)
- **Completed:** 2026-07-31T13:53:29Z (last task commit)
- **Tasks:** 3
- **Files modified:** 2 (`app/ui/app.js`, `app/ui/index.html`); `app/ui/app.css` touched with a confirmed net-zero line diff; 1 test file created

## Accomplishments

- **Task 1 — Reducer extension.** `RuntimeSetupGateModel` gained `validationPath`/`acknowledged`/`checklist`/`checkProgress` closure fields, `progress()`/`acknowledge()`/`toChecklist()` transitions, and a rewritten `bootstrap()` that routes a full-path pending payload to `checking` (D-08) and a healthy-unacknowledged payload to `checklist` (D-12), while a repair-in-progress or already-acknowledged payload is unaffected. `reset()` preserves `acknowledged` since it mirrors a persisted `config.json` fact (D-16), not in-flight operation state. `FIRST_RUN_ROWS`/`FIRST_RUN_VERDICT_STATES` module-level constants key the five friendly labels/live-region sentences to the backend's canonical `FIRST_RUN_CHECKLIST_ITEMS` order (cross-file test asserts the match). All seven pre-existing states and `tests/test_setup_gate_repair.py`'s six tests pass unmodified.
- **Task 2 — Markup and renderers.** `index.html` gained the `checking`/`checklist` `<section>` siblings with all ten new element ids, following the overlay's inline-style house convention. `firstRunRow()`/`renderChecking()`/`renderChecklist()` render the five rows from the fixed `FIRST_RUN_ROWS` array (never from arrival order), with badges whose inline style is restricted to layout-only longhands so the audited `.lp-state[data-state]` class rule supplies the Ready/Needs-Attention/neutral colour. `render()` now hides the shared Exit control only for `checklist` and routes `checking`/`checklist` initial focus to Exit/Continue. The anti-flicker hold and whisper slow-notice threshold are module-level constants resolved from the real `--motion-normal` token. `app/ui/app.css` has a confirmed net change of zero lines.
- **Task 3 — Bootstrap routing, acknowledgement, demo gate.** `admit()` now routes on the reducer's resulting state (`checking`/`checklist`/`gate`/healthy-close/`ready`) instead of re-deriving branches from the raw payload. `startNormalBridgeActivity()` is gated on `bootstrap_pending` behind a once-flag shared across both admission paths (the initial `get_bootstrap()` call and the new `bootstrap_complete` signal, which routes through the same `admit()`). `acknowledge()` is wired to both `btn-runtime-continue` and `btn-runtime-skip` (byte-identical in effect per the owner-resolved UI-SPEC question), calls `acknowledge_setup`, advances the flag even on an empty resolution, and closes via a new shared `closeOverlay()` helper also used by `closeReady()`. `closeReady()` gained the repair-recovered-first-run branch (a healthy-but-unacknowledged post-repair success diverts to `checklist` instead of closing). `syncDemoAdmission()` now requires `view.acknowledged`, so every existing caller (initial admit, retry, repair-admitted event) inherits the D-17 demo gate for free. `RuntimeSetupGate.progress()` parses `bootstrap_progress` payloads defensively, updates the reducer immediately, and paces only the re-render of a flip to `resolved` by the anti-flicker hold; the whisper slow-notice timer and every per-row hold timer are cleared when the row resolves and when the state leaves `checking` (BUG-21 stale-timer lesson).

## Resolved anti-flicker hold value

`antiFlickerHoldMs()` reads `getComputedStyle(document.documentElement).getPropertyValue('--motion-normal')` and parses it via `parseFloat`, falling back to `160` only if the property is unreadable. `app.css` defines `--motion-normal:160ms`, so in the real app this resolves to `160` from the live token, not from the fallback literal — the fallback exists solely for a context where the stylesheet hasn't loaded (never expected in the packaged app). No new duration was introduced; the value is read, not invented.

## Whisper-runtime resolution instant

Per D-09's honesty requirement (carried over from Plan 01-06's own recorded decision), `windows_version` and `data_directory` resolve independently the moment their own `bootstrap_progress` events arrive; `ffmpeg_ffprobe`, `whisper_runtime`, and `bundled_model` all resolve together at the backend's `assess()` completion, because `RuntimeBootstrapService` exposes no per-probe callback. This plan's UI layer does not fabricate an earlier resolution instant for any of the three — each row's "resolved" mark is taken directly from its own `bootstrap_progress` event, whenever the backend actually emits it, with only the anti-flicker *hold* pacing the visual flip (never advancing it early).

## Mutation-check result for the badge colour contract

`tests/test_first_run_checklist_ui.py::test_first_run_row_badge_declares_only_the_allowed_inline_properties` extracts `firstRunRow()`'s `badge.style.cssText` assignment and asserts the set of declared inline property names equals exactly `{border-width, border-style, border-radius, padding, font, white-space, flex}`. Adding `border-color`, `background`, `background-color`, `color`, or the `border` shorthand to that string — even alongside the allowed properties — changes the extracted property-name set and fails this test immediately, naming the exact regression the plan's Known Trap warns about (an inline colour declaration beats the `.lp-state[data-state]` class rule regardless of specificity).

## Task Commits

Each executed task was committed atomically:

1. **Task 1: Extend RuntimeSetupGateModel with the checking and checklist states** - `d81b97b` (feat)
2. **Task 2: Overlay markup and the row renderer for both new states** - `ea9713c` (feat)
3. **Task 3: Bootstrap routing, acknowledgement, and the demo gate** - `6daa275` (feat)

## Files Created/Modified

- `app/ui/app.js` — `FIRST_RUN_ROWS`, `FIRST_RUN_VERDICT_STATES`, `antiFlickerHoldMs()`/`ANTI_FLICKER_HOLD_MS`, `WHISPER_SLOW_NOTICE_MS` module-level constants; `RuntimeSetupGateModel` additions (`validationPath`/`acknowledged`/`checklist`/`checkProgress` fields, `progress()`/`acknowledge()`/`toChecklist()` transitions, rewritten `bootstrap()`, `reset()` preserving `acknowledged`); `STATES` gains `checking`/`checklist`; `RuntimeSetupGate` additions (`firstRunRow()`, `renderChecking()`, `renderChecklist()`, `closeOverlay()`, `acknowledge()`, `progress()`, `checkingRowSentence()`/`clearCheckingTimers()`, rewritten `admit()`/`closeReady()`/`syncDemoAdmission()`); `wireBridge()` gains the hoisted `startNormalBridgeActivity()` once-flag and `bootstrap_progress`/`bootstrap_complete` subscriptions; `lpBridge.ready()`'s bootstrap consumer gated on `bootstrap_pending`; `wire()` wires `btn-runtime-continue`/`btn-runtime-skip` to `acknowledge`.
- `app/ui/index.html` — two new `<section data-runtime-state>` siblings (`checking`, `checklist`) inside `#runtime-setup-overlay`, with all ten new element ids.
- `tests/test_first_run_checklist_ui.py` (new) — 42 tests across three sections mirroring the plan's own task boundaries: Task 1 (reducer, 14 node-executed + structural tests), Task 2 (markup/renderer, 15 structural + one node-executed tests), Task 3 (routing/acknowledgement/demo-gate, 13 structural + node-executed tests).

## Decisions Made

- Pacing lives entirely in the DOM controller (`RuntimeSetupGate.progress()`), not the reducer — see key-decisions in frontmatter for the safety argument (nothing else re-renders checking rows mid-state).
- `flex-wrap:wrap` on the row container and `flex:1;min-width:0` on the label are necessary additions beyond the plan's literal enumerated cssText list, required for the two-line clamp and the needs-attention advisory sentence to render correctly — see key-decisions.
- `runtime-checking-heading`/`runtime-checklist-heading`/`runtime-checklist-body` ship in markup per the plan but are intentionally never JS focus targets or writers; documented inline rather than silently satisfying the BUG-04 writer-audit test via an unexplained reference.
- `acknowledge()` guards re-entrancy with both a state check and an explicit in-flight flag.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Row container needed `flex-wrap:wrap`; label needed `flex:1;min-width:0`**
- **Found during:** Task 2 (writing `firstRunRow()`)
- **Issue:** The plan's literal enumerated cssText list for the row container (flex, centre alignment, space-between, 8px gap, row padding, 9px radius, min-width:0) has no `flex-wrap`, and the label's clamp declarations are `renderComponents()`'s exact single-element pattern, which was never a flex child before. Without `flex-wrap:wrap`, a needs-attention row's third (advisory-sentence) child would squeeze onto one line instead of wrapping below; without `flex:1;min-width:0` on the label, the two-line clamp would not actually take effect inside a flex row (a flex item's default `min-width:auto` prevents shrinking below content size), risking overflow past the badge.
- **Fix:** Added `flex-wrap:wrap` to the row container's cssText and `flex:1;min-width:0` to the label's cssText, both documented inline with the reasoning.
- **Files modified:** `app/ui/app.js`
- **Verification:** Visual/structural review of the constructed cssText strings; the badge's own separately-restricted cssText (the security-relevant property allowlist) is unaffected, since this fix only touches the row container and label.
- **Committed in:** `ea9713c` (Task 2 commit)

**2. [Rule 2 - Missing Critical] `btn-runtime-skip` needed a documented reference to pass the BUG-04 writer audit**
- **Found during:** Task 2, running the phase-level writer-audit verification script
- **Issue:** `btn-runtime-skip` exists in markup (Task 2) but its click-handler wiring is Task 3's scope; the writer-audit test (itself required by Task 2's own acceptance criteria) failed because the id had no writer yet at the end of Task 2.
- **Fix:** Added an honest inline comment near the checklist renderer explaining `btn-runtime-continue`/`btn-runtime-skip` are byte-identical in effect and share one `acknowledge()` handler wired in `wire()` (Task 3) — documenting a real, already-decided design fact rather than an unexplained placeholder reference.
- **Files modified:** `app/ui/app.js`
- **Verification:** `tests/test_first_run_checklist_ui.py::test_every_overlay_id_has_a_writer_in_app_js_except_the_static_label` passes; Task 3 then wires the real click handler, making the comment's forward reference accurate.
- **Committed in:** `ea9713c` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug-prevention, 1 missing-critical/sequencing)
**Impact on plan:** Both were minor, necessary technical completions of the plan's own literal instructions — no scope creep, no architectural change, no CSS added.

## Issues Encountered

None beyond the two auto-fixes above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 01-08 (physical clean-machine evidence gate) can now observe the four UI-SPEC backstop rows deferred here in a real packaged Qt WebEngine session: reduced-motion timing (per-row colour feedback resolving within `--motion-fast`, the aggregate bar jumping with no transition), focus/keyboard containment for `checking`/`checklist`, five-row layout at 1220px/820px/640px with no clipping, and the whisper slow-notice clause appearing on a genuinely slow check.
- No stubs: every rendered row/badge/live-region string traces to either a real backend field (`id`/`verdict`/`detail`/`checkProgress` marks) or this plan's own fixed friendly-copy tables (`FIRST_RUN_ROWS`, `CHECKLIST_WINDOWS_ADVISORY`), keyed to the backend's canonical list by a cross-file test.
- `app/ui/app.css` is untouched (net zero lines) — both new states are fully built from the pre-existing, already-audited `.lp-state`/`.lp-fill` vocabulary, so their reduced-motion and contrast behaviour is correct by inheritance, not by new rule authoring.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: app/ui/app.js
- FOUND: app/ui/index.html
- FOUND: tests/test_first_run_checklist_ui.py (42 tests)
- FOUND commit: d81b97b (Task 1)
- FOUND commit: ea9713c (Task 2)
- FOUND commit: 6daa275 (Task 3)
- CONFIRMED: `pytest tests/test_first_run_checklist_ui.py tests/test_setup_gate_repair.py tests/test_ui_tokens_motion_responsive.py tests/test_guided_tour.py tests/test_webview_settings_bridge.py tests/test_demo_session_isolation.py -q` — 97/97 pass
- CONFIRMED: `pytest tests/test_webview_beta3.py tests/test_webview_ui_fixes.py tests/test_content_hygiene.py -q` — 34/34 pass
- CONFIRMED: `git diff --numstat -- app/ui/app.css` — empty (net zero lines)
- CONFIRMED: overlay-id writer-audit one-liner — exit 0
- CONFIRMED: full `pytest` run — 1006 passed, 7 failed (same 7 pre-existing failures documented in deferred-items.md; zero new failures)
