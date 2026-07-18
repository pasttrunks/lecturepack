---
phase: 01-packaging-release
verified: 2026-07-18T17:51:05Z
status: gaps_found
score: 40/47 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Version strings consistently report 1.2.0 across all release artifacts"
    status: failed
    reason: "The shipped 1.2.0 ZIP contains README-FIRST.txt labeled v0.2.0 and RELEASE_NOTES.md headed v1.1.0; build_release.py also retains a v0.2.1 tool label."
    artifacts:
      - path: "README-FIRST.txt"
        issue: "Portable-release banner reports v0.2.0; the same stale banner is shipped in the ZIP."
      - path: "RELEASE_NOTES.md"
        issue: "Top-level release heading reports v1.1.0; the identical file is shipped in the ZIP and copied to dist-release."
      - path: "build_release.py"
        issue: "Module header reports v0.2.1 despite canonical VERSION being 1.2.0."
    missing:
      - "Update every current portable-release label/document to 1.2.0 and describe the v1.2 release."
      - "Extend the version regression test to cover the shipped release documents and build-tool label."
      - "Rebuild the ZIP and regenerate checksum/manifest evidence after correcting the packaged documents."
  - truth: "The documented release builder is a fail-closed, repeatable producer of the required portable package"
    status: partial
    reason: "The successful build used an external one-off safety wrapper. Direct `python build_release.py` can recursively delete unapproved output content and can exit zero when required FFmpeg, CPU Whisper, or documentation inputs are missing. Its per-binary checksum inventory also omits the primary CPU Whisper runtime."
    artifacts:
      - path: "build_release.py"
        issue: "Lines 92-97 delete build/dist/dist-release after only isdir(); lines 120-165 downgrade required missing inputs to warnings; lines 195-205 look for CPU Whisper files in the wrong directory and omit WHISPER_CPU_DLLS."
      - path: "dist-release/BUILD_MANIFEST.json"
        issue: "Current manifest contains ZIP, FFmpeg, and Vulkan entries but no root CPU whisper-cli/Whisper/ggml runtime entries."
    missing:
      - "Move exact-target, reparse-point, and dist-release allowlist validation into build_release.py and test rejection before deletion."
      - "Validate all required FFmpeg, CPU Whisper, documentation, and partial-Vulkan inputs before cleanup/build; fail nonzero on an incomplete required set."
      - "Checksum WHISPER_BINS and WHISPER_CPU_DLLS from the app root and test complete unique runtime coverage."
deferred:
  - truth: "Runtime calls cross only adjacent UI, controller, service, and infrastructure boundaries"
    addressed_in: "Phase 2"
    evidence: "Phase 2 success criterion 5 requires the whole-tree architecture audit to report zero adjacent-layer violations and explicitly closes the 47-item baseline debt."
  - truth: "Dependency direction is UI to Controller to Service to Infrastructure, never the reverse or skipping a layer"
    addressed_in: "Phase 2"
    evidence: "Phase 2 goal and plan 02-04 specifically own routing controller/UI dependencies through adjacent layers and retiring the baseline."
---

# Phase 1: Packaging & Release Verification Report

**Phase Goal:** v1.2 is packaged, tested, validated, and available as a portable release  
**Verified:** 2026-07-18T17:51:05Z  
**Status:** gaps_found  
**Re-verification:** No — initial verification

## Goal Achievement

The generated executable and archive are real and currently runnable: the 158-item
source suite is recorded passing, both frozen self-tests pass, the ZIP digest is
internally consistent, required runtime files are present, forbidden payloads are
absent, and the architecture no-regression gate has zero new identities. The goal
is nevertheless not complete because the portable archive ships obsolete release
identities and the documented builder does not itself enforce the safety and
completeness contract used by the one successful build.

### Observable Truths

Roadmap truths replace clearly duplicative PLAN truths; PLAN-only detail remains
separate. `DEFERRED` items are specifically owned by Phase 2 and are not actionable
Phase 1 gaps. `UNCERTAIN` items are externally tagged backstops without explicit
held-out evidence; the verifier abstains rather than inferring a pass.

