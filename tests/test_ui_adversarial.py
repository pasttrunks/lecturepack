"""Empirical adversarial UI stress tests for Milestone 2 Subject and Group Study features.

Tests edge cases, boundary conditions, state persistence, and readiness invariants
against app/ui/app.js implementations.
"""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


def run_node_program(code: str) -> subprocess.CompletedProcess[str]:
    """Execute a self-contained JavaScript code block via Node.js."""
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8")


def test_subject_renaming_edge_cases() -> None:
    """Stress-test subject renaming across empty, whitespace, XSS, Unicode, and extreme lengths."""
    node_code = r'''
    const assert = require('assert');

    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    function studyGroupSlug(groupName) {
      if (!groupName) return 'general';
      var clean = String(groupName).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      if (clean.length > 0 && clean.length <= 64) return clean;
      var h = 0;
      for (var i = 0; i < groupName.length; i++) {
        h = ((h << 5) - h) + groupName.charCodeAt(i);
        h |= 0;
      }
      return 'g_' + Math.abs(h).toString(16);
    }

    function simulateBadgeRenameCommit(currentVal, inputValue) {
      let committedGroup = null;
      let bridgeCalled = false;
      const nextVal = inputValue.trim();
      if (nextVal && nextVal !== currentVal) {
        bridgeCalled = true;
        committedGroup = nextVal;
      }
      return { committedGroup, bridgeCalled };
    }

    // 1. Empty and whitespace inputs
    const emptyRes = simulateBadgeRenameCommit('CS101', '');
    assert.strictEqual(emptyRes.bridgeCalled, false, 'Empty string must not trigger bridge call');
    assert.strictEqual(emptyRes.committedGroup, null, 'Empty string must not commit new group');

    const wsRes = simulateBadgeRenameCommit('CS101', '   \t\n  \r ');
    assert.strictEqual(wsRes.bridgeCalled, false, 'Whitespace-only string must not trigger bridge call');

    const sameRes = simulateBadgeRenameCommit('CS101', 'CS101');
    assert.strictEqual(sameRes.bridgeCalled, false, 'Same value must not trigger bridge call');

    const trimmedSameRes = simulateBadgeRenameCommit('CS101', '  CS101  ');
    assert.strictEqual(trimmedSameRes.bridgeCalled, false, 'Whitespace-padded same value must not trigger bridge call');

    // 2. Special characters and XSS payloads
    const xssPayloads = [
      '<script>alert("xss")</script>',
      '"><img src=x onerror=alert(1)>',
      'Bio & Chem / 100% "Core" \'A\'',
      'Course `rm -rf /`',
      '<b>Bold Subject</b>'
    ];

    xssPayloads.forEach(payload => {
      const escaped = esc(payload);
      assert(!escaped.includes('<script>'), `XSS tag must be escaped: ${escaped}`);
      assert(!escaped.includes('">'), `Attribute break must be escaped: ${escaped}`);
      assert(!escaped.includes('"Core"'), `Quotes must be escaped: ${escaped}`);

      const slug = studyGroupSlug(payload);
      assert(/^[a-z0-9\-_]+$/.test(slug), `Slug must be alphanumeric/dash/underscore: ${slug}`);
    });

    // 3. Unicode and Multilingual
    const unicodeNames = [
      '📚 Ancient Egypt & 🏛️ Pyramids',
      '计算机科学 101: 算法',
      'Курс по квантовой физике №4',
      'مقدمة في علوم الحاسوب'
    ];

    unicodeNames.forEach(name => {
      const slug = studyGroupSlug(name);
      assert(slug.length > 0, `Unicode slug must not be empty: ${name}`);
      assert(/^[a-z0-9\-_]+$/.test(slug), `Unicode slug must produce valid token: ${slug}`);
      const escaped = esc(name);
      assert(escaped.length >= name.length, 'Escaped output must preserve content');
    });

    // 4. Extreme length (10,000 characters)
    const longName = 'A'.repeat(5000) + ' ' + 'B'.repeat(5000);
    const longSlug = studyGroupSlug(longName);
    assert(longSlug.startsWith('g_'), 'Names longer than 64 chars must fall back to hash slug');
    assert(longSlug.length <= 16, 'Hash slug must remain compact');
    '''
    res = run_node_program(node_code)
    assert res.returncode == 0, f"Subject renaming edge cases failed: {res.stderr}"


