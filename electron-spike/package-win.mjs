import { packager } from '@electron/packager';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const spikeRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(spikeRoot, '..');
const uiDir = path.join(repoRoot, 'app', 'ui');
const packagedSidecar = path.join(spikeRoot, 'dist-sidecar', 'LecturePackSidecar');
const demoAssets = path.join(spikeRoot, 'assets');
const icon = path.join(repoRoot, 'app', 'packaging', 'lecturepack.ico');
const outputDir = path.join(spikeRoot, 'dist');
const productionAsarFiles = new Set([
  'package.json',
  'production-main.js',
  'production-preload.js',
  'electron-bridge.js',
  'import-path.js'
]);

for (const required of [uiDir, packagedSidecar, demoAssets, icon]) {
  if (!pathExists(required)) throw new Error(`Required Electron package input is missing: ${required}`);
}

function pathExists(candidate) {
  return fs.existsSync(candidate);
}

const output = await packager({
  dir: spikeRoot,
  name: 'LecturePack',
  appVersion: '2.0.0',
  platform: 'win32',
  arch: 'x64',
  out: outputDir,
  asar: true,
  prune: true,
  overwrite: true,
  icon,
  win32metadata: {
    CompanyName: 'LecturePack',
    FileDescription: 'LecturePack local lecture study workspace',
    InternalName: 'LecturePack',
    OriginalFilename: 'LecturePack.exe',
    ProductName: 'LecturePack',
    ProductVersion: '2.0.0',
    FileVersion: '2.0.0.0'
  },
  // The repository keeps the old launcher and diagnostic modes as a fallback,
  // but the production candidate must not ship or expose them as entry points.
  ignore: (absolutePath) => {
    // electron-packager passes this callback a normalized path relative to
    // `dir` (for example `/assets/demo-lecture.mp4`), not the absolute path
    // named by the callback option. Strip the leading slash before matching.
    const relative = String(absolutePath).replaceAll('\\', '/').replace(/^\/+/, '');
    if (!relative) return false;
    return !productionAsarFiles.has(relative);
  },
  // Keep the disposable acceptance demo outside app.asar so the documented
  // packaged gate can pass it to the sidecar as resources/assets/demo-lecture.mp4.
  extraResource: [uiDir, packagedSidecar, demoAssets, icon]
});

// LecturePack's production UI is English-only. Electron Packager copies every
// Chromium locale by default; retain both supported English variants and drop
// only the unreachable locale packs from the generated candidate.
const retainedLocales = new Set(['en-US.pak', 'en-GB.pak']);
for (const candidate of output) {
  const localesDir = path.join(candidate, 'locales');
  for (const entry of fs.readdirSync(localesDir, { withFileTypes: true })) {
    if (entry.isFile() && !retainedLocales.has(entry.name)) {
      fs.rmSync(path.join(localesDir, entry.name));
    }
  }
}

console.log('Packaged LecturePack candidate:', output.join('\n'));
console.log('The executable is inside the generated win32-x64 directory.');
