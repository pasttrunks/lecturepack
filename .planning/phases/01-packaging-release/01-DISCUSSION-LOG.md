# Phase 1: Packaging & Release - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-18
**Phase:** 01-packaging-release
**Areas discussed:** Missing-input policy, Cleanup safety

---

## Missing-input policy

### Required inputs

| Option | Description | Selected |
|--------|-------------|----------|
| Required core plus all-or-nothing Vulkan | Require FFmpeg/FFprobe, complete CPU Whisper, and release documents; Vulkan may be absent but cannot be partial. | ✓ |
| Warning-tolerant | Require core binaries but allow missing documents or partial Vulkan with warnings. | |
| Vulkan mandatory | Require every runtime including Vulkan. | |

### Failure behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Aggregate preflight failure | Validate everything before cleanup, report all problems, exit nonzero, preserve outputs. | ✓ |
| First failure | Stop at the first missing input. | |
| Partial build | Continue but withhold the final ZIP. | |

### Optional Vulkan

| Option | Description | Selected |
|--------|-------------|----------|
| All-or-nothing when present | Absence allowed; partial presence blocks before cleanup. | ✓ |
| Warning-only partial copy | Copy available Vulkan files and warn about missing ones. | |
| CPU-only | Ignore Vulkan for v1.2. | |

### Incomplete-release bypass

| Option | Description | Selected |
|--------|-------------|----------|
| No bypass | The documented builder always fails closed. | ✓ |
| Diagnostic incomplete mode | Allow incomplete diagnostics but no release ZIP. | |
| Forced incomplete ZIP | Permit a marked incomplete package. | |

### Document identity

| Option | Description | Selected |
|--------|-------------|----------|
| Validate every shipped document | All release identities must report v1.2.0 before cleanup. | ✓ |
| Existence only | Defer content consistency to later tests. | |
| README-only | Validate only the first-run banner. | |

### Binary preflight depth

| Option | Description | Selected |
|--------|-------------|----------|
| Structural validation | Require regular, non-empty, non-reparse files; rely on post-build self-tests for execution. | ✓ |
| Existence only | Check only that paths exist. | |
| Execute everything | Run every input binary and verify versions during preflight. | |

### Publication

| Option | Description | Selected |
|--------|-------------|----------|
| Staged replacement | Publish only after all checks pass and preserve the prior release on failure. | ✓ |
| Delete first | Remove the prior release after preflight before building. | |
| Publish partial output | Keep a marked failed-build package. | |

### Failed-build diagnostics

| Option | Description | Selected |
|--------|-------------|----------|
| Compact log and cleanup | Keep a failure log, safely remove staging, preserve the prior release. | ✓ |
| Retain staging | Keep the full failed staging tree. | |
| Exit code only | Remove all output and retain no diagnostic log. | |

**User's choice:** Strict fail-closed preflight and transactional staged publication.
**Notes:** No incomplete release may be produced. Stale document identities are preflight failures.

---

## Cleanup safety

### Unexpected release entries

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse in place | List unexpected entries and leave `dist-release` untouched. | |
| Back up and continue | Move entries to a timestamped backup; continue only after every move succeeds. | ✓ |
| Delete after warning | Remove unexpected entries after printing a warning. | |

### Backup location

| Option | Description | Selected |
|--------|-------------|----------|
| Repo-local `release-backups/` | Store timestamped backups outside all cleanup targets; abort on move failure. | ✓ |
| Inside `dist-release` | Preserve entries under an internal `_backup/` directory. | |
| User temp directory | Move entries to the operating-system temporary directory. | |

### Reparse points

| Option | Description | Selected |
|--------|-------------|----------|
| Block without traversal | Refuse the build and never traverse, move through, or delete the target. | ✓ |
| Remove the link | Delete only the link itself and continue. | |
| Resolve and continue | Follow the target when it appears repo-local. | |

### Cleanup target scope

| Option | Description | Selected |
|--------|-------------|----------|
| Exact hardcoded allowlist | Permit only resolved repo-child `build`, `dist`, staging, and `dist-release`. | ✓ |
| Any CLI repo path | Permit arbitrary user-supplied repo-local paths. | |
| Prefix matching | Permit any directory whose name begins with `build` or `dist`. | |

**User's choice:** Preserve unexpected entries in safe repo-local backups and restrict all destructive actions to exact non-reparse targets.
**Notes:** Backup failures abort before cleanup.

---

## the agent's Discretion

- Internal helper names, error/result structures, test organization, v1.2 release-note wording, manifest presentation, and compact failure-log format remain flexible within the locked safety and verification requirements.

## Deferred Ideas

- None. Architecture remediation remains assigned to Phase 2 by AD-15 and was not reopened.
