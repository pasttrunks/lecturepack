# Phase 1: Runtime Contract & Bootstrap - Research

**Researched:** 2026-07-28  
**Domain:** Windows PySide6/PyInstaller CPU-runtime admission, startup ordering, and signed-repair trust-contract ADR  
**Confidence:** HIGH for repository seams; MEDIUM for the verifier recommendation pending approval

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** The required admission set is packaged FFmpeg, ffprobe, CPU Whisper CLI plus its required DLLs, and bundled `ggml-base.en.bin`; optional CUDA, Vulkan, Ollama, Groq, and yt-dlp never determine core admission health.
- **D-02:** A canonical runtime inventory and payload identity must be shared by startup, diagnostics, packaging, repair, and tests; do not keep separate drifting file lists.
- **D-03:** Persist required-runtime paths/facts only after the complete required set passes validation. Fresh, stale, partial, or invalid saved paths must never become a healthy state.
- **D-04:** Run lightweight identity/readability checks every launch. Run bounded executable/DLL/model smoke checks on first launch, after update or repair, or when payload identity changes.
- **D-05:** Required-runtime bootstrap completes before `JobController` construction or any normal adapter-ready behavior, job activation, navigation, optional-engine probing, or demo start.
- **D-06:** A healthy startup initializes silently; Phase 1 exposes structured component status for later setup/diagnostics surfaces but does not build those surfaces.
- **D-07:** Preserve a healthy existing CUDA/custom engine selection while independently validating bundled CPU as the guaranteed recovery path.
- **D-08:** If the optional selection is missing or broken and bundled CPU is healthy, fall back to CPU and emit a visible structured notice; do not hard-gate the app.
- **D-09:** Beta-6 upgrade selects bundled `ggml-base.en.bin` as the default model. Other installed models remain available for later manual reselection.
- **D-10:** Phase 1 must record and obtain explicit approval for an ADR covering the signature verifier, algorithm/encoding, canonical manifest bytes/schema, exact-version asset naming, public-key embedding, private-key custody/rotation/revocation, PyInstaller collection, and release ownership.
- **D-11:** `cryptography` or any other third-party verifier is unapproved. No plan may add it, imply it is selected, or weaken the signed-manifest requirement; implementation of Phase 2 remains blocked until the ADR choice is approved.
- **D-12:** Use argument arrays and safely escaped Unicode Windows paths for every process probe; bound timeouts and capture exit/stdout/stderr evidence.
- **D-13:** Required completion evidence is targeted and full `pytest` output plus a disposable-profile packaged/bootstrap smoke. Mock-only success is insufficient proof of the real payload.
- **D-14:** Never modify the original lecture video, user job data, the immutable portable payload, or the user's existing `main` worktree during this planning/phase workflow.

### the agent's Discretion
- Exact class/function names and internal status dataclasses, provided the four-layer architecture and decisions above remain intact.
- Exact lightweight identity fingerprint fields and calibrated smoke timeout values, provided they are deterministic, bounded, and tested on the minimum CPU.

### Deferred Ideas (OUT OF SCOPE)
- Hard setup page and one-click repair — Phase 2.
- GitHub download, signature/hash verification, runtime generations, and rollback implementation — Phase 2 after ADR approval.
- Empty Home ownership and guided demo — Phase 3.
- Visual artifact fixes — Phase 4.
- Full offline/physical/damage release matrix — Phase 5.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| RUNT-01 | Fresh profile discovers packaged CPU runtime without settings | Canonical inventory resolves only bundle-relative paths; bootstrap validates before persistence. |
| RUNT-02 | One inventory is shared | One infrastructure module exports entries, payload identity, diagnostics, and package assertions. |
| RUNT-03 | Persist only complete validated facts | Bootstrap writes one atomic `runtime_health` record only on healthy completion. |
| RUNT-04 | Light every launch; full when required | Identity comparison selects deterministic light/full modes and records smoke evidence. |
| RUNT-05 | No normal behavior pre-health | Composition creates the coordinator before adapter/controller and calls readiness once from `HEALTHY`. |
| RUNT-06 | Base-English migration | Explicitly migrate default model to bundled `ggml-base.en.bin`; do not delete other model paths. |
| RUNT-07 | Preserve healthy optional selection | Resolve optional preference after CPU admission and retain it if available. |
| RUNT-08 | Visible CPU fallback | Emit structured non-blocking fallback notice after health; never invoke a download/probe to decide admission. |
| RUNT-09 | Approved signing/verifier ADR | Decision record specifies trust bytes, key lifecycle, release asset naming, packaging evidence, and human approval gate. |
</phase_requirements>

## Project Constraints (from AGENTS.md)

- Work only on approved Phase 1 files; do not add scope or proceed past approval gates. [VERIFIED: AGENTS.md]
- Preserve the selected architecture/stack and add no third-party dependency without a justified, approved decision. [VERIFIED: AGENTS.md]
- Keep source-derived and AI-generated content separate; never change original lecture videos or execute transcript content. [VERIFIED: AGENTS.md]
- Use safely escaped paths for external processes; no credentials, telemetry, advertising, or non-local network behavior except approved first-run model download/localhost LM Studio. [VERIFIED: AGENTS.md]
- Implementation must report actual targeted and full `pytest` output; mocks are not real-integration evidence. [VERIFIED: AGENTS.md]
- Important decisions belong in `docs/DECISIONS.md`; update the phase handoff before ending a long implementation session. [VERIFIED: AGENTS.md]

## Summary

