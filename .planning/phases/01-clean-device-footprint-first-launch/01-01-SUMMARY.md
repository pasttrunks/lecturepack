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
  - "D-23 (ISCC MAX_PATH normalization) was discovered as a build-blocking prerequisite while executing Task 3, resolved as a decision recorded in 01-CONTEXT.md, and fixed in commit 1b6059d — Task 3 could not produce a Setup.exe until this landed."
  - "Task 3 (build one fresh Setup.exe and record the pre-cut baseline) was executed and committed in commit b0a326d, closing the gap left by an earlier run of this plan that deferred it — see Deviations."

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
    verification:
      - kind: other
        ref: "python heading/marker-presence check (see Task 3 <verify> in 01-01-PLAN.md); confirmed 0 exit"
        status: pass
    human_judgment: false
    rationale: "Executed in commit b0a326d against a full python packaging/build.py run at commit 1b6059d (post-D-23 fix). Setup.exe (686,684,565 B), expanded tree via a real --expand-to install/uninstall (1,926,039,216 B), built tree (1,919,524,745 B, exact match to 01-CONTEXT.md's independently measured figure), and portable ZIP (884,697,661 B) are all recorded distinctly in 01-EVIDENCE.md, along with top contributors and the pruned-tree audit. The reconciliation is recorded as a partially-explained, explicitly-open question (torch/transformers/duplicate-model removal accounts for ~40% of the installed-size gap but leaves ~455 MB open) rather than averaged or asserted."

duration: 30min (Tasks 1-2) + a follow-up session for D-23/Task 3
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 1: Footprint Measurement Instrument and Evidence Scaffold Summary

**Reusable pytest-verified footprint/pruned-tree audit script (`scripts/measure_package_footprint.py`), a nine-section `01-EVIDENCE.md`, and the pre-cut baseline measured from one freshly built `Setup.exe` (686.7 MB installer, 1.93 GB expanded, 1.92 GB built tree) with the owner-reported-vs-measured size discrepancy recorded as partially explained and explicitly open, not averaged.**

## Performance

- **Duration:** ~30 min (Tasks 1-2, initial run) + a follow-up session that discovered and fixed D-23 (ISCC MAX_PATH normalization, commit 1b6059d) and then executed Task 3 (commit b0a326d)
- **Started:** 2026-07-31T03:13:06Z (approx., per STATE.md `last_updated` at phase start)
- **Completed:** 2026-07-31 (Task 3 and this amendment)
- **Tasks:** 3 of 3 executed
- **Files modified:** 3 new files (Tasks 1-2) + 1 file amended in place (`01-EVIDENCE.md`, Task 3)

## Accomplishments

