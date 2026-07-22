# Handoff — Safe In-App Updater (LecturePack 0.9.0-beta.1)

_Prepared 2026-07-21._

## Version decision (§1)
`0.9.0-beta.1` is **not** publicly released — the public repo `pasttrunks/lecturepack`
has no `v0.9.0-beta.1` release tag (only a local `safety/…` tag). So the updater
ships at **0.9.0-beta.1** unchanged. No public tag was moved.

- Starting HEAD: `e6f312e` · Ending HEAD: tip of `feat/desktop-webengine` (see git log)
- Safety tag present: `safety/public-beta-0.9.0-beta.1-e6f312e`

## Architecture
- **`app/desktop/update_service.py`** — pure, Qt-free, unit-tested: version
  parsing/compare (`packaging.Version`), channel filtering over the releases
  *list*, strict asset selection, SHA256 parse/verify/reconcile, overview builder.
- **`app/desktop/updater.py`** — Qt orchestration: `_CheckWorker` (fetch list),
  `_DownloadWorker` (.partial → verify → atomic rename, cancellable), install
  handoff, state/settings. No decision logic — it all lives in the service.
- **Bridge** (`app/desktop/bridge.py`): `check_updates`, `get_updater_state`,
  `start_update_download`, `cancel_update_download`, `install_downloaded_update`,
  `open_release_page`, `set_update_channel`, `set_auto_check`,
  `skip_update_version`, `clear_skipped_version` (+ `install_update` back-compat).
  New signal `update_state`.
- **UI** (`app/ui/index.html`, `app.js`): Update Overview overlay (current→available,
  channel, size, date, improvements/fixes/known-limitations, privacy note, and
  Download-and-Install / Remind-me-later / Skip-this-version / View-on-GitHub),
  download progress + cancel, and Updates settings (Beta/Stable channel,
  auto-check toggle, clear-skipped).

## Feed & channel
- URL pattern: `https://api.github.com/repos/pasttrunks/lecturepack/releases?per_page=20`
  (the *list*, so prereleases are discoverable — `/releases/latest` hides them).
- Headers: `Accept: application/vnd.github+json`, `User-Agent: LecturePack/<ver>`,
  `X-GitHub-Api-Version: 2022-11-28`. No token embedded; public repo.
- Beta channel (default for this build) accepts prereleases + stable and picks
  the newest; Stable ignores prereleases. Channel selector lives in Settings.

## Download / verification / install
- Cache: `%LOCALAPPDATA%\LecturePack\Updates`, `.partial` during download,
  **SHA256 verified before** an atomic rename; mismatch/cancel deletes the file;
  old installers pruned (keep 3). Never launches an unverified file.
- Digest sources: published `SHA256SUMS.txt` + GitHub asset `digest`, reconciled
  (must agree when both present).
- Install handoff: visible Inno installer `/CLOSEAPPLICATIONS /NORESTART`
  (never `/VERYSILENT`/`/SILENT`), blocked while a lecture is processing, saves
  state, then quits. Args passed as a list (no shell string).
- Portable/source builds never self-replace — the action opens the download page.

## Security/privacy
- HTTPS only in production; asset host locked to GitHub. A test-only feed can be
  injected via `LECTUREPACK_UPDATE_FEED` / `LECTUREPACK_UPDATE_HOSTS` (env-only,
  not reachable from the production UI; when unset, production host+https rules
  are fully enforced). Release notes rendered as escaped text — no HTML/JS exec.
  No token embedded/logged; no lecture data sent; `LecturePackData` untouched.

## Installer compatibility (§11)
`AppId` in `lecturepack.iss` is unchanged (stable GUID) → the update installs
over the existing app; `LecturePackData` (separate from `{app}`) survives.

## Tests
- `tests/test_update_service.py` — 16 pure-logic tests.
- `tests/test_update_integration.py` — 6 tests driving the real Qt updater
  against a local injected feed: discovery, verified download, checksum-mismatch
  rejection + cleanup, truncated-download rejection, active-job install block,
  visible `/CLOSEAPPLICATIONS` handoff flags, portable no-self-replace.
- Full suite at final HEAD: **330 passed** (was 308; +22).

## Build gate & packaged E2E
- `build.py` now runs `validate_release_assets()` — the build FAILS if
  `LecturePack-<ver>-Setup.exe` / `-Portable.zip` / `-SHA256SUMS.txt` are missing
  or the checksum file doesn't list both binaries.
- Rebuild (this env, no ISCC): **PASS** — `build.py --no-installer` produced
  `LecturePack-0.9.0-beta.1-Portable.zip` (326.5 MB) + `SHA256SUMS.txt`
  (`aa317540…46f9`); the release gate validated both.
- Packaged discovery E2E: **DISCOVERY_OK** — the freshly-built packaged exe
  queried the injected `/releases` feed off-thread on startup (no source
  dependency, no crash). Evidence:
  `docs/evidence/public_beta_release/updater/updater_validation.json`.

## Known limitations
- Installer `.exe` not built here (no Inno Setup); CI/ISCC build produces it.
  The build gate for the installer asset therefore runs on the CI/full build.
- The packaged GUI click-through of download→install is a human step; the
  download/verify/handoff/mismatch/portable *logic* is covered by the
  integration test against the same frozen modules.
- No live "newer release" exists yet; the first published beta.2 is the real
  live update test (do not publish a fake release to test).

## Rollback
`git reset --hard e6f312e` (this pass's start). Does not touch `LecturePackData`.

## Next command
```powershell
.\.venv\Scripts\python.exe app\packaging\build.py   # on a box with Inno Setup 6
```
