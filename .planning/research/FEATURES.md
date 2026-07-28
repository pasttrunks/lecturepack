# Feature Landscape: Beta 6 Clean-Machine Reliability and Onboarding

**Domain:** Windows portable desktop application setup, recovery, and first-run education  
**Researched:** 2026-07-27  
**Confidence:** MEDIUM — locked milestone decisions are authoritative; UX/security recommendations are corroborated by current Microsoft Learn guidance.

## Scope and Decision Boundary

This document translates the approved beta-6 milestone into user-facing requirements. It does **not** reopen the selected runtime, packaging architecture, privacy model, visual language, or release boundary. “Locked” rows repeat decisions from `.planning/MILESTONE-CONTEXT.md`; “recommendation” rows add implementation-level UX detail for roadmap and acceptance planning.

## Table Stakes

Features users need before they can trust a portable, offline-first desktop tool on a new Windows machine. Missing any of these makes the application feel broken or unsafe rather than merely incomplete.

| Feature | Status | Why Expected | Complexity | Requirements / UX notes |
|---|---|---|---|---|
| Deterministic preflight before Home | **Locked** | A user should not discover a missing transcription runtime only after importing a lecture. | High | On every launch perform lightweight required-runtime checks. First launch, update/repair, or changed payload identity additionally run full executable/DLL/model smoke checks. Healthy launch initializes silently and opens Home. |
| Hard required-runtime setup gate | **Locked** | The core offline pipeline cannot honestly be offered while FFmpeg, ffprobe, CPU Whisper CLI/DLLs, or `ggml-base.en.bin` are unavailable or corrupt. | High | Gate is the only startup surface until the required set validates. It names the missing/corrupt component(s), says that LecturePack cannot process lectures yet, and prevents entry to the main app. Do not present this as an optional tutorial or a dismissible toast. |
| One-click, explicitly consented repair | **Locked** | A repair path must remove manual file hunting while making the exceptional network action understandable. | High | The primary command is `Repair all…`, with an ellipsis because it opens a concise confirmation that shows the exact running app version, source (official LecturePack GitHub release), components/download size when known, and that download begins only after confirmation. Secondary commands: `Retry check`, `Open diagnostics`, `Exit LecturePack`. |
| Trustworthy repair outcome | **Locked** | Users must receive a clear result rather than ambiguous download progress. | High | Repair screen shows a restrained stage sequence: download → verify signed manifest → verify component hashes → install → recheck. On success automatically enter the empty Home screen without restart. On failure preserve the previous working runtime, explain the failed stage in plain language, and offer only actions that can help. |
| Offline-aware recovery choices | **Locked** | A blocked offline user needs a truthful route, not a dead-end spinner or generic “network error.” | Medium | If repair cannot contact the official release, retain the gate and offer `Retry check`, `Open diagnostics`, and `Exit LecturePack`. State that no files were installed or changed. Do not promise an offline repair option that beta 6 does not support. |
| Optional-engine graceful fallback notice | **Locked** | An optional CUDA/custom engine failure must not make a healthy CPU installation look broken. | Medium | If bundled CPU is healthy, enter Home and display one visible, non-blocking notice: the optional engine was unavailable, LecturePack switched to bundled CPU, and processing remains available. Include `View details` / Diagnostics. Preserve a healthy optional engine selection across upgrade; do not show the notice on ordinary CPU-only systems. |
| Empty, owned Home screen | **Locked** | A launch should begin in a predictable state and never expose a prior lecture as though it were the current task. | Medium | No automatic opening or active selection of the latest completed job. Existing jobs stay visible in the library and open only through explicit user action. Empty-state copy should direct users to `Add video` and, on the first healthy launch, make the separately chosen demo available. |
| First-success welcome choice | **Locked** | First-run guidance should teach without holding experienced users hostage. | Low | After the first successful runtime check, show a compact welcome choice: `Start guided demo` and `Skip for now`. Neither option is destructive; skipping enters empty Home. Do not automatically launch the tour, create a demo job, or make the welcome a recurring obstacle. |
| Concise, user-controlled spotlight tour | **Locked** | A feature-rich desktop workflow benefits from contextual orientation, but users need control over pace and exit. | Medium | Use an overlay anchored to real controls: arrows/circles/spotlights, `Back`, `Next`, visible step position, and a persistent `Exit demo`. Limit it to the core path: import → configure/start → monitor → review → export. Every spotlight target must remain usable and keyboard focusable or have an equivalent labeled command. |
| Real isolated demo lecture | **Locked** | A demo is credible only when it proves the real core workflow, not a canned animation or fake data. | High | Bundle an original 45–90 second lecture with simple slides and narration; it must contain no university/student/third-party copyrighted content. Run the real offline import, process, transcript/slide review, study-pack generation, and export-location explanation in a temporary isolated workspace. The synthetic source and derived job never enter the normal library. |
| Demo lifecycle clarity and cleanup | **Locked** | The demo must leave neither confusing library content nor an opaque residue on disk. | High | Explain before/at completion that demo artifacts are temporary. Remove the workspace on normal exit; safely sweep abandoned work after cancellation/crash. Settings exposes `Replay guided demo`; replay starts a fresh isolated workspace. |
| Actionable diagnostics language | **Recommendation** | Technical reports are useful for support, but ordinary users need a short diagnosis and a next action. | Medium | Use a two-layer message: a plain-language summary first, optional `Details`/`Copy report` second. Include component name, detected condition, expected release/version if relevant, safe next action, and a stable error/diagnostic code. Never blame the user, expose a raw stack trace as the primary explanation, or label a fixable condition “fatal.” |

