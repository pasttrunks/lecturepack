# Phase 2: Hard Setup Gate and Signed Repair - Context

**Gathered:** 2026-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 blocks normal application entry whenever any required runtime component is missing, unreadable, corrupt, or unusable, then lets the user explicitly consent to a trustworthy repair. Repair must use only the exact running app version's official signed GitHub assets, validate the complete release, stage a complete replacement generation, activate it atomically, preserve the prior generation on failure or cancellation, fully revalidate success, and enter the app without a restart.

This phase owns the hard setup gate, consent flow, signed repair service, safe generation activation, recovery behavior, diagnostics, and automatic post-repair admission. It does not redesign the existing application, change its established visual language, add manual package import, or perform the broader artifact/flicker cleanup reserved for the later visual-quality phase.

</domain>

<decisions>
## Implementation Decisions

### Setup-gate presentation
- **D-01:** Present setup-required state as a full-viewport blocking overlay above the existing app. The app may remain visible underneath but is completely inaccessible until runtime health passes or the user exits.
- **D-02:** The first view is calm and plain-language. Technical evidence stays behind **Open diagnostics**.
- **D-03:** Use one compact **Runtime needs repair** summary followed by a short human-readable list of affected components, using labels such as **Media tools** and **Speech model**.
- **D-04:** Make **Repair all** the prominent primary action. Keep **Retry**, **Open diagnostics**, and an always-visible **Exit** as secondary actions.
- **D-05:** Preserve the beta-5 visual language exactly: existing animation character, hard dark button shadows, embedded pressed-button effect, motion, and transitions. Phase 2 may add the required gate states using those established patterns, but must not redesign them.

### Repair consent
- **D-06:** Selecting **Repair all** advances the same blocking overlay to a dedicated confirmation step with **Back** and **Confirm & repair**. No repair download begins before confirmation.
- **D-07:** Keep the main confirmation friendly and concise. Show **Official LecturePack release**, **Version**, **What will be repaired**, and **Download size** in plain language.
- **D-08:** Put the exact official source URL, signature facts, hashes, and other cryptographic evidence under expandable **Technical details**. Required trust evidence remains inspectable without dominating the primary view.
- **D-09:** Consent is one clear **Confirm & repair** click. Do not add a checkbox or legal-style warning.
- **D-10:** Include one short reassurance: **Downloads only from LecturePack's official GitHub release; no personal data or telemetry is sent.** Do not surround it with additional warning copy.

### Progress and failure recovery
- **D-11:** Show one animated progress bar with changing friendly step text, including **Downloading**, **Verifying**, **Installing safely**, and **Almost there**. Keep filenames and low-level operations out of the primary progress view.
- **D-12:** Keep **Cancel repair** visible throughout. Cancellation takes effect at the next safe boundary, returns to the setup gate, and leaves the previous runtime generation untouched.
- **D-13:** A failed repair stays in the same overlay and shows a short plain-language reason. Make **Try again** primary and retain **Open diagnostics** and **Exit**. Never direct users to replace individual files manually.
- **D-14:** Retry temporary connection interruptions automatically a limited number of times while showing **Connection interrupted - retrying...**. If retries are exhausted, expose the standard retry, diagnostics, and exit actions.

### Success, diagnostics, and offline behavior
- **D-15:** After full revalidation succeeds, briefly show **You're ready**, then dismiss the overlay and enter the app automatically without another click or restart.
- **D-16:** Keep diagnostics inside the setup overlay. Show a friendly summary first, expandable technical details, and **Back** rather than opening a separate window or raw log file.
- **D-17:** Diagnostics provide **Copy details** and **Save report**. Remove secrets while retaining useful local paths and failure evidence.
- **D-18:** When offline, clearly explain that an internet connection is required and expose only **Retry connection**, **Open diagnostics**, and **Exit**. Do not offer manual package import or per-file repair.

### Trust and repair contract carried into this phase
- **D-19:** Implement approved AD-19 exactly: `cryptography==49.0.0`; pure Ed25519 detached signatures; a compiled 32-byte raw public key represented as 64 lowercase hexadecimal characters; a 64-byte raw signature; exact-byte canonical manifest verification; exact release-version and schema checks; and the official origin `https://github.com/pasttrunks/lecturepack/releases/download/v{app_version}/`.
- **D-20:** Accept only the exact running version's signed manifest and canonical release assets. Reject invalid signatures, wrong versions or schemas, missing or extra inventory entries, unsafe paths, hash mismatches, and mixed-release content.
- **D-21:** Build and validate a complete generation in a writable app-managed location, then activate it atomically. Never modify the immutable portable bundle in place.
- **D-22:** Failure or cancellation retains or restores the previously active generation. Successful repair must run the complete runtime admission check before the gate may dismiss.
- **D-23:** Production trust verification, release trust module, repair consumer integration, and frozen-runtime self-test are Phase 2 work. The real repair consumer integration intentionally deferred from Phase 1 must be completed here.

