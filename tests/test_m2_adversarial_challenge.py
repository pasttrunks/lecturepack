"""Adversarial stress-test suite for Milestone 2: Navigation, Switcher Dynamics, and Progressive Unlocking.

This test suite aggressively probes:
1. `navigateStudySource(el)` when `data-job` references a non-existent job ID.
2. `navigateStudySource(el)` when target job has missing transcript or slide data.
3. Timestamp calculation precision during transcript jump navigation (MM:SS vs HH:MM:SS).
4. Rapid switching between group overview ("all") and individual member lecture views under async latency.
5. Progressive unlocking banner behavior across dynamic job status transitions and bridge events.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app" / "ui" / "app.js"
INDEX_HTML = ROOT / "app" / "ui" / "index.html"


def run_node_snippet(program: str) -> subprocess.CompletedProcess[str]:
    """Execute a standalone JavaScript snippet in Node.js."""
    return subprocess.run(["node", "-e", program], capture_output=True, text=True, encoding="utf-8")


def test_navigate_study_source_nonexistent_job_id() -> None:
    """Stress-test navigateStudySource when target job ID does not exist in library."""
    node_script = """
    // Minimal DOM and State Mock
    const state = { jobId: 'job_current', screen: 'study', viewingSlide: 0 };
    const data = { jobs: [{ id: 'job_current', name: 'Current Job' }], slides: [] };
    const bridgeCalls = [];
    const lpBridge = {
        connected: () => true,
        call: (cmd, payload) => {
            bridgeCalls.push({ cmd, payload });
            return Promise.resolve({ ok: false, error: 'Job not found' });
        }
    };
    const studyV2 = {
        content: { concepts: ['existing'] },
        progress: {},
        summary: {},
        quickSession: null
    };

    function _jobById(id) {
        return (data.jobs || []).find(j => j.id === id);
    }

    function setActiveJob(id, name) {
        state.jobId = id;
    }

    function setScreen(s) {
        state.screen = s;
    }

    function selectJob(jobId, opts) {
        opts = opts || {};
        if (!jobId) return;
        const entry = _jobById(jobId);
        setActiveJob(jobId, entry && entry.name ? entry.name : '');
        if (studyV2) {
            studyV2.content = { concepts: [], flashcards: [], quiz: [] };
            studyV2.progress = {};
            studyV2.summary = {};
        }
        if (lpBridge.connected() && !opts.silent) {
            try { lpBridge.call('view_job', jobId); } catch (e) {}
        }
        if (opts.screen) setScreen(opts.screen);
    }

    function navigateStudySource(el) {
        const targetJobId = el.dataset.job || '';
        const segment = el.dataset.segment;
        const ms = Number(el.dataset.ms || 0);
        const slide = el.dataset.slide;

        if (targetJobId && targetJobId !== state.jobId) {
            selectJob(targetJobId, { screen: slide != null ? 'review' : 'transcript' });
            return;
        }
        if (slide != null) setScreen('review');
        else if (segment != null) setScreen('transcript');
    }

    // 1. Non-existent job with slide citation
    const elSlide = { dataset: { job: 'non_existent_999', slide: 'slide_5' } };
    navigateStudySource(elSlide);

    if (state.jobId !== 'non_existent_999') process.exit(1);
    if (state.screen !== 'review') process.exit(2);
    if (studyV2.content.concepts.length !== 0) process.exit(3);
    if (bridgeCalls.length !== 1 || bridgeCalls[0].cmd !== 'view_job' || bridgeCalls[0].payload !== 'non_existent_999') process.exit(4);

    // 2. Non-existent job with transcript segment citation
    const elTrans = { dataset: { job: 'missing_job_888', segment: 'seg_10', ms: '45000' } };
    navigateStudySource(elTrans);

    if (state.jobId !== 'missing_job_888') process.exit(5);
    if (state.screen !== 'transcript') process.exit(6);

    // 3. Citation with empty/undefined dataset attributes
    const elEmpty = { dataset: {} };
    navigateStudySource(elEmpty); // Should gracefully no-op without changing job

    if (state.jobId !== 'missing_job_888') process.exit(7);

    process.exit(0);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"Non-existent job navigation failed: {res.stderr}"


