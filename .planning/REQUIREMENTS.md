# Requirements: LecturePack v0.9.0-beta.6

**Defined:** 2026-07-27
**Core Value:** Convert lecture videos into complete, reviewable, portable study packs entirely on-device, with no accounts, telemetry, or cloud dependency by default.
**Baseline:** `v0.9.0-beta.5` at commit `459faf5`

## Beta 6 Requirements

### Runtime Contract and Bootstrap

- [x] **RUNT-01**: A fresh portable profile discovers the packaged FFmpeg, ffprobe, CPU Whisper CLI/DLL set, and `ggml-base.en.bin` without manual Settings configuration.
- [x] **RUNT-02**: LecturePack validates one canonical required-runtime inventory shared by startup, packaging, repair, diagnostics, and tests.
- [x] **RUNT-03**: LecturePack persists required-runtime paths only after the complete required set passes validation.
- [x] **RUNT-04**: Every launch performs lightweight identity/readability checks; first launch, update, repair, or payload-identity change triggers bounded executable, DLL, and model smoke checks.
- [ ] **RUNT-05**: No normal adapter readiness, job activation, navigation, optional-engine probe, or demo start occurs before required-runtime health reaches `HEALTHY`.
- [x] **RUNT-06**: Upgrade to beta 6 selects bundled `ggml-base.en.bin` as the default model while leaving other installed models available for later manual selection.
- [x] **RUNT-07**: A healthy saved optional CUDA/custom engine remains selected while bundled CPU stays validated as the recovery path.
- [x] **RUNT-08**: A missing or broken optional engine falls back visibly to bundled CPU without blocking entry when the required CPU runtime is healthy.
- [ ] **RUNT-09**: Phase 1 records an approved ADR for the signed-manifest verifier, algorithm/encoding, key custody and rotation, canonical manifest bytes/schema, exact-version asset contract, and PyInstaller validation; signed repair implementation cannot start until it is approved.

### Setup Gate and Secure Repair

- [ ] **REPR-01**: Any missing, unreadable, corrupt, or unusable required-runtime component blocks entry to the normal application behind a non-dismissible setup gate.
- [ ] **REPR-02**: The setup gate identifies failed required components in plain language and offers Repair all, Retry, Open diagnostics, and Exit actions.
- [ ] **REPR-03**: Repair starts only after explicit user confirmation showing the exact LecturePack version, official source, affected components, and download size.
- [ ] **REPR-04**: Repair downloads only the exact running version's asset from the official LecturePack GitHub release and makes no telemetry or unrelated network requests.
- [ ] **REPR-05**: LecturePack verifies the project signature on the exact-version manifest before trusting it, then verifies the SHA-256 and inventory of every staged payload file.
- [ ] **REPR-06**: Repair rejects invalid signatures, wrong app/schema versions, missing/extra archive members, unsafe paths, hash mismatches, and mixed-release components without activating staged content.
- [ ] **REPR-07**: Repair installs a complete verified runtime generation into an app-managed writable location and atomically activates it without modifying the immutable portable bundle in place.
- [ ] **REPR-08**: Any download, validation, permission, cancellation, or activation failure retains or restores the previous runtime generation and leaves actionable diagnostics.
- [ ] **REPR-09**: Successful repair performs full revalidation and enters LecturePack automatically without requiring restart.
- [ ] **REPR-10**: Offline or unavailable repair offers Retry, Open diagnostics, and Exit; beta 6 does not offer manual per-file selection or offline repair-package import.

### Empty Launch and Job Ownership

- [ ] **HOME-01**: A healthy startup opens Home with no active lecture and never automatically opens the latest completed job.
- [ ] **HOME-02**: Existing jobs remain visible in the library and become active only after an explicit user action.
- [ ] **HOME-03**: Packaged, design-time, synthetic-demo, or temporary data never appears as a permanent normal library job.

### Guided Demo

- [ ] **DEMO-01**: First successful startup presents Start guided demo and Skip for now without starting the tour automatically.
- [ ] **DEMO-02**: The guided demo uses user-controlled Next and Back steps with arrows, circles, and spotlights anchored to the real interface.
- [ ] **DEMO-03**: A persistent, obvious Exit demo action is available throughout the tour.
- [ ] **DEMO-04**: The tour teaches only the main workflow and core product value with concise explanations, and it can be replayed from Settings.
- [ ] **DEMO-05**: Beta 6 bundles an original, rights-clear 45–90 second synthetic lecture with simple slides and narration and no university, student, or third-party copyrighted content.
- [ ] **DEMO-06**: The demo runs the real offline pipeline through import, processing, transcript/slide review, study-pack generation, and export-location explanation.
- [ ] **DEMO-07**: Demo processing uses a dedicated session-scoped workspace and configuration that cannot write normal library/job/profile state.
- [ ] **DEMO-08**: Demo success, exit, cancellation, failure, and crash cleanup are idempotent, sentinel-scoped, cancel child work safely, and sweep abandoned demo data on next launch.

### Visual Artifact Reliability