Phase 1 should introduce an immutable, code-owned description of the bundled CPU payload and a bootstrap state boundary before the desktop adapter creates a `JobController`. The current app persists blank runtime paths by default, writes discovered paths one-at-a-time, and only discovers Whisper from diagnostics; it also selects the first `.bin` returned by directory enumeration. `LecturePackAdapter.__init__` currently creates `JobController` immediately, while `on_ui_ready()` reconciles jobs, triggers optional probes, and loads the last completed job. [VERIFIED: `lecturepack/infrastructure/config_manager.py:36-159`; `app/desktop/engine_adapter.py:694-720,951-971`]

The correct Phase-1 boundary is: resolve the exact bundle inventory → perform light checks and decide whether full smoke is required → run bounded local smokes → atomically persist facts only on success → construct normal adapter/controller → run normal readiness exactly once. A non-healthy result must be structured and returned to the future Phase-2 gate, not repaired or bypassed here. [VERIFIED: `01-CONTEXT.md` D-01–D-06; `docs/ARCHITECTURE.md` layer contract]

**Primary recommendation:** Add an infrastructure-owned canonical inventory/validator and service-owned bootstrap result, then make `main.py`/desktop composition invoke it before `LecturePackAdapter` construction; write the signed-manifest ADR as an approval checkpoint, not a dependency installation task. [VERIFIED: `01-CONTEXT.md` D-02, D-05, D-10–D-11]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Bundle-relative inventory and payload fingerprint | Infrastructure | Packaging | Filesystem paths/hashes are infrastructure facts; build consumes the same object. [VERIFIED: `app/packaging/build.py:95-199`] |
| Light/full validation and process evidence | Service | Infrastructure | Policy determines when full validation is due; infrastructure owns file/hash and QProcess process primitives. [VERIFIED: `01-CONTEXT.md` D-04, D-12] |
| Startup admission state | Controller | Service | The controller/composition gates lifecycle; service returns a pure structured health result. [CITED: docs/ARCHITECTURE.md] |
| Runtime fact persistence and upgrade migration | Infrastructure | Service | `ConfigManager`/atomic JSON are the existing persistence boundary. [VERIFIED: `lecturepack/infrastructure/config_manager.py:49-88`] |
| Optional-engine selection/fallback notice | Service | Controller/UI bridge | Registry decides availability; controller emits a post-health structured status. [VERIFIED: `lecturepack/infrastructure/transcription_engines.py:194-272`] |
| Signing/verifier decision | Documentation/ADR | Packaging | This phase records an approval-gated contract; no repair transport belongs here. [VERIFIED: `01-CONTEXT.md` D-10–D-11] |

## Standard Stack

### Core

| Library / facility | Version | Purpose | Why standard |
|---|---:|---|---|
| Python standard library (`pathlib`, `hashlib`, `json`, `os`) | existing Python runtime | Bundle-relative inventory, SHA-256 identity, atomic metadata inputs | Avoids a dependency for non-cryptographic hashing/inventory. [VERIFIED: `docs/DECISIONS.md`; `lecturepack/infrastructure/file_manager.py`] |
| PySide6 `QProcess` | existing PySide6 | Asynchronous bounded local executable smoke | Existing project process boundary; supports separated program/arguments rather than shell command text. [CITED: `docs/ARCHITECTURE.md`; VERIFIED: `lecturepack/infrastructure/whisper_wrapper.py`] |
| Existing `FileManager.write_json_atomic` | existing | Persist one validated runtime-health snapshot | Existing configuration writes use it. [VERIFIED: `lecturepack/infrastructure/config_manager.py:74-88`] |

### Approval-gated verifier candidate (do not install in Phase 1)

