---
phase: 01-clean-device-footprint-first-launch
plan: 08
subsystem: evidence
tags: [packaging, evidence, physical-verification, windows, release-gate]

requires: ["01-04", "01-05", "01-06", "01-07"]
provides:
  - "01-EVIDENCE.md — final artifact measurements and physical verification results"
affects: []

tech-stack:
  added: []
  patterns: []
---

# Phase 1 Plan 8: Physical Evidence Gate Summary

**One fresh artifact from committed source `79225df` — the first containing the single-instance guard, AppUserModelID, and the checklist UI together — measured, installed, launched, and clicked twice. Single instance and icon both pass; four gaps remain honestly unmeasured.**

## Results

Full detail in `01-EVIDENCE.md` `## Plan 01-08`. Headlines:

| Item | Result |
|---|---|
| `Setup.exe` | 379,799,777 B (362.2 MiB) — **−44.7%** vs 686,684,565 B baseline |
| Expanded tree | 1,097,778,827 B (1,046.9 MiB) |
| Portable ZIP | 499,838,479 B (476.7 MiB) — **−43.5%** |
| `--assert-pruned` | exit 0 |
| Single instance (D-18/D-19) | **PASS** — second process exits, minimized window restored and focused |
| Icon (D-20/D-21) | **PASS** on all three launch paths, incl. Start Menu shortcut with AUMID |
| Packaged runtime smoke + real transcription | PASS (33/33, recorded under 01-04's D-24 verification) |

## Two results worth reading carefully

**The single-instance first attempt looked like a failure and wasn't.** With the window already visible, relaunching left the foreground unchanged. That reads as broken until you account for Windows withholding focus changes from a process with no recent user input. Re-run with the window minimized — which is the actual scenario, since not seeing the window is *why* someone clicks again — and it restores and focuses correctly. Recorded both observations rather than only the passing one.

**The icon fix is unproven, not proven.** It passes on every path tested, including the Start Menu shortcut that was the leading hypothesis for the original report. But the blank icon was **never reproduced**, so "PASS" here means "no defect observed", not "defect fixed and confirmed". Plan 01-05's diagnosis ruled out `setWindowIcon` with Win32 handle evidence and fixed the only remaining mechanism; that reasoning is sound but it is reasoning, not a before/after.

## Deviations from Plan

Executed by the orchestrator rather than a subagent, because `packaging/build.py` takes ~15 min and three earlier executor dispatches had builds die with their agent's context. A rebuild was required first: the guard landed in source after the previous build, so no artifact contained it.

## Gaps — not closed

1. **No clean machine.** Every figure came from the developer box: `torch`/`transformers` installed globally, warm file cache, prior LecturePack history. This is developer-machine evidence and must not be cited as clean-device evidence. Beta-6's Phase 5 gate was accepted on evidence like this; that is exactly what `01-EVIDENCE.md` exists to prevent repeating.
2. **Time to *ready* never measured.** All timings are time-to-first-window. Criterion 3's "honest itemized progress" half is qualitative only.
3. **Four UI-SPEC backstops** open — reduced-motion timing, Tab focus containment, layout at other window sizes, whisper slow-notice text.
4. **~455 MB of the size discrepancy** still unexplained.

## Next Phase Readiness

Success Criteria 2, 4, 5, 6 are satisfied. Criterion 1 is satisfied for the measurement half; its reconciliation half remains partially open. Criterion 3 is satisfied for visible feedback, open for the progress-honesty half.

A clean-machine or VM pass is the single highest-value remaining action for this milestone.

## Self-Check: PASSED

Every number recorded came from the one artifact named above. Test install was uninstalled, temp profiles removed, Start Menu folder and registry entry confirmed gone.
