# LecturePack 0.9.0-beta.12: Startup and Reliability Implementation

**Date:** 2026-08-03
**Release:** `v0.9.0-beta.12`
**Status:** Published Windows prerelease; laptop acceptance gates remain open

This document records the beta12 startup/reliability work in implementation
detail. It is the detailed companion to
[`docs/HANDOFF_PHASE_4.md`](HANDOFF_PHASE_4.md).

## 1. Authorized phase and boundaries

### Assignment

- **Authorized phase:** LecturePack 0.9.0-beta.12 startup/reliability release.
- **Base:** `v0.9.0-beta.11`, commit
  `0207f084a687368b3a6b74ee686cb5984fc27e22`, branch
  `codex/beta11-rendering-hotfix`.
- **Implementation branch:** `fix/beta12-startup`.
- **Beta.10 Claude branch:** not used.
- **Initial scope:** A, B, and opt-in diagnostic instrumentation C.
- **Scope correction:** D and E were initially listed as deferred, then the
  user explicitly instructed that they must not be deferred. Both were
  implemented and shipped in this release.

### Required non-goals

- No overlay CSS or compositing workaround was added.
- No GPU flag, animation-wide disable, `will-change` rule, or framework
  migration was added.
- No original lecture video was modified or deleted.
- No user data, transcript, slide, or model data was changed.
- No telemetry, analytics, advertising, or remote trace transport was added.
- The existing local WebChannel, stderr, and `log_line` paths were reused.
- D's grace period is not a replacement for a real slow-checking overlay; a
  genuinely slow check still opens the existing overlay.

## 2. What beta12 fixes

Beta12 addresses three startup failure modes and adds two diagnostic/visual
reliability mechanisms:

| Item | User-visible or diagnostic result |
|---|---|
| A | A warm-start overlay that never became visible can no longer leave the rest of the app inert. |
| B | A late WebChannel/UI subscriber receives the newest bootstrap state for every checklist component instead of staying at `0 of 5`. |
| C | Guided-tour flicker evidence can be collected locally when explicitly enabled, and is off by default. |
| D | A short hidden `checking` state no longer flashes the setup overlay; a check that lasts beyond 600 ms still shows it. |
| E | A native, theme-matched startup surface is shown until the WebChannel UI is ready to accept input. |

## 3. Item A - hidden overlay close and inert-state recovery

### Problem

`beginBootstrap()` captures the underlying application as inert before runtime
admission is known. On a warm start, the backend can report a healthy,
acknowledged runtime before the setup overlay is ever rendered. The old
`closeOverlay()` returned early when the overlay was hidden, so the inert
capture was never released. The result was a visible application that did not
respond to clicks or keyboard input.

### Implementation

`app/ui/app.js` now keeps the existing close guard for a missing overlay and an
in-flight animated close, but no longer treats `el.hidden` as a reason to
return. The hidden branch now:

1. calls `setUnderlyingInert(false)`;
2. resets the runtime setup reducer;
3. clears `lastRenderedState`; and
4. returns without starting an animation.

The normal visible-overlay path is unchanged: it still uses
`LP.motion.close(el, finish)`, restores inert state in `finish()`, hides the
overlay, resets the reducer, and returns focus to the prior or fallback target.

### Regression coverage

`tests/test_flashing_reliability.py` statically verifies both paths. It checks
that the hidden path contains the inert release, reducer reset, and rendered
state reset, while the normal path still contains the animated close call and
the combined visible close sequence.

## 4. Item B - latest bootstrap progress replay

### Problem

Bootstrap assessment starts before the WebChannel handshake. The worker can
emit all five component states before the UI subscribes to
`bootstrap_progress`. The UI reducer needs the latest state per component, not
the entire historical stream, to reconstruct the checklist accurately.

### Implementation in `app/desktop/bridge.py`

Before `_start_bootstrap_async()` starts the worker, `Backend.__init__()` now
creates:

```python
self._bootstrap_progress_state: dict[str, tuple[str, str]] = {}
self._bootstrap_progress_lock = threading.Lock()
```

`_emit_progress()` updates the map under the lock before scheduling the normal
Qt signal emission. This preserves the existing worker-to-main-thread
marshalling and adds a reliable latest-value snapshot.

`_replay_bootstrap_progress()` copies the map under the same lock and emits one
JSON payload for each component. `ui_ready()` calls this replay immediately
after recording readiness, before deferred adapter/updater startup work. The
historical worker events are not re-created; only one newest state per
component is replayed.

### Ordering test

`tests/test_bootstrap_deferral.py` adds a late-subscriber test that waits for
bootstrap completion, subscribes after all worker events have finished, calls
`ui_ready()`, and asserts:

