---
phase: 01-runtime-contract-bootstrap
plan: 01
subsystem: infrastructure
tags: [runtime-inventory, pyinstaller, whisper-cpp, windows-paths, pytest]
requires: []
provides:
  - Canonical CPU runtime inventory and bounded evidence runner
  - Packaged smoke WAV and real disposable onedir proof
  - ASCII-only native whisper.cpp staging boundary with Unicode publication
affects: [runtime-bootstrap, packaging, diagnostics, transcription]
tech-stack:
  added: []
  patterns: [canonical inventory, bounded subprocess evidence, native argv staging]
key-files:
  created: [lecturepack/infrastructure/runtime_inventory.py, lecturepack/infrastructure/runtime_validation.py, lecturepack/infrastructure/whisper_path_staging.py, tests/test_runtime_packaged_smoke.py, tests/test_whisper_path_staging.py]
  modified: [app/packaging/build.py, lecturepack/infrastructure/whisper_wrapper.py, docs/DECISIONS.md]
key-decisions:
  - "Keep Unicode paths end-to-end while staging only v1.9.1 native CLI arguments under private ASCII paths."
patterns-established:
  - "Canonical package/runtime consumers resolve the same root-contained inventory."
  - "Native whisper.cpp calls use staged input/output paths and atomically publish outputs."
requirements-completed: [RUNT-01, RUNT-02, RUNT-04]
coverage:
  - id: D1
    description: Canonical required CPU runtime inventory, identity, and bounded runner
    requirement: RUNT-01
    verification:
      - kind: unit
        ref: pytest tests/test_runtime_inventory.py tests/test_runtime_bootstrap.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Package membership and real disposable packaged CPU smoke
    requirement: RUNT-02
    verification:
      - kind: integration
        ref: pytest tests/test_runtime_packaged_smoke.py tests/test_beta3_packaging.py -q
        status: pass
    human_judgment: false
  - id: D3
    description: ASCII staging with Unicode source/destination preservation and atomic publication
    requirement: RUNT-04
    verification:
      - kind: unit
        ref: pytest tests/test_whisper_path_staging.py tests/test_study_workflow.py tests/test_live_transcript_streaming.py -q
        status: pass
    human_judgment: false
duration: 49min
completed: 2026-07-28
status: complete
---

# Phase 1 Plan 01: Runtime Contract & Bootstrap Summary

**Canonical packaged CPU runtime validation with a real 4.3-second Whisper smoke and an ASCII-only native-path compatibility boundary that preserves Unicode user paths.**

## Performance

- **Duration:** 49 min
- **Completed:** 2026-07-28T00:22:02-04:00
- **Tasks:** 2/2
- **Files modified:** 12
- **Targeted tests:** 49 passed in 16.48s
- **Full suite:** 708 passed in 218.88s

## Accomplishments

- Created one ordered, root-contained inventory for the executable, CPU DLLs, base model, and deterministic smoke WAV; packaging and validation consume it.
- Added a blocking real onedir smoke that copies the source payload read-only to a Unicode-and-space directory, supplements the owned WAV, and captures process evidence with a 30-second bound.
- Added `WhisperPathStaging`: model, WAV, and output-prefix argv paths are ASCII-only for whisper.cpp v1.9.1; original bytes remain unchanged and staged outputs are atomically published to Unicode destinations.

## Real Packaged Smoke Evidence

- Source payload: `C:\\Users\\marsh\\Documents\\LecturePack\\app\\dist\\LecturePack` (read-only)
- Disposable runtime: a copied path containing spaces and `漢`; executable and DLLs remained there.
- Native argv: `whisper-cli.exe -m <ASCII staged model> -f <ASCII staged WAV> -t 1 -nt`
- Result: exit `0`, reason `success`, duration `4328 ms`, no timeout, no transcript/output artifact in the copied runtime.
- Captured output included CPU backend, model load/model size, WAV read, and processing/timing evidence. The smoke runs ffmpeg and ffprobe first and records argv, exit, stdout, stderr, duration, and reason.

## Task Commits

1. **Task 1: Create canonical inventory, validator, fixtures, and Wave 0 contracts** - `7bd3095`, `ed333c8`, `5ae6657` (test/feat/feat)
2. **Task 2: Wire canonical package membership and execute the blocking disposable packaged smoke** - `9a97ac3`, `bacb741` (test/feat)

## Files Created/Modified

- `lecturepack/infrastructure/runtime_inventory.py` - shared ordered package inventory and identity.
- `lecturepack/infrastructure/runtime_validation.py` - bounded evidence-rich runtime command runner.
- `lecturepack/infrastructure/whisper_path_staging.py` - private ASCII staging and atomic output publication.
- `lecturepack/infrastructure/whisper_wrapper.py` - production QProcess integration and cleanup on success/failure/cancel.
- `app/packaging/build.py` - canonical package assembly and real smoke harness.
- `tests/test_runtime_packaged_smoke.py` / `tests/test_whisper_path_staging.py` - real payload and Unicode-path staging contracts.
- `docs/DECISIONS.md` - AD-18 staging-boundary rationale.

## Decisions Made

- AD-18 keeps Unicode installation, model, WAV, data, and destination paths supported while restricting only the v1.9.1 native CLI argv boundary to application-controlled ASCII paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Packaged v1.9.1 Whisper crashed with Unicode model/WAV argv paths**
- **Found during:** Task 2
- **Issue:** The real disposable smoke previously exited `3221226505` after CPU DLL load when model/WAV paths contained non-ACP characters.
- **Fix:** Added private ASCII staging for native Whisper inputs/output prefix; preserved original bytes and atomically published outputs back to Unicode destinations.
- **Files modified:** `lecturepack/infrastructure/whisper_path_staging.py`, `lecturepack/infrastructure/whisper_wrapper.py`, `app/packaging/build.py`, relevant tests, `docs/DECISIONS.md`
- **Verification:** 49 targeted tests passed; real smoke exit 0 in 4328 ms; full pytest passed (708 tests).
- **Committed in:** `bacb741`

**Total deviations:** 1 auto-fixed (Rule 1)

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Runtime package membership and real packaged evidence are available to downstream bootstrap plans. Phase 2 remains blocked on the separately required signing/verifier ADR approval.

## Self-Check: PASSED

- Required source files and `bacb741`, `9a97ac3`, `5ae6657`, `ed333c8`, and `7bd3095` commits exist.

---
*Phase: 01-runtime-contract-bootstrap*
*Completed: 2026-07-28*
