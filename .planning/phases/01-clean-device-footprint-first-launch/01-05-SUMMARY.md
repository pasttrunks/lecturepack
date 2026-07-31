---
phase: 01-clean-device-footprint-first-launch
plan: 05
subsystem: desktop-shell
tags: [windows, qt, single-instance, ipc, taskbar-icon, ctypes, qlocalserver]

# Dependency graph
requires:
  - phase: 01-clean-device-footprint-first-launch
    provides: "Plan 01-01's packaged/installed build (used for Task 1's D-20 diagnosis) and Plan 01-06's deferred bootstrap worker (Backend.__init__ no longer blocks, but the guard must still precede MainWindow() construction regardless)"
provides:
  - "app/desktop/single_instance.py: SingleInstanceGuard (QLocalServer/QLocalSocket) satisfying D-18 (raise-and-focus, never silent exit) and D-19 (guard runs before MainWindow()/Backend.__init__)"
  - "main.py: APP_USER_MODEL_ID + _set_app_user_model_id(), called as the first statement of main() (D-20)"
  - "MainWindow.raise_and_focus(): the single focus mechanism reused by both the tray-click handler and the guard's raise signal"
  - "Non-silent window-icon and tray-icon guards via _report_missing_icon() (D-21)"
  - "lecturepack.iss AppUserModelID on the two non-uninstall [Icons] entries, sharing one #define with main.py's literal"
  - "01-FINDINGS-icon.md: Task 1's completed D-20 diagnosis (candidate (b) ruled out on the installed build; candidate (a) is the only remaining explanation, though the symptom did not reproduce)"
