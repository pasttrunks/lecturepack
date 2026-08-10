'use strict';

/* LecturePack production auto-updater (Electron main process).
 *
 * Consumes STABLE GitHub releases only (drafts and prereleases are ignored),
 * compares versions semantically, selects the Windows x64 installer asset,
 * verifies its SHA-256 against the release manifest, and launches the
 * installer without overwriting the running app. Failures always leave the
 * current installation working.
 *
 * The module is intentionally dependency-light and testable: all network and
 * version logic lives in tiny pure functions that receive injected fetch()
 * and the current version, so unit tests can run off a local HTTP feed without
 * touching production.
 */

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000; // roughly once per day
const DOWNLOAD_TIMEOUT_MS = 30 * 60 * 1000; // 30 min for a large installer
const FETCH_TIMEOUT_MS = 15000;
const CHECK_STATE_KEY = 'updater.checkState.v1';

// GitHub auto-generated source archives are never update artifacts.
const SOURCE_ARCHIVE_NAMES = new Set(['source code (zip)', 'source code (tar.gz)']);

// --------------------------------------------------------------------------- //
// Version comparison (semver, never lexicographic).
// --------------------------------------------------------------------------- //
// Split "2.0.1", "2.0.1-beta.1", "2.0.0" into numeric + prerelease parts.
function parseVersionPart(value) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(String(value || '').trim());
  if (!m) return null;
  return {
    major: Number(m[1]),
    minor: Number(m[2]),
    patch: Number(m[3]),
    pre: m[4] ? m[4].toLowerCase() : null
  };
}

function comparePre(a, b) {
  // A release (no prerelease) is newer than any prerelease.
  if (a === null && b !== null) return 1;
  if (a !== null && b === null) return -1;
  if (a === null && b === null) return 0;
  const ap = a.split('.');
  const bp = b.split('.');
  const len = Math.max(ap.length, bp.length);
  for (let i = 0; i < len; i += 1) {
    const ax = ap[i];
    const bx = bp[i];
    if (ax === undefined) return -1;
    if (bx === undefined) return 1;
    const an = /^\d+$/.test(ax) ? Number(ax) : null;
    const bn = /^\d+$/.test(bx) ? Number(bx) : null;
    if (an !== null && bn !== null) {
      if (an !== bn) return an < bn ? -1 : 1;
    } else {
      const cmp = ax < bx ? -1 : ax > bx ? 1 : 0;
      if (cmp !== 0) return cmp;
    }
  }
  return 0;
}

function compareVersions(a, b) {
  const pa = parseVersionPart(a);
  const pb = parseVersionPart(b);
  if (!pa || !pb) return 0;
  if (pa.major !== pb.major) return pa.major < pb.major ? -1 : 1;
  if (pa.minor !== pb.minor) return pa.minor < pb.minor ? -1 : 1;
  if (pa.patch !== pb.patch) return pa.patch < pb.patch ? -1 : 1;
  return comparePre(pa.pre, pb.pre);
}

function isNewer(remote, local) {
  return compareVersions(remote, local) > 0;
}

function isStable(tag) {
  const p = parseVersionPart(tag);
  return !!(p && p.pre === null);
}

// --------------------------------------------------------------------------- //
// Release feed filtering (stable channel only).
// --------------------------------------------------------------------------- //
function selectStableRelease(releases, currentVersion) {
  if (!Array.isArray(releases)) return null;
  let best = null;
  for (const release of releases) {
    if (!release || release.draft || release.prerelease) continue;
    const tag = String(release.tag_name || release.name || '');
    if (!isStable(tag)) continue;
    // Ignore runtime-only releases that carry no app installer asset.
    const assets = Array.isArray(release.assets) ? release.assets : [];
    const hasInstaller = assets.some((a) => /-Setup\.exe$/i.test(String(a.name || '') || ''));
    if (!hasInstaller) continue;
    if (!isNewer(tag, currentVersion)) continue;
    if (!best || compareVersions(tag, String(best.tag_name || best.name || '')) > 0) best = release;
  }
  return best;
}

// --------------------------------------------------------------------------- //
// Asset selection.
// --------------------------------------------------------------------------- //
function selectInstallerAsset(release) {
  const assets = Array.isArray(release.assets) ? release.assets : [];
  const installer = assets.find((a) => /-Setup\.exe$/i.test(String(a.name || '') || ''));
  const manifest = assets.find((a) => /-release-manifest\.json$/i.test(String(a.name || '') || ''));
  return { installer: installer || null, manifest: manifest || null };
}

function assetDownloadUrl(asset) {
  return String(asset.browser_download_url || asset.url || '');
}

