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

  /* ======================= guided tour models =======================
     These reducers deliberately contain no DOM or bridge calls.  The DOM
     controller below is a thin projection of their state, which keeps the
     user-controlled tour and stale-event filtering testable without a live
     QtWebEngine window. */
  function GuidedTourModel(seen) {
    var active = false, prompt = false, step = -1, completed = !!seen;
    function snapshot() { return { active: active, prompt: prompt, step: step, completed: completed }; }
    return {
      offer: function () { if (!completed && !active) prompt = true; return snapshot(); },
      start: function () { prompt = false; active = true; step = 0; return snapshot(); },
      replay: function () { prompt = false; active = true; step = 0; return snapshot(); },
      next: function (count) { if (active && step < count - 1) step += 1; return snapshot(); },
      back: function () { if (active && step > 0) step -= 1; return snapshot(); },
      exit: function () { active = false; prompt = false; step = -1; completed = true; return snapshot(); },
      snapshot: snapshot
    };
  }

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

  function GuidedDemoFlowModel() {
    var phase = 'idle', imported = false, reviewDecisionMade = false;
    function snapshot() {
      return { phase: phase, imported: imported, reviewDecisionMade: reviewDecisionMade,
        nextEnabled: phase === 'study' || phase === 'exports',
        backEnabled: phase === 'study' || phase === 'exports' };
    }
    return {
      beginAttempt: function () { phase = 'import'; imported = false; reviewDecisionMade = false; return snapshot(); },
      start: function () { phase = 'import'; imported = false; reviewDecisionMade = false; return snapshot(); },
      imported: function () { if (phase === 'import') { imported = true; phase = 'processing'; } return snapshot(); },
      running: function () { if (phase === 'processing') phase = 'processing'; return snapshot(); },
      reviewReady: function () { if (phase === 'processing') phase = 'review'; return snapshot(); },
      reviewDecision: function () { if (phase === 'review') { reviewDecisionMade = true; phase = 'study'; } return snapshot(); },
      next: function () { if (phase === 'study') phase = 'exports'; else if (phase === 'exports') phase = 'finished'; return snapshot(); },
      back: function () { if (phase === 'exports') phase = 'study'; else if (phase === 'study') phase = 'review'; return snapshot(); },
      exit: function () { phase = 'idle'; imported = false; reviewDecisionMade = false; return snapshot(); },
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
  /* ===================== guided tour models end ===================== */
  window.LPTourModel = GuidedTourModel;
  window.LPDemoSessionModel = GuidedDemoSessionModel;
  window.LPDemoFlowModel = GuidedDemoFlowModel;
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
      slidesView: 'grid',   // grid = visual tiles, list = compact rows

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
      var liveLabel = $('status-label'); if (liveLabel) liveLabel.textContent = 'Idle';
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
  function formatTranscriptPlain(blocks) {
    return (blocks || []).map(function (b) {
      return transcriptBlockText(b).replace(/\s+/g, ' ').trim();
    }).filter(Boolean).join('\n\n');
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
    if (/review ready|preparing review/.test(normalized)) return 'Preparing review';
    if (/^prepare|preparing/.test(normalized)) return 'Preparing';
    return raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
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
    // F-2: never stack a modal over the guided tour.
    if (guidedTour.snapshot().active || guidedTour.snapshot().prompt) { toast('Finish or leave the guided tour first.'); return; }
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

  function _jobCardHtml(j) {
    var ready = _jobIsReady(j);
    var displayStatus = ready ? 'ready' : j.status;
    var b = JOB_BADGES[displayStatus] || JOB_BADGES.done;
    var dot = '<span style="width:6px;height:6px;border-radius:50%;background:' + b.dot + (b.blink ? ';animation:lpblink 1s infinite' : '') + '"></span>';
    var badge = '<span class="lp-state" data-state="' + (JOB_STATE_MAP[displayStatus] || 'idle') + '" style="position:absolute;top:9px;right:9px;display:flex;align-items:center;gap:5px;font:600 10px \'JetBrains Mono\';text-transform:uppercase;background:' + b.bg + ';color:' + b.fg + ';border-radius:6px;padding:3px 8px">' + dot + b.label + '</span>';
    var menu = j.id ? '<div style="position:absolute;top:9px;left:9px;display:flex;gap:6px">' +
      _jobBtn('group', j.id, TAG_SVG, 'Set group') + _jobBtn('delete', j.id, TRASH_SVG, 'Delete') + '</div>' : '';
    var body;
    if (j.status === 'running') {
      body = '<div data-job-title title="Double-click to rename" style="font-weight:700;font-size:16px;margin-bottom:9px">' + esc(j.name) + '</div>' +
        '<div style="height:8px;border-radius:5px;background:var(--sunk);overflow:hidden;margin-bottom:7px"><div data-progress style="width:' + (j.pct || 0) + '%;height:100%;background:var(--orange);background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.3) 6px,rgba(255,255,255,.3) 13px);animation:lpbar 1s linear infinite"></div></div>' +
        '<div data-progress-label style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + esc(friendlyProcessingLabel(j.stage)) + ' · ' + (j.pct || 0) + '% · ' + esc(j.eta || '') + '</div>';
    } else {
      body = '<div data-job-title title="Double-click to rename" style="font-weight:700;font-size:16px;margin-bottom:5px">' + esc(j.name) + '</div>' +
        '<div style="font:500 11px \'JetBrains Mono\';color:var(--muted);line-height:1.7">' + esc(j.file || '') + '<br>' + esc(j.meta || '') + '</div>';
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
    // In select mode the per-card menu is replaced by a checkbox, and the whole
    // card toggles selection instead of opening.
    var selecting = LP.state.selecting && j.id;
    var chosen = selecting && !!LP.state.selected[j.id];
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
    return '<div class="lp-card" ' + (j.id ? 'data-job="' + esc(j.id) + '" ' : '') + 'data-status="' + esc(displayStatus) + '" style="background:var(--panel);border:2px solid ' + border + ';border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;cursor:pointer">' +
      '<div style="height:118px;background:var(--sunk);border-bottom:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;position:relative">' + posterHtml(j) + (selecting ? selbox : menu) + badge + '</div>' +
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
    if (!el) return;
    el.textContent = text;
    el.style.color = isError ? 'var(--red)' : 'var(--muted)';
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

  function renderDownloads() {
    var items = mediaLink.downloads || [];
    var indicator = $('downloads-indicator'), panel = $('downloads-panel'), list = $('downloads-list');
    if (!indicator || !panel || !list) return;
    var active = items.filter(function (item) { return item.status === 'downloading'; })[0];
    var waiting = items.filter(function (item) { return item.status === 'waiting'; }).length;
    var unfinished = items.filter(function (item) { return item.status === 'downloading' || item.status === 'waiting'; }).length;
    indicator.hidden = items.length === 0;
    $('downloads-indicator-label').textContent = active
      ? ('Downloading ' + (active.title || 'lecture') + ' · ' + (active.pct || 0) + '%' + (waiting ? ' · ' + waiting + ' waiting' : ''))
      : (unfinished ? ('↓ ' + unfinished + ' downloads') : 'Downloads');
    if (!items.length) { panel.hidden = true; return; }
    list.innerHTML = items.map(function (item) {
      var status = item.status || 'waiting';
      var progress = status === 'downloading'
        ? '<div style="height:6px;border-radius:4px;background:var(--sunk);overflow:hidden;margin:7px 0 4px"><div class="lp-fill" style="width:100%;height:100%;background:var(--orange);transform:scaleX(' + Math.max(0, Math.min(1, (item.pct || 0) / 100)) + ')"></div></div>'
        : '';
      var meta = status === 'downloading'
        ? ((item.pct || 0) + '%' + (item.speed ? ' · ' + fmtBytes(item.speed) + '/s' : '') + (item.eta ? ' · ~' + fmtDuration(item.eta) + ' left' : ''))
        : status.charAt(0).toUpperCase() + status.slice(1);
      var action = status === 'downloading'
        ? '<button data-download-act="cancel" data-download-id="' + esc(item.id) + '">Cancel</button>'
        : status === 'waiting'
          ? '<button data-download-act="remove" data-download-id="' + esc(item.id) + '">Remove</button>'
          : status === 'failed' || status === 'cancelled'
            ? '<button data-download-act="retry" data-download-id="' + esc(item.id) + '">Retry</button>' : '';
      return '<div style="padding:10px;border-radius:9px;background:var(--panel2);margin-bottom:6px"><div style="display:flex;gap:9px;align-items:start"><div style="flex:1;min-width:0"><div style="font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(item.title || 'Lecture download') + '</div>' + progress + '<div style="font:500 10px \'JetBrains Mono\';color:' + (status === 'failed' ? 'var(--red)' : 'var(--muted)') + '">' + esc(meta) + '</div>' + (item.error ? '<details style="font-size:11px;color:var(--muted);margin-top:5px"><summary>Details</summary><div style="overflow-wrap:anywhere">' + esc(item.error) + '</div></details>' : '') + '</div><div class="lp-download-action">' + action + '</div></div></div>';
    }).join('');
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
  function setJobGroup(job) {
    // F-2: never stack the Group lecture modal over the guided tour.
    if (guidedTour.snapshot().active || guidedTour.snapshot().prompt) { toast('Finish or leave the guided tour first.'); return; }
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
  function _jobIsReady(j) {
    return !!j && j.status === 'queued' && !_jobInQueue(j.id) && j.status !== 'running';
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
    if (!el) return;
    var job = _jobById(LP.state.jobId);
    if (!job || !(job.preset || job.product_mode)) { el.textContent = ''; return; }
    el.textContent = _optionsLabel(job);
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
      studyV2.viewJobId = '';
      if (LP.state.screen === 'study') renderStudyV2Overview();
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
    list.innerHTML = q.map(function (row, i) {
      var job = _jobById(row.id) || { id: row.id, preset: 'balanced', product_mode: 'study_pack' };
      var qbtn = function (act, label, disabled) {
        return '<button class="lp-hit" data-queueact="' + act + '" data-queueid="' + esc(row.id) + '"' +
          (disabled ? ' disabled style="opacity:.4;' : ' style="') +
          'font:600 11px \'Space Grotesk\';border-radius:7px;padding:6px 10px;cursor:pointer;background:var(--panel);border:1.5px solid var(--border);color:var(--ink)">' + label + '</button>';
      };
      return '<div class="lp-anim-in" style="display:flex;align-items:center;gap:12px;background:var(--panel);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px">' +
        '<span style="font:700 12px \'JetBrains Mono\';color:var(--muted);min-width:22px">' + (i + 1) + '</span>' +
        '<div style="width:96px;height:54px;flex:none;background:var(--sunk);border:1.5px solid var(--line);border-radius:8px;position:relative;overflow:hidden">' + posterHtml(job) + '</div>' +
        '<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13.5px;margin-bottom:2px">' + esc(_jobName(row.id)) + '</div>' +
        '<div style="font:500 11px \'JetBrains Mono\';color:var(--muted)">' + esc(_optionsLabel(job)) + ' · Queued</div></div>' +
        '<div style="display:flex;gap:6px">' +
          qbtn('up', 'Move up', i === 0) +
          qbtn('down', 'Move down', i === q.length - 1) +
          qbtn('remove', 'Remove', false) +
        '</div></div>';
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
    g.style.display = 'flex'; g.style.flexDirection = 'column'; g.style.gap = '26px';
    g.style.gridTemplateColumns = 'none';
    var groups = {}, order = [];
    LP.data.jobs.forEach(function (j) {
      var k = jobGroup(j);
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
    // The guided-tour processing spotlight is measured before the live stage
    // list fills in. Re-measure after that DOM growth so the border and arrow
    // continue to describe the actual target instead of the initial skeleton.
    if (guidedTour.snapshot().active && demoFlowPhase() === 'processing') scheduleTourGeometry();
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
      if (guidedTour.snapshot().active && demoFlowPhase() === 'processing') scheduleTourGeometry();
      refreshControlStates();
   }

   function renderProcessingStatus() {
     var s = pendingProcessingStatus;
     var key = JSON.stringify(s);
     if (key === lastStatusRenderKey) return;
     lastStatusRenderKey = key;
      if (s.label !== undefined) $('status-label').textContent = friendlyProcessingLabel(s.label) || 'Idle';
      if (s.pct !== undefined) setFill('status-bar', s.pct);
      if (s.detail !== undefined) $('status-pct').textContent = friendlyProcessingLabel(s.detail) || s.detail;
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
     var label = $('status-label'), pct = $('status-pct'), right = $('status-right');
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

  /* Slide review has two genuinely different jobs, so it gets two layouts.
     GRID = image tiles, for scanning a deck fast and spotting the slide you
     want. LIST = compact rows with timecode + status, for working through
     judgements precisely. Before this the Grid/List control was inert markup
     (two <span>s, no handler anywhere) while the only layout that existed was
     the row one -- so it also mislabelled itself as "Grid". */
  /* Grid tiles animate their entrance ONLY when the user enters grid view, not
     on every render. renderSlides() rebuilds innerHTML on every slide click,
     Next/Prev, and now every Keep/Reject (which auto-advances), so an
     unconditional .lp-anim-in made the whole grid re-play its 140ms slide-up on
     every single interaction -- a full-grid flash per judgement click. The list
     branch never carried the class, which is why only grid regressed. */
  var _gridEntrance = true;   // true so the first paint still animates
  function renderSlides() {
    var v = LP.state.viewingSlide;
    var list = $('slide-list');
    updateExportPdfDescription();
    var grid = LP.state.slidesView === 'grid';
    // the container is a flex column for list, an auto-fill grid for tiles
    list.style.display = grid ? 'grid' : 'flex';
    list.style.gridTemplateColumns = grid ? 'repeat(auto-fill,minmax(104px,1fr))' : '';
    list.style.alignContent = grid ? 'start' : '';
    list.style.gap = grid ? '8px' : '9px';
    if (grid) {
      var entrance = _gridEntrance ? ' lp-anim-in' : '';
      _gridEntrance = false;
      list.innerHTML = LP.data.slides.map(function (s, i) {
        var viewing = i === v, bd, tint = 'var(--panel)', label, labelColor;
        if (viewing) { bd = 'var(--orange)'; tint = 'var(--orange-soft)'; label = s.sel ? 'viewing · sel' : 'viewing'; labelColor = 'var(--orange-ink)'; }
        else if (s.sel) { bd = 'var(--blue)'; tint = 'var(--blue-tint)'; label = 'selected'; labelColor = 'var(--blue-ink)'; }
        else if (s.state === 'rejected') { bd = 'var(--red)'; tint = 'var(--red-soft)'; label = 'rejected'; labelColor = 'var(--red)'; }
        else { bd = 'var(--border)'; label = 'accepted'; labelColor = 'var(--blue-ink)'; }
        var img = slideImg(s.thumb || s.img, 'width:100%;height:100%;object-fit:cover;display:block', 18, labelColor);
        return '<div class="lp-hit' + entrance + '" data-slide="' + i + '" style="display:flex;flex-direction:column;gap:5px;' +
          'background:' + tint + ';border:2px solid ' + bd + ';border-radius:10px;padding:5px;cursor:pointer">' +
          '<div style="aspect-ratio:16/10;overflow:hidden;background:var(--sunk);border-radius:6px;display:flex;' +
          'align-items:center;justify-content:center">' + img + '</div>' +
          '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:4px">' +
          '<span style="font:700 11px \'JetBrains Mono\'">' + esc(s.time) + '</span>' +
          '<span style="font:700 8.5px \'JetBrains Mono\';text-transform:uppercase;color:' + labelColor + '">' + label + '</span>' +
          '</div></div>';
      }).join('');
      finishSlides(v);
      return;
    }
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
    finishSlides(v);
  }

  function finishSlides(v) {
    var selCount = LP.data.slides.filter(function (s) { return s.sel; }).length;
    $('slides-sel').textContent = '· ' + selCount + ' sel';
    var cur = LP.data.slides[v];
    previewCtl.show(cur);
    $('slide-frame-meta').innerHTML = cur
      ? (esc(cur.time) + '.500 <span style="color:var(--muted);font-weight:400">· frame ' + (cur.frame || Math.round(cur.pct * 30)) + '</span>')
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

  var CRUMBS = { home: 'Home', process: 'Process', review: 'Review', transcript: 'Transcript', study: 'Study', exports: 'Exports', settings: 'Settings' };

  function setScreen(name) {
    if (LP.state.screen === name) return;
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
      if (name === 'process') renderSlideDetectionPreset();
      if (name === 'exports') updateExportPdfDescription();
      if (name === 'study') {
        studyV2Load();   // load grounded Study V2 content + progress
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
    });
    // N-5: transient toasts do not survive a screen change.
    dismissToast();
    // N-8: the tour follows the student, not the script. If they manually
    // reach the next expected screen, the tour advances to match; otherwise
    // re-measure so the spotlight never glows around empty space.
    if (guidedTour.snapshot().active) {
      var phaseNow = demoFlowPhase();
      if (phaseNow === 'review' && name === 'study') { guidedDemoFlow.reviewDecision(); renderGuidedTour(); }
      else if (phaseNow === 'study' && name === 'exports') { guidedDemoFlow.next(); renderGuidedTour(); }
      else scheduleTourGeometry();
    }
    if (typeof saveAppSession === 'function') saveAppSession();
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

  function setOnb(state) { // null | 'drop' | 'detected'
    LP.state.onb = state;
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
    ['runtime-setup-overlay', 'onb-overlay', 'whatsnew-overlay',
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
    function valid(value) {
      return !!(value && value.operation_id === activeOperation && value.app_version && value.source &&
        value.affected_components && Number.isSafeInteger(value.download_size_bytes) && value.download_size_bytes >= 0);
    }
    function snapshot() {
      return { state: state, returnState: returnState, retryPending: retryPending, cancelPending: cancelPending,
        activeOperation: activeOperation, terminal: terminal, offer: offer, bootstrapPending: bootstrapPending, healthy: healthy,
        validationPath: validationPath, acknowledged: acknowledged, checklist: checklist, checkProgress: checkProgress,
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
            state = 'checking';
            checkProgress = {};
            FIRST_RUN_ROWS.forEach(function (row) { checkProgress[row.id] = 'pending'; });
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
            // D-12: a first-ever healthy admission always shows the
            // checklist; an already-acknowledged admission leaves the state
            // exactly where the pre-01-07 reducer left it, so the
            // controller's existing close path still closes the overlay.
            state = 'checklist';
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
        if (healthy && !acknowledged) state = 'checklist';
        return snapshot();
      },
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
    // btn-runtime-continue and btn-runtime-skip are byte-identical in effect
    // (UI-SPEC "Continue vs Skip effect", owner-resolved) and share one
    // acknowledge() handler wired to both in wire().
    var CHECKLIST_WINDOWS_ADVISORY = "Your Windows version isn't fully tested with LecturePack. Everything checked above works, so you can continue — reliability on this exact version isn't guaranteed.";
    function renderChecklist() {
      var host = $('runtime-checklist-rows'), empty = $('runtime-checklist-empty');
      if (!host || !empty) return;
      // Read only id/verdict/detail -- no health arithmetic of our own on
      // component evidence (backend decides, UI renders).
      var items = eventModel.snapshot().checklist;
      var complete = Array.isArray(items) && items.length === FIRST_RUN_ROWS.length;
      empty.hidden = complete;
      if (!complete) {
        while (host.firstElementChild) host.firstElementChild.remove();
        return;
      }
      var rowIndex = 0;
      items.forEach(function (item) {
        var meta = null;
        for (var i = 0; i < FIRST_RUN_ROWS.length; i++) { if (FIRST_RUN_ROWS[i].id === item.id) { meta = FIRST_RUN_ROWS[i]; break; } }
        var label = meta ? meta.label : String(item.id);
        var dataState = FIRST_RUN_VERDICT_STATES[item.verdict] || null;
        var badgeText = item.verdict === 'needs_attention' ? 'Needs Attention' : 'Ready';
        updateFirstRunRow(host, rowIndex++, item.id, label, badgeText, dataState,
          item.verdict === 'needs_attention' ? CHECKLIST_WINDOWS_ADVISORY : '');
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
      var view = eventModel.snapshot(), next = view.state;
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
      // Per the UI-SPEC nav contract, checklist is the one state in this
      // overlay with no Exit affordance -- Continue and Skip already cover
      // the low-commitment path; every other state (including checking)
      // restores it. The focus helper already filters out zero-size
      // elements, so hiding Exit here removes it from the trap cleanly and
      // Continue/Skip remain the two focusable controls in checklist.
      if (stateChanged) {
        var exitButton = $('btn-runtime-exit');
        if (exitButton) exitButton.hidden = next === 'checklist';
      }
      // runtime-checking-heading and runtime-checklist-heading carry
      // tabindex="-1" for markup consistency with every other overlay
      // heading, but per the UI-SPEC Focal Point rule neither is this
      // state's initial focus target below -- checking focuses the Exit
      // control (nothing else competes for attention) and checklist
      // focuses Continue (the single focal action). runtime-checklist-body
      // is likewise never rewritten by JS: the Ready-only and Mixed
      // fixtures must render byte-identical heading/body copy, differing
      // only in one row's badge.
      var targets = { gate: 'btn-runtime-repair', confirm: 'btn-runtime-confirm', repairing: 'btn-runtime-cancel', offline: 'btn-runtime-offline-retry', failed: 'btn-runtime-failed-retry', diagnostics: 'runtime-diagnostics-heading', ready: 'runtime-ready-heading',
        checking: 'btn-runtime-exit', checklist: 'btn-runtime-continue', startup_failed: 'btn-startup-retry' };
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
        eventModel.toChecklist();
        announce('runtime-live-assertive', "You're ready to go.");
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
      if (bootstrap && Object.prototype.hasOwnProperty.call(bootstrap, 'tour_trace_enabled')) {
        setTourTraceEnabled(bootstrap.tour_trace_enabled === true);
      }
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
    // Continue and Skip are byte-identical in effect (UI-SPEC "Continue vs
    // Skip effect", owner-resolved) -- both call this one handler.
    function acknowledge() {
      var snap = eventModel.snapshot();
      if (snap.state !== 'checklist' || acknowledgeInFlight) return; // idempotent
      acknowledgeInFlight = true;
      var continueBtn = $('btn-runtime-continue'), skipBtn = $('btn-runtime-skip');
      if (continueBtn) continueBtn.disabled = true;
      if (skipBtn) skipBtn.disabled = true;
      lpBridge.call('acknowledge_setup').then(function (json) {
        var refreshed = null;
        // A bridge hiccup (json resolves empty/null) must not trap the user
        // behind a modal: the reducer's acknowledge() transition advances
        // the flag locally even when the payload is empty.
        if (json) { try { refreshed = JSON.parse(json); } catch (e) { refreshed = null; } }
        var view = eventModel.acknowledge(refreshed);
        syncDemoAdmission(view);
        closeOverlay();
        if (continueBtn) continueBtn.disabled = false;
        if (skipBtn) skipBtn.disabled = false;
        acknowledgeInFlight = false;
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
      $('btn-runtime-exit').addEventListener('click', function () { lpBridge.call('exit_application'); window.close(); });
      $('btn-runtime-continue').addEventListener('click', acknowledge);
      $('btn-runtime-skip').addEventListener('click', acknowledge);
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
    $('status-label').textContent = 'Idle';
    $('status-pct').textContent = '';
    setFill('status-bar', 0);
    renderSidePoster('');
    var w = $('storage-widget');
    if (w) w.hidden = true;
  }

  // ------------------------------------------------------------------ //
  // Study V2: grounded concepts, mastery, flashcards, quiz, quick study
  // ------------------------------------------------------------------ //
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
    viewJobId: '',
    restoredView: false,
    resumeMode: 'flashcards',
    restoredQuickActive: false
  };

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
        quickIndex: studyV2.quickIndex,
        quickCorrect: studyV2.quickCorrect,
        quickTotal: studyV2.quickTotal,
        quickMissed: studyV2.quickMissed,
        quickActive: !!studyV2.quickSession,
        quickSummary: studyV2.quickSummary,
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
      if (saved.lastMode === 'overview' || saved.lastMode === 'flashcards' || saved.lastMode === 'quiz' || saved.lastMode === 'ask') studyV2.mode = saved.lastMode;
      if (saved.resumeMode === 'flashcards' || saved.resumeMode === 'quiz' || saved.resumeMode === 'ask') studyV2.resumeMode = saved.resumeMode;
      else if (saved.lastMode === 'flashcards' || saved.lastMode === 'quiz' || saved.lastMode === 'ask') studyV2.resumeMode = saved.lastMode;
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
      studyV2.quickIndex = Math.max(0, Number(saved.quickIndex) || 0);
      studyV2.quickCorrect = Math.max(0, Number(saved.quickCorrect) || 0);
      studyV2.quickTotal = Math.max(0, Number(saved.quickTotal) || 0);
      studyV2.quickMissed = Array.isArray(saved.quickMissed) ? saved.quickMissed : [];
      studyV2.quickSummary = saved.quickSummary || null;
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
    if (!lpBridge.connected()) return;
    var requestedJobId = LP.state.jobId || '';
    if (!requestedJobId) return;
    lpBridge.call('study_v2_status', { job_id: requestedJobId }).then(function (res) {
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
      if (studyV2.quickSession == null && studyV2.progress.quick_study &&
          studyV2.progress.quick_study.items && studyV2.progress.quick_study.items.length &&
          (studyV2.quickIndex > 0 || studyV2.restoredQuickActive)) {
        studyV2.quickSession = studyV2.progress.quick_study;
      }
      studyV2.restoredQuickActive = false;
      renderStudyV2Overview();
      if (restoreMode && studyV2.mode !== 'overview') {
        setStudyV2Mode(studyV2.mode, !!studyV2.quickSession);
      } else if (studyV2.mode === 'flashcards' && studyV2.quickSession) renderQuickStudy();
      else if (studyV2.mode === 'flashcards') renderStudyFlashcards();
      else if (studyV2.mode === 'quiz') renderStudyQuiz();
    }).catch(function () {});
  }

  function conceptMastery(cid) {
    var p = (studyV2.progress && studyV2.progress.concepts) || {};
    return (p[cid] && p[cid].mastery) || 'NEW';
  }

  function renderStudyV2Overview() {
    var content = studyV2.content || { concepts: [], flashcards: [], quiz: [] };
    var summary = studyV2.summary || {};
    var studyJob = _jobById(LP.state.jobId) || LP.data.job || {};
    var title = studyJob.title ||
      (studyJob.name && studyJob.name !== 'Lecture' ? studyJob.name : '') ||
      studyJob.filename || studyJob.source_name || studyJob.file || 'Lecture';
    title = String(title).replace(/\.[^.]+$/, '');
    $('study-ready-title').textContent = title;
    $('study-ready-meta').textContent = content.concepts.length + ' concepts · ' + content.flashcards.length + ' cards · ' + content.quiz.length + ' questions';
    var pct = summary.progress_percent || 0;
    $('study-progress-pct').textContent = pct + '%';
    $('study-progress-bar').style.transform = 'scaleX(' + (pct / 100) + ')';
    var needsReview = summary.needs_review || 0;
    $('study-needs-review-line').textContent = needsReview + ' concepts left to review';

    // Key concepts
    var conceptsHtml = '';
    (content.concepts || []).forEach(function (c) {
      var mastery = conceptMastery(c.id);
      var masteryLabel = { NEW: 'New', LEARNING: 'Learning', MASTERED: 'Mastered', NEEDS_REVIEW: 'Needs review' }[mastery] || 'New';
      var sources = (c.sources || []).map(function (s) {
        var parts = [];
        if (s.segment_id != null) parts.push('<button class="lp-hit study-source study-source-time" data-segment="' + escText(s.segment_id) + '" data-ms="' + (s.start_ms || 0) + '" style="font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer">' + fmtTime(s.start_ms) + '</button>');
        if (s.slide_id != null) parts.push('<button class="lp-hit study-source study-source-slide" data-slide="' + escText(s.slide_id) + '" style="font:600 11px JetBrains Mono;background:var(--green-soft);color:var(--green);border:1.5px solid var(--green);border-radius:6px;padding:3px 8px;cursor:pointer">Slide ' + escText(studySlideLabel(s.slide_id)) + '</button>');
        return parts.join(' ');
      }).join('');
      var emphasisBadge = c.emphasis ? '<span style="font:600 9px JetBrains Mono;color:var(--orange-ink);background:var(--orange-soft);border:1.5px solid var(--orange);border-radius:5px;padding:2px 6px;text-transform:uppercase">Emphasized</span>' : '';
      conceptsHtml += '<div class="study-concept" style="background:var(--sunk);border:1.5px solid var(--line);border-radius:10px;padding:14px 16px">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-weight:700;font-size:14px;flex:1">' + escText(c.title) + '</span>' + emphasisBadge + '<span style="font:600 10px JetBrains Mono;color:var(--muted)">' + masteryLabel + '</span></div>' +
        '<div style="font-size:13px;color:var(--secondary-text);line-height:1.55;margin-bottom:8px">' + escText(c.explanation) + '</div>' +
        (sources ? '<div style="display:flex;gap:6px;flex-wrap:wrap">' + sources + '</div>' : '') +
        '<div style="display:flex;gap:6px;margin-top:8px"><button class="lp-hit study-explain" data-id="' + escText(c.id) + '" style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--ink)">Explain</button>' +
        '<button class="lp-hit study-edit" data-kind="concept" data-id="' + escText(c.id) + '" style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--muted)">Edit</button>' +
        '<button class="lp-hit study-delete" data-kind="concept" data-id="' + escText(c.id) + '" style="font:600 11px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer;color:var(--red)">Delete</button></div></div>';
    });
    $('study-concepts-list').innerHTML = conceptsHtml || '<div style="font:500 12px JetBrains Mono;color:var(--muted)">No concepts yet. Process a lecture to build Study content.</div>';

    // Needs review list
    var needsReviewHtml = '';
    (content.concepts || []).forEach(function (c) {
      if (conceptMastery(c.id) === 'NEEDS_REVIEW') {
        needsReviewHtml += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px"><span style="font-weight:600">' + escText(c.title) + '</span></div>';
      }
    });
    $('study-needs-review-list').innerHTML = needsReviewHtml || '<div style="font:500 12px JetBrains Mono;color:var(--muted)">Nothing to review — nice work.</div>';

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

  function studyV2FlashcardList() {
    var cards = (studyV2.content && studyV2.content.flashcards) || [];
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
    if (studyV2.quickSession) { renderQuickStudy(); return; }
    var cards = studyV2FlashcardList();
    var root = $('study-flashcards-root');
    if (!cards.length) {
      root.innerHTML = '<div class="study-empty-state" style="text-align:center;padding:56px 24px;color:var(--muted)">' +
        '<div style="font:700 18px Space Grotesk;color:var(--ink);margin-bottom:8px">Nothing needs another look</div>' +
        '<div style="font:500 13px JetBrains Mono;margin-bottom:18px">You have cleared the current weak areas.</div>' +
        (studyV2.reviewOnly ? '<button id="btn-study-review-all" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:8px;padding:9px 15px;cursor:pointer;color:var(--ink)">Study all cards</button>' : '') +
        '</div>';
      var all = $('btn-study-review-all');
      if (all) all.addEventListener('click', function () {
        studyV2.reviewOnly = false; studyV2.flashFilterIds = null; studyV2.flashIndex = 0;
        studyV2PersistView(); renderStudyFlashcards();
      });
      return;
    }
    var card = cards[studyV2.flashIndex];
    if (!card) {
      // Session complete
      root.innerHTML = '<div style="text-align:center;padding:40px">' +
        '<div style="font-weight:700;font-size:20px;margin-bottom:8px">Cards reviewed</div>' +
        '<div style="font:500 13px JetBrains Mono;color:var(--muted);margin-bottom:20px">' + cards.length + ' cards · ' + studyV2.flashResults.got + ' got it · ' + studyV2.flashResults.missed + ' need review</div>' +
        (studyV2.flashResults.missed ? '<button id="btn-study-review-missed" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 18px;cursor:pointer">Review the ' + studyV2.flashResults.missed + ' I missed</button>' : '') +
        '<button id="btn-study-flash-restart" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:2px solid var(--border);border-radius:9px;padding:10px 16px;cursor:pointer;color:var(--ink);margin-left:8px">Start over</button></div>';
      bindStudyFlashcardSessionButtons();
      return;
    }
    var sources = (card.sources || []).map(function (s) {
      var parts = [];
      if (s.segment_id != null) parts.push('<button class="lp-hit study-source" data-segment="' + escText(s.segment_id) + '" data-ms="' + (s.start_ms || 0) + '" style="font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer">' + fmtTime(s.start_ms) + '</button>');
      if (s.slide_id != null) parts.push('<button class="lp-hit study-source" data-slide="' + escText(s.slide_id) + '" style="font:600 11px JetBrains Mono;background:var(--green-soft);color:var(--green);border:1.5px solid var(--green);border-radius:6px;padding:3px 8px;cursor:pointer">Slide ' + escText(studySlideLabel(s.slide_id)) + '</button>');
      return parts.join(' ');
    }).join('');
    var progress = 'Card ' + (studyV2.flashIndex + 1) + ' of ' + cards.length;
    root.innerHTML = '<div class="study-focus-content" style="max-width:620px;margin:0 auto">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px JetBrains Mono;color:var(--muted);margin-bottom:12px"><span>' + progress + '</span><span>Space to reveal</span></div>' +
      '<div style="height:4px;border-radius:3px;background:var(--sunk);overflow:hidden;margin-bottom:22px"><div style="width:' + (((studyV2.flashIndex + 1) / cards.length) * 100) + '%;height:100%;background:var(--orange)"></div></div>' +
      '<div id="study-flash-card" class="lp-card study-focus-card" style="background:var(--panel);border:1.5px solid var(--border);border-radius:14px;box-shadow:var(--shadow-soft);padding:40px 34px;min-height:220px;display:flex;flex-direction:column;justify-content:center;text-align:center">' +
      '<div style="font-size:22px;font-weight:700;line-height:1.4;margin-bottom:18px">' + escText(card.front) + '</div>' +
      (studyV2.flashRevealed ? '<div style="border-top:1.5px solid var(--line);padding-top:18px;font-size:16px;color:var(--ink);line-height:1.55">' + escText(card.back) + '</div>' : '<button id="btn-study-flash-show" class="lp-hit lp-press" style="font:700 14px Space Grotesk;background:var(--orange);color:var(--on-signal);border:1.5px solid var(--orange-ink);border-radius:9px;padding:11px 20px;cursor:pointer;margin:0 auto">Show answer</button>') +
      '</div>' +
      (sources ? '<div style="display:flex;justify-content:center;gap:6px;margin-top:14px">' + sources + '</div>' : '') +
      (studyV2.flashRevealed ?
        '<div style="display:flex;justify-content:center;gap:10px;margin-top:20px">' +
        '<button id="btn-study-flash-again" class="lp-hit" style="font:600 13px Space Grotesk;background:var(--panel);border:1.5px solid var(--border);border-radius:9px;padding:10px 18px;cursor:pointer;color:var(--ink)">Review again</button>' +
        '<button id="btn-study-flash-got" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--green-fill);color:var(--on-signal);border:1.5px solid var(--green);border-radius:9px;padding:10px 18px;cursor:pointer">Got it</button></div>' : '') +
      '</div>';
    bindStudyFlashcardButtons();
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

  function quickStudySources(sources) {
    return (sources || []).map(function (s) {
      var parts = [];
      if (s.segment_id != null) parts.push('<button class="lp-hit study-source" data-segment="' + escText(s.segment_id) + '" data-ms="' + (s.start_ms || 0) + '" style="font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer">' + fmtTime(s.start_ms) + '</button>');
      if (s.slide_id != null) parts.push('<button class="lp-hit study-source" data-slide="' + escText(s.slide_id) + '" style="font:600 11px JetBrains Mono;background:var(--green-soft);color:var(--green);border:1.5px solid var(--green);border-radius:6px;padding:3px 8px;cursor:pointer">Slide ' + escText(studySlideLabel(s.slide_id)) + '</button>');
      return parts.join(' ');
    }).join('');
  }

  function renderQuickStudy() {
    var root = $('study-flashcards-root');
    var session = studyV2.quickSession;
    if (!root || !session) return;
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
    var sources = quickStudySources(data.sources);
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

  function renderStudyQuiz() {
    var questions = (studyV2.content && studyV2.content.quiz) || [];
    var root = $('study-quiz-root');
    if (!questions.length) {
      root.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted);font:500 13px JetBrains Mono">No quiz questions yet.</div>';
      return;
    }
    var q = questions[studyV2.quizIndex];
    if (!q) {
      // Quiz complete
      root.innerHTML = '<div style="text-align:center;padding:40px">' +
        '<div style="font-weight:700;font-size:20px;margin-bottom:8px">Quiz complete</div>' +
        '<div style="font:500 13px JetBrains Mono;color:var(--muted);margin-bottom:20px">' + studyV2.quizCorrect + ' / ' + questions.length + ' correct</div>' +
        '<button id="btn-study-quiz-restart" class="lp-hit lp-press" style="font:700 13px Space Grotesk;background:var(--orange);color:var(--on-signal);border:2px solid var(--orange-ink);border-radius:9px;padding:10px 18px;cursor:pointer">Take again</button></div>';
      var restart = $('btn-study-quiz-restart');
      if (restart) restart.addEventListener('click', function () {
        studyV2.quizIndex = 0; studyV2.quizCorrect = 0; studyV2.quizAnswers = []; studyV2.quizPicks = {};
        studyV2PersistView();
        renderStudyQuiz();
      });
      return;
    }
    var savedPick = Object.prototype.hasOwnProperty.call(studyV2.quizPicks, studyV2.quizIndex) ? Number(studyV2.quizPicks[studyV2.quizIndex]) : null;
    var answered = savedPick !== null && !Number.isNaN(savedPick);
    var optionsHtml = (q.options || []).map(function (opt, i) {
      var color = answered ? (i === q.correct_index ? 'var(--green)' : i === savedPick ? 'var(--red)' : 'var(--border)') : 'var(--border)';
      return '<button class="lp-hit study-quiz-opt" data-opt="' + i + '" style="display:block;width:100%;text-align:left;font:600 14px Space Grotesk;background:var(--sunk);border:1.5px solid ' + color + ';border-radius:9px;padding:11px 14px;cursor:pointer;color:var(--ink);margin-bottom:8px"' + (answered ? ' disabled' : '') + '>' + escText(opt) + '</button>';
    }).join('');
    root.innerHTML = '<div class="study-focus-content" style="max-width:680px;margin:0 auto">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;font:500 11px JetBrains Mono;color:var(--muted);margin-bottom:12px"><span>Question ' + (studyV2.quizIndex + 1) + ' of ' + questions.length + '</span><span>Choose one</span></div>' +
      '<div style="height:4px;border-radius:3px;background:var(--sunk);overflow:hidden;margin-bottom:24px"><div style="width:' + (((studyV2.quizIndex + 1) / questions.length) * 100) + '%;height:100%;background:var(--orange)"></div></div>' +
      '<div style="font-size:18px;font-weight:700;line-height:1.4;margin-bottom:18px;text-align:center">' + escText(q.question) + '</div>' +
      optionsHtml +
      '<div id="study-quiz-feedback" style="margin-top:14px"></div></div>';
    bindStudyQuizButtons();
    if (answered) renderStudyQuizFeedback(q, savedPick);
  }

  function renderStudyQuizFeedback(q, selectedIndex) {
    var correct = (q.correct_index === selectedIndex);
    var srcHtml = (q.sources || []).map(function (s) {
      var parts = [];
      if (s.segment_id != null) parts.push('<button class="lp-hit study-source" data-segment="' + escText(s.segment_id) + '" data-ms="' + (s.start_ms || 0) + '" style="font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer">' + fmtTime(s.start_ms) + '</button>');
      if (s.slide_id != null) parts.push('<button class="lp-hit study-source" data-slide="' + escText(s.slide_id) + '" style="font:600 11px JetBrains Mono;background:var(--green-soft);color:var(--green);border:1.5px solid var(--green);border-radius:6px;padding:3px 8px;cursor:pointer">Slide ' + escText(studySlideLabel(s.slide_id)) + '</button>');
      return parts.join(' ');
    }).join('');
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

  function bindStudyQuizButtons() {
    var opts = document.querySelectorAll('.study-quiz-opt');
    opts.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = Number(btn.dataset.opt);
        var questions = (studyV2.content && studyV2.content.quiz) || [];
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
        var srcHtml = (q.sources || []).map(function (s) {
          var parts = [];
          if (s.segment_id != null) parts.push('<button class="lp-hit study-source" data-segment="' + escText(s.segment_id) + '" data-ms="' + (s.start_ms || 0) + '" style="font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer">' + fmtTime(s.start_ms) + '</button>');
          if (s.slide_id != null) parts.push('<button class="lp-hit study-source" data-slide="' + escText(s.slide_id) + '" style="font:600 11px JetBrains Mono;background:var(--green-soft);color:var(--green);border:1.5px solid var(--green);border-radius:6px;padding:3px 8px;cursor:pointer">Slide ' + escText(studySlideLabel(s.slide_id)) + '</button>');
          return parts.join(' ');
        }).join('');
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

  function appendStudyAskSources(sources) {
    if (!studyV2.askAnswer || !Array.isArray(sources) || !sources.length) return;
    var feed = $('study-ask-feed');
    var answers = feed && feed.querySelectorAll('.study-ask-answer');
    var answer = answers && answers.length ? answers[answers.length - 1] : null;
    if (!answer) return;
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin-top:9px';
    sources.forEach(function (source) {
      var button = document.createElement('button');
      button.className = 'lp-hit study-source';
      button.dataset.segment = source.segment_id == null ? '' : source.segment_id;
      button.dataset.ms = source.start_ms || 0;
      button.textContent = source.start_ms != null ? 'Transcript ' + fmtTime(source.start_ms) : 'Transcript source';
      button.style.cssText = 'font:600 11px JetBrains Mono;background:var(--blue-soft);color:var(--blue-ink);border:1.5px solid var(--blue);border-radius:6px;padding:3px 8px;cursor:pointer';
      wrap.appendChild(button);
    });
    answer.parentNode.appendChild(wrap);
  }

  function setStudyV2Mode(mode, keepQuick) {
    if (mode === 'flashcards' && !keepQuick && studyV2.quickSession) {
      studyV2.quickSession = null;
      studyV2.quickSummary = null;
      studyV2.quickIndex = 0;
      studyV2.quickCorrect = 0;
      studyV2.quickTotal = 0;
      studyV2.quickMissed = [];
    }
    studyV2.mode = mode;
    if (mode !== 'overview') studyV2.resumeMode = mode;
    studyV2PersistView();
    document.querySelectorAll('.study-mode-tab').forEach(function (btn) {
      var active = btn.dataset.studyMode === mode;
      btn.className = 'lp-hit lp-tab study-mode-tab' + (active ? ' active' : '');
    });
    ['overview', 'flashcards', 'quiz', 'ask'].forEach(function (m) {
      $('study-mode-' + m).hidden = mode !== m;
    });
    if (mode === 'flashcards') renderStudyFlashcards();
    if (mode === 'quiz') renderStudyQuiz();
    if (mode === 'ask') renderStudyAsk();
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
      if (!lpBridge.connected()) return;
      var requestedJobId = LP.state.jobId || '';
      lpBridge.call('study_v2_quick_study', { job_id: requestedJobId }).then(function (res) {
        if (LP.state.jobId !== requestedJobId || (res && res.job_id && res.job_id !== requestedJobId)) return;
        if (res && res.session) {
          studyV2.quickSession = res.session;
          studyV2.quickIndex = 0; studyV2.quickCorrect = 0; studyV2.quickTotal = 0;
          studyV2.quickMissed = []; studyV2.quickRevealed = false;
          studyV2.quickAnswered = false; studyV2.quickSelected = null; studyV2.quickSummary = null;
          setStudyV2Mode('flashcards', true);
        }
      }).catch(function () {});
    });
    var cont = $('btn-study-continue');
    if (cont) cont.addEventListener('click', function () {
      if (studyV2.quickSession && studyV2.quickIndex < (studyV2.quickSession.items || []).length) {
        setStudyV2Mode('flashcards', true); return;
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
    var send = $('btn-study-ask-send');
    if (send) send.addEventListener('click', studyAskSend);
    var askInput = $('study-ask-input');
    if (askInput) askInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); studyAskSend(); }
    });
    // Source navigation + edit/delete/explain (delegated)
    var concepts = $('study-concepts-list');
    if (concepts) concepts.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) { navigateStudySource(t); return; }
      var edit = e.target.closest('.study-edit');
      if (edit) { studyV2EditItem(edit.dataset.kind, edit.dataset.id); return; }
      var del = e.target.closest('.study-delete');
      if (del) { studyV2DeleteItem(del.dataset.kind, del.dataset.id); return; }
      var explain = e.target.closest('.study-explain');
      if (explain) { studyV2ExplainItem(explain.dataset.id); }
    });
    var flashRoot = $('study-flashcards-root');
    if (flashRoot) flashRoot.addEventListener('click', function (e) {
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
    if (flashRoot) {
      flashRoot.tabIndex = 0;
      flashRoot.addEventListener('keydown', function (e) {
        if (e.code !== 'Space' || studyV2.mode !== 'flashcards') return;
        var action = flashRoot.querySelector('[data-quick-action="reveal"], #btn-study-flash-show');
        if (action) { e.preventDefault(); action.click(); }
      });
    }
    var quizRoot = $('study-quiz-root');
    if (quizRoot) quizRoot.addEventListener('click', function (e) {
      var t = e.target.closest('.study-source');
      if (t) navigateStudySource(t);
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
  }

  function studyV2EditItem(kind, id) {
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
          var payload = { job_id: LP.state.jobId, kind: kind, id: id };
          if (kind === 'concept') payload.title = value;
          else if (kind === 'flashcard') payload.front = value;
          else if (kind === 'quiz') payload.question = value;
          lpBridge.call('study_v2_edit', payload).then(function () { studyV2Load(); }).catch(function () {});
        } }
      ]
    });
    setTimeout(function () { var i = $('lp-study-edit-input'); if (i) { i.focus(); i.select(); } }, 30);
  }

  function studyV2DeleteItem(kind, id) {
    if (!id || !lpBridge.connected()) return;
    var noun = kind === 'concept' ? 'concept' : kind === 'flashcard' ? 'flashcard' : 'question';
    lpModal({
      title: 'Delete this ' + noun + '?',
      bodyHtml: 'This removes it from the Study pack. Related cards and questions are removed too.',
      actions: [
        { label: 'Cancel' },
        { label: 'Delete', danger: true, onClick: function () {
          lpBridge.call('study_v2_delete', { job_id: LP.state.jobId, kind: kind, id: id }).then(function () { studyV2Load(); }).catch(function () {});
        } }
      ]
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
    var segment = el.dataset.segment;
    var ms = Number(el.dataset.ms || 0);
    var slide = el.dataset.slide;
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
            raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : Number(parts[0] || 0);
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

  /* ======================= guided tour / demo ======================= */
  var TOUR_STORAGE_KEY = 'lecturepack.guided-tour.seen.v1';
  var browserStorage = function () { return window.localStorage; };
  var DEMO_DRAG_MIME = 'application/x-lecturepack-demo';
  var TOUR_PHASES = {
    import: { screen: 'home', target: '#dropzone', title: 'Add the demo video', copy: 'Drag the Polar Bears demo into this lecture area, or click the tile to use it.', next: 'Add demo to continue' },
    processing: { screen: 'process', target: '#pipeline-stages', title: 'Watch real processing', copy: 'This is the live local pipeline. It advances only as each step actually completes.', next: 'Processing safely…' },
    review: { screen: 'review', target: '#demo-review-actions', title: 'Make one review choice', copy: 'Use Keep or Reject on the existing review controls to continue.', next: 'Make a review choice' },
    study: { screen: 'study', target: '#demo-study-actions', title: 'Ask about the lecture', copy: 'The study workspace is ready. Try the chat box, then continue when you are ready.', next: 'Next' },
    exports: { screen: 'exports', target: '#btn-export-all', title: 'See export options', copy: 'Exporting unlocks for your own processed lecture. This temporary demo only shows where those options live.', next: 'Finish' }
  };
  function tourSeen() {
    try { return browserStorage().getItem(TOUR_STORAGE_KEY) === '1'; } catch (e) { return false; }
  }
  function markTourSeen() {
    try { browserStorage().setItem(TOUR_STORAGE_KEY, '1'); } catch (e) {}
  }
  var tourTraceEnabled = false;
  var tourTraceQueue = [], tourTraceFlushTimer = null, tourTraceFrame = null;
  var tourTraceObserver = null;

  function flushTourTrace() {
    tourTraceFlushTimer = null;
    if (!tourTraceQueue.length || !lpBridge.connected()) return;
    var batch = tourTraceQueue.splice(0, tourTraceQueue.length);
    lpBridge.call('log_tour_trace', JSON.stringify(batch));
  }

  function traceTour(kind, detail) {
    if (!tourTraceEnabled) return;
    var flow = guidedDemoFlow.snapshot();
    var record = {
      event: kind,
      at: performance.now(),
      guidedTour: guidedTour.snapshot(),
      demoPhase: flow.phase,
      demoAdmissionAvailable: demoAdmissionAvailable
    };
    if (detail) record.detail = detail;
    tourTraceQueue.push(record);
    if (tourTraceFlushTimer === null) tourTraceFlushTimer = setTimeout(flushTourTrace, 100);
  }

  function traceTourFrame(timestamp) {
    tourTraceFrame = null;
    if (!tourTraceEnabled) return;
    traceTour('requestAnimationFrame', { timestamp: timestamp });
    tourTraceFrame = requestAnimationFrame(traceTourFrame);
  }

  function installTourTraceObserver() {
    var overlay = $('guided-tour-overlay');
    if (!tourTraceEnabled || !overlay || tourTraceObserver) return;
    tourTraceObserver = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        traceTour('mutation', {
          type: mutation.type,
          attributeName: mutation.attributeName,
          oldValue: mutation.oldValue,
          addedNodes: mutation.addedNodes.length,
          removedNodes: mutation.removedNodes.length
        });
      });
    });
    tourTraceObserver.observe(overlay, {
      attributes: true,
      childList: true,
      attributeOldValue: true
    });
  }

  function setTourTraceEnabled(enabled) {
    var next = enabled === true;
    if (next === tourTraceEnabled) {
      if (next) installTourTraceObserver();
      return;
    }
    tourTraceEnabled = next;
    if (!next) {
      if (tourTraceObserver) tourTraceObserver.disconnect();
      tourTraceObserver = null;
      if (tourTraceFrame !== null) cancelAnimationFrame(tourTraceFrame);
      tourTraceFrame = null;
      if (tourTraceFlushTimer !== null) clearTimeout(tourTraceFlushTimer);
      tourTraceFlushTimer = null;
      tourTraceQueue = [];
      return;
    }
    installTourTraceObserver();
    tourTraceFrame = requestAnimationFrame(traceTourFrame);
  }

  function setTourOverlayHidden(next) {
    var overlay = $('guided-tour-overlay');
    if (!overlay) return;
    var previous = overlay.hidden;
    overlay.hidden = !!next;
    traceTour('overlay.hidden', { previous: previous, next: overlay.hidden });
  }

  var guidedTour = GuidedTourModel(tourSeen());
  var guidedDemo = GuidedDemoSessionModel();
  var guidedDemoFlow = GuidedDemoFlowModel();
  var slideDetectionPreset = SlideDetectionPresetModel();
  var demoAdmissionAvailable = false;
  var demoHomeDismissed = tourSeen();
  var tourRuntimeHealthy = false;

  function setDemoAdmissionAvailable(available) {
    var next = available === true, wasAvailable = demoAdmissionAvailable;
    demoAdmissionAvailable = next;
    tourRuntimeHealthy = next;
    var onboarding = $('settings-onboarding'), replay = $('btn-replay-tour');
    renderDemoHomeAvailability();
    if (onboarding) onboarding.hidden = !next;
    if (replay) replay.disabled = !next;
    if (!next) {
      // A repair/reset may arrive while a tour is open. Hide every entry point
      // immediately; a late bridge callback cannot re-open it without a new
      // healthy admission from RuntimeSetupGate.
      guidedTour.exit(); guidedDemoFlow.exit(); renderGuidedTour();
      setDemoTourInteraction(false);
      renderSlideDetectionPreset();
      if (guidedDemo.snapshot().active) endGuidedDemo('runtime_unavailable');
      renderDemoCard();
      return;
    }
    renderDemoCard();
    if (!wasAvailable) offerGuidedTour();
  }
  function renderDemoHomeAvailability() {
    var demoHome = $('home-demo');
    var firstRun = !!(LP.data && LP.data.jobs && LP.data.jobs.length === 0);
    // The empty workspace is the first-run entry point, even when a prior
    // tour dismissal is still present in the browser profile.  A zero-job
    // launch must always expose the demo alongside the import guidance.
    if (demoHome) demoHome.hidden = !firstRun &&
      ((!demoAdmissionAvailable) || (demoHomeDismissed && !guidedTour.snapshot().active));
  }

  function stageLabel(name) {
    var labels = { prepare: 'Preparing demo', inspect: 'Inspecting video', extract_audio: 'Extracting audio', transcribe: 'Transcribing audio', detect_slides: 'Detecting slides', align: 'Aligning notes', review_ready: 'Preparing review', export: 'Building Study Pack', complete: 'Complete' };
    return labels[name] || friendlyProcessingLabel(name) || 'Preparing demo';
  }
  function guidedDemoSensitivityLocked() {
    return guidedTour.snapshot().active && demoFlowPhase() !== 'idle';
  }
  // D-08: the sensitivity preset must also be locked during NORMAL (non-demo)
  // processing, not just the guided demo -- otherwise a user can click a
  // different preset while a job runs, see it render "active", but the
  // already-running job silently ignores it because its preset was
  // snapshotted at start_processing() time. LP.state.pipelineRunning is the
  // sibling flag for that case (set/cleared via the pipeline_changed and
  // status_changed handlers). Output mode has no Process-screen control at
  // all (onboarding sets LP.state.onbMode once; start_processing reads it
  // once), so it is already non-editable mid-run by omission -- no code
  // change needed for that half of D-08.
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
      button.title = demoLocked ? 'Guided demo uses its fixed reliable setting.' :
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
    var firstRunUnavailable = !demoAdmissionAvailable && LP.state.jobsEmpty;
    card.disabled = firstRunUnavailable || d.status === 'starting' || d.status === 'cancelling';
    card.setAttribute('aria-disabled', card.disabled ? 'true' : 'false');
    card.title = firstRunUnavailable ? 'Complete runtime setup before starting the guided demo.' : '';
    card.dataset.demoState = d.status === 'failed' || d.status === 'error' ? 'error' : (d.active ? 'running' : 'idle');
    if (firstRunUnavailable) {
      status.textContent = 'Guided demo will be available after runtime setup is ready.';
      action.textContent = 'Runtime setup required';
      return;
    }
    if (d.status === 'error' || d.status === 'failed') {
      status.textContent = d.error || 'The guided demo could not start.'; action.textContent = 'Try again'; return;
    }
    if (d.active) {
      status.textContent = stageLabel(d.stage) + ' · ' + Math.round(d.progress) + '%';
      action.textContent = d.status === 'starting' ? 'Starting…' : d.status === 'cancelling' ? 'Stopping…' : 'End demo'; return;
    }
    // §6: the demo's outputs stay fully explorable after it ends, so the card
    // must not claim its files were removed while they are still open.
    if (d.status === 'ended') { status.textContent = 'Demo complete — its slides, transcript, and study pack stay available to explore.'; action.textContent = 'Run demo again'; return; }
    status.textContent = 'Move this demo video into the lecture drop area, or click to use it.';
    action.textContent = 'Use demo video';
    refreshControlStates();
  }
  function demoFlowPhase() { return guidedDemoFlow.snapshot().phase; }
  function currentTourPhase() { return TOUR_PHASES[demoFlowPhase()] || null; }
  var liftedDemoCardPlaceholder = null, liftedDemoCardStyle = null;
  function positionLiftedDemoCard() {
    var card = $('glowing-demo-card');
    if (!card || !liftedDemoCardPlaceholder) return;
    var r = liftedDemoCardPlaceholder.getBoundingClientRect();
    card.style.left = Math.round(r.left) + 'px';
    card.style.top = Math.round(r.top) + 'px';
    card.style.width = Math.round(r.width) + 'px';
    card.style.height = Math.round(r.height) + 'px';
  }
  function liftDemoCardAboveTourScrim() {
    var card = $('glowing-demo-card'), overlay = $('guided-tour-overlay');
    if (!card || !overlay) return;
    if (!liftedDemoCardPlaceholder) {
      var r = card.getBoundingClientRect(), placeholder = document.createElement('div');
      placeholder.id = 'guided-demo-card-placeholder';
      placeholder.setAttribute('aria-hidden', 'true');
      placeholder.style.cssText = 'display:block;width:' + Math.round(r.width) + 'px;height:' + Math.round(r.height) + 'px';
      liftedDemoCardStyle = card.getAttribute('style');
      card.parentNode.insertBefore(placeholder, card);
      liftedDemoCardPlaceholder = placeholder;
      overlay.appendChild(card);
      card.classList.add('lp-demo-tour-lifted');
    }
    positionLiftedDemoCard();
  }
  function restoreDemoCardBelowTourScrim() {
    var card = $('glowing-demo-card');
    if (!card || !liftedDemoCardPlaceholder) return;
    liftedDemoCardPlaceholder.parentNode.insertBefore(card, liftedDemoCardPlaceholder);
    liftedDemoCardPlaceholder.remove(); liftedDemoCardPlaceholder = null;
    card.classList.remove('lp-demo-tour-lifted');
    if (liftedDemoCardStyle === null) card.removeAttribute('style');
    else card.setAttribute('style', liftedDemoCardStyle);
    liftedDemoCardStyle = null;
  }
  function setDemoTourInteraction(active) {
    var card = $('glowing-demo-card'), dropzone = $('dropzone');
    if (active) liftDemoCardAboveTourScrim(); else restoreDemoCardBelowTourScrim();
    if (card) card.classList.toggle('lp-demo-tour-active', !!active);
    if (dropzone) dropzone.classList.toggle('lp-demo-tour-active', !!active);
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
  function tourFocusable() {
    var card = $('guided-tour-card'), tourTarget = currentTourTarget(), items = card ? visibleFocusable(card) : [];
    if (tourTarget && tourTarget.matches('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')) items.unshift(tourTarget);
    else if (tourTarget) items = items.concat(visibleFocusable(tourTarget));
    return items.filter(function (item, index) { return items.indexOf(item) === index && ((!card || card.contains(item)) || (tourTarget && tourTarget.contains(item))); });
  }
  function trapTourFocus(e) {
    var items = tourFocusable();
    if (!items.length) { e.preventDefault(); return; }
    var first = items[0], last = items[items.length - 1], active = document.activeElement;
    if (items.indexOf(active) === -1) { e.preventDefault(); first.focus(); return; }
    if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  }
  var tourGeometryFrame = null;
  function currentTourTarget() {
    var phase = currentTourPhase();
    return phase && document.querySelector(phase.target);
  }
  function scheduleTourGeometry() {
    if (tourGeometryFrame !== null) return;
    tourGeometryFrame = requestAnimationFrame(function () {
      tourGeometryFrame = null;
      positionTourSpotlight();
    });
  }
  function positionTourSpotlight() {
    var state = guidedTour.snapshot(), box = $('tour-spotlight-box'), arrow = $('tour-arrow');
    if (!state.active || !box || !arrow) return;
    var target = currentTourTarget();
    // N-8: never leave a glow around empty space. A target that is unmounted,
    // inside a hidden screen, or absent after navigation collapses the
    // spotlight instead of drawing the fallback box at the viewport corner.
    if (!target || !target.isConnected || target.closest('[hidden]') || demoFlowPhase() === 'finished') {
      box.style.width = '0px'; box.style.height = '0px'; arrow.hidden = true; return;
    }
    var before = target.getBoundingClientRect();
    if (before.width === 0 && before.height === 0) {
      // Mounted but currently unmeasurable (its screen is still painting):
      // hide rather than point at (0,0), and re-check shortly.
      box.style.width = '0px'; box.style.height = '0px'; arrow.hidden = true;
      setTimeout(function () { scheduleTourGeometry(); }, 200);
      return;
    }
    if (before.top < 0 || before.left < 0 || before.bottom > window.innerHeight || before.right > window.innerWidth) {
      target.scrollIntoView({block: 'nearest', inline: 'nearest'});
    }
    var r = target.getBoundingClientRect(), pad = 7;
    // PC polish: keep the guided-demo glow visible after navigating to a new
    // screen. Some targets (e.g. #pipeline-stages before the first pipeline
    // event) legitimately have zero height; collapsing the box to 0x0 made the
    // overlay disappear for the rest of the demo. Use a fallback minimum box
    // so the active step stays emphasised, and re-measure on the next frame.
    var minW = 120, minH = 40;
    var effW = Math.max(minW, r.width), effH = Math.max(minH, r.height);
    var left = Math.max(6, Math.min(Math.round(r.left - pad), window.innerWidth - Math.round(effW + pad * 2) - 6));
    var top = Math.max(6, Math.min(Math.round(r.top - pad), window.innerHeight - Math.round(effH + pad * 2) - 6));
    var width = Math.max(0, Math.min(Math.round(effW + pad * 2), window.innerWidth - left - 6));
    var height = Math.max(0, Math.min(Math.round(effH + pad * 2), window.innerHeight - top - 6));
    box.style.left = left + 'px';
    box.style.top = top + 'px';
    box.style.width = width + 'px';
    box.style.height = height + 'px';
    arrow.hidden = false;
    arrow.style.left = Math.round(r.left + Math.min(Math.max(r.width, minW) - 18, 24)) + 'px';
    arrow.style.top = Math.max(8, Math.round(r.top - 19)) + 'px';
    var self = this;
    if (r.width === 0 || r.height === 0) {
      setTimeout(function () { scheduleTourGeometry(); }, 200);
    }
    positionLiftedDemoCard();
  }
  function renderGuidedTour() {
    var state = guidedTour.snapshot(), overlay = $('guided-tour-overlay');
    if (!overlay) return;
    installTourTraceObserver();
    setTourOverlayHidden(!demoAdmissionAvailable || (!state.active && !state.prompt));
    if (overlay.hidden) { setDemoTourInteraction(false); return; }
    var isPrompt = state.prompt, flow = guidedDemoFlow.snapshot();
    // §6: the tour ends on a celebration, not an anticlimax. The exports
    // step's Finish advances to a completion card with two real destinations.
    var finished = state.active && flow.phase === 'finished';
    var phase = state.active && !finished ? currentTourPhase() : null;
    $('tour-step-label').textContent = isPrompt ? 'WELCOME' : finished ? 'DEMO · COMPLETE' : 'DEMO · ' + flow.phase.toUpperCase();
    $('tour-title').textContent = isPrompt ? 'A quick look around' : finished ? 'Your first study pack is ready' : phase.title;
    $('tour-copy').textContent = isPrompt ? 'Want a short, user-controlled tour of the main parts of LecturePack?' :
      finished ? 'The demo lecture produced real slides, a transcript, and a study pack — all of it stays available to explore.' : phase.copy;
    $('tour-prompt-actions').hidden = !isPrompt;
    $('tour-step-actions').hidden = !state.active || finished;
    $('tour-finish-actions').hidden = !finished;
    if (!finished) {
      $('btn-tour-back').disabled = !state.active || !flow.backEnabled;
      $('btn-tour-next').disabled = !state.active || !flow.nextEnabled;
      $('btn-tour-next').textContent = state.active ? phase.next : 'Next';
    }
    $('tour-progress').innerHTML = isPrompt ? '' : Object.keys(TOUR_PHASES).map(function (name) { return '<span class="' + ((finished || name === flow.phase) ? 'active' : '') + '"></span>'; }).join('');
    $('tour-spotlight-box').style.display = state.active && !finished ? 'block' : 'none';
    $('tour-arrow').style.display = state.active && !finished ? 'block' : 'none';
    setDemoTourInteraction(state.active && flow.phase === 'import');
    // Geometry stays scheduled whenever the tour is active (PC polish contract);
    // positionTourSpotlight itself collapses the glow during the finished phase.
    if (state.active) scheduleTourGeometry();
  }
  function offerGuidedTour() {
    if (!demoAdmissionAvailable || !tourRuntimeHealthy) return;
    closeAllModals();           // the tour never shares the screen with a modal (F-2)
    guidedTour.offer(); renderGuidedTour();
  }
  function startGuidedTour(replay) {
    if (!demoAdmissionAvailable) return;
    closeAllModals();           // the tour never shares the screen with a modal (F-2)
    if (replay) guidedTour.replay(); else guidedTour.start();
    guidedDemoFlow.start();
    renderDemoHomeAvailability();
    var phase = currentTourPhase();
    if (phase) setScreen(phase.screen);
    renderGuidedTour();
  }
  function exitGuidedTour() {
    guidedTour.exit(); guidedDemoFlow.exit(); markTourSeen(); demoHomeDismissed = true;
    renderDemoHomeAvailability(); renderGuidedTour();
    renderSlideDetectionPreset();
    setScreen('home');
    endGuidedDemo('tour_exit');
  }
  function moveGuidedTour(direction) {
    var before = guidedTour.snapshot();
    if (!before.active) return;
    var flow = guidedDemoFlow.snapshot();
    if (direction > 0 && !flow.nextEnabled) return;
    // Finish on the exports step advances to the completion card (§6) instead
    // of dropping the student back at Home with no next move.
    if (direction > 0 && flow.phase === 'exports') { guidedDemoFlow.next(); renderGuidedTour(); return; }
    if (direction > 0) guidedDemoFlow.next(); else guidedDemoFlow.back();
    var phase = currentTourPhase();
    if (phase) setScreen(phase.screen);
    renderGuidedTour();
  }
  // The completion card's two destinations. Both end the tour like a normal
  // exit (seen-marked, demo settled) and then land somewhere useful.
  function finishGuidedTour(destination) {
    guidedTour.exit(); guidedDemoFlow.exit(); markTourSeen(); demoHomeDismissed = true;
    renderDemoHomeAvailability(); renderGuidedTour();
    renderSlideDetectionPreset();
    endGuidedDemo('tour_complete');
    if (destination === 'pack') setScreen('exports');
    else if (destination === 'import') {
      setScreen('home');
      if (lpBridge.connected()) lpBridge.call('browse_video');
    }
  }
  function parseBridgeResult(value) {
    if (typeof value === 'string') { try { return JSON.parse(value); } catch (e) { return null; } }
    return value && typeof value === 'object' ? value : null;
  }

  function applyAppVersion(value) {
    var version = String(value == null ? '' : value).trim();
    // Settings payloads from older sidecars may carry their neutral
    // 0.0.0 placeholder. Never let that overwrite Electron's packaged
    // metadata version supplied through preload.
    if (!version || version === '0.0.0') return;
    LP.data.version = version;
    var target = $('app-version');
    if (target) target.textContent = version;
  }

  function loadAppVersion() {
    var electron = window.lecturePackElectron;
    if (!electron || typeof electron.getAppVersion !== 'function') return;
    try {
      Promise.resolve(electron.getAppVersion()).then(applyAppVersion, function () {
        // Keep the neutral placeholder; never display a fabricated version.
      });
    } catch (e) { /* browser preview or an older preload */ }
  }

  function startGuidedDemo() {
    var current = guidedDemo.snapshot();
    if (current.status === 'starting' || current.status === 'cancelling') return;
    if (current.active) { endGuidedDemo('user_cancelled'); return; }
    if (!demoAdmissionAvailable) return;
    if (!lpBridge.connected()) { toast('Guided demo needs the LecturePack desktop app.'); return; }
    if (!guidedTour.snapshot().active) startGuidedTour(true);
    // A retry after clean-up (or a failed start) is a new demo, not a
    // continuation of whatever action-led screen the prior run last reached.
    // Do not reset the current run: active attempts returned above.
    if (demoFlowPhase() !== 'import') guidedDemoFlow.beginAttempt();
    guidedDemoFlow.imported(); guidedDemoFlow.running();
    // PC polish: once the demo job is queued/running, the initial new-job
    // setup card must not remain visible over the active processing screen.
    setOnb(null);
    setScreen('process'); renderGuidedTour();
    var startedAttempt = guidedDemo.starting().attempt;
    renderDemoCard();
    lpBridge.startDemoJob().then(function (value) {
      if (!guidedDemo.isCurrentAttempt(startedAttempt)) return;
      var result = parseBridgeResult(value);
      var state = guidedDemo.started(result, startedAttempt);
      renderDemoCard();
      // A start completion can arrive after an idempotent end acknowledgement.
      // Only navigate when it still represents the currently active identity.
      if (result && result.ok && state.active && !state.terminal &&
          state.operationId === result.operation_id && state.sessionId === result.session_id) setScreen('process');
      else if (result && result.error) toast(result.error);
      else if (!result || result.ok !== true) toast(state.error || 'Could not start the guided demo.');
    }, function (error) {
      if (!guidedDemo.isCurrentAttempt(startedAttempt)) return;
      var message = error && error.message ? error.message : 'Could not start the guided demo.';
      var state = guidedDemo.started({ ok: false, error: message }, startedAttempt);
      renderDemoCard();
      toast(state.error || message);
    });
  }
  function endGuidedDemo(reason) {
    var current = guidedDemo.snapshot();
    if (!current.active) return;
    var endingAttempt = current.attempt, endingOperationId = current.operationId, endingSessionId = current.sessionId;
    guidedDemo.cancelling(); renderDemoCard();
    if (!lpBridge.connected()) {
      guidedDemo.settleEndResult({ ok: false, error: 'Guided demo needs the LecturePack desktop app to stop safely.' }, endingAttempt, endingOperationId, endingSessionId);
      renderDemoCard(); return;
    }
    lpBridge.endDemoJob(reason || 'ended').then(function (value) {
      if (!guidedDemo.isCurrentAttempt(endingAttempt, endingOperationId, endingSessionId)) return;
      guidedDemo.settleEndResult(parseBridgeResult(value), endingAttempt, endingOperationId, endingSessionId);
      renderDemoCard();
    }, function () {
      if (!guidedDemo.isCurrentAttempt(endingAttempt, endingOperationId, endingSessionId)) return;
      guidedDemo.settleEndResult({ ok: false, error: 'Could not confirm that the demo stopped. Try again.' }, endingAttempt, endingOperationId, endingSessionId);
      renderDemoCard();
    });
  }
  function receiveDemoEvent(value) {
    var event = parseBridgeResult(value);
    if (!event) return;
    // A start signal can legitimately arrive before the slot return reaches JS.
    // Adopt only that first live identity; every later mismatched/stale event is
    // rejected by the model, so another demo cannot repaint this card.
    var before = guidedDemo.snapshot();
    if (!before.operationId && before.status === 'starting' && event.status === 'started') guidedDemo.started({ ok: true, operation_id: event.operation_id, session_id: event.session_id }, before.attempt);
    var handled = guidedDemo.event(event);
    if (!handled.accepted) return;
    var eventStage = String(event.stage || '').toLowerCase().replace(/[\s-]+/g, '_');
    if (eventStage === 'review_ready') {
      // A late or duplicate review-ready signal must not yank the student back
      // once they already made their review choice: the tour follows the
      // student, not the event stream. Only the processing -> review
      // transition auto-navigates.
      var awaitingReview = demoFlowPhase() === 'processing';
      guidedDemoFlow.reviewReady();
      if (awaitingReview && guidedTour.snapshot().active) { setScreen('review'); renderGuidedTour(); }
    } else if ((event.status === 'started' || event.status === 'running') && demoFlowPhase() === 'import') {
      guidedDemoFlow.imported(); guidedDemoFlow.running();
    }
    renderDemoCard();
    if (event.status === 'failed') toast(event.error || 'Guided demo failed.');
  }
  function isTourFormInput(target) {
    if (!target || !target.matches) return false;
    return target.matches('input, textarea, select, [contenteditable="true"]');
  }
  function wireGuidedTour() {
    $('btn-tour-start').addEventListener('click', function () { startGuidedTour(false); });
    $('btn-tour-skip').addEventListener('click', exitGuidedTour);
    $('btn-tour-next').addEventListener('click', function () { moveGuidedTour(1); });
    $('btn-tour-back').addEventListener('click', function () { moveGuidedTour(-1); });
    $('btn-tour-exit').addEventListener('click', exitGuidedTour);
    $('btn-tour-open-pack').addEventListener('click', function () { finishGuidedTour('pack'); });
    $('btn-tour-import-own').addEventListener('click', function () { finishGuidedTour('import'); });
    $('btn-replay-tour').addEventListener('click', function () { startGuidedTour(true); });
    var demoCard = $('glowing-demo-card');
    demoCard.addEventListener('click', function () {
      if (demoCard.disabled) return;
      if (guidedDemo.snapshot().active) { startGuidedDemo(); return; }
      flyDemoTileToDropzone(startGuidedDemo);
    });
    demoCard.addEventListener('dragstart', function (e) {
      if (demoCard.disabled) { e.preventDefault(); return; }
      // PC polish: only the video thumbnail is draggable. The card's title,
      // metadata, status, and buttons must stay stationary.
      if (!e.target || e.target.tagName !== 'IMG') { e.preventDefault(); return; }
      if (!e.dataTransfer) return;
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData(DEMO_DRAG_MIME, 'polar-bears-10s');
      e.dataTransfer.setData('text/plain', 'Polar Bears 10s Demo.mp4');
    });
    demoCard.addEventListener('dragend', clearDemoDropState);
    function markReviewDecision() {
      if (!guidedTour.snapshot().active || demoFlowPhase() !== 'review') return;
      guidedDemoFlow.reviewDecision();
      setScreen('study');
      renderGuidedTour();
    }
    // These listeners run after the existing review handlers, so this tour gate
    // is advanced by the user's actual Keep/Reject action, never a timer.
    $('btn-keep').addEventListener('click', markReviewDecision);
    $('btn-reject').addEventListener('click', markReviewDecision);
    document.addEventListener('keydown', function (e) {
      if (!guidedTour.snapshot().active || isTourFormInput(e.target)) return;
      if (e.key === 'ArrowRight') { e.preventDefault(); moveGuidedTour(1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); moveGuidedTour(-1); }
    });
    window.addEventListener('resize', scheduleTourGeometry);
    window.addEventListener('scroll', scheduleTourGeometry, true);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', scheduleTourGeometry);
      window.visualViewport.addEventListener('scroll', scheduleTourGeometry);
    }
  }
  function flyDemoTileToDropzone(done) {
    var card = $('glowing-demo-card'), target = $('dropzone');
    if (!card || !target) { done(); return; }
    if (LP.motion && LP.motion.reduced && LP.motion.reduced()) { done(); return; }
    var from = card.getBoundingClientRect(), to = target.getBoundingClientRect();
    card.style.setProperty('--demo-fly-x', Math.round(to.left - from.left) + 'px');
    card.style.setProperty('--demo-fly-y', Math.round(to.top - from.top) + 'px');
    function finish() {
      card.removeEventListener('animationend', finish);
      card.classList.remove('lp-demo-fly');
      card.style.removeProperty('--demo-fly-x'); card.style.removeProperty('--demo-fly-y');
      done();
    }
    card.addEventListener('animationend', finish);
    card.classList.add('lp-demo-fly');
  }
  function hasDemoDrag(e) {
    var types = e.dataTransfer && e.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, DEMO_DRAG_MIME) !== -1;
  }
  function clearDemoDropState() { var dz = $('dropzone'); if (dz) dz.classList.remove('lp-demo-drop-hover'); }
  function useDroppedDemo() {
    if (!demoAdmissionAvailable) return;
    if (!guidedTour.snapshot().active) startGuidedTour(true);
    if (demoFlowPhase() === 'idle') guidedDemoFlow.start();
    guidedDemoFlow.imported(); renderGuidedTour(); startGuidedDemo();
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
    dz.addEventListener('dragover', function (e) {
      e.preventDefault();
      if (hasDemoDrag(e)) { dz.classList.add('lp-demo-drop-hover'); return; }
      if (LP.state.onb !== 'detected') setOnb('drop');
    });
    dz.addEventListener('dragleave', function (e) {
      if (hasDemoDrag(e)) clearDemoDropState();
    });
    dz.addEventListener('drop', function (e) {
      e.preventDefault();
      if (hasDemoDrag(e)) { clearDemoDropState(); useDroppedDemo(); return; }
      importDroppedFiles(e.dataTransfer && e.dataTransfer.files);
    });
    // Electron owns the document-level drop path too. Ignore the dropzone here
    // because its handler already imported the first file and the event bubbles.
    window.addEventListener('dragover', function (e) {
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
      e.preventDefault();
      setOnb(null);
      if (e.target && e.target.closest && e.target.closest('#dropzone')) return;
      importDroppedFiles(e.dataTransfer && e.dataTransfer.files);
    });

    $('btn-show-empty').addEventListener('click', function () { setJobsEmpty(true); });
    // "Try the demo lecture" (N-3): the empty-state recovery action runs the
    // existing guided demo -- a real bundled lecture through the real
    // pipeline, with the tour attached -- instead of a dead sample-library
    // button that seeded nothing.
    $('btn-load-jobs').addEventListener('click', function () {
      if (!demoAdmissionAvailable) { toast('The demo will be available once setup finishes.'); return; }
      if (guidedDemo.snapshot().active) { startGuidedDemo(); return; }
      flyDemoTileToDropzone(startGuidedDemo);
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
      if (qa === 'runnow') lpBridge.call('run_now', qid);
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
    // Grid / List view toggle. Was inert markup with no handler at all.
    Array.prototype.forEach.call(document.querySelectorAll('[data-view]'), function (b) {
      b.addEventListener('click', function () {
        if (LP.state.slidesView === b.dataset.view) return;
        LP.state.slidesView = b.dataset.view;
        if (LP.state.slidesView === 'grid') _gridEntrance = true;
        Array.prototype.forEach.call(document.querySelectorAll('[data-view]'), function (o) {
          o.classList.toggle('active', o.dataset.view === LP.state.slidesView);
        });
        renderSlides();
      });
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
      s.state = 'accepted';
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
    $('btn-export-again').addEventListener('click', function () { LP.state.exportPhase = 'idle'; renderExportPhase(); });
    $('btn-open-folder').addEventListener('click', function () { lpBridge.call('open_export_folder'); });
    $('btn-export-pdf').addEventListener('click', function () {
      if (!LP.state.jobId) { toast('Load a lecture first — there is nothing to export yet.'); return; }
      lpBridge.call('export_one', 'pdf');
    });
    $('btn-export-html').addEventListener('click', function () {
      if (!LP.state.jobId) { toast('Load a lecture first — there is nothing to export yet.'); return; }
      lpBridge.call('export_one', 'html');
    });

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
        o.addEventListener('click', function () { batchQuality = o.dataset.bq; setBatchStyles(); });
      });
      Array.prototype.forEach.call(document.querySelectorAll('#batch-output [data-bo]'), function (o) {
        o.addEventListener('click', function () { batchMode = o.dataset.bo; setBatchStyles(); });
      });
    }

    // Processing strip: click selects the active job and opens Process.
    var procStrip = $('proc-strip');
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
        // N-7: the guided tour dismisses on Esc exactly like the modals. An
        // open lpModal owns Esc first (it closes itself), so the tour only
        // exits when no modal is on top.
        if (!anyModalOpen()) {
          var tourSnap = guidedTour.snapshot();
          if (tourSnap.active) exitGuidedTour();
          else if (tourSnap.prompt) { guidedTour.exit(); markTourSeen(); demoHomeDismissed = true; renderGuidedTour(); renderDemoHomeAvailability(); }
        }
        return;
      }
      var overlay = topOverlay();
      if (overlay) {
        if (e.key === 'Tab') trapFocus(overlay, e);
        if (e.key === 'Tab' && guidedTour.snapshot().active) trapTourFocus(e);
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
      var map = { 1: 'home', 2: 'process', 3: 'review', 4: 'transcript', 5: 'study', 6: 'exports', 7: 'settings' };
      if (map[e.key]) setScreen(map[e.key]);
      else if (e.key === 'f' || e.key === 'F') setFocus(!LP.state.focus);
    });
    // Electron closes the renderer without necessarily switching lectures.
    // Persist the currently viewed lecture at the final reliable page event.
    window.addEventListener('beforeunload', function () {
      if (LP.state.jobId) captureResumeState(LP.state.jobId);
    });
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
      // One routing implementation, not two: completion routes through the
      // same admit() the initial bootstrap uses.
      RuntimeSetupGate.admit(b);
      if (!b.bootstrap_pending && b.runtime_health_state !== 'SETUP_REQUIRED') {
        normalBridgeAdmitted = true;
        if (normalBridgeActivityPending || !normalBridgeActivityStarted) startNormalBridgeActivity();
      }
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
      LP.data.jobs = jobs;
      // Forget selections whose job is gone, else the count lies.
      if (LP.state.selecting) {
        var alive = {};
        LP.data.jobs.forEach(function (j) { if (j.id) alive[j.id] = true; });
        Object.keys(LP.state.selected).forEach(function (id) {
          if (!alive[id]) delete LP.state.selected[id];
        });
        renderSelCount();
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
        var item = mediaLink.downloads.filter(function (candidate) { return candidate.id === update.download_id; })[0];
        if (item) {
          ['status', 'pct', 'eta', 'speed', 'downloaded', 'total'].forEach(function (key) {
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
          var statusLabel = $('status-label');
          if (statusLabel) statusLabel.textContent = 'Idle';
          var statusPct = $('status-pct');
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
      appendStudyAskSources(payload && payload.sources ? payload.sources : []);
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
      if (s.actual_backend) $('status-right').textContent = friendlyProcessingLabel(s.actual_backend) || s.actual_backend;
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

  function importDroppedFiles(files) {
    if (!files || !files.length || importingFile) return;
    var paths = [];
    for (var i = 0; i < files.length; i++) {
      var path = lpBridge.pathForFile ? lpBridge.pathForFile(files[i]) : '';
      if (path) paths.push(path);
    }
    if (!paths.length) {
      toast('LecturePack could not access those files. Try Browse for video.');
      return;
    }
    if (!lpBridge.connected()) {
      setOnb('detected');
      return;
    }
    if (paths.length === 1) {
      importDroppedVideo(files[0]);
      return;
    }
    // Batch: import every file through the normal import path via the sidecar.
    importingFile = files[0].name || paths[0];
    setImporting(true, importingFile);
    setOnb(null);
    lpBridge.call('import_videos', { paths: paths }).then(function (result) {
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
    batchMode = 'study'; batchQuality = 'balanced';
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
  function renderProcessingStrip() {
    var strip = $('proc-strip');
    if (!strip) return;
    var running = LP.data.jobs.filter(function (j) { return j && j.status === 'running'; })[0];
    if (!running) {
      strip.hidden = true;
      renderProcessWorkload();
      return;
    }
    strip.hidden = false;
    $('proc-strip-name').textContent = running.name || 'Processing';
    var pct = running.pct || 0;
    setFill('proc-strip-bar', pct);
    var stage = running.stage || '';
    var parts = [friendlyProcessingLabel(stage || 'Processing')];
    if (pct > 0) parts.push(pct + '%');
    var eta = etaLabel(running);
    if (eta) parts.push(eta);
    $('proc-strip-meta').textContent = parts.join(' · ');
    var waiting = (LP.data.queue && LP.data.queue.queue) ? LP.data.queue.queue.length : 0;
    $('proc-strip-waiting').textContent = waiting > 0 ? (waiting + ' queued') : '';
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

  function transcriptScrollHost() {
    return document.querySelector('main [data-screen="transcript"]');
  }

  function applyPendingTranscriptJump() {
    if (!pendingTranscriptJump || pendingTranscriptJump.jobId !== LP.state.jobId) return;
    var wanted = pendingTranscriptJump.timestamp;
    var rows = document.querySelectorAll('#transcript-blocks [data-transcript-time]');
    var target = null;
    Array.prototype.some.call(rows, function (row) {
      if (row.dataset.transcriptTime === wanted) { target = row; return true; }
      return false;
    });
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
    if (state.screen && state.screen !== 'home' && state.screen !== 'settings') {
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
    wireGuidedTour();
    wireModelTooltip();
    wireBridge();
    bindStudyV2Events();
    renderStudyV2Overview();
    window.addEventListener('resize', function () { LP.motion.indicator(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
