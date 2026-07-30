---
phase: 01-runtime-contract-bootstrap
plan: 05
subsystem: runtime packaging and admission
tags: [pyinstaller, runtime-validation, fail-closed, packaged-smoke, pytest]
requires:
  - phase: 01-runtime-contract-bootstrap/01
    provides: Canonical runtime inventory and disposable packaged smoke harness
  - phase: 01-runtime-contract-bootstrap/02
    provides: Atomic CPU runtime-health admission policy
provides:
  - Fresh-onedir canonical runtime payload assembly
  - Failed launch and validator exception evidence that remains setup-required
affects: [runtime-bootstrap, packaged-release, phase-1-verification]
tech-stack:
  added: []
  patterns: [create canonical destination parents before copy, fail-closed validation evidence]
key-files:
  created: []
  modified: [app/packaging/build.py, lecturepack/infrastructure/runtime_validation.py, lecturepack/services/runtime_bootstrap.py, tests/test_beta3_packaging.py, tests/test_runtime_bootstrap.py, tests/test_runtime_packaged_smoke.py]
key-decisions:
  - "A failed process creation or unexpected full-validator exception is untrusted evidence and cannot authorize persistence or optional-engine resolution."
patterns-established:
  - "The packaged fixture is canonical input only; real smoke always uses a disposable Unicode-and-space copy."
requirements-completed: [RUNT-01, RUNT-03, RUNT-04]
coverage:
  - id: D1
    description: Fresh PyInstaller onedir receives ordered canonical payloads and passes clean-state validation.
    requirement: RUNT-01
    verification:
      - kind: unit
        ref: pytest tests/test_beta3_packaging.py tests/test_runtime_inventory.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Canonical fixture smoke WAV is preserved in a disposable Unicode-and-space runtime copy for the real CLI smoke.
    requirement: RUNT-04
    verification:
      - kind: integration
        ref: pytest tests/test_runtime_packaged_smoke.py -q
        status: pass
    human_judgment: false
  - id: D3
    description: Launch and full-validator failures fail closed without health persistence, migration, or optional-resolution side effects.
    requirement: RUNT-03
    verification:
      - kind: unit
        ref: pytest tests/test_runtime_bootstrap.py tests/test_runtime_inventory.py -q
        status: pass
    human_judgment: false
duration: 28m
completed: 2026-07-28
status: complete
---

# Phase 01 Plan 05: Clean Package and Fail-Closed Admission Summary

**Fresh-onedir canonical CPU payload assembly plus fail-closed runtime launch and validator evidence that never persists untrusted health.**

## Performance

- **Duration:** 28 min
- **Completed:** 2026-07-28T10:50:58-04:00
- **Tasks:** 2/2
- **Files modified:** 6
- **Targeted tests:** 16 passed in 12.97s; 15 passed in 0.63s; packaged smoke 3 passed in 10.28s.
- **Full suite:** 731 passed in 178.64s.

## Accomplishments

- Made `bundle_engine()` create each explicit canonical destination parent immediately before copying, so an otherwise empty onedir runtime tree can be assembled and pass `check_clean_state()`.
- Made the packaged smoke require the fixture-provided nonempty `smoke/runtime-smoke.wav`, verify it after the disposable Unicode/space copy, and run the existing real CLI smoke with a fresh profile without recreating or replacing the asset.
- Converted `Popen` OS launch failures and unexpected full-validator exceptions into inspectable failed admission evidence, returning `SETUP_REQUIRED` before persistence, migration, or optional-engine resolution.

## Fixture Provenance

Every packaged/full-suite command used `LECTUREPACK_ONEDIR_FIXTURE=C:\\Users\\marsh\\AppData\\Local\\Temp\\LecturePack Phase1 Gap Fixture Corrected 20260728`. The supplied fixture was copied from `C:\\Users\\marsh\\Documents\\LecturePack\\app\\dist\\LecturePack` without changing that old package, then augmented only with the repository-approved `app\\packaging\\assets\\runtime-smoke.wav` at canonical `smoke\\runtime-smoke.wav`. It was previously validated as clean with nonempty executable, Whisper CLI, base-English model, and smoke WAV. This plan never modified the fixture; its real smoke used a disposable Unicode/space copy.

## Task Commits

1. **Task 1: Make canonical package assembly work from an empty onedir runtime tree** — `dca41f5` (RED tests), `1be5712` (implementation).
2. **Task 2: Convert validator launch and admission exceptions into failed setup evidence** — `e5a13c8` (RED tests), `fd26e4e` (implementation).

## Files Created/Modified

- `app/packaging/build.py` — creates required canonical destination directories during payload assembly.
- `tests/test_beta3_packaging.py` — proves fresh-tree assembly and clean-state validity.
- `tests/test_runtime_packaged_smoke.py` — enforces fixture WAV provenance and disposable-copy preservation.
- `lecturepack/infrastructure/runtime_validation.py` — returns bounded launch-failure `SmokeEvidence` for `OSError`.
- `lecturepack/services/runtime_bootstrap.py` — synthesizes failed setup-required evidence for validator exceptions.
- `tests/test_runtime_bootstrap.py` — covers launch failure, repeated validator failure, no persistence, and no optional resolution.

## Decisions Made

- A process that cannot be created and a validator that raises both remain failed, inspectable admission evidence; neither path is treated as healthy or allowed to mutate runtime state.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The first full-suite command exceeded its 120-second command timeout before completing. Re-running the same suite with a longer bound completed successfully: 731 passed in 178.64s.

## Known Stubs

None.

## Threat Flags

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The clean-package and fail-closed launch gaps are closed with real fixture-based smoke evidence. Remaining Phase 1 gap plans 01-06 and 01-07 remain separately scoped.

## Self-Check: PASSED

- All six authorized implementation/test files exist.
- Task commits `dca41f5`, `1be5712`, `e5a13c8`, and `fd26e4e` exist in Git history.

---
*Phase: 01-runtime-contract-bootstrap*
*Completed: 2026-07-28*
