# Project Research Summary — Beta 6

**Project:** LecturePack v0.9.0-beta.6  
**Domain:** Windows-local, portable lecture-processing desktop application onboarding and runtime recovery  
**Researched:** 2026-07-27  
**Confidence:** MEDIUM-HIGH

## Executive Summary

Beta 6 is a clean-machine reliability and onboarding release for the existing Windows PySide6/PyInstaller onedir application, not a redesign or stack replacement. Its central product contract is that LecturePack must prove its bundled CPU processing runtime is usable before a user can enter the normal application. Experts should implement this as an explicit, pre-adapter startup state machine: locally inventory and validate the required FFmpeg, ffprobe, CPU Whisper CLI/DLLs, and `ggml-base.en.bin`; silently proceed only when healthy; otherwise present a hard, actionable setup gate. Normal job reconciliation, optional-engine probing, navigation, and demo launch cannot begin before the coordinator reaches `HEALTHY`.

The safe repair design is an exact-version, consented, signed, staged, transactional runtime installation below the writable `LECTUREPACK_DATA_DIR`, with an atomic activation record and prior generation retained for rollback. The immutable PyInstaller bundle remains the bundled source/fallback and is never patched in place. The full user journey then continues into an empty Home screen, an optional real isolated guided demo, artifact-only visual fixes in the shipping WebEngine UI, and a physical Windows release matrix. The main risks are security/availability mistakes in repair, introducing normal UI/job ownership before health is known, demo data crossing into user data, and proving only mocks rather than a packaged runtime. Mitigate them with strict layer ownership, fail-closed validation, disposable-profile package tests, bounded QProcess smokes, and required physical evidence.

## Decision Status: Locked Boundaries vs. Recommendations

### Locked for Beta 6

- Keep the selected Python 3.12, PySide6 6.11.x, PyInstaller onedir, four-layer architecture, QProcess/QThread split, JSON persistence, local-first privacy model, and existing CPU runtime inventory. No stack replacement or unrelated dependency is authorized.
- Required runtime admission set: FFmpeg, ffprobe, CPU Whisper CLI plus required DLLs, and the bundled base-English model. Healthy launches initialize silently; missing/corrupt required parts block entry behind a hard setup gate.
- Repair is user-consented only, targets the exact running application version on the official GitHub release, verifies a project-signed manifest and SHA-256 file hashes, installs transactionally, revalidates, and enters without restart. No offline repair import, manual per-file browsing, silent background repair, or release mixing.
- The bundled CPU runtime is always the validated recovery path. A healthy optional CUDA/custom selection persists through upgrade; an unavailable optional engine falls back visibly to CPU and never hard-gates a healthy CPU runtime.
- Startup shows an empty Home with existing jobs visible but inactive; it must not auto-open the latest completed lecture.
- First-success onboarding is opt-in (`Start guided demo` / `Skip for now`). The real, original 45–90 second synthetic demo is isolated, replayable, never a normal job, and cleaned up after success, cancellation, error, or crash.
- Preserve beta-5's visual language. Limit UI work to atomic theme changes and removal of unintended flicker, repaint artifacts, overflow, and layout jumps.

### Recommendations Requiring Phase Design (not new product scope)

- Use a `DesktopStartupCoordinator` before normal adapter readiness; place runtime policy in services and verification/file primitives in infrastructure.
- Use versioned runtime generations under the writable data directory plus atomically replaced `active.json`, rather than replacing live bundle files.
- Maintain a canonical required-runtime inventory shared by packaging, bootstrap, repair, and tests; light local checks run every launch and full CLI/DLL/model smokes run on first launch, update/repair, or payload-identity change.
- Keep repair UI concise and actionable: plain-language condition first, diagnostics/details second, exact source/version disclosed before `Download and repair`.

## Key Findings

### Stack and Trust Model

Use only the Python standard library (`urllib.request`, `json`, `zipfile`, `hashlib`, `hmac`, `pathlib`, `tempfile`, `os`, `shutil`) for exact-tag GitHub release lookup, downloads, archive handling, SHA-256 checks, staging, and atomic metadata publication. Reuse the existing atomic JSON-write pattern and onedir application-relative path resolution. QProcess remains the required external-tool boundary for the GUI runtime smoke; argument lists and Unicode `Path` values are mandatory for hostile Windows paths.

