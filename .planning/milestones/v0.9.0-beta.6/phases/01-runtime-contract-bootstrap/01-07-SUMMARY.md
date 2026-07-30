---
phase: 01-runtime-contract-bootstrap
plan: 07
subsystem: runtime admission bridge
tags: [PySide6, QWebChannel, runtime-admission, diagnostics, pytest]
requires:
  - phase: 01-runtime-contract-bootstrap/06
    provides: bounded canonical CPU admission evidence and native Whisper staging
provides:
  - Safe setup-required no-op boundary for every adapter/updater bridge operation
  - Bootstrap payload with controller-owned canonical admission state
affects: [phase-1-verification, desktop-bridge, runtime-bootstrap]
tech-stack:
  added: []
  patterns: [centralized admission guard before collaborator access, controller-owned diagnostics transport]
key-files:
  created: []
  modified: [app/desktop/bridge.py, tests/test_adapter_startup.py, docs/HANDOFF_PHASE_1.md]
key-decisions:
  - "SETUP_REQUIRED actions use the existing diagnostics transport and a single JSON-safe payload instead of constructing unavailable collaborators or adding a frontend signal."
  - "Bootstrap derives admission fields from the runtime diagnostics controller; it does not build a second inventory projection."
patterns-established:
  - "All bridge operations that require adapter or updater collaborators are centrally admission-guarded before side effects."
requirements-completed: [RUNT-05]
coverage:
  - id: D1
    description: Every adapter/updater bridge operation is safe and side-effect-free before HEALTHY admission.
    requirement: RUNT-05
    verification:
      - kind: integration
        ref: pytest tests/test_adapter_startup.py tests/test_runtime_diagnostics.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Fixture-backed packaged admission and all prior gap-closure regressions pass together.
    verification:
      - kind: integration
        ref: pytest tests/test_beta3_packaging.py tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py tests/test_whisper_path_staging.py tests/test_adapter_startup.py tests/test_runtime_diagnostics.py -q
        status: pass
    human_judgment: false
duration: 25m
completed: 2026-07-28
status: complete
---

# Phase 01 Plan 07: Safe Setup-Required Bridge Summary

**A centralized QWebChannel admission guard that makes withheld adapter/updater actions stable diagnostics no-ops while preserving the canonical runtime-health transport.**

## Performance

- **Duration:** 25m
- **Tasks:** 2/2
- **Files modified:** 3
- **Targeted bridge/diagnostic gate:** 10 passed in 0.93s.
- **Gap-closure suite:** 38 passed in 16.70s; separate packaged smoke: 3 passed in 15.67s.
- **Full suite:** 737 passed in 183.49s (0:03:03).

## Accomplishments

- Added a single admission guard covering every existing adapter/updater bridge operation, including Qt slot dispatch; `SETUP_REQUIRED` now emits or returns stable structured evidence before collaborator access.
- Kept healthy collaborators and detailed `get_runtime_health_snapshot()` behavior intact, while extending `get_bootstrap()` with controller-owned admission state.
- Recorded fixture provenance, real bounded CPU smoke evidence, all gap-closure tests, and outstanding independent verification/physical-release blockers in the Phase 1 handoff.

## Fixture Provenance and Real Smoke

Every packaged/full-suite command used `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\AppData\Local\Temp\LecturePack Phase1 Gap Fixture Corrected 20260728`: a run-scoped copy of `C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack`, augmented only with approved `app\packaging\assets\runtime-smoke.wav` at `smoke\runtime-smoke.wav`. `check_clean_state()` passed and the fixture itself was never changed.

The disposable copied runtime ran `whisper-cli.exe -m <ASCII staged model.bin> -f <ASCII staged audio.wav> -t 1 -nt` with exit code 0, duration 4078 ms, reason `success`, and stdout `(electronic beeping)`. Its captured stderr confirmed copied `ggml-cpu-haswell.dll` CPU backend loading, model loading, staged WAV reading, one thread, and one-second processing.

## Task Commits

1. **Task 1: Guard every adapter and updater bridge call during setup-required admission** — `65c7764` (RED tests), `5e93806` (implementation).
2. **Task 2: Update the Phase 1 handoff with complete gap-closure evidence** — `284b1c4`.

## Files Created/Modified

- `app/desktop/bridge.py` — centralized guarded-operation registry and setup-required transport; bootstrap admission fields.
- `tests/test_adapter_startup.py` — exhaustive table-driven setup-required slot coverage and Qt metacall regression.
- `docs/HANDOFF_PHASE_1.md` — actual fixture, smoke, targeted, full-suite, and remaining-blocker evidence.

## Decisions Made

- The existing `diagnostics` transport is the no-op channel for void bridge operations; no QWebChannel signal or frontend asset changed.
- `get_updater_state()` returns the same JSON-safe setup-required evidence, while bootstrap uses the existing diagnostics controller snapshot.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

The first evidence-print helper attempted to write a Unicode path through a cp1252 console and raised `UnicodeEncodeError` after the full suite had completed. Re-running that read-only smoke helper with ASCII JSON escaping captured the same successful real smoke evidence; no fixture or source file was modified.

## Known Stubs

None.

## Threat Flags

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Automated gap closures are complete, but Phase 1 must remain in independent code-review and goal-verification status. Physical CPU-only, NVIDIA, AMD/Intel, hostile-path, and frozen signing/verifier proof remain unexecuted; Phase 2 repair/onboarding work remains out of scope.

## Self-Check: PASSED

- Required files `app/desktop/bridge.py`, `tests/test_adapter_startup.py`, `tests/test_runtime_diagnostics.py`, and `docs/HANDOFF_PHASE_1.md` exist.
- Task commits `65c7764`, `5e93806`, and `284b1c4` exist in Git history.
