# Repo and release state

**Snapshot:** 2026-08-15 (updated after the `main` merge) · **Shipped:** v2.0.2

> This is a point-in-time snapshot of branch and worktree topology, written because
> this project has twelve worktrees and two earlier handoffs made confident claims
> about branch positions that turned out to be wrong. Every fact below was verified
> with git at the time of writing, and the command to re-verify it is included.
> **If this file disagrees with git, git wins — re-run the commands.**

---

## Repository

| | |
| --- | --- |
| Remote | `https://github.com/pasttrunks/lecturepack` (`origin`) |
| Release line | `sol/release-polish` |
| Latest release | **v2.0.2**, published and marked Latest |
| Release URL | https://github.com/pasttrunks/lecturepack/releases/tag/v2.0.2 |
| Installer SHA-256 | `c11c455d1948e52eefd3f4a9857f74d325c9b6b7ab9bc023ef2268aab4265439` |

## Branch positions

| Ref | Commit | Contains 2.0.0 | 2.0.1 | 2.0.2 |
| --- | --- | --- | --- | --- |
| `sol/release-polish` (release line) | `bd1dcce` | yes | yes | **yes** |
| `origin/main` | `0408881` | yes | yes | **yes** (merged 2026-08-15) |
| tag `v2.0.2` | `796cd53` | — | — | — |
| tag `v2.0.1` | — | — | — | — |
| tag `v2.0.0` | — | — | — | — |

```bash
git rev-parse --short origin/main sol/release-polish v2.0.2
```

### `main` now carries 2.0.2

Merged 2026-08-15 as `0408881`. The release line is **0 commits ahead of `main`**; the
two are in sync. The merge hit two conflicts, both of which were simply `main` lacking an
addition, and the merged tree came out byte-identical to the release line
(`git diff sol/release-polish` was empty). Suite on the merge result: **1758 passed, 0
failed, 22 skipped** — the extra skips versus the release line are the payload-gated tests
correctly skipping in a checkout with no `bin/`.

### Correction: `main` was never beta-era

Two earlier handoffs stated that `main` was still `459faf5` / `0.9.0-beta.5` and
contained none of 2.0.x. **That is false.** `origin/main` is `8404ddc` and already
contains v2.0.0 and v2.0.1.

The actual gap between `main` and the release line:

| Direction | Commits |
| --- | --- |
| In `sol/release-polish`, not in `main` | **70** (all of 2.0.2) |
| In `main`, not in `sol/release-polish` | **1** — `8404ddc`, already cherry-picked here as `a18b182` |

So promoting the release line to `main` is close to a fast-forward, not the large
reconciliation the older docs implied.

```bash
git rev-list --count origin/main..sol/release-polish
git rev-list --count sol/release-polish..origin/main
git merge-base --is-ancestor v2.0.1 origin/main && echo "main has 2.0.1"
```

## Worktrees

Twelve exist. This is the single biggest source of confusion in the project — the
session that shipped 2.0.2 began by working in the wrong one.

| Path | Branch | State |
| --- | --- | --- |
| `Documents\LecturePack` | `codex/ai-first-study` | main checkout; **fully merged**, 0 unique commits |
| `LecturePack-worktrees\release-polish` | `sol/release-polish` | **the release line — work here** |
| `LecturePack-worktrees\demo-rebuild` | `sol/demo-rebuild` | merged, 0 unique |
| `LecturePack-worktrees\polish-integration` | `sol/polish-integration` | merged, 0 unique |
| `LecturePack-worktrees\release-base-integration` | `sol/release-base-integration` | merged, 0 unique |
| `LecturePack-worktrees\release-hardening` | `sol/release-critical-hardening` | merged, 0 unique |
| `LecturePack-worktrees\stable-release` | `sol/lecturepack-stable-release` | merged, 0 unique |
| `LecturePack-worktrees\polish-ui` | `sol/polish-ui` | reviewed: all 4 commits **already applied** upstream — safe to remove |
| `LecturePack-worktrees\study-v1-integration` | `kimi/study-overhaul-v1` | reviewed: its 1 commit **cherry-picked** as `0dd78c0` — safe to remove |
| `.claude\worktrees\lecturepack-promo-video-b5e67c` | `claude/lecturepack-release-polish-38e98d` | 1 unique = `8404ddc`, already cherry-picked |
| `.claude\worktrees\lecturepak-v2-0-1-hardening-00a922` | `claude/design-mcp-setup-30b506` | same commit, already cherry-picked |
| `.claude\worktrees\remote-control-setup-82c6ab` | detached HEAD | same commit |

```bash
git worktree list
git merge-base --is-ancestor <branch> sol/release-polish && echo merged || echo unmerged
```

