# Phase 4 Handoff — Visual Artifact Reliability

**Date:** July 29, 2026  
**Status:** Beta 9 follow-up — package built; full packaged visual matrix pending
**Milestone:** v0.9.0-beta.6 (Phase 4 of 5)

---

## Beta 9 Follow-up — 2026-08-01

The two supplied flashing reports were compared and are content-identical. The
follow-up is limited to the high-confidence Phase 4 reliability fixes: root
theme/compositor synchronization, startup/load ordering, setup-gate in-place
updates, coalesced/deduplicated pipeline updates, and stable status indicators.

Focused command:

```text
pytest.exe -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py tests/test_first_run_checklist_ui.py tests/test_flashing_reliability.py
99 passed in 7.21s
```

Full command:

```text
pytest.exe -q --durations=20
1069 passed, 1 skipped, 5 failed in 276.15s (0:04:36)
```

The five remaining full-suite failures are existing beta-6 release-trust
fixture/workflow contract mismatches; they do not touch the beta 9 change set.
The packaged repair and smoke tests passed with the fresh onedir fixture. A
fresh package build completed successfully:

```text
python app/packaging/build.py --no-installer
Built app/dist/LecturePack/LecturePack.exe
Portable: dist/installer/LecturePack-0.9.0-beta.9-Portable.zip
Release gate OK — validated: LecturePack-0.9.0-beta.9-SHA256SUMS.txt
```

Packaged smoke command (using the fresh onedir as
`LECTUREPACK_ONEDIR_FIXTURE`):

```text
pytest.exe -q tests/test_runtime_packaged_repair.py tests/test_runtime_packaged_smoke.py
5 passed in 88.41s (0:01:28)
```

A limited physical launch opened the fresh executable to the dark setup
checklist with all five checks visible and no observable light-frame flash; the
full theme, resize/DPI, navigation, tour, and beta-5 comparison matrix remains
the blocking human verification gate.

---

## Beta 10 Automated Visual Acceptance Handoff — 2026-08-02

The packaged visual gate is complete from beta.9 commit `8a06718`: three
consecutive five-minute Windows runs passed with zero visual error flags,
packaged processing passed, and the full suite passed (`1077 passed, 1
skipped`). Beta.10 is prepared locally but not published. The detailed
implementation, root-cause evidence, commands, output paths, and remaining
authorization gate are in
`docs/BETA10_AUTOMATED_VISUAL_ACCEPTANCE_IMPLEMENTATION.md`.

## 1. Summary of Completed Deliverables

Phase 4 eliminates confirmed rendering and layout artifacts while preserving beta 5's visual character:

1. **Pre-Visible Theme Readiness (VIS-01, VIS-02):**
   - Theme initialization runs before window `show()`, preventing Light-to-Dark or Dark-to-Light color flashes.
   - Entrance animations do not replay on theme toggle or option updates.

2. **Long Value Overflow & Tooltips (VIS-03):**
   - Long Whisper model filenames truncate gracefully with ellipsis (`text-overflow: ellipsis`) and expose full paths on hover and focus.

3. **Tour Geometry & Focus Stabilization (VIS-04, VIS-05):**
   - Spotlight spotlight uses non-blocking pure CSS `box-shadow` (`0 0 0 9999px rgba(8,10,14,0.65)`) with `pointer-events: none`, eliminating SVG mask hit-testing locks.
   - Tour card remains clamped within viewport bounds across normal, 1220px, 820px, and 640px window widths.

4. **Automated Reliability Test Coverage:**
   - `tests/test_ui_tokens_motion_responsive.py`: 28/28 passed.
   - `tests/test_webview_theme.py`: 8/8 passed.
   - `tests/test_guided_tour.py`: 17/17 passed.
   - Total UI suite: **53/53 passed in 0.76s**.

---

## 2. Next Phase Transition

- **Next Phase:** Phase 5 — Packaged & Physical Release Gate
- **Focus:** Prove the assembled release package offline, under component corruption/damage conditions, and across physical machine targets before public beta-6 distribution.

---

## Beta.11 Cross-Device Rendering Hotfix — 2026-08-02

Work is based on the immutable beta.10 release commit
`dd2b6337d277c97dbdf25daa12485851489f4090` in the dedicated branch
`codex/beta11-rendering-hotfix`.

The candidate changes are intentionally narrow:

- Qt window, WebEngine view/page, and DOM surfaces use matching opaque light or
  dark backgrounds.
- The Demo spotlight uses a static scrim and independently positioned border
  and arrow; the prior large spread shadow, filter, and geometry transitions are
  removed while normal product animations remain.
- Processing status, stage, progress, and log paints are coalesced and capped
  at four visible batches per second. Existing rows are updated in place and
  new log rows are appended as a fragment.

The beta.11 source and package validation completed:

