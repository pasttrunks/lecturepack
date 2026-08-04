# Electron Bridge Coverage Map

Mapping the historical Qt/QWebChannel frontend bridge to the Electron/Python
JSONL sidecar for **LecturePack Phase 8** (production core) and **Phase 9**
(backend feature parity).

- **Branch:** `deepseek/phase9-backend-parity`
- **Status:** Phase 8 production core is implemented and reconciled. Phase 9
  locks the final command/event contract (names + payloads) so Luna can build
  the Electron UI against it; the backend feature commits implement the
  operations behind those names.
- **Machine-readable contract:** [`electron-spike/contracts/electron-bridge-contract.json`](../electron-spike/contracts/electron-bridge-contract.json)
- **Regression tests:** [`tests/test_electron_bridge_contract.py`](../tests/test_electron_bridge_contract.py)
- Related: [`ELECTRON_MIGRATION_VERTICAL_SLICE.md`](ELECTRON_MIGRATION_VERTICAL_SLICE.md),
  [`HANDOFF_PHASE_7.md`](HANDOFF_PHASE_7.md),
  [`HANDOFF_PHASE_8.md`](HANDOFF_PHASE_8.md)

---

## PHASE 9 CONTRACT LOCK

The Phase 9 contract is locked in
`electron-spike/contracts/electron-bridge-contract.json`. Every operation below
has its **final** command/event name and payload shape defined. Operations stay
`DEFERRED` until the backend feature commits implement them; each feature commit
flips the affected operations to `IMPLEMENTED` (and `production_core: true`).

### Feature Group 1 — Job management and queue

| Operation | Direction | Request / event fields |
| --- | --- | --- |
| `delete_job` | cmd | `{job_id}` → `{ok, id, freed, method, error}` |
| `delete_jobs` | cmd | `{ids}` → `{ok, bulk, count, ids, failed, freed, error}` |
| `enqueue_job` | cmd | `{job_id}` → `{ok, position, job_id}` |
| `reorder_queue` | cmd | `{job_id, index}` → `{ok, job_id, index}` |
| `run_now` | cmd | `{job_id}` → `{ok, job_id}` |
| `remove_from_queue` | cmd | `{job_id}` → `{ok, job_id}` |
| `schedule_job` | cmd | `{job_id, when, tz, missed_policy}` → `{ok, job_id}` |
| `unschedule_job` | cmd | `{job_id}` → `{ok, job_id}` |
| `pause_job` | cmd | `{}` → `{ok, job_id, paused}` |
| `resume_job` | cmd | `{job_id}` → `{ok, job_id, started}` |
| `restart_job` | cmd | `{job_id}` → `{ok, job_id, started}` |
| `retry_stage` | cmd | `{job_id, stage}` → `{ok, job_id, stage, started}` |
| `set_job_group` | cmd | `{job_id, group}` → `{ok, job_id, group}` |
| `set_jobs_group` | cmd | `{ids, group}` → `{ok, count, group}` |
| `rename_job` | cmd | `{job_id, title}` → `{ok, job_id, title, job}` |
| `queue_changed` | evt | `{event, active, queue, schedules}` |
| `job_deleted` | evt | `{event, ok, id, freed, method, bulk, count, ids, failed}` |
| `pause_state` | evt | `{event, state, job}` |

### Feature Group 2 — Paste link / yt-dlp

| Operation | Direction | Request / event fields |
| --- | --- | --- |
| `media_link_support` | cmd | `{}` → `{ok, available, version}` |
| `probe_media_url` | cmd | `{url}` → `{ok, title, duration, uploader, extractor, is_live, webpage_url, error}` |
| `import_media_url` | cmd | `{url, title}` → `{ok, job_id, path, name, cancelled, error}` |
| `cancel_media_url` | cmd | `{}` → `{ok, cancelled}` |
| `media_link_state` | evt | `{event, available, version}` |
| `media_probe` | evt | `{event, ok, title, duration, uploader, extractor, is_live, webpage_url, error}` |
| `media_progress` | evt | `{event, status, pct, downloaded, total, speed, eta}` |
| `media_done` | evt | `{event, ok, path, name, cancelled, error}` |

### Feature Group 3 — Settings and processing options

| Operation | Direction | Request / event fields |
| --- | --- | --- |
| `browse_model` | cmd | `{}` → `{ok, path}` (Electron main opens dialog) |
| `test_endpoint` | cmd | `{}` → `{ok, available, label, model, error}` |
| `get_settings` | cmd | `{}` → `{ok, settings}` |
| `settings_changed` | evt | `{event, job, key, value, applied}` |

### Feature Group 4 — Study and AI backends

