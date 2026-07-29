---
phase: 04
slug: visual-artifact-reliability
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-29
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest with existing Qt/WebEngine and JavaScript reducer harnesses |
| **Config file** | `pytest.ini` |
| **Quick run command** | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | Quick: under 60 seconds; full: measure during execution |

## Sampling Rate

- **After every task commit:** Run `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds for the focused suite

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | VIS-02 | T-04-04 | Pre-visible root theme and idempotent persistence | vertical TDD | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ extend | ⬜ pending |
| 04-01-02 | 01 | 1 | VIS-01, VIS-03 | T-04-05 | Navigation-only entrance and targeted in-place updates | vertical TDD | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ extend | ⬜ pending |
| 04-02-01 | 02 | 2 | VIS-04, VIS-05 | T-04-07 | Inert tooltip and reachable very-small layout | vertical TDD | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ extend | ⬜ pending |
| 04-02-02 | 02 | 2 | VIS-05 | T-04-08, T-04-09 | Intended focus and coalesced live geometry | vertical TDD | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ extend | ⬜ pending |
| 04-03-01 | 03 | 3 | VIS-01, VIS-02, VIS-03, VIS-04, VIS-05 | T-04-10 | Focused integrated automated evidence | focused integration | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ existing | ⬜ pending |
| 04-03-02 | 03 | 3 | VIS-01, VIS-02, VIS-03, VIS-04, VIS-05 | T-04-10 | Full-suite evidence and honest lifecycle flags | full integration | `python -m pytest -q` | ✅ existing | ⬜ pending |
| 04-04-01 | 04 | 4 | VIS-01, VIS-02, VIS-03, VIS-04, VIS-05 | T-04-10 | Handoff with actual automated evidence | handoff | `python -m pytest -q` | ✅ existing | ⬜ pending |
| 04-04-02 | 04 | 4 | VIS-01, VIS-02, VIS-03, VIS-04, VIS-05 | T-04-11 | Packaged gate/tour focus and physical visual behavior | blocking packaged human verification | `python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Automated Coverage Readiness Requirements

- [ ] Extend `tests/test_ui_tokens_motion_responsive.py`, `tests/test_webview_theme.py`, and `tests/test_guided_tour.py` with explicit VIS-01 through VIS-05 coverage; do not create a parallel UI test framework.
- [ ] Add a deterministic DOM/reducer seam that records root `animationstart` events and proves only navigation to a different page can generate them.
- [ ] Add startup/bridge coverage proving a fresh profile applies Light before visibility and a user theme action atomically applies and immediately persists one value.
- [ ] Add a QtWebEngine viewport/DPI helper that asserts no horizontal overflow, required-action visibility, focus containment, geometry tracking, and an empty console-error collection.
- [ ] Add model-name tooltip tests for mouse hover and keyboard focus, exact full text, `aria-describedby`, viewport bounds, and no layout reflow.
- [ ] Add `app/desktop/main.py` coverage proving pre-visible theme readiness and confirming no 1080x680 Phase-4 minimum prevents the 480x560 matrix.
- [ ] After all vertical TDD slices and integrated suites pass, set `wave_0_complete: true` and `nyquist_compliant: true` in this frontmatter; retain both false for any missing or failing seam.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Preserve beta-5 hard shadows, embedded press depth, palette, typography, transitions, and motion | VIS-01 | Perceptual fidelity needs comparison to the approved visual baseline | Exercise every primary screen and control in both themes; compare against beta-5 and record screenshots/video without redesign drift |
| No visible theme flash before the first packaged frame | VIS-02 | Process startup and compositor timing are not fully represented by DOM tests | Launch a fresh packaged profile and a saved Dark profile repeatedly; record first visible frame and confirm the correct complete palette appears atomically |
| Responsive and DPI stability matrix | VIS-05 | Windows QtWebEngine compositor behavior varies with physical DPI and resizing | Exercise representative normal, narrow, and very small windows at supported Windows scaling values; resize during tour/gate display and confirm no clipping, horizontal page scroll, stale spotlight, flicker, or console errors |

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
