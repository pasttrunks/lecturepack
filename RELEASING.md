# Releasing LecturePack 2.0+

This is the **actual** release process, written from the code that runs it
(`scripts/build_electron_release.py`, `electron-spike/package-win.mjs`,
`.github/workflows/release.yml`, and the Electron updater in
`electron-spike/updater.js`). Follow it in order. Do not add aspirational
steps that nothing in the repo implements.

## Version surface

One authoritative version lives in `electron-spike/package.json`. The release
workflow also reads `app/desktop/version.py` and asserts the git tag equals it.
Before any release, bump **all** of these to the same value:

- `electron-spike/package.json` → `version`
- `electron-spike/package-lock.json` → `version` (top + package)
- `electron-spike/package-win.mjs` → `appVersion`, `ProductVersion`, `FileVersion`
- `electron-spike/production-main.js` → the `PRODUCT_VERSION` fallback
- `app/desktop/version.py` → `__version__` (workflow compares tag to this)
- `app/packaging/lecturepack.iss` → the `AppVersion` fallback define

`npm run validate` and the release packaging tests assert the Electron version
surfaces agree.

## Steps

1. **Bump the stable semver** on every surface above. Use a clean `2.x.0`
   incremented from the last stable. No `-beta` / `-rc` in a stable release.
2. **Run validation.**
   ```bash
   cd electron-spike && npm run validate
   ```
3. **Run the test suite** (Python): `python -m pytest` from the repo root.
   The package-pruning and onedir smoke tests need
   `LECTUREPACK_ONEDIR_FIXTURE` pointing at a verified packaged onedir and the
   bundled demo Whisper model present; those are build assets, not in git.
4. **Build the Rust Study Core** so `lecturepack_study_core.pyd` exists. The
   official build fails if it is missing (the packaged self-test asserts
   `study_core.ok == true`).
5. **Build the packaged sidecar**: `npm run package:sidecar` (needs the
   runtime root and MSVC runtime, see `electron-spike/sidecar.spec`).
