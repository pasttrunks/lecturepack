import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const spikeRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(spikeRoot, '..');
const pyinstaller = path.join(repoRoot, '.venv', 'Scripts', 'pyinstaller.exe');
const spec = path.join(spikeRoot, 'sidecar.spec');
const distPath = path.join(spikeRoot, 'dist-sidecar');
const workPath = path.join(spikeRoot, 'build-sidecar');

for (const file of [pyinstaller, spec]) {
  if (!fs.existsSync(file)) throw new Error(`Required sidecar build input is missing: ${file}`);
}

const child = spawn(pyinstaller, [
  '--noconfirm',
  '--clean',
  '--distpath', distPath,
  '--workpath', workPath,
  spec
], {
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
  }
});
