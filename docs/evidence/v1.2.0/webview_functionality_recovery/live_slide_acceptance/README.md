# Phase 1 — Live slide-preview acceptance (real backend, real data)

`harness.py` boots the actual desktop `MainWindow` (real `Backend`, `QWebChannel`,
`lpasset` asset handler, `LecturePackAdapter` over `~/LecturePackData`) into an
offscreen `QWebEngineView` at 1360×860 and drives the production UI against three
real completed jobs.

## Result: ALL_OK (16/16) — see results.json

| Job | imgs | thumbnails | preview |
|-----|------|-----------|---------|
| egypt-live-fast-validation (egyptA excerpt) | 11 | 11/11 naturalWidth>0 | 1024px ✓ |
| 454b0c62 (CL100 Day 3 – Mesopotamia, full) | 167 | 167/167 naturalWidth>0 | 1024px ✓ |
| 75432ce6 (m2-res_1080p, short) | 7 | 7/7 naturalWidth>0 | 1920px ✓ |

Also verified: preview belongs to the addressed job; **next** changes the preview;
**job switch clears the stale image** (SHORT after FULL → src points at SHORT,
never FULL); **open_job via a Home card** (clicks `#jobs-grid [data-job]` →
`open_job` bridge → adapter → Review renders egypt's 11 slides end-to-end);
**missing file shows an explicit marker** (bogus `lpasset://…/__does_not_exist__.png`
→ `[asset] asset missing` logged, preview placeholder `display=flex`).

Directory traversal / absolute-path / cross-job rejection and spaces+Unicode data
dirs are covered by `tests/test_webview_assets.py` (17).

## Findings
1. **Large-PNG decode latency (perf, P2 not P0):** the m2 job stores 1920×1080
   ~2.5 MB PNGs; on the first (cold) check with a 1.1 s settle they had not yet
   decoded (0/7), but rendered fully with a longer settle (naturalWidth=1920).
   Correctness is fine; generating small thumbnails off the critical path is a
   worthwhile P2 optimization (167 × 2.5 MB decoded for 60×38 thumbnails is heavy).
2. **No open-job control in the UI — FIXED this session:** job cards on Home had
   `cursor:pointer` but no handler and no bridge slot, so only the latest completed
   job was reachable. Added `open_job` (bridge slot + adapter method), a job `id`
   in the jobs payload, and a Home-grid click handler that opens the job and jumps
   to Review (or Process if running). Covered by the `open_job via Home card`
   check above.

## Reproduce
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe \
      docs/evidence/v1.2.0/webview_functionality_recovery/live_slide_acceptance/harness.py \
      docs/evidence/v1.2.0/webview_functionality_recovery/live_slide_acceptance/results.json
