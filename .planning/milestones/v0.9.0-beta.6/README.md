# v0.9.0-beta.6 Planning Snapshot

Milestone **Clean-Machine Reliability and Onboarding** — 5 phases, archived 2026-07-30
when the v0.9.0-beta.7 milestone opened.

`STATE.md` recorded this milestone as `milestone_complete` (22/22 plans) on 2026-07-29.
That claim did not survive first contact with a clean device. Five defects reported by
the owner on 2026-07-30 are addressed by beta.7 Phase 1.

## What the beta.6 release gate did not do

Phase 5 ("Packaged & Physical Release Gate") certified the milestone without recording
any of the following, each of which was in its own stated scope:

- Installer size, installed size, or largest packaged contributors.
- Cold or warm launch time.
- Any physical machine identity — no machine name, OS build, or hardware spec appears in
  `05-UAT.md` or `docs/HANDOFF_PHASE_5.md`. Evidence is consistent with disposable
  profiles on the development machine only.

Its evidence documents also cite `LecturePack-0.9.0-beta.5-Portable.zip` artifacts while
certifying `0.9.0-beta.6` — one version behind the thing being certified.

**Read this before trusting any "verified" claim in the archived phases below.** The
phases' engineering content (the runtime contract, the signed-repair design, AD-18/AD-19)
is sound and remains canonical; the *release verification* is not.

## Contents

- `phases/` — all 5 phase directories, unmodified.
- `ROADMAP.md` — the beta.6 roadmap.
- `MILESTONE-CONTEXT.md` — beta.6 milestone context; still canonical for the runtime
  contract and repair architecture.
- `STATE.md` — final beta.6 state, preserved as recorded.