### Execution process
- **D-24:** The primary agent remains engineer and orchestrator. Use lower-cost subagents for bounded research, implementation, and test work where parallel ownership is safe; the primary agent integrates results, enforces phase scope, and owns final verification.

### The agent's Discretion
- Exact component-friendly labels and microcopy, provided they remain calm, concise, and technically accurate.
- Exact duration and easing of new gate-state transitions, provided existing beta-5 animation/shadow/pressed-state conventions are reused.
- The bounded automatic network retry count and backoff policy.
- The exact layout of expandable technical details and sanitized report formatting.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and phase scope
- `AGENTS.md` — Mandatory phase discipline, safety, testing, documentation, and Git rules.
- `.planning/PROJECT.md` — Product-level goals, constraints, and milestone context.
- `.planning/REQUIREMENTS.md` — Phase 2 requirements REPR-01 through REPR-10.
- `.planning/ROADMAP.md` — Phase boundary, goal, requirement mapping, and success criteria.
- `.planning/MILESTONE-CONTEXT.md` — Locked milestone-wide user and product decisions.
- `.planning/phases/01-runtime-contract-bootstrap/01-CONTEXT.md` — Runtime admission and bootstrap contract inherited from Phase 1.

### Product and architecture
- `docs/PRODUCT_SPEC.md` — Canonical product behavior and safety expectations.
- `docs/ARCHITECTURE.md` — Architectural boundaries and runtime integration model.
- `docs/IMPLEMENTATION_PLAN.md` — Existing implementation sequence and file map; reconcile any stale wording with newer locked decisions rather than silently following it.

### Trust, dependency, and failure-mode decisions
- `docs/DECISIONS.md` — Approved architecture decisions, especially AD-19 signed release trust and repair.
- `.planning/research/STACK.md` — Approved dependency versions and runtime/packaging guidance.
- `.planning/research/PITFALLS.md` — Known repair, integrity, atomicity, packaging, and Windows-path failure modes.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/desktop/bridge.py`: Phase 1 admission runs before adapter/updater construction; setup-required bridge operations are already guarded and diagnostics are already emitted as JSON.
- `app/desktop/updater.py` and `app/desktop/update_service.py`: Existing GitHub release, download, cancellation, QThread, and signal patterns can inform the repair implementation, but their direct-to-live update mechanics do not satisfy the stricter signed-generation repair contract.
- `app/ui/bridge.js`: Existing bridge boundary for exposing setup state and adding narrowly scoped repair commands/events.
- `app/ui/app.js`: Existing bootstrap flow currently uses theme/version but does not consume `runtime_health_state` or `setup_required`; this is the primary gate integration point.
- `app/ui/index.html`: Existing overlays, buttons, motion, shadows, and pressed states are the visual source of truth for the new gate.
- Phase 1 runtime bootstrap, inventory, and diagnostics modules: Reuse their canonical component identities, admission result, inventory semantics, and diagnostic evidence rather than creating a parallel health model.

### Established Patterns
- Backend admission precedes construction of runtime-dependent services. Phase 2 must preserve that ordering and must not accidentally construct guarded services behind the gate.
- `get_bootstrap()` already exposes `runtime_health_state` and `setup_required`; the UI should derive hard-gate entry from that canonical result.
- Desktop background work uses explicit workers/signals and cancellation paths. New repair work should match those lifecycle patterns while enforcing stage-verify-activate atomicity.
- Existing web UI owns the beta-5 interaction language. New states must reuse those tokens and motion conventions instead of introducing a second design system.

### Integration Points
- Backend startup/admission -> setup-required state -> web bootstrap -> blocking overlay.
- Overlay consent -> narrow bridge repair API -> signed manifest fetch and verification -> staged generation assembly -> atomic activation -> full admission rerun.
- Repair progress/cancel/failure/success events -> bridge -> deterministic overlay state machine.
- Runtime diagnostics -> in-overlay friendly summary/technical details -> sanitized copy/save actions.

</code_context>

<specifics>
## Specific Ideas

- The gate should feel like the same polished beta-5 application, not a system error dialog: strong dark shadows, embedded button press, and existing motion are intentionally retained.
- The overlay keeps the app visible underneath to preserve orientation while making the blocked state unmistakable.
- Progress copy should evolve through human milestones so users can see continued activity even during non-download work.
- The experience stays as short and reassuring as the trust requirements allow; technical proof is available on demand rather than pushed into the main path.

</specifics>

<deferred>
## Deferred Ideas

- Broader fixes for visual artifacts, unwanted flicker, and animation bugs belong to the later visual-quality phase. Phase 2 must avoid introducing new artifacts, but it must not become a general UI cleanup or redesign.

</deferred>

---

*Phase: 02-hard-setup-signed-repair*
*Context gathered: 2026-07-28*
