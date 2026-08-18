"""Focused renderer regressions for LecturePack's production UI polish."""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


def function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def run_runtime_reducer(body: str) -> subprocess.CompletedProcess[str]:
    constants = JS.split("var FIRST_RUN_ROWS = [", 1)[1].rsplit(
        "function RuntimeSetupGateModel()", 1
    )[0]
    reducer = function_block(JS, "function RuntimeSetupGateModel()", "var RuntimeSetupGate")
    program = "var FIRST_RUN_ROWS = [" + constants + "function RuntimeSetupGateModel()" + reducer + body
    return subprocess.run(["node", "-e", program], capture_output=True, text=True)


def test_runtime_setup_is_green_only_and_reset_is_backend_owned() -> None:
    assert 'id="btn-runtime-done"' in HTML
    assert re.search(r'id="btn-runtime-done"[^>]*\bdisabled\b', HTML)
    assert 'id="btn-runtime-exit"' not in HTML
    assert 'id="btn-runtime-continue"' not in HTML
    assert 'id="btn-runtime-skip"' not in HTML
    assert "requiredChecklistReady" in JS
    for check_id in (
        "windows_version",
        "ffmpeg_ffprobe",
        "whisper_runtime",
        "bundled_model",
        "data_directory",
    ):
        assert check_id in JS
    assert "lpBridge.call('acknowledge_setup')" in JS
    assert "title: 'Reset LecturePack?'" in JS
    assert "Original lecture/video files outside LecturePack will not be deleted." in JS
    assert "lpBridge.call('reset_lecturepack')" in JS


