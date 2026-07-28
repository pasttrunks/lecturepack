# Roadmap: LecturePack v0.9.0-beta.6

## Overview

Beta 6 makes the portable app dependable on clean Windows machines: establish a deterministic runtime contract, make failed setup safely recoverable, enter an empty owned Home surface, teach the real workflow through an isolated guided demo, preserve the beta-5 visual language while removing artifacts, and prove the assembled release on packaged and physical machines. Phases execute one at a time and each transition requires passing evidence plus explicit user approval.

## Phases

**Phase Numbering:** This is a new milestone; numbering resets to Phase 1.

- [ ] **Phase 1: Runtime Contract & Bootstrap** - Establish deterministic CPU-runtime admission, healthy-startup boundaries, and the approved signing/verifier contract.
- [ ] **Phase 2: Hard Setup & Signed Repair** - Block unhealthy launches and recover with consented, exact-version, signed transactional repair.
- [ ] **Phase 3: Empty Launch & Guided Demo** - Give users an empty owned Home and a replayable, real, isolated onboarding workflow.
- [ ] **Phase 4: Visual Artifact Reliability** - Preserve beta-5 visual character while eliminating confirmed rendering and layout artifacts.
- [ ] **Phase 5: Packaged & Physical Release Gate** - Prove the assembled release offline, under damage and hostile-path conditions, on required hardware.

## Phase Details

### Phase 1: Runtime Contract & Bootstrap

**Goal**: A clean installation can deterministically establish and persist a healthy bundled CPU processing runtime before any normal application behavior begins.
**Depends on**: Nothing (first beta-6 phase)
**Requirements**: RUNT-01, RUNT-02, RUNT-03, RUNT-04, RUNT-05, RUNT-06, RUNT-07, RUNT-08, RUNT-09
**Success Criteria** (what must be TRUE):

  1. On a fresh portable profile, LecturePack finds and validates packaged FFmpeg, ffprobe, the CPU Whisper CLI/DLL set, and `ggml-base.en.bin` without Settings input.
  2. A healthy launch silently persists only validated runtime facts, uses the base-English model by default after upgrade, and performs the appropriate lightweight or full smoke checks.
  3. Users cannot reach normal navigation, job activation, optional-engine probing, or demo startup until runtime health is `HEALTHY`.
  4. A healthy saved optional engine remains selected; if it is unavailable, users enter with the validated bundled CPU path and see a clear fallback notice.
  5. An explicitly approved ADR defines the signed-manifest verifier, trust/key lifecycle, canonical manifest/versioned asset contract, and PyInstaller validation required before repair implementation.

**Plans**: 4/7 plans executed; 3 verified gap-closure plans ready

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md
- [x] 01-03-PLAN.md
- [x] 01-04-PLAN.md
- [ ] 01-05-PLAN.md
- [ ] 01-06-PLAN.md
- [ ] 01-07-PLAN.md

**Wave 0**

- [x] `01-01-PLAN.md` — Canonical inventory, Wave 0 validation seams, and a blocking disposable packaged-runtime smoke.

**Wave 1** *(blocked on Wave 0 completion)*

- [x] `01-02-PLAN.md` — Bootstrap persistence, one-time beta-5 migration, and optional-engine fallback.
- [x] `01-04-PLAN.md` — Approval-gated signing/verifier ADR, followed by contract-vector and full-suite evidence only after approval.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `01-03-PLAN.md` — Active beta-5 desktop admission/status seam and the Phase 1 handoff.
- [ ] `01-05-PLAN.md` — Clean onedir directory creation plus fail-closed validator launch and bootstrap evidence.

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] `01-06-PLAN.md` — Real staged model-and-WAV CPU admission, corrupt-model rejection, and Unicode-safe VAD staging.

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] `01-07-PLAN.md` — Stable setup-required bridge guards and an honest Phase 1 handoff.

Cross-cutting constraints: preserve unrelated comments, docstrings, user data, original lecture videos, frontend/web assets, animations, shadows, transitions, motion, theme, and visual behavior; do not implement Phase 2 repair or add an unapproved verifier dependency; run the targeted tests named by each task, the full suite under a validated packaged fixture at each gap-plan gate, and the real packaged-runtime smoke where specified.

