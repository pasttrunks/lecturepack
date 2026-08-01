---
gsd_state_version: 1.0
milestone: v0.9.0-beta.7
milestone_name: Clean-Device Footprint and First Launch
current_phase: 02
current_phase_name: real-lecture-import-processing
status: executing
stopped_at: Completed 02-01-PLAN.md
last_updated: "2026-08-01T11:42:43.739Z"
last_activity: 2026-08-01
last_activity_desc: Phase 02 execution started
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 12
  completed_plans: 9
  percent: 50
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device.
**Current focus:** Phase 02 — real-lecture-import-processing

## Current Position

Phase: 02 (real-lecture-import-processing) — EXECUTING
Plan: 2 of 4
Status: Ready to execute
Last activity: 2026-08-01 — Phase 02 execution started

Milestone progress: [████████░░] 88% (phase-level; 7/8 plans complete within Phase 1)

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
- [Phase 01 Plan 04]: D-01 Qt pruning (~101MB) + model dedupe (~148MB) implemented as post-build deletion in build.py; D-24 torch/transformers excludes (~416.5MB) added to lecturepack.spec; D-04 resources/ (106.3MB) investigated and reported, kept not cut. Full suite 964 passed/7 failed (baseline 944/7, zero new failures). Build-dependent verification (real post-cut build, packaged smoke, WebEngine render proof) explicitly left to the orchestrator.
- [Phase ?]: [Phase 01 Plan 07]: D-08/D-09/D-11/D-12/D-13/D-14/D-16/D-17 implemented on the UI side. RuntimeSetupGateModel gains checking/checklist states routed off bootstrap_pending/validation_path/setup_acknowledged (never a runtime_health_state string), with all seven pre-existing states byte-identical. Row identity is always the fixed FIRST_RUN_ROWS array keyed to the backend's FIRST_RUN_CHECKLIST_ITEMS. Badge colour comes only from the audited .lp-state[data-state] class rule (app/ui/app.css untouched, net zero lines). syncDemoAdmission() now requires the acknowledged flag so the guided demo is reachable only after Continue/Skip. Full suite: 1006 passed, 7 failed (same 7 pre-existing failures; zero new failures). Four UI-SPEC backstop rows (reduced-motion timing, focus containment, real-width layout, whisper slow-notice text) deferred to Plan 01-08's packaged session.
- [Phase ?]: [Phase 01 Plan 05]: D-18/D-19/D-20/D-21 implemented. SingleInstanceGuard (QLocalServer/QLocalSocket) runs right after QApplication(sys.argv) and before MainWindow()/Backend.__init__, raises the existing window via a shared raise_and_focus() rather than exiting silently, and fails open to primary on any IPC error or stale-endpoint reclaim. AppUserModelID declared as main()'s first statement (mechanism-justified per 01-FINDINGS-icon.md's Task 1 diagnosis, which ruled out setWindowIcon and did not reproduce the owner's symptom on this beta-7 build) and matched byte-for-byte in lecturepack.iss. Both icon-resolution guards now report a missing .ico instead of silently continuing. Full suite: 1036 passed, 9 failed (1006 baseline + 28 new tests; the 7 pre-existing failures are unchanged; 2 new failures are a pre-existing BUG-27 stale-test-fixture issue confirmed unrelated to this plan and logged to deferred-items.md). Installed-build two-process and icon-visible proofs remain backstop items owned by Plan 01-08.
- [Phase ?]: [Phase 02 Plan 01]: D-01/D-02 implemented — ConfigManager.persist_runtime_health(exe_paths=...) seeds whisper_exe/ffmpeg_exe/ffprobe_exe from the bootstrap's resolved inventory inside the existing one-time migration guard, never overwriting a real user-set path; start_processing()'s whisper gate now resolves via EngineRegistry.resolve() (Slides Only unaffected); import_video() runs detect_binaries() before _kick_poster() so the first import in a session gets a real poster. Full suite: 1044 passed, 7 failed (same 7 pre-existing release_trust failures; zero new failures).

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

## Deferred Verification

| Phase | State | Resume |
|-------|-------|--------|
| 1 | blocked_on_human_verification | `/gsd-execute-phase 1` (runs 01-08) |

Autonomous mode stopped here by design, not by failure. Seven of eight plans are now executed
and committed; the one remaining (`01-08`) is `autonomous: false` and carries
`checkpoint:human-verify` gates that require a person at a Windows machine. It was not
attempted, skipped, or partially applied.

**01-05 — single instance + taskbar icon (DONE, commits `253bc71`/`16f7a6c`).** Task 1's
diagnosis (`01-FINDINGS-icon.md`) confirmed candidate (b) — the silently-guarded
`setWindowIcon` — is ruled out on the installed build; candidate (a), the missing
`SetCurrentProcessExplicitAppUserModelID` call, is the only remaining explanation, though
the owner's blank-icon symptom did not reproduce during diagnosis. Tasks 2-3 implemented
`SingleInstanceGuard` (D-18/D-19), the AUMID declaration matched byte-for-byte in
`lecturepack.iss` (D-20), and non-silent icon-resolution guards (D-21) — see
`01-05-SUMMARY.md`. The installed-build two-process raise-and-focus proof and the
icon-visible proof remain `verification: backstop` items, owned by Plan 01-08.

**01-08 — physical evidence gate.** Needs a silent install/uninstall of the post-cut
`Setup.exe` for the expanded-tree figure, cold and warm launch timings on a clean profile
(D-07: architecturally different paths, measured separately), the two-process
raise-and-focus proof, the icon-visible proof, and the four UI-SPEC backstop rows deferred by
01-07 (reduced-motion timing, focus/keyboard containment, real-width layout, whisper
slow-notice text). A verified post-cut build is already sitting in `app/dist/` — do not
rebuild before using it.

## Session Continuity

Last session: 2026-08-01T11:42:35.147Z
Stopped at: Completed 02-01-PLAN.md
Resume file: None

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 30min + follow-up | 3 tasks | 3 new + 4 amended files |
| Phase 01 P02 | ~1h (interrupted, closed out) | 2 tasks | 2 new/modified files |
| Phase 01 P03 | ~2.5h | 3 tasks | 2 new + 2 modified files |
| Phase 01 P06 | ~2h30m | 3 tasks | 5 files |
| Phase 01 P04 | ~45min | 3 tasks | 6 files |
| Phase 01 P07 | ~50min | 3 tasks | 3 files |
| Phase 01 P05 | ~45min | 3 tasks | 6 files |
| Phase 02 P01 | ~35min | 2 tasks | 4 files |
