---
phase: 01-runtime-contract-bootstrap
plan: 06
subsystem: runtime admission and native-path staging
tags: [whisper.cpp, runtime-validation, unicode-paths, vad, pytest]
requires:
  - phase: 01-runtime-contract-bootstrap/05
    provides: canonical clean-onedir fixture provenance and fail-closed launch evidence
provides:
  - Bounded staged canonical model-and-WAV CPU admission evidence
  - ASCII-safe optional VAD model native argv boundary
affects: [runtime-bootstrap, packaged-release, phase-1-verification]
tech-stack:
  added: []
  patterns: [complete evidence before runtime-health persistence, stage every native Whisper filesystem input]
key-files:
  created: []
  modified: [lecturepack/services/runtime_bootstrap.py, lecturepack/infrastructure/whisper_path_staging.py, lecturepack/infrastructure/whisper_wrapper.py, tests/test_runtime_bootstrap.py, tests/test_runtime_packaged_smoke.py, tests/test_whisper_path_staging.py, tests/test_study_workflow.py]
key-decisions:
  - "Full CPU admission uses one bounded staged canonical model-and-WAV transcription; the complete command evidence is shared by the model, WAV, Whisper executable, and required DLL entries."
  - "Optional VAD models cross the native whisper.cpp boundary only through the private ASCII staging root."
patterns-established:
  - "Readable runtime bytes are inventory prerequisites, never full-admission proof."
  - "Native Whisper argv paths are staged and cleanup-owned, including optional inputs."
requirements-completed: [RUNT-01, RUNT-03, RUNT-04]
coverage:
  - id: D1
    description: Full runtime admission proves canonical base-English model and smoke WAV usability through bounded CPU transcription before persistence.
    requirement: RUNT-03
    verification:
      - kind: integration
        ref: pytest tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py tests/test_runtime_inventory.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: A disposable Unicode-and-space copy of the supplied clean onedir emits real packaged admission evidence with a fresh profile.
    requirement: RUNT-01
    verification:
      - kind: integration
        ref: pytest tests/test_runtime_packaged_smoke.py -q
        status: pass
    human_judgment: false
  - id: D3
    description: Optional Unicode VAD input is byte-preserved, passed to native Whisper through an ASCII path, and cleaned with the staging root.
    requirement: RUNT-04
    verification:
      - kind: unit
        ref: pytest tests/test_whisper_path_staging.py tests/test_study_workflow.py tests/test_live_transcript_streaming.py -q
        status: pass
    human_judgment: false
duration: 16m
completed: 2026-07-28
status: complete
---

# Phase 01 Plan 06: Real Admission and Complete Whisper Staging Summary

**Bounded staged CPU transcription of the canonical base-English model and WAV, with complete persisted evidence and ASCII-safe optional VAD argv staging.**

## Performance

- **Duration:** 16 min
- **Completed:** 2026-07-28T15:07:58Z
- **Tasks:** 2/2
- **Files modified:** 7
- **Targeted tests:** 20 passed in 15.82s; 32 passed in 5.01s; packaged smoke 3 passed in 16.53s.
- **Full suite:** 733 passed in 184.08s (Task 1); 734 passed in 184.52s (Task 2).

## Accomplishments

- Replaced readability and `--help` admission with a bounded `whisper-cli -m <staged-model> -f <staged-wav> -t 1 -nt` CPU proof, retaining argv, exit code, duration, stdout, stderr, reason, and timeout fields for every canonical component.
- Proved the same admission path from a disposable Unicode-and-space copied onedir with a fresh profile; corrupt model evidence and incomplete evidence remain `SETUP_REQUIRED` and do not persist runtime health.
- Staged optional VAD models beneath the private ASCII root, byte-verified the copy, passed only the staged VAD path to supported native VAD options, and retained shared terminal cleanup.

## Fixture Provenance