// --------------------------------------------------------------------------- //
// Verification.
// --------------------------------------------------------------------------- //
function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  const data = fs.readFileSync(filePath);
  hash.update(data);
  return hash.digest('hex').toLowerCase();
}

function parseManifest(text) {
  try {
    const doc = JSON.parse(text);
    if (doc && typeof doc === 'object' && !Array.isArray(doc)) return doc;
  } catch (_) { /* malformed manifest */ }
  return null;
}

function normalizeVersion(value) {
  return String(value || '').trim().replace(/^v/i, '');
}

const SHA256_HEX = /^[0-9a-f]{64}$/;

/* Authoritative release-manifest gate (updater trust requirements 4-10).
 *
 * Returns { ok, sha256, reason }. `ok` is true ONLY when every field agrees
 * with the release we actually selected AND the digest is bound to the exact
 * installer filename we are about to download. There is deliberately no
 * "hash found somewhere in the document" fallback: a digest published for a
 * different Setup.exe (another version, another platform, another release)
 * must never satisfy this check.
 */
function verifyReleaseManifest(manifest, expected) {
  const wantVersion = normalizeVersion(expected && expected.version);
  const wantFilename = String((expected && expected.filename) || '').trim();
  if (!manifest) return { ok: false, sha256: null, reason: 'manifest_unparseable' };
  if (!wantVersion) return { ok: false, sha256: null, reason: 'release_version_unknown' };
  if (!wantFilename) return { ok: false, sha256: null, reason: 'installer_filename_unknown' };

  if (normalizeVersion(manifest.version) !== wantVersion) {
    return { ok: false, sha256: null, reason: 'manifest_version_mismatch' };
  }
  if (String(manifest.platform || '').toLowerCase() !== 'win32') {
    return { ok: false, sha256: null, reason: 'manifest_platform_mismatch' };
  }
  if (String(manifest.architecture || manifest.arch || '').toLowerCase() !== 'x64') {
    return { ok: false, sha256: null, reason: 'manifest_architecture_mismatch' };
  }
  if (!Array.isArray(manifest.installers) || manifest.installers.length === 0) {
    return { ok: false, sha256: null, reason: 'manifest_missing_installers' };
  }

  // Exact, case-insensitive filename binding. Compare basenames so a manifest
  // cannot smuggle a path prefix past the match.
  const wantKey = path.basename(wantFilename).toLowerCase();
  let entry = null;
  for (const item of manifest.installers) {
    if (!item || typeof item !== 'object') continue;
    const name = path.basename(String(item.filename || item.name || '')).toLowerCase();
    if (name && name === wantKey) {
      if (entry) return { ok: false, sha256: null, reason: 'manifest_duplicate_installer_entry' };
      entry = item;
    }
  }
  if (!entry) return { ok: false, sha256: null, reason: 'manifest_installer_not_listed' };

  const digest = String(entry.sha256 || '').trim().toLowerCase();
  if (!SHA256_HEX.test(digest)) {
    return { ok: false, sha256: null, reason: 'manifest_invalid_sha256' };
  }
  return { ok: true, sha256: digest, reason: 'verified' };
}

// Backwards-compatible helper. The installer filename is REQUIRED: without it
// there is nothing to bind the digest to, so the answer is always null.
function expectedInstallerSha256(manifest, installerFilename, releaseVersion) {
  const filename = String(installerFilename || '');
  const version = releaseVersion !== undefined
    ? releaseVersion
    : (/^LecturePack-(.+)-Setup\.exe$/i.exec(path.basename(filename)) || [])[1];
  return verifyReleaseManifest(manifest, { version, filename }).sha256;
}

// --------------------------------------------------------------------------- //
// State persistence (24h throttle + last check).
// --------------------------------------------------------------------------- //
function statePath(userDataDir) {
  return path.join(userDataDir, `${CHECK_STATE_KEY}.json`);
}

function loadState(userDataDir) {
  const empty = { lastCheck: 0, lastError: '', skippedVersion: '', autoCheck: true };
  try {
    const doc = JSON.parse(fs.readFileSync(statePath(userDataDir), 'utf8'));
    return {
      lastCheck: Number(doc.lastCheck) || 0,
      lastError: doc.lastError || '',
      skippedVersion: normalizeVersion(doc.skippedVersion),
      // Opt-out preference: anything other than an explicit false means on.
      autoCheck: doc.autoCheck !== false
    };
  } catch (_) {
    return empty;
  }
}