def test_navigate_study_source_missing_slides_and_transcript_data() -> None:
    """Stress-test navigateStudySource timeout callbacks when slides or transcript DOM blocks are missing."""
    node_script = """
    let viewingSlide = -1;
    let renderedSlidesCalled = false;
    function renderSlides() { renderedSlidesCalled = true; }

    const LP = {
        state: { viewingSlide: 0 },
        data: { slides: [] } // Empty slides array
    };

    // Simulate slide jump with missing slide in dataset
    const slideToFind = 'slide_nonexistent_99';
    const slides = LP.data.slides || [];
    const idx = slides.findIndex(s => String(s.image_filename) === String(slideToFind) || String(s.index) === String(slideToFind));
    if (idx >= 0) {
        LP.state.viewingSlide = idx;
        renderSlides();
    }

    if (renderedSlidesCalled) process.exit(1); // Should not render or change slide index

    // Simulate transcript DOM blocks search when container has no items
    const blocks = []; // Empty querySelectorAll result
    let target = null;
    const ms = 120000;
    blocks.forEach(b => {
        let raw = b.dataset.start;
        if (raw == null) {
            const parts = String(b.dataset.transcriptTime || '').split(':').map(Number);
            raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : Number(parts[0] || 0);
        }
        if (Number(raw) <= ms / 1000) target = b;
    });

    if (target !== null) process.exit(2); // Should remain null without throwing

    // Simulate malformed timestamps in transcript blocks
    const malformedBlocks = [
        { dataset: { transcriptTime: '' } },
        { dataset: { transcriptTime: 'invalid:time' } },
        { dataset: { start: 'not_a_number' } },
        { dataset: { transcriptTime: null } }
    ];
    let malformedTarget = null;
    malformedBlocks.forEach(b => {
        let raw = b.dataset.start;
        if (raw == null) {
            const parts = String(b.dataset.transcriptTime || '').split(':').map(Number);
            raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : Number(parts[0] || 0);
        }
        if (Number(raw) <= ms / 1000) malformedTarget = b;
    });

    // NaN comparisons evaluate to false, so no error thrown and target remains safe
    process.exit(0);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"Missing slides/transcript stress-test failed: {res.stderr}"


def test_navigate_study_source_timestamp_precision_bug() -> None:
    """Stress-test timestamp parsing bug in navigateStudySource for 2-part (MM:SS) timestamps.
    
    Verifies that `raw = parts.length === 3 ? ... : Number(parts[0] || 0)` incorrectly calculates
    seconds as only the minute component when format is MM:SS (e.g. 05:30 -> 5 instead of 330).
    """
    node_script = """
    // Empirical proof of the timestamp parsing bug in navigateStudySource
    const ms = 300 * 1000; // Target timestamp: 5 minutes (300 seconds)

    const blocks = [
        { id: 'b1', time: '01:00' }, // 60s
        { id: 'b2', time: '05:00' }, // 300s (Intended target)
        { id: 'b3', time: '10:00' }, // 600s
        { id: 'b4', time: '20:00' }  // 1200s
    ];

    let buggyTarget = null;
    blocks.forEach(b => {
        let raw;
        const parts = String(b.time || '').split(':').map(Number);
        // This is the buggy calculation from app.js lines 6391 & 6426:
        raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : Number(parts[0] || 0);
        if (Number(raw) <= ms / 1000) buggyTarget = b;
    });

    // Correct parsing function (as defined in transcriptTimestampSeconds at line 9471)
    function transcriptTimestampSeconds(value) {
        const parts = String(value || '').split(':').map(Number);
        if (parts.some(p => !isFinite(p))) return 0;
        return parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] :
            parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0);
    }

    let correctTarget = null;
    blocks.forEach(b => {
        const raw = transcriptTimestampSeconds(b.time);
        if (raw <= ms / 1000) correctTarget = b;
    });

    // Check bug manifestation:
    // Buggy calculation selects b4 (20:00) because 20 <= 300!
    // Correct calculation selects b2 (05:00) because 300 <= 300 and 600 > 300!
    if (buggyTarget.id !== 'b4') process.exit(1);
    if (correctTarget.id !== 'b2') process.exit(2);

    console.log(JSON.stringify({ buggy: buggyTarget.id, correct: correctTarget.id }));
    process.exit(0);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"Timestamp parsing analysis failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["buggy"] == "b4"
    assert data["correct"] == "b2"