Every packaged/full-suite command set `LECTUREPACK_ONEDIR_FIXTURE=C:\\Users\\marsh\\AppData\\Local\\Temp\\LecturePack Phase1 Gap Fixture Corrected 20260728`. This explicitly supplied run-scoped fixture is a copy of `C:\\Users\\marsh\\Documents\\LecturePack\\app\\dist\\LecturePack`, augmented only with the repository-approved `app\\packaging\\assets\\runtime-smoke.wav` at `smoke\\runtime-smoke.wav`. It was validated with `check_clean_state()` before each real smoke and was never modified; smoke copied it to a disposable Unicode-and-space path.

The real fixture admission evidence captured after the gate was:

- `argv`: `['C:\\Users\\marsh\\AppData\\Local\\Temp\\LecturePack Phase1 Gap Fixture Corrected 20260728\\bin\\whisper-cli.exe', '-m', 'C:\\Users\\marsh\\AppData\\Local\\Temp\\LecturePackWhisper\\lpws-3il6le83\\inputs\\model.bin', '-f', 'C:\\Users\\marsh\\AppData\\Local\\Temp\\LecturePackWhisper\\lpws-3il6le83\\inputs\\audio.wav', '-t', '1', '-nt']`
- `exit_code`: `0`; `duration_ms`: `4125`; `reason`: `success`; `timed_out`: `False`.
- `stdout`: `\n (electronic beeping)`.
- `stderr`: CPU backend loaded from the fixture's `ggml-cpu-haswell.dll`; model loaded from the staged ASCII `model.bin`; audio read from staged ASCII `audio.wav`; `system_info` reported `n_threads = 1`; and `main` reported processing the 1.0-second WAV. The full captured evidence remains in the `SmokeEvidence` returned by the run and is asserted by packaged-smoke tests.

No mock is used as the packaged proof.

## Task Commits

1. **Task 1: Require real canonical model-and-WAV transcription for full CPU admission** — `0122a6c` (RED tests), `1838c70` (implementation).
2. **Task 2: Stage optional VAD model input before every native Whisper invocation** — `4f1c186` (RED tests), `36c61d2` (implementation).

## Files Created/Modified

- `lecturepack/services/runtime_bootstrap.py` — runs staged canonical CPU admission and maps complete evidence to the inventory.
- `lecturepack/infrastructure/whisper_path_staging.py` — stages and byte-verifies optional VAD input.
- `lecturepack/infrastructure/whisper_wrapper.py` — supplies only the staged VAD model path to native argv.
- `tests/test_runtime_bootstrap.py` and `tests/test_runtime_packaged_smoke.py` — cover corrupt/incomplete evidence and real copied-onedir admission.
- `tests/test_whisper_path_staging.py` and `tests/test_study_workflow.py` — cover Unicode VAD preservation and the native-argv contract.

## Decisions Made

- Complete bounded process evidence, rather than readable bytes, is the persistence threshold for every canonical runtime component.
- Optional VAD input follows the same private staging and cleanup ownership as model and WAV inputs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Regression] Updated the existing VAD argument assertion for the strengthened native boundary**
- **Found during:** Task 2
- **Issue:** The pre-existing test asserted that the native command received the source VAD path, which directly contradicted the required staging contract.
- **Fix:** Asserted a distinct ASCII staged VAD path with byte-equivalent contents instead.
- **Files modified:** `tests/test_study_workflow.py`
- **Verification:** `pytest tests/test_whisper_path_staging.py tests/test_study_workflow.py tests/test_live_transcript_streaming.py -q` — 32 passed.
- **Commit:** `36c61d2`

**Total deviations:** 1 auto-fixed (Rule 1 regression).
**Impact:** Required to preserve the existing test's coverage while making it assert the Phase 1 native-path safety contract.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-06 closes the real-admission and Unicode VAD staging gaps. Plan 01-07 remains separately scoped before Phase 1 can be re-verified.

## Self-Check: PASSED

- All seven authorized implementation and test files exist.
- Task commits `0122a6c`, `1838c70`, `4f1c186`, and `36c61d2` exist in Git history.
- Both required full-suite gates passed under the supplied fixture environment.
