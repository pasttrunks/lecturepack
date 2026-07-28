# Phase 2: Hard Setup & Signed Repair - Research

**Researched:** 2026-07-28  
**Domain:** Windows portable-runtime admission, authenticated release repair, and blocking WebEngine UI  
**Confidence:** HIGH for repository/locked-contract scope; MEDIUM for platform/library implementation details

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Present setup-required state as a full-viewport blocking overlay above the existing app; preserve the beta-5 visual language exactly, including animation character, hard dark shadows, embedded pressed-button behavior, motion, and transitions.
- The gate must expose calm plain-language failed-component summaries; Repair all, Retry, diagnostics, and Exit; explicit confirmation before download; progress/cancel/failure/offline/success states exactly as specified in D-01 through D-18.
- Implement AD-19 exactly: `cryptography==49.0.0`; pure Ed25519 detached signature over exact canonical manifest bytes; compiled 32-byte raw public key as 64 lowercase hexadecimal characters; raw 64-byte signature; exact schema/version/origin/release-asset contract; no manual import, telemetry, per-file repair, or unrelated network access.
- Build a complete generation in writable app-managed storage; atomically activate only after complete validation; preserve/restore the previous generation on cancellation or failure; rerun full runtime admission and enter without restart.
- Production verifier, release trust module, repair-consumer integration, and frozen-runtime self-test are Phase 2 work. Broader flicker/artifact cleanup is deferred.

### the agent's Discretion

- Exact friendly labels/microcopy, bounded retry/backoff policy, new-state transition timing/easing, technical-details layout, and sanitized report formatting, while retaining the locked visual conventions.

### Deferred Ideas (OUT OF SCOPE)

- Broader fixes for visual artifacts, unwanted flicker, and animation bugs; offline package import; manual per-component repair; redesign/reduced-motion work.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| REPR-01 | Unhealthy required component hard-gates normal entry. | Reuse `RuntimeBootstrapService` result and guarded bridge; add overlay bootstrap consumer. |
| REPR-02 | Plain-language gate actions and diagnostics. | Deterministic overlay state machine plus existing diagnostics snapshot. |
| REPR-03 | Explicit consent shows version, source, contents, size. | The user may acquire only the exact manifest and detached signature after **Repair all**, before consent; signature-verified manifest data supplies the exact component list and byte total. No ZIP payload request occurs before **Confirm & repair**. |
| REPR-04 | Exact-version official GitHub only, no unrelated network. | Construct URLs from compiled version and fixed `github.com/pasttrunks/lecturepack/releases/download/v{version}/` base. |
| REPR-05 | Verify signature then every payload hash/inventory. | Exact-byte verifier, strict schema, allow-listed archive inventories, streamed SHA-256. |
| REPR-06 | Reject invalid/mixed/unsafe/incomplete content. | Fail-closed parser/extractor and no activation until complete generation validates. |
| REPR-07 | Writable complete generation and atomic activation. | Generation root under `LECTUREPACK_DATA_DIR`; pointer/rename activation, never bundle mutation. |
| REPR-08 | Failure/cancel retains/restores prior generation and diagnostics. | Safe-boundary cancellation state and journaled rollback/failure evidence. |
| REPR-09 | Full revalidation then automatic entry. | Reassess with `trigger="repair"`; construct adapter/updater only after HEALTHY. |
| REPR-10 | Offline retry/diagnostics/exit only. | Network error classification maps to gate state; do not expose imports/browsing. |
</phase_requirements>

## Project Constraints (from AGENTS.md)

- Work only in the approved phase and permitted files; do not begin later phases without approval.
- Preserve application functionality, comments/docstrings, original lecture videos, and separation of source-derived versus AI content.
- Run relevant tests and report actual `pytest` output; do not weaken tests or treat mocks as external-integration proof.
- Do not replace the approved stack or add unapproved dependencies; record material decisions in `docs/DECISIONS.md` during implementation.
- No credentials, telemetry, analytics, advertising, or network requests beyond allowed scoped use; safely escape any external-process paths.
- Use a clean phase branch, commit passing states, and never use destructive Git recovery commands. [VERIFIED: AGENTS.md]

## Summary