- exactly five replayed events;
- the fixed checklist order;
- one event per component; and
- every replayed state is `resolved`.

The bootstrap payload key contract was updated for the new diagnostic flag
described below.

## 5. Item C - opt-in guided-tour trace instrumentation

### Enablement and transport

Tracing is disabled unless the process environment contains:

```text
LECTUREPACK_TOUR_TRACE=1
```

`app/desktop/bridge.py` reads the flag once during backend construction and
exposes the resulting boolean as `tour_trace_enabled` in `get_bootstrap()`.
Any value other than the trimmed string `1` leaves tracing disabled.

The browser batches records for 100 ms and sends each batch through the narrow
local bridge slot `log_tour_trace`. The bridge only acts when the backend flag
is enabled. Enabled records are written to local stderr with a `[tour-trace]`
prefix and forwarded through the existing `log_line` signal for the local UI
log path. No HTTP, telemetry, analytics, or remote sink was introduced.

### Instrumented events in `app/ui/app.js`

Each trace record includes `performance.now()`, the guided-tour snapshot, the
demo flow phase, and whether demo admission is currently available. The
instrumentation records:

- every `#guided-tour-overlay.hidden` write through
  `setTourOverlayHidden()`;
- `MutationObserver` changes on the guided-tour overlay, including attribute
  and child-list changes, the attribute name/old value, and added/removed node
  counts; and
- recurring `requestAnimationFrame` callback timestamps.

The observer, animation-frame loop, timer, and queued batches are all torn
down when tracing is disabled. The normal guided-tour path uses the helper for
the hidden write, making the diagnostic boundary explicit without changing
the overlay's behavior.

### Regression coverage

`tests/test_flashing_reliability.py` verifies the default-off environment
contract, bootstrap exposure, bridge sink, hidden-write helper, observer,
attribute-old-value capture, and rAF timestamp recording. The bootstrap tests
also assert the exact payload key set including `tour_trace_enabled`.

## 6. Item D - 600 ms checking grace period

### Problem

The setup gate can briefly enter `checking` while the runtime health result is
already about to arrive. Opening the full overlay for that short interval
creates a visible flash and steals focus unnecessarily.

### Implementation

`RuntimeSetupGate.render()` now accepts a `forceCheckingOpen` argument. When the
state is `checking`, the overlay is hidden, and the render is not forced, it
calls `scheduleCheckingOpen()` and leaves the overlay hidden.

The grace timer is:

```javascript
var CHECKING_GRACE_MS = 600;
```

After 600 ms, the callback re-reads both the overlay and reducer state. It
opens the overlay only if the state is still `checking` and the overlay is
still hidden, using `render(true, true)`. If checking resolves first, the
state-change path clears the timer and the overlay never flashes.

All per-row checking timers, the slow-notice timer, and the overlay-open timer
are cleared by `clearCheckingTimers()`. Closing the gate also clears them, so
no stale callback can reopen or repaint a superseded state.

### Regression coverage

`tests/test_flashing_reliability.py` verifies the 600 ms constant, hidden-state
gate, timer scheduling, state re-check, forced render, and timer cleanup.
Existing assertions also confirm that the normal animated close path and
live-DOM processing behavior remain present.

## 7. Item E - native startup placeholder

### Problem

The WebEngine view can take time to paint its first frame and complete the
QWebChannel handshake. Showing an unpainted or transparent WebEngine surface
made cold startup look empty or flashed the wrong background, especially on a
slower laptop.

### Implementation in `app/desktop/main.py`

`MainWindow` now creates a `QStackedWidget` containing:

1. the existing `QWebEngineView`; and
2. a native placeholder widget with the centered label
   `LecturePack - starting...` (the source label uses the typographic middle
   dot and ellipsis).

The placeholder is selected before page load. `Backend` exposes a native
`ui_ready_signal`, and `MainWindow` connects it to an idempotent
`_show_startup_content()` method. The first `ui_ready()` call emits the signal
once; subsequent calls still replay progress but do not repeatedly switch the
stack.

The placeholder, stack, main window, and WebEngine view all receive the saved
light/dark opaque background. The placeholder text color is synchronized with
the active theme. `app/ui/bridge.js` includes `ui_ready_signal` in its signal
contract list so the Python and JavaScript bridge declarations remain in sync.

### Regression coverage

`tests/test_flashing_reliability.py` verifies the stack, placeholder, initial
selection, signal connection, idempotent first-ready emission, view switch,
and themed placeholder styling. The existing theme/startup surface test also
verifies that the stack is installed before `view.load()`.

## 8. Metadata, decisions, and release workflow

### Application metadata

