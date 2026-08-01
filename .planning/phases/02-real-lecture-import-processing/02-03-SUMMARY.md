---
phase: 02-real-lecture-import-processing
plan: 03
subsystem: ui
tags: [webengine, javascript, slide-detection, yt-dlp, media-fetch, pytest, regression-test]

# Dependency graph
requires:
  - phase: 02-real-lecture-import-processing (Plan 01)
    provides: EngineRegistry-based whisper gate and persist_runtime_health(exe_paths=...) seeding that lets start_processing() reach controller.run_pipeline() on a clean install
provides:
  - LP.state.pipelineRunning — a JS-side flag tracking whether a normal (non-demo) job is actively processing, set from pipeline_changed's stage states and cleared on the terminal status_changed label (Done/Failed)
  - Extended slide-sensitivity lock (guidedDemoSensitivityLocked() || LP.state.pipelineRunning) covering both renderSlideDetectionPreset's visual disable and setSlideDetectionPreset's early-return guard
  - tests/test_phase2_settings_paste.py — 10 regression tests (9 pass, 1 skip) proving the D-08 lock structure and the D-09 Paste Link probe/download/import/cancel/availability chain
affects: [02-04, real lecture import & processing acceptance gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JS-side 'is a normal job running' flag derived from pipeline_changed's stage array (any stage not \"done\"), with an explicit clear on the terminal status_changed label -- because the Python failure path (_on_pipeline_failed) never re-emits pipeline_changed with the failed stage cleared, so stage-derived truth alone cannot detect failure"
    - "Structural JS regression tests via brace-counted function-body extraction (parse app.js as text, not execute it) for logic that has no Python-observable side effect"

key-files:
  created:
    - tests/test_phase2_settings_paste.py
  modified:
    - app/ui/app.js

key-decisions:
  - "Chose status_changed's terminal label (\"Failed\"/\"Done\") as the clear-signal for pipelineRunning instead of the plan's suggested \"pipeline_completed\"/\"pipeline_failed\" lpBridge.on registrations, because those signal names do not exist as JS-side handlers -- grepping app.js and engine_adapter.py confirmed _on_pipeline_completed/_on_pipeline_failed are Python method names, not emitted signal names. status_changed already fires with label \"Done\" (from _on_pipeline_completed) and label \"Failed\" (from _on_pipeline_failed) at exactly the right moments, so it is the correct real hook rather than inventing a new signal."
  - "Set pipelineRunning=true inside pipeline_changed by checking for any stage whose state is not \"done\", rather than requiring an explicit \"active\" state, so the flag is also true while stages sit \"pending\" between transitions (matches the plan's intent that the lock covers the whole run, not just moments where a stage is mid-progress)."
  - "Added a demoLocked intermediate variable and a locked-reason-aware title string (\"Guided demo uses its fixed reliable setting.\" vs \"Setting is locked while processing runs.\") so the disabled button's tooltip never misattributes a normal-processing lock to the guided demo -- a small UX correctness improvement in the same spirit as D-08's own goal (no misleading state)."

patterns-established: []

requirements-completed: [SC-10, SC-11, WI-06, WI-08]

coverage:
  - id: D1
    description: "Slide sensitivity preset buttons are visually disabled during normal (non-demo) processing, and clicking a disabled button no-ops via setSlideDetectionPreset's extended early return, so a running job's snapshotted preset can never be silently changed underneath it (D-08)"
    requirement: "SC-10"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_sensitivity_lock_function_checks_pipeline_running"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_set_slide_detection_preset_guards_against_pipeline_running"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_pipeline_running_flag_declared_in_state"
        status: pass
      - kind: other
        ref: "grep -n pipelineRunning app/ui/app.js (plan's own automated verify command; confirmed match)"
        status: pass
    human_judgment: true
    rationale: "The structural tests prove the lock's wiring (both call sites reference the same flag), but observing the button actually disable/re-enable live during a real processing run, and confirming a click during that window truly does not persist to config.json, is a browser/packaged-app behavior this unit-level plan does not exercise end-to-end."
  - id: D2
    description: "The guided demo's own sensitivity lock (guidedDemoSensitivityLocked) is byte-identical to before this plan -- this change adds a parallel check, not a rewrite of the demo path"
    requirement: "SC-10"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_guided_demo_lock_function_is_unchanged"
        status: pass
    human_judgment: false
  - id: D3
    description: "Output mode has no Process-screen UI control and is therefore already non-editable mid-run by omission (D-08's second half) -- verified by code inspection, no code change made"
    requirement: "SC-10"
    verification:
      - kind: other
        ref: "Code comment added at app/ui/app.js above guidedDemoSensitivityLocked() documenting the finding; no Process-screen output-mode control exists to test against"
        status: pass
    human_judgment: true
    rationale: "This is an absence-of-a-control claim (no UI element exists to change output mode mid-run). It was confirmed by reading the onboarding overlay and start_processing() call sites, matching the plan's own RESEARCH.md Q6 finding, but proving a negative (no control was added later) is better suited to periodic UI review than an automated test."
  - id: D4
    description: "The Paste Link probe -> media_probe signal chain works: probe_media_url resolves via MediaFetcher.probe and emits ok:true with the probe's metadata"
    requirement: "WI-06"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_probe_media_url_emits_media_probe_signal"
        status: pass
    human_judgment: false
  - id: D5
    description: "The Paste Link download -> import handoff works: a successful download calls import_video with the downloaded file's path"
    requirement: "WI-06"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_import_media_url_on_success_calls_import_video"
        status: pass
    human_judgment: false
  - id: D6
    description: "BUG-18 regression guard: a cancelled download does not call import_video, even when the cancel is only observable via a MediaFetchCancelled exception (not a progress-hook race)"
    requirement: "WI-06"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_import_media_url_on_cancel_does_not_import"
        status: pass
    human_judgment: false
  - id: D7
    description: "When yt-dlp is unavailable, media_link_support emits media_link_state with available=false, and the JS handler hides #btn-paste-link in response (D-04 discretion)"
    requirement: "WI-08"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_media_link_state_hides_button_when_unavailable"
        status: pass
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_media_link_state_js_handler_hides_button"
        status: pass
    human_judgment: false
  - id: D8
    description: "yt-dlp availability check (_media_fetch_available) returns true when yt_dlp is importable"
    requirement: "WI-06"
    verification:
      - kind: unit
        ref: "tests/test_phase2_settings_paste.py#test_media_fetch_available_returns_true_when_yt_dlp_importable"
        status: unknown
    human_judgment: true
    rationale: "yt_dlp is not installed in this dev venv, so the test pytest.skip()s rather than running. The plan explicitly anticipated this (\"If yt_dlp is not installed in the test venv, mark this test as pytest.mark.skipif\"); this is an environment gap, not a code defect -- but it means the assertion has not actually executed in this environment and a human/CI-with-yt-dlp should confirm it once."

duration: ~15min
completed: 2026-08-01
status: complete
---

# Phase 2 Plan 3: Sensitivity Lock and Paste Link Verification Summary

**Extended the slide-sensitivity preset lock to cover normal processing (D-08) via a new LP.state.pipelineRunning flag driven by pipeline_changed/status_changed, and added 10 regression tests (9 pass, 1 environment-skip) proving both the lock and the already-wired Paste Link probe/download/import/cancel chain (D-09).**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-08-01T08:08:59-04:00 (approximate, from commit timestamps)
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 new)

