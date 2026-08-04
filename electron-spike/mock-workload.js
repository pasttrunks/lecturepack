'use strict';

(function () {
  var bridge = window.lpBridge;
  var timers = [];
  var metrics = {
    mode: 'mock',
    logs: 0,
    pipelineUpdates: 0,
    slideUpdates: 0,
    transcriptUpdates: 0,
    demoEvents: 0,
    bootstrapEvents: 0,
    errors: []
  };

  function remember(timer) {
    timers.push(timer);
    return timer;
  }

  function emit(name, payload) {
    if (!bridge || typeof bridge.emit !== 'function') {
      metrics.errors.push('lpBridge.emit is unavailable');
      return;
    }
    try {
      bridge.emit(name, JSON.stringify(payload));
    } catch (error) {
      metrics.errors.push(name + ': ' + error.message);
    }
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

  function stagePayload(pct) {
    var stage = pct < 18 ? 0 : pct < 58 ? 1 : pct < 82 ? 2 : 3;
    var labels = ['Inspect', 'Extract audio', 'Transcribe', 'Detect slides', 'Align', 'Review ready', 'Export'];
    return labels.map(function (label, index) {
      if (index < stage) return { label: label, state: 'done' };
      if (index === stage) return { label: label, state: 'active', pct: Math.max(1, Math.round(pct)), color: index % 2 ? 'blue' : 'orange' };
      return { label: label, state: 'pending' };
    });
  }

  var job = 'renderer-spike-mock';
  var slides = Array.from({ length: 14 }, function (_, index) {
    return {
      pct: Math.round((index + 1) * 6.5 * 10) / 10,
      time: '00:0' + Math.min(9, index) + ':' + String((index * 7) % 60).padStart(2, '0'),
      state: index === 0 ? 'rejected' : 'accepted',
      sel: index === 2 || index === 3,
      frame: (index + 1) * 300
    };
  });
  var reviewSegments = [
    { t: '00:42.7', text: 'The renderer spike is exercising the real LecturePack frontend.' },
    { t: '00:47.2', text: 'This segment is updated while the mocked pipeline is running.', hot: true },
    { t: '00:51.2', text: 'No transcript or slide bytes are being sent to a network service.' },
    { t: '00:55.2', text: 'The workload stays inside the Electron renderer process.' }
  ];
  var transcriptBlocks = [
    { t: '00:42', hotTime: true, html: 'The <strong style="box-shadow:inset 0 -.5em 0 var(--yellow-soft)">mocked frontend</strong> is receiving the same signal-shaped payloads as the desktop bridge.' },
    { t: '00:55', html: 'Five hundred log messages, progress updates, slide changes, and transcript changes are deliberately delivered under resize pressure.' },
    { t: '01:12', html: 'The affected laptop, not this development computer, decides whether the renderer remains stable.' }
  ];

  window.__LECTUREPACK_SPIKE__ = {
    mode: 'mock',
    metrics: metrics,
    stop: function () {
      timers.forEach(function (timer) { clearInterval(timer); clearTimeout(timer); });
      timers = [];
    }
  };

  if (!bridge) {
    metrics.errors.push('lpBridge is unavailable');
    badge('MOCKED FRONTEND · BRIDGE MISSING', '#D65A5A');
    return;
  }

  badge('MOCKED FRONTEND · 0/500 LOGS', '#FF8652');

  emit('jobs_changed', [{ name: 'renderer-spike-mock', file: 'renderer-spike.mock', status: 'running', pct: 0, stage: 'Inspect' }]);
  emit('pipeline_changed', {
    job: job,
    title: 'Renderer workload',
    meta: 'Electron · mocked bridge · 0%',
    stages: stagePayload(0),
    log: []
  });
  metrics.pipelineUpdates += 1;
  emit('slides_changed', { job: job, slides: slides, duration: '06:12', durationMid: '03:06' });
  metrics.slideUpdates += 1;
  emit('transcript_changed', {
    job: job,
    reviewSegments: reviewSegments,
    transcript: { title: 'Renderer spike workload', duration: '06:12', segments: 98, corrections: 0, blocks: transcriptBlocks }
  });
  metrics.transcriptUpdates += 1;

  ['windows_version', 'data_directory', 'ffmpeg_ffprobe', 'whisper_runtime', 'bundled_model'].forEach(function (id, index) {
    remember(setTimeout(function () {
      emit('bootstrap_progress', { id: id, state: 'checking', detail: 'Electron mock check' });
      metrics.bootstrapEvents += 1;
      remember(setTimeout(function () {
        emit('bootstrap_progress', { id: id, state: 'resolved', detail: 'mocked locally' });
        metrics.bootstrapEvents += 1;
      }, 90 + index * 20));
    }, index * 55));
  });
  remember(setTimeout(function () {
    emit('bootstrap_complete', {
      version: 'renderer-spike',
      runtime_health_state: 'HEALTHY',
      setup_acknowledged: true,
      acknowledged: true,
      healthy: true,
      bootstrap_pending: false
    });
    metrics.bootstrapEvents += 1;
  }, 520));

  var logIndex = 0;
  var logTimer = remember(setInterval(function () {
    if (logIndex >= 500) {
      clearInterval(logTimer);
      return;
    }
    var stage = logIndex < 80 ? 'inspect' : logIndex < 160 ? 'transcribe' : logIndex < 360 ? 'detect' : 'align';
    emit('log_line', {
      tag: '[' + stage + ']',
      color: stage === 'detect' ? 'var(--blue-ink)' : stage === 'transcribe' ? 'var(--orange-ink)' : 'var(--muted)',
      text: 'mock line ' + String(logIndex + 1).padStart(3, '0') + ' · renderer workload · no external process'
    });
    logIndex += 1;
    metrics.logs = logIndex;
    badge('MOCKED FRONTEND · ' + logIndex + '/500 LOGS', '#FF8652');
  }, 8));

  var pct = 0;
  remember(setInterval(function () {
    pct = Math.min(100, pct + 2);
    emit('pipeline_changed', {
      job: job,
      title: pct >= 100 ? 'Renderer workload complete' : 'Renderer workload',
      meta: 'Electron · mocked bridge · ' + pct + '%',
      stages: pct >= 100 ? stagePayload(100).map(function (stage) { return { label: stage.label, state: 'done' }; }) : stagePayload(pct),
      log: []
    });
    emit('status_changed', {
      job: job,
      label: pct >= 100 ? 'Done' : 'Processing',
      pct: pct,
      detail: pct >= 100 ? 'mock workload complete' : pct + '% · mocked renderer workload',
      side: pct >= 100 ? 'Done' : 'Processing ' + pct + '%'
    });
    metrics.pipelineUpdates += 1;
    if (pct >= 100) badge('MOCKED FRONTEND · COMPLETE · ' + metrics.logs + '/500 LOGS', '#67C587');
  }, 250));

  var slideTick = 0;
  remember(setInterval(function () {
    slideTick += 1;
    var index = slideTick % slides.length;
    slides[index].state = slides[index].state === 'accepted' ? 'viewing' : 'accepted';
    slides[index].sel = !slides[index].sel;
    emit('slides_changed', { job: job, slides: slides, duration: '06:12', durationMid: '03:06' });
    metrics.slideUpdates += 1;
  }, 650));

  var transcriptTick = 0;
  remember(setInterval(function () {
    transcriptTick += 1;
    reviewSegments[1].text = 'Live transcript update ' + transcriptTick + ' · renderer workload remains local.';
    transcriptBlocks[1].html = 'Live block <strong style="box-shadow:inset 0 -.5em 0 var(--blue-soft)">' + transcriptTick + '</strong> is replacing text in place.';
    emit('transcript_changed', {
      job: job,
      reviewSegments: reviewSegments,
      transcript: { title: 'Renderer spike workload', duration: '06:12', segments: 98 + transcriptTick, corrections: 0, blocks: transcriptBlocks }
    });
    metrics.transcriptUpdates += 1;
  }, 850));

  // The guided demo requires an admitted runtime in the real app. This local
  // override provides only the same narrow result contract so its transition
  // reducer can be exercised without QWebChannel or Python.
  var demoOperation = 'renderer-spike-demo-operation';
  var demoSession = 'renderer-spike-demo-session';
  bridge.connected = function () { return true; };
  bridge.startDemoJob = function () {
    emit('demo_event', { operation: 'guided_demo', operation_id: demoOperation, session_id: demoSession, status: 'started', stage: 'prepare', progress: 0 });
    metrics.demoEvents += 1;
    return Promise.resolve({ ok: true, operation_id: demoOperation, session_id: demoSession });
  };
  bridge.endDemoJob = function () {
    emit('demo_event', { operation: 'guided_demo', operation_id: demoOperation, session_id: demoSession, status: 'cleaned', stage: 'complete', progress: 100 });
    metrics.demoEvents += 1;
    return Promise.resolve({ ok: true, operation_id: demoOperation, session_id: demoSession, status: 'cleaned' });
  };
  remember(setTimeout(function () {
    var card = document.getElementById('glowing-demo-card');
    if (card) card.click();
  }, 1050));
  [
    { delay: 2200, status: 'running', stage: 'extract_audio', progress: 24 },
    { delay: 3400, status: 'running', stage: 'transcribe', progress: 58 },
    { delay: 4700, status: 'running', stage: 'review_ready', progress: 100 },
    { delay: 6200, status: 'cleaned', stage: 'complete', progress: 100 }
  ].forEach(function (step) {
    remember(setTimeout(function () {
      emit('demo_event', { operation: 'guided_demo', operation_id: demoOperation, session_id: demoSession, status: step.status, stage: step.stage, progress: step.progress });
      metrics.demoEvents += 1;
      if (step.stage === 'review_ready') {
        var keep = document.getElementById('btn-keep');
        if (keep) keep.click();
      }
    }, step.delay));
  });
}());
