# Architecture Research: beta.6 Clean-Machine Reliability and Onboarding

**Project:** LecturePack v0.9.0-beta.6  
**Scope:** Runtime bootstrap/validation and repair, setup gate, empty-home ownership, real isolated demo, visual-artifact-only fixes, and packaged release evidence.  
**Confidence:** HIGH for the as-built boundary analysis (repository evidence); MEDIUM for the future repair transport until the signed release-manifest format is specified.

## Recommended Architecture

Beta.6 should add one application-lifecycle path *before* the existing desktop adapter's normal `on_ui_ready()` flow. Keep the approved four layers intact:

```text
Layer 4 UI (QWebEngine UI)                 Layer 3 controller/adapter
SetupGate / WelcomeTour / DemoOverlay  ->  DesktopStartupCoordinator
                                              |
Layer 2 services                         RuntimeBootstrapService
                                        RuntimeRepairService
                                        DemoSessionService
                                        PackagedReleaseSmokeService
                                              |
Layer 1 infrastructure                   RuntimeInventory/Validator
                                        SignedManifestVerifier
                                        TransactionalRuntimeInstaller
                                        ConfigManager + FileManager
                                        QProcess smoke runner

Normal path:  main.py -> Bootstrap -> [healthy] -> Adapter.on_ui_ready()
Repair path:  Setup gate -> repair service -> staging/verify/swap -> revalidate -> Adapter.on_ui_ready()
Demo path:    Welcome tour -> DemoSession -> temporary ConfigManager/JobController -> real pipeline -> cleanup
```

`desktop.main` is composition/UI bootstrap, not a place to implement discovery, hash validation, downloading, or file replacement. It should construct a **controller-layer** `DesktopStartupCoordinator` after `QApplication` exists, then show either a gate/welcome view or the main Web UI. The coordinator talks only to service-layer APIs and passes immutable status snapshots to the bridge. Services own policy; infrastructure owns paths, signatures, hashes, staging, atomic file operations, and executable smoke invocation.

