# Phase 1: Runtime Contract & Bootstrap - Context

**Gathered:** 2026-07-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 establishes one deterministic definition of the required bundled CPU runtime, validates and persists it before normal desktop readiness, preserves or visibly falls back from optional engines, migrates the default model to bundled `ggml-base.en.bin`, and produces the approved signing/verifier ADR that gates Phase 2. It does not implement the setup page, network download, or repair installer.

</domain>

<decisions>
## Implementation Decisions

### Required Runtime Admission
- **D-01:** The required admission set is packaged FFmpeg, ffprobe, CPU Whisper CLI plus its required DLLs, and bundled `ggml-base.en.bin`; optional CUDA, Vulkan, Ollama, Groq, and yt-dlp never determine core admission health.
- **D-02:** A canonical runtime inventory and payload identity must be shared by startup, diagnostics, packaging, repair, and tests; do not keep separate drifting file lists.
- **D-03:** Persist required-runtime paths/facts only after the complete required set passes validation. Fresh, stale, partial, or invalid saved paths must never become a healthy state.
- **D-04:** Run lightweight identity/readability checks every launch. Run bounded executable/DLL/model smoke checks on first launch, after update or repair, or when payload identity changes.

### Startup Ownership
- **D-05:** Required-runtime bootstrap completes before `JobController` construction or any normal adapter-ready behavior, job activation, navigation, optional-engine probing, or demo start.
- **D-06:** A healthy startup initializes silently; Phase 1 exposes structured component status for later setup/diagnostics surfaces but does not build those surfaces.

### Optional Engine and Model Migration
- **D-07:** Preserve a healthy existing CUDA/custom engine selection while independently validating bundled CPU as the guaranteed recovery path.
- **D-08:** If the optional selection is missing or broken and bundled CPU is healthy, fall back to CPU and emit a visible structured notice; do not hard-gate the app.
- **D-09:** Beta-6 upgrade selects bundled `ggml-base.en.bin` as the default model. Other installed models remain available for later manual reselection.

### Signing and Dependency Gate
- **D-10:** Phase 1 must record and obtain explicit approval for an ADR covering the signature verifier, algorithm/encoding, canonical manifest bytes/schema, exact-version asset naming, public-key embedding, private-key custody/rotation/revocation, PyInstaller collection, and release ownership.
- **D-11:** `cryptography` or any other third-party verifier is unapproved. No plan may add it, imply it is selected, or weaken the signed-manifest requirement; implementation of Phase 2 remains blocked until the ADR choice is approved.

### Evidence and Safety
- **D-12:** Use argument arrays and safely escaped Unicode Windows paths for every process probe; bound timeouts and capture exit/stdout/stderr evidence.
- **D-13:** Required completion evidence is targeted and full `pytest` output plus a disposable-profile packaged/bootstrap smoke. Mock-only success is insufficient proof of the real payload.
- **D-14:** Never modify the original lecture video, user job data, the immutable portable payload, or the user's existing `main` worktree during this planning/phase workflow.

### the agent's Discretion
- Exact class/function names and internal status dataclasses, provided the four-layer architecture and decisions above remain intact.
- Exact lightweight identity fingerprint fields and calibrated smoke timeout values, provided they are deterministic, bounded, and tested on the minimum CPU.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product and architecture
- `AGENTS.md` — phase discipline, safety, testing evidence, documentation, and Git rules.
- `docs/PRODUCT_SPEC.md` — local-first behavior, required processing stack, privacy P1–P7, and CPU-mandatory target.
- `docs/ARCHITECTURE.md` — approved UI → Controller → Service → Infrastructure layering and process isolation.
- `docs/DECISIONS.md` — locked ADRs and required location for the Phase 1 security/dependency decision.
- `docs/IMPLEMENTATION_PLAN.md` — original stack/file plan and safety constraints; stale version/runtime wording must be reconciled, not copied blindly.

### Milestone scope and research
- `.planning/MILESTONE-CONTEXT.md` — locked beta-6 product decisions and non-goals.
- `.planning/REQUIREMENTS.md` — RUNT-01 through RUNT-09 acceptance contract.
- `.planning/ROADMAP.md` — Phase 1 goal, evidence gate, and Phase 2 block.
- `.planning/research/SUMMARY.md` — synthesized architecture, build-order, trust-model, test, and pitfall guidance.
- `.planning/research/STACK.md` — signature-verifier alternatives, signed-manifest contract, and Windows/PyInstaller constraints.
- `.planning/research/ARCHITECTURE.md` — proposed startup/bootstrap layering and integration points.
- `.planning/research/PITFALLS.md` — failure matrix, hostile-path/process risks, and reusable test seams.

### Current implementation and tests
- `lecturepack/infrastructure/config_manager.py` — blank defaults, current bundled-path resolution, and diagnostics-only Whisper discovery.
- `lecturepack/infrastructure/transcription_engines.py` — bundled CPU and optional engine discovery behavior.
- `lecturepack/infrastructure/ffmpeg_wrapper.py` — current FFmpeg auto-detection and safe subprocess patterns.
- `lecturepack/controllers/job_controller.py` — current construction ordering and controller integration.
- `app/desktop/engine_adapter.py` — desktop startup, early processing validation, optional-engine state, and adapter-ready behavior.
- `app/desktop/paths.py` — `LECTUREPACK_DATA_DIR` disposable-profile seam and frozen resource resolution.
- `app/packaging/build.py` — current required payload list and presence-only package gate.
- `tests/test_packaging_and_safety.py`, `tests/test_beta3_packaging.py`, `tests/test_adapter_startup.py` — reusable discovery, frozen-path, package, and startup test patterns.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConfigManager.autodetect_whisper()` already finds and persists a bundled CLI/model, but it is nondeterministic for multiple models and only called by diagnostics.
- `FFmpegWrapper.detect_binaries()` and `ConfigManager.autodetect_ffmpeg()` demonstrate existing bundled/PATH discovery, but current constructor ordering initializes only FFmpeg.
- `EngineRegistry` already knows how to locate the bundled CPU executable and optional installed engines.
- `LECTUREPACK_DATA_DIR` enables disposable fresh/upgraded profile tests without touching real user data.
- Existing atomic JSON-write and package clean-state patterns can support validated runtime facts and canonical inventory checks.

### Established Patterns
- External tools run outside the UI process with safely separated arguments.
- Configuration and state use plain JSON files and atomic replacement; no database may be introduced.
- CPU is the mandatory baseline; acceleration is optional and must fail back safely.

### Integration Points
- Startup composition must run bootstrap between `ConfigManager` creation and `JobController`/normal adapter readiness.
- Processing validation must consume the same validated runtime state rather than raw empty config strings.
- Packaging and diagnostics must consume the same canonical inventory as startup.
- Phase 1 produces structured health/fallback data consumed by the Phase 2 hard gate and later UI.

</code_context>

<specifics>
## Specific Ideas

- The normal portable user must never browse manually for the required bundled Whisper path.
- Healthy optional acceleration should survive upgrade, but bundled CPU is always the known-good safety net.
- Deep smoke testing should be event-driven by payload identity, avoiding unnecessary launch delay while still detecting changed/quarantined files.

</specifics>

<deferred>
## Deferred Ideas

- Hard setup page and one-click repair — Phase 2.
- GitHub download, signature/hash verification, runtime generations, and rollback implementation — Phase 2 after ADR approval.
- Empty Home ownership and guided demo — Phase 3.
- Visual artifact fixes — Phase 4.
- Full offline/physical/damage release matrix — Phase 5.

</deferred>

---

*Phase: 01-runtime-contract-bootstrap*
*Context gathered: 2026-07-27*