| # | Truth | Status | Evidence |
|---:|---|---|---|
| 1 | Full pytest suite passes with a documented current count | VERIFIED | Retained log: 158 passed, exit 0; independent collection now reports 158 items. |
| 2 | Development `--selftest` passes for 1.2.0 without import/QThread lifecycle failure | VERIFIED | Retained development log has timeout false, exit 0, `SELFTEST PASS`; source ordering inspected. |
| 3 | PyInstaller builds and the packaged EXE initializes | VERIFIED | Real build exit 0; onedir EXE exists; frozen onedir self-test passes. |
| 4 | Version strings consistently report 1.2.0 across all artifacts | FAILED | ZIP ships README-FIRST v0.2.0 and RELEASE_NOTES v1.1.0; build script header says v0.2.1. |
| 5 | Clean extraction to a path containing spaces launches without fatal errors | VERIFIED | Extracted frozen log records a unique spaced temp path, timeout false, exit 0, PASS. |
| 6 | No architecture violation absent from `25e9dd1`; 47-item debt disclosed | VERIFIED | Independent baseline comparison: 47 current, 47 baseline, 0 new, 0 resolved; strict conformance `NO`. |
| 7 | Reapplying version wiring leaves one authority and cache-key versions unchanged | VERIFIED | Current imports use `lecturepack.__version__`; diff changes no detector/repair cache-key constant. |
| 8 | Concurrent import consumers observe one immutable version | VERIFIED | Independent 64-consumer threaded import check returned only `(1.2.0, 1.2.0, 1.2.0)`. |
| 9 | Hidden-import list is non-empty and includes every named v1.1/v1.2 module | VERIFIED | Spec inspected; focused regression test independently passes. |
| 10 | Repeated clean PyInstaller analysis yields identical module/optimization configuration | UNCERTAIN | `verification: backstop`; one real build exists, but no repeated-analysis held-out comparison was run. |
| 11 | Pytest collection succeeds and records the actual collected-case count | VERIFIED | Retained and independent `--collect-only -q` both report 158, exit 0. |
| 12 | Alignment proves greatest overlap, equal tie to earlier, slide coverage, and one assignment | VERIFIED | Four public ExportService-path tests are collected/passed; tie test independently rerun and passed. |
| 13 | Thirteen inherited product requirements map to executable current-run nodes/checks | VERIFIED | Traceability has 42 covered clauses, 37 unique mapped nodes, no gaps; all 37 appear as PASSED in the retained log. |
| 14 | Privacy audit is current, strict, and records zero violations | VERIFIED | Audit exit 0, `PRIVACY_VIOLATION_COUNT: 0`, `PRIVACY_CHECK: PASS`. |
| 15 | Empty/absent optional inputs fail closed without network, plaintext secrets, or video mutation | VERIFIED | Consent/secret/upload and no-deletion mapped tests pass; static privacy audit passes. |
| 16 | Ordering/product mode cannot bypass online consent or Private Local default | VERIFIED | Backend consent/default and product-mode tests are collected/passed. |
| 17 | Repeated supported operations preserve privacy/no-deletion invariants | VERIFIED | Export/re-export no-deletion and repeated lifecycle tests pass. |
| 18 | Parallel transcription/slide detection preserves consent, secret, and publication boundaries | VERIFIED | Concurrent/fallback/branch-isolation tests pass. |
| 19 | Missing/failed transcription output cannot replace valid canonical output | VERIFIED | Groq/backend fallback and prior-output preservation tests pass. |
| 20 | Unicode transcript text and safely escaped Windows paths survive canonical formats | UNCERTAIN | `verification: backstop`; UTF-8 code exists, but no held-out Unicode + non-ASCII path test proves the combined claim. |
| 21 | Exact equal-overlap boundaries resolve to the earlier slide | VERIFIED | Named public-path boundary test passes. |
| 22 | A segment merely touching a slide boundary follows a defined overlap contract | UNCERTAIN | `verification: backstop`; no named boundary-touch test exists. |
| 23 | Empty slide/segment collections return a defined non-crashing result | UNCERTAIN | `verification: backstop`; no held-out empty-collection alignment test exists. |
| 24 | Equal-overlap results preserve chronological order and assign once | VERIFIED | Tie and exactly-once tests pass. |
| 25 | Floating-point comparisons preserve the earlier-slide tie rule | VERIFIED | Equal-overlap test uses floating timestamp values and passes. |
| 26 | Provider-neutral signals remain valid beside slide detection | VERIFIED | Backend contract and concurrent scheduler tests pass. |
| 27 | Groq overlap de-duplication retains distinct neighboring words | VERIFIED | Merge/dedup test passes. |
| 28 | Missing credentials/consent/responses/chunks fail closed and preserve prior output | VERIFIED | Consent, structured failure, resume, and prior-output tests pass. |
| 29 | Successful provider chunks merge in source order before canonical publication | VERIFIED | Ordered chunk/merge and mock integration tests pass. |
| 30 | Identical provider requests reuse cached chunks and publish consistently | VERIFIED | Resume/cache mock integration test passes. |
| 31 | Provider concurrency is bounded/cancellable and fallback preserves slide branch | VERIFIED | Cancel and online-fallback branch tests pass. |
| 32 | Repeated cancellation/close cannot resurrect a retired worker | VERIFIED | Stability close/cancel tests pass. |
| 33 | Process-tree termination targets owned PIDs and preserves unrelated processes | VERIFIED | Named process-tree test passes. |
| 34 | Runtime layer calls are strictly adjacent | DEFERRED | Current audit has 47 violations; Phase 2 specifically owns zero-violation closure. |
| 35 | Dependency direction never skips/reverses layers | DEFERRED | Same 47-item disclosed baseline; Phase 2 plan 02-04 owns repair. |
| 36 | Widgets remain on the Qt thread while external/internal work uses approved boundaries | VERIFIED | UI/stability/scheduler tests pass; no new architecture identity was introduced. |
| 37 | Release test gate accepts exactly zero failure/collection-error results | VERIFIED | Current collection and full run both exit 0; retained suite has zero failures/errors. |
| 38 | Test total comes from pytest collection | VERIFIED | Independent collector reports 158. |
| 39 | Parameterized cases are counted at pytest-item granularity | VERIFIED | Two functions expand into two items each. |
| 40 | Reconciliation explains historical 149/151 and current 156/158 counts | VERIFIED | Reconciliation documents the two expansions plus seven added tests. |
| 41 | Real onedir and ZIP include required EXE, internal, FFmpeg, CPU/Vulkan, and docs layout | VERIFIED | Independent ZIP inspection: 933 entries, 0 required entries missing. |
| 42 | Portable ZIP checksum recomputes exactly | VERIFIED | Independent SHA-256 equals SHA256SUMS and manifest: `f5680469…0715f9e`. |
| 43 | Current cleanup preflight validates exact repo-child, non-reparse targets | VERIFIED | Current-run build evidence records three validated targets and preflight PASS. |
| 44 | Current pre-deletion inventory rejects non-allowlisted release entries | VERIFIED | Current-run evidence records a non-following root allowlist and authorization before build. |
| 45 | Onedir/ZIP exclude models, secrets, config, jobs, transcripts, slides, and media | VERIFIED | Independent ZIP scan: 0 forbidden entries; retained onedir/extracted checks pass. |
| 46 | Frozen self-test uses empty throwaway state without model/media/secret/network | VERIFIED | Selftest source uses a temp directory; both real frozen executions pass without those inputs. |
| 47 | Frozen self-test performs imports, window/event work, and normalization before PASS | VERIFIED | `run_selftest` ordering inspected; `optimize=0`; both real frozen runs reach PASS. |