The source research recommends `cryptography`'s `Ed25519PublicKey` solely to verify the detached project-signed manifest. **This dependency is not approved. Adding `cryptography`, or any third-party verifier, remains a Phase 1 approval/ADR decision gate. Do not implement or imply an approved dependency before that decision.** Viable alternatives within the current approved stack are poor fits: unsigned release checksums/GitHub TLS do not establish the locked project-signature trust root; HMAC requires shipping a secret; a home-grown pure-Python verifier is unacceptable; Windows CNG, PowerShell, or `certutil` shell-outs add platform/subprocess/packaging variability and still require a security design decision. If the ADR declines a maintained verifier, beta 6 cannot truthfully claim signed-manifest repair under the present dependencies; it must not silently weaken the requirement.

### Features and User Experience

Table-stakes behavior is deterministic local preflight, a non-dismissible required-runtime gate, consented one-click repair, clear offline diagnostics, and automatic re-entry only after full revalidation. The UI must make optional-engine fallback informational, not blocking. First use must be productive but non-coercive: empty Home, a welcome choice, keyboard-operable contextual tour controls, a persistent exit action, and a real offline demo that explains review and export without persisting a fake lecture.

Differentiate through transparent provenance/progress, component-specific explanations, safe cancellation boundaries, replayable onboarding, and visual stability. Explicitly defer manual/offline repair packages, per-file repair selection, background update checks, tutorial expansion, alternate onboarding modes, UI redesign, new providers/accounts, telemetry, and cloud workflows.

### Architecture and Build Order

Keep the enforced UI → Controller → Service → Infrastructure layering. The recommended path is `main.py` composition → controller-layer `DesktopStartupCoordinator` → `RuntimeBootstrapService` → infrastructure inventory/validator and bounded QProcess smoke. Only the healthy transition invokes normal adapter readiness; then reconcile the library and set the active job to `None`. The repair path is gate → consent → `RuntimeRepairService` → signed-manifest verification/staging/transactional installation → full revalidation → healthy transition. Demo work is owned by `DemoSessionService` with session-scoped configuration/controller and a dedicated temporary root, never the real job/profile state.

The build/release path needs a canonical inventory and a disposable-profile smoke driver. Build inventory proves expected payload; packaged subprocess smoke proves CLIs/DLLs/model actually load; GUI smoke proves gate, ownership, onboarding, and cleanup; physical machines are final release evidence. Do not reuse the known unsafe legacy packaged validator that hard-codes owner data.

### Critical Pitfalls

1. **Presence-only or stale-path validation accepts a broken runtime.** Validate every required item and use bounded CLI/DLL/model smokes; persist paths only after proof and recheck on identity changes.
2. **Normal UI starts before health is known.** Gate `on_ui_ready()`, job signals, navigation, optional probing, and demo behind one controller state machine.
3. **Repair trusts transport metadata or partially replaces live files.** Authenticate the exact-version manifest before its contents are trusted; verify all staged content; switch a complete generation atomically; preserve the prior generation.
4. **Optional GPU failures hard-gate CPU recovery.** Validate only the required CPU set for admission, preserve healthy optional preferences, and surface CPU fallback as a notice.
5. **Demo cleanup contaminates or deletes user data.** Use a session-id sentinel beneath a dedicated demo root; refuse out-of-root/missing-sentinel cleanup and keep demo events out of the normal library.
6. **Visual fixes or mock-heavy tests create false confidence.** Change the WebEngine shell only, preserve intentional styling/motion, and require package/GUI/physical evidence in addition to unit tests.

## Implications for Requirements and Roadmap

### Phase 1: Runtime Contract, Bootstrap, and Security Decision Gate

**Rationale:** Every later user-facing behavior needs a reliable answer to “can this app process a lecture?” This phase removes the empty-config/discovery contradiction before UI, repair, or demo work is allowed to depend on it.

**Delivers:** Canonical CPU runtime inventory and payload identity; light/full validation policy; bounded QProcess executable/DLL/model smoke; bootstrap service; coordinator state boundaries; persisted validated runtime facts; default base-English model migration; optional-engine CPU fallback policy.

**Requirements addressed:** Deterministic preflight, silent healthy initialization, CPU recovery path, component-specific status, no pre-health adapter activation.

**Pitfalls avoided:** Presence-only validation, stale config paths, startup ordering, GPU hard-gates, GUI-thread/shell-command path errors.

**Mandatory approval-sensitive output:** An ADR decides whether to add `cryptography` or another verifier. It must define the approved verifier/version/packaging check, Ed25519/key encoding, canonical manifest bytes, key custody/rotation, schema/version binding, exact asset names, expiry policy, and release ownership. If unresolved, Phase 2 repair implementation is blocked—not downgraded.

### Phase 2: Signed Transactional Repair and Hard Setup Gate

**Rationale:** Repair UI is unsafe without a settled trust contract and inventory. Once Phase 1 can assess health deterministically, this phase can make admission recoverable without mixed files or implicit networking.

