---
phase: 03-empty-launch-guided-demo
verified: 2026-07-29T15:39:00-04:00
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "The demo is a 45–90 second synthetic lecture."
    reason: "The developer approved the concise 10-second Polar Bears demo for first-run onboarding; the duration language in the original Phase 3 roadmap/context is stale."
    accepted_by: developer
    accepted_at: 2026-07-29T15:34:02-04:00
re_verification:
  previous_status: human_needed
  previous_score: 10/11
  gaps_closed:
    - "Six packaged technical UAT scenarios, including the calibrated four-slide detector result and detector preset controls, are now recorded as passed in 03-UAT.md."
    - "The owner’s hash-bound redistribution-rights and thumbnail-derivation declaration now exists in app/assets/demo/PROVENANCE.md and matches both assets."
  gaps_remaining: []
  regressions: []
---

# Phase 3: Empty Launch & Guided Demo — Re-verification Report

**Phase Goal:** After healthy admission, users own an empty Home experience and can opt into a concise, real, isolated guided workflow without contaminating their study data.

**Verified:** 2026-07-29T15:39:00-04:00  
**Status:** passed  
**Re-verification:** Yes — after final guided-tour and four-slide-detector fixes

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Healthy startup opens Home with no active lecture; existing jobs remain visible and activate only through an explicit action. | ✓ VERIFIED | `LecturePackAdapter.on_ui_ready()` pushes jobs then calls `_set_active_job(None)`; `_list_jobs()` excludes only session-scoped jobs. `tests/test_empty_home.py` passed. |
| 2 | First healthy admission offers Start guided demo or Skip; the concise replayable tour has user-controlled Back/Next, anchored indicators, and an obvious Exit action. | ✓ VERIFIED | `setDemoAdmissionAvailable()` gates Home/Settings entry on healthy admission; `GuidedDemoFlowModel`, real-target spotlight measurement, prompt/step controls, keyboard wiring, and `#btn-tour-exit` are substantive and exercised by `tests/test_guided_tour.py`. |
| 3 | The bundled Polar Bears demo is the developer-approved concise 10-second local asset. | ✓ VERIFIED (override) | The source MP4 and packaged copy hash to `24957E863C477CD7AD2EF9228F3BBE943F5038E5CCD18EF7AB92EFEFEE13F55F`; packaged `ffprobe` reports `10.005000` seconds. The duration override does **not** prove rights clearance; that remains the single human gate below. |
| 4 | The demo runs the real offline workflow from import through processing, Review, Study, and export-location explanation. | ✓ VERIFIED | `start_demo_job()` creates an isolated `JobController` and calls `controller.run_pipeline()`—no timer/fabricated-result branch. `PRESETS["demo"]` is exercised by the real detector test, which finds exactly four slides near 0.75, 4.00, 6.50, and 8.75 s. Packaged UAT tests 3–5 are passed. |
| 5 | Demo work cannot become a normal job or mutate normal job, library, or profile state. | ✓ VERIFIED | The job manifest is session-scoped, workspace/config/controller are separate, and persistent-job listing rejects `session_scoped`. Isolation/profile-byte-stability tests pass. |
| 6 | Exit, cancellation, failure, success, and later-launch recovery safely clean only owned temporary work and child processes. | ✓ VERIFIED | `cleanup_demo_session()` validates an exact sentinel-owned direct child and rejects reparse/traversal trees; `end_demo_job()` cancels only the isolated controller, revokes assets, and cleanup is idempotent. Terminal-path/sweep tests pass. |
| 7 | The exact bundled MP4 and thumbnail have a rights-clear redistribution provenance record. | ✓ VERIFIED | `app/assets/demo/PROVENANCE.md` records the owner’s redistribution/no-unlicensed-material/thumbnail-derivation declaration; its lowercase hashes exactly match the current assets. |
| 8 | The Polar Bears card remains discoverable/clickable during the import spotlight and visually matches the drop-zone highlight. | ✓ VERIFIED | Current `7c9a1d8` moves the live card above the scrim only while retaining its controls; CSS gives both target and card the same 25px orange baseline glow. Current UAT test 2 is passed. |
| 9 | Low, Balanced, and High slide-detection controls change/persist the normal detector setting without changing the guided demo’s fixed reliable calibration. | ✓ VERIFIED | Semantic controls map Low/Balanced/High to conservative/balanced/detailed, bridge `set_setting` persists them, queued/scheduled snapshots preserve them, and demo forces `preset="demo"`. Focused tests passed. |
| 10 | Demo availability is offered only after runtime admission; after dismissal it is replayable from Settings → Onboarding rather than shown again on Home. | ✓ VERIFIED | `syncDemoAdmission()` feeds `setDemoAdmissionAvailable`; `demoHomeDismissed` hides Home replay after Skip/Exit while `#btn-replay-tour` remains admission-gated in Settings. Current UAT tests 1, 2, and 6 are passed. |
| 11 | Packaged demo media/model payload is complete and identical to the verified source assets. | ✓ VERIFIED | `lecturepack.spec` fail-closes on absent demo media/thumbnail/model and packages all three. Current `app/dist/LecturePack` contains the MP4, JPEG, and `ggml-base.en.bin`; packaged media hashes equal source hashes. |

**Score:** 11/11 truths verified. No state-transition truth relies on source-presence evidence alone.

### Required Artifacts

