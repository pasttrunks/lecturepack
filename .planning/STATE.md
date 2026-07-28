---
gsd_state_version: '1.0'
milestone: v0.9.0-beta.6
milestone_name: Clean-Machine Reliability and Onboarding
status: planning
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-27)

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Phase 1 — Runtime Contract & Bootstrap

## Current Position

Phase: 1 of 5 (Runtime Contract & Bootstrap)
Plan: Not yet planned
Status: Ready to plan after roadmap approval
Last activity: 2026-07-27 — Beta-6 roadmap created; 44 requirements mapped once.

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1–5 | 0 | — | — |

## Accumulated Context

### Decisions

- Beta 6 preserves the existing stack and four-layer architecture; only approval-gated milestone work is in scope.
- Phase 1 must produce an explicitly approved verifier/signing ADR covering trust, release assets, and PyInstaller validation.
- Phase 2 signed-repair implementation is blocked until that ADR is approved; it must not weaken the signed-manifest requirement.
- Startup admission precedes normal UI/job behavior; demo data remains isolated from normal library and profile state.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 verifier/signing ADR has no approved dependency or operational signing contract yet; Phase 2 cannot begin until approval.
- Release proof requires physical CPU-only, NVIDIA, and AMD/Intel Windows machines plus fresh/upgraded and hostile-path evidence.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Repair | Offline repair-package import and per-file selection | Future (FUTR-01, FUTR-02) | 2026-07-27 |
| Onboarding | Alternate tour modes and reduced-motion preference | Future (FUTR-03, FUTR-04) | 2026-07-27 |
| Architecture | Unrelated detector and worker technical debt | Out of beta-6 scope | 2026-07-27 |

## Session Continuity

Last session: 2026-07-27
Stopped at: Beta-6 roadmap, state, and traceability prepared for approval.
Resume file: None
