# Handoff — LecturePack 0.9.0-beta.3 (QoL / reliability)

_Session 2026-07-23. Branch `feat/cuda-engine`. Beta.2 (`deca663`) untouched._

Evidence: `docs/evidence/beta3/fanin_reduction.json` (full audit + phase plan),
`docs/evidence/current_session_status.json` (live checkpoint).

## Status
Graph workflow executed: Node 0 truth → 5 bounded audits → deterministic fan-in
→ phased implementation. **Backend/logic phases 1, 2a, 2b, 3, 4 complete and
tested; controller/adapter wiring + Phase 5 UI + Phase 6 release remain.** This
is a multi-session effort. **Do NOT publish beta.3; stop at `READY FOR USER
AUTHORIZATION`.**

### Session 2 (Phases 2b–4 logic) — commits `0434b0e`, `8f80f95`, `70cc7ff`
- **2b `app/desktop/win_integration.py`** — WindowsIntegration facade over
  injectable PowerRequester (keep-awake), TaskbarButton (ITaskbarList3, no
  QtWinExtras/comtypes), Notifier (QSystemTrayIcon); focus-gating, pref-gating,
  dedup (injected clock), click routing, test-notification; no-ops off Windows.
  15 tests. *Adapter/main wiring pending.*
- **3 `lecturepack/services/job_queue.py`** — one-active invariant, FIFO queue
  (reorder/Run-Now/remove/position), atomic persist + restart recovery; tz-aware
  scheduling (zoneinfo + injected clock; added `tzdata` dep + bundled it) with
  missed policies (run_when_opened/skip_if_missed/ask); `plan_resume` checkpoint
  math. 18 tests. *Controller cooperative-pause + adapter wiring pending.*
- **4 `lecturepack/services/job_ops.py`** — `plan_stage_retry` (preserve
  completed upstream, rerun failed+downstream), completion metrics, and
  **redacted** diagnostics (strips keys/bearer/labeled secrets, anonymizes
  paths; never includes transcript/content). 12 tests. *Controller/bridge
  exposure pending.*

Remaining integration + UI + release are tracked in
`docs/evidence/current_session_status.json` (`remaining_integration`).

## Delivered session 1 (green commits)

## Delivered this session (green commits)
- `f5be012` docs(readme): download links → public beta.2.
- `32eb2a5` **Phase 1 — authoritative job state machine.** New pure module
  `lecturepack/models/job_lifecycle.py`: 10 states (new/scheduled/queued/running/
  pause_requested/paused/completed/failed/interrupted/cancelled), legal-transition
  table + `assert_transition`, active-slot sets (one-active-job basis), and
  **session-ownership reconciliation** — an active job survives load only if the
  current session owns it and its pid is alive, else → `interrupted` (fixes the
  naive reset that would clobber a live job once concurrency exists). Integrated
  into `Job` non-breakingly (new `lifecycle`+`session` fields, backfilled from
  `overall_status` so beta.2 jobs upgrade cleanly; `set_lifecycle` validates edges).
  56 tests (49 unit + 7 Job integration).
- `83d644a` **Phase 2 (partial) — clean-state packaging gate (§3).**
  `build.check_clean_state()` fails the build if the onedir bundles job/dev data
  (jobs/exports/thumbs/LecturePackData/study_packs, *config.json, *.job.json,
  *.db/*.sqlite, stray app *.json) and asserts the engine payload is present +
  non-empty; Qt `_internal` JSON allowlisted. Wired after `bundle_engine()`.
  8 tests; verified clean against the real beta.2 dist.

## Architecture (confirmed — build here)
Packaged app = WebEngine (`app/desktop/main.py` → `app/ui/` vanilla-JS
`window.LP` + `app.css`, via `bridge.py` QWebChannel). Engine = `lecturepack/`
(`JobController`, `models/job.py`) via `engine_adapter.py::LecturePackAdapter`.
The old `lecturepack/ui/` PySide pages are **not shipped**. `bridge.js` SIGNALS
array must stay in sync with `bridge.py` signals.

## Remaining phases (see fanin_reduction.json for file ownership)
- **2b win_integration.py**: keep-awake (`ctypes SetThreadExecutionState`),
  taskbar (hand-rolled `ctypes ITaskbarList3` — QtWinExtras gone in Qt6; zero new
  deps), notifications (`QSystemTrayIcon`), focus (`QApplication.applicationState`).
  Injectable PowerRequester/TaskbarButton/Notifier seams → fakeable unit tests.
- **3 queue/scheduler/pause**: new `lecturepack/services/job_queue.py` (FIFO
  persist/reorder/RunNow/remove, one-active invariant); tz-aware scheduler
  (`zoneinfo`) + missed policies; **stage-boundary** cooperative pause in
  `job_controller` (no mid-stage resume exists — finish atomic op / clean-terminate,
  discard partials, restart interrupted stage; replace `QThread.terminate`). Add a
  clock seam (no `conftest.py`/injected clock today).
- **4 retry/completion/diagnostics**: stage-specific retry (today `run_pipeline`
  bulk-resets ALL stages); completion metrics; redacted diagnostics.
- **5 UI**: Notifications settings, completion panel, retry, queue/schedule/pause
  UI, Interrupted cards (Resume/Restart/View/Remove), **new History screen**,
  Processing empty state, click routing; animations + `prefers-reduced-motion`.
- **6 release**: `version.py`→0.9.0-beta.3, win_version_info, iss AppVersion,
  What's New/CHANGELOG/notes; build on Inno box; packaged + upgrade acceptance;
  **stop for authorization**.

## Data safety
`~/LecturePackData` never touched. Data dir is outside install `{app}`; AppId
`{{9F5D2E31-7C4A-4B8E-9E1D-LECTUREPACK01}}` stable → upgrades preserve data.

## Rollback
`git revert <sha>` per commit (never reset/force-push). Safety tag:
`safety/start-beta3-qol-7cdc889`.
