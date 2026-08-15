import { packager } from '@electron/packager';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const spikeRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(spikeRoot, '..');
const buildRoot = process.env.LECTUREPACK_BUILD_ROOT
  ? path.resolve(process.env.LECTUREPACK_BUILD_ROOT)
  : spikeRoot;
const uiDir = path.join(repoRoot, 'app', 'ui');
const guidedDemoAssets = path.join(repoRoot, 'app', 'assets', 'demo');
const packagedSidecar = path.join(buildRoot, 'dist-sidecar', 'LecturePackSidecar');
const demoAssets = path.join(spikeRoot, 'assets');
const icon = path.join(repoRoot, 'app', 'packaging', 'lecturepack.ico');
const license = path.join(repoRoot, 'LICENSE');
const outputDir = path.join(buildRoot, 'dist');
const productionAsarFiles = new Set([
  'package.json',
  'production-main.js',
  'production-preload.js',
  'electron-bridge.js',
  'import-path.js',
  'updater.js'
]);

for (const required of [uiDir, guidedDemoAssets, packagedSidecar, demoAssets, icon, license]) {
  if (!pathExists(required)) throw new Error(`Required Electron package input is missing: ${required}`);
}

fs.mkdirSync(buildRoot, { recursive: true });

function pathExists(candidate) {
  return fs.existsSync(candidate);
}

// Single source of truth for the packaged product version.
//
// These were previously hardcoded to '2.0.0'. That happened to be correct for
// exactly one release: any version bump shipped a LecturePack.exe whose
// Windows version resource still claimed the old version, while every other
// surface said the new one. Read package.json instead so the executable can
// never disagree with the release it belongs to.
const appVersion = JSON.parse(
  fs.readFileSync(path.join(spikeRoot, 'package.json'), 'utf8')
).version;
if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(String(appVersion || ''))) {
  throw new Error(`electron-spike/package.json has no usable version: ${appVersion}`);
}
// The Windows FileVersion resource is a four-part numeric field, so a
// prerelease suffix cannot appear in it.
const fileVersion = `${String(appVersion).split('-')[0]}.0`;

const output = await packager({
  dir: spikeRoot,
  name: 'LecturePack',
  appVersion,
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
    ProductVersion: appVersion,
    FileVersion: fileVersion
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
  extraResource: [uiDir, packagedSidecar, demoAssets, icon, license],
  afterCopyExtraResources: [async ({ buildPath }) => {
    // index.html is copied to resources/ui and resolves its self-contained
    // walkthrough from ../assets/demo/. Electron Packager flattens every
    // extraResource to its basename, so adding app/assets/demo directly would
    // incorrectly produce resources/demo/. Copy it to the exact renderer
    // contract instead. The live processing video already ships once at
    // resources/assets/demo-lecture.mp4 and is deliberately excluded here.
    const destination = path.join(buildPath, 'resources', 'assets', 'demo');
    await fs.promises.mkdir(path.dirname(destination), { recursive: true });
    await fs.promises.cp(guidedDemoAssets, destination, {
      recursive: true,
      filter: (source) => path.basename(source) !== 'demo_lecture.mp4'
    });
  }]
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
