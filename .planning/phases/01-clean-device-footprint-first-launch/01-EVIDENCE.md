# Phase 1: Clean-Device Footprint & First Launch — Evidence

**Phase:** 01-clean-device-footprint-first-launch
**Milestone:** v0.9.0-beta.7
**Seeded:** 2026-07-30 (Plan 01-01)

## Preamble

Every `NOT YET MEASURED` marker below is a **blocking gap**, not a placeholder to be
inferred, estimated, or waived. This phase's approval/evidence gate (`.planning/ROADMAP.md`
Phase 1 "Approval/evidence gate") cannot be claimed satisfied while any marker in a
required section remains unfilled.

Rules that apply to every section in this file:

- **No averaging.** Where two figures disagree (owner-reported vs. measured, before vs.
  after cuts), both numbers are recorded distinctly, with a stated cause for the gap. An
  averaged figure is never an acceptable resolution — see `01-CONTEXT.md`
  `<open_measurement>`.
- **No stale numbers.** `app/dist/` may carry build residue from a prior run (PyInstaller,
  ISCC, or manual edits). A number in this file must come from the specific build
  identified in `## Machine and build identity` for that section — it may not be carried
  over from a different build date, a different git commit, or a different machine.
- **No missing machine identity.** Beta-6's Phase 5 release gate
  (`.planning/milestones/v0.9.0-beta.6/phases/05-packaged-physical-release-gate/05-UAT.md`)
  named no physical machine, no OS build number, and no git commit for any of its "PASS"
  rows. This file exists so that failure mode cannot recur in beta-7.

---

## Machine and build identity

- OS build number: NOT YET MEASURED
- CPU: NOT YET MEASURED
- Profile clean (fresh disposable profile, not the developer's daily profile): NOT YET MEASURED
- Git commit measured: NOT YET MEASURED
- Exact `python packaging/build.py` invocation used: NOT YET MEASURED
- Build result (success / failure verbatim): NOT YET MEASURED

---

## Size — baseline (pre-cut)

Measured from **one** freshly built `Setup.exe` in a single sitting (Plan 01-01 Task 3),
before Plan 01-04 changes any packaging code.

| Figure | Value |
|---|---|
| `Setup.exe` own byte size | NOT YET MEASURED |
| Expanded tree byte size (what `Setup.exe` installs to) | NOT YET MEASURED |
| `app/dist/LecturePack/` built-tree byte size | NOT YET MEASURED |
| Portable ZIP byte size | NOT YET MEASURED |

**Top contributors (baseline):**

NOT YET MEASURED

---

## Size — after cuts

Filled by Plan 01-08, from one post-cut build. Do not fill from this plan.

| Figure | Value |
|---|---|
| `Setup.exe` own byte size | NOT YET MEASURED |
| Expanded tree byte size | NOT YET MEASURED |
| `app/dist/LecturePack/` built-tree byte size | NOT YET MEASURED |
| Portable ZIP byte size | NOT YET MEASURED |

**Top contributors (after cuts):**

NOT YET MEASURED

**Pruned-tree audit (after cuts) — all six D-01 targets expected absent, `opengl32sw.dll`
expected present (D-02 keep), `ggml-base.en.bin` count expected exactly 1:**

NOT YET MEASURED

---

## Size — reconciliation

**Owner-reported figures (2026-07-30, installed a locally built beta-6 `Setup.exe`):**

- Installer (`Setup.exe`): ~800 MB
- Expanded/installed size: ~900 MB

**Dev-tree figures (measured directly in the `codex/phase4-visual-artifact-reliability`
worktree, `01-CONTEXT.md` `<measured_baseline>`, 2026-07-30):**

- `LecturePack-0.9.0-beta.6-Portable.zip`: 841.2 MB
- `app/dist/LecturePack/` installed footprint: 1.9 GB

These four numbers are kept **distinct** — they are never averaged into a single figure.

- **Measured answer:** NOT YET MEASURED
- **Cause:** NOT YET MEASURED

Averaging the owner-reported and dev-tree figures is **not** an acceptable resolution.
Reusing the 1.9 GB dev-tree figure as-is is also not acceptable — `app/dist/` may carry
build residue from a prior run and must be re-measured from a fresh build (`01-CONTEXT.md`
`<open_measurement>`).

---

## D-04 resources/ investigation

Pointer to `01-FINDINGS-resources.md` (Plan 01-04). NOT YET MEASURED — not produced by this
plan.

---

## D-20 taskbar icon diagnosis

Pointer to `01-FINDINGS-icon.md` (Plan 01-05). NOT YET MEASURED — not produced by this plan.

---

## Launch timing — cold

Per D-07, cold and warm launches take architecturally different paths
(`RuntimeBootstrapService._requires_full()`) and must be measured and recorded separately.

- Time to first visible on-screen feedback: NOT YET MEASURED
- Time to ready (fully validated, usable): NOT YET MEASURED
- Which validation path ran (full / light): NOT YET MEASURED

---

## Launch timing — warm

- Time to first visible on-screen feedback: NOT YET MEASURED
- Time to ready (fully validated, usable): NOT YET MEASURED
- Which validation path ran (full / light): NOT YET MEASURED

---

## Single instance — two-process proof

- Process count observed after a second launch attempt: NOT YET MEASURED
- Which window received focus: NOT YET MEASURED

---

## Packaged clean-profile launch

- Icon visible in title bar: NOT YET MEASURED
- Icon visible in taskbar: NOT YET MEASURED
- Rendered WebEngine content observed: NOT YET MEASURED

---

## Packaged runtime smoke after the cuts

- Exact pytest invocation: NOT YET MEASURED
- Result: NOT YET MEASURED
