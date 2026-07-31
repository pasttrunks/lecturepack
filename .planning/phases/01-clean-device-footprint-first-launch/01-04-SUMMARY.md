---
phase: 01-clean-device-footprint-first-launch
plan: 04
subsystem: infra
tags: [packaging, pyinstaller, qt, size-reduction, windows]

# Dependency graph
requires:
  - phase: 01-clean-device-footprint-first-launch
    provides: "01-01: scripts/measure_package_footprint.py (tree_size/top_contributors/audit_pruned_tree) and the seeded 01-EVIDENCE.md pre-cut baseline"
provides:
  - "app/packaging/build.py: PRUNABLE_QT_COMPONENTS + prune_unused_qt_components(dist_app) — post-build deletion of the six D-01 unused Qt components, wired into main() between bundle_engine() and validate_clean_state()"
  - "app/packaging/lecturepack.spec: demo_model_datas duplication removed (D-01/D-05 model dedupe); excludes=[\"torch\", \"transformers\"] added (D-24)"
  - "tests/test_package_pruning.py: 20 tests proving the pruning mechanism, the D-02 opengl32sw.dll keep, the D-05 model-resolution fallback chain, and the D-24 excludes"
  - ".planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-resources.md: D-04 investigation — resources/ measured (106.3 MB, 80.9 MB of which is a .debug.* subset), nothing deleted"
