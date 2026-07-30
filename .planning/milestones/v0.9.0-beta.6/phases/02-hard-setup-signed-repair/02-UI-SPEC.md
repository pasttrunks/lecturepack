---
phase: 02
slug: hard-setup-signed-repair
status: draft
shadcn_initialized: false
preset: none
created: 2026-07-28
---

# Phase 02 — UI Design Contract

> Visual and interaction contract for the blocking runtime setup and signed-repair flow. It is an extension of beta-5's existing shell, not a new design system.

---

## Scope and Non-Goals

The overlay appears when the canonical `get_bootstrap()` result has `runtime_health_state: "SETUP_REQUIRED"` and consumes its `setup_required` snapshot. It remains until a later canonical admission result is `HEALTHY`, or the user chooses **Exit**. It must not infer health from a download percentage or an installer event.

The overlay owns repair consent, repair status, offline recovery, and sanitized diagnostics only. It must not expose normal navigation, settings, job work, update checks, manual package import, per-component repair, external browsing, or manual file replacement. Do not use this phase to change beta-5's themes, tokens, typography, animations, flicker behavior, or general layout.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — reuse the existing hand-authored WebEngine shell |
| Preset | not applicable |
| Component library | none |
| Icon library | inline existing SVG vocabulary; no new dependency |
| Font | `Space Grotesk` for body/headings; `JetBrains Mono` for labels, metadata, version, and technical evidence |
| Source of truth | `app/ui/index.html`, `app/ui/app.css`, `app/ui/app.js`, `app/ui/bridge.js` (beta-5) |

### Required reuse

- Render a fixed viewport `role="dialog" aria-modal="true"` scrim/panel using the existing overlay construction: `#onb-overlay` / `#whatsnew-overlay`, `.lp-scrim`, `.lp-pop`, `var(--panel)`, `2px solid var(--border)`, `18px` radius, and `var(--shadow-hi)`. The setup overlay must have the highest overlay z-index and must not close on scrim click.
- Use `.lp-hit` plus `.lp-press` or `.lp-press-sm` for every actionable button. Preserve the hard offset/embedded press effects (`--btn-edge-hover`, `--btn-edge-press`, `--shadow-hard[-sm]`) and never substitute scale-on-press.
- Use `.lp-fill` for the progress fill so the bar advances via compositor `scaleX`, not animated width. Reuse `LP.motion`, `LP.motion.close`, `focusFirst`, `topOverlay`, `trapFocus`, and the existing `FOCUSABLE` selector rather than adding a second overlay/focus system.
- Use `esc()` or text nodes for every backend-provided component label, diagnostic field, URL, version, size, or failure reason. Never insert repair metadata through `innerHTML` without escaping.

---

## Spacing Scale

