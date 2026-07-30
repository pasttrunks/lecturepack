# Phase 1 Discussion Log — Clean-Device Footprint & First Launch

**Date:** 2026-07-30
**Milestone:** v0.9.0-beta.7

Human reference only. Not consumed by downstream agents — see `01-CONTEXT.md` for decisions.

---

## Course corrections during discussion

Two, both material.

**1. Wrong branch.** The session opened on `main`, whose `.planning/` describes an
unfinished **v1.2** milestone for the legacy QtWidgets application. The first scout ran
against it and produced a report that was internally accurate but about the wrong codebase.
The owner corrected this: all beta-6 implementation, GSD phases, and handoffs are on
`codex/phase4-visual-artifact-reliability` — **153 commits ahead of `main`**, version
`0.9.0-beta.6`, with its own five-phase planning tree. Everything below is from that branch.

**2. Wrong framing of the first question.** The owner was initially asked where the work
should live while the only known roadmap was the stale v1.2 one, and answered "new
milestone, new Phase 1". Once the beta-6 milestone was found — 5 phases, marked complete —
the question was re-asked with the real options. The re-asked answer superseded the first.

---

## Questions and answers

### Q1 (first pass) — Planning target
Asked against an incomplete picture. Options: new milestone / overwrite phase 01 / skip GSD.
**Answer:** New milestone, new Phase 1. *Superseded by Q1b.*

### Q2 — What "opened Demo directly" looked like
Options: fabricated lecture content (a BUG-15 regression) / straight to Home / investigate.
**Answer (freeform):** Neither preset option. The demo is the **guided walkthrough with a
polar bear video** built in `codex/phase4-visual-artifact-reliability` — a real onboarding
tour, not the old fake-lecture placeholder data.
**Consequence:** ruled out a BUG-15 regression entirely and redirected the investigation to
the guided-demo trigger, which is what surfaced the setup-gate-is-a-failure-gate finding.

### Q3 — Which gray areas to lock
**Answer:** Size-cut aggressiveness; startup fix vs. honest feedback; where Setup lives.
Second-launch behavior was **not** selected → left to the agent's discretion, recorded as
D-18/D-19 with rationale.

### Q1b — Planning target, re-asked with the real picture
Options: Phase 6 on beta.6 / new beta.7 milestone / reopen Phase 5.
**Answer:** New beta.7 milestone, Phase 1.

### Q4 — Setup screen behavior
Options: always show on fresh profile / only on failure / show with auto-continue.
**Answer:** Always show on fresh profile. → D-12
**Note:** the owner was told plainly that the existing gate skipping on a healthy first run
is *by design*, not a defect, and chose the behavior change anyway with that understood.

### Q5 — Startup fix shape
Options: window-first with progress / make validation faster / both.
**Answer:** Both. → D-08, D-10

### Q6 — Size-cut aggressiveness
Options: dedupe + safe Qt cuts / aggressive allowlist / dedupe only.
**Answer:** Dedupe model + safe Qt cuts. → D-01, D-03

---

## Findings that changed the shape of the phase

- **The 148 MB model duplication** — the "confirmed duplicate" the owner asked for, found
  by measuring the built tree rather than reading the spec.
- **The ~2 minute launch is a real bounded whisper transcription**, not a leak or a hang:
  three 30 s-bounded probes running synchronously before the window is shown, one-time per
  runtime identity. This turned an open-ended investigation into a scoped fix.
- **The setup gate already exists** but is a failure gate. What the owner asked for is new
  behavior. Naming this prevented planning a "fix" for working code.
- **No `Setup.exe` is produced** by CI (`--no-installer`) or locally (no ISCC), so the
  artifact the owner installed is unidentified and the reported ~900 MB does not reconcile
  with the measured 1.9 GB. Left explicitly open rather than papered over.
- **Beta 6's release gate never measured size, launch time, or ran on a physical machine**,
  and its evidence cites beta-5 artifacts. Recorded in the archive README so the next
  session does not inherit a false "verified" baseline.

---

## Scope creep

None. Every item traced to one of the owner's thirteen numbered work items. The aggressive
Qt allowlist and the `resources/` trim were surfaced as options, declined or gated, and
captured under Deferred Ideas rather than pulled in.

---

## Left to the agent's discretion

- Single-instance mechanism and wire format (D-18, D-19 constrain behavior, not mechanism).
- Whether size cuts live in PyInstaller `excludes`, post-build pruning, or both.
- Checklist visual treatment within the existing design language.
- Helper naming, module placement, test organization.