This is necessary because normal desktop startup now enters `MainWindow` immediately ([app/desktop/main.py:182-195](../../app/desktop/main.py#L182-L195)), while normal adapter readiness starts job reconciliation and asynchronous probes ([app/desktop/engine_adapter.py:951-971](../../app/desktop/engine_adapter.py#L951-L971)). Setup must complete before either job-derived UI data or optional-engine diagnostics can assert that processing is available.

## Component Boundaries and Ownership

| Layer | New / modified component | Responsibility | Must not own |
|---|---|---|---|
| UI | `app/ui` setup gate, welcome-tour, and demo controls; `bridge.py` status/action signals | Render a compact status from coordinator, obtain consent for repair/demo, provide exit/next/back | Payload hashes, download URLs beyond displayed metadata, job creation, direct filesystem calls |
| Controller | `DesktopStartupCoordinator` (new, likely `app/desktop/startup.py`) | Explicit startup state machine; gate normal adapter activation; relay service signals to bridge; start/exit demo session | Verification algorithms, downloading, replacement mechanics |
| Controller | `LecturePackAdapter` (modified) | Remain the normal-job owner only after readiness; begin with no active job; explicitly open jobs | Selecting an existing job on startup; demo persistence |
| Service | `RuntimeBootstrapService` (new) | Reconcile config with bundled CPU recovery runtime, choose light/full validation, persist healthy discovered paths, preserve a healthy optional engine | UI widgets; network transport; raw `os.replace` calls |
| Service | `RuntimeRepairService` (new) | After explicit consent, obtain exact-release manifest/payload, delegate signature/hash verification and transactional installation, revalidate | Silently repairing; mixing releases; touching jobs/user study data |
| Service | `DemoSessionService` (new) | Create an isolated temporary data root, run the real import-to-export path through a scoped adapter/controller, cleanup/sweep sessions | Writing under `jobs/` in the real profile; synthetic data as a normal library job |
| Service | `PackagedReleaseSmokeService` or test driver (new/modified) | Disposable-profile executable + pipeline smoke, returning structured evidence | Mutating a developer's or user's data root |
| Infrastructure | `RuntimeInventory` / `RuntimeValidator` (new) | Canonical required-file set, payload identity, file hash/size checks, CPU CLI/DLL/model smoke checks | Setup UI policy, optional GPU selection policy |
| Infrastructure | `SignedManifestVerifier`, `TransactionalRuntimeInstaller` (new) | Embedded public-key verification; SHA-256 verification; stage -> validate -> replace -> rollback | Download consent/state; job/config business policy |
| Infrastructure | `ConfigManager` (modified) | Persist only resolved runtime facts and validation identity/result; expose safe app/data paths | A long-running startup state machine or UI behavior |
| Infrastructure | `FileManager` (modified as needed) | Atomic config writes and safe directory replacement/rollback primitives | Signing policy or download source selection |

### Files that must be treated as distinct data domains

| Domain | Location / owner | Rule |
|---|---|---|
| Bundled runtime | install-relative `bin/` and `models/` | Immutable during healthy launch; repair replaces only the exact signed runtime payload transactionally. |
| User configuration | `LECTUREPACK_DATA_DIR/config.json`, `ConfigManager` | Persist resolved paths and validation metadata, never runtime binaries, manifests, job content, or credentials. The disposable-profile seam already exists in [config_manager.py:9-13](../../lecturepack/infrastructure/config_manager.py#L9-L13). |
| Source-derived lecture artifacts | real `data_dir/jobs/<id>` | Continue through existing `Job`/controller pipeline; never treated as demo content or repair input. |
| User-authored study data | per-job `study.json` | Remains job-scoped and must never be overwritten by bootstrap, repair, or demo cleanup. |
| Demo source/derived artifacts | generated package asset + per-launch temporary workspace outside real data dir | Original synthetic asset is not a user lecture; all derived demo files are transient and excluded from library/recents. |
| AI-generated data | existing clearly marked AI/job artifacts | Not an input to runtime validation, repair manifests, or demo source material. |

## Startup State Machine and Data Flow

```text
QApplication / DesktopStartupCoordinator
  -> RuntimeBootstrapService.assess(app_version, payload_identity, config)
       -> RuntimeInventory.required_cpu_payload()
       -> light file/hash check every launch
       -> full QProcess smoke only first launch, after update/repair, identity change
  -> Healthy: persist resolved CPU paths + validation record
       -> Main UI / Adapter.on_ui_ready()
       -> reconcile jobs; emit library; set_active_job(None)
       -> after first healthy validation: offer welcome choice
  -> Unhealthy: SetupGate (main UI unavailable)
       -> explicit Repair all consent
       -> RuntimeRepairService
       -> signed exact-version manifest -> hash each staged file -> atomic swap/rollback
       -> full validation -> healthy transition; no restart
```

**Ordering is a correctness requirement.** Do not construct/activate normal `LecturePackAdapter` readiness until `RuntimeBootstrapService` has reached `HEALTHY`. `ConfigManager` currently initializes all four processing paths empty ([config_manager.py:31-58](../../lecturepack/infrastructure/config_manager.py#L31-L58)); only `MainWindow` calls both auto-detect methods ([main_window.py:178-180](../../lecturepack/ui/main_window.py#L178-L180)), and the Web adapter does not. The current adapter later rejects a local transcription run when the executable/model paths are empty ([engine_adapter.py:1407-1432](../../app/desktop/engine_adapter.py#L1407-L1432)). Centralizing bootstrap removes that race/contradiction.

`RuntimeBootstrapService` should resolve the bundled CPU runtime regardless of an optional engine preference. It writes the canonical bundled `whisper_exe`, `whisper_model`, `ffmpeg_exe`, and `ffprobe_exe` only when each is valid; it must preserve a healthy user CUDA/custom selection separately. At run time `EngineRegistry.resolve()` already degrades unavailable CUDA/Vulkan selections to CPU ([transcription_engines.py:218-266](../../lecturepack/infrastructure/transcription_engines.py#L218-L266)); beta.6 should surface that fallback notice, but never use an optional-engine problem to block entry when the validated bundled CPU runtime works.

Full smoke validation must run the CPU CLI through `QProcess` (or a service-owned subprocess only for a headless packaging driver) with bounded timeout and a known non-user input/model. File presence alone is insufficient: `check_clean_state()` currently accepts only nonempty files and `ggml-cpu-*.dll` presence ([build.py:132-145](../../app/packaging/build.py#L132-L145)). A smoke must demonstrate executable launch and model/DLL load without importing any lecture or creating a job.

## Setup Gate and Repair Transaction

The hard gate is an application-level controller state, not a diagnostic dialog and not a processing-time error. Its allowed actions are **Repair all** (explicit network consent), retry validation, open diagnostics, and exit. It must prevent adapter `on_ui_ready()` and all job-opening/navigation actions until `HEALTHY`.

Repair transaction:

1. Coordinator requests user consent and displays official source, exact app version, and payload identity.
2. `RuntimeRepairService` requests only the official project release assets for the running version.
3. `SignedManifestVerifier` verifies the embedded-public-key signature before trusting file names, URLs, or hashes.
4. Download all payload into an install-adjacent or user-writable staging directory; verify every SHA-256 and required inventory entry.
5. `TransactionalRuntimeInstaller` backs up only runtime-owned files, replaces the whole required set as a unit, runs full local validation, then commits; on any failure it restores the prior runtime.
6. Bootstrap re-assesses and coordinator enters the main app automatically.

Do not call repair from `ConfigManager`, `EngineRegistry`, or a UI event handler. Those components lack user-consent context and would make network behavior implicit. Do not merge repaired files one at a time into the live `bin/`: that violates the exact-version/no-mixed-runtime constraint and makes a partial DLL set runnable only unpredictably.

## Empty Launch, Job Ownership, and Demo Isolation

Normal launch must call `_set_active_job(None)` after job reconciliation and library emission. Remove the startup call to `_load_latest_completed_job()` rather than altering `open_job()`; the latter is the intentional explicit selection path ([engine_adapter.py:1028-1059](../../app/desktop/engine_adapter.py#L1028-L1059)). The adapter already has the correct single ownership setter and job-stamped signals ([engine_adapter.py:740-772](../../app/desktop/engine_adapter.py#L740-L772)); preserve it. Existing tests prove clearing `active_job` empties the workspace and that every job-scoped payload has an owner ([tests/test_workspace_ownership.py:74-145](../../tests/test_workspace_ownership.py#L74-L145)).

The demo must not invoke the normal adapter with the normal `ConfigManager`. Instead `DemoSessionService` creates an application-generated session id and a temporary root (for example `%TEMP%/LecturePack-demo/<session-id>`), instantiates a session-scoped config/controller with that root, and exposes only transient progress/review/export events to the tour. It imports the bundled original synthetic video through the real pipeline, but its `jobs/` path is transient, it is never passed to `_push_jobs()` for the real library, and cleanup is idempotent. A startup sweeper removes only directories bearing a demo-session sentinel and safely contained under the dedicated demo root; it must never sweep generic temp folders or real `LecturePackData` directories.

This preserves the required data provenance: a packaged demo asset is not source-derived user content, and demo output is neither source-derived lecture content nor user study data. The demo may show produced material as an instructional preview, but must label it as demo output and never offer it as a persisted lecture.

## Visual-Artifact Fix Boundary

The Web UI is the active product shell (`QWebEngineView` plus QWebChannel, [app/desktop/main.py:1-5](../../app/desktop/main.py#L1-L5)), so visual fixes belong in `app/ui` plus narrow bridge/controller scheduling changes—not in the legacy Qt-widget `lecturepack/ui/main_window.py` unless a shared defect is demonstrably there. The old widget shell currently applies the theme then rebuilds job cards after theme changes ([main_window.py:618-633](../../lecturepack/ui/main_window.py#L618-L633)); the Web shell has a different lifecycle.

Recommended rules:

- Batch CSS custom-property/theme class changes in one render boundary (`requestAnimationFrame` or a single root-class operation); do not animate colors during the atomic palette swap.
- Preserve documented motion, hard shadows, and pressed/embedded effects. `app/ui/app.css` explicitly marks its values and animations as design, not tuning targets ([app.css:1-2](../../app/ui/app.css#L1-L2)). Limit edits to known repaint/overflow/layout-jump defects.
- Apply model-name truncation at the UI rendering boundary with an accessible tooltip/full label. Do not truncate persisted configuration or adapter payloads.
- Keep the setup gate/tour overlay geometry isolated from normal workspace layout so showing/hiding it cannot reflow an active lecture page.

## Packaged Release Gate Architecture

Keep build-time, packaged-runtime, and physical-machine evidence separate:

| Gate | Owner | Evidence |
|---|---|---|
| Build inventory | `app/packaging/build.py` | Required payload and clean-state checks, extended to emit/version the signed inventory. Existing `bundle_engine()` copies FFmpeg, CPU CLI/DLLs, and base model ([build.py:159-199](../../app/packaging/build.py#L159-L199)). |
| Disposable packaged smoke | headless `PackagedReleaseSmokeService` / test driver | Set `LECTUREPACK_DATA_DIR` to a new disposable root; execute app/runtime checks and bundled demo workflow; capture structured stdout/logs. |
| GUI fresh-profile smoke | test harness/manual scripted run | Gate state, healthy entry, empty library ownership, opt-in tour, cancellation/cleanup. |
| Damage/repair matrix | disposable copies only | Remove/corrupt each required component independently; assert hard gate, signature/hash refusal, rollback, re-entry. |
| Physical matrix | release process | CPU-only, NVIDIA, AMD/Intel; fresh/upgraded; offline and hostile paths. |

Never reuse the existing `run_packaged_validation` behavior until it is refactored behind the disposable-profile service: PROJECT.md flags it as hard-coding owner paths and mutating real user data. The pre-existing `LECTUREPACK_DATA_DIR` precedence is the correct seam, and adapter startup tests already use a temporary data directory ([tests/test_adapter_startup.py:16-61](../../tests/test_adapter_startup.py#L16-L61)).

## Current Boundary Violations / Complications

1. **Split discovery ownership:** `ConfigManager.autodetect_ffmpeg()` can persist bundled or system PATH binaries ([config_manager.py:110-147](../../lecturepack/infrastructure/config_manager.py#L110-L147)), while Whisper discovery is diagnostics-oriented and only picks the first model when no saved model exists ([config_manager.py:149-172](../../lecturepack/infrastructure/config_manager.py#L149-L172)). This is not deterministic clean-machine validation.
2. **Startup contradicts empty ownership:** `on_ui_ready()` intentionally auto-loads the latest completed job ([engine_adapter.py:969-971](../../app/desktop/engine_adapter.py#L969-L971)), violating beta.6's no-active-lecture launch requirement.
3. **Packaging is presence-only:** the current clean-state gate cannot prove binaries launch, DLL dependencies load, or model compatibility.
4. **Layer ambiguity in desktop shell:** `app/desktop/main.py` composes QWebEngine, bridge, assets, and adapter directly; adding repair logic there would skip controller/service boundaries. Use a coordinator instead.
5. **UI duality:** the repository has both legacy PySide widget UI and the shipping WebEngine UI. Beta.6 planning must identify the Web UI as the visual/onboarding target to avoid parallel, inconsistent fixes.
6. **Release validation safety:** current project debt notes that packaged validation targets owner paths. All package tests must explicitly establish a disposable `LECTUREPACK_DATA_DIR` before process launch.

## Recommended Phase Dependencies and File Ownership

1. **Runtime contract and bootstrap** — add immutable runtime inventory/validator and bootstrap service; modify ConfigManager persistence and startup coordinator wiring. This must precede any gate, because the gate needs trustworthy status.
2. **Repair transaction and setup gate** — add signed-manifest verifier/installer, coordinator states, bridge/UI gate, and damage tests. Depends on the inventory contract.
3. **Empty normal ownership and guided demo** — remove auto-activation; add demo session service/tour and cleanup recovery. Depends on a healthy bootstrap path and stable bridge lifecycle.
4. **Visual artifact regressions** — focused `app/ui` fixes and screenshot/manual contract tests. Can run alongside demo UI work only if a single owner coordinates shared shell files.
5. **Packaged and physical release gate** — extend build manifest, headless disposable smoke, GUI/damage matrix, then collect physical hardware evidence. Depends on all prior functional phases.

Suggested ownership avoids conflicts: runtime infrastructure owns `lecturepack/infrastructure/{runtime_*,config_manager,file_manager}`; runtime services own `lecturepack/services/{runtime_*,demo_session,packaged_smoke}`; desktop controller/bridge owns `app/desktop/{startup,engine_adapter,bridge,main}`; onboarding/visual owns `app/ui/*` and bundled synthetic assets; packaging/release owns `app/packaging/build.py` plus validation drivers/tests. No phase should alter normal job schema merely to represent demo or repair state.

## Sources / Evidence

- [Milestone context](../MILESTONE-CONTEXT.md) — locked beta.6 behavior and constraints.
- [Project context](../PROJECT.md) — current technical debt and success criteria.
- [Approved architecture](../../docs/ARCHITECTURE.md) — four-layer and isolation rules.
- [ConfigManager](../../lecturepack/infrastructure/config_manager.py) — current discovery/persistence behavior.
- [Desktop adapter](../../app/desktop/engine_adapter.py) — startup and job-ownership behavior.
- [Packaging build gate](../../app/packaging/build.py) — current payload and clean-state checks.
- [Workspace ownership tests](../../tests/test_workspace_ownership.py) and [adapter startup tests](../../tests/test_adapter_startup.py) — existing enforceable seams.

## Open Design Inputs for Phase-Specific Research

- Exact signed-manifest canonicalization, key algorithm/rotation policy, and official release asset layout require a security-focused phase design before implementation.
- The installation directory may be non-writable; specify whether repair stages in a user-writable location and requests elevation only at final swap, or fails with a clear diagnostic. The product decision permits repair but does not yet define privilege UX.
- Define the smallest smoke input/CLI arguments that reliably prove model and DLL loading across supported CPU machines without expensive inference; verify against the pinned whisper.cpp binary during the runtime-contract phase.