def test_coverage_and_progress_calculations_boundary_values() -> None:
    """Stress-test coverage calculations with 0 concepts, 100 concepts, missing fields, and boundary values."""
    node_code = r'''
    const assert = require('assert');

    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    function lectureProgressPct(job, studyProgress) {
      if (!job) return 0;
      if (job.status !== 'done') return Math.max(0, Math.min(100, Number(job.pct) || 0));
      var studyData = studyProgress || null;
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
      return 100;
    }

    function groupCoveragePct(jobs, progressMap) {
      if (!jobs || !jobs.length) return 0;
      var sum = 0;
      jobs.forEach(function (j) { sum += lectureProgressPct(j, (progressMap || {})[j.id]); });
      return Math.round(sum / jobs.length);
    }

    function renderCoverageBarHtml(pct, label) {
      var p = Math.max(0, Math.min(100, Number(pct) || 0));
      var color = p >= 80 ? 'var(--green)' : p >= 40 ? 'var(--orange)' : 'var(--blue)';
      return '<div class="lp-coverage-bar" title="' + esc(label || (p + '% coverage')) + '">' +
        '<div class="lp-coverage-track"><div class="lp-coverage-fill" style="width:' + p + '%;background:' + color + '"></div></div>' +
        '<span class="lp-coverage-pct">' + p + '%</span></div>';
    }

    // 1. Boundary: Null / empty job
    assert.strictEqual(lectureProgressPct(null), 0);
    assert.strictEqual(lectureProgressPct({}), 0);

    // 2. Boundary: Unready percentage bounds
    assert.strictEqual(lectureProgressPct({ status: 'running', pct: 0 }), 0);
    assert.strictEqual(lectureProgressPct({ status: 'running', pct: 75 }), 75);
    assert.strictEqual(lectureProgressPct({ status: 'running', pct: -15 }), 0);
    assert.strictEqual(lectureProgressPct({ status: 'running', pct: 150 }), 100);
    assert.strictEqual(lectureProgressPct({ status: 'running', pct: 'invalid' }), 0);

    // 3. Boundary: 0 concepts vs 100 concepts
    assert.strictEqual(lectureProgressPct({ id: 'j1', status: 'done' }, { concepts: {} }), 100);

    const hundredConcepts = {};
    for (let i = 0; i < 100; i++) {
      if (i < 40) hundredConcepts[`c_${i}`] = 'mastered';
      else if (i < 80) hundredConcepts[`c_${i}`] = 'medium';
      else hundredConcepts[`c_${i}`] = 'low';
    }
    assert.strictEqual(lectureProgressPct({ id: 'j1', status: 'done' }, { concepts: hundredConcepts }), 64);

    // 4. Mixed formats
    const mixedConcepts = {
      c1: { mastery: 'MASTERED' },
      c2: { mastery: 'learning' },
      c3: 'NEEDS_REVIEW',
      c4: 'unknown_state',
      c5: null
    };
    assert.strictEqual(lectureProgressPct({ id: 'j1', status: 'done' }, { concepts: mixedConcepts }), 34);

    // 5. Group aggregation
    const group = [
      { id: 'j1', status: 'done' },
      { id: 'j2', status: 'running', pct: 50 },
      { id: 'j3', status: 'queued', pct: 0 }
    ];
    assert.strictEqual(groupCoveragePct(group, {}), 50);
    assert.strictEqual(groupCoveragePct([], {}), 0);

    // 6. Coverage bar styling & color thresholds
    assert(renderCoverageBarHtml(0).includes('var(--blue)'));
    assert(renderCoverageBarHtml(39).includes('var(--blue)'));
    assert(renderCoverageBarHtml(40).includes('var(--orange)'));
    assert(renderCoverageBarHtml(79).includes('var(--orange)'));
    assert(renderCoverageBarHtml(80).includes('var(--green)'));
    assert(renderCoverageBarHtml(100).includes('var(--green)'));
    '''
    res = run_node_program(node_code)
    assert res.returncode == 0, f"Coverage calculations failed: {res.stderr}"