// A skipped version stays skipped only until something strictly newer ships.
function isVersionSkipped(userDataDir, remoteVersion) {
  const skipped = loadState(userDataDir).skippedVersion;
  if (!skipped) return false;
  return compareVersions(remoteVersion, skipped) <= 0;
}

function setSkippedVersion(userDataDir, remoteVersion) {
  const value = normalizeVersion(remoteVersion);
  saveState(userDataDir, Object.assign(loadState(userDataDir), { skippedVersion: value }));
  return value;
}

function setAutoCheckEnabled(userDataDir, enabled) {
  const value = enabled !== false;
  saveState(userDataDir, Object.assign(loadState(userDataDir), { autoCheck: value }));
  return value;
}

function saveState(userDataDir, state) {
  try {
    fs.mkdirSync(userDataDir, { recursive: true });
    fs.writeFileSync(statePath(userDataDir), JSON.stringify(state), 'utf8');
  } catch (_) { /* state persistence must never break the app */ }
}

function shouldAutoCheck(userDataDir) {
  const state = loadState(userDataDir);
  if (!state.autoCheck) return false;
  return Date.now() - state.lastCheck >= CHECK_INTERVAL_MS;
}

// --------------------------------------------------------------------------- //
// GitHub feed.
// --------------------------------------------------------------------------- //
function feedUrl(repo) {
  return `https://api.github.com/repos/${repo}/releases?per_page=30`;
}

