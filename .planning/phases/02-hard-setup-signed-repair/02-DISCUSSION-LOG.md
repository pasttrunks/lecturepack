# Phase 2: Hard Setup Gate and Signed Repair - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-28
**Phase:** 02-hard-setup-signed-repair
**Areas discussed:** Setup-gate presentation, Repair consent, Progress and failure recovery, Success and diagnostics

---

## Setup-gate presentation

| Question | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Window occupation | Dedicated setup screen; disabled normal shell; blocking overlay above normal app | Blocking overlay above normal app |
| First-view technical depth | Calm explanation; error-focused component reasons; diagnostic-first technical view | Calm explanation; evidence under Open diagnostics |
| Component presentation | Compact human-readable list; different card/group presentation | Compact summary and human-readable list |
| Action hierarchy | Repair all primary with secondary actions; different hierarchy | Repair all primary; Retry, Open diagnostics, and always-visible Exit secondary |
| Visual behavior | Change visual language; preserve beta-5 behavior | Preserve animations, dark shadows, embedded press, motion, and transitions |

**User's choice:** A hard blocking overlay that stays calm, concise, and consistent with beta 5.
**Notes:** The user explicitly locked existing animation and button behavior. Only bugs, artifacts, and flicker may be corrected later; the visual character must remain unchanged.

---

## Repair consent

| Question | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Consent flow | Dedicated step before download; different or immediate flow | Dedicated confirmation with Back and Confirm & repair; no pre-consent download |
| Trust detail | Exact technical values upfront; friendly summary with technical disclosure | Friendly summary upfront; exact evidence under Technical details |
| Consent action | Single confirmation; checkbox/legal warning | Single Confirm & repair click |
| Privacy reassurance | One concise sentence; none or expanded warning | One concise official-source/no-telemetry reassurance |

**User's choice:** Keep the required confirmation friendly so ordinary users are not scared.
**Notes:** The primary view uses familiar labels. Exact source, signature, and hash evidence remains inspectable under Technical details.

---

## Progress and failure recovery

| Question | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Progress display | Friendly overall progress and current step; detailed per-file operations | Animated bar with Downloading, Verifying, Installing safely, and Almost there |
| Cancellation | Stop at a safe point with rollback; disallow cancellation | Always-visible Cancel repair, honored at the next safe point |
| Failure view | Friendly retry/diagnostics/exit; manual file guidance | Friendly reason with Try again primary, diagnostics, and exit |
| Temporary network failures | Limited automatic retries; fail immediately | Limited automatic retries with visible retrying status |

**User's choice:** Keep users visibly informed and in control without exposing low-level mechanics.
**Notes:** Cancellation and all failures preserve the previous generation. Manual per-file repair is prohibited.

---

## Success and diagnostics

| Question | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Success transition | Brief success then automatic entry; another click/restart | Brief You're ready state, then automatic entry without restart |
| Diagnostics location | In-overlay progressive disclosure; separate window/raw log | Friendly in-overlay summary with expandable details and Back |
| Support actions | Sanitized copy/save; read-only | Copy details and Save report with secrets removed |
| Offline behavior | Retry/diagnostics/exit; manual import or per-file repair | Retry connection, Open diagnostics, and Exit only |

**User's choice:** Keep completion automatic and diagnostics useful without leaving the gate experience.
**Notes:** Offline mode must not introduce manual package import or component-by-component replacement.

---

## The agent's Discretion

- Exact friendly component labels and concise microcopy.
- Exact new-state timing/easing within the existing beta-5 motion system.
- Bounded network retry count and backoff.
- Technical-details layout and sanitized diagnostic report format.

## Deferred Ideas

- General visual artifact, flicker, and animation-bug cleanup remains deferred to the later visual-quality phase; the visual language itself is locked.