**Delivers:** Explicit-consent gate; exact-tag official-release query; verified manifest/archive/file hashes; bounded staging and extraction checks; versioned writable runtime generations; atomic activation/rollback; revalidation/re-entry; diagnostics and offline retry/exit behavior.

**Requirements addressed:** Hard setup gate, one-click repair, provenance, transactional outcome, offline-aware recovery, no restart after repair.

**Pitfalls avoided:** Unsigned/tampered metadata, ZIP traversal/extra files, mixed runtime, cancellation/swap loss, non-admin installation failure, unintended network traffic.

### Phase 3: Empty Launch Ownership and Optional Guided Demo

**Rationale:** Onboarding depends on a healthy runtime and stable startup boundary. Separating normal job ownership from demo ownership prevents demo artifacts and late events crossing into real user state.

**Delivers:** Library reconciliation with no active job; removal of auto-load-latest behavior; opt-in welcome; anchored Back/Next/Exit tour; original bundled synthetic demo; isolated session workspace; real pipeline orchestration; replay; idempotent terminal and crash cleanup.

**Requirements addressed:** Empty Home, explicit open behavior, user-controlled first-run learning, real offline demo, non-persistence, and cleanup.

**Pitfalls avoided:** Demo in library/recents, source/user-study data mixing, unsafe deletion, child-process leaks, cancellation/crash races, inaccessible overlays.

### Phase 4: Artifact-Only Web UI Reliability

**Rationale:** UI work must be constrained after the state surfaces it presents are stable. It may proceed in parallel with Phase 3 only with single ownership of shared `app/ui` assets.

**Delivers:** Atomic theme application, targeted flicker/repaint/layout fixes, model-name ellipsis with accessible full value, non-reflowing gate/tour overlays, and beta-5 comparison guards.

**Requirements addressed:** Visual preservation and guided-demo readability without redesign.

**Pitfalls avoided:** Changing the legacy widget shell instead of shipping WebEngine UI, global motion removal, layout shift, focus traps, configuration-value truncation.

### Phase 5: Packaged, Offline, and Physical Release Gate

**Rationale:** Unit tests cannot prove PyInstaller collection, DLL loader behavior, raw-path handling, or a clean Windows onboarding journey. This is the release proof phase and must follow all functional work.

**Delivers:** Build-time signed inventory/release artifact checks; disposable `LECTUREPACK_DATA_DIR` package subprocess smoke; damage/repair matrix; network-denied offline tests; GUI fresh-profile evidence; completed CPU-only/NVIDIA/AMD-Intel × fresh/upgraded × hostile-path physical matrix.

**Requirements addressed:** Clean-machine dependability, damage repair, offline demo/export, hostile Windows paths, and release completion evidence.

**Pitfalls avoided:** Developer-data mutation, mock-as-integration proof, antivirus/read-only/path failures, hidden network access, release-day hardware surprises.

### Phase Ordering Rationale

- Bootstrap and its security contract come first because the hard gate cannot honestly classify health or safely repair without an immutable runtime definition.
- Repair follows the contract; onboarding follows a healthy, gated startup; visual work remains artifact-only and isolated to the shipping shell.
- Packaging evidence is cumulative and must validate the assembled release, not individual mocked branches.
- No normal job schema should be altered to represent repair or demo state; their lifecycles belong to dedicated services and transient data domains.

## Testing Strategy and Completion Evidence

Use layered evidence, preserving all existing tests:

- **Unit/fault matrix:** fresh, upgraded, stale-path, payload-identity, missing/empty/corrupt every required file/DLL/model, smoke success/nonzero/hang/timeout, optional-engine permutations, bad signature/version/hash/archive/member/path, cancellation/permission/swap/rollback/restart recovery.
- **Controller/UI integration:** no `on_ui_ready()` or job signal before `HEALTHY`; exactly one ready transition; empty active job after library reconciliation; gate command set; repair consent; fallback notice; tour keyboard Back/Next/Exit; no overlay reflow.
- **Demo isolation:** success/cancel/error/forced-process-death; no normal library job/config changes; immutable source asset; no remaining worker/process; safe sentinel-only sweep and retry.
- **Visual regression:** retain token/DOM guards and add light/dark screenshot or video comparison, long labels, resize, repeat gate/tour/theme transitions, navigation with an existing real job, and console-error checks.
- **Packaged/physical evidence:** onedir subprocess executes real FFmpeg/ffprobe/Whisper from a disposable profile with captured stdout/stderr/exit/duration; blocked-network offline smoke; GUI fresh-profile smoke; CPU-only, NVIDIA, and AMD/Intel Windows machines with fresh/upgraded profiles, non-admin folders, spaces, non-ASCII paths, and separate writable data roots.

