---
phase: 01-clean-device-footprint-first-launch
plan: 06
subsystem: desktop-bridge
tags: [qt, threading, startup, bridge, admission-contract, first-run]

# Dependency graph
requires:
  - phase: 01-clean-device-footprint-first-launch
    provides: "Plan 01-03's FIRST_RUN_CHECKLIST_ITEMS, build_first_run_checklist, ConfigManager.setup_acknowledged()/persist_setup_acknowledged(), and the parallelized RuntimeBootstrapService._validate_full"
provides:
  - "Backend.__init__ returns without running any subprocess probe (D-06) — assessment moves to a daemon worker thread started at the end of __init__"
  - "ADMISSION_PENDING fail-closed sentinel assigned as the first attribute in __init__, keeping every _ADMISSION_GUARDED_OPERATIONS name withheld for the whole pending window"
  - "bootstrap_progress/bootstrap_complete Qt signals reporting per-component checking/resolved progress and the final admission payload, using the BUG-09-corrected QTimer.singleShot(0, self, ...) context-object marshal"
  - "get_bootstrap() extended with bootstrap_pending, validation_path, setup_acknowledged, checklist — the full wire contract Plan 01-07 consumes"
  - "acknowledge_setup() slot persisting only a boolean through ConfigManager (D-14/D-16)"
