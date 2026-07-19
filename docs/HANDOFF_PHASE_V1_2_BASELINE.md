# LecturePack v1.2 Baseline Handoff

**Phase:** v1.2 baseline profiling and safety
**Status:** Complete; awaiting approval before the stability/workflow-bug phase
**Branch:** `v1.2-hybrid-study`

## Completed

- Read `AGENTS.md`, `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, and `docs/IMPLEMENTATION_PLAN.md` in full.
- Verified the native Windows repository root, Git branch/remotes/tags/worktree,
  and the required data, model, and release-package directories.
- Created safety tag `safety/start-v1.2-hybrid-study` at starting commit
  `9cfaad25069f346b95e64d54ae4a1f0c5f17304f`.
- Created branch `v1.2-hybrid-study`.
- Preserved the pre-existing two-line `AGENTS.md` change in commit
  `14a35443e3e14c1440c38e9bb616c53ee0dee2b6`.
- Created the copy-only jobs backup at
  `C:\Users\marsh\LecturePackJobsBackup-v1.2-20260716-173647`.
- Reconciled backup and source: 815 files, 1,337,278,447 bytes, zero path,
  length, or timestamp mismatches.
- Verified the v1.1.0 release ZIP SHA-256, extracted it to a fresh path containing
  spaces, and ran the packaged executable against the exact 4,479.9-second
  lecture with isolated job data.
- Captured the raw packaged report, process-tree samples, actual Vulkan child
  executable, CPU/GPU/RAM measurements, source immutability, cache behavior,
  pipeline overlap, re-export behavior, and process cleanup.
- Ran the entire existing suite successfully.

## Baseline result

| Measurement | Result |
|---|---:|
| Required pipeline wall | 619.31 s |
| Inspect | 1.01 s |
| Extract audio | 5.44 s |
| Transcribe | 605.41 s |
| Detect slides (concurrent) | 523.47 s |
| Align + export (v1.1 combined stage) | 7.39 s |
| Peak working set | 1,658,843,136 bytes |
| Peak attributed GPU engine sum | 86.62% |
| Transcript segments | 575 |
| Slide candidates | 167 |
| Orphaned observed child processes | 0 |

Actual backend evidence: the monitored transcription child was
`bin\vulkan\whisper-cli.exe`; its command used `ggml-small.en-q8_0.bin`, and
the attributed Windows GPU counters peaked at 86.62%.

## Tests

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
```

Result:

```text
======================= 106 passed in 120.14s (0:02:00) =======================
```

The first invocation used a 120-second shell timeout and was terminated at 87%
with every executed test passing. No pytest process remained. That partial log
was preserved, and the suite was rerun from the beginning with a five-minute
limit; the second result above is authoritative.

## Evidence

See `docs/evidence/v1.2.0/README.md` and
`docs/evidence/v1.2.0/baseline_performance.json`.

## Remaining work

- v1.1 does not separately time model/backend load, alignment versus export, or
  Context Repair/Ollama. It also does not persist the requested timing breakdown
  in job details. These gaps are recorded explicitly in the baseline JSON.
- No stability bug, Study workspace, provider, VAD, detector, caching, packaging,
  release-documentation, or release-publishing work has begun.
- `docs/IMPLEMENTATION_PLAN.md` still describes the original v1.0 phases. The
  next phase must restate the v1.2 stability scope and exact permitted files
  before code changes.

## Blockers and approval gate

There is no technical blocker. Explicit user approval is required before
starting the next phase, as mandated by `AGENTS.md`.

Proposed next phase: focused stability and workflow bug repairs, beginning with
reproduction and tests for slide-selection behavior, keyboard operations,
Context Repair failure/cancellation/close paths, owned-process cleanup, settings
migration, re-export isolation, chronological transcript sorting, actual-backend
display, and online-error data preservation. Online providers and the Study
workspace remain non-goals for that phase.

## Safe continuation

After approval, first update the active plan and restate the exact permitted
source/test files based on repository inspection. Do not modify user jobs or the
original lecture video.