## Accomplishments

- Added `LP.state.pipelineRunning` (default `false`) to `app/ui/app.js`, set inside the `pipeline_changed` handler whenever the payload's stages contain any entry not yet `"done"`, and explicitly cleared inside `status_changed` when the terminal label is `"Failed"` or `"Done"`. The Python-side `_on_pipeline_completed` already sets every stage to `"done"` before its final `pipeline_changed` emit, so success clears the flag naturally too; failure needed the explicit `status_changed` hook because `_on_pipeline_failed` never re-emits `pipeline_changed` with the failed stage cleared.
- Extended `renderSlideDetectionPreset()`'s `locked` computation and `setSlideDetectionPreset()`'s early-return guard to `guidedDemoSensitivityLocked() || LP.state.pipelineRunning`, so a click during normal processing now truly no-ops instead of only rendering disabled while still persisting the change via `lpBridge.call('set_setting', ...)`.
- Split the button's `title` tooltip by lock reason (`"Guided demo uses its fixed reliable setting."` for the demo path vs. `"Setting is locked while processing runs."` for the new normal-processing path) so the UI never attributes a normal-run lock to the guided demo.
- Added a code comment directly above `guidedDemoSensitivityLocked()` recording the D-08 finding that output mode has no Process-screen control at all (onboarding sets `LP.state.onbMode` once; `start_processing` reads it once) — confirming that half of D-08 is already satisfied by omission, with no code change required.
- Created `tests/test_phase2_settings_paste.py` with 10 tests: 4 structural tests parsing `app.js` (lock computation references `pipelineRunning`, the early-return guard does too, the demo lock function body is unchanged, the state flag defaults to `false`) and 6 tests exercising the real `LecturePackAdapter` link methods against a fake backend + fake `MediaFetcher` (yt-dlp availability — skipped, no yt_dlp in this venv; probe → `media_probe` emission; download → `import_video` handoff; BUG-18 cancel-does-not-import regression guard; `media_link_state` hiding the button both in the Python emission and the JS handler).
- Full suite: 1062 passed, 7 failed, 2 skipped (1053 baseline + 9 new passing tests + 1 new skip; the same 7 pre-existing `release_trust`/signing-key failures documented in `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md`; zero new failures).

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock slide sensitivity during normal processing** - `88b7514` (fix)
2. **Task 2: Paste Link wiring verification tests** - `a15d067` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `app/ui/app.js` — `LP.state.pipelineRunning` added; `renderSlideDetectionPreset()` and `setSlideDetectionPreset()` extended to check it alongside `guidedDemoSensitivityLocked()`; `pipeline_changed` sets the flag from stage states and `status_changed` clears it on the terminal label; code comment documents the output-mode-by-omission finding.
- `tests/test_phase2_settings_paste.py` — 10 new regression tests (structural D-08 lock checks + D-09 Paste Link fake-backend tests), new file.

