# Roadmap: LecturePack

## Overview

LecturePack is a brownfield project with a complete v1.2 codebase on the `v1.2-hybrid-study` branch. Stability, Study workspace, and Groq architecture phases are code-complete with ~151 tests. The roadmap's immediate goal is packaging, test validation, and shipping v1.2 as a release. A follow-up phase addresses critical reliability gaps identified during the codebase audit.

## Phases

- [ ] **Phase 1: Packaging & Release** - Audit packaging spec, reconcile tests, pass full suite, build v1.2 release
- [ ] **Phase 2: Reliability & Architecture Hardening** - Fix critical reliability gaps and eliminate disclosed adjacent-layer debt

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
  6. The architecture audit introduces no violation absent from baseline commit `25e9dd1`; all 47 baseline violations remain disclosed as Phase 2 debt and strict conformance is not claimed

**Plans**: 3/6 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Single-source release 1.2.0, audit hidden imports, and preserve frozen self-test assertions

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Reconcile pytest collection, pass the full suite, and validate the development self-test

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Build and integrity-check the portable package, then validate both frozen launch paths

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-04-PLAN.md — Correct every shipped v1.2.0 identity and add release-document regression coverage

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 01-05-PLAN.md — Make the direct release builder fail closed, reparse-safe, and transactional

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 01-06-PLAN.md — Rebuild the portable release and independently prove inventories, digests, and both frozen paths

### Phase 2: Reliability & Architecture Hardening

**Goal**: Critical reliability gaps are resolved and the 47 disclosed adjacent-layer violations are eliminated, preventing Qt state corruption, UI freezes, and further architecture drift
**Depends on**: Phase 1
**Requirements**: REQ-stability, REQ-test-framework, REQ-architecture-layers
**Success Criteria** (what must be TRUE):

  1. AlignWorker and ExportWorker use cooperative cancellation (no QThread.terminate() on cancel)
  2. FFmpegWrapper.inspect_video runs off the GUI thread with a timeout, preventing UI stalls
  3. New tests cover non-ASCII path image I/O and AlignWorker/ExportWorker cancel behavior
  4. Full test suite still passes after all changes
  5. The whole-tree architecture audit reports zero adjacent-layer violations, closing the 47-item baseline debt without weakening the approved rule

**Plans**: 0/4 plans executed

Plans:

- [ ] 02-01: Replace QThread.terminate() with cooperative cancel for AlignWorker and ExportWorker
- [ ] 02-02: Move ffprobe inspect to a worker thread with timeout; add non-ASCII path test fixture
- [ ] 02-03: Add cancel and image-missing edge case tests
- [ ] 02-04: Route controller/UI dependencies through adjacent layers and retire the 47-violation architecture baseline

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Packaging & Release | 3/6 | In Progress|  |
| 2. Reliability & Architecture Hardening | 0/4 | Not started | - |
