---
phase: 01-runtime-contract-bootstrap
plan: 02
subsystem: infrastructure
tags: [runtime-bootstrap, config, cpu-admission, migration, pytest]
requires:
  - phase: 01-runtime-contract-bootstrap/01
    provides: Canonical runtime inventory and bounded validator
provides:
  - Atomic validated CPU runtime-health persistence
  - One-time base-English model migration with retained prior models
  - CPU-first optional-engine fallback policy
affects: [desktop-bootstrap, runtime-diagnostics, setup-gate]
tech-stack:
  added: []
  patterns: [complete-evidence-before-persistence, CPU-first-optional-resolution]
key-files:
  created: [lecturepack/services/runtime_bootstrap.py]
  modified: [lecturepack/infrastructure/config_manager.py, tests/test_runtime_bootstrap.py]
key-decisions:
  - "Reject incomplete full-validation evidence instead of merging it into a healthy runtime record."
  - "Resolve optional engine preferences only after canonical CPU admission succeeds."
patterns-established:
  - "Runtime health is one complete atomic snapshot, never incrementally persisted component paths."
requirements-completed: [RUNT-03, RUNT-04, RUNT-06, RUNT-07, RUNT-08]
coverage:
  - id: D1
    description: Complete validated CPU admission, persistence, and one-time migration
    requirement: RUNT-03
    verification:
      - kind: unit
        ref: pytest tests/test_runtime_bootstrap.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: CPU-first optional-engine preservation and bounded fallback
    requirement: RUNT-07
    verification:
      - kind: unit
        ref: pytest tests/test_runtime_bootstrap.py tests/test_cuda_engine.py -q
        status: pass
    human_judgment: false
duration: 17min
completed: 2026-07-28
status: complete
---

# Phase 01 Plan 02: Runtime Admission and Migration Summary

**Atomic, evidence-backed CPU runtime admission with one-time base-English migration and optional-engine fallback that cannot block startup.**

## Performance

- **Duration:** 17 min
- **Completed:** 2026-07-28
- **Tasks:** 2/2
- **Files modified:** 4
- **Targeted tests:** 19 passed in 1.26s
- **Full suite:** 714 passed in 180.99s with `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack`.

## Accomplishments

- Added `RuntimeBootstrapService`, which selects light versus full checks from persisted identity and forces full validation for fresh, changed, update, and repair states.
- Added a single atomic `ConfigManager.persist_runtime_health()` path that persists complete facts only after success, writes migration marker `runtime_contract: 1`, migrates to bundled base English once, and retains a prior model.
- Kept healthy optional preferences while falling back unavailable CUDA/Vulkan preferences to CPU only after successful CPU admission; optional resolution is not called on CPU failure.

## Task Commits

1. **Task 1: Implement validated admission and one-time beta-6 migration** - `a38dabc` (test), `a5dd705` (feat)
2. **Task 2: Implement optional-engine preservation and bounded fallback** - `4d7e69d` (test), `7229579` (fix)

## Files Created/Modified

- `lecturepack/services/runtime_bootstrap.py` - admission state/result, full/light validation policy, and post-health optional resolution.
- `lecturepack/infrastructure/config_manager.py` - atomic complete runtime-health persistence and exact migration marker semantics.
- `tests/test_runtime_bootstrap.py` - admission, migration, complete-evidence, and optional fallback contracts.

## Decisions Made

- Incomplete full validation is a setup-required state; inventory readability alone cannot become durable healthy evidence.
- The optional resolver remains strictly post-admission, so it makes no network call or optional provider probe until CPU health is established.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rejected incomplete full-validation evidence**
- **Found during:** Task 2
- **Issue:** A validator response missing one required component could otherwise inherit the light-check healthy flag and persist a false healthy state.
- **Fix:** Missing full-validation entries now become explicit unhealthy evidence.
- **Files modified:** `lecturepack/services/runtime_bootstrap.py`, `tests/test_runtime_bootstrap.py`
- **Verification:** Targeted 19-test suite and full 714-test suite passed.
- **Committed in:** `7229579`

**Total deviations:** 1 auto-fixed (Rule 1)

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The runtime admission service can now be composed ahead of normal desktop readiness in Plan 01-03. Phase 2 repair remains blocked on the signing/verifier ADR approval.

## Self-Check: PASSED

- Required source and test files exist.
- Task commits `a38dabc`, `a5dd705`, `4d7e69d`, and `7229579` exist.

