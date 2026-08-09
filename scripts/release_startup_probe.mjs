/* Probe the real packaged terminal-startup UI through Chromium's local CDP.
 *
 * The caller supplies a disposable candidate and any desired broken runtime
 * mutation. This script launches that copy, waits at most 30 seconds, and
 * proves that the visible renderer exposes the actionable failure contract.
 * It uses only Node built-ins and the WebSocket implementation bundled with
 * supported Node releases; it is a development release gate, not shipped UI.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

function options(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith('--')) continue;
    const key = item.slice(2);
    result[key] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return result;
}

const args = options(process.argv.slice(2));
const executable = path.resolve(String(args.exe || ''));
const resultsDir = path.resolve(String(args.results || ''));
const dataDir = path.resolve(String(args.data || ''));
const expected = String(args.expected || '');
const retryRestore = args['retry-restore'] ? path.resolve(String(args['retry-restore'])) : '';
const retryTarget = args['retry-target'] ? path.resolve(String(args['retry-target'])) : '';
const timeoutMs = Math.min(30_000, Math.max(1_000, Number(args.timeout || 30_000)));
const port = Number(args.port || (9300 + Math.floor(Math.random() * 500)));

if (!fs.existsSync(executable) || !resultsDir || !dataDir) {
  throw new Error('Usage: --exe PATH --results PATH --data PATH [--expected TEXT]');
}
fs.mkdirSync(resultsDir, { recursive: true });
fs.mkdirSync(path.dirname(dataDir), { recursive: true });

const child = spawn(executable, [
  `--remote-debugging-port=${port}`,
  '--results', resultsDir,
  '--data-dir', dataDir,
], {
  cwd: path.dirname(executable),
  env: { ...process.env, ELECTRON_ENABLE_LOGGING: '0' },
  stdio: 'ignore',
  windowsHide: true,
  shell: false,
});

const started = Date.now();
let socket;
let sequence = 0;
const pending = new Map();

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pageTarget() {
  const response = await fetch(`http://127.0.0.1:${port}/json/list`);
  if (!response.ok) return null;
  const targets = await response.json();
  return targets.find((item) => item.type === 'page' && item.webSocketDebuggerUrl) || null;
}

async function waitForTarget() {
  while (Date.now() - started < timeoutMs) {
    if (child.exitCode !== null) throw new Error(`LecturePack exited early with code ${child.exitCode}`);
    try {
      const target = await pageTarget();
      if (target) return target;
    } catch (_) { /* Chromium has not opened its local endpoint yet. */ }
    await delay(100);
  }
  throw new Error('No renderer target appeared before the startup deadline');
}

function connect(url) {
  return new Promise((resolve, reject) => {
    socket = new WebSocket(url);
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', () => reject(new Error('Could not connect to renderer CDP')), { once: true });
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !pending.has(message.id)) return;
      const callback = pending.get(message.id);
      pending.delete(message.id);
      callback(message);
    });
  });
}

function cdp(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, (message) => message.error ? reject(new Error(message.error.message)) : resolve(message.result));
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function inspect() {
  const expression = `(() => {
    const visible = (element) => !!element && !element.hidden && getComputedStyle(element).display !== 'none';
    const panel = document.querySelector('[data-runtime-state="startup_failed"]');
    const title = document.getElementById('startup-failure-title');
    const detail = document.getElementById('startup-failure-detail');
    const technical = document.getElementById('startup-failure-technical');
    return {
      state: visible(panel) ? 'startup_failed' : 'waiting',
      title: title ? title.textContent.trim() : '',
      detail: detail ? detail.textContent.trim() : '',
      technical: technical ? technical.textContent.trim() : '',
      retry: visible(document.getElementById('btn-startup-retry')),
      copyDiagnostics: visible(document.getElementById('btn-startup-copy')),
      openLogs: visible(document.getElementById('btn-startup-open-logs')),
    };
  })()`;
  const result = await cdp('Runtime.evaluate', { expression, returnByValue: true });
  return result.result.value;
}

let evidence = null;
let failure = '';
let retry = null;
try {
  const target = await waitForTarget();
  await connect(target.webSocketDebuggerUrl);
  await cdp('Runtime.enable');
  while (Date.now() - started < timeoutMs) {
    evidence = await inspect();
    if (evidence.state === 'startup_failed') break;
    await delay(100);
  }
  const searchable = `${evidence && evidence.title || ''} ${evidence && evidence.detail || ''} ${evidence && evidence.technical || ''}`;
  if (!evidence || evidence.state !== 'startup_failed') failure = 'terminal startup state was not visible';
  else if (!evidence.retry || !evidence.copyDiagnostics || !evidence.openLogs) failure = 'one or more recovery actions were not visible';
  else if (expected && !searchable.toLowerCase().includes(expected.toLowerCase())) failure = `expected failure text was absent: ${expected}`;
  if (!failure && retryRestore && retryTarget) {
    const retryStarted = Date.now();
    fs.renameSync(retryRestore, retryTarget);
    await cdp('Runtime.evaluate', {
      expression: `document.getElementById('btn-startup-retry').click()`,
      returnByValue: true,
    });
    let startupComplete = false;
    while (Date.now() - retryStarted < timeoutMs) {
      const logs = fs.readdirSync(resultsDir).filter((name) => /^production-.*\.jsonl$/i.test(name));
      startupComplete = logs.some((name) => fs.readFileSync(path.join(resultsDir, name), 'utf8').includes('"event":"startup_complete"'));
      if (startupComplete) break;
      await delay(100);
    }
    retry = { clicked: true, startup_complete: startupComplete, elapsed_ms: Date.now() - retryStarted };
    if (!startupComplete) failure = 'Retry did not complete startup before the deadline';
  }
} catch (error) {
  failure = error.message || String(error);
} finally {
  try { if (socket) socket.close(); } catch (_) { /* force cleanup below */ }
  if (child.exitCode === null) {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore', shell: false });
  }
}

const result = {
  passed: !failure,
  elapsed_ms: Date.now() - started,
  expected,
  evidence,
  retry,
  failure,
  results_dir: resultsDir,
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
if (failure) process.exitCode = 1;
