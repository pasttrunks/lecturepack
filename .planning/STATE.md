---
gsd_state_version: 1.0
milestone: v0.9.0-beta.7
milestone_name: Clean-Device Footprint and First Launch
current_phase: 1
current_phase_name: Clean-Device Footprint & First Launch
status: discussing
stopped_at: Phase 1 context gathered
last_updated: "2026-07-30T00:00:00.000Z"
last_activity: 2026-07-30
last_activity_desc: Phase 1 context captured; beta-6 milestone archived
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Milestone v0.9.0-beta.7 — Phase 1 context gathered, ready for planning.

## Current Position

Phase: 1 (Clean-Device Footprint & First Launch) — DISCUSSED
Plan: none yet
Status: Ready for `/gsd-plan-phase 1`
Last activity: 2026-07-30 — Phase 1 context captured

Milestone progress: [░░░░░░░░░░] 0%

## Branch

**All work lives on `codex/phase4-visual-artifact-reliability`.** `main` is 153 commits
behind and its `.planning/` describes an unfinished v1.2 milestone for the *legacy*
QtWidgets application. Do not plan or implement against `main`.

## Accumulated Context

### Decisions

Beta-6 decisions (AD-18, AD-19, runtime admission contract, demo isolation) remain
canonical — see `.planning/milestones/v0.9.0-beta.6/`.

Beta-7 Phase 1 decisions D-01..D-21 are in
`.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md`. Headlines:

- Size cuts are scoped to the model dedupe plus provably-unused Qt components; an
  aggressive allowlist was considered and rejected for this phase.
- Startup is fixed on both axes — window-first with honest itemized progress, *and*
  reducing validation cost without weakening admission evidence.
- The first-run setup checklist is a deliberate behavior change, not a bug fix; the
  existing gate correctly skips on a healthy first run.
- A second launch raises the existing window, and the guard runs before the slow
  validation path.

### Measured baseline (2026-07-30)

| Artifact | Size |
|---|---|
| `LecturePack-0.9.0-beta.6-Portable.zip` | 841.2 MB |
| `app/dist/LecturePack/` installed | 1.9 GB |
| `_internal/PySide6/` | 538 MB |
| `ggml-base.en.bin` duplication | 148 MB × 2 |

### Blockers/Concerns

- **Unidentified installed artifact.** CI builds with `--no-installer` and ISCC is not
  installed locally, so no `Setup.exe` is produced anywhere visible. The owner's reported
  ~800 MB / ~900 MB does not reconcile with the measured 841 MB / 1.9 GB. Resolve before
  treating any size number as the baseline.
- **Beta-6's "complete" certification is not trustworthy.** Its Phase 5 release gate never
  measured size or launch time, names no physical machine, and cites beta-5 artifacts while
  certifying beta-6. See `.planning/milestones/v0.9.0-beta.6/README.md`.
- Physical clean-machine verification (CPU-only, NVIDIA, AMD/Intel) still outstanding from
  beta 6 and not claimed by this phase.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Packaging | Aggressive Qt module allowlist (~600 MB potential) | Deferred — revisit if D-01 insufficient | 2026-07-30 |
| Packaging | Trimming `PySide6/resources/` (102 MB) | Gated behind D-04 investigation | 2026-07-30 |
| Release | Honest re-verification of beta-6 Phase 5 claims | Future beta-7 release gate phase | 2026-07-30 |
| Repair | Offline repair-package import and per-file selection | Future (FUTR-01, FUTR-02) | 2026-07-27 |
| Onboarding | Alternate tour modes and reduced-motion preference | Future (FUTR-03, FUTR-04) | 2026-07-27 |
| Architecture | Unrelated detector and worker technical debt | Out of scope | 2026-07-27 |

## Session Continuity

Last session: 2026-07-30
Stopped at: Phase 1 context gathered
Resume file: `.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md`
