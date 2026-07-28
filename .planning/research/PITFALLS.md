# Domain Pitfalls: Beta.6 Clean-Machine Reliability and Onboarding

**Domain:** Windows portable desktop reliability, runtime repair, onboarding, and release qualification  
**Researched:** 2026-07-27  
**Confidence:** HIGH for current-code failure modes; MEDIUM for the new signed-manifest protocol until its canonical format and key-rotation policy are specified.

## Critical Pitfalls

### Pitfall 1: Fresh and upgraded profiles resolve different—and sometimes invalid—runtimes

**What goes wrong:** A fresh config starts with every executable/model path empty, while an upgraded config can retain a stale install-relative path, an old model, or a custom optional engine. Current FFmpeg discovery can silently choose `PATH`; Whisper discovery only selects the first `.bin` when no saved model exists. A packaged runtime can therefore be present but unavailable to processing, or a new base model can fail to become the required default on upgrade.

**Why it happens:** Discovery is currently split between `ConfigManager.autodetect_ffmpeg()` and diagnostics-only `autodetect_whisper()` ([config_manager.py:125-172](../../lecturepack/infrastructure/config_manager.py#L125-L172)). `LecturePackAdapter` then rejects missing Whisper paths before engine resolution ([engine_adapter.py:1407-1431](../../app/desktop/engine_adapter.py#L1407-L1431)).

**Consequences:** Clean machines reach a delayed “configure Whisper” error; upgrades accidentally use stale binaries; a user’s healthy CUDA/custom choice can be overwritten; `PATH` makes behavior machine-dependent.

**Prevention:** One bootstrap service must inventory the exact application-relative CPU payload first, validate it, and persist canonical resolved paths plus payload identity. Run this before normal adapter readiness. Migrate beta.6 upgrades to `ggml-base.en.bin` as the selected default only when the prior selection is the old/default value; retain a healthy explicit custom/CUDA selection independently. Treat CPU as mandatory recovery runtime and optional engines as separately selected accelerators.

**Detection:** Parameterize fresh config, beta.5-style blank config, stale install path, custom model, healthy CUDA/custom engine, broken CUDA/Vulkan engine, and payload-identity change. Assert exact chosen CPU paths, default-model migration, preserved optional preference, and a visible fallback notice.

### Pitfall 2: “Found on disk” is mistaken for a usable executable/DLL/model runtime

**What goes wrong:** The package gate only tests nonempty files and any `ggml-cpu-*.dll`; it never launches ffmpeg, ffprobe, or Whisper, nor proves the pinned model and DLL set load together.

**Why it happens:** `check_clean_state()` is deliberately a filesystem-only unit-testable check ([build.py:95-146](../../app/packaging/build.py#L95-L146)); `bundle_engine()` copies a variable CPU-DLL set ([build.py:159-199](../../app/packaging/build.py#L159-L199)). Antivirus quarantine, an architecture mismatch, missing transitive DLL, or corrupt model passes that check.

**Consequences:** The first real lecture becomes the smoke test, often after a long import; broken installs are reported as a job error rather than blocked at setup.

**Prevention:** Define an immutable required-runtime inventory (relative path, byte size, SHA-256, release/payload identity). Do lightweight inventory/hash checks every launch. On first launch, repair/update, or identity change, run bounded `QProcess` smokes: `ffmpeg -version`, `ffprobe -version`, and CPU `whisper-cli` using a bundled non-user smoke input and `ggml-base.en.bin`. Capture stdout/stderr, exit status, elapsed time, and timeout reason; kill only the smoke process tree on expiry. Do not create a job to validate runtime.

**Detection:** Simulate removal and byte corruption independently for ffmpeg, ffprobe, CLI, every mandatory DLL, model, and the CPU backend DLL glob. Add hangs/nonzero exits to the existing subprocess fixtures; assert a hard gate with component-specific diagnostics and no main-app activation.

### Pitfall 3: Startup ordering permits normal UI/jobs before runtime health is known

**What goes wrong:** `main()` constructs and shows `MainWindow` immediately ([main.py:182-195](../../app/desktop/main.py#L182-L195)); adapter `on_ui_ready()` reconciles and pushes jobs, starts optional probes, then loads a completed job ([engine_adapter.py:951-971](../../app/desktop/engine_adapter.py#L951-L971)). A late setup dialog cannot be a hard gate and permits contradictory “available” UI before validation.

**Prevention:** Add an explicit controller startup state machine: `ASSESSING → HEALTHY | SETUP_REQUIRED → REPAIRING → HEALTHY | FAILED`. Do not call normal adapter readiness, job activation, navigation, or demo launch until `HEALTHY`. The setup UI may only retry, open diagnostics, consent to repair, or exit. Keep UI rendering/bridge in the UI/controller layer, validation policy in services, and file/process work in infrastructure.

**Detection:** Fake a slow successful smoke, missing runtime, timeout, and repair success. Assert no `on_ui_ready`, no job signals, and no optional-engine network/probe side effect prior to healthy transition; after healthy transition, assert exactly one readiness call.

### Pitfall 4: Repair trusts transport metadata or leaves a mixed runtime after failure

**What goes wrong:** A repair flow that trusts a release JSON before signature verification, downloads files directly into `bin/`, or replaces one file at a time admits tampered content and mixed-version DLL/model combinations. A failed final swap can destroy the last known-good runtime.

**Why it happens:** Existing CUDA-pack code verifies one archive hash but extracts directly into its destination ([cuda_pack.py:46-76](../../app/desktop/cuda_pack.py#L46-L76)); that is useful precedent for streamed progress/cancel but not sufficient for core-runtime trust or rollback.

**Prevention:** Embed a project public key; verify the exact-running-version manifest signature before trusting asset names, URLs, or file hashes. Download only after explicit “Repair all” consent, into a dedicated staging directory. Verify every staged required inventory entry, then install the complete set transactionally: preserve the old runtime, replace only runtime-owned paths, run full local validation, commit only on success, and restore the previous set on any exception/cancel/crash. Never touch `LECTUREPACK_DATA_DIR`, jobs, exports, settings other than health facts, or optional per-user engine directories. Specify a non-admin install-directory policy before implementation—staging in a writable data area does not solve a non-writable final swap.

**Detection:** Use synthetic signed manifests and locally served/fixture payloads. Cover bad signature, wrong app version, unknown/duplicate/path-traversal inventory entry, hash mismatch, missing required file, cancellation mid-download, extraction failure, swap failure, validation failure after swap, and restart recovery. Each must preserve the prior runtime byte-for-byte and keep the gate closed; only a fully valid exact release may enter the app.

### Pitfall 5: Optional-engine damage blocks a healthy CPU-only recovery path

**What goes wrong:** Broken CUDA/Vulkan/custom settings are treated as a required-runtime failure or overwritten during bootstrap. This is particularly harmful on AMD/Intel systems where CUDA cannot run.

**Evidence:** `EngineRegistry.resolve()` already degrades unavailable CUDA/Vulkan requests to CPU and records a reason ([transcription_engines.py:230-272](../../lecturepack/infrastructure/transcription_engines.py#L230-L272)).

**Prevention:** Gate only the validated bundled CPU inventory. Preserve a healthy optional selection across upgrades; when it becomes unavailable, retain a diagnosable preference if appropriate but resolve the run to CPU and visibly explain why. Never download an optional pack or contact a network endpoint merely to decide startup health.

**Detection:** Reuse CUDA registry/pack seams to test CPU-only, NVIDIA-present, missing NVIDIA driver, missing optional executable/DLL, and Vulkan unavailable cases. Assert CPU entry without repair, no network request, and one human-visible fallback status.

### Pitfall 6: Demo data leaks into real library/profile or cleanup deletes user data

**What goes wrong:** Running a demo through the normal adapter/configuration persists a job, activates it at next launch, or contaminates recents. Conversely, a broad temp cleanup can remove a real profile or an unrelated temp directory.

**Prevention:** `DemoSessionService` owns a per-launch session root under one dedicated demo root, with a sentinel containing a generated session ID. It creates a session-scoped config/controller and routes only transient status to the tour. Normal exit, explicit Exit demo, cancellation, error, and next-startup sweep must be idempotent. The sweeper may remove only a canonical child of the demo root that has the sentinel; never glob `%TEMP%`, jobs, exports, or `LECTUREPACK_DATA_DIR`. The bundled original synthetic asset stays immutable; its derived files remain session-local.

**Detection:** Assert normal library pushes never contain demo jobs, real active job remains `None`, source video is unchanged, and session root disappears after every terminal path. Simulate an interrupted process with a sentinel session, missing sentinel, malformed/symlink-like/out-of-root path, cleanup exception, and simultaneous real job. Existing active-job clearing contract is in [tests/test_workspace_ownership.py:145-175](../../tests/test_workspace_ownership.py#L145-L175).

### Pitfall 7: A “real demo” masks cancellation, process leak, and crash-recovery defects

**What goes wrong:** A scripted happy-path demo with mocked output proves only UI choreography. Cancellation can leave a live QProcess/QThread, a locked workspace, or partial files; crash cleanup may race with a still-running worker.

**Prevention:** Use the real local import-to-export pipeline against a bundled 45–90 second synthetic asset, but cap every external/internal stage with bounded timeouts appropriate to the machine and explicitly differentiate timeout from user cancellation. Propagate one cancellation token through demo orchestration and wait for worker/process ownership to settle before cleanup. Persist only session-local state needed for a safe sweep. Never reuse `QThread.terminate()` for demo cleanup.

**Detection:** Run demo success, cancel during import/audio/transcribe/detection/export, intentional CLI hang, worker failure, and simulated process death. Assert no remaining child process, no normal jobs/config changes, valid cleanup on retry, and one terminal UI state. Existing cancellation precedents include `CancellationToken` ([transcription_backends.py:55-66](../../lecturepack/services/transcription_backends.py#L55-L66)) and bounded worker shutdown ([transcription_backends.py:403-410](../../lecturepack/services/transcription_backends.py#L403-L410)); they must not be mistaken for full demo coverage.

### Pitfall 8: Visual/onboarding fixes regress the intentional beta.5 shell

**What goes wrong:** Fixing flicker by globally removing transitions, rebuilding the DOM during theme selection, or altering legacy Qt Widgets instead of the shipping WebEngine shell changes the established design. An overlay can also reflow the active workspace or trap keyboard focus.

**Prevention:** Restrict work to unintended artifacts in `app/ui`; apply theme state as one root attribute/class change in a single render boundary, preserve documented motion/shadows/pressed effects, and use CSS ellipsis plus tooltip/accessible full name at render time—not configuration truncation. Gate/tour overlays must be isolated from ordinary layout and have keyboard-operable Next, Back, and Exit controls.

**Detection:** Preserve static token guards in [tests/test_webview_theme.py:17-44](../../tests/test_webview_theme.py#L17-L44) and source-level UI guards in [tests/test_webview_ui_fixes.py:1-10](../../tests/test_webview_ui_fixes.py#L1-L10). Add screenshot/video/manual comparison for both themes, long model names, repeated open/close of gate/tour, window resize, and navigation while a real job exists. Check no console errors and no layout shift beyond the contract.

### Pitfall 9: “Offline” is asserted while startup, repair, or demo makes an implicit request

**What goes wrong:** A failed optional probe, update check, model lookup, or repair retry can reach the network during a supposedly offline fresh-profile demo. That violates local-first promises and produces misleading runtime failures.

**Prevention:** Make all non-local requests opt-in and service-owned. Bootstrap inventory/smoke and demo pipeline must use bundled CPU assets only; repair transport starts solely after explicit consent and only targets the exact official release. Tests must deny outbound connections rather than merely omit internet credentials.

**Detection:** Run packaged fresh-profile smoke with socket/HTTP interception or firewall harness that fails any non-localhost request. Assert healthy offline startup, demo, review, export, retry-validation, and optional-engine fallback. Separately assert consented repair uses only its allowlisted official URL and does not send job/source/profile content.

### Pitfall 10: Windows path and antivirus cases are deferred to release day

**What goes wrong:** Shell-string invocation breaks spaces/non-ASCII paths; portable install locations may be read-only; antivirus may remove a single DLL/model after extraction. The current legacy validator hard-codes the owner profile and an owner OneDrive lecture ([lecturepack/app.py:6-119](../../lecturepack/app.py#L6-L119)), so it is neither portable nor safe release evidence.

**Prevention:** Pass executable and argument lists to `QProcess`/safe process APIs; never construct a shell command from transcript, video, install, or profile text. Ensure every packaged check starts with a newly created `LECTUREPACK_DATA_DIR`, including subprocesses. Test a writable external data root independent of a non-admin portable folder. Treat “file disappears/read fails during validation” exactly as a damaged runtime gate, and never attempt to delete/quarantine the original lecture.

**Detection:** Package-copy tests use paths containing spaces and non-ASCII characters, a non-admin/read-only install simulation, data-dir override, and post-inventory deletion/corruption of each component. Keep the existing disposable-profile contract in [tests/test_data_dir_override.py:20-109](../../tests/test_data_dir_override.py#L20-L109); explicitly prohibit invoking `run_packaged_validation` until it is replaced/refactored.

## Moderate Pitfalls

### Timeout values hide hardware regressions or create false failures

**What goes wrong:** One global timeout is too short for the minimum i7 CPU/cold disk or too long for a missing DLL/OneDrive placeholder hang.

**Prevention:** Give each operation a documented budget: quick version probes, bounded model-load smoke, bounded demo stages, and an overall release-smoke deadline. Record elapsed time and distinguish startup timeout, process error, cancellation, and assertion failure. Calibrate on the physical CPU-only minimum before freezing values; test deterministic short budgets with mock fixtures.

### Release testing uses mocks as proof of a packaged integration

**What goes wrong:** Unit fixtures prove policy but never discover a PyInstaller omission, DLL loader failure, or raw-path startup bug.

**Prevention:** Keep unit fault matrices fast, then require a disposable onedir subprocess smoke and a visible GUI fresh-profile smoke. Mocks may prove branches; physical Windows matrix is release evidence.

### Repair/logging leaks paths or turns user-provided text into commands

**What goes wrong:** Diagnostic output exposes profile/source paths excessively or helper scripts interpolate hostile data.

**Prevention:** Structured logs with redacted/download-only repair metadata; process argument lists; no transcript/video text as executable input; sanitize manifest display values. Preserve P1–P7.

## Minor Pitfalls

### Existing jobs disappear while enforcing empty launch

**What goes wrong:** Removing auto-load also suppresses library refresh or emits stale job-scoped payloads.

**Prevention:** Reconcile and emit library list, then call the single active-job setter with `None`; leave explicit `open_job()` unchanged. The setter centrally stamps job-scoped signals ([engine_adapter.py:740-772](../../app/desktop/engine_adapter.py#L740-L772)).

### Signed-manifest design becomes irreversibly underspecified

**What goes wrong:** Implementation chooses a key/signature/canonical JSON scheme ad hoc, blocking secure rotation or interoperable release tooling.

**Prevention:** Make canonical serialization, algorithm, key ID/rotation, expiry/version binding, inventory schema, and official asset layout a security-focused phase deliverable before coding repair transport.

## Reusable Fixtures and Test Seams

| Reusable seam | Exact location | Reuse for beta.6 |
|---|---|---|
| Disposable adapter profile | [tests/test_adapter_startup.py:18-26](../../tests/test_adapter_startup.py#L18-L26) | Startup coordinator/adapter smoke without real data root. Convert to an environment-variable subprocess fixture for packaged tests. |
| Environment override contract | [tests/test_data_dir_override.py:20-109](../../tests/test_data_dir_override.py#L20-L109) | Fresh/upgraded profile, hostile writable root, and proof no validation touches user data. |
| Minimal clean onedir factory | [tests/test_beta3_packaging.py:19-33](../../tests/test_beta3_packaging.py#L19-L33) | Inventory/hash damage cases; extend it with manifest/signature and staged runtime copies. |
| Existing clean-state faults | [tests/test_beta3_packaging.py:36-91](../../tests/test_beta3_packaging.py#L36-L91) | One-required-component-at-a-time missing/empty/corrupt matrix. |
| Mock CLI fixtures | [tests/fixtures/mock_ffmpeg.py](../../tests/fixtures/mock_ffmpeg.py), [tests/fixtures/mock_ffprobe.py](../../tests/fixtures/mock_ffprobe.py), [tests/fixtures/mock_whisper.py](../../tests/fixtures/mock_whisper.py), [tests/fixtures/mock_whisper_streaming.py](../../tests/fixtures/mock_whisper_streaming.py) | Fast smoke success/nonzero/hang/progress/cancel paths; add an explicit no-output hang fixture rather than using real binaries. |
| Existing optional-pack fakes | [tests/test_cuda_pack.py:115-145](../../tests/test_cuda_pack.py#L115-L145) | Progress, download cancellation, hash/install error seams—adapt policy but do not reuse direct-to-live install mechanics. |
| Ownership host/backend | [tests/test_workspace_ownership.py:67-175](../../tests/test_workspace_ownership.py#L67-L175) | Empty launch, job-signal stamping, demo isolation, no late payload after exit. |
| Qt baseline | [tests/conftest.py:1-26](../../tests/conftest.py#L1-L26) | Offscreen controller/bridge tests; supplement with a separate visible/manual packaged GUI gate. |
| Web visual guards | [tests/test_webview_theme.py:17-44](../../tests/test_webview_theme.py#L17-L44), [app/verify_ui.py:19-68](../../app/verify_ui.py#L19-L68) | Token/markup regressions plus screenshot capture for artifact-only changes. |

## Phase-Specific Warnings and Required Evidence

| Phase topic | Likely pitfall | Required automated evidence | Required release/manual evidence |
|---|---|---|---|
| Runtime inventory and bootstrap | Discovery order or upgrade migration changes a valid user choice | Fresh/upgrade/stale-path/payload-identity matrix; assert exact paths, default model, config atomicity, and no adapter readiness pre-health | Fresh/offline first launch on CPU-only machine |
| CLI/DLL/model validation | Presence-only check misses loader/model failure or hang | Mock CLI version/model-load success, exit failure, timeout, each missing/corrupt component | Packaged onedir subprocess captures actual stdout/stderr/exit/duration |
| Setup gate and repair | Unsigned/mixed/partial install enters app | Invalid signature/version/hash/inventory, cancel, swap/validation failure, rollback-byte comparison, success re-entry | Consent screen names source/version; offline repair retry/diagnostics/exit flow |
| Optional engine fallback | GPU issue hard-gates healthy CPU or overwrites selection | CPU/CUDA/Vulkan availability permutations with zero network calls | NVIDIA and AMD/Intel machines show correct notice and CPU recovery |
| Empty home and demo | Demo persists/deletes real data; late signals revive it | No demo in library; active job `None`; cleanup success/cancel/error/crash sweep/idempotency/out-of-root refusal | Replay demo, Exit demo, restart after forced termination; inspect real profile unchanged |
| Visual artifact preservation | “Fix” alters beta.5 aesthetics or produces layout shift | Token/DOM guards; long-label ellipsis/tooltip; overlay keyboard tests | Beta.5/beta.6 screenshots/video in light/dark, resize, repeated toggle/tour |
| Packaged/offline/hostile path gate | Test uses developer data or implicit network | Spawn app with disposable `LECTUREPACK_DATA_DIR`; blocked-network assertion; spaces/non-ASCII/read-only-install simulations | CPU-only, NVIDIA, AMD/Intel × fresh/upgraded × online-repair/offline-demo matrix signed by tester |

## Sources

- [Milestone context](../MILESTONE-CONTEXT.md) — locked beta.6 behavior, repair trust boundary, and physical release matrix.
- [Project context](../PROJECT.md) — authoritative beta.5 debt and success criteria.
- [Approved architecture](../../docs/ARCHITECTURE.md) — layer, QProcess/QThread, atomic state, and crash-recovery rules.
- [Configuration/discovery implementation](../../lecturepack/infrastructure/config_manager.py) — current blank defaults and nondeterministic discovery behavior.
- [Engine selection implementation](../../lecturepack/infrastructure/transcription_engines.py) — optional-engine CPU fallback seam.
- [Desktop lifecycle/ownership implementation](../../app/desktop/engine_adapter.py) and [desktop entry point](../../app/desktop/main.py) — ordering and empty-home risks.
- [Packaging implementation](../../app/packaging/build.py) and [unsafe legacy validator](../../lecturepack/app.py) — current package proof limitations.
- [Existing test fixtures and contracts](../../tests/test_adapter_startup.py), [data-dir override](../../tests/test_data_dir_override.py), [package gate](../../tests/test_beta3_packaging.py), [workspace ownership](../../tests/test_workspace_ownership.py), and [CUDA-pack tests](../../tests/test_cuda_pack.py).