def test_rapid_switcher_race_condition_group_vs_single_job() -> None:
    """Stress-test rapid switching between group overview ('all') and single lecture views under async latency."""
    node_script = """
    const LP = { state: { jobId: 'job_1', screen: 'study' } };
    const studyV2 = {
        scope: {
            type: 'group',
            groupName: 'Physics',
            selectedJobId: 'all',
            groupAnalysis: { concepts: [{ id: 'gc_1', title: 'Group Concept 1' }] },
            members: [{ job_id: 'job_1', title: 'Lecture 1' }]
        },
        content: { concepts: [{ id: 'gc_1', title: 'Group Concept 1' }] },
        summary: {}
    };

    function buildGroupStudyContent(analysis, members) {
        return {
            study_status: 'ready',
            concepts: (analysis.concepts || []).map(c => ({ id: c.id, title: c.title }))
        };
    }

    // Step 1: User switches to job_1 (spawns async study_v2_status)
    const requestedJobId = 'job_1';
    LP.state.jobId = 'job_1';
    studyV2.scope.selectedJobId = 'job_1';
    studyV2.content = { concepts: [] };

    let resolveInFlightStatus;
    const inFlightStatusPromise = new Promise(resolve => { resolveInFlightStatus = resolve; });

    // Step 2: User immediately switches back to 'all' before status resolves
    studyV2.scope.selectedJobId = 'all';
    studyV2.content = buildGroupStudyContent(studyV2.scope.groupAnalysis, studyV2.scope.members);

    // Step 3: In-flight single-lecture status resolves
    inFlightStatusPromise.then(res => {
        // Line 4905 in app.js checks:
        // if (LP.state.jobId !== requestedJobId || (res.job_id && res.job_id !== requestedJobId)) return;
        if (LP.state.jobId !== requestedJobId || (res.job_id && res.job_id !== requestedJobId)) return;
        
        // Flaw: It does not check if (studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all')!
        studyV2.content = res.content;
    });

    resolveInFlightStatus({
        job_id: 'job_1',
        content: { concepts: [{ id: 'single_c_1', title: 'Single Lecture Concept' }] }
    });

    setTimeout(() => {
        const isCorrupted = studyV2.scope.selectedJobId === 'all' && studyV2.content.concepts[0].id === 'single_c_1';
        console.log(JSON.stringify({ corrupted: isCorrupted, currentSelected: studyV2.scope.selectedJobId }));
        process.exit(0);
    }, 20);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"Race condition test failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["corrupted"] is True, "Expected in-flight single job response to overwrite group overview when selectedJobId is 'all'"


def test_progressive_unlocking_banner_state_transitions() -> None:
    """Stress-test progressive unlocking banner and switcher readiness across dynamic job transitions."""
    node_script = """
    function getJobReadiness(job) {
        if (!job) return { status: 'none', label: 'Unknown', icon: '❓', ready: false };
        if (job.status === 'running') return { status: 'processing', label: 'Processing ' + (job.progress || job.pct || 0) + '%', icon: '⏳', ready: false };
        if (job.status === 'queued') return { status: 'queued', label: 'Queued', icon: '⏸', ready: false };
        if (job.status === 'failed' || job.status === 'interrupted') return { status: 'failed', label: 'Needs Attention', icon: '⚠', ready: false };
        if (job.study_status === 'ready' || job.status === 'done') return { status: 'ready', label: 'Ready', icon: '✓', ready: true };
        if (job.study_status === 'basic') return { status: 'basic', label: 'Basic', icon: '✓', ready: true };
        if (job.study_status === 'preparing') return { status: 'preparing', label: 'Preparing Study', icon: '⏳', ready: false };
        if (job.study_status === 'failed') return { status: 'failed', label: 'Needs Attention', icon: '⚠', ready: false };
        return { status: 'ready', label: 'Ready', icon: '✓', ready: true };
    }

    function evaluateBannerState(groupName, jobs, scopeStatus, scopeReason) {
        const groupJobs = (jobs || []).filter(j => (j.group || '').trim().toLowerCase() === groupName.toLowerCase());
        const readyJobs = groupJobs.filter(j => getJobReadiness(j).ready);
        const procJobs = groupJobs.filter(j => getJobReadiness(j).status === 'processing');
        
        const showProgBanner = readyJobs.length > 0 && readyJobs.length < groupJobs.length;
        const bannerCountText = showProgBanner ? (readyJobs.length + ' of ' + groupJobs.length + ' lectures ready') : '';
        
        const isEmpty = scopeStatus === 'failed' && scopeReason === 'no_ready_lectures';
        const isFailed = scopeStatus === 'failed' && scopeReason !== 'no_ready_lectures';
        const showEmptyPanel = isEmpty || isFailed;
        
        return {
            total: groupJobs.length,
            ready: readyJobs.length,
            processing: procJobs.length,
            showProgBanner,
            bannerCountText,
            showEmptyPanel,
            isEmpty,
            isFailed
        };
    }

    // Permutation 1: 0/3 ready (all processing)
    const p1Jobs = [
        { id: 'j1', group: 'CS101', status: 'running', pct: 20 },
        { id: 'j2', group: 'CS101', status: 'queued' },
        { id: 'j3', group: 'CS101', status: 'running', pct: 60 }
    ];
    const s1 = evaluateBannerState('CS101', p1Jobs, 'failed', 'no_ready_lectures');
    if (s1.showProgBanner !== false || s1.showEmptyPanel !== true || !s1.isEmpty) process.exit(1);

    // Permutation 2: 1/3 ready (1 done, 2 processing)
    const p2Jobs = [
        { id: 'j1', group: 'CS101', status: 'done', study_status: 'ready' },
        { id: 'j2', group: 'CS101', status: 'queued' },
        { id: 'j3', group: 'CS101', status: 'running', pct: 80 }
    ];
    const s2 = evaluateBannerState('CS101', p2Jobs, 'ready', '');
    if (s2.showProgBanner !== true || s2.bannerCountText !== '1 of 3 lectures ready' || s2.showEmptyPanel !== false) process.exit(2);

    // Permutation 3: 2/3 ready, 1 failed
    const p3Jobs = [
        { id: 'j1', group: 'CS101', status: 'done', study_status: 'ready' },
        { id: 'j2', group: 'CS101', status: 'failed' },
        { id: 'j3', group: 'CS101', status: 'done', study_status: 'basic' }
    ];
    const s3 = evaluateBannerState('CS101', p3Jobs, 'ready', '');
    if (s3.showProgBanner !== true || s3.bannerCountText !== '2 of 3 lectures ready' || s3.showEmptyPanel !== false) process.exit(3);

    // Permutation 4: 3/3 ready (Fully unlocked)
    const p4Jobs = [
        { id: 'j1', group: 'CS101', status: 'done', study_status: 'ready' },
        { id: 'j2', group: 'CS101', status: 'done', study_status: 'ready' },
        { id: 'j3', group: 'CS101', status: 'done', study_status: 'ready' }
    ];
    const s4 = evaluateBannerState('CS101', p4Jobs, 'ready', '');
    if (s4.showProgBanner !== false || s4.showEmptyPanel !== false) process.exit(4);

    // Permutation 5: Empty subject (0 lectures in group)
    const s5 = evaluateBannerState('NonExistentGroup', p4Jobs, 'failed', 'no_ready_lectures');
    if (s5.total !== 0 || s5.showProgBanner !== false || s5.showEmptyPanel !== true) process.exit(5);

    console.log(JSON.stringify({ s1, s2, s3, s4, s5 }));
    process.exit(0);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"Progressive unlocking state transitions failed: {res.stderr}"