Canonical references: `.planning/PROJECT.md`, `.planning/MILESTONE-CONTEXT.md`, `.planning/research/SUMMARY.md`, `docs/DECISIONS.md`.

**Approval/evidence gate**: Targeted and full `pytest` output, packaged/disposable bootstrap smoke evidence, and explicit approval of the Phase 1 verifier/signing ADR. **Phase 2 implementation is blocked until this ADR is approved.**

### Phase 2: Hard Setup & Signed Repair

**Goal**: Users with an unhealthy required runtime are safely blocked from normal entry and can consent to a trustworthy repair that restores a complete runtime without restart.
**Depends on**: Phase 1 and explicit approval of its verifier/signing ADR
**Requirements**: REPR-01, REPR-02, REPR-03, REPR-04, REPR-05, REPR-06, REPR-07, REPR-08, REPR-09, REPR-10
**Success Criteria** (what must be TRUE):

  1. Missing, unreadable, corrupt, or unusable required components keep users in a non-dismissible setup gate rather than entering the normal app.
  2. The gate plainly identifies failed components and offers Repair all, Retry, Open diagnostics, and Exit; repair consent shows the exact version, official source, affected content, and download size.
  3. Repair uses only the exact running version's official release asset after validating the approved project signature, manifest contract, every staged file hash, and archive inventory.
  4. Tampered, mixed-release, incomplete, unsafe, cancelled, or failed repairs never activate partial content; users retain or restore the prior runtime and receive actionable diagnostics.
  5. A successful repair atomically activates a complete writable runtime generation, fully revalidates it, and enters LecturePack automatically; unavailable network offers only Retry, diagnostics, or Exit.

**Plans**: TBD

Likely plan slices:

- [ ] 02-01: Setup-gate state, component explanations, consent, and offline diagnostics.
- [ ] 02-02: Exact-version release acquisition and approved signature/manifest validation.
- [ ] 02-03: Staging, transactional activation/rollback, revalidation, and fault matrix.

Canonical references: Phase 1 approved ADR, `.planning/MILESTONE-CONTEXT.md`, `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`.

**Approval/evidence gate**: The Phase 1 ADR is approved before implementation; targeted and full `pytest` output plus disposable-package damage, rollback, and repair evidence must pass before Phase 3 approval.
**UI hint**: yes

### Phase 3: Empty Launch & Guided Demo

**Goal**: After healthy admission, users own an empty Home experience and can opt into a concise, real, isolated guided workflow without contaminating their study data.
**Depends on**: Phase 2
**Requirements**: HOME-01, HOME-02, HOME-03, DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-05, DEMO-06, DEMO-07, DEMO-08
**Success Criteria** (what must be TRUE):

  1. Healthy startup opens Home with no active lecture; existing library jobs stay visible and open only after an explicit user action.
  2. On first healthy startup, users may choose Start guided demo or Skip for now; the replayable tour has user-controlled Back/Next controls, anchored indicators, concise workflow teaching, and an always-obvious Exit action.
  3. The demo uses a bundled original, rights-clear 45–90 second synthetic lecture and processes it through the real offline workflow from import through review, study-pack generation, and export-location explanation.
  4. Demo work never appears as a normal library job and cannot write normal job, library, or profile state.
  5. Demo exit, cancellation, error, success, and crash recovery safely clean only sentinel-scoped temporary data and child work, including abandoned data on a later launch.

**Plans**: TBD

Likely plan slices:

- [ ] 03-01: Empty active-job ownership and explicit library activation.
- [ ] 03-02: Guided welcome/tour controls, replay entry point, and accessibility checks. This plan is the exclusive owner of Phase 3 changes to shared `app/ui/index.html`, `app/ui/app.js`, and `app/ui/app.css`; its handoff must identify every touched selector/component for Phase 4.
- [ ] 03-03: Original demo asset, session-scoped real-pipeline orchestration, and lifecycle cleanup.

Canonical references: `.planning/MILESTONE-CONTEXT.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/FEATURES.md`, `docs/ARCHITECTURE.md`.

**Approval/evidence gate**: Targeted and full `pytest` output; fresh-profile GUI evidence; real-demo success/cancel/error/crash-cleanup evidence; explicit approval before Phase 4.
**UI hint**: yes

### Phase 4: Visual Artifact Reliability

