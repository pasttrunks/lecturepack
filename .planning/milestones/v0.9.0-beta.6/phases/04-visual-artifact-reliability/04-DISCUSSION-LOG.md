# Phase 4: Visual Artifact Reliability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-29
**Phase:** 04-visual-artifact-reliability
**Areas discussed:** Page animation replay, Theme switching and startup flashes, Long values and smaller-window layouts, Tour and setup overlays during resize and DPI changes

---

## Page animation replay

| Question | Selected choice | Alternatives considered |
| --- | --- | --- |
| When entrance animation runs | Every explicit navigation to a different page | First visit per session; initial launch only |
| Re-clicking active navigation | Keep the page stable | Replay intentionally |
| Closing an overlay | Underlying page stays exactly in place | Subtle fade; full entrance replay |
| Live backend/settings updates | Update in place; existing micro-animation only on affected control | Fade changed values; flash/highlight updates |

**Notes:** The user repeatedly selected stability outside genuine navigation. Existing motion remains intentional and is not removed globally.

---

## Theme switching and startup flashes

| Question | Selected choice | Alternatives considered |
| --- | --- | --- |
| Startup theme | Apply saved theme before first visible frame | Neutral-dark bootstrap fade; visible theme animation |
| Fresh-profile default | Existing Light theme | Existing Dark theme |
| User theme toggle | Atomic whole-palette switch; preserve button press | Whole-window crossfade; per-element color transitions |
| Theme change with overlay open | Overlay and underlying page switch together | Close/reopen overlay; defer theme change |
| Persistence | Save immediately | Require global Save; session only |

**Notes:** “White theme” was clarified and recorded as the existing Light theme, not a new palette redesign.

---

## Long values and smaller-window layouts

| Question | Selected choice | Alternatives considered |
| --- | --- | --- |
| Long model-name field | One-line ellipsis | Multiline growth; horizontal field scrolling |
| Full-value reveal | Small anchored hover/focus tooltip | Inline expansion; details popover |
| Narrow layout | Stack controls and vertically scroll | Horizontal page scroll; hide secondary controls |
| Smallest window | No imposed minimum; continue adapting | Approx. 1024x700 minimum; approx. 900x600 minimum |

**Notes:** The no-minimum choice requires genuinely small-window coverage; required actions must remain reachable and cannot be hidden.

---

## Tour and setup overlays during resize and DPI changes

| Question | Selected choice | Alternatives considered |
| --- | --- | --- |
| Live resize | Continuously track target and clamp panel to viewport | Freeze then jump; close the step |
| Off-screen target | Scroll just enough to reveal the real control | Ask user to scroll; edge pointer |
| DPI/monitor change | Immediate geometry recalculation | Fade/reposition; restart step |
| Keyboard focus | Modal setup gate; tour cycles through real target and controls with Exit reachable | Unrestricted background focus; instruction-panel-only trap |

**Notes:** The guided tour remains action-led and anchored to real application controls. The CSS-only spotlight and pointer behavior from Phase 3 remain locked.

---

## the agent's Discretion

- Exact breakpoints, measurement scheduling, tooltip collision handling, and test implementation, within the locked user-visible behavior.

## Deferred Ideas

None.
