'use strict';

const {
  app,
  BrowserWindow,
  ipcMain,
  shell
} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn, spawnSync } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..');
const MODES = new Set(['static', 'mock', 'python', 'migration']);
const MODE_LABELS = {
  static: 'Static page',
  mock: 'Mocked LecturePack',
  python: 'Existing Python engine',
  migration: 'Electron migration vertical slice'
};
const options = parseOptions(process.argv.slice(1));

let launcherWindow = null;
let activeSession = null;
let lastResultsDir = null;
let migrationRequestCounter = 0;

function clipped(value, limit) {
  const text = String(value == null ? '' : value);
  const max = limit || 512;
  return text.length <= max ? text : `${text.slice(0, max)}...`;
}

function parseOptions(argv) {
  const parsed = {};
  for (const arg of argv) {
    if (!arg.startsWith('--')) continue;
    const value = arg.slice(2);
    const equals = value.indexOf('=');
    if (equals < 0) parsed[value] = true;
    else parsed[value.slice(0, equals)] = value.slice(equals + 1);
  }
  return parsed;
}

function positiveSeconds(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return Math.min(parsed, 24 * 60 * 60);
}

function requestedMode() {
  const candidate = String(options.mode || process.env.LECTUREPACK_SPIKE_MODE || '').toLowerCase();
  return MODES.has(candidate) ? candidate : '';
}

function uiDirectory() {
  const candidates = [];
  if (app.isPackaged) {
    candidates.push(path.join(process.resourcesPath, 'lecturepack-ui'));
    candidates.push(path.join(process.resourcesPath, 'ui'));
    candidates.push(path.join(process.resourcesPath, 'app', 'ui'));
  }
  candidates.push(path.join(__dirname, 'vendor', 'ui'));
  candidates.push(path.join(REPO_ROOT, 'app', 'ui'));
  const found = candidates.find((candidate) => fs.existsSync(path.join(candidate, 'index.html')));
  if (!found) throw new Error(`LecturePack UI was not found. Checked: ${candidates.join(', ')}`);
  return found;
}

function makeLogger(mode) {
  const requested = options.results || path.join(REPO_ROOT, 'renderer-spike-results');
  const resultDir = path.resolve(requested);
  fs.mkdirSync(resultDir, { recursive: true });
  lastResultsDir = resultDir;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(resultDir, `${mode}-${stamp}.jsonl`);
  const write = (event, details = {}) => {
    const record = { at: new Date().toISOString(), mode, event, ...details };
    try {
      fs.appendFileSync(file, `${JSON.stringify(record)}\n`, 'utf8');
    } catch (error) {
      process.stderr.write(`[renderer-spike] log failure: ${error.message}\n`);
    }
  };
  write('session_started', { file });
  return { file, resultDir, write };
}

function staticDocument(uiDir) {
  const index = fs.readFileSync(path.join(uiDir, 'index.html'), 'utf8');
  const themeScript = fs.readFileSync(path.join(__dirname, 'static-theme.js'), 'utf8');
  const withoutScripts = index.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
  const base = `<base href="${pathToFileURL(`${uiDir}${path.sep}`).href}">`;
  return withoutScripts.replace(/<head>/i, `<head>${base}<script>${themeScript}</script>`);
}

function migrationDocument(uiDir) {
  const index = fs.readFileSync(path.join(uiDir, 'index.html'), 'utf8');
  const bridge = fs.readFileSync(path.join(__dirname, 'electron-bridge.js'), 'utf8');
  let document = index
    .replace(/<script\b[^>]*qrc:\/\/[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<script\s+src=["']bridge\.js["']\s*><\/script>/i, `<script>${bridge}</script>`);
  const base = `<base href="${pathToFileURL(`${uiDir}${path.sep}`).href}">`;
  document = document.replace(/<head>/i, `<head>${base}`);
  return document;
}

function writeDocument(document, prefix) {
  const tempDir = fs.mkdtempSync(path.join(app.getPath('temp'), prefix));
  const file = path.join(tempDir, 'index.html');
  fs.writeFileSync(file, document, 'utf8');
  return { tempDir, file };
}

function writeStaticDocument(uiDir) {
  return writeDocument(staticDocument(uiDir), 'lecturepack-renderer-spike-');
}

function writeMigrationDocument(uiDir) {
  return writeDocument(migrationDocument(uiDir), 'lecturepack-electron-migration-');
}

function injectFile(session, fileName) {
  const source = fs.readFileSync(path.join(__dirname, fileName), 'utf8');
  return session.window.webContents.executeJavaScript(source, true);
}

function sidecarScript() {
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'python-sidecar.py'), path.join(process.resourcesPath, 'lecturepack-spike', 'python-sidecar.py')]
    : [path.join(__dirname, 'python-sidecar.py')];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error(`Python sidecar was not found. Checked: ${candidates.join(', ')}`);
  return found;
}

function migrationDataDirectory() {
  const requested = options['data-dir'];
  return path.resolve(requested || path.join(app.getPath('userData'), 'electron-migration-data'));
}

function migrationDemoVideo() {
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'demo-lecture.mp4')]
    : [path.join(__dirname, 'assets', 'demo-lecture.mp4'), path.join(REPO_ROOT, 'app', 'assets', 'demo', 'demo_lecture.mp4')];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error(`Bundled migration demo was not found. Checked: ${candidates.join(', ')}`);
  return found;
}

