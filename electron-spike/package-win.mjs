import { packager } from '@electron/packager';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const spikeRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(spikeRoot, '..');
const uiDir = path.join(repoRoot, 'app', 'ui');
const sidecar = path.join(spikeRoot, 'python-sidecar.py');
const packagedSidecar = path.join(spikeRoot, 'dist-sidecar', 'LecturePackSidecar');
const demoAssets = path.join(spikeRoot, 'assets');
const engine = path.join(repoRoot, 'lecturepack');
const icon = path.join(repoRoot, 'app', 'packaging', 'lecturepack.ico');
const outputDir = path.join(spikeRoot, 'dist');

for (const required of [uiDir, sidecar, packagedSidecar, demoAssets, engine, icon]) {
  if (!pathExists(required)) throw new Error(`Required Electron package input is missing: ${required}`);
}

function pathExists(candidate) {
  return fs.existsSync(candidate);
}

const output = await packager({
  dir: spikeRoot,
  name: 'LecturePack',
  appVersion: '0.9.0-beta.15',
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
    ProductVersion: '0.9.0-beta.15',
    FileVersion: '0.9.0.15'
  },
  // The repository keeps the old launcher and diagnostic modes as a fallback,
  // but the production candidate must not ship or expose them as entry points.
  ignore: (absolutePath) => {
    // electron-packager passes this callback a normalized path relative to
    // `dir` (for example `/assets/demo-lecture.mp4`), not the absolute path
    // named by the callback option. Strip the leading slash before matching.
    const relative = String(absolutePath).replaceAll('\\', '/').replace(/^\/+/, '');
    return [
      /^main\.js$/,
      /^preload\.js$/,
      /^launcher\.html$/,
      /^mock-workload\.js$/,
      /^python-mode\.js$/,
      /^static-theme\.js$/,
      /^package-sidecar\.mjs$/,
      /^package-win\.mjs$/,
      /^sidecar\.spec$/,
      /^assets(?:\/|$)/,
      /^dist(?:\/|$)/,
      /^dist-sidecar(?:\/|$)/,
      /^build-sidecar(?:\/|$)/,
      /^renderer-spike-results(?:\/|$)/,
      /^electron-production-results(?:\/|$)/,
      /(?:^|\/)node_modules(?:\/|$)/,
      /^package-lock\.json$/,
      /^python-sidecar\.py$/,
      /(?:^|\/)__pycache__(?:\/|$)/,
      /^\.git(?:\/|$)/,
      /^(?:final-|packaged-|transfer(?:\/|$))/
    ].some((pattern) => pattern.test(relative));
  },
  // Keep the disposable acceptance demo outside app.asar so the documented
  // packaged gate can pass it to the sidecar as resources/assets/demo-lecture.mp4.
  extraResource: [uiDir, sidecar, engine, packagedSidecar, demoAssets, icon]
});

console.log('Packaged LecturePack candidate:', output.join('\n'));
console.log('The executable is inside the generated win32-x64 directory.');
