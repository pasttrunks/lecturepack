# Beta 9 Flashing Fix — Implementation Handoff

**Date:** 2026-08-01
**Purpose:** Exact implementation record for a follow-on AI agent
**Repository:** `pasttrunks/lecturepack`
**Worktree:** `C:\Users\marsh\Documents\LecturePack-beta6-plan`
**Branch:** `codex/phase4-visual-artifact-reliability`
**Fix commit:** `8a0671810e235b24aab9ad0805cfa6fed30fcb00`
**Release tag:** `v0.9.0-beta.9`
**Release:** <https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.9>

## 1. Executive summary

Beta 8 was released, but the supplied flashing diagnosis showed that several
beta 8 fixes had not addressed the real rendering boundaries. I compared both
supplied reports, implemented the high-confidence fixes that fit the current
Phase 4 visual-artifact-reliability scope, ran focused and full verification,
built the Windows package, and published beta 9.

The implementation addresses four related causes:

1. Theme state was written to `#app` while CSS variables and the native
   WebEngine surface were resolved at higher/native layers.
2. Startup and setup-gate code repeatedly changed scroll/inert/focus state and
   rebuilt unchanged rows.
3. Pipeline/log events could cause a full panel render for every event.
4. Duplicate backend progress and whole-node status replacements restarted
   animation/layout work even when only the displayed percentage/text changed.

No new dependency was added. The engine/data boundary was preserved. Original
lecture videos were not modified. The approved visual vocabulary was not
redesigned.

## 2. Diagnosis inputs and comparison

The two user-supplied reports were:

- `C:\Users\marsh\.codex\attachments\305456b8-6415-484b-80e1-920495d4e4f6\pasted-text.txt`
- `C:\Users\marsh\.codex\attachments\aa4c303f-f628-4982-b41f-2337c521c6e3\pasted-text.txt`

Both contained 418 lines. A line-by-line comparison returned no content
difference. Their raw SHA-256 hashes differ only because the first file has a
trailing CRLF/newline representation and the second does not:

| Report | Raw SHA-256 |
|---|---|
| `305456b8-6415-484b-80e1-920495d4e4f6` | `96F73EC2273925DA9C5B832573AFBA0034482234FF2B08B3E9099EB75288839D` |
| `aa4c303f-f628-4982-b41f-2337c521c6e3` | `80263908CA8FD23CE52A95A0B83F90D7CE1B8714F113A98600EB4D3C8BDA7EAD` |

The reports' actionable recommendations were grouped as follows:

- **Fix 1:** root-level theme authority and compositor/background alignment.
- **Fix 2:** startup scrollbar/load-order/setup-overlay stability.
- **Fix 3:** coalesced/deduplicated pipeline/status rendering.
- **Deferred:** GPU flags, DPI/monitor work, locale/debug payload changes,
  transcript duplicate-log policy, and renderer redesign unless beta 9
  reproduces those independent symptoms.

## 3. Starting state and repository discipline

Before modifying code, I read the required project documents and Phase 4
context/plans, including:

- `AGENTS.md`
- `docs/PRODUCT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/IMPLEMENTATION_PLAN.md`
- Phase 4 context, plans, UI spec, and validation artifacts under
  `.planning/milestones/v0.9.0-beta.6/phases/04-visual-artifact-reliability/`

The target worktree started at beta 8:

- `f35ba910` / `v0.9.0-beta.8`
- target branch already existed and was checked out
- origin: `https://github.com/pasttrunks/lecturepack.git`

The worktree was not clean. I preserved these unrelated user/planning changes
and did not stage them:

- modified `.planning/config.json`
- untracked `.agents/`
- untracked `.planning/phases/01-clean-device-footprint-first-launch/01-VERIFICATION.md`
- untracked `.planning/phases/02-real-lecture-import-processing/02-RESEARCH.md`
- untracked `docs/FLASH_DIAGNOSIS.md`

The beta 9 commit contains only the 14 intended release/product/test/document
files listed below. `app/verify_ui.py` was inspected for a stale selector but
was restored and is not part of the commit.

## 4. Exact implementation changes

### 4.1 Root theme and first-frame compositor alignment

Files:

- `app/ui/index.html`
- `app/ui/app.js`
- `app/desktop/main.py`
- `app/desktop/bridge.py`
- `tests/test_webview_theme.py`
- `tests/test_flashing_reliability.py`

Changes:

1. `app/ui/index.html` now declares the theme on the document root:

   ```html
   <html lang="en" data-theme="light">
   ```

   The duplicate `data-theme="light"` attribute was removed from `#app`.

2. `applyTheme()` in `app/ui/app.js` now reads/writes
   `document.documentElement.dataset.theme`. Its idempotence check also uses
   the document root. Boot initialization reads the root attribute.

3. `MainWindow._apply_initial_theme_before_show()` in `app/desktop/main.py`
   now injects:

   ```javascript
   document.documentElement.dataset.theme = <JSON-encoded theme>;
   ```

   It no longer injects a theme into `#app`.

4. `MainWindow` connects `backend.settings_changed` to
   `_sync_page_background()`. That method maps the saved theme to both the
   QWebEngine page background and the native `QMainWindow` background:

   - dark: `#16191F`
   - light: `#F3F0E8`

5. `Backend.set_setting()` now explicitly emits `settings_changed` for the
   `theme` key after persisting and forwarding the setting. QSettings itself
   did not provide the required UI signal for this path.

6. `self.setCentralWidget(self.view)` now occurs before
   `self.view.load(...)`, so the native widget/compositor is installed before
   WebEngine page loading begins.

### 4.2 Startup scrollbar and setup-overlay stability

Files:

- `app/ui/app.css`
- `app/ui/app.js`
- `tests/test_first_run_checklist_ui.py`
- `tests/test_flashing_reliability.py`

Changes:

1. `body` width changed from `100vw` to `100%`. This avoids a viewport-width
   scrollbar gutter/overflow interaction while retaining the existing
   `height:100vh;overflow-y:auto` contract.

2. `RuntimeSetupGate.setUnderlyingInert()` no longer mutates
   `document.documentElement.style.overflow`. The app root already owns its
   layout overflow; toggling document overflow during overlay admission was a
   source of scrollbar/layout artifacts.

3. The gate now tracks:

   ```javascript
   var lastRenderedState = null, closeInFlight = false;
   ```

   `render(dataChanged)` returns early when neither the state nor data changed:

   ```javascript
   if (!stateChanged && !dataChanged) return;
   ```

   Overlay visibility, panel selection, exit-button visibility, and initial
   focus are applied only on a state transition. Data updates still refresh
   the dynamic rows/content without refocusing the user or replaying the state
   transition.

4. Setup checklist rows are now retained and updated in place. Rows carry
   `data-runtime-row-id`, labels carry `data-runtime-label`, badges carry
   `data-runtime-badge`, and optional advisory text carries
   `data-runtime-advisory`. This lets checking/checklist updates change text,
   state attributes, and advisory content without replacing all five row
   elements on every progress event.

5. `renderChecklist()` explicitly removes stale children when the checklist is
   incomplete, preventing old rows from surviving a state/data transition.

6. `closeOverlay()` now routes the exit through the existing
   `LP.motion.close()` helper, uses `closeInFlight` to prevent duplicate close
   sequences, restores inert state after the close callback, resets the reducer,
   clears the rendered-state sentinel, and then restores focus.

### 4.3 Pipeline, log, and status update throttling

Files:

- `app/ui/app.js`
- `app/desktop/engine_adapter.py`
- `tests/test_flashing_reliability.py`

Browser-side changes:

1. The `pipeline_changed` bridge handler now calls
   `schedulePipelineRender()` instead of `renderPipeline()` directly. The
   existing requestAnimationFrame/setTimeout scheduler therefore coalesces
   bursts to at most one pipeline render per frame.

2. `renderPipeline()` already had a stage-HTML equality guard. It now applies
   the same dirty check to the generated log HTML:

   ```javascript
   if (logEl.innerHTML !== logHtml) {
     logEl.innerHTML = logHtml;
     ...
   }
   ```

   Scroll anchoring is performed only when the log actually changes.

3. `setStatusDotText()` was added. It creates the status dot/label pair only
   when necessary, then changes child styles/text in place. The side-job status
   and AI status handlers now use it instead of replacing the complete
   container `innerHTML`, which previously restarted the blink animation and
   created a visible strobe under frequent updates.

