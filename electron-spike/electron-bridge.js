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
    // Commands reached by visible controls resolve to a structured
    // FEATURE_UNAVAILABLE response in call(), never a silent null.
    acknowledge_setup: true,
    browse_model: true,
    cancel_update_download: true,
    clear_skipped_version: true,
    exit_application: true,
    get_post_completion: true,
    get_updater_state: true,
    install_downloaded_update: true,
    install_update: true,
    log_tour_trace: true,
    open_release_page: true,
    save_project: true,
    set_auto_check: true,
    set_update_channel: true,
    skip_update_version: true,
    start_update_download: true,
    whatsnew_seen: true,
    // Bootstrap is host-driven in the production app. These legacy calls
    // stay acknowledged locally as specified by the partial contract.
    get_bootstrap: true,
    ui_ready: true,
  };
  var unavailableMessages = {
    acknowledge_setup: 'First-run setup is already complete in this build.',
    browse_model: 'Model browsing is not available in this build.',
    cancel_update_download: 'Updates are not available in this build.',
    clear_skipped_version: 'Updates are not available in this build.',
    exit_application: 'Close the window to exit LecturePack.',
    get_post_completion: 'Post-completion coaching is not available in this build.',
    get_updater_state: 'Updates are not available in this build.',
    install_downloaded_update: 'Updates are not available in this build.',
    install_update: 'Updates are not available in this build.',
    log_tour_trace: 'Guided tour tracing is not available in this build.',
    open_release_page: 'Release notes are not available in this build.',
    save_project: 'Saving is automatic in this build.',
    set_auto_check: 'Updates are not available in this build.',
    set_update_channel: 'Updates are not available in this build.',
    skip_update_version: 'Updates are not available in this build.',
    start_update_download: 'Updates are not available in this build.',
    whatsnew_seen: 'What\'s new is not available in this build.',
    get_bootstrap: 'Bootstrap is host-driven in this build.',
    ui_ready: 'UI readiness is acknowledged in this build.'
  };
  function featureUnavailable(name) {
    return {
      ok: false,
      available: false,
      code: 'FEATURE_UNAVAILABLE',
      message: unavailableMessages[name] || 'This feature is not available in this build.',
      command: name
    };
  }
  var bridgeSettings = {
    slide_detection_preset: 'balanced'
  };
  // D-2: the active guided-demo identity. The bridge translates the normal
  // pipeline lifecycle into demo_event signals so the guided tour can advance
  // without a separate fake demo pipeline.
  var demoSession = null;

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

  var PACKAGED_REPAIR_UNAVAILABLE = 'The bundled LecturePack runtime cannot be repaired in place. Reinstall the current LecturePack package and try again.';

  function repairUnavailable(operationId) {
    return Promise.resolve(json({
      type: 'repair_unavailable',
      operation_id: String(operationId || ''),
      message: PACKAGED_REPAIR_UNAVAILABLE
    }));
  }

  function bootstrapFromHealth(result) {
    var paths = result && result.paths && typeof result.paths === 'object' ? result.paths : {};
    var missing = Object.keys(paths).filter(function (name) {
      return !paths[name] || paths[name].exists !== true;
    });
    var healthy = !!(result && result.healthy === true && missing.length === 0);
    return {
      bootstrap_pending: false,
      runtime_health_state: healthy ? 'HEALTHY' : 'SETUP_REQUIRED',
      setup_acknowledged: false,
      healthy: healthy,
      engine_loaded: !!(result && result.engine_loaded),
      validation_path: 'light',
      failed_components: missing.map(function (name) {
        return { component: name, friendly_name: name + ' is missing' };
      }),
      diagnostics: result && result.error ? String(result.error) : ''
    };
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

  function demoEvent(payload) {
    if (!demoSession) return;
    fire('demo_event', json(Object.assign({
      operation_id: demoSession.operationId,
      session_id: demoSession.sessionId
    }, payload)));
  }

  function deliver(message) {
    var item = message || {};
    if (typeof item === 'string') item = parse(item);
    var event = item.event;
    if (!event || event === 'response') return;
    var payload = eventPayload(event, item);
    // D-2: translate the normal pipeline lifecycle into demo_event signals so
    // the guided tour can advance without a separate fake demo pipeline.
    if (demoSession) {
      if (event === 'pipeline_changed') {
        var stages = payload.stages || [];
        var reviewReady = stages.some(function (stage) {
          return stage && stage.label === 'Review Ready' && stage.state === 'done';
        });
        if (reviewReady) {
          demoEvent({ status: 'running', stage: 'review_ready' });
        } else if (stages.some(function (stage) {
          return stage && (stage.state === 'active' || stage.state === 'running');
        })) {
          demoEvent({ status: 'running', stage: 'processing' });
        }
      } else if (event === 'job_completed') {
        demoEvent({ status: 'cleaned', stage: 'exports' });
      } else if (event === 'job_failed') {
        demoEvent({ status: 'failed', error: String(payload.error || 'Guided demo failed.') });
      } else if (event === 'job_cancelled') {
        demoEvent({ status: 'cleaned', stage: 'ended' });
      }
    }
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
      return { command: name, payload: {
        prompt: stringPayload(Object.prototype.hasOwnProperty.call(payload, 'prompt')
          ? payload.prompt : first)
      } };
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
    if (name === 'run_diagnostics') {
      return { command: name, payload: { job_id: jobIdPayload(first) } };
    }
    if (name === 'set_notification_prefs') {
      return { command: name, payload: { prefs: objectPayload(first) } };
    }
    if (name === 'repair_selection' || name === 'get_notification_prefs' ||
        name === 'test_notification' || name === 'validate_vulkan' ||
        name === 'validate_cuda' || name === 'cuda_pack_status' ||
        name === 'install_cuda_pack' || name === 'cancel_cuda_pack') {
      return { command: name, payload: {} };
    }

    if (name === 'start_demo_job') {
      // D-2: the demo uses the bundled demo video through the normal
      // video-import path. The sidecar resolves the bundled demo when
      // bundled_demo is true and no path is supplied.
      return { command: 'import_video', payload: { bundled_demo: true } };
    }
    if (name === 'end_demo_job') {
      return { command: 'cancel_job', payload: {} };
    }
    if (name === 'start_processing') {
      return {
        command: 'start_job',
        payload: {
          auto_export: payload.auto_export !== false,
          mode: processingMode(typeof first === 'string' ? first : payload.mode),
          preset: payload.preset || bridgeSettings.slide_detection_preset,
          job_id: typeof first === 'string' ? '' : String(payload.job_id || '')
        }
      };
    }
    if (name === 'probe_media_url') {
      return {
        command: name,
        payload: Array.isArray(payload.urls)
          ? { urls: payload.urls.map(String) }
          : { url: String(typeof first === 'string' ? first : payload.url || '') }
      };
    }
    if (name === 'import_media_url') {
      return {
        command: name,
        payload: Array.isArray(payload.items)
          ? { items: payload.items }
          : { url: String(typeof first === 'string' ? first : payload.url || ''), title: String(args[1] || payload.title || '') }
      };
    }
    if (name === 'cancel_media_url') {
      var cancelId = String(payload.download_id || first || '');
      return { command: name, payload: cancelId ? { download_id: cancelId } : {} };
    }
    if (name === 'remove_media_download' || name === 'retry_media_download') {
      return { command: name, payload: { download_id: String(payload.download_id || first || '') } };
    }
    if (name === 'clear_media_downloads' || name === 'get_media_downloads' || name === 'media_link_support') {
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
    if (name === 'view_job') return { command: 'view_job', payload: { job_id: jobIdPayload(first) } };
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
    if (name === 'import_videos') {
      // Batch import: several native paths already resolved by the renderer.
      return { command: 'import_videos', payload: { paths: Array.isArray(payload.paths) ? payload.paths : [] } };
    }
    if (name === 'apply_job_settings') {
      return {
        command: 'apply_job_settings',
        payload: {
          job_ids: Array.isArray(payload.job_ids) ? payload.job_ids : [],
          mode: payload.mode,
          preset: payload.preset
        }
      };
    }
    if (name === 'queue_jobs') {
      return { command: 'queue_jobs', payload: { job_ids: Array.isArray(payload.job_ids) ? payload.job_ids : [] } };
    }
    if (name === 'search_transcripts') {
      return { command: 'search_transcripts', payload: { query: String(payload.query || ''), limit: payload.limit } };
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
    // The packaged sidecar owns a fixed, verified runtime. It can re-assess
    // that runtime through health_check, but it deliberately has no deferred
    // in-place download/repair operation. Keep the historical UI methods
    // total so a missing runtime produces a recovery message, not a renderer
    // TypeError or a call to an unsupported sidecar command.
    beginRuntimeRepairOffer: function (operationId) { return repairUnavailable(operationId); },
    confirmRuntimeRepair: function (operationId) { return repairUnavailable(operationId); },
    cancelRuntimeRepair: function (operationId) {
      return Promise.resolve(json({ type: 'cancelled', operation_id: String(operationId || '') }));
    },
    retryRuntimeAssessment: function () {
      return window.lpBridge.call('health_check').then(function (result) {
        var bootstrap = bootstrapFromHealth(result);
        fire('bootstrap_complete', json(bootstrap));
        return json(bootstrap);
      });
    },
    on: function (name, callback) {
      (listeners[name] = listeners[name] || []).push(callback);
    },
    emit: function (name) {
      fire.apply(null, arguments);
    },
    call: function (name) {
      var args = Array.prototype.slice.call(arguments, 1);
      if (!api) return Promise.resolve(featureUnavailable(name));
      if (name === 'check_updates') {
        // D-6: updates are not available in this build. Resolve immediately
        // with a structured result and clear the UI's "Checking…" state.
        var updateResult = featureUnavailable('check_updates');
        fire('update_state', json({
          phase: 'uptodate',
          message: updateResult.message
        }));
        return Promise.resolve(updateResult);
      }
      if (noopCalls[name]) {
        // Internal bootstrap calls stay acknowledged locally; visible-control
        // commands get a structured unavailable response, never a silent null.
        if (name === 'get_bootstrap' || name === 'ui_ready') return Promise.resolve(null);
        return Promise.resolve(featureUnavailable(name));
      }
      if (isLocalThemeSetting(name, args)) {
        // Theme application is already local in app/ui/app.js. Persist the
        // choice in the renderer when possible, but never turn a UI toggle
        // into a sidecar request that the migration contract does not need.
        try {
          window.localStorage.setItem('lecturepack.electron.theme', String(settingValue(name, args) || ''));
        } catch (_) { /* private/file contexts may deny localStorage */ }
        return Promise.resolve({ ok: true, local: true });
      }
      if (name === 'test_notification') {
        // D-15: route to the Electron main process where Luna's
        // testDesktopNotification() creates the OS notification. The Python
        // sidecar never creates desktop notifications.
        return api.request('test_notification', {}).catch(function (error) {
          return { ok: false, sent: false, available: false, error: String(error && error.message || error) };
        });
      }
      var mapped = mapCall(name, args);
      return api.request(mapped.command, mapped.payload).catch(function (error) {
        fire('error', json({ command: mapped.command, error: String(error && error.message || error) }));
        return featureUnavailable(name);
      });
    },
    startDemoJob: function () {
      // D-2: the demo uses the bundled demo video through the normal
      // import_video path. The guided-demo UI expects a start result with
      // operation_id/session_id and a live demo_event so it can adopt the
      // identity. Derive those from the imported job and start processing.
      var self = this;
      return self.call('start_demo_job').then(function (value) {
        var result = parse(value);
        if (!result || result.ok !== true || !result.job_id) {
          return { ok: false, error: (result && result.error) || 'Could not start the guided demo.' };
        }
        var operationId = 'demo-' + result.job_id;
        var sessionId = 'session-' + result.job_id;
        demoSession = { operationId: operationId, sessionId: sessionId, jobId: result.job_id };
        fire('demo_event', json({
          operation_id: operationId,
          session_id: sessionId,
          status: 'started',
          stage: 'import'
        }));
        // Start the normal processing pipeline for the imported demo. A
        // failure must propagate so the guided-demo UI can show an error
        // instead of a false success.
        return self.call('start_processing', 'study').then(function (started) {
          var startedResult = parse(started);
          if (!startedResult || startedResult.ok !== true) {
            demoSession = null;
            return { ok: false, error: (startedResult && startedResult.error) || 'Could not start processing the guided demo.' };
          }
          return {
            ok: true,
            operation_id: operationId,
            session_id: sessionId,
            job_id: result.job_id
          };
        }, function (error) {
          demoSession = null;
          return { ok: false, error: String(error && error.message || error) || 'Could not start processing the guided demo.' };
        });
      });
    },
    endDemoJob: function (reason) {
      // D-2: the demo end maps to cancel_job; the guided-demo UI expects a
      // terminal status so it can settle the session.
      var self = this;
      return self.call('end_demo_job', reason || 'ended').then(function (value) {
        var result = parse(value);
        if (!result || result.ok !== true) {
          return { ok: false, error: (result && result.error) || 'Could not confirm that the demo stopped. Try again.' };
        }
        demoSession = null;
        return { ok: true, status: 'cleaned' };
      });
    }
  };

  window.__LECTUREPACK_ELECTRON__ = {
    onSidecar: deliver
  };
}());
