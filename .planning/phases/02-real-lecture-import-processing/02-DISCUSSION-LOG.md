# Phase 2: Real Lecture Import & Processing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-01
**Phase:** 02-real-lecture-import-processing
**Areas discussed:** Runtime resolution strategy, Job lifecycle visibility, Pre-processing settings timing, Paste Link / yt-dlp scope, Reproduction strategy, Demo isolation boundary

---

## Runtime Resolution Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-populate Settings on boot | Detect bundled paths and write into ConfigManager on startup | |
| Shared resolver function | One function both demo and normal paths call | |
| You decide | Pick simplest given existing code | ✓ |

**User's choice:** You decide
**Notes:** Claude picks the simplest approach.

### Follow-up: User Settings override

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, user Settings wins | Bundled paths are defaults; explicit user config overrides | ✓ |
| No, always use bundled | Ignore Settings for runtime paths | |
| You decide | | |

**User's choice:** Yes, user Settings wins

### Follow-up: Engine selection scope

| Option | Description | Selected |
|--------|-------------|----------|
| Paths only | Resolver finds exe/model/ffmpeg; engine selection stays in EngineRegistry | |
| Paths + engine | Single call returns full runtime config | |
| You decide | Whatever keeps the change small | ✓ |

**User's choice:** You decide

---

## Job Lifecycle Visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Reproduce and fix what's broken | Find specific wiring bugs, don't redesign | ✓ |
| Audit the full lifecycle | Walk every state transition and verify UI updates | |
| You decide | | |

**User's choice:** Reproduce and fix what's broken

### Follow-up: Failed job visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Stay until dismissed | Failed jobs stay visible with error until user acts | ✓ |
| You decide | | |

**User's choice:** Stay until dismissed

---

## Pre-Processing Settings Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Import/start step only | Show before processing, hide during | |
| Always visible, locked when running | Show during processing but greyed out/disabled | ✓ |
| You decide | | |

**User's choice:** Always visible, locked when running

---

## Paste Link / yt-dlp Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Just make it work | Reconnect existing UI to existing backend, one URL type, clear error | ✓ |
| Minimal but complete | Working paste + progress + error + normal job flow | |
| You decide | | |

**User's choice:** Just make it work

### Follow-up: Missing yt-dlp behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Hide the button | Don't show Paste Link if yt-dlp not importable | |
| Show with error on click | Button always visible, error on click if missing | |
| You decide | Match existing code behavior | ✓ |

**User's choice:** You decide

---

## Reproduction Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Use existing beta-6 packaged build | Fastest reproduction path | |
| Build fresh from current code first | Includes Phase 1 + 1.1 fixes | ✓ |
| You decide | | |

**User's choice:** Build fresh from current code

### Follow-up: Test video

| Option | Description | Selected |
|--------|-------------|----------|
| Any short local video | ~10-30 seconds with speech | |
| Specific file you have | User provides path | |
| You decide | Whatever's convenient | |

**User's choice:** Use the bundled polar bears demo video (10s, 4 slides) imported through the normal path, not the demo button.

---

## Demo Isolation Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Keep demo isolated | Demo keeps own controller/config; unify only path resolution | ✓ |
| Merge demo into normal path | Demo becomes a normal job using the regular pipeline | |
| You decide | | |

**User's choice:** Keep demo isolated

---

## Claude's Discretion

- Mechanism for auto-populating bundled paths (boot-time config write vs shared resolver vs other)
- Whether resolver handles engine selection or just paths
- Whether missing yt-dlp hides Paste Link button or shows error on click

## Deferred Ideas

None — discussion stayed within phase scope.
