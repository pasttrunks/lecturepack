---
gsd_state_version: 1.0
milestone: v0.9.0-beta.6
milestone_name: Clean-Machine Reliability and Onboarding
current_phase: 1
current_phase_name: Runtime Contract & Bootstrap
status: executing
stopped_at: Gap-closure plans 01-05 through 01-07 verified; awaiting execution
last_updated: "2026-07-28T13:18:34.424Z"
last_activity: 2026-07-28
last_activity_desc: Phase 1 gap-closure plans verified
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 7
  completed_plans: 4
  percent: 11
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-27)

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Phase 1 — Runtime Contract & Bootstrap

## Current Position

Phase: 1 (Runtime Contract & Bootstrap) — EXECUTING
Plan: 4 of 7
Status: Ready to execute verified gap-closure plans 01-05 through 01-07
Last activity: 2026-07-28 — Phase 1 gap-closure plans verified

Progress: [██████░░░░] 57%

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: 31m
- Total execution time: 123m

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 4/7 | 123m | 31m |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01-runtime-contract-bootstrap P01 | 49min | 2 tasks | 12 files |
| Phase 01-runtime-contract-bootstrap P02 | 17min | 2 tasks | 4 files |
| Phase 01-runtime-contract-bootstrap P04 | 17m | 3 tasks | 5 files |
| Phase 01-runtime-contract-bootstrap P03 | 40m | 3 tasks | 7 files |

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 verification is `gaps_found`; plans 01-05 through 01-07 must pass before Phase 1 can close or Phase 2 can begin.
- Gap closure must prove clean onedir directory creation, fail-closed validator launch behavior, real model-plus-WAV CPU admission, Unicode VAD staging, and safe setup-required bridge slots.
- Release proof still requires physical CPU-only, NVIDIA, and AMD/Intel Windows machines plus fresh/upgraded and hostile-path evidence.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Repair | Offline repair-package import and per-file selection | Future (FUTR-01, FUTR-02) | 2026-07-27 |
| Onboarding | Alternate tour modes and reduced-motion preference | Future (FUTR-03, FUTR-04) | 2026-07-27 |
| Architecture | Unrelated detector and worker technical debt | Out of beta-6 scope | 2026-07-27 |

## Session Continuity

Last session: 2026-07-28T13:18:34.424Z
Stopped at: Gap-closure plans 01-05 through 01-07 verified; awaiting execution
Resume file: None
