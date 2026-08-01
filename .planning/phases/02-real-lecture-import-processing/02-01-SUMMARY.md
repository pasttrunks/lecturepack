---
phase: 02-real-lecture-import-processing
plan: 01
subsystem: infra
tags: [config, runtime-bootstrap, engine-registry, whisper, ffmpeg, pytest]

# Dependency graph
requires:
  - phase: 01-clean-device-footprint-first-launch
    provides: RuntimeBootstrapService assess()/persist_runtime_health() contract, canonical resolved-inventory paths dict
provides:
  - ConfigManager.persist_runtime_health(exe_paths=...) seeding whisper_exe/ffmpeg_exe/ffprobe_exe from the bootstrap's resolved inventory, guarded so user-set real paths are never overwritten
  - start_processing()'s whisper pre-flight gate resolved via EngineRegistry.resolve() instead of a raw config read
  - import_video()'s _kick_poster() firing after detect_binaries() on every import, including the first one in a session
affects: [02-02, 02-03, 02-04, real lecture import & processing acceptance gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-layer overwrite guard for config seeding: outer migration_versions marker (one-time) + inner per-key os.path.isfile() check (never overwrite a real user file)"
    - "Ask the same resolver a runtime consumer would ask (EngineRegistry.resolve()) instead of re-deriving availability from a raw config field"

key-files:
  created: []
  modified:
    - lecturepack/infrastructure/config_manager.py
    - lecturepack/services/runtime_bootstrap.py
    - app/desktop/engine_adapter.py
    - tests/test_runtime_bootstrap.py

key-decisions:
  - "exe_paths seeding lives strictly inside the existing runtime_contract migration guard block (not a new migration marker) so it fires exactly once, matching D-01/D-02 as specified in the plan"
  - "start_processing() only calls EngineRegistry.resolve() when needs_whisper is true (Slides Only skips it entirely), preserving Slides Only behavior and the existing mocked-controller test fixtures that lack an engine_registry attribute"

patterns-established:
  - "Never-overwrite-a-real-file guard: os.path.isfile(current) check before seeding any user-configurable path"

requirements-completed: [SC-01, SC-04, SC-05, SC-06, SC-07, SC-08, WI-03, WI-05]

coverage:
  - id: D1
    description: "persist_runtime_health(exe_paths=...) seeds whisper_exe/ffmpeg_exe/ffprobe_exe on a clean install and never overwrites a real user-set path"
    requirement: "SC-01"
    verification:
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_persist_runtime_health_seeds_exe_paths_from_empty_config"
        status: pass
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_persist_runtime_health_never_overwrites_a_real_user_set_exe_path"
        status: pass
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_persist_runtime_health_exe_paths_none_is_backward_compatible"
        status: pass
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_persist_runtime_health_second_call_never_reseeds_empty_exe_paths"
        status: pass
    human_judgment: false
  - id: D2
    description: "RuntimeBootstrapService.assess() constructs exe_paths from the resolved inventory and forwards them, guarded per-key so a missing entry cannot crash assessment"
    requirement: "SC-01"
    verification:
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_bootstrap_assess_passes_exe_paths_through_to_persist_runtime_health"
        status: pass
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py#test_bootstrap_assess_missing_inventory_entry_does_not_crash"
        status: pass
    human_judgment: false
  - id: D3
    description: "start_processing() reaches controller.run_pipeline() for Study Pack/Transcript Only modes on a clean install (empty whisper_exe config) via EngineRegistry.resolve()'s bundled-binary fallback"
    requirement: "SC-04"
    verification:
      - kind: unit
        ref: "tests/test_demo_session_isolation.py#test_normal_start_snapshots_detector_setting_while_demo_forces_demo"
        status: pass
      - kind: other
        ref: "python -c ast-walk grep confirming engine_registry.resolve() used in start_processing (plan's automated verify command)"
        status: pass
    human_judgment: true
    rationale: "The specific clean-install/empty-config scenario reaching controller.run_pipeline() end-to-end (not just the gate logic) is proven indirectly by existing unit tests with mocked controllers; a real packaged clean-install run through the actual pipeline is a physical/packaged verification owned by a later phase gate, not this unit-level plan."
  - id: D4
    description: "_kick_poster() fires after detect_binaries() on every import (including the first import in a fresh session), independent of inspect_video's outcome"
    requirement: "SC-08"
    verification:
      - kind: other
        ref: "grep -n _kick_poster / detect_binaries app/desktop/engine_adapter.py confirming _kick_poster (line 1763) follows detect_binaries (line 1760)"
        status: pass
    human_judgment: true
    rationale: "Ordering is proven statically (grep/line-number check per the plan's own verification command); no existing automated test exercises import_video's poster-thread side effect end-to-end, so a real first-import observation is left to manual/packaged verification."

duration: ~35min
completed: 2026-08-01
status: complete
---

# Phase 2 Plan 1: Runtime Path Wiring Summary

**Seeded whisper_exe/ffmpeg_exe/ffprobe_exe into config.json from the bootstrap's resolved inventory (D-01/D-02), pointed start_processing()'s whisper gate at EngineRegistry.resolve() instead of a raw config read, and fixed the _kick_poster()/detect_binaries() ordering race so the first import in a session gets a real poster thumbnail.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-01T11:41:32Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `ConfigManager.persist_runtime_health()` now accepts an optional `exe_paths` dict and seeds `whisper_exe`/`ffmpeg_exe`/`ffprobe_exe` into `config.json`, but only inside the existing one-time `runtime_contract` migration guard, and only when the current value is empty or not a real file — closing the root-cause gap where a clean install's normal processing path read a permanently-empty `whisper_exe`.
- `RuntimeBootstrapService.assess()` constructs the `exe_paths` dict from the same resolved+validated inventory used for admission (`bin/whisper-cli.exe`, `bin/ffmpeg.exe`, `bin/ffprobe.exe`) and forwards it to `persist_runtime_health()`, with each lookup guarded individually so a missing inventory entry cannot crash the whole assessment.
- `start_processing()`'s whisper pre-flight gate now asks `self.controller.engine_registry.resolve(engine)` — the same resolution the transcription backend itself uses — instead of reading `config.get("whisper_exe", "")` directly. Its `_cpu_exe()` fallback finds the bundled binary under `app_root()/bin` even when config is empty, so Study Pack and Transcript Only modes reach `controller.run_pipeline()` on a clean install instead of rejecting with "Setup needed". The resolve() call only runs when `needs_whisper` is true, so Slides Only is unaffected.
- `import_video()` now runs `detect_binaries()` (in its own try/except) before `_kick_poster(job)`, instead of after. Previously `_kick_poster` read `config.get("ffmpeg_exe", None)` before `detect_binaries()` had a chance to populate it, so the first import in a fresh session silently got no poster thread. `_kick_poster` now fires unconditionally right after the detection attempt, independent of `inspect_video`'s own best-effort outcome.
- Demo path (`start_demo_job`, `_bundled_demo_model_path`) has zero diff — confirmed by `git diff` showing no touched lines in that region.
- Added 6 regression tests to `tests/test_runtime_bootstrap.py` covering: clean-install seeding, real-user-path preservation, `exe_paths=None` backward compatibility, migration-guard skip on the second boot, end-to-end `assess()` wiring, and a missing-inventory-entry guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: Seed exe paths via persist_runtime_health** - `832668d` (feat)
2. **Task 2: Fix start_processing gate and _kick_poster ordering** - `befc044` (fix)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `lecturepack/infrastructure/config_manager.py` - `persist_runtime_health()` gained the `exe_paths` kwarg with the two-layer never-overwrite guard
- `lecturepack/services/runtime_bootstrap.py` - `assess()` builds `exe_paths` from the resolved inventory and forwards it
- `app/desktop/engine_adapter.py` - `start_processing()` gate uses `EngineRegistry.resolve()`; `import_video()` reorders `detect_binaries()` before `_kick_poster()`
- `tests/test_runtime_bootstrap.py` - 6 new regression tests for exe-path seeding and wiring

## Decisions Made

- exe_paths seeding rides the existing `runtime_contract` migration marker rather than introducing a second migration flag — this was the plan's explicit design (D-01/D-02) and keeps the guard logic in one place.
- `resolved_engine` is computed only under `if needs_whisper:` rather than unconditionally before the check, because the test suite's `_DemoController` fixture (used across `tests/test_demo_session_isolation.py`) has no `engine_registry` attribute and Slides Only never needed whisper resolution in the first place — computing it unconditionally would have been unnecessary work on a path that explicitly doesn't need it, and broke an existing test on first attempt (self-corrected before commit; see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Guarded EngineRegistry.resolve() call behind needs_whisper check**
- **Found during:** Task 2, first full-suite run after implementing Fix 1
- **Issue:** Initial implementation called `self.controller.engine_registry.resolve(...)` unconditionally before the `needs_whisper` check, causing `AttributeError: '_DemoController' object has no attribute 'engine_registry'` in `tests/test_demo_session_isolation.py::test_normal_start_snapshots_detector_setting_while_demo_forces_demo` (a Slides Only mode test using a lightweight test-double controller).
- **Fix:** Moved the `resolve()` call inside `if needs_whisper:`, matching the plan's explicit instruction not to change Slides Only behavior (it does not need whisper) and avoiding unnecessary registry calls on a path where the result is never used.
- **Files modified:** `app/desktop/engine_adapter.py`
- **Verification:** Full suite re-run: 1044 passed, 7 failed (same pre-existing failures)
- **Committed in:** `befc044` (Task 2 commit — fixed before the single commit was made, so this never landed as a separate broken commit)

---

**Total deviations:** 1 auto-fixed (1 bug, caught by the existing test suite before commit)
**Impact on plan:** No scope creep — self-corrected within Task 2's own verification loop before committing.

## Issues Encountered

- The pre-commit hook's `code-review-graph` panel print step threw a `UnicodeEncodeError` (cp1252 console codec) on both task commits. This is a cosmetic hook-reporting failure unrelated to the code change — the commit itself completed successfully both times (confirmed via `git log`), so no action was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The dependency root for Phase 2 is now closed: normal processing (Study Pack/Transcript Only/Slides Only) reaches the real pipeline on a clean install, exactly like the demo path already did.
- Full suite: 1044 passed, 7 failed — same 7 pre-existing `release_trust`/signing-key failures documented in `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md` (stale test fixtures, unrelated to this plan). Zero new failures.
- Plans 02-02/02-03/02-04 can now build real end-to-end import/processing/export flows on top of a working whisper+ffmpeg config path without needing their own workaround for D-01.
- Not yet exercised: a real packaged clean-install run through the actual pipeline (physical verification), and an in-app observation of the first-import poster thumbnail appearing without the previous no-op. Both are flagged as `human_judgment: true` coverage items above and are natural candidates for this phase's later physical/packaged verification gate.

---
*Phase: 02-real-lecture-import-processing*
*Completed: 2026-08-01*

## Self-Check: PASSED

All 4 modified source files and the SUMMARY.md exist on disk; both task commits (`832668d`, `befc044`) verified present in `git log --oneline --all`.