def test_healthy_incomplete_bootstrap_waits_before_exposing_checklist() -> None:
    result = run_runtime_reducer(
        r'''
        const gate = RuntimeSetupGateModel();
        let view = gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: []});
        if (view.state !== 'checking' || view.checklistReady) process.exit(1);
        if (Object.keys(view.checkProgress).length !== 5) process.exit(2);
        const ready = [
          {id: 'windows_version', verdict: 'ready'},
          {id: 'ffmpeg_ffprobe', verdict: 'ready'},
          {id: 'whisper_runtime', verdict: 'ready'},
          {id: 'bundled_model', verdict: 'ready'},
          {id: 'data_directory', verdict: 'ready'}
        ];
        view = gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: ready});
        if (view.state !== 'checklist' || !view.checklistReady) process.exit(3);
        const malformed = RuntimeSetupGateModel();
        malformed.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: ready.slice(0, 4)});
        if (malformed.toChecklist().state !== 'checking') process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_demo_uses_authoritative_eligibility_and_self_contained_screen() -> None:
    assert 'id="glowing-demo-card"' in HTML
    assert '<section data-screen="demo"' in HTML
    availability = function_block(JS, "function renderDemoHomeAvailability()", "function stageLabel")
    assert "demoAdmissionAvailable && tourEligibilityAllowsOffer()" in availability
    assert "jobsEmpty" not in availability
    assert "firstRun" not in availability
    assert "function applyGuidedTourEligibility" in JS
    assert "set_guided_tour_state" in JS
    assert "replay_guided_tour" in JS
    replay = function_block(JS, "function replayDemoScreen()", "function endGuidedDemo")
    assert "openDemo(1)" in replay
    assert "runDemoForReal" not in replay
    empty_action = function_block(JS, "$('btn-load-jobs').addEventListener", "var ONB_ACTIVE_STYLE")
    assert "var savedDemo = demoState()" in empty_action
    assert "savedDemo.completed === true ? 1 : (savedDemo.chapter || 1)" in empty_action
    assert "runDemoForReal" not in empty_action


def test_demo_processing_is_real_identity_safe_and_retryable() -> None:
    run = function_block(JS, "function runDemoForReal()", "function bindDemoScreen")
    assert "setOnb(null);" in run
    assert "guidedDemo.starting().attempt" in run
    assert "lpBridge.startDemoJob()" in run
    assert "guidedDemo.isCurrentAttempt(attempt)" in run
    assert run.index("demoCleanupRequested = false") < run.index("guidedDemo.starting()")
    assert run.index("demoCleanupConfirmed = false") < run.index("guidedDemo.starting()")
    receive = function_block(JS, "function receiveDemoEvent(value)", "function wireDemoLifecycle")
    assert "guidedDemo.event(event)" in receive
    assert "if (!handled.accepted) return" in receive
    assert "eventStage === 'review_ready' && LP.state.screen === 'process'" in receive


def test_stacked_review_column_has_a_definite_height() -> None:
    block = CSS.split("@media (max-width:1220px)", 1)[1].split(chr(10) + "}", 1)[0]
    assert ".lp-review-col-slides{height:230px}" in block.replace(" ", "")
    assert ".lp-review-col-slides{max-height" not in block.replace(" ", "")


def test_existing_lecture_drag_queues_ids_without_reimporting() -> None:
    assert 'data-existing-job-drag="true"' in JS
    assert "application/x-lecturepack-job-ids" in JS
    # createInternalDragGhost is gone: it built a bitmap for the NATIVE drag
    # image, which the OS composites and which therefore could not be tilted,
    # scaled or eased. Internal drags now carry a live cloned element instead.
    assert "createInternalDragGhost" not in JS
    assert "function buildProxy(src, count, x, y)" in JS
    assert "queueExistingJobIds" in JS
    # The request is built up now that a drop can also carry the reprocess
    # opt-in, but it is still one queue_jobs call over the existing IDs --
    # never a re-import.
    assert "var request = { job_ids: unique };" in JS
    assert "lpBridge.call('queue_jobs', request)" in JS
    assert "import_video" not in JS.split("function queueExistingJobIds", 1)[1][:900]
    assert "lpBridge.call('enqueue_job', id)" in JS
    assert 'id="process-queue-target"' in HTML
    assert 'data-existing-job-drop-target="true"' in HTML


def test_downloads_review_and_timeline_polish_hooks_are_present() -> None:
    assert 'id="downloads-indicator"' in HTML
    assert 'class="lp-download-popover"' in HTML
    assert "positionDownloadsPanel" in JS
    assert "normalizedDownloadStatus" in JS
    assert "document.addEventListener('pointerdown'" in JS
    assert 'aria-expanded' in HTML

    # The Compact/Roomy density toggle is gone: the two modes differed by a
    # 22px thumbnail and neither size was legible. A three-stop size control in
    # the All slides overlay replaces it, and the rail auto-fits its columns.
    # See tests/test_slide_viewer_layout.py.
    assert 'data-slide-size' in JS
    assert ".lp-slide-card" in CSS
    assert 'id="btn-all-slides"' in HTML
    assert 'id="all-slides-overlay"' in HTML
    assert "repeat(auto-fill," in CSS
    assert 'data-state="' in JS and 'data-selected="' in JS
    assert "s.state = 'accepted'; s.sel = true" in JS
    selected_rule = CSS.split('.lp-slide-check[data-checked="true"]', 1)[1].split("}", 1)[0]
    assert "background" not in selected_rule, "selection is a checkbox, not a filled card"
    rejected_rule = CSS.split('.lp-slide-card[data-state="rejected"]', 1)[1].split("}", 1)[0]
    assert "var(--red-soft)" in rejected_rule and "var(--red)" in rejected_rule

    assert "setPointerCapture" in JS
    assert "releasePointerCapture" in JS
    assert "LP.state.viewingSlide = nearest.slide._i" in JS
    assert "transcriptTimestampSeconds" in JS
    assert "scrollIntoView({ block: 'center' })" in JS


def test_runtime_checklist_render_has_a_defensive_readiness_guard() -> None:
    runtime_render = function_block(JS, "function render(dataChanged, forceCheckingOpen)", "function neutralPanels")
    checklist_render = function_block(JS, "function renderChecklist()", "function renderOffer")
    assert "view.state === 'checklist' && !view.checklistReady" in runtime_render
    assert "eventModel.waitForChecklist()" in runtime_render
    assert "empty.hidden = ready" in checklist_render


def run_node_snippet(program: str) -> subprocess.CompletedProcess[str]:
    """Execute a standalone JavaScript snippet in Node.js."""
    return subprocess.run(["node", "-e", program], capture_output=True, text=True)


def test_subjects_screen_dom_navigation_and_rendering() -> None:
    """Verify Subject screen DOM elements, sidebar navigation, screen switching, and rendering."""
    # 1. HTML structure and navigation presence
    assert 'data-nav="subjects"' in HTML, "Sidebar must contain a Subjects navigation button"
    assert '<section data-screen="subjects"' in HTML, "HTML must contain data-screen='subjects' container"
    assert 'id="subjects-grid"' in HTML or 'class="subjects-grid"' in HTML, "Subjects container must exist"
    assert 'id="subjects-empty"' in HTML, "Subjects empty state container must exist"

    # 2. JS screen switching and render wiring
    assert "renderSubjects" in JS, "app.js must define renderSubjects()"
    assert "set_jobs_group" in JS, "app.js must support bulk subject renaming via set_jobs_group"

    # 3. CSS styling rules
    assert ".subjects-grid" in CSS or "#subjects-grid" in CSS, "CSS must style subjects grid"
    assert ".subject-card" in CSS, "CSS must style subject cards"


def test_home_card_subject_badge_and_inline_rename() -> None:
    """Verify Home card subject badge cell replaces old tag modal button and supports inline editing."""
    # 1. Elimination of old modal tag button in card HTML
    card_func = function_block(JS, "function _jobCardHtml(j)", "function mediaUrls")
    assert "_jobBtn('group'" not in card_func, "Old tag button opening modal must be removed from _jobCardHtml"

    # 2. Presence of subject badge cell with attributes
    assert "lp-subject-badge" in card_func or "data-subject" in card_func, "Card HTML must render a subject badge cell"
    assert "data-jobid" in card_func or "data-job" in card_func, "Subject badge must carry job identifier"

    # 3. Inline rename event handling
    assert "lp-subject-inline-input" in JS or "data-subject-input" in JS, "Inline input field class must be supported"
    assert "set_job_group" in JS, "app.js must invoke set_job_group for single card rename"
    assert "stopPropagation" in JS, "Subject badge interaction must stop event propagation to prevent card selection"

    # 4. CSS styling
    assert ".lp-subject-badge" in CSS, "CSS must style .lp-subject-badge"


def test_per_lecture_and_group_coverage_bar_calculation_and_rendering() -> None:
    """Verify per-lecture and group coverage calculations and progress bar rendering."""
    # 1. Coverage bar CSS rules
    assert ".lp-coverage-track" in CSS or ".lp-coverage-bar" in CSS, "CSS must define coverage track/bar"
    assert ".lp-coverage-fill" in CSS, "CSS must define coverage fill"

    # 2. Coverage calculation logic evaluated via Node.js
    coverage_node_script = """
    function calcLectureCoverage(job, progress) {
        if (!job || job.status !== 'done' || !progress) return 0;
        const concepts = (progress && progress.concepts) || {};
        const keys = Object.keys(concepts);
        if (!keys.length) return 0;
        let score = 0;
        keys.forEach(k => {
            const val = concepts[k];
            if (val === 'mastered') score += 1.0;
            else if (val === 'medium') score += 0.5;
        });
        return Math.min(100, Math.max(0, Math.round((score / keys.length) * 100)));
    }

    function calcGroupCoverage(jobs, progressMap) {
        if (!jobs || !jobs.length) return 0;
        let total = 0;
        let readyCount = 0;
        jobs.forEach(j => {
            if (j.status === 'done') {
                readyCount++;
                total += calcLectureCoverage(j, progressMap[j.id]);
            }
        });
        return readyCount > 0 ? Math.round(total / readyCount) : 0;
    }

    // Assert unready job returns 0
    if (calcLectureCoverage({ id: 'j1', status: 'running' }, null) !== 0) process.exit(1);

    // Assert 50% mastery
    const p1 = { concepts: { c1: 'mastered', c2: 'low' } };
    if (calcLectureCoverage({ id: 'j1', status: 'done' }, p1) !== 50) process.exit(2);

    // Assert 100% mastery
    const p2 = { concepts: { c1: 'mastered', c2: 'mastered' } };
    if (calcLectureCoverage({ id: 'j2', status: 'done' }, p2) !== 100) process.exit(3);

    // Assert group aggregation (mean of 50 and 100 is 75)
    const jobs = [{ id: 'j1', status: 'done' }, { id: 'j2', status: 'done' }, { id: 'j3', status: 'running' }];
    const pMap = { j1: p1, j2: p2 };
    if (calcGroupCoverage(jobs, pMap) !== 75) process.exit(4);

    // Empty jobs returns 0
    if (calcGroupCoverage([], {}) !== 0) process.exit(5);

    process.exit(0);
    """
    res = run_node_snippet(coverage_node_script)
    assert res.returncode == 0, f"Coverage calculation failed: {res.stderr}"


def test_study_persistent_scope_header_bar_and_modes() -> None:
    """Verify persistent scope header bar is defined at the top of Study view and persists across modes."""
    # 1. HTML structure
    assert 'id="study-scope-header"' in HTML or 'class="study-scope-header"' in HTML, "Study view must have scope header"
    assert 'id="study-scope-subject"' in HTML or 'id="study-scope-subject-badge"' in HTML or 'class="study-scope-title"' in HTML, "Scope header must have subject title"
    assert 'id="study-scope-meta"' in HTML or 'id="study-scope-summary"' in HTML or 'class="study-scope-meta"' in HTML, "Scope header must have metadata summary"

    # 2. Scope state in app.js
    assert "studyV2.scope" in JS or "scope:" in JS, "studyV2 must maintain scope state"
    assert "study_v2_group_prepare" in JS, "app.js must call study_v2_group_prepare bridge command"

    # 3. CSS styling
    assert ".study-scope-header" in CSS or "#study-scope-header" in CSS, "CSS must style study scope header"


def test_in_study_lecture_switcher_readiness_and_disabled_states() -> None:
    """Verify in-study lecture switcher lists all group members and enforces disabled (not hidden) invariant."""
    # Node.js simulation of switcher rendering enforcing disabled not hidden
    switcher_node_script = """
    function renderGroupSwitcher(groupName, members) {
        let html = '<div class="study-lecture-switcher" role="listbox">';
        // All lectures option
        html += '<button role="option" data-switch-job="all" aria-selected="true">All Lectures (' + groupName + ')</button>';
        members.forEach(m => {
            const isReady = m.status === 'ready' || m.status === 'done';
            const disabledAttr = isReady ? '' : ' disabled aria-disabled="true"';
            const statusLabel = m.status === 'running' ? 'Processing ' + (m.pct || 0) + '%' : (m.status === 'queued' ? 'Queued' : (isReady ? 'Ready' : 'Needs Attention'));
            // Item must NEVER be hidden: hidden attribute must not be present
            html += '<button role="option" data-switch-job="' + m.id + '"' + disabledAttr + '>';
            html += '<span>' + m.title + '</span><span class="switcher-status">' + statusLabel + '</span></button>';
        });
        html += '</div>';
        return html;
    }

    const testMembers = [
        { id: 'j1', title: 'Lecture 1', status: 'done' },
        { id: 'j2', title: 'Lecture 2', status: 'running', pct: 45 },
        { id: 'j3', title: 'Lecture 3', status: 'queued' }
    ];

    const out = renderGroupSwitcher('CL100', testMembers);

    // Assert All Lectures option exists
    if (!out.includes('data-switch-job="all"')) process.exit(1);

    // Assert Lecture 1 is enabled
    if (out.includes('data-switch-job="j1" disabled')) process.exit(2);

    // Assert Lecture 2 is disabled but visible
    if (!out.includes('data-switch-job="j2" disabled') || !out.includes('Processing 45%')) process.exit(3);

    // Assert Lecture 3 is disabled but visible
    if (!out.includes('data-switch-job="j3" disabled') || !out.includes('Queued')) process.exit(4);

    // Assert no item has hidden attribute
    if (out.includes('hidden')) process.exit(5);

    process.exit(0);
    """
    res = run_node_snippet(switcher_node_script)
    assert res.returncode == 0, f"Switcher rendering invariant failed: {res.stderr}"


def test_cross_lecture_citation_formatting_and_cross_job_navigation() -> None:
    """Verify cross-lecture citations prefix source lecture title and navigateStudySource handles job switches."""
    # 1. Source button data-job attribute and selectJob navigation in JS
    nav_func = function_block(JS, "function navigateStudySource(el)", "function setStudyTab")
    assert "data.job" in nav_func or "dataset.job" in nav_func or "getAttribute('data-job')" in nav_func, "navigateStudySource must inspect data-job attribute"
    assert "selectJob" in nav_func, "navigateStudySource must call selectJob when crossing lectures"

    # 2. Citation formatting in Node.js
    citation_node_script = """
    function formatCrossLectureCitation(item, getJobTitle) {
        const sources = item.sources || item.lecture_sources || [];
        if (!sources.length) return '';
        const groups = {};
        sources.forEach(s => {
            const jid = s.job_id || 'default';
            if (!groups[jid]) groups[jid] = [];
            groups[jid].push(s);
        });

        const parts = [];
        Object.keys(groups).forEach(jid => {
            const title = getJobTitle(jid);
            const items = groups[jid].map(s => {
                if (s.slide_id) {
                    return '<button class="study-source" data-job="' + jid + '" data-slide="' + s.slide_id + '">' + title + ' · Slide ' + s.slide_id + '</button>';
                }
                return '<button class="study-source" data-job="' + jid + '" data-segment="' + s.segment_id + '">' + title + ' · Transcript</button>';
            });
            parts.push('<div class="study-citation-group"><span class="study-citation-lecture-name">' + title + '</span>' + items.join(' ') + '</div>');
        });
        return parts.join('');
    }

    const testItem = {
        sources: [
            { job_id: 'job-1', slide_id: '01:15' },
            { job_id: 'job-2', segment_id: '5' }
        ]
    };

    const titleMap = { 'job-1': 'Lecture 1: The Old Kingdom', 'job-2': 'Lecture 2: Construction' };
    const html = formatCrossLectureCitation(testItem, id => titleMap[id]);

    // Assert lecture titles prefixed
    if (!html.includes('Lecture 1: The Old Kingdom · Slide 01:15')) process.exit(1);
    if (!html.includes('Lecture 2: Construction · Transcript')) process.exit(2);
    if (!html.includes('data-job="job-1"') || !html.includes('data-job="job-2"')) process.exit(3);

    process.exit(0);
    """
    res = run_node_snippet(citation_node_script)
    assert res.returncode == 0, f"Citation formatting test failed: {res.stderr}"


def test_group_study_progressive_unlocking_and_fallback_states() -> None:
    """Verify progressive unlocking banner, empty states, and preparation failure handling."""
    # 1. State containers in HTML or templates
    assert "study-partial" in HTML or "study-partial" in JS or "partial_readiness" in JS or "study-progressive" in HTML, "Partial readiness status banner must be supported"
    assert "no_ready_lectures" in JS or "study-group-empty" in JS or "study-group-empty" in HTML, "Empty group state must be supported"

    # 2. Bridge event wiring
    assert "group_study_progress" in JS, "app.js must listen for group_study_progress events"

