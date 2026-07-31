---
gsd_state_version: 1.0
milestone: v0.9.0-beta.7
milestone_name: Clean-Device Footprint and First Launch
current_phase: 1
current_phase_name: Clean-Device Footprint & First Launch
status: planned
stopped_at: Phase 1 planned — 8 plans in 4 waves, plan-checker passed
last_updated: "2026-07-31T00:17:09.958Z"
last_activity: 2026-07-30
last_activity_desc: Phase 1 planned (8 plans, 4 waves); D-22 recorded
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 8
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Milestone v0.9.0-beta.7 — Phase 1 planned (8 plans, 4 waves), ready to execute.

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

- **Updater cannot consume a current-workflow release.** `a6164b1` (beta-6 Phase 2 Plan 05)
  replaced the installer-publishing release job with one publishing only six signed runtime
  assets. `expected_asset_names()` (`app/desktop/update_service.py:117-120`) requires
  `Setup.exe` + `SHA256SUMS.txt`, neither of which CI now publishes. Pre-existing, not
  caused by beta 7, but it contradicts the "preserve updater behavior" constraint.

- **Size figures not yet reconciled.** ISCC *is* installed (`%LOCALAPPDATA%\Programs\Inno
  Setup 6\`) and `build.py` does produce `Setup.exe` locally — an earlier claim to the
  contrary was based on a PATH-only check and was wrong. What remains unexplained is the
  owner's ~900 MB extraction vs. the 1.9 GB measured dev tree. Build and measure one fresh
  artifact before adopting any baseline.

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

Last session: 2026-07-31T00:17:09.945Z
Stopped at: Phase 1 UI-SPEC approved
Resume file: .planning/phases/01-clean-device-footprint-first-launch/01-UI-SPEC.md
