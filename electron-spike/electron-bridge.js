/* Renderer-facing adapter for the real Electron migration slice.
 *
 * The existing app/ui code speaks the historical lpBridge signal/slot shape.
 * This file keeps that UI source unchanged and maps its small set of actions
 * to the request-id JSONL sidecar contract through the context-isolated
 * preload API. It never exposes Node or Electron primitives to app.js.
 */
(function () {
  'use strict';

  var api = window.lecturePackElectron;
  var listeners = {};
  var noopCalls = {
    // These commands remain deliberately inert until DeepSeek's backend
    // parity commits change their contract status from DEFERRED.
    acknowledge_setup: true,
    ask_ai: true,
    browse_model: true,
    cancel_cuda_pack: true,
    cancel_flashcards: true,
    cancel_media_url: true,
    cancel_quiz: true,
    cancel_smart_study: true,
    cancel_update_download: true,
    check_updates: true,
    clear_skipped_version: true,
    cuda_pack_status: true,
    delete_job: true,
    delete_jobs: true,
    end_demo_job: true,
    enqueue_job: true,
    exit_application: true,
    generate_flashcards: true,
    generate_quiz: true,
    get_notification_prefs: true,
    get_post_completion: true,
    get_settings: true,
    get_updater_state: true,
    import_media_url: true,
    install_cuda_pack: true,
    install_downloaded_update: true,
    install_smart_study: true,
    install_update: true,
    launch_ollama_installer: true,
    list_ollama_models: true,
    log_tour_trace: true,
    media_link_support: true,
    pause_job: true,
    probe_media_url: true,
    remove_from_queue: true,
    remove_groq_key: true,
    reorder_queue: true,
    repair_selection: true,
    restart_job: true,
    resume_job: true,
    retry_stage: true,
    run_diagnostics: true,
    run_now: true,
    save_flashcard_session: true,
    save_notes: true,
    save_project: true,
    save_quiz_session: true,
    schedule_job: true,
    set_auto_check: true,
    set_groq_key: true,
    set_job_group: true,
    set_jobs_group: true,
    set_notification_prefs: true,
    set_study_preset: true,
    set_update_channel: true,
    skip_update_version: true,
    smart_study_status: true,
    start_demo_job: true,
    start_update_download: true,
    test_endpoint: true,
    test_groq_key: true,
    test_notification: true,
    unschedule_job: true,
    validate_cuda: true,
    validate_vulkan: true,
    whatsnew_seen: true,
    // Bootstrap is host-driven in the production app. These legacy calls
    // stay acknowledged locally as specified by the partial contract.
    get_bootstrap: true,
    ui_ready: true,
  };
  var bridgeSettings = {
    slide_detection_preset: 'balanced'
  };

  function fire(name) {
    var args = Array.prototype.slice.call(arguments, 1);
    (listeners[name] || []).forEach(function (fn) {
      try { fn.apply(null, args); } catch (error) { console.error('electron bridge listener', name, error); }
    });
  }

  function json(value) {
    return JSON.stringify(value == null ? {} : value);
  }

  function parse(value) {
    if (value && typeof value === 'object') return value;
    try { return JSON.parse(value || '{}'); } catch (_) { return {}; }
  }

  function objectPayload(value) {
    var parsed = parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  }

  function arrayPayload(value) {
    var parsed = parse(value);
    return Array.isArray(parsed) ? parsed : [];
  }

  function jobIdPayload(value) {
    var parsed = objectPayload(value);
    return String(parsed.job_id || (typeof value === 'string' ? value : '') || '');
  }

  function eventPayload(event, item) {
    // app/ui/app.js parses jobs_changed directly and immediately calls
    // forEach on it. Keep the migration envelope internal to the transport;
    // the renderer-facing signal must receive the historical array shape.
    if (event === 'jobs_changed') {
      if (Array.isArray(item)) return item;
      if (Array.isArray(item.jobs)) return item.jobs;
      if (Array.isArray(item.payload)) return item.payload;
      return [];
    }
    var payload = Object.assign({}, item);
    delete payload.event;
    return payload;
  }

  function deliver(message) {
    var item = message || {};
    if (typeof item === 'string') item = parse(item);
    var event = item.event;
    if (!event || event === 'response') return;
    fire(event, json(eventPayload(event, item)));
  }

  function isLocalThemeSetting(name, args) {
    return name === 'set_setting' && (
      objectPayload(args[0]).key === 'theme' || args[0] === 'theme'
    );
  }

  function settingValue(name, args) {
    if (name !== 'set_setting') return undefined;
    var payload = objectPayload(args[0]);
    return Object.prototype.hasOwnProperty.call(payload, 'value') ? payload.value : args[1];
  }

  function processingMode(value) {
    var normalized = String(value || 'study').toLowerCase();
    return normalized === 'transcript' || normalized === 'slides' ? normalized : 'study';
  }

  function mapCall(name, args) {
    var first = args[0];
    var payload = objectPayload(first);

    if (name === 'start_processing') {
      return {
        command: 'start_job',
        payload: {
          auto_export: payload.auto_export !== false,
          mode: processingMode(typeof first === 'string' ? first : payload.mode),
          preset: payload.preset || bridgeSettings.slide_detection_preset
        }
      };
    }
    if (name === 'delete_job') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'delete_jobs') {
      return { command: name, payload: { ids: arrayPayload(first) } };
    }
    if (name === 'enqueue_job' || name === 'run_now' || name === 'remove_from_queue' || name === 'unschedule_job') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'reorder_queue') {
      return { command: name, payload: { job_id: jobIdPayload(first), index: Number(args[1]) } };
    }
    if (name === 'schedule_job') {
      return {
        command: name,
        payload: {
          job_id: jobIdPayload(first),
          when: String(args[1] || ''),
          tz: String(args[2] || 'local'),
          missed_policy: String(args[3] || 'run_when_opened')
        }
      };
    }
    if (name === 'pause_job') return { command: name, payload: {} };
    if (name === 'resume_job' || name === 'restart_job') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'retry_stage') {
      return { command: name, payload: { job_id: jobIdPayload(first), stage: String(args[1] || '') } };
    }
    if (name === 'set_job_group') {
      return { command: name, payload: { job_id: jobIdPayload(first), group: String(args[1] || '') } };
    }
    if (name === 'set_jobs_group') {
      return { command: name, payload: { ids: arrayPayload(first), group: String(args[1] || '') } };
    }
    if (name === 'rename_job') {
      return { command: name, payload: { job_id: jobIdPayload(first), title: String(args[1] || '') } };
    }
    if (name === 'open_job') return { command: 'get_job', payload: { job_id: jobIdPayload(first) } };
    if (name === 'open_job_folder' || name === 'open_export_folder') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'set_slide_state') {
      var slideIndex = payload.index != null ? payload.index : first;
      var slideState = payload.state || args[1] || '';
      return {
        command: 'set_slide_state',
        payload: {
          index: Number(slideIndex),
          state: String(slideState)
        }
      };
    }
    if (name === 'save_corrections') {
      var texts = Array.isArray(payload.texts) ? payload.texts : first;
      if (typeof texts === 'string') texts = arrayPayload(texts);
      return {
        command: 'save_corrections',
        payload: {
          texts: Array.isArray(texts) ? texts : []
        }
      };
    }
    if (name === 'export_all' || name === 'export_one') return { command: 'export', payload: {} };
    if (name === 'import_video') {
      return {
        command: 'import_video',
        payload: {
          path: String(payload.path || ''),
          title: payload.title,
          preset: payload.preset,
          bundled_demo: payload.bundled_demo
        }
      };
    }
    if (name === 'get_job' || name === 'get_slides' || name === 'get_transcript' || name === 'cancel_job') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'list_jobs' || name === 'health_check' || name === 'shutdown' || name === 'export') {
      return {
        command: name,
        payload: name === 'export' ? { job_id: jobIdPayload(first) } : {}
      };
    }
    if (name === 'set_setting') {
      var setting = String(payload.key || args[0] || '');
      if (setting === 'slide_detection_preset') {
        bridgeSettings.slide_detection_preset = String(settingValue(name, args) || 'balanced');
      }
      return { command: 'set_setting', payload: { key: setting, value: settingValue(name, args) } };
    }
    return { command: name, payload: payload };
  }

  if (api && api.onMessage) {
    api.onMessage(deliver);
  }

  window.lpBridge = {
    ready: function (callback) {
      setTimeout(function () { callback({}); }, 0);
    },
    connected: function () { return !!api; },
    pathForFile: function (file) {
      if (!file) return '';
      try {
        if (api && api.getPathForFile) return api.getPathForFile(file) || '';
      } catch (error) {
        console.warn('electron bridge file path', error);
      }
      return typeof file.path === 'string' ? file.path : '';
    },
    on: function (name, callback) {
      (listeners[name] = listeners[name] || []).push(callback);
    },
    emit: function (name) {
      fire.apply(null, arguments);
    },
    call: function (name) {
      var args = Array.prototype.slice.call(arguments, 1);
      if (!api || noopCalls[name]) return Promise.resolve(null);
      if (isLocalThemeSetting(name, args)) {
        // Theme application is already local in app/ui/app.js. Persist the
        // choice in the renderer when possible, but never turn a UI toggle
        // into a sidecar request that the migration contract does not need.
        try {
          window.localStorage.setItem('lecturepack.electron.theme', String(settingValue(name, args) || ''));
        } catch (_) { /* private/file contexts may deny localStorage */ }
        return Promise.resolve({ ok: true, local: true });
      }
      var mapped = mapCall(name, args);
      return api.request(mapped.command, mapped.payload).catch(function (error) {
        fire('error', json({ command: mapped.command, error: String(error && error.message || error) }));
        return null;
      });
    },
    startDemoJob: function () { return this.call('start_demo_job'); },
    endDemoJob: function (reason) { return this.call('end_demo_job', reason || 'ended'); }
  };

  window.__LECTUREPACK_ELECTRON__ = {
    onSidecar: deliver
  };
}());
