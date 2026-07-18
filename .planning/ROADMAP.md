# Roadmap: LecturePack

## Overview

LecturePack is a brownfield project with a complete v1.2 codebase on the `v1.2-hybrid-study` branch. Stability, Study workspace, and Groq architecture phases are code-complete with ~151 tests. The roadmap's immediate goal is packaging, test validation, and shipping v1.2 as a release. A follow-up phase addresses critical reliability gaps identified during the codebase audit.

## Phases

- [ ] **Phase 1: Packaging & Release** - Audit packaging spec, reconcile tests, pass full suite, build v1.2 release
- [ ] **Phase 2: Reliability Hardening** - Fix critical reliability gaps: cooperative cancel, GUI-thread subprocess, test coverage

## Phase Details

### Phase 1: Packaging & Release
**Goal**: v1.2 is packaged, tested, validated, and available as a portable release
**Depends on**: Nothing (first phase — brownfield, all code exists)
**Requirements**: REQ-core-conversion, REQ-privacy-safety, REQ-transcription, REQ-slide-extraction, REQ-alignment, REQ-export-formats, REQ-job-lifecycle, REQ-study-workspace, REQ-provider-neutral-transcription, REQ-groq-transcription, REQ-stability, REQ-architecture-layers, REQ-test-framework, REQ-version-bump, REQ-packaging-spec-audit, REQ-packaged-build, REQ-test-suite-pass, REQ-self-test, REQ-test-reconciliation
**Success Criteria** (what must be TRUE):
  1. `python -m pytest -v` passes with 0 failures, 0 errors, documented test count
  2. Application self-test (`--selftest`) passes: all imports resolve, MainWindow constructs, no QThread lifecycle errors
  3. PyInstaller builds successfully; packaged EXE initializes without import/startup errors
  4. Version strings consistently report 1.2.0 across all artifacts
  5. Packaged build extracts to a clean path and launches without fatal errors
**Plans**: TBD

Plans:
- [ ] 01-01: Version bump and packaging spec audit (single-version-source, hiddenimports for v1.2 tree, fix optimize=1)
- [ ] 01-02: Test suite reconciliation and fixing (reconcile 149 vs 151 count, fix any broken tests)
- [ ] 01-03: Package build and validation (PyInstaller build, --selftest, portable ZIP, SHA256SUMS)

### Phase 2: Reliability Hardening
**Goal**: Critical reliability gaps from the codebase audit are resolved, preventing Qt state corruption and UI freezes
**Depends on**: Phase 1
**Requirements**: REQ-stability, REQ-test-framework
**Success Criteria** (what must be TRUE):
  1. AlignWorker and ExportWorker use cooperative cancellation (no QThread.terminate() on cancel)
  2. FFmpegWrapper.inspect_video runs off the GUI thread with a timeout, preventing UI stalls
  3. New tests cover non-ASCII path image I/O and AlignWorker/ExportWorker cancel behavior
  4. Full test suite still passes after all changes
**Plans**: TBD

Plans:
- [ ] 02-01: Replace QThread.terminate() with cooperative cancel for AlignWorker and ExportWorker
- [ ] 02-02: Move ffprobe inspect to a worker thread with timeout; add non-ASCII path test fixture
- [ ] 02-03: Add cancel and image-missing edge case tests

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Packaging & Release | 0/3 | Not started | - |
| 2. Reliability Hardening | 0/3 | Not started | - |