- Built `scripts/measure_package_footprint.py`: five pure functions (`tree_size`, `top_contributors`, `audit_pruned_tree`, `render_footprint_markdown`, `compare_footprints`) plus a CLI (`--installer`, `--expand-to`, `--tree`, `--assert-pruned`, `--json`, `--markdown`, `--compare`), all in the same walk-and-return-data-structure idiom as `check_clean_state()` in `app/packaging/build.py`.
- `audit_pruned_tree()` checks the six D-01 cut targets (`translations/`, `qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll`) and reports `opengl32sw.dll` presence as a structurally separate, "expected-and-correct" field per D-02 — it can never be mistaken for a violation.
- 16 tests in `tests/test_package_footprint.py`, all passing, against synthetic `tmp_path` trees only — no real installer is ever launched by the test suite.
- Seeded `.planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md` with all nine required ROADMAP-gate headings, each field carrying the literal `NOT YET MEASURED` marker, plus a preamble stating averaging is unacceptable and stale `app/dist/` numbers may not be reused.
- Discovered and fixed D-23 (ISCC receives a non-normalized `..\dist\LecturePack\` path, pushing three `torch` licence files past Windows' 260-char `MAX_PATH` and silently producing no `Setup.exe`) — recorded as a decision in `01-CONTEXT.md` and fixed in commit `1b6059d`.
- Executed Task 3: ran one full `python packaging/build.py` (no `--no-installer`) at commit `1b6059d`, then measured the resulting `Setup.exe` (686,684,565 B), its real expanded install via `--expand-to` (1,926,039,216 B, install/uninstall cycle completed and scratch dir cleaned up), the built `app/dist/LecturePack/` tree (1,919,524,745 B — an exact byte-for-byte match to `01-CONTEXT.md`'s independently measured figure, retiring the build-residue hypothesis), and the portable ZIP (884,697,661 B). Recorded all four, the top contributors, the pruned-tree audit (all 6 D-01 targets present, `opengl32sw.dll` present per D-02, `ggml-base.en.bin` count 2), and the reconciliation in `01-EVIDENCE.md` (commit `b0a326d`).
- Reconciliation: neither the owner's ~800 MB installer recollection nor the ~900 MB installed recollection closes under a MiB/MB reinterpretation — installer is measured *smaller* than recalled, installed is measured *more than double* the recollection. The torch+transformers+duplicate-model hypothesis (D-24) closes ~40% of the installed gap (to ~1.36 GB) but leaves ~455 MB open; recorded as an explicit open question (known / ruled-out / closing-evidence), never averaged or asserted.

## Task Commits

Each executed task was committed atomically:

1. **Task 1: Footprint measurement and pruned-tree audit script** - `68cdaeb` (feat)
2. **Task 2: Seed 01-EVIDENCE.md with an unfilled section per evidence-gate item** - `7a41fdb` (docs)
3. **D-23 prerequisite fix** (ISCC MAX_PATH normalization, found while executing Task 3) - `1b6059d` (fix)
4. **Task 3: Build one fresh installer and record the pre-cut baseline** - `b0a326d` (docs)

## Files Created/Modified

- `scripts/measure_package_footprint.py` - Pure measurement/audit functions plus a subprocess-argument-list-only CLI.
- `tests/test_package_footprint.py` - 16 tests against synthetic trees; also exercises the CLI via `subprocess.run([sys.executable, ...])`.
- `.planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md` - Nine-heading evidence scaffold (Tasks 1-2); baseline size, machine identity, and reconciliation sections filled with measured figures (Task 3, commit `b0a326d`). After-cuts, launch-timing, single-instance, icon, and packaged-smoke sections remain `NOT YET MEASURED` by design — those belong to later plans (01-04, 01-05, 01-08).
- `app/packaging/build.py`, `app/packaging/lecturepack.iss`, `tests/test_installer_iscc_path.py` - D-23 fix: ISCC now receives normalized absolute paths (`/DSourceDir`, `/DOutputDir`) instead of `app/packaging/../dist/LecturePack`, plus a test asserting no `..` segment in the ISCC argv (commit `1b6059d`; not part of this plan's `files_modified` frontmatter but required as a Task 3 prerequisite — see Deviations).

## Decisions Made

- Kept `tree_size`/`top_contributors`/`audit_pruned_tree` walking with `os.walk(..., followlinks=False)` and explicit symlink skips (not `Path.rglob`), to satisfy T-01-01-03 (symlink-loop DoS mitigation) without needing a separate guard function.
- Split the installer/uninstaller invocation into pure `build_install_argv`/`build_uninstall_argv` functions so the "never `shell=True`, argument-list only" requirement (T-01-01-02) is unit-testable without ever spawning a process — the impure `expand_installer()` calls these builders and then `subprocess.run(argv, ...)` with no shell.
- `audit_pruned_tree()`'s return shape keeps `cut_targets` (the six D-01 violations-if-present) and `opengl32sw_present`/`opengl32sw_disposition` as separate top-level keys rather than folding everything into one "violations" list — this was a deliberate structural choice so a caller cannot accidentally treat the D-02 keep as a cut-target violation.

## Deviations from Plan

### Rule 3 — Auto-fixed blocking issue: D-23 (ISCC MAX_PATH) discovered as a Task 3 prerequisite

**While executing Task 3's `python packaging/build.py` run, ISCC aborted with `The system cannot find the path specified` and produced no `Setup.exe`.**

- **Root cause:** `build.py` handed ISCC `str(PKG_DIR / "lecturepack.iss")`, and the `.iss` resolved `..\dist\LecturePack\*` relative to `app/packaging/`, so ISCC internally worked with `...\app\packaging\..\dist\LecturePack\...` — 13 characters longer than the normalized `...\app\dist\LecturePack\...`. Three bundled `torch` third-party licence files sit at 247-250 characters on disk in this checkout (`Documents\LecturePack-beta6-plan`, 12 characters longer than the `Documents\LecturePack` path the plan's own `<open_measurement>` had been verified against), which that extra prefix pushed past Windows' 260-character `MAX_PATH`. This blocked Task 3 outright — no build, no baseline, no evidence — so it was fixed under deviation Rule 3 rather than deferred again.
- **Fix:** `build.py` now hands ISCC already-collapsed absolute paths via `/DSourceDir` and `/DOutputDir`; `lecturepack.iss` consumes them through `{#SourceDir}`/`{#OutputDir}` macros, falling back to the old relative defaults only for manual, defineless ISCC invocations. A new test (`tests/test_installer_iscc_path.py`) asserts the ISCC argv contains no `..` segment, without requiring a real ISCC compile.
- **Recorded as a decision:** D-23 in `01-CONTEXT.md`, which also corrects `<open_measurement>`'s earlier claim that a local `python packaging/build.py` "does produce `LecturePack-<version>-Setup.exe`" — that held in the shorter `Documents\LecturePack` path it was tested in, but not in this checkout, 12 characters longer.
- **Commit:** `1b6059d` (`fix(01-01): normalize ISCC source/output dirs per D-23`).
- **Files touched beyond this plan's `files_modified` frontmatter:** `app/packaging/build.py`, `app/packaging/lecturepack.iss`, `tests/test_installer_iscc_path.py`. This is packaging-code scope, not measurement-instrument scope — flagged here rather than silently absorbed into "Task 3."

### Rule 3 — Auto-fixed blocking issue: preamble literal-marker collision

**`01-EVIDENCE.md`'s Task-2-seeded preamble contained the literal string `` `NOT YET MEASURED` `` inside explanatory prose** ("Every `NOT YET MEASURED` marker below is a **blocking gap**…"). Task 3's own automated `<verify>` command checks for that exact substring anywhere before `## Size — after cuts`, so once the preamble existed, that check could never pass regardless of what Task 3 measured. Reworded the sentence to convey the same meaning ("Every unfilled sentinel marker below is a **blocking gap**…") without the literal collision — wording-only, no change in meaning or in the actual per-field `NOT YET MEASURED` markers that remain everywhere they should. Included in commit `b0a326d`.

### Task 3 now executed (closes the prior run's deferral)

An earlier execution of this plan deferred Task 3 per an explicit orchestrator instruction in that run, leaving `01-EVIDENCE.md`'s baseline sections `NOT YET MEASURED`. This run executed Task 3 as written: one full `python packaging/build.py` (no `--no-installer`) at commit `1b6059d`, followed by the three `measure_package_footprint.py` invocations from the plan (`--installer`, `--tree`, `--installer --expand-to`), with results recorded in `01-EVIDENCE.md` (commit `b0a326d`). See Accomplishments above and `01-EVIDENCE.md` for the full figures and reconciliation. No installer artifact was rebuilt for this run — the `Setup.exe`, `Portable.zip`, and `SHA256SUMS.txt` already on disk from the build performed alongside the D-23 fix were verified present at their exact recorded byte counts and used directly, per this run's explicit instruction not to re-run the multi-minute build a second time.

### Out-of-scope, logged not fixed

**`tests/test_runtime_packaged_smoke.py::test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile` fails in this environment** because `LECTUREPACK_ONEDIR_FIXTURE` is unset (it requires a real packaged onedir fixture). This is pre-existing, unrelated to any file this plan touched, and out of scope per the scope-boundary rule — not fixed, logged here for visibility. The other 3 tests in that file pass, as does the full `tests/test_beta3_packaging.py` suite (9/9).

---

**Total deviations:** 2 Rule 3 auto-fixes (D-23 ISCC MAX_PATH prerequisite; preamble literal-marker collision), 1 out-of-scope pre-existing failure logged.
**Impact on plan:** All three tasks are complete, verified, and committed. Phase 1 Success Criterion 1's pre-cut baseline (installer size, expanded size, built-tree size, portable-ZIP size, top contributors, and a stated reconciliation cause) is recorded in `01-EVIDENCE.md`. The installed-size reconciliation is partially explained (torch/transformers/duplicate-model removal accounts for ~40% of the gap) and the remainder is recorded as an explicit open question rather than closed by assumption — see `01-EVIDENCE.md` `## Size — reconciliation`.

## Issues Encountered

None beyond the D-23 discovery and fix documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The measurement instrument (`scripts/measure_package_footprint.py`) and its test suite are ready for reuse by Plan 01-04 (post-cut audit) and Plan 01-08 (after-cuts baseline and reconciliation).
- The pre-cut baseline in `01-EVIDENCE.md` (`## Machine and build identity`, `## Size — baseline (pre-cut)`, `## Size — reconciliation`) is now measured and recorded. Plan 01-04 rebuilds `app/dist/` and will overwrite the tree this baseline was measured from — that rebuild may now proceed, since the baseline it would otherwise destroy has already been captured.
- **Still open, not a blocker for 01-04:** the residual ~455 MB gap between the owner's ~900 MB installed recollection and the torch/transformers/duplicate-model-adjusted ~1.36 GB figure is recorded as an explicit open question in `01-EVIDENCE.md`, not resolved. Likewise the installer-size direction (owner recalled more than measured) has no stated cause. Neither blocks Plan 01-04's size cuts from proceeding; both remain open for whichever later plan (01-08's reconciliation checkpoint, or the owner directly) can supply the missing evidence.
- Plan 01-02 and 01-03 (also wave 1) are unaffected by this update.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: scripts/measure_package_footprint.py
- FOUND: tests/test_package_footprint.py
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-01-SUMMARY.md
- FOUND: app/dist/installer/LecturePack-0.9.0-beta.6-Setup.exe (686,684,565 bytes, matches recorded figure)
- FOUND: app/dist/installer/LecturePack-0.9.0-beta.6-Portable.zip (884,697,661 bytes, matches recorded figure)
- FOUND: app/dist/installer/LecturePack-0.9.0-beta.6-SHA256SUMS.txt (207 bytes, matches recorded figure)
- FOUND commit: 68cdaeb (Task 1)
- FOUND commit: 7a41fdb (Task 2)
- FOUND commit: 1b6059d (D-23 prerequisite fix)
- FOUND commit: b0a326d (Task 3)
