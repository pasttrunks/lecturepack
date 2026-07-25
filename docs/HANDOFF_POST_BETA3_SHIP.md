# Handoff — LecturePack 0.9.0-beta.3 SHIPPED (post-release)

_Prepared 2026-07-24. Read this first in a new session, then `git log --oneline -20`._

## TL;DR — current state
**beta.3 is built, published, and live on the default branch.** All of Phases 1–6
are done. Nothing is blocked. Remaining items are optional polish + human-only
validations. Do **not** re-do finished work; do **not** move published tags.

- **Published release:** `v0.9.0-beta.3` — **Latest, non-prerelease** —
  https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.3
  Assets: `Setup.exe` (395 MB, sha256 `bbd1db0f…`), `Portable.zip` (526 MB,
  sha256 `bc101cb6…`), `SHA256SUMS.txt`. Published digests == local == SHA256SUMS.
- **Default branch `main`** = `3fd9244` (pushed). Public README now points to
  beta.3 with refreshed screenshots.
- **Dev branch `feat/cuda-engine`** = `0c8c951` (pushed). This is where all
  development happened; `main` was merged from it.
- **Immutable:** `v0.9.0-beta.2` → `deca663` (never touch). `v0.9.0-beta.1`.
- Working tree clean (only pre-existing untracked `promo-video/`, `scripts/` —
  leave them alone).

## Version authority (IMPORTANT — two separate versions)
- **Release/app version:** `app/desktop/version.py` `__version__ = "0.9.0-beta.3"`.
  This is what `build.py`, the updater, and installer use. Bump THIS for releases.
- **Engine package version:** `lecturepack.__version__ = "1.2.0"` (in
  `lecturepack/constants.py` via `APP_VERSION`). SEPARATE authority;
  `test_packaging_and_safety.py` asserts it == "1.2.0". Do not conflate.

## Tests
- Full suite: **475 passed** at `ff8265c` (`.venv\Scripts\python.exe -m pytest -q`).
  Run with `-p no:faulthandler` to avoid a cosmetic slow-test faulthandler dump.
- ~110 tests added across beta.3. Key new test files: `test_job_lifecycle.py`,
  `test_job_lifecycle_integration.py`, `test_beta3_packaging.py`,
  `test_win_integration.py`, `test_job_queue.py`, `test_job_ops.py`,
  `test_pause_resume_retry.py`, `test_webview_beta3.py`, `test_adapter_startup.py`.

## Architecture (build features HERE)
- **Shipped UI = WebEngine:** `app/desktop/main.py` (QMainWindow + QWebEngineView)
  loads `app/ui/` (vanilla-JS `window.LP` IIFE in `app.js` + `app.css`) via
  `app/desktop/bridge.py` (QWebChannel `Backend`). The **old `lecturepack/ui/`
  PySide pages are NOT shipped** — never build features there.
- **Engine = `lecturepack/`** (`JobController`, `models/job.py`) wired through
  `app/desktop/engine_adapter.py::LecturePackAdapter`.
- **bridge.py signals MUST stay in sync with `app/ui/bridge.js` SIGNALS array.**
- Packaged entry: `app/lecturepack_desktop.py` → spec `app/packaging/lecturepack.spec`.

## What beta.3 delivered (all committed + on main)
- **Phase 1** `lecturepack/models/job_lifecycle.py` — authoritative state machine
  (new/scheduled/queued/running/pause_requested/paused/completed/failed/
  interrupted/cancelled), legal transitions, **session ownership** (session_id/
  process_id) + `reconcile_on_load` (dead-session running → interrupted). Wired
  into `Job` (state.json gains `lifecycle`+`session`, backfilled from
  `overall_status` for beta.2 jobs). `set_lifecycle()` validates edges.
- **Phase 2a** clean-state packaging gate in `build.py`
  (`check_clean_state`/`validate_clean_state`) — fails build if job/dev data
  bundled; asserts engine payload present.
- **Phase 2b** `app/desktop/win_integration.py` — `WindowsIntegration` facade over
  injectable `PowerRequester` (keep-awake, `SetThreadExecutionState`),
  `TaskbarButton` (hand-rolled ctypes ITaskbarList3 — no QtWinExtras/comtypes),
  `Notifier` (QSystemTrayIcon). Focus-gating, dedup, click routing. No-ops
  off-Windows. Wired in `main.py` (tray, focus, aboutToQuit).
- **Phase 3** `lecturepack/services/job_queue.py` — one-active invariant, FIFO
  queue (reorder/Run-Now/remove), atomic persist to `<data_dir>/queue.json`,
  restart recovery; tz-aware scheduling (`zoneinfo` + injected clock; **added
  `tzdata` dependency + bundled it in the spec**) with missed policies
  (run_when_opened/skip_if_missed/ask); `plan_resume`/`resume_stage` checkpoint
  math. Cooperative pause/resume + `retry_stage` wired into `JobController`
  (stage-boundary; NO `QThread.terminate` for pause; `pause_state_changed` signal).
- **Phase 4** `lecturepack/services/job_ops.py` — `plan_stage_retry` (preserve
  completed upstream), completion metrics, **redacted diagnostics** (strips
  keys/bearer/labeled secrets, anonymizes paths).
- **Adapter/bridge seam** (`engine_adapter.py`+`bridge.py`+`main.py`+`bridge.js`):
  per-launch session id, keep-awake/taskbar/notify at lifecycle points,
  one-active enqueue-when-busy + auto-promote next, startup reconciliation SWEEP
  (`_reconcile_jobs_on_startup` in `on_ui_ready`), lifecycle-aware `_list_jobs`.
  New bridge methods: pause_job/resume_job/retry_stage/restart_job, enqueue/
  reorder/run_now/remove, schedule/unschedule, notification prefs, run_diagnostics,
  open_job_folder. New signals: queue_changed, pause_state, notification_prefs,
  notification_navigate, diagnostics, job_completed, post_completion.