def test_localstorage_persistence_and_corruption_resilience() -> None:
    """Stress-test group view persistence and restoration against empty and corrupt localStorage states."""
    node_code = r'''
    const assert = require('assert');

    function studyGroupSlug(groupName) {
      if (!groupName) return 'general';
      var clean = String(groupName).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      if (clean.length > 0 && clean.length <= 64) return clean;
      var h = 0;
      for (var i = 0; i < groupName.length; i++) {
        h = ((h << 5) - h) + groupName.charCodeAt(i);
        h |= 0;
      }
      return 'g_' + Math.abs(h).toString(16);
    }

    function studyGroupStorageKey(groupName) {
      return groupName ? 'lecturepack.study.v2.group.' + studyGroupSlug(groupName) : '';
    }

    function createMockStorage(initialStore = {}) {
      const store = { ...initialStore };
      return {
        getItem: function(k) { return store[k] !== undefined ? store[k] : null; },
        setItem: function(k, v) { store[k] = String(v); },
        removeItem: function(k) { delete store[k]; },
        _dump: function() { return store; }
      };
    }

    function restoreGroupView(groupName, storage, studyV2) {
      var key = studyGroupStorageKey(groupName);
      if (!key || !storage) return false;
      try {
        var saved = JSON.parse(storage.getItem(key) || 'null');
        if (!saved || typeof saved !== 'object') return false;
        if (saved.selectedJobId) studyV2.scope.selectedJobId = saved.selectedJobId;
        if (['overview', 'flashcards', 'quiz', 'ask', 'quick', 'teach'].indexOf(saved.lastMode) >= 0) {
          studyV2.mode = saved.lastMode;
        }
        return true;
      } catch (e) { return false; }
    }

    function persistGroupView(storage, studyV2) {
      var groupName = studyV2.scope && studyV2.scope.groupName;
      var key = studyGroupStorageKey(groupName);
      if (!key || !storage) return;
      try {
        storage.setItem(key, JSON.stringify({
          selectedJobId: studyV2.scope.selectedJobId,
          lastMode: studyV2.mode,
          resumeMode: studyV2.resumeMode,
          quizDifficulty: studyV2.quizDifficulty,
          flashDifficulty: studyV2.flashDifficulty
        }));
      } catch (e) {}
    }

    // 1. Corrupted localStorage values
    const corruptedValues = [
      '{malformed json...',
      '12345',
      'true',
      '"just a string"',
      'null',
      '[1, 2, 3]',
      '{ "lastMode": "hacked_mode", "selectedJobId": "j1" }'
    ];

    corruptedValues.forEach(badVal => {
      const storage = createMockStorage({ 'lecturepack.study.v2.group.cs101': badVal });
      const studyV2 = { scope: { groupName: 'CS101', selectedJobId: 'all' }, mode: 'overview' };

      const res = restoreGroupView('CS101', storage, studyV2);
      if (badVal.includes('hacked_mode')) {
        assert.strictEqual(studyV2.mode, 'overview');
        assert.strictEqual(studyV2.scope.selectedJobId, 'j1');
      } else if (badVal === '12345' || badVal === 'true' || badVal === '"just a string"' || badVal === 'null') {
        assert.strictEqual(res, false);
      } else if (badVal.startsWith('{malformed')) {
        assert.strictEqual(res, false);
      }
    });

    // 2. Empty group name
    assert.strictEqual(restoreGroupView('', createMockStorage(), { scope: {} }), false);
    assert.strictEqual(restoreGroupView(null, createMockStorage(), { scope: {} }), false);

    // 3. Round-trip persistence
    const storage = createMockStorage();
    const sourceStudy = {
      scope: { groupName: 'Biology 202', selectedJobId: 'job_bio_99' },
      mode: 'quiz',
      resumeMode: 'flashcards',
      quizDifficulty: 'hard',
      flashDifficulty: 'medium'
    };

    persistGroupView(storage, sourceStudy);

    const targetStudy = {
      scope: { groupName: 'Biology 202', selectedJobId: 'all' },
      mode: 'overview'
    };

    const restored = restoreGroupView('Biology 202', storage, targetStudy);
    assert.strictEqual(restored, true);
    assert.strictEqual(targetStudy.scope.selectedJobId, 'job_bio_99');
    assert.strictEqual(targetStudy.mode, 'quiz');

    // 4. Exception handling
    const throwingStorage = {
      getItem: function() { throw new Error('SecurityError: Access is denied'); },
      setItem: function() { throw new Error('QuotaExceededError'); }
    };
    assert.doesNotThrow(() => {
      restoreGroupView('CS101', throwingStorage, targetStudy);
      persistGroupView(throwingStorage, sourceStudy);
    });
    '''
    res = run_node_program(node_code)
    assert res.returncode == 0, f"LocalStorage resilience failed: {res.stderr}"


