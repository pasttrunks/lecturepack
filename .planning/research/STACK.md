# Technology Stack — Beta 6 Runtime Repair

**Project:** LecturePack v0.9.0-beta.6  
**Scope:** Exact-version repair of the bundled CPU runtime on Windows 10/11 x64  
**Researched:** 2026-07-27  
**Confidence:** MEDIUM — official primary documentation was checked; the final dependency decision requires an ADR because the verifier is not currently declared.

## Recommendation

Build a small **Infrastructure-layer `RuntimeRepairService`** using the Python standard library for release discovery/download, SHA-256, staging, atomic metadata writes, and ZIP extraction; add **`cryptography` with a pinned compatible range** solely for Ed25519 public-key verification. Do not adopt a general updater framework, GitHub client, HTTP library, or installer framework.

This meets the locked trust model: GitHub is the distribution host, but the embedded project public key authenticates the manifest; the signed manifest binds the exact running app version to one complete runtime package and every file hash. The repair target is a versioned, writable runtime cache below the already-configurable data directory—not the PyInstaller bundle or portable-install directory. That is necessary for the required non-admin/hostile-path support.

## Recommended Stack

### Core mechanism

| Technology | Version / status | Purpose | Why |
|---|---|---|---|
| Python standard library: `urllib.request`, `json`, `zipfile`, `pathlib`, `tempfile`, `os`, `shutil` | Python 3.12 project baseline | HTTPS download, canonical manifest bytes, safe archive handling, local file operations | No new HTTP/archive dependency. `urllib` follows GitHub release redirects; download only after the user presses **Repair all**. |
| Python standard library: `hashlib.sha256`, `hmac.compare_digest` | Python 3.12 | Streaming SHA-256 of downloaded package and extracted files | SHA-256 is guaranteed by `hashlib`; `compare_digest` is the intended non-short-circuit comparator for externally supplied digests. |
| `cryptography` — `Ed25519PublicKey` | **New direct dependency; approval required before implementation** | Verify the project-signed manifest against an embedded public key | The approved requirements do not include an Ed25519 verifier. A maintained verifier with a narrow public-key API is safer than home-grown crypto; its `verify()` raises `InvalidSignature` on failure. Pin a compatible range and ensure PyInstaller collects its native components. |
| GitHub Releases REST API | versioned API, public read only | Find the release by the exact application tag and enumerate/download its assets | Use `GET /repos/{owner}/{repo}/releases/tags/{tag}`—never “latest.” GitHub documents public asset access without auth and permits a stream or redirect response. |
| Existing PyInstaller **onedir** deployment | locked AD-8 | Read immutable bundled fallback; locate launcher/bundle accurately | Current PyInstaller docs distinguish `sys.executable` (launched EXE) and `sys._MEIPASS` (`_internal` in onedir). Do not write repaired files there. |
| Existing `FileManager.write_json_atomic` pattern plus `os.replace` | existing project pattern | Atomically publish active runtime generation/metadata | Preserve AD-2’s temp-file + replace approach. Promote only an already complete, validated generation; retain the prior generation for rollback. |

### Release asset contract

Publish exactly these assets per application release (names incorporate the exact application version):

| Asset | Contents / trust role |
|---|---|
| `LecturePack-<version>-cpu-runtime.zip` | Only the required CPU runtime: `ffmpeg.exe`, `ffprobe.exe`, `whisper-cli.exe`, all required Whisper/GGML DLLs, and `ggml-base.en.bin`. No application EXE and no optional CUDA/Vulkan pack. |
| `LecturePack-<version>-runtime-manifest.json` | Canonical UTF-8 JSON: schema version, `app_version`, release tag, archive filename + SHA-256 + byte size, and an exact sorted file map of normalized relative path, SHA-256, and byte size. |
| `LecturePack-<version>-runtime-manifest.sig` | Detached Ed25519 signature over the exact canonical manifest bytes (not a reserialized parsed object). |

The release query must fail closed unless its `tag_name` equals the normalized running tag (for example `v0.9.0-beta.6`) and its non-draft/non-prerelease policy is explicitly defined. Select assets by **exact filename**, reject duplicates/missing assets, and reject a manifest whose `app_version`, tag, archive name, or file list does not match. GitHub’s returned asset digest can be logged as an additional diagnostic, but it is not the project trust root; the signed manifest is.

