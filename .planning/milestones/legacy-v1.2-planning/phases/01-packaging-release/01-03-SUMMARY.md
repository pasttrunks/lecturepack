---
phase: 01-packaging-release
plan: 03
subsystem: packaging
tags: [pyinstaller, windows-portable, sha256, frozen-selftest, release-validation]

requires:
  - phase: 01-01
    provides: Canonical 1.2.0 version authority and audited assertion-preserving PyInstaller specification
  - phase: 01-02
    provides: Reconciled 158-pass source suite, development self-test, privacy gate, and architecture no-regression baseline
provides:
  - Real LecturePack 1.2.0 Windows onedir package and portable ZIP
  - SHA-256 and manifest integrity proof for the portable archive
  - Complete CPU, Vulkan, FFmpeg, documentation, and forbidden-content inventories
  - Passing frozen self-tests from onedir and a clean extraction path containing a space
affects: [phase-01-release, phase-02-reliability-hardening]

tech-stack:
  added: []
  patterns:
    - Fail-closed generated-output cleanup requires exact normalized repo-child targets and a root-only release-artifact allowlist
    - Frozen validation records absolute executable paths, finite timeouts, complete output, and exit codes before evaluation

key-files:
  created:
    - docs/evidence/v1.2.0/release/build_output.txt
    - docs/evidence/v1.2.0/release/packaged_selftest_output.txt
    - docs/evidence/v1.2.0/release/extracted_selftest_output.txt
    - docs/evidence/v1.2.0/release/PACKAGED_VALIDATION.md
    - .planning/phases/01-packaging-release/01-03-SUMMARY.md
  modified: []

key-decisions: []

patterns-established:
  - "Release cleanup: exact generated targets, non-reparse checks, and explicit per-entry allowlist decisions before deletion"
  - "Portable proof: independent digest equality plus two real frozen executions, including clean extraction under a path with spaces"

requirements-completed:
  - REQ-packaged-build
  - REQ-self-test
  - REQ-version-bump
  - REQ-packaging-spec-audit
  - REQ-privacy-safety

coverage:
  - id: D1
    description: "The real PyInstaller release contains the complete required CPU, Vulkan, FFmpeg, and documentation layout in both onedir and ZIP form."
    requirement: REQ-packaged-build
    verification:
      - kind: integration
        ref: ".venv\\Scripts\\python.exe build_release.py (EXIT_CODE 0; onedir 1168 entries; ZIP 933 entries)"
        status: pass
      - kind: other
        ref: "docs/evidence/v1.2.0/release/build_output.txt#TASK1_VALIDATION_STATUS: PASS"
        status: pass
    human_judgment: false
  - id: D2
    description: "The 1.2.0 portable ZIP independently matches SHA256SUMS.txt and BUILD_MANIFEST.json."
    requirement: REQ-version-bump
    verification:
      - kind: other
        ref: "Get-FileHash SHA256 = f5680469c55b4420249b1cfcd264f4161d049080f9e2cfd17d551f2620715f9e"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both the onedir and clean-extracted frozen executables pass self-test as LecturePack 1.2.0 within 120 seconds."
    requirement: REQ-self-test
    verification:
      - kind: integration
        ref: "docs/evidence/v1.2.0/release/packaged_selftest_output.txt (exit 0, timeout false, SELFTEST PASS)"
        status: pass
      - kind: integration
        ref: "docs/evidence/v1.2.0/release/extracted_selftest_output.txt (exit 0, timeout false, SELFTEST PASS)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The portable package excludes Whisper models, secrets, user configuration, job/transcript/slide data, and original media."
    requirement: REQ-privacy-safety
    verification:
      - kind: other
        ref: "docs/evidence/v1.2.0/release/PACKAGED_VALIDATION.md (all seven exclusion categories PASS)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The audited PyInstaller configuration remains assertion-preserving and passes focused release regression tests."
    requirement: REQ-packaging-spec-audit
    verification:
      - kind: unit
        ref: ".venv\\Scripts\\python.exe -m pytest tests/test_packaging_and_safety.py -v (7 passed in 0.97s)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 3: Portable Build and Frozen Validation Summary

**LecturePack 1.2.0 now has a real 365.9 MiB portable Windows release whose runtime layout, archive integrity, privacy exclusions, and two frozen launch paths are proven by current non-mocked evidence.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-18T16:57:00Z
- **Completed:** 2026-07-18T17:22:02Z
- **Tasks:** 2
- **Tracked evidence files:** 4

## Accomplishments

- Built the real PyInstaller onedir package and `LecturePack-portable-1.2.0.zip` with build exit 0 after a fail-closed cleanup preflight.
- Verified 1168 onedir entries and 933 ZIP entries, including every required CPU/Vulkan/FFmpeg runtime and all three release documents.
- Independently recomputed SHA-256 `f5680469c55b4420249b1cfcd264f4161d049080f9e2cfd17d551f2620715f9e`, matching both release records exactly.
- Passed both frozen self-tests with LecturePack 1.2.0, timeout false, and exit 0; the second ran from a fresh temporary extraction path containing a space.
- Rejected all prohibited model payloads, secrets, user configuration, job/transcript/slide data, and original media; the validated temporary extraction was removed afterward.