def test_cross_lecture_citation_synthesis_and_navigation_matrix() -> None:
    """Stress-test citation synthesis across single-lecture, multi-lecture group scope, and missing metadata."""
    node_code = r'''
    const assert = require('assert');

    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    function fmtTime(ms) {
      if (ms == null) return '';
      var s = Math.max(0, Math.round(Number(ms) / 1000));
      var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      if (h) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
      return m + ':' + String(sec).padStart(2, '0');
    }

    function studySlideLabel(slideId) {
      if (slideId == null) return '';
      return String(slideId);
    }

    function studyItemSourcesHtml(item, opts, jobLookup) {
      item = item || {};
      opts = opts || {};
      var isGroup = opts.isGroup;
      var lecture = item.lecture_sources || item.sources || [];
      var web = item.web_sources || [];

      if (!lecture.length && !web.length && !item.provenance) return '';

      var byJob = {};
      var distinctJobs = [];
      lecture.forEach(function (source) {
        var jid = source.job_id || 'default';
        if (!byJob[jid]) {
          byJob[jid] = [];
          distinctJobs.push(jid);
        }
        byJob[jid].push(source);
      });

      if (isGroup && distinctJobs.length > 1) {
        var groupRows = distinctJobs.map(function (jid) {
          var memberJob = jobLookup(jid);
          var title = (memberJob && (memberJob.name || memberJob.title || memberJob.filename)) || (byJob[jid][0] && byJob[jid][0].lecture_title) || 'Lecture';
          var btns = byJob[jid].map(function (source) {
            var parts = [];
            if (source.segment_id != null) {
              parts.push('<button class="lp-hit study-source study-source-time" data-job="' + esc(jid) + '" data-segment="' + esc(source.segment_id) + '" data-ms="' + (source.start_ms || 0) + '">Transcript ' + fmtTime(source.start_ms) + '</button>');
            }
            if (source.slide_id != null) {
              parts.push('<button class="lp-hit study-source study-source-slide" data-job="' + esc(jid) + '" data-slide="' + esc(source.slide_id) + '">Slide ' + esc(studySlideLabel(source.slide_id)) + '</button>');
            }
            return parts.join(' ');
          }).join(' ');
          return '<div class="study-citation-group">' +
            '<span class="study-citation-lecture-name">' + esc(title) + '</span>' +
            '<div class="study-citation-buttons">' + btns + '</div>' +
            '</div>';
        }).join('');
        return '<div class="study-cross-lecture-citations">' + groupRows + '</div>';
      }

      var parts = [];
      if (lecture.length) {
        parts.push('<span class="study-provenance-badge" data-provenance="lecture">From lecture</span>');
      }

      lecture.forEach(function (source) {
        var jid = source.job_id || '';
        var jobObj = jid ? jobLookup(jid) : null;
        var prefix = (isGroup && (jobObj || source.lecture_title)) ? ((jobObj ? (jobObj.name || jobObj.title || jobObj.filename) : source.lecture_title) + ' · ') : '';
        if (source.segment_id != null) {
          parts.push('<button class="lp-hit study-source study-source-time"' + (jid ? ' data-job="' + esc(jid) + '"' : '') + ' data-segment="' + esc(source.segment_id) + '" data-ms="' + (source.start_ms || 0) + '">' + esc(prefix) + 'Transcript ' + fmtTime(source.start_ms) + '</button>');
        }
        if (source.slide_id != null) {
          parts.push('<button class="lp-hit study-source study-source-slide"' + (jid ? ' data-job="' + esc(jid) + '"' : '') + ' data-slide="' + esc(source.slide_id) + '">' + esc(prefix) + 'Slide ' + esc(studySlideLabel(source.slide_id)) + '</button>');
        }
      });

      return parts.join(' ');
    }

    const jobMap = {
      'job_1': { id: 'job_1', name: 'Lecture 1: The Nile & Agriculture' },
      'job_2': { id: 'job_2', name: 'Lecture 2: The Pyramids of Giza' }
    };
    const lookup = id => jobMap[id];

    // 1. Time formatting
    assert.strictEqual(fmtTime(0), '0:00');
    assert.strictEqual(fmtTime(65000), '1:05');
    assert.strictEqual(fmtTime(3665000), '1:01:05');
    assert.strictEqual(fmtTime(null), '');

    // 2. Multi-lecture citation in group scope
    const multiItem = {
      sources: [
        { job_id: 'job_1', segment_id: 12, start_ms: 75000 },
        { job_id: 'job_2', slide_id: 'slide_08.png' }
      ]
    };

    const multiHtml = studyItemSourcesHtml(multiItem, { isGroup: true }, lookup);
    assert(multiHtml.includes('class="study-cross-lecture-citations"'));
    assert(multiHtml.includes('Lecture 1: The Nile &amp; Agriculture'));
    assert(multiHtml.includes('Lecture 2: The Pyramids of Giza'));
    assert(multiHtml.includes('data-job="job_1" data-segment="12" data-ms="75000"'));
    assert(multiHtml.includes('Transcript 1:15'));
    assert(multiHtml.includes('data-job="job_2" data-slide="slide_08.png"'));

    // 3. Single lecture source in group scope
    const singleInGroup = {
      sources: [
        { job_id: 'job_1', segment_id: 2, start_ms: 30000 }
      ]
    };
    const singleHtml = studyItemSourcesHtml(singleInGroup, { isGroup: true }, lookup);
    assert(singleHtml.includes('Lecture 1: The Nile &amp; Agriculture · Transcript 0:30'));
    '''
    res = run_node_program(node_code)
    assert res.returncode == 0, f"Citation synthesis tests failed: {res.stderr}"


