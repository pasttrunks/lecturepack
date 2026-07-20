/* LecturePack bridge — connects the UI to the Python backend over QWebChannel.
   In a plain browser (design preview / development) there is no backend:
   every call resolves to null and the UI falls back to its built-in demo behavior. */

window.lpBridge = (function () {
  var backend = null;
  var readyCbs = [];
  var listeners = {};   // signal name -> [fn]

  function fire(name /*, ...args */) {
    var args = Array.prototype.slice.call(arguments, 1);
    (listeners[name] || []).forEach(function (fn) {
      try { fn.apply(null, args); } catch (e) { console.error('lpBridge listener', name, e); }
    });
  }

  // Qt signal names exposed by desktop/bridge.py — keep the two lists in sync.
  var SIGNALS = [
    'jobs_changed', 'pipeline_changed', 'log_line', 'status_changed',
    'slides_changed', 'transcript_changed', 'study_changed',
    'export_progress', 'export_done',
    'ai_token', 'ai_done', 'ai_status', 'onboarding',
    'update_available', 'update_progress', 'update_ready', 'update_error', 'whatsnew',
    'settings_changed', 'ollama_models'
  ];

  function connectQt() {
    if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined' || !qt.webChannelTransport) {
      // Browser mode — no backend.
      readyCbs.forEach(function (cb) { cb(null); });
      readyCbs = null;
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      backend = channel.objects.backend;
      SIGNALS.forEach(function (name) {
        if (backend[name] && backend[name].connect) {
          backend[name].connect(function () { fire.apply(null, [name].concat(Array.prototype.slice.call(arguments))); });
        }
      });
      readyCbs.forEach(function (cb) { cb(backend); });
      readyCbs = null;
      if (backend.ui_ready) backend.ui_ready();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connectQt);
  } else {
    connectQt();
  }

  return {
    /** cb(backendOrNull) — called once the QWebChannel handshake settles. */
    ready: function (cb) { if (readyCbs === null) { cb(backend); } else { readyCbs.push(cb); } },
    /** True when running inside the desktop shell with a live backend. */
    connected: function () { return backend !== null; },
    /** Subscribe to a backend signal by name. */
    on: function (name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    /** Invoke a backend slot; resolves with its return value, or null in browser mode. */
    call: function (name /*, ...args */) {
      var args = Array.prototype.slice.call(arguments, 1);
      return new Promise(function (resolve) {
        if (!backend || !backend[name]) { resolve(null); return; }
        args.push(function (result) { resolve(result); });
        backend[name].apply(backend, args);
      });
    }
  };
})();