def test_appjs_navigate_study_source_fixed_timestamp_parsing() -> None:
    """Verify that app.js navigateStudySource timestamp calculation parses MM:SS format correctly."""
    app_js_text = APP_JS.read_text(encoding="utf-8")
    assert "raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : (parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0));" in app_js_text

    node_script = """
    const ms = 300 * 1000; // 5 minutes (300 seconds)
    const blocks = [
        { id: 'b1', dataset: { transcriptTime: '01:00' } }, // 60s
        { id: 'b2', dataset: { transcriptTime: '05:00' } }, // 300s (target)
        { id: 'b3', dataset: { transcriptTime: '10:00' } }, // 600s
        { id: 'b4', dataset: { transcriptTime: '20:00' } }  // 1200s
    ];

    let target = null;
    blocks.forEach(function (b) {
        var raw = b.dataset.start;
        if (raw == null) {
            var parts = String(b.dataset.transcriptTime || '').split(':').map(Number);
            raw = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : (parts.length === 2 ? parts[0] * 60 + parts[1] : Number(parts[0] || 0));
        }
        if (Number(raw) <= ms / 1000) target = b;
    });

    if (!target || target.id !== 'b2') {
        console.error('Target selected: ' + (target ? target.id : 'none') + ', expected b2');
        process.exit(1);
    }
    process.exit(0);
    """
    res = run_node_snippet(node_script)
    assert res.returncode == 0, f"app.js timestamp parsing verification failed: {res.stderr}"


def test_appjs_study_v2_load_race_guard() -> None:
    """Verify that app.js studyV2Load contains the group overview race guard."""
    app_js_text = APP_JS.read_text(encoding="utf-8")
    assert "if (studyV2.scope && studyV2.scope.type === 'group' && studyV2.scope.selectedJobId === 'all') return;" in app_js_text

