/* LecturePack app logic — ported 1:1 from the Claude Design prototype (LecturePack.dc.html).
   State model, keyboard shortcuts, focus mode, timeline scrub, study tabs, chat streaming,
   quiz, flashcards, import flow and export state machine all match the prototype.
   Data flows through LP.data; the Python backend replaces the demo payloads via lpBridge. */

(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  // One guarded indirection keeps feature stores consistent and preserves a
  // single place to substitute storage in renderer-level tests.
  var browserStorage = function () { return window.localStorage; };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  function parseBridgePayload(value, fallback) {
    if (value && typeof value === 'object') return value;
    try {
      var parsed = JSON.parse(value == null ? '' : value);
      return parsed == null ? (fallback === undefined ? {} : fallback) : parsed;
    } catch (e) {
      return fallback === undefined ? {} : fallback;
    }
  }

  // Shared import-state helpers: used by the home import handlers (wire) and
  // the bridge onboarding listener (wireBridge).
  var importingFile = null;
  function setImporting(on, name) {
    LP.state.importing = !!on;
    var el = $('home-importing'), nm = $('importing-name');
    if (el) el.hidden = !on;
    if (nm && name) nm.textContent = name;
  }

  /* ======================= demo session model =======================
     This reducer deliberately contains no DOM or bridge calls. The
     self-contained demo screen owns presentation; this model only rejects
     stale start/stop events from the real bundled-lecture hand-off. */
  function GuidedDemoSessionModel() {
    var operationId = '', sessionId = '', active = false, status = 'idle', stage = '', progress = 0, error = '', terminal = false, attempt = 0;
    function snapshot() { return { operationId: operationId, sessionId: sessionId, active: active, status: status, stage: stage, progress: progress, error: error, terminal: terminal, attempt: attempt }; }
    function same(event) { return !!(event && event.operation_id && event.session_id && event.operation_id === operationId && event.session_id === sessionId); }
    function sameResult(result) { return !!(result && result.operation_id === operationId && result.session_id === sessionId); }
    return {
      starting: function () {
        // A retry is a genuinely new local attempt. Clearing the old backend
        // identity prevents its terminal state from poisoning the retry, while
        // the incremented token lets promise callbacks prove they still belong.
        attempt += 1; operationId = ''; sessionId = ''; active = true; terminal = false;
        status = 'starting'; stage = 'prepare'; progress = 0; error = '';
        return snapshot();
      },
      isCurrentAttempt: function (token, expectedOperationId, expectedSessionId) {
        if (token !== attempt) return false;
        if (expectedOperationId && operationId !== expectedOperationId) return false;
        if (expectedSessionId && sessionId !== expectedSessionId) return false;
        return true;
      },
      started: function (result, token) {
        // The backend may emit a live `started` event before this slot result
        // reaches JS. A delayed result must never revive a session that was
        // cancelled/cleaned in the meantime, overwrite live progress, or swap
        // the identity adopted from that event.
        if (token !== undefined && token !== attempt) return snapshot();
        if (terminal || status === 'cancelling') return snapshot();
        if (!result || !result.ok || !result.operation_id || !result.session_id) {
          if (!operationId && status === 'starting') { active = false; status = 'error'; error = result && result.error || 'Could not start the guided demo.'; }
          return snapshot();
        }
        if (operationId || sessionId) {
          // Same identity is an idempotent duplicate; a different identity is
          // a stale slot completion and is rejected by leaving state untouched.
          if (!sameResult(result)) return snapshot();
          return snapshot();
        }
        operationId = result.operation_id; sessionId = result.session_id; active = true; terminal = false; status = 'started'; return snapshot();
      },
      event: function (event) {
        if (terminal || !same(event)) return { accepted: false, state: snapshot() };
        status = event.status || status;
        if (event.stage !== undefined) stage = event.stage;
        if (typeof event.progress === 'number') progress = Math.max(0, Math.min(100, event.progress));
        if (event.error) error = event.error;
        if (status === 'cleaned') { active = false; terminal = true; status = 'ended'; }
        else if (status === 'failed') { active = false; terminal = true; }
        return { accepted: true, state: snapshot() };
      },
      cancelling: function () { if (active) status = 'cancelling'; return snapshot(); },
      settleEndResult: function (result, token, expectedOperationId, expectedSessionId) {
        // A terminal UI state is monotonic for this operation. In particular,
        // a start slot completion may arrive after an idempotent end response.
        if (token !== undefined && token !== attempt) return snapshot();
        if (expectedOperationId && operationId !== expectedOperationId) return snapshot();
        if (expectedSessionId && sessionId !== expectedSessionId) return snapshot();
        if (terminal) return snapshot();
        if (!result || result.ok !== true) {
          active = false; terminal = true; status = 'error';
          error = result && result.error || 'Could not confirm that the demo stopped. Try again.';
          return snapshot();
        }
        if (result.status === 'not_running' || result.status === 'cleaned' || result.status === 'ended') {
          active = false; terminal = true; status = 'ended'; error = '';
          return snapshot();
        }
        if (result.status === 'cancelling') return snapshot();
        active = false; terminal = true; status = 'error';
        error = 'The demo stop request returned an unexpected response. Try again.';
        return snapshot();
      },
      snapshot: snapshot
    };
  }

  function SlideDetectionPresetModel() {
    var selected = 'balanced';
    var presets = { low: 'conservative', balanced: 'balanced', high: 'detailed' };
    function labelFor(value) {
      var normalized = String(value || '').toLowerCase();
      if (Object.prototype.hasOwnProperty.call(presets, normalized)) return normalized;
      return Object.keys(presets).filter(function (label) { return presets[label] === normalized; })[0] || 'balanced';
    }
    function snapshot() { return { label: selected, preset: presets[selected] }; }
    return {
      select: function (label) { selected = labelFor(label); return snapshot(); },
      reflect: function (preset) { selected = labelFor(preset); return snapshot(); },
      snapshot: snapshot
    };
  }
  /* ===================== demo session model end ===================== */
  window.LPDemoSessionModel = GuidedDemoSessionModel;
  window.LPSlideDetectionPresetModel = SlideDetectionPresetModel;

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
  var CHECK_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--on-signal)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  /* ======================= demo data (design content) =======================
     Everything below is DESIGN-TIME content for the static screenshot pipeline
     and for opening app/ui/index.html with no backend. It is opt-in: without
     ?preview=1 the job list starts empty and boot() blanks the whole workspace,
     so a real launch can never show a lecture that does not exist. See BUG-15.
     ------------------------------------------------------------------------ */
  var PREVIEW = (function () {
    try { return /[?&]preview=1(&|$)/.test(location.search); }
    catch (e) { return false; }        // no location (odd host) -> not preview
  })();

  var LP = window.LP = {
    state: {
      // jobId owns the workspace: Process/Review/Transcript/Study render the
      // data belonging to THIS lecture. '' means nothing is loaded, and the
      // workspace renders structurally empty rather than showing whatever the
      // backend last happened to push.
      jobId: '', jobTitle: '',
      // Home multi-select: an explicit mode, so a plain click still opens.
      selecting: false, selected: {},
      screen: 'home', theme: 'dark', focus: false, onb: null, jobsEmpty: false,
      onbMode: 'study', onbSens: 'balanced', setupJobId: '', importing: false,
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
      // "All slides" tile size: s/m/l are three visibly different stops, unlike
      // the Compact/Roomy pair they replace. Remembered across sessions.
      slideSize: (function () {
        try {
          var saved = browserStorage().getItem('lecturepack.slideSize');
          return ['s', 'm', 'l'].indexOf(saved) >= 0 ? saved : 'm';
        } catch (e) { return 'm'; }
      })(),

      updateInfo: null,
      smartStudy: null,   // last smart_study payload
      ssPreset: null,     // user-chosen preset (defaults to recommendation)
      ssDismissed: false, // user chose "Continue with Built-in Study"

      // D-08: true while a NORMAL (non-demo) job is actively processing. Set
      // from pipeline_changed (a stage is not yet done), cleared on the
      // terminal status_changed label (Done/Failed). Sibling to the guided
      // demo's own lock so a running job's snapshotted settings can never be
      // changed out from under it mid-run.
      pipelineRunning: false,
      // The job currently processing (driven by the backend active_job signal
      // and terminal status events). This is deliberately separate from
      // jobId, which is the job the user is VIEWING: a new processing job
      // must never prevent the user from opening an older completed job.
      activeJobId: '',
      // Live-log following: true while the user stays at the bottom; cleared
      // when they scroll up and restored by the Latest button.
      logFollow: true
    },
    data: {
      // Populated from Electron's packaged app metadata by loadAppVersion().
      // An empty value is intentional: the renderer must never invent a
      // release number when it is running outside the desktop shell.
      version: '',
      // BUG-07: these three demo lectures exist ONLY so the static screenshot
      // pipeline and a bare `python -m http.server app/ui` have something to
      // render. In the packaged app a live bridge overwrites them on the first
      // jobs_changed, so they were never user-visible -- but shipping fake job
      // data that is one bridge-failure away from appearing is a foot-gun, and
      // it already cost a false positive once (a DOM scan matched
      // `egypt_excerpt` after the markup had been cleaned).
      // Now opt-in: only seeded when the URL carries ?preview=1.
      jobs: (function () {
        if (!PREVIEW) return [];
        return [
          { name: 'egypt_excerpt', file: 'egypt_excerpt.m4v', meta: '06:12 · 14 slides · Jul 16', status: 'done' },
          { name: 'm2-res_1080p', status: 'running', pct: 62, stage: 'Transcribe', eta: '~3m' },
          { name: 'synthetic_lecture', file: 'synthetic_lecture.mp4', meta: '00:30 · 3 slides · Jul 15', status: 'done' }
        ];
      })(),
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
        summary: 'A tour of the Great Pyramid of Giza — how Khufu\'s builders laid a foundation level to two centimeters, aligned it to true north without a compass, and moved 2.3 million stone blocks around 2560 BC.',
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
    },
    // Per-lecture workspace store, keyed by job id. LP.data.<blob> is the live
    // VIEW of LP.state.jobId; switching lectures saves the outgoing blobs here
    // and loads the incoming ones, so switching back is instant and no lecture
    // can ever paint over another.
    byJob: {}
  };

  /* ======================= motion module (LP.motion) =======================
     Small, self-contained motion helpers. See scratchpad MOTION_CONTRACT.md.
     Every entry point is null-safe: missing elements or a reduced-motion OS
     setting degrade to the plain, instant behavior with no thrown errors. */
  var _rmMql = (function () {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)'); }
    catch (e) { return null; }
  })();
  LP.motion = {
    reduced: function () {
      return !!(_rmMql && _rmMql.matches);
    },
    // Navigation wrapper. Signature unchanged: nav(fn) runs fn once.
    //
    // The document.startViewTransition() path was REMOVED 2026-07-27. It is now
    // a synchronous call, deliberately:
    //   - No element ever set `view-transition-name`, so there were never any
    //     shared-element transitions to gain; the layer was root-only.
    //   - The UA's default root transition IS a full-page crossfade, which was
    //     precisely the page-level flash being removed (it stacked a 0 -> 1
    //     opacity ramp on top of the screen rule's own ramp).
    //   - Its callback fires ASYNCHRONOUSLY, which is what made indicator()
    //     measure the previously-active nav button.
    // Kept as a wrapper rather than inlined so setScreen() and any future
    // caller keep one place to hook screen-change motion.
    nav: function (fn) {
      fn();
    },
    // Positions the sidebar rail. Sets --ind-y (travel) and --ind-s (scale),
    // both consumed by a single transform in .lp-nav-ind -- it used to set
    // --ind-h and transition `height`, which is not compositable and was a
    // no-op anyway because every nav button is one line of identical height.
    // The rail's CSS base height is 36px; --ind-s scales that on Y only.
    indicator: function () {
      var ind = document.querySelector('.lp-nav-ind');
      var active = document.querySelector('.lp-nav-list .lp-nav.active');
      if (!ind || !active) return;
      var h = active.offsetHeight || 36;
      ind.style.setProperty('--ind-y', active.offsetTop + 'px');
      ind.style.setProperty('--ind-s', (h / 36).toFixed(4));
      ind.classList.add('on');
    },
    // Reusable exit-motion close. `cls` defaults to 'out' (scrim/pop overlays);
    // pass 'lp-out' for the focus pill or any other single-element exit.
    // Reduced motion / missing element -> done() fires immediately. Guards
    // against double-invocation so `done` (typically a remove/hide) never
    // runs twice, and falls back to `done`/`el.remove()` if anything throws.
    close: function (el, done, cls) {
      cls = cls || 'out';
      if (!done) done = function () { if (el) el.remove(); };
      if (LP.motion.reduced() || !el) { done(); return; }
      var finished = false, timer = null;
      function finish() {
        if (finished) return;
        finished = true;
        if (timer) clearTimeout(timer);
        // The 300ms fallback is never cancelled by a REOPEN, only by this
        // guard. Reopening a persistent element (#focus-pill, #onb-overlay,
        // #whatsnew-overlay) within that window used to let the previous
        // close's timer fire and run ITS done() -- e.g. `hidden = true` on an
        // element the user had just reopened, with no user action, up to 300ms
        // later. `finished` cannot catch that: it is per-invocation, and the
        // stale call is a DIFFERENT invocation with its own flag.
        // A reopen removes the close class, so its absence means "superseded".
        if (el && el.classList && !el.classList.contains(cls)) return;
        done();
      }
      try {
        el.classList.add(cls);
        var pop = el.querySelector && el.querySelector('.lp-pop');
        if (pop) pop.classList.add(cls);
        el.addEventListener('animationend', finish, { once: true });
        timer = setTimeout(finish, 300);
      } catch (e) {
        finish();
      }
    }
  };

  /* ================= workspace ownership (job-scoped state) =================
     The workspace screens (Process/Review/Transcript/Study/Exports) used to
     read one global scratchpad that was seeded with demo content, overwritten
     by whatever the backend last pushed, and never cleared -- so with no
     lecture loaded they showed a mix of stale and half-loaded data from earlier
     jobs. Now a single owner (LP.state.jobId) decides what they render, and
     "nothing loaded" is structurally empty rather than merely uncleaned. */

  // The blobs that belong to one lecture. Anything NOT listed here is app-wide
  // (theme, settings, export format choices) and must survive a job switch.
  var WORKSPACE_KEYS = ['pipeline', 'slides', 'transcript', 'study',
                        'quiz', 'flashcards', 'exportFiles', 'reviewSegments'];

  function emptyWorkspace() {
    return {
      pipeline: { title: 'No lecture loaded', meta: '', stages: [], log: [] },
      slides: [],
      reviewSegments: [],
      transcript: { title: '', duration: '', segments: 0, corrections: 0, blocks: [] },
      study: {
        topics: [], topicBlocks: [], topicLabels: [], keyTerms: [],
        bookmarks: [], stats: [], cards: []
      },
      quiz: { questions: [], provider: '', model: '', meta: {} },
      flashcards: { cards: [], provider: '', model: '', meta: {} },
      exportFiles: []
    };
  }

  function snapshotWorkspace() {
    var snap = {};
    WORKSPACE_KEYS.forEach(function (k) { snap[k] = LP.data[k]; });
    return snap;
  }

  function applyWorkspace(snap) {
    WORKSPACE_KEYS.forEach(function (k) { LP.data[k] = snap[k]; });
  }

  // Per-job live status memory. status_changed / pipeline_changed payloads for
  // jobs other than the one being viewed are accumulated here (and in the
  // per-job workspace blob below) so switching back shows the latest state
  // without waiting for a new event.
  var statusByJob = {};
  var runningByJob = {};
  // The last processing job the UI auto-followed (once per new active job).
  // Manual job selection never resets it, so a running job cannot re-yank the
  // view; a genuinely new active job id triggers the single follow.
  var autoSelectedActiveId = '';

  function workspaceFor(jobId) {
    if (!jobId) return null;
    if (!LP.byJob[jobId]) LP.byJob[jobId] = emptyWorkspace();
    return LP.byJob[jobId];
  }

  /* Route a job-scoped event to the workspace it belongs to. Returns true
     when the payload targets the job being viewed (the caller re-renders),
     false when it was accumulated for a different job's store. */
  function routeJobPayload(payload, apply) {
    var owner = payload && payload.job;
    if (!owner) { apply(LP.data); return true; }
    if (owner === LP.state.jobId) { apply(LP.data); return true; }
    apply(workspaceFor(owner)); return false;
  }

  /* Switch which lecture the workspace belongs to. Driven by the backend's
     active_job signal -- the UI never invents a job identity. */
  function setActiveJob(id, title) {
    id = id || '';
    if (id === LP.state.jobId) {
      if (title && !looksLikeJobId(title)) LP.state.jobTitle = title;
      if (!LP.state.jobTitle) LP.state.jobTitle = friendlyJobName(id);
      renderJobChrome();
      return;
    }
    if (LP.state.jobId) LP.byJob[LP.state.jobId] = snapshotWorkspace();
    LP.state.jobId = id;
    LP.state.jobTitle = '';
    LP.state.jobTitle = title && !looksLikeJobId(title) ? title : friendlyJobName(id);
    applyWorkspace(id && LP.byJob[id] ? LP.byJob[id] : emptyWorkspace());
    // Per-lecture view state must not leak across lectures either.
    LP.state.chat = [];
    LP.state.quiz.phase = 'setup';
    LP.state.quiz.index = 0;
    LP.state.quiz.answers = {};
    LP.state.quiz.flags = {};
    LP.state.exportPhase = 'idle';
    // Chrome first: it names the lecture, and it must not be collateral damage
    // if a workspace renderer throws on unusual data.
    renderJobChrome();
    renderProcOptions();
    renderWorkspace();
    // Per-job live state: the sidebar/status readouts and the pipelineRunning
    // lock belong to the VIEWED job, not to whichever job happens to be
    // processing in the background.
    LP.state.pipelineRunning = !!runningByJob[id];
    if (id && statusByJob[id]) {
      pendingProcessingStatus = Object.assign({}, statusByJob[id]);
      lastStatusRenderKey = null;
      scheduleProcessingRender('status');
    } else {
      pendingProcessingStatus = {};
      lastStatusRenderKey = null;
    }
    renderJobSwitcher();
    renderProcessJobState();
    // F-3: settle every status readout to the restored job's terminal state.
    // On relaunch or a job switch no live pipeline events will ever arrive
    // for a completed/failed/cancelled lecture, so paint its final state now
    // instead of leaving whatever the previous job left behind.
    var restored = (LP.data.jobs || []).filter(function (j) { return j && j.id === id; })[0];
    if (restored && restored.status === 'done') settleTerminalStatus('complete');
    if (restored && restored.status === 'done') {
      if (completionInfo[id]) applyCompletionPanel(completionInfo[id]);
      else { var panel = $('proc-completion'); if (panel) panel.hidden = true; }
    }
    else if (restored && restored.status === 'failed') settleTerminalStatus('failed');
    else if (restored && restored.status === 'cancelled') settleTerminalStatus('cancelled');
    else if (restored && restored.status === 'interrupted') settleTerminalStatus('interrupted');
    else if (restored && !id) settleTerminalStatus('idle');
    else if (restored) {
      // A live (queued/running/paused) job: clear the previous job's terminal
      // readouts; real pipeline events take over from here.
      var liveLabel = $('status-state'); if (liveLabel) liveLabel.textContent = 'Idle';
      setFill('status-bar', 0);
      setStatusDotText($('side-job-status'), restored.status === 'running' ? 'Processing' : 'Queued', 'var(--orange)', restored.status === 'running');
    }
  }

  /* Reject a payload that belongs to a lecture other than the active one.
     Without this, a slow signal from the PREVIOUS job lands after a switch and
     silently repaints its data over the new lecture. An unstamped payload (or
     one arriving while a job is loading) is accepted for compatibility. */
  function ownsPayload(p) {
    if (!p || typeof p !== 'object') return true;
    var owner = p.job;
    if (!owner) return true;                 // unstamped -- legacy/app-wide
    if (!LP.state.jobId) {                   // first data for a fresh load
      LP.state.jobId = owner;
      return true;
    }
    return owner === LP.state.jobId;
  }

  function renderWorkspace() {
    renderPipeline();
    renderSlides();
    renderReviewTranscript();
    renderTranscript();
    renderStudy();
    renderChat();
    renderQuiz();
    renderExportPhase();
  }

  /* Sidebar chip + breadcrumb: name the lecture the workspace is scoped to, so
     content is never anonymous. Idle when nothing is loaded. */
  function renderJobChrome() {
    var name = LP.state.jobTitle || '';
    if (!LP.state.jobId) {
      resetJobChrome();
      return;
    }
    $('side-job-name').textContent = name || 'Untitled lecture';
    $('crumb-job').textContent = name || 'Lecture';
    renderSidePoster(LP.state.jobId);
  }

  /* The sidebar chip showed a generic icon even once a lecture was loaded.
     Reuse the same poster the job cards use; the icon stays underneath as the
     fallback while the poster generates (or if the job has no frame at all). */
  function renderSidePoster(jobId) {
    var img = $('side-job-poster'), ph = $('side-job-thumb');
    if (!img) return;
    var placeholder = ph && ph.querySelector('[data-side-ph]');
    if (!jobId) {
      img.hidden = true; img.style.opacity = 0; img.removeAttribute('src');
      if (placeholder) placeholder.hidden = false;
      return;
    }
    if (img.getAttribute('data-for') === jobId && !img.hidden) return;
    img.setAttribute('data-for', jobId);
    img.hidden = false;
    img.style.opacity = 0;
    if (placeholder) placeholder.hidden = false;
    img.onload = function () {
      img.style.opacity = 1;
      if (placeholder) placeholder.hidden = true;
    };
    img.onerror = function () {
      // no poster yet: keep the icon, and let the next list refresh retry
      img.hidden = true;
      if (placeholder) placeholder.hidden = false;
    };
    img.src = posterSrc(jobId, 0);
  }

  /* ======================= renderers ======================= */

  /* ---- lightweight modal + toast (no markup needed) ---- */
  // Every open lpModal registers here so the guided tour (and only it) can
  // close competing dialogs before its overlay appears -- a modal and the
  // tour are never visible together (F-2/F-5). This is a small registry for
  // the existing helper, not a new overlay system.
  var _openModals = [];
  function lpModal(opts) {
    var ov = document.createElement('div');
    ov.className = 'lp-modal-ov lp-scrim';
    ov.style.cssText = 'position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)';
    var box = document.createElement('div');
    box.className = 'lp-pop';
    box.style.cssText = 'background:var(--panel);border:2px solid var(--border);border-radius:14px;box-shadow:var(--shadow-hi);padding:22px 24px;max-width:430px;width:90%';
    box.innerHTML = '<div style="font:700 17px \'Space Grotesk\';margin-bottom:10px">' + esc(opts.title) + '</div>' +
      '<div style="font-size:14px;line-height:1.55;margin-bottom:18px">' + (opts.bodyHtml || '') + '</div>';
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;justify-content:flex-end;gap:10px';
    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
      var ix = _openModals.indexOf(entry);
      if (ix >= 0) _openModals.splice(ix, 1);
      document.removeEventListener('keydown', onKey);
      try { LP.motion.close(ov, function () { ov.remove(); }); }
      catch (e) { try { ov.remove(); } catch (e2) {} }
    }
    (opts.actions || []).forEach(function (a) {
      var b = document.createElement('button');
      b.textContent = a.label;
      var base = 'font:600 13px \'Space Grotesk\';border-radius:9px;padding:9px 16px;cursor:pointer;border:2px solid var(--border)';
      b.style.cssText = a.danger ? base + ';background:var(--red-fill);color:var(--on-signal);border-color:var(--red)'
        : a.primary ? base + ';background:var(--orange);color:var(--on-signal);border-color:var(--orange-ink)'
          : base + ';background:var(--panel);color:var(--ink)';
      b.addEventListener('click', function () { if (!(a.onClick && a.onClick())) close(); });
      row.appendChild(b);
    });
    box.appendChild(row); ov.appendChild(box); document.body.appendChild(ov);
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) close(); });
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);
    // Move focus into the dialog; the global handler keeps Tab inside it.
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');
    focusFirst(ov);
    var entry = { close: close, overlay: ov };
    _openModals.push(entry);
    return entry;
  }
  function closeAllModals() {
    _openModals.slice().forEach(function (m) { m.close(); });
  }
  function anyModalOpen() {
    return _openModals.length > 0;
  }
  /* Progress fills: drive them with transform:scaleX() rather than width, so a
     per-frame progress tick stays on the compositor instead of forcing layout +
     paint. The element must carry .lp-fill and width:100%; pct is 0-100.
     One bar still animates width: #whatsnew-progress-bar -- it runs once, so the
     layout cost is irrelevant there. */
  function setFill(el, pct) {
    if (typeof el === 'string') el = $(el);
    if (!el) return;
    var p = Math.max(0, Math.min(100, parseFloat(pct) || 0));
    el.style.transform = 'scaleX(' + (p / 100) + ')';
  }

  // Keep animated status dots alive while only their adjacent text changes.
  // Replacing the whole status container restarts lpblink on every backend
  // tick, which makes a steady 1 Hz indicator look like a strobe.
  function setStatusDotText(el, value, color, blink) {
    if (!el) return;
    var dot = el.querySelector('[data-status-dot]');
    var label = el.querySelector('[data-status-label]');
    if (!dot || !label) {
      el.textContent = '';
      dot = document.createElement('span');
      dot.setAttribute('data-status-dot', 'true');
      dot.style.cssText = 'width:6px;height:6px;border-radius:50%;flex:none';
      label = document.createElement('span');
      label.setAttribute('data-status-label', 'true');
      el.appendChild(dot);
      el.appendChild(label);
    }
    dot.style.background = color;
    dot.style.animation = blink ? 'lpblink 1s infinite' : 'none';
    label.textContent = value == null ? '' : String(value);
  }

  // `.lp-toast`'s CSS entrance is opacity-only (reuses `lpsupport`), so it cannot
  // conflict with this singleton's inline `transform:translateX(-50%)`
  // centering. Re-trigger the entrance on every show by toggling the class
  // off/on around a reflow; skipped entirely under reduced motion.
  // Toast discipline (N-5): ordinary toasts auto-dismiss after ~5s, the
  // singleton caps the visible stack at one, navigation clears stale
  // transient messages, and no toast may linger once its condition is gone.
  var _toastT = null, _toastClearT = null;
  function toast(msg) {
    var t = $('lp-toast');
    if (!t) {
      t = document.createElement('div'); t.id = 'lp-toast'; t.className = 'lp-toast';
      t.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:130;background:var(--ink);color:var(--bg);font:600 13px \'Space Grotesk\';padding:10px 18px;border-radius:10px;box-shadow:var(--shadow-hi);opacity:0;transition:opacity .2s';
      document.body.appendChild(t);
    }
    t.textContent = msg; t.style.opacity = '1';
    if (!LP.motion.reduced()) {
      t.classList.remove('lp-toast');
      void t.offsetWidth;
      t.classList.add('lp-toast');
    }
    if (_toastT) clearTimeout(_toastT);
    if (_toastClearT) { clearTimeout(_toastClearT); _toastClearT = null; }
    _toastT = setTimeout(dismissToast, 5000);
  }
  function dismissToast() {
    if (_toastT) { clearTimeout(_toastT); _toastT = null; }
    var t = $('lp-toast');
    if (!t) return;
    t.style.opacity = '0';
    if (_toastClearT) clearTimeout(_toastClearT);
    // Clear the text once the fade has finished so a stale message can never
    // be read back out of the DOM on another screen.
    _toastClearT = setTimeout(function () { _toastClearT = null; if (t.style.opacity === '0') t.textContent = ''; }, 240);
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

  // Transcript copy helpers (pure, tested). Blocks are the renderer's loaded
  // transcript blocks {t, html|text}; the plain form is words only, the
  // stamped form keeps each block's visible timestamp.
  function transcriptBlockText(b) {
    if (!b) return '';
    if (b.text != null) return String(b.text);
    var tmp = document.createElement('div'); tmp.innerHTML = b.html || '';
    return tmp.textContent;
  }
  /* "Copy text" reflows the transcript into readable PARAGRAPHS.
     It used to emit one paragraph per transcript block, so a transcript cut
     into short caption-length blocks pasted as a column of fragments -- which
     is what "Copy with timestamps" is already for. Here the blocks are joined
     back into continuous prose and re-broken at sentence ends.

     Speech-to-text output is not reliably punctuated, so a run with no
     sentence ending is split at a word boundary rather than pasted as one
     unbroken wall. */
  function formatTranscriptPlain(blocks) {
    // Self-contained on purpose: this function is extracted and run on its own
    // in a VM by tests/test_job_view_switching.py, so it must not depend on
    // anything outside itself except transcriptBlockText.
    var PARAGRAPH_CHARS = 700, HARD_WRAP_CHARS = 1200;

    function splitLongRun(run) {
      var out = [];
      while (run.length > HARD_WRAP_CHARS) {
        var cut = run.lastIndexOf(' ', PARAGRAPH_CHARS);
        if (cut <= 0) cut = PARAGRAPH_CHARS;
        out.push(run.slice(0, cut).trim());
        run = run.slice(cut).trim();
      }
      if (run) out.push(run);
      return out;
    }

    var text = (blocks || []).map(function (b) {
      return transcriptBlockText(b);
    }).join(' ').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    var sentences = text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) || [text];
    var paragraphs = [], current = '';
    sentences.forEach(function (sentence) {
      current += sentence;
      if (current.length >= PARAGRAPH_CHARS) {
        paragraphs.push(current.trim());
        current = '';
      }
    });
    if (current.trim()) paragraphs.push(current.trim());
    return paragraphs.reduce(function (all, paragraph) {
      return all.concat(splitLongRun(paragraph));
    }, []).join('\n\n');
  }
  function formatTranscriptStamped(blocks) {
    return (blocks || []).map(function (b) {
      var text = transcriptBlockText(b).replace(/\s+/g, ' ').trim();
      if (!text) return '';
      return (b.t ? b.t + '  ' : '') + text;
    }).filter(Boolean).join('\n\n');
  }

  var TRASH_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>';
  var TAG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="0.5" fill="currentColor"/></svg>';

  function _jobBtn(action, id, svg, title) {
    return '<button class="lp-jobbtn" data-action="' + action + '" data-jobid="' + esc(id) + '" title="' + title + '" style="width:27px;height:27px;border-radius:7px;border:1.5px solid var(--border);background:var(--panel);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:var(--shadow-soft)">' + svg + '</button>';
  }

  // status -> badge {label, bg, fg, dot, blink}
  var JOB_BADGES = {
    running: { label: 'Processing', bg: 'var(--orange-soft)', fg: 'var(--orange-ink)', dot: 'var(--orange)', blink: true },
    ready: { label: 'Ready to process', bg: 'var(--blue-tint)', fg: 'var(--blue-ink)', dot: 'var(--blue-ink)' },
    done: { label: 'Complete', bg: 'var(--green-soft)', fg: 'var(--green)', dot: 'var(--green)' },
    cancelled: { label: 'Cancelled', bg: 'var(--sunk)', fg: 'var(--muted)', dot: 'var(--muted)' },
    interrupted: { label: 'Interrupted', bg: 'var(--orange-soft)', fg: 'var(--orange-ink)', dot: 'var(--orange)' },
    failed: { label: 'Failed', bg: 'var(--red-soft, rgba(220,60,60,.15))', fg: 'var(--red)', dot: 'var(--red)' },
    paused: { label: 'Paused', bg: 'var(--blue-tint)', fg: 'var(--blue-ink)', dot: 'var(--blue-ink)' },
    queued: { label: 'Queued', bg: 'var(--sunk)', fg: 'var(--muted)', dot: 'var(--muted)' },
    scheduled: { label: 'Scheduled', bg: 'var(--sunk)', fg: 'var(--muted)', dot: 'var(--muted)' }
  };
  // Maps the app's own status vocabularies onto the seven lp-state values
  // (idle|running|paused|success|failed|interrupted|complete). Purely a
  // lookup for motion/color feedback -- never consulted for app logic.
  var JOB_STATE_MAP = {
    running: 'running', ready: 'idle', done: 'complete', cancelled: 'interrupted', interrupted: 'interrupted',
    failed: 'failed', paused: 'paused', queued: 'idle', scheduled: 'idle'
  };

  function normalizedProcessingText(value) {
    return String(value == null ? '' : value).trim().toLowerCase()
      .replace(/[\u2013\u2014]/g, '-')
      .replace(/[\s_-]+/g, ' ');
  }

  // Backend status vocabulary is deliberately kept out of the visible UI.
  // The raw event still remains in LP.data.pipeline.log for technical review.
  function friendlyProcessingLabel(value) {
    var raw = String(value == null ? '' : value).trim();
    var normalized = normalizedProcessingText(raw);
    if (!normalized) return '';
    if (/detector.*decode.*piped|detect.*slide|slide.*detect/.test(normalized)) return 'Detecting slides';
    if (/whisper|transcrib|transcription/.test(normalized)) return 'Transcribing audio';
    if (/export|study pack/.test(normalized)) return 'Building Study Pack';
    if (/^(done|complete|completed|success|successful)$/.test(normalized)) return 'Complete';
    if (/^(inspect|inspecting|probe|probing)/.test(normalized)) return 'Inspecting video';
    if (/extract( audio|ing audio)?/.test(normalized)) return 'Extracting audio';
    if (/^align|aligning/.test(normalized)) return 'Aligning notes';
    if (/preparing review/.test(normalized)) return 'Preparing review';
    if (/review[ _-]?ready/.test(normalized)) return 'Review ready';
    if (/^prepare|preparing/.test(normalized)) return 'Preparing';
    return raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
  }

  /* A stage the pipeline FINISHED and handed back to the student. The app is
     NOT working, so the footer must stop implying that it is: a partly-filled
     solid orange bar is this app's idiom for work in progress, and the demo
     parks at review_ready/86% permanently (auto_export:false), which is what
     made the footer read "Preparing review 86%" through Review, Study AND
     Exports. The backend stage alone cannot say WHICH handoff is pending, so
     it resolves from app state. Works for a real job too: a job is "decided"
     once every slide carries an accepted/rejected state. */
  function reviewDecisionTaken() {
    var slides = (LP.data && LP.data.slides) || [];
    if (!slides.length) return false;
    return slides.every(function (sl) {
      return sl.state === 'accepted' || sl.state === 'rejected';
    });
  }
  function waitingHandoff(stage) {
    var n = normalizedProcessingText(String(stage == null ? '' : stage));
    if (!/review[ _-]?ready|awaiting[ _-]?review/.test(n)) return null;
    if (reviewDecisionTaken()) {
      return { label: 'Ready to export', detail: 'Study pack not exported yet' };
    }
    var undecided = ((LP.data && LP.data.slides) || []).filter(function (sl) {
      return sl.state !== 'accepted' && sl.state !== 'rejected';
    }).length;
    return { label: 'Review ready',
             detail: undecided
               ? undecided + (undecided === 1 ? ' slide' : ' slides') + ' to keep or reject'
               : 'Waiting for your review' };
  }

  /* Backend and IPC failures must never reach the student raw (N-2):
     "Error invoking remote method '…': Error: RuntimeError: no job is loaded"
     is log-speak, not a message. Strip the transport wrapper, map the known
     failure phrases to short actionable copy, and keep the raw string in the
     technical log only. `command` is the mapped sidecar command name when the
     failure came through the bridge's error channel. */
  function friendlyErrorMessage(raw, command) {
    var text = String(raw == null ? '' : raw).trim();
    if (!text) return 'Something went wrong. Try again.';
    var cleaned = text.replace(/^Error invoking remote method '[^']*':\s*/i, '').replace(/^Error:\s*/i, '').trim();
    var lower = cleaned.toLowerCase();
    if (lower.indexOf('no job is loaded') >= 0) {
      if (command === 'repair_selection') return 'Load a lecture before repairing slide selections.';
      if (command === 'export') return 'Load a lecture first — there is nothing to export yet.';
      if (command === 'set_slide_state' || command === 'save_corrections') return 'Load a lecture first — there are no slides to review yet.';
      if (command === 'pause_job' || command === 'resume_job' || command === 'cancel_job') return 'No lecture is processing right now.';
      return 'Load a lecture first — there is nothing to process yet.';
    }
    if (lower.indexOf('sidecar command failed') >= 0) {
      if (lower.indexOf('repair_selection') >= 0) return 'Load a lecture before repairing slide selections.';
      if (lower.indexOf('export') >= 0) return 'The export could not be completed. Try again.';
      return 'That action could not be completed right now. Try again.';
    }
    if (command === 'probe_media_url' || command === 'import_media_url') {
      var link = friendlyLinkError(cleaned);
      if (link) return link;
    }
    if (command === 'import_video' || command === 'browse_video') {
      if (/not found|no longer exists|video not found|ENOENT/i.test(cleaned)) {
        return 'That video could not be found. It may have been moved or removed.';
      }
      if (/permission|denied|not readable|unreadable|EACCES|EPERM/i.test(cleaned)) {
        return 'LecturePack cannot read that video. Check the file permissions or copy it to a local folder.';
      }
      if (/ffprobe|could not read this video format/i.test(cleaned)) {
        return 'LecturePack could not read this video format.';
      }
      if (/resolve|could not access|invalid path/i.test(cleaned)) {
        return 'LecturePack could not access that file. Try Browse for video.';
      }
    }
    if (/runtimeerror|traceback|exception|errno|0x[0-9a-f]{4}/i.test(cleaned)) {
      try { console.error('[lecturepack]', text); } catch (e) {}
      return 'Something went wrong. Please try again.';
    }
    return cleaned;
  }

  /* yt-dlp stderr → student copy (N-6). Returns '' when nothing matches so
     the caller can fall back to its own generic message; the raw technical
     text stays in the log or behind the dialog's Details section. */
  function friendlyLinkError(raw) {
    var lower = String(raw == null ? '' : raw).toLowerCase();
    if (!lower) return '';
    if (/getaddrinfo|name or service|temporary failure in name|nodename|errno 11001|unreachable|connection refused|timed?\s?out|failed to establish|urlopen|network is down/.test(lower))
      return 'We could not reach that link. Check the URL and your internet connection.';
    if (/unsupported url|unsupported site|no suitable extractor/.test(lower))
      return 'That site is not supported. Try a direct video file or a supported video link.';
    if (/private video|sign in|log ?in|cookies?|authentication/.test(lower))
      return 'That video requires a sign-in and cannot be imported.';
    if (/http error 404|404|not found|video unavailable|has been removed/.test(lower))
      return 'That link did not resolve to a video. Check the URL and try again.';
    return '';
  }

  function looksLikeJobId(value) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || '').trim());
  }

  function friendlyJobName(value) {
    var raw = String(value == null ? '' : value).trim();
    if (!raw) return '';
    if (raw === LP.state.jobId && LP.state.jobTitle && !looksLikeJobId(LP.state.jobTitle)) return LP.state.jobTitle;
    var found = (LP.data.jobs || []).filter(function (job) { return job && job.id === raw; })[0];
    if (found && (found.name || found.title)) return found.name || found.title;
    return looksLikeJobId(raw) ? (raw === LP.state.jobId ? (LP.state.jobTitle || 'Lecture') : 'Lecture') : raw;
  }

  function setComputeReadyFallback() {
    var vulkan = $('vulkan-status'), cuda = $('cuda-status');
    if (vulkan && /checking/i.test(vulkan.textContent || '')) {
      vulkan.textContent = 'CPU · AVX2 ready';
      vulkan.style.color = 'var(--secondary-text)';
    }
    if (cuda && /checking/i.test(cuda.textContent || '')) {
      cuda.textContent = 'CUDA unavailable in this build · CPU · AVX2 ready';
      cuda.style.color = 'var(--muted)';
    }
  }
  // Best-effort: sets data-state on the nearest ancestor (or self) carrying
  // class lp-state. No-ops silently if that class isn't present -- the
  // markup owner may not have landed it yet, or may never for this element.
  function _applyLpState(el, mapped) {
    if (!el || !mapped) return;
    var host = el.classList && el.classList.contains('lp-state')
      ? el : (el.closest ? el.closest('.lp-state') : null);
    if (host) host.dataset.state = mapped;
  }
  function _jobActBtn(act, id, label, primary) {
    var s = primary
      ? 'background:var(--secondary-surface);border:1.5px solid var(--secondary-border);color:var(--secondary-text)'
      : 'background:var(--panel);border:1.5px solid var(--border);color:var(--ink)';
    return '<button class="lp-hit" data-jobact="' + act + '" data-jobid="' + esc(id) + '" style="font:600 11px \'Space Grotesk\';border-radius:7px;padding:6px 11px;cursor:pointer;' + s + '">' + label + '</button>';
  }
  /* Job-card poster frame. The backend generates posters lazily and returns 404
     until one is cached, so the icon placeholder stays underneath and the <img>
     stays invisible until it actually loads -- no broken-image glyph, no layout
     shift.

     The URL is deliberately STABLE (no cache-busting query): jobs_changed fires
     on every job state change, and a per-refresh epoch made all N posters
     refetch on every tick (measured: a full grid rebuild is ~1.1ms per 3 cards
     plus N image loads). Instead a missing poster retries a bounded number of
     times with backoff, which is all that's needed now that posters prewarm
     when a job appears. */
  // 3 tries x 700ms*n gave up after ~4.2s and then removed the img for good, so
  // a poster that took longer to extract (a multi-hundred-MB source) never
  // appeared at all -- the file landed on disk seconds after the UI stopped
  // asking. Budget now spans ~30s, which covers a cold extract, while still
  // ending rather than polling forever.
  var POSTER_RETRIES = 9;

  function posterSrc(id, attempt) {
    var u = 'lpasset://poster/' + encodeURIComponent(id) + '/poster';
    return attempt ? u + '?r=' + attempt : u;      // only retries bust the cache
  }

  function posterHtml(j) {
    var ph = '<span data-poster-ph style="position:absolute;display:flex;align-items:center;justify-content:center">' +
      thumb(30, 'var(--muted)') + '</span>';
    if (!j.id) return ph;
    // decoding=async + loading=lazy keep a large grid off the main thread.
    var img = '<img src="' + posterSrc(j.id, 0) + '" alt="" loading="lazy" decoding="async" ' +
      'data-poster-job="' + esc(j.id) + '" ' +
      'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;' +
      'transition:opacity var(--motion-medium,.22s) var(--motion-ease,ease)" ' +
      'onload="LP.posterLoaded(this)" onerror="LP.posterRetry(this)">';
    return ph + img;
  }

  // Exposed on LP because the handlers are inline attributes on generated HTML.
  LP.posterLoaded = function (img) {
    img.style.opacity = 1;
    var ph = img.parentNode && img.parentNode.querySelector('[data-poster-ph]');
    if (ph) ph.hidden = true;
  };

  LP.posterRetry = function (img) {
    var n = parseInt(img.getAttribute('data-try') || '0', 10) + 1;
    if (n > POSTER_RETRIES) { img.remove(); return; }   // give up; icon remains
    img.setAttribute('data-try', String(n));
    var id = img.getAttribute('data-poster-job');
    setTimeout(function () {
      if (img.parentNode) img.src = posterSrc(id, n);   // backend may have it now
    }, 700 * n);
  };

  /* ==================== Home multi-select ====================
     Selecting is an explicit mode so a normal click still opens a lecture -- no
     accidental selection, and no checkbox clutter until it is wanted. Bulk
     delete/group go through one bridge call each so the backend performs one
     list refresh for the whole batch instead of N. */
  function selCount() { return Object.keys(LP.state.selected).length; }

  function setSelectMode(on) {
    LP.state.selecting = !!on;
    if (!on) LP.state.selected = {};
    var bar = $('jobs-selectbar');
    if (bar) bar.hidden = !on;
    var btn = $('btn-select-mode');
    if (btn) btn.textContent = on ? 'Cancel' : 'Select';
    renderJobs();
    renderSelCount();
  }

  function toggleSelected(id) {
    if (!id) return;
    if (LP.state.selected[id]) delete LP.state.selected[id];
    else LP.state.selected[id] = true;
    renderSelCount();
    // repaint just this card's checkbox rather than the whole grid
    var card = document.querySelector('.lp-card[data-job="' + cssEsc(id) + '"]');
    var box = card && card.querySelector('[data-selbox]');
    if (box) paintSelBox(box, !!LP.state.selected[id]);
    if (card) card.style.borderColor = LP.state.selected[id] ? 'var(--blue)' : 'var(--border)';
  }

  function cssEsc(s) {
    return String(s).replace(/["\\]/g, '\\$&');
  }

  function paintSelBox(box, on) {
    box.style.background = on ? 'var(--blue)' : 'var(--panel)';
    box.style.borderColor = on ? 'var(--blue)' : 'var(--border)';
    box.innerHTML = on
      ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--on-signal)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
      : '';
    box.setAttribute('aria-checked', on ? 'true' : 'false');
  }

  function renderSelCount() {
    var n = selCount();
    var el = $('jobs-selcount');
    if (el) el.textContent = n + ' selected';
    ['btn-bulk-delete', 'btn-bulk-group'].forEach(function (id) {
      var b = $(id);
      if (!b) return;
      b.disabled = n === 0;
      b.style.opacity = n === 0 ? '.45' : '1';
      b.style.cursor = n === 0 ? 'default' : 'pointer';
    });
  }

  // Every member of a group that select mode can actually act on.
  function groupSelectableIds(members) {
    return (members || []).filter(function (j) { return j && j.id; }).map(function (j) { return j.id; });
  }
  function groupFullySelected(members) {
    var ids = groupSelectableIds(members);
    return ids.length > 0 && ids.every(function (id) { return !!LP.state.selected[id]; });
  }
  function selectableIds() {
    return LP.data.jobs.filter(function (j) { return j.id; })
      .map(function (j) { return j.id; });
  }

  function bulkDelete() {
    var ids = Object.keys(LP.state.selected);
    if (!ids.length) return;
    var names = LP.data.jobs.filter(function (j) { return LP.state.selected[j.id]; })
      .map(function (j) { return j.name; });
    var preview = names.slice(0, 5).map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('');
    if (names.length > 5) preview += '<li>and ' + (names.length - 5) + ' more</li>';
    lpModal({
      title: 'Delete ' + ids.length + (ids.length === 1 ? ' lecture?' : ' lectures?'),
      bodyHtml: '<ul style="margin:0 0 10px 18px;padding:0">' + preview + '</ul>' +
        'They move to the Recycle Bin and are removed from LecturePack, freeing disk space. Their export files go too.',
      actions: [
        { label: 'Cancel' },
        { label: 'Delete ' + ids.length, danger: true, onClick: function () {
          if (lpBridge.connected()) lpBridge.call('delete_jobs', JSON.stringify(ids));
          else toast('Preview mode — nothing deleted');
          setSelectMode(false);
        } }
      ]
    });
  }

  function bulkGroup() {
    var ids = Object.keys(LP.state.selected);
    if (!ids.length) return;
    lpModal({
      title: 'Group ' + ids.length + (ids.length === 1 ? ' lecture' : ' lectures'),
      bodyHtml: '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px">Course / subject</label>' +
        '<input id="lp-bulk-group-input" type="text" spellcheck="false" placeholder="e.g. CL100" style="width:100%;box-sizing:border-box;font:600 14px \'JetBrains Mono\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">' +
        '<div style="font-size:12px;color:var(--muted);margin-top:8px">Leave blank to auto-group by each lecture title.</div>',
      actions: [
        { label: 'Cancel' },
        { label: 'Apply', primary: true, onClick: function () {
          var i = $('lp-bulk-group-input');
          if (lpBridge.connected()) {
            var group = (i && i.value || '').trim();
            lpBridge.call('set_jobs_group', JSON.stringify(ids), group).then(function (result) {
              if (!result || !result.ok) return;
              LP.data.jobs.forEach(function (job) {
                if (ids.indexOf(job.id) >= 0) job.group = group;
              });
              renderJobs();
            });
          }
          else toast('Preview mode — not grouped');
          setSelectMode(false);
        } }
      ]
    });
    setTimeout(function () { var i = $('lp-bulk-group-input'); if (i) i.focus(); }, 30);
  }

  /* yt-dlp appends its video id to the filename, so a downloaded lecture is
     called "... Archaeology [_OQbKAx9878]" and the card printed that id twice --
     once in the heading, once in the filename line beneath it. The id is not
     something a student reads, so it is dropped from the DISPLAYED name only;
     j.name itself is untouched, because rename, search and the drag label all
     depend on it.

     This is anchored on the SOURCE FILENAME's id rather than on a shape, and
     deliberately so. A shape-based rule cannot win here: the importer rewrites
     "_" as " " when it derives a display name, so the real stored name ends
     "[ OQbKAx9878]" -- with a space -- and any pattern loose enough to catch
     that also eats legitimate brackets like "[Lecture Notes]". Matching the id
     the file actually carries has no false positives at all. A name with no
     matching file keeps its brackets, which is the safe direction to err. */
  function _jobDisplayName(name, file) {
    var full = String(name || '').trim();
    /* No space in this class, deliberately. The FILENAME is unmangled, so a
       real id ("_OQbKAx9878") has no spaces in it, while a bracket the user
       chose ("[Lecture Notes]") does -- that is the discriminator. The _ -> " "
       leniency below applies only when matching the already-rewritten NAME. */
    var found = String(file || '').match(/\[([A-Za-z0-9_-]{8,})\](?=\.[A-Za-z0-9]+$|$)/);
    if (!found) return full;
    // Escape the id, then let "_" and " " stand in for each other.
    var pattern = found[1].replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/[_ ]/g, '[_ ]');
    var trimmed = full.replace(new RegExp('\\s*\\[' + pattern + '\\]\\s*$'), '').trim();
    return trimmed || full;
  }

  function _jobCardHtml(j) {
    var ready = _jobIsReady(j);
    var draggable = _jobIsDraggable(j);
    var displayStatus = ready ? 'ready' : j.status;
    var b = JOB_BADGES[displayStatus] || JOB_BADGES.done;
    var dot = '<span style="width:6px;height:6px;border-radius:50%;background:' + b.dot + (b.blink ? ';animation:lpblink 1s infinite' : '') + '"></span>';
    var badge = '<span class="lp-state" data-state="' + (JOB_STATE_MAP[displayStatus] || 'idle') + '" style="position:absolute;top:9px;right:9px;display:flex;align-items:center;gap:5px;font:600 10px \'JetBrains Mono\';text-transform:uppercase;background:' + b.bg + ';color:' + b.fg + ';border-radius:6px;padding:3px 8px">' + dot + b.label + '</span>';
    var subject = jobGroup(j) || 'General';
    var subjectBadge = '<button type="button" class="lp-subject-badge" data-jobid="' + esc(j.id) + '" data-subject="' + esc(subject) + '" title="Click to rename subject">' +
      '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>' +
      '<span>' + esc(subject) + '</span></button>';
    /* The subject badge USED to live here, pinned over the poster beside the
       delete button. It carries a full subject name, so the top-left group grew
       rightwards until it collided with the status badge pinned top-right --
       measured at ~15px of overlap on a 247px card, and guaranteed to worsen
       with a longer subject name. Moving it into the body removes the collision
       by construction rather than by tuning offsets, and leaves the poster
       carrying only status (top-right), the menu (on hover) and the drag grip
       (bottom-left). */
    var menu = j.id ? '<div style="position:absolute;top:9px;left:9px;display:flex;align-items:center;gap:6px">' +
      _jobBtn('delete', j.id, TRASH_SVG, 'Delete') + '</div>' : '';
    /* In select mode the per-card menu becomes a checkbox and the whole card
       toggles selection. Computed HERE, above the body, because the body needs
       it too now: the subject badge renames on click, which must not be
       reachable while the card's job is to be ticked. */
    var selecting = LP.state.selecting && j.id;
    var chosen = selecting && !!LP.state.selected[j.id];
    var kicker = (!selecting && j.id) ? '<div style="margin-bottom:8px">' + subjectBadge + '</div>' : '';
    var display = _jobDisplayName(j.name, j.file);
    // The stripped id stays recoverable on hover rather than vanishing.
    var nameTitle = display === String(j.name || '').trim()
      ? 'Double-click to rename'
      : esc(j.name) + ' · double-click to rename';
    var body;
    if (j.status === 'running') {
      body = kicker + '<div data-job-title title="' + nameTitle + '" style="font-weight:700;font-size:16px;margin-bottom:9px">' + esc(display) + '</div>' +
        '<div style="height:8px;border-radius:5px;background:var(--sunk);overflow:hidden;margin-bottom:7px"><div data-progress style="width:' + (j.pct || 0) + '%;height:100%;background:var(--orange);background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.3) 6px,rgba(255,255,255,.3) 13px);animation:lpbar 1s linear infinite"></div></div>' +
        '<div data-progress-label style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + esc(friendlyProcessingLabel(j.stage)) + ' · ' + (j.pct || 0) + '% · ' + esc(j.eta || '') + '</div>';
    } else {
      /* One identity line, not three. This printed the heading, then the source
         filename -- the same words plus ".mp4" -- and only then the duration, so
         a card said its own name twice before it said anything new. Only the
         meta line survives; j.file is kept purely as a fallback so a card with
         no meta is not left blank. */
      body = kicker + '<div data-job-title title="' + nameTitle + '" style="font-weight:700;font-size:16px;margin-bottom:5px">' + esc(display) + '</div>' +
        '<div style="font:500 11px \'JetBrains Mono\';color:var(--muted);line-height:1.7">' + esc(j.meta || j.file || '') + '</div>';
      if (ready) {
        body += '<div style="font:500 11px \'JetBrains Mono\';color:var(--blue-ink);margin-top:6px">' + esc(_optionsLabel(j)) + '</div>';
      }
    }
    // Ready-to-process jobs stay editable until Start is pressed.
    if (j.id && ready) {
      body += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:11px">' +
        _jobActBtn('start', j.id, 'Start processing', true) +
        _jobActBtn('options', j.id, 'Set options') +
        _jobActBtn('remove', j.id, 'Remove') + '</div>';
    }
    // Needs-Attention actions for interrupted/failed jobs.
    if (j.id && (j.status === 'interrupted' || j.status === 'failed')) {
      body += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:11px">' +
        _jobActBtn('resume', j.id, 'Resume', true) +
        _jobActBtn('restart', j.id, 'Restart') +
        _jobActBtn('view', j.id, 'View Details') +
        _jobActBtn('remove', j.id, 'Remove') + '</div>';
    }
    // selecting / chosen are declared above, since the body's subject-badge
    // kicker needs them too.
    var selbox = selecting
      ? '<span data-selbox role="checkbox" aria-checked="' + (chosen ? 'true' : 'false') + '" ' +
        'style="position:absolute;top:9px;left:9px;width:22px;height:22px;border-radius:6px;' +
        'border:2px solid ' + (chosen ? 'var(--blue)' : 'var(--border)') + ';background:' +
        (chosen ? 'var(--blue)' : 'var(--panel)') + ';display:flex;align-items:center;justify-content:center;' +
        'box-shadow:var(--shadow-soft)">' +
        (chosen ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--on-signal)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>' : '') +
        '</span>'
      : '';
    var border = chosen ? 'var(--blue)' : 'var(--border)';
    /* data-lp-drag marks this card as a source for the ONE drag system; the
       older data-existing-job-drag stays because it is the selector the
       acceptance tests and the Process-target contract already use.
       The grip renders only on a card that can actually be dragged -- its
       absence is the honest signal on the rest, which previously advertised
       cursor:grab and then refused to lift. */
    var grip = draggable
      ? '<button type="button" class="lp-drag-grip" tabindex="-1" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></button>'
      : '';
    return '<div class="lp-card" ' + (j.id ? 'data-job="' + esc(j.id) + '" ' : '') + /* NO draggable="true": the pointer layer owns internal drags now, and leaving
         the native attribute on would let Chromium start its own unstyleable drag
         for the same gesture. data-existing-job-drag stays -- it is the selector
         the Process-target contract and the acceptance tests use. */
      (draggable ? 'data-existing-job-drag="true" data-lp-drag="lecture" ' : '') +
      /* No native title here on purpose. Two unstyled OS tooltips (one on the
         card, one on the grip) used to stack over the poster and cover the very
         thumbnail they described -- reported as the card looking congested.
         The drag is now taught at the moment it matters instead: the status
         strip names the verb on lift and every valid target lights up, which no
         hover-only tooltip could do. */
      (_jobIsReprocessable(j) ? 'data-reprocess="true" ' : '') +
      'data-status="' + esc(displayStatus) + '" style="position:relative;background:var(--panel);border:2px solid ' + border + ';border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;cursor:' + (draggable ? 'grab' : 'pointer') + '">' +
      '<div style="height:118px;background:var(--sunk);border-bottom:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;position:relative">' + posterHtml(j) + (selecting ? selbox : menu) + badge + grip + '</div>' +
      '<div style="padding:14px 16px">' + body + '</div></div>';
  }

  /* ==================== import from a link (yt-dlp) ====================
     Three short steps, each its own lpModal so they inherit the focus trap:
     paste -> confirm what was found -> transfer with progress/cancel.
     The backend hands the finished file to the normal import path, so the
     existing New-job overlay takes over from there. */
  var mediaLink = { available: false, version: '', done: null, downloads: [] };

  function mediaUrls(text) {
    var seen = {};
    return String(text || '').split(/\r?\n/).map(function (url) { return url.trim(); })
      .filter(function (url) { if (!url || seen[url]) return false; seen[url] = true; return true; });
  }

  function fmtDuration(sec) {
    sec = Math.max(0, parseInt(sec, 10) || 0);
    if (!sec) return 'unknown length';
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return h ? h + ':' + p(m) + ':' + p(s) : m + ':' + p(s);
  }

  function fmtBytes(n) {
    n = parseFloat(n) || 0;
    if (n < 1024) return n.toFixed(0) + ' B';
    if (n < 1048576) return (n / 1024).toFixed(0) + ' KB';
    if (n < 1073741824) return (n / 1048576).toFixed(1) + ' MB';
    return (n / 1073741824).toFixed(2) + ' GB';
  }

  function linkImportDialog() {
    if (!lpBridge.connected()) { toast('Preview mode — link import needs the app'); return; }
    var inp = 'width:100%;box-sizing:border-box;font:500 13px \'JetBrains Mono\';padding:10px 12px;border:2px solid var(--border);border-radius:8px;background:var(--sunk);color:var(--ink)';
    var body =
      '<label for="link-url" style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted);margin-bottom:6px">Video links</label>' +
      '<textarea id="link-url" rows="5" spellcheck="false" placeholder="One https:// link per line" style="' + inp + ';resize:vertical"></textarea>' +
      '<div id="link-msg" role="status" style="min-height:18px;font-size:12px;color:var(--muted);margin-top:9px"></div>' +
      '<div style="font-size:12px;line-height:1.5;color:var(--muted);margin-top:4px">Downloads the recording to your computer so it can be processed here. Only fetch lectures you have the right to download.</div>';
    var m = lpModal({
      title: 'Import from a link',
      bodyHtml: body,
      actions: [
        { label: 'Cancel' },
        { label: 'Check link', primary: true, onClick: function () {
          var urls = mediaUrls(($('link-url') || {}).value || '');
          if (!urls.length || urls.some(function (url) { return !/^https?:\/\/.+/i.test(url); })) { setLinkMsg('Enter one full http(s) link per line.', true); return true; }
          setLinkMsg('Looking up ' + urls.length + (urls.length === 1 ? ' video…' : ' videos…'));
          mediaLink.pending = urls;
          lpBridge.call('probe_media_url', { urls: urls });
          return true;                 // keep the dialog open while we wait
        } }
      ]
    });
    mediaLink.probeModal = m;
    setTimeout(function () { var i = $('link-url'); if (i) i.focus(); }, 40);
  }

  function setLinkMsg(text, isError) {
    var el = $('link-msg');
    if (el) {
      el.textContent = text;
      el.style.color = isError ? 'var(--red)' : 'var(--muted)';
      el.style.fontWeight = isError ? '650' : '';
    }
    // The message alone was easy to miss -- it sits below the field and never
    // changed shape, so a rejected link read as "nothing happened".
    var input = $('link-url');
    if (input) {
      input.classList.toggle('lp-input-invalid', !!isError);
      input.setAttribute('aria-invalid', isError ? 'true' : 'false');
      if (isError) {
        input.classList.remove('lp-shake');
        void input.offsetWidth;
        input.classList.add('lp-shake');
        try { input.focus(); } catch (err) { /* modal may not be mounted yet */ }
      }
    }
  }

  function linkConfirmDialog(info) {
    var items = Array.isArray(info.items) ? info.items : [info];
    var ready = items.filter(function (item) { return item && item.ok !== false; });
    var failed = items.filter(function (item) { return item && item.ok === false; });
    var rows = ready.map(function (item) {
      return '<div style="padding:8px 10px;border:1.5px solid var(--line);border-radius:8px;background:var(--sunk)"><div style="font-weight:650">' + esc(item.title || 'Untitled video') + '</div><div style="font:500 10px \'JetBrains Mono\';color:var(--muted);margin-top:3px">' + esc(fmtDuration(item.duration)) + '</div></div>';
    }).join('');
    if (failed.length) rows += '<div style="font-size:12px;color:var(--red)">' + failed.length + ' link' + (failed.length === 1 ? '' : 's') + ' could not be read and will be skipped.</div>';
    lpModal({
      title: ready.length + (ready.length === 1 ? ' video' : ' videos'),
      bodyHtml: '<div style="display:flex;flex-direction:column;gap:7px;max-height:300px;overflow:auto">' + rows + '</div>',
      actions: [
        { label: 'Cancel' },
        { label: 'Download ' + ready.length, primary: true, onClick: function () {
          if (!ready.length) return;
          lpBridge.call('import_media_url', { items: ready.map(function (item) {
            return { url: item.webpage_url || item.url, title: item.title || '' };
          }) });
          toast(ready.length + (ready.length === 1 ? ' download started' : ' downloads queued'));
        } }
      ]
    });
  }

  function positionDownloadsPanel() {
    var indicator = $('downloads-indicator'), panel = $('downloads-panel');
    if (!indicator || !panel || panel.hidden) return;
    var r = indicator.getBoundingClientRect(), width = panel.offsetWidth || 390, pad = 10;
    var left = Math.max(pad, Math.min(r.right - width, window.innerWidth - width - pad));
    panel.style.left = Math.round(left) + 'px';
    panel.style.top = Math.round(r.bottom + 8) + 'px';
    panel.style.right = 'auto';
  }

  function downloadId(item) {
    var value = item && item.download_id != null ? item.download_id : item && item.id;
    return value == null ? '' : String(value);
  }
  function normalizedDownloadStatus(item) {
    var status = String(item && item.status || '').trim().toLowerCase();
    if (status === 'waiting' || status === 'running' || status === 'completed' || status === 'failed') return status;
    // Older bridges exposed their vocabulary as status; newer bridges keep it
    // under legacy_status while the normalized status remains authoritative.
    var legacy = String(item && item.legacy_status || '').trim().toLowerCase();
    if (status === 'downloading' || legacy === 'downloading') return 'running';
    if (status === 'complete' || legacy === 'complete') return 'completed';
    if (status === 'cancelled' || legacy === 'cancelled') return 'failed';
    return 'waiting';
  }
  function downloadPercent(item) {
    var raw = item && item.pct != null ? item.pct : item && item.progress;
    var pct = Number(raw);
    if (!isFinite(pct)) pct = 0;
    if (item && item.pct == null && pct >= 0 && pct <= 1) pct *= 100;
    return Math.max(0, Math.min(100, pct));
  }
  function downloadEta(item) {
    var raw = item && item.eta_seconds != null ? item.eta_seconds : item && item.eta;
    var eta = Number(raw);
    return isFinite(eta) && eta >= 0 ? eta : null;
  }
  function renderDownloads() {
    var items = mediaLink.downloads || [];
    var indicator = $('downloads-indicator'), panel = $('downloads-panel'), list = $('downloads-list');
    if (!indicator || !panel || !list) return;
    var rows = items.map(function (item) {
      return { item: item, id: downloadId(item), status: normalizedDownloadStatus(item) };
    });
    var active = rows.filter(function (row) { return row.status === 'running'; })[0];
    var waiting = rows.filter(function (row) { return row.status === 'waiting'; }).length;
    var unfinished = rows.filter(function (row) { return row.status === 'running' || row.status === 'waiting'; }).length;
    indicator.hidden = false;
    var count = $('downloads-indicator-count'), label = $('downloads-indicator-label');
    if (count) { count.hidden = !unfinished; count.textContent = unfinished ? String(unfinished) : ''; }
    if (label) label.textContent = active ? (downloadPercent(active.item) + '%') : 'Downloads';
    indicator.setAttribute('aria-label', active
      ? ('Downloads: ' + downloadPercent(active.item) + '% in progress' + (waiting ? ', ' + waiting + ' waiting' : ''))
      : 'Open downloads');
    if (!items.length) {
      list.innerHTML = '<div style="padding:18px 10px;text-align:center;font:500 12px \'Space Grotesk\';color:var(--muted)">No downloads yet.</div>';
      return;
    }
    list.innerHTML = rows.map(function (row) {
      var item = row.item, status = row.status, pct = downloadPercent(item), eta = downloadEta(item);
      var progress = status === 'running'
        ? '<div style="height:6px;border-radius:4px;background:var(--sunk);overflow:hidden;margin:7px 0 4px"><div class="lp-fill" style="width:100%;height:100%;background:var(--orange);transform:scaleX(' + (pct / 100) + ')"></div></div>'
        : '';
      var meta = status === 'running'
        ? (pct + '%' + (item.speed ? ' · ' + fmtBytes(item.speed) + '/s' : '') + (eta != null ? ' · ~' + fmtDuration(eta) + ' left' : ''))
        : status === 'completed'
          ? 'Completed'
          : status === 'failed'
            ? (String(item.legacy_status || '').toLowerCase() === 'cancelled' ? 'Cancelled' : 'Failed')
            : 'Waiting';
      var action = row.id && status === 'running'
        ? '<button data-download-act="cancel" data-download-id="' + esc(row.id) + '">Cancel</button>'
        : row.id && status === 'waiting'
          ? '<button data-download-act="remove" data-download-id="' + esc(row.id) + '">Remove</button>'
          : row.id && status === 'failed'
            ? '<button data-download-act="retry" data-download-id="' + esc(row.id) + '">Retry</button>' : '';
      return '<div style="padding:10px;border-radius:9px;background:var(--panel2);margin-bottom:6px"><div style="display:flex;gap:9px;align-items:start"><div style="flex:1;min-width:0"><div style="font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(item.title || 'Lecture download') + '</div>' + progress + '<div style="font:500 10px \'JetBrains Mono\';color:' + (status === 'failed' ? 'var(--red)' : 'var(--muted)') + '">' + esc(meta) + '</div>' + (item.error ? '<details style="font-size:11px;color:var(--muted);margin-top:5px"><summary>Details</summary><div style="overflow-wrap:anywhere">' + esc(item.error) + '</div></details>' : '') + '</div><div class="lp-download-action">' + action + '</div></div></div>';
    }).join('');
    positionDownloadsPanel();
  }

  // "YYYY-MM-DDTHH:MM" for *local* time -- toISOString() would return UTC and
  // shift the floor by the timezone offset.
  function localNowValue() {
    var d = new Date();
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
      'T' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function scheduleJobDialog(id) {
    var inp = 'width:100%;font:500 13px \'JetBrains Mono\';padding:9px 11px;border:2px solid var(--border);border-radius:8px;background:var(--sunk);color:var(--ink)';
    var body =
      '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted);margin-bottom:6px">When (your local time)</label>' +
      '<input id="sched-when" type="datetime-local" min="' + localNowValue() + '" style="' + inp + ';margin-bottom:15px">' +
      '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted);margin-bottom:6px">If the app was closed at that time</label>' +
      '<select id="sched-policy" style="' + inp + '">' +
        '<option value="run_when_opened">Run when the app next opens</option>' +
        '<option value="skip_if_missed">Skip it</option>' +
        '<option value="ask">Ask me</option>' +
      '</select>';
    lpModal({
      title: 'Schedule this lecture',
      bodyHtml: body,
      actions: [
        { label: 'Cancel' },
        { label: 'Schedule', primary: true, onClick: function () {
          var when = (document.getElementById('sched-when') || {}).value;
          if (!when) { toast('Pick a date and time'); return true; }
          // `min` is advisory only -- typed input bypasses it, so re-check here
          // rather than silently scheduling a run in the past (BUG-06).
          if (when < localNowValue()) { toast('Pick a time in the future'); return true; }
          var pol = (document.getElementById('sched-policy') || {}).value || 'run_when_opened';
          if (lpBridge.connected()) lpBridge.call('schedule_job', id, when, 'local', pol);
          else toast('Preview mode — not scheduled');
        } }
      ]
    });
  }

  function confirmDeleteJob(job) {
    lpModal({
      title: 'Delete this lecture?',
      bodyHtml: '<strong>' + esc(job.name) + '</strong> will be moved to the Recycle Bin and removed from LecturePack, freeing disk space. Its export files are removed too.',
      actions: [{ label: 'Cancel' }, { label: 'Delete', danger: true, onClick: function () { if (lpBridge.connected()) lpBridge.call('delete_job', job.id); else toast('Preview mode — not deleted'); } }]
    });
  }
  function confirmResetLecturePack() {
    var status = $('reset-lecturepack-status'), modal;
    modal = lpModal({
      title: 'Reset LecturePack?',
      bodyHtml: 'This will permanently remove LecturePack jobs, Study progress, downloaded LecturePack media, settings, and app history.<br><br>Original lecture/video files outside LecturePack will not be deleted.',
      actions: [
        { label: 'Cancel' },
        { label: 'Reset LecturePack', danger: true, onClick: function () {
          if (!lpBridge.connected()) {
            toast('Reset needs the LecturePack desktop app.');
            return false;
          }
          if (status) status.textContent = 'Waiting for reset confirmation…';
          lpBridge.call('reset_lecturepack').then(function (value) {
            var result = parseBridgeResult(value);
            if (!result || result.ok !== true) {
              if (status) status.textContent = (result && result.error) || 'Reset is unavailable in this build.';
              toast((result && result.error) || 'Reset is unavailable in this build.');
              return;
            }
            if (status) status.textContent = 'LecturePack is restarting…';
            modal.close();
          }, function () {
            if (status) status.textContent = 'Reset could not be started.';
            toast('Reset could not be started.');
          });
          return true;
        } }
      ]
    });
  }
  function setJobGroup(job) {
    lpModal({
      title: 'Group lecture',
      bodyHtml: '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px">Course / subject</label>' +
        '<input id="lp-group-input" type="text" spellcheck="false" value="' + esc(job.group || '') + '" placeholder="e.g. CL100" style="width:100%;box-sizing:border-box;font:600 14px \'JetBrains Mono\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">' +
        '<div style="font-size:12px;color:var(--muted);margin-top:8px">Leave blank to auto-group by the lecture title.</div>',
      actions: [{ label: 'Cancel' }, { label: 'Save', primary: true, onClick: function () {
        var i = $('lp-group-input');
        if (lpBridge.connected()) {
          var group = (i && i.value || '').trim();
          lpBridge.call('set_job_group', job.id, group).then(function (result) {
            if (!result || !result.ok) return;
            job.group = group;
            renderJobs();
          });
        }
      } }]
    });
    setTimeout(function () { var i = $('lp-group-input'); if (i) { i.focus(); i.select(); } }, 30);
  }

  function _jobName(id) {
    var j = (LP.data.jobs || []).filter(function (x) { return x.id === id; })[0];
    return j ? j.name : id;
  }
  function inferredJobGroup(title) {
    var text = String(title || '').trim();
    if (!text) return 'Ungrouped';
    var separators = [':', '—', '-'];
    for (var i = 0; i < separators.length; i++) {
      if (text.indexOf(separators[i]) >= 0) {
        var head = text.split(separators[i], 1)[0].trim();
        if (head) return head.slice(0, 40);
      }
    }
    return text.split(/\s+/).filter(Boolean).slice(0, 2).join(' ').slice(0, 40) || 'Ungrouped';
  }
  function jobGroup(job) {
    return (job && job.group) || inferredJobGroup(job && (job.name || job.title));
  }

  function lectureProgressPct(job) {
    if (!job) return 0;
    if (job.status !== 'done') return Math.max(0, Math.min(100, Number(job.pct) || 0));
    var studyData = (typeof studyV2 !== 'undefined' && studyV2.progress && studyV2.viewJobId === job.id) ? studyV2.progress : null;
    if (!studyData && job.study_summary && typeof job.study_summary.progress_percent === 'number') {
      return Math.max(0, Math.min(100, Math.round(job.study_summary.progress_percent)));
    }
    if (studyData && studyData.concepts) {
      var cids = Object.keys(studyData.concepts);
      if (cids.length > 0) {
        var scoreSum = 0;
        cids.forEach(function (cid) {
          var state = studyData.concepts[cid];
          if (typeof state === 'object' && state !== null) state = state.mastery;
          if (state === 'MASTERED' || state === 'mastered') scoreSum += 1.0;
          else if (state === 'LEARNING' || state === 'learning' || state === 'MEDIUM' || state === 'medium') scoreSum += 0.5;
          else if (state === 'NEEDS_REVIEW' || state === 'needs_review' || state === 'LOW' || state === 'low') scoreSum += 0.2;
        });
        return Math.max(0, Math.min(100, Math.round((scoreSum / cids.length) * 100)));
      }
    }
    return 100; // Processed and ready for study
  }

  function groupCoveragePct(jobs) {
    if (!jobs || !jobs.length) return 0;
    var sum = 0;
    jobs.forEach(function (j) { sum += lectureProgressPct(j); });
    return Math.round(sum / jobs.length);
  }

  function renderCoverageBarHtml(pct, label) {
    var p = Math.max(0, Math.min(100, Number(pct) || 0));
    var color = p >= 80 ? 'var(--green)' : p >= 40 ? 'var(--orange)' : 'var(--blue)';
    return '<div class="lp-coverage-bar" title="' + esc(label || (p + '% coverage')) + '">' +
      '<div class="lp-coverage-track"><div class="lp-coverage-fill" style="width:' + p + '%;background:' + color + '"></div></div>' +
      '<span class="lp-coverage-pct">' + p + '%</span></div>';
  }

  var subjectFilterQuery = '';

  function renderSubjects() {
    var grid = $('subjects-grid'), empty = $('subjects-empty'), countLabel = $('subjects-summary-count');
    if (!grid) return;
    var allJobs = (typeof LP !== 'undefined' && LP.data && LP.data.jobs) || [];
    var groupsMap = {};
    allJobs.forEach(function (j) {
      var grp = jobGroup(j) || 'General';
      if (!groupsMap[grp]) groupsMap[grp] = [];
      groupsMap[grp].push(j);
    });
    var groupNames = Object.keys(groupsMap).sort();
    if (subjectFilterQuery) {
      var q = subjectFilterQuery.toLowerCase().trim();
      groupNames = groupNames.filter(function (name) {
        if (name.toLowerCase().indexOf(q) >= 0) return true;
        return groupsMap[name].some(function (j) { return ((j && (j.name || j.title)) || '').toLowerCase().indexOf(q) >= 0; });
      });
    }
    if (countLabel) countLabel.textContent = groupNames.length + (groupNames.length === 1 ? ' Subject' : ' Subjects');
    if (!groupNames.length) {
      grid.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    grid.innerHTML = groupNames.map(function (grpName) {
      var members = groupsMap[grpName];
      var cov = groupCoveragePct(members);
      var doneCount = members.filter(function (m) { return m.status === 'done'; }).length;
      var memberListHtml = members.map(function (m) {
        var mPct = lectureProgressPct(m);
        var isViewing = typeof LP !== 'undefined' && LP.state && m.id === LP.state.jobId;
        var r = getJobReadiness(m);
        var mName = m.name || m.title || m.filename || 'Lecture';
        /* A Subjects row is a drag SOURCE: moving a lecture between subjects is
           the gesture this screen is for, and dragging the row itself is more
           direct than opening the lecture to change its group. It carries
           data-job (not just data-jobid) because the drag layer resolves a
           lecture by that attribute everywhere else. Only a lecture the
           pipeline could act on is draggable -- same predicate as the library,
           so the grip never appears on a row that would refuse to lift. */
        var mDraggable = _jobIsDraggable(m);
        return '<div class="subject-member-row' + (isViewing ? ' active' : '') + '" data-jobid="' + esc(m.id) + '"' +
          (mDraggable ? ' data-lp-drag="lecture" data-job="' + esc(m.id) + '"' : '') + '>' +
          (mDraggable ? '<button type="button" class="lp-drag-grip lp-drag-grip-row" tabindex="-1" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></button>' : '') +
          '<div style="flex:1;min-width:0">' +
            '<div class="subject-member-name" title="' + esc(mName) + '">' + esc(mName) + '</div>' +
            '<div class="subject-member-meta">' + esc(r.label + (m.duration ? ' · ' + fmtDuration(m.duration) : '')) + '</div>' +
          '</div>' +
          '<div style="width:70px;flex:none">' + renderCoverageBarHtml(mPct, mName + ': ' + mPct + '%') + '</div>' +
          '<button type="button" class="lp-hit subject-member-open" data-jobid="' + esc(m.id) + '" title="Open lecture">Open</button>' +
        '</div>';
      }).join('');

      return '<div class="subject-card lp-card" data-lp-drop="group" data-group="' + esc(grpName) + '">' +
        '<div class="subject-card-head">' +
          '<div style="flex:1 1 12rem;min-width:0">' +
            '<div class="subject-card-title-wrap">' +
              '<span class="subject-card-title" data-group="' + esc(grpName) + '" title="' + esc(grpName) + '\nClick to rename">' + esc(grpName) + '</span>' +
              '<button type="button" class="subject-rename-btn" data-group="' + esc(grpName) + '" title="Rename subject group"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg></button>' +
            '</div>' +
            '<div class="subject-card-meta">' + members.length + (members.length === 1 ? ' lecture' : ' lectures') + ' · ' + doneCount + ' ready</div>' +
          '</div>' +
          '<button type="button" class="lp-hit lp-press-sm subject-study-btn" data-group="' + esc(grpName) + '" title="Study entire subject">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="5 3 19 12 5 21 5 3"/></svg>Study Subject' +
          '</button>' +
        '</div>' +
        '<div class="subject-coverage-section">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px \'JetBrains Mono\';color:var(--muted);margin-bottom:6px">' +
            '<span>SUBJECT MASTERY</span>' +
          '</div>' +
          renderCoverageBarHtml(cov, 'Overall subject mastery: ' + cov + '%') +
        '</div>' +
        '<div class="subject-members-list">' + memberListHtml + '</div>' +
      '</div>';
    }).join('');
  }

  function wireSubjectEvents() {
    var searchInput = $('subjects-filter-input');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        subjectFilterQuery = this.value;
        renderSubjects();
      });
    }

    var grid = $('subjects-grid');
    if (grid) {
      grid.addEventListener('click', function (e) {
        var openBtn = e.target.closest('.subject-member-open');
        if (openBtn) {
          var jid = openBtn.dataset.jobid;
          if (jid) selectJob(jid, { screen: 'review' });
          return;
        }
        var studyBtn = e.target.closest('.subject-study-btn');
        if (studyBtn) {
          var grp = studyBtn.dataset.group;
          if (grp) studySubjectGroup(grp);
          return;
        }
        var renameBtn = e.target.closest('.subject-rename-btn') || e.target.closest('.subject-card-title');
        if (renameBtn) {
          var groupName = renameBtn.dataset.group;
          if (groupName) handleSubjectCardRename(renameBtn.closest('.subject-card'), groupName);
          return;
        }
      });
    }

    var jobsContainer = $('jobs-grid') || document.body;
    jobsContainer.addEventListener('click', function (e) {
      var badge = e.target.closest('.lp-subject-badge');
      if (badge && !badge.querySelector('input')) {
        e.stopPropagation();
        handleHomeBadgeInlineRename(badge);
      }
    });
  }

  function handleHomeBadgeInlineRename(badgeEl) {
    var jobId = badgeEl.dataset.jobid;
    var currentVal = badgeEl.dataset.subject || '';
    badgeEl.innerHTML = '<input class="lp-subject-inline-input" type="text" value="' + esc(currentVal) + '" data-prev="' + esc(currentVal) + '" style="font:700 11px \'JetBrains Mono\';width:80px;padding:2px 4px;border:1.5px solid var(--blue);border-radius:4px;background:var(--panel);color:var(--ink)">';
    var input = badgeEl.querySelector('input');
    if (!input) return;
    input.focus();
    input.select();
    var committed = false;
    function commit() {
      if (committed) return;
      committed = true;
      var nextVal = input.value.trim();
      if (nextVal && nextVal !== currentVal) {
        if (lpBridge.connected()) lpBridge.call('set_job_group', jobId, nextVal);
        var job = _jobById(jobId);
        if (job) job.group = nextVal;
        toast('Subject updated to ' + nextVal);
      }
      renderJobs();
      if (typeof LP !== 'undefined' && LP.state && LP.state.screen === 'subjects') renderSubjects();
    }
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      if (e.key === 'Escape') { e.preventDefault(); committed = true; renderJobs(); }
    });
    input.addEventListener('blur', function () { commit(); });
  }

  function handleSubjectCardRename(cardEl, oldGroup) {
    handleGroupRename(cardEl && cardEl.querySelector('.subject-card-title'), oldGroup,
      'font:700 18px \'Space Grotesk\'');
  }
  /* ONE rename implementation, two surfaces. The Subjects card and the library
     group header rename the same thing -- every lecture whose subject is this
     name -- so they must not be allowed to drift into two behaviours. Only the
     input's type size differs, because one sits in an 18px heading and the
     other in an 11px mono chip. */
  function handleGroupRename(titleEl, oldGroup, fontCss) {
    if (!titleEl) return;
    titleEl.innerHTML = '<input class="subject-card-title-input" type="text" value="' + esc(oldGroup) + '" style="' + fontCss + ';padding:3px 8px;border:2px solid var(--blue);border-radius:6px;background:var(--panel);color:var(--ink);width:100%;min-width:90px;box-sizing:border-box">';
    var input = titleEl.querySelector('input');
    if (!input) return;
    input.focus();
    input.select();
    var committed = false;
    function commit() {
      if (committed) return;
      committed = true;
      var nextGroup = input.value.trim();
      if (nextGroup && nextGroup !== oldGroup) {
        var allJobs = (typeof LP !== 'undefined' && LP.data && LP.data.jobs) || [];
        var memberIds = allJobs.filter(function (j) { return (jobGroup(j) || 'General') === oldGroup; }).map(function (j) { return j.id; });
        if (memberIds.length) {
          if (lpBridge.connected()) lpBridge.call('set_jobs_group', JSON.stringify(memberIds), nextGroup);
          allJobs.forEach(function (j) {
            if (memberIds.indexOf(j.id) >= 0) j.group = nextGroup;
          });
          // Study keeps its own copy of the scope; without this the Subject
          // Overview headline kept showing the pre-rename name.
          if (typeof studyV2 !== 'undefined' && studyV2.scope && studyV2.scope.groupName === oldGroup) {
            studyV2.scope.groupName = nextGroup;
            if (LP.state.screen === 'study') {
              renderStudyScopeHeader();
              renderStudyV2Overview();
            }
          }
          toast('Renamed subject to ' + nextGroup + ' (' + memberIds.length +
            (memberIds.length === 1 ? ' lecture updated)' : ' lectures updated)'));
        }
      }
      renderSubjects();
      renderJobs();
    }
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      if (e.key === 'Escape') { e.preventDefault(); committed = true; renderSubjects(); renderJobs(); }
    });
    input.addEventListener('blur', function () { commit(); });
  }

  function studySubjectGroup(groupName) {
    openGroupStudy(groupName, { jobId: 'all' });
  }

  /* Collapsed groups, remembered by group NAME rather than by job id: the
     student collapses "CL100", not a set of lectures, so adding a lecture to a
     collapsed course must not silently reopen it. Survives restart. */
  var COLLAPSED_GROUPS_KEY = 'lecturepack.home.collapsedGroups';
  function collapsedGroups() {
    try {
      var raw = JSON.parse(browserStorage().getItem(COLLAPSED_GROUPS_KEY) || '{}');
      return raw && typeof raw === 'object' ? raw : {};
    } catch (e) { return {}; }
  }
  function toggleGroupCollapsed(name) {
    if (!name) return;
    var state = collapsedGroups();
    if (state[name]) delete state[name]; else state[name] = true;
    try { browserStorage().setItem(COLLAPSED_GROUPS_KEY, JSON.stringify(state)); } catch (e) {}
    renderJobs();
  }
  function _jobById(id) {
    return (LP.data.jobs || []).filter(function (j) { return j && j.id === id; })[0] || null;
  }
  function lectureStatusText(job) {
    if (!job) return '';
    if (job.status === 'running') return 'Processing ' + (job.pct || 0) + '%';
    if (job.status === 'queued') return _jobInQueue(job.id) ? 'Queued' : 'Ready';
    if (job.status === 'done') return 'Complete';
    if (job.status === 'failed') return 'Failed';
    if (job.status === 'paused') return 'Paused';
    if (job.status === 'interrupted') return 'Interrupted';
    return job.status || '';
  }
  function sensibleJobScreen(job) {
    if (!job || job.status !== 'done') return 'process';
    var saved = resumeStore && resumeStore.load ? resumeStore.load(job.id) : null;
    return saved && /^(review|transcript|study|exports)$/.test(saved.screen) ? saved.screen : 'review';
  }
  function renameJobDialog(job) {
    if (!job || !job.id) return;
    lpModal({
      title: 'Rename lecture',
      bodyHtml: '<label for="lp-rename-input" style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted);margin-bottom:7px">Display title</label>' +
        '<input id="lp-rename-input" type="text" maxlength="180" value="' + esc(job.name || '') + '" style="width:100%;box-sizing:border-box;font:600 14px \'Space Grotesk\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">',
      actions: [{ label: 'Cancel' }, { label: 'Rename', primary: true, onClick: function () {
        var input = $('lp-rename-input');
        var title = (input && input.value || '').trim();
        if (!title) { toast('Enter a lecture title.'); return true; }
        return lpBridge.call('rename_job', job.id, title).then(function (result) {
          if (!result || result.ok === false) return;
          job.name = result.title || title;
          if (LP.state.jobId === job.id) setActiveJob(job.id, job.name);
          renderJobs(); renderJobSwitcher(); renderLectureSwitcher();
        });
      } }]
    });
    setTimeout(function () { var input = $('lp-rename-input'); if (input) { input.focus(); input.select(); } }, 30);
  }
  function renderLectureSwitcher() {
    var panel = $('lecture-switcher'), toggle = $('lecture-switcher-toggle');
    if (!panel || !toggle) return;
    toggle.disabled = !(LP.data.jobs || []).length;
    $('lecture-switcher-arrow').hidden = toggle.disabled;
    var allJobs = LP.data.jobs || [];
    var pinned = [];
    [LP.state.activeJobId, LP.state.jobId].forEach(function (id) {
      var job = allJobs.filter(function (candidate) { return candidate.id === id; })[0];
      if (job && !pinned.some(function (candidate) { return candidate.id === job.id; })) pinned.push(job);
    });
    var pinnedIds = pinned.map(function (job) { return job.id; });
    var switcherJobs = pinned.concat(allJobs.filter(function (job) {
      return pinnedIds.indexOf(job.id) < 0;
    }).slice(0, Math.max(0, 12 - pinned.length)));
    panel.innerHTML = switcherJobs.map(function (job) {
      return '<button type="button" role="option" data-switch-job="' + esc(job.id) + '" aria-selected="' + (job.id === LP.state.jobId ? 'true' : 'false') + '" style="width:100%;display:flex;align-items:center;gap:10px;padding:8px;background:' + (job.id === LP.state.jobId ? 'var(--panel2)' : 'transparent') + ';border:0;border-radius:8px;color:var(--ink);cursor:pointer;text-align:left">' +
        '<span style="width:54px;height:34px;flex:none;border-radius:6px;overflow:hidden;background:var(--sunk);position:relative">' + posterHtml(job) + '</span>' +
        '<span style="flex:1;min-width:0;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(job.name || 'Lecture') + '</span>' +
        '<span style="font:600 10px \'JetBrains Mono\';color:' + (job.status === 'failed' ? 'var(--red)' : job.status === 'running' ? 'var(--orange-ink)' : 'var(--muted)') + ';white-space:nowrap">' + esc(lectureStatusText(job)) + '</span></button>';
    }).join('');
  }
  function hideLectureContextMenu() {
    var menu = $('lecture-context-menu');
    if (menu) menu.hidden = true;
  }
  function lectureContextActions(job) {
    var actions = [];
    function add(label, run, danger) { actions.push({ label: label, run: run, danger: !!danger }); }
    function divider() { actions.push({ divider: true }); }
    if (job.status === 'done') {
      add('Open', function () { selectJob(job.id, { screen: sensibleJobScreen(job) }); });
      add('Open Review', function () { selectJob(job.id, { screen: 'review' }); });
      add('Open Transcript', function () { selectJob(job.id, { screen: 'transcript' }); });
      add('Open Study', function () { selectJob(job.id, { screen: 'study' }); });
      add('Export', function () { selectJob(job.id, { screen: 'exports' }); });
      divider();
      add('Rename', function () { renameJobDialog(job); });
      add('Reveal in Explorer', function () { lpBridge.call('open_job_folder', job.id); });
      divider();
      add('Remove from Library', function () { confirmDeleteJob(job); }, true);
    } else if (job.status === 'running' || job.status === 'paused') {
      add('Open Process', function () { selectJob(job.id, { screen: 'process' }); });
      add('Cancel Processing', function () { if (job.id === LP.state.activeJobId) lpBridge.call('cancel_job'); }, true);
      divider(); add('Rename', function () { renameJobDialog(job); });
      add('Reveal in Explorer', function () { lpBridge.call('open_job_folder', job.id); });
    } else if (job.status === 'queued') {
      add('Open Process', function () { selectJob(job.id, { screen: 'process' }); });
      if (_jobInQueue(job.id)) {
        var rows = (LP.data.queue && LP.data.queue.queue) || [];
        var index = rows.map(function (row) { return row.id; }).indexOf(job.id);
        add('Move Up', function () { if (index > 0) lpBridge.call('reorder_queue', job.id, index - 1); });
        add('Move Down', function () { if (index >= 0 && index < rows.length - 1) lpBridge.call('reorder_queue', job.id, index + 1); });
        add('Remove from Queue', function () { lpBridge.call('remove_from_queue', job.id); });
      }
      divider(); add('Rename', function () { renameJobDialog(job); });
    } else {
      add('Open Process', function () { selectJob(job.id, { screen: 'process' }); });
      add('Retry', function () { selectJob(job.id, { screen: 'process' }); lpBridge.call('restart_job', job.id); });
      add('View Error Details', function () { lpModal({ title: 'Processing error', bodyHtml: '<div style="white-space:pre-wrap;overflow-wrap:anywhere">' + esc(job.error || 'No technical details were saved for this failure.') + '</div>', actions: [{ label: 'Close', primary: true }] }); });
      divider(); add('Rename', function () { renameJobDialog(job); });
      add('Reveal in Explorer', function () { lpBridge.call('open_job_folder', job.id); });
    }
    return actions;
  }
  function showLectureContextMenu(job, x, y) {
    var menu = $('lecture-context-menu');
    if (!menu || !job) return;
    var actions = lectureContextActions(job);
    menu.innerHTML = actions.map(function (action, index) {
      if (action.divider) return '<div style="height:1px;background:var(--line);margin:5px 3px"></div>';
      return '<button type="button" role="menuitem" data-context-index="' + index + '" style="display:block;width:100%;padding:8px 10px;text-align:left;background:transparent;border:0;border-radius:6px;color:' + (action.danger ? 'var(--red)' : 'var(--ink)') + ';font:600 12px \'Space Grotesk\';cursor:pointer">' + esc(action.label) + '</button>';
    }).join('');
    menu._actions = actions;
    menu.hidden = false;
    menu.style.left = Math.min(x, window.innerWidth - menu.offsetWidth - 8) + 'px';
    menu.style.top = Math.min(y, window.innerHeight - menu.offsetHeight - 8) + 'px';
  }
  function _jobInQueue(id) {
    var q = (LP.data.queue && LP.data.queue.queue) || [];
    return q.some(function (r) { return r.id === id; });
  }
  // "Imported but never processed" -- the backend has used several names for
  // that state over time ('queued', 'ready', 'unstarted', 'imported'), and
  // matching only 'queued' left freshly imported lectures undraggable.
  var UNSTARTED_STATUSES = { queued: true, ready: true, unstarted: true, imported: true };
  function _jobIsReady(j) {
    if (!j || !j.id || j.status === 'running') return false;
    return UNSTARTED_STATUSES[j.status] === true && !_jobInQueue(j.id);
  }
  // A lecture that has already finished (or failed, or was cancelled) can be
  // put back through the pipeline. This is deliberately SEPARATE from
  // _jobIsReady, which means "imported but never processed" and still governs
  // the Start/Options/Remove buttons -- widening that would have put a Start
  // button on every finished lecture. Only dragging consults this.
  var REPROCESSABLE_STATUSES = { done: true, failed: true, cancelled: true, interrupted: true };
  function _jobIsReprocessable(j) {
    return !!j && !!j.id && REPROCESSABLE_STATUSES[j.status] === true && !_jobInQueue(j.id);
  }
  function _jobIsDraggable(j) {
    return _jobIsReady(j) || _jobIsReprocessable(j);
  }
  function internalDragIdsFor(sourceId) {
    var selected = LP.state.selecting && LP.state.selected[sourceId];
    var ids = [];
    (LP.data.jobs || []).forEach(function (job) {
      if (!job || !job.id || !(_jobIsDraggable(job) && (!LP.state.selecting || !selected || LP.state.selected[job.id]))) return;
      if (!selected && job.id !== sourceId) return;
      if (ids.indexOf(job.id) < 0) ids.push(job.id);
    });
    return ids;
  }
  function readInternalJobDrag(event) {
    var transfer = event && event.dataTransfer;
    if (!transfer) return [];
    var raw = '';
    try { raw = transfer.getData(INTERNAL_JOB_DRAG_MIME); } catch (e) {}
    if (!raw) return internalJobDragIds.slice();
    try {
      var ids = JSON.parse(raw);
      return Array.isArray(ids) ? ids.filter(function (id, index) { return typeof id === 'string' && id && ids.indexOf(id) === index; }) : [];
    } catch (e) { return []; }
  }

  /* ==========================================================================
     LPDrag -- the ONE internal drag system.

     Why this exists at all: internal drag used to be a single hardcoded
     gesture (a lecture card onto Process) wired with listeners bound directly
     to elements. Two consequences, both of which read to the user as "internal
     drag is broken":

       1. Releasing anywhere else did NOTHING AND SAID NOTHING. The window-level
          dragover called preventDefault() before it checked whether the drag
          was internal, so the entire window advertised itself as a valid drop
          target for a lecture -- the cursor promised a drop that no handler
          would ever act on. A user cannot tell that apart from a broken app.
       2. Listeners bound per element could not survive a rerender. The queue
          and the library both rebuild via innerHTML on every poll, so any
          handler attached to a card was destroyed seconds after it was
          attached. Delegation from `document` is not a style preference here,
          it is the only thing that works on this markup.

     So: targets DECLARE themselves in markup with data-lp-drop, sources with
     data-lp-drag, and everything below is delegated. Adding a surface later is
     a render-time attribute plus a registry entry -- not new event wiring.

     Invariant worth keeping: every gesture here has a pointer-free equivalent
     that already shipped (queue rows have Move up / Move down buttons and
     context-menu items; group assignment has the card's Group action and the
     bulk Group dialog). Drag is an accelerator layered on top, never the only
     route to a capability.
     ====================================================================== */

  /* ======================================================================
     LPAudio: Zero-Asset Mechanical Web Audio Cues.
     Synthesised on demand with the Web Audio API without shipping audio assets.
     Square-wave click on button depression, low-frequency pop on card drop,
     light ratchet on queue reordering, and tactile toggle clack on switch.
     ====================================================================== */
  var LPAudio = (function () {
    var audioCtx = null;

    function soundEnabled() {
      /* Opt-IN, matching the drag cue ('lecturepack.drag.sound' === 'on') further
         down. This defaulted to ON with an off-switch nothing ever wrote: no
         Settings control exists, and the key appeared exactly once in the whole
         codebase -- this read. The listener that calls playClick() matches
         `button, .lp-hit, .nav-item, [role="button"], .export-chip, [data-lp-drag]`,
         i.e. effectively every press, so a student running the app for hours got an
         unmutable click track. Audible feedback nobody asked for and cannot turn
         off is a defect; the cue itself stays, reachable by setting the key. */
      try { return localStorage.getItem('lecturepack.sound.enabled') === 'on'; }
      catch (e) { return false; }
    }

    function getContext() {
      if (!soundEnabled()) return null;
      try {
        var Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        if (!audioCtx) audioCtx = new Ctx();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        return audioCtx;
      } catch (e) { return null; }
    }

    function playClick() {
      try {
        var ctx = getContext();
        if (!ctx) return;
        var now = ctx.currentTime;
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(1200, now);
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.010);
        gain.gain.setValueAtTime(0.02, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.010);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(now); osc.stop(now + 0.012);
      } catch (e) {}
    }


    function playRatchet() {
      try {
        var ctx = getContext();
        if (!ctx) return;
        var now = ctx.currentTime;
        [0, 0.018].forEach(function (offset) {
          var osc = ctx.createOscillator();
          var gain = ctx.createGain();
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(1300, now + offset);
          osc.frequency.exponentialRampToValueAtTime(600, now + offset + 0.008);
          gain.gain.setValueAtTime(0.03, now + offset);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.008);
          osc.connect(gain); gain.connect(ctx.destination);
          osc.start(now + offset); osc.stop(now + offset + 0.010);
        });
      } catch (e) {}
    }

    function playToggle(isEngaged) {
      try {
        var ctx = getContext();
        if (!ctx) return;
        var now = ctx.currentTime;
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = 'sine';
        if (isEngaged) {
          osc.frequency.setValueAtTime(440, now);
          osc.frequency.exponentialRampToValueAtTime(880, now + 0.018);
        } else {
          osc.frequency.setValueAtTime(780, now);
          osc.frequency.exponentialRampToValueAtTime(360, now + 0.016);
        }
        gain.gain.setValueAtTime(0.035, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.020);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(now); osc.stop(now + 0.022);
      } catch (e) {}
    }

    return {
      playClick: playClick,
      playRatchet: playRatchet,
      playToggle: playToggle,
      soundEnabled: soundEnabled
    };
  })();

  /* ======================================================================
     LPNumberRoller: Rolling Monospace Odometer Reels.
     Smooth vertical digit reels for percentages and counters.
     ====================================================================== */
  var LPNumberRoller = (function () {
    /* Rolls a number's digits like an odometer.

       Two things were wrong with this before it was wired up. It was never called
       at all -- the whole module, and ~35 lines of .lp-odometer CSS, were
       unreachable. And rebuilding innerHTML on every update defeats the very
       transition it depends on: a brand-new ribbon element has no previous
       transform to animate FROM, so each digit rendered instantly at its final
       position. Rolling requires the SAME element to persist and only its
       transform to change, which is what the fast path below does. */
    function setRolling(el, numText) {
      if (!el) return;
      var str = String(numText == null ? '' : numText);
      if (el.dataset.rollValue === str) return;      // nothing changed
      var ribbons = el.querySelectorAll('.lp-odometer-digit');
      var same = el.firstChild && ribbons.length &&
        el.dataset.rollShape === str.replace(/[0-9]/g, '#');
      if (same) {
        /* Same shape ("12" -> "34", but not "9" -> "10"): move the existing
           ribbons, so the CSS transition has somewhere to travel from. */
        var di = 0, ok = true;
        for (var k = 0; k < str.length; k++) {
          var c = str.charAt(k);
          if (!/[0-9]/.test(c)) continue;
          var rib = ribbons[di] && ribbons[di].querySelector('.lp-odometer-ribbon');
          var hid = ribbons[di] && ribbons[di].querySelector('.lp-odometer-hidden');
          if (!rib) { ok = false; break; }
          ribbons[di].dataset.digit = c;
          rib.style.transform = 'translateY(-' + (parseInt(c, 10) * 10) + '%)';
          if (hid) hid.textContent = c;
          di++;
        }
        var od = el.querySelector('.lp-odometer');
        if (od) od.setAttribute('aria-label', str);
        if (ok) { el.dataset.rollValue = str; return; }
      }
      el.dataset.rollValue = str;
      el.dataset.rollShape = str.replace(/[0-9]/g, '#');
      var digits = str.split('');
      var html = '<span class="lp-odometer" aria-label="' + esc(str) + '">';
      for (var i = 0; i < digits.length; i++) {
        var ch = digits[i];
        if (/[0-9]/.test(ch)) {
          var d = parseInt(ch, 10);
          html += '<span class="lp-odometer-digit" data-digit="' + d + '"><span class="lp-odometer-ribbon" style="transform:translateY(-' + (d * 10) + '%)">' +
            '0<br>1<br>2<br>3<br>4<br>5<br>6<br>7<br>8<br>9' +
            '</span><span class="lp-odometer-hidden">' + d + '</span></span>';
        } else {
          html += '<span class="lp-odometer-char">' + esc(ch) + '</span>';
        }
      }
      html += '</span>';
      el.innerHTML = html;
    }
    return { setRolling: setRolling };
  })();

  /* ======================================================================
     Physical Review Mode Polish: Loupe, Keyboard Stamping, Edge Flashes.
     ====================================================================== */
  var viewportFlashEl = null;
  function getViewportFlash() {
    if (viewportFlashEl) return viewportFlashEl;
    viewportFlashEl = document.createElement('div');
    viewportFlashEl.id = 'lp-viewport-flash';
    viewportFlashEl.className = 'lp-viewport-flash';
    viewportFlashEl.setAttribute('aria-hidden', 'true');
    document.body.appendChild(viewportFlashEl);
    return viewportFlashEl;
  }

  function flashViewport(tone) {
    var el = getViewportFlash();
    el.className = 'lp-viewport-flash';
    void el.offsetWidth;
    el.className = 'lp-viewport-flash lp-viewport-flash-' + tone;
    setTimeout(function () {
      el.className = 'lp-viewport-flash';
    }, 140);
  }

  var slideLoupeEl = null;
  function getSlideLoupe() {
    if (slideLoupeEl) return slideLoupeEl;
    slideLoupeEl = document.createElement('div');
    slideLoupeEl.id = 'lp-slide-loupe';
    slideLoupeEl.className = 'lp-slide-loupe';
    slideLoupeEl.hidden = true;
    slideLoupeEl.setAttribute('aria-hidden', 'true');
    document.body.appendChild(slideLoupeEl);
    return slideLoupeEl;
  }

  function showSlideLoupe(slideIndex, clientX, clientY) {
    if (LP.state.screen !== 'review' || (typeof LPDrag !== 'undefined' && LPDrag.dragging && LPDrag.dragging())) {
      hideSlideLoupe();
      return;
    }
    var slide = LP.data.slides && LP.data.slides[slideIndex];
    if (!slide) { hideSlideLoupe(); return; }
    var el = getSlideLoupe();
    var state = slideReviewState(slide);
    var label = state === 'rejected' ? 'Rejected' : 'Kept';
    var badgeColor = state === 'rejected' ? 'var(--red)' : 'var(--blue)';
    var imgHtml = slideImg(slide.img || slide.thumb, 'width:100%;height:auto;display:block;border-radius:4px;', 32, 'var(--muted)');

    el.innerHTML = '<div class="lp-loupe-inner">' +
      '<div class="lp-loupe-img-wrap">' + imgHtml + '</div>' +
      '<div class="lp-loupe-meta">' +
        '<span class="lp-loupe-title">Slide ' + (slideIndex + 1) + '</span>' +
        '<span class="lp-loupe-time">' + esc(slide.time || '') + '</span>' +
        '<span class="lp-loupe-badge" style="color:' + badgeColor + '">' + label + '</span>' +
      '</div>' +
    '</div>';

    var loupeW = 280, loupeH = 180;
    var x = clientX + 24;
    var y = clientY - 60;
    if (x + loupeW > window.innerWidth - 12) x = clientX - loupeW - 24;
    if (y < 12) y = 12;
    if (y + loupeH > window.innerHeight - 12) y = window.innerHeight - loupeH - 12;

    el.style.left = Math.round(x) + 'px';
    el.style.top = Math.round(y) + 'px';
    el.hidden = false;
    el.classList.add('is-visible');
  }

  function hideSlideLoupe() {
    if (slideLoupeEl) {
      slideLoupeEl.hidden = true;
      slideLoupeEl.classList.remove('is-visible');
    }
  }

  var LPDrag = (function () {
    // The live drag: {kind, ids, label, hint}. Null whenever nothing is
    // in flight, which is also the guard that keeps the external file-drop
    // path (which works, and must keep working) completely untouched.
    var active = null;
    var armed = null;      // resolved valid target for the current pointer spot
    var didDrop = false;
    var stripEl = null, insertEl = null, hideTimer = 0;
    var lastAfter = false;   // reorder side, kept across a no-op for hysteresis

    function strip() {
      if (stripEl) return stripEl;
      stripEl = document.createElement('div');
      stripEl.className = 'lp-drag-strip';
      stripEl.id = 'lp-drag-strip';
      stripEl.hidden = true;
      // role=status + aria-live makes this the SAME string the screen reader
      // hears and the sighted user reads, so the two channels cannot drift.
      stripEl.setAttribute('role', 'status');
      stripEl.setAttribute('aria-live', 'polite');
      document.body.appendChild(stripEl);
      return stripEl;
    }
    // tone: '' (neutral guidance) | 'ok' (will land here) | 'bad' (will not)
    function say(text, tone) {
      var el = strip();
      if (hideTimer) { clearTimeout(hideTimer); hideTimer = 0; }
      el.textContent = '';
      var verb = document.createElement('span');
      verb.className = 'lp-drag-strip-verb';
      /* 'done' exists because a completed action must not be phrased as an
         invitation: after the drop the strip read "Release to ... moved to
         position 1", which is an instruction for something already finished. */
      verb.textContent = tone === 'bad' ? "Can't drop here"
        : tone === 'done' ? 'Done —'
        : tone === 'ok' ? 'Release to' : 'Dragging';
      el.appendChild(verb);
      var body = document.createElement('span');
      body.textContent = ' ' + text;
      el.appendChild(body);
      el.dataset.tone = tone || '';
      el.hidden = false;
    }
    function hideStrip(delay) {
      if (!stripEl) return;
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () {
        hideTimer = 0;
        if (stripEl) { stripEl.hidden = true; stripEl.textContent = ''; stripEl.dataset.tone = ''; }
      }, delay || 0);
    }
    function insertBar() {
      if (insertEl) return insertEl;
      insertEl = document.createElement('div');
      insertEl.className = 'lp-drop-insert';
      insertEl.id = 'lp-drop-insert';
      insertEl.hidden = true;
      insertEl.setAttribute('aria-hidden', 'true');
      document.body.appendChild(insertEl);
      return insertEl;
    }
    function applyFlipSeparation(targetRowId, after) {
      var items = document.querySelectorAll('[data-lp-drag="queue"], .job-card, .queue-item');
      if (!items || !items.length) return;
      if (!targetRowId) {
        Array.prototype.forEach.call(items, function (card) {
          if (card.style && card.style.transform && !card.classList.contains('lp-drag-proxy')) {
            card.style.transform = '';
            card.style.transition = '';
          }
        });
        return;
      }
      var target = document.querySelector('[data-lp-drag][data-queueid="' + cssEscapeId(targetRowId) + '"]');
      if (!target) return;
      var targetRect = target.getBoundingClientRect();
      Array.prototype.forEach.call(items, function (card) {
        if (card.classList.contains('lp-dragging') || card.classList.contains('lp-drag-proxy')) return;
        var r = card.getBoundingClientRect();
        card.style.transition = 'transform 180ms cubic-bezier(0.2, 0.9, 0.3, 1.2)';
        if (after && r.left > targetRect.left) {
          card.style.transform = 'translateX(6px)';
        } else if (!after && r.left >= targetRect.left) {
          card.style.transform = 'translateX(6px)';
        } else {
          card.style.transform = '';
        }
      });
    }

    // The queue is a WRAPPING grid in row-major order, not a vertical list, so
    // the indicator is a vertical bar on the leading or trailing edge of the
    // card it would insert next to. Measured from a live rect, so it lands
    // correctly no matter how the grid has wrapped.
    function showInsert(rect, after, targetRowId) {
      var el = insertBar();
      el.style.top = rect.top + 'px';
      el.style.height = rect.height + 'px';
      el.style.left = ((after ? rect.right + 3 : rect.left - 6)) + 'px';
      el.hidden = false;
      el.classList.add('lp-drop-insert-active');
      applyFlipSeparation(targetRowId, after);
    }
    function hideInsert() {
      if (insertEl) {
        insertEl.hidden = true;
        insertEl.classList.remove('lp-drop-insert-active');
      }
      applyFlipSeparation(null);
    }

    /* "Where can I actually drop this?" -- the question the old system could not
       answer, because only the target under the pointer ever reacted. Every
       valid destination for the drag now announces itself the MOMENT the lift
       starts, so the answer is on screen before the user goes hunting.
       Reorder targets are excluded on purpose: for a reorder every row is
       trivially a candidate, so outlining all of them says nothing -- the
       insertion bar is the real indicator there. */
    function markCandidates(kind) {
      if (kind !== 'lecture') return 0;
      var lit = 0;
      Array.prototype.forEach.call(document.querySelectorAll('[data-lp-drop]'), function (el) {
        var desc = descriptorFor(el);
        if (!desc || desc.drop === 'queue-reorder' || !desc.kinds[kind]) return;
        if (el.offsetParent === null) return;   // hidden on this screen
        el.classList.add('lp-drop-candidate');
        lit++;
      });
      return lit;
    }
    function clearCandidates() {
      Array.prototype.forEach.call(document.querySelectorAll('.lp-drop-candidate'), function (el) {
        el.classList.remove('lp-drop-candidate');
      });
    }

    function clearTargetPaint() {
      Array.prototype.forEach.call(document.querySelectorAll('.lp-drop-ok, .lp-drop-bad'), function (el) {
        el.classList.remove('lp-drop-ok'); el.classList.remove('lp-drop-bad');
      });
      // The pre-existing Process-target class predates this system and is still
      // asserted by tests, so it is kept in lockstep rather than replaced.
      Array.prototype.forEach.call(document.querySelectorAll('.lp-existing-drop-hover'), function (el) {
        el.classList.remove('lp-existing-drop-hover');
      });
    }

    /* The registry. `kinds` is which drag types a target accepts; `reason`
       explains a refusal in the user's words, never in the app's. */
    var TARGETS = [
      { drop: 'process', kinds: { lecture: true },
        reason: 'only a lecture that has not been processed yet can be queued here',
        label: function () { return 'queue for processing'; } },
      { drop: 'group', kinds: { lecture: true },
        reason: 'only lectures can be filed under a subject',
        label: function (el) { return 'file under ' + (el.dataset.group || 'this subject'); } },
      { drop: 'queue-reorder', kinds: { queue: true },
        reason: 'only a queued row can be reordered here',
        label: function () { return 'move it here in the queue'; } }
    ];
    function descriptorFor(el) {
      var key = el && el.dataset ? el.dataset.lpDrop : '';
      for (var i = 0; i < TARGETS.length; i++) if (TARGETS[i].drop === key) return TARGETS[i];
      return null;
    }

    /* Queue reorder maths, kept out of the event handler so it is testable by
       inspection. `before` is the index the row would be inserted in front of;
       reorder_queue takes a FINAL absolute index, so removing the row from
       earlier in the list shifts the destination down by one. */
    function reorderIndex(from, before) {
      var target = before;
      if (from < target) target -= 1;
      return target;
    }

    /* The subject a lecture would DISPLAY under if it were filed into `group`.
       "Ungrouped" is not a real subject: filing there clears j.group, after
       which jobGroup() re-infers the subject from the lecture's NAME -- so
       clearing the group of "CL100 - Day 9 ..." leaves it under CL100 exactly
       where it was. Without this, the strip cheerfully confirmed "filed under
       Ungrouped" for a change with no visible effect, which is the same
       silent-failure class as the no-op reorder. */
    function bucketAfter(job, group) {
      var target = group === 'Ungrouped' ? '' : group;
      return target || inferredJobGroup(job && (job.name || job.title));
    }

    function queueRowIds() {
      return (((LP.data.queue && LP.data.queue.queue) || []).map(function (r) { return r && r.id; }));
    }

    /* ================= the LIFT: pointer-driven, not native ==================
       Native HTML5 drag was replaced HERE and only here -- the registry, the
       status strip, the insertion bar and the actions above are untouched.

       Why: the native drag preview is a bitmap the OS composites, so it cannot
       be tilted, scaled, shadowed or eased. Physical feel (a card that lifts,
       tilts and snaps home) is only reachable by drawing the carried object
       ourselves and following the pointer.

       What this deliberately does NOT take over: drops of real files from the
       OS. Those can only arrive as native drag events, so the window-level
       dragover/drop handlers still own them, untouched. Two input paths is
       inherent to wanting physics AND OS file drops -- no library removes that,
       because none of them can style the OS drag image either. */
    var LIFT_THRESHOLD = 6;      // px of travel before a click becomes a drag
    var pending = null;          // pointer down on a source, not yet a drag
    var proxy = null;            // the thing the user is actually carrying
    var proxyGrab = { x: 0, y: 0 };
    var sourceRect = null;
    var justDragged = false;     // swallow the click that follows a real drag

    /* Audio cues, OFF unless the student turns them on. This app runs for
       hours at a time on a laptop in a library; a click on every lift is the
       kind of thing that is charming for ten minutes and intolerable by the
       afternoon, so silence is the default and the preference is persisted.
       Synthesised with WebAudio rather than shipped as .wav files: two short
       envelopes cost nothing to package and cannot go missing from a build. */
    var audioCtx = null;
    function dragSoundEnabled() {
      try { return localStorage.getItem('lecturepack.drag.sound') === 'on'; } catch (e) { return false; }
    }
    function dragCue(kind) {
      if (!dragSoundEnabled()) return;
      try {
        var Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        audioCtx = audioCtx || new Ctx();
        var now = audioCtx.currentTime;
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        // lift = a light woody click; drop = a lower, softer thud.
        var freq = kind === 'lift' ? 880 : 180;
        var dur = kind === 'lift' ? 0.045 : 0.12;
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, now);
        osc.frequency.exponentialRampToValueAtTime(Math.max(60, freq * 0.55), now + dur);
        gain.gain.setValueAtTime(0.0001, now);
        gain.gain.exponentialRampToValueAtTime(kind === 'lift' ? 0.05 : 0.09, now + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
        osc.connect(gain); gain.connect(audioCtx.destination);
        osc.start(now); osc.stop(now + dur + 0.02);
      } catch (e) { /* audio is a nicety; never let it break a drag */ }
    }

    var dragVelocity = { vx: 0, lastX: 0, lastTime: 0, currentTilt: 0 };

    function reducedMotion() {
      try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
    }
    function proxyTransform(x, y, settled, tilt) {
      var t = 'translate3d(' + Math.round(x) + 'px,' + Math.round(y) + 'px,0)';
      // The tilt and scale ARE the "lifted off the canvas" cue. Dropped under
      // reduced motion, and dropped again once the card is settling into place.
      if (!settled && !reducedMotion()) {
        var rot = typeof tilt === 'number' ? Math.round(tilt * 10) / 10 : null;
        if (rot === null) t += ' rotate(3.5deg) scale(1.03)';
        else t += ' rotate(' + rot + 'deg) scale(1.03)';
      }
      return t;
    }
    function buildProxy(src, count, x, y) {
      var rect = src.getBoundingClientRect();
      sourceRect = rect;
      proxyGrab = { x: x - rect.left, y: y - rect.top };
      var el = document.createElement('div');
      el.className = 'lp-drag-proxy';
      el.setAttribute('aria-hidden', 'true');
      el.style.width = rect.width + 'px';
      /* A real DECK for a multi-select: up to two faces peeking out behind the
         front one. Offset only -- never fanned at an angle, because a fan
         implies an order the selection does not have. */
      var layers = Math.min(count, 3);
      for (var i = layers - 1; i >= 1; i--) {
        var back = document.createElement('span');
        back.className = 'lp-drag-proxy-back';
        back.style.transform = 'translate(' + (i * 7) + 'px,' + (i * 7) + 'px)';
        el.appendChild(back);
      }
      var face = src.cloneNode(true);
      face.removeAttribute('id');
      face.removeAttribute('draggable');
      face.classList.add('lp-drag-proxy-face');
      face.classList.remove('lp-dragging');
      face.classList.remove('lp-drop-ok');
      face.classList.remove('lp-drop-bad');
      face.classList.remove('lp-drop-candidate');
      face.style.width = rect.width + 'px';
      face.style.margin = '0';
      el.appendChild(face);
      if (count > 1) {
        var chip = document.createElement('span');
        chip.className = 'lp-drag-proxy-count';
        chip.textContent = count;
        el.appendChild(chip);
      }
      document.body.appendChild(el);
      el.style.transform = proxyTransform(rect.left, rect.top);
      proxy = el;
      return el;
    }
    function moveProxy(x, y) {
      if (!proxy) return;
      var now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      var dt = Math.max(1, now - (dragVelocity.lastTime || now));
      var dx = x - (dragVelocity.lastX || x);
      var instVx = dx / dt;
      dragVelocity.vx = dragVelocity.vx * 0.6 + instVx * 0.4;
      dragVelocity.lastX = x;
      dragVelocity.lastTime = now;
      var targetTilt = Math.max(-6, Math.min(6, dragVelocity.vx * 4.0));
      dragVelocity.currentTilt = dragVelocity.currentTilt * 0.5 + targetTilt * 0.5;
      proxy.style.transform = proxyTransform(x - proxyGrab.x, y - proxyGrab.y, false, dragVelocity.currentTilt);
    }
    // Magnetic snap: the card travels to where it landed instead of vanishing.
    function snapProxy(toRect, then) {
      if (!proxy) { then(); return; }
      var el = proxy;
      proxy = null;
      if (reducedMotion() || !toRect) { el.remove(); then(); return; }
      var w = el.offsetWidth || 1, h = el.offsetHeight || 1;
      var x = toRect.left + (toRect.width - w) / 2;
      var y = toRect.top + (toRect.height - h) / 2;
      el.classList.add('lp-drag-proxy-settling');
      el.style.transform = proxyTransform(x, y, true);
      el.style.opacity = '0';
      var done = false;
      var finishSnap = function () {
        if (done) return;
        done = true;
        el.remove();
        then();
      };
      el.addEventListener('transitionend', finishSnap, { once: true });
      // Never strand the proxy on a transitionend that does not arrive.
      setTimeout(finishSnap, 280);
    }
    function paintProxy(state) {
      if (!proxy) return;
      proxy.classList.remove('is-ok');
      proxy.classList.remove('is-bad');
      if (state) proxy.classList.add('is-' + state);
    }
    function cssEscapeId(value) {
      return (window.CSS && CSS.escape) ? CSS.escape(value) : String(value).replace(/"/g, '\\"');
    }

    function beginDrag(src, x, y) {
      var kind = src.dataset.lpDrag;
      if (kind === 'lecture') {
        var ids = internalDragIdsFor(src.dataset.job);
        if (!ids.length) return false;
        internalJobDragIds = ids.slice();
        var first = _jobById(ids[0]);
        active = { kind: 'lecture', ids: ids, from: -1,
          label: ids.length === 1 ? (first && first.name) || 'this lecture' : ids.length + ' lectures',
          hint: 'drop on a subject heading to file it, or on Process to queue it' };
      } else if (kind === 'queue') {
        var qid = src.dataset.queueid;
        var order = queueRowIds();
        var from = order.indexOf(qid);
        if (!qid || from < 0) return false;
        active = { kind: 'queue', ids: [qid], from: from, label: _jobName(qid) || 'this row',
          // Reorder lights no candidates (every row is trivially one), so its
          // own hint is what the opening message uses.
          hint: 'drop between queued lectures to reorder' };
      } else { return false; }
      didDrop = false;
      armed = null;
      dragVelocity.lastX = x;
      dragVelocity.lastTime = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      dragVelocity.vx = 0;
      dragVelocity.currentTilt = 0;
      var lit = markCandidates(active.kind);
      /* Name the payload from the very first frame -- on a multi-select the
         count is the whole point -- and say how many places will take it, now
         that every one of them is outlined on screen. */
      say(active.label + ' — ' + (lit
        ? lit + (lit === 1 ? ' highlighted place' : ' highlighted places') + ' will take it'
        : active.hint || 'drop it on a highlighted target'), '');
      active.ids.forEach(function (id) {
        var card = document.querySelector('[data-lp-drag][data-job="' + cssEscapeId(id) + '"]') ||
                   document.querySelector('[data-lp-drag][data-queueid="' + cssEscapeId(id) + '"]');
        if (card) card.classList.add('lp-dragging');
      });
      src.classList.add('lp-dragging');
      buildProxy(src, active.ids.length, x, y);
      document.body.classList.add('lp-drag-in-flight');
      dragCue('lift');
      return true;
    }

    /* Target resolution by GEOMETRY rather than by event target -- the proxy is
       pointer-events:none, so elementFromPoint sees straight through it to
       whatever is underneath. */
    function updateAt(x, y) {
      if (!active) return;
      var under = document.elementFromPoint(x, y);
      var host = under && under.closest ? under.closest('[data-lp-drop]') : null;
      var desc = descriptorFor(host);
      if (!desc) {
        armed = null; clearTargetPaint(); hideInsert(); paintProxy('');
        say(active.label + ' — no drop target here', '');
        return;
      }
      if (!desc.kinds[active.kind]) {
        /* A REAL target that refuses THIS drag: say why, and make the carried
           card itself look refused. There is no OS cursor doing that job now,
           so the refusal has to be visible on the thing being carried. */
        armed = null; clearTargetPaint(); hideInsert();
        host.classList.add('lp-drop-bad');
        paintProxy('bad');
        say(desc.reason, 'bad');
        return;
      }
      if (desc.drop === 'queue-reorder') {
        var rowId = host.dataset.queueid;
        var order = queueRowIds();
        var over = order.indexOf(rowId);
        if (over < 0) { armed = null; hideInsert(); return; }
        var rect = host.getBoundingClientRect();
        // Midpoint on X, because the grid flows left-to-right. 4px of
        // hysteresis so a trembling hand does not flip the indicator.
        var mid = rect.left + rect.width / 2;
        // Remembered separately from `armed`, because a no-op clears `armed`
        // and the side has to survive that.
        var after = x > mid + 4 ? true : x < mid - 4 ? false : lastAfter;
        lastAfter = after;
        var finalIndex = reorderIndex(active.from, after ? over + 1 : over);
        clearTargetPaint();
        if (finalIndex === active.from || finalIndex < 0) {
          /* A drop that would change nothing is the other thing that reads as
             broken: the user releases, sees no movement, blames the app. It is
             refused outright rather than accepted-and-ignored. */
          armed = null; hideInsert(); paintProxy('bad');
          say(active.label + ' is already in this position', 'bad');
          return;
        }
        armed = { desc: desc, host: host, after: after, index: finalIndex, rect: rect };
        showInsert(rect, after, rowId);
        paintProxy('ok');
        say('move ' + active.label + ' to position ' + (finalIndex + 1) + ' of ' + order.length, 'ok');
        return;
      }
      if (desc.drop === 'group') {
        var moving = active.ids.map(_jobById).filter(Boolean);
        var target = host.dataset.group || '';
        var pointless = moving.length > 0 && moving.every(function (job) {
          return bucketAfter(job, target) === jobGroup(job);
        });
        if (pointless) {
          armed = null; clearTargetPaint(); hideInsert();
          host.classList.add('lp-drop-bad');
          paintProxy('bad');
          say(moving.length === 1
            ? active.label + ' is already filed under ' + jobGroup(moving[0])
            : 'those lectures are already filed here', 'bad');
          return;
        }
      }
      clearTargetPaint(); hideInsert();
      host.classList.add('lp-drop-ok');
      if (desc.drop === 'process') host.classList.add('lp-existing-drop-hover');
      armed = { desc: desc, host: host, rect: host.getBoundingClientRect() };
      paintProxy('ok');
      say(desc.label(host) + ' — ' + active.label, 'ok');
    }

    function commit() {
      if (!active) return;
      if (!armed) { abandon(); return; }
      var target = armed, drag = active;
      didDrop = true;
      clearTargetPaint(); hideInsert();
      dragCue('drop');
      try {
      /* The card flies to where it landed and the action runs when it arrives,
         so a library rerender can never yank the proxy out mid-flight. */
      snapProxy(target.rect, function () {
        if (target.desc.drop === 'group') {
          var group = target.host.dataset.group || '';
          /* "Ungrouped" is a SYNTHETIC bucket the library invents for lectures
             that have no group (renderJobs assigns that label itself), not a
             subject you can belong to. Dropping there therefore has to CLEAR
             the group -- writing the literal string would create a real subject
             named "Ungrouped" that looks identical in the list but stops the
             inferred grouping from ever applying to that lecture again. */
          if (group === 'Ungrouped') group = '';
          assignJobsToGroup(drag.ids, group, target.host);
          say(drag.label + ' filed under ' + (group || 'Ungrouped'), 'done');
          hideStrip(1200);
        } else if (target.desc.drop === 'process') {
          say(drag.label + ' queued for processing', 'done');
          hideStrip(1200);
          dropLecturesOnProcess(drag.ids, target.host);
        } else if (target.desc.drop === 'queue-reorder') {
          say(drag.label + ' moved to position ' + (target.index + 1), 'done');
          hideStrip(1200);
          if (lpBridge.connected()) lpBridge.call('reorder_queue', drag.ids[0], target.index);
          else toast('Preview mode — the queue was not reordered.');
        }
      });
      } finally {
        /* snapProxy runs its callback SYNCHRONOUSLY under prefers-reduced-motion,
           so a throw inside the drop action skipped finish() entirely and left the
           UI carrying a phantom card with external file drop dead. */
        finish();
      }
    }

    /* Released over nothing, or cancelled. THE anti-silent-failure rule, now
       with a physical form: the card visibly returns to where it came from, so
       the gesture is seen not to have taken, and the reason stays on screen
       long enough to read. */
    function abandon() {
      if (!active) return;
      var el = strip();
      if (!(!el.hidden && el.dataset.tone === 'bad')) say(active.label + ' was not moved', 'bad');
      hideStrip(1400);
      snapProxy(sourceRect, function () {});
      finish();
    }

    function finish() {
      // A scroll that outlives its drag runs away with the page.
      try { dragScroll.stop(); } catch (e) {}
      Array.prototype.forEach.call(document.querySelectorAll('.lp-dragging'), function (el) { el.classList.remove('lp-dragging'); });
      clearTargetPaint(); clearCandidates(); hideInsert();
      if (proxy) { proxy.remove(); proxy = null; }
      document.body.classList.remove('lp-drag-in-flight');
      active = null; armed = null; pending = null; sourceRect = null;
      internalJobDragIds = [];
      justDragged = false;   // any exit route disarms; onPointerUp re-arms on release
    }

    function settle(el) {
      if (!el) return;
      el.classList.remove('lp-drop-settle');
      el.classList.remove('lp-drop-stamp');
      // reflow, so the same class can flash twice in a row
      void el.offsetWidth;
      el.classList.add('lp-drop-settle');
      el.classList.add('lp-drop-stamp');
      setTimeout(function () {
        el.classList.remove('lp-drop-settle');
        el.classList.remove('lp-drop-stamp');
      }, 240);
    }

    /* ------------------------------- input -------------------------------- */
    function onPointerDown(e) {
      if (active || e.button !== 0 || e.isPrimary === false) return;
      var t = e.target;
      var src = t && t.closest ? t.closest('[data-lp-drag]') : null;
      if (!src) return;
      /* Never hijack a real control. A card is full of them -- Start, Remove,
         the subject badge, the select checkbox -- and a lift that began on one
         would steal its click. The grip is the exception: it exists only to be
         dragged. */
      if (!t.closest('.lp-drag-grip') &&
          t.closest('button, a, input, textarea, select, summary, [contenteditable], [data-selbox]')) return;
      pending = { x: e.clientX, y: e.clientY, src: src };
    }
    function onPointerMove(e) {
      if (pending && !active) {
        if (Math.abs(e.clientX - pending.x) < LIFT_THRESHOLD &&
            Math.abs(e.clientY - pending.y) < LIFT_THRESHOLD) return;
        var src = pending.src;
        pending = null;
        if (!beginDrag(src, e.clientX, e.clientY)) return;
        /* Capture the pointer to the source. Without it the drag depends on
           pointerup arriving at the window: if it does not, `active` stays set,
           the proxy stays in the DOM, and -- the part that outlives the gesture --
           internalJobDragIds stays populated, which makes the window drop handler
           bail and kills EXTERNAL file drop for the rest of the session (the
           DEF-025 failure, by a new route). Capture also guarantees the release
           lands here when the pointer ends up over another element. */
        if (src.setPointerCapture && e.pointerId !== undefined) {
          try { src.setPointerCapture(e.pointerId); } catch (err) {}
        }
      }
      if (!active) return;
      e.preventDefault();          // no text selection, no native image drag
      moveProxy(e.clientX, e.clientY);
      updateAt(e.clientX, e.clientY);
      /* DEF-023 again, by a new route: auto-scroll was wired to the native
         `dragover`, which a pointer drag never fires -- so lifting a lecture at
         the bottom of a long library could not reach the Process tab any more.
         The SAME manager is reused rather than a second one being grown here. */
      dragScroll.update(e.clientX, e.clientY);
    }
    function onPointerUp(e) {
      pending = null;
      if (!active) return;
      e.preventDefault();
      updateAt(e.clientX, e.clientY);
      commit();
      /* Arm the click-swallow HERE, not in beginDrag. A browser emits the stray
         click after a pointer RELEASE, so that is the only case worth swallowing.
         Setting it at lift meant a drag cancelled by window blur (Alt+Tab while
         carrying a card) left it armed with no click ever coming -- and the user's
         next click anywhere in the app was silently eaten. commit()/abandon() run
         finish(), which clears it, so this must come after. */
      justDragged = true;
    }
    function onPointerCancel() { pending = null; if (active) abandon(); }
    function onKeyDown(e) {
      if (e.key === 'Escape' && active) { e.preventDefault(); abandon(); }
      // Ctrl/Cmd temporarily hands text selection back to the cards (app.css).
      if (e.key === 'Control' || e.key === 'Meta') document.body.classList.add('lp-text-select');
    }
    function onKeyUp(e) {
      if (e.key === 'Control' || e.key === 'Meta') document.body.classList.remove('lp-text-select');
    }
    /* A drag that ends on its own card must not also open the lecture. */
    function onClickCapture(e) {
      if (!justDragged) return;
      justDragged = false;
      e.stopPropagation();
      e.preventDefault();
    }

    function wire() {
      document.addEventListener('pointerdown', onPointerDown, true);
      window.addEventListener('pointermove', onPointerMove, { passive: false });
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerCancel);
      window.addEventListener('blur', onPointerCancel);
      window.addEventListener('keydown', onKeyDown, true);
      window.addEventListener('keyup', onKeyUp, true);
      document.addEventListener('click', onClickCapture, true);
      /* Native drag is suppressed for internal sources so the two input paths
         can never both run for one gesture. OS file drops are untouched: they
         do not originate from a [data-lp-drag] element. */
      document.addEventListener('dragstart', function (e) {
        if (e.target && e.target.closest && e.target.closest('[data-lp-drag]')) e.preventDefault();
      }, true);
    }
    return { wire: wire, settle: settle, reorderIndex: reorderIndex,
             dragging: function () { return !!active; } };
  })();

  /* Dropping lectures on Process. Extracted verbatim from the old per-element
     handler so the reprocess confirmation and the queueing path are unchanged;
     only the way the drop REACHES it moved to the registry. */
  function dropLecturesOnProcess(ids, host) {
    if (!ids.length) return;
    if (host && host.dataset && host.dataset.nav === 'process') setScreen('process');
    var again = ids.map(_jobById).filter(_jobIsReprocessable).length > 0;
    (again ? confirmReprocess(ids) : Promise.resolve(false)).then(function (agreed) {
      if (again && !agreed) return;
      return queueExistingJobIds(ids, { reprocess: again }).then(function (result) {
        var count = result && Number.isFinite(result.count) ? result.count : ids.length;
        toast(count + ' lecture' + (count === 1 ? '' : 's') + ' queued');
      }, function () { toast('The selected lectures could not be queued.'); });
    });
  }

  /* Filing lectures under a subject by drag. Same bridge call the Group dialog
     and the bulk Group action already use, so drag adds a route to an existing
     capability rather than a second way to persist one. */
  function assignJobsToGroup(ids, group, host) {
    var unique = ids.filter(function (id, i) { return id && ids.indexOf(id) === i; });
    if (!unique.length) return;
    if (!lpBridge.connected()) { toast('Preview mode — not grouped'); return; }
    lpBridge.call('set_jobs_group', JSON.stringify(unique), group).then(function (result) {
      if (!result || !result.ok) { toast('Those lectures could not be filed under ' + (group || 'Ungrouped') + '.'); return; }
      (LP.data.jobs || []).forEach(function (job) {
        if (unique.indexOf(job.id) >= 0) job.group = group;
      });
      setSelectMode(false);
      renderJobs();
      toast(unique.length + ' lecture' + (unique.length === 1 ? '' : 's') + ' filed under ' + (group || 'Ungrouped'));
      // renderJobs() rebuilt the DOM, so flash the group that received them.
      var fresh = document.querySelector('[data-lp-drop="group"][data-group="' + (window.CSS && CSS.escape ? CSS.escape(group) : group) + '"]');
      LPDrag.settle(fresh || host);
    }, function () { toast('Those lectures could not be filed under ' + (group || 'Ungrouped') + '.'); });
  }
  // Dropping finished lectures on Process re-runs them, which REPLACES their
  // slides, transcript and Study pack. That is not something to discover after
  // the fact, so the confirm names what is about to be overwritten and the
  // reprocess flag only reaches the sidecar once the student has agreed.
  function confirmReprocess(ids) {
    var again = ids.map(_jobById).filter(_jobIsReprocessable);
    if (!again.length) return Promise.resolve(false);
    var names = again.map(function (j) { return '<li>' + esc(j.name || 'Untitled lecture') + '</li>'; }).join('');
    return new Promise(function (resolve) {
      lpModal({
        title: again.length === 1 ? 'Process this lecture again?' : 'Process ' + again.length + ' lectures again?',
        bodyHtml: '<div>Running these again replaces their existing slides, transcript and Study pack:</div>' +
          '<ul style="margin:10px 0 0;padding-left:20px">' + names + '</ul>',
        actions: [
          { label: 'Cancel', onClick: function () { resolve(false); } },
          { label: 'Process again', danger: true, onClick: function () { resolve(true); } }
        ]
      });
    });
  }
  function queueExistingJobIds(ids, opts) {
    var unique = ids.filter(function (id, index) { return id && ids.indexOf(id) === index; });
    if (!unique.length) return Promise.resolve(null);
    if (!lpBridge.connected()) { toast('Preview mode — existing lectures were not queued.'); return Promise.resolve(null); }
    var request = { job_ids: unique };
    if (opts && opts.reprocess) request.reprocess = true;
    return lpBridge.call('queue_jobs', JSON.stringify(request)).then(function (result) {
      // Older desktop bridges expose the same normal queue one job at a time.
      // This fallback still sends each existing ID exactly once and never
      // routes an internal drag through file import.
      if (result !== null && result !== undefined) return result;
      return unique.reduce(function (chain, id) {
        return chain.then(function () { return lpBridge.call('enqueue_job', id); });
      }, Promise.resolve(null));
    }).then(function (result) {
      renderJobs(); renderQueue(); renderProcessingStrip();
      return result;
    });
  }
  // Display labels for the per-job processing options (chosen before start and
  // locked for that run). The backend stores preset balanced/detailed and
  // product_mode study_pack/transcript_only/slides_only.
  function _optionsLabel(j) {
    var quality = j && j.preset === 'detailed' ? 'High' : (j && j.preset === 'conservative' ? 'Low' : 'Balanced');
    var output = j && j.product_mode === 'transcript_only' ? 'Transcript only' :
      (j && j.product_mode === 'slides_only' ? 'Slides only' : 'Study Pack');
    return quality + ' · ' + output;
  }
  function renderProcOptions() {
    var el = $('proc-options');
    var job = _jobById(LP.state.jobId);
    if (el) {
      if (!job || !(job.preset || job.product_mode)) el.textContent = '';
      else el.textContent = _optionsLabel(job);
    }
    // The Output mode rows were hardcoded to "Study Pack" selected and never
    // read the job, so a transcript-only lecture still showed Study Pack.
    var modes = $('proc-modes');
    if (!modes) return;
    var active = (job && job.product_mode) || (job ? 'study_pack' : '');
    Array.prototype.forEach.call(modes.querySelectorAll('[data-mode]'), function (row) {
      var on = row.dataset.mode === active;
      var dot = row.querySelector('[data-dot]');
      var label = row.querySelector('[data-label]');
      row.style.background = on ? 'var(--blue-tint)' : '';
      row.style.borderColor = on ? 'var(--blue)' : 'transparent';
      if (dot) {
        dot.style.borderColor = on ? 'var(--blue)' : 'var(--muted)';
        dot.style.background = on ? 'radial-gradient(var(--blue) 42%,transparent 46%)' : '';
      }
      if (label) {
        label.style.color = on ? 'var(--ink)' : 'var(--muted)';
        label.style.fontWeight = on ? '600' : '';
      }
    });
    var note = $('proc-modes-note');
    if (note) note.hidden = !job;
  }

  // ---------------- viewed-job selection -------------------------------
  // Selecting a job makes it the VIEWED job without touching the backend's
  // active processing slot. Fresh payloads are fetched through view_job so a
  // completed/queued job can be opened while another job keeps processing.
  function selectJob(jobId, opts) {
    opts = opts || {};
    if (!jobId) return;
    var previousJobId = LP.state.jobId || '';
    var previousScreen = LP.state.screen;
    if (!appSessionRestored && !opts.silent && !opts.restoring) sessionNavigationExplicit = true;
    // Feature 4: when leaving the currently viewed job, persist its view state.
    if (LP.state.jobId && LP.state.jobId !== jobId) captureResumeState(LP.state.jobId);
    var entry = _jobById(jobId);
    setActiveJob(jobId, entry && entry.name ? entry.name : '');
    if (previousJobId !== jobId && typeof studyV2 !== 'undefined') {
      // Study V2 is renderer-global, so clear the prior lecture immediately;
      // the explicitly scoped request below repopulates the new lecture.
      studyV2.content = { concepts: [], flashcards: [], quiz: [] };
      studyV2.progress = { concepts: {}, flashcard_results: {}, quiz_attempts: [] };
      studyV2.summary = {};
      studyV2.quickSession = null;
      studyV2.quickSummary = null;
      studyV2.askStreaming = false;
      studyV2.askAnswer = null;
      studyV2.teachConceptId = '';
      studyV2.teachResult = null;
      studyV2.teachLoading = false;
      studyV2.teachGrade = null;
      studyV2.quizGrading = false;
      studyV2.quizGrades = {};
      studyV2.quizGradingQuestionId = '';
      studyV2.viewJobId = '';
      if (LP.state.screen === 'study') {
        renderStudyGenerationState();
        renderStudyV2Overview();
      }
    }
    if (lpBridge.connected() && !opts.silent) {
      try { lpBridge.call('view_job', jobId); } catch (err) { /* cached data already shown */ }
    }
    // Feature 4: restore the viewed job's last position unless an explicit
    // navigation (search result / Process) overrides it.
    if (!opts.screen || opts.screen === 'review' || opts.screen === 'transcript' || opts.screen === 'study') {
      applyResumeState(jobId);
    }
    if (opts.screen) setScreen(opts.screen);
    // setScreen intentionally no-ops when the screen name is unchanged. A
    // lecture switch made while already in Study still needs the new job's
    // scoped content and progress.
    if (previousScreen === 'study' && LP.state.screen === 'study') studyV2Load();
    renderJobSwitcher();
    saveAppSession();
  }

  function selectAdjacentJob(dir) {
    var jobs = LP.data.jobs || [];
    if (!jobs.length) return;
    var idx = -1;
    jobs.forEach(function (j, i) { if (j.id === LP.state.jobId) idx = i; });
    var next = idx === -1 ? 0 : idx + (dir < 0 ? -1 : 1);
    if (next < 0 || next >= jobs.length) return;
    selectJob(jobs[next].id, {});
  }

  // One writer for the shared Previous/Next source switcher rendered into every
  // [data-jsw] host (Process Source card, Review timeline, Transcript header,
  // Study timeline, Exports header). Buttons disable at the ends of the job
  // list; the order is the same stable job-list order the Home cards use.
  function renderJobSwitcher() {
    var jobs = LP.data.jobs || [];
    var hosts = document.querySelectorAll('[data-jsw]');
    if (!hosts.length) return;
    var idx = -1;
    jobs.forEach(function (j, i) { if (j.id === LP.state.jobId) idx = i; });
    var name = idx === -1 ? '' : (jobs[idx].name || friendlyJobName(jobs[idx].id) || 'Lecture');
    var prevDisabled = idx <= 0;
    var nextDisabled = idx === -1 || idx >= jobs.length - 1;
    var html =
      '<button type="button" data-jdir="-1" title="Previous job" aria-label="Previous job"' + (prevDisabled ? ' disabled' : '') +
      '><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>' +
      '<span class="lp-jsw-name" title="' + esc(name) + '">' + esc(name) + '</span>' +
      '<button type="button" data-jdir="1" title="Next job" aria-label="Next job"' + (nextDisabled ? ' disabled' : '') +
      '><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></button>';
    Array.prototype.forEach.call(hosts, function (host) { host.innerHTML = html; });
    renderLectureSwitcher();
  }

  function renderProcessWorkload() {
    var badge = $('process-workload');
    if (!badge) return;
    var waiting = (LP.data.queue && LP.data.queue.queue || []).length;
    var active = (LP.data.jobs || []).some(function (job) { return job && job.status === 'running'; }) ? 1 : 0;
    var count = active + waiting;
    badge.textContent = count;
    badge.hidden = count === 0;
  }

  // Process screen banner for jobs that are not actively running: queued jobs
  // show their position, ready jobs show their locked options. Live jobs paint
  // the real pipeline instead and keep this hidden.
  function renderProcessJobState() {
    var el = $('proc-waiting'), text = $('proc-waiting-text');
    if (!el || !text) return;
    var job = _jobById(LP.state.jobId);
    if (!job || job.status === 'running') { el.hidden = true; return; }
    if (job.status === 'queued' && _jobInQueue(job.id)) {
      // The backend reports 0-based queue positions; the visible queue list is
      // 1-based ("Position 1" is first in line). Normalize to 1-based here, and
      // never treat a valid 0 (first in queue) as "no position".
      var pos = job.queue_position;
      if (pos === null || pos === undefined || pos === '') {
        pos = null;
        (LP.data.queue && LP.data.queue.queue || []).forEach(function (r, i) {
          if (r.id === job.id) pos = i + 1;
        });
      } else {
        pos = Number(pos) + 1;
      }
      text.textContent = 'Waiting to process' + (pos ? ' · Position ' + pos : '');
      el.hidden = false;
      return;
    }
    if (_jobIsReady(job)) {
      text.textContent = 'Ready to process · ' + _optionsLabel(job);
      el.hidden = false;
      return;
    }
    if (job.status === 'paused') {
      text.textContent = 'Paused';
      el.hidden = false;
      return;
    }
    el.hidden = true;
  }

  // Completion card stats arrive on job_completed; keep them per job so
  // switching back to a completed job re-paints its final summary card.
  var completionInfo = {};
  function applyCompletionPanel(m) {
    if (!m || !m.job_id) return;
    completionInfo[m.job_id] = m;
    if (m.job_id !== LP.state.jobId) return;
    var set = function (id, v) { var el = $(id); if (el) el.textContent = v; };
    set('cm-time', m.wall_time || '—');
    set('cm-words', (m.transcript_words != null ? m.transcript_words : '—'));
    set('cm-segments', (m.segment_count != null ? m.segment_count : '—'));
    set('cm-slides', (m.slides_detected != null ? m.slides_detected : '—'));
    var panel = $('proc-completion'); if (panel) panel.hidden = false;
    _applyLpState(panel, 'complete');
  }
  function renderQueue() {
    var wrap = $('home-queue'), list = $('queue-list');
    if (!wrap || !list) return;
    var jobs = LP.data.jobs || [];
    var q = (LP.data.queue && LP.data.queue.queue) || [];
    if (!jobs.length) { wrap.hidden = true; list.innerHTML = ''; return; }
    wrap.hidden = false;
    var cnt = $('queue-count');
    if (cnt) cnt.textContent = q.length ? q.length + (q.length === 1 ? ' job queued' : ' jobs queued') : '0 queued';
    if (!q.length) {
      list.innerHTML = '<div style="font:500 12px \'JetBrains Mono\';color:var(--muted);padding:12px 2px">No jobs waiting.</div>';
      return;
    }
    // The queue was one full-width row per job, so five queued lectures filled
    // the viewport in a straight line. It is now the same auto-filling grid the
    // library uses. A wrapping grid only keeps its order if the order is
    // written down, so the position moves onto the thumbnail as a badge and
    // reading order stays row-major.
    list.innerHTML = q.map(function (row, i) {
      var job = _jobById(row.id) || { id: row.id, preset: 'balanced', product_mode: 'study_pack' };
      var qbtn = function (act, glyph, label, disabled) {
        return '<button class="lp-hit' + (act === 'remove' ? ' q-rm' : '') + '" data-queueact="' + act +
          '" data-queueid="' + esc(row.id) + '" title="' + esc(label) + '" aria-label="' + esc(label) + '"' +
          (disabled ? ' disabled' : '') + '>' + glyph + '</button>';
      };
      /* A queue row is both a drag SOURCE and a reorder TARGET -- the only
         surface in the app that is both, which is why the registry keys on the
         drag's kind rather than on the element. The Move up / Move down buttons
         below stay exactly as they are: they are the keyboard and screen-reader
         route to this same capability, and drag is only an accelerator on top
         of them. */
      return '<div class="q-card" data-lp-drag="queue" data-lp-drop="queue-reorder"' +
        ' data-queueid="' + esc(row.id) + '">' +
        '<div class="q-thumb">' + posterHtml(job) +
        '<span class="q-pos" aria-hidden="true">' + (i + 1) + '</span>' +
        '<button type="button" class="lp-drag-grip" tabindex="-1" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></button></div>' +
        '<div class="q-body">' +
        '<div class="q-title">' + esc(_jobName(row.id)) + '</div>' +
        '<div class="q-meta">' + esc(_optionsLabel(job)) + ' · Queued</div>' +
        '<div class="q-actions">' +
          /* The 'runnow' handler existed with nothing to trigger it: promoting a
             queued lecture meant reordering it to the front and waiting. */
          qbtn('runnow', '&#9654;', 'Process now', false) +
          qbtn('up', '&#8593;', 'Move up', i === 0) +
          qbtn('down', '&#8595;', 'Move down', i === q.length - 1) +
          qbtn('remove', '&#10005;', 'Remove from queue', false) +
        '</div></div></div>';
    }).join('');
  }
  function renderScheduled() {
    var wrap = $('home-scheduled'), list = $('scheduled-list');
    if (!wrap || !list) return;
    var sch = (LP.data.queue && LP.data.queue.schedules) || {};
    var ids = Object.keys(sch);
    if (!ids.length) { wrap.hidden = true; list.innerHTML = ''; return; }
    wrap.hidden = false;
    list.innerHTML = ids.map(function (id) {
      var e = sch[id];
      var when = String(e.when || '').replace('T', ' ');
      var pol = { run_when_opened: 'run when opened', skip_if_missed: 'skip if missed', ask: 'ask if missed' }[e.missed_policy] || '';
      return '<div style="display:flex;align-items:center;gap:12px;background:var(--panel);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px">' +
        '<span style="flex:1;font-weight:600;font-size:13.5px">' + esc(_jobName(id)) + '</span>' +
        '<span style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + esc(when) + ' · ' + esc(pol) + '</span>' +
        '<button class="lp-hit" data-queueact="unschedule" data-queueid="' + esc(id) + '" style="font:600 11px \'Space Grotesk\';border-radius:7px;padding:6px 10px;cursor:pointer;background:var(--panel);border:1.5px solid var(--border);color:var(--ink)">Unschedule</button>' +
        '</div>';
    }).join('');
  }
  function renderJobs() {
    var g = $('jobs-grid');
    var empty = !(LP.data.jobs || []).length;
    setJobsEmpty(empty);
    var actionBar = $('jobs-actionbar');
    if (actionBar) actionBar.hidden = empty;
    if (empty && LP.state.selecting) {
      LP.state.selecting = false;
      LP.state.selected = {};
      var selectBar = $('jobs-selectbar');
      if (selectBar) selectBar.hidden = true;
    }
    g.style.display = 'flex'; g.style.flexDirection = 'column'; g.style.gap = '16px';
    g.style.gridTemplateColumns = 'none';
    // A group only earns a container when it actually groups something.
    // jobGroup() falls back to inferredJobGroup(), which slices a prefix off
    // the title -- so a library of separately-named lectures produced one
    // "group" per lecture, and containerising those gave seven boxes of one
    // card each: noisier than no grouping at all. An EXPLICIT group (set by
    // the student) always gets its own box, even alone; an INFERRED one only
    // when two or more lectures share it. The rest pool into Ungrouped.
    var counts = {};
    LP.data.jobs.forEach(function (j) {
      var k = jobGroup(j);
      counts[k] = (counts[k] || 0) + 1;
    });
    var groups = {}, order = [];
    LP.data.jobs.forEach(function (j) {
      var k = jobGroup(j);
      if (!(j && j.group) && counts[k] < 2) k = 'Ungrouped';
      if (!groups[k]) { groups[k] = []; order.push(k); }
      groups[k].push(j);
    });
    // Ungrouped is a remainder, not a category, so it sorts last.
    order.sort(function (a, b) {
      if (a === 'Ungrouped') return 1;
      if (b === 'Ungrouped') return -1;
      return String(a).localeCompare(String(b));
    });
    // Every group is a bordered container with a persistent header. The old
    // build suppressed the header whenever there was only one group, which is
    // the common case -- so grouping was invisible exactly when a student was
    // first learning that lectures HAVE groups. The card grid auto-fills
    // instead of being pinned to three columns at every window width.
    var collapsed = collapsedGroups();
    g.innerHTML = order.map(function (k) {
      var count = groups[k].length;
      var shut = collapsed[k] === true;
      // Collapsed groups render their header only. Dropping the cards from the
      // DOM (rather than hiding them) is the point of collapsing a library
      // that has grown too tall to scan.
      /* The WHOLE SECTION is the drop target, not just its header bar. Aiming a
         card at a 30px strip is fussy when a 400px box means the same thing --
         and because the cards live inside the section, dropping onto any card
         in a subject files the dragged lecture into that subject too, which is
         what a user means when they drop "into" a group.
         The collapsed case still works for free: a collapsed section IS its
         header, so it remains a target at the same place on screen. */
      return '<section class="lib-group" data-lp-drop="group" aria-label="' + esc(k) + '" data-group="' + esc(k) + '"' +
        (shut ? ' data-collapsed="true"' : '') + '>' +
        '<div class="lib-group-head">' +
        '<button type="button" class="lp-hit lib-group-toggle" data-group-toggle="' + esc(k) + '"' +
        ' aria-expanded="' + (shut ? 'false' : 'true') + '"' +
        ' title="' + (shut ? 'Expand' : 'Collapse') + ' ' + esc(k) + '"' +
        ' aria-label="' + (shut ? 'Expand' : 'Collapse') + ' ' + esc(k) + '">' +
        (shut ? '&#43;' : '&#8722;') + '</button>' +
        '<span class="lib-group-code" data-group="' + esc(k) + '">' + esc(k) + '</span>' +
        /* The same pencil the Subjects cards carry. Renaming a subject from the
           library was previously only reachable through a lecture's own badge,
           so the two screens disagreed about where that action lives. */
        '<button type="button" class="lib-group-rename" data-group-rename="' + esc(k) + '" title="Rename subject" aria-label="Rename subject ' + esc(k) + '">' +
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg></button>' +
        /* Selecting a whole subject at once. The bulk actions already operate on
           a selection, so the only missing piece was a way to say "this whole
           subject". It toggles, so pressing again clears the group. */
        (LP.state.selecting
          ? '<button type="button" class="lib-group-select" data-group-select="' + esc(k) + '"' +
            ' aria-pressed="' + (groupFullySelected(groups[k]) ? 'true' : 'false') + '">' +
            (groupFullySelected(groups[k]) ? 'Deselect group' : 'Select group') + '</button>'
          : '') +
        '<span class="lib-group-count">' + count +
        (count === 1 ? ' lecture' : ' lectures') + '</span></div>' +
        (shut ? '' : '<div class="lib-grid">' + groups[k].map(_jobCardHtml).join('') + '</div>') +
        '</section>';
    }).join('');
    Array.prototype.forEach.call(g.querySelectorAll('[data-group-toggle]'), function (button) {
      button.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleGroupCollapsed(button.getAttribute('data-group-toggle'));
      });
    });
    /* Rename from the library header, through the SAME commit path the Subjects
       card uses -- the input is opened on the group's own code chip. */
    Array.prototype.forEach.call(g.querySelectorAll('[data-group-rename]'), function (button) {
      button.addEventListener('click', function (e) {
        e.stopPropagation(); e.preventDefault();
        var name = button.getAttribute('data-group-rename');
        var head = button.closest('.lib-group-head');
        var chip = head && head.querySelector('.lib-group-code');
        if (chip) handleGroupRename(chip, name, "font:700 12px 'JetBrains Mono'");
      });
    });
    /* Select an entire subject at once. Toggles on the group's CURRENT
       membership rather than a remembered list, so a group that changed while
       select mode was open still selects exactly what is on screen. */
    Array.prototype.forEach.call(g.querySelectorAll('[data-group-select]'), function (button) {
      button.addEventListener('click', function (e) {
        e.stopPropagation(); e.preventDefault();
        var name = button.getAttribute('data-group-select');
        var members = groups[name] || [];
        var ids = groupSelectableIds(members);
        var clearing = groupFullySelected(members);
        ids.forEach(function (id) {
          if (clearing) delete LP.state.selected[id];
          else LP.state.selected[id] = true;
        });
        renderJobs(); renderSelCount();
        toast((clearing ? 'Deselected ' : 'Selected ') + ids.length +
          (ids.length === 1 ? ' lecture in ' : ' lectures in ') + name);
      });
    });
    LPNumberRoller.setRolling($('jobs-count'), LP.data.jobs.length);
    renderContinueCard();
    if (typeof LP !== 'undefined' && LP.state && LP.state.screen === 'subjects') renderSubjects();
  }

  // Live progress updates land on the matching Home card BY JOB ID, never only
  // on the viewed job. applyJobLive merges into the job list (so any later full
  // render is correct); updateJobCardDom patches the visible card cheaply.
  function applyJobLive(jobId, patch) {
    var entry = _jobById(jobId);
    if (!entry) return;
    Object.keys(patch).forEach(function (k) {
      if (patch[k] !== undefined) entry[k] = patch[k];
    });
  }

  // Extract the raw pipeline stage from a status detail such as
  // "Transcribe - 43%" or "Detecting slides - 12%" so the Home card keeps the
  // same stage vocabulary the Process screen uses.
  function stageFromStatusDetail(detail) {
    var text = String(detail == null ? '' : detail).trim();
    var m = text.match(/^(.+?)\s*-\s*\d+%/);
    return m ? m[1].trim() : '';
  }

  // Patch one Home card in place from live progress events. A structural
  // status change (running -> done, queued -> running, ...) rebuilds the card;
  // same-status progress updates only touch the bar and the label line.
  function updateJobCardDom(jobId) {
    var job = _jobById(jobId);
    if (!job) return;
    var card = null;
    Array.prototype.forEach.call(document.querySelectorAll('#jobs-grid .lp-card[data-job]'), function (c) {
      if (c.dataset.job === jobId) card = c;
    });
    if (!card) return;
    if (card.dataset.status !== job.status) { renderJobs(); return; }
    if (job.status !== 'running') return;
    var bar = card.querySelector('[data-progress]');
    if (bar) bar.style.width = (job.pct || 0) + '%';
    var label = card.querySelector('[data-progress-label]');
    if (label) label.textContent = friendlyProcessingLabel(job.stage) + ' · ' + (job.pct || 0) + '% · ' + (job.eta || '');
  }

  // renderPipeline is called every tick, so skip the rebuild (and the motion
  // it destroys) when nothing about the stage list actually changed. Compare
  // directly against the container's live DOM rather than a cached variable --
  // the DOM is the source of truth and cannot go stale if the container is
  // ever mutated or recreated elsewhere.
  /* Coalesce pipeline re-renders to one per animation frame.
     `log_line` fires per backend log line, and during transcription / slide
     detection that is a fast stream. Each event used to call renderPipeline()
     directly, re-rendering the whole panel INCLUDING all 500 buffered log
     lines, so the main thread saturated rebuilding DOM and the window stopped
     accepting clicks mid-job (reported as "stuck for a while, can't click any
     buttons" around 42-50%). The 500-line cap bounded memory, not work: the
     cost was one full render PER LINE, not per frame.
     Batching keeps the same visible output -- a frame is the fastest anything
     can be seen -- while collapsing N renders per frame into one. */
   /* Processing state may arrive much faster than a clean-install WebEngine
      can paint. Keep engine state live, but cap visible processing writes at
      four per second and commit each batch in one animation frame. */
   var PROCESSING_RENDER_INTERVAL = 250;
   var processingRenderTimer = null, processingRenderRaf = null;
   var processingRenderLastAt = 0;
   var pipelineRenderDirty = false, statusRenderDirty = false;
   var pendingProcessingStatus = {};
   var lastPipelineRenderKey = null, lastStatusRenderKey = null;
   // Processing temporarily replaces the footer's backend identity with a
   // stage label. Keep the last authoritative backend label so returning to
   // a no-lecture state cannot pair "Idle" with stale work such as
   // "Detecting slides".
   var runtimeBackendLabel = (($('status-right') || {}).textContent || '').trim();

   function processingRaf(fn) {
     return (window.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(fn);
   }

   function scheduleProcessingRender(kind) {
     if (kind === 'pipeline') pipelineRenderDirty = true;
     if (kind === 'status') statusRenderDirty = true;
     if (processingRenderTimer !== null || processingRenderRaf !== null) return;
     var elapsed = Date.now() - processingRenderLastAt;
     var delay = Math.max(0, PROCESSING_RENDER_INTERVAL - elapsed);
     processingRenderTimer = setTimeout(function () {
       processingRenderTimer = null;
       processingRenderRaf = processingRaf(function () {
         processingRenderRaf = null;
         var shouldRenderPipeline = pipelineRenderDirty;
         var shouldRenderStatus = statusRenderDirty;
         pipelineRenderDirty = false;
         statusRenderDirty = false;
         if (shouldRenderPipeline) renderPipeline();
         if (shouldRenderStatus) renderProcessingStatus();
         processingRenderLastAt = Date.now();
         if (pipelineRenderDirty || statusRenderDirty) scheduleProcessingRender();
       });
     }, delay);
   }

   function schedulePipelineRender() { scheduleProcessingRender('pipeline'); }
   function renderPipelineLegacy() {
    var p = LP.data.pipeline;
     $('proc-status-title').textContent = friendlyProcessingLabel(p.title);
    $('proc-status-meta').textContent = p.meta;
    // BUG-16: the Process screen's "Source" card had NO writer anywhere in
    // app.js -- the same defect class as BUG-04's storage figure. It was only
    // ever set by resetJobChrome(), so it read "No lecture loaded" plus a
    // hardcoded "1920x1080 · 06:12 · H.264" even while a real lecture was
    // being processed. The pipeline payload already carries both values.
    var hasJob = !!(p.title && p.stages && p.stages.length);
     $('proc-source-name').textContent = hasJob ? friendlyJobName(p.title) : 'No lecture loaded';
    $('proc-source-meta').textContent = hasJob ? (p.meta || '') : '';
    var stagesEl = $('pipeline-stages');
     var stageHtml = p.stages.map(function (st) {
       // Contract data-state values: idle|running|paused|success|failed|interrupted|complete
       var ds = st.state === 'done' ? 'complete' : st.state === 'active' ? 'running' :
         st.state === 'error' ? 'failed' : 'idle';
       var visibleStage = friendlyProcessingLabel(st.label || st.name || '');
       if (st.state === 'done') {
         return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:600;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;background:var(--green-fill);border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--on-signal)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>' + esc(visibleStage) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--green-soft);overflow:hidden"><div style="width:100%;height:100%;background:var(--green)"></div></div></div>';
      }
      if (st.state === 'active') {
        var c = st.color === 'blue' ? 'var(--blue)' : 'var(--orange)';
        var pctColor = st.color === 'blue' ? ';color:var(--blue-ink)' : '';
        var blink = st.color === 'blue' ? '1.3s' : '1s';
         return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid ' + c + ';border-radius:50%;flex:none;animation:lpblink ' + blink + ' infinite"></span>' + esc(visibleStage) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk);overflow:hidden"><div style="width:' + (st.pct || 0) + '%;height:100%;background:' + c + ';background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.32) 6px,rgba(255,255,255,.32) 13px);animation:lpbar 1s linear infinite"></div></div><span style="width:38px;text-align:right;font:700 11px \'JetBrains Mono\'' + pctColor + '">' + (st.pct || 0) + '%</span></div>';
      }
       return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px;opacity:.45"><span style="width:120px;flex:none;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid var(--muted);border-radius:50%;flex:none"></span>' + esc(visibleStage) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk)"></div></div>';
    }).join('');
    if (stagesEl.innerHTML !== stageHtml) { stagesEl.innerHTML = stageHtml; }
    var logEl = $('proc-log');
      // Follow the newest line only while the user has not scrolled upward.
      // LP.logFollow is cleared by the scroll listener on manual scrolling and
      // restored by the Latest button.
      var stick = LP.logFollow !== false &&
        logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 8;
    var logHtml = p.log.map(function (l) {
      return '<div><span style="color:' + l.color + '">' + esc(l.tag) + '</span> ' + esc(l.text) + '</div>';
    }).join('');
    if (logEl.innerHTML !== logHtml) {
      logEl.innerHTML = logHtml;
      if (stick) logEl.scrollTop = logEl.scrollHeight;
    }
  }

   function pipelineStageNode() {
     var row = document.createElement('div');
     row.className = 'lp-stage';
     row.style.cssText = 'display:flex;align-items:center;gap:13px';
     var labelWrap = document.createElement('span');
     labelWrap.className = 'lp-stage-label-wrap';
     labelWrap.style.cssText = 'width:120px;flex:none;display:flex;align-items:center;gap:8px';
     var marker = document.createElement('span');
     marker.className = 'lp-stage-marker';
     marker.style.cssText = 'width:19px;height:19px;display:flex;align-items:center;justify-content:center;flex:none';
     var check = document.createElement('span');
     check.className = 'lp-stage-check';
     check.textContent = '✓';
     check.style.cssText = 'font:700 14px/1 system-ui;color:var(--on-signal)';
     marker.appendChild(check);
     var label = document.createElement('span');
     label.className = 'lp-stage-label';
     labelWrap.appendChild(marker);
     labelWrap.appendChild(label);
     var bar = document.createElement('div');
     bar.className = 'lp-stage-bar';
     bar.style.cssText = 'flex:1;height:9px;border-radius:6px;overflow:hidden';
     var fill = document.createElement('div');
     fill.className = 'lp-stage-fill';
     fill.style.cssText = 'width:100%;height:100%;transform-origin:left center';
     bar.appendChild(fill);
     var pct = document.createElement('span');
     pct.className = 'lp-stage-pct';
     pct.style.cssText = 'width:38px;text-align:right;font:700 11px \'JetBrains Mono\'';
     row.appendChild(labelWrap);
     row.appendChild(bar);
     row.appendChild(pct);
     return row;
   }

   function applyPipelineStage(row, st) {
     var ds = st.state === 'done' ? 'complete' : st.state === 'active' ? 'running' :
       st.state === 'error' ? 'failed' : 'idle';
     var labelWrap = row.querySelector('.lp-stage-label-wrap');
     var marker = row.querySelector('.lp-stage-marker');
     var check = row.querySelector('.lp-stage-check');
     var label = row.querySelector('.lp-stage-label');
     var bar = row.querySelector('.lp-stage-bar');
     var fill = row.querySelector('.lp-stage-fill');
     var pct = row.querySelector('.lp-stage-pct');
     var color = st.color === 'blue' ? 'var(--blue)' : 'var(--orange)';
     row.dataset.state = ds;
      row.dataset.stageLabel = friendlyProcessingLabel(st.label || st.name || '');
      label.textContent = friendlyProcessingLabel(st.label || st.name || '');
     check.hidden = st.state !== 'done';
     pct.hidden = st.state !== 'active';
     if (st.state === 'done') {
       row.style.opacity = '1';
       labelWrap.style.fontWeight = '600';
       marker.style.cssText = 'width:19px;height:19px;background:var(--green-fill);border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none';
       bar.style.background = 'var(--green-soft)';
       fill.style.background = 'var(--green)';
       fill.style.backgroundImage = 'none';
       fill.style.transform = 'scaleX(1)';
       fill.style.animation = 'none';
     } else if (st.state === 'active') {
       var value = Math.max(0, Math.min(100, Number(st.pct) || 0));
       row.style.opacity = '1';
       labelWrap.style.fontWeight = '700';
       marker.style.cssText = 'width:19px;height:19px;border:2px solid ' + color + ';border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none;animation:lpblink ' + (st.color === 'blue' ? '1.3s' : '1s') + ' infinite';
       bar.style.background = 'var(--sunk)';
       fill.style.background = color;
       fill.style.backgroundImage = 'repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.32) 6px,rgba(255,255,255,.32) 13px)';
       fill.style.transform = 'scaleX(' + (value / 100) + ')';
       fill.style.animation = 'lpbar 1s linear infinite';
       pct.textContent = Math.round(value) + '%';
       pct.style.color = st.color === 'blue' ? 'var(--blue-ink)' : '';
     } else {
       row.style.opacity = '.45';
       labelWrap.style.fontWeight = '400';
       marker.style.cssText = 'width:19px;height:19px;border:2px solid var(--muted);border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none';
       bar.style.background = 'var(--sunk)';
       fill.style.background = 'transparent';
       fill.style.backgroundImage = 'none';
       fill.style.transform = 'scaleX(0)';
       fill.style.animation = 'none';
       pct.textContent = '';
       pct.style.color = '';
     }
   }

   function renderPipelineLog(logEl, logs) {
     var keys = logs.map(function (entry) {
       return [entry.tag || '', entry.color || '', entry.text || ''].join('\\u001f');
     });
     var rows = Array.prototype.slice.call(logEl.children);
     var samePrefix = rows.every(function (row, index) { return row.dataset.logKey === keys[index]; });
     var stick = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 8;
     if (!samePrefix || rows.length > keys.length) {
       while (logEl.firstChild) logEl.removeChild(logEl.firstChild);
       rows = [];
     }
     var fragment = document.createDocumentFragment();
     for (var i = rows.length; i < logs.length; i += 1) {
       var entry = logs[i], row = document.createElement('div');
       row.dataset.logKey = keys[i];
       var tag = document.createElement('span');
       tag.style.color = entry.color || 'var(--muted)';
       tag.textContent = entry.tag || '';
       row.appendChild(tag);
       row.appendChild(document.createTextNode(' ' + (entry.text || '')));
       fragment.appendChild(row);
     }
     if (fragment.childNodes.length) logEl.appendChild(fragment);
     if (stick) logEl.scrollTop = logEl.scrollHeight;
   }

    function renderPipeline() {
      var p = LP.data.pipeline || { title: '', meta: '', stages: [], log: [] };
      var stages = Array.isArray(p.stages) ? p.stages : [];
      var logs = Array.isArray(p.log) ? p.log : [];
      renderProcessJobState();
      var key = JSON.stringify({ title: p.title || '', meta: p.meta || '', stages: stages, log: logs });
     if (key === lastPipelineRenderKey) return;
     lastPipelineRenderKey = key;
       $('proc-status-title').textContent = friendlyProcessingLabel(p.title || '');
       $('proc-status-meta').textContent = p.meta || '';
       var hasJob = !!(p.title && stages.length);
       // Source card: prefer the live pipeline title, fall back to the job
       // list so a queued/ready job never reads "No lecture loaded".
       $('proc-source-name').textContent = hasJob ? friendlyJobName(p.title) : (friendlyJobName(LP.state.jobId) || 'No lecture loaded');
      $('proc-source-meta').textContent = hasJob ? (p.meta || '') : '';
     var stagesEl = $('pipeline-stages');
     while (stagesEl.children.length > stages.length) stagesEl.lastElementChild.remove();
     while (stagesEl.children.length < stages.length) stagesEl.appendChild(pipelineStageNode());
      stages.forEach(function (st, index) { applyPipelineStage(stagesEl.children[index], st); });
      renderPipelineLog($('proc-log'), logs);
      refreshControlStates();
   }

   function renderProcessingStatus() {
     var s = pendingProcessingStatus;
     var key = JSON.stringify(s);
     if (key === lastStatusRenderKey) return;
     lastStatusRenderKey = key;
      var hold = s.label !== undefined ? waitingHandoff(s.label) : null;
      var footer = $('status-footer');
      if (footer) footer.dataset.status = hold ? 'waiting' : '';
      if (s.label !== undefined) {
        $('status-state').textContent = hold ? hold.label : (friendlyProcessingLabel(s.label) || 'Idle');
      }
      // The real percentage, always -- the bar changes MATERIAL when parked,
      // it never lies about magnitude.
      if (s.pct !== undefined) setFill('status-bar', s.pct);
      if (s.detail !== undefined) {
        $('status-detail').textContent = hold ? hold.detail : (friendlyProcessingLabel(s.detail) || s.detail);
      }
      if (s.right !== undefined) $('status-right').textContent = friendlyProcessingLabel(s.right) || s.right;
      if (s.job !== undefined && LP.state.jobId) {
        var jobName = friendlyJobName(s.job);
        $('side-job-name').textContent = jobName || 'Untitled lecture';
        $('crumb-job').textContent = jobName || 'Lecture';
      }
     if (s.side !== undefined) setStatusDotText($('side-job-status'), s.side, 'var(--orange)', true);
   }

   /* One writer for the enable/disable state of every job-dependent control
      (N-1/N-2). A control the student cannot validly use right now is
      disabled with a one-line reason on the tooltip instead of answering the
      click with a raw backend error. */
   function setCtl(id, enabled, disabledTip) {
     var el = $(id); if (!el) return;
     el.disabled = !enabled;
     el.style.opacity = enabled ? '' : '.45';
     el.style.cursor = enabled ? '' : 'not-allowed';
     if (enabled) { if (el.dataset.ctlTip) { el.removeAttribute('title'); delete el.dataset.ctlTip; } }
     else { el.title = disabledTip || 'Load a lecture first.'; el.dataset.ctlTip = '1'; }
   }
   function refreshControlStates() {
     var hasSlides = LP.data.slides.length > 0;
     var hasJob = !!LP.state.jobId;
     var processing = LP.state.pipelineRunning || guidedDemo.snapshot().active;
     var reviewTip = 'Load a lecture first — there are no slides to review yet.';
     setCtl('btn-keep', hasSlides, reviewTip);
     setCtl('btn-reject', hasSlides, reviewTip);
     setCtl('btn-prev-slide', hasSlides, reviewTip);
     setCtl('btn-next-slide', hasSlides, reviewTip);
     setCtl('btn-save-corrections', hasSlides, reviewTip);
     setCtl('btn-repair', hasSlides, 'Load a lecture before repairing slide selections.');
     var exportTip = 'Load a lecture first — there is nothing to export yet.';
     setCtl('btn-export-all', hasJob, exportTip);
     setCtl('btn-export-pdf', hasJob, exportTip);
     setCtl('btn-export-html', hasJob, exportTip);
     var procTip = 'No lecture is processing right now.';
     setCtl('btn-pause-job', processing, procTip);
     setCtl('btn-cancel-job', processing, procTip);
   }

   /* Terminal job states settle EVERY readout from one place (F-3): the job
      card, the sidebar chip, the status-bar label, the stage text, and the
      progress fill must never contradict each other or rest mid-pipeline.
      "Transcribing audio" / "Detecting slides" may only appear while those
      stages are actually active; afterwards the stage text reads Ready. */
   function settleTerminalStatus(kind) {
     var hasJob = !!LP.state.jobId;
     var label = $('status-state'), pct = $('status-detail'), right = $('status-right');
     if (pct) pct.textContent = '';
     if (right) right.textContent = 'Ready';
     if (kind === 'complete') {
       if (label) label.textContent = 'Complete';
       setFill('status-bar', 100);
       setStatusDotText($('side-job-status'), hasJob ? 'Complete' : 'Idle', hasJob ? 'var(--green)' : 'var(--muted)', false);
     } else if (kind === 'failed') {
       if (label) label.textContent = 'Failed';
       setFill('status-bar', 0);
       setStatusDotText($('side-job-status'), 'Failed', 'var(--red)', false);
     } else if (kind === 'cancelled') {
       if (label) label.textContent = 'Cancelled';
       setFill('status-bar', 0);
       setStatusDotText($('side-job-status'), 'Cancelled', 'var(--muted)', false);
     } else if (kind === 'interrupted') {
       if (label) label.textContent = 'Interrupted';
       setFill('status-bar', 0);
       setStatusDotText($('side-job-status'), 'Interrupted', 'var(--orange)', false);
     } else {
       if (label) label.textContent = 'Idle';
       setFill('status-bar', 0);
       setStatusDotText($('side-job-status'), 'Idle', 'var(--muted)', false);
     }
     refreshControlStates();
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

  /* Review has one narrow working rail and one deliberate deck overview.
     A "Grid/List" toggle inside a 250px rail could never produce a useful grid:
     its auto-fill expression resolved to one 246px column. The rail is now
     always a list with density control; visual deck scanning lives in the
     full-window All Slides dialog where 168px cards can actually form a grid. */
  function slideReviewState(slide) {
    return slide && slide.state === 'rejected' ? 'rejected' : 'accepted';
  }

  function slideCheckHtml(selected) {
    return '<span class="lp-slide-check" data-checked="' + (selected ? 'true' : 'false') +
      '" aria-hidden="true">' + (selected ? '&#10003;' : '') + '</span>';
  }

  function slideRailCardHtml(slide, index, viewing) {
    var state = slideReviewState(slide), selected = state !== 'rejected' && slide.sel === true;
    var label = state === 'rejected' ? 'Rejected' : (viewing ? 'Viewing' : 'Kept');
    var image = slideImg(slide.thumb || slide.img, '', 16, state === 'rejected' ? 'var(--red)' : 'var(--muted)');
    // A 16:9 thumbnail across the full rail width. The old row put it at
    // 60x38 (82x52 "roomy"), at which a lecture slide is an unreadable smear
    // -- and telling two bullet slides apart is the entire job of this screen.
    return '<button type="button" class="lp-hit lp-slide-card lp-slide-rail-card" data-slide="' + index +
      '" data-state="' + state + '" data-viewing="' + (viewing ? 'true' : 'false') +
      '" data-selected="' + (selected ? 'true' : 'false') + '" aria-label="Slide ' + (index + 1) +
      ', ' + esc(slide.time || '') + ', ' + label.toLowerCase() + '">' +
      '<span class="lp-slide-card-thumb">' + image + '</span>' +
      '<span class="lp-slide-card-meta"><span class="lp-slide-card-time">' + esc(slide.time) + '</span>' +
      '<span class="lp-slide-card-status">' + label + '</span>' +
      '<span class="lp-slide-card-idx">' + (index + 1) + '</span></span>' +
      slideCheckHtml(selected) + '</button>';
  }

  function allSlidesCardHtml(slide, index, viewing) {
    var state = slideReviewState(slide), selected = state !== 'rejected' && slide.sel === true;
    var label = state === 'rejected' ? 'Rejected' : (viewing ? 'Viewing' : 'Kept');
    var image = slideImg(slide.thumb || slide.img, '', 22, state === 'rejected' ? 'var(--red)' : 'var(--muted)');
    return '<button type="button" class="lp-hit lp-all-slide-card" data-slide="' + index +
      '" data-state="' + state + '" data-viewing="' + (viewing ? 'true' : 'false') +
      '" data-selected="' + (selected ? 'true' : 'false') + '" aria-label="Open slide ' + (index + 1) +
      ', ' + esc(slide.time || '') + ', ' + label.toLowerCase() + '">' +
      '<span class="lp-all-slide-image">' + image + '</span>' +
      '<span class="lp-all-slide-meta"><span><strong>Slide ' + (index + 1) + '</strong><time>' +
      esc(slide.time) + '</time></span><span class="lp-all-slide-state">' + label + '</span>' +
      slideCheckHtml(selected) + '</span></button>';
  }

  function renderAllSlides() {
    var grid = $('all-slides-grid'), count = $('all-slides-count');
    if (!grid) return;
    grid.dataset.size = LP.state.slideSize;
    Array.prototype.forEach.call(document.querySelectorAll('[data-slide-size]'), function (button) {
      button.setAttribute('aria-pressed',
        button.dataset.slideSize === LP.state.slideSize ? 'true' : 'false');
    });
    var viewing = LP.state.viewingSlide;
    grid.innerHTML = LP.data.slides.map(function (slide, index) {
      return allSlidesCardHtml(slide, index, index === viewing);
    }).join('');
    if (count) {
      var kept = LP.data.slides.filter(function (slide) { return slideReviewState(slide) === 'accepted'; }).length;
      count.textContent = LP.data.slides.length + ' slides · ' + kept + ' kept';
    }
  }

  var allSlidesReturnFocus = null;
  function openAllSlides() {
    var overlay = $('all-slides-overlay');
    if (!overlay || !LP.data.slides.length) return;
    allSlidesReturnFocus = document.activeElement;
    renderAllSlides();
    overlay.hidden = false;
    focusFirst(overlay);
  }

  function closeAllSlides(restoreFocus) {
    var overlay = $('all-slides-overlay');
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    if (restoreFocus !== false && allSlidesReturnFocus && allSlidesReturnFocus.isConnected) {
      allSlidesReturnFocus.focus();
    }
    allSlidesReturnFocus = null;
  }

  function renderSlides() {
    var v = LP.state.viewingSlide;
    var list = $('slide-list');
    updateExportPdfDescription();
    list.innerHTML = LP.data.slides.map(function (slide, index) {
      return slideRailCardHtml(slide, index, index === v);
    }).join('');
    if (!$('all-slides-overlay').hidden) renderAllSlides();
    finishSlides(v);
  }

  function finishSlides(v) {
    var selCount = LP.data.slides.filter(function (s) { return s.sel; }).length;
    $('slides-sel').textContent = '· ' + selCount + ' kept';
    var cur = LP.data.slides[v];
    previewCtl.show(cur);
    $('slide-frame-meta').innerHTML = cur
      ? (esc(cur.time) + ' <span style="color:var(--muted);font-weight:400">· frame ' + (cur.frame || Math.round(cur.pct * 30)) + '</span>')
      : '';
    renderTimeline();
    refreshControlStates();
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
    // An empty workspace (no lecture loaded) is a legitimate state: slides[v]
    // does not exist, so the timeline must render at zero rather than throw --
    // a throw here aborted the whole renderWorkspace() pass.
    var at = LP.data.slides[v];
    setFill('timeline-progress', at ? at.pct : 0);
    $('timeline-meta').textContent = LP.data.slides.length
      ? LP.data.slides.length + ' slides · ' + (LP.data.duration || '')
      : 'No slides yet';
    $('timeline-mid').textContent = LP.data.durationMid || '';
    $('timeline-end').textContent = LP.data.duration || '';
    // Restore the axis origin once there is a lecture to measure against;
    // resetJobChrome() blanks it, and nothing else re-sets it (BUG-15).
    $('timeline-start').textContent = LP.data.slides.length ? '00:00' : '';
  }

  function renderReviewTranscript() {
    $('review-transcript').innerHTML = LP.data.reviewSegments.map(function (s, i) {
      var last = i === LP.data.reviewSegments.length - 1;
      var row = 'display:flex;padding:11px 13px;' + (last ? '' : 'border-bottom:1px solid var(--line);') + 'gap:11px';
      var tColor = 'var(--muted)';
      if (s.hot) { row += ';background:var(--blue-tint);border-left:3px solid var(--blue)'; tColor = 'var(--blue-ink)'; }
      return '<div style="' + row + '"><span style="width:104px;flex:none;min-width:104px;white-space:nowrap;font:500 11px \'JetBrains Mono\';color:' + tColor + '">' + esc(s.t) + '</span><span contenteditable="true" style="flex:1;min-width:0;overflow-wrap:anywhere;font-size:13px;line-height:1.5">' + esc(s.text) + '</span></div>';
    }).join('');
  }

  function renderTranscript() {
    var t = LP.data.transcript;
    $('transcript-title').textContent = t.title;
    $('transcript-duration').textContent = t.duration;
    $('transcript-segcount').textContent = t.segments + ' segments';
    $('transcript-corrections').textContent = t.corrections + ' corrections';
    // The staggered entrance (.lp-stagger) must run ONCE, when the transcript
    // first arrives -- not on every re-render. This container is rebuilt with
    // innerHTML on every transcript update, so while a lecture is transcribing
    // each update re-ran a 500ms animation with delays ramping to 300ms on
    // EVERY block at once. That reads as a flicker, and it fights the user if
    // they are reading while it streams. Stagger the arrival, not the updates.
    var blocksEl = $('transcript-blocks');
    var hadContent = blocksEl.childElementCount > 0;
    blocksEl.classList.toggle('lp-stagger', !hadContent);
    blocksEl.innerHTML = t.blocks.map(function (b) {
      var chip = b.hotTime
        ? '<span style="font:700 12px \'JetBrains Mono\';color:var(--orange-ink);background:var(--orange-soft);border-radius:7px;padding:3px 7px">' + esc(b.t) + '</span>'
        : '<span style="font:700 12px \'JetBrains Mono\';color:var(--muted)">' + esc(b.t) + '</span>';
      return '<div data-transcript-time="' + esc(b.t) + '" style="display:flex;gap:18px;border-radius:9px;transition:background var(--motion-fast) ease,box-shadow var(--motion-fast) ease"><div style="width:104px;flex:none;text-align:right;min-width:104px;white-space:nowrap">' + chip + '</div><p style="margin:0;font-size:17px;line-height:1.72;text-wrap:pretty;flex:1;min-width:0;overflow-wrap:anywhere">' + b.html + '</p></div>';
    }).join('');
    applyPendingTranscriptJump();
  }

  function renderStudy() {
    // Study V2 owns the visible Study workspace. The legacy topic timeline is
    // retained only for backward-compatible data, and its old markup is no
    // longer mounted in the V2 screen. Do not let that hidden renderer throw
    // during startup when the legacy-only nodes are absent.
    if (!$('study-topic-blocks')) return;
    var st = LP.data.study;
    var overview = $('study-overview');
    if (overview) overview.textContent = studyOverviewText(st);
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

  function studyOverviewText(study) {
    var summary = study && typeof study.summary === 'string' ? study.summary.trim() : '';
    return summary || 'A study overview will appear here after your lecture is ready.';
  }

  function renderChat() {
    var feed = $('chat-feed');
    // N-9: with no lecture loaded the assistant must not leak the design-time
    // sample conversation. Demo Q&A only ever exists inside the demo's own
    // session; everywhere else an empty feed gets a neutral prompt.
    if (!LP.state.chat.length) {
      feed.innerHTML = '<div style="margin:auto;max-width:320px;text-align:center;color:var(--muted);font-size:13px;line-height:1.6;padding:20px">' +
        (LP.state.jobId ? 'Ask anything about this lecture — answers come from its transcript.' : 'Ask about your lecture once it is ready.') + '</div>';
      return;
    }
    feed.innerHTML = LP.state.chat.map(function (m, i) {
      var last = i === LP.state.chat.length - 1;
      var cls = m.role === 'user' ? 'lp-bubble-user' : 'lp-bubble-ai';
      var caret = (m.role === 'ai' && last && LP.state.streaming) ? '<span class="lp-caret"></span>' : '';
      return '<div class="' + cls + '">' + esc(m.text) + caret + '</div>';
    }).join('');
    var pending = feed.lastElementChild;
    if (pending) {
      pending.classList.add('study-ask-answer-wrap');
      if (pending.firstElementChild) pending.firstElementChild.classList.add('study-ask-thinking');
    }
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
        (on ? 'var(--orange)' : 'var(--border)') + ';background:' + (on ? 'var(--orange)' : 'var(--panel)') + ';color:' + (on ? 'var(--on-signal)' : 'var(--ink)') + '">' + esc(o) + '</button>';
    }).join('') + '</div>';
  }
  function _qField(label, html) {
    return '<div style="margin-bottom:15px"><div style="font:600 10px \'JetBrains Mono\';letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:7px">' + label + '</div>' + html + '</div>';
  }

  /* ---- generation progress bar + ETA (shared by quiz + flashcards) ---- */
  var _genTimers = { quiz: null, flash: null };
  function _genBar(kind) {
    var st = kind === 'quiz' ? LP.state.quiz : LP.state.flash;
    var elapsed = Date.now() - (st.genStart || Date.now()), est = st.genEst || 12000;
    var timedPct = elapsed / est * 100;
    var backendPct = typeof st.backendPct === 'number' ? st.backendPct : 0;
    var pct = Math.max(4, Math.min(93, Math.max(timedPct, backendPct))), etaMs = est - elapsed;
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
    st.generating = true; st.genStart = Date.now(); st.backendPct = 0;
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
    st.backendPct = 0;
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
        '<button data-qact="generate" style="font:700 14px \'Space Grotesk\';background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:10px;padding:11px 22px;cursor:pointer">Generate quiz</button>' +
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
      (answered ? '' : '<button data-qact="submit"' + (q.pick == null ? ' disabled' : '') + ' style="font:700 13px \'Space Grotesk\';background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 17px;cursor:pointer;opacity:' + (q.pick == null ? '.5' : '1') + '">Submit</button>') +
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
      (wrong.length ? '<button data-qact="retry-wrong" style="font:700 13px \'Space Grotesk\';background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 17px;cursor:pointer">Retry incorrect (' + wrong.length + ')</button>' : '') +
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
        '<button data-fact="generate" style="font:700 14px \'Space Grotesk\';background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:10px;padding:11px 22px;cursor:pointer">Generate flashcards</button>' +
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
        (on ? 'var(--orange)' : 'var(--border)') + ';background:' + (on ? 'var(--orange)' : 'var(--panel)') + ';color:' + (on ? 'var(--on-signal)' : 'var(--ink)') + '">' + esc(o) + '</button>';
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
      '<button data-fact="known" style="font:700 12px \'Space Grotesk\';background:' + (marked === 'known' ? 'var(--green-fill)' : 'var(--green-soft)') + ';color:' + (marked === 'known' ? 'var(--on-signal)' : 'var(--green)') + ';border:2px solid var(--green);border-radius:9px;padding:9px 15px;cursor:pointer">Known</button>' +
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
      (unsure ? '<button data-fact="retry-unsure" style="font:700 13px \'Space Grotesk\';background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 17px;cursor:pointer">Review unsure (' + unsure + ')</button>' : '') +
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
    updateExportPdfDescription();
  }

  function exportPdfDescription(slides) {
    var accepted = (slides || []).filter(function (slide) { return slide && slide.state === 'accepted'; }).length;
    return accepted + ' accepted ' + (accepted === 1 ? 'slide' : 'slides') + ', one per page, full resolution.';
  }
  function updateExportPdfDescription() {
    var description = $('export-pdf-desc');
    if (description) description.textContent = exportPdfDescription(LP.data.slides);
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

  var CRUMBS = { home: 'Home', subjects: 'Subjects', process: 'Process', review: 'Review', transcript: 'Transcript', study: 'Study', exports: 'Exports', settings: 'Settings' };

  function setScreen(name) {
    if (LP.state.screen === name) return;
    if (name !== 'review') closeAllSlides(false);
    // Home's Continue card must reflect the screen the student just left in
    // this same session, not only state captured during a job switch or app
    // shutdown. Capture before changing LP.state.screen so the saved target
    // remains Review/Transcript/Study/Process rather than Home.
    if (name === 'home' && LP.state.jobId &&
        /^(process|review|transcript|study|exports|subjects)$/.test(LP.state.screen || '')) {
      if (typeof captureResumeState === 'function') captureResumeState(LP.state.jobId);
    }
    LP.motion.nav(function () {
      LP.state.screen = name;
      if (typeof hideScrub === 'function') hideScrub();
      Array.prototype.forEach.call(document.querySelectorAll('main [data-screen]'), function (sec) {
        var show = sec.dataset.screen === name;
        if (show === !sec.hidden) return;
        sec.hidden = !show;
      });
      Array.prototype.forEach.call(document.querySelectorAll('.lp-nav'), function (b) {
        b.classList.toggle('active', b.dataset.nav === name);
      });
      // MUST stay inside this callback, immediately after the .active toggle
      // above — it measures the active button, so it has to run after the class
      // moves. It was previously broken by LP.motion.nav() wrapping this in
      // document.startViewTransition(), whose callback fires ASYNCHRONOUSLY: an
      // indicator() call placed after nav() ran BEFORE the toggle and measured
      // the PREVIOUS button, so the rail trailed one navigation behind. nav()
      // is synchronous now (the View Transition layer was removed 2026-07-27),
      // but do not move this line out — ordering, not the API, is the contract.
      LP.motion.indicator();
      $('crumb').textContent = CRUMBS[name] || name;
      // The preview may have been laid out while Review was hidden (0x0) — refit
      // now that it's visible so the slide fills the canvas.
      if (name === 'review') {
        requestAnimationFrame(function () { previewCtl.refit(); });
      }
      if (name === 'subjects') {
        renderSubjects();
      }
      if (name === 'process') renderSlideDetectionPreset();
      if (name === 'exports') updateExportPdfDescription();
      if (name === 'study') {
        studyV2Load();   // load grounded Study V2 content + progress
      }
      if (name === 'settings' && lpBridge.connected()) {
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
    });
    // N-5: transient toasts do not survive a screen change.
    dismissToast();
    if (typeof saveAppSession === 'function') saveAppSession();
    if (name === 'home' && typeof renderContinueCard === 'function') renderContinueCard();
  }

  function applyTheme(theme, persist) {
    if (LP.state.theme === theme && document.documentElement.dataset.theme === theme) return;
    LP.state.theme = theme;
    document.documentElement.dataset.theme = theme;
    $('theme-label').textContent = theme === 'light' ? 'DARK' : 'LIGHT';
    $('theme-icon').setAttribute('d', theme === 'light'
      ? 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4'
      : 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z');
    $('btn-set-light').classList.toggle('active', theme === 'light');
    $('btn-set-dark').classList.toggle('active', theme === 'dark');
    if (persist) lpBridge.call('set_setting', 'theme', theme);
  }

  function setTheme(theme) { applyTheme(theme, true); }

  function initialTheme() {
    try {
      var saved = window.localStorage.getItem('lecturepack.electron.theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (e) { /* private/file contexts may deny localStorage */ }
    return document.documentElement.dataset.theme || 'light';
  }

  function applyInitialTheme() {
    var theme = initialTheme();
    if (theme === document.documentElement.dataset.theme) {
      // Keep the explicit light-default path visible to the legacy WebView
      // contract while still avoiding a duplicate theme mutation on startup.
      applyTheme(document.documentElement.dataset.theme || 'light', false);
      return;
    }
    applyTheme(theme, false);
  }

  function setFocus(on) {
    LP.state.focus = on;
    $('app').dataset.focus = on ? 'true' : 'false';
    var pill = $('focus-pill');
    if (!pill) return;
    if (on) {
      pill.classList.remove('lp-out');
      pill.hidden = false;
      if (!LP.motion.reduced()) {
        // OPACITY-ONLY entrance, for the same reason as the toast (§4.7): this
        // pill carries an inline `transform:translateX(-50%)` for horizontal
        // centering. A transform keyframe with only a `from` state (lpseat-sm)
        // takes the element's cascaded transform as its implicit `to`, and with
        // fill-mode `both` the `from` REPLACES the inline centering -- so the
        // pill started half its own width off-centre and slid sideways into
        // place. `.lp-anim-fade` touches opacity only and cannot conflict with
        // any transform the element carries.
        pill.classList.remove('lp-anim-fade');
        void pill.offsetWidth; // force reflow so the entrance re-triggers
        pill.classList.add('lp-anim-fade');
      }
    } else {
      try { LP.motion.close(pill, function () { pill.hidden = true; }, 'lp-out'); }
      catch (e) { pill.hidden = true; }
    }
  }

  /* The whole window is the drop target for a file from the OS, so the whole
     window is what lights up. Deliberately a DIFFERENT visual language from the
     internal-drag vocabulary: a full-bleed inset frame rather than a ring around
     one element, because "anywhere works" is the message and picking out a
     single panel would contradict it.
     Created on demand and position:fixed, so it costs nothing until a file is
     actually over the window and it never participates in layout. */
  function fileDropVeil(show) {
    var el = document.getElementById('lp-file-drop-veil');
    if (!el) {
      if (!show) return;
      el = document.createElement('div');
      el.id = 'lp-file-drop-veil';
      el.className = 'lp-file-drop-veil';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<span class="lp-file-drop-card">' +
        '<span class="lp-file-drop-arrow"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" ' +
        'stroke="var(--on-signal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 5v14M5 12l7 7 7-7"/></svg></span>' +
        'Drop the video anywhere</span>';
      document.body.appendChild(el);
    }
    el.hidden = !show;
  }

  function setOnb(state) { // null | 'drop' | 'detected'
    LP.state.onb = state;
    // 'drop' means a real file is hovering the window; anything else clears it.
    fileDropVeil(state === 'drop');
    var ov = $('onb-overlay');
    if (state === null) {
      if (ov) {
        try { LP.motion.close(ov, function () { ov.hidden = true; }); }
        catch (e) { ov.hidden = true; }
      }
    } else if (ov) {
      ov.classList.remove('out');
      var ovPop = ov.querySelector && ov.querySelector('.lp-pop');
      if (ovPop) ovPop.classList.remove('out');
      ov.hidden = false;
    }
    $('onb-drop').hidden = state !== 'drop';
    $('onb-detected').hidden = state !== 'detected';
    if (state !== null) focusFirst($('onb-overlay'));
  }

  /* ---------- modal containment (BUG-01 / BUG-02) ----------
     Overlays in this UI are plain divs toggled with [hidden] plus dynamically
     created .lp-modal-ov nodes.  These helpers give whichever one is on top
     ownership of the keyboard. */
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),' +
    'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

  function visibleFocusable(scope) {
    return Array.prototype.filter.call(scope.querySelectorAll(FOCUSABLE), function (el) {
      if (el.hidden || el.closest('[hidden]')) return false;
      return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    });
  }

  // Highest-z-index open overlay, or null when none is open.
  function topOverlay() {
    var open = [];
    ['runtime-setup-overlay', 'all-slides-overlay', 'onb-overlay', 'whatsnew-overlay',
      'batch-overlay', 'search-overlay', 'palette-overlay'].forEach(function (id) {
      var el = $(id);
      if (el && !el.hidden) open.push(el);
    });
    Array.prototype.push.apply(open, document.querySelectorAll('.lp-modal-ov'));
    if (!open.length) return null;
    return open.reduce(function (a, b) {
      var za = parseInt(window.getComputedStyle(a).zIndex, 10) || 0;
      var zb = parseInt(window.getComputedStyle(b).zIndex, 10) || 0;
      return zb >= za ? b : a;   // later/higher wins, so the newest modal owns focus
    });
  }

  function focusFirst(scope) {
    var items = visibleFocusable(scope);
    if (items.length) setTimeout(function () { items[0].focus(); }, 30);
  }

  // Cycle Tab within `scope` instead of letting it reach the page behind.
  function trapFocus(scope, e) {
    var items = visibleFocusable(scope);
    if (!items.length) { e.preventDefault(); return; }
    var first = items[0], last = items[items.length - 1], active = document.activeElement;
    if (!scope.contains(active)) { e.preventDefault(); first.focus(); return; }
    if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  }

  /* ================= runtime setup gate =================
     The desktop bridge is the trust boundary.  This controller only renders
     its canonical admission/repair events; it never infers health or sizes. */
  /* First-run checklist wire contract (D-13): five canonical backend ids, in
     canonical order, with UI-owned friendly labels and live-region sentences.
     The backend owns the ids and the verdicts; the UI owns only this copy.
     Ids and order are locked to FIRST_RUN_CHECKLIST_ITEMS in
     lecturepack/services/first_run_checklist.py -- a cross-file test asserts
     the two lists match, so a sixth backend item fails loudly here instead of
     rendering an unlabelled row. */
  var FIRST_RUN_ROWS = [
    { id: 'windows_version', label: 'Windows version', checking: 'Checking Windows version…' },
    { id: 'ffmpeg_ffprobe', label: 'Media tools (FFmpeg)', checking: 'Checking FFmpeg & ffprobe…' },
    { id: 'whisper_runtime', label: 'Speech engine (Whisper)', checking: 'Checking Whisper runtime…' },
    { id: 'bundled_model', label: 'Speech model', checking: 'Checking speech model…' },
    { id: 'data_directory', label: 'Storage folder', checking: 'Checking storage folder…' }
  ];
  /* Two-entry backend-verdict -> badge data-state mapping. Backend decides,
     UI renders: an unrecognised verdict maps to no data-state at all, which
     renders as a neutral badge rather than inventing a third colour. */
  var FIRST_RUN_VERDICT_STATES = { ready: 'success', needs_attention: 'paused' };
  /* Anti-flicker pacing (UI-SPEC "Startup Progress Semantics"): resolved
     once, lazily, from the real --motion-normal token rather than a new
     one-off duration. Applied in both normal and reduced-motion mode -- the
     hold exists to prevent a visible flash, which is a STRONGER requirement
     for a reduced-motion user, not a weaker one, so it is never skipped
     under prefers-reduced-motion. */
  var ANTI_FLICKER_HOLD_MS = null;
  function antiFlickerHoldMs() {
    if (ANTI_FLICKER_HOLD_MS !== null) return ANTI_FLICKER_HOLD_MS;
    var raw = (typeof window !== 'undefined' && window.getComputedStyle)
      ? window.getComputedStyle(document.documentElement).getPropertyValue('--motion-normal') : '';
    var parsed = parseFloat(raw);
    ANTI_FLICKER_HOLD_MS = Number.isFinite(parsed) ? parsed : 160;
    return ANTI_FLICKER_HOLD_MS;
  }
  /* UI-SPEC "Startup Progress Semantics": the whisper-runtime check can
     legitimately run for several real seconds; past this threshold its
     live-region text gains a bounded reassurance clause. */
  var WHISPER_SLOW_NOTICE_MS = 5000;
  /* The one mutable lifecycle reducer used by the DOM controller and Node tests. */
  function RuntimeSetupGateModel() {
    var state = 'gate', returnState = 'gate', retryPending = false, cancelPending = false;
    var activeOperation = null, terminal = false, offer = null, bootstrapPending = true, healthy = false;
    var validationPath = null, acknowledged = false, checklist = [], checkProgress = {}, startupFailure = null;
    var REQUIRED_CHECK_IDS = ['windows_version', 'ffmpeg_ffprobe', 'whisper_runtime', 'bundled_model', 'data_directory'];
    function waitForChecklist() {
      state = 'checking';
      checkProgress = {};
      REQUIRED_CHECK_IDS.forEach(function (id) { checkProgress[id] = 'pending'; });
      return snapshot();
    }
    function requiredChecklistReady(items) {
      if (!Array.isArray(items) || items.length !== REQUIRED_CHECK_IDS.length) return false;
      return REQUIRED_CHECK_IDS.every(function (id) {
        return items.some(function (item) { return item && item.id === id && item.verdict === 'ready'; });
      });
    }
    function valid(value) {
      return !!(value && value.operation_id === activeOperation && value.app_version && value.source &&
        value.affected_components && Number.isSafeInteger(value.download_size_bytes) && value.download_size_bytes >= 0);
    }
    function snapshot() {
      return { state: state, returnState: returnState, retryPending: retryPending, cancelPending: cancelPending,
        activeOperation: activeOperation, terminal: terminal, offer: offer, bootstrapPending: bootstrapPending, healthy: healthy,
        validationPath: validationPath, acknowledged: acknowledged, checklist: checklist, checklistReady: requiredChecklistReady(checklist), checkProgress: checkProgress,
        startupFailure: startupFailure };
    }
    function accept(event) { return !!(event && event.operation_id === activeOperation && !terminal); }
    return {
      /* retryState deliberately preserves repairing: a retry must not visually regress to gate. */
      begin: function (id, retryState) {
        activeOperation = id; terminal = false; offer = null; cancelPending = false; retryPending = false;
        state = retryState === 'repairing' ? 'repairing' : 'gate'; return snapshot();
      },
      accept: accept,
      offer: function (value) {
        if (!accept(value)) return snapshot();
        offer = value;
        if (valid(value)) state = 'confirm'; else { state = 'failed'; terminal = true; }
        return snapshot();
      },
      confirm: function () { if (state === 'confirm' && valid(offer)) state = 'repairing'; return snapshot(); },
      diagnostics: function () { if (state !== 'diagnostics') { returnState = state; state = 'diagnostics'; } return snapshot(); },
      back: function () { state = returnState || 'gate'; return snapshot(); },
      retry: function () { if (!retryPending) retryPending = true; return snapshot(); },
      retryResult: function (bootstrap) { retryPending = false; return this.bootstrap(bootstrap); },
      requestCancel: function () { if (activeOperation && !terminal) cancelPending = true; return snapshot(); },
      abandon: function () { if (activeOperation) terminal = true; offer = null; cancelPending = false; state = 'gate'; return snapshot(); },
      bootstrap: function (bootstrap) {
        // Read the extended payload defensively: an absent key yields the
        // same falsy default the pre-01-07 reducer always had, so every
        // existing caller and test is unaffected.
        var pending = !!(bootstrap && bootstrap.bootstrap_pending);
        bootstrapPending = pending;
        validationPath = (bootstrap && bootstrap.validation_path) || null;
        acknowledged = !!(bootstrap && bootstrap.setup_acknowledged === true);
        checklist = (bootstrap && Array.isArray(bootstrap.checklist)) ? bootstrap.checklist : [];
        if (pending) {
          // A pending result carries no verdict yet: never set healthy or
          // terminal here, so a later resolved result can still route
          // freely. Full-path pending opens the checking overlay; light-path
          // pending stays invisible, exactly as today's warm launch (D-07).
          // An in-flight repair operation is never hijacked by a pending
          // bootstrap arriving mid-repair.
          if (validationPath === 'full' && !activeOperation) {
            waitForChecklist();
          }
          return snapshot();
        }
        if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') {
          healthy = false; terminal = true;
          if (!activeOperation) { state = 'gate'; terminal = false; offer = null; cancelPending = false; }
        } else if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY') {
          healthy = true;
          if (activeOperation && !terminal) this.event({ operation_id: activeOperation, kind: 'admitted' });
          else if (!activeOperation && !acknowledged) {
            // A healthy result without the authoritative five-row checklist
            // is still incomplete. Keep the existing checking panel visible
            // until the backend result can support a real checklist frame.
            if (requiredChecklistReady(checklist)) state = 'checklist';
            else waitForChecklist();
          }
        }
        return snapshot();
      },
      /* Per-component checking progress (D-08/D-09). Ignored outside the
         checking state and for any id not in the canonical five -- pacing
         and timers are the controller's job, this method holds neither. */
      progress: function (payload) {
        if (state !== 'checking' || !payload || !payload.id) return snapshot();
        var known = FIRST_RUN_ROWS.some(function (row) { return row.id === payload.id; });
        if (!known) return snapshot();
        checkProgress[payload.id] = payload.state;
        return snapshot();
      },
      startupFailed: function (payload) {
        startupFailure = payload || {};
        bootstrapPending = false;
        healthy = false;
        terminal = true;
        state = 'startup_failed';
        return snapshot();
      },
      retryStartup: function () {
        startupFailure = null;
        bootstrapPending = true;
        healthy = false;
        terminal = false;
        state = 'checking';
        checkProgress = {};
        FIRST_RUN_ROWS.forEach(function (row) { checkProgress[row.id] = 'pending'; });
        return snapshot();
      },
      /* The only write path for the acknowledged flag on the reducer side;
         the bridge slot (acknowledge_setup) is the only write path on the
         persistence side. The controller owns closing the overlay. */
      acknowledge: function (bootstrap) {
        acknowledged = true;
        if (bootstrap && Array.isArray(bootstrap.checklist)) checklist = bootstrap.checklist;
        return snapshot();
      },
      /* The seam a repair-recovered first-run admission uses: closeReady()
         is not the only future caller, so the healthy/unacknowledged guard
         lives here rather than at each call site. */
      toChecklist: function () {
        if (healthy && !acknowledged) {
          if (requiredChecklistReady(checklist)) state = 'checklist';
          else waitForChecklist();
        }
        return snapshot();
      },
      waitForChecklist: waitForChecklist,
      event: function (event) {
        if (!accept(event)) return snapshot();
        if (event.kind === 'metadata_ready') return this.offer(event.offer || event);
        if (event.kind === 'started') state = 'repairing';
        else if (event.kind === 'cancel_requested') this.requestCancel();
        else if (event.kind === 'cancelled') { terminal = true; state = 'gate'; }
        else if (event.kind === 'admitted') { terminal = true; state = 'ready'; healthy = true; }
        else if (event.kind === 'offline' || (event.kind === 'failed' && event.classification === 'offline')) { terminal = true; state = 'offline'; }
        else if (event.kind === 'failed') { terminal = true; state = 'failed'; }
        return snapshot();
      },
      reset: function () {
        // `acknowledged` is deliberately left untouched: it mirrors a value
        // persisted in the user's config.json (D-16), not in-flight
        // operation state -- clearing it here would re-show the checklist
        // for the rest of the session even though the backend still
        // considers setup acknowledged.
        state = 'gate'; returnState = 'gate'; retryPending = false; cancelPending = false;
        activeOperation = null; terminal = false; offer = null; healthy = false; startupFailure = null; return snapshot();
      },
      // Closing a valid runtime overlay must clear the transient repair state
      // without leaving the reducer at the invalid default `gate` state.
      restoreHealthy: function () {
        healthy = true; terminal = true; state = 'ready'; return snapshot();
      },
      snapshot: snapshot
    };
  }
  var RuntimeSetupGate = (function () {
    var STATES = ['gate', 'diagnostics', 'confirm', 'repairing', 'offline', 'failed', 'ready', 'checking', 'checklist', 'startup_failed'];
    var bootstrapSnapshot = null, restoreInert = [], inertCaptured = false, priorFocus = null;
    var lastRenderedState = null, closeInFlight = false;
    var eventModel = RuntimeSetupGateModel();

    function overlay() { return $('runtime-setup-overlay'); }
    function isOpen() { var el = overlay(); return !!(el && !el.hidden); }
    function isBlocking() { return eventModel.snapshot().bootstrapPending || isOpen(); }
    function operationId() {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
      return 'runtime-repair-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    }
    function text(id, value) { var el = $(id); if (el) el.textContent = value == null ? '' : String(value); }
    function announce(id, value) { text(id, value); }
    function componentRows() {
      if (!bootstrapSnapshot) return [];
      var list = bootstrapSnapshot.failed_components || bootstrapSnapshot.components || bootstrapSnapshot.affected_components || [];
      return Array.isArray(list) ? list : [];
    }
    function friendlyComponent(row) {
      if (typeof row === 'string') return row;
      return row && (row.friendly_name || row.label || row.component || row.name) || 'Runtime component';
    }
    function setUnderlyingInert(open) {
      var root = $('app'); if (!root) return;
      var children = root.children;
      if (open) {
        if (inertCaptured) return;
        var candidate = document.activeElement;
        priorFocus = isNormalFocusable(candidate) ? candidate : null;
        restoreInert = [];
        Array.prototype.forEach.call(children, function (child) {
          if (child === overlay()) return;
          restoreInert.push({ el: child, inert: child.inert, aria: child.getAttribute('aria-hidden'), pointer: child.style.pointerEvents });
          try { child.inert = true; } catch (e) {}
          child.setAttribute('aria-hidden', 'true'); child.style.pointerEvents = 'none';
        });
        inertCaptured = true;
      } else {
        if (!inertCaptured) return;
        restoreInert.forEach(function (saved) {
          try { saved.el.inert = saved.inert; } catch (e) {}
          if (saved.aria === null) saved.el.removeAttribute('aria-hidden'); else saved.el.setAttribute('aria-hidden', saved.aria);
          saved.el.style.pointerEvents = saved.pointer;
        });
        restoreInert = []; inertCaptured = false;
      }
    }
    function isNormalFocusable(candidate) {
      if (!candidate || candidate === document.body || candidate === document.documentElement || candidate.disabled || candidate.tabIndex < 0 || !candidate.closest) return false;
      if (!candidate.closest('#app') || candidate.closest('#runtime-setup-overlay') || candidate.closest('[aria-hidden="true"], [inert], [hidden]')) return false;
      return candidate.matches('a[href], button, input, select, textarea, summary, [tabindex]');
    }
    function fallbackFocus() {
      var home = document.querySelector('[data-nav="home"], [data-screen-nav="home"], #nav-home');
      if (isNormalFocusable(home)) return home;
      var main = document.querySelector('#app main, #main, [role="main"]');
      return main && main.querySelector('a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])');
    }
    function renderComponents() {
      var host = $('runtime-components'), empty = $('runtime-components-empty');
      if (!host || !empty) return;
      host.textContent = '';
      var rows = componentRows(); empty.hidden = !!rows.length;
      rows.forEach(function (row) {
        var label = friendlyComponent(row), line = document.createElement('div');
        line.style.cssText = 'background:var(--panel2);border:2px solid var(--line);border-radius:9px;padding:8px 10px;min-width:0;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden';
        line.textContent = label; line.title = label; line.setAttribute('aria-label', label); host.appendChild(line);
      });
    }
    /* Builds one first-run row (checking or checklist). The badge's inline
       style is deliberately restricted to layout-only longhands -- no border
       shorthand, no colour -- so the `.lp-state[data-state]` class rule
       (app.css:625-632) supplies the Ready/Needs-Attention/neutral colour.
       An inline colour declaration would beat that class rule regardless of
       specificity and silently erase it (the first Known Trap). */
    function firstRunRow(label, badgeText, dataState, rowId) {
      var row = document.createElement('div');
      row.setAttribute('data-runtime-row-id', rowId || '');
      // flex-wrap is required so a checklist advisory sentence (a third,
      // full-width child appended only for a needs-attention row) wraps
      // below the label/badge pair instead of squeezing into one line.
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:8px 10px;border-radius:9px;min-width:0';
      var labelEl = document.createElement('div');
      labelEl.setAttribute('data-runtime-label', 'true');
      // flex:1;min-width:0 make the two-line clamp actually take effect
      // inside this flex row instead of overflowing the badge (the row
      // container's own min-width:0 alone is not sufficient for a flex
      // child); the clamp declarations themselves are renderComponents()'s
      // exact truncation pattern, reused verbatim per the UI-SPEC.
      labelEl.style.cssText = 'flex:1;min-width:0;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden';
      labelEl.textContent = label; labelEl.title = label; labelEl.setAttribute('aria-label', label);
      var badge = document.createElement('span');
      badge.setAttribute('data-runtime-badge', 'true');
      badge.className = 'lp-state';
      if (dataState) badge.setAttribute('data-state', dataState);
      badge.style.cssText = "border-width:2px;border-style:solid;border-radius:9px;padding:4px 10px;font:700 14px 'Space Grotesk';white-space:nowrap;flex:0 0 auto";
      badge.textContent = badgeText;
      row.appendChild(labelEl); row.appendChild(badge);
      return row;
    }
    function updateFirstRunRow(host, index, rowId, label, badgeText, dataState, advisoryText) {
      var row = host.children[index];
      if (!row || row.getAttribute('data-runtime-row-id') !== rowId) {
        row = firstRunRow(label, badgeText, dataState, rowId);
        if (host.children[index]) host.replaceChild(row, host.children[index]);
        else host.appendChild(row);
      }
      var labelEl = row.querySelector('[data-runtime-label]');
      var badge = row.querySelector('[data-runtime-badge]');
      if (labelEl) { labelEl.textContent = label; labelEl.title = label; labelEl.setAttribute('aria-label', label); }
      if (badge) {
        if (dataState) badge.setAttribute('data-state', dataState); else badge.removeAttribute('data-state');
        badge.textContent = badgeText;
      }
      var advisory = row.querySelector('[data-runtime-advisory]');
      if (advisoryText) {
        if (!advisory) {
          advisory = document.createElement('div');
          advisory.setAttribute('data-runtime-advisory', 'true');
          advisory.style.cssText = 'flex-basis:100%;font-size:12px;line-height:1.4;overflow-wrap:anywhere';
          row.appendChild(advisory);
        }
        advisory.textContent = advisoryText; advisory.title = advisoryText;
      } else if (advisory) {
        advisory.remove();
      }
    }
    var FIRST_RUN_CHECKING_BADGE_TEXT = { pending: 'Pending', checking: 'Checking…', resolved: 'Done' };
    function renderChecking() {
      var host = $('runtime-checking-rows'); if (!host) return;
      var progress = eventModel.snapshot().checkProgress || {};
      var resolvedCount = 0;
      // Row identity comes from the fixed FIRST_RUN_ROWS array, never from
      // progress's own keys, so all five rows exist on the first frame and
      // never change position regardless of resolution order (D-08).
      var rowIndex = 0;
      FIRST_RUN_ROWS.forEach(function (row) {
        var mark = progress[row.id] || 'pending';
        if (mark === 'resolved') resolvedCount++;
        updateFirstRunRow(host, rowIndex++, row.id, row.label,
          FIRST_RUN_CHECKING_BADGE_TEXT[mark] || 'Pending', null, '');
      });
      while (host.children.length > rowIndex) host.lastElementChild.remove();
      var total = FIRST_RUN_ROWS.length, fraction = resolvedCount / total;
      var bar = $('runtime-checking-progress'), fill = bar && bar.querySelector('.lp-fill');
      if (fill) fill.style.transform = 'scaleX(' + fraction + ')';
      if (bar) bar.setAttribute('aria-valuenow', String(Math.round(fraction * 100)));
      text('runtime-checking-counter', resolvedCount + ' of ' + total + ' checked');
    }
    // The checklist is a rendering of the backend's five canonical verdicts.
    // It never infers health from a detail string or from a partial payload.
    function renderChecklist() {
      var host = $('runtime-checklist-rows'), empty = $('runtime-checklist-empty'), done = $('btn-runtime-done');
      if (!host || !empty) return;
      var view = eventModel.snapshot();
      var items = Array.isArray(view.checklist) ? view.checklist : [];
      var byId = {};
      items.forEach(function (item) { if (item && item.id) byId[item.id] = item; });
      var ready = !!view.checklistReady;
      // A checklist frame is meaningful only when all five authoritative
      // records are present and green. If a malformed/partial payload reaches
      // this renderer boundary, keep its waiting copy visible and keep Done
      // hidden instead of presenting a false readiness state.
      empty.hidden = ready;
      if (done) { done.disabled = !ready; done.hidden = !ready; }
      var rowIndex = 0;
      FIRST_RUN_ROWS.forEach(function (row) {
        var item = byId[row.id] || { id: row.id, verdict: 'pending', detail: '' };
        var dataState = FIRST_RUN_VERDICT_STATES[item.verdict] || null;
        var badgeText = item.verdict === 'needs_attention' ? 'Needs Attention' : item.verdict === 'ready' ? 'Ready' : 'Pending';
        var advisory = item.detail || (item.verdict === 'needs_attention' ? 'This required check needs attention.' : '');
        updateFirstRunRow(host, rowIndex++, row.id, row.label, badgeText, dataState, advisory);
      });
      while (host.children.length > rowIndex) host.lastElementChild.remove();
    }
    function renderOffer() {
      var value = eventModel.snapshot().offer, enabled = validOffer(value);
      text('runtime-offer-source', enabled ? value.source : '');
      text('runtime-offer-version', enabled ? value.app_version : '');
      text('runtime-offer-components', enabled ? value.affected_components : '');
      text('runtime-offer-size', enabled ? value.download_size_label : '');
      text('runtime-offer-technical', enabled ? value.technical_details || '' : '');
      $('btn-runtime-confirm').disabled = !enabled;
    }
    function renderStartupFailure() {
      var failure = eventModel.snapshot().startupFailure || {};
      var check = failure.failed_check || {};
      text('startup-failure-title', check.title || 'Processing service failed to start.');
      text('startup-failure-detail', check.detail || failure.detail || failure.message || 'LecturePack could not start its processing service.');
      var diagnostics = failure.diagnostics || failure;
      text('startup-failure-technical', typeof diagnostics === 'string' ? diagnostics : JSON.stringify(diagnostics, null, 2));
    }
    function validOffer(value) {
      return !!(value && typeof value.operation_id === 'string' && value.operation_id === eventModel.snapshot().activeOperation &&
        typeof value.app_version === 'string' && typeof value.source === 'string' &&
        typeof value.affected_components === 'string' && typeof value.download_size_bytes === 'number' &&
        Number.isSafeInteger(value.download_size_bytes) && value.download_size_bytes >= 0 &&
        typeof value.download_size_label === 'string');
    }
    function formatOfferSize(bytes) {
      // This is the checked four-archive total supplied by the authenticated
      // offer. Formatting it here never estimates or recomputes the total.
      return Number(bytes).toLocaleString('en-US') + ' bytes';
    }
    function render(dataChanged, forceCheckingOpen) {
      var view = eventModel.snapshot();
      // Defensive DOM-boundary guard: no malformed bootstrap or stale event
      // may expose the checklist heading before the five green records exist.
      if (view.state === 'checklist' && !view.checklistReady) view = eventModel.waitForChecklist();
      var next = view.state;
      if (STATES.indexOf(next) < 0) return;
      var el = overlay(); if (!el) return;
      if (closeInFlight) return;
      if (next === 'checking' && el.hidden && !forceCheckingOpen) {
        scheduleCheckingOpen();
        return;
      }
      var stateChanged = next !== lastRenderedState;
      if (!stateChanged && !dataChanged) return;
      if (stateChanged) {
        el.hidden = false; el.classList.remove('out'); setUnderlyingInert(true);
        Array.prototype.forEach.call(el.querySelectorAll('[data-runtime-state]'), function (panel) { panel.hidden = panel.dataset.runtimeState !== next; });
      }
      renderComponents(); renderOffer(); renderChecking(); renderChecklist(); renderStartupFailure();
      // Runtime Setup is a blocking gate. It has no renderer-side exit or
      // bypass path; the only checklist action is Done after green verdicts.
      // Focus moves ONLY to genuinely interactive elements. The state headings
      // used to carry tabindex="-1" and be focused here so a screen reader
      // announced each new state -- but Chromium counts that programmatic
      // focus as :focus-visible, so the global focus ring painted a blue
      // rectangle around a heading nobody could interact with, which read as
      // a rendering bug until the next click cleared it. The announcement was
      // redundant anyway: every state change already writes a sentence into
      // #runtime-live-polite / #runtime-live-assertive, which is what a live
      // region is for. States with no focusable content (checking, ready) now
      // move focus nowhere; #app is inert while the gate is open, so there is
      // nothing for a stray Tab to escape to.
      var targets = { gate: 'btn-runtime-repair', confirm: 'btn-runtime-confirm', repairing: 'btn-runtime-cancel', offline: 'btn-runtime-offline-retry', failed: 'btn-runtime-failed-retry', diagnostics: 'btn-runtime-copy',
        startup_failed: 'btn-startup-retry' };
      if (next === 'checklist' && view.checklistReady) targets.checklist = 'btn-runtime-done';
      if (stateChanged) {
        var target = $(targets[next]); if (target) target.focus();
      }
      lastRenderedState = next;
    }
    // F-6: once the runtime is healthy, a hidden overlay must not keep the
    // stale "Runtime needs repair" gate markup live. Leave it parked on the
    // neutral healthy panel so an accidental re-show can never claim the
    // runtime is broken after a healthy bootstrap.
    function neutralPanels() {
      var el = overlay(); if (!el) return;
      Array.prototype.forEach.call(el.querySelectorAll('[data-runtime-state]'), function (panel) {
        panel.hidden = panel.dataset.runtimeState !== 'ready';
      });
    }
    // Shared close sequence: restore the underlying app from inert, hide the
    // overlay, reset the reducer, and return focus. closeReady() and
    // acknowledge() both fully close the overlay this same way.
    function closeOverlay() {
      var el = overlay(); if (!el || closeInFlight) return;
      clearCheckingTimers();
      var preserveHealthy = eventModel.snapshot().healthy;
      if (el.hidden) {
        // beginBootstrap() always captured the underlying app as inert. Warm
        // starts can skip opening this overlay entirely, so release that
        // capture even though there is no animated overlay to close.
        setUnderlyingInert(false);
        eventModel.reset();
        if (preserveHealthy) eventModel.restoreHealthy();
        lastRenderedState = null;
        neutralPanels();
        return;
      }
      closeInFlight = true;
      function finish() {
        closeInFlight = false;
        setUnderlyingInert(false); el.hidden = true; eventModel.reset();
        if (preserveHealthy) eventModel.restoreHealthy();
        lastRenderedState = null;
        neutralPanels();
        var target = isNormalFocusable(priorFocus) ? priorFocus : fallbackFocus();
        if (isNormalFocusable(target)) target.focus();
      }
      try { LP.motion.close(el, finish); } catch (e) { finish(); }
    }
    function closeReady() {
      var snap = eventModel.snapshot();
      if (snap.state !== 'ready') return;
      // Repair-recovered first run (UI-SPEC Open Question 2, owner-resolved):
      // keyed purely to the persisted acknowledged flag, never to which path
      // reached HEALTHY, so a first-ever healthy admission that needed a
      // repair still shows the checklist exactly once, right after this
      // existing success state closes -- the checklist is the gateway to
      // the demo offer (D-17), so skipping it here would silently drop the
      // demo offer for the users with the roughest install.
      if (snap.healthy && !snap.acknowledged) {
        var view = eventModel.toChecklist();
        announce('runtime-live-assertive', view.state === 'checklist'
          ? "You're ready to go."
          : 'LecturePack is still checking the required runtime components.');
        render();
        return;
      }
      closeOverlay();
    }
    // Per-row anti-flicker pacing state (D-08/D-09, BUG-21 stale-timer
    // lesson): every hold timer and the slow-notice timer are cleared when
    // the corresponding row resolves and when the state leaves checking, so
    // no superseded timer can ever write to a row that has moved on.
    var CHECKING_GRACE_MS = 600;
    var checkingHoldTimers = {}, checkingStartedAt = {}, whisperSlowTimer = null, checkingOpenTimer = null;
    function scheduleCheckingOpen() {
      var el = overlay();
      if (!el || !el.hidden || checkingOpenTimer !== null) return;
      checkingOpenTimer = setTimeout(function () {
        checkingOpenTimer = null;
        var current = overlay(), view = eventModel.snapshot();
        if (view.state === 'checking' && current && current.hidden) render(true, true);
      }, CHECKING_GRACE_MS);
    }
    function clearCheckingTimers() {
      Object.keys(checkingHoldTimers).forEach(function (id) { clearTimeout(checkingHoldTimers[id]); });
      checkingHoldTimers = {}; checkingStartedAt = {};
      if (whisperSlowTimer) { clearTimeout(whisperSlowTimer); whisperSlowTimer = null; }
      if (checkingOpenTimer !== null) { clearTimeout(checkingOpenTimer); checkingOpenTimer = null; }
    }
    function checkingRowSentence(id) {
      var row = FIRST_RUN_ROWS.filter(function (r) { return r.id === id; })[0];
      return row ? row.checking : '';
    }
    function admit(bootstrap) {
      bootstrapSnapshot = bootstrap && bootstrap.setup_required || bootstrap || bootstrapSnapshot;
      var before = eventModel.snapshot(), view = eventModel.bootstrap(bootstrap);
      if (before.state === 'checking' && view.state !== 'checking') clearCheckingTimers();
      syncDemoAdmission(view);
      // The overlay is already inert from the boot-time beginBootstrap()
      // call, so this is simply the first frame the user sees.
      if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY' && bootstrap.setup_acknowledged === true && !before.activeOperation) { closeOverlay(); return; }
      if (view.state === 'checking') { render(true); return; }
      // D-11: the existing failure gate, entirely unchanged.
      if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') { render(true); return; }
      // D-12: a first-ever healthy admission always shows the checklist.
      // The assertive live region announces the state change itself, not
      // per-row chatter (that stays on the polite region during checking).
      if (view.state === 'checklist') { announce('runtime-live-assertive', "You're ready to go."); render(true); return; }
      if (view.state === 'ready') ready();
    }
    var acknowledgeInFlight = false;
    function acknowledge() {
      var snap = eventModel.snapshot();
      if (snap.state !== 'checklist' || !snap.checklistReady || acknowledgeInFlight) return; // idempotent and green-only
      acknowledgeInFlight = true;
      var doneBtn = $('btn-runtime-done');
      if (doneBtn) doneBtn.disabled = true;
      lpBridge.call('acknowledge_setup').then(function (json) {
        var refreshed = parseBridgeResult(json);
        // Done is an authoritative backend transition. An absent response or
        // an explicit FEATURE_UNAVAILABLE/error envelope must leave the gate
        // open instead of locally pretending setup was persisted.
        if (!refreshed || refreshed.ok === false) {
          if (doneBtn) { doneBtn.disabled = false; doneBtn.hidden = false; }
          acknowledgeInFlight = false;
          toast((refreshed && (refreshed.error || refreshed.message)) || 'LecturePack could not save setup completion. Try again.');
          return;
        }
        var view = eventModel.acknowledge(refreshed);
        syncDemoAdmission(view);
        closeOverlay();
        acknowledgeInFlight = false;
      }, function () {
        if (doneBtn) doneBtn.disabled = false;
        acknowledgeInFlight = false;
        toast('LecturePack could not save setup completion. Try again.');
      });
    }
    // Per-component checking progress (D-08/D-09). The reducer records the
    // raw mark immediately; only the re-render of a flip TO resolved is
    // paced, by the anti-flicker hold, so a fast check never reads as a
    // flash. Nothing else re-renders the checking rows while in the
    // checking state, so a paced re-render can never be pre-empted by a
    // premature one.
    function progress(payload) {
      var record = typeof payload === 'string'
        ? (function () { try { return JSON.parse(payload); } catch (e) { return null; } })()
        : payload;
      if (!record || typeof record !== 'object' || !record.id) return;
      if (eventModel.snapshot().state !== 'checking') return;
      var id = record.id, mark = record.state;
      var groupedIds = {
        ffmpeg: 'ffmpeg_ffprobe', ffprobe: 'ffmpeg_ffprobe',
        whisper_runtime: 'whisper_runtime', whisper_smoke: 'whisper_runtime'
      };
      id = groupedIds[id] || id;
      record.id = id;
      eventModel.progress(record);
      if (mark === 'checking') {
        checkingStartedAt[id] = Date.now();
        announce('runtime-live-polite', checkingRowSentence(id));
        if (id === 'whisper_runtime') {
          if (whisperSlowTimer) clearTimeout(whisperSlowTimer);
          whisperSlowTimer = setTimeout(function () {
            announce('runtime-live-polite', checkingRowSentence('whisper_runtime') + ' this can take a few seconds.');
          }, WHISPER_SLOW_NOTICE_MS);
        }
        render(true);
        return;
      }
      if (mark === 'resolved') {
        if (id === 'whisper_runtime' && whisperSlowTimer) { clearTimeout(whisperSlowTimer); whisperSlowTimer = null; }
        if (checkingHoldTimers[id]) clearTimeout(checkingHoldTimers[id]);
        var elapsed = Date.now() - (checkingStartedAt[id] || Date.now());
        var remaining = Math.max(0, antiFlickerHoldMs() - elapsed);
        if (remaining <= 0) { delete checkingHoldTimers[id]; render(true); }
        else checkingHoldTimers[id] = setTimeout(function () { delete checkingHoldTimers[id]; render(true); }, remaining);
        return;
      }
      render(true);
    }
    // The guided demo is available only after this authoritative setup gate
    // admits the runtime. Its controller owns both initial and repair paths.
    // D-17: the demo is reachable only after the user continues past the
    // checklist or deliberately skips it -- extending this one boolean with
    // the acknowledged term is what makes every existing caller (initial
    // admit, retry path, repair-admitted event) inherit that gate for free,
    // rather than adding a second, parallel gating mechanism.
    function syncDemoAdmission(view) {
      setDemoAdmissionAvailable(!!(view && view.healthy && !view.bootstrapPending && view.acknowledged &&
        (view.state === 'ready' || !view.activeOperation)));
    }
    function startupFailed(payload) {
      var failure = typeof payload === 'string'
        ? (function () { try { return JSON.parse(payload); } catch (e) { return {}; } })()
        : (payload || {});
      clearCheckingTimers();
      eventModel.startupFailed(failure);
      announce('runtime-live-assertive', "LecturePack couldn't start.");
      render(true, true);
    }
    function retryStartup() {
      eventModel.retryStartup();
      render(true, true);
      lpBridge.call('retry_startup').then(function (result) {
        if (result && result.ok === false) {
          startupFailed({ reason: 'sidecar_start_failed', detail: result.error || 'Processing service failed to start.' });
        }
      });
    }
    function handleElectronRepairResult(operationId, value) {
      var result = value;
      if (typeof result === 'string') {
        try { result = JSON.parse(result); } catch (e) { result = null; }
      }
      if (!result || result.type !== 'repair_unavailable' || result.operation_id !== operationId) return false;
      var view = eventModel.event({ operation_id: operationId, kind: 'failed', classification: 'portable_unavailable' });
      text('runtime-failure-reason', result.message || 'Reinstall LecturePack to restore the bundled runtime.');
      announce('runtime-live-assertive', 'The bundled runtime cannot be repaired in place.');
      render(true);
      return !!view;
    }
    function beginOffer() {
      var previous = eventModel.snapshot(); if (previous.retryPending || (previous.activeOperation && !previous.terminal)) return;
      var view = eventModel.begin(operationId());
      $('btn-runtime-repair').disabled = true; announce('runtime-live-polite', 'Checking runtime…');
      render(); lpBridge.beginRuntimeRepairOffer(view.activeOperation).then(function (result) {
        handleElectronRepairResult(view.activeOperation, result);
      });
    }
    function confirm() {
      var before = eventModel.snapshot(); if (!validOffer(before.offer) || before.terminal) return;
      var view = eventModel.confirm(); if (view.state !== 'repairing') return;
      render(); text('runtime-progress-text', 'Downloading'); lpBridge.confirmRuntimeRepair(view.activeOperation).then(function (result) {
        handleElectronRepairResult(view.activeOperation, result);
      });
    }
    function retryAssessment() {
      if (eventModel.snapshot().retryPending) return;
      eventModel.retry(); $('btn-runtime-retry').disabled = true; announce('runtime-live-polite', 'Checking runtime…');
      lpBridge.retryRuntimeAssessment().then(function (json) {
        var bootstrap; try { bootstrap = JSON.parse(json); } catch (e) { bootstrap = null; }
        bootstrapSnapshot = bootstrap && bootstrap.setup_required || bootstrap || bootstrapSnapshot;
        var view = eventModel.retryResult(bootstrap); $('btn-runtime-retry').disabled = false;
        syncDemoAdmission(view);
        if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY' && !view.activeOperation) closeOverlay(); else render(true);
      });
    }
    function beginNewRepair() {
      var view = eventModel.begin(operationId(), 'repairing');
      render(); text('runtime-progress-text', 'Downloading'); lpBridge.beginRuntimeRepairOffer(view.activeOperation).then(function (result) {
        handleElectronRepairResult(view.activeOperation, result);
      });
    }
    function cancel() {
      var view = eventModel.snapshot(); if (!view.activeOperation || view.cancelPending || view.terminal) return;
      view = eventModel.requestCancel(); $('btn-runtime-cancel').disabled = true; text('btn-runtime-cancel', 'Cancelling safely…');
      lpBridge.cancelRuntimeRepair(view.activeOperation).then(function (result) {
        var payload = result;
        if (typeof payload === 'string') {
          try { payload = JSON.parse(payload); } catch (e) { payload = null; }
        }
        if (payload && payload.type === 'cancelled' && payload.operation_id === view.activeOperation) {
          eventModel.event({ operation_id: view.activeOperation, kind: 'cancelled' });
          render(true);
        }
      });
    }
    function diagnostics(invoker) {
      eventModel.diagnostics();
      if (invoker) RuntimeSetupGate._diagnosticsInvoker = invoker;
      text('runtime-diagnostics-summary', 'Review the runtime repair details below.');
      text('runtime-diagnostics-report', bootstrapSnapshot && (bootstrapSnapshot.diagnostics || bootstrapSnapshot.summary) || 'No additional diagnostics are available.');
      if (lpBridge.connected()) lpBridge.call('run_diagnostics', LP.state.jobId || '');
      render();
    }
    function back() {
      eventModel.back(); render();
      if (RuntimeSetupGate._diagnosticsInvoker) RuntimeSetupGate._diagnosticsInvoker.focus();
    }
    function ready() {
      announce('runtime-live-assertive', "You're ready"); render();
      if (LP.motion.reduced()) closeReady(); else setTimeout(closeReady, 800);
    }
    function event(payload) {
      var d = typeof payload === 'string' ? (function () { try { return JSON.parse(payload); } catch (e) { return null; } })() : payload;
      if (!eventModel.accept(d)) return;
      var kind = d.kind;
      if (kind === 'metadata_ready') {
        var o = d.offer || d;
        var normalizedOffer = { operation_id: d.operation_id, app_version: o.app_version, source: o.source || o.official_source,
          affected_components: Array.isArray(o.affected_components) ? o.affected_components.join(', ') : o.affected_components,
          download_size_bytes: o.download_size_bytes,
          download_size_label: typeof o.download_size_bytes === 'number' && Number.isSafeInteger(o.download_size_bytes) && o.download_size_bytes >= 0 ? formatOfferSize(o.download_size_bytes) : '',
          technical_details: o.technical_details || '' };
        var offered = eventModel.event({ operation_id: d.operation_id, kind: 'metadata_ready', offer: normalizedOffer });
        if (offered.state !== 'confirm' || !validOffer(offered.offer)) announce('runtime-live-assertive', 'Repair could not be completed.');
        else $('btn-runtime-repair').disabled = false;
        render(true); return;
      }
      var view = eventModel.event(d);
      if (kind === 'started') { render(); return; }
      if (kind === 'progress') {
        var percent = typeof d.percent === 'number' ? Math.max(0, Math.min(100, d.percent)) : null;
        var phase = d.phase === 'verifying' ? 'Verifying' : d.phase === 'installing' ? 'Installing safely' : d.phase === 'admitting' ? 'Almost there' : 'Downloading';
        text('runtime-progress-text', phase); announce('runtime-live-polite', phase);
        var bar = $('runtime-setup-progress'), fill = bar && bar.querySelector('.lp-fill');
        if (fill && percent !== null) { fill.style.transform = 'scaleX(' + (percent / 100) + ')'; bar.setAttribute('aria-valuenow', String(Math.round(percent))); }
        return;
      }
      if (kind === 'retrying') { text('runtime-progress-text', 'Connection interrupted — retrying…'); return; }
      if (kind === 'cancel_requested') { if (view.cancelPending) { $('btn-runtime-cancel').disabled = true; text('btn-runtime-cancel', 'Finishing a safe step…'); } return; }
      if (kind === 'activated') { text('runtime-progress-text', 'Almost there'); return; }
      if (kind === 'admitted') { syncDemoAdmission(view); ready(); return; }
      if (kind === 'cancelled') { render(); return; }
      if (kind === 'offline' || (kind === 'failed' && d.classification === 'offline')) { announce('runtime-live-assertive', 'An internet connection is needed to repair LecturePack.'); render(); return; }
      if (kind === 'failed') { announce('runtime-live-assertive', 'Repair could not be completed.'); text('runtime-failure-reason', "We couldn't verify the repair download. Your previous runtime is still in place."); render(); }
    }
    function wire() {
      $('btn-runtime-repair').addEventListener('click', beginOffer);
      $('btn-runtime-confirm').addEventListener('click', confirm);
      $('btn-runtime-back').addEventListener('click', function () { var view = eventModel.snapshot(); if (view.activeOperation && !view.terminal) lpBridge.cancelRuntimeRepair(view.activeOperation); eventModel.abandon(); render(); });
      $('btn-runtime-retry').addEventListener('click', retryAssessment);
      $('btn-runtime-offline-retry').addEventListener('click', beginNewRepair);
      $('btn-runtime-failed-retry').addEventListener('click', beginNewRepair);
      $('btn-runtime-cancel').addEventListener('click', cancel);
      $('btn-runtime-done').addEventListener('click', acknowledge);
      Array.prototype.forEach.call(document.querySelectorAll('[data-runtime-diagnostics]'), function (button) { button.addEventListener('click', function () { diagnostics(button); }); });
      $('btn-runtime-diagnostics-back').addEventListener('click', back);
      function diagnosticFeedback(promise, ok, bad) { promise.then(function (json) { var r; try { r = JSON.parse(json); } catch (e) {} announce('runtime-live-polite', r && /copied|saved/.test(r.type || '') ? ok : bad); }, function () { announce('runtime-live-polite', bad); }); }
      function diagnosticText() { return ($('runtime-diagnostics-report') && $('runtime-diagnostics-report').textContent) || 'No runtime diagnostics are available.'; }
      function copyDiagnostics() {
        if (!navigator.clipboard || !navigator.clipboard.writeText) return Promise.reject(new Error('clipboard unavailable'));
        return navigator.clipboard.writeText(diagnosticText()).then(function () { return JSON.stringify({ type: 'copied' }); });
      }
      function saveDiagnostics(filename) {
        var blob = new Blob([diagnosticText()], { type: 'text/plain;charset=utf-8' });
        var url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url; link.download = filename || 'runtime-repair-report.txt';
        document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
        return Promise.resolve(JSON.stringify({ type: 'saved' }));
      }
      $('btn-runtime-copy').addEventListener('click', function () { diagnosticFeedback(copyDiagnostics(), 'Details copied.', 'Could not copy details.'); });
      $('btn-runtime-save').addEventListener('click', function () { diagnosticFeedback(saveDiagnostics('runtime-repair-report.txt'), 'Report saved.', 'Could not save report.'); });
      $('btn-startup-retry').addEventListener('click', retryStartup);
      $('btn-startup-copy').addEventListener('click', function () { copyText(($('startup-failure-technical') && $('startup-failure-technical').textContent) || 'No startup diagnostics are available.', 'Diagnostics copied'); });
      $('btn-startup-open-logs').addEventListener('click', function () { lpBridge.call('open_logs'); });
      document.addEventListener('keydown', function (e) { if (!isBlocking()) return; if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); return; } if (e.key === 'Tab' && isOpen()) { trapFocus(overlay(), e); e.stopImmediatePropagation(); return; } e.stopImmediatePropagation(); }, true);
      document.addEventListener('wheel', function (e) { if (isBlocking() && (!isOpen() || !overlay().contains(e.target))) { e.preventDefault(); e.stopImmediatePropagation(); } }, { capture: true, passive: false });
      document.addEventListener('pointerdown', function (e) { if (isBlocking() && (!isOpen() || !overlay().contains(e.target))) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
    }
    return { admit: admit, event: event, progress: progress, startupFailed: startupFailed, acknowledge: acknowledge, wire: wire, beginBootstrap: function () {
      setUnderlyingInert(true);
      // A hidden overlay must never report the invalid `gate` state while the
      // first authoritative health response is still in flight. Start in the
      // existing checking state; render() keeps the short grace period and
      // opens the honest progress panel if the response is slow.
      eventModel.bootstrap({ bootstrap_pending: true, validation_path: 'full' });
      render(true);
    }, isOpen: isOpen, state: function () { return eventModel.snapshot().state; }, _diagnosticsInvoker: null };
  })();

  /* Clears the design-time placeholder chrome shipped in index.html so a fresh
     profile never shows a fake in-progress job (BUG-04). */
  function resetJobChrome() {
    $('side-job-name').textContent = 'No lecture loaded';
    $('side-job-status').innerHTML = 'Idle';
    $('crumb-job').textContent = 'Home';
    $('proc-source-name').textContent = 'No lecture loaded';
    $('proc-status-meta').textContent = '';
    // BUG-15: these ship with the demo lecture's real numbers baked in
    // (1920x1080 · 06:12 · H.264, a 00:00/03:06/06:12 timeline axis), so with
    // no lecture loaded the Review timeline still advertised a 6-minute
    // lecture that does not exist. Blank them with everything else.
    ['proc-source-meta', 'transcript-duration',
     'timeline-start', 'timeline-mid', 'timeline-end'].forEach(function (id) {
      var el = $(id);
      if (el) el.textContent = '';
    });
    $('status-state').textContent = 'Idle';
    $('status-detail').textContent = '';
    $('status-right').textContent = runtimeBackendLabel;
    setFill('status-bar', 0);
    renderSidePoster('');
    var w = $('storage-widget');
    if (w) w.hidden = true;
  }

  // ------------------------------------------------------------------ //
  // Study V2: grounded concepts, mastery, flashcards, quiz, quick study
  // ------------------------------------------------------------------ //
  // 'all' first: indexOf(...) > 0 is the "is a real difficulty" test.
  var QUIZ_DIFFICULTIES = ['all', 'easy', 'medium', 'hard'];
  var QUIZ_LENGTHS = ['all', '5', '10', '20'];
  var studyV2 = {
    content: null,
    progress: null,
    summary: null,
    mode: 'overview',
    flashIndex: 0,
    flashRevealed: false,
    flashResults: { got: 0, missed: 0, missedIds: [] },
    quizIndex: 0,
    quizAnswers: [],
    quizPicks: {},
    quizCorrect: 0,
    quizAsked: [],
    quizGrades: {},
    // How the student wants THIS run shaped. Applied locally to the generated
    // pack: no AI request, works offline, and takes effect instantly.
    quizDifficulty: 'all',
    quizLength: 'all',
    flashDifficulty: 'all',
    quickSession: null,
    quickIndex: 0,
    quickCorrect: 0,
    quickTotal: 0,
    quickMissed: [],
    quickRevealed: false,
    quickAnswered: false,
    quickSelected: null,
    quickSummary: null,
    reviewOnly: false,
    flashFilterIds: null,
    askStreaming: false,
    askAnswer: null,
    quickMinutes: '5',
    teachConceptId: '',
    teachResult: null,
    teachLoading: false,
    teachGrade: null,
    quizGrading: false,
    quizGradingQuestionId: '',
    loadError: '',
    viewJobId: '',
    restoredView: false,
    resumeMode: 'flashcards',
    restoredQuickActive: false,
    // --- Group Scope State ---
    scope: {
      type: 'lecture', // 'lecture' | 'group'
      groupName: '',
      selectedJobId: 'all', // 'all' | '<job_id>'
      groupAnalysis: null,
      members: [],
      loading: false,
      status: 'idle', // 'idle' | 'preparing' | 'ready' | 'failed'
      stage: '',
      error: '',
      reason: ''
    }
  };

  function studyGroupSlug(name) {
    var s = String(name || '').trim().toLowerCase();
    var h = 0;
    for (var i = 0; i < s.length; i++) {
      h = ((h << 5) - h) + s.charCodeAt(i);
      h |= 0;
    }
    return 'g_' + Math.abs(h).toString(16);
  }

  function studyGroupStorageKey(groupName) {
    return groupName ? 'lecturepack.study.v2.group.' + studyGroupSlug(groupName) : '';
  }

  function studyV2PersistGroupView() {
    var groupName = studyV2.scope && studyV2.scope.groupName;
    var key = studyGroupStorageKey(groupName);
    if (!key || !localStorage) return;
    try {
      localStorage.setItem(key, JSON.stringify({
        selectedJobId: studyV2.scope.selectedJobId,
        lastMode: studyV2.mode,
        resumeMode: studyV2.resumeMode,
        quizDifficulty: studyV2.quizDifficulty,
        flashDifficulty: studyV2.flashDifficulty
      }));
    } catch (e) {}
  }

  function studyV2RestoreGroupView(groupName) {
    var key = studyGroupStorageKey(groupName);
    if (!key || !localStorage) return false;
    try {
      var saved = JSON.parse(localStorage.getItem(key) || 'null');
      if (!saved || typeof saved !== 'object') return false;
      if (saved.selectedJobId) studyV2.scope.selectedJobId = saved.selectedJobId;
      if (['overview', 'flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(saved.lastMode) >= 0) {
        studyV2.mode = saved.lastMode;
      }
      return true;
    } catch (e) { return false; }
  }

  function getJobReadiness(job) {
    if (!job) return { status: 'queued', label: 'Queued', icon: '⏸', ready: false };
    if (job.status === 'running') {
      return { status: 'processing', label: 'Processing ' + (job.progress || job.pct || 0) + '%', icon: '⏳', ready: false };
    }
    if (job.status === 'queued') {
      return { status: 'queued', label: 'Queued', icon: '⏸', ready: false };
    }
    if (job.status === 'failed' || job.status === 'interrupted') {
      return { status: 'failed', label: 'Needs Attention', icon: '⚠', ready: false };
    }
    if (job.study_status === 'preparing') {
      return { status: 'preparing', label: 'Preparing Study', icon: '⏳', ready: false };
    }
    if (job.study_status === 'failed') {
      return { status: 'failed', label: 'Needs Attention', icon: '⚠', ready: false };
    }
    if (job.study_status === 'basic') {
      return { status: 'basic', label: 'Basic', icon: '✓', ready: true };
    }
    if (job.study_status === 'ready' || job.status === 'done') {
      return { status: 'ready', label: 'Ready', icon: '✓', ready: true };
    }
    return { status: 'ready', label: 'Ready', icon: '✓', ready: true };
  }

  function openGroupStudy(groupName, opts) {
    opts = opts || {};
    groupName = String(groupName || '').trim();
    if (!groupName) return;
    studyV2.scope.type = 'group';
    studyV2.scope.groupName = groupName;
    studyV2.scope.selectedJobId = opts.jobId || 'all';
    studyV2RestoreGroupView(groupName);
    setScreen('study');
    studyV2GroupLoad(groupName, opts);
  }

  function studyV2GroupLoad(groupName, opts) {
    opts = opts || {};
    if (!lpBridge.connected()) return;
    groupName = String(groupName || (studyV2.scope && studyV2.scope.groupName) || '').trim();
    if (!groupName) return;

    studyV2.scope.type = 'group';
    studyV2.scope.groupName = groupName;
    studyV2.scope.loading = true;
    studyV2.scope.status = 'preparing';
    studyV2.scope.stage = 'Collecting member lectures';
    studyV2.scope.error = '';
    studyV2.scope.reason = '';

    renderStudyScopeHeader();
    renderStudyGenerationState();

    lpBridge.call('study_v2_group_prepare', { group: groupName, force: !!opts.force })
      .then(function (res) {
        if (!res) return;
        if (studyV2.scope.groupName.toLowerCase() !== groupName.toLowerCase()) return;
        studyV2.scope.loading = false;
        if (res.ok) {
          studyV2.scope.status = 'ready';
          studyV2.scope.groupAnalysis = res.analysis || null;
          studyV2.scope.members = Array.isArray(res.members) ? res.members : [];
          studyV2.scope.reason = '';
          studyV2.scope.error = '';

          if (studyV2.scope.selectedJobId === 'all') {
            studyV2.content = buildGroupStudyContent(studyV2.scope.groupAnalysis, studyV2.scope.members);
            // Mastery is WRITTEN to the owning lecture, so it must also be READ
            // from there. Without this, progress was whatever single lecture
            // was loaded last, keyed by a different id space -- so a concept
            // set to Mastered snapped back to New and the subject bar sat at 0%.
            studyV2.progress = buildGroupStudyProgress(studyV2.content, studyV2.scope.members);
            studyV2.summary = buildGroupStudySummary(studyV2.content, studyV2.scope.members);
          }
        } else {
          studyV2.scope.status = 'failed';
          studyV2.scope.reason = res.reason || 'prepare_failed';
          studyV2.scope.error = res.error || (res.reason === 'no_ready_lectures' ? 'No ready lectures in this subject yet.' : 'Group study could not be prepared.');
          studyV2.scope.members = Array.isArray(res.members) ? res.members : [];
        }
        renderStudyScopeHeader();
        renderStudyGenerationState();
        if (studyV2.scope.status === 'ready' && studyV2.scope.selectedJobId === 'all') {
          renderStudyV2Overview();
        }
      })
      .catch(function (err) {
        if (studyV2.scope.groupName.toLowerCase() !== groupName.toLowerCase()) return;
        studyV2.scope.loading = false;
        studyV2.scope.status = 'failed';
        studyV2.scope.reason = 'prepare_failed';
        studyV2.scope.error = 'Group Study could not be prepared: ' + (err && err.message ? err.message : String(err));
        renderStudyScopeHeader();
        renderStudyGenerationState();
      });
  }

  /* Re-key each owning lecture's stored progress onto the SYNTHESIZED group
     concept ids the subject view renders with, so the read side matches the
     write side (which targets origin_job_id/origin_concept_id). Flashcards and
     quizzes are not merged into group content, so their progress stays empty
     here rather than leaking the last single lecture's results. */
  function buildGroupStudyProgress(content, members) {
    var byJob = {};
    (members || []).forEach(function (m) {
      var p = (m && m.progress) || {};
      byJob[m.job_id] = (p && p.concepts) || {};
    });
    var concepts = {};
    ((content && content.concepts) || []).forEach(function (c) {
      if (!c.origin_job_id || !c.origin_concept_id) return;
      var entry = byJob[c.origin_job_id] && byJob[c.origin_job_id][c.origin_concept_id];
      if (entry) concepts[c.id] = entry;
    });
    return { concepts: concepts, flashcard_results: {}, quiz_attempts: [] };
  }

  function buildGroupStudyContent(analysis, members) {
    analysis = analysis || {};
    members = members || [];
    var memberMap = {};
    members.forEach(function (m) { memberMap[m.job_id] = m; });

    function sameTitle(a, b) {
      return !!a && !!b && String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
    }

    var concepts = (analysis.concepts || []).map(function (c) {
      var sources = [];
      // A group concept is a SYNTHESIZED merge of per-lecture concepts, so its
      // id exists in no single lecture's store. Remember the real owning
      // lecture + concept so per-concept actions (mastery, Teach Me, edit,
      // delete, regenerate) address the row the backend actually has.
      //
      // Identity is resolved by TITLE ONLY, never by source_concept_ids.
      // That field is model-generated, and on real subjects the model returns
      // the SIBLING concept ids instead of the ones the concept was built from
      // (observed 2026-08-15: "Homeric Troy" listed concept_1/concept_3, the
      // other two concepts). Trusting it made every concept resolve to
      // concept_1 -- which would have written mastery to the WRONG concept, a
      // worse failure than the "concept not found" error it replaced. If no
      // title matches we leave the origin empty and the caller falls back to
      // the displayed id, which fails loudly instead of corrupting a row.
      var originJobId = '';
      var originConceptId = '';
      (c.job_ids || []).forEach(function (jid) {
        var member = memberMap[jid];
        if (!member) return;
        (member.concepts || []).forEach(function (mc) {
          // Provenance may still use the looser match: a wrong citation is a
          // display flaw, whereas a wrong id is a data-integrity flaw.
          var titleHit = sameTitle(mc.title, c.title);
          var looseHit = titleHit || (c.source_concept_ids || []).indexOf(mc.id) >= 0;
          if (titleHit && !originJobId) { originJobId = jid; originConceptId = mc.id; }
          if (!looseHit) return;
          (mc.lecture_sources || mc.sources || []).forEach(function (s) {
            sources.push({
              job_id: jid,
              lecture_title: member.title,
              segment_id: s.segment_id,
              start_ms: s.start_ms,
              slide_id: s.slide_id
            });
          });
        });
      });
      return {
        id: c.id,
        title: c.title,
        explanation: c.explanation,
        importance: c.importance,
        coverage: c.coverage,
        job_ids: c.job_ids || [],
        origin_job_id: originJobId,
        origin_concept_id: originConceptId,
        sources: sources,
        lecture_sources: sources
      };
    });

    var studyGuide = [];
    (analysis.through_lines || []).forEach(function (tl) {
      studyGuide.push({
        heading: 'Through-line: ' + tl.title,
        body: tl.body,
        job_ids: tl.job_ids || [],
        concept_ids: tl.concept_ids || []
      });
    });
    (analysis.gaps || []).forEach(function (gap) {
      studyGuide.push({
        heading: 'Knowledge Gap: ' + gap.title,
        body: gap.body,
        concept_ids: gap.concept_ids || []
      });
    });

    return {
      study_status: 'ready',
      lecture_summary: analysis.group_summary || '',
      study_guide: studyGuide,
      concepts: concepts,
      flashcards: [],
      quiz: [],
      relationships: analysis.relationships || []
    };
  }

  function buildGroupStudySummary(content, members) {
    content = content || { concepts: [] };
    var totalConcepts = (content.concepts || []).length;
    var mastered = 0, learning = 0, needsReview = 0;
    (content.concepts || []).forEach(function (c) {
      var m = conceptMastery(c.id);
      if (m === 'MASTERED') mastered++;
      else if (m === 'LEARNING') learning++;
      else if (m === 'NEEDS_REVIEW') needsReview++;
    });
    var pct = totalConcepts ? Math.round((mastered / totalConcepts) * 100) : 0;
    return {
      progress_percent: pct,
      mastered: mastered,
      learning: learning,
      needs_review: needsReview,
      cards_completed: 0,
      quiz_correct: 0
    };
  }

  function renderStudyScopeHeader() {
    var header = $('study-scope-header');
    var progBanner = $('study-group-progressive-banner');
    var emptyPanel = $('study-group-empty-panel');
    if (!header) return;

    var isGroup = studyV2.scope && studyV2.scope.type === 'group' && !!studyV2.scope.groupName;
    header.hidden = !isGroup;
    if (!isGroup) {
      if (progBanner) progBanner.hidden = true;
      if (emptyPanel) emptyPanel.hidden = true;
      return;
    }

    var groupName = studyV2.scope.groupName;
    var badge = $('study-scope-subject-badge');
    var title = $('study-scope-title');
    var summary = $('study-scope-summary');
    if (badge) badge.textContent = groupName;

    var groupJobs = ((typeof LP !== 'undefined' && LP.data && LP.data.jobs) || []).filter(function (j) {
      return (jobGroup(j) || '').trim().toLowerCase() === groupName.toLowerCase();
    });

    var readyJobs = groupJobs.filter(function (j) { return getJobReadiness(j).ready; });
    var procJobs = groupJobs.filter(function (j) { return getJobReadiness(j).status === 'processing'; });

    if (title) {
      if (studyV2.scope.selectedJobId === 'all') {
        // The badge immediately to the left already names the subject, and the
        // page heading names it again below. Say what the scope IS here rather
        // than printing the subject name three times in one header.
        title.textContent = 'Subject overview';
      } else {
        var curJob = _jobById(studyV2.scope.selectedJobId);
        title.textContent = curJob ? (curJob.name || curJob.title || curJob.filename || 'Lecture') : 'Lecture View';
      }
    }

    if (summary) {
      var total = groupJobs.length;
      var readyCount = readyJobs.length;
      var procCount = procJobs.length;
      summary.textContent = total + (total === 1 ? ' lecture' : ' lectures') + ' · ' +
        readyCount + ' ready' + (procCount ? ', ' + procCount + ' processing' : '');
    }

    // Populate In-Study Lecture Switcher
    var select = $('study-scope-lecture-select');
    if (select) {
      var optionsHtml = '<option value="all"' + (studyV2.scope.selectedJobId === 'all' ? ' selected' : '') + '>All lectures in this subject</option>';
      groupJobs.forEach(function (job) {
        var r = getJobReadiness(job);
        var jobTitle = job.name || job.title || job.filename || 'Lecture';
        var disabled = !r.ready ? ' disabled' : '';
        var selected = studyV2.scope.selectedJobId === job.id ? ' selected' : '';
        optionsHtml += '<option value="' + esc(job.id) + '"' + disabled + selected + '>' +
          r.icon + ' ' + esc(jobTitle) + ' (' + r.label + ')' + '</option>';
      });
      select.innerHTML = optionsHtml;
    }

    // Progressive Unlocking Banner
    if (progBanner) {
      var showProg = readyJobs.length > 0 && readyJobs.length < groupJobs.length;
      progBanner.hidden = !showProg;
      if (showProg) {
        var cnt = $('study-progressive-count');
        var subj = $('study-progressive-subject');
        if (cnt) cnt.textContent = readyJobs.length + ' of ' + groupJobs.length + ' lectures ready';
        if (subj) subj.textContent = groupName;
      }
    }

    // Empty / Failure Panel
    if (emptyPanel) {
      var isEmpty = studyV2.scope.status === 'failed' && studyV2.scope.reason === 'no_ready_lectures';
      var isFailed = studyV2.scope.status === 'failed' && studyV2.scope.reason !== 'no_ready_lectures';
      emptyPanel.hidden = !(isEmpty || isFailed);
      if (isEmpty) {
        var emptyTitle = $('study-group-empty-title');
        var emptyDetail = $('study-group-empty-detail');
        if (emptyTitle) emptyTitle.textContent = 'No ready lectures in ' + groupName + ' yet';
        if (emptyDetail) emptyDetail.textContent = 'None of the lectures in this subject have finished processing. Once at least one lecture is ready, group study materials will be generated automatically.';
      } else if (isFailed) {
        var emptyTitle = $('study-group-empty-title');
        var emptyDetail = $('study-group-empty-detail');
        if (emptyTitle) emptyTitle.textContent = 'Group Study could not be prepared';
        if (emptyDetail) emptyDetail.textContent = studyV2.scope.error || 'The AI Gateway was unable to synthesize cross-lecture material for this subject.';
      }
    }
  }

  function bindStudyScopeControls() {
    var select = $('study-scope-lecture-select');
    if (select) {
      select.addEventListener('change', function () {
        var val = select.value;
        if (val === 'all') {
          studyV2.scope.selectedJobId = 'all';
          studyV2PersistGroupView();
          if (studyV2.scope.groupAnalysis) {
            studyV2.content = buildGroupStudyContent(studyV2.scope.groupAnalysis, studyV2.scope.members);
            studyV2.summary = buildGroupStudySummary(studyV2.content, studyV2.scope.members);
            renderStudyScopeHeader();
            renderStudyGenerationState();
            renderStudyV2Overview();
          } else {
            studyV2GroupLoad(studyV2.scope.groupName);
          }
        } else {
          studyV2.scope.selectedJobId = val;
          studyV2PersistGroupView();
          selectJob(val, { screen: 'study' });
          renderStudyScopeHeader();
          // selectJob clears the group content immediately but only reloads
          // when it happens to observe a study->study transition. Ask for the
          // single-lecture pack explicitly so the panel never lands empty.
          studyV2Load();
        }
      });
    }

    var btnRebuild = $('btn-study-rebuild-map');
    if (btnRebuild) {
      btnRebuild.addEventListener('click', function () {
        if (studyV2.scope && studyV2.scope.groupName) {
          toast('Rebuilding cross-lecture map…');
          studyV2GroupLoad(studyV2.scope.groupName, { force: true });
        }
      });
    }

    var btnManage = $('btn-study-manage-subject');
    if (btnManage) {
      btnManage.addEventListener('click', function () {
        setScreen('subjects');
      });
    }

    var btnEmptyProc = $('btn-study-empty-process');
    if (btnEmptyProc) {
      btnEmptyProc.addEventListener('click', function () {
        setScreen('process');
      });
    }

    var btnEmptyHome = $('btn-study-empty-home');
    if (btnEmptyHome) {
      btnEmptyHome.addEventListener('click', function () {
        setScreen('home');
      });
    }
  }

  function studyV2StorageKey() {
    var jobId = typeof LP !== 'undefined' && LP.state && LP.state.jobId;
    return jobId ? 'lecturepack.study.v2.view.' + jobId : '';
  }

  function studyV2PersistView() {
    var key = studyV2StorageKey();
    if (!key || !localStorage) return;
    try {
      localStorage.setItem(key, JSON.stringify({
        lastMode: studyV2.mode,
        resumeMode: studyV2.resumeMode,
        flashIndex: studyV2.flashIndex,
        flashGot: studyV2.flashResults.got,
        flashMissed: studyV2.flashResults.missed,
        flashMissedIds: studyV2.flashResults.missedIds,
        quizIndex: studyV2.quizIndex,
        quizCorrect: studyV2.quizCorrect,
        quizAnswers: studyV2.quizAnswers,
        quizPicks: studyV2.quizPicks,
        quizGrades: studyV2.quizGrades,
        quizDifficulty: studyV2.quizDifficulty,
        quizLength: studyV2.quizLength,
        flashDifficulty: studyV2.flashDifficulty,
        quickIndex: studyV2.quickIndex,
        quickCorrect: studyV2.quickCorrect,
        quickTotal: studyV2.quickTotal,
        quickMissed: studyV2.quickMissed,
        quickActive: !!studyV2.quickSession,
        quickSummary: studyV2.quickSummary,
        quickMinutes: studyV2.quickMinutes,
        teachConceptId: studyV2.teachConceptId,
        reviewOnly: !!studyV2.reviewOnly
      }));
    } catch (e) { /* browser storage is a convenience, not a dependency */ }
  }

  function studyV2RestoreView() {
    var key = studyV2StorageKey();
    if (!key || !localStorage) return false;
    try {
      var saved = JSON.parse(localStorage.getItem(key) || 'null');
      if (!saved || typeof saved !== 'object') return false;
      if (['overview', 'flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(saved.lastMode) >= 0) studyV2.mode = saved.lastMode;
      if (['flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(saved.resumeMode) >= 0) studyV2.resumeMode = saved.resumeMode;
      else if (['flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(saved.lastMode) >= 0) studyV2.resumeMode = saved.lastMode;
      studyV2.flashIndex = Math.max(0, Number(saved.flashIndex) || 0);
      studyV2.flashResults = {
        got: Math.max(0, Number(saved.flashGot) || 0),
        missed: Math.max(0, Number(saved.flashMissed) || 0),
        missedIds: Array.isArray(saved.flashMissedIds) ? saved.flashMissedIds : []
      };
      studyV2.quizIndex = Math.max(0, Number(saved.quizIndex) || 0);
      studyV2.quizCorrect = Math.max(0, Number(saved.quizCorrect) || 0);
      studyV2.quizAnswers = Array.isArray(saved.quizAnswers) ? saved.quizAnswers : [];
      studyV2.quizPicks = saved.quizPicks && typeof saved.quizPicks === 'object' ? saved.quizPicks : {};
      studyV2.quizGrades = saved.quizGrades && typeof saved.quizGrades === 'object' ? saved.quizGrades : {};
      studyV2.quizDifficulty = QUIZ_DIFFICULTIES.indexOf(String(saved.quizDifficulty)) >= 0 ? String(saved.quizDifficulty) : 'all';
      studyV2.quizLength = QUIZ_LENGTHS.indexOf(String(saved.quizLength)) >= 0 ? String(saved.quizLength) : 'all';
      studyV2.flashDifficulty = QUIZ_DIFFICULTIES.indexOf(String(saved.flashDifficulty)) >= 0 ? String(saved.flashDifficulty) : 'all';
      studyV2.quickIndex = Math.max(0, Number(saved.quickIndex) || 0);
      studyV2.quickCorrect = Math.max(0, Number(saved.quickCorrect) || 0);
      studyV2.quickTotal = Math.max(0, Number(saved.quickTotal) || 0);
      studyV2.quickMissed = Array.isArray(saved.quickMissed) ? saved.quickMissed : [];
      studyV2.quickSummary = saved.quickSummary || null;
      studyV2.quickMinutes = ['5', '10', '20', 'full'].indexOf(String(saved.quickMinutes)) >= 0 ? String(saved.quickMinutes) : '5';
      studyV2.teachConceptId = String(saved.teachConceptId || '');
      studyV2.reviewOnly = !!saved.reviewOnly;
      studyV2.restoredQuickActive = !!saved.quickActive;
      return true;
    } catch (e) { /* ignore malformed local view state */ }
    return false;
  }

  function fmtTime(ms) {
    if (ms == null) return '';
    var s = Math.max(0, Math.round(Number(ms) / 1000));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    if (h) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
    return m + ':' + String(sec).padStart(2, '0');
  }

  function escText(v) {
    return esc(v);
  }

  function studyV2Load() {
    if (studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all' && studyV2.scope.groupName) {
      renderStudyScopeHeader();
      studyV2GroupLoad(studyV2.scope.groupName);
      return;
    }
    if (!lpBridge.connected()) return;
    var requestedJobId = LP.state.jobId || '';
    if (!requestedJobId) return;
    lpBridge.call('study_v2_status', { job_id: requestedJobId }).then(function (res) {
      if (studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all') return;
      if (!res || !res.content) return;
      // A response for the lecture that was viewed when the request started
      // must never repaint a different lecture selected while it was in flight.
      if (LP.state.jobId !== requestedJobId || (res.job_id && res.job_id !== requestedJobId)) return;
      var restoreMode = false;
      if (studyV2.viewJobId !== (LP.state.jobId || '')) {
        studyV2.viewJobId = LP.state.jobId || '';
        restoreMode = studyV2RestoreView();
        studyV2.restoredView = true;
      }
      studyV2.content = res.content;
      studyV2.progress = res.progress || { concepts: {}, flashcard_results: {}, quiz_attempts: [] };
      studyV2.summary = res.summary || {};
      studyV2.loadError = '';
      if (studyV2.quickSession == null && studyV2.progress.quick_study &&
          studyV2.progress.quick_study.items && studyV2.progress.quick_study.items.length &&
          (studyV2.quickIndex > 0 || studyV2.restoredQuickActive)) {
        studyV2.quickSession = studyV2.progress.quick_study;
      }
      studyV2.restoredQuickActive = false;
      renderStudyScopeHeader();
      renderStudyGenerationState();
      renderStudyV2Overview();
      if (restoreMode && studyV2.mode !== 'overview') {
        setStudyV2Mode(studyV2.mode, !!studyV2.quickSession);
      } else if (studyV2.mode === 'flashcards' && studyV2.quickSession) renderQuickStudy();
      else if (studyV2.mode === 'flashcards') renderStudyFlashcards();
      else if (studyV2.mode === 'quiz') renderStudyQuiz();
      else if (studyV2.mode === 'quick') renderQuickStudy();
      else if (studyV2.mode === 'teach') renderStudyTeach();
    }).catch(function () {
      if (LP.state.jobId !== requestedJobId) return;
      studyV2.loadError = 'Study data could not be loaded. Retry, or use Basic Study.';
      renderStudyScopeHeader();
      renderStudyGenerationState();
    });
  }

  /* ---- AI Study preparation: surface the stages the backend already sends ----
     ai_study_service.py emits seven named stages with real percentages. The
     old panel put the current stage in a small title, showed one bar, and
     discarded the rest -- so a run that was working fine read as frozen. This
     renders the whole sequence, marking each stage complete as the run passes
     it, plus an elapsed clock. Nothing here is invented reassurance: every
     value shown comes from the backend or from the wall clock.

     Static only, per AD-20: the only things that move are TEXT and step-wise
     fill widths. No keyframes, no transitions, no will-change. */
  var STUDY_PREP_STAGES = [
    /* The sidecar emits this BEFORE the worker starts. It was missing from
       this list, so during the queued phase nothing matched and every row
       rendered idle -- which reads exactly like "stuck at 0%". */
    {match: /queued for study ai/i,             label: 'Queued for Study AI',         note: 'Waiting for a slot'},
    {match: /preparing lecture evidence/i,      label: 'Gathering your lecture',      note: 'Collecting transcript and slide text'},
    {match: /understanding the lecture/i,       label: 'Reading the transcript',      note: 'The longest step on a long lecture'},
    {match: /connecting lecture sections/i,     label: 'Connecting the sections',     note: 'Linking related ideas across the lecture'},
    {match: /reading selected lecture slides/i, label: 'Reading your slides',         note: 'Looking at the slides that carry the most meaning'},
    {match: /checking optional public context/i,label: 'Checking public sources',     note: 'Optional', net: true},
    {match: /building the study system/i,       label: 'Building your study material',note: 'Study guide, flashcards and quiz'},
    {match: /validating sources and saving/i,   label: 'Checking sources and saving', note: 'Making sure every claim traces to your lecture'}
  ];
  var studyPrepStartedAt = 0, studyPrepTimer = null, studyPrepLastStage = '';

  function studyPrepIndex(stage) {
    var text = String(stage || '');
    for (var i = 0; i < STUDY_PREP_STAGES.length; i++) {
      if (STUDY_PREP_STAGES[i].match.test(text)) return i;
    }
    return -1;
  }

  function studyPrepStage(stage) {
    var index = studyPrepIndex(stage);
    return index >= 0 ? STUDY_PREP_STAGES[index] : null;
  }

  function formatElapsed(ms) {
    var total = Math.max(0, Math.round(ms / 1000));
    var mins = Math.floor(total / 60), secs = total % 60;
    return mins + ':' + (secs < 10 ? '0' : '') + secs + ' elapsed';
  }

  function renderStudyPrepElapsed() {
    var el = $('study-prep-elapsed');
    if (!el || !studyPrepStartedAt) return;
    el.textContent = formatElapsed(Date.now() - studyPrepStartedAt);
  }

  function stopStudyPrepClock() {
    if (studyPrepTimer) { clearInterval(studyPrepTimer); studyPrepTimer = null; }
    studyPrepStartedAt = 0;
    studyPrepLastStage = '';
  }

  function renderStudyPrepStages(metadata) {
    var host = $('study-prep-stages'), meta = $('study-prep-meta'), inputs = $('study-prep-inputs');
    if (!host) return;
    var stage = metadata.stage || '';
    var pct = Math.max(0, Math.min(99, Number(metadata.progress_percent) || 0));
    var active = studyPrepIndex(stage);

    // `study_status: preparing` exists as soon as a lecture is imported. It
    // does NOT prove that Study AI has started: while the local transcript and
    // slides are still being built, generation_metadata.stage is deliberately
    // empty. Rendering the full AI checklist at 0% in that state made healthy
    // lecture processing look like a two-minute AI hang. Show the dependency,
    // not eight idle tasks, and do not start the Study wait clock early.
    if (!stage) {
      stopStudyPrepClock();
      var waitingForLecture = LP.state.pipelineRunning === true;
      host.innerHTML = '<div class="lp-prep-stage" data-state="waiting">' +
        '<span class="lp-prep-marker"></span>' +
        '<span class="lp-prep-text"><span class="lp-prep-label">' +
        (waitingForLecture ? 'Waiting for lecture processing to finish' : 'Starting Study AI') +
        '</span><span class="lp-prep-note">' +
        (waitingForLecture ? 'Study starts after the transcript and slides are ready' : 'Joining the Study AI queue') +
        '</span></span></div>';
      host.hidden = false;
      if (meta) meta.hidden = true;
      if (inputs) { inputs.textContent = ''; inputs.hidden = true; }
      return;
    }

    // The clock starts with the panel, not with each stage: it measures how
    // long the student has been waiting for Study AI, not time spent in the
    // prerequisite local lecture pipeline.
    if (!studyPrepStartedAt) {
      studyPrepStartedAt = Date.now();
      if (studyPrepTimer) clearInterval(studyPrepTimer);
      studyPrepTimer = setInterval(renderStudyPrepElapsed, 1000);
    }
    studyPrepLastStage = stage;

    var rows = STUDY_PREP_STAGES.map(function (s, i) {
      var state = active < 0 ? 'idle'
        : i < active ? 'complete'
        : i === active ? 'running' : 'idle';
      return '<div class="lp-prep-stage" data-state="' + state + '"' +
        (s.net ? ' data-net="true"' : '') + '>' +
        '<span class="lp-prep-marker"></span>' +
        '<span class="lp-prep-text"><span class="lp-prep-label">' + esc(s.label) + '</span>' +
        '<span class="lp-prep-note">' + esc(s.note) + '</span></span></div>';
    });
    // A stage name we do not recognise must still show as work in progress.
    // Rendering every row idle is indistinguishable from a hang, and a new
    // backend stage should never make a working run look broken.
    if (active < 0 && stage) {
      rows.unshift('<div class="lp-prep-stage" data-state="running">' +
        '<span class="lp-prep-marker"></span>' +
        '<span class="lp-prep-text"><span class="lp-prep-label">' + esc(stage) + '</span>' +
        '<span class="lp-prep-note">Working</span></span></div>');
    }
    host.innerHTML = rows.join('');
    host.hidden = false;

    if (meta) {
      meta.hidden = false;
      $('study-prep-pct').textContent = pct + '%';
      renderStudyPrepElapsed();
    }
    // What it is actually working from -- the question a privacy-minded
    // student is really asking while they wait.
    if (inputs) {
      var slides = (LP.data.slides || []).length;
      var segments = (LP.data.transcript || []).length;
      var parts = [];
      if (slides) parts.push(slides + (slides === 1 ? ' slide' : ' slides'));
      if (segments) parts.push(segments + ' transcript segment' + (segments === 1 ? '' : 's'));
      inputs.textContent = parts.length ? 'Working from ' + parts.join(' · ') : '';
      inputs.hidden = !parts.length;
    }
  }

  function hideStudyPrepStages() {
    stopStudyPrepClock();
    ['study-prep-stages', 'study-prep-meta', 'study-prep-inputs'].forEach(function (id) {
      var el = $(id);
      if (el) el.hidden = true;
    });
  }

  function renderStudyGenerationState() {
    var panel = $('study-generation-panel');
    if (!panel) return;
    var content = studyV2.content || {};
    var metadata = content.generation_metadata || {};
    var status = studyV2.loadError ? 'failed' : String(content.study_status || 'preparing');
    var usable = status === 'ready' || status === 'basic';
    var badge = $('study-generation-badge');
    var title = $('study-generation-title');
    var detail = $('study-generation-detail');
    var progressWrap = $('study-generation-progress-wrap');
    var progressBar = $('study-generation-progress-bar');
    var actions = $('study-generation-actions');
    var retry = $('btn-study-ai-retry');
    var copy = $('btn-study-copy-diagnostics');
    var basic = $('btn-study-use-basic');
    var readyBadge = $('study-ready-status-badge');
    panel.dataset.studyStatus = status;
    panel.hidden = status === 'ready';
    if (status === 'ready') hideStudyPrepStages();
    badge.textContent = status === 'failed' ? 'Needs attention' : status === 'basic' ? 'Basic' : 'Preparing';
    if (status === 'preparing') {
      var stage = String(metadata.stage || '');
      var stageInfo = studyPrepStage(stage);
      var waitingForLecture = !stage && LP.state.pipelineRunning === true;
      // The stage name is the headline: it is the thing that actually changes.
      // An empty stage is a dependency state, not 0% AI progress.
      title.textContent = stage
        ? (stageInfo ? stageInfo.label : stage)
        : (waitingForLecture ? 'Waiting for lecture processing' : 'Starting Study AI');
      detail.textContent = stage
        ? (stageInfo ? stageInfo.note : 'Working on your grounded study material')
        : (waitingForLecture
          ? 'Study AI starts automatically when the transcript and slides are ready.'
          : 'Your lecture is ready. Study AI is joining the queue.');
      progressWrap.hidden = !stage;
      progressBar.style.transform = 'scaleX(' + (Math.max(0, Math.min(99, Number(metadata.progress_percent) || 0)) / 100) + ')';
      renderStudyPrepStages(metadata);
      actions.hidden = true;
    } else if (status === 'failed') {
      var lastError = metadata.last_error || {};
      hideStudyPrepStages();
      title.textContent = 'Study AI needs attention';
      detail.textContent = studyV2.loadError || lastError.message || 'Study AI could not finish. Retry, or continue with Basic Study.';
      progressWrap.hidden = true;
      actions.hidden = false;
      retry.hidden = false;
      copy.hidden = false;
      basic.hidden = false;
    } else if (status === 'basic') {
      hideStudyPrepStages();
      title.textContent = 'Basic Study is active';
      detail.textContent = 'This lecture is using deterministic study material. Your sources and mastery still work.';
      progressWrap.hidden = true;
      actions.hidden = false;
      retry.hidden = false;
      copy.hidden = true;
      basic.hidden = true;
    }
    if (readyBadge) {
      readyBadge.hidden = status !== 'basic';
      readyBadge.textContent = 'Basic';
    }
    document.querySelectorAll('.study-mode-tab').forEach(function (button) {
      button.disabled = !usable && button.dataset.studyMode !== 'overview';
    });
    var readyPanel = $('study-ready-panel');
    var overviewContent = $('study-overview-content');
    if (readyPanel) readyPanel.hidden = !usable;
    if (overviewContent) overviewContent.hidden = !usable;
    if (!usable && studyV2.mode !== 'overview') setStudyV2Mode('overview');
  }

  function conceptMastery(cid) {
    var p = (studyV2.progress && studyV2.progress.concepts) || {};
    return (p[cid] && p[cid].mastery) || 'NEW';
  }

  function renderStudyV2Overview() {
    var content = studyV2.content || { concepts: [], flashcards: [], quiz: [] };
    var summary = studyV2.summary || {};
    var isGroup = studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all';
    var title;
    if (isGroup) {
      title = (studyV2.scope.groupName || 'Subject') + ' Subject Overview';
    } else {
      var studyJob = _jobById(LP.state.jobId) || LP.data.job || {};
      title = studyJob.title ||
        (studyJob.name && studyJob.name !== 'Lecture' ? studyJob.name : '') ||
        studyJob.filename || studyJob.source_name || studyJob.file || 'Lecture';
      title = String(title).replace(/\.[^.]+$/, '');
    }
    $('study-ready-title').textContent = title;
    $('study-ready-meta').textContent = (content.concepts || []).length + ' concepts · ' + (content.flashcards || []).length + ' cards · ' + (content.quiz || []).length + ' questions';
    var pct = summary.progress_percent || 0;
    $('study-progress-pct').textContent = pct + '%';
    $('study-progress-bar').style.transform = 'scaleX(' + (pct / 100) + ')';
    var needsReview = summary.needs_review || 0;
    // "0 concepts left to review" next to "0% progress" reads as finished when
    // nothing has been started. Only claim a remaining count once there is one.
    $('study-needs-review-line').textContent = needsReview
      ? needsReview + ' concepts left to review'
      : (pct ? 'No concepts left to review' : 'Start studying to build your review queue');

    var guideHtml = content.lecture_summary ?
      '<div class="study-guide-section"><h3>' + (isGroup ? 'Subject summary' : 'Lecture summary') + '</h3><p>' + escText(content.lecture_summary) + '</p></div>' : '';
    (content.study_guide || []).forEach(function (section) {
      guideHtml += '<div class="study-guide-section"><h3>' + escText(section.heading || 'Key idea') + '</h3><p>' + escText(section.body || '') + '</p>' +
        (studyItemSourcesHtml(section) ? '<div class="study-provenance-row" style="margin-top:9px">' + studyItemSourcesHtml(section) + '</div>' : '') + '</div>';
    });
    [['Key terms', content.key_terms], ['People', content.people], ['Dates', content.dates], ['Common misconceptions', content.misconceptions]].forEach(function (group) {
      if (!Array.isArray(group[1]) || !group[1].length) return;
      var rows = group[1].map(function (item) {
        return '<div style="padding:8px 0;border-top:1px solid var(--line)"><div style="font-weight:700;font-size:13px">' + escText(item.label || '') + '</div><div style="font-size:12px;line-height:1.5;color:var(--secondary-text)">' + escText(item.detail || '') + '</div>' +
          (studyItemSourcesHtml(item) ? '<div class="study-provenance-row" style="margin-top:6px">' + studyItemSourcesHtml(item) + '</div>' : '') + '</div>';
      }).join('');
      guideHtml += '<div class="study-guide-section"><h3>' + escText(group[0]) + '</h3>' + rows + '</div>';
    });
    $('study-guide-root').innerHTML = guideHtml || '<div style="font:500 12px JetBrains Mono;color:var(--muted)">The study guide will appear when lecture analysis is ready.</div>';

    // Key concepts
    var conceptsHtml = '';
    (content.concepts || []).forEach(function (c) {
      var mastery = conceptMastery(c.id);
      var masteryLabel = { NEW: 'New', LEARNING: 'Learning', MASTERED: 'Mastered', NEEDS_REVIEW: 'Needs review' }[mastery] || 'New';
      var sources = studyItemSourcesHtml(c);
      var emphasisBadge = c.emphasis ? '<span style="font:600 9px JetBrains Mono;color:var(--orange-ink);background:var(--orange-soft);border:1.5px solid var(--orange);border-radius:5px;padding:2px 6px;text-transform:uppercase">Emphasized</span>' : '';
      // In Subject scope the visible concept is a merge; address the owning
      // lecture's real row instead of whatever lecture is active in the switcher.
      var ownerAttrs = ' data-job-id="' + escText(c.origin_job_id || '') + '" data-origin-id="' + escText(c.origin_concept_id || '') + '"';
      // Bottom padding is set HERE, not in the stylesheet: this inline style
      // would override a .study-concept rule, which is how the citation pills
      // ended up sitting flush on the card's bottom border.
      conceptsHtml += '<div class="study-concept" style="background:var(--sunk);border:1.5px solid var(--line);border-radius:10px;padding:14px 16px 16px">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-weight:700;font-size:14px;flex:1">' + escText(c.title) + '</span>' + emphasisBadge + '<span style="font:600 10px JetBrains Mono;color:var(--muted)">' + masteryLabel + '</span></div>' +
        '<div style="font-size:13px;color:var(--secondary-text);line-height:1.55;margin-bottom:8px">' + escText(c.explanation) + '</div>' +
        (sources ? '<div class="study-provenance-row">' + sources + '</div>' : '') +
        // No ownerAttrs on Explain: it does not address a stored row, it asks
        // the Study chat about the concept. Carrying owner data it ignores
        // would read as intentional to the next reader.
        '<div style="display:flex;gap:6px;margin-top:8px"><button class="lp-hit study-explain" data-id="' + escText(c.id) + '" style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--ink)">Explain</button>' +
        '<button class="lp-hit study-edit" data-kind="concept" data-id="' + escText(c.id) + '"' + ownerAttrs + ' style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--muted)">Edit</button>' +
        '<button class="lp-hit study-regenerate" data-kind="concept" data-id="' + escText(c.id) + '"' + ownerAttrs + ' style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--muted)">Regenerate</button>' +
        '<button class="lp-hit study-delete" data-kind="concept" data-id="' + escText(c.id) + '"' + ownerAttrs + ' style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--red)">Delete</button>' +
        '<select class="study-mastery-select" data-concept-id="' + escText(c.id) + '"' + ownerAttrs + ' aria-label="Mastery for ' + escText(c.title) + '">' +
        ['NEW', 'LEARNING', 'MASTERED', 'NEEDS_REVIEW'].map(function (value) { return '<option value="' + value + '"' + (value === mastery ? ' selected' : '') + '>' + ({ NEW: 'New', LEARNING: 'Learning', MASTERED: 'Mastered', NEEDS_REVIEW: 'Needs review' }[value]) + '</option>'; }).join('') +
        '</select></div></div>';
    });
    $('study-concepts-list').innerHTML = conceptsHtml || '<div style="font:500 12px JetBrains Mono;color:var(--muted)">No concepts yet. Process a lecture to build Study content.</div>';

    // Needs review list
    var needsReviewHtml = '';
    (content.concepts || []).forEach(function (c) {
      if (conceptMastery(c.id) === 'NEEDS_REVIEW') {
        needsReviewHtml += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px"><span style="font-weight:600">' + escText(c.title) + '</span></div>';
      }
    });
    // "Nice work" is only true if there was something to do. Nothing studied
    // yet and nothing due are different states and must not read the same.
    var reviewEmptyCopy = (summary.reviewed_count || summary.progress_percent)
      ? 'Nothing to review right now. Nice work.'
      : 'Nothing due yet. Review appears here once you have studied some concepts.';
    $('study-needs-review-list').innerHTML = needsReviewHtml || '<div style="font:500 12px JetBrains Mono;color:var(--muted);line-height:1.5">' + reviewEmptyCopy + '</div>';

    // Study stats
    $('study-stats-v2').innerHTML =
      statRow('Mastered', summary.mastered || 0) +
      statRow('Learning', summary.learning || 0) +
      statRow('Needs review', summary.needs_review || 0) +
      statRow('Cards done', summary.cards_completed || 0) +
      statRow('Quiz correct', summary.quiz_correct || 0);
  }

  function statRow(label, value) {
    return '<div style="display:flex;justify-content:space-between;font-size:13px"><span style="color:var(--muted)">' + label + '</span><span style="font-weight:700">' + value + '</span></div>';
  }

  function studySlideLabel(slideId) {
    // Slide IDs are image filenames or indices; show a readable source time.
    var raw = String(slideId || '');
    var timestamp = raw.match(/_(\d{4,})(?:\.[^.]+)?$/);
    if (timestamp) return fmtTime(Number(timestamp[1]));
    var idx = raw.replace(/[^0-9]/g, '');
    return idx || '?';
  }

  function studyItemSourcesHtml(item, opts) {
    item = item || {};
    opts = opts || {};
    var isGroup = (typeof studyV2 !== 'undefined' && studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all') || opts.isGroup;
    var lecture = item.lecture_sources || item.sources || [];
    var web = item.web_sources || [];

    if (!lecture.length && !web.length && !item.provenance) return '';

    // Check if citations span multiple distinct lectures
    var byJob = {};
    var distinctJobs = [];
    lecture.forEach(function (source) {
      var jid = source.job_id || (typeof LP !== 'undefined' && LP.state && LP.state.jobId) || 'default';
      if (!byJob[jid]) {
        byJob[jid] = [];
        distinctJobs.push(jid);
      }
      byJob[jid].push(source);
    });

    if (isGroup && distinctJobs.length > 1) {
      var groupRows = distinctJobs.map(function (jid) {
        var memberJob = _jobById(jid);
        var title = (memberJob && (memberJob.name || memberJob.title || memberJob.filename)) || (byJob[jid][0] && byJob[jid][0].lecture_title) || 'Lecture';
        var btns = byJob[jid].map(function (source) {
          var parts = [];
          if (source.segment_id != null) {
            parts.push('<button class="lp-hit study-source study-source-time" data-job="' + escText(jid) + '" data-segment="' + escText(source.segment_id) + '" data-ms="' + (source.start_ms || 0) + '">Transcript ' + fmtTime(source.start_ms) + '</button>');
          }
          if (source.slide_id != null) {
            parts.push('<button class="lp-hit study-source study-source-slide" data-job="' + escText(jid) + '" data-slide="' + escText(source.slide_id) + '">Slide ' + escText(studySlideLabel(source.slide_id)) + '</button>');
          }
          return parts.join(' ');
        }).join(' ');
        return '<div class="study-citation-group">' +
          '<span class="study-citation-lecture-name">' + escText(title) + '</span>' +
          '<div class="study-citation-buttons">' + btns + '</div>' +
          '</div>';
      }).join('');
      return '<div class="study-cross-lecture-citations">' + groupRows + '</div>';
    }

    var parts = [];
    if (lecture.length) {
      parts.push('<span class="study-provenance-badge" data-provenance="lecture">From lecture</span>');
    }
    if (item.provenance === 'extra_context') {
      parts.push('<span class="study-provenance-badge" data-provenance="context">Extra context</span>');
    }
    if (web.length) {
      parts.push('<span class="study-provenance-badge" data-provenance="web">Web verified</span>');
    }

    lecture.forEach(function (source) {
      var jid = source.job_id || (typeof LP !== 'undefined' && LP.state && LP.state.jobId) || '';
      var jobObj = jid ? _jobById(jid) : null;
      var prefix = (isGroup && (jobObj || source.lecture_title)) ? ((jobObj ? (jobObj.name || jobObj.title || jobObj.filename) : source.lecture_title) + ' · ') : '';
      if (source.segment_id != null) {
        parts.push('<button class="lp-hit study-source study-source-time"' + (jid ? ' data-job="' + escText(jid) + '"' : '') + ' data-segment="' + escText(source.segment_id) + '" data-ms="' + (source.start_ms || 0) + '">' + escText(prefix) + 'Transcript ' + fmtTime(source.start_ms) + '</button>');
      }
      if (source.slide_id != null) {
        parts.push('<button class="lp-hit study-source study-source-slide"' + (jid ? ' data-job="' + escText(jid) + '"' : '') + ' data-slide="' + escText(source.slide_id) + '">' + escText(prefix) + 'Slide ' + escText(studySlideLabel(source.slide_id)) + '</button>');
      }
    });

    web.forEach(function (source) {
      if (!source || !source.url) return;
      parts.push('<a class="study-web-source" href="' + escText(source.url) + '" target="_blank" rel="noopener noreferrer">' + escText(source.title || 'Web source') + '</a>');
    });

    return parts.join(' ');
  }

  function studyV2FlashcardList() {
    var cards = (studyV2.content && studyV2.content.flashcards) || [];
    // Difficulty is the student's standing preference, so it composes with the
    // "missed cards" and "needs review" filters rather than replacing them.
    if (studyV2.flashDifficulty && studyV2.flashDifficulty !== 'all') {
      cards = cards.filter(function (card) {
        return quizDifficultyOf(card) === studyV2.flashDifficulty;
      });
    }
    if (studyV2.flashFilterIds && studyV2.flashFilterIds.length) {
      return cards.filter(function (card) {
        return studyV2.flashFilterIds.indexOf(card.id) >= 0;
      });
    }
    if (studyV2.reviewOnly) {
      return cards.filter(function (card) {
        return (card.concept_ids || []).some(function (cid) {
          return conceptMastery(cid) === 'NEEDS_REVIEW';
        });
      });
    }
    return cards;
  }

  function renderStudyFlashcards() {
    var cards = studyV2FlashcardList();
    var root = $('study-flashcards-root');
    var hasAnyCard = ((studyV2.content && studyV2.content.flashcards) || []).length > 0;
    if (!cards.length) {
      var filteredOut = hasAnyCard && studyV2.flashDifficulty !== 'all';
      // Three different situations were collapsed into two. With no deck at
      // all -- which is every subject-level scope, because the cross-lecture
      // map produces concepts rather than cards -- the "you have cleared the
      // weak areas" copy congratulated a student who had not studied anything
      // yet. An empty deck is not a finished deck; say which one this is.
      var isGroupScope = !!(studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.groupName);
      var emptyTitle, emptyBody;
      if (filteredOut) {
        emptyTitle = 'No cards at this difficulty';
        emptyBody = 'Choose Any to see the whole deck.';
      } else if (!hasAnyCard) {
        emptyTitle = 'No flashcards here yet';
        emptyBody = isGroupScope
          ? 'Studying a subject builds the cross-lecture map. Flashcards belong to individual lectures, so open one from the Scope menu above to practise them.'
          : 'This lecture has no flashcards yet.';
      } else {
        emptyTitle = 'Nothing needs another look';
        emptyBody = 'You have cleared the current weak areas.';
      }
      root.innerHTML = (hasAnyCard ? flashShapeControlsHtml() : '') +
        '<div class="study-empty-state" style="text-align:center;padding:56px 24px;color:var(--muted)">' +
        '<div style="font:700 18px Space Grotesk;color:var(--ink);margin-bottom:8px">' +
        emptyTitle + '</div>' +
        '<div style="font:500 13px JetBrains Mono;margin-bottom:18px;max-width:52ch;margin-left:auto;margin-right:auto;line-height:1.55">' +
        emptyBody + '</div>' +
        (studyV2.reviewOnly ? '<button id="btn-study-review-all" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:8px;padding:9px 15px;cursor:pointer;color:var(--ink)">Study all cards</button>' : '') +
        '</div>';
      var all = $('btn-study-review-all');
      if (all) all.addEventListener('click', function () {
        studyV2.reviewOnly = false; studyV2.flashFilterIds = null; studyV2.flashIndex = 0;
        studyV2PersistView(); renderStudyFlashcards();
      });
      bindQuizShapeControls(root);
      return;
    }
    var card = cards[studyV2.flashIndex];
    if (!card) {
      // Session complete
      root.innerHTML = flashShapeControlsHtml() +
        '<div style="text-align:center;padding:40px">' +
        '<div style="font-weight:700;font-size:20px;margin-bottom:8px">Cards reviewed</div>' +
        '<div style="font:500 13px JetBrains Mono;color:var(--muted);margin-bottom:20px">' + cards.length + ' cards · ' + studyV2.flashResults.got + ' got it · ' + studyV2.flashResults.missed + ' need review</div>' +
        (studyV2.flashResults.missed ? '<button id="btn-study-review-missed" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 18px;cursor:pointer">Review the ' + studyV2.flashResults.missed + ' I missed</button>' : '') +
        '<button id="btn-study-flash-restart" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 16px;cursor:pointer;color:var(--ink);margin-left:8px">Start over</button></div>';
      bindStudyFlashcardSessionButtons();
      bindQuizShapeControls(root);
      return;
    }
    var sources = studyItemSourcesHtml(card);
    var progress = 'Card ' + (studyV2.flashIndex + 1) + ' of ' + cards.length;
    root.innerHTML = flashShapeControlsHtml() +
      '<div class="study-focus-content" style="max-width:620px;margin:0 auto">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px JetBrains Mono;color:var(--muted);margin-bottom:12px"><span>' + progress + '</span><span>Space to reveal</span></div>' +
      '<div style="height:4px;border-radius:3px;background:var(--sunk);overflow:hidden;margin-bottom:22px"><div style="width:' + (((studyV2.flashIndex + 1) / cards.length) * 100) + '%;height:100%;background:var(--orange)"></div></div>' +
      '<div id="study-flash-card" class="lp-card study-focus-card" style="background:var(--panel);border:1.5px solid var(--border);border-radius:14px;box-shadow:var(--shadow-soft);padding:40px 34px;min-height:220px;display:flex;flex-direction:column;justify-content:center;text-align:center">' +
      '<div style="font-size:22px;font-weight:700;line-height:1.4;margin-bottom:18px">' + escText(card.front) + '</div>' +
      (studyV2.flashRevealed ? '<div style="border-top:1.5px solid var(--line);padding-top:18px;font-size:16px;color:var(--ink);line-height:1.55">' + escText(card.back) + '</div>' : '<button id="btn-study-flash-show" class="lp-hit lp-press" style="font:700 14px Space Grotesk;background:var(--orange);color:var(--on-signal);border:1.5px solid var(--orange-ink);border-radius:9px;padding:11px 20px;cursor:pointer;margin:0 auto">Show answer</button>') +
      '</div>' +
      (sources ? '<div class="study-provenance-row" style="justify-content:center;margin-top:14px">' + sources + '</div>' : '') +
      '<div style="display:flex;justify-content:center;gap:7px;margin-top:12px"><button class="lp-hit study-edit" data-kind="flashcard" data-id="' + escText(card.id) + '">Edit</button><button class="lp-hit study-regenerate" data-kind="flashcard" data-id="' + escText(card.id) + '">Regenerate</button><button class="lp-hit study-delete" data-kind="flashcard" data-id="' + escText(card.id) + '">Delete</button></div>' +
      (studyV2.flashRevealed ?
        '<div style="display:flex;justify-content:center;gap:10px;margin-top:20px">' +
        '<button id="btn-study-flash-again" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:9px;padding:10px 18px;cursor:pointer;color:var(--ink)">Review again</button>' +
        '<button id="btn-study-flash-got" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--green-fill);color:var(--on-signal);border:1.5px solid var(--green);border-radius:9px;padding:10px 18px;cursor:pointer">Got it</button></div>' : '') +
      '</div>';
    bindStudyFlashcardButtons();
    bindQuizShapeControls(root);
  }

  function bindStudyFlashcardButtons() {
    var show = $('btn-study-flash-show');
    if (show) show.addEventListener('click', function () { studyV2.flashRevealed = true; renderStudyFlashcards(); });
    var again = $('btn-study-flash-again');
    if (again) again.addEventListener('click', function () { recordFlashReview(false); });
    var got = $('btn-study-flash-got');
    if (got) got.addEventListener('click', function () { recordFlashReview(true); });
  }

  function recordFlashReview(correct) {
    var cards = studyV2FlashcardList();
    var card = cards[studyV2.flashIndex];
    if (!card) return;
    if (correct) studyV2.flashResults.got++;
    else { studyV2.flashResults.missed++; studyV2.flashResults.missedIds.push(card.id); }
    if (lpBridge.connected()) {
      lpBridge.call('study_v2_record_flashcard', {
        job_id: LP.state.jobId,
        card_id: card.id,
        concept_ids: card.concept_ids || [],
        correct: correct
      }).then(function () { studyV2Load(); }).catch(function () {});
    }
    studyV2.flashIndex++;
    studyV2.flashRevealed = false;
    studyV2PersistView();
    renderStudyFlashcards();
  }

  function quickStudyItemData(item) {
    var content = studyV2.content || { concepts: [], flashcards: [], quiz: [] };
    if (!item) return null;
    if (item.kind === 'concept') return (content.concepts || []).find(function (c) { return c.id === item.id; });
    if (item.kind === 'flashcard') return (content.flashcards || []).find(function (c) { return c.id === item.id; });
    if (item.kind === 'quiz') return (content.quiz || []).find(function (q) { return q.id === item.id; });
    return null;
  }

  function quickStudySources(item) {
    return studyItemSourcesHtml(item || {});
  }

  function renderQuickStudy() {
    var root = $('study-quick-root');
    var session = studyV2.quickSession;
    if (!root) return;
    document.querySelectorAll('.study-duration').forEach(function (button) {
      button.classList.toggle('active', String(button.dataset.studyMinutes) === String(studyV2.quickMinutes));
    });
    if (!session) {
      root.innerHTML = '<div style="max-width:620px;margin:0 auto;text-align:center;padding:52px 24px"><div style="font:700 21px Space Grotesk;margin-bottom:8px">Ready for a focused review?</div><div style="font:500 13px JetBrains Mono;color:var(--muted);line-height:1.6">Choose 5, 10, 20 minutes, or the full set above. Starting a different length rebuilds the session locally without another AI call.</div></div>';
      return;
    }
    var items = session.items || [];
    if (studyV2.quickIndex >= items.length) {
      studyV2.quickSummary = {
        correct: studyV2.quickCorrect,
        total: studyV2.quickTotal,
        missed: studyV2.quickMissed.length
      };
      studyV2PersistView();
      root.innerHTML = '<div class="study-complete-state" style="max-width:620px;margin:0 auto;text-align:center;padding:52px 24px">' +
        '<div style="font:700 22px Space Grotesk;margin-bottom:8px">Study complete</div>' +
        '<div style="font:500 13px JetBrains Mono;color:var(--muted);margin-bottom:8px">' + studyV2.quickCorrect + ' / ' + studyV2.quickTotal + ' correct</div>' +
        '<div style="font-size:14px;color:var(--secondary-text);margin-bottom:22px">' + (studyV2.quickMissed.length ? studyV2.quickMissed.length + ' concepts need another look' : 'Nothing needs another look') + '</div>' +
        (studyV2.quickMissed.length ? '<button class="lp-hit lp-press" data-quick-action="review-weak" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:1.5px solid var(--orange-ink);border-radius:9px;padding:10px 18px;cursor:pointer">Review weak areas</button>' : '') +
        '<button class="lp-hit" data-quick-action="done" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:9px;padding:10px 18px;cursor:pointer;color:var(--ink);margin-left:8px">Done</button></div>';
      return;
    }
    var item = items[studyV2.quickIndex];
    var data = quickStudyItemData(item);
    if (!data) {
      studyV2.quickIndex++; renderQuickStudy(); return;
    }
    var header = '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px JetBrains Mono;color:var(--muted);margin-bottom:12px"><span>Quick Study</span><span>' + (studyV2.quickIndex + 1) + ' of ' + items.length + '</span></div>' +
      '<div style="height:4px;border-radius:3px;background:var(--sunk);overflow:hidden;margin-bottom:24px"><div style="width:' + (((studyV2.quickIndex + 1) / items.length) * 100) + '%;height:100%;background:var(--orange)"></div></div>';
    var body = '';
    var sources = quickStudySources(data);
    if (item.kind === 'quiz') {
      var options = (data.options || []).map(function (option, idx) {
        var selected = studyV2.quickSelected === idx;
        var color = studyV2.quickAnswered ? (idx === data.correct_index ? 'var(--green)' : selected ? 'var(--red)' : 'var(--border)') : 'var(--border)';
        return '<button class="lp-hit study-quick-opt" data-quick-opt="' + idx + '" style="display:block;width:100%;text-align:left;font:600 14px Space Grotesk;background:var(--sunk);border:1.5px solid ' + color + ';border-radius:9px;padding:11px 14px;cursor:pointer;color:var(--ink);margin-bottom:8px"' + (studyV2.quickAnswered ? ' disabled' : '') + '>' + escText(option) + '</button>';
      }).join('');
      body = '<div style="font-size:19px;font-weight:700;line-height:1.45;margin-bottom:18px">' + escText(data.question) + '</div>' + options;
      if (studyV2.quickAnswered) body += '<div style="margin-top:14px;padding:13px 15px;background:var(--panel2);border-radius:9px"><div style="font-weight:700;color:' + (studyV2.quickSelected === data.correct_index ? 'var(--green)' : 'var(--red)') + ';margin-bottom:5px">' + (studyV2.quickSelected === data.correct_index ? 'Correct' : 'Not quite') + '</div><div style="font-size:13px;line-height:1.5;color:var(--secondary-text)">' + escText(data.explanation || '') + '</div>' + (sources ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:9px">' + sources + '</div>' : '') + '<button class="lp-hit lp-press" data-quick-action="continue" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:1.5px solid var(--orange-ink);border-radius:8px;padding:9px 16px;cursor:pointer;margin-top:12px">Continue</button></div>';
    } else {
      var title = item.kind === 'concept' ? data.title : data.front;
      var answer = item.kind === 'concept' ? data.explanation : data.back;
      body = '<div style="font-size:21px;font-weight:700;line-height:1.45;margin-bottom:20px">' + escText(title) + '</div>' +
        (studyV2.quickRevealed ? '<div style="border-top:1.5px solid var(--line);padding-top:18px;font-size:15px;line-height:1.55">' + escText(answer || '') + '</div>' : '<button class="lp-hit lp-press" data-quick-action="reveal" style="font:700 14px Space Grotesk;background:var(--orange);color:var(--on-signal);border:1.5px solid var(--orange-ink);border-radius:9px;padding:11px 20px;cursor:pointer">Show explanation</button>');
      if (studyV2.quickRevealed) body += '<div style="display:flex;justify-content:center;gap:10px;margin-top:20px"><button class="lp-hit" data-quick-action="result-wrong" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:9px;padding:10px 18px;cursor:pointer;color:var(--ink)">Need another look</button><button class="lp-hit lp-press" data-quick-action="result-right" style="font:700 13px Space Grotesk;background:var(--green-fill);color:var(--on-signal);border:1.5px solid var(--green);border-radius:9px;padding:10px 18px;cursor:pointer">Got it</button></div>';
    }
    root.innerHTML = '<div class="study-focus-content" style="max-width:680px;margin:0 auto">' + header + '<div class="study-focus-card" style="background:var(--panel);border:1.5px solid var(--border);border-radius:14px;box-shadow:var(--shadow-soft);padding:38px 34px;text-align:center">' + body + '</div>' + (sources && item.kind !== 'quiz' ? '<div style="display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin-top:14px">' + sources + '</div>' : '') + '</div>';
  }

  function quickStudyFinishItem(correct) {
    var items = (studyV2.quickSession && studyV2.quickSession.items) || [];
    var item = items[studyV2.quickIndex];
    var data = quickStudyItemData(item);
    if (!item || !data) return;
    studyV2.quickTotal++;
    if (correct) studyV2.quickCorrect++;
    else if (item.concept_id && studyV2.quickMissed.indexOf(item.concept_id) < 0) studyV2.quickMissed.push(item.concept_id);
    if (lpBridge.connected()) {
      if (item.kind === 'quiz') lpBridge.call('study_v2_record_quiz', { job_id: LP.state.jobId, question_id: item.id, concept_ids: [item.concept_id], correct: correct }).catch(function () {});
      else lpBridge.call('study_v2_record_flashcard', { job_id: LP.state.jobId, card_id: item.kind === 'concept' ? 'quick-' + item.id : item.id, concept_ids: [item.concept_id], correct: correct }).catch(function () {});
    }
    studyV2.quickIndex++; studyV2.quickRevealed = false; studyV2.quickAnswered = false; studyV2.quickSelected = null;
    studyV2PersistView(); renderQuickStudy();
  }

  function quickStudySelectQuiz(index) {
    var items = (studyV2.quickSession && studyV2.quickSession.items) || [];
    var item = items[studyV2.quickIndex];
    var data = quickStudyItemData(item);
    if (!item || !data || studyV2.quickAnswered) return;
    var correct = Number(data.correct_index) === Number(index);
    studyV2.quickTotal++;
    if (correct) studyV2.quickCorrect++;
    else if (item.concept_id && studyV2.quickMissed.indexOf(item.concept_id) < 0) studyV2.quickMissed.push(item.concept_id);
    studyV2.quickAnswered = true; studyV2.quickSelected = Number(index);
    if (lpBridge.connected()) lpBridge.call('study_v2_record_quiz', { job_id: LP.state.jobId, question_id: item.id, concept_ids: [item.concept_id], correct: correct }).catch(function () {});
    studyV2PersistView(); renderQuickStudy();
  }

  function bindStudyFlashcardSessionButtons() {
    var restart = $('btn-study-flash-restart');
    if (restart) restart.addEventListener('click', function () {
      studyV2.flashIndex = 0; studyV2.flashRevealed = false;
      studyV2.flashResults = { got: 0, missed: 0, missedIds: [] };
      studyV2PersistView();
      renderStudyFlashcards();
    });
    var missed = $('btn-study-review-missed');
    if (missed) missed.addEventListener('click', function () {
      studyV2.flashFilterIds = studyV2.flashResults.missedIds.slice();
      studyV2.flashIndex = 0; studyV2.flashRevealed = false;
      studyV2PersistView();
      renderStudyFlashcards();
    });
    var reviewAll = $('btn-study-review-all');
    if (reviewAll) reviewAll.addEventListener('click', function () {
      studyV2.reviewOnly = false; studyV2.flashFilterIds = null; studyV2.flashIndex = 0;
      studyV2PersistView(); renderStudyFlashcards();
    });
  }

  /* ---- shaping the quiz -----------------------------------------------
     "Make it harder / easier / longer / shorter" is answered from the pack
     that is already generated: filtering is instant, costs no AI request and
     works offline, where regenerating for every adjustment would be slow and
     could fail. The generator is told to spread difficulty across the pack so
     there is something real to filter. Whatever the model wrote is normalised
     here -- an item with an unrecognised difficulty counts as medium rather
     than vanishing from every view. */
  /* The grader returns a null score when its own verdict and number
     contradicted each other (see ai_study_service.grade_short_answer). Showing
     nothing beats showing "Keep working · 0%", which reads as a harsher grade
     than the student actually got. */
  function studyScoreSuffix(score) {
    var value = Number(score);
    if (score === null || score === undefined || !isFinite(value)) return '';
    return ' · ' + Math.round(value * 100) + '%';
  }

  function quizDifficultyOf(item) {
    var raw = String((item && item.difficulty) || '').trim().toLowerCase();
    return QUIZ_DIFFICULTIES.indexOf(raw) > 0 ? raw : 'medium';
  }

  function quizPool() {
    var all = (studyV2.content && studyV2.content.quiz) || [];
    var picked = studyV2.quizDifficulty === 'all' ? all.slice() : all.filter(function (q) {
      return quizDifficultyOf(q) === studyV2.quizDifficulty;
    });
    var limit = Number(studyV2.quizLength);
    return studyV2.quizLength === 'all' || !limit ? picked : picked.slice(0, limit);
  }

  function quizDifficultyCounts() {
    var counts = { all: 0, easy: 0, medium: 0, hard: 0 };
    ((studyV2.content && studyV2.content.quiz) || []).forEach(function (q) {
      counts.all += 1;
      counts[quizDifficultyOf(q)] += 1;
    });
    return counts;
  }

  function setQuizShape(key, value) {
    if (key === 'difficulty') {
      if (studyV2.quizDifficulty === value) return;
      studyV2.quizDifficulty = value;
    } else {
      if (studyV2.quizLength === value) return;
      studyV2.quizLength = value;
    }
    // Reshaping changes which questions exist, so a part-finished run cannot
    // be carried over -- its index and score would refer to a different set.
    studyV2.quizIndex = 0;
    studyV2.quizCorrect = 0;
    studyV2.quizAnswers = [];
    studyV2.quizPicks = {};
    studyV2PersistView();
    renderStudyQuiz();
  }

  /* One shaping row, shared by Quiz and Flashcards. `groups` is
     [{label, key, selected, options:[{value,label,disabled,title}]}]. */
  function studyShapeRowHtml(groups, countText) {
    return '<div class="lp-study-shape">' + groups.map(function (g) {
      return '<div class="lp-study-shape-group"><span class="lp-study-shape-label">' + escText(g.label) + '</span>' +
        g.options.map(function (opt) {
          var on = String(g.selected) === String(opt.value);
          return '<button class="lp-hit lp-study-shape-btn" data-shape="' + escText(g.key) + '" data-value="' + escText(String(opt.value)) + '"' +
            ' aria-pressed="' + (on ? 'true' : 'false') + '"' + (opt.disabled ? ' disabled' : '') +
            (opt.title ? ' title="' + escText(opt.title) + '"' : '') + '>' + escText(opt.label) + '</button>';
        }).join('') + '</div>';
    }).join('') + '<span class="lp-study-shape-count">' + escText(countText) + '</span></div>';
  }

  function difficultyOptions(counts, noun) {
    return [{ value: 'all', label: 'Any' }].concat(
      [['easy', 'Easier'], ['medium', 'Medium'], ['hard', 'Harder']].map(function (pair) {
        var n = counts[pair[0]];
        return {
          value: pair[0], label: pair[1], disabled: !n,
          title: n ? n + ' ' + noun + (n === 1 ? '' : 's') : 'No ' + pair[0] + ' ' + noun + 's in this pack'
        };
      }));
  }

  function quizShapeControlsHtml() {
    var total = quizPool().length;
    return studyShapeRowHtml([
      { label: 'Difficulty', key: 'difficulty', selected: studyV2.quizDifficulty,
        options: difficultyOptions(quizDifficultyCounts(), 'question') },
      { label: 'Length', key: 'length', selected: studyV2.quizLength, options: [
        { value: '5', label: '5' }, { value: '10', label: '10' },
        { value: '20', label: '20' }, { value: 'all', label: 'All' }] }
    ], total + (total === 1 ? ' question' : ' questions'));
  }

  function flashDifficultyCounts() {
    var counts = { all: 0, easy: 0, medium: 0, hard: 0 };
    ((studyV2.content && studyV2.content.flashcards) || []).forEach(function (card) {
      counts.all += 1;
      counts[quizDifficultyOf(card)] += 1;
    });
    return counts;
  }

  function flashShapeControlsHtml() {
    var total = studyV2FlashcardList().length;
    return studyShapeRowHtml([
      { label: 'Difficulty', key: 'flash-difficulty', selected: studyV2.flashDifficulty,
        options: difficultyOptions(flashDifficultyCounts(), 'card') }
    ], total + (total === 1 ? ' card' : ' cards'));
  }

  function setFlashDifficulty(value) {
    if (studyV2.flashDifficulty === value) return;
    studyV2.flashDifficulty = value;
    // Same reasoning as the quiz: flashIndex points into the shaped deck.
    studyV2.flashIndex = 0;
    studyV2.flashResults = { got: 0, missed: 0, missedIds: [] };
    studyV2PersistView();
    renderStudyFlashcards();
  }

  function renderStudyQuiz() {
    var all = (studyV2.content && studyV2.content.quiz) || [];
    var questions = quizPool();
    var root = $('study-quiz-root');
    if (!all.length) {
      root.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted);font:500 13px JetBrains Mono">No quiz questions yet.</div>';
      return;
    }
    if (!questions.length) {
      // Reachable only if the pack has questions but none match the shape;
      // offer the way back rather than an empty screen.
      root.innerHTML = quizShapeControlsHtml() +
        '<div style="text-align:center;padding:40px;color:var(--muted);font:500 13px JetBrains Mono">' +
        'No questions at this difficulty. Choose <strong>Any</strong> to see all ' + all.length + '.</div>';
      bindQuizShapeControls(root);
      return;
    }
    var q = questions[studyV2.quizIndex];
    if (!q) {
      // Quiz complete
      root.innerHTML = quizShapeControlsHtml() +
        '<div style="text-align:center;padding:40px">' +
        '<div style="font-weight:700;font-size:20px;margin-bottom:8px">Quiz complete</div>' +
        '<div style="font:500 13px JetBrains Mono;color:var(--muted);margin-bottom:20px">' + studyV2.quizCorrect + ' / ' + questions.length + ' correct</div>' +
        '<button id="btn-study-quiz-restart" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 18px;cursor:pointer">Take again</button></div>';
      var restart = $('btn-study-quiz-restart');
      if (restart) restart.addEventListener('click', function () {
        studyV2.quizIndex = 0; studyV2.quizCorrect = 0; studyV2.quizAnswers = []; studyV2.quizPicks = {};
        studyV2PersistView();
        renderStudyQuiz();
      });
      bindQuizShapeControls(root);
      return;
    }
    var savedPick = Object.prototype.hasOwnProperty.call(studyV2.quizPicks, studyV2.quizIndex) ? Number(studyV2.quizPicks[studyV2.quizIndex]) : null;
    var isShortAnswer = q.qtype === 'short_answer';
    var grade = studyV2.quizGrades[q.id] || null;
    var answered = isShortAnswer ? !!grade : savedPick !== null && !Number.isNaN(savedPick);
    var optionsHtml = isShortAnswer ?
      '<textarea id="study-quiz-short-answer" class="study-short-answer" placeholder="Answer in your own words"' + (answered || studyV2.quizGrading ? ' disabled' : '') + '></textarea>' +
      '<button id="btn-study-grade-short-answer" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 16px;cursor:pointer;margin-top:10px"' + (answered || studyV2.quizGrading ? ' disabled' : '') + '>' + (studyV2.quizGrading ? 'Grading…' : 'Grade answer') + '</button>' :
      (q.options || []).map(function (opt, i) {
        var color = answered ? (i === q.correct_index ? 'var(--green)' : i === savedPick ? 'var(--red)' : 'var(--border)') : 'var(--border)';
        return '<button class="lp-hit study-quiz-opt" data-opt="' + i + '" style="display:block;width:100%;text-align:left;font:600 14px Space Grotesk;background:var(--sunk);border:1.5px solid ' + color + ';border-radius:9px;padding:11px 14px;cursor:pointer;color:var(--ink);margin-bottom:8px"' + (answered ? ' disabled' : '') + '>' + escText(opt) + '</button>';
      }).join('');
    root.innerHTML = quizShapeControlsHtml() +
      '<div class="study-focus-content" style="max-width:680px;margin:0 auto">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px JetBrains Mono;color:var(--muted);margin-bottom:12px"><span>Question ' + (studyV2.quizIndex + 1) + ' of ' + questions.length + '</span><span>' + (isShortAnswer ? 'Short answer' : q.qtype === 'true_false' ? 'True or false' : 'Choose one') + '</span></div>' +
      '<div style="height:4px;border-radius:3px;background:var(--sunk);overflow:hidden;margin-bottom:24px"><div style="width:' + (((studyV2.quizIndex + 1) / questions.length) * 100) + '%;height:100%;background:var(--orange)"></div></div>' +
      '<div style="font-size:18px;font-weight:700;line-height:1.4;margin-bottom:18px;text-align:center">' + escText(q.question) + '</div>' +
      optionsHtml +
      '<div id="study-quiz-feedback" style="margin-top:14px"></div>' +
      '<div style="display:flex;gap:7px;justify-content:center;margin-top:16px"><button class="lp-hit study-edit" data-kind="quiz" data-id="' + escText(q.id) + '">Edit</button><button class="lp-hit study-regenerate" data-kind="quiz" data-id="' + escText(q.id) + '">Regenerate</button><button class="lp-hit study-delete" data-kind="quiz" data-id="' + escText(q.id) + '">Delete</button></div></div>';
    bindStudyQuizButtons();
    bindQuizShapeControls(root);
    if (answered && isShortAnswer) renderStudyShortAnswerFeedback(q, grade);
    else if (answered) renderStudyQuizFeedback(q, savedPick);
  }

  function bindQuizShapeControls(root) {
    if (!root) return;
    Array.prototype.forEach.call(root.querySelectorAll('.lp-study-shape-btn'), function (button) {
      button.addEventListener('click', function () {
        if (button.dataset.shape === 'flash-difficulty') setFlashDifficulty(button.dataset.value);
        else setQuizShape(button.dataset.shape, button.dataset.value);
      });
    });
  }

  function renderStudyQuizFeedback(q, selectedIndex) {
    var correct = (q.correct_index === selectedIndex);
    var srcHtml = studyItemSourcesHtml(q);
    var fb = $('study-quiz-feedback');
    if (!fb) return;
    fb.innerHTML = (correct ? '<div style="color:var(--green);font-weight:700;font-size:15px;margin-bottom:6px">âœ“ Correct</div>' : '<div style="color:var(--red);font-weight:700;font-size:15px;margin-bottom:6px">âœ• Not quite</div>') +
      (q.explanation ? '<div style="font-size:13px;color:var(--secondary-text);line-height:1.5;margin-bottom:8px">' + escText(q.explanation) + '</div>' : '') +
      (srcHtml ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">' + srcHtml + '</div>' : '') +
      '<button id="btn-study-quiz-next" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 16px;cursor:pointer">Next</button>';
    if (fb.firstElementChild) fb.firstElementChild.textContent = correct ? 'Correct' : 'Not quite';
    var next = $('btn-study-quiz-next');
    if (next) next.addEventListener('click', function () {
      studyV2.quizIndex++; studyV2PersistView(); renderStudyQuiz();
    });
  }

  function renderStudyShortAnswerFeedback(q, result) {
    var fb = $('study-quiz-feedback');
    if (!fb || !result) return;
    var sourceHtml = studyItemSourcesHtml(result) || studyItemSourcesHtml(q);
    fb.innerHTML = '<div style="padding:14px 16px;background:var(--panel2);border-radius:9px">' +
      '<div style="font-weight:700;color:' + (result.correct ? 'var(--green)' : 'var(--red)') + ';margin-bottom:6px">' + (result.correct ? 'Correct' : 'Keep working') + studyScoreSuffix(result.score) + '</div>' +
      '<div style="font-size:13px;line-height:1.55;color:var(--secondary-text)">' + escText(result.feedback || '') + '</div>' +
      (result.ideal_answer ? '<div style="font-size:13px;line-height:1.55;margin-top:9px"><strong>Strong answer:</strong> ' + escText(result.ideal_answer) + '</div>' : '') +
      (sourceHtml ? '<div class="study-provenance-row" style="margin-top:10px">' + sourceHtml + '</div>' : '') +
      '<button id="btn-study-quiz-next" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 16px;cursor:pointer;margin-top:12px">Next</button></div>';
    var next = $('btn-study-quiz-next');
    if (next) next.addEventListener('click', function () {
      studyV2.quizIndex++; studyV2PersistView(); renderStudyQuiz();
    });
  }

  function bindStudyQuizButtons() {
    var opts = document.querySelectorAll('.study-quiz-opt');
    opts.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = Number(btn.dataset.opt);
        // Same pool the question was drawn from -- quizIndex is an index INTO
        // the shaped run, so reading the full pack would answer a different
        // question than the one on screen.
        var questions = quizPool();
        var q = questions[studyV2.quizIndex];
        if (!q || studyV2.quizAnswers.indexOf(studyV2.quizIndex) >= 0) return;
        var correct = (q.correct_index === idx);
        if (correct) studyV2.quizCorrect++;
        studyV2.quizAnswers.push(studyV2.quizIndex);
        studyV2.quizPicks[studyV2.quizIndex] = idx;
        if (lpBridge.connected()) {
          lpBridge.call('study_v2_record_quiz', {
            job_id: LP.state.jobId,
            question_id: q.id,
            concept_ids: q.concept_ids || [],
            correct: correct
          }).then(function () { studyV2Load(); }).catch(function () {});
        }
        studyV2PersistView();
        var srcHtml = studyItemSourcesHtml(q);
        var fb = $('study-quiz-feedback');
        fb.innerHTML = (correct ? '<div style="color:var(--green);font-weight:700;font-size:15px;margin-bottom:6px">✓ Correct</div>' : '<div style="color:var(--red);font-weight:700;font-size:15px;margin-bottom:6px">✕ Not quite</div>') +
          (q.explanation ? '<div style="font-size:13px;color:var(--secondary-text);line-height:1.5;margin-bottom:8px">' + escText(q.explanation) + '</div>' : '') +
          (srcHtml ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">' + srcHtml + '</div>' : '') +
          '<button id="btn-study-quiz-next" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 16px;cursor:pointer">Next</button>';
        if (fb.firstElementChild) fb.firstElementChild.textContent = correct ? 'Correct' : 'Not quite';
        var next = $('btn-study-quiz-next');
        if (next) next.addEventListener('click', function () {
          studyV2.quizIndex++; studyV2PersistView(); renderStudyQuiz();
        });
      });
    });
    var grade = $('btn-study-grade-short-answer');
    if (grade) grade.addEventListener('click', function () {
      var questions = quizPool();
      var q = questions[studyV2.quizIndex];
      var input = $('study-quiz-short-answer');
      var answer = input && input.value.trim();
      if (!q || !answer || !lpBridge.connected() || studyV2.quizGrading) return;
      studyV2.quizGrading = true;
      studyV2.quizGradingQuestionId = q.id;
      renderStudyQuiz();
      lpBridge.call('study_v2_grade_short_answer', {
        job_id: LP.state.jobId,
        question_id: q.id,
        question: q.question,
        answer: answer,
        rubric: q.rubric || q.explanation || '',
        concept_ids: q.concept_ids || []
      }).then(function (result) {
        if (!result || result.ok === false) {
          studyV2.quizGrading = false;
          studyV2.quizGradingQuestionId = '';
          toast((result && result.error) || 'This answer could not be graded.');
          renderStudyQuiz();
        }
      }).catch(function () {
        studyV2.quizGrading = false;
        studyV2.quizGradingQuestionId = '';
        toast('This answer could not be graded.');
        renderStudyQuiz();
      });
    });
  }

  function renderStudyAsk() {
    // Feed already has messages; add suggestion chips when empty.
    if ($('study-ask-feed').children.length) return;
    $('study-ask-feed').innerHTML =
      '<div style="display:flex;gap:8px;flex-wrap:wrap;padding:8px">' +
      '<button class="lp-hit study-ask-chip" data-q="Explain this lecture simply" style="font:600 12px Space Grotesk;background:var(--panel);border:2px solid var(--border);border-radius:8px;padding:8px 13px;cursor:pointer;color:var(--ink)">Explain simply</button>' +
      '<button class="lp-hit study-ask-chip" data-q="What are the key concepts?" style="font:600 12px Space Grotesk;background:var(--panel);border:2px solid var(--border);border-radius:8px;padding:8px 13px;cursor:pointer;color:var(--ink)">Key concepts</button>' +
      '<button class="lp-hit study-ask-chip" data-q="Quiz me on this" style="font:600 12px Space Grotesk;background:var(--panel);border:2px solid var(--border);border-radius:8px;padding:8px 13px;cursor:pointer;color:var(--ink)">Quiz me</button>' +
      '</div>';
  }

  function renderStudyTeach() {
    var select = $('study-teach-concept');
    var root = $('study-teach-root');
    if (!select || !root) return;
    var concepts = (studyV2.content && studyV2.content.concepts) || [];
    if (!concepts.length) {
      select.innerHTML = '<option value="">No concepts available</option>';
      root.innerHTML = '<div style="text-align:center;padding:52px 24px;font:500 13px JetBrains Mono;color:var(--muted)">Teach Me will be ready when lecture concepts are available.</div>';
      return;
    }
    if (!studyV2.teachConceptId || !concepts.some(function (concept) { return concept.id === studyV2.teachConceptId; })) {
      studyV2.teachConceptId = concepts[0].id;
    }
    select.innerHTML = concepts.map(function (concept) {
      return '<option value="' + escText(concept.id) + '"' + (concept.id === studyV2.teachConceptId ? ' selected' : '') + '>' + escText(concept.title) + '</option>';
    }).join('');
    if (studyV2.teachLoading) {
      root.innerHTML = '<div style="text-align:center;padding:52px 24px"><div style="font:700 19px Space Grotesk;margin-bottom:7px">Building your explanation…</div><div style="font:500 13px JetBrains Mono;color:var(--muted)">Grounding the lesson in this lecture.</div></div>';
      return;
    }
    var result = studyV2.teachResult;
    if (!result || result.concept_ids && result.concept_ids.indexOf(studyV2.teachConceptId) < 0) {
      var foundation = ((studyV2.content && studyV2.content.teach_me_foundations) || []).find(function (item) {
        return item.concept_id === studyV2.teachConceptId;
      });
      root.innerHTML = '<div style="max-width:680px;margin:0 auto;text-align:center;padding:46px 24px"><div style="font:700 20px Space Grotesk;margin-bottom:8px">Learn one idea step by step</div><div style="font-size:14px;line-height:1.6;color:var(--secondary-text)">' + escText(foundation && foundation.explanation || 'Choose a concept and LecturePack will teach it using the lecture evidence.') + '</div>' +
        (foundation && studyItemSourcesHtml(foundation) ? '<div class="study-provenance-row" style="justify-content:center;margin-top:13px">' + studyItemSourcesHtml(foundation) + '</div>' : '') + '</div>';
      return;
    }
    var concept = concepts.find(function (item) { return item.id === studyV2.teachConceptId; }) || {};
    var grade = studyV2.teachGrade;
    root.innerHTML = '<div class="study-teach-card">' +
      '<div><div style="font:700 22px Space Grotesk;margin-bottom:8px">' + escText(concept.title || 'Concept') + '</div><div style="font-size:15px;line-height:1.65;color:var(--secondary-text)">' + escText(result.explanation || '') + '</div></div>' +
      (result.analogy ? '<div class="study-guide-section"><h3>Try this analogy</h3><p>' + escText(result.analogy) + '</p></div>' : '') +
      (studyItemSourcesHtml(result) ? '<div class="study-provenance-row">' + studyItemSourcesHtml(result) + '</div>' : '') +
      '<div class="study-guide-section"><h3>Check your understanding</h3><p style="margin-bottom:10px">' + escText(result.check_question || '') + '</p>' +
      '<textarea id="study-teach-answer" class="study-short-answer" placeholder="Explain it in your own words"' + (grade ? ' disabled' : '') + '></textarea>' +
      '<button id="btn-study-teach-grade" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:9px 16px;cursor:pointer;margin-top:10px"' + (grade ? ' disabled' : '') + '>Check answer</button>' +
      (grade ? '<div style="margin-top:13px;padding:12px 14px;background:var(--panel);border-radius:8px"><div style="font-weight:700;color:' + (grade.correct ? 'var(--green)' : 'var(--red)') + '">' + (grade.correct ? 'You have it' : 'Keep working') + studyScoreSuffix(grade.score) + '</div><div style="font-size:13px;line-height:1.55;color:var(--secondary-text);margin-top:5px">' + escText(grade.feedback || '') + '</div></div>' : '') +
      '</div></div>';
  }

  function studyAskSend() {
    if (studyV2.askStreaming) return;
    var input = $('study-ask-input');
    var q = input.value.trim();
    if (!q) return;
    input.value = '';
    var feed = $('study-ask-feed');
    studyV2.askStreaming = true;
    studyV2.askAnswer = null;
    feed.innerHTML += '<div style="display:flex;justify-content:flex-end"><div style="background:var(--orange-soft);border:2px solid var(--orange);border-radius:11px;padding:10px 14px;font-size:14px;max-width:80%">' + escText(q) + '</div></div>';
    feed.innerHTML += '<div style="display:flex;justify-content:flex-start"><div class="study-ask-thinking" style="background:var(--panel);border:2px solid var(--border);border-radius:11px;padding:10px 14px;font-size:14px;max-width:80%;color:var(--secondary-text)">Thinking…</div></div>';
    feed.scrollTop = feed.scrollHeight;
    if (lpBridge.connected()) {
      studyV2.askJobId = LP.state.jobId || '';
      lpBridge.call('ask_ai', { job_id: studyV2.askJobId, prompt: q }).then(function () {}).catch(function () {});
    } else {
      setTimeout(function () {
        var msgs = feed.querySelectorAll('div');
        if (msgs.length) msgs[msgs.length - 1].textContent = 'Built-in Study: I could not find that in this lecture.';
        studyV2.askStreaming = false;
      }, 600);
    }
  }

  function appendStudyAskText(text, done) {
    if (!studyV2.askStreaming) return;
    var feed = $('study-ask-feed');
    if (!feed) return;
    var answers = feed.querySelectorAll('.study-ask-thinking, .study-ask-answer');
    var answer = answers.length ? answers[answers.length - 1] : null;
    if (!answer && feed.lastElementChild) {
      answer = feed.lastElementChild.lastElementChild;
    }
    if (!answer) return;
    answer.classList.remove('study-ask-thinking');
    answer.classList.add('study-ask-answer');
    studyV2.askAnswer = String(text == null ? '' : text);
    answer.textContent = studyV2.askAnswer || 'I could not find that in this lecture.';
    if (done) studyV2.askStreaming = false;
    feed.scrollTop = feed.scrollHeight;
  }

  function appendStudyAskSources(sources, provenance) {
    if (!studyV2.askAnswer || !Array.isArray(sources)) return;
    // Ask may answer a question about the lecture's subject that the lecture
    // itself never covers (a date, who someone was). That answer honestly has
    // no lecture source, so it arrives with an empty list. Say where it came
    // from rather than rendering nothing -- and never borrow a lecture chip.
    var beyond = !sources.length && String(provenance || '') === 'extra_context';
    if (!sources.length && !beyond) return;
    var feed = $('study-ask-feed');
    var answers = feed && feed.querySelectorAll('.study-ask-answer');
    var answer = answers && answers.length ? answers[answers.length - 1] : null;
    if (!answer) return;
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin-top:9px';
    if (beyond) {
      var note = document.createElement('span');
      note.className = 'study-source-beyond';
      note.textContent = 'Beyond this lecture · general knowledge';
      note.title = 'This lecture does not cover it, so this answer is not cited to a slide or transcript line.';
      wrap.appendChild(note);
    }
    sources.forEach(function (source) {
      if (source && (source.kind === 'web' || source.url)) {
        var link = document.createElement('a');
        link.className = 'study-web-source';
        link.href = source.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Web verified · ' + (source.title || 'Source');
        wrap.appendChild(link);
        return;
      }
      var button = document.createElement('button');
      button.className = 'lp-hit study-source' + (source.slide_id != null ? ' study-source-slide' : '');
      if (source.slide_id != null) {
        button.dataset.slide = source.slide_id;
        button.textContent = 'From lecture · Slide ' + studySlideLabel(source.slide_id);
      } else {
        button.dataset.segment = source.segment_id;
        button.dataset.ms = source.start_ms || 0;
        button.textContent = 'From lecture · ' + (source.start_ms != null ? 'Transcript ' + fmtTime(source.start_ms) : 'Transcript source');
      }
      wrap.appendChild(button);
    });
    answer.parentNode.appendChild(wrap);
  }

  function setStudyV2Mode(mode, keepQuick) {
    if (['overview', 'flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(mode) < 0) mode = 'overview';
    studyV2.mode = mode;
    if (mode !== 'overview') studyV2.resumeMode = mode;
    studyV2PersistView();
    document.querySelectorAll('.study-mode-tab').forEach(function (btn) {
      var active = btn.dataset.studyMode === mode;
      btn.className = 'lp-hit lp-tab study-mode-tab' + (active ? ' active' : '');
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    ['overview', 'flashcards', 'quiz', 'ask', 'quick', 'teach'].forEach(function (m) {
      $('study-mode-' + m).hidden = mode !== m;
    });
    if (mode === 'flashcards') renderStudyFlashcards();
    if (mode === 'quiz') renderStudyQuiz();
    if (mode === 'ask') renderStudyAsk();
    if (mode === 'quick') renderQuickStudy();
    if (mode === 'teach') renderStudyTeach();
  }

  function startQuickStudy(minutes) {
    if (!lpBridge.connected()) return;
    studyV2.quickMinutes = String(minutes || '5');
    var requestedJobId = LP.state.jobId || '';
    setStudyV2Mode('quick');
    var root = $('study-quick-root');
    if (root) root.innerHTML = '<div style="text-align:center;padding:52px 24px;font:500 13px JetBrains Mono;color:var(--muted)">Building your focused session…</div>';
    lpBridge.call('study_v2_quick_study', {
      job_id: requestedJobId,
      minutes: studyV2.quickMinutes
    }).then(function (res) {
      if (LP.state.jobId !== requestedJobId || (res && res.job_id && res.job_id !== requestedJobId)) return;
      if (!res || !res.session) {
        toast('Quick Study could not be prepared.');
        renderQuickStudy();
        return;
      }
      studyV2.quickSession = res.session;
      studyV2.quickIndex = 0; studyV2.quickCorrect = 0; studyV2.quickTotal = 0;
      studyV2.quickMissed = []; studyV2.quickRevealed = false;
      studyV2.quickAnswered = false; studyV2.quickSelected = null; studyV2.quickSummary = null;
      studyV2PersistView();
      renderQuickStudy();
    }).catch(function () {
      toast('Quick Study could not be prepared.');
      renderQuickStudy();
    });
  }

  function bindStudyV2Events() {
    // Boot can be re-entered after a restored job or a bridge reconnect. Keep
    // the delegated Study handlers single-owner so one click cannot submit
    // the same edit, delete, or answer multiple times.
    if (bindStudyV2Events._bound) return;
    bindStudyV2Events._bound = true;
    document.querySelectorAll('.study-mode-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.dataset.studyMode === 'flashcards' &&
            (studyV2.reviewOnly || studyV2.flashFilterIds)) {
          studyV2.reviewOnly = false;
          studyV2.flashFilterIds = null;
          studyV2.flashIndex = 0;
        }
        setStudyV2Mode(btn.dataset.studyMode);
      });
    });
    var quick = $('btn-study-quick');
    if (quick) quick.addEventListener('click', function () {
      startQuickStudy('10');
    });
    document.querySelectorAll('.study-duration').forEach(function (button) {
      button.addEventListener('click', function () {
        startQuickStudy(button.dataset.studyMinutes || '5');
      });
    });
    var cont = $('btn-study-continue');
    if (cont) cont.addEventListener('click', function () {
      if (studyV2.quickSession && studyV2.quickIndex < (studyV2.quickSession.items || []).length) {
        setStudyV2Mode('quick', true); return;
      }
      var needsReview = (studyV2.summary && studyV2.summary.needs_review > 0);
      if (needsReview) {
        studyV2.reviewOnly = true; studyV2.flashFilterIds = null; studyV2.flashIndex = 0;
        setStudyV2Mode('flashcards');
      } else {
        setStudyV2Mode(studyV2.resumeMode || 'flashcards');
      }
    });
    var review = $('btn-study-review');
    if (review) review.addEventListener('click', function () {
      studyV2.reviewOnly = true; studyV2.flashFilterIds = null; studyV2.flashIndex = 0;
      setStudyV2Mode('flashcards');
    });
    var retryAi = $('btn-study-ai-retry');
    if (retryAi) retryAi.addEventListener('click', function () {
      if (!lpBridge.connected()) return;
      retryAi.disabled = true;
      lpBridge.call('study_v2_retry', { job_id: LP.state.jobId }).then(function (result) {
        retryAi.disabled = false;
        if (result && result.content) studyV2.content = result.content;
        renderStudyGenerationState();
        if (!result || result.ok === false) toast((result && result.error) || 'Study AI could not be retried.');
      }).catch(function () {
        retryAi.disabled = false;
        toast('Study AI could not be retried.');
      });
    });
    var useBasic = $('btn-study-use-basic');
    if (useBasic) useBasic.addEventListener('click', function () {
      if (!lpBridge.connected()) return;
      lpBridge.call('study_v2_use_basic', { job_id: LP.state.jobId }).then(function (result) {
        if (result && result.content) {
          studyV2.content = result.content;
          renderStudyGenerationState();
          studyV2Load();
        } else toast((result && result.error) || 'Basic Study could not be prepared.');
      }).catch(function () { toast('Basic Study could not be prepared.'); });
    });
    var copyDiagnostics = $('btn-study-copy-diagnostics');
    if (copyDiagnostics) copyDiagnostics.addEventListener('click', function () {
      if (!lpBridge.connected()) return;
      lpBridge.call('study_v2_copy_diagnostics', { job_id: LP.state.jobId }).then(function (result) {
        var text = JSON.stringify((result && result.diagnostics) || {}, null, 2);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { toast('Diagnostics copied.'); }).catch(function () { toast('Diagnostics could not be copied.'); });
        }
      }).catch(function () { toast('Diagnostics could not be copied.'); });
    });
    var send = $('btn-study-ask-send');
    if (send) send.addEventListener('click', studyAskSend);
    var askInput = $('study-ask-input');
    if (askInput) askInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); studyAskSend(); }
    });
    var teachSelect = $('study-teach-concept');
    if (teachSelect) teachSelect.addEventListener('change', function () {
      studyV2.teachConceptId = teachSelect.value;
      studyV2.teachResult = null;
      studyV2.teachGrade = null;
      studyV2PersistView();
      renderStudyTeach();
    });
    var teachStart = $('btn-study-teach-start');
    if (teachStart) teachStart.addEventListener('click', function () {
      if (!lpBridge.connected() || !studyV2.teachConceptId || studyV2.teachLoading) return;
      studyV2.teachLoading = true;
      studyV2.teachResult = null;
      studyV2.teachGrade = null;
      renderStudyTeach();
      // Subject scope: teach the owning lecture's real concept row.
      var teachConcept = ((studyV2.content && studyV2.content.concepts) || []).filter(function (c) {
        return c.id === studyV2.teachConceptId;
      })[0] || {};
      var teachOwned = !!(teachConcept.origin_job_id && teachConcept.origin_concept_id);
      if (!teachOwned && inGroupScope()) {
        studyV2.teachLoading = false;
        ownerMissingToast();
        renderStudyTeach();
        return;
      }
      lpBridge.call('study_v2_teach_me', {
        job_id: teachOwned ? teachConcept.origin_job_id : LP.state.jobId,
        concept_id: teachOwned ? teachConcept.origin_concept_id : studyV2.teachConceptId
      }).then(function (result) {
        if (!result || result.ok === false) {
          studyV2.teachLoading = false;
          toast((result && result.error) || 'Teach Me could not start.');
          renderStudyTeach();
        }
      }).catch(function () {
        studyV2.teachLoading = false;
        toast('Teach Me could not start.');
        renderStudyTeach();
      });
    });
    // Source navigation + edit/delete/explain (delegated)
    var concepts = $('study-concepts-list');
    if (concepts) concepts.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) { navigateStudySource(t); return; }
      var edit = e.target.closest('.study-edit');
      if (edit) {
        var editOwner = studyItemOwner(edit, edit.dataset.id);
        if (!editOwner) { ownerMissingToast(); return; }
        studyV2EditItem(edit.dataset.kind, edit.dataset.id, editOwner); return;
      }
      var del = e.target.closest('.study-delete');
      if (del) {
        var delOwner = studyItemOwner(del, del.dataset.id);
        if (!delOwner) { ownerMissingToast(); return; }
        studyV2DeleteItem(del.dataset.kind, del.dataset.id, delOwner); return;
      }
      var regenerate = e.target.closest('.study-regenerate');
      if (regenerate) {
        var regenOwner = studyItemOwner(regenerate, regenerate.dataset.id);
        if (!regenOwner) { ownerMissingToast(); return; }
        studyV2RegenerateItem(regenerate.dataset.kind, regenerate.dataset.id, regenOwner); return;
      }
      var explain = e.target.closest('.study-explain');
      if (explain) { studyV2ExplainItem(explain.dataset.id); }
    });
    if (concepts) concepts.addEventListener('change', function (e) {
      var select = e.target.closest('.study-mastery-select');
      if (!select || !lpBridge.connected()) return;
      var masteryOwner = studyItemOwner(select, select.dataset.conceptId);
      if (!masteryOwner) { ownerMissingToast(); studyV2Load(); return; }
      lpBridge.call('study_v2_set_mastery', {
        job_id: masteryOwner.job_id,
        concept_id: masteryOwner.id,
        mastery: select.value
      }).then(function (result) {
        // A rejected call RESOLVES with {ok:false}; only transport errors
        // reject. Without this check the select silently snapped back.
        if (result && result.ok === false) {
          toast((result && result.error) || 'Mastery could not be updated.');
        }
        studyV2Load();
      }).catch(function () {
        toast('Mastery could not be updated.');
        studyV2Load();
      });
    });
    var guideRoot = $('study-guide-root');
    if (guideRoot) guideRoot.addEventListener('click', function (e) {
      var source = e.target.closest('.study-source');
      if (source) navigateStudySource(source);
    });
    var flashRoot = $('study-flashcards-root');
    if (flashRoot) flashRoot.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) navigateStudySource(t);
      var edit = e.target.closest('.study-edit');
      if (edit) studyV2EditItem(edit.dataset.kind, edit.dataset.id);
      var regenerate = e.target.closest('.study-regenerate');
      if (regenerate) studyV2RegenerateItem(regenerate.dataset.kind, regenerate.dataset.id);
      var del = e.target.closest('.study-delete');
      if (del) studyV2DeleteItem(del.dataset.kind, del.dataset.id);
    });
    var quickRoot = $('study-quick-root');
    if (quickRoot) quickRoot.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) navigateStudySource(t);
      var quickAction = e.target.closest('[data-quick-action]');
      if (quickAction) {
        var action = quickAction.dataset.quickAction;
        if (action === 'reveal') { studyV2.quickRevealed = true; renderQuickStudy(); }
        else if (action === 'result-right') quickStudyFinishItem(true);
        else if (action === 'result-wrong') quickStudyFinishItem(false);
        else if (action === 'continue') {
          studyV2.quickIndex++; studyV2.quickAnswered = false; studyV2.quickSelected = null;
          studyV2PersistView(); renderQuickStudy();
        } else if (action === 'review-weak') {
          studyV2.quickSession = null; studyV2.quickSummary = null; studyV2.reviewOnly = true;
          studyV2.flashFilterIds = null; studyV2.flashIndex = 0; setStudyV2Mode('flashcards');
        } else if (action === 'done') {
          studyV2.quickSession = null; studyV2.quickSummary = null; setStudyV2Mode('overview');
        }
        return;
      }
      var quickOpt = e.target.closest('[data-quick-opt]');
      if (quickOpt) quickStudySelectQuiz(Number(quickOpt.dataset.quickOpt));
    });
    if (quickRoot) {
      quickRoot.tabIndex = 0;
      quickRoot.addEventListener('keydown', function (e) {
        if (e.code !== 'Space' || studyV2.mode !== 'quick') return;
        var action = quickRoot.querySelector('[data-quick-action="reveal"]');
        if (action) { e.preventDefault(); action.click(); }
      });
    }
    if (flashRoot) {
      flashRoot.tabIndex = 0;
      flashRoot.addEventListener('keydown', function (e) {
        if (e.code !== 'Space' || studyV2.mode !== 'flashcards') return;
        var action = flashRoot.querySelector('#btn-study-flash-show');
        if (action) { e.preventDefault(); action.click(); }
      });
    }
    var quizRoot = $('study-quiz-root');
    if (quizRoot) quizRoot.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) navigateStudySource(t);
      var edit = e.target.closest('.study-edit');
      if (edit) studyV2EditItem(edit.dataset.kind, edit.dataset.id);
      var regenerate = e.target.closest('.study-regenerate');
      if (regenerate) studyV2RegenerateItem(regenerate.dataset.kind, regenerate.dataset.id);
      var del = e.target.closest('.study-delete');
      if (del) studyV2DeleteItem(del.dataset.kind, del.dataset.id);
    });
    var askFeed = $('study-ask-feed');
    if (askFeed) askFeed.addEventListener('click', function (e) {
      var chip = e.target.closest('.study-ask-chip');
      if (chip) {
        $('study-ask-input').value = chip.dataset.q;
        studyAskSend();
        return;
      }
      var t = e.target.closest('.study-source');
      if (t) navigateStudySource(t);
    });
    var teachRoot = $('study-teach-root');
    if (teachRoot) teachRoot.addEventListener('click', function (e) {
      var source = e.target.closest('.study-source');
      if (source) { navigateStudySource(source); return; }
      var gradeButton = e.target.closest('#btn-study-teach-grade');
      if (!gradeButton || !studyV2.teachResult || !lpBridge.connected()) return;
      var answer = (($('study-teach-answer') || {}).value || '').trim();
      if (!answer) return;
      gradeButton.disabled = true;
      gradeButton.textContent = 'Checking…';
      lpBridge.call('study_v2_grade_short_answer', {
        job_id: LP.state.jobId,
        question_id: 'teach:' + studyV2.teachConceptId,
        question: studyV2.teachResult.check_question,
        answer: answer,
        rubric: studyV2.teachResult.rubric || '',
        concept_ids: [studyV2.teachConceptId]
      }).then(function (result) {
        if (!result || result.ok === false) {
          gradeButton.disabled = false;
          gradeButton.textContent = 'Check answer';
          toast((result && result.error) || 'This answer could not be checked.');
        }
      }).catch(function () {
        gradeButton.disabled = false;
        gradeButton.textContent = 'Check answer';
        toast('This answer could not be checked.');
      });
    });
  }

  function studyV2EditItem(kind, id, owner) {
    owner = owner || { job_id: LP.state.jobId, id: id };
    if (!id || !lpBridge.connected()) return;
    var content = studyV2.content || { concepts: [], flashcards: [], quiz: [] };
    var item = null, field = 'title', label = 'Title';
    if (kind === 'concept') {
      item = (content.concepts || []).filter(function (c) { return c.id === id; })[0];
      field = 'title'; label = 'Title';
    } else if (kind === 'flashcard') {
      item = (content.flashcards || []).filter(function (c) { return c.id === id; })[0];
      field = 'front'; label = 'Front';
    } else if (kind === 'quiz') {
      item = (content.quiz || []).filter(function (c) { return c.id === id; })[0];
      field = 'question'; label = 'Question';
    }
    if (!item) return;
    var current = item[field] || '';
    lpModal({
      title: 'Edit ' + (kind || 'item'),
      bodyHtml: '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px">' + esc(label) + '</label>' +
        '<input id="lp-study-edit-input" type="text" spellcheck="false" value="' + esc(current) + '" style="width:100%;box-sizing:border-box;font:600 14px \'JetBrains Mono\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">',
      actions: [
        { label: 'Cancel' },
        { label: 'Save', primary: true, onClick: function () {
          var input = $('lp-study-edit-input');
          var value = (input && input.value || '').trim();
          if (!value || !lpBridge.connected()) return true;
          var payload = { job_id: owner.job_id, kind: kind, id: owner.id };
          if (kind === 'concept') payload.title = value;
          else if (kind === 'flashcard') payload.front = value;
          else if (kind === 'quiz') payload.question = value;
          lpBridge.call('study_v2_edit', payload)
            .then(function (result) {
              if (result && result.ok === false) {
                toast((result && result.error) || 'This edit could not be saved.');
              }
              studyV2Load();
            })
            .catch(function () { toast('This edit could not be saved.'); });
        } }
      ]
    });
    setTimeout(function () { var i = $('lp-study-edit-input'); if (i) { i.focus(); i.select(); } }, 30);
  }

  function studyV2DeleteItem(kind, id, owner) {
    if (!id || !lpBridge.connected()) return;
    owner = owner || { job_id: LP.state.jobId, id: id };
    var noun = kind === 'concept' ? 'concept' : kind === 'flashcard' ? 'flashcard' : 'question';
    lpModal({
      title: 'Delete this ' + noun + '?',
      bodyHtml: 'This removes it from the Study pack. Related cards and questions are removed too.',
      actions: [
        { label: 'Cancel' },
        { label: 'Delete', danger: true, onClick: function () {
          lpBridge.call('study_v2_delete', { job_id: owner.job_id, kind: kind, id: owner.id })
            .then(function (result) {
              // A destructive action that quietly does nothing is worse than
              // one that errors: the user believes the item is gone.
              if (result && result.ok === false) {
                toast((result && result.error) || ('This ' + noun + ' could not be deleted.'));
              }
              studyV2Load();
            })
            .catch(function () { toast('This ' + noun + ' could not be deleted.'); });
        } }
      ]
    });
  }

  /* In Subject scope the rendered concept is a cross-lecture merge whose id is
     not in any lecture's store. The card carries the owning lecture + the real
     concept id; fall back to the active lecture for ordinary single-lecture
     scope, where the displayed id IS the stored id. */
  function inGroupScope() {
    return !!(studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all');
  }

  /* Returns null when the owning row cannot be established. Callers MUST treat
     null as "refuse and explain".

     The old fallback to {job_id: LP.state.jobId, id: displayedId} was unsafe in
     subject scope: a group concept id is a free-form model string, per-lecture
     ids are short and sequential ("c7", "concept_2"), and they collide across
     lectures. A collision would have set mastery on -- or DELETED, with its
     cascade into flashcards/quiz/guide -- an unrelated concept in whatever
     lecture happened to be active, and reported success. In single-lecture
     scope the displayed id IS the stored id, so the fallback stays there. */
  function studyItemOwner(el, displayedId) {
    var jobId = (el && el.dataset && el.dataset.jobId) || '';
    var originId = (el && el.dataset && el.dataset.originId) || '';
    if (jobId && originId) return { job_id: jobId, id: originId };
    if (inGroupScope()) return null;
    return { job_id: LP.state.jobId, id: displayedId };
  }

  function ownerMissingToast() {
    toast('This concept could not be traced back to one lecture. Open that lecture from the Scope menu to change it.');
  }

  function studyV2RegenerateItem(kind, id, owner) {
    if (!kind || !id || !lpBridge.connected()) return;
    owner = owner || { job_id: LP.state.jobId, id: id };
    lpBridge.call('study_v2_regenerate', {
      job_id: owner.job_id,
      kind: kind,
      id: owner.id
    }).then(function (result) {
      if (!result || result.ok === false) {
        toast((result && result.error) || 'This Study item could not be regenerated.');
        return;
      }
      toast('Refreshing only the connected Study items…');
    }).catch(function () {
      toast('This Study item could not be regenerated.');
    });
  }

  function studyV2ExplainItem(id) {
    if (!id || !lpBridge.connected()) return;
    var content = studyV2.content || { concepts: [] };
    var concept = (content.concepts || []).filter(function (c) { return c.id === id; })[0];
    if (!concept) return;
    setStudyV2Mode('ask');
    var input = $('study-ask-input');
    if (input) input.value = 'Explain "' + (concept.title || 'this concept') + '" in this lecture';
    studyAskSend();
  }

  function navigateStudySource(el) {
    var targetJobId = el.dataset.job || '';
    var segment = el.dataset.segment;
    var ms = Number(el.dataset.ms || 0);
    var slide = el.dataset.slide;

    if (targetJobId && typeof LP !== 'undefined' && LP.state && targetJobId !== LP.state.jobId) {
      selectJob(targetJobId, { screen: slide != null ? 'review' : 'transcript' });
      if (slide != null) {
        setTimeout(function () {
          var slides = LP.data.slides || [];
          var idx = slides.findIndex(function (s) { return String(s.image_filename) === String(slide) || String(s.index) === String(slide); });
          if (idx >= 0) {
            LP.state.viewingSlide = idx;
            renderSlides();
          }
        }, 150);
      } else if (segment != null) {
        setTimeout(function () {
          var blocks = document.querySelectorAll('#transcript-blocks [data-transcript-time], #transcript-blocks [data-start]');
          var target = null;
          blocks.forEach(function (b) {
            var raw = b.dataset.start;
            if (raw == null) {
              var parts = String(b.dataset.transcriptTime || '').split(':').map(Number);
              raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : (parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0));
            }
            if (Number(raw) <= ms / 1000) target = b;
          });
          if (target) {
            target.scrollIntoView({ block: 'center' });
            target.classList.add('transcript-target-highlight');
            setTimeout(function () { target.classList.remove('transcript-target-highlight'); }, 2000);
          }
        }, 220);
      }
      return;
    }

    if (slide != null) {
      // Navigate to the slides/review source.
      setScreen('review');
      var slides = LP.data.slides || [];
      var idx = slides.findIndex(function (s) { return String(s.image_filename) === String(slide) || String(s.index) === String(slide); });
      if (idx >= 0) {
        LP.state.viewingSlide = idx;
        renderSlides();
      }
      return;
    }
    if (segment != null) {
      setScreen('transcript');
      // Scroll to the transcript segment by timestamp.
      setTimeout(function () {
        var blocks = document.querySelectorAll('#transcript-blocks [data-transcript-time], #transcript-blocks [data-start]');
        var target = null;
        blocks.forEach(function (b) {
          var raw = b.dataset.start;
          if (raw == null) {
            var parts = String(b.dataset.transcriptTime || '').split(':').map(Number);
            raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : (parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0));
          }
          if (Number(raw) <= ms / 1000) target = b;
        });
        if (target) target.scrollIntoView({ block: 'center' });
      }, 180);
    }
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
    if (!LP.motion.reduced()) {
      var shownId = { chat: 'pane-chat', quiz: 'pane-quiz', flash: 'pane-flash', notes: 'pane-notes' }[tab];
      var shown = shownId && $(shownId);
      if (shown) {
        shown.classList.remove('lp-anim-fade');
        void shown.offsetWidth; // force reflow so the class re-triggers every switch
        shown.classList.add('lp-anim-fade');
      }
    }
    if (tab === 'quiz') renderQuiz();
    if (tab === 'flash') renderCard();
  }

  function setJobsEmpty(empty) {
    LP.state.jobsEmpty = !!empty;
    var jobs = $('home-jobs'), emptyState = $('home-empty'), actionBar = $('jobs-actionbar');
    if (jobs) jobs.hidden = !!empty;
    if (emptyState) emptyState.hidden = !empty;
    if (actionBar) actionBar.hidden = !!empty;
    if (empty) {
      LP.state.selecting = false;
      LP.state.selected = {};
      var selectBar = $('jobs-selectbar');
      if (selectBar) selectBar.hidden = true;
    }
    renderDemoHomeAvailability();
  }

  /* ======================= guided demo lifecycle =======================
     The walkthrough is a self-contained screen. This block owns only the
     durable eligibility state and the optional real bundled-lecture run; it
     performs no live-screen measurement, spotlighting, or geometry work. */
  var DEMO_DRAG_MIME = 'application/x-lecturepack-demo';
  var INTERNAL_JOB_DRAG_MIME = 'application/x-lecturepack-job-ids';
  var internalJobDragIds = [];

  /* ================= drag auto-scroll =================
     ONE manager for every drag, internal and external. Scrolling logic used to
     be absent entirely, so a drag that started at the bottom of a long library
     could never reach the Process tab at the top: the pointer is held down, so
     the wheel is the only other way to move and the drag ends if you release.

     It lives here, not inside #dropzone / #jobs-grid / the Process targets,
     because a drag crosses all of them and each would otherwise need its own
     copy, its own rAF loop, and its own teardown.

     The scroll container is resolved from the POINTER, not from the drag
     source, so nested scrollers (the Process queue panes) work with no extra
     registration. The rAF loop is what makes "hold still at the edge" scroll:
     dragover only fires when the pointer MOVES, so a velocity driven purely by
     events would stall the moment the user stops moving -- which is exactly
     what a user does when waiting for the list to come to them. */
  var dragScroll = (function () {
    var EDGE = 72;          // px from an edge where scrolling begins
    var MAX_SPEED = 24;     // px per frame at the very edge
    var frame = 0;
    var target = null;
    var vx = 0;
    var vy = 0;

    function canScroll(el) {
      if (!el || el === document || el.nodeType !== 1) return false;
      var style;
      try { style = getComputedStyle(el); } catch (e) { return false; }
      var oy = style.overflowY, ox = style.overflowX;
      var scrollsY = (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 1;
      var scrollsX = (ox === 'auto' || ox === 'scroll') && el.scrollWidth > el.clientWidth + 1;
      return scrollsY || scrollsX;
    }

    function containerAt(x, y) {
      var el = null;
      try { el = document.elementFromPoint(x, y); } catch (e) { el = null; }
      while (el && el !== document.body && el !== document.documentElement) {
        if (canScroll(el)) return el;
        el = el.parentElement;
      }
      // Fall back to the page scroller when the pointer is over static content.
      var doc = document.scrollingElement || document.documentElement;
      return canScroll(doc) ? doc : null;
    }

    // 0 outside the edge zone, ramping to MAX_SPEED at the boundary itself.
    function speed(distance) {
      if (distance >= EDGE) return 0;
      var ratio = (EDGE - Math.max(0, distance)) / EDGE;
      return Math.max(1, Math.round(ratio * ratio * MAX_SPEED));
    }

    function step() {
      frame = 0;
      if (!target || (!vx && !vy)) return;
      if (vy) target.scrollTop += vy;
      if (vx) target.scrollLeft += vx;
      frame = requestAnimationFrame(step);
    }

    function ensureRunning() {
      if (!frame && (vx || vy)) frame = requestAnimationFrame(step);
    }

    return {
      update: function (clientX, clientY) {
        var el = containerAt(clientX, clientY);
        if (!el) { this.stop(); return; }
        var rect = (el === document.scrollingElement || el === document.documentElement)
          ? { top: 0, left: 0, bottom: window.innerHeight, right: window.innerWidth }
          : el.getBoundingClientRect();
        // Outside the container entirely -> no scrolling, no stale velocity.
        if (clientY < rect.top - EDGE || clientY > rect.bottom + EDGE ||
            clientX < rect.left - EDGE || clientX > rect.right + EDGE) {
          this.stop();
          return;
        }
        target = el;
        var up = speed(clientY - rect.top);
        var down = speed(rect.bottom - clientY);
        var left = speed(clientX - rect.left);
        var right = speed(rect.right - clientX);
        vy = up ? -up : (down ? down : 0);
        vx = left ? -left : (right ? right : 0);
        // Do not fight a container already at its limit.
        if (vy < 0 && target.scrollTop <= 0) vy = 0;
        if (vy > 0 && target.scrollTop >= target.scrollHeight - target.clientHeight - 1) vy = 0;
        if (vx < 0 && target.scrollLeft <= 0) vx = 0;
        if (vx > 0 && target.scrollLeft >= target.scrollWidth - target.clientWidth - 1) vx = 0;
        if (!vx && !vy) { if (frame) { cancelAnimationFrame(frame); frame = 0; } return; }
        ensureRunning();
      },
      stop: function () {
        if (frame) cancelAnimationFrame(frame);
        frame = 0; target = null; vx = 0; vy = 0;
      },
      // test seam: report whether a scroll is currently running
      _active: function () { return !!frame; }
    };
  }());

  function persistGuidedTourState(status) {
    if (!status || !lpBridge.connected()) return Promise.resolve(null);
    return lpBridge.call('set_guided_tour_state', { status: status }).then(function (value) {
      var result = parseBridgeResult(value);
      if (!result || result.ok !== true) {
        toast('LecturePack could not save the demo state.');
        return result;
      }
      if (result.guided_tour) applyGuidedTourEligibility(result);
      return result;
    }, function () {
      toast('LecturePack could not save the demo state.');
      return null;
    });
  }

  var guidedDemo = GuidedDemoSessionModel();
  var slideDetectionPreset = SlideDetectionPresetModel();
  var demoAdmissionAvailable = false;
  var guidedTourEligibility = null;
  var demoCleanupRequested = false;
  var demoCleanupConfirmed = false;

  function applyGuidedTourEligibility(payload) {
    var source = payload && (payload.guided_tour || payload.guided_tour_state || payload.tour);
    if (!source && payload && typeof payload.tour_eligible === 'boolean') source = payload;
    if (!source || typeof source !== 'object') return false;
    var eligible = source.eligible === true;
    if (source.eligible === undefined) eligible = source.completed !== true && source.skipped !== true;
    if (source.completed === true || source.skipped === true) eligible = false;
    guidedTourEligibility = {
      version: String(source.version || source.current_version || ''),
      eligible: eligible,
      completed: source.completed === true,
      skipped: source.skipped === true
    };
    renderDemoHomeAvailability();
    return true;
  }

  function tourEligibilityAllowsOffer() {
    if (demoCompleted()) return false;
    if (guidedTourEligibility) return guidedTourEligibility.eligible === true;
    return !lpBridge.connected();
  }

  function setDemoAdmissionAvailable(available) {
    var next = available === true;
    demoAdmissionAvailable = next;
    var onboarding = $('settings-onboarding'), replay = $('btn-replay-tour');
    if (onboarding) onboarding.hidden = !next;
    if (replay) replay.disabled = !next;
    renderDemoHomeAvailability();
    if (!next) {
      if (LP.state.screen === 'demo') setScreen('home');
      renderSlideDetectionPreset();
      endGuidedDemo('runtime_unavailable', true);
      renderDemoCard();
      return;
    }
    renderDemoCard();
  }

  function renderDemoHomeAvailability() {
    var demoHome = $('home-demo');
    if (demoHome) demoHome.hidden = !(demoAdmissionAvailable && tourEligibilityAllowsOffer());
  }

  function stageLabel(name) {
    var labels = { prepare: 'Preparing demo', inspect: 'Inspecting video', extract_audio: 'Extracting audio', transcribe: 'Transcribing audio', detect_slides: 'Detecting slides', align: 'Aligning notes', review_ready: 'Preparing review', export: 'Building Study Pack', complete: 'Complete' };
    return labels[name] || friendlyProcessingLabel(name) || 'Preparing demo';
  }

  function guidedDemoSensitivityLocked() {
    return guidedDemo.snapshot().active;
  }

  // Processing settings are snapshotted at start. Lock them for both the
  // bundled demo and normal jobs so a visible mid-run change never lies.
  function renderSlideDetectionPreset() {
    var group = $('proc-sensitivity'), note = $('proc-sensitivity-note');
    if (!group) return;
    var state = slideDetectionPreset.snapshot(),
        demoLocked = guidedDemoSensitivityLocked(),
        locked = demoLocked || LP.state.pipelineRunning;
    Array.prototype.forEach.call(group.querySelectorAll('button[data-sens]'), function (button) {
      var active = button.dataset.sens === state.label;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.disabled = locked;
      button.title = demoLocked ? 'Demo processing uses its fixed reliable setting.' :
        (locked ? 'Setting is locked while processing runs.' : '');
      button.style.fontWeight = active ? '700' : '500';
      button.style.borderColor = active ? 'var(--secondary-border)' : 'transparent';
      button.style.background = active ? 'var(--secondary-surface)' : 'transparent';
      button.style.color = active ? 'var(--secondary-text)' : 'var(--muted)';
      button.style.cursor = locked ? 'not-allowed' : 'pointer';
    });
    if (note) note.hidden = !locked;
  }

  function setSlideDetectionPreset(label) {
    if (guidedDemoSensitivityLocked() || LP.state.pipelineRunning) return;
    var state = slideDetectionPreset.select(label);
    renderSlideDetectionPreset();
    lpBridge.call('set_setting', 'slide_detection_preset', state.preset);
  }

  function renderDemoCard() {
    var card = $('glowing-demo-card'), status = $('demo-card-status'), action = $('demo-card-action');
    if (!card || !status || !action) return;
    var d = guidedDemo.snapshot();
    var firstRunUnavailable = !demoAdmissionAvailable;
    card.disabled = firstRunUnavailable || d.status === 'starting' || d.status === 'cancelling';
    card.setAttribute('aria-disabled', card.disabled ? 'true' : 'false');
    card.title = firstRunUnavailable ? 'Complete runtime setup before opening the demo.' : '';
    card.dataset.demoState = d.status === 'failed' || d.status === 'error' ? 'error' : (d.active ? 'running' : 'idle');
    if (firstRunUnavailable) {
      status.textContent = 'The demo will be available after runtime setup is ready.';
      action.textContent = 'Runtime setup required';
      return;
    }
    if (d.status === 'error' || d.status === 'failed') {
      status.textContent = d.error || 'The demo lecture could not start.';
      action.textContent = 'Try again';
      return;
    }
    if (d.active) {
      status.textContent = stageLabel(d.stage) + ' · ' + Math.round(d.progress) + '%';
      action.textContent = d.status === 'starting' ? 'Starting…' : d.status === 'cancelling' ? 'Stopping…' : 'End demo';
      return;
    }
    var idleAction = demoCompleted() ? 'Use demo video' : 'Take the 60-second tour';
    if (d.status === 'ended') {
      status.textContent = 'Demo cleaned up.';
      action.textContent = idleAction;
      return;
    }
    status.textContent = demoCompleted()
      ? 'Process this real 10-second lecture again.'
      : 'See real LecturePack output from a 10-second lecture. No processing yet.';
    action.textContent = idleAction;
    refreshControlStates();
  }

  function hideModelTooltip() {
    var tooltip = $('ai-model-tooltip');
    if (tooltip) tooltip.hidden = true;
  }

  function showModelTooltip() {
    var value = $('ai-model-name'), tooltip = $('ai-model-tooltip');
    if (!value || !tooltip || !value.textContent || value.textContent === '—') { hideModelTooltip(); return; }
    tooltip.textContent = value.textContent;
    tooltip.hidden = false;
    requestAnimationFrame(function () {
      if (tooltip.hidden) return;
      var rect = value.getBoundingClientRect(), inset = 8, width = tooltip.offsetWidth, height = tooltip.offsetHeight;
      tooltip.style.left = Math.max(inset, Math.min(rect.left, window.innerWidth - width - inset)) + 'px';
      tooltip.style.top = Math.max(inset, Math.min(rect.bottom + inset, window.innerHeight - height - inset)) + 'px';
    });
  }

  function setModelValue(value) {
    var model = $('ai-model-name');
    if (!model) return;
    var text = String(value || '');
    var friendly = text ? text.split(/[\\/]/).pop() : '';
    model.textContent = friendly || '—';
    if (!text) hideModelTooltip();
  }

  function setWhisperModelPath(value) {
    var raw = String(value || ''), path = $('setting-model-path'), name = $('setting-model-name');
    if (path && raw) path.textContent = raw;
    if (!name) return;
    if (!raw) { name.textContent = 'Bundled Whisper Base English model'; return; }
    var file = raw.split(/[\\/]/).pop();
    var friendly = /base\.en/i.test(file) ? 'Whisper Base English model' : 'Whisper model · ' + file;
    name.textContent = friendly;
  }

  function wireModelTooltip() {
    var model = $('ai-model-name');
    if (!model) return;
    model.addEventListener('mouseenter', showModelTooltip);
    model.addEventListener('mouseleave', hideModelTooltip);
    model.addEventListener('focus', showModelTooltip);
    model.addEventListener('blur', hideModelTooltip);
  }

  function parseBridgeResult(value) {
    if (typeof value === 'string') { try { return JSON.parse(value); } catch (e) { return null; } }
    return value && typeof value === 'object' ? value : null;
  }

  function applyAppVersion(value) {
    var version = String(value == null ? '' : value).trim();
    if (!version || version === '0.0.0') return;
    LP.data.version = version;
    var target = $('app-version');
    if (target) target.textContent = version;
  }

  function loadAppVersion() {
    var electron = window.lecturePackElectron;
    if (!electron || typeof electron.getAppVersion !== 'function') return;
    try {
      Promise.resolve(electron.getAppVersion()).then(applyAppVersion, function () {});
    } catch (e) {}
  }

  function replayDemoScreen() {
    function begin() {
      demoSave({ seen: false, completed: false, chapter: 1 });
      if (guidedTourEligibility) {
        guidedTourEligibility.eligible = true;
        guidedTourEligibility.completed = false;
        guidedTourEligibility.skipped = false;
      }
      renderDemoHomeAvailability();
      openDemo(1);
      return true;
    }
    if (!demoAdmissionAvailable) return Promise.resolve(false);
    if (!lpBridge.connected()) return Promise.resolve(begin());
    return lpBridge.call('replay_guided_tour').then(function (value) {
      var result = parseBridgeResult(value);
      if (!result || result.ok !== true || result.ready_to_start !== true) {
        toast((result && result.error) || 'Could not replay the demo.');
        return false;
      }
      if (result.guided_tour) applyGuidedTourEligibility(result);
      return begin();
    }, function () {
      toast('Could not replay the demo.');
      return false;
    });
  }

  function endGuidedDemo(reason, force) {
    var current = guidedDemo.snapshot();
    force = force === true || reason === 'tour_exit' || reason === 'tour_complete';
    if (!force && !current.active) return;
    if (demoCleanupConfirmed || demoCleanupRequested) return;
    var endingAttempt = current.attempt, endingOperationId = current.operationId, endingSessionId = current.sessionId;
    demoCleanupRequested = true;
    if (current.active) { guidedDemo.cancelling(); renderDemoCard(); }
    if (!lpBridge.connected()) {
      if (current.active) guidedDemo.settleEndResult({ ok: false, error: 'The demo needs the LecturePack desktop app to stop safely.' }, endingAttempt, endingOperationId, endingSessionId);
      demoCleanupRequested = false;
      renderDemoCard();
      return;
    }
    lpBridge.endDemoJob(reason || 'ended').then(function (value) {
      var result = parseBridgeResult(value);
      if (result && result.ok === true) demoCleanupConfirmed = true;
      else demoCleanupRequested = false;
      if (current.active && !guidedDemo.isCurrentAttempt(endingAttempt, endingOperationId, endingSessionId)) return;
      if (current.active) guidedDemo.settleEndResult(result, endingAttempt, endingOperationId, endingSessionId);
      renderDemoCard();
    }, function () {
      demoCleanupRequested = false;
      if (current.active && !guidedDemo.isCurrentAttempt(endingAttempt, endingOperationId, endingSessionId)) return;
      if (current.active) guidedDemo.settleEndResult({ ok: false, error: 'Could not confirm that the demo stopped. Try again.' }, endingAttempt, endingOperationId, endingSessionId);
      renderDemoCard();
    });
  }

  function receiveDemoEvent(value) {
    var event = parseBridgeResult(value);
    if (!event) return;
    var before = guidedDemo.snapshot();
    if (!before.operationId && before.status === 'starting' && event.status === 'started') {
      guidedDemo.started({ ok: true, operation_id: event.operation_id, session_id: event.session_id }, before.attempt);
    }
    var handled = guidedDemo.event(event);
    if (!handled.accepted) return;
    if (event.status === 'cleaned' || event.status === 'failed') {
      if (event.status === 'cleaned') demoCleanupConfirmed = true;
      demoCleanupRequested = true;
    }
    var eventStage = String(event.stage || '').toLowerCase().replace(/[\s-]+/g, '_');
    if (eventStage === 'review_ready' && LP.state.screen === 'process') setScreen('review');
    renderDemoCard();
    renderSlideDetectionPreset();
    if (event.status === 'failed') toast(event.error || 'Demo processing failed.');
  }

  function wireDemoLifecycle() {
    $('btn-replay-tour').addEventListener('click', replayDemoScreen);
    var demoCard = $('glowing-demo-card');
    demoCard.addEventListener('click', function () {
      if (demoCard.disabled) return;
      if (guidedDemo.snapshot().active) { endGuidedDemo('user_cancelled'); return; }
      if (!demoCompleted()) { openDemo(1); return; }
      runDemoForReal();
    });
    demoCard.addEventListener('dragstart', function (e) {
      if (demoCard.disabled) { e.preventDefault(); return; }
      if (!e.target || e.target.tagName !== 'IMG') { e.preventDefault(); return; }
      if (!e.dataTransfer) return;
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData(DEMO_DRAG_MIME, 'polar-bears-10s');
      e.dataTransfer.setData('text/plain', 'Polar Bears 10s Demo.mp4');
    });
    demoCard.addEventListener('dragend', clearDemoDropState);
  }

  function hasDemoDrag(e) {
    var types = e.dataTransfer && e.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, DEMO_DRAG_MIME) !== -1;
  }

  function clearDemoDropState() {
    var dz = $('dropzone');
    if (dz) dz.classList.remove('lp-demo-drop-hover');
  }

  function useDroppedDemo() {
    if (!demoAdmissionAvailable) return;
    if (guidedDemo.snapshot().active) {
      setScreen('process');
      return;
    }
    runDemoForReal();
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
          + (on ? 'var(--orange)' : 'transparent') + ';background:' + (on ? 'var(--orange-soft)' : 'var(--panel)') + ';color:' + (on ? 'var(--orange-ink)' : 'var(--ink)');
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
      d.ready ? 'Ready.' : (d.message || (d.state === 'need_engine'
        ? 'Install the optional local AI engine to enable Smart Study.'
        : 'Smart Study is optional; Built-in Study is ready.'));

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
      setFill('ss-bar', pct != null ? pct : (st === 'testing' ? 100 : 3));
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
    var status = $('ss-settings-msg');
    if (!lpBridge.connected()) {
      if (status) status.textContent = 'Smart Study setup is unavailable in browser preview; Built-in Study is ready.';
      toast('Preview mode — Smart Study needs the app');
      return;
    }
    if (status) status.textContent = 'Starting Smart Study setup…';
    lpBridge.call('install_smart_study', ssChosenPreset(LP.state.smartStudy) || 'balanced').then(function (value) {
      var result = parseBridgeResult(value);
      if (!result) { if (status) status.textContent = 'Smart Study setup is unavailable in this build.'; return; }
      if (result.error) { if (status) status.textContent = 'Smart Study setup failed: ' + result.error; return; }
      if (result.ok === false) { if (status) status.textContent = result.message || 'Smart Study setup could not start.'; return; }
      if (status) status.textContent = result.message || 'Smart Study setup started…';
    }, function (error) {
      if (status) status.textContent = 'Smart Study setup failed: ' + (error && error.message || 'unknown error');
    });
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

  function highlightScrubTick(slideIndex) {
    var ticks = document.querySelectorAll('.lp-tick');
    Array.prototype.forEach.call(ticks, function (t) {
      if (t.dataset && t.dataset.slide === String(slideIndex)) {
        t.classList.add('is-snapped');
      } else {
        t.classList.remove('is-snapped');
      }
    });
  }

  // The hover preview is portaled to <body> so it escapes the timeline's
  // overflow clipping; positioned with fixed coords + collision-aware flip.
  function hideScrub() {
    var w = $('scrub-wrap'), pv = $('scrub-preview');
    if (w) w.hidden = true;
    if (pv) pv.style.display = 'none';
    highlightScrubTick(-1);
  }

  function bestTimelineSlide(e) {
    var strip = $('timeline-strip');
    if (!strip || !LP.data.slides.length || !e) return null;
    var r = strip.getBoundingClientRect();
    if (!r.width) return null;
    var pct = Math.max(0, Math.min(100, (e.clientX - r.left) / r.width * 100));
    var best = LP.data.slides[0], bd = Infinity, bestIndex = 0;
    LP.data.slides.forEach(function (s, i) {
      var d = Math.abs(s.pct - pct);
      if (d < bd) { bd = d; best = s; bestIndex = i; }
    });
    best._i = bestIndex;
    return { slide: best, rect: r };
  }

  function onScrub(e) {
    var nearest = bestTimelineSlide(e);
    if (!nearest) return;
    var strip = $('timeline-strip'), best = nearest.slide, r = nearest.rect;
    highlightScrubTick(best._i);

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

  var timelinePointerDrag = { active: false, pointerId: null };
  function beginTimelinePointerDrag(e) {
    if (!LP.data.slides.length || e.button !== undefined && e.button !== 0) return;
    timelinePointerDrag.active = true;
    timelinePointerDrag.pointerId = e.pointerId;
    e.preventDefault();
    var strip = $('timeline-strip');
    if (strip && strip.setPointerCapture && e.pointerId !== undefined) {
      try { strip.setPointerCapture(e.pointerId); } catch (err) {}
    }
    onScrub(e);
  }
  function moveTimelinePointerDrag(e) {
    if (!timelinePointerDrag.active || (e.pointerId !== undefined && e.pointerId !== timelinePointerDrag.pointerId)) return;
    e.preventDefault();
    onScrub(e);
  }
  function endTimelinePointerDrag(e) {
    if (!timelinePointerDrag.active || (e.pointerId !== undefined && e.pointerId !== timelinePointerDrag.pointerId)) return;
    var nearest = bestTimelineSlide(e);
    timelinePointerDrag.active = false;
    timelinePointerDrag.pointerId = null;
    var strip = $('timeline-strip');
    if (strip && strip.releasePointerCapture && e.pointerId !== undefined) {
      try { strip.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    if (!nearest) { hideScrub(); return; }
    // The preview above is renderer-only. Commit one viewed-slide change on
    // release so a drag never reloads the backend once per pixel.
    LP.state.viewingSlide = nearest.slide._i;
    renderSlides();
  }

  /* ======================= export ======================= */

  function startExport() {
    // N-2/N-4: guard the invalid state first, and only enter the exporting
    // state when the backend reports REAL progress. A failed export shows one
    // friendly message and leaves no phantom progress bar behind.
    if (!LP.state.jobId) { toast('Load a lecture first — there is nothing to export yet.'); return; }
    if (lpBridge.connected()) {
      var formats = LP.data.exportFormats.filter(function (f) { return f.sel; }).map(function (f) { return f.key; });
      lpBridge.call('export_all', JSON.stringify(formats)).then(function (value) {
        var result = parseBridgeResult(value);
        if (result && result.ok === false && LP.state.exportPhase === 'running') {
          LP.state.exportPhase = 'idle'; renderExportPhase();
        }
      });
    } else {
      LP.state.exportPhase = 'running';
      renderExportPhase();
      setTimeout(function () { LP.state.exportPhase = 'done'; renderExportPhase(); }, 1700);
    }
  }

  /* Rebuilds the study pack so the requested file is refreshed. These used to
     fire and return silently, which read exactly like a dead button. */
  function exportOne(kind, label) {
    if (!LP.state.jobId) { toast('Load a lecture first — there is nothing to export yet.'); return; }
    if (!lpBridge.connected()) { toast('Not connected to the engine — the ' + label + ' could not be rebuilt.'); return; }
    LP.state.exportPhase = 'running';
    renderExportPhase();
    toast('Rebuilding the study pack to refresh the ' + label + '…');
    lpBridge.call('export_one', { kind: kind }).then(function (value) {
      var result = parseBridgeResult(value);
      if (result && result.already_running) {
        toast('An export is already running — the ' + label + ' will be refreshed with it.');
        return;
      }
      if (result && result.ok === false) {
        LP.state.exportPhase = 'idle';
        renderExportPhase();
        toast((result && result.error) || ('The ' + label + ' could not be rebuilt.'));
      }
    }).catch(function () {
      LP.state.exportPhase = 'idle';
      renderExportPhase();
      toast('The ' + label + ' could not be rebuilt.');
    });
  }

  /* ======================= updates / what's new ======================= */

  var UPD_DL_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3"/><path d="m7 10 5 5 5-5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>';

  function _wnBullet(n) {
    return '<div style="display:flex;gap:9px;align-items:flex-start"><span style="width:6px;height:6px;flex:none;border-radius:2px;background:var(--orange);margin-top:7px"></span><span>' + esc(n) + '</span></div>';
  }

  /* Release notes arrive as GitHub-flavoured Markdown and are rendered as flat
     bullets, so raw "## " and "- " markers and code fences would show up
     verbatim. Strip the markers, drop fenced blocks (the notes carry a SHA-256
     block), and keep headings as their own short lines. */
  function _wnNoteLines(raw) {
    var out = [];
    var fenced = false;
    String(raw || '').split(/\r?\n/).forEach(function (line) {
      var t = line.trim();
      if (/^```/.test(t)) { fenced = !fenced; return; }
      if (fenced || !t) return;
      t = t.replace(/^#{1,6}\s*/, '')          // headings
           .replace(/^[-*+]\s+/, '')           // bullets
           .replace(/^\d+\.\s+/, '')           // numbered
           .replace(/\*\*(.+?)\*\*/g, '$1')    // bold
           .replace(/`(.+?)`/g, '$1');         // inline code
      if (t) out.push(t);
    });
    return out;
  }

  function showWhatsNew(info, mode) { // mode: 'available' | 'installed'
    var noteItems = Array.isArray(info.notes) ? info.notes : _wnNoteLines(info.notes);
    LP.state.updateInfo = info;
    LP.state.updateMode = mode;
    $('whatsnew-title').textContent = mode === 'installed' ? 'What’s new in this update' : 'Update available';
    var cur = info.current || LP.data.version || '';
    $('whatsnew-current').textContent = cur ? ('v' + cur) : '';
    $('whatsnew-arrow').style.display = (mode === 'installed' || !cur) ? 'none' : '';
    // Never concatenate a raw value here: an absent version printed the
    // literal "vundefined" in the Settings card (and a bare "v" here).
    var newVersion = String(info.available || info.version || '').replace(/^v/i, '');
    $('whatsnew-version').textContent = newVersion ? ('v' + newVersion) : '';
    $('whatsnew-channel').textContent = info.channel || 'Stable';
    $('whatsnew-channel').style.display = info.channel ? '' : 'none';
    // The updater reports the asset size in BYTES; printing it raw rendered
    // "· 390761266" next to the version.
    $('whatsnew-size').textContent = info.size
      ? ('· ' + (typeof info.size === 'number' ? fmtBytes(info.size) : info.size))
      : '';
    $('whatsnew-date').textContent = info.date || '';
    $('whatsnew-skipnote').hidden = !info.is_skipped;
    ['improvements', 'fixes', 'limitations'].forEach(function (sec) {
      var items = info[sec] || [];
      $('whatsnew-sec-' + sec).hidden = !items.length;
      var list = document.querySelector('[data-sec="' + sec + '"]');
      if (list) list.innerHTML = items.map(_wnBullet).join('');
    });
    var hasSecs = (info.improvements || []).length || (info.fixes || []).length || (info.limitations || []).length;
    $('whatsnew-notes').innerHTML = (!hasSecs ? noteItems : []).map(_wnBullet).join('')
      || (!hasSecs ? '<div style="color:var(--muted)">No release notes.</div>' : '');
    $('whatsnew-progress').hidden = true;
    $('whatsnew-progress-bar').style.width = '0%';
    $('whatsnew-msg').hidden = true;
    updSetPhase(mode === 'installed' ? 'installed' : (info.portable ? 'portable' : 'available'));
    $('whatsnew-overlay').hidden = false;
    if (mode === 'available') {
      $('update-badge').hidden = false;
      $('update-status').textContent = newVersion ? ('v' + newVersion + ' available') : 'An update is available';
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

  function renderUpdaterState(d) {
    if (!d) return;
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
      b.addEventListener('click', function () {
        if (!appSessionRestored) sessionNavigationExplicit = true;
        setScreen(b.dataset.nav);
      });
    });
    $('proc-sensitivity').addEventListener('click', function (e) {
      var button = e.target.closest('button[data-sens]');
      if (!button) return;
      setSlideDetectionPreset(button.dataset.sens);
    });

    // The sidebar lecture chip used to be inert text that just said "No lecture
    // loaded" -- a dead end exactly when the user has nothing and most needs a
    // way forward. It is now a button whose destination depends on state:
    //   lecture loaded -> jump to Review, its workspace (the thing the chip names)
    //   nothing loaded -> go Home and draw the eye to the import card, so the
    //                     empty state points at its own cure in one click.
    // Deliberately does NOT auto-open the native file dialog: this chip is easy
    // to click while exploring, and a surprise OS dialog is a worse outcome than
    // one extra intentional click.
    var sideBtn = $('side-job-btn');
    if (sideBtn) sideBtn.addEventListener('click', function () {
      if (LP.state.jobId) { setScreen('review'); return; }
      setScreen('home');
      var browse = $('btn-browse');
      if (!browse) return;
      var card = browse.closest('.lp-card') || browse.parentElement;
      if (card) {
        // re-trigger the shared entrance so the card announces itself; reuses
        // the MOTION SYSTEM v2 class rather than inventing a highlight effect.
        card.classList.remove('lp-anim-in');
        void card.offsetWidth;                 // force reflow so it replays
        card.classList.add('lp-anim-in');
      }
      if (!LP.motion.reduced()) browse.focus({ preventScroll: true });
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
    $('btn-test-endpoint').addEventListener('click', function () {
      var button = $('btn-test-endpoint'), status = $('endpoint-test-status');
      if (button) button.disabled = true;
      if (status) status.textContent = 'Testing endpoint…';
      var request;
      try { request = lpBridge.connected() ? lpBridge.call('test_endpoint') : Promise.resolve(null); }
      catch (error) { request = Promise.reject(error); }
      Promise.resolve(request).then(function (value) {
        var result = parseBridgeResult(value);
        if (value === true || value === 'ok' || value === 'available' || (result && (result.ok === true || result.success === true || result.available === true))) {
          if (status) status.textContent = 'Endpoint test succeeded.';
        } else if (!result) {
          if (status) status.textContent = 'Endpoint testing is unavailable in this build.';
        } else if (result.error || result.message) {
          if (status) status.textContent = 'Endpoint test failed: ' + (result.error || result.message);
        } else {
          if (status) status.textContent = 'Endpoint is unavailable.';
        }
      }, function (error) {
        if (status) status.textContent = 'Endpoint test failed: ' + (error && error.message || 'unknown error');
      }).then(function () { if (button) button.disabled = false; });
    });

    // Compute engine (CPU / Vulkan) — reflects the persisted engine and writes
    // it back so a Vulkan selection actually reaches the transcription backend.
    var COMPUTE_IDS = { cpu: 'compute-cpu', cuda: 'compute-cuda', vulkan: 'compute-gpu' };
    function reflectEngine(engine) {
      Object.keys(COMPUTE_IDS).forEach(function (k) {
        var el = $(COMPUTE_IDS[k]); if (!el) return;
        var on = engine === k;
        el.style.background = on ? 'var(--secondary-surface)' : 'transparent';
        el.style.color = on ? 'var(--secondary-text)' : 'var(--muted)';
        el.style.border = '1.5px solid ' + (on ? 'var(--secondary-border)' : 'transparent');
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
    function applyComputeResponse(kind, value) {
      var data = parseBridgeResult(value);
      if (!data || typeof data !== 'object') return;
      var id = kind === 'cuda' ? 'cuda-status' : 'vulkan-status', el = $(id);
      if (!el || data.state === 'checking') return;
      var message = data.message || data.detail;
      if (!message && data.state === 'available') message = kind === 'cuda' ? 'CUDA available' : 'Vulkan available';
      if (!message && data.state === 'unavailable') message = kind === 'cuda' ? 'CUDA unavailable · CPU · AVX2 ready' : 'Vulkan unavailable · CPU · AVX2 ready';
      if (message) el.textContent = friendlyProcessingLabel(message) || message;
      el.style.color = data.state === 'available' || data.state === 'loaded' ? 'var(--secondary-text)' : 'var(--muted)';
    }
    $('btn-validate-vulkan').addEventListener('click', function () {
      ['vulkan-status', 'cuda-status'].forEach(function (id) {
        var el = $(id); if (el) { el.textContent = 'Checking compute backend…'; el.style.color = 'var(--muted)'; }
      });
      var requests = lpBridge.connected()
        ? [lpBridge.call('validate_vulkan'), lpBridge.call('validate_cuda')]
        : [Promise.resolve(null), Promise.resolve(null)];
      Promise.all(requests).then(function (values) {
        applyComputeResponse('vulkan', values[0]);
        applyComputeResponse('cuda', values[1]);
        setComputeReadyFallback();
      }, function () { setComputeReadyFallback(); });
      // A backend may report through its event channel rather than the command
      // response. This bounded fallback guarantees the CPU path is never left
      // behind a permanent spinner if either response is unavailable.
      setTimeout(setComputeReadyFallback, 1500);
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
        b.style.borderColor = on ? 'var(--secondary-border)' : 'transparent';
      });
    }
    LP.ui = { reflectEngine: reflectEngine, reflectBackend: reflectBackend };
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
        setModelValue(this.value);
      }
    });
    var updateCheckToken = 0;
    $('btn-reset-lecturepack').addEventListener('click', confirmResetLecturePack);
    $('btn-check-updates').addEventListener('click', function () {
      var token = ++updateCheckToken, button = $('btn-check-updates'), status = $('update-status');
      if (status) status.textContent = 'Checking…';
      if (button) button.disabled = true;
      function settle(message) {
        if (token !== updateCheckToken) return;
        if (status) status.textContent = message;
        if (button) button.disabled = false;
      }
      var request;
      try { request = lpBridge.connected() ? lpBridge.call('check_updates') : Promise.resolve(null); }
      catch (error) { request = Promise.reject(error); }
      Promise.resolve(request).then(function (value) {
        var result = parseBridgeResult(value);
        if (!result) { settle('Updates are not available in this build.'); return; }
        if (result.error) { settle('Update check failed: ' + result.error); return; }
        if (result.available === false || result.phase === 'unavailable' || result.phase === 'not_available') {
          settle(result.message || 'Updates are not available in this build.'); return;
        }
        if (result.available === true || result.phase === 'available') {
          settle(result.message || 'An update is available.'); return;
        }
        settle(result.message || 'Updates are not available in this build.');
      }, function (error) {
        settle('Update check failed: ' + (error && error.message || 'unknown error'));
      });
      setTimeout(function () { settle('Updates are not available in this build.'); }, 4000);
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
    function beginBrowseImport() {
      if (!lpBridge.connected()) { setOnb('drop'); return; }
      setImporting(true, 'video');
      lpBridge.call('browse_video').then(function (result) {
        setImporting(false);
        if (result && result.cancelled) return;
        if (result && result.ok === false) {
          var message = friendlyImportError(result);
          if (message) toast(message);
        }
      }, function () { setImporting(false); });
    }
    dz.addEventListener('click', beginBrowseImport);
    $('btn-browse').addEventListener('click', function (e) {
      e.stopPropagation();
      beginBrowseImport();
    });

    $('btn-paste-link').addEventListener('click', function (e) {
      e.stopPropagation();
      linkImportDialog();
    });
    $('downloads-indicator').addEventListener('click', function () {
      var panel = $('downloads-panel');
      panel.hidden = !panel.hidden;
      this.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
      if (!panel.hidden) { renderDownloads(); positionDownloadsPanel(); }
    });
    $('downloads-close').addEventListener('click', function () {
      $('downloads-panel').hidden = true;
      $('downloads-indicator').setAttribute('aria-expanded', 'false');
    });
    $('downloads-clear').addEventListener('click', function () { lpBridge.call('clear_media_downloads'); });
    $('downloads-list').addEventListener('click', function (e) {
      var button = e.target.closest('[data-download-act]');
      if (!button) return;
      var payload = { download_id: button.dataset.downloadId };
      if (button.dataset.downloadAct === 'cancel') lpBridge.call('cancel_media_url', payload);
      else if (button.dataset.downloadAct === 'remove') lpBridge.call('remove_media_download', payload);
      else if (button.dataset.downloadAct === 'retry') lpBridge.call('retry_media_download', payload);
    });
    document.addEventListener('pointerdown', function (e) {
      var panel = $('downloads-panel'), indicator = $('downloads-indicator');
      if (!panel || panel.hidden || panel.contains(e.target) || indicator.contains(e.target)) return;
      panel.hidden = true;
      indicator.setAttribute('aria-expanded', 'false');
    });
    window.addEventListener('resize', positionDownloadsPanel);

    // ---- Home multi-select ----
    $('btn-select-mode').addEventListener('click', function (e) {
      e.stopPropagation();
      setSelectMode(!LP.state.selecting);
    });
    $('btn-select-done').addEventListener('click', function (e) {
      e.stopPropagation(); setSelectMode(false);
    });
    $('btn-select-all').addEventListener('click', function (e) {
      e.stopPropagation();
      LP.state.selected = {};
      selectableIds().forEach(function (id) { LP.state.selected[id] = true; });
      renderJobs(); renderSelCount();
    });
    $('btn-select-none').addEventListener('click', function (e) {
      e.stopPropagation();
      LP.state.selected = {};
      renderJobs(); renderSelCount();
    });
    $('btn-bulk-delete').addEventListener('click', function (e) {
      e.stopPropagation(); bulkDelete();
    });
    $('btn-bulk-group').addEventListener('click', function (e) {
      e.stopPropagation(); bulkGroup();
    });
    /* dragenter MUST be cancelled or no drop ever arrives.
       This is the whole "drag and drop doesn't work anywhere" bug. Chromium
       decides whether an element is a valid drop target from the dragenter /
       dragover pair; cancelling only dragover leaves the ENTER unhandled, so
       the page is rejected as a target and `drop` is never dispatched at all.
       The handlers below were therefore correct and simply never ran.
       Verified over CDP against the packaged app with a real file drag:
         without this listener -> dragenter, dragover, dragenter ... no drop
         with it               -> drop fires, 1 file, full path resolved
       Registered on window (capture) so it covers every screen, not just the
       dropzone -- the app advertises "Drop a lecture video anywhere". */
    window.addEventListener('dragenter', function (e) { e.preventDefault(); }, true);
    /* The whole drag auto-scroll wiring, in ONE place, in capture so it runs
       for every drag regardless of which element ends up handling the drop.
       dragover drives the velocity; drop / dragend / a dragleave that leaves
       the window all tear it down, so a scroll can never outlive its drag. */
    window.addEventListener('dragover', function (e) {
      dragScroll.update(e.clientX, e.clientY);
    }, true);
    window.addEventListener('drop', function () { dragScroll.stop(); }, true);
    window.addEventListener('dragend', function () { dragScroll.stop(); }, true);
    window.addEventListener('dragleave', function (e) {
      if (!e.relatedTarget) dragScroll.stop();
    }, true);
    // A drag can also end without any of the above (Esc, or the OS cancelling
    // an external drag). Both of these fire in that case.
    window.addEventListener('mouseup', function () { dragScroll.stop(); }, true);
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') dragScroll.stop();
    }, true);
    dz.addEventListener('dragenter', function (e) { e.preventDefault(); });
    /* The internal-drag guards here used to stopPropagation(), which was aimed
       at the window handler below but also blocked the event from ever reaching
       LPDrag's delegated listeners on document -- so dragging a lecture across
       the dropzone went dark: no target paint, no status strip, no explanation.
       A plain return is enough now, because the window handlers check for an
       internal drag themselves. */
    dz.addEventListener('dragover', function (e) {
      if (readInternalJobDrag(e).length || internalJobDragIds.length || LPDrag.dragging()) return;
      e.preventDefault();
      if (hasDemoDrag(e)) { dz.classList.add('lp-demo-drop-hover'); return; }
      if (LP.state.onb !== 'detected') setOnb('drop');
    });
    dz.addEventListener('dragleave', function (e) {
      if (hasDemoDrag(e)) clearDemoDropState();
    });
    dz.addEventListener('drop', function (e) {
      if (readInternalJobDrag(e).length || internalJobDragIds.length || LPDrag.dragging()) return;
      e.preventDefault();
      if (hasDemoDrag(e)) { clearDemoDropState(); useDroppedDemo(); return; }
      importDroppedFiles(e.dataTransfer && e.dataTransfer.files);
    });
    // Electron owns the document-level drop path too. Ignore the dropzone here
    // because its handler already imported the first file and the event bubbles.
    window.addEventListener('dragover', function (e) {
      /* ORDER MATTERS, and getting it wrong was the whole "internal drag is
         broken" complaint. This preventDefault() is what makes the entire
         window a valid drop target so an external video can be dropped on any
         screen -- but it used to run BEFORE the internal-drag check, so an
         internal lecture drag also got a window-wide "yes, drop here" cursor
         while only one element could actually act on it. The cursor promised a
         drop that silently did nothing, everywhere.
         Internal drags now bail out FIRST, leaving the browser to paint its own
         no-drop cursor anywhere LPDrag has not claimed a target. */
      if (readInternalJobDrag(e).length || internalJobDragIds.length || LPDrag.dragging()) return;
      e.preventDefault();
      if (hasDemoDrag(e)) return;
      var types = e.dataTransfer && e.dataTransfer.types;
      var hasFiles = false;
      try { hasFiles = Array.prototype.indexOf.call(types || [], 'Files') >= 0; } catch (err) { hasFiles = false; }
      if (hasFiles && LP.state.onb !== 'detected') setOnb('drop');
    });
    window.addEventListener('dragleave', function (e) {
      if (e.relatedTarget) return;
      if (LP.state.onb === 'drop') setOnb(null);
    });
    window.addEventListener('drop', function (e) {
      // Same ordering rule as the dragover above: an internal drag must never
      // reach importDroppedFiles(), and must not be cancelled here either --
      // LPDrag has already handled it and stopped propagation if it landed.
      if (readInternalJobDrag(e).length || internalJobDragIds.length || LPDrag.dragging()) return;
      e.preventDefault();
      setOnb(null);
      if (e.target && e.target.closest && e.target.closest('#dropzone')) return;
      importDroppedFiles(e.dataTransfer && e.dataTransfer.files);
    });

    /* The Process drop targets are now DECLARED, not wired. LPDrag delegates
       from document, so these two elements need only say what they accept --
       and the reprocess confirmation below is unchanged, because dropping a
       finished lecture on Process still replaces its slides and Study pack. */
    /* #dropzone is in this list because it SAYS "Drop a lecture video anywhere"
       and then refused the app's own lectures -- reported as "I can't drag a
       lecture from Recent onto the dropzone". Dropping an existing lecture on
       the import zone can only sensibly mean "put this through the pipeline",
       which is exactly the Process semantic, so it shares that entry rather
       than growing a third one. External file drops on the same element are
       untouched: dz's own handlers still run for those and bail out only for
       internal drags. */
    Array.prototype.slice.call(document.querySelectorAll('#process-queue-target, [data-existing-job-drop-target], [data-nav="process"], #dropzone'))
      .forEach(function (el) { el.dataset.lpDrop = 'process'; });
    LPDrag.wire();

    $('btn-show-empty').addEventListener('click', function () { setJobsEmpty(true); });
    // "Try the demo lecture" (N-3): the empty-state recovery action opens the
    // self-contained walkthrough. The real bundled lecture runs only after the
    // student's explicit final-chapter action, instead of a dead sample-library
    // button that seeded nothing.
    $('btn-load-jobs').addEventListener('click', function () {
      if (!demoAdmissionAvailable) { toast('The demo will be available once setup finishes.'); return; }
      if (guidedDemo.snapshot().active) { setScreen('process'); return; }
      var savedDemo = demoState();
      // An interrupted walkthrough resumes where the student left it. Once it
      // has been completed, the explicitly named "Try the demo" action starts
      // a fresh walkthrough instead of reopening on the final export page.
      openDemo(savedDemo.completed === true ? 1 : (savedDemo.chapter || 1));
    });

    // Home grid: per-card menu buttons (delete / set group) take priority,
    // otherwise clicking a card opens the job.
    var ONB_ACTIVE_STYLE = 'flex:1;text-align:center;font:700 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--orange);border-radius:9px;background:var(--orange-soft);color:var(--orange-ink);box-shadow:var(--shadow-hard-sm);cursor:pointer';
    var ONB_INACTIVE_STYLE = 'flex:1;text-align:center;font:500 12px \'Space Grotesk\';padding:9px 0;border:2px solid transparent;border-radius:9px;color:var(--muted);box-shadow:var(--shadow-hard-sm);cursor:pointer';
    function syncOnbModeStyles() {
      Array.prototype.forEach.call(document.querySelectorAll('[data-onb-mode]'), function (o) {
        o.style.cssText = o.dataset.onbMode === (LP.state.onbMode || 'study') ? ONB_ACTIVE_STYLE : ONB_INACTIVE_STYLE;
      });
    }
    function syncOnbSensStyles() {
      Array.prototype.forEach.call(document.querySelectorAll('[data-onb-sens]'), function (o) {
        o.style.cssText = o.dataset.onbSens === (LP.state.onbSens || 'balanced') ? ONB_ACTIVE_STYLE : ONB_INACTIVE_STYLE;
      });
    }
    function openJobSetup(jobId) {
      var job = _jobById(jobId);
      if (!job) return;
      LP.state.setupJobId = jobId;
      LP.state.onbMode = job.product_mode === 'transcript_only' ? 'transcript' :
        (job.product_mode === 'slides_only' ? 'slides' : 'study');
      LP.state.onbSens = job.preset === 'detailed' ? 'high' : 'balanced';
      if (job.name) $('onb-file-name').textContent = job.name;
      if (job.file || job.meta) $('onb-file-meta').textContent = job.meta || '';
      syncOnbModeStyles();
      syncOnbSensStyles();
      setOnb('detected');
      if (lpBridge.connected()) {
        try { lpBridge.call('open_job', jobId); } catch (err) { /* setup already shown */ }
      }
    }
    function startJobFromCard(jobId) {
      var job = _jobById(jobId);
      if (!job) return;
      // Follow the job being started immediately: it either claims the active
      // slot (Process shows live progress) or joins the queue (Process shows
      // "Waiting to process · Position N" while the current job finishes).
      selectJob(jobId, { screen: 'process' });
      var panel = $('proc-completion'); if (panel) panel.hidden = true;
      lpBridge.call('start_processing', {
        mode: job.product_mode === 'transcript_only' ? 'transcript' :
          (job.product_mode === 'slides_only' ? 'slides' : 'study'),
        preset: job.preset === 'detailed' ? 'high' : (job.preset === 'conservative' ? 'low' : 'balanced'),
        job_id: jobId
      });
    }
    $('jobs-grid').addEventListener('click', function (e) {
      // Select mode owns the click: toggle instead of opening the lecture.
      if (LP.state.selecting) {
        var selCard = e.target.closest('.lp-card[data-job]');
        if (selCard) { e.stopPropagation(); toggleSelected(selCard.dataset.job); }
        return;
      }
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
        if (a === 'resume') { selectJob(aid, { screen: 'process' }); lpBridge.call('resume_job', aid); }
        else if (a === 'restart') { selectJob(aid, { screen: 'process' }); lpBridge.call('restart_job', aid); }
        else if (a === 'view') { selectJob(aid, { screen: 'process' }); }
        else if (a === 'start') { startJobFromCard(aid); }
        else if (a === 'options') { openJobSetup(aid); }
        else if (a === 'remove') {
          var jb = LP.data.jobs.filter(function (x) { return x.id === aid; })[0];
          if (jb) confirmDeleteJob(jb);
        }
        return;
      }
      var card = e.target.closest('[data-job]');
      if (!card) return;
      var jobId = card.dataset.job;
      var cardJob = LP.data.jobs.filter(function (x) { return x.id === jobId; })[0];
      // A ready job opens its pre-processing setup, not the Process screen.
      if (cardJob && _jobIsReady(cardJob)) {
        openJobSetup(jobId);
        return;
      }
      // F-4: the click's visible response never depends on the bridge
      // round-trip. A completed lecture opens Review; anything else (queued,
      // running, failed, cancelled) opens Process with its final/live state.
      selectJob(jobId, { screen: cardJob && cardJob.status === 'done' ? 'review' : 'process' });
    });
    /* The lecture-card dragstart/dragend that used to live here moved into
       LPDrag's delegated handlers. It could not stay: renderJobs() rebuilds
       #jobs-grid via innerHTML, and while the listener on the grid itself
       survived, every new surface would have needed its own copy of this. One
       registry, one lift path, five surfaces. */

    $('jobs-grid').addEventListener('dblclick', function (e) {
      var title = e.target.closest('.lp-card[data-job] [data-job-title]');
      if (!title) return;
      var card = title.closest('.lp-card[data-job]');
      var job = card && _jobById(card.dataset.job);
      if (job) { e.preventDefault(); e.stopPropagation(); renameJobDialog(job); }
    });
    document.addEventListener('contextmenu', function (e) {
      var owner = e.target && e.target.closest ? e.target.closest('[data-job], [data-switch-job], [data-queueid]') : null;
      if (!owner) return;
      var jobId = owner.dataset.job || owner.dataset.switchJob || owner.dataset.queueid;
      var job = _jobById(jobId);
      if (!job) return;
      e.preventDefault();
      showLectureContextMenu(job, e.clientX, e.clientY);
    });
    var contextMenu = $('lecture-context-menu');
    if (contextMenu) contextMenu.addEventListener('click', function (e) {
      var button = e.target.closest('[data-context-index]');
      if (!button) return;
      var action = contextMenu._actions && contextMenu._actions[Number(button.dataset.contextIndex)];
      hideLectureContextMenu();
      if (action && action.run) action.run();
    });
    var switchToggle = $('lecture-switcher-toggle');
    if (switchToggle) switchToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      var panel = $('lecture-switcher');
      if (!panel || switchToggle.disabled) return;
      panel.hidden = !panel.hidden;
      switchToggle.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
      if (!panel.hidden) renderLectureSwitcher();
    });
    var lectureSwitcher = $('lecture-switcher');
    if (lectureSwitcher) lectureSwitcher.addEventListener('click', function (e) {
      var row = e.target.closest('[data-switch-job]');
      if (!row) return;
      var job = _jobById(row.dataset.switchJob);
      lectureSwitcher.hidden = true;
      switchToggle.setAttribute('aria-expanded', 'false');
      if (job) selectJob(job.id, { screen: sensibleJobScreen(job) });
    });
    document.addEventListener('click', function (e) {
      hideLectureContextMenu();
      var panel = $('lecture-switcher');
      if (panel && !panel.hidden && !e.target.closest('.lp-breadcrumb')) {
        panel.hidden = true;
        if (switchToggle) switchToggle.setAttribute('aria-expanded', 'false');
      }
    });

    // Processing queue controls (Run Now / reorder / remove).
    var queueList = $('queue-list');
    if (queueList) queueList.addEventListener('click', function (e) {
      var q = e.target.closest('[data-queueact]');
      if (!q) return;
      var qid = q.dataset.queueid, qa = q.dataset.queueact;
      var rows = (LP.data.queue && LP.data.queue.queue) || [];
      var idx = rows.map(function (r) { return r.id; }).indexOf(qid);
      /* Follow the job being promoted: Process then shows its live progress
         rather than leaving the user on a queue row that silently vanished. */
      if (qa === 'runnow') { selectJob(qid, { screen: 'process' }); lpBridge.call('run_now', qid); }
      else if (qa === 'remove') lpBridge.call('remove_from_queue', qid);
      else if (qa === 'up' && idx > 0) lpBridge.call('reorder_queue', qid, idx - 1);
      else if (qa === 'down' && idx >= 0) lpBridge.call('reorder_queue', qid, idx + 1);
      else if (qa === 'schedule') scheduleJobDialog(qid);
    });

    // Scheduled list controls (Unschedule).
    var schedList = $('scheduled-list');
    if (schedList) schedList.addEventListener('click', function (e) {
      var b = e.target.closest('[data-queueact="unschedule"]');
      if (b) lpBridge.call('unschedule_job', b.dataset.queueid);
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
            ? 'flex:1;text-align:center;font:700 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--orange);border-radius:9px;background:var(--orange-soft);color:var(--orange-ink);box-shadow:var(--shadow-hard-sm);cursor:pointer'
            : 'flex:1;text-align:center;font:500 12px \'Space Grotesk\';padding:9px 0;border:2px solid transparent;border-radius:9px;color:var(--muted);box-shadow:var(--shadow-hard-sm);cursor:pointer';
        });
        LP.state.onbMode = el.dataset.onbMode;
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-onb-sens]'), function (el) {
      el.addEventListener('click', function () {
        Array.prototype.forEach.call(document.querySelectorAll('[data-onb-sens]'), function (o) {
          var on = o === el;
          o.style.cssText = on
            ? 'flex:1;text-align:center;font:700 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--orange);border-radius:9px;background:var(--orange-soft);color:var(--orange-ink);box-shadow:var(--shadow-hard-sm);cursor:pointer'
            : 'flex:1;text-align:center;font:500 12px \'Space Grotesk\';padding:9px 0;border:2px solid transparent;border-radius:9px;color:var(--muted);box-shadow:var(--shadow-hard-sm);cursor:pointer';
        });
        LP.state.onbSens = el.dataset.onbSens;
      });
    });
    $('btn-start-processing').addEventListener('click', function () {
      setOnb(null);
      if (LP.state.setupJobId) selectJob(LP.state.setupJobId, { screen: 'process' });
      else setScreen('process');
      // Reset any stale completion/pause UI from a prior run.
      var panel = $('proc-completion'); if (panel) panel.hidden = true;
      var pause = $('btn-pause-job'), resume = $('btn-resume-job'), dot = $('proc-status-dot');
      if (pause) { pause.hidden = false; pause.disabled = false; pause.textContent = 'Pause'; }
      if (resume) resume.hidden = true;
      if (dot) dot.style.animation = 'lpblink 1s infinite';
      lpBridge.call('start_processing', {
        mode: LP.state.onbMode || 'study',
        preset: LP.state.onbSens || 'balanced',
        job_id: LP.state.setupJobId || ''
      });
    });

    // process
    $('btn-cancel-job').addEventListener('click', function () {
      if (!LP.state.pipelineRunning && !guidedDemo.snapshot().active) { toast('No lecture is processing right now.'); return; }
      lpBridge.call('cancel_job');
    });
    (function () {
      var p = $('btn-pause-job'), r = $('btn-resume-job');
      if (p) p.addEventListener('click', function () {
        if (!LP.state.pipelineRunning && !guidedDemo.snapshot().active) { toast('No lecture is processing right now.'); return; }
        lpBridge.call('pause_job');
      });
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

    // Shared Previous/Next source switcher (Process / Review / Transcript /
    // Study / Exports). Delegated on document so re-rendered switcher buttons
    // keep working without rebinding. Selecting stays on the current screen.
    document.addEventListener('click', function (e) {
      var sw = e.target && e.target.closest ? e.target.closest('[data-jsw] button[data-jdir]') : null;
      if (!sw) return;
      e.preventDefault();
      selectAdjacentJob(parseInt(sw.dataset.jdir, 10) || 0);
    });

    // Live log: Latest jumps to the newest line and resumes auto-follow.
    // Scrolling upward deliberately pauses following until Latest is pressed.
    var procLogEl = $('proc-log');
    if (procLogEl) {
      procLogEl.addEventListener('scroll', function () {
        LP.logFollow = procLogEl.scrollTop + procLogEl.clientHeight >= procLogEl.scrollHeight - 8;
      });
    }
    var btnLogLatest = $('btn-log-latest');
    if (btnLogLatest) btnLogLatest.addEventListener('click', function () {
      var el = $('proc-log');
      if (!el) return;
      LP.logFollow = true;
      el.scrollTop = el.scrollHeight;
    });

    // review
    var strip = $('timeline-strip');
    // Portal the hover preview out of the timeline so it can never be clipped
    // by the timeline card's overflow.
    var scrubPv = $('scrub-preview');
    if (scrubPv && scrubPv.parentNode !== document.body) document.body.appendChild(scrubPv);
    strip.addEventListener('mousemove', onScrub);
    strip.addEventListener('pointerdown', beginTimelinePointerDrag);
    strip.addEventListener('pointermove', function (e) {
      if (timelinePointerDrag.active) moveTimelinePointerDrag(e);
      else onScrub(e);
    });
    strip.addEventListener('pointerup', endTimelinePointerDrag);
    strip.addEventListener('pointercancel', endTimelinePointerDrag);
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
    Array.prototype.forEach.call(document.querySelectorAll('[data-slide-size]'), function (b) {
      b.addEventListener('click', function () {
        if (LP.state.slideSize === b.dataset.slideSize) return;
        LP.state.slideSize = b.dataset.slideSize;
        try { browserStorage().setItem('lecturepack.slideSize', LP.state.slideSize); } catch (e) {}
        renderAllSlides();
      });
    });
    $('btn-all-slides').addEventListener('click', openAllSlides);
    $('btn-all-slides-close').addEventListener('click', function () { closeAllSlides(true); });
    $('all-slides-grid').addEventListener('click', function (e) {
      var item = e.target.closest('[data-slide]');
      if (!item) return;
      LP.state.viewingSlide = +item.dataset.slide;
      renderSlides();
      closeAllSlides(true);
    });
    $('btn-prev-slide').addEventListener('click', function () {
      if (!LP.data.slides.length) return;   // N-1: nothing to page through
      LP.state.viewingSlide = (LP.state.viewingSlide + LP.data.slides.length - 1) % LP.data.slides.length;
      renderSlides();
    });
    $('btn-next-slide').addEventListener('click', function () {
      if (!LP.data.slides.length) return;   // N-1: nothing to page through
      LP.state.viewingSlide = (LP.state.viewingSlide + 1) % LP.data.slides.length;
      renderSlides();
    });
    $('btn-keep').addEventListener('click', function () {
      var s = LP.data.slides[LP.state.viewingSlide];
      if (!s) return;   // N-1: no slide selected / no lecture loaded
      s.state = 'accepted'; s.sel = true;
      lpBridge.call('set_slide_state', LP.state.viewingSlide, 'accepted');
      // Advance after judging: the user is working THROUGH the deck, so keeping
      // or rejecting is implicitly "done with this one". Wraps like the next
      // button. Guarded so a 1-slide deck (or an empty one) cannot divide by
      // zero or bounce the view.
      if (LP.data.slides.length > 1) {
        LP.state.viewingSlide = (LP.state.viewingSlide + 1) % LP.data.slides.length;
      }
      renderSlides();
    });
    $('btn-reject').addEventListener('click', function () {
      var s = LP.data.slides[LP.state.viewingSlide];
      if (!s) return;   // N-1: no slide selected / no lecture loaded
      s.state = 'rejected'; s.sel = false;
      lpBridge.call('set_slide_state', LP.state.viewingSlide, 'rejected');
      // Advance after judging: the user is working THROUGH the deck, so keeping
      // or rejecting is implicitly "done with this one". Wraps like the next
      // button. Guarded so a 1-slide deck (or an empty one) cannot divide by
      // zero or bounce the view.
      if (LP.data.slides.length > 1) {
        LP.state.viewingSlide = (LP.state.viewingSlide + 1) % LP.data.slides.length;
      }
      renderSlides();
    });
    $('btn-save-corrections').addEventListener('click', function () {
      if (!LP.state.jobId) { toast('Load a lecture first — there are no corrections to save yet.'); return; }
      var rows = document.querySelectorAll('#review-transcript [contenteditable]');
      var texts = Array.prototype.map.call(rows, function (r) { return r.textContent; });
      lpBridge.call('save_corrections', JSON.stringify(texts));
    });
    $('btn-repair').addEventListener('click', function () {
      if (!LP.state.jobId) { toast('Load a lecture before repairing slide selections.'); return; }
      lpBridge.call('repair_selection');
    });

    // transcript
    var btnCopyText = $('btn-copy-text'), btnCopyStamped = $('btn-copy-stamped');
    if (btnCopyText) btnCopyText.addEventListener('click', function () {
      copyText(formatTranscriptPlain(LP.data.transcript.blocks), 'Transcript copied');
    });
    if (btnCopyStamped) btnCopyStamped.addEventListener('click', function () {
      copyText(formatTranscriptStamped(LP.data.transcript.blocks), 'Transcript copied with timestamps');
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
    // Re-running the export is the whole point of this button; resetting the
    // banner alone left the files on disk untouched.
    $('btn-export-again').addEventListener('click', function () {
      LP.state.exportPhase = 'idle';
      renderExportPhase();
      startExport();
    });
    $('btn-open-folder').addEventListener('click', function () { lpBridge.call('open_export_folder'); });
    $('btn-export-pdf').addEventListener('click', function () { exportOne('pdf', 'PDF'); });
    $('btn-export-html').addEventListener('click', function () { exportOne('html', 'HTML'); });

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
      // The main process holds the authoritative available-update version.
      if (lpBridge.connected()) lpBridge.call('skip_update_version');
      hideWhatsNew();
    });
    // Updates settings: auto-check + clear-skipped. LecturePack 2 stable ships
    // one channel, so there is no channel selector.
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
      var status = $('notification-test-status');
      testBtn.disabled = true;
      if (status) status.textContent = 'Sending test notification…';
      var request;
      try { request = lpBridge.connected() ? lpBridge.call('test_notification') : Promise.resolve(null); }
      catch (error) { request = Promise.reject(error); }
      Promise.resolve(request).then(function (value) {
        var result = parseBridgeResult(value);
        if (value === true || (result && (result.ok === true || result.success === true))) {
          if (status) status.textContent = 'Test notification sent.';
        } else if (!result) {
          if (status) status.textContent = 'Desktop notifications are unavailable in this build.';
        } else {
          if (status) status.textContent = result.error || result.message || 'Desktop notification failed.';
        }
      }, function (error) {
        if (status) status.textContent = 'Desktop notification failed: ' + (error && error.message || 'unknown error');
      }).then(function () { testBtn.disabled = false; });
    });

    // ---- QOL wiring: batch import, processing strip, transcript search,
    //      Ctrl+K command palette, per-job resume state ----
    var batchOverlay = $('batch-overlay');
    if (batchOverlay) {
      var batchClose = $('batch-close');
      if (batchClose) batchClose.addEventListener('click', closeBatchImport);
      batchOverlay.addEventListener('click', function (e) { if (e.target === batchOverlay) closeBatchImport(); });
      $('btn-batch-apply').addEventListener('click', batchApplyAll);
      $('btn-batch-queue').addEventListener('click', batchQueueAll);
      $('btn-batch-done').addEventListener('click', closeBatchImport);
      Array.prototype.forEach.call(document.querySelectorAll('#batch-quality [data-bq]'), function (o) {
        o.addEventListener('click', function () { batchQuality = o.dataset.bq; setBatchStyles(); batchPresetStore.save(batchMode, batchQuality); });
      });
      Array.prototype.forEach.call(document.querySelectorAll('#batch-output [data-bo]'), function (o) {
        o.addEventListener('click', function () { batchMode = o.dataset.bo; setBatchStyles(); batchPresetStore.save(batchMode, batchQuality); });
      });
    }

    // Footer job button: click selects the active job and opens Process.
    var procStrip = $('status-job');
    if (procStrip) procStrip.addEventListener('click', function () {
      if (LP.state.activeJobId) selectJob(LP.state.activeJobId, { screen: 'process' });
      else {
        var running = LP.data.jobs.filter(function (j) { return j && j.status === 'running'; })[0];
        if (running) selectJob(running.id, { screen: 'process' });
      }
    });

    // Global transcript search trigger + interactions.
    var globalSearchButton = $('btn-global-search');
    if (globalSearchButton) globalSearchButton.addEventListener('click', openGlobalSearch);
    var searchInput = $('search-input');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        if (searchDebounce) clearTimeout(searchDebounce);
        var value = this.value;
        searchDebounce = setTimeout(function () { runGlobalSearch(value); }, 220);
      });
      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeGlobalSearch(); }
      });
    }
    var searchResults = $('search-results');
    if (searchResults) searchResults.addEventListener('click', function (e) {
      var r = e.target.closest('[data-result]');
      if (r) openSearchResult(r.dataset.job, r.dataset.ts);
    });

    // Ctrl+K command palette: open + input + keyboard navigation.
    var paletteInput = $('palette-input');
    if (paletteInput) {
      paletteInput.addEventListener('input', function () { paletteIndex = 0; renderPalette(this.value); });
      paletteInput.addEventListener('keydown', function (e) {
        var host = $('palette-results'), items = (host && host._items) || [];
        if (e.key === 'Escape') { closePalette(); return; }
        if (e.key === 'Enter') { e.preventDefault(); activatePaletteItem(paletteIndex, items); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); paletteIndex = Math.min(paletteIndex + 1, items.length - 1); renderPalette(this.value); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); paletteIndex = Math.max(paletteIndex - 1, 0); renderPalette(this.value); }
      });
    }
    var paletteOverlayEl = $('palette-overlay');
    if (paletteOverlayEl) paletteOverlayEl.addEventListener('click', function (e) {
      var item = e.target.closest('[data-palette-item]');
      if (item) { activatePaletteItem(+item.dataset.index, (paletteOverlayEl.querySelector('#palette-results') || {})._items || []); }
      else if (e.target === paletteOverlayEl) closePalette();
    });

    // Keyboard shortcuts.  An open overlay OWNS the keyboard: digit/F shortcuts
    // must not change the screen behind a modal, and Tab must not escape to
    // controls the user cannot see (both were live defects -- see BUG_LIST.md
    // BUG-01 and BUG-02).
    window.addEventListener('keydown', function (e) {
      // Ctrl+K opens the command palette (or closes it if open). Runs before
      // the editing guard so it works even while typing elsewhere.
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && String(e.key || '').toLowerCase() === 'k') {
        e.preventDefault();
        if (paletteOverlayEl && !paletteOverlayEl.hidden) closePalette();
        else openPalette();
        return;
      }
      // Escape closes the palette / search / batch overlays.
      if (e.key === 'Escape') {
        if ($('all-slides-overlay') && !$('all-slides-overlay').hidden) { closeAllSlides(true); return; }
        if (paletteOverlayEl && !paletteOverlayEl.hidden) { closePalette(); return; }
        if ($('search-overlay') && !$('search-overlay').hidden) { closeGlobalSearch(); return; }
        if (batchOverlay && !batchOverlay.hidden) { closeBatchImport(); return; }
        if ($('lecture-context-menu') && !$('lecture-context-menu').hidden) { hideLectureContextMenu(); return; }
        if ($('lecture-switcher') && !$('lecture-switcher').hidden) {
          $('lecture-switcher').hidden = true;
          if ($('lecture-switcher-toggle')) $('lecture-switcher-toggle').setAttribute('aria-expanded', 'false');
          return;
        }
      }
      var tag = (e.target && e.target.tagName) || '';
      var editing = /INPUT|TEXTAREA|SELECT/.test(tag) || (e.target && e.target.isContentEditable);
      if (e.key === 'Escape') {
        setFocus(false); setOnb(null);
        if (!$('whatsnew-overlay').hidden) hideWhatsNew();
        return;
      }
      var overlay = topOverlay();
      if (overlay) {
        if (e.key === 'Tab') trapFocus(overlay, e);
        return;
      }
      if (editing) return;
      // N-11: the two documented app shortcuts.
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {
        var sk = String(e.key || '').toLowerCase();
        if (sk === 'o') {
          e.preventDefault();
          if (lpBridge.connected()) lpBridge.call('browse_video'); else setOnb('drop');
          return;
        }
        if (sk === 'e') {
          e.preventDefault();
          var exportJob = (LP.data.jobs || []).filter(function (j) { return j && j.id === LP.state.jobId; })[0];
          if (exportJob && exportJob.status === 'done') setScreen('exports');
          else if (LP.state.jobId) toast('Export unlocks when the lecture finishes processing.');
          else toast('Load a lecture first — there is nothing to export yet.');
          return;
        }
      }
      /* Review keyboard macros. These are ADDITIVE: every one of them drives the
         existing on-screen control rather than reimplementing it, so the buttons
         stay the source of truth and a macro can never drift from what the button
         does. Arrows navigate, J/K stamp, Space is the fast path (stamp + move on).
         Nothing here overrides an existing binding -- Space and the arrows are
         already claimed on the flashcards screen, which is `screen === 'study'`,
         and the guard below keeps these to Review only. */
      if (LP.state.screen === 'review' && !editing && !overlay) {
        var rk = String(e.key || '').toLowerCase();
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          var navBtn = $(e.key === 'ArrowRight' ? 'btn-next-slide' : 'btn-prev-slide');
          if (navBtn && !navBtn.disabled) { e.preventDefault(); navBtn.click(); }
          return;
        }
        if (rk === 'j') {
          e.preventDefault();
          var btnKeep = $('btn-keep');
          if (btnKeep) {
            btnKeep.click();
            flashViewport('keep');
          }
          return;
        }
        if (rk === 'k') {
          e.preventDefault();
          var btnReject = $('btn-reject');
          if (btnReject) {
            btnReject.click();
            flashViewport('reject');
          }
          return;
        }
        if (rk === ' ' || e.code === 'Space') {
          /* Space was an exact duplicate of J -- same button, same flash, no
             advance -- so triaging a deck with it re-stamped one slide forever.
             It is the fast-path key, so it keeps AND advances: one key, straight
             down the deck. */
          e.preventDefault();
          var btnKeep2 = $('btn-keep');
          if (btnKeep2) {
            btnKeep2.click();
            flashViewport('keep');
            var nextSlideBtn = $('btn-next-slide');
            if (nextSlideBtn && !nextSlideBtn.disabled) nextSlideBtn.click();
          }
          return;
        }
      }
      var map = { 1: 'home', 2: 'process', 3: 'review', 4: 'transcript', 5: 'study', 6: 'exports', 7: 'settings' };
      if (map[e.key]) setScreen(map[e.key]);
      else if (e.key === 'f' || e.key === 'F') setFocus(!LP.state.focus);
    });
    // Electron closes the renderer without necessarily switching lectures.
    // Persist the currently viewed lecture at the final reliable page event.
    window.addEventListener('beforeunload', function () {
      if (LP.state.jobId) captureResumeState(LP.state.jobId);
    });

    // Slide filmstrip Loupe on hover
    var slideListEl = $('slide-list');
    if (slideListEl) {
      slideListEl.addEventListener('mousemove', function (e) {
        var card = e.target && e.target.closest && e.target.closest('.lp-slide-rail-card');
        if (card && card.dataset.slide !== undefined) {
          showSlideLoupe(+card.dataset.slide, e.clientX, e.clientY);
        } else {
          hideSlideLoupe();
        }
      });
      slideListEl.addEventListener('mouseleave', hideSlideLoupe);
    }

    // Mechanical Web Audio: zero-asset clicks on button depressions & switches
    document.addEventListener('pointerdown', function (e) {
      var btn = e.target && e.target.closest && e.target.closest('button, .lp-hit, .nav-item, [role="button"], .export-chip, [data-lp-drag]');
      if (btn && !btn.disabled) {
        if (btn.classList.contains('lp-reorder-btn') || btn.dataset.reorder) {
          LPAudio.playRatchet();
        } else if (btn.classList.contains('toggle-btn') || btn.getAttribute('role') === 'switch') {
          LPAudio.playToggle(btn.getAttribute('aria-checked') !== 'true');
        } else {
          LPAudio.playClick();
        }
      }
    }, { passive: true });
  }

  /* ======================= backend hookup ======================= */

  function wireBridge() {
    loadAppVersion();
    // Shared with the lpBridge.ready() bootstrap consumer below: normal
    // bridge activity must start exactly once per launch, from whichever of
    // the two admission paths (this signal, or the initial get_bootstrap()
    // call) resolves first. Both of its calls are admission-guarded on the
    // Python side (_ADMISSION_GUARDED_OPERATIONS); lpBridge.call() already
    // resolves null safely when a slot is missing, so a browser preview and
    // an older backend both still work with no extra guard here.
    var normalBridgeActivityStarted = false;
    var normalBridgeAdmitted = !lpBridge.connected();
    var normalBridgeActivityPending = false;
    function startNormalBridgeActivity() {
      if (normalBridgeActivityStarted) return;
      if (!normalBridgeAdmitted) { normalBridgeActivityPending = true; return; }
      normalBridgeActivityStarted = true;
      normalBridgeActivityPending = false;
      lpBridge.call('get_settings');
      lpBridge.call('list_ollama_models');
      // PC polish: probe the packaged yt-dlp capability so the Paste Link
      // control appears only when the runtime actually provides it.
      lpBridge.call('media_link_support');
    }
    lpBridge.on('repair_event', function (json) { RuntimeSetupGate.event(json); });
    lpBridge.on('bootstrap_progress', function (json) { RuntimeSetupGate.progress(json); });
    lpBridge.on('startup_failure', function (json) { RuntimeSetupGate.startupFailed(json); });
    lpBridge.on('service_failure', function (json) { RuntimeSetupGate.startupFailed(json); });
    lpBridge.on('exit', function (json) {
      var d = parseBridgePayload(json, {});
      RuntimeSetupGate.startupFailed({
        reason: 'sidecar_exit',
        detail: 'The processing service stopped unexpectedly.',
        diagnostics: d
      });
    });
    lpBridge.on('bootstrap_complete', function (json) {
      var b = parseBridgePayload(json, null);
      if (!b) return;
      applyGuidedTourEligibility(b);
      // One routing implementation, not two: completion routes through the
      // same admit() the initial bootstrap uses.
      RuntimeSetupGate.admit(b);
      if (!b.bootstrap_pending && b.runtime_health_state !== 'SETUP_REQUIRED') {
        normalBridgeAdmitted = true;
        if (normalBridgeActivityPending || !normalBridgeActivityStarted) startNormalBridgeActivity();
      }
    });
    lpBridge.on('recovery_notice', function (json) {
      var d = parseBridgePayload(json, null);
      var n = d && Number.isFinite(d.recovered) ? d.recovered : 0;
      if (n <= 0) return;
      toast('Processing resumed — ' + n + ' interrupted lecture' + (n === 1 ? '' : 's') + ' was returned to the queue.');
    });
    lpBridge.on('error', function (json) {
      var d = parseBridgePayload(json, {});
      var raw = String(d.error || d.message || 'The LecturePack runtime reported an error.');
      // N-2: backend and IPC failures reach the student as short friendly
      // copy; the raw technical string stays in the console log only.
      try { console.error('[lecturepack]', d.command || 'command', raw); } catch (err) {}
      toast(friendlyErrorMessage(raw, d.command));
      // N-4: a failed export must never leave the progress panel running.
      if (LP.state.exportPhase === 'running' && (d.command === 'export' || d.stage === 'Export')) {
        LP.state.exportPhase = 'idle'; renderExportPhase();
      }
      var title = $('proc-status-title');
      if (title && (d.kind === 'startup' || d.kind === 'bootstrap')) {
        title.textContent = 'LecturePack needs attention';
        title.title = raw;
        _applyLpState(title, 'failed');
      }
    });
    lpBridge.on('diagnostics', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var report = d.bundle || d.diagnostics || d;
      var reportEl = $('runtime-diagnostics-report');
      if (reportEl) reportEl.textContent = typeof report === 'string' ? report : JSON.stringify(report, null, 2);
    });
    lpBridge.on('repair_required', function (json) {
      var d = parseBridgePayload(json, null);
      if (d && d.detail) toast(d.detail);
    });
    lpBridge.on('runtime_missing', function (json) {
      var d = parseBridgePayload(json, null);
      if (d && d.detail) toast('Runtime component missing: ' + d.detail);
    });
    lpBridge.on('storage_warning', function (json) {
      var d = parseBridgePayload(json, null);
      if (d && d.message) toast(d.message);
    });
    lpBridge.on('demo_event', receiveDemoEvent);
    lpBridge.on('queue_changed', function (json) {
      var payload = parseBridgePayload(json, null);
      // The locked Electron contract carries the queue rows together with the
      // active slot and schedules. Keep accepting the historical direct array
      // shape for the Qt/browser adapters, but preserve the full object when
      // it crosses the JSONL sidecar boundary.
      var queue = Array.isArray(payload)
        ? { active: null, queue: payload, schedules: {} }
        : payload;
      if (!queue || typeof queue !== 'object' || !Array.isArray(queue.queue)) return;
      LP.data.queue = queue;
      renderQueue();
      renderScheduled();
      renderJobSwitcher();
      renderProcessJobState();
      renderProcessingStrip();
    });
    // Multi-file import returns a batch_import event; the renderer's
    // importDroppedFiles handles the response directly, but browse_video also
    // resolves with the jobs for a multi-selection. Open the batch setup panel.
    lpBridge.on('batch_import', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var jobs = (d && d.jobs) || [];
      if (jobs.length) openBatchImport(jobs);
    });

    lpBridge.on('study_progress', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      if (d.job_id && LP.state.jobId && d.job_id !== LP.state.jobId) return;
      var kind = d.kind === 'flashcards' ? 'flash' : d.kind === 'quiz' ? 'quiz' : '';
      if (!kind) return;
      var state = kind === 'quiz' ? LP.state.quiz : LP.state.flash;
      if (d.message) state.status = d.message;
      // The renderer's existing timer supplies a smooth ETA between backend
      // checkpoints. A real percentage from the sidecar is still useful as a
      // monotonic lower bound for the visible progress bar.
      if (typeof d.pct === 'number' && isFinite(d.pct)) {
        state.backendPct = Math.max(0, Math.min(100, d.pct));
      }
      if (state.generating) {
        (kind === 'quiz' ? renderQuiz : renderCard)();
      }
    });

    lpBridge.on('group_study_progress', function (json) {
      var p = parseBridgePayload(json, null);
      if (!p || typeof p !== 'object') return;
      if (studyV2.scope && studyV2.scope.type === 'group' &&
          studyV2.scope.groupName.toLowerCase() === String(p.group || '').toLowerCase()) {
        studyV2.scope.status = p.status || studyV2.scope.status;
        if (p.stage) studyV2.scope.stage = p.stage;
        if (p.error) studyV2.scope.error = p.error;
        if (p.reason) studyV2.scope.reason = p.reason;
        renderStudyScopeHeader();
        renderStudyGenerationState();
      }
    });

    lpBridge.on('pause_state', function (json) {
      var pauseState = parseBridgePayload(json, null);
      if (!pauseState || typeof pauseState !== 'object') return;
      var st = pauseState.state;
      var pause = $('btn-pause-job'), resume = $('btn-resume-job'),
          title = $('proc-status-title'), dot = $('proc-status-dot');
      if (st === 'pause_requested') {
        if (title) title.textContent = 'Finishing current step…';
        if (pause) { pause.disabled = true; pause.textContent = 'Pausing…'; }
        _applyLpState(title || dot, 'running');
      } else if (st === 'paused') {
        if (title) title.textContent = 'Paused';
        if (dot) dot.style.animation = 'none';
        if (pause) { pause.hidden = true; pause.disabled = false; pause.textContent = 'Pause'; }
        if (resume) resume.hidden = false;
        _applyLpState(title || dot, 'paused');
      } else if (st === 'resumed') {
        if (dot) dot.style.animation = 'lpblink 1s infinite';
        if (pause) pause.hidden = false;
        if (resume) resume.hidden = true;
        _applyLpState(title || dot, 'running');
      }
    });
    lpBridge.on('job_completed', function (json) {
      var m = parseBridgePayload(json, null);
      if (!m || typeof m !== 'object') return;
      LP.state.completedJob = m.job_id || '';
      // Paint the completion card only when the completed job is the one being
      // viewed; the stats are kept per job so switching back re-paints them.
      applyCompletionPanel(m);
      var pause = $('btn-pause-job'), resume = $('btn-resume-job');
      if (pause) pause.hidden = true;
      if (resume) resume.hidden = true;
      // F-3: every readout settles to the terminal state from one place.
      if (m.job_id === LP.state.jobId) settleTerminalStatus('complete');
    });
    lpBridge.on('notification_prefs', function (json) {
      var payload = parseBridgePayload(json, null);
      var prefs = payload && payload.prefs && typeof payload.prefs === 'object' ? payload.prefs : payload;
      if (!prefs || typeof prefs !== 'object') return;
      Array.prototype.forEach.call(document.querySelectorAll('[data-notif]'), function (cb) {
        if (cb.dataset.notif in prefs) cb.checked = !!prefs[cb.dataset.notif];
      });
    });
    // BUG-04: the storage widget ships hidden and only appears once a backend
    // actually reports usage. `ok:false` (demo adapter, or a failed walk) keeps
    // it hidden rather than showing an invented figure -- inventing one was the
    // original bug.
    lpBridge.on('storage_changed', function (json) {
      var w = $('storage-widget');
      if (!w) return;
      var s;
      s = parseBridgePayload(json, null);
      if (!s || s.ok === false) { w.hidden = true; return; }
      var human = function (bytes) {
        var value = Number(bytes);
        if (!isFinite(value) || value < 0) return '—';
        var units = ['B', 'KB', 'MB', 'GB', 'TB'], index = 0;
        while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
        return (index === 0 ? Math.round(value) : value.toFixed(1)) + ' ' + units[index];
      };
      var usedLabel = s.used_h || human(s.used), freeLabel = s.free_h || human(s.free);
      $('storage-label').textContent = usedLabel + ' · ' + freeLabel + ' free';
      setFill('storage-bar', s.pct != null ? s.pct : s.percent || 0);
      w.hidden = false;
    });

    lpBridge.on('jobs_changed', function (json) {
      var jobs = parseBridgePayload(json, null);
      if (!Array.isArray(jobs)) return;
      var alive = {};
      jobs.forEach(function (job) { if (job && job.id) alive[job.id] = true; });
      LP.data.jobs = jobs;
      // Drop the per-lecture workspace cache for anything that no longer
      // exists. Without this a deleted lecture's slides, transcript and scroll
      // position stayed in memory for the rest of the session, and a reused id
      // (or a stale late event) could paint the dead workspace back onto a
      // live screen.
      Object.keys(LP.byJob).forEach(function (id) {
        if (!alive[id]) delete LP.byJob[id];
      });
      // Prune selection state before any job-removal navigation. Keeping this
      // adjacent to the received summary array makes the data-shape boundary
      // explicit and prevents a stale selection count during that navigation.
      if (LP.state.selecting) {
        Object.keys(LP.state.selected).forEach(function (id) {
          if (!alive[id]) delete LP.state.selected[id];
        });
        renderSelCount();
      }
      var viewedJobRemoved = !!(LP.state.jobId && !_jobById(LP.state.jobId));
      if (viewedJobRemoved) {
        setActiveJob('', '');
        setScreen('home');
      }
      renderJobs();           // poster URLs are stable, so loaded ones stay cached
      restoreAppSessionOnce();
      renderProcOptions();
      // Track the processing slot from the list truth: the running job is the
      // active one; a terminal active job has released the slot.
      var runningId = '';
      LP.data.jobs.forEach(function (j) { if (j && j.status === 'running' && !runningId) runningId = j.id; });
      if (runningId) LP.state.activeJobId = runningId;
      else if (LP.state.activeJobId) {
        var activeStill = _jobById(LP.state.activeJobId);
        if (!activeStill || activeStill.status !== 'running') LP.state.activeJobId = '';
      }
      renderJobSwitcher();
      renderProcessJobState();
      renderProcessingStrip();
      // F-3: settle the readouts once the job list can confirm the active
      // job's terminal state. On relaunch active_job legitimately arrives
      // BEFORE this list exists, so setActiveJob alone cannot settle.
      var activeEntry = (LP.data.jobs || []).filter(function (j) { return j && j.id === LP.state.jobId; })[0];
      if (activeEntry && activeEntry.status === 'done') settleTerminalStatus('complete');
      else if (activeEntry && activeEntry.status === 'failed') settleTerminalStatus('failed');
      else if (activeEntry && activeEntry.status === 'cancelled') settleTerminalStatus('cancelled');
      else if (activeEntry && activeEntry.status === 'interrupted') settleTerminalStatus('interrupted');
    });

    // ---- import from a link ----
    lpBridge.on('media_link_state', function (json) {
      var s = parseBridgePayload(json, null);
      mediaLink.available = !!s.available;
      mediaLink.version = s.version || '';
      var btn = $('btn-paste-link');
      // Link importing is a release feature. Keep the action visible when the
      // packaged provider fails so the user sees the actual capability state.
      if (btn) {
        btn.hidden = false;
        btn.disabled = !mediaLink.available;
        btn.title = mediaLink.available
          ? ('Bundled yt-dlp ' + (mediaLink.version || 'is ready'))
          : (s.reason || 'Link importing is unavailable because the bundled yt-dlp runtime could not load.');
        btn.setAttribute('aria-label', mediaLink.available ? 'Paste a link' : 'Paste a link unavailable');
      }
      if (mediaLink.available) lpBridge.call('get_media_downloads');
    });

    lpBridge.on('media_probe', function (json) {
      var info = parseBridgePayload(json || '{}', {});
      var hasReady = Array.isArray(info.items) && info.items.some(function (item) { return item && item.ok; });
      if (!info.ok && !hasReady) {
        // N-6: map yt-dlp's technical stderr to student copy; keep the raw
        // text on the tooltip as the optional details view.
        var probeFriendly = friendlyLinkError(info.error) || 'That link could not be read.';
        setLinkMsg(probeFriendly, true);
        var linkMsgEl = $('link-msg');
        if (linkMsgEl && info.error) linkMsgEl.title = String(info.error);
        return;
      }
      if (mediaLink.probeModal) { mediaLink.probeModal.close(); mediaLink.probeModal = null; }
      linkConfirmDialog(info);
    });

    lpBridge.on('media_progress', function (json) {
      try {
        var update = parseBridgePayload(json || '{}', {});
        var updateId = update.download_id != null ? String(update.download_id) : String(update.id || '');
        var item = mediaLink.downloads.filter(function (candidate) { return downloadId(candidate) === updateId; })[0];
        if (item) {
          ['status', 'legacy_status', 'progress', 'pct', 'eta', 'eta_seconds', 'speed', 'downloaded', 'total'].forEach(function (key) {
            if (update[key] !== undefined) item[key] = update[key];
          });
          renderDownloads();
        }
      } catch (err) { /* downloads_changed remains authoritative */ }
    });

    lpBridge.on('downloads_changed', function (json) {
      var payload = parseBridgePayload(json || '{}', {});
      mediaLink.downloads = Array.isArray(payload.downloads) ? payload.downloads : [];
      renderDownloads();
    });

    lpBridge.on('media_done', function (json) {
      var r = parseBridgePayload(json || '{}', {});
      if (r.ok) toast('Downloaded ' + (r.name || 'the recording'));
      else if (r.cancelled) toast('Download cancelled');
      // Raw failure text stays in renderDownloads() behind its <details>
      // disclosure; this terminal event only surfaces a non-blocking toast.
      else toast(friendlyLinkError(r.error) || 'A download failed — open Downloads for details.');
    });
    lpBridge.on('job_deleted', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      if (d.bulk) {
        var msg = d.ok
          ? (d.count + (d.count === 1 ? ' lecture' : ' lectures') + ' deleted · ' + (d.freed || '') + ' freed')
          : (d.error || 'Delete failed');
        if (d.ok && (d.failed || []).length) msg += ' · ' + d.failed.length + ' could not be deleted';
        toast(msg);
        (d.ids || []).forEach(function (id) {
          // Deactivate FIRST, same reason as the single-delete path below:
          // setActiveJob snapshots the outgoing lecture into byJob, so dropping
          // the cache entry before the switch would put it straight back.
          if (id === LP.state.jobId) setActiveJob('', '');
          if (id === LP.state.activeJobId) LP.state.activeJobId = '';
          delete LP.byJob[id];
          delete LP.state.selected[id];
          delete statusByJob[id];
          delete runningByJob[id];
        });
        renderSelCount();
        if (lpBridge.connected()) lpBridge.call('list_jobs');
        return;
      }
      toast(d.ok ? ('Lecture deleted · ' + (d.freed || '') + ' freed') : 'Delete failed');
      // Drop the deleted lecture's cached workspace so it can never come back
      // if a job id is ever reused, and empty the screens if it was active.
      if (d.ok && d.id) {
        // Deactivate FIRST: setActiveJob snapshots the outgoing lecture into
        // byJob, so deleting before the switch would put it straight back.
        if (d.id === LP.state.jobId) setActiveJob('', '');
        if (d.id === LP.state.activeJobId) LP.state.activeJobId = '';
        delete LP.byJob[d.id];
        delete statusByJob[d.id];
        delete runningByJob[d.id];
      }
      if (d.ok && lpBridge.connected()) lpBridge.call('list_jobs');
    });

    // The backend owns which job is PROCESSING; the UI decides which job is
    // VIEWED. active_job updates the processing slot and auto-selects a NEW
    // active job once (so Process follows a job the moment it starts), but it
    // never yanks the user away from an older job they have opened since.
    lpBridge.on('active_job', function (json) {
      var a = parseBridgePayload(json || '{}', {});
      if (a.id && LP.data.jobs.length && !LP.data.jobs.some(function (job) { return job.id === a.id; })) {
        // Ignore a stale active-slot event after deletion.
        if (LP.state.jobId === a.id) setActiveJob('', '');
        return;
      }
      if (!a.id) {
        LP.state.activeJobId = '';
        autoSelectedActiveId = '';
        renderJobSwitcher();
        return;
      }
      // Only a job the list actually reports as running is "processing". The
      // backend also re-asserts a non-running restored/default slot; that
      // never counts as the active processing job.
      var running = LP.data.jobs.some(function (j) { return j && j.id === a.id && j.status === 'running'; });
      LP.state.activeJobId = running ? a.id : '';
      // Auto-follow ONCE per genuinely new processing job. On relaunch with no
      // view yet, also follow the restored slot so the workspace is not empty.
      if (a.id !== autoSelectedActiveId && (running || !LP.state.jobId)) {
        autoSelectedActiveId = a.id;
        selectJob(a.id, { silent: true });
      }
      renderJobSwitcher();
    });
    lpBridge.on('pipeline_changed', function (json) {
      var p = parseBridgePayload(json, null);
      if (!p || typeof p !== 'object') return;
      var owner = p.job || LP.state.jobId;
      // Route by job id: the pipeline of the job being viewed updates the live
      // workspace; any other job's pipeline accumulates in its per-job store so
      // switching back shows the latest stages without waiting for a replay.
      var viewed = routeJobPayload(p, function (data) {
        if (p.log) data.pipeline.log = p.log;
        data.pipeline.title = p.title || data.pipeline.title;
        data.pipeline.meta = p.meta || data.pipeline.meta;
        data.pipeline.stages = p.stages || data.pipeline.stages;
      });
      // D-08: pipeline_changed only ever reaches here for a NORMAL job
      // (demo signals are filtered by _forward_normal on the Python side),
      // so any non-"done" stage means a real job is actively running.
      // _on_pipeline_completed sets every stage to "done" before its final
      // emit, so this naturally clears on success too; the failure path
      // clears via the terminal status_changed label below.
      var running = Array.isArray(p.stages) &&
        p.stages.some(function (st) { return st && st.state !== 'done'; });
      runningByJob[owner] = running;
      if (viewed) {
        LP.state.pipelineRunning = running;
        schedulePipelineRender();
        renderSlideDetectionPreset();
      }
      // Keep the Home card's stage label current from the pipeline payload.
      var activeStage = '';
      if (Array.isArray(p.stages)) {
        p.stages.forEach(function (st) {
          if (st && st.state === 'active' && !activeStage) activeStage = st.label || st.name || '';
        });
      }
      if (activeStage) applyJobLive(owner, { stage: activeStage });
    });
    lpBridge.on('log_line', function (json) {
      var line = parseBridgePayload(json, null);
      if (!line || typeof line !== 'object') return;
      var owner = line.job || LP.state.jobId;
      if (!owner) return;
      var viewed = routeJobPayload(line, function (data) {
        data.pipeline.log.push(line);
        if (data.pipeline.log.length > 500) data.pipeline.log.shift();
      });
      if (viewed) schedulePipelineRender();   // was renderPipeline() per line -- see the comment there
    });
    lpBridge.on('status_changed', function (json) {
      var s = parseBridgePayload(json, null);
      if (!s || typeof s !== 'object') return;
      var owner = s.job || LP.state.jobId;
      if (!owner) return;
      var incomingTerminal = s.label === 'Failed' || (function (t) {
        return t === 'failed' || t === 'done' || t === 'complete' || t === 'cancelled';
      })(normalizedProcessingText(s.label));
      var terminalLabel = normalizedProcessingText(s.label);

      var listEntry = _jobById(owner);
      // F-3: the job list is the truth about whether a job is finished. On
      // relaunch the backend replays the last LIVE status of a restored job
      // ("Processing - 100%", "Detecting slides"); no terminal event ever
      // follows it. A non-terminal status for a job the list already calls
      // done/failed/cancelled/interrupted is that replay — ignore it entirely
      // so neither the sidebar nor the Home card reverts to Processing.
      var listTerminal = listEntry && (listEntry.status === 'done' || listEntry.status === 'failed' ||
        listEntry.status === 'cancelled' || listEntry.status === 'interrupted') ? listEntry.status : null;
      if (listTerminal && !incomingTerminal) {
        if (owner === LP.state.jobId) settleTerminalStatus(listTerminal === 'done' ? 'complete' : listTerminal);
        return;
      }

      // 1) Keep the matching Home card live BY JOB ID — never only the viewed
      // job. Status transitions rebuild the card; progress-only updates patch
      // the bar and label in place so Home never freezes mid-transcription.
      if (listEntry) {
        var patch = {};
        if (incomingTerminal) {
          patch.status = (s.label === 'Failed' || terminalLabel === 'failed') ? 'failed'
            : terminalLabel === 'cancelled' ? 'cancelled'
            : terminalLabel === 'interrupted' ? 'interrupted' : 'done';
          patch.pct = patch.status === 'done' ? 100 : 0;
          runningByJob[owner] = false;
          if (owner === LP.state.activeJobId) LP.state.activeJobId = '';
          // The slot is released: a next queued job that starts is a NEW active
          // job and is allowed to auto-follow once.
          if (owner === autoSelectedActiveId) autoSelectedActiveId = '';
          delete processingEta[owner];
        } else {
          var processingLabel = s.label === 'Processing' || /- \d+%$/.test(String(s.detail || ''));
          if (processingLabel) patch.status = 'running';
          var stage = stageFromStatusDetail(s.detail);
          if (stage) patch.stage = stage;
          if (s.pct !== undefined) patch.pct = s.pct;
          recordProcessingEta(owner, patch.stage || listEntry.stage || '', patch.pct !== undefined ? patch.pct : listEntry.pct);
        }
        applyJobLive(owner, patch);
        updateJobCardDom(owner);
      }

      // 2) The sidebar/status readouts follow the VIEWED job. Live labels are
      // remembered per job so switching back repaints without waiting for a
      // replay; a job processing in the background never overwrites the screen.
      if (owner === LP.state.jobId) {
        pendingProcessingStatus = Object.assign({}, pendingProcessingStatus, s);
        scheduleProcessingRender('status');
        // D-08: _on_pipeline_failed (Python) never re-emits pipeline_changed
        // with the failed stage cleared, so pipelineRunning must be released
        // explicitly on the terminal "Failed" status label. "Done" is handled
        // here too as a redundant safety net -- the all-"done" stages payload
        // already clears it above.
        if (incomingTerminal) {
          LP.state.pipelineRunning = false;
          runningByJob[owner] = false;
          // PC polish: clear stale processing text (e.g. a lingering
          // "Transcribing audio") so the primary status area returns to Idle
          // when no job is actively processing.
          pendingProcessingStatus = {};
          lastStatusRenderKey = null;
          var statusLabel = $('status-state');
          if (statusLabel) statusLabel.textContent = 'Idle';
          var statusPct = $('status-detail');
          if (statusPct) statusPct.textContent = '';
          setFill('status-bar', 0);
          renderSlideDetectionPreset();
          // F-3: the terminal event's own readouts were previously dropped with
          // the cleared pending dict, freezing the sidebar/status bar mid-stage
          // ("Processing - 86%" / "Detecting slides") forever. Paint the
          // settled terminal state directly from the current job state.
          settleTerminalStatus(terminalLabel === 'failed' || s.label === 'Failed' ? 'failed' :
            terminalLabel === 'cancelled' ? 'cancelled' : 'complete');
        }
      } else {
        statusByJob[owner] = Object.assign({}, statusByJob[owner], s);
      }
      refreshControlStates();
      renderProcessingStrip();
    });
    lpBridge.on('slides_changed', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var viewed = routeJobPayload(d, function (data) {
        data.slides = d.slides || data.slides;
        if (d.duration) data.duration = d.duration;
        if (d.durationMid) data.durationMid = d.durationMid;
      });
      if (!viewed) return;
      if (LP.state.viewingSlide >= LP.data.slides.length) LP.state.viewingSlide = 0;
      hideScrub();  // job changed — drop any stale hover preview
      renderSlides();
      updateExportPdfDescription();
    });
    lpBridge.on('transcript_changed', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var viewed = routeJobPayload(d, function (data) {
        if (d.reviewSegments) data.reviewSegments = d.reviewSegments;
        if (d.transcript) data.transcript = d.transcript;
      });
      if (!viewed) return;
      if (d.reviewSegments) renderReviewTranscript();
      if (d.transcript) renderTranscript();
    });
    lpBridge.on('study_changed', function (json) {
      var sd = parseBridgePayload(json, null);
      if (!sd || typeof sd !== 'object') return;
      var viewed = routeJobPayload(sd, function (data) { data.study = sd; });
      if (!viewed) return;
      renderStudy();
      var na = $('notes-area');
      if (na && document.activeElement !== na) na.value = LP.data.study.notes || '';
    });
    lpBridge.on('quiz_changed', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var q = LP.state.quiz;
      var viewed = routeJobPayload(d, function (data) {
        data.quiz = { questions: d.questions || [], provider: d.provider || '', model: d.model || '', meta: d.meta || {} };
      });
      if (!viewed) return;
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
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var q = LP.state.quiz;
      q.status = d.message || '';
      if (d.state === 'ready' || d.state === 'error' || d.state === 'cancelled') stopGen('quiz');
      if (d.state === 'error') { toast(d.message || 'Quiz failed'); renderQuiz(); }
    });
    lpBridge.on('flashcards_changed', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var f = LP.state.flash;
      var viewed = routeJobPayload(d, function (data) {
        data.flashcards = { cards: d.cards || [], provider: d.provider || '', model: d.model || '', meta: d.meta || {} };
      });
      if (!viewed) return;
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
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var f = LP.state.flash;
      f.status = d.message || '';
      if (d.state === 'ready' || d.state === 'error' || d.state === 'cancelled') stopGen('flash');
      if (d.state === 'error') { toast(d.message || 'Flashcards failed'); renderCard(); }
    });
    lpBridge.on('export_progress', function (json) {
      var p = parseBridgePayload(json, null);
      if (!p || typeof p !== 'object') return;
      if (p.job && p.job !== LP.state.jobId) return;   // another job's export
      LP.state.exportPhase = 'running'; renderExportPhase();
      setFill('export-progress-bar', p.pct || 0);
      $('export-progress-label').textContent = p.label || '';
    });
    lpBridge.on('export_done', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      var viewed = routeJobPayload(d, function (data) {
        data.exportFiles = d.files || data.exportFiles;
      });
      if (!viewed) return;
      LP.state.exportPhase = 'done';
      renderExportPhase();
      if (d.meta) $('export-done-meta').textContent = d.meta;
    });
    lpBridge.on('ai_token', function (text) {
      var payload = parseBridgePayload(text, text);
      if (payload && typeof payload === 'object') {
        if (payload.job && payload.job !== LP.state.jobId) return;
        text = payload.text || '';
      }
      if (studyV2.askStreaming) appendStudyAskText(text, false);
      else appendAiText(text, false);
    });
    lpBridge.on('ai_done', function (json) {
      var payload = parseBridgePayload(json, null);
      if (payload && payload.job && payload.job !== LP.state.jobId) return;
      if (studyV2.askStreaming) appendStudyAskText(studyV2.askAnswer, true);
      else { LP.state.streaming = false; renderChat(); }
    });
    lpBridge.on('ai_sources', function (json) {
      var payload = parseBridgePayload(json, null);
      if (payload && payload.job && payload.job !== LP.state.jobId) return;
      appendStudyAskSources(payload && payload.sources ? payload.sources : [],
        payload ? payload.provenance : '');
    });
    lpBridge.on('study_generation', function (json) {
      var payload = parseBridgePayload(json, null);
      if (!payload || (payload.job && payload.job !== LP.state.jobId)) return;
      studyV2.content = studyV2.content || { concepts: [], flashcards: [], quiz: [] };
      studyV2.content.study_status = payload.status || studyV2.content.study_status || 'preparing';
      studyV2.content.generation_metadata = studyV2.content.generation_metadata || {};
      if (payload.stage) studyV2.content.generation_metadata.stage = payload.stage;
      if (payload.progress_percent != null) studyV2.content.generation_metadata.progress_percent = payload.progress_percent;
      if (payload.error) studyV2.content.generation_metadata.last_error = { message: payload.error };
      renderStudyGenerationState();
      // A refresh that failed must correct the optimistic "Refreshing…" toast
      // the click put on screen, otherwise Regenerate reads as a dead button.
      if (payload.refresh_status === 'failed') {
        toast(payload.error || 'Those Study items could not be refreshed.');
      }
      if (payload.status === 'ready' || payload.status === 'basic' || payload.status === 'failed' || payload.refresh_status === 'ready') {
        studyV2Load();
      }
    });
    lpBridge.on('study_teach_ready', function (json) {
      var payload = parseBridgePayload(json, null);
      if (!payload || (payload.job && payload.job !== LP.state.jobId)) return;
      studyV2.teachLoading = false;
      if (payload.ok && payload.result) {
        studyV2.teachConceptId = payload.concept_id || studyV2.teachConceptId;
        studyV2.teachResult = payload.result;
        studyV2.teachGrade = null;
      } else {
        toast(payload.error || 'Teach Me could not prepare this lesson.');
      }
      renderStudyTeach();
    });
    lpBridge.on('study_short_answer_graded', function (json) {
      var payload = parseBridgePayload(json, null);
      if (!payload || (payload.job && payload.job !== LP.state.jobId)) return;
      var questionId = String(payload.question_id || '');
      if (!payload.ok || !payload.result) {
        studyV2.quizGrading = false;
        studyV2.quizGradingQuestionId = '';
        toast(payload.error || 'This answer could not be graded.');
        if (questionId.indexOf('teach:') === 0) renderStudyTeach();
        else renderStudyQuiz();
        return;
      }
      if (payload.progress) studyV2.progress = payload.progress;
      if (payload.summary) studyV2.summary = payload.summary;
      if (questionId.indexOf('teach:') === 0) {
        studyV2.teachGrade = payload.result;
        renderStudyTeach();
      } else {
        studyV2.quizGrades[questionId] = payload.result;
        studyV2.quizGrading = false;
        studyV2.quizGradingQuestionId = '';
        var questions = quizPool();
        var index = questions.findIndex(function (question) { return question.id === questionId; });
        if (index >= 0 && studyV2.quizAnswers.indexOf(index) < 0) {
          studyV2.quizAnswers.push(index);
          if (payload.result.correct) studyV2.quizCorrect++;
        }
        studyV2PersistView();
        renderStudyQuiz();
      }
    });
    lpBridge.on('groq_status', function (json) {
      var d = parseBridgePayload(json, null), el = $('groq-status');
      if (!d || typeof d !== 'object') return;
      if (el) { el.textContent = d.message || ''; el.style.color = d.has_key ? 'var(--secondary-text)' : 'var(--muted)'; }
      if (d.backend && LP.ui) LP.ui.reflectBackend(d.backend);
    });
    lpBridge.on('vulkan_status', function (json) {
      var d = parseBridgePayload(json, null), el = $('vulkan-status');
      if (!d || typeof d !== 'object') return;
      if (!el) return;
      if (d.state === 'checking' || /checking/i.test(d.message || '')) {
        setComputeReadyFallback();
        return;
      }
      el.textContent = d.message || (d.state === 'available' ? 'Vulkan available' : 'Vulkan unavailable · CPU · AVX2 ready');
      el.style.color = (d.state === 'loaded' || d.state === 'available') ? 'var(--secondary-text)' : 'var(--muted)';
    });
    lpBridge.on('cuda_status', function (json) {
      var d = parseBridgePayload(json, null), el = $('cuda-status');
      if (!d || typeof d !== 'object') return;
      if (!el) return;
      if (d.state === 'checking' || /checking/i.test(d.message || '')) {
        setComputeReadyFallback();
        return;
      }
      el.textContent = d.message || (d.state === 'available' ? 'CUDA available' : 'CUDA unavailable · CPU · AVX2 ready');
      el.style.color = (d.state === 'loaded' || d.state === 'available') ? 'var(--secondary-text)' : 'var(--muted)';
    });
    lpBridge.on('cuda_pack', function (json) {
      var d; try { d = JSON.parse(json); } catch (e) { return; }
      var box = $('cuda-pack'); if (!box) return;
      var st = d.state;
      var busy = st === 'downloading' || st === 'verifying' || st === 'installing';
      // Offer the pack only on an NVIDIA machine that hasn't installed it yet.
      var installationAvailable = d.installation_available === true || d.install_available === true || d.can_install === true;
      var show = installationAvailable && d.gpu_present && (!d.installed || busy || st === 'error' || st === 'cancelled');
      box.hidden = !show;
      if (!show) return;
      $('cuda-pack-progress').hidden = !busy;
      $('btn-cuda-pack-install').disabled = busy;
      var note = $('cuda-pack-note');
      if (st === 'downloading') {
        setFill('cuda-pack-bar', d.percent || 0);
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
      var s = parseBridgePayload(json, null);
      if (!s || typeof s !== 'object') return;
      var lbl = s.label || 'Built-in Study';
      var builtin = lbl === 'Built-in Study';
      var err = lbl === 'AI error';
      var txt = lbl + (s.model && s.model !== '—' && !builtin ? ' · ' + s.model : '');
      var col = builtin ? 'var(--secondary-text)' : (err ? 'var(--muted)' : 'var(--green)');
      $('ai-status').style.color = col; $('ai-status').style.borderColor = col;
      setStatusDotText($('ai-status'), txt, col, false);
      if (s.model) setModelValue(s.model);
    });
    lpBridge.on('smart_study', function (json) {
      try { renderSmartStudy(JSON.parse(json)); } catch (e) { console.error('smart_study', e); }
    });
    lpBridge.on('onboarding', function (json) {
      var d = parseBridgePayload(json, null);
      if (!d || typeof d !== 'object') return;
      setImporting(false);
      // Demo import emits the same onboarding event as a normal file import.
      // The guided demo has already moved to Process before that event arrives;
      // reopening the New Job overlay here covered the real processing screen.
      // Normal imports (no active demo session) always show the pre-processing
      // setup panel so quality and output can be chosen before Start.
      var demoIsActive = guidedDemo.snapshot().active;
      if (demoIsActive) {
        setOnb(null);
        return;
      }
      LP.state.setupJobId = d.job || '';
      if (d.name) $('onb-file-name').textContent = d.name;
      if (d.meta) $('onb-file-meta').textContent = d.meta;
      setScreen('home');
      setOnb('detected');
    });
    lpBridge.on('update_available', function (json) {
      var d = parseBridgePayload(json, null);
      if (d && typeof d === 'object') showWhatsNew(d, 'available');
    });
    lpBridge.on('update_progress', function (json) {
      // The transport always delivers a JSON STRING of the payload object, never
      // a bare number. Treating it as one produced "Downloading update… NaN%"
      // with the bar stuck at 0, because Math.round('{"pct":42}') is NaN.
      var d = parseBridgePayload(json, null);
      var pct = Number(d && typeof d === 'object' ? d.pct : d);
      if (!isFinite(pct)) return;                    // never paint NaN
      pct = Math.max(0, Math.min(100, pct));
      if ($('whatsnew-overlay').hidden) $('whatsnew-overlay').hidden = false;
      if (LP.state.updatePhase !== 'downloading') updSetPhase('downloading');
      $('whatsnew-progress-bar').style.width = pct + '%';
      $('whatsnew-progress-label').textContent = pct >= 100 ? 'Verifying…' : 'Downloading update… ' + Math.round(pct) + '%';
    });
    lpBridge.on('update_ready', function () {
      // update_state 'ready' already reconfigured the buttons; this is a backstop.
      if (LP.state.updatePhase !== 'ready') updSetPhase('ready');
    });
    lpBridge.on('update_error', function (json) {
      // Same transport contract: an object arrives as a JSON string, so the raw
      // envelope was being shown to the user as the error text.
      var d = parseBridgePayload(json, null);
      var msg = (d && typeof d === 'object' ? (d.message || d.error) : d) || 'Unknown error';
      updSetPhase(LP.state.updateMode === 'installed' ? 'installed' : 'available');
      updMsg(String(msg), 'error');
      $('update-status').textContent = 'Update failed: ' + msg;
    });
    lpBridge.on('update_state', function (json) {
      var d; try { d = JSON.parse(json); } catch (e) { return; }
      var phase = d.phase;
      if (phase === 'checking') { $('update-status').textContent = 'Checking…'; }
      else if (phase === 'uptodate') { $('update-status').textContent = d.message || 'You’re up to date'; }
      else if (phase === 'unavailable' || phase === 'not_available') { $('update-status').textContent = d.message || 'Updates are not available in this build.'; }
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
    lpBridge.on('whatsnew', function (json) {
      var d = parseBridgePayload(json, null);
      if (d && typeof d === 'object') showWhatsNew(d, 'installed');
    });
    lpBridge.on('settings_changed', function (json) {
      var s = parseBridgePayload(json, null);
      if (!s || typeof s !== 'object') return;
      if (s.theme) applyTheme(s.theme, false);
      if (s.version) applyAppVersion(s.version);
      if (s.model_path) setWhisperModelPath(s.model_path);
      if (s.endpoint) {
        var ep = $('ai-endpoint-url');
        if (ep && document.activeElement !== ep) ep.value = s.endpoint;
      }
      // TODO: COMPUTE_IDS has no "auto" key — design decision needed for
      // default engine highlight. Leave as-is for now (no button highlighted).
      if (s.engine && LP.ui) LP.ui.reflectEngine(s.engine);
      if (s.transcription_backend && LP.ui) LP.ui.reflectBackend(s.transcription_backend);
      if (s.slide_detection_preset !== undefined) {
        slideDetectionPreset.reflect(s.slide_detection_preset);
        renderSlideDetectionPreset();
      }
      if (s.ollama_model) {
        setModelValue(s.ollama_model);
        var msel = $('ai-model-select');
        if (msel && msel.querySelector('option[value="' + s.ollama_model + '"]')) msel.value = s.ollama_model;
      }
      if (s.actual_backend) {
        runtimeBackendLabel = friendlyProcessingLabel(s.actual_backend) || s.actual_backend;
        $('status-right').textContent = runtimeBackendLabel;
      }
      if (s.export_dir) $('export-dir').textContent = s.export_dir;
      if (s.update_status) $('update-status').textContent = s.update_status;
    });
    lpBridge.on('ollama_models', function (json) {
      var d = parseBridgePayload(json, null), sel = $('ai-model-select');
      if (!d || typeof d !== 'object') return;
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
      if (backend && backend.get_bootstrap) {
        lpBridge.call('get_bootstrap').then(function (json) {
          if (!json) {
            normalBridgeAdmitted = true;
          }
          if (!json) { startNormalBridgeActivity(); return; }
          try {
            var b = JSON.parse(json);
            if (b.theme) applyTheme(b.theme, false);
            if (b.version) applyAppVersion(b.version);
            applyGuidedTourEligibility(b);
            RuntimeSetupGate.admit(b);
            // Gate on bootstrap_pending, never on a runtime_health_state
            // string comparison (that string legitimately reads "PENDING"
            // during the checking window). Both of startNormalBridgeActivity()'s
            // calls are admission-guarded on the Python side, so starting
            // them while pending would surface a spurious setup-required
            // diagnostics payload behind the honest progress panel.
            if (!b.bootstrap_pending && b.runtime_health_state !== 'SETUP_REQUIRED') {
              normalBridgeAdmitted = true;
              startNormalBridgeActivity();
            }
          } catch (e) { console.error('bootstrap parse', e); }
        });
      } else startNormalBridgeActivity();
    });
  }

  /* ======================= QOL features (multi-import, strip, search,
       resume state, command palette) ======================= */

  // ---- Feature 1: multi-video import + batch setup ----
  var batchJobs = [];   // [{id, name}] imported in the current batch
  var batchMode = 'study', batchQuality = 'balanced';
  // Feature 1: remember the most-recently-used batch output mode and quality
  // and preselect them the next time a batch is imported.
  var batchPresetStore = (function () {
    var KEY = 'lecturepack.batchpreset.v1';
    function read() { try { return JSON.parse(browserStorage().getItem(KEY) || '{}'); } catch (_) { return {}; } }
    function write(data) { try { browserStorage().setItem(KEY, JSON.stringify(data)); } catch (_) {} }
    return {
      load: function () {
        var saved = read();
        return {
          mode: saved.mode === 'study' || saved.mode === 'transcript' || saved.mode === 'slides' ? saved.mode : 'study',
          quality: saved.quality === 'high' || saved.quality === 'balanced' ? saved.quality : 'balanced'
        };
      },
      save: function (mode, quality) {
        write({ mode: mode, quality: quality });
      }
    };
  })();

  /* Module scope, NOT inside wire(). These were nested in wire() while the
     only caller, importDroppedFiles, is module scope -- so every real file
     drop threw "ReferenceError: importDroppedVideo is not defined" and died
     silently, with no toast, no import and no visible failure. That is the
     whole "drag and drop does nothing" bug. Both are pure functions over
     module state (importingFile, lpBridge, toast, setOnb, setImporting), so
     they belong here. */
  function friendlyImportError(result) {
    if (!result || !result.code) return (result && result.error) || 'The video could not be imported.';
    var code = String(result.code);
    if (code === 'RESOLVE_FAILED') return 'LecturePack could not access that file. Try Browse for video.';
    if (code === 'NOT_FOUND') return 'That video could not be found. It may have been moved or removed.';
    if (code === 'UNREADABLE') return 'LecturePack cannot read that video. Check the file permissions or copy it to a local folder.';
    if (code === 'FFPROBE_FAILED') return 'LecturePack could not read this video format.';
    if (code === 'FEATURE_UNAVAILABLE') return '';
    return (result && result.error) || 'The video could not be imported.';
  }
  function importDroppedVideo(file) {
    if (!file || importingFile) return;
    var path = lpBridge.pathForFile ? lpBridge.pathForFile(file) : '';
    if (!path) {
      toast('LecturePack could not access that file. Try Browse for video.');
      return;
    }
    if (!lpBridge.connected()) {
      setOnb('detected');
      return;
    }
    // Drop and Browse converge on the same native import: the path is
    // resolved here (webUtils in the preload), then the host validates it
    // and the sidecar inspects it with FFprobe.
    importingFile = file.name || path;
    setImporting(true, importingFile);
    setOnb(null); // remove the drop overlay immediately
    lpBridge.call('import_video', { path: path }).then(function (result) {
      setImporting(false);
      importingFile = null;
      if (result && result.ok === false) {
        var message = friendlyImportError(result);
        if (message) toast(message);
      }
    }, function () {
      setImporting(false);
      importingFile = null;
    });
  }

  function importDroppedFiles(files) {
    if (importingFile) return;
    // A drop that carries NO file at all used to return in silence, so the
    // window simply swallowed it and the feature read as completely broken.
    // Windows delivers nothing when the drag starts from a virtual shell view
    // -- Explorer's Home/Recent list, "Gallery", or a cloud placeholder that is
    // not downloaded -- because those entries have no real path to hand over.
    // Say so, and name the way out.
    if (!files || !files.length) {
      toast('That drop did not include a file. Dragging from Explorer’s Home or Recent list often sends nothing — open the real folder, or use Browse for video.');
      return;
    }
    var paths = [];
    for (var i = 0; i < files.length; i++) {
      var path = lpBridge.pathForFile ? lpBridge.pathForFile(files[i]) : '';
      if (path) paths.push(path);
    }
    if (!paths.length) {
      toast('LecturePack could not read a path for those files. If they came from Explorer’s Home or Recent list, open the real folder instead, or use Browse for video.');
      return;
    }
    if (!lpBridge.connected()) {
      setOnb('detected');
      return;
    }
    // A single media file follows the tuned single-video import path. Any
    // folder (no media extension) or any multi-item batch flows through the
    // host's import_paths, which expands folders recursively and imports every
    // supported media file through the normal pipeline.
    var singleFile = paths.length === 1 && /\.(mp4|avi|mkv|mov|m4v|webm|mpeg|mpg|wmv)$/i.test(paths[0]);
    if (singleFile) {
      importDroppedVideo(files[0]);
      return;
    }
    // Batch: import every path (files and folders) via the host expansion.
    importingFile = files[0].name || paths[0];
    setImporting(true, importingFile);
    setOnb(null);
    lpBridge.call('import_paths', { paths: paths }).then(function (result) {
      setImporting(false);
      importingFile = null;
      if (!result || result.ok === false) {
        var message = friendlyImportError(result);
        if (message) toast(message);
        return;
      }
      var jobs = (result && result.jobs) || [];
      if (!jobs.length) {
        if (result.failures && result.failures.length) toast('None of the selected videos could be imported.');
        return;
      }
      openBatchImport(jobs);
    }, function () {
      setImporting(false);
      importingFile = null;
    });
  }

  function openBatchImport(jobs) {
    batchJobs = jobs.map(function (j) { return { id: j.id, name: j.name || j.file || 'Lecture' }; });
    var remembered = batchPresetStore.load();
    batchMode = remembered.mode; batchQuality = remembered.quality;
    var overlay = $('batch-overlay');
    if (!overlay) return;
    $('batch-count').textContent = batchJobs.length;
    var list = $('batch-list');
    list.innerHTML = batchJobs.map(function (j) {
      return '<div style="display:flex;align-items:center;gap:9px;font:500 12px \'Space Grotesk\';background:var(--sunk);border:1.5px solid var(--line);border-radius:8px;padding:7px 10px">' +
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>' +
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(j.name) + '</span></div>';
    }).join('');
    setBatchStyles();
    $('batch-msg').textContent = 'Each lecture keeps its own controls — change one before starting it.';
    overlay.hidden = false;
  }

  function closeBatchImport() {
    batchJobs = [];
    var overlay = $('batch-overlay');
    if (overlay) overlay.hidden = true;
  }

  function setBatchStyles() {
    var ACTIVE = 'flex:1;text-align:center;font:700 12px \'Space Grotesk\';padding:9px 0;border:2px solid var(--orange);border-radius:9px;background:var(--orange-soft);color:var(--orange-ink);box-shadow:var(--shadow-hard-sm);cursor:pointer';
    var INACTIVE = 'flex:1;text-align:center;font:500 12px \'Space Grotesk\';padding:9px 0;border:2px solid transparent;border-radius:9px;background:transparent;color:var(--muted);box-shadow:var(--shadow-hard-sm);cursor:pointer';
    Array.prototype.forEach.call(document.querySelectorAll('#batch-quality [data-bq]'), function (o) {
      o.style.cssText = o.dataset.bq === batchQuality ? ACTIVE : INACTIVE;
    });
    Array.prototype.forEach.call(document.querySelectorAll('#batch-output [data-bo]'), function (o) {
      o.style.cssText = o.dataset.bo === batchMode ? ACTIVE : INACTIVE;
    });
  }

  function batchApplyAll() {
    if (!batchJobs.length) return;
    batchPresetStore.save(batchMode, batchQuality);
    lpBridge.call('apply_job_settings', {
      job_ids: batchJobs.map(function (j) { return j.id; }),
      mode: batchMode,
      preset: batchQuality === 'high' ? 'detailed' : 'balanced'
    }).then(function (result) {
      var applied = (result && result.applied) || [];
      $('batch-msg').textContent = applied.length + ' lecture' + (applied.length === 1 ? '' : 's') + ' updated to ' +
        (batchMode === 'study' ? 'Study Pack' : batchMode === 'transcript' ? 'Transcript only' : 'Slides only') +
        (batchQuality === 'high' ? ' · High' : ' · Balanced') + '.';
      renderJobs();
    });
  }

  function batchQueueAll() {
    if (!batchJobs.length) return;
    var ids = batchJobs.map(function (j) { return j.id; });
    var settings = {
      job_ids: ids,
      mode: batchMode,
      preset: batchQuality === 'high' ? 'detailed' : 'balanced'
    };
    $('batch-msg').textContent = 'Applying settings and starting the queue…';
    lpBridge.call('apply_job_settings', settings).then(function () {
      return lpBridge.call('queue_jobs', { job_ids: ids });
    }).then(function (result) {
      var count = (result && result.count) || 0;
      closeBatchImport();
      if (count) toast(count + ' lecture' + (count === 1 ? '' : 's') + ' queued — processing started');
      renderJobs();
    }, function () {
      $('batch-msg').textContent = 'The batch could not be queued. Your imported lectures are still safe in the library.';
    });
  }

  // ---- Feature 2: persistent processing strip ----
  var processingEta = {};
  function recordProcessingEta(jobId, stage, pct) {
    pct = Number(pct);
    if (!jobId || !isFinite(pct) || pct <= 0 || pct >= 100) return;
    var now = Date.now();
    var state = processingEta[jobId];
    if (!state || pct < state.lastPct) state = processingEta[jobId] = { startedAt: now, lastPct: pct, seconds: 0 };
    var elapsed = (now - state.startedAt) / 1000;
    state.lastPct = Math.max(state.lastPct || 0, pct);
    state.stage = stage || state.stage || '';
    // The percentage remains the backend's authoritative overall progress.
    // ETA is only a smoothed projection from elapsed time and that percentage.
    if (state.lastPct < 8 || elapsed < 20) return;
    var estimate = elapsed * (100 - state.lastPct) / state.lastPct;
    if (!isFinite(estimate) || estimate < 20 || estimate > 12 * 3600) return;
    state.seconds = state.seconds ? (state.seconds * .75 + estimate * .25) : estimate;
  }
  function etaLabel(job) {
    var state = job && processingEta[job.id];
    if (!state || !state.seconds || state.lastPct < 8) return '';
    return '~' + Math.max(1, Math.round(state.seconds / 60)) + ' min left';
  }
  /* Formerly #proc-strip, a second full-width bar stacked above the footer
     showing the SAME job at a different width, with the same stage text the
     footer already had. It is now the footer's single job button: one bar,
     34px of chrome instead of 68px, and the stage name appears exactly once. */
  function renderProcessingStrip() {
    var job = $('status-job');
    if (!job) return;
    var running = LP.data.jobs.filter(function (j) { return j && j.status === 'running'; })[0];
    if (!running) {
      job.hidden = true;
      renderProcessWorkload();
      return;
    }
    job.hidden = false;
    var name = running.name || 'Processing';
    $('status-job-name').textContent = name;
    // Announce the ACTION, not the raw progress readout.
    job.setAttribute('aria-label', 'Open ' + name);
    var pct = running.pct || 0;
    setFill('status-bar', pct);
    var stage = running.stage || '';
    var parts = [friendlyProcessingLabel(stage || 'Processing')];
    if (pct > 0) parts.push(pct + '%');
    var eta = etaLabel(running);
    if (eta) parts.push(eta);
    $('status-detail').textContent = parts.join(' · ');
    var waiting = (LP.data.queue && LP.data.queue.queue) ? LP.data.queue.queue.length : 0;
    var queued = $('status-queued');
    queued.textContent = waiting > 0 ? ('+' + waiting + ' queued') : '';
    queued.hidden = waiting <= 0;
    var footer = $('status-footer');
    if (footer && footer.dataset.status !== 'waiting') footer.dataset.status = 'processing';
    $('status-state').textContent = 'Processing';
    renderProcessWorkload();
  }

  // ---- Feature 3: global transcript search ----
  var searchDebounce = null;
  function openGlobalSearch() {
    var overlay = $('search-overlay');
    if (!overlay) return;
    overlay.hidden = false;
    $('search-results').innerHTML = '<div style="padding:18px;text-align:center;font:500 12px \'JetBrains Mono\';color:var(--muted)">Type to search across your lectures’ transcripts.</div>';
    var input = $('search-input');
    input.value = '';
    setTimeout(function () { input.focus(); }, 30);
  }
  function closeGlobalSearch() {
    var overlay = $('search-overlay');
    if (overlay) overlay.hidden = true;
    if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; }
  }
  function runGlobalSearch(query) {
    var results = $('search-results');
    var q = (query || '').trim();
    if (!q) {
      results.innerHTML = '<div style="padding:18px;text-align:center;font:500 12px \'JetBrains Mono\';color:var(--muted)">Type to search across your lectures’ transcripts.</div>';
      return;
    }
    results.innerHTML = '<div style="padding:18px;text-align:center;font:500 12px \'JetBrains Mono\';color:var(--muted)">Searching…</div>';
    lpBridge.call('search_transcripts', { query: q, limit: 20 }).then(function (result) {
      var matches = (result && result.results) || [];
      if (!matches.length) {
        results.innerHTML = '<div style="padding:18px;text-align:center;font:500 12px \'Space Grotesk\';color:var(--muted)">No transcript matches for “' + esc(q) + '”</div>';
        return;
      }
      results.innerHTML = matches.map(function (m) {
        return '<button data-result data-job="' + esc(m.job_id) + '" data-ts="' + esc(m.timestamp) + '" style="display:block;width:100%;text-align:left;background:transparent;border:none;border-bottom:1.5px solid var(--line);padding:11px 14px;cursor:pointer;color:var(--ink)">' +
          '<div style="display:flex;align-items:baseline;gap:9px;margin-bottom:4px"><span style="font-weight:700;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(m.name) + '</span><span style="font:600 11px \'JetBrains Mono\';color:var(--blue-ink);flex:none">' + esc(m.timestamp) + '</span></div>' +
          '<div style="font:500 12px \'Space Grotesk\';color:var(--muted);line-height:1.5">“' + esc(m.snippet) + '”</div></button>';
      }).join('');
    });
  }
  function openSearchResult(jobId, timestamp) {
    closeGlobalSearch();
    // Explicit navigation: opens this lecture at this transcript segment. It
    // must override any restored per-job resume position.
    pendingTranscriptJump = { jobId: jobId, timestamp: timestamp };
    selectJob(jobId, { screen: 'transcript' });
  }
  var pendingTranscriptJump = null;

  function transcriptTimestampSeconds(value) {
    var parts = String(value || '').split(':').map(Number);
    if (parts.some(function (part) { return !isFinite(part); })) return 0;
    return parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] :
      parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0);
  }

  function transcriptScrollHost() {
    return document.querySelector('main [data-screen="transcript"]');
  }

  function applyPendingTranscriptJump() {
    if (!pendingTranscriptJump || pendingTranscriptJump.jobId !== LP.state.jobId) return;
    var wanted = pendingTranscriptJump.timestamp;
    var rows = document.querySelectorAll('#transcript-blocks [data-transcript-time]');
    var target = null, wantedSeconds = transcriptTimestampSeconds(wanted), nearest = null, nearestDistance = Infinity;
    Array.prototype.some.call(rows, function (row) {
      var value = row.dataset.transcriptTime || row.dataset.start || '';
      var distance = Math.abs(transcriptTimestampSeconds(value) - wantedSeconds);
      if (distance < nearestDistance) { nearestDistance = distance; nearest = row; }
      if (value === wanted) { target = row; return true; }
      return false;
    });
    if (!target) target = nearest;
    if (!target) return; // keep the request until transcript_changed supplies the block
    pendingTranscriptJump = null;
    setTimeout(function () {
      target.scrollIntoView({ block: 'center', inline: 'nearest' });
      target.style.background = 'var(--orange-soft)';
      target.style.boxShadow = '0 0 0 2px var(--orange)';
      setTimeout(function () {
        target.style.background = '';
        target.style.boxShadow = '';
      }, 1600);
    }, 80);
  }

  // ---- Feature 4: per-job resume state ----
  // Persistence goes through the shared browserStorage() helper so the app
  // keeps exactly one direct localStorage call site for the setup flag — the
  // invariant enforced by
  // test_no_third_browser_storage_call_site_is_added_for_the_setup_flag.
  var resumeStore = (function () {
    var key = 'lecturepack.resume.v1';
    function read() { try { return JSON.parse(browserStorage().getItem(key) || '{}'); } catch (_) { return {}; } }
    function write(data) { try { browserStorage().setItem(key, JSON.stringify(data)); } catch (_) {} }
    return {
      save: function (jobId, state) {
        if (!jobId) return;
        var all = read();
        all[jobId] = state;
        write(all);
      },
      load: function (jobId) {
        var all = read();
        return all[jobId] || null;
      },
      clear: function (jobId) {
        if (!jobId) return;
        var all = read();
        delete all[jobId];
        write(all);
      }
    };
  })();
  var appSessionStore = (function () {
    var key = 'lecturepack.session.v1';
    return {
      load: function () { try { return JSON.parse(browserStorage().getItem(key) || '{}'); } catch (_) { return {}; } },
      save: function (state) { try { browserStorage().setItem(key, JSON.stringify(state || {})); } catch (_) {} }
    };
  })();
  var appSessionRestored = false;
  var sessionNavigationExplicit = false;

  function saveAppSession() {
    // The provisional active_job replay arrives before jobs_changed. It must
    // not overwrite the user's saved viewed lecture before restore reads it.
    if (!appSessionRestored) return;
    if (!LP.state.jobId) return;
    appSessionStore.save({ jobId: LP.state.jobId, screen: LP.state.screen || 'home' });
  }

  function restoreAppSessionOnce() {
    if (appSessionRestored) return;
    appSessionRestored = true;
    if (sessionNavigationExplicit) { saveAppSession(); return; }
    var saved = appSessionStore.load();
    var job = saved.jobId && _jobById(saved.jobId);
    if (!job) { saveAppSession(); return; }
    // Mark the current processing id as already observed so the bootstrap
    // active_job replay cannot overwrite the explicitly restored selection.
    var running = (LP.data.jobs || []).filter(function (entry) { return entry && entry.status === 'running'; })[0];
    if (running) autoSelectedActiveId = running.id;
    var screen = /^(home|process|review|transcript|study|exports)$/.test(saved.screen) ? saved.screen : sensibleJobScreen(job);
    selectJob(job.id, { screen: screen, restoring: true });
  }

  function captureResumeState(jobId) {
    if (!jobId) return;
    var state = {
      screen: LP.state.screen || 'home',
      studyTab: LP.state.studyTab || 'chat'
    };
    var transcriptEl = transcriptScrollHost();
    if (transcriptEl) state.transcriptScroll = transcriptEl.scrollTop || 0;
    if (LP.data.slides && LP.data.slides.length) state.viewingSlide = LP.state.viewingSlide || 0;
    resumeStore.save(jobId, state);
    saveAppSession();
  }

  function applyResumeState(jobId) {
    if (!jobId) return;
    var state = resumeStore.load(jobId);
    if (!state) return;
    // Only restore the screen when it is a workspace screen and no explicit
    // navigation overrides it (search result / Process for active job).
    if (pendingTranscriptJump && pendingTranscriptJump.jobId === jobId) return;
    // ...and only when the student is NOT already working in a lecture screen.
    // Switching lecture from the header switcher passes no explicit screen, so
    // this used to drop them wherever the INCOMING lecture was last left: ask a
    // question in Study, change lecture, and you land in Review. Changing which
    // lecture you are looking at should not change what you are looking at.
    // Home and Settings are not workspace screens, so opening a lecture from
    // there still resumes where that lecture left off.
    var current = LP.state.screen;
    var alreadyInWorkspace = current && current !== 'home' && current !== 'settings';
    if (!alreadyInWorkspace
        && state.screen && state.screen !== 'home' && state.screen !== 'settings') {
      setScreen(state.screen);
    }
    if (state.studyTab) setStudyTab(state.studyTab);
    if (state.viewingSlide != null && LP.data.slides && LP.data.slides.length) {
      LP.state.viewingSlide = Math.min(state.viewingSlide, LP.data.slides.length - 1);
    }
    if (state.transcriptScroll != null) {
      var transcriptEl = transcriptScrollHost();
      if (transcriptEl) {
        setTimeout(function () { transcriptEl.scrollTop = state.transcriptScroll; }, 60);
      }
    }
  }

  // ---- Feature 4: one-click Continue on Home ----
  // A quiet Home surface that returns the student to their last meaningful
  // activity. Continue destinations are workspace screens only (Review,
  // Transcript, Study/Flashcards/Quiz, Process); transient surfaces such as
  // Settings, Downloads, or Export are never offered as a Continue target.
  var CONTINUE_SCREENS = {
    review: { label: 'Review', screen: 'review' },
    transcript: { label: 'Transcript', screen: 'transcript' },
    study: { label: 'Study', screen: 'study' },
    process: { label: 'Process', screen: 'process' },
    exports: { label: 'Review', screen: 'review' }
  };
  var CONTINUE_STUDY_TABS = {
    chat: { label: 'Ask', screen: 'study', tab: 'chat' },
    overview: { label: 'Overview', screen: 'study', tab: 'overview' },
    cards: { label: 'Flashcards', screen: 'study', tab: 'cards' },
    quiz: { label: 'Quiz', screen: 'study', tab: 'quiz' },
    quick: { label: 'Quick Study', screen: 'study', tab: 'quick' }
  };
  function continueScreenOf(state) {
    if (!state) return null;
    if (state.screen === 'study' && state.studyTab) {
      var tab = CONTINUE_STUDY_TABS[state.studyTab];
      if (tab) return tab;
    }
    return CONTINUE_SCREENS[state.screen] || null;
  }
  function renderContinueCard() {
    var card = $('continue-card');
    if (!card) return;
    var jobId = LP.state.jobId || (appSessionStore.load() || {}).jobId || '';
    var job = jobId && _jobById(jobId);
    if (!job) {
      card.hidden = true;
      return;
    }
    var state = resumeStore.load(jobId) || {};
    var target = continueScreenOf(state);
    if (!target) {
      card.hidden = true;
      return;
    }
    $('continue-title').textContent = job.name || 'Lecture';
    var detail = target.label;
    if (state.screen === 'study' && state.studyTab === 'quiz') {
      var qs = (studyV2.progress && studyV2.progress.quiz_attempts) || [];
      if (qs.length) detail = 'Quiz · ' + qs.length + ' questions';
    } else if (state.screen === 'study' && state.studyTab === 'cards') {
      var fc = (studyV2.progress && studyV2.progress.flashcard_results) || {};
      var fcCount = Object.keys(fc).length;
      if (fcCount) detail = 'Flashcards · ' + fcCount + ' studied';
    } else if (state.screen === 'transcript') {
      detail = 'Transcript';
    } else if (state.screen === 'review') {
      detail = 'Review';
    } else if (state.screen === 'process') {
      detail = 'Processing';
    }
    $('continue-detail').textContent = detail;
    card.hidden = false;
    $('btn-continue').onclick = function () {
      selectJob(jobId, { screen: target.screen });
      if (target.tab) setStudyTab(target.tab);
      setScreen(target.screen);
      saveAppSession();
    };
  }

  // ---- Feature 5: Ctrl+K command palette ----
  var paletteIndex = 0;
  var paletteCommands = [
    { label: 'Import video', run: function () { if (lpBridge.connected()) lpBridge.call('browse_video'); else setOnb('drop'); } },
    { label: 'Search all transcripts', run: function () { openGlobalSearch(); } },
    { label: 'Paste link', run: function () { linkImportDialog(); } },
    { label: 'Go to Home', run: function () { setScreen('home'); } },
    { label: 'Go to Process', run: function () { setScreen('process'); } },
    { label: 'Go to Review', run: function () { setScreen('review'); } },
    { label: 'Go to Transcript', run: function () { setScreen('transcript'); } },
    { label: 'Go to Study', run: function () { setScreen('study'); } },
    { label: 'Go to Exports', run: function () { setScreen('exports'); } },
    { label: 'Next lecture', run: function () { selectAdjacentJob(1); } },
    { label: 'Previous lecture', run: function () { selectAdjacentJob(-1); } },
    { label: 'Copy transcript', run: function () { if (LP.data.transcript && LP.data.transcript.blocks) copyText(formatTranscriptPlain(LP.data.transcript.blocks), 'Transcript copied'); } },
    { label: 'Export Study Pack', run: function () { if (lpBridge.connected()) lpBridge.call('export_all', JSON.stringify(['pdf', 'html', 'txt', 'srt', 'md'])); } },
    { label: 'Open Settings', run: function () { setScreen('settings'); } }
  ];

  function openPalette() {
    var overlay = $('palette-overlay');
    if (!overlay) return;
    overlay.hidden = false;
    paletteIndex = 0;
    $('palette-input').value = '';
    renderPalette('');
    setTimeout(function () { $('palette-input').focus(); }, 30);
  }
  function closePalette() {
    var overlay = $('palette-overlay');
    if (overlay) overlay.hidden = true;
  }
  function renderPalette(query) {
    var q = (query || '').toLowerCase().trim();
    var jobResults = [];
    if (q) {
      (LP.data.jobs || []).forEach(function (j) {
        if (j && j.name && j.name.toLowerCase().indexOf(q) >= 0 && jobResults.length < 8) {
          jobResults.push({
            label: 'Open: ' + j.name,
            run: (function (id, status) {
              return function () { selectJob(id, { screen: status === 'done' ? 'review' : 'process' }); };
            })(j.id, j.status)
          });
        }
      });
    }
    var commands = paletteCommands.filter(function (c) {
      return !q || c.label.toLowerCase().indexOf(q) >= 0;
    });
    var items = commands.concat(jobResults);
    var host = $('palette-results');
    if (!items.length) {
      host.innerHTML = '<div style="padding:16px;text-align:center;font:500 12px \'JetBrains Mono\';color:var(--muted)">No commands match “' + esc(q) + '”</div>';
      paletteIndex = 0;
      return;
    }
    paletteIndex = Math.max(0, Math.min(paletteIndex, items.length - 1));
    host.innerHTML = items.map(function (item, i) {
      return '<button data-palette-item data-index="' + i + '" style="display:block;width:100%;text-align:left;background:' + (i === paletteIndex ? 'var(--blue-tint)' : 'transparent') + ';border:1.5px solid ' + (i === paletteIndex ? 'var(--blue)' : 'transparent') + ';border-radius:8px;padding:9px 13px;cursor:pointer;color:var(--ink);font:500 13px \'Space Grotesk\'">' + esc(item.label) + '</button>';
    }).join('');
    host._items = items;
  }
  function activatePaletteItem(index, items) {
    var item = items[index];
    if (!item) return;
    closePalette();
    try { item.run(); } catch (e) { console.error('palette command', e); }
  }

  /* ======================= boot ======================= */

  /* ===================== guided demo (self-contained) =====================
     A screen, not an overlay. It measures nothing in the live UI, mutates
     nothing outside its own section, and shows PRE-BAKED REAL output of the
     bundled Polar Bears lecture (app/assets/demo/demo.json + slide PNGs).

     Why baked rather than processed live: the demo is the first impression and
     must work every time. Running the pipeline needs ffprobe and a Whisper
     model, takes tens of seconds, and can fail -- and when it fails it reads as
     the PRODUCT failing. The real pipeline now runs AFTER the walkthrough, from
     an explicit "Process this lecture for real" button, once the student knows
     what the stages mean. See docs/DECISIONS.md AD-48. */
  var DEMO_KEY = 'lecturepack.demo.v2';
  var DEMO_CHAPTERS = 5;
  var DEMO_NEXT = ['See what it found', 'And the words', 'Now study it', 'Take it with you', ''];
  var demoChapter = 1, demoData = null;

  function demoState() {
    try { return JSON.parse(browserStorage().getItem(DEMO_KEY)) || {}; } catch (e) { return {}; }
  }
  function demoSave(patch) {
    var next = demoState(), k;
    for (k in patch) if (Object.prototype.hasOwnProperty.call(patch, k)) next[k] = patch[k];
    try { browserStorage().setItem(DEMO_KEY, JSON.stringify(next)); } catch (e) {}
  }
  function demoCompleted() { return demoState().completed === true; }

  function demoFallback(host, message) {
    if (host) host.innerHTML = '<div class="lp-demo-fallback">' + esc(message) + '</div>';
  }

  function renderDemoChapter(n) {
    demoChapter = Math.max(1, Math.min(DEMO_CHAPTERS, n));
    var all = document.querySelectorAll('[data-screen="demo"] .lp-demo-ch'), i;
    for (i = 0; i < all.length; i++) {
      all[i].hidden = parseInt(all[i].getAttribute('data-ch'), 10) !== demoChapter;
    }
    $('btn-demo-back').hidden = demoChapter === 1;
    $('btn-demo-next').hidden = demoChapter === DEMO_CHAPTERS;
    $('btn-demo-next').textContent = DEMO_NEXT[demoChapter - 1];
    var dots = '', k;
    for (k = 1; k <= DEMO_CHAPTERS; k++) {
      dots += '<span data-on="' + (k <= demoChapter ? 'true' : 'false') + '"></span>';
    }
    $('demo-dots').innerHTML = dots;
    demoSave({ seen: true, chapter: demoChapter });
  }

  function paintDemo() {
    if (!demoData) {
      // Degraded, never blank: the copy is the payload and the artifact only
      // illustrates it, so every chapter still teaches and both CTAs still work.
      demoFallback($('demo-slides'), 'Slide previews unavailable - LecturePack still detects them from your lecture.');
      demoFallback($('demo-transcript'), 'Transcript preview unavailable.');
      demoFallback(document.querySelector('.lp-demo-study'), 'Study preview unavailable.');
      return;
    }
    var src = demoData.source || {};
    if (src.name) {
      $('demo-src-name').textContent = src.name + ' · ' + (src.duration || '');
      $('demo-hero-cap').textContent = src.name + ' · ' + (src.duration || '') +
        (src.resolution ? ' · ' + src.resolution : '');
    }
    $('demo-slides').innerHTML = (demoData.slides || []).map(function (s) {
      return '<figure class="lp-demo-slide">' +
        '<img src="../assets/demo/' + encodeURIComponent(s.img) + '" alt="' + esc(s.title || '') + '">' +
        '<figcaption><span>' + esc(s.t || '') + '</span>' +
        '<span class="lp-demo-flag">kept</span></figcaption></figure>';
    }).join('');
    $('demo-transcript').innerHTML = (demoData.lines || []).map(function (l) {
      return '<div class="lp-demo-line" data-active="' + (l.active ? 'true' : 'false') + '">' +
        '<time>' + esc(l.t || '') + '</time><span>' + esc(l.text || '') + '</span></div>';
    }).join('');
    var card = demoData.card || {}, quiz = demoData.quiz || {};
    $('demo-card-tag').textContent = 'Question';
    $('demo-card-face').textContent = card.q || '';
    $('demo-quiz-q').textContent = quiz.q || '';
    // The answer is NOT revealed up front -- a pre-highlighted correct option
    // spoils the question and makes the quiz look decorative rather than real.
    $('demo-quiz-opts').innerHTML = (quiz.options || []).map(function (o, i) {
      return '<li><button type="button" class="lp-demo-opt" data-i="' + i + '" aria-pressed="false">' +
        esc(o) + '</button></li>';
    }).join('');
    var quizFeedback = $('demo-quiz-feedback');
    if (quizFeedback) {
      quizFeedback.hidden = true;
      quizFeedback.textContent = '';
      quizFeedback.removeAttribute('data-state');
    }
  }

  function openDemo(startAt) {
    setScreen('demo');
    var hero = $('demo-hero');
    if (hero && !hero.getAttribute('src')) {
      hero.onerror = function () { hero.style.display = 'none'; };
      hero.setAttribute('src', '../assets/demo/hero.png');
    }
    // Data arrives as a plain global from ../assets/demo/demo.data.js. The
    // renderer runs over file://, where fetch() of a sibling file is blocked
    // by web security -- an earlier fetch() version silently degraded to the
    // fallback on EVERY launch, including the packaged app.
    if (!demoData) demoData = window.LP_DEMO_DATA || null;
    paintDemo();
    renderDemoChapter(startAt || 1);
  }

  function closeDemo(screen, status) {
    demoSave({ seen: true, completed: true, chapter: demoChapter });
    if (guidedTourEligibility) {
      guidedTourEligibility.eligible = false;
      guidedTourEligibility.completed = status !== 'skipped';
      guidedTourEligibility.skipped = status === 'skipped';
    }
    persistGuidedTourState(status || 'completed');
    renderDemoHomeAvailability();
    renderDemoCard();
    setScreen(screen || 'home');
  }

  /* The real pipeline runs, on purpose, only AFTER the walkthrough. */
  function runDemoForReal() {
    if (!demoAdmissionAvailable) { toast('The demo lecture will be available once setup finishes.'); return; }
    if (!lpBridge.connected()) { toast('Processing needs the LecturePack desktop app.'); return; }
    var current = guidedDemo.snapshot();
    if (current.status === 'starting' || current.active) { closeDemo('process'); return; }
    closeDemo('process');
    setOnb(null);
    // Terminal cleanup belongs to the prior attempt. Without resetting these
    // guards, a second demo run could start normally but endGuidedDemo() would
    // reject its stop request as though cleanup had already completed.
    demoCleanupRequested = false;
    demoCleanupConfirmed = false;
    var attempt = guidedDemo.starting().attempt;
    renderDemoCard();
    lpBridge.startDemoJob().then(function (value) {
      if (!guidedDemo.isCurrentAttempt(attempt)) return;
      var result = parseBridgeResult(value);
      guidedDemo.started(result, attempt);
      renderDemoCard();
      if (!result || result.ok !== true) toast((result && result.error) || 'Could not start the demo lecture.');
    }, function (error) {
      if (!guidedDemo.isCurrentAttempt(attempt)) return;
      var message = error && error.message ? error.message : 'Could not start the demo lecture.';
      guidedDemo.started({ ok: false, error: message }, attempt);
      renderDemoCard();
      toast(message);
    });
  }

  function bindDemoScreen() {
    $('btn-demo-next').addEventListener('click', function () { renderDemoChapter(demoChapter + 1); });
    $('btn-demo-back').addEventListener('click', function () { renderDemoChapter(demoChapter - 1); });
    $('btn-demo-skip').addEventListener('click', function () { closeDemo('home', 'skipped'); });
    $('btn-demo-own').addEventListener('click', function () { closeDemo('home', 'completed'); beginBrowseImport(); });
    $('btn-demo-run').addEventListener('click', runDemoForReal);
    $('demo-quiz-opts').addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.lp-demo-opt') : null;
      if (!btn || !demoData || !demoData.quiz) return;
      var chosen = parseInt(btn.getAttribute('data-i'), 10);
      var answer = demoData.quiz.answer;
      Array.prototype.forEach.call($('demo-quiz-opts').querySelectorAll('.lp-demo-opt'), function (b, i) {
        b.setAttribute('data-state', i === answer ? 'correct' : (i === chosen ? 'wrong' : 'idle'));
        b.setAttribute('aria-pressed', i === chosen ? 'true' : 'false');
        var outcome = i === answer ? ', correct answer' : (i === chosen ? ', incorrect' : '');
        b.setAttribute('aria-label', b.textContent.trim() + outcome);
      });
      var feedback = $('demo-quiz-feedback');
      if (feedback) {
        var correct = chosen === answer;
        feedback.hidden = false;
        feedback.setAttribute('data-state', correct ? 'correct' : 'wrong');
        feedback.textContent = correct ? 'Correct.' :
          'Not quite. Correct answer: ' + String(demoData.quiz.options[answer] || '');
      }
    });
    $('demo-card').addEventListener('click', function () {
      if (!demoData || !demoData.card) return;
      var showingQuestion = $('demo-card-tag').textContent === 'Question';
      $('demo-card-tag').textContent = showingQuestion ? 'Answer' : 'Question';
      $('demo-card-face').textContent = showingQuestion ? demoData.card.a : demoData.card.q;
    });
  }

  function boot() {
    // BUG-15: gating only `LP.data.jobs` behind ?preview=1 was not enough. The
    // pipeline/slides/reviewSegments/transcript/study literals are ALSO
    // design-time demo content (a 14-slide "Great Pyramid of Giza" lecture),
    // and Home was the only screen that got cleaned. Verified on a real launch
    // against an empty profile: Home correctly showed "No lecture loaded" and
    // RECENT JOBS 0, while Review showed a full fake lecture — timeline,
    // slide list with accepted/rejected states, and transcript.
    //
    // A brand-new user pressing Review would see a lecture that does not
    // exist. `active_job` cannot be relied on to clear it, because
    // _load_latest_completed_job() returns early without emitting when there
    // is nothing to load. So the workspace starts EMPTY unless explicitly
    // previewing, and real data only ever arrives from the backend.
    if (!PREVIEW) {
      var blank = emptyWorkspace();
      Object.keys(blank).forEach(function (k) { LP.data[k] = blank[k]; });
      LP.data.reviewSegments = [];
      LP.state.chat = [];   // N-9: no design-time Q&A without a lecture
    }
    // Last-resort safety net (N-1): no renderer exception may ever surface
    // raw to a student. Log technically; toast friendly.
    window.addEventListener('unhandledrejection', function (e) {
      try { console.error('[lecturepack] unhandled rejection:', e.reason); } catch (err) {}
      var msg = e.reason && e.reason.message ? e.reason.message : String(e.reason || '');
      if (msg) toast(friendlyErrorMessage(msg));
      e.preventDefault();
    });
    window.addEventListener('error', function (e) {
      try { console.error('[lecturepack] uncaught:', e.error || e.message); } catch (err) {}
    });
    resetJobChrome();           // clear index.html's design-time placeholders
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
    renderDemoCard();
    renderSlideDetectionPreset();
    setScreen('home');
    applyInitialTheme();
    setStudyTab('chat');
    RuntimeSetupGate.wire();
    RuntimeSetupGate.beginBootstrap();
    wire();
    wireDemoLifecycle();
    wireModelTooltip();
    wireBridge();
    wireSubjectEvents();
    bindStudyV2Events();
    bindStudyScopeControls();
    bindDemoScreen();
    renderStudyV2Overview();
    window.addEventListener('resize', function () { LP.motion.indicator(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