Declared values (must be multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | icon-to-label and inline metadata gaps |
| sm | 8px | compact action gaps and list-row separation |
| md | 16px | standard panel rhythm and control separation |
| lg | 24px | panel body padding and section separation |
| xl | 32px | viewport scrim padding and major state separation |
| 2xl | 48px | reserved; do not add within the compact overlay unless vertically roomy |
| 3xl | 64px | not used inside the gate |

Exceptions: minimum 44px pointer target for every gate action; panel scrim padding may reduce from 32px to 16px below 820px so all required actions remain reachable.

---

## Typography

Only these existing sizes and weights may be used for new gate UI.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Metadata / technical label | 12px | 500 | 1.5 |
| Body / action label | 14px | 700 | 1.5 |
| State heading | 20px | 700 | 1.2 |
| Overlay title / compact progress number | 16px | 700 | 1.2 |

Use `JetBrains Mono` at 12px/500 for upper-case or tabular operational metadata only; use `Space Grotesk` at 700 for all friendly prose, headings, and action labels. Live percentage, byte count, and elapsed values use tabular numerals (`.lp-num`). New gate UI uses exactly these two weights, 500 and 700; this preserves beta-5's weight contrast without changing product-wide typography.

---

## Color

All values are existing theme variables and therefore resolve correctly in both beta-5 themes.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `var(--bg)` / `var(--panel)` | visible underlying application and gate panel |
| Secondary (30%) | `var(--panel2)`, `var(--sunk)`, `var(--blue-soft)` | affected-component rows, technical-details surface, progress track |
| Accent (10%) | `var(--orange)` with `var(--on-signal)` | **Repair all**, **Confirm & repair**, active repair milestone indicator, ready confirmation mark only |
| Destructive | `var(--red-fill)` / `var(--red)` | repair-failure marker and concise failure reason only; never make Exit red |

Accent reserved for: the two consented repair CTAs, current progress/milestone indication, and the short successful-ready state. Secondary actions use `var(--panel)`/`var(--ink)` with `var(--border)`; diagnostics disclosure uses existing blue secondary surfaces; success uses `var(--green)`/`var(--green-soft)` only as status evidence, not a competing primary CTA.

---

## Layout and Responsive Contract

- The root is `position: fixed; inset: 0`, above all normal UI, with the beta-5 dark scrim (`rgba(8,10,14,.62)`). The underlying app remains visually recognizable but is inert and cannot scroll, receive a pointer event, or receive keyboard shortcuts.
- The panel is centered at 560px ideal width, `max-width: 100%`, with a 2px border, 18px radius, `var(--shadow-hi)`, and `overflow: hidden`. Reuse beta-5 overlay and component spacing unmodified wherever an existing construction applies. For genuinely new gate-only gaps, use only the declared 4/8/16/24/32/48/64px tokens. The panel must never exceed the visible viewport: its body gets `overflow-y:auto` and a max height derived from viewport minus scrim padding.
- Header: LecturePack mark, **Runtime setup**, and an always-visible **Exit** button. Exit is a normal secondary button, not an X icon, and stays available in every state including progress. Do not display a dismiss icon.
- Affected components render as a short vertical collection. Each row uses a stable friendly label (for example **Media tools**, **Speech model**), optional concise impact sentence, and no raw paths, filenames, hashes, or stack traces. Preserve canonical component order from the backend snapshot.
- At widths below 820px, retain the full-viewport overlay, reduce scrim/panel side padding to 16px, make action groups wrap into one full-width primary action followed by secondary actions, and keep the footer/action area reachable by scrolling the panel body. At any size, controls retain 44px minimum hit area and text wraps rather than clipping.
- Long friendly component names, version strings, release URLs, hashes, paths, and diagnostics must not grow the panel horizontally. Friendly labels wrap to two lines then ellipsize; expose the complete label through `title` and accessible name. Technical values use horizontal scroll only inside the technical-details code/value region; never scroll the entire dialog sideways.

---

## Deterministic State Machine

Client state is a single reducer value: `gate | diagnostics | confirm | repairing | offline | failed | ready`. Retain `returnState` (`gate`, `failed`, or `offline`) when opening diagnostics. Every repair command/event includes an operation ID; ignore events that do not match the active operation ID, events after a terminal result, and duplicate terminal events.

| Current state | Visible content and permitted actions | Transition |
|---|---|---|
| `gate` | Calm setup explanation; failed-component list; **Repair all** primary; **Retry**, **Open diagnostics**, **Exit** secondary | Repair all → `confirm`; Retry asks bridge to reassess and stays pending/disabled until canonical result; diagnostics → `diagnostics`; failed admission remains `gate`; healthy admission is only allowed after repair and goes `ready`; Exit closes app |
| `confirm` | Friendly repair summary; exact version, official release, contents, download size; reassurance; collapsed Technical details; **Confirm & repair** primary; **Back** and **Exit** secondary | Back → `gate`; Confirm creates operation ID and invokes repair → `repairing`; Exit closes app |
| `repairing` | One progress bar, friendly phase text, concise connection-retry status when applicable, **Cancel repair** and **Exit** | progress/retrying updates stay `repairing`; Cancel sends one cancel request, immediately labels it “Cancelling safely…”, disables repeat cancel, and waits for backend terminal event; cancelled → `gate`; network exhausted → `offline`; failure → `failed`; `admitted` → `ready` |
| `offline` | Internet-required explanation; no component list/repair CTA; **Retry connection** primary; **Open diagnostics** and **Exit** secondary | Retry connection starts a new operation → `repairing`; diagnostics → `diagnostics`; Exit closes app |
| `failed` | One plain-language reason and assurance that the previous runtime was kept; **Try again** primary; **Open diagnostics** and **Exit** secondary | Try again starts a new operation → `repairing`; diagnostics → `diagnostics`; Exit closes app |
| `diagnostics` | Friendly summary first, collapsed/expanded Technical details, **Copy details**, **Save report**, **Back**, and always-visible **Exit** | Back → `returnState`; Copy/Save do not change state; Exit closes app |
| `ready` | Success mark, **You're ready**, one sentence that LecturePack will open automatically | After 800ms (or immediately under reduced motion), dismiss only after `admitted`; restore normal app focus and allow startup continuation. No button is required or displayed. |

Backend event mapping: `started` → `repairing`; `progress` → friendly stage/optional percentage; `retrying` → `repairing`; `cancel_requested` → cancelling substate; `cancelled` → `gate`; `failed` → `failed` unless classified offline; `activated` remains `repairing`; `admitted` → `ready`. Pointer activation is an atomic safe boundary: the UI may show cancellation pending but must not promise cancellation until the matching `cancelled` event arrives.

### Focal Point by Primary State

| State | Focal point |
|---|---|
| `gate` | **Repair all** is the single orange focal action beneath the concise setup explanation. |
| `confirm` | **Confirm & repair** is the single orange focal action after the repair summary and trust facts. |
| `repairing` | The labelled progress bar and current friendly phase are focal; **Cancel repair** remains secondary. |
| `offline` | **Retry connection** is the single orange focal action beneath the fixed offline explanation. |
| `failed` | **Try again** is the single orange focal action beneath the sanitized reason. |
| `diagnostics` | The friendly summary and collapsed **Technical details** disclosure are focal; copy/save remain secondary. |
| `ready` | The success mark and **You're ready** status are focal; no action competes with automatic continuation. |

---

## Progress, Failure, and Offline Semantics

- Progress is a labelled `role="progressbar"` with `aria-valuemin="0"`, `aria-valuemax="100"`, and an updated `aria-valuenow` only when a trustworthy aggregate percentage exists. Otherwise omit `aria-valuenow` and expose the current step through an `aria-live="polite"` status.
- Use exactly one visual progress bar. Friendly phases are **Downloading**, **Verifying**, **Installing safely**, and **Almost there**. Never show archive filenames, file paths, raw hashes, command output, or low-level installer operations in the primary progress view.
- While a transient connection retry is in progress, show **Connection interrupted — retrying…** with attempt context only if it stays human-readable (for example, “Trying again (2 of 3)”). Use the bounded backend policy; do not add a client retry loop.
- Cancel is available throughout `repairing`, except that it becomes disabled with **Finishing a safe step…** while the backend reports the indivisible activation boundary. Cancellation leaves the old generation untouched/restored and returns to `gate` only after the backend confirms it.
- Failure reason is one short sanitized sentence, e.g. **We couldn't verify the repair download. Your previous runtime is still in place.** Map signature/inventory/hash/version/extraction/revalidation failures to this form; detailed evidence belongs only in diagnostics.
- Offline content is exactly: heading **An internet connection is needed to repair LecturePack**, body **Reconnect, then try again. LecturePack can't repair this runtime without the official release.** Available controls are only Retry connection, Open diagnostics, and Exit.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Gate heading | Runtime needs repair |
| Gate body | LecturePack found a problem with the tools it needs to process lectures. Repair can restore them safely. |
| Primary CTA | Repair all |
| Retry CTA | Retry |
| Consent heading | Repair LecturePack? |
| Consent fields | Official LecturePack release; Version; What will be repaired; Download size |
| Consent reassurance | Downloads only from LecturePack's official GitHub release; no personal data or telemetry is sent. |
| Consent primary CTA | Confirm & repair |
| Consent secondary actions | Back; Exit |
| Progress states | Downloading; Verifying; Installing safely; Almost there; Cancelling safely… |
| Offline CTA | Retry connection |
| Failure state | Repair couldn't be completed. Your previous runtime is still in place. |
| Failure primary CTA | Try again |
| Diagnostics entry | Open diagnostics |
| Diagnostics actions | Copy details; Save report; Back; Exit |
| Success state | You're ready |
| Success body | Your runtime is ready. Opening LecturePack… |
| Empty state heading | Not applicable — the gate always has a canonical admission result. |
| Empty state body | If the backend supplies zero failed components, display “LecturePack needs repair, but the affected components could not be listed.” and keep Repair all, diagnostics, and Exit available. |
| Destructive confirmation | None. Repair is non-destructive to the portable bundle and requires the dedicated Confirm & repair step; Exit closes the app immediately and does not modify the runtime. |

---

## Diagnostics Disclosure and Privacy

- **Technical details** is collapsed by default in `confirm` and `diagnostics`; expansion is a semantic button with `aria-expanded` and `aria-controls`. It may show official URL, public-key/signature facts, canonical-manifest/schema/version outcome, hash/inventory outcome, sanitized local paths, operation ID, and failure evidence.
- The initial focus in `diagnostics` is its heading; when expanded, focus remains on the disclosure control, not moved into lengthy content. **Back** returns focus to the exact invoking control in the retained state.
- `Copy details` copies the same sanitized, plain-text report shown/exported; announce completion/failure in a polite live region. `Save report` calls the narrow bridge operation and confirms the chosen saved location without opening a raw log viewer.
- Do not include university credentials, personal data, lecture/video/transcript content, auth headers, environment variables, or secrets in visible, copied, or saved diagnostics. Local paths and verified failure facts are permitted after sanitization.

---

## Accessibility and Input Blocking

- The setup gate is non-dismissible: no click-through, scrim close, Escape close, normal navigation shortcut, focus-mode shortcut, theme toggle, browser default tab escape, or background scrolling. Add it to `topOverlay()` before existing overlays so it owns focus whenever visible.
- On opening any state, call the existing `focusFirst()`; initial targets are Repair all (`gate`), Confirm & repair (`confirm`), Cancel repair (`repairing`), Retry connection (`offline`), Try again (`failed`), diagnostics heading/back (`diagnostics`), and the ready status (`ready`, `tabindex="-1"`). Use the existing `trapFocus()` for Tab/Shift+Tab.
- Escape is ignored for all gate states. Enter/Space activate only the focused visible control. Do not bind Enter to Confirm & repair unless that button is focused. Prevent repeated submit/cancel actions while the corresponding bridge call is pending.
- Preserve the approved visible labels. Where a concise single-word visible control could be ambiguous outside its immediate context, add a contextual `aria-label` and matching `title` without changing its text: for example, `Exit` → “Exit LecturePack”, `Retry` → “Retry runtime assessment”, `Back` → “Back to runtime setup”, and `Copy details`/`Save report` → “Copy runtime repair details”/“Save runtime repair report”.
- Use `aria-live="assertive"` for state-changing failure/offline/admitted announcements and `aria-live="polite"` for ordinary progress/retry changes. Keep action labels visible; do not rely only on color, icons, animation, or hover tooltips.
- Mark normal app content inert while the gate is visible (native `inert` where supported, otherwise a tested pointer-event/focus guard) and restore its prior state only after the ready dismissal or application exit. Underlying controls must not be discoverable by a screen reader while the modal is active.
- Respect beta-5's existing global `prefers-reduced-motion: reduce` rules and `LP.motion.reduced()`: no custom animation, no progress shimmer, no delayed panel movement, no `LP.motion.close` delay for success. Preserve instant color/border/shadow state feedback and show static progress/ready states.

---

## UI Considerations

Applicable state considerations resolved: 11 covered, 2 backstop, 0 unresolved.

| Category | Element(s) | Status | Resolution / Reason |
|----------|------------|--------|---------------------|
| loading | gate assessment and Retry | ✅ covered | Disable only the invoked retry control, announce “Checking runtime…”, and retain Exit; canonical result decides next state. |
| error | repair flow | ✅ covered | `failed` is a persistent in-overlay state with short reason, Try again, diagnostics, and Exit. |
| loading | repair progress | ✅ covered | `repairing` provides one labelled progressbar and changing friendly status; neither success nor dismissal is inferred from percentage. |
| partial | affected component list | ✅ covered | Render canonical ordered available labels; absent labels use the documented unknown-components fallback without losing repair/diagnostics actions. |
| empty | affected component list | ✅ covered | Use the Copywriting Contract fallback when no failed components can be listed. |
| zero-one-many | affected component list | ✅ covered | One compact summary plus 0/1/many component rows; singular/plural text is derived without changing action hierarchy. |
| long-text | component names, error summary, trust values | ✅ covered | Friendly values wrap/ellipsize with title and accessible full name; technical values remain inside a scrollable technical region. |
| overflow | diagnostics and panel body | ✅ covered | Only the panel body/technical value region scrolls; whole dialog never exceeds viewport or gains horizontal overflow. |
| populated | diagnostics report | ✅ covered | Friendly summary precedes optional technical facts; Copy details and Save report use the same sanitized report. |
| error | clipboard/save report | ✅ covered | Keep diagnostics open and announce a plain failure without hiding the report or changing repair state. |
| nav | focus/keyboard containment | 🧪 backstop | Automated UI test proves Tab/Shift+Tab, Escape, background shortcuts, pointer events, and scroll cannot reach underlying app in every gate state. |
| media | reduced-motion progress/success | 🧪 backstop | Visual/reduced-motion test proves progress and ready state remain understandable with all movement disabled. |
| overflow | supported narrow windows/DPI | ✅ covered | 820px responsive wrap/scroll rules preserve full action reachability and no horizontal clipping. |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable — shadcn is not initialized |
| third-party | none | not applicable |

---

## Verification Contract

- Automated UI coverage must exercise every reducer state and permitted transition, operation-ID stale-event suppression, no dismissal before `admitted`, cancellation at safe boundaries, offline restrictions, and diagnostics copy/save feedback.
- Keyboard coverage must verify the modal focus trap, initial focus, ignored Escape, blocked background shortcuts/pointer/scroll, and restoration of normal focus only after automatic ready dismissal.
- Visual/manual coverage must compare both existing themes with beta-5 motion/pressed/shadow character intact; test narrow supported window/DPI, long component/path evidence, repeated gate transitions, and reduced motion. No new flash, flicker, overflow, or layout jump is acceptable, but broader existing artifact fixes remain out of scope.
- Bridge/UI integration coverage must prove bootstrap reads `runtime_health_state`/`setup_required`, uses canonical component identities, and does not construct/enable normal UI activity while setup is required.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