Backend-side changes in `LecturePackAdapter`:

1. Added `_last_pipeline_payload`, a canonical JSON serialization of the last
   emitted pipeline payload. `_render_pipeline()` skips `_emit()` when the
   serialized payload is byte-identical.

2. Added `_last_stage_progress`, keyed by stage name. `_on_stage_progress()`
   converts incoming values to integer percentages and returns without emitting
   taskbar/status/pipeline updates when the same stage reports the same integer
   percentage again.

3. `_on_stage_started()` seeds that stage at 0%, allowing the start event to be
   emitted once while suppressing an immediate duplicate worker 0% callback.

4. Both caches reset at normal/demo pipeline start. Demo cleanup snapshots and
   restores the previous cache values along with the existing stage/job state,
   so demo isolation does not corrupt a normal pipeline's dedupe state.

### 4.4 Release metadata and project records

Files:

- `app/desktop/version.py`: `0.9.0-beta.8` → `0.9.0-beta.9`
- `app/packaging/win_version_info.txt`: file/product versions → beta 9
- `CHANGELOG.md`: beta 9 flashing-fix section
- `docs/DECISIONS.md`: AD-19 records the root/compositor and dedupe decision
- `docs/HANDOFF_PHASE_4.md`: records focused/full/package/physical evidence and
  keeps the full visual gate status honest

No dependency file or architecture stack was changed.

## 5. Test changes

### Existing tests updated

`tests/test_webview_theme.py` now asserts:

- root `<html lang="en" data-theme="light">`
- no theme attribute on `#app`
- root-based `applyTheme()` bootstrap/idempotence
- root-based pre-show injection
- native/WebEngine background synchronization

`tests/test_first_run_checklist_ui.py` now asserts the required `body{width:100%}`
contract instead of asserting that `app.css` must have zero changed lines. Its
render-function extraction was updated for the new `render(dataChanged)`
signature.

### New test file

`tests/test_flashing_reliability.py` covers:

- root theme/startup/load-order contracts
- no document overflow mutation
- setup-gate render guard/in-place row/close-motion contracts
- scheduled pipeline and stable status-node contracts
- real `LecturePackAdapter` duplicate-progress and identical-payload behavior

The new backend test uses a lightweight `LecturePackAdapter.__new__()` object
with a fake window and event collector. It does not mock the behavior being
tested; it exercises the actual adapter methods while avoiding external media
or network integration.

## 6. Verification record

### JavaScript syntax

The changed UI module passed the Node syntax check:

```powershell
& 'C:\Users\marsh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check app\ui\app.js
```

Exit code: `0`.

### Focused reliability suite

The final focused command was:

```powershell
& 'C:\Users\marsh\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' -q tests/test_ui_tokens_motion_responsive.py tests/test_webview_theme.py tests/test_guided_tour.py tests/test_first_run_checklist_ui.py tests/test_flashing_reliability.py
```

Result:

```text
99 passed in 7.21s
```

### Full test suite

The first full-suite run without a packaged fixture reported `1066 passed,
2 skipped, 7 failed`; two of those failures were the expected packaged tests
without their required fixture environment.

I then ran the full suite with a fresh local onedir fixture:

```powershell
& {
  $env:LECTUREPACK_ONEDIR_FIXTURE = (Resolve-Path 'app\dist\LecturePack').Path
  & 'C:\Users\marsh\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' -q --durations=20
}
```

Result:

```text
1069 passed, 1 skipped, 5 failed in 276.15s (0:04:36)
```

The five remaining failures are:

```text
tests/test_release_trust.py::test_frozen_manifest_authenticates_before_parsing_and_altered_byte_fails
tests/test_release_trust.py::test_exact_six_asset_layout_and_checked_archive_total
tests/test_release_trust.py::test_offer_uses_authenticated_metadata_and_admission_evidence_only
tests/test_release_trust.py::test_release_workflow_binds_both_triggers_to_the_peeled_tag_before_signing
tests/test_runtime_repair.py::test_offer_authenticates_only_manifest_and_signature_before_confirmation
```

These failures are release-trust fixture/workflow-contract mismatches outside
the beta 9 flashing changes. I did not weaken, delete, or skip those tests.

### Local package build

The final local package build was:

