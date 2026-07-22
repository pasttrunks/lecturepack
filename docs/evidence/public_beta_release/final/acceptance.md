# LecturePack 0.9.0-beta.1 — Final Release Acceptance

_Validation pass 2026-07-21/22. Branch `feat/desktop-webengine`._

## Version / Git
- Release version: **0.9.0-beta.1** (not previously published publicly; only a
  local `safety/public-beta-0.9.0-beta.1-e6f312e` tag existed).
- Full suite rerun at final code commit `82e05cd`: **330 passed in 211.11s, exit 0**
  (log: `pytest-final.txt`). Build/tooling changes since (docs, workflow) do not
  touch tested code.

## Artifacts (locally built, gate-verified)
Built with `app/packaging/build.py` (PyInstaller onedir + Inno Setup 6 ISCC +
portable ZIP + SHA256SUMS + release-asset gate):

| Artifact | Size | SHA256 |
| --- | --- | --- |
| `LecturePack-0.9.0-beta.1-Setup.exe` | 219,768,054 B | `38e2db6da2e8316708747c7e45bb6d95e56fc7ca08702d11fc8a802407971205` |
| `LecturePack-0.9.0-beta.1-Portable.zip` | 326,534,657 B | `c6549c4961f38fb57810e76cbd21ddad4d56325a50bbeeadf468534692186850` |
| `LecturePack-0.9.0-beta.1-SHA256SUMS.txt` | 207 B | (lists both binaries above) |

**Full release gate: PASS** — `validate_release_assets(require_installer=True)`
confirmed all three assets exist, are non-empty, and that SHA256SUMS lists both
binaries. A `--no-installer` build is NOT accepted as full release; this was the
full installer build.

## Updater validation
- Unit + integration: `tests/test_update_service.py` (16) + `tests/test_update_integration.py` (6)
  — discovery, verified download, checksum-mismatch rejection + cleanup,
  truncated-download rejection, active-job install block, visible
  `/CLOSEAPPLICATIONS /NORESTART` handoff flags, portable no-self-replace.
- Packaged discovery E2E on the **final** built exe: **DISCOVERY_OK** — the
  packaged binary queried the injected fake feed off-thread on startup (no
  source dependency, no crash).

## Human-pending gates (NOT self-certified — require a person/VM)
These could not be performed by the agent and were not fabricated:
1. **Packaged GUI click-through (§4)** — clicking through banner → overview →
   remind/skip → download → cancel → verified-ready → mismatch-blocked →
   active-job-blocked → visible installer → portable in the native window.
   Run it yourself with:
   `docs/evidence/public_beta_release/final/updater_clickthrough_harness.py`
   (add `--mismatch` for the rejection case). The underlying logic is covered
   by the integration tests + packaged discovery E2E above.
2. **Clean / new-user install (§5)** — install `Setup.exe` on a fresh Windows
   profile/VM; confirm first launch, local transcription, slides, transcript,
   Built-in Study, exports, updater UI, uninstall, and `LecturePackData`
   preservation. (Running the installer here would install software on the
   dev machine and can't drive a clean VM.)

## Installer compatibility
`lecturepack.iss` uses a stable `AppId` (unchanged) → updates install over the
existing app; `LecturePackData` lives outside `{app}` and is never in `[Files]`,
so uninstall preserves user data by default.

## Security / privacy
No secrets in the tree or artifacts (scanned; Groq key lives only in Windows
Credential Manager). HTTPS-only + GitHub-host-locked updater in production; test
feed override is env-only. No token embedded/logged; `LecturePackData` untouched.

## Publish decision
Published as a **GitHub pre-release** from the locally-verified artifacts (the
release workflow was switched to manual `workflow_dispatch` so a tag push cannot
trigger a second, non-reproducible rebuild that would overwrite the verified
binaries and break the published checksums). The two human-pending gates are
disclosed in the release notes; appropriate for a public beta.