### Installation layout and activation

```text
<LECTUREPACK_DATA_DIR>/
  runtime/
    active.json                       # atomically replaced activation record
    0.9.0-beta.5/                     # retained known-good generation
    0.9.0-beta.6/                     # complete verified generation
      bin/...
      models/ggml-base.en.bin
    .staging/<uuid>/                  # download + extract only; never executable source
```

`active.json` contains the selected version, generation path, manifest digest, and completion marker. It is written only after all validation succeeds. Runtime discovery order should be: healthy selected optional engine (unchanged), healthy active repaired/bundled CPU runtime, then bundled CPU fallback; a broken optional engine is a notice, never a setup-gate cause when CPU is healthy.

Do **not** copy repaired components over the application’s `bin/` or `models/` directory. A portable bundle may be read-only, in Program Files, on a removable drive, or currently open. The existing `ConfigManager` already makes `LECTUREPACK_DATA_DIR` a disposable-profile seam and persists runtime paths; extend that mechanism to resolve an active runtime generation without weakening the bundled fallback.

## Required Repair Algorithm

1. The setup gate obtains explicit user consent and reports the official GitHub source, app version, and planned download size. No request is made during normal healthy launch.
2. Query the official repository’s release **by the running tag**, with an explicit GitHub API version and timeout. Verify expected release/tag and the exact three asset names.
3. Download the manifest and detached signature to a uniquely created staging directory under the runtime parent. Verify the signature against the embedded Ed25519 public key *before trusting any manifest field*.
4. Parse with strict schema/type/size/path limits. Require UTF-8 canonical bytes (define and test canonical serialization at build time), a supported schema, the exact version/tag, no duplicate paths, relative POSIX paths only, and the expected required-file set. Reject absolute paths, `..`, drive prefixes, symlinks, extra entries, and ZIP compression-bomb limits.
5. Download the archive to staging with bounded streaming reads and a maximum size from the signed manifest. Hash while downloading; require the archive SHA-256 and size to match. Let `urllib` handle GitHub’s documented `200` or `302` asset response, but reject HTTP errors and unexpected final assets.
6. Extract into a fresh staging subdirectory only after archive verification. For every signed member, hash and size-check the extracted regular file; reject any missing, extra, duplicate, symlink-like, or path-escaping entry. Perform the required executable/DLL/model smoke checks here—not merely presence/size.
7. Move the complete validated directory into `<data_dir>/runtime/<version>/` on the **same volume**, then atomically replace `active.json`. Only now persist resolved paths/config and enter the application. This activation-pointer transaction avoids Windows directory-replace/open-handle ambiguity.
8. On any failure before activation, delete only the staging generation best-effort, preserve the previous active generation unchanged, log the reason, and return to the hard gate. On startup, ignore/sweep stale staging; if an activation record points to an invalid generation, fall back to the retained prior healthy generation or the bundled CPU payload and require repair.

## Compatibility and Windows/PyInstaller Constraints

| Constraint | Design response |
|---|---|
| Windows non-admin folders, spaces, and non-ASCII paths | Use `pathlib.Path`/Unicode paths and argument lists for smoke subprocesses; write only under the configured writable data directory. Test `LECTUREPACK_DATA_DIR` explicitly. |
| Onedir resources live beside/under a PyInstaller installation | Treat bundle files as immutable source/fallback. Current PyInstaller documents `sys._MEIPASS` as `_internal` in onedir and `sys.executable` as the launched EXE; use existing app-root discovery rather than current working directory. |
| Windows open DLL/EXE handles and antivirus locks | Never replace live bundle files. Stage below the final runtime parent; retries/backoff and actionable diagnostics are required for `PermissionError`. Keep previous generation until a later cleanup pass. |
| `os.replace` semantics | It replaces an existing file when permitted but may not cross filesystems; the atomic-success guarantee documented by Python is POSIX-specific. Use it for `active.json` on one volume, not as proof of a cross-directory transaction. |
| Existing CPU payload | Include the complete list currently enforced by `app/packaging/build.py`: FFmpeg/ffprobe, Whisper CLI, Whisper/GGML DLLs including `ggml-cpu-*.dll`, and base English model. Generate the manifest from the same release-build inventory so packaging and repair cannot drift. |
| Optional CUDA/Vulkan/custom engine | Preserve selection when healthy. Do not put optional GPU runtimes in the beta-6 recovery archive; the bundled CPU generation is the deterministic recovery path. |

