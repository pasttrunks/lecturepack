# Handoff — Final Beta Release (LecturePack 0.9.0-beta.1)

_2026-07-22. Branch `feat/desktop-webengine`._

## Outcome
Public **pre-release** `0.9.0-beta.1` published to GitHub from locally-built,
gate-verified artifacts. Two human-pending gates (packaged GUI click-through,
clean-machine install) are disclosed in the release notes — appropriate for a
public beta and not claimed as passed.

## Git
- Starting HEAD (this pass): `a6e34d2`
- Final code commit: `82e05cd` (tests rerun here → 330 passed)
- Final tree commit / tag target: see `git log` (docs commit) — tag `v0.9.0-beta.1`
- Working tree at tag time: **clean** (`git status --short` empty). Local
  agent/MCP tooling (`.claude/`, `.mcp.json`) is now gitignored; `CLAUDE.md`
  is tracked as a project file; evidence under `docs/evidence/.../final/` is
  committed.
- Never touched `C:\Users\marsh\LecturePackData`.

## Tests
Full suite at `82e05cd`: **330 passed in 211.11s, exit 0**
(`docs/evidence/public_beta_release/final/pytest-final.txt`).

## Artifacts + checksums
| Artifact | Bytes | SHA256 |
| --- | --- | --- |
| Setup.exe | 219,768,054 | `38e2db6da2e8316708747c7e45bb6d95e56fc7ca08702d11fc8a802407971205` |
| Portable.zip | 326,534,657 | `c6549c4961f38fb57810e76cbd21ddad4d56325a50bbeeadf468534692186850` |
| SHA256SUMS.txt | 207 | lists both binaries |
Full release gate (require_installer=True): **PASS**.

## Updater
Unit (16) + integration (6) green; packaged discovery E2E on the final exe:
**DISCOVERY_OK**. See `docs/HANDOFF_INAPP_UPDATER.md` and
`docs/evidence/public_beta_release/updater/updater_validation.json`.

## Remaining limitations (human/VM)
1. Packaged GUI click-through — run
   `docs/evidence/public_beta_release/final/updater_clickthrough_harness.py`.
2. Clean/new-user install of `Setup.exe` on a fresh profile/VM.
3. Live end-to-end update: the first real update test is `0.9.0-beta.1 →
   0.9.0-beta.2` once beta.2 is published (do NOT publish a fake release to test).

## Release process note
`.github/workflows/release.yml` is now manual `workflow_dispatch(tag)` — releases
are cut from locally-verified artifacts so published checksums always match the
verified binaries (a tag push no longer triggers a non-reproducible rebuild).

## Rollback
`git reset --hard a6e34d2` (this pass's start). Delete the GitHub release/tag via
`gh release delete v0.9.0-beta.1 --cleanup-tag` if it must be pulled.

## Next command
Publish beta.2 later by bumping `app/desktop/version.py`, tagging, building
locally (`app/packaging/build.py`), and `gh release create`.