Actual targeted and full `pytest` output remains mandatory for every completed implementation phase. Mocks establish policy branches but never replace packaged or physical evidence.

## Research Flags

### Needs deeper phase research / explicit ADR

- **Phase 1:** Security/trust ADR for the verifier and release-manifest contract. This is the gating unresolved decision; validate PyInstaller compatibility of any approved verifier on the target Windows matrix.
- **Phase 2:** Exact GitHub asset/release policy, staging location and non-admin privilege behavior, cancellation boundary, archive limits, and byte-level rollback semantics need implementation-specific threat modeling.
- **Phase 3:** Real-pipeline demo timing budgets on the minimum CPU, cancellation propagation across QProcess/QThread boundaries, and keyboard/screen-reader behavior require empirical validation.
- **Phase 5:** Define reproducible physical-machine sign-off records and offline-network denial harness before release execution.

### Established patterns: lighter research expected

- **Phase 4:** The WebEngine target and existing visual guard seams are known; work is narrowly constrained to documented artifacts.
- **Phase 3 empty-launch portion:** Existing active-job setter and workspace ownership tests give a clear, local implementation seam.
- **Phase 1 basic persistence/disposable profiles:** Existing `ConfigManager`, atomic JSON, and `LECTUREPACK_DATA_DIR` seams are documented; research should focus on semantics, not new libraries.

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | MEDIUM | Standard-library repair pieces and PyInstaller constraints are well documented; the signature verifier is deliberately unapproved pending ADR. |
| Features | HIGH | Milestone context is authoritative and UX requirements are specific; external guidance is supporting rather than controlling. |
| Architecture | HIGH | Repository-backed analysis identifies concrete startup, ownership, packaging, and test seams. |
| Pitfalls | HIGH | Failure modes are tied to current code/debt and reusable test contracts; final time budgets require physical calibration. |

**Overall confidence:** MEDIUM-HIGH. The roadmap can proceed, but Phase 2 cannot begin implementation until the Phase 1 security/dependency decision is explicit.

### Gaps to Address

- **Verifier dependency and release-signing operations:** Approval, algorithm/library, canonical JSON, public-key encoding, private-key custody, rotation/revocation, schema versioning, expiry, and exact release asset layout are not yet ADR-backed.
- **Final install/activation location policy:** The research recommends a writable versioned data cache and atomic activation pointer; reconcile this with the milestone’s wording about runtime replacement and define clear non-admin/read-only diagnostics before coding.
- **Smoke command/input and budgets:** Specify a non-user, bundled smoke input and calibrate timeouts on the i7-9700F/CPU baseline; distinguish timeout, process error, and cancellation.
- **Accessibility and DPI:** Microsoft guidance is general; verify actual Qt/WebEngine keyboard focus, accessible labels, high-DPI layout, and tooltip behavior.
- **Release evidence ownership:** Assign who maintains signing keys/assets and who signs the physical test matrix; tests alone cannot close this operational gap.

## Sources

### Primary / repository and approved planning context

- [.planning/PROJECT.md](../PROJECT.md) — authoritative beta-5 baseline, locked architecture, constraints, success criteria, and debt.
- [.planning/MILESTONE-CONTEXT.md](../MILESTONE-CONTEXT.md) — locked beta-6 scope, repair trust boundary, onboarding behavior, and physical release gate.
- [STACK.md](STACK.md) — exact-version release repair approach, dependency decision gate, installation layout, and primary platform documentation.
- [FEATURES.md](FEATURES.md) — table stakes, differentiators, anti-features, user copy, and acceptance themes.
- [ARCHITECTURE.md](ARCHITECTURE.md) — as-built startup/order analysis, layer boundaries, data domains, component ownership, and proposed build order.
- [PITFALLS.md](PITFALLS.md) — failure modes, mitigations, reusable test seams, and release evidence matrix.

### External primary documentation synthesized by the research files

- GitHub REST documentation for exact release-by-tag and release-asset download behavior.
- Python documentation for `hashlib`, `hmac.compare_digest`, `os.replace`, and temporary-directory semantics.
- PyInstaller runtime-information documentation.
- `cryptography` Ed25519 verification documentation (conditional on approval only).
- Microsoft Learn desktop error-message, first-experience, teaching-tip, and update-security guidance.

---
*Research completed: 2026-07-27*  
*Ready for roadmap: yes — with Phase 1 verifier/ADR gate explicitly required before signed repair implementation.*