function migrationExecutable() {
  if (!app.isPackaged) {
    const sourceCandidate = path.join(__dirname, 'dist-sidecar', 'LecturePackSidecar', 'LecturePackSidecar.exe');
    return fs.existsSync(sourceCandidate) ? sourceCandidate : '';
  }
  const candidates = [
    path.join(process.resourcesPath, 'LecturePackSidecar', 'LecturePackSidecar.exe'),
    path.join(process.resourcesPath, 'sidecar', 'LecturePackSidecar.exe'),
    path.join(process.resourcesPath, 'LecturePackSidecar.exe')
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || '';
}

function sendToPage(session, message) {
  if (session.closed || session.window.isDestroyed()) return;
  if (!session.pageReady) {
    session.pendingPageMessages.push(message);
    return;
  }
  const encoded = JSON.stringify(message);
  const target = session.mode === 'migration'
    ? 'window.__LECTUREPACK_ELECTRON__'
    : 'window.__LECTUREPACK_SPIKE__';
  session.window.webContents
    .executeJavaScript(`${target} && ${target}.onSidecar(${encoded});`, true)
    .catch((error) => session.logger.write('page_message_failed', { error: error.message }));
}

function flushPageMessages(session) {
  const pending = session.pendingPageMessages.splice(0);
  pending.forEach((message) => sendToPage(session, message));
}

function startResizeAndThemeStress(session) {
  if (session.mode === 'static' || options['no-stress']) return;

  const sizes = [
    [1360, 860],
    [1180, 780],
    [980, 720],
    [820, 680],
    [1440, 900],
    [1080, 760]
  ];
  let sizeIndex = 0;
  let themeIndex = 0;
  session.resizeTimer = setInterval(() => {
    if (session.window.isDestroyed()) return;
    const [width, height] = sizes[sizeIndex++ % sizes.length];
    session.window.setSize(width, height, true);
    session.logger.write('resize', { width, height });
  }, 1500);
  session.themeTimer = setInterval(() => {
    if (session.window.isDestroyed()) return;
    const theme = themeIndex++ % 2 === 0 ? 'dark' : 'light';
    const script = "(function(){var b=document.getElementById('btn-theme');if(b)b.click();return document.documentElement.dataset.theme;})()";
    session.window.webContents.executeJavaScript(script, true)
      .then((actual) => session.logger.write('theme_toggle', { requested: theme, actual }))
      .catch((error) => session.logger.write('theme_toggle_failed', { error: error.message }));
  }, 1800);

  const duration = positiveSeconds(options['duration-seconds'], 600);
  if (duration > 0) {
    session.durationTimer = setTimeout(() => {
      session.logger.write('stress_window_complete', { duration_seconds: duration });
      stopStressTimers(session);
    }, duration * 1000);
  }
  session.logger.write('stress_started', { duration_seconds: duration });
}

function stopStressTimers(session) {
  if (session.resizeTimer) clearInterval(session.resizeTimer);
  if (session.themeTimer) clearInterval(session.themeTimer);
  if (session.durationTimer) clearTimeout(session.durationTimer);
  if (session.metricsTimer) clearInterval(session.metricsTimer);
  session.resizeTimer = null;
  session.themeTimer = null;
  session.durationTimer = null;
  session.metricsTimer = null;
}

function startMetricsCapture(session) {
  if (session.mode === 'static') return;
  const capture = () => {
    if (session.window.isDestroyed()) return;
    const target = session.mode === 'migration'
      ? 'window.__LECTUREPACK_ELECTRON__ ? {connected:true} : {connected:false}'
      : 'window.__LECTUREPACK_SPIKE__ && window.__LECTUREPACK_SPIKE__.metrics';
    session.window.webContents
      .executeJavaScript(target, true)
      .then((metrics) => session.logger.write('page_metrics', { metrics }))
      .catch((error) => session.logger.write('page_metrics_failed', { error: error.message }));
  };
  capture();
  session.metricsTimer = setInterval(capture, 2000);
}

function consumeSidecarLines(session, chunk, handler) {
  session.sidecarBuffer += chunk.toString('utf8');
  let newline;
  while ((newline = session.sidecarBuffer.indexOf('\n')) >= 0) {
    const line = session.sidecarBuffer.slice(0, newline).trim();
    session.sidecarBuffer = session.sidecarBuffer.slice(newline + 1);
    if (!line) continue;
    try {
      const message = JSON.parse(line);
      session.logger.write('sidecar_message', { message });
      handler(message);
    } catch (error) {
      session.logger.write('sidecar_protocol_error', { line, error: error.message });
    }
  }
}

function attachSidecar(session, child, kind, description) {
  session.sidecar = child;
  session.sidecarKind = kind;
  session.sidecarBuffer = '';
  session.logger.write('sidecar_started', { kind, description, pid: child.pid });

  child.stdout.on('data', (chunk) => consumeSidecarLines(
    session,
    chunk,
    kind === 'migration'
      ? (message) => handleMigrationMessage(session, message)
      : (message) => sendToPage(session, message)
  ));
  child.stderr.on('data', (chunk) => {
    const text = chunk.toString('utf8').trim();
    if (text) session.logger.write('sidecar_stderr', { text });
  });
  child.on('error', (error) => {
    session.logger.write('sidecar_spawn_error', { error: error.message });
    sendToPage(session, { event: 'error', error: error.message });
  });
  child.on('close', (code, signal) => {
    session.logger.write('sidecar_exit', { code, signal });
    if (kind === 'migration') rejectMigrationCommands(session, `sidecar exited (${code ?? signal ?? 'unknown'})`);
    sendToPage(session, { event: 'exit', code, signal });
  });
}

function startPythonSidecar(session) {
  const python = options.python || process.env.LECTUREPACK_SPIKE_PYTHON || (process.platform === 'win32' ? 'python.exe' : 'python3');
  const script = sidecarScript();
  const child = spawn(python, [script, '--repo-root', REPO_ROOT], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    shell: false
  });
  attachSidecar(session, child, 'diagnostic-python', `${python} ${script}`);
}

