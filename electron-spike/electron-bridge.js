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
    media_link_support: true,
    list_ollama_models: true,
    smart_study_status: true,
    get_bootstrap: true,
    get_settings: true,
    ui_ready: true,
    delete_jobs: true,
    delete_job: true,
    set_jobs_group: true,
    set_job_group: true,
    pause_job: true,
    start_demo_job: false,
    end_demo_job: false
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
    return name === 'set_setting' && args[0] === 'theme';
  }

  function settingValue(name, args) {
    if (name !== 'set_setting') return undefined;
    return args[1];
  }

  function processingMode(value) {
    var normalized = String(value || 'study').toLowerCase();
    return normalized === 'transcript' || normalized === 'slides' ? normalized : 'study';
  }

  function mapCall(name, args) {
    var first = args[0];
    var payload = {};
    if (first && typeof first === 'object') payload = first;
    else if (typeof first === 'string' && first.charAt(0) === '{') payload = parse(first);

    if (name === 'start_processing' || name === 'start_job') {
      var jobId = payload.job_id || '';
      if (name === 'start_job' && typeof first === 'string' && first.charAt(0) !== '{') jobId = first;
      return {
        command: 'start_job',
        payload: {
          job_id: jobId,
          auto_export: payload.auto_export !== false,
          mode: name === 'start_processing' ? processingMode(first) : payload.mode,
          preset: payload.preset || bridgeSettings.slide_detection_preset
        }
      };
    }
    if (name === 'resume_job' || name === 'restart_job') {
      return { command: 'start_job', payload: { job_id: first || '', auto_export: true } };
    }
    if (name === 'open_job') return { command: 'get_job', payload: { job_id: first || '' } };
    if (name === 'open_job_folder' || name === 'open_export_folder') {
      return { command: name, payload: { job_id: payload.job_id || (typeof first === 'string' ? first : '') } };
    }
    if (name === 'set_slide_state') {
      var slideIndex = payload.index != null ? payload.index : first;
      var slideState = payload.state || args[1] || '';
      return {
        command: 'set_slide_state',
        payload: {
          job_id: payload.job_id || '',
          index: Number(slideIndex),
          state: String(slideState)
        }
      };
    }
    if (name === 'save_corrections') {
      var texts = Array.isArray(payload.texts) ? payload.texts : first;
      if (typeof texts === 'string') texts = parse(texts);
      return {
        command: 'save_corrections',
        payload: {
          job_id: payload.job_id || '',
          texts: Array.isArray(texts) ? texts : []
        }
      };
    }
    if (name === 'export_all' || name === 'export_one') return { command: 'export', payload: (payload.job_id ? { job_id: payload.job_id } : {}) };
    if (name === 'import_video') return { command: 'import_video', payload: payload };
    if (name === 'get_job' || name === 'get_slides' || name === 'get_transcript' || name === 'cancel_job') {
      return { command: name, payload: { job_id: payload.job_id || (typeof first === 'string' ? first : '') } };
    }
    if (name === 'list_jobs' || name === 'health_check' || name === 'shutdown' || name === 'export') {
      return { command: name, payload: payload };
    }
    if (name === 'set_setting') {
      var setting = String(args[0] || '');
      if (setting === 'slide_detection_preset') {
        bridgeSettings.slide_detection_preset = String(settingValue(name, args) || 'balanced');
      }
      return { command: 'set_setting', payload: { key: setting, value: settingValue(name, args) } };
    }
    if (name === 'start_demo_job') return { command: 'start_job', payload: { job_id: '', auto_export: true, demo: true } };
    if (name === 'end_demo_job') return { command: 'cancel_job', payload: {} };
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
          window.localStorage.setItem('lecturepack.electron.theme', String(args[1] || ''));
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
