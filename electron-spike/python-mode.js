'use strict';

(function () {
  var bridge = window.lpBridge;
  var job = 'renderer-spike-python';
  var metrics = { mode: 'python', ready: false, pings: 0, errors: [] };

  function emit(name, payload) {
    if (!bridge || typeof bridge.emit !== 'function') {
      metrics.errors.push('lpBridge.emit is unavailable');
      return;
    }
    try { bridge.emit(name, JSON.stringify(payload)); }
    catch (error) { metrics.errors.push(name + ': ' + error.message); }
  }

  function badge(text, color) {
    var el = document.getElementById('renderer-spike-badge');
    if (!el) {
      el = document.createElement('div');
      el.id = 'renderer-spike-badge';
      el.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:250;padding:7px 10px;border:1px solid ' + color + ';border-radius:8px;background:var(--panel);color:var(--ink);font:700 10px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;box-shadow:var(--shadow-soft);pointer-events:none';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.borderColor = color;
  }

  function onSidecar(message) {
    if (!message || typeof message !== 'object') return;
    if (message.event === 'ready') {
      metrics.ready = message.engine_loaded === true;
      var label = metrics.ready ? 'PYTHON SIDECAR · ENGINE IMPORTED' : 'PYTHON SIDECAR · ENGINE IMPORT FAILED';
      badge(label, metrics.ready ? '#67C587' : '#D65A5A');
      emit('jobs_changed', [{ name: 'renderer-spike-python', file: 'stdio-sidecar', status: metrics.ready ? 'done' : 'failed', meta: message.controller || 'LecturePack engine import' }]);
      emit('pipeline_changed', {
        job: job,
        title: metrics.ready ? 'Python engine connected' : 'Python engine unavailable',
        meta: message.controller || message.error || 'sidecar handshake',
        stages: [
          { label: 'Electron renderer', state: 'done' },
          { label: 'Python stdio sidecar', state: metrics.ready ? 'done' : 'active', pct: metrics.ready ? 100 : 0, color: 'orange' },
          { label: 'LecturePack engine import', state: metrics.ready ? 'done' : 'active', pct: metrics.ready ? 100 : 0, color: 'blue' }
        ],
        log: []
      });
      emit('status_changed', { job: job, label: metrics.ready ? 'Connected' : 'Engine error', pct: metrics.ready ? 100 : 0, detail: message.error || 'local stdio handshake complete' });
      emit('log_line', { tag: '[python]', color: metrics.ready ? 'var(--green)' : 'var(--red)', text: message.error || (message.controller + ' imported successfully') });
      return;
    }
    if (message.event === 'pong') {
      metrics.pings += 1;
      badge((metrics.ready ? 'PYTHON SIDECAR · LIVE' : 'PYTHON SIDECAR · NOT READY') + ' · ping ' + metrics.pings, metrics.ready ? '#67C587' : '#D65A5A');
      return;
    }
    if (message.event === 'error') {
      metrics.errors.push(message.error || 'sidecar error');
      badge('PYTHON SIDECAR · ERROR', '#D65A5A');
      return;
    }
    if (message.event === 'exit') badge('PYTHON SIDECAR · EXITED', '#D65A5A');
  }

  window.__LECTUREPACK_SPIKE__ = { mode: 'python', metrics: metrics, onSidecar: onSidecar };
  badge('PYTHON SIDECAR · WAITING', '#FF8652');
}());
