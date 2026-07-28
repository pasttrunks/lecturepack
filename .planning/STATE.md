---
gsd_state_version: 1.0
milestone: v0.9.0-beta.6
milestone_name: Clean-Machine Reliability and Onboarding
current_phase: 2
current_phase_name: Hard Setup & Signed Repair
status: executing
stopped_at: Phase 2 UI-SPEC approved
last_updated: "2026-07-28T18:34:00.365Z"
last_activity: 2026-07-28
last_activity_desc: Phase 1 complete, transitioned to Phase 2
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 7
  completed_plans: 7
  percent: 20
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-28)

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Phase 2 — Hard Setup & Signed Repair

## Current Position

Phase: 2 — Hard Setup & Signed Repair
Plan: Not started
Status: Ready to execute
Last activity: 2026-07-28 — Phase 1 complete, transitioned to Phase 2

Milestone progress: [██░░░░░░░░] 20%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: 31m
- Total execution time: 123m

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 7 | - | - |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01-runtime-contract-bootstrap P01 | 49min | 2 tasks | 12 files |
| Phase 01-runtime-contract-bootstrap P02 | 17min | 2 tasks | 4 files |
| Phase 01-runtime-contract-bootstrap P04 | 17m | 3 tasks | 5 files |
| Phase 01-runtime-contract-bootstrap P03 | 40m | 3 tasks | 7 files |
| Phase 01-runtime-contract-bootstrap P05 | 28m | 2 tasks | 6 files |
| Phase 01-runtime-contract-bootstrap P06 | 16m | 2 tasks | 7 files |
| Phase 01-runtime-contract-bootstrap P07 | 25m | 2 tasks | 3 files |

## Accumulated Context

### Decisions

- Beta 6 preserves the existing stack and four-layer architecture; only approval-gated milestone work is in scope.
- Phase 1 must produce an explicitly approved verifier/signing ADR covering trust, release assets, and PyInstaller validation.
- Phase 2 signed-repair implementation is blocked until that ADR is approved; it must not weaken the signed-manifest requirement.
- Startup admission precedes normal UI/job behavior; demo data remains isolated from normal library and profile state.
- [Phase ?]: AD-18: keep Unicode paths end-to-end while staging only whisper.cpp v1.9.1 native CLI arguments under private ASCII paths.
- [Phase ?]: Runtime admission rejects incomplete full-validation evidence; only complete trusted component evidence is persisted.
- [Phase ?]: Optional engine resolution happens only after healthy canonical CPU admission, preserving healthy choices and falling back visibly to CPU.
- [Phase ?]: AD-19 approves cryptography==49.0.0 and pure Ed25519 detached signatures over exact canonical manifest bytes.
- [Phase ?]: The release trust root will be compiled into a future application release; Phase 2 implementation remains deferred.
- [Phase ?]: Backend owns runtime admission and constructs no adapter before HEALTHY.
- [Phase ?]: Runtime diagnostics transport serializes one controller/service snapshot and never rebuilds required inventory.
- [Phase ?]: Failed runtime launch or validator exceptions are untrusted evidence and cannot persist health or resolve optional engines.
- [Phase 01-runtime-contract-bootstrap]: Full CPU admission requires a bounded staged canonical model-and-WAV transcription before persistence. — Readable inventory bytes are not usability evidence.
- [Phase 01-runtime-contract-bootstrap]: Optional VAD models use the same private ASCII native staging boundary as model and WAV inputs. — No Unicode source path may reach whisper.cpp.
- [Phase ?]: SETUP_REQUIRED bridge operations use the existing diagnostics transport and one JSON-safe payload before collaborator access.
- [Phase ?]: Bootstrap admission fields are derived from the runtime diagnostics controller without a second inventory projection.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2 must implement the AD-19 signed exact-version repair contract, transactional activation/rollback, and frozen verifier proof before Phase 3 can begin.
- The real RUNT-02 repair-consumer integration test is intentionally deferred to Phase 2 and must prove repair consumes the Phase 1 canonical inventory.
- Release proof still requires physical CPU-only, NVIDIA, and AMD/Intel Windows machines plus fresh/upgraded and hostile-path evidence.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Repair | Offline repair-package import and per-file selection | Future (FUTR-01, FUTR-02) | 2026-07-27 |
| Onboarding | Alternate tour modes and reduced-motion preference | Future (FUTR-03, FUTR-04) | 2026-07-27 |
| Architecture | Unrelated detector and worker technical debt | Out of beta-6 scope | 2026-07-27 |

## Session Continuity

Last session: 2026-07-28T17:53:34.703Z
Stopped at: Phase 2 UI-SPEC approved
Resume file: .planning/phases/02-hard-setup-signed-repair/02-UI-SPEC.md