## Task Commits

1. **Task 1: Produce the real onedir package, portable ZIP, checksums, and manifest** - `5c97724` (chore)
2. **Task 1 evidence correction: Retain the initial pre-deletion release inventory** - `af20614` (fix)
3. **Task 2: Prove checksum integrity and frozen launch from onedir and clean extraction** - `35cd04e` (test)

**Plan metadata:** committed separately with this summary and GSD state updates.

## Files Created/Modified

- `docs/evidence/v1.2.0/release/build_output.txt` - Exact cleanup targets, initial four-entry allowlist, real build stdout/stderr/exit, complete inventories, and exclusions.
- `docs/evidence/v1.2.0/release/packaged_selftest_output.txt` - Timed onedir frozen self-test with absolute path and complete process output.
- `docs/evidence/v1.2.0/release/extracted_selftest_output.txt` - Timed frozen self-test from the clean extraction path containing a space.
- `docs/evidence/v1.2.0/release/PACKAGED_VALIDATION.md` - Digest equality, inventories, exclusions, frozen results, extraction path, cleanup, and architecture-debt disclosure.
- `build/**`, `dist/**`, `dist-release/**` - Generated release outputs; intentionally gitignored and not committed.

## Decisions Made

None - the plan followed the approved packaging architecture and retained the Phase 2 architecture-debt boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made build process capture compatible with Windows PowerShell**
- **Found during:** Task 1 build invocation
- **Issue:** Windows PowerShell promoted PyInstaller's normal stderr progress stream to a terminating `NativeCommandError` after the cleanup gate passed.
- **Fix:** Repeated the full safety preflight and used a non-interactive process with separate temporary stdout/stderr capture; retained the initial four-entry pre-deletion inventory and disclosed the retry.
- **Files modified:** `docs/evidence/v1.2.0/release/build_output.txt`
- **Verification:** Real builder exit 0; complete stdout/stderr and final layout evidence retained.
- **Committed in:** `5c97724`, `af20614`

**2. [Rule 1 - Bug] Excluded the QtQml Models plugin from Whisper-model false positives**
- **Found during:** Task 1 forbidden-content inspection
- **Issue:** A case-insensitive generic `models/` pattern classified PySide6's required `_internal/PySide6/qml/QtQml/Models/modelsplugin.dll` as bundled Whisper data.
- **Fix:** Restricted directory exclusion to the application-root `models/` location while keeping `ggml-*.bin` and `*.gguf` payload rejection anywhere in the tree.
- **Files modified:** Generated validation evidence only; no source or release contents changed.
- **Verification:** All seven exclusion categories pass for onedir, ZIP, and extracted inventories.
- **Committed in:** `5c97724`

**3. [Rule 3 - Blocking] Read frozen process exit codes through System.Diagnostics.Process**
- **Found during:** Task 2 onedir self-test
- **Issue:** Windows PowerShell's `Start-Process` wrapper returned a blank exit-code property even though the frozen executable emitted a complete PASS line.
- **Fix:** Used a non-shell `System.Diagnostics.Process` invocation with redirected streams and a 120-second wait boundary.
- **Files modified:** Frozen self-test evidence only.
- **Verification:** Both final logs record timeout false, exit 0, `SELFTEST PASS`, and `LecturePack v1.2.0`.
- **Committed in:** `35cd04e`

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking wrapper issues)
**Impact on plan:** Validation correctness and evidence durability improved; production source, tests, package contents, dependencies, and user data remained unchanged.

## Issues Encountered

- PyInstaller emitted optional dependency warnings for unused SciPy/Qt database/QML components; none named a required release runtime or document, and both frozen self-tests passed.
- Strict adjacent-layer architecture conformance remains `NO`: the 47 exact baseline violation identities are still disclosed Phase 2 debt, with zero new identities introduced by Phase 1.

## Verification Evidence

- Phase source suite from Plan 01-02: **158 passed in 113.56s**.
- Current focused packaging suite: **7 passed in 0.97s**.
- Real build: **EXIT_CODE 0**.
- Onedir frozen self-test: **timeout false, EXIT_CODE 0, SELFTEST PASS, LecturePack v1.2.0**.
- Clean-extracted frozen self-test: **timeout false, EXIT_CODE 0, SELFTEST PASS, LecturePack v1.2.0**.
- Independent/checksum-file/manifest ZIP digests: **all equal**.

## User Setup Required

None - no installs, downloads, credentials, network providers, models, or original lecture media were used.

## Known Stubs

None introduced.

## Next Phase Readiness

- Phase 1 packaging and release evidence is complete and ready for phase verification/owner release approval.
- Phase 2 remains responsible for eliminating the disclosed 47-violation architecture baseline and the approved reliability backlog.

## Self-Check: PASSED

- All four tracked release-evidence files and all required generated release artifacts exist.
- Task commits `5c97724`, `af20614`, and `35cd04e` exist in git history.
- Digest equality, both frozen PASS results, and validated extraction cleanup are present in the packaged-validation report.

---
*Phase: 01-packaging-release*
*Completed: 2026-07-18*
