# Electron Bridge Coverage Map

Mapping the historical Qt/QWebChannel frontend bridge to the Electron/Python
JSONL sidecar for **LecturePack Phase 8**.

- **Branch:** `deepseek/electron-bridge-contract`
- **Status:** Contract, documentation, and regression tests only. No production
  Electron, Qt, engine, UI, or packaging code is changed by this deliverable.
- **Machine-readable contract:** [`electron-spike/contracts/electron-bridge-contract.json`](../electron-spike/contracts/electron-bridge-contract.json)
- **Regression tests:** [`tests/test_electron_bridge_contract.py`](../tests/test_electron_bridge_contract.py)
- Related: [`ELECTRON_MIGRATION_VERTICAL_SLICE.md`](ELECTRON_MIGRATION_VERTICAL_SLICE.md),
  [`HANDOFF_PHASE_7.md`](HANDOFF_PHASE_7.md)

---

## PHASE 8 IMPLEMENTATION CHECKLIST

Status values: `IMPLEMENTED` · `PARTIAL` · `MISSING` · `DEFERRED`.

### Implemented core operations (30)

| Phase 8 requirement | Bridge operation | Where implemented |
| --- | --- | --- |
| bootstrap/runtime readiness | `health_check` (cmd) · `ready`, `bootstrap_progress` (events) | `electron-spike/python-sidecar.py` |
| list jobs | `list_jobs` (cmd) · `jobs_changed` (event) | `electron-spike/python-sidecar.py` |
| restore jobs after reopening | `get_job`, `open_job` (cmds) · `active_job` (event) | `electron-spike/python-sidecar.py` + `production-main.js` `bootstrap()` |
| import local video | `browse_video`, `import_video` (cmds) · `onboarding` (event) | `production-main.js` `browseVideo()` + `python-sidecar.py` |
| start job | `start_processing` → `start_job` (cmd) | `electron-spike/electron-bridge.js` + `python-sidecar.py` |
| cancel job | `cancel_job` (cmd) | `electron-spike/python-sidecar.py` |
| job status | `status_changed`, `job_completed` (events) | `electron-spike/python-sidecar.py` |
| progress/stages | `pipeline_changed` (event) | `electron-spike/python-sidecar.py` |
| processing logs | `log_line` (event) | `electron-spike/python-sidecar.py` |
| slides | `get_slides` (cmd) · `slides_changed` (event) | `electron-spike/python-sidecar.py` |
| transcript | `get_transcript` (cmd) · `transcript_changed` (event) | `electron-spike/python-sidecar.py` |
| exports | `export`, `export_all`, `export_one` (cmds) · `export_done` (event) · `open_export_folder`, `open_job_folder` (cmds) | `python-sidecar.py` + `production-main.js` `openJobFolder()` |
| errors | `error` (event) | `electron-spike/python-sidecar.py` |
| clean shutdown | `shutdown` (cmd) · `exit` (event) | `python-sidecar.py` + `production-main.js` `stopSession()` |


### Missing core operations (4) — connect in these exact files

| Bridge operation | Frontend consumer | Connect here |
| --- | --- | --- |
| `bootstrap_complete` (event) | `app/ui/app.js` subscribes via `lpBridge.on('bootstrap_complete', …)`; the sidecar never emits it. | `electron-spike/python-sidecar.py` — emit `{"event":"bootstrap_complete"}` after the engine bootstrap finishes (alongside/after the `ready` emission). `electron-spike/electron-bridge.js` already forwards unknown events through `deliver()`; no adapter change needed for delivery. |
| `set_slide_state` (command) | `app/ui/app.js` calls `lpBridge.call('set_slide_state', index, state)` to accept/reject a slide; `electron-bridge.js` resolves it as a noop. | (1) `electron-spike/electron-bridge.js` — remove `set_slide_state` from `noopCalls` and add a `mapCall` branch emitting command `set_slide_state`. (2) `electron-spike/python-sidecar.py` — add `elif command == "set_slide_state"` that persists the candidacy decision files. |
| `save_corrections` (command) | `app/ui/app.js` calls `lpBridge.call('save_corrections', texts_json)` to persist transcript edits; `electron-bridge.js` resolves it as a noop. | (1) `electron-spike/electron-bridge.js` — remove `save_corrections` from `noopCalls` and add a `mapCall` branch. (2) `electron-spike/python-sidecar.py` — add an `elif command == "save_corrections"` handler. |
| `export_progress` (event) | `app/ui/app.js` subscribes via `lpBridge.on('export_progress', …)`; the sidecar only emits `export_done`. | `electron-spike/python-sidecar.py` — emit `{"event":"export_progress", …}` from the Export stage (for example in `_on_stage_progress` when `stage == "Export"`). Delivery already works. |