- [ ] **VIS-01**: Beta 6 preserves beta 5's animation language, timing, transitions, hard dark shadows, and pressed/embedded button effect.
- [ ] **VIS-02**: Theme changes apply atomically without unintended luminance flashes or independent per-element color-transition artifacts.
- [ ] **VIS-03**: Backend state updates and option clicks do not replay screen entrance animations or create unintended repaint/layout artifacts.
- [ ] **VIS-04**: Long local-model names remain within their container using ellipsis, with the full value available on hover and keyboard focus.
- [ ] **VIS-05**: Gate, tour, theme, resize, and navigation states have no unintended flicker, overflow, layout jump, focus trap, or WebEngine console error at supported window sizes/DPI.

### Packaged and Physical Release Evidence

- [ ] **REL-01**: The package build validates the canonical required inventory, signed release manifest contract, expected asset identity, and absence of bundled user/job/demo state.
- [ ] **REL-02**: A disposable-profile packaged subprocess smoke executes real packaged FFmpeg, ffprobe, Whisper CLI/DLLs, and a bounded model-load/transcription input with captured command, exit code, duration, stdout, and stderr.
- [ ] **REL-03**: A fresh packaged GUI profile persists validated runtime state, enters empty Home when healthy, and does not depend on developer paths, Python, Node, or PATH-installed tools.
- [ ] **REL-04**: With networking denied, the packaged app completes the bundled demo's real import-to-export workflow and makes no unauthorized network request.
- [ ] **REL-05**: Disposable package copies separately remove or corrupt every required executable, DLL, and model and prove hard gating, signed/hash-verified one-click repair, rollback, revalidation, and normal entry.
- [ ] **REL-06**: Release tests pass from non-admin portable folders, paths with spaces and non-ASCII characters, non-ASCII user/profile paths, and a separate writable data directory.
- [ ] **REL-07**: Before publication, signed evidence exists for CPU-only, NVIDIA, and AMD/Intel Windows machines using fresh and upgraded profiles; any missing required target blocks release.
- [ ] **REL-08**: Every implementation phase reports actual targeted and full `pytest` output without deleting, weakening, or substituting mock-only evidence for packaged/physical integration proof.
- [ ] **REL-09**: Beta-5 visual comparison evidence confirms intentional styling/motion is preserved while the reported flicker, repaint, overflow, and layout artifacts are removed.

## Future Requirements

### Repair and Onboarding Extensions

- **FUTR-01**: User can import a verified offline runtime repair package.
- **FUTR-02**: User can select and repair individual required components.
- **FUTR-03**: User can choose alternate guided-tour depths or tutorial modes.
- **FUTR-04**: LecturePack supports a dedicated reduced-motion preference.

## Out of Scope

| Feature | Reason |
|---------|--------|
| New transcription providers, accounts, telemetry, or analytics | Not part of clean-machine reliability; conflicts with local-first boundaries. |
| Visual redesign or reduced animation language | Beta 5 appearance and intentional motion are locked for preservation. |
| Silent/background repair or update checks | Repair requires explicit user consent and exact-version provenance. |
| Manual required-runtime path browsing in the portable release | Normal users must not configure bundled core dependencies manually. |
| Permanent demo job or fake persisted lecture | Demo state must remain isolated from source-derived and user-authored data. |
| Unrelated architecture debt and detector refactors | Separate work; beta 6 changes only dependencies needed by its acceptance criteria. |

## Traceability

Every beta-6 requirement maps to exactly one approval-gated roadmap phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| RUNT-01 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-02 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-03 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-04 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-05 | Phase 1 — Runtime Contract & Bootstrap | Pending |
| RUNT-06 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-07 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-08 | Phase 1 — Runtime Contract & Bootstrap | Complete |
| RUNT-09 | Phase 1 — Runtime Contract & Bootstrap | Pending — ADR approval gates Phase 2 |
| REPR-01 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-02 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-03 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-04 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-05 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-06 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-07 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-08 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-09 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| REPR-10 | Phase 2 — Hard Setup & Signed Repair | Pending — blocked by Phase 1 ADR |
| HOME-01 | Phase 3 — Empty Launch & Guided Demo | Pending |
| HOME-02 | Phase 3 — Empty Launch & Guided Demo | Pending |
| HOME-03 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-01 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-02 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-03 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-04 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-05 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-06 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-07 | Phase 3 — Empty Launch & Guided Demo | Pending |
| DEMO-08 | Phase 3 — Empty Launch & Guided Demo | Pending |
| VIS-01 | Phase 4 — Visual Artifact Reliability | Pending |
| VIS-02 | Phase 4 — Visual Artifact Reliability | Pending |
| VIS-03 | Phase 4 — Visual Artifact Reliability | Pending |
| VIS-04 | Phase 4 — Visual Artifact Reliability | Pending |
| VIS-05 | Phase 4 — Visual Artifact Reliability | Pending |
| REL-01 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-02 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-03 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-04 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-05 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-06 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-07 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-08 | Phase 5 — Packaged & Physical Release Gate | Pending |
| REL-09 | Phase 5 — Packaged & Physical Release Gate | Pending |

**Coverage:**

- Beta-6 requirements: 44 total
- Mapped to phases: 44
- Unmapped: 0

---
*Requirements defined: 2026-07-27*
*Last updated: 2026-07-27 after roadmap creation*
