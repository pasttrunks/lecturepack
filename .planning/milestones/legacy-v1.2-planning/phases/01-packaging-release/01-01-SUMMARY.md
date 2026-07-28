---
phase: 01-packaging-release
plan: 01
subsystem: packaging
tags: [python, pyinstaller, versioning, pytest]

requires: []
provides:
  - Canonical dependency-free LecturePack 1.2.0 runtime and build version authority
  - Audited PyInstaller hidden-import inventory for current v1.1/v1.2 modules
  - Assertion-preserving PyInstaller analysis configuration and release regression tests
affects: [01-02-test-validation, 01-03-portable-build]

tech-stack:
  added: []
  patterns:
    - Package __version__ is the sole executable release semantic-version authority
    - PyInstaller configuration drift is guarded by focused static tests before real frozen-build proof

key-files:
  created:
    - .planning/phases/01-packaging-release/01-01-SUMMARY.md
  modified:
    - lecturepack/__init__.py
    - lecturepack/constants.py
    - build_release.py
    - LecturePack.spec
    - tests/test_packaging_and_safety.py
    - docs/DECISIONS.md

key-decisions:
  - "AD-14: lecturepack.__version__ is the sole executable runtime/build version authority; human-facing build labels remain synchronized but non-authoritative."

patterns-established:
  - "Version flow: lecturepack.__version__ -> constants.APP_VERSION / build_release.VERSION"
  - "Frozen drift gate: required dynamic modules are unique and Analysis uses optimize=0"

requirements-completed:
  - REQ-version-bump
  - REQ-packaging-spec-audit
  - REQ-architecture-layers
  - REQ-test-framework

coverage:
  - id: D1
    description: "LecturePack runtime, job manifests, and release tooling resolve release 1.2.0 from one package authority."
    requirement: REQ-version-bump
    verification:
      - kind: unit
        ref: "tests/test_packaging_and_safety.py::test_release_version_has_single_authority"
        status: pass
      - kind: unit
        ref: "tests/test_packaging_and_safety.py::test_new_job_manifest_uses_release_version"
        status: pass
    human_judgment: false
  - id: D2
    description: "The PyInstaller onedir spec uniquely includes the approved current module inventory and preserves self-test assertions."
    requirement: REQ-packaging-spec-audit
    verification:
      - kind: unit
        ref: "tests/test_packaging_and_safety.py::test_spec_includes_current_hiddenimports_and_keeps_asserts"
        status: pass
    human_judgment: false
  - id: D3
    description: "Packaging changes remain within the approved four-layer architecture and six-file implementation scope."
    requirement: REQ-architecture-layers
    verification:
      - kind: other
        ref: "git diff --name-only 9038b11..HEAD"
        status: pass
    human_judgment: false
  - id: D4
    description: "Focused release regression coverage integrates with the existing pytest framework without weakening prior safety tests."
    requirement: REQ-test-framework
    verification:
      - kind: unit
        ref: ".venv\\Scripts\\python.exe -m pytest tests/test_packaging_and_safety.py -v (7 passed)"
        status: pass
    human_judgment: false

duration: 2min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 1: Release Metadata and Frozen Spec Summary

**LecturePack 1.2.0 now has one import-safe release authority, an audited frozen module graph, and assertion-preserving PyInstaller analysis guarded by seven passing packaging tests.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-18T12:10:31Z
- **Completed:** 2026-07-18T12:12:21Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Defined `lecturepack.__version__` as the sole executable release authority and routed job manifests and release tooling through it.
- Added every approved current UI, service, and infrastructure hidden import exactly once while retaining the onedir layout and third-party collection.
- Synchronized the spec label at 1.2.0, set `optimize=0`, and added focused regression coverage for version, manifest, and frozen-spec drift.

## Task Commits

Each task was committed atomically:

1. **Task 1: Single-source release 1.2.0 and lock the version flow with tests** - `0110c26` (fix)
2. **Task 2: Audit the frozen-module collection and preserve self-test assertions** - `182829d` (fix)

**Plan metadata:** committed with this summary and GSD state updates.

## Files Created/Modified

- `lecturepack/__init__.py` - Defines the dependency-free canonical `__version__ = "1.2.0"`.
- `lecturepack/constants.py` - Binds `APP_VERSION` to the package authority.
- `build_release.py` - Binds archive and manifest `VERSION` to the package authority.
- `LecturePack.spec` - Synchronizes the release label, adds current hidden imports, and retains assertions with `optimize=0`.
- `tests/test_packaging_and_safety.py` - Adds three focused release regression tests.
- `docs/DECISIONS.md` - Records accepted AD-14 and rejected independent-literal/spec-parsing alternatives.

## Decisions Made

- Accepted AD-14: `lecturepack.__version__` is the canonical runtime/build authority; spec headers and other human-facing labels are synchronized but non-authoritative.

## Verification Evidence

- Focused version/manifest run: **2 passed in 0.41s**.
- Focused PyInstaller spec run: **1 passed in 0.07s**.
- Complete packaging and safety module: **7 passed in 9.68s**.
- Scoped diff check: passed; exactly the six authorized implementation files changed from the plan base.
- Cache-key guard: `DETECTOR_VERSION` and `REPAIR_PROMPT_VERSION` remained unchanged.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None introduced.

## Next Phase Readiness

- Ready for `01-02-PLAN.md` to reconcile pytest collection, run the full suite, and validate the development self-test.
- Real PyInstaller build and frozen executable proof remain correctly deferred to `01-03-PLAN.md`.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Task commits `0110c26` and `182829d` exist in git history.
- All six authorized modified implementation files exist.

---
*Phase: 01-packaging-release*
*Completed: 2026-07-18*