affects: ["01-08-PLAN.md (post-cut build, real measurement, packaged WebEngine render backstop)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-build pruning as a violation-list/walk-and-act function mirroring check_clean_state() (01-PATTERNS.md's prescribed shape), not PyInstaller Analysis.excludes, for Qt components with no importable Python module or that are native link-time deps of WebEngineCore"
    - "Analysis.excludes IS the correct lever for genuine importable top-level packages with zero in-repo importer (torch/transformers, D-24) — this is the complementary case to the post-build-pruning finding, not a contradiction of it"

key-files:
  created:
    - tests/test_package_pruning.py
    - .planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-resources.md
  modified:
    - app/packaging/build.py
    - app/packaging/lecturepack.spec
    - tests/test_demo_session_isolation.py

key-decisions:
  - "D-01 implemented as post-build pruning per 01-RESEARCH.md's empirical finding: excludes has been present in lecturepack.spec since its first commit and never removed these six targets."
  - "D-05 required no new resolution code: engine_adapter.py's _bundled_demo_model_path() fallback chain already reached the canonical resource_dir/models/ copy once the _internal/models/ duplicate is removed — confirmed by reading app_root()/config_manager.py's resource_dir before writing any test, and proven by three new tests covering the single-copy, both-copies, and neither-copy cases."
  - "D-24 (owner decision, new scope beyond the original plan text) implemented via Analysis.excludes, not post-build pruning — torch and transformers are genuine importable top-level packages with zero in-repo importer (grep-confirmed against app/ and lecturepack/), unlike the D-01 Qt add-ons that excludes cannot reach."
  - "D-04 resolved as report-only: resources/ measured at 106.3 MB (80.9 MB is a .debug.* subset), recommendation is keep-not-cut this phase because RESEARCH Assumption A2 (whether Release Qt6WebEngineCore.dll can ever reference a .debug.* file) remains unresolved and this phase has no packaged-WebEngine-render backstop scoped to cover a resources/ cut."
  - "Fixed a pre-existing test (tests/test_demo_session_isolation.py::test_packaging_spec_collects_validated_demo_model_and_frozen_lookup, renamed) that asserted the now-removed demo_model_datas duplicate tuple was present in datas — reworked to assert the dedupe and to prove the frozen fallback reaches the canonical copy, which is a strictly stronger assertion than what it replaced (Rule 1 auto-fix)."

patterns-established:
  - "prune_unused_qt_components() returns {\"removed\": {name: bytes}, \"reclaimed_bytes\": int} rather than only printing, so main() can report it and tests can assert on it — matches audit_pruned_tree()'s inspectable-record precedent from Plan 01-01."

requirements-completed: []

coverage:
  - id: D1
    description: "D-01 Qt pruning: PRUNABLE_QT_COMPONENTS (exactly 6 targets) + prune_unused_qt_components(dist_app), wired into build.py main() between bundle_engine() and validate_clean_state(), idempotent, scoped only to _internal/PySide6/"
    verification:
      - kind: unit
        ref: "tests/test_package_pruning.py (12 tests covering the six-target count, removal, idempotency, scope isolation, disjointness from canonical_inventory, and the inspectable return record)"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-02 opengl32sw.dll survives pruning and a fail-loud build-time assertion guards it"
    verification:
      - kind: unit
        ref: "tests/test_package_pruning.py::test_prune_keeps_opengl32sw_dll_per_d02"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-01/D-05 model dedupe: demo_model_datas removed from lecturepack.spec datas=; DEMO_WHISPER_MODEL RuntimeError guard preserved; frozen fallback chain proven to reach the canonical survivor for single-copy, both-copies, and neither-copy cases; resolve_inventory and audit_pruned_tree confirmed to still resolve/report the deduped model"
    verification:
      - kind: unit
        ref: "tests/test_package_pruning.py (8 tests: spec datas/excludes captured via sandboxed runpy, RuntimeError guard preserved, three model-resolution-chain cases, resolve_inventory, audit_pruned_tree ggml count)"
        status: pass
      - kind: unit
        ref: "tests/test_demo_session_isolation.py::test_packaging_spec_validates_demo_model_source_and_frozen_lookup_falls_back"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-24 excludes: torch and transformers added to Analysis.excludes, confirmed absent from requirements.txt and grep-confirmed unimported anywhere under app/ or lecturepack/"
    verification:
      - kind: unit
        ref: "tests/test_package_pruning.py::test_spec_excludes_torch_and_transformers, test_spec_excludes_captured_include_torch_and_transformers"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-04 resources/ investigation report: measured inventory, debug/release pairing, reachability preflight (grep for QTWEBENGINE_*/DevTools — zero occurrences), keep-not-cut recommendation naming RESEARCH Assumption A2, scope statement, and the measured Tasks-1-2-vs-resources/ interaction table — nothing deleted"
    verification:
      - kind: other
        ref: "python heading/marker-presence check (Task 3's own <verify> command); confirmed 0 exit"
        status: pass
    human_judgment: false
  - id: D6
    description: "Full test suite compared against the 944/7 pre-plan baseline shows zero new failures"
    verification:
      - kind: unit
        ref: "pytest (964 passed, 7 failed, 177.87s) — 944 baseline + 20 new tests from tests/test_package_pruning.py; the 7 failures are byte-identical to the pre-existing, pre-documented set in deferred-items.md"
        status: pass
    human_judgment: false
  - id: D7
    description: "Build-dependent verification (a real python packaging/build.py run producing a post-cut app/dist/LecturePack/, the --assert-pruned audit against that real tree, the packaged runtime smoke against it, and the packaged WebEngine render proof) — explicitly NOT performed by this plan"
    verification: []
    human_judgment: true
    rationale: "The clean-venv rebuild and its downstream verification (packaged smoke, real transcription, WebEngine render check) is orchestrator-owned per this dispatch's explicit build-split instruction. This plan implements and unit-tests the source/spec changes only; the orchestrator runs the real build and closes out this remainder. Recorded here, not asserted as passed."

# Metrics
duration: ~45min
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 4: Packaging Size Cuts — Qt Pruning, Model Dedupe, torch/transformers Excludes, resources/ Investigation Summary

**Post-build pruning removes six unused Qt components (~101 MB) and dedupes `ggml-base.en.bin` (~148 MB) via a two-line spec change plus a proven fallback chain; `Analysis.excludes` now also drops undeclared `torch`/`transformers` (~416.5 MB, D-24); `resources/`'s 106.3 MB stays untouched with a written investigation report recommending keep-not-cut.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-31 (this session)
- **Completed:** 2026-07-31
- **Tasks:** 3 of 3 executed
- **Files modified:** 3 modified (`app/packaging/build.py`, `app/packaging/lecturepack.spec`, `tests/test_demo_session_isolation.py`) + 2 new (`tests/test_package_pruning.py`, `01-FINDINGS-resources.md`)

## Accomplishments

- **Task 1 (D-01, D-02, D-03):** Added `PRUNABLE_QT_COMPONENTS` (exactly six entries: `translations/`, `qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll`) and `prune_unused_qt_components(dist_app) -> dict` to `app/packaging/build.py`, wired into `main()` between `bundle_engine()` and `validate_clean_state()`. Measured against the real (pre-cut) `app/dist/LecturePack/_internal/PySide6/` tree: these six targets total **100,964,806 bytes (~101.0 MB)**. `opengl32sw.dll` is asserted present after pruning and the build aborts loudly (`sys.exit`) if it is ever missing — a fail-loud guard against a future edit to the target list accidentally widening scope, per D-02. Pruning is idempotent (a second run reports zero removals) and scoped strictly to `_internal/PySide6/` (a synthetic-tree test seeds files at `bin/`, `models/`, `smoke/`, `lecturepack.ico`, and `_internal/base_library.zip` and asserts every one survives). Did not modify `lecturepack.spec`'s `excludes` list for the Qt cuts — `01-RESEARCH.md`'s empirical proof (the list has carried these names' siblings since the spec's first commit and never removed any of them) is confirmed by a source-order test (`test_spec_excludes_list_unchanged_by_pruning_mechanism`), not just cited.
- **Task 2 (D-01, D-05, D-24):** Removed `demo_model_datas = [(DEMO_WHISPER_MODEL, "models")]` and its reference in `Analysis(datas=...)` from `lecturepack.spec` (a 2-line change) — this was pure duplication of `bundle_engine()`'s copy, **~147,964,211 bytes (~148.0 MB)**. The `DEMO_WHISPER_MODEL` existence/size `RuntimeError` guard is preserved unchanged, since `bundle_engine()` still needs that source file present to copy from; a monkeypatched-`os.path.isfile` test proves the guard still fires when the source is missing. **No new resolution code was written** — reading `app/desktop/engine_adapter.py`'s `_bundled_demo_model_path()` and `app/desktop/paths.py`'s `app_root()` confirmed the existing three-candidate chain already falls through candidate 1 (`app_root()/models/...`, the removed duplicate, frozen `app_root()` returns `_MEIPASS` == `_internal/`) to candidates 2/3 (`config.resource_dir/models/...`, which `lecturepack/infrastructure/config_manager.py`'s `_resource_dir()` resolves to `dirname(sys.executable)` when frozen — the exact top-level directory `bundle_engine()` places the survivor in). Three new tests prove the chain for the single-copy (D-05-named), both-copies (backward-compat), and neither-copy (empty-string, no raise) cases. `resolve_inventory()` and `audit_pruned_tree()` were independently confirmed to still resolve/report the deduped model correctly. **D-24 (owner decision, additional scope beyond this plan's original text):** added `excludes=["torch", "transformers"]` to the same `Analysis(...)` call — grep-confirmed neither package is imported anywhere under `app/` or `lecturepack/`, nor listed in `app/requirements.txt`; measured against the real tree, `torch` is 378,347,026 bytes (378.3 MB) and `transformers` is 38,128,476 bytes (38.1 MB), totaling **~416,475,502 bytes (~416.5 MB)** — more than the entire D-01 cut scope combined. Unlike the Qt add-ons, `excludes` is the correct, effective lever here because these are genuine importable top-level packages, not native link-time dependencies or module-less DLLs.
- **Task 3 (D-04):** Wrote `01-FINDINGS-resources.md`. Freshly measured `_internal/PySide6/resources/` at **106,290,093 bytes (106.3 MB, 101.4 MiB)** across 10 files, all matching a debug/release pairing pattern except `icudtl.dat` (no debug variant, unconditionally required). The `.debug.*` subset totals **80,904,435 bytes (80.9 MB)** — larger than the entire D-01 Qt cut list — with `qtwebengine_devtools_resources.debug.pak` alone at 75,843,536 bytes (71% of the directory). Confirmed no `d`-suffixed (debug-build) Qt DLL exists anywhere under `_internal/PySide6/` (this build ships Release Qt6 only). Ran the reachability preflight (grep for `QTWEBENGINE_*`/DevTools/remote-debugging usage across `app/` and `lecturepack/`): **zero occurrences found**, recorded as a finding. **Recommendation: keep, not cut, this phase** — RESEARCH Assumption A2 (whether a Release `Qt6WebEngineCore.dll` can ever reference a `.debug.*` file under any code path) remains unresolved, and this phase's only packaged-render backstop (Plan 01-08) is scoped to the six approved D-01 targets, not `resources/`. **Deleted nothing.** Recorded the measured interaction: Tasks 1-2 plus D-24 project reducing the pre-cut 1,919,524,745-byte built tree to ~1,254,120,226 bytes (~34.7% reduction) without touching `resources/` at all, leaving it at ~8.5% of the projected post-cut tree — handed to the owner as a number, not a decision this document makes.

## Task Commits

Each executed task was committed atomically:

1. **Task 1: Post-build Qt pruning in build.py** - `e3c2992` (feat)
2. **Task 2: Dedupe ggml-base.en.bin, D-24 torch/transformers excludes, fix pre-existing test** - `246f264` (fix)
3. **Task 3: Investigate PySide6/resources/ and report — no deletion** - `fa0faa6` (docs)

## Files Created/Modified

- `app/packaging/build.py` — `PRUNABLE_QT_COMPONENTS`, `_path_size()`, `prune_unused_qt_components(dist_app)`, called from `main()` between `bundle_engine()` and `validate_clean_state()`.
- `app/packaging/lecturepack.spec` — removed `demo_model_datas` (D-01/D-05 dedupe); added `"torch"`, `"transformers"` to `Analysis.excludes` (D-24); updated the comment above the `DEMO_WHISPER_MODEL` guard to explain the new single-bundle truth.
- `tests/test_package_pruning.py` (new) — 20 tests: 12 for Task 1's pruning mechanism (including the D-02-named opengl32sw.dll keep, idempotency, scope isolation, canonical-inventory disjointness, source-order assertion, and the excludes-list-unchanged assertion), 2 for D-24's excludes, 6 for Task 2's spec/dedupe/resolution-chain behaviors.
- `.planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-resources.md` (new) — D-04 investigation report with all five required sections.
- `tests/test_demo_session_isolation.py` — fixed a pre-existing assertion broken by the D-01 dedupe (see Deviations).

## Decisions Made

- Used a single dict (`name -> relative path tuple`) for `PRUNABLE_QT_COMPONENTS` rather than separate dir/file tuples, dispatching on `Path.is_dir()`/`is_file()` at prune time — simpler than tracking kind explicitly and matches the plan's "exactly 6 members" acceptance criterion cleanly.
- Bundled D-24's `excludes` addition into the same `lecturepack.spec` commit as the D-01/D-05 model dedupe, since both are edits to the same `Analysis(...)` call and D-24 is owner-decided scope explicitly assigned to this plan by the dispatch (not present in the original 01-04-PLAN.md text, which predates the D-24 decision).
- Fixed `tests/test_demo_session_isolation.py`'s `test_packaging_spec_collects_validated_demo_model_and_frozen_lookup` (renamed `test_packaging_spec_validates_demo_model_source_and_frozen_lookup_falls_back`) rather than leaving it broken — its old assertion (`(str(model), "models") in datas`) directly tested the duplication this plan's D-01 mandate removes. The rewritten test asserts the dedupe positively (`not in datas`) and proves the frozen fallback reaches `config.resource_dir`'s canonical copy when no `_internal/models/` duplicate exists, which is a strictly stronger and more relevant assertion than the one it replaced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/stale test] Fixed a pre-existing test broken by the D-01 model dedupe**
- **Found during:** Task 2, running the plan's own required verification command (`pytest tests/test_demo_session_isolation.py ...`).
- **Issue:** `tests/test_demo_session_isolation.py::test_packaging_spec_collects_validated_demo_model_and_frozen_lookup` asserted `(str(model), "models") in datas` — directly testing the presence of the `demo_model_datas` tuple this plan's D-01/D-05 mandate requires removing. Removing the duplication (as instructed) made this specific assertion fail, exactly as expected for an assertion that encoded the old, duplicated behavior.
- **Fix:** Reworked the test (renamed for clarity) to assert the dedupe positively — the tuple is absent from `datas`, the `DEMO_WHISPER_MODEL` guard still exists and the source file is still real, and the frozen fallback chain still reaches a real model file when only `config.resource_dir`'s canonical copy exists (no `_internal/models/` duplicate). This is a strengthening, not a weakening: it now actively proves the D-05 resolution-chain requirement in addition to what it originally tested.
- **Files modified:** `tests/test_demo_session_isolation.py`.
- **Verification:** `pytest tests/test_demo_session_isolation.py -x` — 22/22 pass.
- **Committed in:** `246f264` (Task 2 commit).

---

**Total deviations:** 1 Rule 1 auto-fix (pre-existing test updated to match the mandated dedupe, strengthened rather than weakened).
**Impact on plan:** No scope creep — this was a direct, necessary consequence of implementing D-01/D-05 exactly as specified. D-24 (torch/transformers excludes) was explicit owner-decided scope assigned by this dispatch, not a self-initiated deviation.

## Issues Encountered

None beyond the test fix documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness — and what is explicitly UNVERIFIED

**This plan implements and unit-tests the source/spec changes only. It does NOT run a real build.** Per this dispatch's explicit build-split instruction, the following are **orchestrator-owned and explicitly left unverified here** — not asserted, not claimed passed, not silently dropped:

- **A real `python packaging/build.py` run producing a post-cut `app/dist/LecturePack/`.** All measurements in this summary and in `01-FINDINGS-resources.md` are computed from the existing pre-cut tree (Plan 01-01's baseline build, commit `1b6059d`) plus static analysis of the removed/excluded targets' sizes in that same tree — they are accurate measurements of what *will* be removed, but no new build has actually produced a pruned/deduped/excluded tree yet.
- **`scripts/measure_package_footprint.py --tree app/dist/LecturePack --assert-pruned`** against a real post-cut tree — this exits non-zero on any D-01 violation and is the correct instrument (built in Plan 01-01) but has not been run against output this plan produced, because no such output exists yet.
- **The packaged runtime smoke** (`tests/test_runtime_packaged_smoke.py`'s real-fixture test, which requires `LECTUREPACK_ONEDIR_FIXTURE`) against the post-cut tree.
- **The real staged whisper-cli transcription** as admission evidence against the post-cut, deduped model.
- **The packaged WebEngine render proof** — per `01-RESEARCH.md`'s Pitfall 1 and this plan's own threat register (T-01-04-01), the existing automated smoke never launches `QWebEngineView`, so nothing here proves `Qt6Quick.dll`/`Qt6Qml.dml` removal did not break WebEngine's internal compositor. This is recorded in the plan's `must_haves` as a `backstop` owned by Plan 01-08, and remains genuinely unverified until that plan (or the orchestrator's own build+smoke pass) runs it.

**Ready for the orchestrator to:** run `python packaging/build.py` from a clean venv (per D-24 point 2 — a fresh venv built only from the project's locked requirements, so undeclared global packages cannot be collected again), then `scripts/measure_package_footprint.py --tree app/dist/LecturePack --assert-pruned --json <out>.json`, compare against `01-EVIDENCE.md`'s pre-cut baseline via `--compare`, run the packaged runtime smoke with `LECTUREPACK_ONEDIR_FIXTURE` pointed at the fresh tree, and perform one real local transcription plus a packaged WebEngine launch showing rendered content. Fill `01-EVIDENCE.md`'s `## Size — after cuts` section from that run (explicitly not filled by this plan, per that file's own instruction).

**Unaffected:** Plans 01-02, 01-03, 01-05, 01-06 (already landed, wave 1/2) are unaffected by this plan's changes — no bridge, UI, or startup-sequencing files were touched.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: app/packaging/build.py
- FOUND: app/packaging/lecturepack.spec
- FOUND: tests/test_package_pruning.py
- FOUND: tests/test_demo_session_isolation.py
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-FINDINGS-resources.md
- FOUND: .planning/phases/01-clean-device-footprint-first-launch/01-04-SUMMARY.md
- FOUND commit: e3c2992 (Task 1)
- FOUND commit: 246f264 (Task 2)
- FOUND commit: fa0faa6 (Task 3)
- FOUND commit: 8d4d856 (Summary)

---

## Orchestrator addendum — D-24 build verification (2026-07-31)

The plan was executed with its build-dependent criteria left explicitly unverified, because
`packaging/build.py` takes ~15 minutes and three prior executor dispatches had builds die the
instant their agent context ended. The orchestrator ran that step afterwards. **All previously
unverified criteria now pass.** Results are recorded in `01-EVIDENCE.md` `## Size — after cuts`.

**Clean venv (D-24 clause 2):** `.venv` created fresh with `python -m venv`, populated from
`app/requirements.txt` + `app/requirements-build.txt` plus `tzdata`. `torch`, `transformers`,
and `sklearn` confirmed absent from the venv *before* building.

**Post-cut build:** exit 0, clean log, no ISCC failure (D-23 holding).

| Figure | Pre-cut | Post-cut | Δ |
|---|---|---|---|
| `Setup.exe` | 686,684,565 B | 376,323,704 B | −45.2% |
| Built tree | 1,919,524,745 B | 1,081,124,808 B | −43.7% (−799.6 MiB) |
| Portable ZIP | 884,697,661 B | 494,736,030 B | −44.1% |

**`--assert-pruned` against the real post-cut tree: exit 0.** All six D-01 targets absent;
`opengl32sw.dll` present (D-02); `ggml-base.en.bin` count exactly 1 (D-05).

**D-24 runtime guards: both satisfied.** 33/33 pass across
`test_runtime_packaged_smoke.py`, `test_beta3_packaging.py`, `test_package_pruning.py` with
`LECTUREPACK_ONEDIR_FIXTURE` pointed at the post-cut tree.
`test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile` performs the real
`whisper-cli.exe` transcription from a Unicode path and drives full admission to `HEALTHY` —
so it is simultaneously the packaged smoke, the required real transcription, proof D-05's
surviving model copy resolves, and proof AD-18's ASCII staging boundary holds after the cuts.
**Admission reached `HEALTHY` with `torch`/`transformers` absent, so neither is requested at
runtime** — D-24's stop-and-report condition did not trigger.

**Actual cuts exceeded the plan's ~658 MB projection by ~180 MB.** The surplus is not
additional deliberate cutting: `sklearn` (11.9 MiB) was only ever a global-env artifact, and
`cv2` shrank because `app/requirements.txt` pins `opencv-python-headless` where the global env
had the heavier `opencv-python`. Credit belongs to D-24's clean-venv clause, not to D-01.

**Still unverified, correctly deferred to 01-08's physical session:** expanded-tree size (needs
a silent install/uninstall of the post-cut `Setup.exe`), cold and warm launch timings, the
two-process raise-and-focus proof, and the icon-visible proof.

**Discovered during this step, logged not fixed:** `app/requirements.txt` does not mirror the
repo-root `requirements.txt` despite claiming to — `Send2Trash`, `tzdata`, and `yt-dlp` are
missing, and CI installs only `app/requirements.txt`. The `Send2Trash` gap means packaged
builds hard-delete user files where `engine_adapter.py:1206` intends a recycle-bin move. See
`deferred-items.md`.

**One pre-existing failure retired:** `test_runtime_packaged_smoke.py::test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile`
was counted among the 7 known failures only because it requires `LECTUREPACK_ONEDIR_FIXTURE`.
Given a real fixture it passes. The genuine pre-existing count is **6**, all stale-fixture
`manifest signature verification failed` cases.