| Candidate | Registry version observed | Purpose | Decision status |
|---|---:|---|---|
| `cryptography` | 49.0.0 | Maintained Python Ed25519 detached-signature verifier candidate | **Unapproved; Phase-1 ADR/human approval required before any dependency or code change.** Official API loads raw public bytes and raises `InvalidSignature` on failure. [CITED: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Maintained Ed25519 verifier | Windows CNG through `ctypes`/native bindings | Microsoft documents CNG as a native Windows cryptography API, but its documented signature providers list DSA/RSA/ECDSA rather than a stable Ed25519 verifier contract; bindings, key import, encoding, OS support, and package testing would become owned security surface. Do not choose without an ADR. [CITED: https://learn.microsoft.com/en-us/windows/win32/seccng/cng-cryptographic-algorithm-providers] |
| Maintained verifier | PowerShell/`certutil`/external executable | Adds shell/process and availability variability, violates the desired in-process deterministic verifier boundary, and still needs a signature/key contract. [ASSUMED] |
| Public-key signature | SHA-256 release file / GitHub TLS only | Integrity metadata and transport do not establish the locked project signature trust root. [VERIFIED: `01-CONTEXT.md` D-10–D-11] |
| Public-key signature | HMAC / custom pure-Python Ed25519 | HMAC requires embedding a secret; custom crypto is prohibited by the project trust model. [VERIFIED: `.planning/research/SUMMARY.md`] |

**Installation:** None in Phase 1. The planner must create an explicit `checkpoint:human-verify`/approval task before any verifier dependency is added. [VERIFIED: `01-CONTEXT.md` D-11]

## Package Legitimacy Audit

| Package | Registry | Age / downloads | Source Repo | Verdict | Disposition |
|---|---|---|---|---|---|
| `cryptography` | PyPI | Registry current version 49.0.0; seam did not report downloads | Official docs link to project GitHub | SUS (seam: unknown downloads/repo) | **Not installed; ADR approval and independent human verification required.** [VERIFIED: PyPI `pip index versions cryptography`; CITED: https://cryptography.io/en/latest/] |

**Packages removed due to [SLOP] verdict:** none.  
**Packages flagged as suspicious [SUS]:** `cryptography` — it remains merely a candidate, so the Phase 2 verifier plan cannot install it absent explicit approval. [VERIFIED: package-legitimacy seam]

## Architecture Patterns

### System Architecture Diagram

```text
PyInstaller bundle / dev payload
        |
        v
CanonicalRuntimeInventory (relative entries, hashes, payload identity)
        |
        v
RuntimeBootstrapService
  light: path containment + regular file + readable + size/hash/identity
  full when first/update/repair/identity changed:
      QProcess ffmpeg -version / ffprobe -version / whisper smoke model input
        |
        +--> UNHEALTHY (component results only) --> Phase-2 gate later
        |
        +--> HEALTHY --> atomically persist runtime_health + canonical CPU paths
                             |
                             v
                      construct LecturePackAdapter / JobController
                             |
                             v
          on_ui_ready once: jobs, settings, optional-engine resolution/fallback notice
```

### Recommended Project Structure

```text
lecturepack/
├── infrastructure/runtime_inventory.py       # canonical entries, containment, identity, file checks
├── infrastructure/runtime_validation.py      # QProcess/testable smoke primitive and result records
├── services/runtime_bootstrap.py             # light/full policy, persistence transaction, migration
└── controllers/desktop_startup.py            # state transition; invokes normal adapter only when healthy
app/
├── desktop/main.py                           # composition; no early MainWindow/adapter readiness
└── packaging/
    ├── build.py                              # imports canonical inventory for build gate/copies smoke asset
    └── assets/runtime-smoke.wav              # checked-in 1 s, 16 kHz mono PCM synthetic fixture
docs/
└── DECISIONS.md                              # approval-gated signed-manifest ADR
```

Exact names are discretionary; responsibilities are not. [VERIFIED: `01-CONTEXT.md` discretion; `docs/ARCHITECTURE.md`]

### Pattern 1: Canonical inventory is data, not scattered conditionals

**What:** Define ordered, relative, non-user-controlled entries such as `bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/whisper-cli.exe`, fixed required Whisper DLLs plus the explicitly enumerated CPU backend DLL glob, and `models/ggml-base.en.bin`. Each entry carries component id, allowed type, expected size/SHA-256, and smoke role. Inventory resolution rejects absolute paths, `..`, duplicates, and paths outside the immutable application root. [VERIFIED: `01-CONTEXT.md` D-01–D-02; `app/packaging/build.py:132-145`; `tests/test_beta3_packaging.py:19-33,87-91`]

**When to use:** Startup, diagnostics, build validation, Phase-2 repair schema, and all synthetic package fixtures. [VERIFIED: `01-CONTEXT.md` D-02]

**Why:** `build.py` currently has a fixed list that omits the variable `ggml-cpu-*.dll` validation despite copying an expanded CPU set, while `ConfigManager` searches generic paths and picks the first model returned from `os.listdir`; these lists can drift. [VERIFIED: `app/packaging/build.py:132-199`; `lecturepack/infrastructure/config_manager.py:115-159`]

### Pattern 2: Persist one validated snapshot, never discovery fragments

**What:** Maintain a versioned `runtime_health` config object containing inventory schema, app version/payload identity, resolved canonical relative paths, validation timestamp/mode, and per-component status/evidence. Build it in memory; write it atomically only after every required component passes the selected validation. On failure, preserve prior facts for diagnostics but treat them as unusable unless they pass current light validation. [VERIFIED: `01-CONTEXT.md` D-03–D04; `lecturepack/infrastructure/config_manager.py:65-88`]

**One-time beta-5 → beta-6 migration:** Use a versioned config marker such as `migration_versions.runtime_contract = 1`, not an every-launch default assignment. When the marker is absent or below `1`, first retain the pre-migration `engine` and `whisper_model` values in memory, complete bundled CPU validation, and then perform one atomic config save containing the healthy runtime facts, canonical bundled paths, migrated values, and marker. Set `whisper_model` to `<runtime_root>/models/ggml-base.en.bin` exactly once. If the prior model is a different existing `.bin`, preserve its absolute path in a de-duplicated `known_whisper_models` list; do not move, rename, overwrite, or delete it. Also retain other files discoverable through `model_search_dirs()` so Settings can offer later manual reselection. On later launches, marker `1` suppresses the migration entirely: light/full health validation still runs, but a user's subsequent model choice is not reset to base.en. [VERIFIED: `01-CONTEXT.md` D-03, D-06, D-09; `lecturepack/infrastructure/config_manager.py:68-104` preserves unknown versioned keys and saves atomically; `lecturepack/infrastructure/transcription_engines.py:285-305` searches bundled, parent, data, and configured-model directories]

For engine migration, normalize the saved alias first and validate it only after CPU admission. Leave `engine` byte-for-byte unchanged when an explicit optional CUDA/Vulkan/custom selection is healthy. If it is missing/broken, atomically set the active `engine` to CPU while preserving the rejected value and reason in structured fallback facts/notice; `auto` remains `auto`. Do not install/probe/download an optional engine to run this migration. If CPU validation fails, write neither the migration marker nor model/engine changes, so retry remains a complete transaction. [VERIFIED: `01-CONTEXT.md` D-03, D-07–D08; `lecturepack/infrastructure/transcription_engines.py:181-278`]

### Pattern 3: Admission coordinator has a hard, one-way readiness edge

**What:** States are `ASSESSING`, `HEALTHY`, and `SETUP_REQUIRED` (Phase 2 will add repair states). Only the transition to `HEALTHY` may instantiate `JobController`, wire it, emit UI-ready, permit navigation/job activation, or start optional probes. It must be idempotent: a repeated successful callback never invokes normal readiness twice. [VERIFIED: `01-CONTEXT.md` D-05–D06]

**Integration seam:** `main()` currently makes and shows `MainWindow` directly at `app/desktop/main.py:182-212`; `LecturePackAdapter.__init__` makes `ConfigManager` then `JobController` at `engine_adapter.py:694-720`; `on_ui_ready()` performs reconciliation/probes at `engine_adapter.py:951-971`. Refactor composition so the future controller owns adapter construction/readiness; do not merely add a late check inside `on_ui_ready()`. [VERIFIED: repository line evidence]

### Pattern 4: CPU admission independent from optional resolution

**What:** Validate only the CPU inventory for admission. After `HEALTHY`, ask `EngineRegistry.resolve(saved_engine)`: retain a healthy explicit CUDA/Vulkan/custom selection; if unavailable, select CPU and emit one structured notice containing requested engine, resolved engine, and reason. No optional engine download, LM Studio/Ollama probe, or network request may occur during admission. [VERIFIED: `01-CONTEXT.md` D-01, D-07–D08; `lecturepack/infrastructure/transcription_engines.py:213-272`; `app/desktop/engine_adapter.py:962-968`]

### Smoke specification

- Light validation on every launch: resolve the canonical root, verify each exact entry is a non-empty regular readable file, recompute a deterministic identity from inventory schema + app/payload version + ordered `(relative_path, byte_size, SHA-256)`, and compare it with the persisted healthy snapshot. A missing, changed, unreadable, or out-of-root entry yields `SETUP_REQUIRED`. [VERIFIED: `01-CONTEXT.md` D-03–D04]
- Full validation is mandatory when no healthy snapshot exists, when app/inventory identity differs, or when a Phase-2 repair records a new generation. It reruns light validation and starts `ffmpeg.exe -version`, `ffprobe.exe -version`, and the CPU `whisper-cli.exe` smoke below. Capture exact argument vector, start/end/elapsed, exit status, stdout, stderr, timeout/cancel reason, and component id. [VERIFIED: `01-CONTEXT.md` D-04, D-12; `.planning/MILESTONE-CONTEXT.md`]
- **Exact packaged Whisper smoke:** check in a project-owned, non-speech synthetic fixture at `app/packaging/assets/runtime-smoke.wav`; package it as `<runtime_root>/smoke/runtime-smoke.wav` and include its exact byte size/SHA-256 in the canonical inventory. Its fixed format is RIFF/WAVE, signed 16-bit little-endian PCM (`pcm_s16le`), 16,000 Hz, mono, exactly 16,000 samples (1.000 s), generated from a deterministic non-silent tone and never derived from a lecture or user profile. Invoke with separated arguments: `<runtime_root>/bin/whisper-cli.exe -m <runtime_root>/models/ggml-base.en.bin -f <runtime_root>/smoke/runtime-smoke.wav -t 1 -nt`. Do not add `-of`, so bootstrap creates no transcript files. [VERIFIED: packaged CLI `--help` read-only probe on 2026-07-28 confirmed `-m`, `-f`, `-t`, and `-nt`; `app/packaging/build.py:183-192` confirms the packaged CLI/DLL/model layout]
- **Success evidence:** require `QProcess.NormalExit`, exit code `0`, elapsed time below the 30,000 ms provisional model-smoke budget, and captured diagnostics showing (a) `load_backend: loaded CPU backend from` a canonical `<runtime_root>/bin/ggml-cpu-*.dll`, (b) `loading model from` the canonical `ggml-base.en.bin`, (c) a nonzero model-size/load record, and (d) `read_audio_data`/`main: processing` for the canonical smoke WAV. Those observations jointly execute the EXE, Windows loader-selected CPU DLL, model parser/allocation, WAV decoder, and inference path; an existence/hash check alone proves none of those runtime behaviors. Match stable prefixes/contained canonical paths, not hardware-specific DLL names or timings. [VERIFIED: read-only run of the existing protected `app/dist/LecturePack` payload on 2026-07-28 loaded packaged `ggml-cpu-haswell.dll`, loaded the 147.37 MB base model, decoded PCM WAV, exited `0`, and completed in 6,972 ms]
- **Timeout/error evidence:** start a single-shot 30,000 ms timer with the Whisper `QProcess`; on expiry, record `state=TIMEOUT`, component id, exact program/argument vector, elapsed time, partial stdout/stderr, and process error/exit fields, then terminate only that process tree and keep admission non-healthy. Version probes use separate 5,000 ms budgets. Tests inject shorter budgets and the no-output hang fixture; the 30-second production budget must still be confirmed on the minimum i7-9700F before release. [VERIFIED: `01-CONTEXT.md` D-12–D13; measured packaged smoke above; ASSUMED only for final minimum-machine calibration]
- Terminate only the smoke process tree on timeout; never direct a smoke command at user input, source video, job root, or original lecture. [VERIFIED: AGENTS.md safety; `docs/PRODUCT_SPEC.md` P5–P7]

### Anti-Patterns to Avoid

- **`autodetect_*()` as admission:** it persists partial values and falls back to PATH, which violates deterministic packaged-only admission. [VERIFIED: `lecturepack/infrastructure/config_manager.py:107-159`; `01-CONTEXT.md` D-01, D-03]
- **Presence-only packaging gate:** current `check_clean_state()` only checks existence/nonzero byte size; loader/model failure remains undetected. [VERIFIED: `app/packaging/build.py:95-156`]
- **Late gate inside adapter readiness:** the controller already exists and normal probes/jobs may have run. [VERIFIED: `app/desktop/engine_adapter.py:694-720,951-971`]
- **Optional GPU determines admission:** registry already has CPU fallback semantics; use it after admission. [VERIFIED: `lecturepack/infrastructure/transcription_engines.py:230-272`]
- **Shell command construction:** use QProcess program plus argument list/`Path`, never concatenated command strings. [VERIFIED: AGENTS.md; CITED: https://docs.python.org/3/library/subprocess.html]

## Don't Hand-Roll

| Problem | Do not build | Use instead | Why |
|---|---|---|---|
| JSON replacement | ad-hoc multi-file writes | `FileManager.write_json_atomic` | Existing atomic configuration pattern avoids partial snapshots. [VERIFIED: `lecturepack/infrastructure/config_manager.py:74-88`] |
| GUI external-process execution | `subprocess` shell string on GUI thread | existing QProcess/process-tree boundary | Maintains UI responsiveness and Unicode-safe argument separation. [CITED: `docs/ARCHITECTURE.md`] |
| Signature verification | pure Python Ed25519/HMAC workaround | approval-gated maintained verifier selected by ADR | Cryptographic verification/key lifecycle is security-critical; no custom implementation is acceptable. [VERIFIED: `.planning/research/SUMMARY.md`; `01-CONTEXT.md` D-10–D11] |
| Bundle membership lists | separate startup/packaging/test literals | one `CanonicalRuntimeInventory` export | Existing packaging and discovery lists already differ. [VERIFIED: `app/packaging/build.py:132-199`; `lecturepack/infrastructure/config_manager.py:107-159`] |

## Common Pitfalls

### Pitfall 1: Full smoke is skipped after a changed payload
**What goes wrong:** A nonempty corrupted DLL/model passes existence checks and the first real lecture fails.  
**Avoid:** Persist the ordered payload identity only after full success; identity mismatch forces full smoke. [VERIFIED: `01-CONTEXT.md` D-03–D04]

### Pitfall 2: CPU backend DLLs are under-specified
**What goes wrong:** `build.py` copies a variable set matching `ggml-cpu*.dll`, while its current presence gate names only a subset. [VERIFIED: `app/packaging/build.py:132-199`; `tests/test_beta3_packaging.py:87-91`]  
**Avoid:** Inventory emits the resolved expected DLL entries at build time and stores their exact identities; test deletion/corruption of every resolved entry. [VERIFIED: `01-CONTEXT.md` D-02]

### Pitfall 3: Adapter readiness is called twice or before health
**What goes wrong:** Duplicate job signals/probes occur, or normal UI appears before a failed runtime is known. [VERIFIED: `app/desktop/engine_adapter.py:951-971`]  
**Avoid:** A single coordinator callback owns both adapter construction and one readiness call; assert no adapter/controller/probe invocation while `ASSESSING`/`SETUP_REQUIRED`. [VERIFIED: `01-CONTEXT.md` D-05]

### Pitfall 4: Upgrade overwrites a valid optional engine or loses models
**What goes wrong:** A broad config reset clobbers CUDA/custom selection or installed models. [VERIFIED: `01-CONTEXT.md` D-07, D-09]  
**Avoid:** Migrate only runtime-owned fields, preserve valid optional preference and model metadata, then independently set canonical default model/fallback. [VERIFIED: `01-CONTEXT.md` D-07–D09]

### Pitfall 5: ADR pretends a dependency is approved
**What goes wrong:** A planning task adds `cryptography` before the required human decision. [VERIFIED: `01-CONTEXT.md` D-11]  
**Avoid:** ADR records recommendation and an explicit approval/rejection section; every Phase-2 verifier/repair task depends on an approved ADR reference. [VERIFIED: `01-CONTEXT.md` D-10–D11]

## Verifier / Signing ADR Recommendation (RUNT-09)

### Threat model and non-negotiable contract

The verifier protects a repair client from a malicious or substituted manifest/archive, replay/mixed-release content, path traversal, and unauthorized release metadata. It does **not** replace local inventory/hash validation, staging, version binding, or transactional activation; those remain Phase 2. The protected message must bind schema version, `app_version`, exact asset filename, archive SHA-256/size, and every required inventory entry (relative path, size, SHA-256) before any URL/name/hash is trusted. [VERIFIED: `01-CONTEXT.md` D-10; `.planning/MILESTONE-CONTEXT.md`]

### Decision comparison

| Option | Strengths | Risks / rejection criteria | Recommendation |
|---|---|---|---|
| `cryptography` + Ed25519 detached signature | Official API supports raw 32-byte public keys and detached verify that raises on invalid signature; its Windows wheel is documented as statically linked. [CITED: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/; https://cryptography.io/en/latest/installation/] | New dependency, PyInstaller collection/release test required; legitimacy seam flags unknown registry signals; still unapproved. | **Preferred candidate only, subject to explicit approval.** |
| Windows CNG through native bindings | No Python package; Microsoft describes CNG as the Windows native primitive API. [CITED: https://learn.microsoft.com/en-us/windows/win32/seccng/cng-portal] | Official provider table documents DSA/RSA/ECDSA, not an application-ready Ed25519 path; bindings and key/signature encoding become maintained security code. [CITED: https://learn.microsoft.com/en-us/windows/win32/seccng/cng-cryptographic-algorithm-providers] | Do not select for beta-6 without a separate native-security design and physical matrix. |
| PowerShell/`certutil`/GitHub checksums | No package addition. | External availability/shell behavior and no project-signature trust root; cannot meet locked signed-manifest requirement as stated. [VERIFIED: `.planning/research/SUMMARY.md`] | Reject. |
| Home-grown verifier / HMAC | No package addition. | Custom crypto is unacceptable; HMAC ships a secret. [VERIFIED: `.planning/research/SUMMARY.md`] | Reject. |

### ADR approval checkpoint (required)

Create a dated `docs/DECISIONS.md` ADR that names the decision owner and includes: (1) algorithm `Ed25519`; (2) signature encoding (base64url without padding is recommended) and 32-byte raw public-key encoding; (3) exact canonical manifest bytes — UTF-8 JSON, sorted keys, separators `,`/`:`, no insignificant whitespace, explicit schema; (4) `key_id`, one embedded active public key plus rotation set; (5) key generation/storage/signing authority, offline backup, incident revocation/replacement process; (6) exact `v{app_version}` release asset/manifest/signature names; (7) expiry/replay policy; (8) PyInstaller collection rule and frozen onedir verifier smoke; (9) release owner and sign-off evidence; and (10) a signed known-good plus altered-byte known-bad test vector. Items (2), (3), and expiry/replay policy are proposed details and require approval. [VERIFIED: `01-CONTEXT.md` D-10; ASSUMED for exact encoding/canonicalization choice]

**Phase-2 gate:** Until an authorized human approves this ADR, do not add a verifier dependency, download metadata, verify repair files, or downgrade to unsigned hashes. [VERIFIED: `01-CONTEXT.md` D-11]

### PyInstaller implications

PyInstaller’s onedir default is a distributable directory, and it provides explicit `--add-binary`, `--hidden-import`, and `--collect-binaries` mechanisms. The ADR must require a clean `dist/LecturePack` inspection plus a disposable-profile frozen-process verification test because import analysis alone cannot prove the packaged verifier and bundled DLL/model payload load together. [CITED: https://pyinstaller.org/en/stable/usage.html; VERIFIED: `app/packaging/build.py:95-199`]

## Code Examples

### Identity and persistence shape

```python
# Repository-guided pseudocode; policy is Phase-1 implementation work.
identity = sha256(canonical_json({
    "inventory_schema": inventory.schema_version,
    "app_version": app_version,
    "entries": [entry.file_fact(root) for entry in inventory.entries],
}).encode("utf-8")).hexdigest()

result = bootstrap.assess(previous=config.get("runtime_health"))
if result.healthy:
    config.set("runtime_health", result.persistable_facts())  # atomic existing setter
else:
    return result  # Later Phase-2 gate consumes component statuses
```

`ConfigManager.set()` delegates to its atomic save path, but the plan must avoid calling it per discovered component. [VERIFIED: `lecturepack/infrastructure/config_manager.py:74-96`]

### QProcess smoke contract

```python
# Source: project QProcess architecture + locked D-12.
process.setProgram(str(executable))
process.setArguments(["-version"])  # separate arguments; no shell
process.start()
if not process.waitForFinished(timeout_ms):
    terminate_only_this_process_tree(process)
    return SmokeResult.timeout(component="ffmpeg", elapsed_ms=elapsed())
return SmokeResult.capture(
    exit_code=process.exitCode(), stdout=bytes(process.readAllStandardOutput()),
    stderr=bytes(process.readAllStandardError()), elapsed_ms=elapsed(),
)
```

Use injected runners/fake QProcess in unit tests and the real packaged payload in subprocess smoke evidence. [VERIFIED: AGENTS.md; `01-CONTEXT.md` D-12–D13]

## State of the Art

| Old approach in repository | Phase-1 approach | Impact |
|---|---|---|
| `ConfigManager.autodetect_*()` searches saved/bundle/PATH and persists incrementally | Bundle-only canonical admission followed by atomic validated facts | Deterministic portable startup; no stale/PATH runtime accepted. [VERIFIED: `lecturepack/infrastructure/config_manager.py:107-159`] |
| `check_clean_state()` checks nonempty fixed paths | Shared inventory verifies complete payload identity; Phase 5 later proves actual frozen smokes | Avoids missing variable DLL and loader/model blind spots. [VERIFIED: `app/packaging/build.py:95-156`] |
| `main()` shows window and adapter makes controller before health | Bootstrap coordinator owns healthy transition | Enforces RUNT-05 before jobs/optional probes. [VERIFIED: `app/desktop/main.py:182-212`; `app/desktop/engine_adapter.py:694-720`] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | The measured 6,972 ms packaged model smoke supports a provisional 30,000 ms production budget, but final calibration still requires the minimum i7-9700F. | Smoke specification | False timeout / unacceptable startup delay; retain the release calibration gate. |
| A2 | Base64url-no-padding, sorted-key compact UTF-8 JSON, and an expiry/replay policy are suitable ADR defaults. | ADR checkpoint | Signing/release tooling interoperability; user must approve exact form. |
| A3 | PowerShell/`certutil` are poor fits for this app’s signed-manifest verifier. | ADR comparison | Could exclude a valid platform approach; it remains a rejected recommendation, not a fact. |

## Open Questions (RESOLVED)

1. **Resolved — exact binary/audio invocation proving CPU Whisper DLL plus model loading.**
   - Add the checked-in deterministic fixture `app/packaging/assets/runtime-smoke.wav` and package it as `smoke/runtime-smoke.wav`: 1.000 s, 16 kHz, mono, signed 16-bit little-endian PCM, non-silent synthetic tone, canonical-inventory hashed, and never sourced from user content. Run `<runtime_root>/bin/whisper-cli.exe -m <runtime_root>/models/ggml-base.en.bin -f <runtime_root>/smoke/runtime-smoke.wav -t 1 -nt` with a 30,000 ms QProcess deadline and no output-file flag. [VERIFIED: packaged CLI `--help` and existing layout inspection on 2026-07-28; `app/packaging/build.py:183-192`]
   - Success requires normal exit `0` plus captured stable-prefix evidence for a CPU backend DLL loaded from canonical `bin`, the canonical model load/model size, WAV read, and processing. Timeout/nonzero/process-error results record exact argv, elapsed, partial streams, status/reason, terminate only the smoke tree, and keep admission closed. A read-only analog run using the current protected packaged CLI/model and existing 16 kHz mono `pcm_s16le` `tests/fixtures/sapi_speech.wav` exited `0` in 6,972 ms and emitted all four evidence classes; the planning worktree itself has no checked-in WAV yet, so the new 1-second asset is an explicit Wave 0/package deliverable. [VERIFIED: local packaged probe and `ffprobe` inspection on 2026-07-28]
2. **Resolved — one-time beta-5 → beta-6 migration semantics.**
   - Gate migration with `migration_versions.runtime_contract = 1`. With no marker, preserve a healthy saved optional engine selection, set the canonical bundled base-English model as default exactly once, preserve a different existing prior model in `known_whisper_models`, and atomically write these values with healthy runtime facts and the marker. A broken optional engine becomes CPU with a structured fallback notice retaining requested engine/reason; CPU failure writes nothing. With marker `1`, never reset `whisper_model` or repeat fallback migration, so later manual model selection survives every launch. [VERIFIED: `01-CONTEXT.md` D-03, D-07–D09; `lecturepack/infrastructure/config_manager.py:68-104`; `lecturepack/infrastructure/transcription_engines.py:181-305`]
3. **Resolved by mandatory human checkpoint — signing-key ownership and revocation communication.**
   - RUNT-09 cannot be settled by code inference. The `docs/DECISIONS.md` ADR must name the verifier choice, signing/release owner, private-key custodian, backup/rotation/revocation authority, incident communication path, and approver; Phase 2 remains blocked until that named human approval is recorded. [VERIFIED: `01-CONTEXT.md` D-10–D11]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Python | existing test/tooling | ✓ | installed locally; exact version to record during implementation | — |
| pytest | Phase-1 evidence | ✓ | project environment | — |
| PySide6/QProcess | startup/process smoke unit integration | ✓ (existing project dependency) | project-pinned | mocked runner for unit tests only |
| PyInstaller | frozen-package evidence | project build tooling | inspect at Phase-5/package smoke | no substitute for packaged proof |
| `cryptography` | only if ADR approves verifier candidate | installed in current environment but **not approved for project** | 49.0.0 observed | ADR-approved alternative only |

**Missing dependencies with no fallback:** none for planning; the chosen verifier remains an approval blocker, not an installation instruction. [VERIFIED: `01-CONTEXT.md` D-11]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest + existing PySide6 `qapp` fixture [VERIFIED: `tests/conftest.py`] |
| Config file | `pytest.ini` / project settings; inspect before implementation if command changes [VERIFIED: repository test layout] |
| Quick run command | `pytest tests/test_runtime_inventory.py tests/test_runtime_bootstrap.py tests/test_adapter_startup.py tests/test_beta3_packaging.py tests/test_cuda_engine.py -q` (Wave 0 adds first two files) |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| RUNT-01 | Fresh disposable profile resolves every exact bundled component | unit/integration | `pytest tests/test_runtime_inventory.py -q` | ❌ Wave 0 |
| RUNT-02 | Same inventory drives package check, diagnostics, bootstrap | unit | `pytest tests/test_runtime_inventory.py -q` | ❌ Wave 0 |
| RUNT-03 | No partial/stale facts persist; healthy facts atomically do | unit | `pytest tests/test_runtime_bootstrap.py -q` | ❌ Wave 0 |
| RUNT-04 | light/full decision; exact real-CLI/model/WAV smoke plus success/nonzero/hang/timeout evidence | unit + packaged process fixture | `pytest tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py -q` | ❌ Wave 0 |
| RUNT-05 | no adapter/controller/readiness/probe before healthy; exactly one after | controller integration | `pytest tests/test_adapter_startup.py tests/test_runtime_bootstrap.py -q` | ◐ extend |
| RUNT-06 | marker-v1 beta-5 migration selects base.en once, preserves prior/alternate models, and never resets later choice | migration unit | `pytest tests/test_runtime_bootstrap.py -q` | ❌ Wave 0 |
| RUNT-07 | healthy optional selection remains selected after CPU admission | unit | `pytest tests/test_cuda_engine.py -q` | ✅ extend |
| RUNT-08 | broken CUDA/Vulkan/custom resolves CPU + structured notice/no network | unit/controller | `pytest tests/test_cuda_engine.py tests/test_runtime_bootstrap.py -q` | ◐ extend |
| RUNT-09 | ADR has all mandatory fields; known-good/bad verifier vectors once approved | documentation/static test + manual approval | `pytest tests/test_signing_adr_contract.py -q` | ❌ Wave 0; human checkpoint |

### Required test matrix

- Inventory: missing, empty, unreadable, byte-corrupt each executable/model/DLL including every resolved `ggml-cpu-*.dll`; absolute/traversal/duplicate inventory entry; changed app version/identity. [VERIFIED: `tests/test_beta3_packaging.py:73-91`; `01-CONTEXT.md` D-02–D04]
- Bootstrap: fresh, healthy light launch, stale saved paths, partial facts, identity-changed full smoke, update/repair-forced full smoke; persistence only after all checks pass. Add beta-5 configs with no marker, healthy CUDA/Vulkan/custom, broken optional engine, alternate prior model, migration failure, marker `1` plus later user-selected model, and two consecutive launches; assert one atomic migration and no second-launch reset. [VERIFIED: `01-CONTEXT.md` D-03–D09]
- Smoke: validate the exact packaged argument vector and `runtime-smoke.wav` inventory hash/format; cover ffmpeg/ffprobe success, nonzero, no-output hang/timeout, Whisper stable success prefixes, missing CPU DLL, bad model, unreadable WAV, nonzero, and timeout. Assert captured argv/exit/stdout/stderr/duration/reason and no `-of`/output artifact. [VERIFIED: `01-CONTEXT.md` D-12–D13; packaged read-only probe on 2026-07-28]
- Ordering: fake slow/failed bootstrap verifies no `JobController`, `on_ui_ready`, job signal, Ollama probe, CUDA/Vulkan validation, or demo action prior to `HEALTHY`; success verifies exactly one normal-ready sequence. [VERIFIED: `app/desktop/engine_adapter.py:694-720,951-971`; `01-CONTEXT.md` D-05]
- Optional engines: CPU only; valid saved CUDA/custom; missing CUDA driver/executable/DLL; Vulkan unavailable; preserve valid preference, CPU fallback notice, zero admission network calls. [VERIFIED: `lecturepack/infrastructure/transcription_engines.py:194-272`; `tests/test_cuda_engine.py`]
- Packaged smoke (required completion evidence): copy a clean onedir fixture/path with spaces and non-ASCII characters, set a fresh `LECTUREPACK_DATA_DIR`, and execute the exact real CLI/model/`smoke/runtime-smoke.wav` argument vector. Require normal exit `0`, backend-DLL/model/WAV/processing markers, elapsed <30 s, no transcript artifact, and a persisted healthy identity; separately force timeout to prove the gate stays closed. This remains a Phase-1 targeted/disposable proof, not Phase-5’s full physical matrix. [VERIFIED: `tests/test_data_dir_override.py:1-109`; `01-CONTEXT.md` D-13]

### Sampling Rate

- **Per task commit:** targeted command above, plus any directly affected existing test file.
- **Per wave merge:** `pytest`.
- **Phase gate:** targeted + full output, disposable-profile packaged/bootstrap smoke evidence, and a human-approved RUNT-09 ADR before Phase 2. [VERIFIED: `AGENTS.md`; `.planning/ROADMAP.md`]

### Wave 0 Gaps

- [ ] `tests/test_runtime_inventory.py` — canonical entry/path/identity/package-consumer fault matrix.
- [ ] `tests/test_runtime_bootstrap.py` — persistence, light/full policy, runner evidence, ordering, migration, fallback notice.
- [ ] `app/packaging/assets/runtime-smoke.wav` — checked-in, project-owned deterministic 1.000 s 16 kHz mono `pcm_s16le` tone; copied to `smoke/runtime-smoke.wav` and included in canonical inventory/package gate.
- [ ] `tests/test_runtime_packaged_smoke.py` — exact real packaged CLI/model/WAV execution and evidence assertions under a disposable Unicode/space path.
- [ ] `tests/fixtures/mock_runtime_hang.py` — deterministic no-output hang; do not use real binaries for timeout branch.
- [ ] `tests/test_signing_adr_contract.py` — required ADR fields and known-good/altered-byte vector after approval.
- [ ] Packaged disposable subprocess harness/fixture — no mocks as proof for the real CPU payload.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | no | No remote user authentication in Phase 1. [VERIFIED: `docs/PRODUCT_SPEC.md`] |
| V3 Session Management | no | No account/session protocol. [VERIFIED: `docs/PRODUCT_SPEC.md`] |
| V4 Access Control | yes (release trust boundary) | Only an approved embedded public key/verifier may authorize repair manifest content; implementation deferred to Phase 2. [VERIFIED: `01-CONTEXT.md` D-10–D11] |
| V5 Input Validation | yes | Canonical relative inventory, root containment, strict JSON/schema and bounded process arguments. [VERIFIED: `01-CONTEXT.md` D-02, D-12] |
| V6 Cryptography | yes | No custom crypto; ADR-approved detached signature verifier only; SHA-256 handles payload identity, not authenticity. [VERIFIED: `01-CONTEXT.md` D-10–D11] |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Tampered/mixed runtime payload | Tampering | Exact canonical inventory plus full smoke; Phase 2 signature + per-file hash + staged transaction. [VERIFIED: `01-CONTEXT.md` D-02, D-10] |
| Path traversal in future manifest/archive | Tampering/Elevation | Reject absolute/`..`/duplicate/out-of-root entries before any write; Phase 1 defines schema seam. [VERIFIED: `.planning/MILESTONE-CONTEXT.md`] |
| CLI hang or hostile Unicode path | Denial of service/Tampering | Bounded QProcess, separate arguments, captured diagnostics; terminate smoke tree only. [VERIFIED: AGENTS.md; `01-CONTEXT.md` D-12] |
| Optional engine causes degraded availability | Denial of service | CPU-only admission and post-health fallback notice without automatic downloads. [VERIFIED: `01-CONTEXT.md` D-07–D08] |

## Sources

### Primary (HIGH confidence)

- `01-CONTEXT.md` — locked decisions D-01 through D-14 and phase boundary.
- `app/desktop/main.py:182-212`, `app/desktop/engine_adapter.py:694-720,951-971` — actual startup ordering seam.
- `lecturepack/infrastructure/config_manager.py:36-159`, `transcription_engines.py:194-272`, `app/packaging/build.py:95-199` — current discovery/optional/package contracts.
- `tests/test_beta3_packaging.py`, `tests/test_data_dir_override.py`, `tests/test_adapter_startup.py`, `tests/test_cuda_engine.py` — reusable test seams.
- [Cryptography Ed25519 official documentation](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) — candidate API/encoding behavior.
- [Cryptography installation official documentation](https://cryptography.io/en/latest/installation/) — current Windows wheel characteristics.
- [PyInstaller usage documentation](https://pyinstaller.org/en/stable/usage.html) — onedir and binary/import collection controls.

### Secondary (MEDIUM confidence)

- [Microsoft CNG provider documentation](https://learn.microsoft.com/en-us/windows/win32/seccng/cng-cryptographic-algorithm-providers) — documented provider capabilities informing the platform-alternative caution.
- [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html) — argument-list/shell safety corroboration.

### Tertiary (LOW confidence)

- Time-budget calibration and exact canonical JSON/signature encoding are deliberately unapproved design proposals pending physical measurement and ADR approval.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for existing stack; MEDIUM for verifier candidate because it is intentionally unapproved.
- Architecture: HIGH — startup/config/package/test seams are repository-backed.
- Pitfalls: HIGH — each maps to locked phase decisions and current code.

**Research date:** 2026-07-28  
**Valid until:** 2026-08-04 for verifier/package documentation; repository evidence remains valid until code changes.