## Differentiators

These are not additional product scope; they are quality properties that make the locked beta-6 experience feel deliberate and trustworthy.

| Feature | Status | Value Proposition | Complexity | Notes |
|---|---|---|---|---|
| Repair confirmation with provenance | **Recommendation within locked repair model** | Lets users understand why a local-first app is requesting the release download, increasing informed consent without extra configuration. | Low | Keep the confirmation short: “Download the verified runtime for LecturePack {version} from the official release?” Reveal file list/size and signature/hash detail in an expandable Details area. The primary action must say `Download and repair`, not `OK`. |
| Component-specific failure explanation | **Recommendation** | A message such as “The bundled Whisper model is incomplete” is materially more useful than “Setup failed.” | Medium | Map known preflight/repair failures to separate copy and recovery actions: missing file, hash mismatch, manifest signature rejected, executable smoke failure, unavailable network, insufficient writable space/permission, and post-install recheck failure. Do not speculate when cause is unknown; say what was observed. |
| Truthful repair progress and cancellation boundary | **Recommendation** | Reduces fear of a stalled updater and avoids misleading cancellation affordances. | Medium | Progress identifies the current step and component count without claiming a precise ETA unless measured. Before the installation commit, `Cancel` safely discards staged payload; during the atomic replacement it may be temporarily unavailable with an explanation. A failed or cancelled repair must revalidate and remain at the gate. |
| Tour completion by demonstrated value | **Recommendation** | The user leaves with an actual study pack and an understanding of where it is, rather than only memorizing controls. | Medium | Final step identifies the generated output location and points to the demo’s transcript/slide review result. It should not force users to inspect every screen or wait for unrelated educational copy. |
| Replayable, non-persistent learning | **Locked + recommendation** | Users can revisit orientation without contaminating their lecture library. | Low | Put `Replay guided demo` in Settings and use the same visible `Exit demo` guarantee on each replay. A first-run “skipped” state should not prevent replay. |
| Optional-engine fallback as an informational notice | **Locked + recommendation** | Maintains continuity and makes actual processing capability auditable. | Low | Use a persistent-but-dismissible in-app banner/status item rather than a modal. Clearly distinguish requested engine, unavailable optional engine, and effective CPU fallback in Diagnostics. |
| Visual artifact guardrails | **Locked** | Fixes must preserve the beta-5 identity rather than turn onboarding work into a redesign. | Medium | Preserve intentional motion, dark hard shadows, transitions, and pressed/embedded buttons. Restrict changes to atomic theme switching, flicker/flash/repaint removal, ellipsized long model names, tooltips on hover/focus, and layout stability. |

## Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| Bypass, “continue anyway,” or a hidden route around the hard gate | Invites users into an app that cannot perform its essential offline workflow and makes later failures harder to diagnose. | Keep the gate strict; offer Retry, Diagnostics, Exit, and consented Repair all only. |
| Silent background repair or preemptive network check | Violates the local-first/no-unrelated-network promise and obscures a security-relevant action. | Check local payload silently; request network only after the user confirms repair. |
| Generic “setup failed” / “unknown error” message as the whole experience | Leaves the user unable to distinguish missing runtime, corruption, access, or network conditions. | Give condition-specific problem, consequence, and next action; place technical evidence under Details/Diagnostics. |
| Manual per-file runtime browsing or offline repair package import | Explicitly out of beta-6 scope; it increases support and integrity complexity. | Use exact-version, signed, transactional official-release repair; retain diagnostics and exit when offline. |
| Auto-started tutorial, looping popups, or an unskippable tour | Microsoft first-experience guidance favors fast productive use and optional teaching; forced tours are a hurdle. | Offer `Start guided demo` / `Skip for now`, make replay discoverable in Settings, and keep tour controls user-driven. |
| Fake demo screens, mocked exports, or a permanent demo job | Undermines confidence in the core pipeline and violates the isolated demo decision. | Run the real offline workflow in an isolated temporary workspace, then clean it up. |
| “Optional engine failed” presented as a blocking error | Contradicts the mandatory bundled CPU recovery path and unnecessarily prevents productive use. | Fall back to healthy bundled CPU with a visible non-blocking notice and diagnostic details. |
| Visual simplification framed as an onboarding improvement | Directly conflicts with beta-5 visual preservation and expands scope. | Limit work to artifact fixes and regression checks against beta-5 visual/motion contracts. |
| Raw stack traces, file-system dumps, or security-verification internals in the primary dialog | Overwhelms ordinary users and can expose confusing local path details. | Use concise plain text in the gate; provide Copy Report/Open Diagnostics for support-level data. |

## Feature Dependencies

```text
Bundled payload identity + local validation
  → first-launch full smoke check
  → healthy silent bootstrap → empty Home → first-success welcome choice

Local validation failure
  → hard setup gate
  → explicit Repair all confirmation
  → download to staging → signed manifest + SHA-256 verification
  → transactional installation / rollback → full revalidation
  → empty Home

Healthy bundled CPU runtime
  → optional-engine health evaluation
  → (if optional engine broken) visible CPU fallback notice

First-success welcome choice
  → Start guided demo
  → isolated temporary demo workspace
  → real offline pipeline + contextual spotlight steps
  → review/export-location explanation
  → normal-exit cleanup or crash/cancel sweep

Replay guided demo (Settings)
  → fresh isolated workspace; never normal library persistence
```

## Roadmap-Ready Acceptance Themes

1. **Required runtime is a real admission criterion.** Test healthy first launch, every separately missing/corrupt required component, corrupt signed metadata, and successful post-repair revalidation. The UI must not expose Home before the full required set is confirmed.
2. **Repair is consented, exact-version, and reversible.** Verify the confirmation identifies source/version; network occurs only after user action; every downloaded payload is staged, signature/hash-verified, installed as one set, and prior runtime survives failure/cancel.
3. **First run is productive without being coercive.** Confirm healthy launch reaches empty Home; welcome offers exactly the opt-in demo/skip choice; skipping does not block use; tour supports Back, Next, and Exit; Settings can replay it.
4. **The demo proves the product.** In a disposable profile, run the bundled synthetic input through the actual offline pipeline, review, generation, and export explanation; verify no normal-library item or persistent demo workspace is left after completion/cancel/crash sweep.
5. **Fallback and diagnostics make state intelligible.** Confirm a broken optional engine shows CPU fallback without the hard gate; confirm messages identify the component/condition/action and support diagnostic report access.
6. **Visual preservation is verified, not assumed.** Compare the specified beta-5 contracts while checking atomic theme changes, no repaint flash/flicker/layout jump, and ellipsis+tooltip behavior for long model names.

## Copy and Interaction Guidance

Use a compact “problem → consequence → action” structure, following Microsoft error-message guidance:

| Situation | Recommended plain-language summary | Primary command | Secondary commands |
|---|---|---|---|
| Required runtime check finds missing/corrupt parts | “LecturePack needs to repair its bundled processing tools before it can process lectures.” Then list affected component names. | `Repair all…` | `Retry check`, `Open diagnostics`, `Exit LecturePack` |
| Repair consent | “Download verified runtime files for LecturePack {version} from the official LecturePack release?” Show source/details. | `Download and repair` | `Cancel` |
| Network unavailable | “LecturePack could not reach the official release, so no repair files were downloaded.” | `Retry` | `Open diagnostics`, `Exit LecturePack` |
| Verification rejected | “The downloaded runtime files could not be verified and were not installed.” | `Retry repair` | `Open diagnostics`, `Exit LecturePack` |
| Repair succeeded | “Required processing tools are ready.” | Automatically continue | No acknowledgement modal needed |
| Optional engine unavailable | “{Optional engine} was unavailable. LecturePack will use its bundled CPU engine.” | `View details` | Dismiss notice |
| Welcome | “LecturePack is ready. Would you like a short guided demo using a built-in sample lecture?” | `Start guided demo` | `Skip for now` |

Avoid wording that blames the user (for example, “your configuration is invalid”), vague verbs (“failed” without cause), generic `OK` on corrective dialogs, and warnings where there is no meaningful action. The repair confirmation is justified because it authorizes a network download and runtime replacement; do not add confirmations to routine local checks, welcome choices, or ordinary demo navigation.

## MVP Recommendation

Prioritize in this order:

1. **Runtime admission and recovery contract:** deterministic validation, hard gate, condition-specific diagnostics, consented repair, signature/hash verification, transactional install/rollback, and final revalidation.
2. **Startup ownership and safe fallback:** empty Home; no auto-opened job; CPU remains a verified recovery path; optional-engine issues become a non-blocking notice.
3. **Real guided demo:** opt-in welcome, concise anchored tour, real isolated synthetic workflow, clear output explanation, replay, and cleanup.
4. **Artifact-only visual reliability:** atomic theme change, flicker/overflow/layout fixes, and visual regression evidence.

Defer: manual/offline repair-package workflows, per-file repair selection, automatic background update checks, richer tutorial content, alternate onboarding modes, redesign work, and any new providers or cloud/account/telemetry features.

## Sources

- [Microsoft Learn — Error Message Guidelines](https://learn.microsoft.com/en-us/windows/win32/debug/error-message-guidelines) — MEDIUM confidence via Brave; current page crawled July 2026. Recommends clear problem/cause/solution, audience-appropriate wording, and explicit command buttons.
- [Microsoft Learn — UX checklist for desktop applications](https://learn.microsoft.com/en-us/windows/win32/uxguide/top-violations) — MEDIUM confidence via Brave. Supports actionable, specific, non-blaming messages; specific command labels; confirmations only for consequential actions.
- [Microsoft Learn — First Experience](https://learn.microsoft.com/en-us/windows/win32/uxguide/exper-first-exper) — MEDIUM confidence via Brave. Supports simple first use, safe defaults, consent for privacy-relevant choices, and making tutorials optional rather than blocking productivity.
- [Microsoft Learn — TeachingTip](https://learn.microsoft.com/en-us/windows/apps/design/controls/dialogs-and-flyouts/teaching-tip) — MEDIUM confidence via Brave. Supports targeted, transient contextual teaching and avoiding tips for critical state or too frequently.
- [Microsoft Learn — Windows Update security](https://learn.microsoft.com/en-us/windows/deployment/update/windows-update-security) — MEDIUM confidence via Brave, cross-checked. Describes end-to-end content validation through signatures and hashes before installation.
- [Microsoft Learn — Known Issue Rollback](https://learn.microsoft.com/en-us/troubleshoot/windows-server/installing-updates-features-roles/known-issue-rollback) — MEDIUM confidence via Brave. Reinforces targeted rollback/restoration as a reliability pattern.

## Research Limits

- The supplied milestone context, not external research, is the authority for product-specific constraints such as the exact runtime contents, official GitHub release source, signed-manifest scheme, no offline repair import, and visual preservation boundary.
- Microsoft’s current guidance is largely platform-general rather than PySide6-specific. Phase planning should validate keyboard focus, screen-reader labeling, high-DPI behavior, and actual repair progress/cancellation semantics against the implemented Qt UI.