### Partial core operations (4)

| Bridge operation | What is covered | What remains |
| --- | --- | --- |
| `get_bootstrap` (cmd) | Initial state is delivered by the `ready` event + Electron host bootstrap (`health_check` + `list_jobs` + restore). | The dedicated `get_bootstrap` call is intercepted as a noop; the sidecar returns no bootstrap payload for it. |
| `ui_ready` (cmd) | Readiness is established by the sidecar `ready` event and the renderer `pageReady` flag. | The legacy `ui_ready` slot is acknowledged (noop) and does not return state. |
| `set_setting` (cmd) | Primary processing settings are applied (`slide_detection_preset`, `engine`, `transcription_backend`); theme is handled locally. | Secondary settings are acknowledged without persistence; `get_settings` (initial load) is a noop. |


---

## Detailed coverage (Phase 8 core operations)

Legend — **Direction:** `cmd` = renderer/main → sidecar command; `evt` = sidecar/main → renderer event.
**Old Qt:** the QWebChannel slot/signal exposed on `backend` by `app/desktop/bridge.py`.
**Electron:** the command or event on the JSONL sidecar / Electron main process.

### bootstrap / runtime readiness

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime readiness | `lpBridge.call('get_bootstrap')`, `bridge.js` `backend.ui_ready()` | `get_bootstrap`, `ui_ready` slots; `bootstrap_progress`, `bootstrap_complete`, `ui_ready_signal` signals | `health_check` (cmd); `ready`, `bootstrap_progress` (evt) | `{}` | `{healthy, paths, qt_application}`; `{event:ready, engine_loaded}` | `PARTIAL` | core | `get_bootstrap`/`ui_ready` are intercepted noops; readiness is driven by the `ready` event and Electron host bootstrap. |
| Engine import progress | `lpBridge.on('bootstrap_progress')` | `bootstrap_progress` signal | `bootstrap_progress` (evt) | — | `{event, id, state, detail}` | `IMPLEMENTED` | core | Emitted while the engine loads. |
| Bootstrap completion | `lpBridge.on('bootstrap_complete')` | `bootstrap_complete` signal | *(missing)* | — | `{event}` expected | `MISSING` | core | Sidecar never emits `bootstrap_complete`; connect in `python-sidecar.py`. |

### list jobs & restore

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Enumerate jobs | Electron host `bootstrap()` / `list_jobs`; UI via `jobs_changed` | `jobs_changed` signal | `list_jobs` (cmd); `jobs_changed` (evt) | `{}` | response `{jobs}`; event `{jobs: [...]}` | `IMPLEMENTED` | core | `jobs_changed` is delivered to the renderer as the direct summary array expected by `app.js`. |
| Restore job on reopen | Electron host `restoreJob()` | `get_job`-equivalent via `get_bootstrap` | `get_job` (cmd); `active_job` (evt) | `{job_id}` | `{job, manifest, source, state, exports, job_dir, export_dir}`; `{event:active_job, id, title}` | `IMPLEMENTED` | core | Host calls `get_job` + `get_slides` + `get_transcript` after `list_jobs` on `ready`. |

### import local video

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Choose file | `lpBridge.call('browse_video')` | `browse_video` slot | `browse_video` (cmd, main-handled) | `{}` | `{ok, cancelled, job, job_id}` | `IMPLEMENTED` | core | `production-main.js` opens a dialog then forwards to `import_video`. |
| Import file | `lpBridge.call('import_video')`; `open_job` fallback | `import_video` slot; `onboarding` signal | `import_video` (cmd); `onboarding` (evt) | `{path, title, preset, bundled_demo}` | `{job_id, job, source}`; `{event:onboarding, job, name, meta}` | `IMPLEMENTED` | core | Creates + activates a persisted job. |

### processing options & start / cancel



### slides & transcript

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Load slides | `open_job` path / host restore; `lpBridge.on('slides_changed')` | `slides_changed` signal | `get_slides` (cmd); `slides_changed` (evt) | `{job_id}` | `{job_id, slides}`; `{event, job, slides, duration, durationMid}` | `IMPLEMENTED` | core | |
| Accept/reject slide | `lpBridge.call('set_slide_state', index, state)` | `set_slide_state` slot | *(missing)* | `{index, state}` | — | `MISSING` | core | Intercepted as noop in `electron-bridge.js`; needs a sidecar command. |
| Load transcript | `open_job` path / host restore; `lpBridge.on('transcript_changed')` | `transcript_changed` signal | `get_transcript` (cmd); `transcript_changed` (evt) | `{job_id}` | `{job_id, transcript}`; `{event, job, reviewSegments, transcript}` | `IMPLEMENTED` | core | |
| Save transcript edits | `lpBridge.call('save_corrections', texts_json)` | `save_corrections` slot | *(missing)* | `{texts}` | — | `MISSING` | core | Intercepted as noop in `electron-bridge.js`; needs a sidecar command. |