- **Phase 5 UI** (`app/ui/`): Settings→Notifications (6 toggles+Test), completion
  panel (metrics+actions), pause/resume controls, Interrupted/Needs-Attention
  cards (Resume/Restart/View/Remove), Home **queue UI** (Run Now/reorder/remove),
  **scheduling UI** (datetime + missed policy + Scheduled list), reduced-motion.
- **Phase 6:** version bump, CHANGELOG (beta.2+beta.3), RELEASE_NOTES_0.9.0-beta.3.md,
  build, acceptance, publish, README/main sync, refreshed screenshots.

## Acceptance evidence
`docs/evidence/beta3/acceptance.json` (build gates, hashes, real-lecture pipeline,
publish, live updater discovery) and `docs/evidence/current_session_status.json`.
- **Real-lecture pipeline acceptance PASSED** on a 4-min segment of a genuine
  lecture using the built dist engine into a disposable dir: 446 words / 18
  segments transcribed + 3 slides detected. (Sample video created at
  `C:\Users\marsh\Videos\LecturePack Input\CL100-Day2-sample-4min.m4v`; full
  lecture is `CL100 - Day 2 - Egypt and Archaeology.m4v` there.)
- Live updater: beta.2 users are offered beta.3 with matching digest.

## Human-pending validations (NOT blockers; disclosed like beta.1/beta.2)
1. **Packaged GUI click-through** on the installed app (queue/pause/notifications/
   completion/interrupted).
2. **Live beta.2 → beta.3 install-over upgrade** on a disposable Windows profile/VM
   (data preservation).
- ⚠️ **Why not auto-run:** the built app has **no data-dir override** — launching
  it runs the startup reconciliation SWEEP against the user's REAL
  `~/LecturePackData` jobs (flips orphaned running→interrupted = modifying real
  jobs). Rule: never modify real jobs. **Recommended fix: add a
  `LECTUREPACK_DATA_DIR` env override** to `app/desktop/paths.py::data_dir()` AND
  `ConfigManager` default, so packaged GUI acceptance can run against a throwaway
  profile. This is the single most useful next task.

## Known gotchas / env facts
- **code-review-graph post-commit hook prints a cosmetic `UnicodeEncodeError`
  (cp1252) traceback on Windows — commits STILL SUCCEED. Ignore it.** (It also
  causes `git commit` chained with `&&` to sometimes report exit 1 while having
  succeeded — verify with `git log`.)
- **Git remote-tracking ref got stale this session** (`origin/main` showed
  `a93f14d`/`dff1825` inconsistently). Trust `git ls-remote origin refs/heads/main`
  as authoritative. Never force-push; integrate with `git pull --no-rebase`.
- **beta.3 is non-prerelease** → the in-app updater **stable channel now also
  offers beta.3** (channel filter keys off the prerelease flag). If offering a
  beta to stable users is unwanted, flip it back:
  `gh release edit v0.9.0-beta.3 --prerelease=true` (it stays downloadable).
- **Inno Setup 6 (ISCC)** is installed at
  `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (build.py `_find_iscc` finds it).
- **Groq API key** lives ONLY in Windows Credential Manager (never in the tree).
- **Screenshot pipeline** (for future README updates): headless **Chrome**
  (`C:\Program Files\Google\Chrome\Application\chrome.exe`) `--headless=new
  --screenshot` against a static server (`python -m http.server 8778 -d app/ui`)
  using a `_capture.html` wrapper that iframes `index.html` and drives it via
  `[data-nav=...]` clicks + `#btn-theme` toggle. **Disable transitions in the
  wrapper** (`*{transition:none!important}`) before capture, else theme-toggled
  frames show stale button backgrounds (this bit us on the light-mode shot — it
  was a CAPTURE artifact, the app is fine). The Claude in-app Browser pane
  CANNOT screenshot here (doesn't composite).
- **Do NOT run `claude remote-control` from inside a session** to test it — it's a
  user CLI action. It IS real (phone pairing via QR in the Claude app Code tab).

## Build / release commands
```
.\.venv\Scripts\python.exe -m pytest -q -p no:faulthandler      # tests
.\.venv\Scripts\python.exe app\packaging\build.py               # full build (needs ISCC)
# artifacts land in app\dist\installer\
gh release create v0.9.0-beta.N --prerelease --notes-file docs/RELEASE_NOTES_...md <assets>
```
Release workflow is `workflow_dispatch`-only and `ci.yml` triggers on main/v1.2 —
so pushing a tag does NOT rebuild/overwrite verified binaries.

## Recommended next steps (priority order)
1. **Add `LECTUREPACK_DATA_DIR` override** (paths.py + ConfigManager) so packaged
   GUI acceptance runs against a disposable profile. Then run the packaged
   click-through + beta.2→beta.3 upgrade acceptance.
2. Decide on the **stable-channel** implication (keep beta.3 non-prerelease, or
   flip back to prerelease).
3. If a post-publish defect appears: **prepare beta.4** (bump version.py, build,
   publish). **Never move the beta.3 tag.**
4. Optional UI polish deferred: dedicated History screen, Processing empty state,
   showcase_new_job.png recapture (kept old — the new-job overlay needs an import
   to trigger).

## Rollback
`git revert <sha>` per commit (never reset/force-push). Safety tags exist:
`safety/resume-beta3-phases2b6-4e443d6`, `safety/start-beta3-qol-7cdc889`.
`~/LecturePackData` was never touched this whole effort.
