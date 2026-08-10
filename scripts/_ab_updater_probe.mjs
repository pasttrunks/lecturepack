/* Drive the PRODUCTION updater against a controlled local release feed.
 *
 * Helper for scripts/updater_ab_acceptance.py. It serves the real B installer
 * and its real release manifest over 127.0.0.1 and asks electron-spike/
 * updater.js -- the shipping module, not a copy -- to select, verify and
 * download the update. Anything it proves is a property of production code.
 *
 * argv: <updater.js> <newSetup> <newManifest> <dataDir> <fromVersion>
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [updaterPath, newSetup, newManifest, dataDir, fromVersion] = process.argv.slice(2);
const require = createRequire(pathToFileURL(updaterPath));
const updaterModule = require(updaterPath);

const manifest = JSON.parse(fs.readFileSync(newManifest, 'utf8'));
const toVersion = manifest.version;
const installerName = manifest.installers[0].filename;
const size = fs.statSync(newSetup).size;

const server = http.createServer((req, res) => {
  const base = `http://127.0.0.1:${server.address().port}`;
  if (req.url.startsWith('/releases')) {
    res.setHeader('content-type', 'application/json');
    return res.end(JSON.stringify([
      // An older stable release, a draft and a prerelease must all be ignored.
      { tag_name: `v${fromVersion}`, draft: false, prerelease: false,
        assets: [{ name: `LecturePack-${fromVersion}-Setup.exe` }] },
      { tag_name: 'v9.9.9', draft: true, prerelease: false,
        assets: [{ name: 'LecturePack-9.9.9-Setup.exe' }] },
      { tag_name: `v${toVersion}-beta.1`, draft: false, prerelease: true,
        assets: [{ name: `LecturePack-${toVersion}-beta.1-Setup.exe` }] },
      { tag_name: `v${toVersion}`, draft: false, prerelease: false,
        html_url: `https://example.invalid/releases/tag/v${toVersion}`,
        body: 'controlled A->B acceptance feed',
        assets: [
          { name: installerName, size, browser_download_url: `${base}/installer` },
          { name: `LecturePack-${toVersion}-release-manifest.json`,
            browser_download_url: `${base}/manifest` }
        ] }
    ]));
  }
  if (req.url === '/manifest') {
    res.setHeader('content-type', 'application/json');
    return res.end(JSON.stringify(manifest));
  }
  if (req.url === '/installer') {
    res.setHeader('content-length', String(size));
    return fs.createReadStream(newSetup).pipe(res);
  }
  res.statusCode = 404;
  res.end();
});

server.listen(0, '127.0.0.1', async () => {
  const port = server.address().port;
  const out = { from: fromVersion, to: toVersion };
  try {
    const updater = updaterModule.createUpdater({
      version: fromVersion,
      repo: 'controlled/feed',
      userDataDir: dataDir,
      fetchImpl: (url, options) => fetch(
        String(url).replace(
          'https://api.github.com/repos/controlled/feed/releases?per_page=30',
          `http://127.0.0.1:${port}/releases`
        ), options)
    });

    const checked = await updater.check();
    out.status = checked.status;
    out.selected_newer = checked.status === 'available'
      && String(checked.update?.version || '').replace(/^v/, '') === toVersion;
    out.manifest_verified = /^[0-9a-f]{64}$/.test(String(checked.update?.expectedSha256 || ''));
    out.expected_sha256 = checked.update?.expectedSha256 || null;

    if (out.selected_newer && out.manifest_verified) {
      // download() refuses outright without a manifest-verified digest, so a
      // returned path is itself proof the digest matched the bytes.
      out.installer_path = await updater.download(checked.update);
      out.downloaded_bytes = fs.statSync(out.installer_path).size;
    }
    // Nothing may be left behind other than the verified installer.
    out.leftover_temp_files = fs.readdirSync(dataDir).filter((f) => f.endsWith('.tmp'));
  } catch (error) {
    out.error = String(error && error.message || error);
  } finally {
    server.close();
  }
  process.stdout.write(JSON.stringify(out, null, 1));
});