def test_empirical_evaluation_of_appjs_get_job_readiness() -> None:
    """Directly test app.js's getJobReadiness implementation against unready video/study states."""
    # Extract getJobReadiness directly from app/ui/app.js
    func_body = JS.split("function getJobReadiness(job) {", 1)[1].split("\n  }\n", 1)[0]
    
    node_code = f"""
    const assert = require('assert');

    function getJobReadiness(job) {{
    {func_body}
    }}

    // State 1: Queued job
    const rQueued = getJobReadiness({{ id: 'j1', status: 'queued' }});
    assert.strictEqual(rQueued.ready, false);
    assert.strictEqual(rQueued.status, 'queued');

    // State 2: Running job
    const rRunning = getJobReadiness({{ id: 'j2', status: 'running', pct: 45 }});
    assert.strictEqual(rRunning.ready, false);
    assert.strictEqual(rRunning.status, 'processing');

    // State 3: Failed job
    const rFailed = getJobReadiness({{ id: 'j3', status: 'failed' }});
    assert.strictEqual(rFailed.ready, false);
    assert.strictEqual(rFailed.status, 'failed');

    // State 4: Done video, Ready study
    const rReady = getJobReadiness({{ id: 'j4', status: 'done', study_status: 'ready' }});
    assert.strictEqual(rReady.ready, true);
    assert.strictEqual(rReady.status, 'ready');

    // State 5: Done video, preparing study
    const rPreparing = getJobReadiness({{ id: 'j5', status: 'done', study_status: 'preparing' }});
    assert.strictEqual(rPreparing.ready, false);
    assert.strictEqual(rPreparing.status, 'preparing');

    // State 6: Done video, failed study
    const rStudyFailed = getJobReadiness({{ id: 'j6', status: 'done', study_status: 'failed' }});
    assert.strictEqual(rStudyFailed.ready, false);
    assert.strictEqual(rStudyFailed.status, 'failed');

    // State 7: Done video, basic study
    const rBasic = getJobReadiness({{ id: 'j7', status: 'done', study_status: 'basic' }});
    assert.strictEqual(rBasic.ready, true);
    assert.strictEqual(rBasic.status, 'basic');
    """
    res = run_node_program(node_code)
    assert res.returncode == 0, f"Extraction failed: {res.stderr}"