6. **Build the Electron app + installer + hashes + manifest**:
   ```bash
   python scripts/build_electron_release.py --runtime-root <runtime> \
     --iscc <ISCC.exe> --output-dir <out>
   ```
   This produces:
   - `LecturePack-<version>-Portable.zip`
   - `LecturePack-<version>-Setup.exe` (per-user Inno, `PrivilegesRequired=lowest`)
   - `LecturePack-<version>-SHA256SUMS.txt`
   - `LecturePack-<version>-release-manifest.json` (the updater's SHA-256 source)
7. **Sign artifacts** if valid Authenticode credentials exist. Otherwise record
   `AUTHENTICODE SIGNING: NOT AVAILABLE` and do not fake it. The updater still
   enforces its own SHA-256 verification regardless.
8. **Run the packaged self-test**: `build_electron_release.py` runs the
   authoritative health contract (FFmpeg, ffprobe, Whisper smoke, model, Rust
   core, yt-dlp, controller) and **fails the build** if any required check
   fails.
9. **Run the updater E2E**: point the updater at a test-only feed (never a
   production env-var backdoor) and prove OLD → NEW version comparison,
   x64 installer selection, download, SHA-256 verification, active-work
   deferral, and that `LecturePackData` survives. See `tests/test_electron_updater.py`
   for the pure-logic coverage and the updater unit feed pattern.
10. **Run the release gates** (runtime packaged acceptance, clean-machine
    script, negative tests). See `scripts/electron_packaged_acceptance.py` and
    `scripts/clean_machine_validation.ps1`.
    Include `scripts/installer_test_isolation.ps1` beside the clean-machine
    validator in every kit. Both installer runners snapshot the actual per-user
    uninstall keys and shortcut bytes before installation and restore them after
    uninstall, including on failure. Use a fresh test directory. A leftover
    `LecturePack-installer-acceptance.lock` in LocalAppData means restoration
    needs recovery from its recorded snapshot; do not delete the lease or
    overwrite the snapshot to get another run started. `/NOICONS` alone does
    not isolate an Inno test install from an existing installation.
11. **Create an immutable git tag**: `git tag v<version>` (e.g. `v2.0.0`).
    Never reuse or move an existing tag.
12. **Push normally** (no force).
13. **Create the GitHub stable release** named `LecturePack <version>`, marked
    stable (not draft, not prerelease). Upload exactly the final assets:
    installer, portable zip, SHA256SUMS, release-manifest.json.
14. **Verify an installed previous stable detects the new stable** before
    publishing broadly (REQUIRED for the next release).

## Signing state

This project does not currently have valid Authenticode credentials committed
anywhere. Do **not** create a self-signed cert or invent signing keys. Record
`AUTHENTICODE SIGNING: AVAILABLE / NOT AVAILABLE` explicitly before each
release and surface it to the user rather than implying a signed binary.

## Real Electron multi-link gate

Run alone on Windows against the final packaged executable. Supply two or more
short public video URLs you may download, and new scratch data/results roots:

```powershell
python scripts/electron_batch_link_acceptance.py `
  --exe C:\LecturePackScratch\builds\candidate\LecturePack.exe `
  --data-dir C:\LecturePackScratch\data\batch-links `
  --results-dir C:\LecturePackScratch\results\batch-links `
  --url 'https://www.youtube.com/watch?v=jNQXAC9IVRw' `
  --url 'https://samplelib.com/mp4/sample-5s-360p.mp4'
```

The opt-in gate drives the actual Paste a link/Check link/Download UI, repeats
the first URL to check deduplication, verifies real inspected recordings and
persisted jobs, then reopens the app and requires the same renderer job IDs and
unchanged download hashes. It records screenshots, text, JSONL and result.json.
Success requires clean close on both launches and no orphan processes. It
leaves evidence/data intact and refuses existing roots. It does not process
the lectures, run Study AI, or substitute for those separate release gates.

## CI native runtime source

PR CI also runs an `electron-candidate` Windows job using this same official
builder. It builds and installs the locked Rust Python extension before sidecar
packaging, restores the pinned runtime, builds installer/portable assets, runs
mandatory packaged health checks and checks visible window startup. Only audit
logs, locks and hash/manifest evidence are retained for seven days. It has
read-only repository permissions and cannot publish desktop releases. This
candidate gate does not replace final-tag verification, real lecture/export
acceptance, clean shutdown, installer/updater or live Study AI gates.

The desktop workflow restores build inputs with scripts/restore_ci_runtime.py
and scripts/ci-runtime-lock.json before invoking the official Electron builder.
The source is the public 2.1.3 portable ZIP, verified by its pinned archive hash
and each of the 20 allowlisted CPU/model/Deno/MSVC member hashes. Cache hits are
verified too; corruption, missing members or existing runtime destinations fail
closed. CI uses fresh runner-temp runtime/MSVC roots and retains the restore
audit plus lock file. The prior app UI, Python package and user files are not
copied into the build. Restore pins are changed only after real binary checks
and member/hash review, never by updating a floating latest URL.

For local reproduction with a fresh output root:

```powershell
python scripts/restore_ci_runtime.py `
  --cache-dir C:\LecturePackScratch\data\ci-runtime-source `
  --output-dir C:\LecturePackScratch\data\ci-runtime-restored
$env:LECTUREPACK_RUNTIME_ROOT = 'C:\LecturePackScratch\data\ci-runtime-restored'
$env:LECTUREPACK_MSVC_RUNTIME_DIR = 'C:\LecturePackScratch\data\ci-runtime-restored\msvc'
```

Then run the normal Electron release builder. This is build-time restoration;
the application gains no runtime URL/key override. A local green build is not
a substitute for a successful GitHub-hosted release run on the final tag.