**Score:** 40/47 truths verified. One truth failed, four externally tagged
backstops lack explicit evidence, and two strict-architecture truths are
specifically deferred to Phase 2.

## Required Artifacts

| Artifact group | Status | Details |
|---|---|---|
| Canonical version files (`__init__.py`, `constants.py`, spec) | VERIFIED | Runtime authority and executable consumers are 1.2.0; spec uses `optimize=0`. |
| `build_release.py` | PARTIAL | Current build works, but direct cleanup/input/checksum paths are not fail-closed and its header is stale. |
| Packaging/alignment tests | PARTIAL | Existing focused tests pass, but version coverage omits the documents actually shipped. |
| Decision log | VERIFIED | AD-14 and AD-15 are present and consistent with the intended contracts. |
| Eight source-validation artifacts | VERIFIED | All exist, are substantive, mutually consistent, and map 37 current passing nodes. |
| `dist/LecturePack/LecturePack.exe` | VERIFIED | Real frozen executable exists and passed self-test. |
| Portable ZIP | PARTIAL | Runtime/integrity checks pass, but packaged README/release notes identify obsolete releases. |
| SHA256SUMS | VERIFIED | Whole-ZIP digest independently matches. |
| BUILD_MANIFEST | PARTIAL | Whole-ZIP digest/version pass; per-binary list omits the primary CPU Whisper runtime. |
| Root/packaged release documents | FAILED | README-FIRST reports v0.2.0 and RELEASE_NOTES reports v1.1.0. |
| Build/frozen validation evidence | VERIFIED | Exact commands, timeouts, exits, inventories, exclusions, and cleanup state are retained for this run. |

