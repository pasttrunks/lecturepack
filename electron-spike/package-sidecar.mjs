import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const spikeRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(spikeRoot, '..');
const buildRoot = process.env.LECTUREPACK_BUILD_ROOT
  ? path.resolve(process.env.LECTUREPACK_BUILD_ROOT)
  : spikeRoot;
const pyinstaller = process.env.LECTUREPACK_PYINSTALLER
  ? path.resolve(process.env.LECTUREPACK_PYINSTALLER)
  : path.join(repoRoot, '.venv', 'Scripts', 'pyinstaller.exe');
const spec = path.join(spikeRoot, 'sidecar.spec');
const distPath = path.join(buildRoot, 'dist-sidecar');
const workPath = path.join(buildRoot, 'build-sidecar');
const packagedSidecar = path.join(distPath, 'LecturePackSidecar');

fs.mkdirSync(buildRoot, { recursive: true });

for (const file of [pyinstaller, spec]) {
  if (!fs.existsSync(file)) throw new Error(`Required sidecar build input is missing: ${file}`);
}

function pruneHeadlessQtPayload() {
  // The frozen sidecar uses QCoreApplication/QThread/QProcess only. It never
  // creates a Qt GUI or localizes Qt-owned widgets, so these two PyInstaller
  // hook payloads cannot be reached by the production sidecar.
  for (const relative of [
    path.join('_internal', 'PySide6', 'opengl32sw.dll'),
    path.join('_internal', 'PySide6', 'translations')
  ]) {
    const target = path.resolve(packagedSidecar, relative);
    if (!target.startsWith(`${path.resolve(packagedSidecar)}${path.sep}`)) {
      throw new Error(`Refusing to prune path outside packaged sidecar: ${target}`);
    }
    fs.rmSync(target, { recursive: true, force: true });
  }
}

const pyinstallerArgs = ['--noconfirm'];
if (process.env.LECTUREPACK_CLEAN_BUILD === '1' || process.env.CLEAN_BUILD === '1') {
  pyinstallerArgs.push('--clean');
}
pyinstallerArgs.push('--distpath', distPath, '--workpath', workPath, spec);

const child = spawn(pyinstaller, pyinstallerArgs, {
  cwd: spikeRoot,
  stdio: 'inherit',
  windowsHide: true,
  shell: false
});

child.on('error', (error) => {
  console.error(`Could not launch PyInstaller: ${error.message}`);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`PyInstaller exited via ${signal}`);
    process.exitCode = 1;
  } else {
    process.exitCode = code ?? 1;
    if (process.exitCode === 0) pruneHeadlessQtPayload();
  }
});