### Both were read, and the result corrects this document

An earlier version of this file said these two branches held unmerged work needing review.
That was measured with `git rev-list --count`, which counts **hashes**, not content. The
right tool is `git cherry`, which compares patch-ids:

```bash
git cherry -v sol/release-polish sol/polish-ui          # all "-" = already applied
git cherry -v sol/release-polish kimi/study-overhaul-v1 # "+" = genuinely missing
```

**`sol/polish-ui`** — all four commits came back `-`: already applied upstream under
different hashes. `requiredChecklistReady`, `waitForChecklist` and `REQUIRED_CHECK_IDS`
are all present in the release line. **Nothing to salvage; safe to delete.**

**`kimi/study-overhaul-v1`** — its single commit came back `+`, genuinely missing, and it
mattered: study progress persistence was writing through a fixed `.tmp` name with **no
`fsync` and no backup**. `study-progress-v2.json` holds irreplaceable mastery, attempt
history and Quick Study position; a power loss mid-write, or later corruption, lost it
permanently. Now cherry-picked as `0dd78c0`: unique same-directory temp file, flush and
`fsync`, atomic replace, and a rolling `.bak` last-known-good generation that load falls
back to. An invalid primary is never promoted over a valid backup.

Two conflicts were resolved by keeping **both** sides rather than either: the release
line's `_job_lock` (thread safety, added after this commit was authored) now wraps the
backup logic, and the incoming tests were kept alongside the `@requires_rust_study_core`
decorator they collided with. Recorded as **AD-54** in `docs/DECISIONS.md`, renumbered
because AD-36 was taken. Suite went 1772 → **1776 passed**.

## Commits that produced 2.0.2

Sixteen, on top of `0646a14`. The tag sits on `796cd53`; the two commits above it are
documentation written after tagging.

```
4a0cca6  docs: final handoff for the shipped 2.0.2 release
796cd53  docs: record the group study fix, the UX repairs and the CI payload gap   <- v2.0.2
d98aaf5  fix(ui): stop telling a student they have finished work they never started
2347678  fix(ci): the release workflow could never build the sidecar
f63c640  docs: changelog entries for the group study and Subjects fixes
a37201a  fix(ui): repair four defects on the Subjects screen
6adb4d7  fix(study): group study never unwrapped the gateway's answer
bdadeb0  docs: correct the handoff's release state
1b40d35  docs: record the installer, A/B and ISCC findings
450d12f  release: bump the npm lockfile to 2.0.2 as well
e96df27  docs: handoff for the 2.0.2 release candidate
88d7125  fix(gateway): stop leaking the admin key, constant-time compare
4095f1d  release: bump to 2.0.2, changelog and the M3 harness bug
a18b182  test: skip payload-dependent suites on a bare checkout (cherry-picked)
cb66a12  test(m3): fix the adversarial suite's four wrong assumptions
cdcf1df  feat(study): group study, subjects UI and the Gemini gateway route
```

```bash
git log --oneline 0646a14..sol/release-polish
```

## Corrections this snapshot makes to earlier docs

Recorded because each one cost real time in the session that shipped 2.0.2.

| Earlier claim | Reality |
| --- | --- |
| `main` is beta-era `459faf5`, has no 2.0.x | `main` is `8404ddc` and has 2.0.0 + 2.0.1 |
| `sol/release-polish` and the 2.0.1 hardening line have diverged | Never diverged; release-polish already contained all of v2.0.1 |
| v2.0.1 was tagged but not published | v2.0.1 **is** a published GitHub release |
| Inno Setup is not installed on this machine | Installed per-user at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`, just not on PATH |
| The gateway has `group_analysis` deployed | It did not; the deployed Worker was stale at 8 tasks. Deployed 2026-08-15, now 10/10 |

**The pattern:** every one of these was a confident statement inherited from a previous
document and repeated without re-checking. Branch topology, tool presence, and deployment
state are all cheap to verify and expensive to assume.

## Open structural work

- [x] ~~Merge the release line into `main`.~~ Done, `0408881`. In sync, 0 ahead.
- [x] ~~Review `sol/polish-ui` and `kimi/study-overhaul-v1`.~~ Done. The first was already
      applied; the second is cherry-picked as `0dd78c0`.
- [ ] **Prune worktrees.** All eleven besides `release-polish` now hold nothing unmerged.
      Left to the user to remove.
- [ ] **CI still cannot build.** `bin/` (ffmpeg, ffprobe, whisper-cli, model) is gitignored
      with no fetch step, so releases can only be cut from this machine. Fix is to host the
      payload and add a fetch + checksum step.
