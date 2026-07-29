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
      ssDismissed: false  // user chose "Continue with Built-in Study"
    },
    data: {
      version: '0.0.0',
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
                        'quiz', 'flashcards', 'exportFiles'];

  function emptyWorkspace() {
    return {
      pipeline: { title: 'No lecture loaded', meta: '', stages: [], log: [] },
      slides: [],
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

  /* Switch which lecture the workspace belongs to. Driven by the backend's
     active_job signal -- the UI never invents a job identity. */
  function setActiveJob(id, title) {
    id = id || '';
    if (id === LP.state.jobId) {
      if (title) LP.state.jobTitle = title;
      renderJobChrome();
      return;
    }
    if (LP.state.jobId) LP.byJob[LP.state.jobId] = snapshotWorkspace();
    LP.state.jobId = id;
    LP.state.jobTitle = title || '';
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
    renderWorkspace();
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
    return { close: close };
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

  // `.lp-toast`'s CSS entrance is opacity-only (reuses `lpsupport`), so it cannot
  // conflict with this singleton's inline `transform:translateX(-50%)`
  // centering. Re-trigger the entrance on every show by toggling the class
  // off/on around a reflow; skipped entirely under reduced motion.
  var _toastT = null;
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
  // Maps the app's own status vocabularies onto the seven lp-state values
  // (idle|running|paused|success|failed|interrupted|complete). Purely a
  // lookup for motion/color feedback -- never consulted for app logic.
  var JOB_STATE_MAP = {
    running: 'running', done: 'complete', interrupted: 'interrupted',
    failed: 'failed', paused: 'paused', queued: 'idle', scheduled: 'idle'
  };
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
    lpModal({
      title: 'Group ' + ids.length + (ids.length === 1 ? ' lecture' : ' lectures'),
      bodyHtml: '<label style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px">Course / subject</label>' +
        '<input id="lp-bulk-group-input" type="text" spellcheck="false" placeholder="e.g. CL100" style="width:100%;box-sizing:border-box;font:600 14px \'JetBrains Mono\';background:var(--sunk);border:2px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--ink)">' +
        '<div style="font-size:12px;color:var(--muted);margin-top:8px">Leave blank to auto-group by each lecture title.</div>',
      actions: [
        { label: 'Cancel' },
        { label: 'Apply', primary: true, onClick: function () {
          var i = $('lp-bulk-group-input');
          if (lpBridge.connected()) lpBridge.call('set_jobs_group', JSON.stringify(ids), (i && i.value || '').trim());
          else toast('Preview mode — not grouped');
          setSelectMode(false);
        } }
      ]
    });
    setTimeout(function () { var i = $('lp-bulk-group-input'); if (i) i.focus(); }, 30);
  }

  function _jobCardHtml(j) {
    var b = JOB_BADGES[j.status] || JOB_BADGES.done;
    var dot = '<span style="width:6px;height:6px;border-radius:50%;background:' + b.dot + (b.blink ? ';animation:lpblink 1s infinite' : '') + '"></span>';
    var badge = '<span class="lp-state" data-state="' + (JOB_STATE_MAP[j.status] || 'idle') + '" style="position:absolute;top:9px;right:9px;display:flex;align-items:center;gap:5px;font:600 10px \'JetBrains Mono\';text-transform:uppercase;background:' + b.bg + ';color:' + b.fg + ';border-radius:6px;padding:3px 8px">' + dot + b.label + '</span>';
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
    return '<div class="lp-card" ' + (j.id ? 'data-job="' + esc(j.id) + '" ' : '') + 'style="background:var(--panel);border:2px solid ' + border + ';border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;cursor:pointer">' +
      '<div style="height:118px;background:var(--sunk);border-bottom:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;position:relative">' + posterHtml(j) + (selecting ? selbox : menu) + badge + '</div>' +
      '<div style="padding:14px 16px">' + body + '</div></div>';
  }

  /* ==================== import from a link (yt-dlp) ====================
     Three short steps, each its own lpModal so they inherit the focus trap:
     paste -> confirm what was found -> transfer with progress/cancel.
     The backend hands the finished file to the normal import path, so the
     existing New-job overlay takes over from there. */
  var mediaLink = { available: false, version: '', progressModal: null, done: null };

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
      '<label for="link-url" style="display:block;font:600 11px \'JetBrains Mono\';text-transform:uppercase;color:var(--muted);margin-bottom:6px">Video link</label>' +
      '<input id="link-url" type="url" spellcheck="false" placeholder="https://…" style="' + inp + '">' +
      '<div id="link-msg" role="status" style="min-height:18px;font-size:12px;color:var(--muted);margin-top:9px"></div>' +
      '<div style="font-size:12px;line-height:1.5;color:var(--muted);margin-top:4px">Downloads the recording to your computer so it can be processed here. Only fetch lectures you have the right to download.</div>';
    var m = lpModal({
      title: 'Import from a link',
      bodyHtml: body,
      actions: [
        { label: 'Cancel' },
        { label: 'Check link', primary: true, onClick: function () {
          var v = ($('link-url') || {}).value || '';
          v = v.trim();
          if (!/^https?:\/\/.+/i.test(v)) { setLinkMsg('Enter a full http(s) link.', true); return true; }
          setLinkMsg('Looking it up…');
          mediaLink.pending = v;
          lpBridge.call('probe_media_url', v);
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
    var meta = [fmtDuration(info.duration), info.uploader, info.extractor]
      .filter(Boolean).join(' · ');
    var warn = info.is_live
      ? '<div style="font-size:12px;color:var(--orange-ink);margin-top:9px">This looks like a live stream — only the portion already broadcast can be fetched.</div>'
      : '';
    lpModal({
      title: 'Import this recording?',
      bodyHtml: '<div style="font-weight:700;font-size:15px;margin-bottom:5px;word-break:break-word">' + esc(info.title || 'Untitled') + '</div>' +
        '<div style="font:500 12px \'JetBrains Mono\';color:var(--muted)">' + esc(meta) + '</div>' + warn,
      actions: [
        { label: 'Cancel' },
        { label: 'Download', primary: true, onClick: function () {
          linkProgressDialog(info.title || '');
          lpBridge.call('import_media_url', info.webpage_url || mediaLink.pending || '', info.title || '');
        } }
      ]
    });
  }

  function linkProgressDialog(title) {
    var m = lpModal({
      title: 'Downloading',
      bodyHtml: '<div style="font-weight:600;font-size:14px;margin-bottom:10px;word-break:break-word">' + esc(title || 'Fetching…') + '</div>' +
        '<div style="height:9px;border-radius:6px;background:var(--sunk);overflow:hidden"><div id="link-bar" class="lp-fill" style="width:100%;height:100%;background:var(--orange);transform:scaleX(0)"></div></div>' +
        '<div id="link-stat" role="status" style="font:500 11px \'JetBrains Mono\';color:var(--muted);margin-top:8px">starting…</div>',
      actions: [{ label: 'Cancel download', danger: true, onClick: function () {
        lpBridge.call('cancel_media_url');
      } }]
    });
    mediaLink.progressModal = m;
  }

  function onMediaProgress(p) {
    var bar = $('link-bar'), stat = $('link-stat');
    if (!bar || !stat) return;
    setFill(bar, p.pct || 0);
    var bits = [(p.pct || 0) + '%'];
    if (p.total) bits.push(fmtBytes(p.downloaded) + ' / ' + fmtBytes(p.total));
    else if (p.downloaded) bits.push(fmtBytes(p.downloaded));
    if (p.speed) bits.push(fmtBytes(p.speed) + '/s');
    if (p.eta) bits.push('~' + fmtDuration(p.eta) + ' left');
    stat.textContent = p.status === 'finished' ? 'finishing up…' : bits.join(' · ');
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
      return '<div class="lp-anim-in" style="display:flex;align-items:center;gap:12px;background:var(--panel);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px">' +
        '<span style="font:700 12px \'JetBrains Mono\';color:var(--muted);min-width:20px">' + (i + 1) + '</span>' +
        '<span style="flex:1;font-weight:600;font-size:13.5px">' + esc(_jobName(row.id)) + '</span>' +
        '<div style="display:flex;gap:6px">' +
          qbtn('runnow', 'Run Now') + qbtn('up', '↑', i === 0) +
          qbtn('down', '↓', i === q.length - 1) +
          qbtn('schedule', 'Schedule') + qbtn('remove', 'Remove') +
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
  var _pipeRaf = 0;
  function schedulePipelineRender() {
    if (_pipeRaf) return;
    _pipeRaf = (window.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () {
      _pipeRaf = 0;
      renderPipeline();
    });
  }
  function renderPipeline() {
    var p = LP.data.pipeline;
    $('proc-status-title').textContent = p.title;
    $('proc-status-meta').textContent = p.meta;
    // BUG-16: the Process screen's "Source" card had NO writer anywhere in
    // app.js -- the same defect class as BUG-04's storage figure. It was only
    // ever set by resetJobChrome(), so it read "No lecture loaded" plus a
    // hardcoded "1920x1080 · 06:12 · H.264" even while a real lecture was
    // being processed. The pipeline payload already carries both values.
    var hasJob = !!(p.title && p.stages && p.stages.length);
    $('proc-source-name').textContent = hasJob ? p.title : 'No lecture loaded';
    $('proc-source-meta').textContent = hasJob ? (p.meta || '') : '';
    var stagesEl = $('pipeline-stages');
    var stageHtml = p.stages.map(function (st) {
      // Contract data-state values: idle|running|paused|success|failed|interrupted|complete
      var ds = st.state === 'done' ? 'complete' : st.state === 'active' ? 'running' :
        st.state === 'error' ? 'failed' : 'idle';
      if (st.state === 'done') {
        return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:600;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;background:var(--green-fill);border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--on-signal)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--green-soft);overflow:hidden"><div style="width:100%;height:100%;background:var(--green)"></div></div></div>';
      }
      if (st.state === 'active') {
        var c = st.color === 'blue' ? 'var(--blue)' : 'var(--orange)';
        var pctColor = st.color === 'blue' ? ';color:var(--blue-ink)' : '';
        var blink = st.color === 'blue' ? '1.3s' : '1s';
        return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px"><span style="width:120px;flex:none;font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid ' + c + ';border-radius:50%;flex:none;animation:lpblink ' + blink + ' infinite"></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk);overflow:hidden"><div style="width:' + (st.pct || 0) + '%;height:100%;background:' + c + ';background-image:repeating-linear-gradient(90deg,transparent,transparent 6px,rgba(255,255,255,.32) 6px,rgba(255,255,255,.32) 13px);animation:lpbar 1s linear infinite"></div></div><span style="width:38px;text-align:right;font:700 11px \'JetBrains Mono\'' + pctColor + '">' + (st.pct || 0) + '%</span></div>';
      }
      return '<div class="lp-stage" data-state="' + ds + '" style="display:flex;align-items:center;gap:13px;opacity:.45"><span style="width:120px;flex:none;font-size:13px;display:flex;align-items:center;gap:8px"><span style="width:19px;height:19px;border:2px solid var(--muted);border-radius:50%;flex:none"></span>' + esc(st.label) + '</span><div style="flex:1;height:9px;border-radius:6px;background:var(--sunk)"></div></div>';
    }).join('');
    if (stagesEl.innerHTML !== stageHtml) { stagesEl.innerHTML = stageHtml; }
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
      return '<div style="' + row + '"><span style="width:66px;flex:none;font:500 11px \'JetBrains Mono\';color:' + tColor + '">' + esc(s.t) + '</span><span contenteditable="true" style="flex:1;font-size:13px;line-height:1.5">' + esc(s.text) + '</span></div>';
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
      return '<div style="display:flex;gap:18px"><div style="width:58px;flex:none;text-align:right">' + chip + '</div><p style="margin:0;font-size:17px;line-height:1.72;text-wrap:pretty">' + b.html + '</p></div>';
    }).join('');
  }

  function renderStudy() {
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
  }

  function applyTheme(theme, persist) {
    if (LP.state.theme === theme && $('app').dataset.theme === theme) return;
    LP.state.theme = theme;
    $('app').dataset.theme = theme;
    $('theme-label').textContent = theme === 'light' ? 'DARK' : 'LIGHT';
    $('theme-icon').setAttribute('d', theme === 'light'
      ? 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4'
      : 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z');
    $('btn-set-light').classList.toggle('active', theme === 'light');
    $('btn-set-dark').classList.toggle('active', theme === 'dark');
    if (persist) lpBridge.call('set_setting', 'theme', theme);
  }

  function setTheme(theme) { applyTheme(theme, true); }

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
    ['runtime-setup-overlay', 'onb-overlay', 'whatsnew-overlay'].forEach(function (id) {
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
  /* The one mutable lifecycle reducer used by the DOM controller and Node tests. */
  function RuntimeSetupGateModel() {
    var state = 'gate', returnState = 'gate', retryPending = false, cancelPending = false;
    var activeOperation = null, terminal = false, offer = null, bootstrapPending = true, healthy = false;
    function valid(value) {
      return !!(value && value.operation_id === activeOperation && value.app_version && value.source &&
        value.affected_components && Number.isSafeInteger(value.download_size_bytes) && value.download_size_bytes >= 0);
    }
    function snapshot() {
      return { state: state, returnState: returnState, retryPending: retryPending, cancelPending: cancelPending,
        activeOperation: activeOperation, terminal: terminal, offer: offer, bootstrapPending: bootstrapPending, healthy: healthy };
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
        bootstrapPending = false;
        if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') {
          healthy = false; terminal = true;
          if (!activeOperation) { state = 'gate'; terminal = false; offer = null; cancelPending = false; }
        } else if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY') {
          healthy = true;
          if (activeOperation && !terminal) this.event({ operation_id: activeOperation, kind: 'admitted' });
        }
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
        state = 'gate'; returnState = 'gate'; retryPending = false; cancelPending = false;
        activeOperation = null; terminal = false; offer = null; healthy = false; return snapshot();
      },
      snapshot: snapshot
    };
  }
  var RuntimeSetupGate = (function () {
    var STATES = ['gate', 'diagnostics', 'confirm', 'repairing', 'offline', 'failed', 'ready'];
    var bootstrapSnapshot = null, restoreInert = [], inertCaptured = false, priorFocus = null;
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
        inertCaptured = true; document.documentElement.style.overflow = 'hidden';
      } else {
        if (!inertCaptured) return;
        restoreInert.forEach(function (saved) {
          try { saved.el.inert = saved.inert; } catch (e) {}
          if (saved.aria === null) saved.el.removeAttribute('aria-hidden'); else saved.el.setAttribute('aria-hidden', saved.aria);
          saved.el.style.pointerEvents = saved.pointer;
        });
        restoreInert = []; inertCaptured = false; document.documentElement.style.overflow = '';
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
    function renderOffer() {
      var value = eventModel.snapshot().offer, enabled = validOffer(value);
      text('runtime-offer-source', enabled ? value.source : '');
      text('runtime-offer-version', enabled ? value.app_version : '');
      text('runtime-offer-components', enabled ? value.affected_components : '');
      text('runtime-offer-size', enabled ? value.download_size_label : '');
      text('runtime-offer-technical', enabled ? value.technical_details || '' : '');
      $('btn-runtime-confirm').disabled = !enabled;
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
    function render() {
      var view = eventModel.snapshot(), next = view.state;
      if (STATES.indexOf(next) < 0) return;
      var el = overlay(); if (!el) return;
      el.hidden = false; el.classList.remove('out'); setUnderlyingInert(true);
      Array.prototype.forEach.call(el.querySelectorAll('[data-runtime-state]'), function (panel) { panel.hidden = panel.dataset.runtimeState !== next; });
      renderComponents(); renderOffer();
      var targets = { gate: 'btn-runtime-repair', confirm: 'btn-runtime-confirm', repairing: 'btn-runtime-cancel', offline: 'btn-runtime-offline-retry', failed: 'btn-runtime-failed-retry', diagnostics: 'runtime-diagnostics-heading', ready: 'runtime-ready-heading' };
      var target = $(targets[next]); if (target) target.focus();
    }
    function closeReady() {
      var el = overlay(); if (!el || eventModel.snapshot().state !== 'ready') return;
      setUnderlyingInert(false); el.hidden = true; eventModel.reset();
      var target = isNormalFocusable(priorFocus) ? priorFocus : fallbackFocus();
      if (isNormalFocusable(target)) target.focus();
    }
    function admit(bootstrap) {
      bootstrapSnapshot = bootstrap && bootstrap.setup_required || bootstrap || bootstrapSnapshot;
      var before = eventModel.snapshot(), view = eventModel.bootstrap(bootstrap);
      syncDemoAdmission(view);
      if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') { render(); return; }
      if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY' && !before.activeOperation) { setUnderlyingInert(false); return; }
      if (view.state === 'ready') ready();
    }
    // The guided demo is available only after this authoritative setup gate
    // admits the runtime. Its controller owns both initial and repair paths.
    function syncDemoAdmission(view) {
      setDemoAdmissionAvailable(!!(view && view.healthy && !view.bootstrapPending &&
        (view.state === 'ready' || !view.activeOperation)));
    }
    function beginOffer() {
      var previous = eventModel.snapshot(); if (previous.retryPending || (previous.activeOperation && !previous.terminal)) return;
      var view = eventModel.begin(operationId());
      $('btn-runtime-repair').disabled = true; announce('runtime-live-polite', 'Checking runtime…');
      render(); lpBridge.beginRuntimeRepairOffer(view.activeOperation).then(function () {});
    }
    function confirm() {
      var before = eventModel.snapshot(); if (!validOffer(before.offer) || before.terminal) return;
      var view = eventModel.confirm(); if (view.state !== 'repairing') return;
      render(); text('runtime-progress-text', 'Downloading'); lpBridge.confirmRuntimeRepair(view.activeOperation);
    }
    function retryAssessment() {
      if (eventModel.snapshot().retryPending) return;
      eventModel.retry(); $('btn-runtime-retry').disabled = true; announce('runtime-live-polite', 'Checking runtime…');
      lpBridge.retryRuntimeAssessment().then(function (json) {
        var bootstrap; try { bootstrap = JSON.parse(json); } catch (e) { bootstrap = null; }
        bootstrapSnapshot = bootstrap && bootstrap.setup_required || bootstrap || bootstrapSnapshot;
        var view = eventModel.retryResult(bootstrap); $('btn-runtime-retry').disabled = false;
        syncDemoAdmission(view);
        if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY' && !view.activeOperation) setUnderlyingInert(false); else render();
      });
    }
    function beginNewRepair() {
      var view = eventModel.begin(operationId(), 'repairing');
      render(); text('runtime-progress-text', 'Downloading'); lpBridge.beginRuntimeRepairOffer(view.activeOperation);
    }
    function cancel() {
      var view = eventModel.snapshot(); if (!view.activeOperation || view.cancelPending || view.terminal) return;
      view = eventModel.requestCancel(); $('btn-runtime-cancel').disabled = true; text('btn-runtime-cancel', 'Cancelling safely…');
      lpBridge.cancelRuntimeRepair(view.activeOperation);
    }
    function diagnostics(invoker) {
      eventModel.diagnostics();
      if (invoker) RuntimeSetupGate._diagnosticsInvoker = invoker;
      text('runtime-diagnostics-summary', 'Review the runtime repair details below.');
      text('runtime-diagnostics-report', bootstrapSnapshot && (bootstrapSnapshot.diagnostics || bootstrapSnapshot.summary) || 'No additional diagnostics are available.');
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
        render(); return;
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
      Array.prototype.forEach.call(document.querySelectorAll('[data-runtime-diagnostics]'), function (button) { button.addEventListener('click', function () { diagnostics(button); }); });
      $('btn-runtime-diagnostics-back').addEventListener('click', back);
      function diagnosticFeedback(promise, ok, bad) { promise.then(function (json) { var r; try { r = JSON.parse(json); } catch (e) {} announce('runtime-live-polite', r && /copied|saved/.test(r.type || '') ? ok : bad); }, function () { announce('runtime-live-polite', bad); }); }
      $('btn-runtime-copy').addEventListener('click', function () { diagnosticFeedback(lpBridge.copyRuntimeRepairDiagnostics(), 'Details copied.', 'Could not copy details.'); });
      $('btn-runtime-save').addEventListener('click', function () { diagnosticFeedback(lpBridge.saveRuntimeRepairDiagnostics('runtime-repair-report.txt'), 'Report saved.', 'Could not save report.'); });
      document.addEventListener('keydown', function (e) { if (!isBlocking()) return; if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); return; } if (e.key === 'Tab' && isOpen()) { trapFocus(overlay(), e); e.stopImmediatePropagation(); return; } e.stopImmediatePropagation(); }, true);
      document.addEventListener('wheel', function (e) { if (isBlocking() && (!isOpen() || !overlay().contains(e.target))) { e.preventDefault(); e.stopImmediatePropagation(); } }, { capture: true, passive: false });
      document.addEventListener('pointerdown', function (e) { if (isBlocking() && (!isOpen() || !overlay().contains(e.target))) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
    }
    return { admit: admit, event: event, wire: wire, beginBootstrap: function () { setUnderlyingInert(true); }, isOpen: isOpen, state: function () { return eventModel.snapshot().state; }, _diagnosticsInvoker: null };
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
    LP.state.jobsEmpty = empty;
    $('home-jobs').hidden = empty;
    $('home-empty').hidden = !empty;
  }

  /* ======================= guided tour / demo ======================= */
  var TOUR_STORAGE_KEY = 'lecturepack.guided-tour.seen.v1';
  var DEMO_DRAG_MIME = 'application/x-lecturepack-demo';
  var TOUR_PHASES = {
    import: { screen: 'home', target: '#dropzone', title: 'Add the demo video', copy: 'Drag the Polar Bears demo into this lecture area, or click the tile to use it.', next: 'Add demo to continue' },
    processing: { screen: 'process', target: '#pipeline-stages', title: 'Watch real processing', copy: 'This is the live local pipeline. It advances only as each step actually completes.', next: 'Processing safely…' },
    review: { screen: 'review', target: '#demo-review-actions', title: 'Make one review choice', copy: 'Use Keep or Reject on the existing review controls to continue.', next: 'Make a review choice' },
    study: { screen: 'study', target: '#demo-study-actions', title: 'Ask about the lecture', copy: 'The study workspace is ready. Try the chat box, then continue when you are ready.', next: 'Next' },
    exports: { screen: 'exports', target: '#btn-export-all', title: 'See export options', copy: 'Exporting unlocks for your own processed lecture. This temporary demo only shows where those options live.', next: 'Finish' }
  };
  function tourSeen() {
    try { return window.localStorage.getItem(TOUR_STORAGE_KEY) === '1'; } catch (e) { return false; }
  }
  function markTourSeen() {
    try { window.localStorage.setItem(TOUR_STORAGE_KEY, '1'); } catch (e) {}
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
      return;
    }
    renderDemoCard();
    if (!wasAvailable) offerGuidedTour();
  }
  function renderDemoHomeAvailability() {
    var demoHome = $('home-demo');
    if (demoHome) demoHome.hidden = !demoAdmissionAvailable ||
      (demoHomeDismissed && !guidedTour.snapshot().active);
  }

  function stageLabel(name) {
    var labels = { prepare: 'Preparing demo', inspect: 'Inspecting video', extract_audio: 'Extracting audio', transcribe: 'Transcribing locally', detect_slides: 'Detecting slides', align: 'Aligning notes', review_ready: 'Preparing review', export: 'Exporting study pack', complete: 'Complete' };
    return labels[name] || (name ? String(name).replace(/_/g, ' ') : 'Preparing demo');
  }
  function guidedDemoSensitivityLocked() {
    return guidedTour.snapshot().active && demoFlowPhase() !== 'idle';
  }
  function renderSlideDetectionPreset() {
    var group = $('proc-sensitivity'), note = $('proc-sensitivity-note');
    if (!group) return;
    var state = slideDetectionPreset.snapshot(), locked = guidedDemoSensitivityLocked();
    Array.prototype.forEach.call(group.querySelectorAll('button[data-sens]'), function (button) {
      var active = button.dataset.sens === state.label;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.disabled = locked;
      button.title = locked ? 'Guided demo uses its fixed reliable setting.' : '';
      button.style.fontWeight = active ? '700' : '500';
      button.style.borderColor = active ? 'var(--secondary-border)' : 'transparent';
      button.style.background = active ? 'var(--secondary-surface)' : 'transparent';
      button.style.color = active ? 'var(--secondary-text)' : 'var(--muted)';
      button.style.cursor = locked ? 'not-allowed' : 'pointer';
    });
    if (note) note.hidden = !locked;
  }
  function setSlideDetectionPreset(label) {
    if (guidedDemoSensitivityLocked()) return;
    var state = slideDetectionPreset.select(label);
    renderSlideDetectionPreset();
    lpBridge.call('set_setting', 'slide_detection_preset', state.preset);
  }
  function renderDemoCard() {
    var card = $('glowing-demo-card'), status = $('demo-card-status'), action = $('demo-card-action');
    if (!card || !status || !action) return;
    var d = guidedDemo.snapshot();
    card.dataset.demoState = d.status === 'failed' || d.status === 'error' ? 'error' : (d.active ? 'running' : 'idle');
    if (d.status === 'error' || d.status === 'failed') {
      status.textContent = d.error || 'The guided demo could not start.'; action.textContent = 'Try again'; return;
    }
    if (d.active) {
      status.textContent = stageLabel(d.stage) + ' · ' + Math.round(d.progress) + '%';
      action.textContent = d.status === 'cancelling' ? 'Stopping…' : 'End demo'; return;
    }
    if (d.status === 'ended') { status.textContent = 'Demo ended and its temporary files were removed.'; action.textContent = 'Try guided demo'; return; }
    status.textContent = 'Move this demo video into the lecture drop area, or click to use it.';
    action.textContent = 'Use demo video';
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
    model.textContent = text || '—';
    if (!text) hideModelTooltip();
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
    if (!target) { box.style.width = '0px'; box.style.height = '0px'; arrow.hidden = true; return; }
    var before = target.getBoundingClientRect();
    if (before.top < 0 || before.left < 0 || before.bottom > window.innerHeight || before.right > window.innerWidth) {
      target.scrollIntoView({block: 'nearest', inline: 'nearest'});
    }
    var r = target.getBoundingClientRect(), pad = 7;
    var left = Math.max(6, Math.min(Math.round(r.left - pad), window.innerWidth - Math.round(r.width + pad * 2) - 6));
    var top = Math.max(6, Math.min(Math.round(r.top - pad), window.innerHeight - Math.round(r.height + pad * 2) - 6));
    var width = Math.max(0, Math.min(Math.round(r.width + pad * 2), window.innerWidth - left - 6));
    var height = Math.max(0, Math.min(Math.round(r.height + pad * 2), window.innerHeight - top - 6));
    box.style.left = left + 'px';
    box.style.top = top + 'px';
    box.style.width = width + 'px';
    box.style.height = height + 'px';
    arrow.hidden = false;
    arrow.style.left = Math.round(r.left + Math.min(r.width - 18, 24)) + 'px';
    arrow.style.top = Math.max(8, Math.round(r.top - 19)) + 'px';
    positionLiftedDemoCard();
  }
  function renderGuidedTour() {
    var state = guidedTour.snapshot(), overlay = $('guided-tour-overlay');
    if (!overlay) return;
    overlay.hidden = !demoAdmissionAvailable || (!state.active && !state.prompt);
    if (overlay.hidden) { setDemoTourInteraction(false); return; }
    var isPrompt = state.prompt, phase = state.active ? currentTourPhase() : null, flow = guidedDemoFlow.snapshot();
    $('tour-step-label').textContent = isPrompt ? 'WELCOME' : 'DEMO · ' + flow.phase.toUpperCase();
    $('tour-title').textContent = isPrompt ? 'A quick look around' : phase.title;
    $('tour-copy').textContent = isPrompt ? 'Want a short, user-controlled tour of the main parts of LecturePack?' : phase.copy;
    $('tour-prompt-actions').hidden = !isPrompt;
    $('tour-step-actions').hidden = !state.active;
    $('btn-tour-back').disabled = !state.active || !flow.backEnabled;
    $('btn-tour-next').disabled = !state.active || !flow.nextEnabled;
    $('btn-tour-next').textContent = state.active ? phase.next : 'Next';
    $('tour-progress').innerHTML = isPrompt ? '' : Object.keys(TOUR_PHASES).map(function (name) { return '<span class="' + (name === flow.phase ? 'active' : '') + '"></span>'; }).join('');
    $('tour-spotlight-box').style.display = state.active ? 'block' : 'none';
    $('tour-arrow').style.display = state.active ? 'block' : 'none';
    setDemoTourInteraction(state.active && flow.phase === 'import');
    if (state.active) scheduleTourGeometry();
  }
  function offerGuidedTour() {
    if (!demoAdmissionAvailable || !tourRuntimeHealthy) return;
    guidedTour.offer(); renderGuidedTour();
  }
  function startGuidedTour(replay) {
    if (!demoAdmissionAvailable) return;
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
    if (direction > 0 && flow.phase === 'exports') { exitGuidedTour(); return; }
    if (direction > 0) guidedDemoFlow.next(); else guidedDemoFlow.back();
    var phase = currentTourPhase();
    if (phase) setScreen(phase.screen);
    renderGuidedTour();
  }
  function parseBridgeResult(value) {
    if (typeof value === 'string') { try { return JSON.parse(value); } catch (e) { return null; } }
    return value && typeof value === 'object' ? value : null;
  }
  function startGuidedDemo() {
    var current = guidedDemo.snapshot();
    if (current.active) { endGuidedDemo('user_cancelled'); return; }
    if (!demoAdmissionAvailable) return;
    if (!lpBridge.connected()) { toast('Guided demo needs the LecturePack desktop app.'); return; }
    if (!guidedTour.snapshot().active) startGuidedTour(true);
    // A retry after clean-up (or a failed start) is a new demo, not a
    // continuation of whatever action-led screen the prior run last reached.
    // Do not reset the current run: active attempts returned above.
    if (demoFlowPhase() !== 'import') guidedDemoFlow.beginAttempt();
    guidedDemoFlow.imported(); guidedDemoFlow.running();
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
    }, function () {
      if (!guidedDemo.isCurrentAttempt(startedAttempt)) return;
      guidedDemo.started({ ok: false, error: 'Could not start the guided demo.' }, startedAttempt);
      renderDemoCard();
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
      guidedDemoFlow.reviewReady();
      if (guidedTour.snapshot().active) { setScreen('review'); renderGuidedTour(); }
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
    $('btn-replay-tour').addEventListener('click', function () { startGuidedTour(true); });
    var demoCard = $('glowing-demo-card');
    demoCard.addEventListener('click', function () {
      if (guidedDemo.snapshot().active) { startGuidedDemo(); return; }
      flyDemoTileToDropzone(startGuidedDemo);
    });
    demoCard.addEventListener('dragstart', function (e) {
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

    $('btn-paste-link').addEventListener('click', function (e) {
      e.stopPropagation();
      linkImportDialog();
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
      setOnb('detected');
    });
    // "drop anywhere": in the desktop shell native drops are captured by Qt and
    // routed through backend.import_video, which drives the same overlay.
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) { e.preventDefault(); });

    $('btn-show-empty').addEventListener('click', function () { setJobsEmpty(true); });
    $('btn-load-jobs').addEventListener('click', function () { setJobsEmpty(false); });

    // Home grid: per-card menu buttons (delete / set group) take priority,
    // otherwise clicking a card opens the job.
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

    // Keyboard shortcuts.  An open overlay OWNS the keyboard: digit/F shortcuts
    // must not change the screen behind a modal, and Tab must not escape to
    // controls the user cannot see (both were live defects -- see BUG_LIST.md
    // BUG-01 and BUG-02).
    window.addEventListener('keydown', function (e) {
      var tag = (e.target && e.target.tagName) || '';
      var editing = /INPUT|TEXTAREA|SELECT/.test(tag) || (e.target && e.target.isContentEditable);
      if (e.key === 'Escape') {
        setFocus(false); setOnb(null);
        if (!$('whatsnew-overlay').hidden) hideWhatsNew();
        return;
      }
      var overlay = topOverlay();
      if (overlay) {
        if (e.key === 'Tab') {
          if (guidedTour.snapshot().active) trapTourFocus(e);
          else trapFocus(overlay, e);
        }
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
    lpBridge.on('repair_event', function (json) { RuntimeSetupGate.event(json); });
    lpBridge.on('demo_event', receiveDemoEvent);
    lpBridge.on('queue_changed', function (json) {
      try { LP.data.queue = JSON.parse(json); } catch (e) { return; }
      renderQueue();
      renderScheduled();
    });
    lpBridge.on('pause_state', function (json) {
      var st; try { st = JSON.parse(json).state; } catch (e) { return; }
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
      _applyLpState(panel, 'complete');
    });
    lpBridge.on('notification_prefs', function (json) {
      var prefs; try { prefs = JSON.parse(json); } catch (e) { return; }
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
      try { s = JSON.parse(json); } catch (e) { w.hidden = true; return; }
      if (!s || !s.ok) { w.hidden = true; return; }
      $('storage-label').textContent = s.used_h + ' · ' + s.free_h + ' free';
      setFill('storage-bar', s.pct);
      w.hidden = false;
    });

    lpBridge.on('jobs_changed', function (json) {
      LP.data.jobs = JSON.parse(json);
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
    });

    // ---- import from a link ----
    lpBridge.on('media_link_state', function (json) {
      var s = JSON.parse(json || '{}');
      mediaLink.available = !!s.available;
      mediaLink.version = s.version || '';
      var btn = $('btn-paste-link');
      if (btn) btn.hidden = !mediaLink.available;
    });

    lpBridge.on('media_probe', function (json) {
      var info = JSON.parse(json || '{}');
      if (!info.ok) { setLinkMsg(info.error || 'That link could not be read.', true); return; }
      if (mediaLink.probeModal) { mediaLink.probeModal.close(); mediaLink.probeModal = null; }
      linkConfirmDialog(info);
    });

    lpBridge.on('media_progress', function (json) {
      try { onMediaProgress(JSON.parse(json || '{}')); } catch (err) { /* ignore */ }
    });

    lpBridge.on('media_done', function (json) {
      var r = JSON.parse(json || '{}');
      if (mediaLink.progressModal) { mediaLink.progressModal.close(); mediaLink.progressModal = null; }
      if (r.ok) toast('Downloaded ' + (r.name || 'the recording'));
      else if (r.cancelled) toast('Download cancelled');
      else lpModal({ title: 'Download failed', bodyHtml: esc(r.error || 'Unknown error.'), actions: [{ label: 'Close', primary: true }] });
    });
    lpBridge.on('job_deleted', function (json) {
      var d = JSON.parse(json);
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
          delete LP.byJob[id];
          delete LP.state.selected[id];
        });
        renderSelCount();
        return;
      }
      toast(d.ok ? ('Lecture deleted · ' + (d.freed || '') + ' freed') : 'Delete failed');
      // Drop the deleted lecture's cached workspace so it can never come back
      // if a job id is ever reused, and empty the screens if it was active.
      if (d.ok && d.id) {
        // Deactivate FIRST: setActiveJob snapshots the outgoing lecture into
        // byJob, so deleting before the switch would put it straight back.
        if (d.id === LP.state.jobId) setActiveJob('', '');
        delete LP.byJob[d.id];
      }
    });

    // The backend owns which lecture the workspace belongs to; the UI follows.
    lpBridge.on('active_job', function (json) {
      var a = JSON.parse(json || '{}');
      setActiveJob(a.id || '', a.title || '');
    });
    lpBridge.on('pipeline_changed', function (json) {
      var p = JSON.parse(json);
      if (!ownsPayload(p)) return;      // stale: belongs to another lecture
      if (p.log) LP.data.pipeline.log = p.log;
      LP.data.pipeline.title = p.title || LP.data.pipeline.title;
      LP.data.pipeline.meta = p.meta || LP.data.pipeline.meta;
      LP.data.pipeline.stages = p.stages || LP.data.pipeline.stages;
      renderPipeline();
    });
    lpBridge.on('log_line', function (json) {
      if (!LP.state.jobId) return;      // no lecture owns this log yet
      LP.data.pipeline.log.push(JSON.parse(json));
      if (LP.data.pipeline.log.length > 500) LP.data.pipeline.log.shift();
      schedulePipelineRender();   // was renderPipeline() per line -- see the comment there
    });
    lpBridge.on('status_changed', function (json) {
      var s = JSON.parse(json);
      if (s.label !== undefined) $('status-label').textContent = s.label;
      if (s.pct !== undefined) setFill('status-bar', s.pct);
      if (s.detail !== undefined) $('status-pct').textContent = s.detail;
      if (s.right !== undefined) $('status-right').textContent = s.right;
      if (s.job !== undefined && LP.state.jobId) {
        $('side-job-name').textContent = s.job; $('crumb-job').textContent = s.job;
      }
      if (s.side !== undefined) $('side-job-status').innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:var(--orange);animation:lpblink 1s infinite"></span>' + esc(s.side);
    });
    lpBridge.on('slides_changed', function (json) {
      var d = JSON.parse(json);
      if (!ownsPayload(d)) return;
      LP.data.slides = d.slides || LP.data.slides;
      if (d.duration) LP.data.duration = d.duration;
      if (d.durationMid) LP.data.durationMid = d.durationMid;
      if (LP.state.viewingSlide >= LP.data.slides.length) LP.state.viewingSlide = 0;
      hideScrub();  // job changed — drop any stale hover preview
      renderSlides();
      updateExportPdfDescription();
    });
    lpBridge.on('transcript_changed', function (json) {
      var d = JSON.parse(json);
      if (!ownsPayload(d)) return;
      if (d.reviewSegments) { LP.data.reviewSegments = d.reviewSegments; renderReviewTranscript(); }
      if (d.transcript) { LP.data.transcript = d.transcript; renderTranscript(); }
    });
    lpBridge.on('study_changed', function (json) {
      var sd = JSON.parse(json);
      if (!ownsPayload(sd)) return;
      LP.data.study = sd; renderStudy();
      var na = $('notes-area');
      if (na && document.activeElement !== na) na.value = LP.data.study.notes || '';
    });
    lpBridge.on('quiz_changed', function (json) {
      var d = JSON.parse(json), q = LP.state.quiz;
      if (!ownsPayload(d)) return;
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
      if (!ownsPayload(d)) return;
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
      setFill('export-progress-bar', p.pct || 0);
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
      if (d.backend && LP.ui) LP.ui.reflectBackend(d.backend);
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
      var s = JSON.parse(json);
      var lbl = s.label || 'Built-in Study';
      var builtin = lbl === 'Built-in Study';
      var err = lbl === 'AI error';
      var txt = lbl + (s.model && s.model !== '—' && !builtin ? ' · ' + s.model : '');
      var col = builtin ? 'var(--secondary-text)' : (err ? 'var(--muted)' : 'var(--green)');
      $('ai-status').style.color = col; $('ai-status').style.borderColor = col;
      $('ai-status').innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:' + col + '"></span>' + esc(txt);
      if (s.model) setModelValue(s.model);
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
      if (s.theme) applyTheme(s.theme, false);
      if (s.version) { LP.data.version = s.version; $('app-version').textContent = s.version; }
      if (s.model_path) $('setting-model-path').textContent = s.model_path;
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
      function startNormalBridgeActivity() {
        if (backend && backend.list_ollama_models) lpBridge.call('list_ollama_models');
        // Ask whether link import exists in this build; the button stays hidden
        // until the backend says yes.
        if (backend && backend.media_link_support) lpBridge.call('media_link_support');
      }
      if (backend && backend.get_bootstrap) {
        lpBridge.call('get_bootstrap').then(function (json) {
          if (!json) { startNormalBridgeActivity(); return; }
          try {
            var b = JSON.parse(json);
            if (b.theme) applyTheme(b.theme, false);
            if (b.version) { LP.data.version = b.version; $('app-version').textContent = b.version; }
            RuntimeSetupGate.admit(b);
            if (b.runtime_health_state !== 'SETUP_REQUIRED') {
              startNormalBridgeActivity();
            }
          } catch (e) { console.error('bootstrap parse', e); }
        });
      } else startNormalBridgeActivity();
    });
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
    }
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
    applyTheme('light', false);
    setStudyTab('chat');
    RuntimeSetupGate.wire();
    RuntimeSetupGate.beginBootstrap();
    wire();
    wireGuidedTour();
    wireModelTooltip();
    wireBridge();
    window.addEventListener('resize', function () { LP.motion.indicator(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