**Goal**: Users retain beta 5's intentional visual language while all beta-6 state surfaces render without unwanted flash, flicker, overflow, or layout instability.
**Depends on**: Phase 3
**Requirements**: VIS-01, VIS-02, VIS-03, VIS-04, VIS-05
**Success Criteria** (what must be TRUE):

  1. Across normal use, beta-5 animation timing, transitions, dark shadows, and pressed/embedded controls remain visibly intact.
  2. Theme changes and backend/option updates do not produce unintended color flashes, entrance-animation replay, repaint artifacts, or layout jumps.
  3. Long local-model names fit their container with ellipsis and expose their full value by hover and keyboard focus.
  4. Gate, tour, theme, resize, and navigation states remain free of unintended flicker, overflow, focus traps, layout jumps, and WebEngine console errors at supported window sizes and DPI.

**Plans**: TBD

Likely plan slices:

- [ ] 04-01: Take exclusive ownership of shared `app/ui/index.html`, `app/ui/app.js`, and `app/ui/app.css` after Phase 3 approval; consume the Phase 3 UI handoff, establish the beta-5 baseline comparison, and apply targeted atomic-theme/repaint fixes in the shipping UI shell.
- [ ] 04-02: Long-value overflow, overlay/layout/focus stabilization, and visual regression coverage.

Canonical references: `.planning/MILESTONE-CONTEXT.md`, `.planning/research/ARCHITECTURE.md`, beta-5 visual comparison evidence.

**Approval/evidence gate**: Targeted and full `pytest` output, beta-5 visual/motion comparison evidence, and manual supported-size/DPI checks before Phase 5.
**UI hint**: yes

### Phase 5: Packaged & Physical Release Gate

**Goal**: The release is demonstrably dependable as a portable, offline Windows application across required machine types, profiles, path conditions, and runtime failures.
**Depends on**: Phase 4
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05, REL-06, REL-07, REL-08, REL-09
**Success Criteria** (what must be TRUE):

  1. The release package proves its canonical inventory, approved manifest/asset contract, and lack of bundled user/job/demo state before distribution.
  2. A disposable packaged profile runs the actual bundled FFmpeg, ffprobe, Whisper CLI/DLLs, and bounded model load independent of developer paths, Python, Node, PATH tools, or user state; every smoke invocation records the exact command/argument vector, exit code, duration, stdout, and stderr.
  3. A fresh packaged GUI profile persists validated runtime state, opens empty Home, and completes the bundled demo's real import-to-export workflow while networking is denied and no unauthorized request occurs.
  4. Separate removal or corruption of every required executable, DLL, and model in disposable package copies proves hard gating, signed/hash-verified repair, rollback, revalidation, and restored entry under hostile Windows paths and writable-data locations.
  5. Signed release evidence covers CPU-only, NVIDIA, and AMD/Intel Windows machines with fresh and upgraded profiles; targeted/full `pytest` and beta-5 visual comparison evidence are complete, or publication remains blocked.

**Plans**: TBD

Likely plan slices:

- [ ] 05-01: Package inventory/manifest build checks and disposable-profile subprocess/GUI smoke harnesses.
- [ ] 05-02: Offline, hostile-path, and component-damage/repair acceptance matrix.
- [ ] 05-03: Physical-machine execution records and final release-evidence review.

Canonical references: `.planning/MILESTONE-CONTEXT.md`, `.planning/research/SUMMARY.md`, `.planning/research/PITFALLS.md`, Phase 1 approved ADR.

**Approval/evidence gate**: All required package, offline, damage, GUI, test, visual-comparison, and physical-machine evidence is recorded and approved. Packaged process evidence must include command/argument vector, exit code, duration, stdout, and stderr for every smoke invocation. Any missing CPU-only, NVIDIA, or AMD/Intel target blocks public beta-6 publication.

## Progress

**Execution Order:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5. Only one phase may be implemented at a time; every phase requires its evidence gate and explicit user approval before the next phase begins.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Runtime Contract & Bootstrap | 4/4 | In Progress|  |
| 2. Hard Setup & Signed Repair | 0/TBD | Blocked — Phase 1 ADR approval | - |
| 3. Empty Launch & Guided Demo | 0/TBD | Not started | - |
| 4. Visual Artifact Reliability | 0/TBD | Not started | - |
| 5. Packaged & Physical Release Gate | 0/TBD | Not started | - |