affects: [01-08-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "QLocalServer/QLocalSocket single-instance guard: probe-then-listen, unconditional QLocalServer.removeServer() before listening to reclaim a crashed prior instance's endpoint, fail-open to 'primary' on any exception"
    - "One-word fixed-sentinel local IPC: RAISE_SENTINEL compared by byte equality only, MAX_MESSAGE_BYTES-bounded reads, no json.loads/eval/exec/pickle anywhere near peer-supplied bytes"
    - "Outbound QLocalSocket lifetime: a locally-created socket must be kept referenced past the function that wrote to it until its disconnected signal fires, or Python's GC tears it down mid-drain and silently discards an already-flushed write (see Issues Encountered)"
    - "Ctypes OS-integration with silent degrade, same shape as win_integration.py's PowerRequester.set_awake(): lazy import, win32-only guard, bare except: pass"

key-files:
  created:
    - app/desktop/single_instance.py
    - tests/test_single_instance_identity.py
  modified:
    - app/desktop/main.py
    - app/packaging/lecturepack.iss
    - .planning/phases/01-clean-device-footprint-first-launch/deferred-items.md

key-decisions:
  - "Tasks 2 and 3 landed in one commit, per 01-05-PLAN.md's own explicit instruction ('prefer landing both in one commit') since Task 2's main() ordering already reserves the call site Task 3's AUMID call fills."
  - "The D-21 icon-resolution logic (_resolve_icon_path, _report_missing_icon) was extracted to module-level functions and unit-tested directly, plus AST-structural tests proving MainWindow.__init__ wires them into both guard sites correctly (body calls setWindowIcon/tray.setIcon and no report; orelse calls _report_missing_icon and not the icon setter). No test in this repo constructs a real MainWindow (it requires a live QWebEngineView, WebChannel handshake, and Backend's worker thread) — extracting and testing the pure logic plus structural wiring was judged safer and more reliable than being the first test to attempt that, per CONTEXT.md's discretion over internal test organization."
  - "The IPC probe deliberately runs after QApplication(sys.argv) is constructed, not before, per 01-RESEARCH.md Open Question 1's recommendation that QLocalSocket likely needs QCoreApplication machinery. This still satisfies D-19 because everything slow (Backend.__init__'s worker thread) lives behind the later MainWindow() construction line."
  - "MainWindow.raise_and_focus() adds showNormal()-if-minimized ahead of the existing raise_()/activateWindow() sequence already used by _on_notification_clicked, and _on_notification_clicked was updated to call the new shared method instead of duplicating the two calls -- one focus mechanism, not two, per the plan's explicit instruction."

requirements-completed: []

coverage:
  - id: D1
    description: "A second launch raises and focuses the running instance's window and returns 0 without constructing MainWindow, instead of exiting silently (D-18)"
    verification:
      - kind: unit
        ref: "tests/test_single_instance_identity.py::test_secondary_signal_existing_delivers_sentinel_and_fires_callback_once"
        status: pass
      - kind: manual_procedural
        ref: "backstop — installed-build two-process proof owned by 01-08-PLAN.md"
        status: unknown
    human_judgment: true
    rationale: "The plan's own must_haves mark the installed-build two-process raise-and-focus proof as verification: backstop, explicitly deferred to Plan 01-08. Only the in-process guard mechanism is unit-proven here."
  - id: D2
    description: "The guard runs in main() before MainWindow()/Backend.__init__'s deferred assess() worker (D-19)"
    verification:
      - kind: unit
        ref: "tests/test_single_instance_identity.py::test_single_instance_guard_acquire_precedes_mainwindow_construction"
        status: pass
    human_judgment: false
  - id: D3
    description: "The local IPC channel accepts exactly one fixed sentinel, never deserializes peer bytes, bounds every read, degrades to primary on IPC failure, and reclaims a stale endpoint (T-01-05-01..04)"
    verification:
      - kind: unit
        ref: "tests/test_single_instance_identity.py (non_sentinel_payload, mutation_sentinel_equality_loosened, no_deserialization_primitives, connection_handler_reads_at_most_max_message_bytes, acquire_fails_open_to_primary_when_the_ipc_primitive_raises, acquire_reclaims_a_stale_endpoint_via_removeserver)"
        status: pass
    human_judgment: false
  - id: D4
    description: "SetCurrentProcessExplicitAppUserModelID is called as the first statement of main(), win32-only, degrading silently on failure, and matches lecturepack.iss's AppUserModelID byte-for-byte on exactly the two non-uninstall [Icons] entries (D-20)"
    verification:
      - kind: unit
        ref: "tests/test_single_instance_identity.py (set_app_user_model_id_calls_shell32_on_win32, set_app_user_model_id_is_a_noop_off_windows, set_app_user_model_id_swallows_ctypes_exceptions, set_app_user_model_id_called_before_register_asset_scheme, aumid_literal_matches_lecturepack_iss_byte_for_byte, aumid_set_on_exactly_two_icons_entries_not_the_uninstall_entry, aumid_literal_contains_no_version_digit_sequence)"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-20's actual cause was determined on the packaged/installed build before any fix was applied (Task 1, completed by the orchestrator)"
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-icon.md"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both the window-icon and tray-icon os.path.exists guards report the resolved path instead of silently continuing when the .ico is missing (D-21)"
    verification:
      - kind: unit
        ref: "tests/test_single_instance_identity.py (report_missing_icon_writes_the_resolved_path_to_stderr, report_missing_icon_tray_tag_writes_to_stderr, window_icon_guard_reports_when_missing_and_sets_icon_when_present, tray_icon_guard_reports_when_missing_and_sets_icon_when_present)"
        status: pass
    human_judgment: false
  - id: D7
    description: "On the installed build, the LecturePack icon is visible in the window title bar and taskbar"
    verification:
      - kind: manual_procedural
        ref: "backstop — owned by 01-08-PLAN.md; 01-FINDINGS-icon.md already recorded that the symptom did not reproduce during Task 1's diagnosis"
        status: unknown
    human_judgment: true
    rationale: "must_haves marks this verification: backstop explicitly. This plan's fix is justified by mechanism (no AUMID call existed) and the absence of a competing cause, not by a reproduced-then-fixed symptom -- 01-08 owns the installed-build proof."

# Metrics
duration: ~45min (Tasks 2-3; Task 1's checkpoint:human-verify diagnosis was run separately by the orchestrator and is documented in 01-FINDINGS-icon.md)
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 5: Single-Instance Guard & Taskbar Icon Summary

**QLocalServer/QLocalSocket single-instance guard with a one-word fixed sentinel, `SetCurrentProcessExplicitAppUserModelID` declared before any window/UI, and non-silent icon-resolution guards — landed after Task 1's completed diagnosis ruled out the `setWindowIcon` guard and left the missing AUMID as the only remaining, but unreproduced, explanation.**

## Performance

- **Duration:** ~45 min (Tasks 2-3)
- **Completed:** 2026-07-31
- **Tasks:** 3 (Task 1 was a `checkpoint:human-verify` completed by the orchestrator before this executor ran; Tasks 2-3 executed here)
- **Files modified:** 4 (2 new, 2 modified) plus this SUMMARY and a `deferred-items.md` addition

## Accomplishments

- **D-18/D-19 — single-instance guard.** `app/desktop/single_instance.py`'s `SingleInstanceGuard` probes a `QLocalServer`/`QLocalSocket` endpoint right after `QApplication(sys.argv)` is constructed and strictly before `MainWindow()`. A second launch that finds the endpoint owned sends one fixed literal (`RAISE_SENTINEL = b"RAISE"`) and returns `0` immediately — no silent exit. The primary's registered raise handler calls `MainWindow.raise_and_focus()` (new: `showNormal()` if minimized, `raise_()`, `activateWindow()`), the same method `_on_notification_clicked` was updated to call instead of duplicating the sequence.
- **D-19 ordering verified structurally, not assumed.** A static AST test (`test_single_instance_guard_acquire_precedes_mainwindow_construction`) reads `main()`'s actual source order and asserts `guard.acquire()` precedes `MainWindow()` — since `Backend.__init__` (per Plan 01-06) starts its deferred `assess()` worker at the end of construction, a guard placed later would have let a second process sit invisible for the whole pending-admission window.
- **T-01-05-01..04 — the IPC channel is minimal and unforgiving.** The wire protocol is one fixed ASCII literal compared by byte equality; every read is bounded to `MAX_MESSAGE_BYTES` (64); no `json.loads`/`eval`/`exec`/`pickle` appears anywhere near peer-supplied bytes (statically asserted); a stale endpoint from a crashed prior instance is unconditionally reclaimed via `QLocalServer.removeServer()` before listening; and any IPC primitive failure (exception during connect/listen) fails open to `"primary"` so an OS-integration failure can never block startup.
- **D-20 — AppUserModelID declared, justified by mechanism, not by reproduction.** `main.py` gained `APP_USER_MODEL_ID = "LecturePack.LecturePack"` and `_set_app_user_model_id()`, called as `main()`'s first statement (before `register_asset_scheme()`), following `win_integration.py`'s `PowerRequester.set_awake()` ctypes idiom exactly: lazy `import ctypes`, `sys.platform == "win32"` guard, bare `except Exception: pass`. Per Task 1's completed diagnosis (`01-FINDINGS-icon.md`), candidate (b) — the silently-guarded `setWindowIcon` — was measured and ruled out on the installed build (`WM_GETICON`/class-icon handles all populated); the missing AUMID is the only remaining explanation, but the owner's blank-taskbar-icon symptom did not reproduce during diagnosis. **This SUMMARY does not claim the symptom was observed and fixed** — the fix is justified by mechanism (no AUMID call existed anywhere in `app/`) and the absence of a competing cause.
- **`lecturepack.iss` matches byte-for-byte.** A new `#define AppUserModelID "LecturePack.LecturePack"` is referenced by the Start Menu and desktop `[Icons]` entries (not the uninstall entry, which points at `{uninstallexe}`, a different process). A test reads both `main.py` and `lecturepack.iss` as text and asserts the literal appears identically in both.
- **D-21 — the missing-icon path is no longer silent.** Both `MainWindow.__init__`'s window-icon and tray-icon `os.path.exists` guards now call `_report_missing_icon(tag, path)` in their `else` branch, printing to stderr (the same sink `Backend.log_asset_error` ultimately writes to — no project logger exists yet). The present-icon path is unchanged: `setWindowIcon`/`tray.setIcon` still fire and no report is produced.

## Task Commits

Task 1 (`checkpoint:human-verify`, D-20 diagnosis) was completed by the orchestrator before this executor ran:

1. **Task 1: Determine the actual taskbar-icon cause on the packaged build (D-20)** — `253bc71` (docs) — see `01-FINDINGS-icon.md`

Tasks 2 and 3 landed together, per the plan's own instruction to prefer one commit since Task 2's `main()` ordering already reserves Task 3's AUMID call site:

2. **Tasks 2-3: Single-instance guard + AppUserModelID + non-silent icon path** — `16f7a6c` (feat)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `app/desktop/single_instance.py` (new) — `SINGLE_INSTANCE_ENDPOINT`, `RAISE_SENTINEL`, `MAX_MESSAGE_BYTES`, `SingleInstanceGuard` (`acquire`, `signal_existing`, `set_raise_handler`, `release`).
- `app/desktop/main.py` — `APP_USER_MODEL_ID`, `_set_app_user_model_id()`, `_resolve_icon_path()`, `_report_missing_icon()`, `MainWindow.raise_and_focus()`, updated `_on_notification_clicked()` and the two icon guards in `MainWindow.__init__`, and `main()`'s new ordering (AUMID first, guard right after `QApplication`, raise handler registered before `show_when_ready()`, `guard.release()` added to the existing `_on_quit` handler).
- `app/packaging/lecturepack.iss` — new `#define AppUserModelID`, referenced on the two non-uninstall `[Icons]` entries.
- `tests/test_single_instance_identity.py` (new) — 28 tests covering both tasks' behaviors (see coverage table above).
- `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md` — recorded a pre-existing, unrelated `tests/test_package_footprint.py` failure surfaced by this plan's full-suite run (see Issues Encountered).

## Decisions Made

- Tasks 2 and 3 committed together — see key-decisions in frontmatter.
- D-21's icon-resolution logic was tested via extracted pure functions plus AST-structural wiring checks rather than constructing a real `MainWindow` — see key-decisions in frontmatter for the full reasoning (no existing test in this repo constructs a full WebEngine `MainWindow`, and this plan judged that too fragile/risky a precedent to set as a side effect of D-21).
- The single-instance probe runs after `QApplication(sys.argv)`, matching 01-RESEARCH.md's Open Question 1 guidance — see key-decisions in frontmatter.
- `raise_and_focus()` consolidated onto one focus mechanism reused by both the tray-click handler and the guard — see key-decisions in frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `signal_existing()`'s outbound socket silently dropped its own just-written sentinel**
- **Found during:** Task 2, writing `tests/test_single_instance_identity.py::test_secondary_signal_existing_delivers_sentinel_and_fires_callback_once`
- **Issue:** The first implementation wrote `RAISE_SENTINEL`, flushed, then called `sock.disconnectFromServer()` followed immediately by `sock.close()`, and `sock` was a local variable. In the single-process test harness (and, on inspection, plausibly on a real two-process launch too, since the calling process exits immediately afterward) this raced: `disconnectFromServer()` only *schedules* a graceful close once buffered writes drain, but the local `sock` reference could be torn down (via `close()`, or via Python GC once the function returned) before that drain completed on the Qt event loop, silently discarding the just-written sentinel before the primary ever read it. Diagnosed with a series of isolated repro scripts (`QLocalServer`/`QLocalSocket` pairs with and without an explicit `close()`, and with `sock` kept alive at different scopes) that pinned the exact failure to socket lifetime, not to the sentinel logic itself.
- **Fix:** Removed the redundant `sock.close()` call, and — since a bare local variable alone still wasn't sufficient once the function returned — added `self._pending_outbound`, a list that keeps the socket referenced until its `disconnected` signal fires and removes it. This is the same "keep it alive until its own signal says it's done" shape already used for inbound connections (`self._live_connections`).
- **Files modified:** `app/desktop/single_instance.py`
- **Verification:** `tests/test_single_instance_identity.py::test_secondary_signal_existing_delivers_sentinel_and_fires_callback_once` and `test_mutation_sentinel_equality_loosened_is_caught_by_this_test` both pass; re-ran the full `tests/test_single_instance_identity.py` file (28/28) after the fix.
- **Committed in:** `16f7a6c` (part of the Task 2-3 commit; this was found and fixed before the first commit, not as a follow-up)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for D-18 to actually work — the bug would have made every real second-launch raise silently fail while `acquire()`/`signal_existing()` still both reported success, exactly the kind of "looks fine, doesn't work" failure this plan exists to close. No scope creep.

## Issues Encountered

- **Full-suite run surfaced two new, unrelated failures.** `pytest -q` (full suite) produced 1036 passed, 9 failed, 1 skipped — 30 more passed than the 1006-passed baseline (28 from this plan's new test file, plus 2 that were already passing and are unrelated to the count math) and 2 more failed than the 7 pre-existing failures documented in `deferred-items.md`. The 2 new failures are `tests/test_package_footprint.py::test_audit_pruned_tree_reports_all_six_present` and `::test_cli_tree_and_assert_pruned_passes_on_pruned_synthetic_tree`, both hardcoding an expectation of 6 Qt-pruning cut targets. `BUG_LIST.md`'s BUG-27 entry (landed before this plan started, per the orchestrator's brief) reduced `PRUNABLE_QT_COMPONENTS` in `app/packaging/build.py` from 6 to 4 (removing `Qt6Qml.dll`/`Qt6Quick.dll`, which turned out to be load-bearing link-time dependencies of `Qt6WebEngineCore`/`Qt6WebChannel`), but `tests/test_package_footprint.py`'s fixture and assertions were never updated to match. Confirmed unrelated to this plan: neither `test_package_footprint.py` nor `PRUNABLE_QT_COMPONENTS`/`build.py` are in Plan 01-05's `files_modified`, and this plan touches no packaging-footprint or Qt-pruning code. Logged to `deferred-items.md`, not fixed, per the scope-boundary rule.
- The `signal_existing()` socket-lifetime bug above (see Deviations) took the most debugging time in this plan — isolating it required several standalone repro scripts outside pytest to separate "does the Qt mechanism work at all" from "does the test harness pump events correctly," since the same code path behaves differently depending on whether the socket object is kept referenced by the caller.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 01-08 owns two backstop proofs this plan cannot self-certify:** (1) on the installed build, launching while an instance is running raises and focuses the existing window and no second process survives; (2) on the installed build, the LecturePack icon is visible in the window title bar and taskbar button. Both are marked `verification: backstop` in this plan's `must_haves` and in the coverage table above — they are NOT claimed as verified here, only as unit-proven at the guard/mechanism level.
- `01-FINDINGS-icon.md` (Task 1, already complete) is the binding diagnosis 01-08 should reference: the owner's blank-icon symptom did not reproduce on this beta-7 post-cut build, so if it recurs during 01-08's physical verification, that is new evidence about beta-7 specifically (not a contradiction of this plan's fix, which was justified by mechanism).
- The `tests/test_package_footprint.py` stale-fixture issue (see Issues Encountered / `deferred-items.md`) is available for whichever future slice owns `PRUNABLE_QT_COMPONENTS`/packaging-footprint tests to pick up; it does not block this phase's remaining plans.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: app/desktop/single_instance.py
- FOUND: tests/test_single_instance_identity.py
- FOUND: app/desktop/main.py
- FOUND: app/packaging/lecturepack.iss
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-icon.md
- FOUND commit: 253bc71 (Task 1, orchestrator-run)
- FOUND commit: 16f7a6c (Tasks 2-3)
- CONFIRMED: `pytest tests/test_single_instance_identity.py -q` — 28/28 pass
- CONFIRMED: `pytest tests/test_main_window_structure.py tests/test_win_integration.py tests/test_adapter_startup.py tests/test_webview_packaging.py -q` — 30/30 pass
- CONFIRMED: full `pytest -q` — 1036 passed, 9 failed, 1 skipped (1006 baseline + 28 new; 7 pre-existing failures unchanged; 2 new failures confirmed unrelated to this plan and logged to `deferred-items.md`; zero failures caused by this plan)
