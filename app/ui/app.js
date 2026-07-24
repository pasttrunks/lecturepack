/* LecturePack app logic — ported 1:1 from the Claude Design prototype (LecturePack.dc.html).
   State model, keyboard shortcuts, focus mode, timeline scrub, study tabs, chat streaming,
   quiz, flashcards, import flow and export state machine all match the prototype.
   Data flows through LP.data; the Python backend replaces the demo payloads via lpBridge. */

(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  var THUMB_SVG = '<svg width="{S}" height="{S}" viewBox="0 0 24 24" fill="none" stroke="{C}" stroke-width="1.6"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>';
  function thumb(size, color) { return THUMB_SVG.replace(/\{S\}/g, size).replace('{C}', color); }

  // Slide image with graceful fallback: on load error the <img> hides and its
  // placeholder sibling (the frame-icon) is revealed, so a missing file shows
  // an explicit marker rather than a silent blank box.
  function slideImg(url, imgStyle, phSize, phColor) {
    if (!url) { return thumb(phSize, phColor); }
    var ph = '<span class="lp-img-ph" style="display:none;flex-direction:column;align-items:center;gap:4px">' +
      thumb(phSize, phColor) + '</span>';
    return '<img src="' + esc(url) + '" style="' + imgStyle + '" ' +
      'onerror="this.style.display=\'none\';var p=this.parentNode.querySelector(\'.lp-img-ph\');if(p)p.style.display=\'flex\'">' + ph;
  }
  var CHECK_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  /* ======================= demo data (design content) ======================= */
  var LP = window.LP = {
    state: {
      screen: 'home', theme: 'dark', focus: false, onb: null, jobsEmpty: false,
      exportPhase: 'idle', studyTab: 'chat',
      chat: [
        { role: 'user', text: 'How did they align it to north without a compass?' },
        { role: 'ai', text: 'They watched a star rise and set, then bisected the angle between the two points — that line runs true north. The transcript covers this at 01:12. Want a quick quiz on it?' }
      ],
      streaming: false,
      quiz: {
        phase: 'setup', index: 0, pick: null, answers: {}, flags: {},
        autoAdvance: false, generating: false, status: '',
        settings: { count: 5, difficulty: 'Mixed', type: 'Multiple choice', scope: 'Entire lecture', source: 'Transcript' }
      },
      flash: {
        phase: 'setup', index: 0, flipped: false, known: {}, unsure: {}, bookmarks: {},
        order: [], generating: false, status: '',
        settings: { count: 10, difficulty: 'Basic', style: 'Term → definition', scope: 'Entire lecture' }
      },
      viewingSlide: 2,
      updateInfo: null,
      smartStudy: null,   // last smart_study payload
      ssPreset: null,     // user-chosen preset (defaults to recommendation)
      ssDismissed: false  // user chose "Continue with Built-in Study"
    },
    data: {
      version: '0.0.0',
      jobs: [
        { name: 'egypt_excerpt', file: 'egypt_excerpt.m4v', meta: '06:12 · 14 slides · Jul 16', status: 'done' },
        { name: 'm2-res_1080p', status: 'running', pct: 62, stage: 'Transcribe', eta: '~3m' },
        { name: 'synthetic_lecture', file: 'synthetic_lecture.mp4', meta: '00:30 · 3 slides · Jul 15', status: 'done' }
      ],
      pipeline: {
        title: 'Transcribing…', meta: 'elapsed 00:41 · 62%',
        stages: [
          { label: 'Inspect', state: 'done' },
          { label: 'Extract audio', state: 'done' },
          { label: 'Transcribe', state: 'active', pct: 62, color: 'orange' },
          { label: 'Detect slides', state: 'active', pct: 38, color: 'blue' },
          { label: 'Align', state: 'pending' },
          { label: 'Review ready', state: 'pending' },
          { label: 'Export', state: 'pending' }
        ],
        log: [
          { tag: '[extract]', color: 'var(--green)', text: 'audio → 16kHz mono · done in 2.1s' },
          { tag: '[whisper]', color: 'var(--orange-ink)', text: 'ggml-base.en · 8 threads · streaming…' },
          { tag: '[t]', color: 'var(--ink)', text: '00:00:42.720 → 00:00:47.240 great pyramid originally rose more than 146 meters' },
          { tag: '[t]', color: 'var(--ink)', text: '00:00:47.240 → 00:00:51.240 million stone blocks but the start of any construction…' },
          { tag: '[detect]', color: 'var(--blue-ink)', text: 'keyframe candidate @ 00:00:56 · ssim 0.71' },
          { tag: '[t]', color: 'var(--ink)', text: '00:00:51.240 → 00:00:55.220 the foundation which is impressive in its own right' }
        ]
      },
      slides: [
        { pct: 0.5, time: '00:00:02', state: 'rejected' },
        { pct: 9.7, time: '00:00:36', state: 'accepted' },
        { pct: 11.6, time: '00:00:43', state: 'accepted', sel: true, frame: 1305 },
        { pct: 15, time: '00:00:56', state: 'accepted', sel: true },
        { pct: 27, time: '00:01:41', state: 'accepted' },
        { pct: 36, time: '00:02:13', state: 'accepted' },
        { pct: 39, time: '00:02:26', state: 'accepted' },
        { pct: 46, time: '00:02:52', state: 'accepted' },
        { pct: 51, time: '00:03:11', state: 'rejected' },
        { pct: 57, time: '00:03:32', state: 'accepted' },
        { pct: 64, time: '00:04:10', state: 'accepted' },
        { pct: 72, time: '00:04:48', state: 'accepted' },
        { pct: 81, time: '00:05:24', state: 'accepted' },
        { pct: 93, time: '00:06:02', state: 'accepted' }
      ],
      duration: '06:12', durationMid: '03:06',
      reviewSegments: [
        { t: '00:42.7', text: 'great pyramid originally rose more than 146 meters tall contained about 2.3' },
        { t: '00:47.2', text: 'million stone blocks but the start of any construction project truly begins with', hot: true },
        { t: '00:51.2', text: 'the foundation which is impressive in its own right. Its base is level less than' },
        { t: '00:55.2', text: 'two centimeters, its square within 11 and its edges are aligned to the compass' },
        { t: '00:59.7', text: 'within 3/60 of a degree. This position is pretty incredible since' }
      ],
      transcript: {
        title: 'The Great Pyramid of Giza', duration: '06:12', segments: 98, corrections: 4,
        blocks: [
          { t: '00:42', hotTime: true, html: 'The great pyramid originally rose more than <strong style="box-shadow:inset 0 -.5em 0 var(--yellow-soft)">146 meters</strong> tall and contained about 2.3 million stone blocks. But the start of any construction project truly begins with the foundation — which is impressive in its own right.' },
          { t: '00:55', html: 'Its base is level to less than two centimeters, it\'s square within eleven centimeters, and its edges are aligned to the compass within 3/60 of a degree. This position is pretty incredible since <strong style="box-shadow:inset 0 -.5em 0 var(--blue-soft)">compasses</strong> didn\'t actually exist yet.' },
          { t: '01:12', html: 'Finding north is actually pretty easy — just watch where any star rises and sets during the night, and cut the angle in half. After that, squaring the sides just requires measuring a right angle.' },
          { t: '01:25', html: '<strong style="box-shadow:inset 0 -.5em 0 var(--yellow-soft)">Pythagoras</strong> and his equation came way later, but ancient cultures like the Egyptians knew a 3-4-5 triangle made a 90 degree angle.' }
        ]
      },
      quiz: { questions: [], provider: '', model: '', meta: {} },
      flashcards: { cards: [], provider: '', model: '', meta: {} },
      study: {
        topics: [
          { t: '00:01', title: 'Welcome & overview', active: true },
          { t: '00:36', title: 'Building the foundation' },
          { t: '01:12', title: 'Finding true north' },
          { t: '02:26', title: 'Moving the stones' }
        ],
        topicBlocks: [
          { left: 0.5, width: 16, active: true },
          { left: 18, width: 22 },
          { left: 42, width: 24 },
          { left: 68, width: 31 }
        ],
        topicLabels: ['Welcome', 'Foundation', 'True north', 'Stones'],
        keyTerms: ['Khufu', 'Giza', 'foundation', 'true north', '3-4-5 triangle', 'Pythagoras'],
        bookmarks: [
          { t: '00:00:56', text: 'Revisit the pyramid–star alignment method', color: 'var(--orange)' },
          { t: '00:01:25', text: '3-4-5 triangle → right angle', color: 'var(--blue)' }
        ],
        stats: [ ['Slides', '14 kept'], ['Segments', '98'], ['Time read', '12m'] ],
        cards: [
          { q: 'How level is the pyramid’s base?', a: 'Level to less than two centimeters across its entire footprint.' },
          { q: 'How did builders find true north?', a: 'Watch a star rise and set, then bisect the angle between those points.' },
          { q: 'What made a right angle before Pythagoras?', a: 'A 3-4-5 triangle — known to the Egyptians for a 90° corner.' }
        ]
      },
      exportFormats: [
        { key: 'TXT', sel: true }, { key: 'SRT', sel: true }, { key: 'VTT', sel: false }, { key: 'MD', sel: true },
        { key: 'JSON', sel: false }, { key: 'CSV', sel: false }, { key: 'DOCX', sel: false }, { key: 'TSV', sel: false }
      ],
      exportFiles: ['slides.pdf', 'study_pack.html', 'transcript.txt', 'transcript.srt', 'transcript.md']
    }
  };

  /* ======================= renderers ======================= */

  /* ---- lightweight modal + toast (no markup needed) ---- */
  function lpModal(opts) {
    var ov = document.createElement('div');
    ov.className = 'lp-modal-ov';
    ov.style.cssText = 'position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45);animation:lpin .15s ease';
    var box = document.createElement('div');
    box.style.cssText = 'background:var(--panel);border:2px solid var(--border);border-radius:14px;box-shadow:var(--shadow-hi);padding:22px 24px;max-width:430px;width:90%';
    box.innerHTML = '<div style="font:700 17px \'Space Grotesk\';margin-bottom:10px">' + esc(opts.title) + '</div>' +
      '<div style="font-size:14px;line-height:1.55;margin-bottom:18px">' + (opts.bodyHtml || '') + '</div>';
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;justify-content:flex-end;gap:10px';
    function close() { ov.remove(); document.removeEventListener('keydown', onKey); }
    (opts.actions || []).forEach(function (a) {
      var b = document.createElement('button');
      b.textContent = a.label;
      var base = 'font:600 13px \'Space Grotesk\';border-radius:9px;padding:9px 16px;cursor:pointer;border:2px solid var(--border)';
      b.style.cssText = a.danger ? base + ';background:var(--red);color:#fff;border-color:var(--red)'
        : a.primary ? base + ';background:var(--orange);color:#fff;border-color:var(--orange-ink)'
          : base + ';background:var(--panel);color:var(--ink)';
      b.addEventListener('click', function () { if (!(a.onClick && a.onClick())) close(); });
      row.appendChild(b);
    });
    box.appendChild(row); ov.appendChild(box); document.body.appendChild(ov);
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) close(); });
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);
    return { close: close };
  }
  var _toastT = null;
  function toast(msg) {
    var t = $('lp-toast');
    if (!t) {
      t = document.createElement('div'); t.id = 'lp-toast';
      t.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:130;background:var(--ink);color:var(--bg);font:600 13px \'Space Grotesk\';padding:10px 18px;border-radius:10px;box-shadow:var(--shadow-hi);opacity:0;transition:opacity .2s';
      document.body.appendChild(t);
    }
    t.textContent = msg; t.style.opacity = '1';
    if (_toastT) clearTimeout(_toastT);
    _toastT = setTimeout(function () { t.style.opacity = '0'; }, 2600);
  }
  function copyText(text, okMsg) {
    text = text || '';
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); toast(okMsg || 'Copied'); }
      catch (e) { toast('Copy failed'); }
      ta.remove();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(okMsg || 'Copied'); }, fallback);
    } else { fallback(); }
  }

  var TRASH_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>';
  var TAG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="0.5" fill="currentColor"/></svg>';

  function _jobBtn(action, id, svg, title) {
    return '<button class="lp-jobbtn" data-action="' + action + '" data-jobid="' + esc(id) + '" title="' + title + '" style="width:27px;height:27px;border-radius:7px;border:1.5px solid var(--border);background:var(--panel);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:var(--shadow-soft)">' + svg + '</button>';
  }

  // status -> badge {label, bg, fg, dot, blink}
  var JOB_BADGES = {
    running: { label: 'Running', bg: 'var(--orange-soft)', fg: 'var(--orange-ink)', dot: 'var(--orange)', blink: true },
    done: { label: 'Done', bg: 'var(--green-soft)', fg: 'var(--green)', dot: 'var(--green)' },
    interrupted: { label: 'Interrupted', bg: 'var(--orange-soft)', fg: 'var(--orange-ink)', dot: 'var(--orange)' },
    failed: { label: 'Failed', bg: 'var(--red-soft, rgba(220,60,60,.15))', fg: 'var(--red)', dot: 'var(--red)' },
    paused: { label: 'Paused', bg: 'var(--blue-tint)', fg: 'var(--blue-ink)', dot: 'var(--blue-ink)' },
    queued: { label: 'Queued', bg: 'var(--sunk)', fg: 'var(--muted)', dot: 'var(--muted)' },
    scheduled: { label: 'Scheduled', bg: 'var(--sunk)', fg: 'var(--muted)', dot: 'var(--muted)' }
  };
  function _jobActBtn(act, id, label, primary) {
    var s = primary
      ? 'background:var(--secondary-surface);border:1.5px solid var(--secondary-border);color:var(--secondary-text)'
      : 'background:var(--panel);border:1.5px solid var(--border);color:var(--ink)';
    return '<button class="lp-hit" data-jobact="' + act + '" data-jobid="' + esc(id) + '" style="font:600 11px \'Space Grotesk\';border-radius:7px;padding:6px 11px;cursor:pointer;' + s + '">' + label + '</button>';
  }
  function _jobCardHtml(j) {
    var b = JOB_BADGES[j.status] || JOB_BADGES.done;
    var dot = '<span style="width:6px;height:6px;border-radius:50%;background:' + b.dot + (b.blink ? ';animation:lpblink 1s infinite' : '') + '"></span>';
    var badge = '<span style="position:absolute;top:9px;right:9px;display:flex;align-items:center;gap:5px;font:600 10px \'JetBrains Mono\';text-transform:uppercase;background:' + b.bg + ';color:' + b.fg + ';border-radius:6px;padding:3px 8px">' + dot + b.label + '</span>';
    var menu = j.id ? '<div style="position:absolute;top:9px;left:9px;display:flex;gap:6px">' +
      _jobBtn('group', j.id, TAG_SVG, 'Set group') + _jobBtn('delete', j.id, TRASH_SVG, 'Delete') + '</div>' : '';
    var body;
    if (j.status === 'running') {
      body = '<div style="font-weight:700;font-size:16px;margin-bottom:9px">' + esc(j.name) + '</div>' +
        '<div style="height:8px;border-radius:5px;background:var(--sunk);overflow:hidden;margin-bottom:7px"><div style="width:' + (j.pct || 0) + '%;height:100%;background:var(--orange);background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.3) 6px,rgba(255,255,255,.3) 13px);animation:lpbar 1s linear infinite"></div></div>' +
        '<div style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + esc(j.stage) + ' · ' + (j.pct || 0) + '% · ' + esc(j.eta || '') + '</div>';
    } else {
      body = '<div style="font-weight:700;font-size:16px;margin-bottom:5px">' + esc(j.name) + '</div>' +
        '<div style="font:500 11px \'JetBrains Mono\';color:var(--muted);line-height:1.7">' + esc(j.file || '') + '<br>' + esc(j.meta || '') + '</div>';
    }
    // Needs-Attention actions for interrupted/failed jobs.
    if (j.id && (j.status === 'interrupted' || j.status === 'failed')) {
      body += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:11px">' +
        _jobActBtn('resume', j.id, 'Resume', true) +
        _jobActBtn('restart', j.id, 'Restart') +
        _jobActBtn('view', j.id, 'View Details') +
        _jobActBtn('remove', j.id, 'Remove') + '</div>';
    }
    return '<div class="lp-card" ' + (j.id ? 'data-job="' + esc(j.id) + '" ' : '') + 'style="background:var(--panel);border:2px solid var(--border);border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;cursor:pointer">' +
      '<div style="height:118px;background:var(--sunk);border-bottom:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;position:relative">' + thumb(30, 'var(--muted)') + menu + badge + '</div>' +
      '<div style="padding:14px 16px">' + body + '</div></div>';
  }

  function confirmDeleteJob(job) {
    lpModal({
      title: 'Delete this lecture?',
      bodyHtml: '<strong>' + esc(job.name) + '</strong> will be moved to the Recycle Bin and removed from LecturePack, freeing disk space. Its export files are removed too.',
      actions: [{ label: 'Cancel' }, { label: 'Delete', danger: true, onClick: function () { if (lpBridge.connected()) lpBridge.call('delete_job', job.id); else toast('Preview mode — not deleted'); } }]
    });
  }
  function setJobGroup(job) {
    lpModal({
      title: 'Group lecture',
      bodyHtml: '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px">Course / subject</label>' +
        '<input id="lp-group-input" type="text" spellcheck="false" value="' + esc(job.group || '') + '" placeholder="e.g. CL100" style="width:100%;box-sizing:border-box;font:600 14px \'JetBrains Mono\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">' +
        '<div style="font-size:12px;color:var(--muted);margin-top:8px">Leave blank to auto-group by the lecture title.</div>',
      actions: [{ label: 'Cancel' }, { label: 'Save', primary: true, onClick: function () { var i = $('lp-group-input'); if (lpBridge.connected()) lpBridge.call('set_job_group', job.id, (i && i.value || '').trim()); } }]
    });
    setTimeout(function () { var i = $('lp-group-input'); if (i) { i.focus(); i.select(); } }, 30);
  }

  function _jobName(id) {
    var j = (LP.data.jobs || []).filter(function (x) { return x.id === id; })[0];
    return j ? j.name : id;
  }
  function renderQueue() {
    var wrap = $('home-queue'), list = $('queue-list');
    if (!wrap || !list) return;
    var q = (LP.data.queue && LP.data.queue.queue) || [];
    if (!q.length) { wrap.hidden = true; list.innerHTML = ''; return; }
    wrap.hidden = false;
    var cnt = $('queue-count'); if (cnt) cnt.textContent = q.length + (q.length === 1 ? ' job' : ' jobs');
    list.innerHTML = q.map(function (row, i) {
      var qbtn = function (act, label, disabled) {
        return '<button class="lp-hit" data-queueact="' + act + '" data-queueid="' + esc(row.id) + '"' +
          (disabled ? ' disabled style="opacity:.4;' : ' style="') +
          'font:600 11px \'Space Grotesk\';border-radius:7px;padding:6px 10px;cursor:pointer;background:var(--panel);border:1.5px solid var(--border);color:var(--ink)">' + label + '</button>';
      };
      return '<div style="display:flex;align-items:center;gap:12px;background:var(--panel);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px">' +
        '<span style="font:700 12px \'JetBrains Mono\';color:var(--muted);min-width:20px">' + (i + 1) + '</span>' +
        '<span style="flex:1;font-weight:600;font-size:13.5px">' + esc(_jobName(row.id)) + '</span>' +
        '<div style="display:flex;gap:6px">' +
          qbtn('runnow', 'Run Now') + qbtn('up', '↑', i === 0) +
          qbtn('down', '↓', i === q.length - 1) + qbtn('remove', 'Remove') +
        '</div></div>';
    }).join('');
  }
  function renderJobs() {
    var g = $('jobs-grid');
    g.style.display = 'flex'; g.style.flexDirection = 'column'; g.style.gap = '26px';
    g.style.gridTemplateColumns = 'none';
    var groups = {}, order = [];
    LP.data.jobs.forEach(function (j) {
      var k = j.group || 'Ungrouped';
      if (!groups[k]) { groups[k] = []; order.push(k); }
      groups[k].push(j);
    });
    order.sort(function (a, b) { return String(a).localeCompare(String(b)); });
    var single = order.length <= 1;
    g.innerHTML = order.map(function (k) {
      var cards = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px">' +
        groups[k].map(_jobCardHtml).join('') + '</div>';
      var header = single ? '' :
        '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:12px"><span style="font:700 14px \'Space Grotesk\'">' + esc(k) + '</span><span style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + groups[k].length + '</span></div>';
      return '<div>' + header + cards + '</div>';
    }).join('');
    $('jobs-count').textContent = LP.data.jobs.length;
  }

  function renderPipeline() {
    var p = LP.data.pipeline;
    $('proc-status-title').textContent = p.title;
    $('proc-status-meta').textContent = p.meta;
    $('pipeline-stages').innerHTML = p.stages.map(function (st) {
      if (st.state === 'done') {
        return '<div style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:600;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;background:var(--green);border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--green-soft);overflow:hidden"><div style="width:100%;height:100%;background:var(--green)"></div></div></div>';
      }
      if (st.state === 'active') {
        var c = st.color === 'blue' ? 'var(--blue)' : 'var(--orange)';
        var pctColor = st.color === 'blue' ? ';color:var(--blue-ink)' : '';
        var blink = st.color === 'blue' ? '1.3s' : '1s';
        return '<div style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid ' + c + ';border-radius:50%;flex:none;animation:lpblink ' + blink + ' infinite"></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk);overflow:hidden"><div style="width:' + (st.pct || 0) + '%;height:100%;background:' + c + ';background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.32) 6px,rgba(255,255,255,.32) 13px);animation:lpbar 1s linear infinite"></div></div><span style="width:38px;text-align:right;font:700 11px \'JetBrains Mono\'' + pctColor + '">' + (st.pct || 0) + '%</span></div>';
      }
      return '<div style="display:flex;align-items:center;gap:13px;opacity:.45"><span style="width:120px;flex:none;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid var(--muted);border-radius:50%;flex:none"></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk)"></div></div>';
    }).join('');
    var logEl = $('proc-log');
    var stick = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 8;
    logEl.innerHTML = p.log.map(function (l) {
      return '<div><span style="color:' + l.color + '">' + esc(l.tag) + '</span> ' + esc(l.text) + '</div>';
    }).join('');
    if (stick) logEl.scrollTop = logEl.scrollHeight;
  }

  // Main slide preview: fills the canvas at Fit (preserving aspect ratio) and
  // supports zoom/pan. Uses the full-resolution candidate image (cur.img), NOT
  // the small thumbnail box. scale is natural-pixel -> CSS-pixel (100% = 1:1).
  var previewCtl = (function () {
    var ZMIN = 0.25, ZMAX = 4, PAD = 16;
    var st = { natW: 1, natH: 1, scale: 1, fit: 1, mode: 'fit', panX: 0, panY: 0, url: '' };
    var frame, img, ph, phLabel, zoom, zlabel, built = false, drag = null;

    function zbtn(z, txt) {
      return '<button data-z="' + z + '" style="font:600 11px \'JetBrains Mono\';background:var(--sunk);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:3px 7px;cursor:pointer;line-height:1.1">' + txt + '</button>';
    }

    function build() {
      if (built) return;
      frame = $('slide-frame');
      frame.style.border = 'none';
      frame.style.background = 'transparent';
      frame.innerHTML =
        '<img id="preview-img" alt="" draggable="false" style="display:none;user-select:none;-webkit-user-drag:none;box-shadow:var(--shadow-soft);border-radius:6px;will-change:transform;max-width:none;max-height:none">' +
        '<span id="preview-ph" style="display:none;flex-direction:column;align-items:center;gap:10px">' +
        thumb(34, 'var(--muted)') +
        '<span id="preview-ph-label" style="font:500 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.1em;color:var(--muted)">slide frame</span></span>' +
        '<div id="preview-zoom" style="position:absolute;top:10px;right:10px;display:none;align-items:center;gap:5px;background:var(--panel);border:1.5px solid var(--border);border-radius:8px;padding:4px 6px;box-shadow:var(--shadow-soft);z-index:3">' +
        zbtn('out', '&minus;') + '<span id="preview-zoom-label" style="font:700 11px \'JetBrains Mono\';min-width:40px;text-align:center">100%</span>' +
        zbtn('in', '+') + zbtn('fit', 'Fit') + zbtn('100', '100%') + zbtn('reset', 'Reset') + '</div>';
      img = $('preview-img'); ph = $('preview-ph'); phLabel = $('preview-ph-label');
      zoom = $('preview-zoom'); zlabel = $('preview-zoom-label');
      wire();
      built = true;
    }

    function computeFit() {
      var r = frame.getBoundingClientRect();
      var aw = Math.max(1, r.width - PAD * 2), ah = Math.max(1, r.height - PAD * 2);
      st.fit = Math.min(aw / st.natW, ah / st.natH);
    }
    function clampPan() {
      var r = frame.getBoundingClientRect();
      var mx = Math.max(0, (st.natW * st.scale - (r.width - PAD * 2)) / 2);
      var my = Math.max(0, (st.natH * st.scale - (r.height - PAD * 2)) / 2);
      st.panX = Math.max(-mx, Math.min(mx, st.panX));
      st.panY = Math.max(-my, Math.min(my, st.panY));
    }
    function apply() {
      img.style.width = (st.natW * st.scale) + 'px';
      img.style.height = (st.natH * st.scale) + 'px';
      img.style.transform = 'translate(' + Math.round(st.panX) + 'px,' + Math.round(st.panY) + 'px)';
      img.style.cursor = st.scale > st.fit + 1e-3 ? (drag ? 'grabbing' : 'grab') : 'default';
      if (zlabel) zlabel.textContent = Math.round(st.scale * 100) + '%';
    }
    function setMode(mode) {
      computeFit();
      st.mode = mode; st.panX = 0; st.panY = 0;
      st.scale = Math.max(ZMIN, Math.min(ZMAX, mode === '100' ? 1 : st.fit));
      apply();
    }
    function zoomTo(s) {
      st.scale = Math.max(ZMIN, Math.min(ZMAX, s));
      st.mode = Math.abs(st.scale - st.fit) < 1e-3 ? 'fit' : 'custom';
      clampPan(); apply();
    }
    function zoomAt(f, cx, cy) {
      var r = frame.getBoundingClientRect();
      var ox = cx - (r.left + r.width / 2) - st.panX;
      var oy = cy - (r.top + r.height / 2) - st.panY;
      var ns = Math.max(ZMIN, Math.min(ZMAX, st.scale * f)), k = ns / st.scale;
      st.panX -= ox * (k - 1); st.panY -= oy * (k - 1); st.scale = ns;
      st.mode = Math.abs(ns - st.fit) < 1e-3 ? 'fit' : 'custom';
      clampPan(); apply();
    }
    function onLoad() {
      st.natW = img.naturalWidth || 1; st.natH = img.naturalHeight || 1;
      ph.style.display = 'none'; img.style.display = 'block'; zoom.style.display = 'flex';
      setMode('fit');
    }
    function onError() {
      img.style.display = 'none'; zoom.style.display = 'none';
      phLabel.textContent = 'slide image missing'; phLabel.style.color = 'var(--red)';
      ph.style.display = 'flex';
    }
    function wire() {
      img.addEventListener('load', onLoad);
      img.addEventListener('error', onError);
      zoom.addEventListener('click', function (e) {
        var b = e.target.closest('[data-z]'); if (!b) return;
        var z = b.dataset.z;
        if (z === 'fit' || z === 'reset') setMode('fit');
        else if (z === '100') setMode('100');
        else if (z === 'in') zoomTo(st.scale * 1.25);
        else if (z === 'out') zoomTo(st.scale * 0.8);
      });
      frame.addEventListener('wheel', function (e) {
        if (!e.ctrlKey || img.style.display === 'none') return;
        e.preventDefault();
        zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY);
      }, { passive: false });
      frame.addEventListener('dblclick', function () {
        if (img.style.display === 'none') return;
        setMode(Math.abs(st.scale - st.fit) < 1e-3 ? '100' : 'fit');
      });
      img.addEventListener('mousedown', function (e) {
        if (st.scale <= st.fit + 1e-3) return;
        e.preventDefault(); drag = { x: e.clientX, y: e.clientY, px: st.panX, py: st.panY };
        apply();
      });
      window.addEventListener('mousemove', function (e) {
        if (!drag) return;
        st.panX = drag.px + (e.clientX - drag.x); st.panY = drag.py + (e.clientY - drag.y);
        clampPan(); apply();
      });
      window.addEventListener('mouseup', function () { if (drag) { drag = null; apply(); } });
      if (window.ResizeObserver) {
        new ResizeObserver(function () {
          if (img.style.display === 'none') return;
          computeFit();
          if (st.mode === 'fit') st.scale = st.fit;
          clampPan(); apply();
        }).observe(frame);
      }
    }

    function refit() {
      // Recompute Fit against the CURRENT frame size — call when the Review
      // panel becomes visible/resizes (renderSlides may run while it's hidden,
      // i.e. 0x0, which would otherwise clamp the image to the minimum zoom).
      if (!built || img.style.display === 'none') return;
      computeFit();
      if (st.mode === 'fit') { st.scale = Math.max(ZMIN, Math.min(ZMAX, st.fit)); }
      clampPan(); apply();
    }

    function show(cur) {
      build();
      if (cur && cur.img) {
        if (cur.img !== st.url) {
          st.url = cur.img;
          img.style.display = 'none'; zoom.style.display = 'none';
          img.src = cur.img;
          if (img.complete && img.naturalWidth > 0) onLoad();
        }
      } else {
        st.url = ''; img.removeAttribute('src'); img.style.display = 'none';
        zoom.style.display = 'none';
        phLabel.textContent = 'slide frame' + (cur ? ' · ' + cur.time : '');
        phLabel.style.color = 'var(--muted)';
        ph.style.display = 'flex';
      }
    }
    return { show: show, refit: refit };
  })();

  function renderSlides() {
    var v = LP.state.viewingSlide;
    var list = $('slide-list');
    list.innerHTML = LP.data.slides.map(function (s, i) {
      var viewing = i === v;
      var wrap, thumbBd = 'var(--line)', icon = 'var(--muted)', label, labelColor;
      if (viewing) {
        wrap = 'background:var(--orange-soft);border:2px solid var(--orange);border-radius:11px;padding:7px;cursor:pointer;box-shadow:var(--shadow-soft)';
        thumbBd = 'var(--orange)'; icon = 'var(--orange-ink)';
        label = s.sel ? 'viewing · sel' : 'viewing'; labelColor = 'var(--orange-ink)';
      } else if (s.sel) {
        wrap = 'background:var(--blue-tint);border:2px solid var(--blue);border-radius:11px;padding:7px;cursor:pointer;box-shadow:var(--shadow-soft)';
        thumbBd = 'var(--blue)'; icon = 'var(--blue-ink)';
        label = 'selected'; labelColor = 'var(--blue-ink)';
      } else if (s.state === 'rejected') {
        wrap = 'background:var(--red-soft);border:1.5px solid var(--line);border-radius:11px;padding:8px;cursor:pointer';
        label = 'rejected'; labelColor = 'var(--red)';
      } else {
        wrap = 'background:var(--panel);border:1.5px solid var(--line);border-left:5px solid var(--blue);border-radius:11px;padding:8px;cursor:pointer';
        label = 'accepted'; labelColor = 'var(--blue-ink)';
      }
      var thumbImg = slideImg(s.thumb || s.img, 'width:100%;height:100%;object-fit:cover;border-radius:5px;display:block', 16, icon);
      return '<div class="lp-hit" data-slide="' + i + '" style="display:flex;align-items:center;gap:11px;' + wrap + '">' +
        '<div style="width:60px;height:38px;flex:none;overflow:hidden;background:var(--sunk);border:1.5px solid ' + thumbBd + ';border-radius:6px;display:flex;align-items:center;justify-content:center">' + thumbImg + '</div>' +
        '<div><div style="font:700 13px \'JetBrains Mono\'">' + esc(s.time) + '</div><div style="font:700 10px \'JetBrains Mono\';text-transform:uppercase;color:' + labelColor + '">' + label + '</div></div></div>';
    }).join('');
    var selCount = LP.data.slides.filter(function (s) { return s.sel; }).length;
    $('slides-sel').textContent = '· ' + selCount + ' sel';
    var cur = LP.data.slides[v];
    previewCtl.show(cur);
    $('slide-frame-meta').innerHTML = cur
      ? (esc(cur.time) + '.500 <span style="color:var(--muted);font-weight:400">· frame ' + (cur.frame || Math.round(cur.pct * 30)) + '</span>')
      : '';
    renderTimeline();
  }

  function renderTimeline() {
    var v = LP.state.viewingSlide;
    var ticks = $('timeline-ticks');
    ticks.innerHTML = LP.data.slides.map(function (s, i) {
      if (i === v) {
        return '<div style="position:absolute;top:2px;left:' + s.pct + '%;transform:translateX(-50%)"><div style="width:14px;height:14px;border-radius:50%;background:var(--orange);border:3px solid var(--panel);box-shadow:0 0 0 1.5px var(--orange)"></div></div>';
      }
      var color = s.state === 'rejected' ? 'var(--red)' : 'var(--blue)';
      return '<div class="lp-tick" data-slide="' + i + '" style="position:absolute;top:6px;left:' + s.pct + '%;width:3px;height:14px;border-radius:2px;background:' + color + '"></div>';
    }).join('');
    $('timeline-progress').style.width = LP.data.slides[v].pct + '%';
    var accepted = LP.data.slides.filter(function (s) { return s.state !== 'rejected'; }).length;
    $('timeline-meta').textContent = LP.data.slides.length + ' slides · ' + LP.data.duration;
    $('timeline-mid').textContent = LP.data.durationMid;
    $('timeline-end').textContent = LP.data.duration;
  }

  function renderReviewTranscript() {
    $('review-transcript').innerHTML = LP.data.reviewSegments.map(function (s, i) {
      var last = i === LP.data.reviewSegments.length - 1;
      var row = 'display:flex;padding:11px 13px;' + (last ? '' : 'border-bottom:1px solid var(--line);') + 'gap:11px';
      var tColor = 'var(--muted)';
      if (s.hot) { row += ';background:var(--blue-tint);border-left:3px solid var(--blue)'; tColor = 'var(--blue-ink)'; }
      return '<div style="' + row + '"><span style="width:66px;flex:none;font:500 11px \'JetBrains Mono\';color:' + tColor + '">' + esc(s.t) + '</span><span contenteditable="true" style="flex:1;font-size:13px;line-height:1.5">' + esc(s.text) + '</span></div>';
    }).join('');
  }

  function renderTranscript() {
    var t = LP.data.transcript;
    $('transcript-title').textContent = t.title;
    $('transcript-duration').textContent = t.duration;
    $('transcript-segcount').textContent = t.segments + ' segments';
    $('transcript-corrections').textContent = t.corrections + ' corrections';
    $('transcript-blocks').innerHTML = t.blocks.map(function (b) {
      var chip = b.hotTime
        ? '<span style="font:700 12px \'JetBrains Mono\';color:var(--orange-ink);background:var(--orange-soft);border-radius:7px;padding:3px 7px">' + esc(b.t) + '</span>'
        : '<span style="font:700 12px \'JetBrains Mono\';color:var(--muted)">' + esc(b.t) + '</span>';
      return '<div style="display:flex;gap:18px"><div style="width:58px;flex:none;text-align:right">' + chip + '</div><p style="margin:0;font-size:17px;line-height:1.72;text-wrap:pretty">' + b.html + '</p></div>';
    }).join('');
  }

  function renderStudy() {
    var st = LP.data.study;
    $('topics-list').innerHTML = st.topics.map(function (tp, i) {
      var wrap = tp.active
        ? 'background:var(--blue-tint);border:1.5px solid var(--blue);border-radius:10px;padding:10px 12px;cursor:pointer'
        : 'background:var(--panel);border:1.5px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer';
      var tColor = tp.active ? 'var(--blue-ink)' : 'var(--muted)';
      var weight = tp.active ? 'font-weight:600;' : '';
      return '<div class="lp-hit" data-topic="' + i + '" style="' + wrap + '"><div style="font:500 10px \'JetBrains Mono\';color:' + tColor + ';margin-bottom:2px">' + esc(tp.t) + '</div><div style="' + weight + 'font-size:13px">' + esc(tp.title) + '</div></div>';
    }).join('');
    $('study-topic-blocks').innerHTML = st.topicBlocks.map(function (b) {
      var styleActive = b.active ? 'background:var(--blue-soft);border:1.5px solid var(--blue)' : 'background:var(--sunk);border:1.5px solid var(--line)';
      return '<div class="lp-tick" style="position:absolute;top:4px;left:' + b.left + '%;width:' + b.width + '%;height:16px;border-radius:4px;' + styleActive + '"></div>';
    }).join('');
    $('study-topic-labels').innerHTML = st.topicLabels.map(function (l) { return '<span>' + esc(l) + '</span>'; }).join('');
    $('study-timeline-meta').textContent = st.topics.length + ' topics · ' + LP.data.slides.length + ' slides';
    $('study-bookmarks-count').textContent = st.bookmarks.length + ' bookmarks';
    $('bookmarks-list').innerHTML = st.bookmarks.map(function (b) {
      return '<div style="border-left:3px solid ' + b.color + ';padding-left:10px"><div style="font:500 10px \'JetBrains Mono\';color:var(--muted)">' + esc(b.t) + '</div><div style="font-size:13px;line-height:1.4">' + esc(b.text) + '</div></div>';
    }).join('');
    $('study-stats').innerHTML = st.stats.map(function (row, i) {
      var mb = i === st.stats.length - 1 ? '' : 'margin-bottom:8px;';
      return '<div style="display:flex;justify-content:space-between;font-size:13px;' + mb + '"><span style="color:var(--muted)">' + esc(row[0]) + '</span><span style="font-weight:700">' + esc(row[1]) + '</span></div>';
    }).join('');
    renderCard();
  }

  function renderChat() {
    var feed = $('chat-feed');
    feed.innerHTML = LP.state.chat.map(function (m, i) {
      var last = i === LP.state.chat.length - 1;
      var cls = m.role === 'user' ? 'lp-bubble-user' : 'lp-bubble-ai';
      var caret = (m.role === 'ai' && last && LP.state.streaming) ? '<span class="lp-caret"></span>' : '';
      return '<div class="' + cls + '">' + esc(m.text) + caret + '</div>';
    }).join('');
    feed.scrollTop = feed.scrollHeight;
  }

  /* ======================= quiz (configurable + session) ======================= */
  var Q = function () { return LP.state.quiz; };
  function qQuestions() { return LP.data.quiz.questions || []; }
  function qScore() {
    var q = Q(), qs = qQuestions(), n = 0;
    Object.keys(q.answers).forEach(function (k) { if (qs[k] && q.answers[k] === qs[k].correct_index) n++; });
    return n;
  }
  function qSaveSession() {
    var q = Q();
    if (lpBridge.connected()) lpBridge.call('save_quiz_session', JSON.stringify({
      phase: q.phase, index: q.index, answers: q.answers, flags: q.flags, autoAdvance: q.autoAdvance
    }));
  }
  function _seg(name, opts, cur) {
    return '<div style="display:flex;flex-wrap:wrap;gap:6px">' + opts.map(function (o) {
      var on = String(o) === String(cur);
      return '<button data-qset="' + name + '" data-qval="' + esc(o) + '" style="font:600 12px \'JetBrains Mono\';padding:6px 11px;border-radius:8px;cursor:pointer;border:1.5px solid ' +
        (on ? 'var(--orange)' : 'var(--border)') + ';background:' + (on ? 'var(--orange)' : 'var(--panel)') + ';color:' + (on ? '#fff' : 'var(--ink)') + '">' + esc(o) + '</button>';
    }).join('') + '</div>';
  }
  function _qField(label, html) {
    return '<div style="margin-bottom:15px"><div style="font:600 10px \'JetBrains Mono\';letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:7px">' + label + '</div>' + html + '</div>';
  }

  /* ---- generation progress bar + ETA (shared by quiz + flashcards) ---- */
  var _genTimers = { quiz: null, flash: null };
  function _genBar(kind) {
    var st = kind === 'quiz' ? LP.state.quiz : LP.state.flash;
    var el = Date.now() - (st.genStart || Date.now()), est = st.genEst || 12000;
    var pct = Math.max(4, Math.min(93, el / est * 100)), etaMs = est - el;
    var eta = etaMs > 1000 ? '~' + Math.ceil(etaMs / 1000) + 's remaining'
      : (etaMs > -8000 ? 'almost done…' : 'still working…');
    var noun = kind === 'quiz' ? 'quiz' : 'flashcards';
    var actAttr = kind === 'quiz' ? 'qact' : 'fact';
    return '<div style="padding:24px 4px">' +
      '<div style="font:700 15px \'Space Grotesk\';margin-bottom:4px">Generating ' + noun + '…</div>' +
      '<div style="font:500 12px \'JetBrains Mono\';color:var(--muted);margin-bottom:14px;min-height:16px">' + esc(st.status || '') + '</div>' +
      '<div style="height:10px;border-radius:6px;background:var(--sunk);overflow:hidden;border:1.5px solid var(--border)"><div style="width:' + pct.toFixed(1) + '%;height:100%;background:var(--orange);background-image:repeating-linear-gradient(90deg,transparent,transparent 8px,rgba(255,255,255,.28) 8px,rgba(255,255,255,.28) 16px);transition:width .25s linear"></div></div>' +
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px">' +
      '<span style="font:600 12px \'JetBrains Mono\';color:var(--muted)">' + Math.round(pct) + '% · ' + eta + '</span>' +
      '<button data-' + actAttr + '="cancel" style="font:600 12px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:8px;padding:7px 14px;cursor:pointer;color:var(--ink)">Cancel</button></div></div>';
  }
  function startGen(kind, count) {
    var st = kind === 'quiz' ? LP.state.quiz : LP.state.flash;
    st.generating = true; st.genStart = Date.now();
    st.genEst = (3.5 + 1.6 * (count || 5)) * 1000;  // rough ETA; capped until result lands
    if (_genTimers[kind]) clearInterval(_genTimers[kind]);
    _genTimers[kind] = setInterval(function () {
      if (!st.generating) { clearInterval(_genTimers[kind]); _genTimers[kind] = null; return; }
      (kind === 'quiz' ? renderQuiz : renderCard)();
    }, 250);
  }
  function stopGen(kind) {
    var st = kind === 'quiz' ? LP.state.quiz : LP.state.flash;
    st.generating = false;
    if (_genTimers[kind]) { clearInterval(_genTimers[kind]); _genTimers[kind] = null; }
  }

  function renderQuiz() {
    var root = $('quiz-root'); if (!root) return;
    var q = Q(), s = q.settings, qs = qQuestions();
    if (q.generating) { root.innerHTML = _genBar('quiz'); return; }
    if (q.phase === 'setup' || !qs.length) {
      root.innerHTML =
        '<div style="font:700 17px \'Space Grotesk\';margin-bottom:4px">New quiz</div>' +
        '<div style="font-size:13px;color:var(--muted);margin-bottom:18px">Generated from this lecture' + (LP.data.quiz.provider ? ' · last: ' + esc(LP.data.quiz.provider) : '') + '.</div>' +
        _qField('Questions', _seg('count', [3, 5, 10, 20], s.count) +
          '<input id="quiz-count-custom" type="number" min="1" max="50" placeholder="custom" value="" style="margin-top:7px;width:110px;font:600 12px \'JetBrains Mono\';background:var(--sunk);border:1.5px solid var(--border);border-radius:8px;padding:6px 10px;color:var(--ink)">') +
        _qField('Difficulty', _seg('difficulty', ['Easy', 'Medium', 'Hard', 'Mixed'], s.difficulty)) +
        _qField('Type', _seg('type', ['Multiple choice', 'True / false', 'Mixed'], s.type)) +
        _qField('Source', _seg('source', ['Transcript', 'Slides', 'Both'], s.source)) +
        '<div style="display:flex;gap:10px;margin-top:8px">' +
        '<button data-qact="generate" style="font:700 14px \'Space Grotesk\';background:var(--orange);color:#fff;border:2px solid var(--orange-ink);border-radius:10px;padding:11px 22px;cursor:pointer">Generate quiz</button>' +
        (qs.length ? '<button data-qact="resume" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:10px;padding:11px 18px;cursor:pointer;color:var(--ink)">Resume last</button>' : '') +
        '</div>' +
        '<div style="font-size:12px;color:var(--muted);margin-top:14px">Difficulty/type/source are recorded with the quiz; question count is applied now. Falls back to a built-in quiz if local AI is off.</div>';
      return;
    }
    if (q.phase === 'summary') { renderQuizSummary(root); return; }
    renderQuizQuestion(root);
  }

  function renderQuizQuestion(root) {
    var q = Q(), qs = qQuestions(), i = q.index, item = qs[i];
    if (!item) { q.phase = 'setup'; renderQuiz(); return; }
    var answered = q.answers.hasOwnProperty(i);
    var chosen = answered ? q.answers[i] : q.pick;
    var flagged = !!q.flags[i];
    var letters = 'ABCDEFGH';
    var opts = item.options.map(function (opt, oi) {
      var border = 'var(--border)', bg = 'var(--panel)', col = 'var(--ink)';
      if (answered) {
        if (oi === item.correct_index) { border = 'var(--green)'; bg = 'var(--green-soft)'; col = 'var(--green)'; }
        else if (oi === chosen) { border = 'var(--red)'; bg = 'var(--red-soft)'; col = 'var(--red)'; }
        else { col = 'var(--muted)'; }
      } else if (oi === chosen) { border = 'var(--orange)'; bg = 'var(--orange-soft)'; }
      return '<button class="lp-opt" data-opt="' + oi + '"' + (answered ? ' disabled' : '') +
        ' style="display:flex;align-items:center;gap:11px;text-align:left;font:500 14px \'Space Grotesk\';padding:11px 13px;border-radius:10px;cursor:' + (answered ? 'default' : 'pointer') + ';border:2px solid ' + border + ';background:' + bg + ';color:' + col + '">' +
        '<span style="width:22px;height:22px;flex:none;border:2px solid currentColor;border-radius:6px;display:flex;align-items:center;justify-content:center;font:700 12px \'JetBrains Mono\'">' + letters[oi] + '</span>' + esc(opt) + '</button>';
    }).join('');
    var reveal = answered ? (
      '<div style="margin-top:15px;padding:12px 14px;border:2px solid var(--border);border-radius:11px;background:var(--panel)">' +
      '<div style="font:700 12px \'JetBrains Mono\';text-transform:uppercase;color:' + (chosen === item.correct_index ? 'var(--green)' : 'var(--red)') + ';margin-bottom:5px">' +
      (chosen === item.correct_index ? '✓ Correct' : '✗ Incorrect') + '</div>' +
      '<div style="font-size:13px;line-height:1.5">' + esc(item.explanation || item.options[item.correct_index]) + '</div></div>') : '';
    var last = i === qs.length - 1;
    root.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">' +
      '<span style="font:500 10px \'JetBrains Mono\';letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Question ' + (i + 1) + ' of ' + qs.length + ' · score ' + qScore() + '/' + Object.keys(q.answers).length + '</span>' +
      '<span style="display:flex;align-items:center;gap:8px">' +
      '<button data-qact="newquiz" title="Discard this quiz and choose new settings" style="font:600 11px \'JetBrains Mono\';border-radius:7px;padding:4px 9px;cursor:pointer;border:1.5px solid var(--border);background:var(--panel);color:var(--ink)">↻ New quiz</button>' +
      '<button data-qact="flag" title="Flag for review" style="font:600 11px \'JetBrains Mono\';border-radius:7px;padding:4px 9px;cursor:pointer;border:1.5px solid ' + (flagged ? 'var(--yellow)' : 'var(--border)') + ';background:' + (flagged ? 'var(--yellow-soft)' : 'var(--panel)') + ';color:var(--ink)">⚑ ' + (flagged ? 'Flagged' : 'Flag') + '</button></span></div>' +
      '<div style="font-weight:700;font-size:17px;margin-bottom:16px;line-height:1.35">' + esc(item.question) + '</div>' +
      '<div style="display:flex;flex-direction:column;gap:9px">' + opts + '</div>' + reveal +
      '<div style="display:flex;align-items:center;gap:10px;margin-top:18px">' +
      '<button data-qact="prev"' + (i === 0 ? ' disabled' : '') + ' style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:9px 15px;cursor:pointer;color:var(--ink);opacity:' + (i === 0 ? '.5' : '1') + '">Prev</button>' +
      (answered ? '' : '<button data-qact="submit"' + (q.pick == null ? ' disabled' : '') + ' style="font:700 13px \'Space Grotesk\';background:var(--orange);color:#fff;border:2px solid var(--orange-ink);border-radius:9px;padding:9px 17px;cursor:pointer;opacity:' + (q.pick == null ? '.5' : '1') + '">Submit</button>') +
      '<label style="display:flex;align-items:center;gap:6px;font:500 11px \'JetBrains Mono\';color:var(--muted);cursor:pointer;margin-left:auto"><input type="checkbox" data-qact="auto"' + (q.autoAdvance ? ' checked' : '') + '>auto-advance</label>' +
      (last ? '<button data-qact="finish" style="font:700 13px \'Space Grotesk\';background:var(--secondary-surface);color:var(--secondary-text);border:2px solid var(--secondary-border);border-radius:9px;padding:9px 17px;cursor:pointer">Finish</button>'
        : '<button data-qact="next"' + (answered ? '' : ' disabled') + ' style="font:700 13px \'Space Grotesk\';background:var(--secondary-surface);color:var(--secondary-text);border:2px solid var(--secondary-border);border-radius:9px;padding:9px 17px;cursor:pointer;opacity:' + (answered ? '1' : '.5') + '">Next</button>') +
      '</div>';
  }

  function renderQuizSummary(root) {
    var q = Q(), qs = qQuestions(), score = qScore(), wrong = [];
    qs.forEach(function (it, i) { if (q.answers[i] !== it.correct_index) wrong.push(i); });
    var pct = qs.length ? Math.round(score / qs.length * 100) : 0;
    root.innerHTML =
      '<div style="font:700 20px \'Space Grotesk\';margin-bottom:4px">Quiz complete</div>' +
      '<div style="font-size:32px;font-weight:800;margin:10px 0;color:' + (pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--orange)' : 'var(--red)') + '">' + score + ' / ' + qs.length + '<span style="font-size:16px;color:var(--muted);font-weight:600"> · ' + pct + '%</span></div>' +
      '<div style="display:flex;flex-direction:column;gap:7px;margin:16px 0">' + qs.map(function (it, i) {
        var ok = q.answers[i] === it.correct_index;
        return '<div style="display:flex;gap:9px;align-items:flex-start;font-size:13px;padding:9px 11px;border:1.5px solid var(--border);border-radius:9px;background:var(--panel)">' +
          '<span style="color:' + (ok ? 'var(--green)' : 'var(--red)') + ';font-weight:700">' + (ok ? '✓' : '✗') + '</span>' +
          '<span>' + esc(it.question) + (q.flags[i] ? ' <span style="color:var(--yellow)">⚑</span>' : '') + '</span></div>';
      }).join('') + '</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:10px">' +
      (wrong.length ? '<button data-qact="retry-wrong" style="font:700 13px \'Space Grotesk\';background:var(--orange);color:#fff;border:2px solid var(--orange-ink);border-radius:9px;padding:10px 17px;cursor:pointer">Retry incorrect (' + wrong.length + ')</button>' : '') +
      '<button data-qact="restart" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">Restart</button>' +
      '<button data-qact="copy" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">Copy</button>' +
      '<button data-qact="newquiz" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">New quiz settings</button>' +
      '</div>';
  }

  function quizAction(act, el) {
    var q = Q(), qs = qQuestions();
    if (act === 'generate') {
      var ci = $('quiz-count-custom'), cv = ci && ci.value ? Math.max(1, Math.min(50, +ci.value)) : q.settings.count;
      q.settings.count = cv; q.status = 'Contacting the study model…';
      if (lpBridge.connected()) {
        startGen('quiz', cv);
        lpBridge.call('generate_quiz', JSON.stringify({
          count: cv, difficulty: q.settings.difficulty, type: q.settings.type,
          scope: q.settings.scope, source: q.settings.source
        }));
      } else { toast('Preview mode — connect the app to generate'); }
      renderQuiz();
    } else if (act === 'cancel') {
      stopGen('quiz'); if (lpBridge.connected()) lpBridge.call('cancel_quiz'); renderQuiz();
    } else if (act === 'resume') { q.phase = 'session'; renderQuiz();
    } else if (act === 'submit') {
      if (q.pick != null) { q.answers[q.index] = q.pick; q.pick = null; qSaveSession(); renderQuiz();
        if (q.autoAdvance && q.index < qs.length - 1) setTimeout(function () { quizAction('next'); }, 850); }
    } else if (act === 'next') {
      if (q.index < qs.length - 1) { q.index++; q.pick = null; qSaveSession(); renderQuiz(); }
    } else if (act === 'prev') {
      if (q.index > 0) { q.index--; q.pick = null; qSaveSession(); renderQuiz(); }
    } else if (act === 'flag') { q.flags[q.index] = !q.flags[q.index]; qSaveSession(); renderQuiz();
    } else if (act === 'auto') { q.autoAdvance = !!(el && el.checked); qSaveSession();
    } else if (act === 'finish') { q.phase = 'summary'; qSaveSession(); renderQuiz();
    } else if (act === 'restart') { q.phase = 'session'; q.index = 0; q.pick = null; q.answers = {}; q.flags = {}; qSaveSession(); renderQuiz();
    } else if (act === 'retry-wrong') {
      var keep = {}; qQuestions().forEach(function (it, i) { if (q.answers[i] === it.correct_index) keep[i] = q.answers[i]; });
      q.answers = keep; q.phase = 'session'; q.index = 0; q.pick = null;
      // jump to first unanswered
      for (var k = 0; k < qs.length; k++) { if (!q.answers.hasOwnProperty(k)) { q.index = k; break; } }
      qSaveSession(); renderQuiz();
    } else if (act === 'copy') {
      var L = 'ABCDEFGH';
      var txt = qs.map(function (it, i) {
        return (i + 1) + '. ' + it.question + '\n' +
          it.options.map(function (o, oi) { return '   ' + L[oi] + ') ' + o; }).join('\n') +
          '\n   Answer: ' + L[it.correct_index] + ') ' + it.options[it.correct_index] +
          (it.explanation ? '\n   ' + it.explanation : '');
      }).join('\n\n');
      copyText(txt, 'Quiz copied');
    } else if (act === 'newquiz') { q.phase = 'setup'; renderQuiz(); }
  }

  /* ======================= flashcards (configurable session) ======================= */
  var F = function () { return LP.state.flash; };
  function fCards() { return LP.data.flashcards.cards || []; }
  function fOrder() {
    var f = F(), n = fCards().length;
    if (!f.order || f.order.length !== n) { f.order = []; for (var i = 0; i < n; i++) f.order.push(i); }
    return f.order;
  }
  function fCur() { return fCards()[fOrder()[F().index]]; }
  function fSaveSession() {
    var f = F();
    if (lpBridge.connected()) lpBridge.call('save_flashcard_session', JSON.stringify({
      phase: f.phase, index: f.index, known: f.known, unsure: f.unsure,
      bookmarks: f.bookmarks, order: f.order
    }));
  }
  function fCardId() { return fOrder()[F().index]; }

  function renderCard() {
    var root = $('flash-root'); if (!root) return;
    var f = F(), s = f.settings, cards = fCards();
    if (f.generating) { root.innerHTML = _genBar('flash'); return; }
    if (f.phase === 'setup' || !cards.length) {
      root.innerHTML =
        '<div style="font:700 17px \'Space Grotesk\';margin-bottom:4px">New flashcards</div>' +
        '<div style="font-size:13px;color:var(--muted);margin-bottom:18px">Generated from this lecture' + (LP.data.flashcards.provider ? ' · last: ' + esc(LP.data.flashcards.provider) : '') + '.</div>' +
        _qField('Cards', _fSeg('count', [5, 10, 20, 30], s.count) +
          '<input id="flash-count-custom" type="number" min="1" max="60" placeholder="custom" style="margin-top:7px;width:110px;font:600 12px \'JetBrains Mono\';background:var(--sunk);border:1.5px solid var(--border);border-radius:8px;padding:6px 10px;color:var(--ink)">') +
        _qField('Depth', _fSeg('difficulty', ['Basic', 'Detailed', 'Exam-focused'], s.difficulty)) +
        _qField('Style', _fSeg('style', ['Term → definition', 'Question → answer', 'Concept → explanation', 'Mixed'], s.style)) +
        '<div style="display:flex;gap:10px;margin-top:8px">' +
        '<button data-fact="generate" style="font:700 14px \'Space Grotesk\';background:var(--orange);color:#fff;border:2px solid var(--orange-ink);border-radius:10px;padding:11px 22px;cursor:pointer">Generate flashcards</button>' +
        (cards.length ? '<button data-fact="resume" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:10px;padding:11px 18px;cursor:pointer;color:var(--ink)">Resume last</button>' : '') +
        '</div>';
      return;
    }
    if (f.phase === 'summary') { renderCardSummary(root); return; }
    renderCardSession(root);
  }

  function _fSeg(name, opts, cur) {
    return '<div style="display:flex;flex-wrap:wrap;gap:6px">' + opts.map(function (o) {
      var on = String(o) === String(cur);
      return '<button data-fset="' + name + '" data-fval="' + esc(o) + '" style="font:600 12px \'JetBrains Mono\';padding:6px 11px;border-radius:8px;cursor:pointer;border:1.5px solid ' +
        (on ? 'var(--orange)' : 'var(--border)') + ';background:' + (on ? 'var(--orange)' : 'var(--panel)') + ';color:' + (on ? '#fff' : 'var(--ink)') + '">' + esc(o) + '</button>';
    }).join('') + '</div>';
  }

  function renderCardSession(root) {
    var f = F(), cards = fCards(), c = fCur(), id = fCardId();
    if (!c) { f.phase = 'setup'; renderCard(); return; }
    var known = Object.keys(f.known).length, unsure = Object.keys(f.unsure).length;
    var marked = f.known[id] ? 'known' : f.unsure[id] ? 'unsure' : '';
    var bm = !!f.bookmarks[id];
    root.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">' +
      '<span style="font:500 10px \'JetBrains Mono\';letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Card ' + (f.index + 1) + ' of ' + cards.length + '</span>' +
      '<span style="font:500 11px \'JetBrains Mono\';color:var(--muted)">✓ ' + known + ' · ? ' + unsure + '</span></div>' +
      '<div data-fact="flip" style="width:100%;min-height:170px;background:var(--panel);border:2px solid ' + (marked === 'known' ? 'var(--green)' : marked === 'unsure' ? 'var(--yellow)' : 'var(--border)') + ';border-radius:14px;box-shadow:var(--shadow-hi);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:26px;cursor:pointer">' +
      '<span style="font:500 10px \'JetBrains Mono\';letter-spacing:.12em;text-transform:uppercase;color:' + (f.flipped ? 'var(--orange-ink)' : 'var(--blue-ink)') + ';margin-bottom:12px">' + (f.flipped ? 'Definition' : 'Term') + '</span>' +
      '<span style="font-weight:700;font-size:18px;line-height:1.4">' + esc(f.flipped ? c.definition : c.term) + '</span>' +
      '<span style="font:500 11px \'JetBrains Mono\';color:var(--muted);margin-top:16px">tap or Space to flip</span></div>' +
      '<div style="display:flex;gap:8px;margin-top:14px;justify-content:center">' +
      '<button data-fact="known" style="font:700 12px \'Space Grotesk\';background:' + (marked === 'known' ? 'var(--green)' : 'var(--green-soft)') + ';color:' + (marked === 'known' ? '#fff' : 'var(--green)') + ';border:2px solid var(--green);border-radius:9px;padding:9px 15px;cursor:pointer">Known</button>' +
      '<button data-fact="unsure" style="font:700 12px \'Space Grotesk\';background:' + (marked === 'unsure' ? 'var(--yellow)' : 'var(--yellow-soft)') + ';color:var(--ink);border:2px solid var(--yellow);border-radius:9px;padding:9px 15px;cursor:pointer">Unsure</button>' +
      '<button data-fact="bookmark" title="Bookmark" style="font:700 12px \'Space Grotesk\';background:' + (bm ? 'var(--orange-soft)' : 'var(--panel)') + ';color:var(--ink);border:2px solid ' + (bm ? 'var(--orange)' : 'var(--border)') + ';border-radius:9px;padding:9px 13px;cursor:pointer">☆</button>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:10px;margin-top:14px">' +
      '<button data-fact="prev"' + (f.index === 0 ? ' disabled' : '') + ' style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:9px 15px;cursor:pointer;color:var(--ink);opacity:' + (f.index === 0 ? '.5' : '1') + '">Prev</button>' +
      '<button data-fact="shuffle" style="font:600 12px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:9px 13px;cursor:pointer;color:var(--ink)">Shuffle</button>' +
      '<button data-fact="restart" style="font:600 12px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:9px 13px;cursor:pointer;color:var(--ink)">Restart</button>' +
      '<button data-fact="newdeck" title="Discard these cards and choose new settings" style="font:600 12px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:9px 13px;cursor:pointer;color:var(--ink)">↻ New cards</button>' +
      '<div style="flex:1"></div>' +
      (f.index === cards.length - 1
        ? '<button data-fact="finish" style="font:700 13px \'Space Grotesk\';background:var(--secondary-surface);color:var(--secondary-text);border:2px solid var(--secondary-border);border-radius:9px;padding:9px 17px;cursor:pointer">Summary</button>'
        : '<button data-fact="next" style="font:700 13px \'Space Grotesk\';background:var(--secondary-surface);color:var(--secondary-text);border:2px solid var(--secondary-border);border-radius:9px;padding:9px 17px;cursor:pointer">Next</button>') +
      '</div>';
  }

  function renderCardSummary(root) {
    var f = F(), cards = fCards(), known = Object.keys(f.known).length, unsure = Object.keys(f.unsure).length;
    root.innerHTML =
      '<div style="font:700 20px \'Space Grotesk\';margin-bottom:12px">Deck complete</div>' +
      '<div style="display:flex;gap:14px;margin-bottom:18px">' +
      '<div style="flex:1;background:var(--green-soft);border:2px solid var(--green);border-radius:12px;padding:16px;text-align:center"><div style="font-size:26px;font-weight:800;color:var(--green)">' + known + '</div><div style="font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--green)">Known</div></div>' +
      '<div style="flex:1;background:var(--yellow-soft);border:2px solid var(--yellow);border-radius:12px;padding:16px;text-align:center"><div style="font-size:26px;font-weight:800;color:var(--ink)">' + unsure + '</div><div style="font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--ink)">Unsure</div></div>' +
      '<div style="flex:1;background:var(--panel);border:2px solid var(--border);border-radius:12px;padding:16px;text-align:center"><div style="font-size:26px;font-weight:800">' + cards.length + '</div><div style="font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted)">Total</div></div>' +
      '</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:10px">' +
      (unsure ? '<button data-fact="retry-unsure" style="font:700 13px \'Space Grotesk\';background:var(--orange);color:#fff;border:2px solid var(--orange-ink);border-radius:9px;padding:10px 17px;cursor:pointer">Review unsure (' + unsure + ')</button>' : '') +
      '<button data-fact="restart" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">Restart</button>' +
      '<button data-fact="copy" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">Copy</button>' +
      '<button data-fact="newdeck" style="font:600 13px \'Space Grotesk\';background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 17px;cursor:pointer;color:var(--ink)">New settings</button>' +
      '</div>';
  }

  function flashAction(act) {
    var f = F(), cards = fCards();
    if (act === 'generate') {
      var ci = $('flash-count-custom'), cv = ci && ci.value ? Math.max(1, Math.min(60, +ci.value)) : f.settings.count;
      f.settings.count = cv; f.status = 'Contacting the study model…';
      if (lpBridge.connected()) {
        startGen('flash', cv);
        lpBridge.call('generate_flashcards', JSON.stringify({
          count: cv, difficulty: f.settings.difficulty, style: f.settings.style, scope: f.settings.scope
        }));
      } else { toast('Preview mode — connect the app to generate'); }
      renderCard();
    } else if (act === 'cancel') { stopGen('flash'); if (lpBridge.connected()) lpBridge.call('cancel_flashcards'); renderCard();
    } else if (act === 'resume') { f.phase = 'session'; renderCard();
    } else if (act === 'flip') { f.flipped = !f.flipped; renderCard();
    } else if (act === 'next') { if (f.index < cards.length - 1) { f.index++; f.flipped = false; fSaveSession(); renderCard(); }
    } else if (act === 'prev') { if (f.index > 0) { f.index--; f.flipped = false; fSaveSession(); renderCard(); }
    } else if (act === 'known') { var id = fCardId(); delete f.unsure[id]; if (f.known[id]) delete f.known[id]; else f.known[id] = 1; fSaveSession(); renderCard();
    } else if (act === 'unsure') { var iu = fCardId(); delete f.known[iu]; if (f.unsure[iu]) delete f.unsure[iu]; else f.unsure[iu] = 1; fSaveSession(); renderCard();
    } else if (act === 'bookmark') { var ib = fCardId(); if (f.bookmarks[ib]) delete f.bookmarks[ib]; else f.bookmarks[ib] = 1; fSaveSession(); renderCard();
    } else if (act === 'shuffle') {
      var ord = fOrder().slice();
      for (var k = ord.length - 1; k > 0; k--) { var j = Math.floor(Math.random() * (k + 1)); var t = ord[k]; ord[k] = ord[j]; ord[j] = t; }
      f.order = ord; f.index = 0; f.flipped = false; fSaveSession(); renderCard();
    } else if (act === 'finish') { f.phase = 'summary'; fSaveSession(); renderCard();
    } else if (act === 'restart') { f.phase = 'session'; f.index = 0; f.flipped = false; f.known = {}; f.unsure = {}; fSaveSession(); renderCard();
    } else if (act === 'retry-unsure') {
      var keep = Object.keys(f.unsure).map(Number);
      if (keep.length) { f.order = keep; f.index = 0; f.flipped = false; f.known = {}; f.unsure = {}; f.phase = 'session'; fSaveSession(); renderCard(); }
    } else if (act === 'copy') {
      var txt = cards.map(function (c, i) { return (i + 1) + '. ' + c.term + '\n   ' + c.definition; }).join('\n\n');
      copyText(txt, 'Flashcards copied');
    } else if (act === 'newdeck') { f.phase = 'setup'; renderCard(); }
  }

  function renderExportFormats() {
    $('export-formats').innerHTML = LP.data.exportFormats.map(function (f, i) {
      if (f.sel) {
        return '<label class="lp-hit" data-fmt="' + i + '" style="display:flex;align-items:center;gap:8px;border:1.5px solid var(--blue);border-radius:9px;padding:10px 12px;background:var(--blue-tint);cursor:pointer"><span style="width:16px;height:16px;background:var(--blue);border-radius:5px;flex:none;display:flex;align-items:center;justify-content:center">' + CHECK_SVG + '</span><span style="font:700 12px \'JetBrains Mono\'">' + esc(f.key) + '</span></label>';
      }
      return '<label class="lp-hit" data-fmt="' + i + '" style="display:flex;align-items:center;gap:8px;border:1.5px solid var(--line);border-radius:9px;padding:10px 12px;cursor:pointer"><span style="width:16px;height:16px;border:1.5px solid var(--muted);border-radius:5px;flex:none"></span><span style="font:700 12px \'JetBrains Mono\';color:var(--muted)">' + esc(f.key) + '</span></label>';
    }).join('');
    var n = LP.data.exportFormats.filter(function (f) { return f.sel; }).length;
    $('export-all-desc').textContent = 'PDF + HTML + ' + n + ' transcript formats';
  }

  function renderExportPhase() {
    var ph = LP.state.exportPhase;
    $('export-idle').hidden = ph !== 'idle';
    $('export-running').hidden = ph !== 'running';
    $('export-done').hidden = ph !== 'done';
    if (ph === 'done') {
      $('export-files').innerHTML = LP.data.exportFiles.map(function (f) {
        return '<span style="font:500 11px \'JetBrains Mono\';background:var(--panel);border:2px solid var(--line);border-radius:7px;padding:5px 10px">' + esc(f) + '</span>';
      }).join('');
    }
  }

  /* ======================= screen switching / chrome ======================= */

  var CRUMBS = { home: 'Home', process: 'Process', review: 'Review', transcript: 'Transcript', study: 'Study', exports: 'Exports', settings: 'Settings' };

  function setScreen(name) {
    LP.state.screen = name;
    if (typeof hideScrub === 'function') hideScrub();
    Array.prototype.forEach.call(document.querySelectorAll('main [data-screen]'), function (sec) {
      var show = sec.dataset.screen === name;
      if (show === !sec.hidden) return;
      sec.hidden = !show;
      if (show) { // retrigger entrance animation
        sec.style.animation = 'none'; void sec.offsetWidth; sec.style.animation = '';
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll('.lp-nav'), function (b) {
      b.classList.toggle('active', b.dataset.nav === name);
    });
    $('crumb').textContent = CRUMBS[name] || name;
    // The preview may have been laid out while Review was hidden (0x0) — refit
    // now that it's visible so the slide fills the canvas.
    if (name === 'review') {
      requestAnimationFrame(function () { previewCtl.refit(); });
    }
    if ((name === 'study' || name === 'settings') && lpBridge.connected()) {
      lpBridge.call('smart_study_status');
    }
    if (name === 'settings' && lpBridge.connected()) {
      lpBridge.call('get_updater_state').then(function (json) {
        if (!json) return;
        try { renderUpdaterState(JSON.parse(json)); } catch (e) {}
      });
      lpBridge.call('cuda_pack_status');
      lpBridge.call('get_notification_prefs');
    }
  }

  function setTheme(theme) {
    LP.state.theme = theme;
    $('app').dataset.theme = theme;
    $('theme-label').textContent = theme === 'light' ? 'DARK' : 'LIGHT';
    $('theme-icon').setAttribute('d', theme === 'light'
      ? 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4'
      : 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z');
    $('btn-set-light').classList.toggle('active', theme === 'light');
    $('btn-set-dark').classList.toggle('active', theme === 'dark');
    lpBridge.call('set_setting', 'theme', theme);
  }

  function setFocus(on) {
    LP.state.focus = on;
    $('app').dataset.focus = on ? 'true' : 'false';
    $('focus-pill').hidden = !on;
  }

  function setOnb(state) { // null | 'drop' | 'detected'
    LP.state.onb = state;
    $('onb-overlay').hidden = state === null;
    $('onb-drop').hidden = state !== 'drop';
    $('onb-detected').hidden = state !== 'detected';
  }

  function setStudyTab(tab) {
    LP.state.studyTab = tab;
    Array.prototype.forEach.call(document.querySelectorAll('.lp-tab'), function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    $('pane-chat').hidden = tab !== 'chat';
    $('pane-quiz').hidden = tab !== 'quiz';
    $('pane-flash').hidden = tab !== 'flash';
    $('pane-notes').hidden = tab !== 'notes';
    if (tab === 'quiz') renderQuiz();
    if (tab === 'flash') renderCard();
  }

  function setJobsEmpty(empty) {
    LP.state.jobsEmpty = empty;
    $('home-jobs').hidden = empty;
    $('home-empty').hidden = !empty;
  }

  /* ======================= Smart Study ======================= */

  function presetByKey(d, key) {
    var list = (d && d.presets) || [];
    for (var i = 0; i < list.length; i++) if (list[i].key === key) return list[i];
    return null;
  }

  function ssChosenPreset(d) {
    var rec = (d && d.recommendation && d.recommendation.recommended) || 'balanced';
    var key = LP.state.ssPreset || (d && d.preset) || rec;
    if (!presetByKey(d, key)) key = rec;
    return key;
  }

  function renderSmartStudy(d) {
    if (!d) return;
    LP.state.smartStudy = d;
    var banner = $('smart-study-banner');
    var seg = $('ss-preset-seg');
    var setSeg = $('ss-settings-seg');
    if (!banner) return;

    // Build the preset chooser (both the banner and the settings card share logic).
    var chosen = ssChosenPreset(d);
    function segButtons(container, small) {
      if (!container) return;
      var list = (d.presets) || [];
      container.innerHTML = list.map(function (p) {
        var on = p.key === chosen;
        var pad = small ? '7px 11px' : '9px 13px';
        var css = 'flex:1;min-width:120px;text-align:left;font:600 12px \'Space Grotesk\';padding:' + pad + ';border-radius:9px;cursor:pointer;border:2px solid '
          + (on ? 'var(--orange)' : 'var(--line)') + ';background:' + (on ? 'var(--orange-soft)' : 'var(--panel)') + ';color:' + (on ? 'var(--orange-ink)' : 'var(--ink)');
        var rec = p.recommended ? ' <span style="font:600 9px \'JetBrains Mono\';color:var(--orange-ink)">· RECOMMENDED</span>' : '';
        return '<button class="lp-hit" data-ss-preset="' + p.key + '" style="' + css + '">'
          + esc(p.label) + rec
          + '<div style="font:500 10px \'JetBrains Mono\';color:var(--muted);margin-top:3px">~' + p.approx_gb + ' GB · ' + esc(p.blurb) + '</div></button>';
      }).join('');
      Array.prototype.forEach.call(container.querySelectorAll('[data-ss-preset]'), function (b) {
        b.addEventListener('click', function () {
          LP.state.ssPreset = b.dataset.ssPreset;
          if (lpBridge.connected()) lpBridge.call('set_study_preset', b.dataset.ssPreset);
          renderSmartStudy(LP.state.smartStudy);
        });
      });
    }
    segButtons(seg, false);
    segButtons(setSeg, true);

    // Recommendation copy.
    var cp = presetByKey(d, chosen) || {};
    var recNote = (d.recommendation && d.recommendation.note) || '';
    if ($('ss-rec-text')) $('ss-rec-text').textContent =
      'Recommended for this computer: ' + (cp.label || 'Balanced Study') + ' · approximately ' + (cp.approx_gb || 2.5) + ' GB';
    if ($('ss-settings-rec')) $('ss-settings-rec').textContent = recNote;

    // Settings-card status line + badge.
    var epStatus = $('ai-endpoint-status');
    if (epStatus) {
      var prov = d.provider || 'Built-in Study';
      var good = prov !== 'Built-in Study';
      var c = good ? 'var(--green)' : 'var(--secondary-text)';
      epStatus.style.color = c; epStatus.style.borderColor = good ? 'var(--green)' : 'var(--secondary-border)';
      epStatus.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:' + c + '"></span>' + esc(prov + (d.ready && d.model ? ' · ' + d.model : ''));
    }
    if ($('ss-settings-msg')) $('ss-settings-msg').textContent =
      d.state === 'downloading' ? (d.message || 'Downloading…') :
      d.ready ? 'Ready.' : (d.message || '');

    // State machine drives which sub-panel of the banner shows.
    var st = d.state || 'idle';
    var showBanner = !d.ready && !LP.state.ssDismissed;
    banner.hidden = !showBanner;
    var intro = $('ss-intro'), need = $('ss-need-engine'), prog = $('ss-progress'), msg = $('ss-msg');
    intro.hidden = !(st === 'idle' || st === 'error' || st === 'cancelled');
    need.hidden = st !== 'need_engine';
    prog.hidden = !(st === 'downloading' || st === 'testing');
    if (st === 'downloading' || st === 'testing') {
      var pct = (typeof d.percent === 'number') ? d.percent : null;
      $('ss-bar').style.width = (pct != null ? pct : (st === 'testing' ? 100 : 3)) + '%';
      $('ss-status').textContent = d.message || (st === 'testing' ? 'Testing…' : 'Downloading…');
      $('ss-pct').textContent = pct != null ? Math.round(pct) + '%' : '';
    }
    if (msg) {
      var showMsg = (st === 'error' || st === 'cancelled') && d.message;
      msg.hidden = !showMsg;
      if (showMsg) { msg.textContent = d.message; msg.style.color = st === 'error' ? 'var(--red)' : 'var(--muted)'; }
    }
    if (st === 'ready') toast('Smart Study ready · ' + (d.model || ''));
  }

  function ssInstall() {
    if (!lpBridge.connected()) { toast('Preview mode — Smart Study needs the app'); return; }
    lpBridge.call('install_smart_study', ssChosenPreset(LP.state.smartStudy) || 'balanced');
  }

  /* ======================= chat ======================= */

  function appendAiText(text, done) {
    var c = LP.state.chat;
    if (!c.length || c[c.length - 1].role !== 'ai' || !LP.state.streaming) return;
    c[c.length - 1].text = text;
    if (done) LP.state.streaming = false;
    renderChat();
  }

  var mockTimer = null;
  function sendChat() {
    var input = $('chat-input');
    var t = (input.value || '').trim();
    if (!t || LP.state.streaming) return;
    LP.state.chat.push({ role: 'user', text: t });
    LP.state.chat.push({ role: 'ai', text: '' });
    LP.state.streaming = true;
    input.value = '';
    renderChat();
    if (lpBridge.connected()) {
      lpBridge.call('ask_ai', t);
    } else {
      var full = 'Great question. Based on the transcript around 00:55, the base sits level to under two centimeters and the sides align to true north within 3/60 of a degree — remarkable precision for 2560 BC.';
      var i = 0;
      var step = function () {
        i += 2;
        appendAiText(full.slice(0, i), i >= full.length);
        if (i < full.length) mockTimer = setTimeout(step, 22);
      };
      mockTimer = setTimeout(step, 320);
    }
  }

  /* ======================= scrub ======================= */

  // The hover preview is portaled to <body> so it escapes the timeline's
  // overflow clipping; positioned with fixed coords + collision-aware flip.
  function hideScrub() {
    var w = $('scrub-wrap'), pv = $('scrub-preview');
    if (w) w.hidden = true;
    if (pv) pv.style.display = 'none';
  }

  function onScrub(e) {
    var strip = $('timeline-strip');
    if (!strip || !LP.data.slides.length) return;
    var r = strip.getBoundingClientRect();
    var pct = Math.max(0, Math.min(100, (e.clientX - r.left) / r.width * 100));
    var best = LP.data.slides[0], bd = 1e9;
    LP.data.slides.forEach(function (s, i) {
      var d = Math.abs(s.pct - pct);
      if (d < bd) { bd = d; best = s; best._i = i; }
    });

    // Needle stays inside the strip.
    $('scrub-wrap').hidden = false;
    $('scrub-needle').style.left = best.pct + '%';
    $('scrub-time').textContent = best.time;
    $('scrub-state').textContent = best._i === LP.state.viewingSlide ? 'viewing' : best.state;

    // Real slide image in the preview thumb (falls back to placeholder).
    var thumb = $('scrub-thumb');
    if (thumb) {
      thumb.innerHTML = slideImg(best.thumb || best.img, 'width:100%;height:100%;object-fit:cover', 20, 'var(--muted)');
    }

    // Fixed-position, collision-aware placement.
    var pv = $('scrub-preview');
    pv.style.display = 'block';
    var pw = pv.offsetWidth || 150;
    var ph = pv.offsetHeight || 110;
    var vw = window.innerWidth, vh = window.innerHeight, gap = 12, pad = 8;
    var tickX = r.left + r.width * (best.pct / 100);
    var left = Math.max(pad, Math.min(tickX - pw / 2, vw - pw - pad));
    var top = r.top - ph - gap;              // prefer above
    if (top < pad) {                         // not enough room -> below
      var below = r.bottom + gap;
      top = (below + ph + pad <= vh) ? below : Math.max(pad, r.top - ph - gap);
    }
    pv.style.left = left + 'px';
    pv.style.top = top + 'px';
  }

  /* ======================= export ======================= */

  function startExport() {
    LP.state.exportPhase = 'running';
    renderExportPhase();
    if (lpBridge.connected()) {
      var formats = LP.data.exportFormats.filter(function (f) { return f.sel; }).map(function (f) { return f.key; });
      lpBridge.call('export_all', JSON.stringify(formats));
    } else {
      setTimeout(function () { LP.state.exportPhase = 'done'; renderExportPhase(); }, 1700);
    }
  }

  /* ======================= updates / what's new ======================= */

  var UPD_DL_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3"/><path d="m7 10 5 5 5-5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>';

  function _wnBullet(n) {
    return '<div style="display:flex;gap:9px;align-items:flex-start"><span style="width:6px;height:6px;flex:none;border-radius:2px;background:var(--orange);margin-top:7px"></span><span>' + esc(n) + '</span></div>';
  }

  function showWhatsNew(info, mode) { // mode: 'available' | 'installed'
    LP.state.updateInfo = info;
    LP.state.updateMode = mode;
    $('whatsnew-title').textContent = mode === 'installed' ? 'What’s new in this update' : 'Update available';
    var cur = info.current || LP.data.version || '';
    $('whatsnew-current').textContent = cur ? ('v' + cur) : '';
    $('whatsnew-arrow').style.display = (mode === 'installed' || !cur) ? 'none' : '';
    $('whatsnew-version').textContent = 'v' + (info.available || info.version || '');
    $('whatsnew-channel').textContent = info.channel || 'Beta';
    $('whatsnew-channel').style.display = info.channel ? '' : 'none';
    $('whatsnew-size').textContent = info.size ? ('· ' + info.size) : '';
    $('whatsnew-date').textContent = info.date || '';
    $('whatsnew-skipnote').hidden = !info.is_skipped;
    ['improvements', 'fixes', 'limitations'].forEach(function (sec) {
      var items = info[sec] || [];
      $('whatsnew-sec-' + sec).hidden = !items.length;
      var list = document.querySelector('[data-sec="' + sec + '"]');
      if (list) list.innerHTML = items.map(_wnBullet).join('');
    });
    var hasSecs = (info.improvements || []).length || (info.fixes || []).length || (info.limitations || []).length;
    $('whatsnew-notes').innerHTML = (!hasSecs ? (info.notes || []) : []).map(_wnBullet).join('')
      || (!hasSecs ? '<div style="color:var(--muted)">No release notes.</div>' : '');
    $('whatsnew-progress').hidden = true;
    $('whatsnew-progress-bar').style.width = '0%';
    $('whatsnew-msg').hidden = true;
    updSetPhase(mode === 'installed' ? 'installed' : (info.portable ? 'portable' : 'available'));
    $('whatsnew-overlay').hidden = false;
    if (mode === 'available') {
      $('update-badge').hidden = false;
      $('update-status').textContent = 'v' + (info.available || info.version) + ' available';
    }
  }

  // Drive the overview's buttons/labels by phase.
  function updSetPhase(phase) {
    LP.state.updatePhase = phase;
    var install = $('btn-update-install'), later = $('btn-update-later'),
        skip = $('btn-update-skip'), gh = $('btn-update-github'),
        prog = $('whatsnew-progress');
    function label(txt, withIcon) { install.innerHTML = (withIcon ? UPD_DL_ICON : '') + esc(txt); }
    // sensible defaults
    install.hidden = false; install.disabled = false;
    later.hidden = false; later.textContent = 'Remind me later';
    skip.hidden = false; gh.hidden = false; prog.hidden = true;
    if (phase === 'installed') {
      install.hidden = true; skip.hidden = true; gh.hidden = true;
      later.textContent = 'Nice!';
    } else if (phase === 'portable') {
      label('Open Download Page', false); install.dataset.action = 'openpage';
      skip.hidden = false;
    } else if (phase === 'downloading' || phase === 'verifying') {
      install.hidden = true; skip.hidden = true; gh.hidden = true; later.hidden = true;
      prog.hidden = false;
    } else if (phase === 'ready') {
      label('Install Now', true); install.dataset.action = 'install';
      skip.hidden = true; prog.hidden = true;
    } else if (phase === 'blocked') {
      install.disabled = true; label('Install Now', true); install.dataset.action = 'install';
      skip.hidden = true;
    } else { // 'available' or 'error'/'cancelled' -> ready to (re)download
      label('Download and Install', true); install.dataset.action = 'download';
    }
  }

  function updMsg(text, kind) {
    var el = $('whatsnew-msg');
    el.hidden = !text;
    if (text) { el.textContent = text; el.style.color = kind === 'error' ? 'var(--red)' : 'var(--muted)'; }
  }

  function hideWhatsNew() {
    $('whatsnew-overlay').hidden = true;
    lpBridge.call('whatsnew_seen');
  }

  function setUpdateChannel(ch) {
    Array.prototype.forEach.call(document.querySelectorAll('#update-channel-seg [data-channel]'), function (b) {
      var on = b.dataset.channel === ch;
      b.style.border = '1.5px solid ' + (on ? 'var(--secondary-border)' : 'var(--line)');
      b.style.background = on ? 'var(--secondary-surface)' : 'var(--panel)';
      b.style.color = on ? 'var(--secondary-text)' : 'var(--ink)';
    });
  }

  function renderUpdaterState(d) {
    if (!d) return;
    if (d.channel) setUpdateChannel(d.channel);
    var ac = $('update-autocheck'); if (ac) ac.checked = d.auto_check !== false;
    var row = $('update-skipped-row');
    if (row) {
      var has = !!d.skipped_version;
      row.hidden = !has;
      if (has) $('update-skipped-label').textContent = 'Skipped v' + d.skipped_version;
    }
  }

  /* ======================= wiring ======================= */

  function wire() {
    // nav
    Array.prototype.forEach.call(document.querySelectorAll('.lp-nav'), function (b) {
      b.addEventListener('click', function () { setScreen(b.dataset.nav); });
    });

    // header
    $('btn-theme').addEventListener('click', function () { setTheme(LP.state.theme === 'light' ? 'dark' : 'light'); });
    $('btn-focus').addEventListener('click', function () { setFocus(!LP.state.focus); });
    $('focus-pill').addEventListener('click', function () { setFocus(false); });
    $('btn-save').addEventListener('click', function () { lpBridge.call('save_project'); });
    $('btn-export-top').addEventListener('click', function () { setScreen('exports'); });

    // settings
    $('btn-set-light').addEventListener('click', function () { setTheme('light'); });
    $('btn-set-dark').addEventListener('click', function () { setTheme('dark'); });
    $('btn-browse-model').addEventListener('click', function () { lpBridge.call('browse_model'); });
    $('btn-test-endpoint').addEventListener('click', function () { lpBridge.call('test_endpoint'); });

    // Compute engine (CPU / Vulkan) — reflects the persisted engine and writes
    // it back so a Vulkan selection actually reaches the transcription backend.
    var COMPUTE_IDS = { cpu: 'compute-cpu', cuda: 'compute-cuda', vulkan: 'compute-gpu' };
    function reflectEngine(engine) {
      Object.keys(COMPUTE_IDS).forEach(function (k) {
        var el = $(COMPUTE_IDS[k]); if (!el) return;
        var on = engine === k;
        el.style.background = on ? 'var(--secondary-surface)' : 'transparent';
        el.style.color = on ? 'var(--secondary-text)' : 'var(--muted)';
        el.style.border = '1.5px solid ' + (on ? 'var(--secondary-border)' : 'var(--line)');
        el.style.fontWeight = on ? '700' : '500';
        el.style.cursor = 'pointer';
      });
    }
    Object.keys(COMPUTE_IDS).forEach(function (k) {
      var el = $(COMPUTE_IDS[k]); if (!el) return;
      el.classList.add('lp-hit');
      el.addEventListener('click', function () {
        reflectEngine(k); lpBridge.call('set_setting', 'engine', k);
      });
    });
    $('btn-validate-vulkan').addEventListener('click', function () {
      ['vulkan-status', 'cuda-status'].forEach(function (id) {
        var el = $(id); if (el) { el.textContent = 'Checking compute backend…'; el.style.color = 'var(--muted)'; }
      });
      if (lpBridge.connected()) { lpBridge.call('validate_vulkan'); lpBridge.call('validate_cuda'); }
    });
    $('btn-cuda-pack-install').addEventListener('click', function () {
      if (!lpBridge.connected()) { toast('Preview mode — needs the app'); return; }
      $('cuda-pack-progress').hidden = false; this.disabled = true;
      $('cuda-pack-label').textContent = 'Starting download…';
      lpBridge.call('install_cuda_pack');
    });
    $('btn-cuda-pack-cancel').addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('cancel_cuda_pack');
    });

    // Transcription backend selector (Private Local / Online Fast|Accurate).
    function reflectBackend(bk) {
      Array.prototype.forEach.call(document.querySelectorAll('#tbk-seg [data-tbk]'), function (b) {
        var on = b.dataset.tbk === bk;
        b.style.background = on ? 'var(--secondary-surface)' : 'var(--panel)';
        b.style.color = on ? 'var(--secondary-text)' : 'var(--ink)';
        b.style.borderColor = on ? 'var(--secondary-border)' : 'var(--line)';
      });
    }
    $('tbk-seg').addEventListener('click', function (e) {
      var b = e.target.closest('[data-tbk]'); if (!b) return;
      reflectBackend(b.dataset.tbk);
      lpBridge.call('set_setting', 'transcription_backend', b.dataset.tbk);
    });
    // Groq key management (user types their own key; stored in Credential Manager).
    $('btn-groq-set').addEventListener('click', function () {
      var v = ($('groq-key-input').value || '').trim();
      if (!v) { toast('Enter an API key first'); return; }
      if (lpBridge.connected()) lpBridge.call('set_groq_key', v);
      $('groq-key-input').value = '';
    });
    $('btn-groq-test').addEventListener('click', function () { if (lpBridge.connected()) lpBridge.call('test_groq_key'); });
    $('btn-groq-remove').addEventListener('click', function () { if (lpBridge.connected()) lpBridge.call('remove_groq_key'); });

    // Local AI endpoint — editable, committed on blur / Enter.
    var epEl = $('ai-endpoint-url');
    epEl.addEventListener('blur', function () {
      lpBridge.call('set_setting', 'ollama_base_url', epEl.value.trim());
    });
    epEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); epEl.blur(); }
    });

    // Ollama model discovery + selection.
    $('btn-refresh-models').addEventListener('click', function () {
      $('ai-model-select').innerHTML = '<option value="">loading…</option>';
      lpBridge.call('list_ollama_models');
    });
    $('ai-model-select').addEventListener('change', function () {
      if (this.value) {
        lpBridge.call('set_setting', 'ollama_model', this.value);
        $('ai-model-name').textContent = this.value;
      }
    });
    $('btn-check-updates').addEventListener('click', function () {
      $('update-status').textContent = 'Checking…';
      if (lpBridge.connected()) { lpBridge.call('check_updates'); }
      else { setTimeout(function () { $('update-status').textContent = 'Up to date (browser preview)'; }, 600); }
    });

    // Smart Study setup (§5): install flow + built-in continue + engine install.
    function ssBind(id, fn) { var el = $(id); if (el) el.addEventListener('click', fn); }
    ssBind('btn-ss-install', ssInstall);
    ssBind('btn-ss-recheck', ssInstall);
    ssBind('btn-ss-setup', function () { setScreen('study'); setStudyTab('quiz'); ssInstall(); });
    ssBind('btn-ss-install-engine', function () {
      if (lpBridge.connected()) lpBridge.call('launch_ollama_installer');
      else toast('Preview mode — get Ollama from ollama.com/download');
    });
    ssBind('btn-ss-cancel', function () { if (lpBridge.connected()) lpBridge.call('cancel_smart_study'); });
    function ssContinue() {
      LP.state.ssDismissed = true;
      var b = $('smart-study-banner'); if (b) b.hidden = true;
    }
    ssBind('btn-ss-continue', ssContinue);
    ssBind('btn-ss-continue2', ssContinue);

    // home / import
    var dz = $('dropzone');
    dz.addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('browse_video'); else setOnb('drop');
    });
    $('btn-browse').addEventListener('click', function (e) {
      e.stopPropagation();
      if (lpBridge.connected()) lpBridge.call('browse_video'); else setOnb('drop');
    });
    dz.addEventListener('dragover', function (e) { e.preventDefault(); if (LP.state.onb !== 'detected') setOnb('drop'); });
    dz.addEventListener('drop', function (e) { e.preventDefault(); setOnb('detected'); });
    // "drop anywhere": in the desktop shell native drops are captured by Qt and
    // routed through backend.import_video, which drives the same overlay.
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) { e.preventDefault(); });

    $('btn-show-empty').addEventListener('click', function () { setJobsEmpty(true); });
    $('btn-load-jobs').addEventListener('click', function () { setJobsEmpty(false); });

    // Home grid: per-card menu buttons (delete / set group) take priority,
    // otherwise clicking a card opens the job.
    $('jobs-grid').addEventListener('click', function (e) {
      var btn = e.target.closest('.lp-jobbtn');
      if (btn) {
        e.stopPropagation();
        var id = btn.dataset.jobid;
        var job = LP.data.jobs.filter(function (x) { return x.id === id; })[0];
        if (!job) return;
        if (btn.dataset.action === 'delete') confirmDeleteJob(job);
        else if (btn.dataset.action === 'group') setJobGroup(job);
        return;
      }
      var act = e.target.closest('[data-jobact]');
      if (act) {
        e.stopPropagation();
        var aid = act.dataset.jobid, a = act.dataset.jobact;
        if (a === 'resume') { lpBridge.call('resume_job', aid); setScreen('process'); }
        else if (a === 'restart') { lpBridge.call('restart_job', aid); setScreen('process'); }
        else if (a === 'view') { lpBridge.call('open_job', aid); setScreen('process'); }
        else if (a === 'remove') {
          var jb = LP.data.jobs.filter(function (x) { return x.id === aid; })[0];
          if (jb) confirmDeleteJob(jb);
        }
        return;
      }
      var card = e.target.closest('[data-job]');
      if (!card) return;
      var running = card.querySelector('span[style*="animation:lpblink"]');
      if (lpBridge.connected()) lpBridge.call('open_job', card.dataset.job);
      setScreen(running ? 'process' : 'review');
    });

    // Processing queue controls (Run Now / reorder / remove).
    var queueList = $('queue-list');
    if (queueList) queueList.addEventListener('click', function (e) {
      var q = e.target.closest('[data-queueact]');
      if (!q) return;
      var qid = q.dataset.queueid, qa = q.dataset.queueact;
      var rows = (LP.data.queue && LP.data.queue.queue) || [];
      var idx = rows.map(function (r) { return r.id; }).indexOf(qid);
      if (qa === 'runnow') lpBridge.call('run_now', qid);
      else if (qa === 'remove') lpBridge.call('remove_from_queue', qid);
      else if (qa === 'up' && idx > 0) lpBridge.call('reorder_queue', qid, idx - 1);
      else if (qa === 'down' && idx >= 0) lpBridge.call('reorder_queue', qid, idx + 1);
    });

    // onboarding overlay
    $('onb-overlay').addEventListener('click', function (e) { if (e.target === this) setOnb(null); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-onb-close]'), function (b) {
      b.addEventListener('click', function () { setOnb(null); });
    });
    $('btn-onb-sample').addEventListener('click', function () { setOnb('detected'); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-onb-mode]'), function (el) {
      el.addEventListener('click', function () {
        Array.prototype.forEach.call(document.querySelectorAll('[data-onb-mode]'), function (o) {
          var on = o === el;
          o.style.cssText = on
            ? 'flex:1;text-align:center;font:700 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--orange);border-radius:9px;background:var(--orange-soft);color:var(--orange-ink);cursor:pointer'
            : 'flex:1;text-align:center;font:500 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--line);border-radius:9px;color:var(--muted);cursor:pointer';
        });
        LP.state.onbMode = el.dataset.onbMode;
      });
    });
    $('btn-start-processing').addEventListener('click', function () {
      setOnb(null);
      setScreen('process');
      // Reset any stale completion/pause UI from a prior run.
      var panel = $('proc-completion'); if (panel) panel.hidden = true;
      var pause = $('btn-pause-job'), resume = $('btn-resume-job'), dot = $('proc-status-dot');
      if (pause) { pause.hidden = false; pause.disabled = false; pause.textContent = 'Pause'; }
      if (resume) resume.hidden = true;
      if (dot) dot.style.animation = 'lpblink 1s infinite';
      lpBridge.call('start_processing', LP.state.onbMode || 'study');
    });

    // process
    $('btn-cancel-job').addEventListener('click', function () { lpBridge.call('cancel_job'); });
    (function () {
      var p = $('btn-pause-job'), r = $('btn-resume-job');
      if (p) p.addEventListener('click', function () { lpBridge.call('pause_job'); });
      if (r) r.addEventListener('click', function () { lpBridge.call('resume_job', ''); });
      var acts = {
        'cm-open-transcript': function () { setScreen('transcript'); },
        'cm-review-slides': function () { setScreen('review'); },
        'cm-start-studying': function () { setScreen('study'); },
        'cm-open-folder': function () { if (LP.state.completedJob) lpBridge.call('open_job_folder', LP.state.completedJob); },
        'cm-open-exports': function () { lpBridge.call('open_export_folder'); }
      };
      Object.keys(acts).forEach(function (id) {
        var b = $(id); if (b) b.addEventListener('click', acts[id]);
      });
    })();

    // review
    var strip = $('timeline-strip');
    // Portal the hover preview out of the timeline so it can never be clipped
    // by the timeline card's overflow.
    var scrubPv = $('scrub-preview');
    if (scrubPv && scrubPv.parentNode !== document.body) document.body.appendChild(scrubPv);
    strip.addEventListener('mousemove', onScrub);
    strip.addEventListener('mouseleave', hideScrub);
    // Position is stale once the layout shifts — hide on scroll/resize.
    window.addEventListener('resize', hideScrub);
    window.addEventListener('scroll', hideScrub, true);
    strip.addEventListener('click', function (e) {
      var t = e.target.closest('[data-slide]');
      if (t) { LP.state.viewingSlide = +t.dataset.slide; renderSlides(); }
    });
    $('slide-list').addEventListener('click', function (e) {
      var item = e.target.closest('[data-slide]');
      if (item) { LP.state.viewingSlide = +item.dataset.slide; renderSlides(); }
    });
    $('btn-prev-slide').addEventListener('click', function () {
      LP.state.viewingSlide = (LP.state.viewingSlide + LP.data.slides.length - 1) % LP.data.slides.length;
      renderSlides();
    });
    $('btn-next-slide').addEventListener('click', function () {
      LP.state.viewingSlide = (LP.state.viewingSlide + 1) % LP.data.slides.length;
      renderSlides();
    });
    $('btn-keep').addEventListener('click', function () {
      var s = LP.data.slides[LP.state.viewingSlide];
      s.state = 'accepted';
      lpBridge.call('set_slide_state', LP.state.viewingSlide, 'accepted');
      renderSlides();
    });
    $('btn-reject').addEventListener('click', function () {
      var s = LP.data.slides[LP.state.viewingSlide];
      s.state = 'rejected'; s.sel = false;
      lpBridge.call('set_slide_state', LP.state.viewingSlide, 'rejected');
      renderSlides();
    });
    $('btn-save-corrections').addEventListener('click', function () {
      var rows = document.querySelectorAll('#review-transcript [contenteditable]');
      var texts = Array.prototype.map.call(rows, function (r) { return r.textContent; });
      lpBridge.call('save_corrections', JSON.stringify(texts));
    });
    $('btn-repair').addEventListener('click', function () { lpBridge.call('repair_selection'); });

    // transcript
    $('btn-copy-transcript').addEventListener('click', function () {
      var text = LP.data.transcript.blocks.map(function (b) {
        var tmp = document.createElement('div'); tmp.innerHTML = b.html;
        return b.t + '  ' + tmp.textContent;
      }).join('\n\n');
      if (navigator.clipboard) navigator.clipboard.writeText(text);
    });

    // study
    Array.prototype.forEach.call(document.querySelectorAll('.lp-tab'), function (b) {
      b.addEventListener('click', function () { setStudyTab(b.dataset.tab); });
    });
    // Notes: debounced auto-save + copy.
    var _notesT = null;
    $('notes-area').addEventListener('input', function () {
      $('notes-status').textContent = 'Notes for this lecture · saving…';
      if (_notesT) clearTimeout(_notesT);
      _notesT = setTimeout(function () {
        if (lpBridge.connected()) lpBridge.call('save_notes', $('notes-area').value);
        $('notes-status').textContent = 'Notes for this lecture · saved';
      }, 600);
    });
    $('btn-copy-notes').addEventListener('click', function () {
      copyText($('notes-area').value, 'Notes copied');
    });
    $('topics-list').addEventListener('click', function (e) {
      var t = e.target.closest('[data-topic]');
      if (!t) return;
      LP.data.study.topics.forEach(function (tp, i) { tp.active = i === +t.dataset.topic; });
      LP.data.study.topicBlocks.forEach(function (b, i) { b.active = i === +t.dataset.topic; });
      renderStudy();
    });
    $('btn-send').addEventListener('click', sendChat);
    $('chat-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); sendChat(); }
    });
    // Quiz: one delegated handler over the JS-rendered #quiz-root.
    $('quiz-root').addEventListener('click', function (e) {
      var opt = e.target.closest('[data-opt]');
      if (opt && !opt.disabled) {
        if (!LP.state.quiz.answers.hasOwnProperty(LP.state.quiz.index)) {
          LP.state.quiz.pick = +opt.dataset.opt; renderQuiz();
        }
        return;
      }
      var seg = e.target.closest('[data-qset]');
      if (seg) {
        var v = seg.dataset.qval;
        LP.state.quiz.settings[seg.dataset.qset] = (seg.dataset.qset === 'count') ? +v : v;
        renderQuiz(); return;
      }
      var act = e.target.closest('[data-qact]');
      if (act) quizAction(act.dataset.qact, act);
    });
    $('quiz-root').addEventListener('change', function (e) {
      var act = e.target.closest('[data-qact="auto"]');
      if (act) quizAction('auto', act);
    });
    // Flashcards: one delegated handler over the JS-rendered #flash-root.
    $('flash-root').addEventListener('click', function (e) {
      var seg = e.target.closest('[data-fset]');
      if (seg) { LP.state.flash.settings[seg.dataset.fset] = (seg.dataset.fset === 'count') ? +seg.dataset.fval : seg.dataset.fval; renderCard(); return; }
      var act = e.target.closest('[data-fact]');
      if (act) flashAction(act.dataset.fact);
    });
    // Space/arrow keys drive the flashcard when the deck is on screen.
    window.addEventListener('keydown', function (e) {
      if (LP.state.screen !== 'study' || LP.state.studyTab !== 'flash') return;
      if (LP.state.flash.phase !== 'session') return;
      var tag = (e.target && e.target.tagName) || '';
      if (/INPUT|TEXTAREA/.test(tag)) return;
      if (e.key === ' ') { e.preventDefault(); flashAction('flip'); }
      else if (e.key === 'ArrowRight') flashAction('next');
      else if (e.key === 'ArrowLeft') flashAction('prev');
    });

    // exports
    $('export-formats').addEventListener('click', function (e) {
      var l = e.target.closest('[data-fmt]');
      if (!l) return;
      var f = LP.data.exportFormats[+l.dataset.fmt];
      f.sel = !f.sel;
      renderExportFormats();
    });
    $('btn-export-all').addEventListener('click', startExport);
    $('btn-export-again').addEventListener('click', function () { LP.state.exportPhase = 'idle'; renderExportPhase(); });
    $('btn-open-folder').addEventListener('click', function () { lpBridge.call('open_export_folder'); });
    $('btn-export-pdf').addEventListener('click', function () { lpBridge.call('export_one', 'pdf'); });
    $('btn-export-html').addEventListener('click', function () { lpBridge.call('export_one', 'html'); });

    // what's new / updates
    $('btn-whatsnew-close').addEventListener('click', hideWhatsNew);
    $('btn-update-later').addEventListener('click', hideWhatsNew);   // Remind me later
    $('btn-update-install').addEventListener('click', function () {
      var action = this.dataset.action || 'download';
      if (!lpBridge.connected()) { toast('Preview mode — updater needs the app'); return; }
      if (action === 'openpage') { lpBridge.call('open_release_page'); }
      else if (action === 'install') { lpBridge.call('install_downloaded_update'); }
      else { updSetPhase('downloading'); $('whatsnew-progress-label').textContent = 'Starting download…'; lpBridge.call('start_update_download'); }
    });
    $('btn-update-cancel').addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('cancel_update_download');
    });
    $('btn-update-github').addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('open_release_page');
    });
    $('btn-update-skip').addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('skip_update_version');
      hideWhatsNew();
    });
    // Updates settings: channel + auto-check + clear-skipped.
    Array.prototype.forEach.call(document.querySelectorAll('#update-channel-seg [data-channel]'), function (b) {
      b.addEventListener('click', function () {
        setUpdateChannel(b.dataset.channel);
        if (lpBridge.connected()) lpBridge.call('set_update_channel', b.dataset.channel);
      });
    });
    $('update-autocheck').addEventListener('change', function () {
      if (lpBridge.connected()) lpBridge.call('set_auto_check', this.checked ? 'true' : 'false');
    });
    $('btn-clear-skipped').addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('clear_skipped_version');
      $('update-skipped-row').hidden = true;
    });

    // Notifications settings: persist every toggle change as one prefs object.
    function collectNotifPrefs() {
      var prefs = {};
      Array.prototype.forEach.call(document.querySelectorAll('[data-notif]'), function (cb) {
        prefs[cb.dataset.notif] = cb.checked;
      });
      return prefs;
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-notif]'), function (cb) {
      cb.addEventListener('change', function () {
        if (lpBridge.connected()) lpBridge.call('set_notification_prefs', JSON.stringify(collectNotifPrefs()));
      });
    });
    var testBtn = $('btn-test-notification');
    if (testBtn) testBtn.addEventListener('click', function () {
      if (lpBridge.connected()) lpBridge.call('test_notification');
    });

    // keyboard shortcuts (prototype behavior)
    window.addEventListener('keydown', function (e) {
      var tag = (e.target && e.target.tagName) || '';
      var editing = /INPUT|TEXTAREA/.test(tag) || (e.target && e.target.isContentEditable);
      if (e.key === 'Escape') {
        setFocus(false); setOnb(null);
        if (!$('whatsnew-overlay').hidden) hideWhatsNew();
        return;
      }
      if (editing) return;
      var map = { 1: 'home', 2: 'process', 3: 'review', 4: 'transcript', 5: 'study', 6: 'exports', 7: 'settings' };
      if (map[e.key]) setScreen(map[e.key]);
      else if (e.key === 'f' || e.key === 'F') setFocus(!LP.state.focus);
    });
  }

  /* ======================= backend hookup ======================= */

  function wireBridge() {
    lpBridge.on('queue_changed', function (json) {
      try { LP.data.queue = JSON.parse(json); } catch (e) { return; }
      renderQueue();
    });
    lpBridge.on('pause_state', function (json) {
      var st; try { st = JSON.parse(json).state; } catch (e) { return; }
      var pause = $('btn-pause-job'), resume = $('btn-resume-job'),
          title = $('proc-status-title'), dot = $('proc-status-dot');
      if (st === 'pause_requested') {
        if (title) title.textContent = 'Finishing current step…';
        if (pause) { pause.disabled = true; pause.textContent = 'Pausing…'; }
      } else if (st === 'paused') {
        if (title) title.textContent = 'Paused';
        if (dot) dot.style.animation = 'none';
        if (pause) { pause.hidden = true; pause.disabled = false; pause.textContent = 'Pause'; }
        if (resume) resume.hidden = false;
      } else if (st === 'resumed') {
        if (dot) dot.style.animation = 'lpblink 1s infinite';
        if (pause) pause.hidden = false;
        if (resume) resume.hidden = true;
      }
    });
    lpBridge.on('job_completed', function (json) {
      var m; try { m = JSON.parse(json); } catch (e) { return; }
      LP.state.completedJob = m.job_id || '';
      var set = function (id, v) { var el = $(id); if (el) el.textContent = v; };
      set('cm-time', m.wall_time || '—');
      set('cm-words', (m.transcript_words != null ? m.transcript_words : '—'));
      set('cm-segments', (m.segment_count != null ? m.segment_count : '—'));
      set('cm-slides', (m.slides_detected != null ? m.slides_detected : '—'));
      var panel = $('proc-completion'); if (panel) panel.hidden = false;
      var pause = $('btn-pause-job'), resume = $('btn-resume-job');
      if (pause) pause.hidden = true;
      if (resume) resume.hidden = true;
    });
    lpBridge.on('notification_prefs', function (json) {
      var prefs; try { prefs = JSON.parse(json); } catch (e) { return; }
      Array.prototype.forEach.call(document.querySelectorAll('[data-notif]'), function (cb) {
        if (cb.dataset.notif in prefs) cb.checked = !!prefs[cb.dataset.notif];
      });
    });
    lpBridge.on('jobs_changed', function (json) { LP.data.jobs = JSON.parse(json); renderJobs(); });
    lpBridge.on('job_deleted', function (json) {
      var d = JSON.parse(json);
      toast(d.ok ? ('Lecture deleted · ' + (d.freed || '') + ' freed') : 'Delete failed');
    });
    lpBridge.on('pipeline_changed', function (json) {
      var p = JSON.parse(json);
      if (p.log) LP.data.pipeline.log = p.log;
      LP.data.pipeline.title = p.title || LP.data.pipeline.title;
      LP.data.pipeline.meta = p.meta || LP.data.pipeline.meta;
      LP.data.pipeline.stages = p.stages || LP.data.pipeline.stages;
      renderPipeline();
    });
    lpBridge.on('log_line', function (json) {
      LP.data.pipeline.log.push(JSON.parse(json));
      if (LP.data.pipeline.log.length > 500) LP.data.pipeline.log.shift();
      renderPipeline();
    });
    lpBridge.on('status_changed', function (json) {
      var s = JSON.parse(json);
      if (s.label !== undefined) $('status-label').textContent = s.label;
      if (s.pct !== undefined) { $('status-bar').style.width = s.pct + '%'; }
      if (s.detail !== undefined) $('status-pct').textContent = s.detail;
      if (s.right !== undefined) $('status-right').textContent = s.right;
      if (s.job !== undefined) { $('side-job-name').textContent = s.job; $('crumb-job').textContent = s.job; }
      if (s.side !== undefined) $('side-job-status').innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:var(--orange);animation:lpblink 1s infinite"></span>' + esc(s.side);
    });
    lpBridge.on('slides_changed', function (json) {
      var d = JSON.parse(json);
      LP.data.slides = d.slides || LP.data.slides;
      if (d.duration) LP.data.duration = d.duration;
      if (d.durationMid) LP.data.durationMid = d.durationMid;
      if (LP.state.viewingSlide >= LP.data.slides.length) LP.state.viewingSlide = 0;
      hideScrub();  // job changed — drop any stale hover preview
      renderSlides();
    });
    lpBridge.on('transcript_changed', function (json) {
      var d = JSON.parse(json);
      if (d.reviewSegments) { LP.data.reviewSegments = d.reviewSegments; renderReviewTranscript(); }
      if (d.transcript) { LP.data.transcript = d.transcript; renderTranscript(); }
    });
    lpBridge.on('study_changed', function (json) {
      LP.data.study = JSON.parse(json); renderStudy();
      var na = $('notes-area');
      if (na && document.activeElement !== na) na.value = LP.data.study.notes || '';
    });
    lpBridge.on('quiz_changed', function (json) {
      var d = JSON.parse(json), q = LP.state.quiz;
      LP.data.quiz = { questions: d.questions || [], provider: d.provider || '', model: d.model || '', meta: d.meta || {} };
      if (d.session && typeof d.session === 'object' && Object.keys(d.session).length) {
        q.index = d.session.index || 0; q.answers = d.session.answers || {}; q.flags = d.session.flags || {};
        q.autoAdvance = !!d.session.autoAdvance; q.phase = d.session.phase === 'summary' ? 'summary' : 'session';
      } else {
        q.index = 0; q.pick = null; q.answers = {}; q.flags = {}; q.phase = 'session';
      }
      stopGen('quiz');
      renderQuiz();
    });
    lpBridge.on('quiz_status', function (json) {
      var d = JSON.parse(json), q = LP.state.quiz;
      q.status = d.message || '';
      if (d.state === 'ready' || d.state === 'error' || d.state === 'cancelled') stopGen('quiz');
      if (d.state === 'error') { toast(d.message || 'Quiz failed'); renderQuiz(); }
    });
    lpBridge.on('flashcards_changed', function (json) {
      var d = JSON.parse(json), f = LP.state.flash;
      LP.data.flashcards = { cards: d.cards || [], provider: d.provider || '', model: d.model || '', meta: d.meta || {} };
      if (d.session && typeof d.session === 'object' && Object.keys(d.session).length) {
        f.index = d.session.index || 0; f.known = d.session.known || {}; f.unsure = d.session.unsure || {};
        f.bookmarks = d.session.bookmarks || {}; f.order = d.session.order || []; f.phase = 'session';
      } else {
        f.index = 0; f.flipped = false; f.known = {}; f.unsure = {}; f.bookmarks = {}; f.order = []; f.phase = 'session';
      }
      stopGen('flash');
      renderCard();
    });
    lpBridge.on('flashcards_status', function (json) {
      var d = JSON.parse(json), f = LP.state.flash;
      f.status = d.message || '';
      if (d.state === 'ready' || d.state === 'error' || d.state === 'cancelled') stopGen('flash');
      if (d.state === 'error') { toast(d.message || 'Flashcards failed'); renderCard(); }
    });
    lpBridge.on('export_progress', function (json) {
      var p = JSON.parse(json);
      LP.state.exportPhase = 'running'; renderExportPhase();
      $('export-progress-bar').style.width = (p.pct || 0) + '%';
      $('export-progress-label').textContent = p.label || '';
    });
    lpBridge.on('export_done', function (json) {
      var d = JSON.parse(json);
      LP.data.exportFiles = d.files || LP.data.exportFiles;
      LP.state.exportPhase = 'done'; renderExportPhase();
      if (d.meta) $('export-done-meta').textContent = d.meta;
    });
    lpBridge.on('ai_token', function (text) { appendAiText(text, false); });
    lpBridge.on('ai_done', function () {
      LP.state.streaming = false; renderChat();
    });
    lpBridge.on('groq_status', function (json) {
      var d = JSON.parse(json), el = $('groq-status');
      if (el) { el.textContent = d.message || ''; el.style.color = d.has_key ? 'var(--secondary-text)' : 'var(--muted)'; }
      if (d.backend && typeof reflectBackend === 'function') reflectBackend(d.backend);
    });
    lpBridge.on('vulkan_status', function (json) {
      var d = JSON.parse(json), el = $('vulkan-status');
      if (!el) return;
      el.textContent = d.message || '';
      el.style.color = (d.state === 'loaded' || d.state === 'available') ? 'var(--secondary-text)'
        : (d.state === 'unavailable' || d.state === 'error') ? 'var(--muted)' : 'var(--muted)';
    });
    lpBridge.on('cuda_status', function (json) {
      var d = JSON.parse(json), el = $('cuda-status');
      if (!el) return;
      el.textContent = d.message || '';
      el.style.color = (d.state === 'loaded' || d.state === 'available') ? 'var(--secondary-text)' : 'var(--muted)';
    });
    lpBridge.on('cuda_pack', function (json) {
      var d; try { d = JSON.parse(json); } catch (e) { return; }
      var box = $('cuda-pack'); if (!box) return;
      var st = d.state;
      var busy = st === 'downloading' || st === 'verifying' || st === 'installing';
      // Offer the pack only on an NVIDIA machine that hasn't installed it yet.
      var show = d.gpu_present && (!d.installed || busy || st === 'error' || st === 'cancelled');
      box.hidden = !show;
      if (!show) return;
      $('cuda-pack-progress').hidden = !busy;
      $('btn-cuda-pack-install').disabled = busy;
      var note = $('cuda-pack-note');
      if (st === 'downloading') {
        $('cuda-pack-bar').style.width = (d.percent || 0) + '%';
        $('cuda-pack-label').textContent = 'Downloading… ' + (typeof d.percent === 'number' ? Math.round(d.percent) + '%' : '');
        note.textContent = '';
      } else if (busy) {
        $('cuda-pack-label').textContent = d.message || 'Working…';
      } else if (st === 'ready') {
        box.hidden = true; toast('CUDA acceleration installed');
      } else if (st === 'error') {
        note.textContent = d.message || 'Failed'; note.style.color = 'var(--red)';
      } else if (st === 'cancelled') {
        note.textContent = d.message || 'Cancelled'; note.style.color = 'var(--muted)';
      } else {
        note.textContent = d.size_label ? ('Optional · ' + d.size_label + ' · NVIDIA only') : '';
        note.style.color = 'var(--muted)';
      }
    });
    lpBridge.on('ai_status', function (json) {
      var s = JSON.parse(json);
      var lbl = s.label || 'Built-in Study';
      var builtin = lbl === 'Built-in Study';
      var err = lbl === 'AI error';
      var txt = lbl + (s.model && s.model !== '—' && !builtin ? ' · ' + s.model : '');
      var col = builtin ? 'var(--secondary-text)' : (err ? 'var(--muted)' : 'var(--green)');
      $('ai-status').style.color = col; $('ai-status').style.borderColor = col;
      $('ai-status').innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:' + col + '"></span>' + esc(txt);
      if (s.model) $('ai-model-name').textContent = s.model;
    });
    lpBridge.on('smart_study', function (json) {
      try { renderSmartStudy(JSON.parse(json)); } catch (e) { console.error('smart_study', e); }
    });
    lpBridge.on('onboarding', function (json) {
      var d = JSON.parse(json);
      if (d.name) $('onb-file-name').textContent = d.name;
      if (d.meta) $('onb-file-meta').textContent = d.meta;
      setScreen('home');
      setOnb('detected');
    });
    lpBridge.on('update_available', function (json) { showWhatsNew(JSON.parse(json), 'available'); });
    lpBridge.on('update_progress', function (pct) {
      if ($('whatsnew-overlay').hidden) $('whatsnew-overlay').hidden = false;
      if (LP.state.updatePhase !== 'downloading') updSetPhase('downloading');
      $('whatsnew-progress-bar').style.width = pct + '%';
      $('whatsnew-progress-label').textContent = pct >= 100 ? 'Verifying…' : 'Downloading update… ' + Math.round(pct) + '%';
    });
    lpBridge.on('update_ready', function () {
      // update_state 'ready' already reconfigured the buttons; this is a backstop.
      if (LP.state.updatePhase !== 'ready') updSetPhase('ready');
    });
    lpBridge.on('update_error', function (msg) {
      updSetPhase(LP.state.updateMode === 'installed' ? 'installed' : 'available');
      updMsg(String(msg), 'error');
      $('update-status').textContent = 'Update failed: ' + msg;
    });
    lpBridge.on('update_state', function (json) {
      var d; try { d = JSON.parse(json); } catch (e) { return; }
      var phase = d.phase;
      if (phase === 'checking') { $('update-status').textContent = 'Checking…'; }
      else if (phase === 'uptodate') { $('update-status').textContent = d.message || 'You’re up to date'; }
      else if (phase === 'downloading') {
        if ($('whatsnew-overlay').hidden) $('whatsnew-overlay').hidden = false;
        updSetPhase('downloading'); updMsg('');
        $('whatsnew-progress-label').textContent = 'Downloading ' + (d.filename || 'update') + '…';
      }
      else if (phase === 'verifying') { updSetPhase('verifying'); $('whatsnew-progress-label').textContent = 'Verifying…'; }
      else if (phase === 'ready') { updSetPhase('ready'); updMsg(d.message || 'Verified and ready to install.'); }
      else if (phase === 'blocked') { updSetPhase('blocked'); updMsg(d.message, 'error'); }
      else if (phase === 'portable') { updSetPhase('portable'); updMsg('This is a portable build — open the download page to get the new version.'); }
      else if (phase === 'cancelled') { updSetPhase('available'); updMsg(d.message || 'Download cancelled.'); }
      else if (phase === 'error') {
        updSetPhase(LP.state.updateMode === 'installed' ? 'installed' : 'available');
        updMsg(d.message, 'error');
        if (d.stage === 'check' || d.manual) $('update-status').textContent = d.message || 'Unable to check right now';
      }
    });
    lpBridge.on('whatsnew', function (json) { showWhatsNew(JSON.parse(json), 'installed'); });
    lpBridge.on('settings_changed', function (json) {
      var s = JSON.parse(json);
      if (s.theme) setTheme(s.theme);
      if (s.version) { LP.data.version = s.version; $('app-version').textContent = s.version; }
      if (s.model_path) $('setting-model-path').textContent = s.model_path;
      if (s.endpoint) {
        var ep = $('ai-endpoint-url');
        if (ep && document.activeElement !== ep) ep.value = s.endpoint;
      }
      if (s.engine) reflectEngine(s.engine);
      if (s.transcription_backend && typeof reflectBackend === 'function') reflectBackend(s.transcription_backend);
      if (s.ollama_model) {
        $('ai-model-name').textContent = s.ollama_model;
        var msel = $('ai-model-select');
        if (msel && msel.querySelector('option[value="' + s.ollama_model + '"]')) msel.value = s.ollama_model;
      }
      if (s.actual_backend) $('status-right').textContent = s.actual_backend;
      if (s.export_dir) $('export-dir').textContent = s.export_dir;
      if (s.update_status) $('update-status').textContent = s.update_status;
    });
    lpBridge.on('ollama_models', function (json) {
      var d = JSON.parse(json), sel = $('ai-model-select');
      if (!sel) return;
      if (!d.available) {
        sel.innerHTML = '<option value="">Ollama unavailable — ' + esc(d.error || 'not reachable') + '</option>';
        return;
      }
      var models = d.models || [];
      if (!models.length) { sel.innerHTML = '<option value="">no models installed</option>'; return; }
      sel.innerHTML = models.map(function (m) {
        var bits = [m.parameter_size, m.quantization_level].filter(Boolean).join(' ');
        var label = m.name + (bits ? '  ·  ' + bits : '');
        return '<option value="' + esc(m.name) + '"' + (m.name === d.selected ? ' selected' : '') + '>' + esc(label) + '</option>';
      }).join('');
      if (d.selected) sel.value = d.selected;
    });

    lpBridge.ready(function (backend) {
      if (backend && backend.list_ollama_models) lpBridge.call('list_ollama_models');
      if (backend && backend.get_bootstrap) {
        lpBridge.call('get_bootstrap').then(function (json) {
          if (!json) return;
          try {
            var b = JSON.parse(json);
            if (b.theme) setTheme(b.theme);
            if (b.version) { LP.data.version = b.version; $('app-version').textContent = b.version; }
          } catch (e) { console.error('bootstrap parse', e); }
        });
      }
    });
  }

  /* ======================= boot ======================= */

  function boot() {
    renderJobs();
    renderPipeline();
    renderSlides();
    renderReviewTranscript();
    renderTranscript();
    renderStudy();
    renderChat();
    renderQuiz();
    renderExportFormats();
    renderExportPhase();
    setScreen('home');
    setTheme('dark');           // dark by default (design decision)
    setStudyTab('chat');
    wire();
    wireBridge();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