```powershell
& 'C:\Users\marsh\AppData\Local\Programs\Python\Python312\python.exe' app\packaging\build.py --no-installer
```

The build reported:

```text
Building LecturePack 0.9.0-beta.9
Built ...\app\dist\LecturePack\LecturePack.exe
Bundled canonical CPU runtime: 17 payload files
Pruned unused Qt components: 4/4 targets present, 88990550 bytes reclaimed
Clean-state gate OK — no job/dev data bundled; engine payload present.
Portable: dist/installer/LecturePack-0.9.0-beta.9-Portable.zip
Release gate OK — validated: LecturePack-0.9.0-beta.9-SHA256SUMS.txt
```

This local build ran outside the project virtual environment and may therefore
collect globally installed packages. The clean CI workflow build also passed,
so the released artifact was produced by the clean workflow path.

### Packaged smoke tests

Against the freshly built onedir fixture:

```powershell
& {
  $env:LECTUREPACK_ONEDIR_FIXTURE = (Resolve-Path 'app\dist\LecturePack').Path
  & 'C:\Users\marsh\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' -q tests/test_runtime_packaged_repair.py tests/test_runtime_packaged_smoke.py
}
```

Result:

```text
5 passed in 90.72s (0:01:30)
```

### Limited physical launch check

I launched exactly:

```text
C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack\LecturePack.exe
```

Using the desktop UI, I selected the single returned LecturePack window,
observed the dark setup checklist with all five rows in `Ready` state, saw no
observable light-frame flash during launch, and closed the app with `Alt+F4`.

This was a limited smoke check, not the complete Phase 4 visual matrix. The
following remain suitable follow-up checks if the artifact is still reported:

- saved-light and saved-dark startup
- resize and DPI changes
- navigation between all major views
- guided-tour and dialog transitions
- side-by-side beta 5 comparison

## 7. Commit, tag, push, and release

The implementation was committed as:

```text
8a0671810e235b24aab9ad0805cfa6fed30fcb00 fix(visual): stop beta9 flashing artifacts
```

The branch and release tag were pushed with:

```powershell
git push origin codex/phase4-visual-artifact-reliability
git push origin v0.9.0-beta.9
```

GitHub Actions run `30718921847` (job `91419278929`) completed successfully
in approximately 9 minutes 49 seconds. The prerelease was published at
`2026-08-01T21:29:52Z`:

<https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.9>

The release contains eight assets:

- `LecturePack-0.9.0-beta.9-Runtime-ffmpeg.zip`
- `LecturePack-0.9.0-beta.9-Runtime-model-base-en.zip`
- `LecturePack-0.9.0-beta.9-Runtime-smoke-fixture.zip`
- `LecturePack-0.9.0-beta.9-Runtime-whisper-cpu.zip`
- `LecturePack-0.9.0-beta.9-RuntimeManifest-v1.json`
- `LecturePack-0.9.0-beta.9-RuntimeManifest-v1.json.sig`
- `LecturePack-0.9.0-beta.9-Setup.exe`
- `LecturePack-0.9.0-beta.9-SHA256SUMS.txt`

The post-commit review hook printed a `UnicodeEncodeError` while rendering a
panel under the Windows CP1252 console. `git commit` still returned exit code
0, and the commit, tag, push, and CI/release verification were checked
afterward.

## 8. Current worktree and follow-up guidance

At the time this handoff was written, the target branch pointed at beta 9.
The following pre-existing or unrelated files were left untouched and are not
part of the flashing-fix commit:

```text
M  .planning/config.json
?? .agents/
?? .planning/phases/01-clean-device-footprint-first-launch/01-VERIFICATION.md
?? .planning/phases/02-real-lecture-import-processing/02-RESEARCH.md
?? docs/FLASH_DIAGNOSIS.md
```

Recommended next-agent sequence:

1. Treat `8a06718` and this document as the starting point; do not redo the
   beta 9 implementation.
2. Resolve the five release-trust fixture/workflow failures separately from
   the visual-artifact work.
3. Complete the full Phase 4 visual matrix listed above.
4. If flashing persists after that matrix, isolate the smallest reproducible
   state transition before changing deferred GPU, DPI, or renderer policy.

The beta 9 release is complete, but the complete visual acceptance gate is
not claimed complete based on the limited physical launch alone.