## Decisions Made

- Used `status_changed`'s terminal label (`"Failed"`/`"Done"`) as the clear-signal for `pipelineRunning` instead of the plan's suggested `pipeline_completed`/`pipeline_failed` `lpBridge.on` registrations, since grepping confirmed those are Python method names (`_on_pipeline_completed`, `_on_pipeline_failed`), not emitted JS signal names — no such `lpBridge.on` handlers exist. `status_changed` already fires with the right label at exactly the right moments.
- Derived `pipelineRunning` from "any stage not `done`" (covering both `"pending"` and `"active"` states) rather than only `"active"`, so the lock holds for the whole run, matching the plan's intent.
- Added a lock-reason-aware tooltip (demo vs. processing) as a small proactive UX correctness fix in the same spirit as D-08, since the pre-existing tooltip text would have been misleading once a second lock source existed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the plan's assumed signal names for clearing pipelineRunning**
- **Found during:** Task 1, while locating the `pipeline_completed`/`pipeline_failed` `lpBridge.on` registrations the plan referenced
- **Issue:** The plan instructed clearing the new flag "when pipeline_completed or pipeline_failed fires (find these handlers by grepping for those signal names in the lpBridge.on registrations)". Grepping `app/ui/app.js` for `pipeline_completed|pipeline_failed` found zero matches — no such `lpBridge.on` registrations exist. Cross-checking `app/desktop/engine_adapter.py` confirmed `_on_pipeline_completed`/`_on_pipeline_failed` are internal Python method names, not `_emit()`'d signal names; the JS side never receives a signal by either name.
- **Fix:** Used the real, existing hooks instead: `pipeline_changed`'s stage-state check (which naturally clears on success, since `_on_pipeline_completed` sets every stage to `"done"` before its final emit) plus an explicit clear inside the existing `status_changed` handler when the label is `"Failed"` (or `"Done"`, as a redundant safety net).
- **Files modified:** `app/ui/app.js` (same file the plan already scoped)
- **Verification:** `grep -n "pipelineRunning" app/ui/app.js` and the combined `guidedDemoSensitivityLocked.*pipelineRunning` check both pass per the plan's own automated verify command; the full test suite (1062 passed / 7 pre-existing failures) confirms no regression.
- **Committed in:** `88b7514` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — plan referenced non-existent signal names, corrected to the real wiring)
**Impact on plan:** No scope creep. The fix stays entirely within `app/ui/app.js` as scoped, and achieves the exact behavior the plan specified (lock clears on completion or failure) via the code that actually exists.

## Issues Encountered

- The pre-commit hook's `code-review-graph` panel-print step threw the same cosmetic `UnicodeEncodeError` (cp1252 console codec) documented in `02-01-SUMMARY.md` and `02-02-SUMMARY.md`'s Issues Encountered, on both task commits. The commits themselves completed successfully (confirmed via `git log`); no action needed.
- `yt_dlp` is not installed in this dev venv, so `test_media_fetch_available_returns_true_when_yt_dlp_importable` skips rather than asserting. This was anticipated by the plan itself ("If yt_dlp is not installed in the test venv, mark this test as pytest.mark.skipif with a clear message") and is recorded as a `human_judgment: true` coverage item (D8) above, not a defect.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-08's sensitivity-lock gap is closed for both the demo and normal-processing paths, with structural regression tests guarding the wiring; a real browser/packaged-app observation of the button disabling live during an actual run remains a natural candidate for the phase's later physical/UI verification gate (see D1's `human_judgment` rationale above).
- D-09's Paste Link chain is now proven end-to-end at the unit level (probe, download success, BUG-18 cancel guard, and the yt-dlp-unavailable hide-the-button path), closing out the plan's independent verification goal without touching any production code in that area.
- Plan 02-04 can build on both a verified sensitivity lock and a verified Paste Link wiring without re-deriving either.
- Full suite: 1062 passed, 7 failed (same 7 pre-existing `release_trust`/signing-key failures; zero new failures), 2 skipped (1 pre-existing + 1 new yt-dlp-unavailable skip in this venv).

---
*Phase: 02-real-lecture-import-processing*
*Completed: 2026-08-01*

## Self-Check: PASSED

All modified/created files (`app/ui/app.js`, `tests/test_phase2_settings_paste.py`) exist on disk; both task commits (`88b7514`, `a15d067`) verified present in `git log --oneline --all`.