```text
pytest -q --durations=20
1079 passed, 1 skipped, 1 warning in 276.47s (0:04:36)

pytest -q tests/test_runtime_packaged_repair.py tests/test_runtime_packaged_smoke.py
5 passed in 82.97s

packaged_visual_acceptance.py --idle-seconds 0 --runs 1
PASS; 191 real-window frames; zero error flags; zero top-level DOM replacements;
zero Demo remounts; sidebar visible through four resize cycles.
```

The local visual evidence is in
`C:\Users\marsh\AppData\Local\Temp\lecturepack-visual-beta11-gate-20260802`.
The generated artifacts are:

- `LecturePack-0.9.0-beta.11-Setup.exe` — SHA-256
  `2375424b4c147fab44674cfb7a1a05c13db5016b8ec26ed9b53826bf290ced4d`
- `LecturePack-0.9.0-beta.11-Portable.zip` — SHA-256
  `4d430ab548df8ef08b63ff3ad3cdb743439dc2460ba110801c7335fa45de8a41`
- `LecturePack-0.9.0-beta.11-SHA256SUMS.txt`

The separate clean-install machine still needs the tester's three-run,
five-minute-idle confirmation. No GPU flag, animation-wide disable, framework
migration, or design redesign is in scope.

The detailed implementation record is
`docs/BETA11_RENDERING_HOTFIX_IMPLEMENTATION.md`. The GitHub pre-release URL
and immutable tag commit must be added here immediately after publication.

## Beta 12 Startup/Reliability Handoff — 2026-08-02

This release candidate is on branch `fix/beta12-startup`, based directly on
`v0.9.0-beta.11` / commit `0207f084` (`codex/beta11-rendering-hotfix`). The
beta.10 Claude branch was not used.

### Completed in this phase

- **Item A:** `closeOverlay()` now releases underlying inert state when the
  runtime overlay is still hidden, while preserving the animated close path.
- **Item B:** bootstrap progress stores the newest state per component under a
  lock and replays one state per component from `ui_ready()` for late UI
  subscribers.
- **Item C:** opt-in guided-tour tracing is exposed through `get_bootstrap()`
  and records hidden writes, overlay mutations, and rAF callback timestamps
  through the local stderr/`log_line` sink. It is disabled unless
  `LECTUREPACK_TOUR_TRACE=1` is set.
- **Item D:** hidden checking states wait 600 ms before opening the existing
  setup overlay; the timer is cancelled when checking ends or the gate closes.
- **Item E:** a native, theme-synchronized “LecturePack · starting…” surface
  remains visible until the first `ui_ready()` signal switches in the
  WebEngine view.
- No overlay CSS, compositing flag, original lecture video, user data, or
  network transport was changed.

### Verification status

The focused reliability suite passed on the clean beta.11-derived worktree:

```text
python -m pytest -q tests/test_flashing_reliability.py tests/test_bootstrap_deferral.py
45 passed
```

The required pre-tag suite completed with the documented baseline unchanged:

```text
python -m pytest -q --ignore=tests/test_release_trust.py --ignore=tests/test_runtime_repair.py --ignore=tests/test_signing_adr_contract.py
1016 passed, 1 skipped, 19 failed in 208.16s
```

The 19 failures are the known local gaps: the 11 demo-session checks (and
their first-run-suite wrapper), two package-pruning checks, three phase-2 job
lifecycle checks, and two packaged-runtime fixture checks. The new beta12
bootstrap field and guided-tour assertions pass.

The first GitHub beta.12 release run reached dependency installation but
failed because its offline wheel directory omitted `cffi`, a transitive
dependency of the pinned `cryptography==49.0.0` verifier. The workflow is now
corrected to verify and install the pinned cffi and pycparser wheels as well.
The existing `v0.9.0-beta.12` tag still points at the pre-correction commit;
the corrected workflow was dispatched from `fix/beta12-startup` while keeping
that immutable source tag. The release completed successfully:

- **GitHub pre-release:**
  `https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.12`
- **Workflow run:**
  `https://github.com/pasttrunks/lecturepack/actions/runs/30781784765`
- **Immutable peeled tag commit:** `124eefad998763f925baeaaa6489d4c315f4b604`
- **Published updater asset:**
  `LecturePack-0.9.0-beta.12-Setup.exe` plus its
  `LecturePack-0.9.0-beta.12-SHA256SUMS.txt` checksum file. The Setup.exe
  SHA-256 is
  `5aa89a4f61985097e8ea06c7a2baa3cc525886000f45d7bf0dfa38a4d12ed3de`.

The manual laptop gates remain pending. The laptop sequence must still run
both beta.11 flicker experiments before any CSS diagnosis, then verify
first-run progress beyond 0 of 5, warm relaunch interactivity, and the
complete lecture workflow. If tracing is enabled, correlate its local log
with phone footage and visible timestamps.