function startMigrationSidecar(session) {
  const dataDir = migrationDataDirectory();
  const demoVideo = migrationDemoVideo();
  fs.mkdirSync(dataDir, { recursive: true });

  const executable = migrationExecutable();
  let command;
  let args;
  let cwd;
  if (executable) {
    command = executable;
    args = [
      '--resources-root', path.dirname(executable),
      '--data-dir', dataDir,
      '--demo-video', demoVideo
    ];
    cwd = path.dirname(executable);
  } else if (!app.isPackaged) {
    const python = options.python || path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
    const script = sidecarScript();
    if (!fs.existsSync(python)) throw new Error(`Locked project Python was not found: ${python}`);
    command = python;
    args = [
      script,
      '--repo-root', REPO_ROOT,
      '--resources-root', REPO_ROOT,
      '--data-dir', dataDir,
      '--demo-video', demoVideo
    ];
    cwd = REPO_ROOT;
  } else {
    throw new Error('Packaged LecturePackSidecar.exe was not found; customer Python is not a migration fallback.');
  }

  session.migrationDataDir = dataDir;
  session.migrationDemoVideo = demoVideo;
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    shell: false
  });
  attachSidecar(session, child, 'migration', command);
}

function sendMigrationRaw(session, message) {
  if (!session.sidecar || session.sidecar.killed || session.sidecar.stdin.destroyed) {
    throw new Error('Migration sidecar is not running.');
  }
  session.sidecar.stdin.write(`${JSON.stringify(message)}\n`);
}

