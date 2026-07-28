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
| REPR-03 | Explicit consent shows version, source, contents, size. | Acquisition plan fetches signed manifest only after confirm; presentation data derives from fixed asset contract. |
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
       -> Repair all -> confirmation -> Confirm & repair
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
**What:** Use `<data-dir>/runtime/generations/<generation-id>/` for immutable complete staged generations and a small `active.json` pointer written atomically (`temp` in same directory, flush/fsync, `os.replace`). Retain `previous_generation` in a transaction journal until full revalidation succeeds. At startup, recover an interrupted journal by selecting the last known valid pointer/generation and deleting only its private incomplete staging directory. Do not mutate `resource_dir`, `sys._MEIPASS`, or portable bundle files. [VERIFIED: project constraints; PyInstaller runtime layout]

**Activation rule:** Verify the full staged generation first; atomically replace only pointer metadata, not a populated directory. If revalidation after activation fails, atomically restore the prior pointer and report recovery. A first-install failure has no prior generation and must leave the pointer absent, thus stays gated. [ASSUMED]

### Pattern 4: Explicit overlay reducer and safe cancellation boundaries
**What:** Define client states `gate`, `diagnostics`, `confirm`, `repairing`, `offline`, `failed`, `ready`; server events `started`, `progress`, `retrying`, `cancel_requested`, `cancelled`, `failed`, `activated`, `admitted`. Permit cancellation only before activation; once the coordinator begins pointer replacement it finishes that small atomic operation, then returns `cancelled` if requested. The UI never infers success from percent/progress and never dismisses before `admitted`. [ASSUMED]

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
**How to avoid:** Check cancel before/after every network/extraction/validation unit and treat pointer replacement as an indivisible safe boundary with a durable prior pointer. [ASSUMED]

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
| A1 | `active.json` pointer replacement plus journal is the preferred Windows crash-recovery layout. | Architecture Pattern 3 | Planner must validate Windows rename/locking behavior with disposable package tests. |
| A2 | A redirect-aware strict transport can reliably enforce final official GitHub origin with stdlib `urllib`. | Pitfall 4 | Must be proven with transport tests before network implementation. |
| A3 | The explicit UI reducer states/events are sufficient without a more formal persisted state machine. | Architecture Pattern 4 | UI may mishandle late/stale events unless tokenized operation IDs are added. |

## Open Questions

1. **Archive member-to-component mapping is not yet specified by AD-19.**
   - What we know: fixed archives and canonical runtime inventory are locked.
   - What's unclear: exact member names for each ZIP, whether the smoke fixture is installed or validation-only, and download-size source when GitHub omits Content-Length.
   - Recommendation: first implementation plan creates/test-locks a release-layout table and manifest fixture before production download code.
2. **Active generation resolver integration.**
   - What we know: Phase 1 bootstrap defaults to `resource_dir`.
   - What's unclear: exact chosen config/journal schema and whether an existing bundle can seed a first writable generation.
   - Recommendation: make this a Wave 0 contract test; no repair service before every consumer uses the same resolver.

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
