---
phase: 01-clean-device-footprint-first-launch
plan: 01
subsystem: packaging
tags: [packaging, pyinstaller, measurement, windows, evidence]

# Dependency graph
requires: []
provides:
  - "scripts/measure_package_footprint.py — reusable, unit-tested footprint measurement and D-01/D-02 pruned-tree audit instrument"
  - "tests/test_package_footprint.py — 16 tests against synthetic trees"
  - "01-EVIDENCE.md — the phase's single evidence file, one heading per ROADMAP approval/evidence-gate item, seeded with NOT YET MEASURED markers"
affects: [01-04-PLAN.md, 01-08-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-predicate measurement functions (tree_size/top_contributors/audit_pruned_tree) mirroring check_clean_state()'s walk-and-return-data-structure idiom in app/packaging/build.py"
    - "Argument-list-only subprocess invocation (build_install_argv/build_uninstall_argv kept separate from process launching so tests never spawn a real installer)"

key-files:
  created:
    - scripts/measure_package_footprint.py
    - tests/test_package_footprint.py
    - .planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md
  modified: []

key-decisions:
  - "Task 3 (build one fresh Setup.exe and record the pre-cut baseline) was NOT executed in this run, per explicit orchestrator instruction — see Deviations."

patterns-established:
  - "audit_pruned_tree() reports the six D-01 cut targets and the D-02 opengl32sw.dll keep as structurally distinct fields, so a present opengl32sw.dll can never be conflated with a violation."

requirements-completed: []

coverage:
  - id: D1
    description: "Footprint measurement and pruned-tree audit script (tree_size, top_contributors, audit_pruned_tree, render_footprint_markdown, compare_footprints) plus CLI, unit-tested against synthetic trees"
    verification:
      - kind: unit
        ref: "tests/test_package_footprint.py (16 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "01-EVIDENCE.md seeded with one heading per ROADMAP Phase 1 approval/evidence-gate item, each carrying an explicit NOT YET MEASURED marker"
    verification:
      - kind: other
        ref: "python heading-presence check (see Task 2 <verify> in 01-01-PLAN.md)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pre-cut baseline recorded from one freshly built Setup.exe (installer bytes, expanded bytes, built-tree bytes, portable-ZIP bytes, top contributors, reconciliation cause)"
    verification: []
    human_judgment: true
    rationale: "Orchestrator explicitly instructed this run not to build an installer or fill measured values, deferring physical baseline gathering to Plan 01-08's blocking human-verify checkpoint. 01-EVIDENCE.md's baseline sections remain NOT YET MEASURED by design; this deliverable is not yet proven and must not be auto-passed."

duration: 30min
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 1: Footprint Measurement Instrument and Evidence Scaffold Summary

**Reusable pytest-verified footprint/pruned-tree audit script (`scripts/measure_package_footprint.py`) and a nine-section `01-EVIDENCE.md` seeded with explicit `NOT YET MEASURED` markers; the physical pre-cut baseline build itself was deferred, not gathered, in this run.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-07-31T03:13:06Z (approx., per STATE.md `last_updated` at phase start)
- **Completed:** 2026-07-31T03:19:03Z
- **Tasks:** 2 of 3 executed (Task 3 deferred — see Deviations)
- **Files modified:** 3 (all new files)

## Accomplishments

- Built `scripts/measure_package_footprint.py`: five pure functions (`tree_size`, `top_contributors`, `audit_pruned_tree`, `render_footprint_markdown`, `compare_footprints`) plus a CLI (`--installer`, `--expand-to`, `--tree`, `--assert-pruned`, `--json`, `--markdown`, `--compare`), all in the same walk-and-return-data-structure idiom as `check_clean_state()` in `app/packaging/build.py`.
- `audit_pruned_tree()` checks the six D-01 cut targets (`translations/`, `qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll`) and reports `opengl32sw.dll` presence as a structurally separate, "expected-and-correct" field per D-02 — it can never be mistaken for a violation.
- 16 tests in `tests/test_package_footprint.py`, all passing, against synthetic `tmp_path` trees only — no real installer is ever launched by the test suite.
- Seeded `.planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md` with all nine required ROADMAP-gate headings, each field carrying the literal `NOT YET MEASURED` marker, plus a preamble stating averaging is unacceptable and stale `app/dist/` numbers may not be reused.

## Task Commits

Each executed task was committed atomically:

1. **Task 1: Footprint measurement and pruned-tree audit script** - `68cdaeb` (feat)
2. **Task 2: Seed 01-EVIDENCE.md with an unfilled section per evidence-gate item** - `7a41fdb` (docs)

Task 3 ("Build one fresh installer and record the pre-cut baseline") was not executed — no commit exists for it. See Deviations below.

## Files Created/Modified

- `scripts/measure_package_footprint.py` - Pure measurement/audit functions plus a subprocess-argument-list-only CLI.
- `tests/test_package_footprint.py` - 16 tests against synthetic trees; also exercises the CLI via `subprocess.run([sys.executable, ...])`.
- `.planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md` - Nine-heading evidence scaffold, all baseline/after-cuts/timing/instance/icon/smoke fields seeded `NOT YET MEASURED`.

## Decisions Made

- Kept `tree_size`/`top_contributors`/`audit_pruned_tree` walking with `os.walk(..., followlinks=False)` and explicit symlink skips (not `Path.rglob`), to satisfy T-01-01-03 (symlink-loop DoS mitigation) without needing a separate guard function.
- Split the installer/uninstaller invocation into pure `build_install_argv`/`build_uninstall_argv` functions so the "never `shell=True`, argument-list only" requirement (T-01-01-02) is unit-testable without ever spawning a process — the impure `expand_installer()` calls these builders and then `subprocess.run(argv, ...)` with no shell.
- `audit_pruned_tree()`'s return shape keeps `cut_targets` (the six D-01 violations-if-present) and `opengl32sw_present`/`opengl32sw_disposition` as separate top-level keys rather than folding everything into one "violations" list — this was a deliberate structural choice so a caller cannot accidentally treat the D-02 keep as a cut-target violation.

## Deviations from Plan

### Architectural / scope deviation (directed by orchestrator, not a Rule 1-3 auto-fix)

**Task 3 ("Build one fresh installer and record the pre-cut baseline") was not executed.**

- **Directive source:** The orchestrator's spawn-time instructions for this run stated explicitly: *"This plan builds the measurement instrument and the evidence scaffold. It does NOT gather the physical numbers — that is plan 01-08's blocking human-verify checkpoint. Do not attempt to build an installer or fill in measured values; leave the explicit unfilled markers in place. An empty slot must read as visibly absent, never as assumed."*
- **Conflict with plan text:** 01-01-PLAN.md's Task 3, its `<verify>` command, its acceptance criteria, and the plan-level `<verification>`/`<success_criteria>` blocks all require a real `python packaging/build.py` run and a filled `01-EVIDENCE.md` baseline in this same plan. ROADMAP.md's Wave 1 description for 01-01 likewise says "the pre-cut baseline from one fresh installer." This run followed the orchestrator's explicit override rather than the plan text, per the executor's instruction that spawning-agent messages direct the work.
- **Consequence:** `01-EVIDENCE.md`'s `## Machine and build identity`, `## Size — baseline (pre-cut)`, and the measured half of `## Size — reconciliation` remain `NOT YET MEASURED`. The plan's own `<verify>` command for Task 3 and the plan-level `<verification>` bullet "`01-EVIDENCE.md` baseline sections contain measured numbers and no `NOT YET MEASURED` marker" will both fail if re-run against the current state of this file — this is intentional given the deferral, not a bug.
- **What was NOT touched:** No installer was built, no `app/dist/` tree was created or modified, and no `NOT YET MEASURED` marker was replaced with an assumed or estimated number. The measurement instrument built in Task 1 is ready to run this exact workflow whenever a human/later plan actually performs the build.
- **Environment note:** ISCC 6 was confirmed present at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` in this environment, so the deferral is a scope/orchestration decision, not an environment limitation.
- **Follow-up required:** Plan 01-08 (or an explicit re-run of this plan's Task 3) must perform the actual build-and-measure step before Phase 1's approval/evidence gate can be claimed satisfied for Success Criterion 1.

### Out-of-scope, logged not fixed

**`tests/test_runtime_packaged_smoke.py::test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile` fails in this environment** because `LECTUREPACK_ONEDIR_FIXTURE` is unset (it requires a real packaged onedir fixture). This is pre-existing, unrelated to any file this plan touched, and out of scope per the scope-boundary rule — not fixed, logged here for visibility. The other 3 tests in that file pass, as does the full `tests/test_beta3_packaging.py` suite (9/9).

---

**Total deviations:** 1 orchestrator-directed scope deferral (Task 3), 1 out-of-scope pre-existing failure logged.
**Impact on plan:** Tasks 1 and 2 are fully complete and verified. Task 3's physical baseline measurement is outstanding and must be completed before Phase 1's Success Criterion 1 can be claimed.

## Issues Encountered

None beyond the Task 3 deferral documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The measurement instrument (`scripts/measure_package_footprint.py`) and its test suite are ready for reuse by Plan 01-04 (post-cut audit) and Plan 01-08 (after-cuts baseline and reconciliation).
- **Blocker for Plan 01-08 and for Phase 1's Success Criterion 1:** the pre-cut baseline in `01-EVIDENCE.md` (`## Machine and build identity`, `## Size — baseline (pre-cut)`, `## Size — reconciliation`) is still `NOT YET MEASURED`. Someone must run `python packaging/build.py` (full build, no `--no-installer`) and the three `measure_package_footprint.py` invocations described in 01-01-PLAN.md Task 3 before that gap can close. Plan 01-04 rebuilds `app/dist/` and will overwrite the tree this baseline needs to be measured from, so this should happen before 01-04 executes if the original wave-1 sequencing is to hold.
- Plan 01-02 and 01-03 (also wave 1) are unaffected by this deferral.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: scripts/measure_package_footprint.py
- FOUND: tests/test_package_footprint.py
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-01-SUMMARY.md
- FOUND commit: 68cdaeb (Task 1)
- FOUND commit: 7a41fdb (Task 2)