### exports

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Export | `lpBridge.call('export_all'/'export_one')` | `export_all`, `export_one` slots; `export_done` signal | `export` (cmd); `export_done` (evt) | `{job_id}` | `{job_id, started, already_running}`; `{event:export_done}` | `IMPLEMENTED` | core | Both frontend calls map to `export`. |
| Export progress | `lpBridge.on('export_progress')` | `export_progress` signal | *(missing)* | — | `{event}` expected | `MISSING` | core | Sidecar only emits `export_done`; connect in `python-sidecar.py`. |
| Open export/job folder | `lpBridge.call('open_export_folder'/'open_job_folder')` | `open_export_folder` slot | `open_export_folder`/`open_job_folder` (cmd, main-handled) | `{job_id}` | `{ok, path}` | `IMPLEMENTED` | core | `production-main.js` via `get_job` → `shell.openPath`. |

### errors & shutdown

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |


---

## Deferred operations (not required by Phase 8)

Each remaining bridge operation is `DEFERRED` in the machine-readable contract
(`production_core: false`). The full machine-readable list in
`electron-spike/contracts/electron-bridge-contract.json` is the source of truth;
grouped here for readability.

| Group | Operations (status DEFERRED) |
| --- | --- |
| URL/Paste Link import | `probe_media_url`, `import_media_url`, `cancel_media_url`, `media_link_support` (cmds) · `media_link_state`, `media_probe`, `media_progress`, `media_done` (evts) |
| Updater / whats-new | `check_updates`, `get_updater_state`, `start_update_download`, `cancel_update_download`, `install_downloaded_update`, `open_release_page`, `set_update_channel`, `set_auto_check`, `skip_update_version`, `clear_skipped_version`, `install_update`, `whatsnew_seen` (cmds) · `update_available`, `update_progress`, `update_ready`, `update_error`, `update_state`, `whatsnew` (evts) |
| Ollama / smart study | `list_ollama_models`, `install_smart_study`, `cancel_smart_study`, `smart_study_status`, `launch_ollama_installer`, `set_study_preset` (cmds) · `ollama_models`, `smart_study` (evts) |
| Groq | `set_groq_key`, `remove_groq_key`, `test_groq_key` (cmds) · `groq_status` (evt) |


---

## Incompatibilities and remediation notes

1. **`jobs_changed` envelope.** The sidecar JSONL payload is
   `{event, jobs}`; `electron-bridge.js` `eventPayload()` strips the envelope
   and passes the direct array to `app.js`. Do not change this.
2. **Theme is renderer-local.** `electron-bridge.js` handles
   `set_setting('theme', value)` with `localStorage` and never issues a sidecar
   request. Keep it that way (test 8 guards it).
3. **No initial settings push.** `get_settings` is a noop and the sidecar has no
   startup `settings_changed` broadcast; the UI relies on defaults for
   processing options.
4. **`bootstrap_complete` / `export_progress` / `set_slide_state` /
   `save_corrections`** are the four Phase 8 core gaps; connect them as listed
   in the checklist.
5. **Deferred features** (`media_*`, `update_*`, Ollama, Groq, GPU, queue,
   notifications) are intentionally left as no-ops/interception in the
   production scope and must not be re-enabled for Phase 8.