- `app/desktop/version.py` is `0.9.0-beta.12`.
- `app/packaging/win_version_info.txt` carries beta12 file and product
  versions.
- `CHANGELOG.md` documents A-E, opt-in tracing, and the release dependency
  closure.
- `docs/DECISIONS.md` records the trace transport decision and AD-23, the
  offline release dependency-closure decision.
- `docs/HANDOFF_PHASE_4.md` records the phase result, test evidence, release
  URLs, immutable tag commit, and installer checksum.

### Release dependency correction

The first automatic tag run (`30781624532`) failed during offline dependency
installation because the verified wheel directory contained
`cryptography==49.0.0` but not its required `cffi` dependency.

The workflow correction, committed as `85ae81c`, now downloads, verifies, and
installs:

| Package | Pin | Verified SHA-256 |
|---|---|---|
| cryptography | `49.0.0` | `e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e` |
| cffi | `2.0.0` | `da68248800ad6320861f129cd9c1bf96ca849a2771a59e0344e88681905916f5` |
| pycparser | `2.22` | `c3702b6d3dd8c7abc1afa565d7e63d53a1d0bd86cdc24edd75470f4de499cfcc` |

The corrected workflow was manually dispatched from `fix/beta12-startup` with
the input tag `v0.9.0-beta.12`. The workflow checked out the immutable beta12
source tag, so the release payload remained tied to the tagged product commit
while the workflow definition came from the corrected branch.

## 9. Verification evidence

### Focused and targeted tests

The required focused command passed:

```text
python -m pytest -q tests/test_flashing_reliability.py tests/test_bootstrap_deferral.py
45 passed in 1.51s
```

Additional targeted checks passed:

```text
tests/test_flashing_reliability.py tests/test_bootstrap_deferral.py
tests/test_adapter_startup.py tests/test_guided_tour.py tests/test_webview_theme.py
78 passed in 2.28s

tests/test_media_link_adapter.py::test_bridge_signals_match_ui_signal_list
tests/test_flashing_reliability.py tests/test_bootstrap_deferral.py
46 passed in 2.61s
```

JavaScript syntax checks for `app/ui/app.js` and `app/ui/bridge.js`, plus
Python compilation checks for `app/desktop/bridge.py` and
`app/desktop/main.py`, passed with no output.

### Required pre-tag suite

The exact required command completed as:

```text
python -m pytest -q --ignore=tests/test_release_trust.py --ignore=tests/test_runtime_repair.py --ignore=tests/test_signing_adr_contract.py
1016 passed, 1 skipped, 19 failed in 208.16s (0:03:28)
```

The 19 failures matched the documented pre-existing baseline categories:

- 11 demo-session checks plus the first-run-suite wrapper;
- 2 package-pruning checks;
- 3 Phase 2 job-lifecycle checks; and
- 2 packaged-runtime fixture checks.

No A-E-specific failure was introduced. The release trust module was excluded
from this suite as required; its local test module also requires the approved
cryptography package that is intentionally not installed in the development
test environment. The GitHub runner's corrected offline install step passed.

The release asset contract test passed separately with `10 passed`. The first
successful Windows release workflow run completed all steps, including
packaging, signing, updater-asset assertions, publication, and audit-artifact
retention.

## 10. Published release

- **Release page:**
  <https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.12>
- **Successful workflow run:**
  <https://github.com/pasttrunks/lecturepack/actions/runs/30781784765>
- **Tagged source commit:**
  `124eefad998763f925baeaaa6489d4c315f4b604`
- **Installer:**
  `LecturePack-0.9.0-beta.12-Setup.exe`
- **Installer SHA-256:**
  `5aa89a4f61985097e8ea06c7a2baa3cc525886000f45d7bf0dfa38a4d12ed3de`
- **Checksum file:**
  `LecturePack-0.9.0-beta.12-SHA256SUMS.txt`

The installer is a Windows prerelease. The GitHub release contains the setup
executable, checksum file, and the six signed runtime-repair assets.

## 11. Laptop acceptance gates still required

These checks require the target laptop and were not claimed as locally passed:

1. Run both beta11 flicker experiments before applying any CSS/compositing
   diagnosis.
2. On the first beta12 run, confirm setup progress advances beyond `0 of 5`.
3. Close and relaunch; confirm the sidebar, theme controls, and Browse action
   respond to input.
4. Run the complete lecture workflow: import, setup, processing, review, and
   export.
5. If tracing is enabled, correlate the local `[tour-trace]` log with phone
   footage and visible timestamps. Keep tracing disabled for ordinary use.

The beta12 code intentionally stops at evidence collection for the flicker
question. A future CSS or compositing change requires laptop evidence first.