async function fetchJson(url, fetchImpl) {
  const fn = fetchImpl || globalThis.fetch;
  if (typeof fn !== 'function') throw new Error('No fetch implementation available.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fn(url, {
      headers: { 'User-Agent': 'LecturePack-Updater/2', Accept: 'application/vnd.github+json' },
      signal: controller.signal
    });
    if (!resp.ok) throw new Error(`GitHub returned HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

// --------------------------------------------------------------------------- //
// Download with progress + integrity.
// --------------------------------------------------------------------------- //
function removeQuietly(filePath) {
  try { fs.unlinkSync(filePath); } catch (_) { /* already gone */ }
}

class UpdateCancelledError extends Error {
  constructor() {
    super('The update download was cancelled.');
    this.name = 'UpdateCancelledError';
    this.cancelled = true;
  }
}

/* Stream a download straight to <destPath>.tmp while hashing incrementally.
 *
 * The installer is several hundred megabytes, so it is never buffered in
 * memory. The temporary file is promoted to destPath only after the digest
 * matches. Every failure path (HTTP error, network drop, timeout, abort,
 * checksum mismatch) removes the partial .tmp and leaves destPath untouched.
 */
async function fetchToFile(url, destPath, { fetchImpl, onProgress, expectedSha256, signal } = {}) {
  const fn = fetchImpl || globalThis.fetch;
  if (typeof fn !== 'function') throw new Error('No fetch implementation available.');

  const tmpPath = `${destPath}.tmp`;
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  if (signal) {
    if (signal.aborted) throw new UpdateCancelledError();
    signal.addEventListener('abort', abortFromCaller, { once: true });
  }
  const timer = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT_MS);
  const hash = crypto.createHash('sha256');

  fs.mkdirSync(path.dirname(tmpPath), { recursive: true });
  removeQuietly(tmpPath);
  let handle = null;
  try {
    const resp = await fn(url, {
      headers: { 'User-Agent': 'LecturePack-Updater/2' },
      signal: controller.signal
    });
    if (!resp.ok) throw new Error(`Download returned HTTP ${resp.status}`);
    const total = Number(resp.headers.get('content-length')) || 0;
    let received = 0;

    handle = fs.openSync(tmpPath, 'w');
    const writeChunk = (value) => {
      const chunk = Buffer.isBuffer(value) ? value : Buffer.from(value);
      hash.update(chunk);
      fs.writeSync(handle, chunk);
      received += chunk.length;
      if (onProgress) onProgress(received, total);
    };

    const reader = resp.body && typeof resp.body.getReader === 'function' ? resp.body.getReader() : null;
    if (reader) {
      for (;;) {
        if (signal && signal.aborted) throw new UpdateCancelledError();
        const { done, value } = await reader.read();
        if (done) break;
        if (value) writeChunk(value);
      }
    } else {
      // Fetch implementations without a streaming body (some test doubles).
      writeChunk(Buffer.from(await resp.arrayBuffer()));
    }
    fs.closeSync(handle);
    handle = null;

    if (expectedSha256) {
      const actual = hash.digest('hex').toLowerCase();
      if (actual !== String(expectedSha256).toLowerCase()) {
        removeQuietly(tmpPath);
        throw new Error(
          'Update verification failed: the downloaded installer checksum does not match the release manifest.'
        );
      }
    }
    removeQuietly(destPath);
    fs.renameSync(tmpPath, destPath);
    return destPath;
  } catch (error) {
    if (handle !== null) { try { fs.closeSync(handle); } catch (_) { /* ignore */ } }
    removeQuietly(tmpPath);
    removeQuietly(destPath);
    if (signal && signal.aborted && !(error && error.cancelled)) throw new UpdateCancelledError();
    throw error;
  } finally {
    clearTimeout(timer);
    if (signal) { try { signal.removeEventListener('abort', abortFromCaller); } catch (_) { /* ignore */ } }
  }
}

// --------------------------------------------------------------------------- //
// Updater instance.
// --------------------------------------------------------------------------- //
function createUpdater({ version, repo, userDataDir, logger, fetchImpl, onState }) {
  const log = (event, details) => {
    try { if (logger && typeof logger.write === 'function') logger.write(event, details || {}); } catch (_) {}
  };
  const emitState = (patch) => {
    try { if (onState && typeof onState === 'function') onState(patch || {}); } catch (_) {}
  };

  // One concise, recoverable message per refusal. The user is never told an
  // update is ready unless it passed every gate; they are always pointed at a
  // retry or at the GitHub releases page.
  const UNTRUSTED_MESSAGES = {
    installer_asset_missing: 'This release does not publish a Windows installer.',
    installer_asset_unexpected: 'This release publishes an unexpected installer filename.',
    release_manifest_missing: 'This release does not publish a verification manifest.',
    release_manifest_unavailable: 'LecturePack could not download the release verification manifest.',
    manifest_unparseable: 'The release verification manifest could not be read.',
    manifest_version_mismatch: 'The release verification manifest is for a different version.',
    manifest_platform_mismatch: 'The release verification manifest is not for Windows.',
    manifest_architecture_mismatch: 'The release verification manifest is not for 64-bit Windows.',
    manifest_missing_installers: 'The release verification manifest lists no installer.',
    manifest_installer_not_listed: 'The release verification manifest does not cover this installer.',
    manifest_duplicate_installer_entry: 'The release verification manifest is ambiguous.',
    manifest_invalid_sha256: 'The release verification manifest has no valid checksum.'
  };

  const untrustedMessage = (reason) =>
    `${UNTRUSTED_MESSAGES[reason] || 'This update could not be verified.'} ` +
    'LecturePack will not install an unverified update. You can try again later or download it yourself from GitHub.';

  // Terminal refusal: current installation is untouched, nothing is staged.
  const fail = (event, reason, now) => {
    const message = untrustedMessage(reason);
    log(event, { reason });
    const state = { status: 'untrusted', reason, error: message, checkedAt: now };
    saveState(userDataDir, Object.assign(loadState(userDataDir), { lastError: message }));
    emitState(state);
    return state;
  };

  // Live download cancellation (AbortController owned by the updater).
  let activeDownload = null;

  return {
    // `respectSkip` is set for background checks so a version the user chose
    // to skip stays quiet. An explicit "Check for updates" always reports.
    async check({ respectSkip = false } = {}) {
      log('update_check_started', { version });
      const now = Date.now();
      saveState(userDataDir, Object.assign(loadState(userDataDir), { lastCheck: now }));
      try {
        const releases = await fetchJson(feedUrl(repo), fetchImpl);
        let release = selectStableRelease(releases, version);
        if (release && respectSkip && isVersionSkipped(userDataDir, String(release.tag_name || release.name || ''))) {
          log('update_skipped_by_user', { remote: String(release.tag_name || release.name || '') });
          release = null;
        }
        if (!release) {
          log('update_none', { version });
          emitState({ status: 'uptodate', version, checkedAt: now });
          return { status: 'uptodate' };
        }
        const tag = String(release.tag_name || release.name || '');
        const { installer, manifest: manifestAsset } = selectInstallerAsset(release);

        // Gate 3: the asset must be the expected Windows x64 LecturePack setup.
        if (!installer || !assetDownloadUrl(installer)) {
          return fail('update_untrusted', 'installer_asset_missing', now);
        }
        if (String(installer.name || '') !== `LecturePack-${normalizeVersion(tag)}-Setup.exe`) {
          return fail('update_untrusted', 'installer_asset_unexpected', now);
        }
        if (!manifestAsset || !assetDownloadUrl(manifestAsset)) {
          return fail('update_untrusted', 'release_manifest_missing', now);
        }

        // Gates 4-10: fetch and fully validate the release manifest. Any
        // failure here is terminal for this check -- there is no path that
        // continues with an unverified installer.
        const manifestPath = path.join(userDataDir, `release-manifest-${tag}.json`);
        let verdict;
        try {
          await fetchToFile(assetDownloadUrl(manifestAsset), manifestPath, { fetchImpl });
          verdict = verifyReleaseManifest(
            parseManifest(fs.readFileSync(manifestPath, 'utf8')),
            { version: tag, filename: String(installer.name || '') }
          );
        } catch (error) {
          verdict = { ok: false, sha256: null, reason: 'release_manifest_unavailable' };
        } finally {
          removeQuietly(manifestPath);
        }
        if (!verdict.ok) return fail('update_untrusted', verdict.reason, now);

        const update = {
          version: tag,
          installerName: String(installer.name || ''),
          downloadUrl: assetDownloadUrl(installer),
          size: Number(installer.size) || 0,
          expectedSha256: verdict.sha256,
          releaseUrl: String(release.html_url || ''),
          notes: String(release.body || '').slice(0, 4000)
        };
        log('update_available', { remote: tag, verified: true });
        const state = { status: 'available', update, checkedAt: now, lastError: '' };
        saveState(userDataDir, Object.assign(loadState(userDataDir), { lastError: '' }));
        emitState(state);
        return state;
      } catch (error) {
        log('update_check_failed', { error: error.message });
        const state = { status: 'error', error: error.message, checkedAt: now };
        saveState(userDataDir, Object.assign(loadState(userDataDir), { lastError: error.message }));
        emitState(state);
        return state;
      }
    },

    async download(update, onProgress) {
      if (!update || !update.downloadUrl) throw new Error('No update download is available.');
      // Fail closed: an update that never carried a manifest-verified digest
      // cannot be downloaded for installation at all.
      if (!SHA256_HEX.test(String(update.expectedSha256 || '').toLowerCase())) {
        const message = untrustedMessage('manifest_invalid_sha256');
        log('update_download_refused', { remote: update.version, reason: 'no_verified_sha256' });
        emitState({ status: 'untrusted', reason: 'manifest_invalid_sha256', error: message });
        throw new Error(message);
      }
      log('update_download_started', { remote: update.version });
      const dest = path.join(
        userDataDir,
        update.installerName || `LecturePack-${normalizeVersion(update.version)}-Setup.exe`
      );
      const controller = new AbortController();
      activeDownload = controller;
      try {
        await fetchToFile(update.downloadUrl, dest, {
          fetchImpl,
          signal: controller.signal,
          onProgress: (received, total) => {
            if (onProgress) onProgress(received, total);
          },
          expectedSha256: update.expectedSha256
        });
        log('update_download_completed', { remote: update.version, file: dest, sha256: 'verified' });
        emitState({ status: 'downloaded', update, installerPath: dest, verified: true });
        return dest;
      } catch (error) {
        // fetchToFile already removed the .tmp and any partial destination.
        if (error && error.cancelled) {
          log('update_download_cancelled', { remote: update.version });
          emitState({ status: 'available', update, cancelled: true });
        } else {
          log('update_download_failed', { error: error.message });
          emitState({ status: 'error', error: error.message });
        }
        throw error;
      } finally {
        if (activeDownload === controller) activeDownload = null;
      }
    },

    // Real cancellation: aborts the in-flight fetch so the download stops and
    // its partial file is removed. Returns whether a download was cancelled.
    cancelDownload() {
      if (!activeDownload) return false;
      activeDownload.abort();
      return true;
    },

    isDownloading() {
      return activeDownload !== null;
    },

    // Launch the installer over the same per-user installation. Returns the
    // child process. The installer must be allowed to run; the app exits after
    // spawning it so the installer can finish.
    install(installerPath) {
      if (!installerPath || !fs.existsSync(installerPath)) {
        throw new Error('The downloaded installer is missing.');
      }
      log('update_installer_launch', { file: installerPath });
      const child = spawn(installerPath, [], {
        detached: true,
        stdio: 'ignore',
        windowsHide: false,
        shell: false
      });
      child.on('error', (error) => log('update_installer_spawn_error', { error: error.message }));
      child.unref();
      return child;
    }
  };
}

module.exports = {
  compareVersions,
  isNewer,
  isStable,
  selectStableRelease,
  selectInstallerAsset,
  expectedInstallerSha256,
  verifyReleaseManifest,
  normalizeVersion,
  parseManifest,
  sha256File,
  shouldAutoCheck,
  loadState,
  saveState,
  isVersionSkipped,
  setSkippedVersion,
  setAutoCheckEnabled,
  fetchToFile,
  UpdateCancelledError,
  createUpdater,
  CHECK_INTERVAL_MS
};