| Operation | Direction | Request / event fields |
| --- | --- | --- |
| `ask_ai` | cmd | `{prompt}` → `{ok, job_id}` |
| `generate_quiz` | cmd | `{count, difficulty, type, scope}` → `{ok, job_id}` |
| `cancel_quiz` | cmd | `{}` → `{ok, cancelled}` |
| `save_quiz_session` | cmd | `{session}` → `{ok, job_id, saved}` |
| `generate_flashcards` | cmd | `{count, difficulty, style, scope}` → `{ok, job_id}` |
| `cancel_flashcards` | cmd | `{}` → `{ok, cancelled}` |
| `save_flashcard_session` | cmd | `{session}` → `{ok, job_id, saved}` |
| `save_notes` | cmd | `{text}` → `{ok, job_id, saved}` |
| `smart_study_status` | cmd | `{}` → `{ok}` |
| `set_study_preset` | cmd | `{preset}` → `{ok, preset, model}` |
| `install_smart_study` | cmd | `{preset}` → `{ok, preset}` |
| `cancel_smart_study` | cmd | `{}` → `{ok, cancelled}` |
| `launch_ollama_installer` | cmd | `{}` → `{ok}` |
| `list_ollama_models` | cmd | `{}` → `{ok, models, selected, available, error}` |
| `set_groq_key` | cmd | `{key}` → `{ok, stored}` (key never logged) |
| `remove_groq_key` | cmd | `{}` → `{ok, removed}` |
| `test_groq_key` | cmd | `{}` → `{ok, valid, message}` |
| `ai_token` | evt | `{event, text}` |
| `ai_done` | evt | `{event}` |
| `ai_status` | evt | `{event, label, model}` |
| `quiz_changed` | evt | `{event, questions, provider, model, meta, session}` |
| `quiz_status` | evt | `{event, state, message}` |
| `flashcards_changed` | evt | `{event, cards, provider, model, meta, session}` |
| `flashcards_status` | evt | `{event, state, message}` |
| `smart_study` | evt | `{event, state, message, percent, ram_gb, recommendation, presets, preset, model, enabled, ready, ollama, installed_models, provider}` |
| `ollama_models` | evt | `{event, models, selected, available, error}` |
| `groq_status` | evt | `{event, has_key, testing, backend, message}` |
| `study_changed` | evt | `{event, topics, topicBlocks, topicLabels, keyTerms, summary, summarySource, bookmarks, stats, cards, notes}` |

### Feature Group 5 — Runtime, GPU, diagnostics, repair, storage

| Operation | Direction | Request / event fields |
| --- | --- | --- |
| `run_diagnostics` | cmd | `{job_id}` → `{ok, job_id}` |
| `validate_vulkan` | cmd | `{}` → `{ok, state, available, selected, reason, requested, resolved_backend, resolved_label, benchmark_ok, exe}` |
| `validate_cuda` | cmd | `{}` → `{ok, state, available, selected, reason, requested, resolved_backend, resolved_label, benchmark_ok, exe}` |
| `cuda_pack_status` | cmd | `{}` → `{ok, state, gpu_present, installed, size_label}` |
| `install_cuda_pack` | cmd | `{}` → `{ok, started}` (explicit frontend command required) |
| `cancel_cuda_pack` | cmd | `{}` → `{ok, cancelled}` |
| `get_notification_prefs` | cmd | `{}` → `{ok, prefs}` |
| `set_notification_prefs` | cmd | `{prefs}` → `{ok, prefs}` |
| `test_notification` | cmd | `{}` → `{ok, sent}` |
| `repair_selection` | cmd | `{}` → `{ok, job_id, started}` |
| `diagnostics` | evt | `{event, bundle, job_id, type}` |
| `vulkan_status` | evt | `{event, state, message, available, selected, reason, requested, resolved_backend, resolved_label, benchmark_ok, exe}` |
| `cuda_status` | evt | `{event, state, message, available, selected, reason, requested, resolved_backend, resolved_label, benchmark_ok, exe}` |
| `cuda_pack` | evt | `{event, state, message, percent, gpu_present, installed, size_label}` |
| `notification_prefs` | evt | `{event, prefs}` |
| `repair_event` | evt | `{event, operation_id, kind, detail}` |
| `storage_changed` | evt | `{event, total, used, free, percent}` |

### Feature Group 6 — Backend notifications and events

| Operation | Direction | Event fields |
| --- | --- | --- |
| `job_queued` | evt | `{event, job_id, position}` |
| `job_started` | evt | `{event, job_id}` |
| `job_failed` | evt | `{event, job_id, stage, error}` |
| `job_cancelled` | evt | `{event, job_id}` |
| `download_progress` | evt | `{event, job_id, pct, downloaded, total, speed, eta}` |
| `export_progress` | evt | `{event, job, pct, label}` |
| `study_progress` | evt | `{event, job_id, kind, pct, message}` |
| `runtime_missing` | evt | `{event, component, detail}` |
| `repair_required` | evt | `{event, operation_id, detail}` |
| `storage_warning` | evt | `{event, total, used, free, percent, message}` |

