---
gsd_state_version: 1.0
milestone: v0.9.0-beta.7
milestone_name: Clean-Device Footprint and First Launch
current_phase: 01
current_phase_name: Clean-Device Footprint & First Launch
status: executing
stopped_at: Completed 01-06-PLAN.md
last_updated: "2026-07-31T12:54:12.557Z"
last_activity: 2026-07-31
last_activity_desc: Plan 01-03 executed (backend first-run checklist contract)
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 8
  completed_plans: 4
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Phase 01 — Clean-Device Footprint & First Launch

## Current Position

Phase: 01 (Clean-Device Footprint & First Launch) — EXECUTING
Plan: 4 of 8 complete (wave 1 done)
Status: Ready to execute wave 2 (01-04, 01-05, 01-06)
Last activity: 2026-07-31 — Plan 01-03 executed (backend first-run checklist contract)

Milestone progress: [░░░░░░░░░░] 0% (phase-level; 3/8 plans complete within Phase 1)

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

- [Phase 01 Plan 01]: D-23 (ISCC MAX_PATH normalization) discovered and fixed (commit 1b6059d); Task 3 (build fresh installer + record pre-cut baseline) executed and the pre-cut baseline recorded in 01-EVIDENCE.md (commit b0a326d), closing an earlier deferral of that task. Installed-size reconciliation is partially explained (torch/transformers/duplicate-model removal accounts for ~40% of the owner-vs-measured gap) and the residual ~455 MB is recorded as an explicit open question, not resolved.

- [Phase 01 Plan 02]: D-22 implemented — release.yml additively restores Setup.exe/Portable.zip/SHA256SUMS.txt publication alongside the six existing signed runtime assets, with 10 contract tests bound to expected_asset_names().

- [Phase 01 Plan 03]: D-16, D-13, D-14, D-10 implemented. `ConfigManager.setup_acknowledged()`/`persist_setup_acknowledged()` persist the first-run flag in `config.json` (D-16). New `lecturepack/services/first_run_checklist.py` exposes exactly five checklist items in canonical order with no remediation affordance (D-13/D-14), keyed to `canonical_inventory()`. `RuntimeBootstrapService._validate_full` now runs its three independent probes concurrently in a bounded thread pool, preserving the real staged whisper-cli transcription and every evidence field (D-10). No UI or bridge file touched; this is the fixed wire contract for Plans 01-06/01-07. Full suite: 912 passed, 7 failed (same 7 pre-existing failures documented in deferred-items.md; no new failures).
- [Phase 01 Plan 06]: D-06/D-07/D-08/D-09/D-14/D-16 implemented. Backend.__init__ no longer calls assess() synchronously; a fail-closed ADMISSION_PENDING sentinel is assigned before any collaborator, and assessment runs on a daemon worker thread with itemized bootstrap_progress signals per FIRST_RUN_CHECKLIST_ITEMS id, marshalled via the BUG-09-corrected QTimer.singleShot(0, self, ...) form. get_bootstrap() extended with bootstrap_pending/validation_path/setup_acknowledged/checklist for Plan 01-07 to consume; ui_ready removed from the admission guard so it can always record readiness during the pending window; new acknowledge_setup() slot persists only a boolean. Full suite: 944 passed, 7 failed (912 baseline + 32 new tests; same 7 pre-existing failures; no new failures).

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

- **Size figures partially reconciled; a residual gap remains open.** ISCC *is* installed
  (`%LOCALAPPDATA%\Programs\Inno Setup 6\`) and `build.py` does produce `Setup.exe` locally
  (confirmed by a real build at commit `1b6059d`, after fixing D-23's MAX_PATH defect).
  The pre-cut baseline is now measured and recorded in `01-EVIDENCE.md`: `Setup.exe`
  686.7 MB, expanded install 1.93 GB, built tree 1.92 GB (exact match to the dev-tree figure
  below, confirming it was not build residue), portable ZIP 884.7 MB. Neither the owner's
  ~800 MB installer nor ~900 MB installed recollection closes under a MiB/MB
  reinterpretation. Removing D-24's torch+transformers plus one duplicate model copy
  explains ~40% of the installed-size gap (to ~1.36 GB) but leaves ~455 MB open — recorded
  as an explicit open question (known / ruled-out / closing-evidence), not averaged or
  asserted. The installer-size direction (owner recalled *more* than measured) has no
  stated cause at all. See `01-EVIDENCE.md` `## Size — reconciliation` for full detail.

- **Beta-6's "complete" certification is not trustworthy.** Its Phase 5 release gate never
  measured size or launch time, names no physical machine, and cites beta-5 artifacts while
  certifying beta-6. See `.planning/milestones/v0.9.0-beta.6/README.md`.

- Physical clean-machine verification (CPU-only, NVIDIA, AMD/Intel) still outstanding from
  beta 6 and not claimed by this phase.

- 01-EVIDENCE.md's pre-cut size baseline is now measured and recorded (Plan 01-01 Task 3, commit `b0a326d`), before Plan 01-04 rebuilds `app/dist/`. The residual ~455 MB installed-size gap and the unexplained installer-size direction remain open questions for Plan 01-08's reconciliation checkpoint or the owner directly — see `01-EVIDENCE.md` `## Size — reconciliation`.

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

Last session: 2026-07-31T12:54:12.547Z
Stopped at: Completed 01-06-PLAN.md
Resume file: None

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 30min + follow-up | 3 tasks | 3 new + 4 amended files |
| Phase 01 P02 | ~1h (interrupted, closed out) | 2 tasks | 2 new/modified files |
| Phase 01 P03 | ~2.5h | 3 tasks | 2 new + 2 modified files |
| Phase 01 P06 | ~2h30m | 3 tasks | 5 files |