## Key Link Verification

| From | To | Status | Details |
|---|---|---|---|
| `lecturepack.__version__` | `constants.APP_VERSION` / `build_release.VERSION` | VERIFIED | Manual inspection and focused test show direct aliases; generic query false negatives were regex-tool limitations. |
| `constants.APP_VERSION` | new job manifest | VERIFIED | Focused manifest test and source link pass. |
| Alignment tests | public `ExportService.align_and_export` | VERIFIED | Tests invoke the public path and inspect `aligned.json`. |
| `python -m lecturepack --selftest` | `run_selftest` | VERIFIED | Dispatch and two real frozen executions verified. |
| `LecturePack.spec` | onedir EXE | VERIFIED | Build evidence invokes current spec; resulting EXE passes. |
| Canonical version | BUILD_MANIFEST/ZIP filename | VERIFIED | Manifest and ZIP report 1.2.0. |
| ZIP | SHA256SUMS/manifest digest | VERIFIED | All three digests are equal. |
| Cleanup guard | documented `build_release.py` entry point | PARTIAL | Guard existed only in the external execution wrapper; direct entry point bypasses it. |

## Data-Flow Trace (Level 4)

Not applicable: this phase produces release tooling, validation evidence, and a
portable package rather than a dynamic data-rendering artifact.

## Behavioral Spot-Checks

| Behavior | Command/check | Result | Status |
|---|---|---|---|
| Current pytest collection | `.venv\Scripts\python.exe -m pytest --collect-only -q` | 158 items, exit 0 in 1.5s | PASS |
| Version/spec/alignment guard | Three named focused pytest nodes | 3 passed in 1.03s | PASS |
| Concurrent version imports | 64 threaded import consumers | All returned 1.2.0 for package/app/build values | PASS |
| ZIP integrity/inventory | Get-FileHash + read-only ZIP entry scan | SHA equal; 933 entries; 0 missing required; 0 forbidden | PASS |
| Architecture identity baseline | Compare retained identities with `git show 25e9dd1:…` | baseline 47, current 47, new 0, resolved 0 | PASS |
| Shipped document identity | Read ZIP README/release-note headings | v0.2.0 and v1.1.0 | FAIL |

The full suite was not rerun: the retained unabridged 158-pass log is current,
the worktree is clean, no source changed after that evidence, and verifier rules
prefer collection plus named tests over repeating a two-minute suite.

## Probe Execution

SKIPPED — no phase-declared or conventional probe script exists for this release
phase. Real frozen execution is represented by the retained subprocess logs and
the read-only artifact checks above.

## Requirements Coverage

| Requirement | Source plan | Status | Evidence / disposition |
|---|---|---|---|
| REQ-core-conversion | 01-02 | SATISFIED | Mapped integration/mode nodes pass. |
| REQ-privacy-safety | 01-02, 01-03 | SATISFIED | Strict audit 0; behavioral nodes pass; ZIP exclusions rechecked. |
| REQ-transcription | 01-02 | SATISFIED | Canonical-output/provenance/format nodes pass. |
| REQ-slide-extraction | 01-02 | SATISFIED | Deterministic worker/target/false-positive nodes pass. |
| REQ-alignment | 01-02 | SATISFIED | Four exact public-path acceptance nodes pass. |
| REQ-export-formats | 01-02 | SATISFIED | Export/serializer/provenance nodes pass. |
| REQ-job-lifecycle | 01-02 | SATISFIED | Persistence/cancel/cache/no-deletion nodes pass. |
| REQ-study-workspace | 01-02 | SATISFIED | Old-job/state/navigation/export nodes pass. |
| REQ-provider-neutral-transcription | 01-02 | SATISFIED | Contract/injection/default/provenance nodes pass. |
| REQ-groq-transcription | 01-02 | SATISFIED | Fake-provider chunk/retry/cache/fallback nodes pass; live call correctly not claimed. |
| REQ-stability | 01-02 | SATISFIED | Close/PID/backend persistence nodes pass. |
| REQ-architecture-layers | 01-01, 01-02 | SATISFIED FOR PHASE 1 | Zero-new gate passes; strict closure explicitly deferred to Phase 2. |
| REQ-test-framework | 01-01, 01-02 | SATISFIED | pytest/pytest-qt/integration/CV/UI nodes collected and passed. |
| REQ-version-bump | 01-01, 01-03 | BLOCKED | Runtime/manifest/ZIP are 1.2.0, but shipped docs/tool label report 0.2.0/1.1.0/0.2.1. |
| REQ-packaging-spec-audit | 01-01, 01-03 | SATISFIED | Hidden modules/optimize guard pass; real frozen imports pass. |
| REQ-packaged-build | 01-03 | BLOCKED | Current archive runs, but packaged docs are stale and direct builder is not fail-closed/repeatable; clean-machine SmartScreen remains human-only. |
| REQ-test-suite-pass | 01-02 | SATISFIED | 158 passed, 0 failures/errors, exit 0. |
| REQ-self-test | 01-02, 01-03 | SATISFIED | Development, onedir, and extracted runs pass. |
| REQ-test-reconciliation | 01-02 | SATISFIED | No orphan requirement; 156 source functions + 2 expansion delta = 158. |

