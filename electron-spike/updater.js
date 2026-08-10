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
    if (doc && typeof doc === 'object') return doc;
  } catch (_) { /* malformed manifest */ }
  return null;
}

// Expected installer SHA-256 from the release manifest (U7). Supports both a
// top-level "installer_sha256" and a nested asset list.
function expectedInstallerSha256(manifest) {
  if (!manifest) return null;
  const direct = manifest.installer_sha256 || manifest.sha256;
  if (direct && /^[0-9a-fA-F]{64}$/.test(String(direct))) return String(direct).toLowerCase();
  if (Array.isArray(manifest.installers)) {
    for (const item of manifest.installers) {
      if (item && /-Setup\.exe$/i.test(String(item.filename || item.name || '')) &&
          /^[0-9a-fA-F]{64}$/.test(String(item.sha256 || ''))) {
        return String(item.sha256).toLowerCase();
      }
    }
  }
  return null;
}

// --------------------------------------------------------------------------- //
// State persistence (24h throttle + last check).
// --------------------------------------------------------------------------- //
function statePath(userDataDir) {
  return path.join(userDataDir, `${CHECK_STATE_KEY}.json`);
}

function loadState(userDataDir) {
  try {
    const doc = JSON.parse(fs.readFileSync(statePath(userDataDir), 'utf8'));
    return { lastCheck: Number(doc.lastCheck) || 0, lastError: doc.lastError || '' };
  } catch (_) {
    return { lastCheck: 0, lastError: '' };
  }
}

function saveState(userDataDir, state) {
  try {
    fs.mkdirSync(userDataDir, { recursive: true });
    fs.writeFileSync(statePath(userDataDir), JSON.stringify(state), 'utf8');
  } catch (_) { /* state persistence must never break the app */ }
}

function shouldAutoCheck(userDataDir) {
  const state = loadState(userDataDir);
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
async function fetchToFile(url, destPath, { fetchImpl, onProgress, expectedSha256 } = {}) {
  const fn = fetchImpl || globalThis.fetch;
  if (typeof fn !== 'function') throw new Error('No fetch implementation available.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT_MS);
  const hash = crypto.createHash('sha256');
  await new Promise((resolve, reject) => {
    (async () => {
      try {
        const resp = await fn(url, {
          headers: { 'User-Agent': 'LecturePack-Updater/2' },
          signal: controller.signal
        });
        if (!resp.ok) throw new Error(`Download returned HTTP ${resp.status}`);
        const total = Number(resp.headers.get('content-length')) || 0;
        let received = 0;
        const reader = resp.body && typeof resp.body.getReader === 'function' ? resp.body.getReader() : null;
        if (!reader) {
          const buf = Buffer.from(await resp.arrayBuffer());
          hash.update(buf);
          fs.writeFileSync(destPath, buf);
          if (onProgress) onProgress(buf.length, buf.length || total);
          resolve();
          return;
        }
        const chunks = [];
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value) {
            const chunk = Buffer.from(value);
            hash.update(chunk);
            chunks.push(chunk);
            received += chunk.length;
            if (onProgress) onProgress(received, total);
          }
        }
        fs.writeFileSync(destPath, Buffer.concat(chunks));
        resolve();
      } catch (error) {
        reject(error);
      }
    })();
  })
    .catch((error) => {
      try { fs.unlinkSync(destPath); } catch (_) { /* ignore */ }
      throw error;
    })
    .finally(() => clearTimeout(timer));
  if (expectedSha256) {
    const actual = hash.digest('hex').toLowerCase();
    if (actual !== expectedSha256.toLowerCase()) {
      try { fs.unlinkSync(destPath); } catch (_) { /* ignore */ }
      throw new Error('Update verification failed: the downloaded installer checksum does not match the release manifest.');
    }
  }
  return destPath;
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

  return {
    async check() {
      log('update_check_started', { version });
      const now = Date.now();
      saveState(userDataDir, Object.assign(loadState(userDataDir), { lastCheck: now }));
      try {
        const releases = await fetchJson(feedUrl(repo), fetchImpl);
        const release = selectStableRelease(releases, version);
        if (!release) {
          log('update_none', { version });
          emitState({ status: 'uptodate', version, checkedAt: now });
          return { status: 'uptodate' };
        }
        const tag = String(release.tag_name || release.name || '');
        const { installer, manifest: manifestAsset } = selectInstallerAsset(release);
        let expectedSha256 = null;
        if (manifestAsset && assetDownloadUrl(manifestAsset)) {
          try {
            const manifestText = await fetchToFile(assetDownloadUrl(manifestAsset), path.join(userDataDir, 'release-manifest.json'), { fetchImpl });
            expectedSha256 = expectedInstallerSha256(parseManifest(fs.readFileSync(manifestText, 'utf8')));
          } catch (_) { expectedSha256 = null; }
        }
        const update = {
          version: tag,
          downloadUrl: installer ? assetDownloadUrl(installer) : '',
          size: installer ? Number(installer.size) || 0 : 0,
          expectedSha256,
          notes: String(release.body || '').slice(0, 4000)
        };
        log('update_available', { remote: tag, has_sha: !!expectedSha256 });
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
      log('update_download_started', { remote: update.version });
      const tmp = path.join(userDataDir, `LecturePack-${update.version}-Setup.exe.tmp`);
      const dest = path.join(userDataDir, `LecturePack-${update.version}-Setup.exe`);
      try {
        await fetchToFile(update.downloadUrl, tmp, {
          fetchImpl,
          onProgress: (received, total) => {
            if (onProgress) onProgress(received, total);
          },
          expectedSha256: update.expectedSha256 || undefined
        });
        fs.renameSync(tmp, dest);
        log('update_download_completed', { remote: update.version, file: dest, sha256: update.expectedSha256 ? 'verified' : 'unverified' });
        emitState({ status: 'downloaded', update, installerPath: dest });
        return dest;
      } catch (error) {
        log('update_download_failed', { error: error.message });
        emitState({ status: 'error', error: error.message });
        throw error;
      }
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
  parseManifest,
  sha256File,
  shouldAutoCheck,
  loadState,
  saveState,
  createUpdater,
  CHECK_INTERVAL_MS
};