| Artifact | Expected | L1/L2/L3 status | Evidence |
| --- | --- | --- | --- |
| `tests/test_empty_home.py` | Empty Home/library isolation | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ EXECUTED | 2 focused tests passed. |
| `tests/test_demo_session_isolation.py` | Isolated lifecycle and cleanup | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ EXECUTED | 22 tests cover workspace, profile, terminal, and stale-event cases. |
| `tests/test_guided_tour.py` | Admission, action-led tour, replay, card spotlight, preset controls | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ EXECUTED | 14 tests passed, including current lifted-card wiring. |
| `tests/test_slide_detection.py` | Real CV detection against the bundled media | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ EXECUTED | Real detector invocation asserts exactly four calibrated candidates. |
| `app/desktop/engine_adapter.py` + `app/desktop/paths.py` | Isolated real-pipeline lifecycle | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ WIRED | Bridge delegates `start_demo_job`/`end_demo_job`; startup and teardown use only sentinel validation. |
| `app/ui/index.html`, `app/ui/app.js`, `app/ui/app.css`, `app/ui/bridge.js` | Gated card, tour controls, CSS spotlight, and bridge calls | ✓ EXISTS / ✓ SUBSTANTIVE / ✓ WIRED | Button/card event handlers call named bridge methods; reducer events render real processing/review/study state. |
| `app/assets/demo/demo_lecture.mp4` + `polar_bears_thumbnail.jpg` + `PROVENANCE.md` | Bundled demo source assets and rights record | ✓ EXISTS / ✓ PACKAGED / ✓ ATTESTED | Source/package hashes match the owner-confirmed, hash-bound provenance declaration. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| Healthy runtime state | Empty Home/demo availability | `syncDemoAdmission()` → `setDemoAdmissionAvailable()` and backend `on_ui_ready()` → `_set_active_job(None)` | WIRED | No normal-job activation occurs during healthy bootstrap. |
| Demo card/drop action | Real isolated controller | `lpBridge.startDemoJob()` → bridge → `LecturePackAdapter.start_demo_job()` → `JobController.run_pipeline()` | WIRED | Real pipeline call is direct and tested. |
| Controller events | Process/Review/Study UI | tagged `demo_event` → `receiveDemoEvent()` → guided reducer/screen rendering | WIRED | Session/operation identity rejects stale events; review-ready emits real job projections. |
| Exit/failure/app exit | Sentinel-only cleanup | `endGuidedDemo()` → bridge → `end_demo_job()` → child cancel/asset revoke/`cleanup_demo_session()` | WIRED | Tests cover idempotence, error/cancel, and later sweep. |
| PyInstaller build | Demo assets/model | `lecturepack.spec` validates non-empty paths then `demo_datas + demo_model_datas` | WIRED | Current package contains matching MP4/JPEG and base.en model. |

### Data-Flow Trace

| Surface | Dynamic value | Upstream source | Status |
| --- | --- | --- | --- |
| Processing UI | stage/progress/logs | Isolated controller signals tagged as `demo_event` | ✓ FLOWING |
| Review and Study | accepted slides, transcript, study projection | Isolated completed job via `_push_review_data()` / `_push_study_data()` | ✓ FLOWING |
| Export guidance | accepted-slide count | Review-state `slides_changed` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command / evidence | Result | Status |
| --- | --- | --- | --- |
| Current Phase 3 automated contracts | `python -m pytest -q tests/test_empty_home.py tests/test_demo_session_isolation.py tests/test_guided_tour.py tests/test_slide_detection.py` | `40 passed in 8.27s` | ✓ PASS |
| Bundled media duration | `app/dist/LecturePack/bin/ffprobe.exe ... demo_lecture.mp4` | `10.005000` seconds | ✓ PASS |
| Final package build and complete package-backed suite | Current build/UAT evidence supplied with the handoff | `python app/packaging/build.py --no-installer` exit 0; package-backed suite `842 passed` | ✓ PASS (recorded evidence) |
| Complete Phase 3 UAT | `03-UAT.md` tests 1–7 | 7 passed; 0 issues | ✓ PASS |

### Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| HOME-01, HOME-02, HOME-03 | ✓ SATISFIED | Truths 1 and 5; empty-Home tests. |
| DEMO-01, DEMO-02, DEMO-03, DEMO-04 | ✓ SATISFIED | Truths 2, 8, and 10; guided-tour tests and passed packaged UAT. |
| DEMO-05 | ✓ SATISFIED | Technical asset/payload evidence plus the owner’s hash-bound provenance declaration. |
| DEMO-06 | ✓ SATISFIED | Truth 4; real controller/CV test and passed packaged UAT. |
| DEMO-07 | ✓ SATISFIED | Truth 5; isolated config/controller/workspace tests. |
| DEMO-08 | ✓ SATISFIED | Truth 6; sentinel cleanup, cancellation, and sweep tests. |

No Phase 3 requirement is orphaned from the plans.

### Anti-Patterns and Disconfirmation Checks

| Check | Result |
| --- | --- |
| Empty handlers, fabricated timer completion, or SVG-mask click interception in the Phase 3 path | None found. The spotlight is CSS-only and pointer-transparent; demo start calls the actual controller. |
| Stale/late event regression | Guarded by operation/session identity, with focused stale-event tests. |
| Cleanup path that could delete unrelated data | Guarded by direct-child, sentinel, and reparse checks; tests exercise foreign/reparse rejection. |
| Debt markers introduced by Phase 3 | None. The lone unrelated `TODO` in `app/ui/app.js:3905` predates Phase 3 and concerns engine-button highlighting. |

## Final Verdict

All Phase 3 implementation, package, UAT, and provenance criteria are evidenced. The prior escalation gate is closed: the owner’s rights declaration is recorded against the exact source hashes, and `03-UAT.md` reports 7/7 passed. Phase 3 is ready for its approved Phase 4 transition.

---

_Verified: 2026-07-29T15:39:00-04:00_  
_Verifier: the agent (gsd-verifier)_