---

## PHASE 8 IMPLEMENTATION CHECKLIST

Status values: `IMPLEMENTED` · `PARTIAL` · `MISSING` · `DEFERRED`.

### Implemented core operations (34)

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


### Reconciled core operations (4)

| Bridge operation | Frontend consumer | Connect here |
| --- | --- | --- |
| `bootstrap_complete` (event) | `app/ui/app.js` subscribes via `lpBridge.on('bootstrap_complete', …)`. | `electron-spike/python-sidecar.py` emits the completion payload after the ready/bootstrap progress records. `electron-bridge.js` forwards it unchanged. |
| `set_slide_state` (command) | `app/ui/app.js` calls `lpBridge.call('set_slide_state', index, state)` to accept/reject a slide. | `electron-bridge.js` maps the call; `python-sidecar.py` persists the existing `candidates.json` decision and emits refreshed `slides_changed`. |
| `save_corrections` (command) | `app/ui/app.js` calls `lpBridge.call('save_corrections', texts_json)` to persist transcript edits. | `electron-bridge.js` maps the JSON array; `python-sidecar.py` persists the existing working transcript layer and `edited.json` mirror. |
| `export_progress` (event) | `app/ui/app.js` subscribes via `lpBridge.on('export_progress', …)`. | `python-sidecar.py` emits `{event, job, pct, label}` during and at the end of Export. |

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
| Runtime readiness | `lpBridge.call('get_bootstrap')`, `bridge.js` `backend.ui_ready()` | `get_bootstrap`, `ui_ready` slots; `bootstrap_progress`, `bootstrap_complete`, `ui_ready_signal` signals | `health_check` (cmd); `ready`, `bootstrap_progress`, `bootstrap_complete` (evt) | `{}` | `{healthy, paths, qt_application}`; `{event:ready, engine_loaded}`; `{bootstrap_pending, runtime_health_state, setup_acknowledged}` | `PARTIAL` | core | `get_bootstrap`/`ui_ready` remain intercepted noops; readiness is driven by sidecar bootstrap and the Electron host health/list/restore sequence. |
| Engine import progress | `lpBridge.on('bootstrap_progress')` | `bootstrap_progress` signal | `bootstrap_progress` (evt) | — | `{event, id, state, detail}` | `IMPLEMENTED` | core | Emitted while the engine loads. |
| Bootstrap completion | `lpBridge.on('bootstrap_complete')` | `bootstrap_complete` signal | `bootstrap_complete` (evt) | — | `{event, bootstrap_pending, runtime_health_state, setup_acknowledged}` | `IMPLEMENTED` | core | Emitted after the sidecar reports ready and bootstrap progress. |

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
| Accept/reject slide | `lpBridge.call('set_slide_state', index, state)` | `set_slide_state` slot | `set_slide_state` (cmd); `slides_changed` (evt) | `{index, state}` | `{job_id, index, state, applied}` | `IMPLEMENTED` | core | Persists the candidate decision in the existing job format. |
| Load transcript | `open_job` path / host restore; `lpBridge.on('transcript_changed')` | `transcript_changed` signal | `get_transcript` (cmd); `transcript_changed` (evt) | `{job_id}` | `{job_id, transcript}`; `{event, job, reviewSegments, transcript}` | `IMPLEMENTED` | core | |
| Save transcript edits | `lpBridge.call('save_corrections', texts_json)` | `save_corrections` slot | `save_corrections` (cmd); `transcript_changed` (evt) | `{texts}` | `{job_id, saved, changed}` | `IMPLEMENTED` | core | Persists the working layer and legacy `edited.json` mirror; raw transcript remains unchanged. |

### exports

| Feature | Frontend caller | Old Qt method/signal | Electron command/event | Request payload | Response/event payload | Status | Phase 8 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Export | `lpBridge.call('export_all'/'export_one')` | `export_all`, `export_one` slots; `export_done` signal | `export` (cmd); `export_done` (evt) | `{job_id}` | `{job_id, started, already_running}`; `{event:export_done}` | `IMPLEMENTED` | core | Both frontend calls map to `export`. |
| Export progress | `lpBridge.on('export_progress')` | `export_progress` signal | `export_progress` (evt) | — | `{event, job, pct, label}` | `IMPLEMENTED` | core | Emitted from Export stage progress and at 100% completion. |
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
   `save_corrections`** were the four Phase 8 core gaps identified by the
   contract commit; all four are now implemented in the production seam.
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