Phase 1 already provides the correct admission seam: `Backend` runs `RuntimeBootstrapService.assess()` before it constructs either the engine adapter or updater; unhealthy state exposes a canonical JSON snapshot through `get_bootstrap()` and guards normal bridge operations. Phase 2 should retain this ownership and add only a narrowly scoped repair coordinator that can be called while the gate is active. The UI currently reads theme/version during bootstrap but ignores `runtime_health_state` and `setup_required`, so `app/ui/app.js` plus a new overlay section in `index.html` are the direct gate integration points. [VERIFIED: repository inspection]

The repair must be a two-phase transaction: authenticate fixed-name bytes from the exact version's GitHub release, build an entirely new writable generation under the app data directory, validate it as the canonical runtime, then atomically select it. The immutable PyInstaller bundle remains an input/fallback only. This is necessary because current `cuda_pack` flattens selected archive names and the existing updater downloads directly to a cache; both are useful lifecycle examples but violate the Phase 2 complete-inventory contract if reused as installers. [VERIFIED: repository inspection]

**Primary recommendation:** implement a pure `release_trust` + `runtime_repair` service layer with strict data types and fault-injectable filesystem/network seams; have a QThread bridge coordinator emit a small documented repair-event protocol into one deterministic setup-overlay state machine.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Startup admission and normal-operation withholding | Desktop backend | Service | Bridge owns construction order; bootstrap service owns runtime evidence. [VERIFIED: repository inspection] |
| Signed manifest/authenticated acquisition | Service | Infrastructure | Policy must be testable without Qt; HTTP, hashing, and filesystem are injected infrastructure. |
| Archive inspection/extraction and staged generation | Infrastructure | Service | Untrusted ZIP bytes and path containment belong below policy; service controls ordered transaction. |
| Generation activation/rollback | Infrastructure | Service | Pointer/current-generation mutation is atomic filesystem state governed by repair transaction. |
| User consent/progress/diagnostics | Browser / Client | Desktop backend | UI owns presentation/state transitions; bridge owns narrow commands and event delivery. |
| Post-repair admission and adapter construction | Desktop backend | Service | Only `HEALTHY` may create adapter/updater; re-assessment is canonical. [VERIFIED: repository inspection] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---:|---|---|
| `cryptography` | `49.0.0` | Ed25519 detached signature verification | Locked by AD-19. Its Ed25519 API accepts raw 32-byte public bytes and verifies signature/data, raising on invalid signatures. [CITED: https://cryptography.io/_/downloads/en/49.0.0/pdf/] |
| Python stdlib `hashlib`, `json`, `zipfile`, `urllib.request`, `pathlib` | Python 3.12 | SHA-256, strict canonical JSON checks, ZIP inspection, scoped HTTPS, path containment | No additional runtime dependency is needed for acquisition/extraction. [VERIFIED: repository inspection] |
| PySide6 `QThread`/signals | existing | Repair orchestration and UI events | Matches the desktop project's established background-work pattern. [VERIFIED: app/desktop/updater.py] |

### Supporting

| Library / facility | Purpose | When to Use |
|---|---|---|
| `RuntimeBootstrapService.assess(trigger="repair")` | Full post-repair admission and persisted evidence | After activation; never substitute a hand-written “looks installed” check. [VERIFIED: lecturepack/services/runtime_bootstrap.py] |
| `RuntimeInventory`/`resolve_inventory`/`payload_identity` | Canonical component identities and containment | Stage validation and generation revalidation. [VERIFIED: lecturepack/infrastructure/runtime_inventory.py] |
| `RuntimeValidator` | Bounded CLI smoke evidence | Full admission remains the actual runtime usability proof. [VERIFIED: lecturepack/infrastructure/runtime_validation.py] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| In-process `cryptography` Ed25519 | Windows CNG or external PowerShell/certutil | Rejected by AD-19: creates project-owned native/key-import/shell variability. [VERIFIED: docs/DECISIONS.md AD-19] |
| New generation transaction | Existing CUDA pack extraction/direct updater cache | Rejected: neither validates the complete fixed inventory nor guarantees a rollback-safe active runtime. [VERIFIED: repository inspection] |

**Installation:** `cryptography==49.0.0` is already present in `app/requirements.txt`; implementation must add the same approved pin to the second approved requirements file, verify the AD-19 Windows x64 wheel hash before use, and record actual install evidence. [VERIFIED: app/requirements.txt; docs/DECISIONS.md AD-19]

## Package Legitimacy Audit

| Package | Registry | Verdict | Disposition |
|---|---|---|---|
| `cryptography==49.0.0` | PyPI | SUS (seam reported unknown downloads/no repository metadata) | Locked by approved AD-19; retain exact pin but planner must include `checkpoint:human-verify` for PyPI project/Windows-wheel SHA-256 before installation/use. `pip index versions` confirms 49.0.0 exists. [ASSUMED] |

**Packages removed due to [SLOP] verdict:** none.  
**Packages flagged as suspicious [SUS]:** `cryptography` — human verification checkpoint required despite the locked ADR.

## Architecture Patterns

### System Architecture Diagram

```text
App start
  -> RuntimeBootstrapService.assess()
  -> HEALTHY -> construct adapter + updater -> normal application
  -> SETUP_REQUIRED -> get_bootstrap() snapshot -> blocking web overlay
       -> Retry -> assess() again
       -> Repair all -> manifest + signature metadata only -> verify -> confirmation -> Confirm & repair
          -> QThread repair coordinator
          -> exact fixed GitHub URLs -> manifest bytes + .sig
          -> verify raw signature BEFORE JSON parse
          -> strict manifest/schema/inventory validation
          -> download ZIP assets to transaction staging
          -> inspect member names, sizes, duplicates; extract allow-listed files
          -> hash every staged file + canonical generation admission
          -> atomic active-generation switch
          -> assess(trigger="repair")
             -> HEALTHY -> construct collaborators -> You're ready -> dismiss overlay
             -> failure/cancel -> retain previous active generation -> setup gate + diagnostics
```

### Recommended Project Structure

```text
lecturepack/
  infrastructure/
    release_trust.py          # compiled public key, exact-byte manifest verifier, schema/canonical checks
    runtime_generation.py     # generation paths, staging, safe ZIP extraction, activation/recovery
  services/
    runtime_repair.py         # ordered repair state machine, retry/cancel/error result model
app/desktop/
  bridge.py                   # only repair slots/signals and post-repair collaborator construction
  repair_worker.py            # QThread wrapper around service; no trust policy
app/ui/
  index.html                  # setup overlay markup reusing existing CSS tokens/classes
  app.js / bridge.js          # overlay reducer, bridge event names and commands
tests/
  test_release_trust.py
  test_runtime_generation.py
  test_runtime_repair.py
  test_setup_gate_repair.py
```

### Pattern 1: Authenticate bytes before interpretation
**What:** Download only the fixed manifest and `.sig` names for `version.__version__`; reject wrong URL/content type/length as applicable; verify raw signature length is exactly 64 and call Ed25519 verify against the original response bytes. Only then decode UTF-8 and parse with duplicate-key detection; reject unknown/missing fields and reject any reserialized form that differs from required canonical bytes. [VERIFIED: docs/DECISIONS.md AD-19]

**Why:** Signature-valid JSON is not enough if a tolerant parser accepts duplicate keys, extra schema fields, noncanonical whitespace, or an altered version/inventory after parsing. The cryptography API takes raw public bytes and verifies exact data; `from_public_bytes` requires a 32-byte key. [CITED: https://cryptography.io/_/downloads/en/49.0.0/pdf/]

### Pattern 2: Allow-list archive extraction, never generic extraction
**What:** For each fixed archive, precompute the exact expected relative members from the signed manifest/canonical inventory. Reject duplicate members, directories/symlinks/special entries, absolute/drive/UNC/backslash paths, `.`/`..`, unexpected archive members, omitted members, filename case collisions, over-limit member/total uncompressed size, and size/hash mismatch. Stream each accepted member to a new staging root using `Path.resolve()` plus a `relative_to(staging_root)` containment check; then hash the written file. Do not call `extractall`. [CITED: https://docs.python.org/3.13/library/zipfile.html]

**Why:** Python documents that untrusted ZIP extraction requires inspection; ZIP path helpers do not sanitize names for callers. Windows Unicode and space paths are safe when passed as `Path`/argument-list values, but archive names themselves must remain the strict forward-slash canonical inventory format. [CITED: https://docs.python.org/3.13/library/zipfile.html]

### Pattern 3: Generation transaction with durable recovery
**What:** Use `<data-dir>/runtime/generations/<generation-id>/` for immutable complete generations, `<data-dir>/runtime/active.json` as the sole active-generation pointer, and `<data-dir>/runtime/repair-journal.json` as the sole in-progress transaction record. A generation contains the canonical relative inventory exactly as defined below; it is never altered after its inventory/hash validation starts. Do not mutate `resource_dir`, `sys._MEIPASS`, or portable-bundle files. [VERIFIED: project constraints; `runtime_inventory.py`; AD-19]

`active.json` is canonical UTF-8 JSON with `schema_version: 1`, `generation_id`, `app_version`, and `payload_identity`; it contains no arbitrary path. The resolver derives the generation path from the ASCII UUID-like `generation_id`, rejects an invalid/missing/escaping target as `SETUP_REQUIRED`, and otherwise returns that generation root to *all* runtime consumers. An absent pointer is the only first-install condition and resolves to the immutable bundled root; Phase 2 never copies the bundle to seed a writable generation. [VERIFIED: `ConfigManager.resource_dir`; `RuntimeBootstrapService`; `runtime_inventory.py`]

`repair-journal.json` is canonical UTF-8 JSON with `schema_version: 1`, `operation_id`, `state` (`staging`, `activating`, `revalidating`), `candidate_generation_id`, `previous_active` (the complete prior pointer object or `null`), and `app_version`. It is atomically written before work begins and retained until the candidate has passed `assess(trigger="repair")`. Write each JSON file to a unique sibling temporary file, flush and `os.fsync()` the file, then call `os.replace(temp, target)` without deleting `target` first; a bounded retry on `PermissionError` may retry the replace but must never fall back to delete-then-rename. [VERIFIED: `docs/ARCHITECTURE.md` atomic-write contract; `app/desktop/updater.py` same-directory replace pattern]

**Activation and recovery rule:** Before activation, validate the candidate's complete inventory and signed archive-derived file set. Set journal state `activating`, then replace only `active.json` as one indivisible, non-cancellable boundary. Set journal state `revalidating`, run complete admission on the candidate, then delete the journal only after `HEALTHY`. A cancel before that boundary deletes only private staging and leaves the old pointer unchanged; a cancel received after activation finishes revalidation and reports its real terminal result rather than claiming cancellation. On startup: `staging` removes only its candidate staging tree; `activating`/`revalidating` requires a full candidate admission, commits if healthy, otherwise atomically restores `previous_active` (or removes the pointer if it was `null`) before removing the candidate. A first-install failure/cancel leaves `active.json` absent and the setup gate remains active. [VERIFIED: `RuntimeBootstrapService.assess(trigger="repair")`; `docs/ARCHITECTURE.md` recovery contract; CONTEXT.md D-21/D-22]

### Pattern 4: Explicit overlay reducer and safe cancellation boundaries
**What:** Define client states `gate`, `diagnostics`, `confirm`, `repairing`, `offline`, `failed`, `ready`; server events `metadata_ready`, `started`, `progress`, `retrying`, `cancel_requested`, `cancelled`, `failed`, `activated`, `admitted`. The UI enters `confirm` only on `metadata_ready` for the active operation id, and it never infers success from percentage/progress or dismisses before `admitted`. Cancellation is accepted between acquisition, archive, extraction, and validation units; the `active.json` replace plus mandatory post-activation admission is the indivisible boundary described above. [VERIFIED: UI-SPEC progress/cancellation contract; CONTEXT.md D-06/D-12/D-22]

### Anti-Patterns to Avoid

- **Reuse `cuda_pack.extract_pack`:** it flattens names and accepts selected files, which destroys the signed inventory mapping. [VERIFIED: app/desktop/cuda_pack.py]
- **Reuse updater host flexibility/testing overrides in production:** repair URL construction must be exact, not feed-driven or test-host-widened. [VERIFIED: app/desktop/update_service.py; docs/DECISIONS.md AD-19]
- **Construct adapter/updater to run repair:** unhealthy state intentionally has neither collaborator; add dedicated bridge-owned repair collaborators. [VERIFIED: app/desktop/bridge.py]
- **Only verify ZIP hash:** each final staged payload must be checked against signed file identity/inventory, and complete admission must run after activation. [VERIFIED: requirements REPR-05–09]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Ed25519 | Native crypto binding or custom signature math | `cryptography==49.0.0` Ed25519 | AD-19 locks a maintained in-process verifier. [VERIFIED: docs/DECISIONS.md AD-19] |
| Runtime usability proof | Presence/size-only repair check | Canonical bootstrap full smoke | DLL/model/CLI failure can pass presence checks. [VERIFIED: lecturepack/services/runtime_bootstrap.py] |
| UI animation system | New repair design tokens/motion | Existing `.lp-hit`, `.lp-press`, overlay/motion conventions | Visual language is locked unchanged. [VERIFIED: CONTEXT.md D-05] |

## Common Pitfalls

### Pitfall 1: Treating a PyInstaller resource root as writable
**What goes wrong:** Writing repaired assets under `sys._MEIPASS` or the installation bundle fails on locked/read-only portable folders and can invalidate the packaged app.  
**How to avoid:** Keep bundle resolution for read-only fallback resources; place generations under the configurable data directory. PyInstaller documents that one-folder resources live under `_internal` via `_MEIPASS`. [CITED: https://pyinstaller.org/en/stable/runtime-information.html]

### Pitfall 2: A cancel races activation
**What goes wrong:** A cancel arriving during direct replacement can expose partial content or misreport success.  
**How to avoid:** Check cancel before/after every acquisition, archive, extraction, and validation unit. Treat `active.json` replacement followed by mandatory full admission as the indivisible boundary: after it starts, finish recovery/admission and report the actual terminal result; never overwrite a successful admission with a synthetic `cancelled` result. [VERIFIED: CONTEXT.md D-12/D-22; UI-SPEC progress/cancellation contract]

### Pitfall 3: Phase 1 still validates the bundle, not the active repaired generation
**What goes wrong:** `RuntimeBootstrapService` defaults its root from `config.resource_dir`; a successful repair outside the bundle would not be consumed unless root resolution becomes active-generation aware.  
**How to avoid:** Make one canonical runtime-root resolver return the active verified generation when present, otherwise bundled root; feed it to bootstrap, diagnostics, inventory, packaging test seams, and repair. This is the explicit Phase 1 repair-consumer gap. [VERIFIED: lecturepack/services/runtime_bootstrap.py; CONTEXT.md D-23]

### Pitfall 4: “Official GitHub only” accidentally permits redirects or tests in production
**What goes wrong:** A generic URL downloader can follow a cross-origin redirect or a configurable host.  
**How to avoid:** Construct only the locked HTTPS base + fixed encoded filename; validate initial/final URL host/path and reject origin changes. Keep any injected local transport strictly test-only and absent from production construction. [ASSUMED]

## Code Examples

### Ed25519 exact-byte verification

```python
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

def verify_manifest(raw_manifest: bytes, raw_signature: bytes, public_key_hex: str) -> None:
    if len(raw_signature) != 64:
        raise ValueError("signature must be exactly 64 raw bytes")
    if len(public_key_hex) != 64 or public_key_hex.lower() != public_key_hex:
        raise ValueError("public key must be 64 lowercase hex characters")
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(raw_signature, raw_manifest)
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("manifest signature rejected") from exc
```

Source: [cryptography Ed25519 API](https://cryptography.io/_/downloads/en/49.0.0/pdf/). The subsequent canonical-JSON/schema checks are project-required policy, not a cryptography feature. [CITED: https://cryptography.io/_/downloads/en/49.0.0/pdf/]

## State of the Art

| Old Approach | Current Phase 2 Approach | Impact |
|---|---|---|
| Bundle presence/size validation and direct optional CUDA pack install | Signed exact-version, complete writable generation with canonical admission | Repair becomes authenticated and rollback-safe instead of best-effort. [VERIFIED: repository inspection] |
| UI bootstrap consumes only theme/version | Bootstrap consumes canonical setup-required state | Gate becomes a real entry boundary rather than a diagnostics-only backend state. [VERIFIED: app/ui/app.js; app/desktop/bridge.py] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | A redirect-aware strict transport can reliably enforce final official GitHub origin with stdlib `urllib`. | Pitfall 4 | Must be proven with transport tests before network implementation. |

## Resolved Planning Decisions

### R1. AD-19 release layout and member-to-component contract

The six AD-19 release assets are exact, and the manifest/signature are release metadata only: neither is extracted into a generation. The four ZIPs always create one **complete** candidate generation; repair never downloads only a failed individual component. The signed manifest's four archive records use these exact `component`, `file_name`, and `size_bytes` values:

| Release asset role | Manifest `component` | Exact `file_name` | Allowed ZIP members (forward slash only) | Staged destination and canonical ownership |
|---|---|---|---|---|
| Manifest | `runtime-manifest` | `LecturePack-{app_version}-RuntimeManifest-v1.json` | Not a ZIP; verify raw bytes then parse. | Metadata only; owned by `release_trust`, never installed. |
| Detached signature | `runtime-manifest-signature` | `LecturePack-{app_version}-RuntimeManifest-v1.json.sig` | Not a ZIP; exactly 64 raw bytes. | Metadata only; owned by `release_trust`, never installed. |
| FFmpeg ZIP | `ffmpeg` | `LecturePack-{app_version}-Runtime-ffmpeg.zip` | `bin/ffmpeg.exe`; `bin/ffprobe.exe` | `<candidate>/bin/ffmpeg.exe`, `<candidate>/bin/ffprobe.exe`; static entries in `runtime_inventory._STATIC_ENTRIES`. |
| Whisper CPU ZIP | `whisper-cpu` | `LecturePack-{app_version}-Runtime-whisper-cpu.zip` | `bin/ggml-base.dll`; `bin/ggml.dll`; `bin/whisper-cli.exe`; `bin/whisper.dll`; and one-or-more `bin/ggml-cpu-*.dll` names | Same relative paths under `<candidate>/bin/`; static entries plus the concrete CPU DLL names discovered from this archive are owned by `canonical_inventory()` / `inventory_for_root()`. |
| Base-English model ZIP | `model-base-en` | `LecturePack-{app_version}-Runtime-model-base-en.zip` | `models/ggml-base.en.bin` | `<candidate>/models/ggml-base.en.bin`; static entry in `runtime_inventory._STATIC_ENTRIES`. |
| Smoke-fixture ZIP | `smoke-fixture` | `LecturePack-{app_version}-Runtime-smoke-fixture.zip` | `smoke/runtime-smoke.wav` | `<candidate>/smoke/runtime-smoke.wav`; static entry in `runtime_inventory._STATIC_ENTRIES`. |

The archive records are the signed payload records: their SHA-256 and `size_bytes` authenticate the exact ZIP bytes before inspection. The member allow-list above then rejects every directory entry, symlink/special entry, duplicate, case-collision, backslash, absolute/drive/UNC path, traversal segment, unexpected member, missing required static member, or whisper ZIP with zero `ggml-cpu-*.dll` members. The wildcard is deliberately constrained to the existing canonical inventory rule; after extraction the concrete set is frozen by `inventory_for_root(candidate)` and must be identical for every later `resolve_inventory`, identity calculation, admission, diagnostics, and packaged-smoke call. There is no second repair-owned inventory. [VERIFIED: AD-19 asset contract; `runtime_inventory.py`; `app/packaging/build.py`]

The release workflow must create exactly these four ZIPs plus the manifest/signature, generate the manifest archive records from the ZIP bytes, sign its canonical bytes, and reject publication unless the extracted archive layout reconstructs the canonical inventory. It must be triggered by both a `v*` tag push and manual `workflow_dispatch` selecting an existing `v{app_version}` tag; both paths must check that tag-without-`v`, checked-out commit, manifest `app_version`, and `app/desktop/version.py::__version__` agree before signing/publishing. This replaces the current manual-only packaging workflow for Phase 2 planning; it is mandatory AD-19 scope, not optional release polish. [VERIFIED: AD-19; existing `.github/workflows/release.yml`; `app/desktop/version.py`]

### R2. Smoke fixture is a runtime-required canonical component

`smoke/runtime-smoke.wav` is runtime-required, not validation-only. `RuntimeBootstrapService._validate_full()` stages it with `models/ggml-base.en.bin` and invokes `whisper-cli.exe` against it; without it the mandatory full admission cannot establish health. Therefore the smoke fixture ZIP participates in the signed archive inventory, complete generation, `payload_identity`, repair rollback, startup admission, and packaged repaired-runtime smoke evidence exactly like the executables and model. It is never placed in a separate test-fixtures directory and is never omitted merely because the user did not select a diagnostic action. [VERIFIED: `runtime_inventory.py`; `RuntimeBootstrapService._validate_full()`; `app/packaging/build.py`; `tests/test_runtime_packaged_smoke.py`]

The Phase 2 packaged repair harness must copy a repaired complete generation to a disposable writable path containing both spaces and non-ASCII characters, resolve that generation through the active-generation resolver, and retain the same captured `RuntimeValidator` argv, exit code, duration, stdout, and stderr evidence already required for the bundled smoke. [VERIFIED: `tests/test_runtime_packaged_smoke.py`; 02-VALIDATION.md]

### R3. Authenticated metadata-before-consent and exact download size

Selecting **Repair all** starts a metadata-only operation. It may issue GET requests only for the fixed exact-version manifest and detached-signature URLs under the AD-19 origin. It verifies the 64-byte signature against the exact manifest bytes *before* parsing; then enforces canonical JSON, schema, `app_version`, signing key id, exactly the four ZIP records in R1, exact filenames/components, non-negative integer `size_bytes`, and valid lowercase SHA-256. It does not issue HEAD, range, or ZIP requests before **Confirm & repair**. [VERIFIED: AD-19; CONTEXT.md D-06/D-19/D-20]

The confirmation derives two separate truthful fields from this authenticated metadata and the current admission result: (1) **Affected components** is the friendly, deduplicated mapping of unhealthy canonical inventory paths to `Media tools`, `Speech runtime`, `Base English model`, and `Runtime check audio`; (2) **What will be repaired** says the entire four-archive runtime will be replaced safely, because atomic complete-generation activation requires all four archives even when only one component was unhealthy. **Download size** is the exact decimal sum of the four signed ZIP `size_bytes` values, with checked integer arithmetic; it is formatted only after computing the exact byte total. It must not use HTTP `Content-Length`, because that header is neither authenticated nor required. [VERIFIED: UI-SPEC confirmation fields; CONTEXT.md D-21; R1 contract]

If manifest/signature acquisition is offline, the gate enters the locked offline state. If the signature, schema, component set, archive size, or total is missing, invalid, negative, duplicate, or overflows the defined unsigned-64-bit total, the gate enters failed/diagnostics and does not present an enabled **Confirm & repair** action. Thus the UI never estimates, hides, or changes the bytes after consent, and no repair payload download occurs until a valid confirmation is shown and explicitly accepted. [VERIFIED: UI-SPEC offline/failure contract; CONTEXT.md D-06/D-07/D-19/D-20]

### R4. Active-generation resolver, pointer/journal, and rollback contract

`resolve_active_runtime_root(config)` is the one canonical resolver introduced before repair integration. It uses `config.resolve_data_dir()/runtime/active.json`; `RuntimeBootstrapService`, bridge collaborator construction, packaged-smoke harnesses, and repair receive its resolved root rather than independently reading `config.resource_dir`. `RuntimeDiagnosticsService` remains a projection of the bootstrap result obtained through that resolver. If no pointer exists, it returns the immutable bundled `config.resource_dir` (first install). If a pointer exists but is malformed, wrong-schema, wrong-app-version, noncanonical, points outside `runtime/generations`, or targets a missing/non-directory generation, it returns a setup-required resolver error rather than falling back to the bundle. [VERIFIED: `ConfigManager`; `RuntimeBootstrapService`; `RuntimeDiagnosticsService`; CONTEXT.md D-21/D-23]

The exact pointer and journal schemas, activation ordering, Windows atomic-write behavior, crash recovery, and cancellation invariants are specified in Architecture Pattern 3 and are test requirements, not implementation discretion. Wave 0 must parameterize pointer write/replace, process-crash-after-journal, process-crash-after-pointer-replace, cancelled-before-activation, invalid candidate admission, and first-install failure. Each case asserts that the prior generation's files and pointer meaning remain unchanged, no incomplete candidate is resolvable, and normal bridge collaborators remain absent until canonical `assess(trigger="repair")` reports `HEALTHY`. [VERIFIED: 02-VALIDATION.md; `RuntimeBootstrapService`; CONTEXT.md D-21/D-22]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---:|---|---|
| Python | repair service/tests | ✓ | 3.12.3 | — |
| pytest | validation | ✓ | 9.1.1 | repository pin/environment reconciliation required |
| PyInstaller | frozen verifier/package smoke | ✓ | 6.21.0 | — |
| `cryptography` | verifier | ✓ | 49.0.0 | no fallback; locked AD-19 |

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 9.1.1 installed; project tests use pytest/pytest-qt. [VERIFIED: environment; repository] |
| Config file | `pytest.ini` |
| Quick run command | `python -m pytest tests/test_release_trust.py tests/test_runtime_generation.py tests/test_runtime_repair.py tests/test_setup_gate_repair.py -q` |
| Full suite command | `python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| REPR-01/02 | unhealthy bootstrap produces non-dismissible overlay and all normal commands remain guarded | bridge/UI integration | targeted pytest | ❌ Wave 0 |
| REPR-03/04 | no request before confirm; exact only official version URLs; offline allowed actions only | service/UI unit | targeted pytest | ❌ Wave 0 |
| REPR-05/06 | real known-good vector; altered byte; malformed raw key/sig; duplicate/unknown JSON fields; wrong schema/version/key id; hashes; ZIP traversal/duplicates/extra/missing/mixed members | pure unit/fault matrix | targeted pytest | ❌ Wave 0 |
| REPR-07/08 | staged generation, permission/write/download/cancel/activation failures preserve pointer and byte-identical old generation | filesystem integration | targeted pytest | ❌ Wave 0 |
| REPR-09 | activated generation forces full admission and constructs collaborators only after success | bridge/service integration | targeted pytest | ❌ Wave 0 |
| REPR-10 | unavailable network maps to retry/diagnostics/exit and no import controls | UI integration | targeted pytest | ❌ Wave 0 |

### Required non-mock evidence

- Build a disposable PyInstaller onedir after the frozen verifier self-test loads the compiled key, accepts the real vector, and rejects one altered manifest byte; retain executable/wheel hashes, build log, and raw output per AD-19. [VERIFIED: docs/DECISIONS.md AD-19]
- Exercise real packaged required-runtime smoke after repair in a disposable `LECTUREPACK_DATA_DIR`, including a space/non-ASCII writable path and captured argv, exit code, duration, stdout, stderr. Existing `RuntimeValidator` already captures this evidence shape. [VERIFIED: lecturepack/infrastructure/runtime_validation.py; requirements REL-02/06]

### Wave 0 Gaps

- [ ] Add immutable signed manifest/vector fixtures and an explicit complete release-layout table.
- [ ] Add active-generation resolver contract tests before repair integration.
- [ ] Add repair transaction fault-injection filesystem transport fixtures; do not use actual GitHub for unit tests.
- [ ] Add visible/manual packaged UI gate evidence separate from Qt offscreen tests.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes | compiled Ed25519 trust root and exact-byte detached verification. [VERIFIED: docs/DECISIONS.md AD-19] |
| V4 Access Control | yes | non-dismissible gate and guarded bridge operations until HEALTHY. [VERIFIED: app/desktop/bridge.py] |
| V5 Input Validation | yes | strict manifest/ZIP allow lists, duplicate rejection, path containment, fixed URL construction. |
| V6 Cryptography | yes | `cryptography==49.0.0`; no custom cryptographic implementation. [VERIFIED: docs/DECISIONS.md AD-19] |

| Threat Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Tampered manifest/signature | Tampering | Verify signature before parse and canonical bytes/schema afterward. |
| Mixed release or swapped asset | Tampering | Exact app version, fixed asset names, signed hashes/inventory, no activation before complete validation. |
| ZIP traversal/bomb/duplicate member | Tampering/DoS | Pre-inspect allow list, containment, count/size limits, streamed extraction; never `extractall`. [CITED: https://docs.python.org/3.13/library/zipfile.html] |
| Partial/cancelled activation | Availability/Tampering | Staging plus atomic pointer and retained previous generation. |
| Unauthorized network | Information disclosure | Explicit consent gate and fixed official-origin transport; no telemetry paths. [VERIFIED: CONTEXT.md D-06/D-10/D-19] |

## Sources

### Primary

- [AD-19](../../../../docs/DECISIONS.md) — locked key, signature, schema, origin, asset, frozen-evidence contract.
- [Phase context](02-CONTEXT.md) — locked UX, trust, and scope decisions.
- [Runtime bootstrap](../../../../lecturepack/services/runtime_bootstrap.py), [runtime inventory](../../../../lecturepack/infrastructure/runtime_inventory.py), and [desktop bridge](../../../../app/desktop/bridge.py) — current integration seams.

### Secondary

- [cryptography 49 Ed25519 documentation](https://cryptography.io/_/downloads/en/49.0.0/pdf/) — raw key and verify API.
- [Python zipfile documentation](https://docs.python.org/3.13/library/zipfile.html) — untrusted archive caveats and path-sanitization limits.
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html) — frozen resource-root behavior.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — the exact dependency is locked and installed, while the legitimacy seam marked registry metadata SUS.
- Architecture: HIGH — based on locked contract and inspected existing seams.
- Pitfalls: MEDIUM — official ZIP/PyInstaller sources plus project-specific code inspection.

**Research date:** 2026-07-28  
**Valid until:** 2026-08-27 for repository architecture; reverify external dependency/docs at implementation.