| GPU / installer / admission | `install_cuda_pack`, `cancel_cuda_pack`, `cuda_pack_status`, `validate_cuda`, `validate_vulkan`, `test_endpoint`, `browse_model`, `save_project` (cmds) · `cuda_status`, `cuda_pack`, `vulkan_status` (evts) |
| Study AI | `ask_ai`, `generate_quiz`, `cancel_quiz`, `save_quiz_session`, `generate_flashcards`, `cancel_flashcards`, `save_flashcard_session`, `save_notes` (cmds) · `ai_token`, `ai_done`, `ai_status`, `quiz_changed`, `quiz_status`, `flashcards_changed`, `flashcards_status`, `study_changed` (evts) |
| Queue / scheduling / deletion | `schedule_job`, `unschedule_job`, `enqueue_job`, `reorder_queue`, `run_now`, `remove_from_queue`, `retry_stage`, `pause_job`, `resume_job`, `restart_job`, `delete_job`, `delete_jobs`, `set_job_group`, `set_jobs_group` (cmds) · `queue_changed`, `pause_state`, `job_deleted` (evts) |
| Notifications / diagnostics / repair | `test_notification`, `get_notification_prefs`, `set_notification_prefs`, `run_diagnostics`, `repair_selection`, `get_post_completion`, `log_tour_trace`, `acknowledge_setup` (cmds) · `notification_prefs`, `notification_navigate`, `diagnostics`, `repair_event`, `post_completion`, `storage_changed` (evts) |
| Guided demo / misc | `start_demo_job`, `end_demo_job`, `exit_application` (cmds) · `demo_event` (evt) |

| Errors | Renderer event handler | (backend diagnostics) | `error` (evt) | — | `{event, error, command, response_to, job, stage}` | `IMPLEMENTED` | core | Also carries `ok:false` on failed command responses. |
| Clean shutdown | Electron host `stopSession()` | app close | `shutdown` (cmd); `exit` (evt) | `{}` | response `{ok}`; `{event:exit, code, signal}` | `IMPLEMENTED` | core | Host stops the sidecar, terminates the process tree, emits `exit`. |

### Sidecar transport events (internal)

| Feature | Old Qt method/signal | Electron command/event | Status | Notes |
| --- | --- | --- | --- | --- |
| Request response | Qt slot return values | `response` (evt, with `response_to`) | `IMPLEMENTED` | Internal JSONL correlation, not surfaced to `app.js`. |
| Settings broadcast | `settings_changed` signal | `settings_changed` (evt) | `PARTIAL` | Emitted per `set_setting`; no full initial push. |

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Select processing options | `lpBridge.call('set_setting', key, value)` via Settings; `start_processing` mode/preset | `set_setting`, `start_processing` slots; `settings_changed` signal | `set_setting` (cmd); `settings_changed` (evt) | `{key, value}` | `{key, value, applied}`; `{event:settings_changed,…}` | `PARTIAL` | core | Primary keys applied; secondary acked; theme handled locally (`electron-bridge.js`) and never sent to the sidecar. |
| Start job | `lpBridge.call('start_processing', mode)` | `start_processing` slot | `start_processing` → `start_job` (cmd) | `{mode, auto_export, preset}` | `{job_id, started, already_running}` | `IMPLEMENTED` | core | `electron-bridge.js` maps `start_processing` to `start_job`. |
| Cancel job | `lpBridge.call('cancel_job')` | `cancel_job` slot | `cancel_job` (cmd) | `{job_id}` | `{job_id, cancelled}` | `IMPLEMENTED` | core | Cancels the active pipeline and reports terminal status. |

### job status / progress / logs

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Job status | `lpBridge.on('status_changed')`, `jobs_changed` | `status_changed`, `jobs_changed` signals | `status_changed` (evt) | — | `{event, job, label, pct, detail, right, side}` | `IMPLEMENTED` | core | |
| Progress/stages | `lpBridge.on('pipeline_changed')` | `pipeline_changed` signal | `pipeline_changed` (evt) | — | `{event, job, title, meta, stages}` | `IMPLEMENTED` | core | Per-stage progress array. |
| Processing logs | `lpBridge.on('log_line')` | `log_line` signal | `log_line` (evt) | — | `{event, job, tag, color, text}` | `IMPLEMENTED` | core | |
| Completion | `lpBridge.on('job_completed')` | `job_completed` signal | `job_completed` (evt) | — | `{event, job_id, slides_detected, segment_count}` | `IMPLEMENTED` | core | Emitted after the final Export stage. |

| `settings_changed` (event) | Emitted after each `set_setting`. | There is no initial full-settings push on startup. |

### Deferred operations (100)

Not required by Phase 8 and intentionally not implemented: URL/Paste Link import
(`probe_media_url`, `import_media_url`, `cancel_media_url`,
`media_link_state`, `media_probe`, `media_progress`, `media_done`), the updater
and whats-new (`check_updates`, `get_updater_state`, all `update_*`/`whatsnew`
operations), Ollama/smart-study, Groq, GPU/CUDA installer and backend
admission, study AI (quiz/flashcards/ask_ai), queue/scheduling/deletion
controls, notifications, diagnostics, context repair, storage measurement
(`storage_changed`), the guided demo, and the historical Static/Mock/Python
spike modes (`main.js` diagnostic modes are superseded by `production-main.js`).