function sendMigrationCommand(session, command, payload = {}) {
  if (!session || session.mode !== 'migration') return Promise.reject(new Error('No migration session is active.'));
  const requestId = `migration-${process.pid}-${++migrationRequestCounter}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      session.migrationPending.delete(requestId);
      reject(new Error(`Timed out waiting for sidecar command: ${command}`));
    }, 30000);
    session.migrationPending.set(requestId, { resolve, reject, timer, command });
    try {
      sendMigrationRaw(session, { request_id: requestId, command, payload });
    } catch (error) {
      clearTimeout(timer);
      session.migrationPending.delete(requestId);
      reject(error);
    }
  });
}

function rejectMigrationCommands(session, reason) {
  if (!session.migrationPending) return;
  for (const [requestId, pending] of session.migrationPending.entries()) {
    clearTimeout(pending.timer);
    pending.reject(new Error(reason));
    session.migrationPending.delete(requestId);
  }
}

function settleMigrationResponse(session, message) {
  const requestId = message.response_to;
  const pending = session.migrationPending && session.migrationPending.get(requestId);
  if (!pending) return;
  clearTimeout(pending.timer);
  session.migrationPending.delete(requestId);
  if (message.event === 'error' || message.ok === false) {
    pending.reject(new Error(message.error || `Sidecar command failed: ${pending.command}`));
  } else {
    pending.resolve(message);
  }
}

async function restoreMigrationJob(session, summary) {
  session.migrationJobId = summary.id;
  await sendMigrationCommand(session, 'get_job', { job_id: summary.id });
  await sendMigrationCommand(session, 'get_slides', { job_id: summary.id });
  await sendMigrationCommand(session, 'get_transcript', { job_id: summary.id });
  if (summary.status !== 'done') {
    await sendMigrationCommand(session, 'start_job', { job_id: summary.id, auto_export: true });
  }
}

async function bootstrapMigration(session) {
  if (session.migrationBootstrapped) return;
  session.migrationBootstrapped = true;
  try {
    const health = await sendMigrationCommand(session, 'health_check');
    if (!health.healthy) throw new Error(health.error || 'The packaged engine did not pass health_check.');
    const listed = await sendMigrationCommand(session, 'list_jobs');
    const jobs = Array.isArray(listed.jobs) ? listed.jobs : [];
    if (jobs.length) {
      await restoreMigrationJob(session, jobs[0]);
      return;
    }
    const imported = await sendMigrationCommand(session, 'import_video', {
      path: session.migrationDemoVideo,
      bundled_demo: true,
      title: 'Electron migration demo'
    });
    session.migrationJobId = imported.job_id;
    await sendMigrationCommand(session, 'start_job', {
      job_id: imported.job_id,
      auto_export: true,
      demo: true
    });
  } catch (error) {
    session.logger.write('migration_bootstrap_failed', { error: error.message });
    sendToPage(session, { event: 'error', error: error.message });
  }
}

function handleMigrationMessage(session, message) {
  if (!message || typeof message !== 'object') return;
  if (message.response_to) {
    settleMigrationResponse(session, message);
    if (message.event === 'error') sendToPage(session, message);
    return;
  }
  sendToPage(session, message);
  if (message.event === 'ready') void bootstrapMigration(session);
}

function terminateProcessTree(child, logger) {
  if (!child || child.exitCode !== null) return;
  const pid = child.pid;
  if (!pid) return;
  if (process.platform === 'win32') {
    const result = spawnSync('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
      windowsHide: true,
      shell: false,
      stdio: 'ignore'
    });
    logger.write('sidecar_tree_terminated', { pid, status: result.status, error: result.error?.message || '' });
  } else {
    try { child.kill('SIGTERM'); }
    catch (error) { logger.write('sidecar_terminate_failed', { pid, error: error.message }); }
  }
}

function stopSession(session) {
  if (!session || session.closed) return;
  session.closed = true;
  stopStressTimers(session);
  rejectMigrationCommands(session, 'Electron session closed.');
  if (session.sidecar && session.sidecar.exitCode === null) {
    try {
      session.sidecar.stdin.write(`${JSON.stringify({ command: 'shutdown' })}\n`);
      session.sidecar.stdin.end();
    } catch (_) { /* process is already closing */ }
    terminateProcessTree(session.sidecar, session.logger);
  }
  session.logger.write('session_closed');
}

function createModeWindow(mode) {
  const logger = makeLogger(mode);
  const uiDir = uiDirectory();
  const title = `LecturePack Renderer Spike - ${MODE_LABELS[mode]}`;
  const window = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 640,
    minHeight: 480,
    show: true,
    title,
    backgroundColor: '#16191F',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });
  const session = {
    mode,
    window,
    logger,
    uiDir,
    pageReady: false,
    pendingPageMessages: [],
    sidecar: null,
    sidecarKind: '',
    sidecarBuffer: '',
    resizeTimer: null,
    themeTimer: null,
    durationTimer: null,
    metricsTimer: null,
    closed: false,
    migrationPending: new Map(),
    migrationBootstrapped: false,
    migrationJobId: ''
  };
  activeSession = session;

  window.webContents.on('did-finish-load', async () => {
    session.pageReady = true;
    logger.write('page_ready', { uiDir });
    try {
      if (mode === 'mock') await injectFile(session, 'mock-workload.js');
      if (mode === 'python') {
        await injectFile(session, 'python-mode.js');
        startPythonSidecar(session);
      }
      if (mode === 'migration') startMigrationSidecar(session);
      flushPageMessages(session);
      startResizeAndThemeStress(session);
      startMetricsCapture(session);
    } catch (error) {
      logger.write('page_bootstrap_failed', { error: error.message });
      sendToPage(session, { event: 'error', error: error.message });
    }
  });
  window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    logger.write('page_load_failed', { errorCode, errorDescription, validatedURL });
  });
  window.webContents.on('render-process-gone', (_event, details) => {
    logger.write('render_process_gone', details);
  });
  window.webContents.on('unresponsive', () => logger.write('renderer_unresponsive'));
  window.webContents.on('responsive', () => logger.write('renderer_responsive'));
  window.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    logger.write('console', { level, message: clipped(message), line, sourceId: clipped(sourceId, 240) });
  });
  window.on('closed', () => {
    stopSession(session);
    if (activeSession === session) activeSession = null;
  });

  if (mode === 'static') {
    const staticFile = writeStaticDocument(uiDir);
    session.documentTempDir = staticFile.tempDir;
    logger.write('static_document_written', { file: staticFile.file });
    window.loadFile(staticFile.file);
  } else if (mode === 'migration') {
    const migrationFile = writeMigrationDocument(uiDir);
    session.documentTempDir = migrationFile.tempDir;
    logger.write('migration_document_written', { file: migrationFile.file });
    window.loadFile(migrationFile.file, { query: 'spike=migration' });
  } else {
    window.loadFile(path.join(uiDir, 'index.html'), { query: `spike=${mode}` });
  }
  return session;
}

function launchMode(mode) {
  if (!MODES.has(mode)) return;
  if (activeSession && !activeSession.window.isDestroyed()) {
    activeSession.window.focus();
    return;
  }
  if (launcherWindow && !launcherWindow.isDestroyed()) {
    launcherWindow.close();
    launcherWindow = null;
  }
  createModeWindow(mode);
}

function createLauncher() {
  launcherWindow = new BrowserWindow({
    width: 760,
    height: 700,
    resizable: false,
    title: 'LecturePack Electron migration',
    backgroundColor: '#16191F',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });
  launcherWindow.loadFile(path.join(__dirname, 'launcher.html'));
  launcherWindow.on('closed', () => { launcherWindow = null; });
}

ipcMain.on('lecturepack-spike:choose-mode', (_event, mode) => launchMode(String(mode)));
ipcMain.on('lecturepack-spike:open-results', () => {
  if (!lastResultsDir) return;
  shell.openPath(lastResultsDir).catch(() => {});
});
ipcMain.handle('lecturepack-migration:command', (_event, command, payload) => {
  if (!activeSession || activeSession.mode !== 'migration') {
    throw new Error('The Electron migration session is not active.');
  }
  return sendMigrationCommand(activeSession, String(command || ''), payload && typeof payload === 'object' ? payload : {});
});

app.whenReady().then(() => {
  const mode = requestedMode();
  if (mode) createModeWindow(mode);
  else createLauncher();
  const quitAfter = positiveSeconds(options['quit-after-seconds'], 0);
  if (quitAfter > 0) {
    setTimeout(() => {
      const session = activeSession;
      if (session) {
        session.logger.write('quit_requested');
        stopSession(session);
      }
      app.quit();
    }, quitAfter * 1000);
  }
});

app.on('before-quit', () => stopSession(activeSession));
app.on('window-all-closed', () => app.quit());