All 19 Phase 1 requirement IDs appear in at least one plan; there are no
orphaned roadmap requirements.

## Anti-Patterns and Disconfirmation Pass

| File | Line(s) | Finding | Severity | Impact |
|---|---:|---|---|---|
| `build_release.py` | 3 | Stale v0.2.1 release-tool label | BLOCKER | Directly falsifies roadmap version consistency. |
| `README-FIRST.txt` | 2 | v0.2.0 portable-release banner is shipped in the 1.2.0 ZIP | BLOCKER | Users are told they extracted a different release. |
| `RELEASE_NOTES.md` | 1 | v1.1.0 is copied as the 1.2.0 release notes | BLOCKER | Release artifact lacks v1.2 identity/content. |
| `build_release.py` | 92-97 | Recursive cleanup has no exact-target/reparse/allowlist guard | BLOCKER | Re-running the advertised command risks deleting unapproved content. |
| `build_release.py` | 120-165 | Missing required inputs are warning-only; partial Vulkan copies | BLOCKER | Builder can exit 0 with a nonfunctional/incomplete package. |
| `build_release.py` | 195-205 | CPU Whisper checksum paths/coverage are incomplete | WARNING | Whole ZIP is protected, but per-runtime diagnostic integrity is incomplete. |

No `TBD`, `FIXME`, or `XXX` debt marker was found in the six changed
source/test/spec files. The disconfirmation pass found: (1) a partially met
version requirement, (2) narrow version tests that pass while shipped docs are
stale, and (3) untested missing-input/destructive-cleanup error paths.

## Human Verification and Abstentions

These do not supersede the two automated gaps above. After gap closure:

1. **Clean-machine launch / SmartScreen:** Extract the rebuilt ZIP on a Windows
   machine without the development environment and launch it. Expected: any
   SmartScreen warning is nonfatal and the app reaches its native window.
2. **Repeated analysis backstop:** Compare two clean PyInstaller analysis runs.
   Expected: identical module/optimization configuration.
3. **Unicode/non-ASCII backstop:** Run canonical transcript formats under a
   non-ASCII Windows path. Expected: path and text round-trip unchanged.
4. **Boundary-touch backstop:** Exercise a zero-overlap boundary-touch segment.
   Expected: behavior matches an explicitly documented contract.
5. **Empty alignment backstop:** Exercise empty slides and empty segments.
   Expected: defined non-crashing output with no invented source mapping.

Nine descriptor-less PLAN prohibitions also remain marked `status: unverified`
and require explicit owner resolution rather than a silent verifier pass:
cache-key immutability; assertion preservation; no test weakening; no mocked or
historical integration proof; no live Groq/key/content use; no owner-specific
packaged validation/real data; no static-only release claim; no forbidden
payload bundling; and no mutation of real LecturePackData. Current code, git
diffs, logs, and ZIP inspection support these prohibitions, but the plans did
not supply test-tier enforcement descriptors.

## Gaps Summary

The current binary is executable and its archive integrity is sound, but it is
not ready to be called the completed v1.2 portable release: two documents inside
the ZIP identify obsolete versions, the release-tool header is stale, and the
documented build command does not incorporate the safety/completeness gate that
made this one build acceptable. Correct the source release documents and
builder, add focused failure-path/version-document tests, rebuild, and re-run
the existing frozen/integrity verification before owner approval.

---

_Verified: 2026-07-18T17:51:05Z_  
_Verifier: generic-agent workaround (gsd-verifier role)_
