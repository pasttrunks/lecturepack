---
phase: 02-hard-setup-signed-repair
plan: 02
subsystem: infrastructure
tags: [runtime-generation, transactional-activation, zip-safety, runtime-bootstrap]
requires:
  - phase: 02-hard-setup-signed-repair
    provides: signed release trust metadata and canonical inventory
provides:
  - writable complete runtime generations with atomic active-pointer publication
  - fail-closed active runtime-root resolution for normal bootstrap
  - strict streamed ZIP extraction and rollback-safe journal recovery
affects: [runtime-repair, setup-gate, packaged-smoke]
tech-stack:
  added: []
  patterns: [same-directory atomic JSON publication, private generation staging, canonical active-root resolver]
key-files:
  created:
    - lecturepack/infrastructure/runtime_generation.py
    - tests/test_runtime_generation.py
  modified:
    - lecturepack/services/runtime_bootstrap.py
key-decisions:
  - "Only an absent active pointer permits immutable-bundle fallback; malformed pointers and journals are setup-required."
  - "A generation is fully admitted before activation and re-admitted after the atomic pointer boundary, restoring the prior pointer on failure."
patterns-established:
  - "Use RuntimeGenerationStore for durable writable runtime activation; never write runtime repairs into the portable bundle."
  - "Normal RuntimeBootstrapService construction resolves the active root once through resolve_active_runtime_root."
requirements-completed: [REPR-05, REPR-06, REPR-07, REPR-08, REPR-09]
coverage:
  - id: D1
    description: "Strict streamed archive extraction rejects unsafe, duplicate/case-colliding, noncanonical, oversized, linked, and hash-mismatched members."
    requirement: REPR-05
    verification:
      - kind: unit
        ref: tests/test_runtime_generation.py#test_safe_extract_rejects_unsafe_or_noncanonical_members
        status: pass
    human_judgment: false
  - id: D2
    description: "Writable complete runtime generations publish through one active pointer and restore the previous pointer when post-activation admission fails."
    requirement: REPR-07
    verification:
      - kind: unit
        ref: tests/test_runtime_generation.py#test_publish_is_atomic_and_restores_previous_pointer_after_post_activation_failure
        status: pass
    human_judgment: false
  - id: D3
    description: "Malformed pointers or interrupted journals fail closed without falling back to the portable bundle."
    requirement: REPR-08
    verification:
      - kind: unit
        ref: tests/test_runtime_generation.py#test_interrupted_journal_or_pointer_never_falls_back_to_bundle
        status: pass
    human_judgment: false
  - id: D4
    description: "Normal bootstrap consumes the canonical active generation and repair trigger forces full admission."
    requirement: REPR-09
    verification:
      - kind: unit
        ref: tests/test_runtime_bootstrap.py#test_default_bootstrap_uses_the_canonical_active_generation_resolver
        status: pass
    human_judgment: false
duration: 28min
completed: 2026-07-28
status: complete
---

# Phase 02 Plan 02: Atomic Active Runtime Generation Summary

**Transactional writable runtime generations use strict streamed extraction, full admission, and one fail-closed active-root resolver while leaving the portable bundle immutable.**

## Performance

- **Duration:** 28 min
- **Completed:** 2026-07-28
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Added private writable generation storage with fsynced atomic JSON pointer and journal publication.
- Added strict, allow-listed ZIP streaming extraction with containment, member-shape, hash, and configured-size protections.
- Made bootstrap use the canonical active-generation resolver during normal startup, with immutable-bundle fallback only when no pointer exists.
- Added RED/GREEN coverage for activation rollback, cancellation, journal interruption, hostile archive input, and repair-triggered full admission.

## Task Commits

1. **Task 1: Specify generation resolution and transactional failure behavior** — `723578f` (test)
2. **Task 2: Implement verified staging, journaled activation, and canonical root resolution** — `10ca862` (feat)

## Files Created/Modified

- `lecturepack/infrastructure/runtime_generation.py` — transactional writable generation store, resolver, journal, and strict archive extraction.
- `lecturepack/services/runtime_bootstrap.py` — canonical runtime-root resolution before admission.
- `tests/test_runtime_generation.py` — generation transaction and archive safety contracts.

## Decisions Made

- Only a missing pointer falls back to the immutable bundle; malformed state fails closed so interrupted repair cannot silently run an unintended payload.
- Pointer activation is protected by a journal and a second admission check, restoring the prior pointer if the active generation cannot be admitted.

## Deviations from Plan

### Scope Corrections

**1. Restored an out-of-scope test file and relocated its coverage**
- **Found during:** Wave 1 scope acceptance
- **Issue:** `tests/test_runtime_bootstrap.py` was not in this plan's permitted file list.
- **Fix:** Restored it to the pre-plan content and moved the canonical active-generation bootstrap assertion into the permitted `tests/test_runtime_generation.py`.
- **Files modified:** `tests/test_runtime_bootstrap.py`, `tests/test_runtime_generation.py`, this summary
- **Committed in:** `12d47b7` (scope correction)

## Issues Encountered

- The complete suite reached `766 passed` but the required packaged-smoke integration test could not run because `LECTUREPACK_ONEDIR_FIXTURE` is unset. This is an external clean-onedir fixture prerequisite, not a code failure; no environment value was invented or mocked.

## User Setup Required

Set `LECTUREPACK_ONEDIR_FIXTURE` to a verified clean packaged runtime before rerunning the packaged smoke integration test.

## Next Phase Readiness

The repair service can now build on a fail-closed writable-generation activation boundary and one canonical startup root. The actual repair transport and UI remain in later Phase 2 plans.

## TDD Gate Compliance

- RED commit: `723578f`
- GREEN commit: `10ca862`

## Self-Check: PASSED

- `lecturepack/infrastructure/runtime_generation.py` exists and `tests/test_runtime_bootstrap.py` matches expected base `3a08c53`.
- Task commits `723578f` and `10ca862` exist in git history.
- Focused verification: `python -m pytest tests/test_runtime_generation.py tests/test_runtime_bootstrap.py tests/test_runtime_diagnostics.py -q` — **29 passed in 2.11s**.
- Full verification: `python -m pytest -q` — **766 passed, 1 failed** solely because the explicit packaged-fixture environment variable is unset.

---
*Phase: 02-hard-setup-signed-repair*
*Completed: 2026-07-28*
