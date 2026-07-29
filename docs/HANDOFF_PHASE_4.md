# Phase 4 Handoff — Visual Artifact Reliability

**Date:** July 29, 2026  
**Status:** Automated evidence complete; blocking packaged physical visual verification pending  
**Branch:** `codex/phase4-visual-artifact-reliability`

## Authorized Scope and Preservation Contract

Phase 4 repaired visual reliability without redesigning LecturePack. The locked beta-5 visual language remains the contract: existing palette, typography, hard dark shadows, embedded/pressed control movement, 90/110/140/160/220 ms motion vocabulary, and CSS (not SVG-mask) guided-tour spotlight must be preserved. Phase 4 must not introduce a full-window crossfade, per-element palette tweens, new entrance-motion vocabulary, or page-entrance replay from backend/options/overlay events.

No original lecture video was modified. Phase 4 introduced no dependency and did not change the product's source-derived versus AI-generated data boundary: transcripts and slide images remain source-derived; optional LM Studio output remains separately stored and labelled AI-generated.

## Package Identity and Fixture Safety

- Read-only onedir fixture: `C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack`
- Executable: `C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack\LecturePack.exe`
- Product name: `LecturePack`
- File version / product version: `0.9.0-beta.5`
- Executable size: `79,578,140` bytes
- Fixture clean-state check before tests: `CLEAN_STATE_VIOLATIONS=[]` (exit `0`)
- Fixture clean-state check after tests: `CLEAN_STATE_VIOLATIONS=[]` (exit `0`)

The fixture was provided only to the pytest process through `LECTUREPACK_ONEDIR_FIXTURE`; this handoff did not rebuild, launch, or modify it.

## Automated Evidence

Environment reported by pytest: Windows (`win32`), Python `3.12.3`, pytest `9.1.1`, PySide6 / Qt runtime / Qt compiled `6.11.1`; repository root `C:\Users\marsh\Documents\LecturePack-beta6-plan`.

### Focused Phase 4 UI Suite

```text
python -m pytest -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py
collected 53 items

tests\test_ui_tokens_motion_responsive.py ............................   [ 52%]
tests\test_webview_theme.py ........                                     [ 67%]
tests\test_guided_tour.py .................                              [100%]

============================= 53 passed in 0.95s ==============================
```

### Full Fixture-Backed Regression Suite

```text
LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack
python -m pytest -q
collected 853 items

============================== warnings summary ===============================
tests/test_runtime_repair.py::test_archive_fault_matrix_rejects_special_duplicate_cross_component_and_size_bounds[duplicate]
  C:\Users\marsh\AppData\Local\Programs\Python\Python312\Lib\zipfile\__init__.py:1607: UserWarning: Duplicate name: 'bin/ffmpeg.exe'
    return self._open_to_write(zinfo, force_zip64=force_zip64)

================= 853 passed, 1 warning in 305.57s (0:05:05) ==================
```

The single warning is the deliberately exercised duplicate archive-member case in `tests/test_runtime_repair.py`; no test failed.

## Automated Requirement Coverage

| Requirement | Automated evidence | Result | Physical evidence still required |
| --- | --- | --- | --- |
| VIS-01 | Token/motion responsive suite; navigation-only entrance reducer coverage | Pass | Compare approved beta-5 shadows, press depth, palette, typography, and motion in the packaged app. |
| VIS-02 | WebView theme bootstrap/persistence coverage and desktop pre-visible readiness coverage | Pass | Observe first visible packaged frame repeatedly for fresh Light and saved Dark profiles. |
| VIS-03 | Navigation/overlay/update in-place behavior in the focused suite | Pass | Exercise active navigation, live updates, settings/options, and overlay close in the packaged app. |
| VIS-04 | Tooltip hover/focus, full text, ARIA, viewport-bound, and no-reflow coverage | Pass | Confirm the long-model tooltip with pointer and keyboard in physical Windows rendering. |
| VIS-05 | Responsive, geometry, focus, scroll, and console-error helper coverage | Pass | Execute the complete Windows size/DPI/resize/tour/gate matrix below. |

## Blocking Physical Packaged Visual Matrix

No physical packaged observation, screenshot, video, console capture, or scaling result has been claimed or recorded yet. Execute this matrix against the fixture above and append evidence locations and observed results before approving Phase 4.

| Area | Exact matrix | Required observation / evidence |
| --- | --- | --- |
| First frame | Fresh profile and saved Dark profile; launch each repeatedly | Capture first visible frame. Light/default or saved Dark must be complete before visibility with no palette flash. |
| Visual preservation | Light and Dark: Home, Settings, buttons, pressed states, hard shadows, typography, navigation entrance | Side-by-side screenshots/video against approved beta-5 baseline; confirm no flattening, palette redesign, or new motion vocabulary. |
| In-place updates | Click active navigation; trigger progress/log/settings/backend updates; change options; close gate, tour, dialog, and dropdown | Underlying page stays stationary; only a real page change may play the established entrance. |
| Responsive dimensions | Home, Settings, runtime gate, and every tour phase at normal, `1220px`, `820px`, `640px`, and very-small window | At each size, required actions remain vertically reachable; no horizontal page scroll or clipping. Test long-model tooltip by mouse and keyboard; record console state. |
| Windows scale | Repeat responsive dimensions at `100%`, `125%`, and `150%` Windows scale | Record screen scale and result for each representative page/overlay. |
| Live geometry and focus | Resize, scroll, and move between DPI-scaled monitors during tour/gate | Real target is minimally revealed; spotlight/card remain in viewport; focus cycles only highlighted action/tour controls with Exit reachable; no stale spotlight, flicker, fade, step restart, or page replay. |

## Pending Approval Evidence

**Blocking gate:** Packaged QtWebEngine compositor, physical DPI, native focus, and perceptual beta-5 preservation remain unverified. Automated DOM/reducer and Qt helper coverage cannot substitute for this gate.

Append all of the following after the physical check:

- Screenshot/video paths for fresh Light and saved Dark first-frame runs.
- Baseline-comparison capture paths for both themes.
- Completed size-by-scale matrix with pass/fail observations.
- Console/error capture location or a recorded statement of no console errors.
- Any defect, reproduction steps, and blocker.

Do not approve Phase 4 until those observations exist.