## Alternatives Considered

| Category | Recommended | Alternative | Why not |
|---|---|---|---|
| Release lookup | GitHub release by exact tag + exact asset names | `releases/latest` | Violates exact-version repair and allows accidental cross-release components. |
| Manifest trust | Embedded-key Ed25519 detached signature | Unsigned SHA256SUMS / GitHub TLS alone | Checksums fetched from the same compromised location are not an authenticated project manifest and fail the locked decision. |
| Signature implementation | Approved `cryptography` Ed25519 | Home-grown pure-Python Ed25519 | Cryptographic verification must not be handwritten for a release trust boundary. |
| Signature implementation | Approved `cryptography` Ed25519 | Windows CNG/PowerShell/`certutil` shell-outs | Adds OS/API variability, subprocess surface, and packaging/test complexity without avoiding a formal dependency decision. |
| Install target | Versioned user data runtime cache + atomic activation record | Overwrite PyInstaller `bin/`/`models/` | Fails on non-admin/read-only installs and risks broken live application files. |
| Transaction | Fully validate immutable staged generation, then atomically switch pointer | Per-file in-place replacement | A crash, lock, or partial download can leave a mixed runtime. |
| HTTP client | Standard `urllib.request` | `requests`, PyGithub, general auto-update package | Adds unapproved dependencies without a capability gap. |

## Dependency Decision Gate

Before coding, record an approved ADR that adds the direct `cryptography` dependency and states its supported version range, wheel/PyInstaller collection check, manifest canonicalization format, embedded public-key encoding, private-key release custody, and key-rotation procedure. This is a material but narrowly scoped stack addition compelled by the locked signed-manifest requirement.

If approval is withheld, Beta 6 cannot honestly claim a project-signed Ed25519 manifest with the existing declared dependencies. Do not downgrade to unsigned checksums, HMAC (which would require shipping a secret), or a custom verifier.

## Verification Requirements for the Stack

- Build-time test generates a real manifest/signature from the runtime inventory, then verifies it with the embedded public key in a frozen-compatible build.
- Targeted tests cover wrong tag/version, altered manifest/signature, altered archive, every missing/corrupt required file, duplicate asset/name, traversal/extra ZIP member, size limit, failed smoke check, interrupted download, permission lock, and crash at each activation boundary.
- Packaged subprocess smoke test executes FFmpeg, ffprobe, and CPU Whisper/model loading from the staged generation on a disposable profile.
- Physical Windows matrix covers CPU-only, NVIDIA, AMD/Intel; fresh and upgraded profiles; offline healthy launch; non-admin, spaces, non-ASCII, and alternate data directory paths.

## Sources

- [GitHub REST: releases and exact release-by-tag endpoint](https://docs.github.com/en/rest/releases/releases#get-a-release-by-tag-name) — MEDIUM (official documentation retrieved through web fallback)
- [GitHub REST: release-asset download behavior](https://docs.github.com/en/rest/releases/assets#get-a-release-asset) — MEDIUM (official documentation retrieved through web fallback)
- [Python `hashlib` SHA-256 and file hashing](https://docs.python.org/3/library/hashlib.html) — MEDIUM (official documentation retrieved through web fallback)
- [Python `hmac.compare_digest`](https://docs.python.org/3/library/hmac.html#hmac.compare_digest) — MEDIUM (official documentation retrieved through web fallback)
- [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace) and [`tempfile.TemporaryDirectory`](https://docs.python.org/3/library/tempfile.html#tempfile.TemporaryDirectory) — MEDIUM (official documentation retrieved through web fallback)
- [`cryptography` Ed25519 verification](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) — MEDIUM (official documentation retrieved through web fallback)
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html) — MEDIUM (official documentation retrieved through web fallback)

