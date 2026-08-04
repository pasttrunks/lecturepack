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
    // Commands remain inert only while the locked contract marks them
    // DEFERRED. Implemented operations are mapped below and cross JSONL.
    acknowledge_setup: true,
    browse_model: true,
    cancel_cuda_pack: true,
    cancel_update_download: true,
    check_updates: true,
    clear_skipped_version: true,
    cuda_pack_status: true,
    end_demo_job: true,
    exit_application: true,
    get_notification_prefs: true,
    get_post_completion: true,
    get_updater_state: true,
    install_cuda_pack: true,
    install_downloaded_update: true,
    install_update: true,
    log_tour_trace: true,
    repair_selection: true,
    run_diagnostics: true,
    save_project: true,
    set_auto_check: true,
    set_notification_prefs: true,
    set_update_channel: true,
    skip_update_version: true,
    start_demo_job: true,
    start_update_download: true,
    test_notification: true,
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

  function stringPayload(value) {
    return typeof value === 'string' ? value : String(value == null ? '' : value);
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
    if (event === 'ai_token') return String(item.text || '');
    var payload = Object.assign({}, item);
    delete payload.event;
    return payload;
  }

  function deliver(message) {
    var item = message || {};
    if (typeof item === 'string') item = parse(item);
    var event = item.event;
    if (!event || event === 'response') return;
    var payload = eventPayload(event, item);
    // The historical UI treats ai_token as a text signal; every other event
    // keeps the JSON-string payload shape expected by app/ui/app.js.
    fire(event, event === 'ai_token' ? payload : json(payload));
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

    if (name === 'ask_ai') {
      return { command: name, payload: { prompt: stringPayload(first) } };
    }
    if (name === 'generate_quiz') {
      return {
        command: name,
        payload: {
          count: payload.count,
          difficulty: payload.difficulty,
          type: payload.type,
          scope: payload.scope
        }
      };
    }
    if (name === 'cancel_quiz') return { command: name, payload: {} };
    if (name === 'save_quiz_session') {
      return { command: name, payload: { session: payload } };
    }
    if (name === 'generate_flashcards') {
      return {
        command: name,
        payload: {
          count: payload.count,
          difficulty: payload.difficulty,
          style: payload.style,
          scope: payload.scope
        }
      };
    }
    if (name === 'cancel_flashcards') return { command: name, payload: {} };
    if (name === 'save_flashcard_session') {
      return { command: name, payload: { session: payload } };
    }
    if (name === 'save_notes') {
      return { command: name, payload: { text: stringPayload(first) } };
    }
    if (name === 'smart_study_status' || name === 'cancel_smart_study' ||
        name === 'launch_ollama_installer' || name === 'list_ollama_models' ||
        name === 'remove_groq_key' || name === 'test_groq_key' ||
        name === 'test_endpoint') {
      return { command: name, payload: {} };
    }
    if (name === 'set_study_preset' || name === 'install_smart_study') {
      return { command: name, payload: { preset: stringPayload(first) } };
    }
    if (name === 'set_groq_key') {
      return { command: name, payload: { key: stringPayload(first) } };
    }

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
    if (name === 'probe_media_url') {
      return { command: name, payload: { url: String(typeof first === 'string' ? first : payload.url || '') } };
    }
    if (name === 'import_media_url') {
      return {
        command: name,
        payload: { url: String(typeof first === 'string' ? first : payload.url || ''), title: String(args[1] || payload.title || '') }
      };
    }
    if (name === 'cancel_media_url' || name === 'media_link_support') {
      return { command: name, payload: {} };
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