affects: [01-07-PLAN.md, 01-08-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "threading.Thread(daemon=True) + QTimer.singleShot(0, self, callback) for worker-to-main-thread marshaling (BUG-09's corrected _emit_soon pattern, reused rather than reinvented)"
    - "Fail-closed sentinel assigned as the very first mutable attribute in __init__, before any collaborator that could observe it"
    - "Best-effort progress reporting wrapped separately from the admission call itself, so a progress-reporting failure never blocks or corrupts the real assess() result"

key-files:
  created:
    - tests/test_bootstrap_deferral.py
  modified:
    - app/desktop/bridge.py
    - app/ui/bridge.js
    - tests/test_adapter_startup.py
    - tests/test_runtime_repair.py

key-decisions:
  - "validation_path is predicted from RuntimeBootstrapService._requires_full's exact inputs (real identity hash, real inventory resolution) on the worker thread before assess() runs — not a cheaper heuristic proxy. This duplicates one identity-hash pass per launch (assess() will also compute it), accepted because it is still off the main thread and correctness (never silently predicting 'light' when the real path is 'full') matters more than the extra hash pass."
  - "When the bootstrap service is not cheaply introspectable (missing .runtime_root/.inventory_resolver — true of every test double and any future alternate implementation), _predict_validation_path falls back to the conservative 'full' prediction, per the plan's own stated tradeoff (a wasted checking overlay is cosmetic; a suppressed overlay on a genuinely slow launch reproduces the D-08 defect)."
  - "get_bootstrap()'s checklist field is 5 placeholder {id, verdict: 'pending', detail: ''} rows while bootstrap_pending is true, not null — matching this plan's own acceptance criterion that checklist always has exactly 5 canonical-order items, pending or resolved, so the UI never needs to special-case a null checklist."
  - "ui_ready is removed from _ADMISSION_GUARDED_OPERATIONS. The UI calls it immediately after the WebChannel handshake, which now happens while admission is still pending; if it stayed guarded, the real method (which records _ui_ready_seen) would never run, and the deferred on_ui_ready/startup_check work would never be dispatched once HEALTHY completion later arrives. Its own body already no-ops when self._adapter is None, so removing the guard does not open a new capability."
  - "ffmpeg_ffprobe/whisper_runtime/bundled_model resolved-progress is reported at assess() completion, not at an invented per-probe instant — RuntimeBootstrapService exposes no per-probe callback and D-10 forbids weakening the real staged whisper-cli transcription to fabricate one. windows_version and data_directory (host-only, independent of assess()) ARE reported the moment they resolve, before assess() is even called."
  - "acknowledge_setup is NOT added to _ADMISSION_GUARDED_OPERATIONS: its entire effect is one ConfigManager boolean write, it touches no engine collaborator, and the checklist screen it acknowledges is only reachable once HEALTHY. Recorded as a code comment at the guard-list boundary."

patterns-established:
  - "_run_bootstrap_worker's three-stage try/except structure: progress-reporting failures are swallowed independently of the admission call, and an admission-call failure still produces a safe non-HEALTHY RuntimeBootstrapResult so bootstrap_complete is always eventually emitted (T-01-06-03) — a template for any future worker that must never leave the UI in a permanent pending state."

requirements-completed: []

coverage:
  - id: D1
    description: "Backend.__init__ returns without running any subprocess probe; assess() runs on a worker thread; the admission guard is fail-closed for the whole pending window (D-06)"
    verification:
      - kind: unit
        ref: "tests/test_bootstrap_deferral.py (11 tests matching -k pending, plus test_construction_returns_while_a_slow_assessment_is_still_running)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deferred assessment worker emits itemized bootstrap_progress per FIRST_RUN_CHECKLIST_ITEMS id (checking then resolved) and one bootstrap_complete, using the BUG-09-corrected QTimer.singleShot(0, self, ...) marshal, proven functionally (thread identity) and statically (no bare two-argument form)"
    verification:
      - kind: unit
        ref: "tests/test_bootstrap_deferral.py::test_bootstrap_progress_emits_checking_then_resolved_for_all_five_ids, ::test_completion_handler_observes_the_main_thread_identity, ::test_no_bare_two_argument_qtimer_singleshot_in_bridge, ::test_raising_worker_still_produces_a_completion_and_a_non_healthy_result"
        status: pass
    human_judgment: false
  - id: D3
    description: "HEALTHY completion constructs the adapter/updater exactly once, attaches the window/tray, and dispatches deferred ui_ready work exactly once regardless of ordering (T-01-06-06)"
    verification:
      - kind: unit
        ref: "tests/test_bootstrap_deferral.py::test_healthy_completion_dispatches_ready_work_once_for_both_orderings_ready_first, ::test_healthy_completion_dispatches_ready_work_once_for_both_orderings_completion_first, ::test_attach_window_is_called_with_window_and_tray_after_healthy_completion"
        status: pass
    human_judgment: false
  - id: D4
    description: "get_bootstrap() extended with bootstrap_pending, validation_path, setup_acknowledged, checklist (8 keys total); acknowledge_setup() persists only a boolean through ConfigManager and touches no repair/updater collaborator (D-14/D-16)"
    verification:
      - kind: unit
        ref: "tests/test_bootstrap_deferral.py (Task 3 section, 16 tests) plus tests/test_adapter_startup.py::test_setup_required_bootstrap_reuses_canonical_admission_snapshot"
        status: pass
    human_judgment: false

# Metrics
duration: ~2h30m
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 6: Deferred Bootstrap Assessment Summary

**Window-first startup: `Backend.__init__` no longer blocks on `RuntimeBootstrapService.assess()` — admission runs on a worker thread with itemized `bootstrap_progress` signals per checklist component, a fail-closed `ADMISSION_PENDING` guard for the whole pending window, and an extended `get_bootstrap()` contract (`bootstrap_pending`, `validation_path`, `setup_acknowledged`, `checklist`) plus an `acknowledge_setup()` slot for Plan 01-07 to consume.**

## Wire Contract for Plan 01-07

`get_bootstrap()` now returns 8 keys (the original `theme`, `version`, `runtime_health_state`, `setup_required`, plus):

- **`bootstrap_pending`** (`bool`) — `true` until the deferred worker's completion has been marshalled back onto the main thread, for both eventual outcomes (HEALTHY and SETUP_REQUIRED). **This is the field 01-07 must branch on** — not a string comparison against `runtime_health_state` (which legitimately reads `"PENDING"` while pending; that string never appears in user-facing copy, only as this internal routing value). Concretely: `app/ui/app.js`'s `if (b.runtime_health_state !== 'SETUP_REQUIRED') startNormalBridgeActivity();` must become `if (!b.bootstrap_pending && b.runtime_health_state === 'HEALTHY') startNormalBridgeActivity();` (or equivalent gating on `bootstrap_pending`) — otherwise `startNormalBridgeActivity()`'s `list_ollama_models`/`media_link_support` calls (both admission-guarded) would fire during the pending window and surface a spurious setup-required diagnostics payload behind the honest progress panel, which is the exact hazard the plan-checker flagged.
- **`validation_path`** (`"full"` or `"light"`) — available even while `bootstrap_pending` is true, predicted from `RuntimeBootstrapService._requires_full`'s real identity/inventory inputs (not a probe). Drives whether 01-07 renders the `checking` overlay at all (D-07): full path → render it; light path → render nothing, preserving today's near-instant warm-launch feel.
- **`setup_acknowledged`** (`bool`) — from `ConfigManager.setup_acknowledged()`, unchanged contract from Plan 01-03.
- **`checklist`** (5-item list, canonical `FIRST_RUN_CHECKLIST_ITEMS` order, always) — while pending: `{"id": <id>, "verdict": "pending", "detail": ""}` for all five, so the UI never needs a null-check special case for the checking overlay's initial paint. Once resolved: the real `build_first_run_checklist()` output (`{"id", "verdict": "ready"|"needs_attention", "detail"}`).

`bootstrap_progress` (new signal, JSON string): `{"id": <one of FIRST_RUN_CHECKLIST_ITEMS>, "state": "checking"|"resolved", "detail": <str>}`, emitted once "checking" then once "resolved" per component, in canonical order. `windows_version` and `data_directory` resolve independently and typically arrive first (they don't depend on `assess()` at all); `ffmpeg_ffprobe`, `whisper_runtime`, and `bundled_model` all resolve together at `assess()` completion, because `RuntimeBootstrapService` exposes no per-probe callback and D-10 forbids fabricating one by weakening the real staged whisper-cli transcription. `bootstrap_complete` (new signal, JSON string): the exact `get_bootstrap()` payload, emitted exactly once per assessment (including the exception-fallback path).

`acknowledge_setup()` (new slot, `@Slot(result=str)`): persists only a boolean via `ConfigManager.persist_setup_acknowledged()`, returns the refreshed `get_bootstrap()` JSON. Idempotent. Not admission-guarded.

## Accomplishments

- **Task 1 — Fail-closed pending admission state (D-06).** `ADMISSION_PENDING = "PENDING"` and `_pending_result()` introduced. `Backend.__init__` assigns `self.runtime_health_result = _pending_result()` as the very next statement after `ConfigManager()` construction — before `_runtime_diagnostics` or anything else — closing the exact hazard the plan named: an unset attribute makes `__getattribute__`'s guard fall through and open every `_ADMISSION_GUARDED_OPERATIONS` name. The synchronous `.assess()` call and the `if HEALTHY:` adapter/updater block were removed from `__init__` entirely.
- **Task 2 — Deferred assessment worker with itemized progress (D-08, D-09, BUG-09).** `_start_bootstrap_async()`/`_run_bootstrap_worker()` run assessment on a daemon `threading.Thread`. Every worker-to-main-thread handoff uses `QTimer.singleShot(0, self, lambda: ...)` — the corrected three-argument form `engine_adapter._emit_soon` already established for BUG-09, reused rather than reinvented. `bootstrap_progress`/`bootstrap_complete` signals added to `Backend` and registered in `app/ui/bridge.js`'s `SIGNALS` array. `_on_bootstrap_complete()` promotes admission exactly once (mirroring `_on_repair_event`'s HEALTHY-promotion shape), attaches the window to the adapter (closing the gap where `main.py`'s own attempt runs before the adapter exists and is swallowed by its bare `except`), and dispatches the deferred `on_ui_ready`/`startup_check`/`fallback_notice` work exactly once via two flags (`_ui_ready_seen`, `_ui_ready_dispatched`) regardless of whether `ui_ready()` or completion happens first. `ui_ready` was removed from `_ADMISSION_GUARDED_OPERATIONS` (see Decisions) so it can always record readiness during the pending window. A worker exception is caught at the admission-call boundary and still produces a safe `SETUP_REQUIRED` result with `bootstrap_complete` emitted (T-01-06-03) — progress-reporting failures are caught independently and never block the real `assess()` call.
- **Task 3 — Extended `get_bootstrap()` contract and `acknowledge_setup()` (D-07, D-13, D-14, D-16).** `get_bootstrap()` gained `bootstrap_pending`, `validation_path`, `setup_acknowledged`, `checklist`. `validation_path` is cached on the instance (`self.validation_path`, default `"full"` until the worker predicts it) so it is stable and available even before assessment resolves. `acknowledge_setup()` added as a new `@Slot(result=str)`, deliberately excluded from the admission guard with the reasoning recorded in a code comment at the guard-list boundary.

## Task Commits

Given the depth of cross-task coupling in this plan (Task 2's worker reuses Task 1's guard sentinel; Task 3's `get_bootstrap` keys read Task 2's cached `validation_path`; all three tasks share one `Backend.__init__` rewrite, one `bridge.js` signal registration, and one incrementally-extended test file per the plan's own read_first cross-references), splitting into three independently-working commits would have required fabricating throwaway intermediate states (e.g., a "Task 1 only" commit where admission never resolves because the worker doesn't exist yet). This was judged a worse outcome than one atomic, fully-tested commit — see Deviations below.

1. **Tasks 1-3 (fail-closed pending state, deferred worker with itemized progress, extended get_bootstrap contract)** - `1c7f516` (feat)

## Files Created/Modified

- `app/desktop/bridge.py` — `ADMISSION_PENDING`, `_pending_result()`, `_pending_checklist()`, `Backend.bootstrap_progress`/`bootstrap_complete` signals, `Backend._start_bootstrap_async()`/`_run_bootstrap_worker()`/`_predict_validation_path()`/`_emit_progress()`/`_emit_host_only_resolved()`/`_emit_dependent_resolved()`/`_on_bootstrap_complete()`/`_dispatch_ui_ready_work()`, rewritten `__init__`/`ui_ready`/`get_bootstrap`, new `acknowledge_setup()` slot, `ui_ready` removed from `_ADMISSION_GUARDED_OPERATIONS`.
- `app/ui/bridge.js` — `bootstrap_progress`/`bootstrap_complete` added to the `SIGNALS` array.
- `tests/test_bootstrap_deferral.py` (new) — 32 tests covering all three tasks' behaviors, plus a static BUG-09 regression guard and a real (non-stubbed) `RuntimeBootstrapService`/`ConfigManager` integration test proving `validation_path` correctly predicts `"full"` on a fresh profile and `"light"` after a complete prior admission.
- `tests/test_adapter_startup.py` — three synchronous-completion assertions now pump the Qt event loop via `qtbot.waitUntil` (assess() is no longer synchronous); `ui_ready` removed from the guarded-call sweep (no longer guarded); `_RuntimeConfig` test double gained `resolve_data_dir()`/`setup_acknowledged()` since every `Backend` construction now probes them; `test_setup_required_bootstrap_reuses_canonical_admission_snapshot` updated for the 8-key payload.
- `tests/test_runtime_repair.py` — `test_setup_bridge_rejects_stale_repair_confirmation` now points `ConfigManager`'s default data dir at `tmp_path`, since it was the one existing `Backend(None)` construction using a *real* `ConfigManager` without already isolating the data directory, and the new worker unconditionally probes data-directory writability.

## Decisions Made

- `validation_path` prediction uses the real `_requires_full` inputs (identity hash + inventory), not a cheap heuristic — see key-decisions in frontmatter for the full tradeoff reasoning.
- `checklist` is 5 `verdict: "pending"` placeholder rows while pending, never `null` — matches this plan's own acceptance criterion and avoids a UI null-check special case.
- `ui_ready` removed from `_ADMISSION_GUARDED_OPERATIONS` — see key-decisions; this is the backend-side half of the hazard the plan-checker flagged (the JS-side half, gating `startNormalBridgeActivity()` on `bootstrap_pending`, is Plan 01-07's to implement per the Wire Contract section above).
- `ffmpeg_ffprobe`/`whisper_runtime`/`bundled_model` resolved-progress is honestly reported at `assess()` completion rather than an invented per-probe instant (D-09) — `RuntimeBootstrapService` has no per-probe callback and D-10 forbids weakening the real staged transcription to fabricate one. `windows_version`/`data_directory` resolve independently and are reported the moment they're known.
- `acknowledge_setup` is not admission-guarded — reasoning recorded as a code comment at the call site per the plan's explicit request not to leave a ~90-name guard-list omission silent.
- Tasks 1-3 committed as one atomic unit rather than three, given the depth of cross-task attribute/structural coupling (see Task Commits above).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `ui_ready` removed from `_ADMISSION_GUARDED_OPERATIONS`**
- **Found during:** Task 2 implementation
- **Issue:** The plan's binding constraints named the `list_ollama_models`/`media_link_support` hazard from `startNormalBridgeActivity()` explicitly, but the same class of hazard applies to `ui_ready` itself: it was already in the guarded set, and the UI calls it immediately after the WebChannel handshake — which now happens while admission is pending. Left guarded, every `ui_ready()` call during the pending window would hit the guard lambda instead of the real method, so `self._ui_ready_seen` would never be set, and the deferred `on_ui_ready`/`startup_check` work built in this same task would never dispatch once HEALTHY completion later arrived — a permanent regression of the update-check and adapter-ready wiring on every cold, deferred-assessment launch.
- **Fix:** Removed `"ui_ready"` from `_ADMISSION_GUARDED_OPERATIONS`; its own body already no-ops when `self._adapter is None`, so removing the guard opens no new capability.
- **Files modified:** `app/desktop/bridge.py`
- **Verification:** `tests/test_bootstrap_deferral.py::test_healthy_completion_dispatches_ready_work_once_for_both_orderings_ready_first` proves the ready-work dispatches correctly when `ui_ready()` is called during the pending window.
- **Committed in:** `1c7f516` (part of the single task commit)

**2. [Rule 1 - Bug] Two pre-existing tests updated for the new async contract**
- **Found during:** Full-suite verification after Tasks 1-3
- **Issue:** `tests/test_adapter_startup.py` had three tests asserting `Backend._adapter`/`runtime_health_result` synchronously right after `Backend(None)` construction, and a guarded-call sweep including `ui_ready` — both invalid now that assessment is asynchronous and `ui_ready` is no longer guarded. Separately, `tests/test_runtime_repair.py::test_setup_bridge_rejects_stale_repair_confirmation` used a real, unpatched `ConfigManager()`; the new worker's data-directory-writability probe would have touched the real default `~/LecturePackData` on every test run.
- **Fix:** The three `test_adapter_startup.py` tests now pump the Qt event loop via `qtbot.waitUntil(lambda: backend.runtime_health_result.state != bridge.ADMISSION_PENDING)` before asserting; the guarded-call tuple no longer includes `ui_ready`; the shared `_RuntimeConfig` test double gained `resolve_data_dir()` (routed at the shared OS temp dir) and `setup_acknowledged()`. `test_setup_bridge_rejects_stale_repair_confirmation` now monkeypatches `constants.DEFAULT_DATA_DIR`/`cm.DEFAULT_DATA_DIR` at `tmp_path`, mirroring the existing `_temp_data_dir` fixture pattern already established elsewhere in the same file.
- **Files modified:** `tests/test_adapter_startup.py`, `tests/test_runtime_repair.py`
- **Verification:** Both files pass in full; full-suite run shows 944 passed / 7 failed (912 baseline + 32 new tests in this plan; same 7 pre-existing failures, zero new failures — see Out-of-scope section).
- **Committed in:** `1c7f516` (part of the single task commit)

---

**Total deviations:** 2 auto-fixed (1 missing-critical, 1 bug/test-compatibility)
**Impact on plan:** Both were necessary consequences of implementing D-06/D-08 as specified — no scope creep, no architectural change beyond what the plan already called for.

## Issues Encountered

- `resolve_inventory()` requires at least one `bin/ggml-cpu-*.dll` entry present or it raises `RuntimeInventoryError`; the real-`RuntimeBootstrapService` integration tests for `validation_path` initially failed until the test fixture included a `ggml-cpu-avx2.dll` stand-in file. Resolved by using `canonical_inventory(("ggml-cpu-avx2.dll",))` when building the test fixture's runtime root.
- `pytest-qt`'s `qtbot.waitUntil` requires the callback to return `None`/`True`/`False` strictly (not an arbitrary truthy value); several `lambda: some_list` predicates needed wrapping as `lambda: bool(some_list)`.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 01-07 (the `checking`/`checklist` UI overlay states in `app/ui/app.js`/`index.html`/`app.css`) can now consume the full wire contract documented above: `bootstrap_progress`/`bootstrap_complete` signals, and `get_bootstrap()`'s `bootstrap_pending`/`validation_path`/`setup_acknowledged`/`checklist` fields. The critical implementation note for 01-07: gate `startNormalBridgeActivity()` on `bootstrap_pending`, not on a `runtime_health_state !== 'SETUP_REQUIRED'` string comparison (see Wire Contract section).
- Plan 01-08 (physical clean-machine evidence gate) can now measure real cold vs. warm launch timing against this deferred-window-first startup — this plan's own worker-thread timing is necessarily proven with stubbed/synthetic `assess()` calls (per Plan 01-03's own scoping precedent), not real hardware.
- No stubs, no invented data: every emitted `bootstrap_progress`/`checklist` verdict traces to either a real host check (`windows_version`, `data_directory`) or `RuntimeBootstrapService`'s own evidence (`ffmpeg_ffprobe`, `whisper_runtime`, `bundled_model`).

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: app/desktop/bridge.py (ADMISSION_PENDING, _pending_result, bootstrap_progress/bootstrap_complete signals, acknowledge_setup present)
- FOUND: app/ui/bridge.js (bootstrap_progress/bootstrap_complete in SIGNALS)
- FOUND: tests/test_bootstrap_deferral.py (32 tests)
- FOUND commit: 1c7f516
- CONFIRMED: `pytest tests/test_bootstrap_deferral.py -x -k pending` — 11/11 pass (≥6 required)
- CONFIRMED: `pytest tests/test_bootstrap_deferral.py tests/test_emit_soon_threading.py -x` — 35/35 pass
- CONFIRMED: `pytest tests/test_bootstrap_deferral.py -x` — 32/32 pass (≥20 required)
- CONFIRMED: `pytest tests/test_setup_gate_repair.py tests/test_adapter_startup.py tests/test_runtime_diagnostics.py tests/test_storage_signal.py tests/test_webview_settings_bridge.py tests/test_first_run_checklist.py -x` — 65/65 pass
- CONFIRMED: `pytest tests/test_update_integration.py tests/test_ollama_and_repair.py -x` — 22/22 pass
- CONFIRMED: full `pytest` run — 944 passed, 7 failed (912 baseline + 32 new; same 7 pre-existing failures documented in deferred-items.md; zero new failures)
