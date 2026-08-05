'use strict';

const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  Notification,
  shell
} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn, spawnSync } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..');
const packageInfo = require('./package.json');
const PRODUCT_NAME = packageInfo.productName || 'LecturePack';
const PRODUCT_VERSION = packageInfo.version || '0.9.0-beta.15';
const APP_USER_MODEL_ID = 'LecturePack.LecturePack';
const options = parseOptions(process.argv.slice(1));
const hasSingleInstanceLock = app.requestSingleInstanceLock();

app.setName(PRODUCT_NAME);
app.setVersion(PRODUCT_VERSION);
if (process.platform === 'win32') app.setAppUserModelId(APP_USER_MODEL_ID);

let activeSession = null;
let lastResultsDir = null;
let requestCounter = 0;
let quitPromise = null;

function parseOptions(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith('--')) continue;
    const value = arg.slice(2);
    const equals = value.indexOf('=');
    if (equals >= 0) {
      parsed[value.slice(0, equals)] = value.slice(equals + 1);
      continue;
    }
    const next = argv[index + 1];
    if (next && !next.startsWith('--')) {
      parsed[value] = next;
      index += 1;
    } else {
      parsed[value] = true;
    }
  }
  return parsed;
}

function pathExists(candidate) {
  try { return fs.existsSync(candidate); }
  catch (_) { return false; }
}

function uiDirectory() {
  const candidates = app.isPackaged
    ? [
      path.join(process.resourcesPath, 'lecturepack-ui'),
      path.join(process.resourcesPath, 'ui'),
      path.join(process.resourcesPath, 'app', 'ui')
    ]
    : [path.join(REPO_ROOT, 'app', 'ui')];
  const found = candidates.find((candidate) => pathExists(path.join(candidate, 'index.html')));
  if (!found) throw new Error(`LecturePack UI was not found. Checked: ${candidates.join(', ')}`);
  return found;
}

function productionDocument(uiDir) {
  const index = fs.readFileSync(path.join(uiDir, 'index.html'), 'utf8');
  const bridge = fs.readFileSync(path.join(__dirname, 'electron-bridge.js'), 'utf8');
  const productionScope = `
    <style id="lecturepack-production-scope">
      #btn-paste-link, #btn-show-empty, #btn-save, #update-badge {
        display: none !important;
      }
    </style>`;
  let document = index
    .replace(/<script\b[^>]*qrc:\/\/[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<script\s+src=["']bridge\.js["']\s*><\/script>/i, `<script>${bridge}</script>`);
  const base = `<base href="${pathToFileURL(`${uiDir}${path.sep}`).href}">`;
  document = document.replace(/<head>/i, `<head>${base}${productionScope}`);
  return document;
}

function writeProductionDocument(uiDir) {
  const tempDir = fs.mkdtempSync(path.join(app.getPath('temp'), 'lecturepack-production-'));
  const file = path.join(tempDir, 'index.html');
  fs.writeFileSync(file, productionDocument(uiDir), 'utf8');
  return { tempDir, file };
}

function makeLogger() {
  const requested = options.results || (
    app.isPackaged
      ? path.join(app.getPath('userData'), 'results')
      : path.join(REPO_ROOT, 'electron-production-results')
  );
  const resultDir = path.resolve(requested);
  fs.mkdirSync(resultDir, { recursive: true });
  lastResultsDir = resultDir;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(resultDir, `production-${stamp}.jsonl`);
  const write = (event, details = {}) => {
    const record = { at: new Date().toISOString(), event, ...details };
    try {
      fs.appendFileSync(file, `${JSON.stringify(record)}\n`, 'utf8');
    } catch (error) {
      process.stderr.write(`[lecturepack-production] log failure: ${error.message}\n`);
    }
  };
  write('session_started', { file });
  return { file, resultDir, write };
}

function dataDirectory() {
  const requested = options['data-dir'] || process.env.LECTUREPACK_DATA_DIR;
  return path.resolve(requested || path.join(app.getPath('home'), 'LecturePackData'));
}

function applicationIcon() {
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'lecturepack.ico')]
    : [path.join(REPO_ROOT, 'app', 'packaging', 'lecturepack.ico')];
  return candidates.find(pathExists) || undefined;
}

function sidecarScript() {
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'python-sidecar.py')]
    : [path.join(__dirname, 'python-sidecar.py')];
  const found = candidates.find(pathExists);
  if (!found) throw new Error(`Python sidecar script was not found. Checked: ${candidates.join(', ')}`);
  return found;
}

function sidecarExecutable() {
  if (!app.isPackaged) {
    const sourceCandidate = path.join(__dirname, 'dist-sidecar', 'LecturePackSidecar', 'LecturePackSidecar.exe');
    return pathExists(sourceCandidate) ? sourceCandidate : '';
  }
  const candidates = [
    path.join(process.resourcesPath, 'LecturePackSidecar', 'LecturePackSidecar.exe'),
    path.join(process.resourcesPath, 'sidecar', 'LecturePackSidecar.exe'),
    path.join(process.resourcesPath, 'LecturePackSidecar.exe')
  ];
  return candidates.find(pathExists) || '';
}

function sendToPage(session, message) {
  if (!session || session.closed || session.window.isDestroyed()) return;
  if (!session.pageReady) {
    session.pendingPageMessages.push(message);
    return;
  }
  const encoded = JSON.stringify(message);
  session.window.webContents
    .executeJavaScript(`window.__LECTUREPACK_ELECTRON__ && window.__LECTUREPACK_ELECTRON__.onSidecar(${encoded});`, true)
    .catch((error) => session.logger.write('page_message_failed', { error: error.message }));
}

function flushPageMessages(session) {
  const pending = session.pendingPageMessages.splice(0);
  pending.forEach((message) => sendToPage(session, message));
}

function rejectPending(session, reason) {
  for (const [requestId, pending] of session.pending.entries()) {
    clearTimeout(pending.timer);
    pending.reject(new Error(reason));
    session.pending.delete(requestId);
  }
}

function settleResponse(session, message) {
  const requestId = message.response_to;
  const pending = session.pending.get(requestId);
  if (!pending) return;
  clearTimeout(pending.timer);
  session.pending.delete(requestId);
  if (message.event === 'error' || message.ok === false) {
    pending.reject(new Error(message.error || `Sidecar command failed: ${pending.command}`));
  } else {
    pending.resolve(message);
  }
}

function sendRaw(session, message) {
  if (!session.sidecar || session.sidecar.exitCode !== null || session.sidecar.stdin.destroyed) {
    throw new Error('The LecturePack sidecar is not running.');
  }
  session.sidecar.stdin.write(`${JSON.stringify(message)}\n`);
}

function sendCommand(session, command, payload = {}) {
  if (!session || session.closed) return Promise.reject(new Error('The LecturePack session is closed.'));
  const requestId = `production-${process.pid}-${++requestCounter}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      session.pending.delete(requestId);
      reject(new Error(`Timed out waiting for sidecar command: ${command}`));
    }, 60000);
    session.pending.set(requestId, { resolve, reject, timer, command });
    try {
      sendRaw(session, { request_id: requestId, command, payload });
    } catch (error) {
      clearTimeout(timer);
      session.pending.delete(requestId);
      reject(error);
    }
  });
}

function handleSidecarMessage(session, message) {
  if (!message || typeof message !== 'object') return;
  session.logger.write('sidecar_message', {
    event: message.event || '',
    command: message.command || '',
    response_to: message.response_to || ''
  });
  if (message.event === 'active_job') session.activeJobId = message.id || '';
  if (message.response_to) {
    settleResponse(session, message);
    if (message.event === 'error') sendToPage(session, message);
    return;
  }
  sendToPage(session, message);
  if (message.event === 'ready') void bootstrap(session);
}

function attachSidecar(session, child, command) {
  session.sidecar = child;
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    session.sidecarBuffer += chunk;
    const lines = session.sidecarBuffer.split(/\r?\n/);
    session.sidecarBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        handleSidecarMessage(session, JSON.parse(line));
      } catch (error) {
        session.logger.write('sidecar_protocol_error', { error: error.message, line: line.slice(0, 1000) });
        sendToPage(session, { event: 'error', error: `Invalid sidecar JSONL: ${error.message}` });
      }
    }
  });
  child.stderr.on('data', (chunk) => {
    const text = chunk.trim();
    if (text) {
      session.logger.write('sidecar_stderr', { text: text.slice(0, 2000) });
      sendToPage(session, { event: 'log_line', tag: '[sidecar]', color: 'var(--muted)', text });
    }
  });
  child.on('error', (error) => {
    session.logger.write('sidecar_spawn_error', { command, error: error.message });
    sendToPage(session, { event: 'error', error: error.message });
  });
  child.on('close', (code, signal) => {
    session.logger.write('sidecar_exit', { code, signal });
    rejectPending(session, `Sidecar exited (${code ?? signal ?? 'unknown'}).`);
    sendToPage(session, { event: 'exit', code, signal });
  });
}

function startSidecar(session) {
  const dataDir = dataDirectory();
  fs.mkdirSync(dataDir, { recursive: true });

  const executable = sidecarExecutable();
  let command;
  let args;
  let cwd;
  if (executable) {
    command = executable;
    args = [
      '--resources-root', path.dirname(executable),
      '--data-dir', dataDir
    ];
    const bundledDemo = path.join(process.resourcesPath, 'assets', 'demo-lecture.mp4');
    if (pathExists(bundledDemo)) args.push('--demo-video', bundledDemo);
    cwd = path.dirname(executable);
  } else if (!app.isPackaged) {
    const python = options.python || path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
    const script = sidecarScript();
    if (!pathExists(python)) throw new Error(`Locked project Python was not found: ${python}`);
    command = python;
    args = [
      script,
      '--repo-root', REPO_ROOT,
      '--resources-root', REPO_ROOT,
      '--data-dir', dataDir
    ];
    cwd = REPO_ROOT;
  } else {
    throw new Error('Packaged LecturePackSidecar.exe was not found; customer Python is not a fallback.');
  }

  session.dataDir = dataDir;
  session.logger.write('sidecar_starting', { command, args, data_dir: dataDir });
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    shell: false
  });
  attachSidecar(session, child, command);
}

async function bootstrap(session) {
  if (session.bootstrapped || session.closed) return;
  session.bootstrapped = true;
  try {
    const health = await sendCommand(session, 'health_check');
    if (!health.healthy) throw new Error(health.error || 'The packaged LecturePack engine failed health_check.');
    const listed = await sendCommand(session, 'list_jobs');
    const jobs = Array.isArray(listed.jobs) ? listed.jobs : [];
    if (!jobs.length) return;
    // The sidecar returns newest-first. Restore the newest completed job when
    // possible; interrupted/running jobs remain visible for an explicit retry.
    const preferred = jobs.find((job) => job.status === 'done') || jobs[0];
    await restoreJob(session, preferred);
  } catch (error) {
    session.logger.write('bootstrap_failed', { error: error.message });
    sendToPage(session, { event: 'error', kind: 'bootstrap', error: error.message });
  }
}

async function restoreJob(session, summary) {
  session.activeJobId = summary.id || '';
  await sendCommand(session, 'get_job', { job_id: summary.id });
  await sendCommand(session, 'get_slides', { job_id: summary.id });
  await sendCommand(session, 'get_transcript', { job_id: summary.id });
  session.logger.write('job_restored', { job_id: summary.id, status: summary.status || '' });
}

async function browseVideo(session) {
  const result = await dialog.showOpenDialog(session.window, {
    title: 'Import a lecture video',
    properties: ['openFile'],
    filters: [{ name: 'Lecture videos', extensions: ['mp4', 'mkv', 'mov', 'm4v', 'webm', 'avi'] }]
  });
  if (result.canceled || !result.filePaths.length) return { ok: true, cancelled: true };
  return sendCommand(session, 'import_video', { path: result.filePaths[0] });
}

async function openJobFolder(session, command, payload) {
  const jobId = payload.job_id || session.activeJobId || '';
  const result = await sendCommand(session, 'get_job', { job_id: jobId });
  const target = command === 'open_export_folder' ? result.export_dir : result.job_dir;
  if (!target) throw new Error('The selected job does not have an accessible folder.');
  const error = await shell.openPath(target);
  if (error) throw new Error(error);
  return { ok: true, path: target };
}

function testDesktopNotification() {
  if (!Notification.isSupported()) {
    return {
      ok: false,
      unavailable: true,
      error: 'Desktop notifications are unavailable on this system.'
    };
  }
  try {
    const notification = new Notification({
      title: 'LecturePack',
      body: 'Desktop notifications are working.'
    });
    notification.show();
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error.message || 'The desktop notification could not be shown.' };
  }
}

async function handleCommand(session, command, payload) {
  if (command === 'browse_video') return browseVideo(session);
  if (command === 'open_job_folder' || command === 'open_export_folder') {
    return openJobFolder(session, command, payload);
  }
  if (command === 'test_notification') return testDesktopNotification();
  return sendCommand(session, command, payload);
}

function terminateProcessTree(child, logger) {
  if (!child || child.exitCode !== null || !child.pid) return;
  if (process.platform === 'win32') {
    const result = spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      windowsHide: true,
      shell: false,
      stdio: 'ignore'
    });
    logger.write('sidecar_tree_terminated', {
      pid: child.pid,
      status: result.status,
      error: result.error?.message || ''
    });
  } else {
    try { child.kill('SIGTERM'); }
    catch (error) { logger.write('sidecar_terminate_failed', { pid: child.pid, error: error.message }); }
  }
}

function waitForExit(child, timeoutMs) {
  if (!child || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(finish, timeoutMs);
    child.once('close', finish);
  });
}

async function stopSession(session) {
  if (!session) return;
  if (session.stopPromise) return session.stopPromise;
  session.stopPromise = (async () => {
    session.closed = true;
    rejectPending(session, 'Electron session closed.');
    const child = session.sidecar;
    if (child && child.exitCode === null) {
      try {
        child.stdin.write(`${JSON.stringify({
          request_id: `production-${process.pid}-shutdown`,
          command: 'shutdown',
          payload: {}
        })}\n`);
        // Keep the pipe open while the sidecar drains this command. Closing
        // stdin at the same instant can race the Windows pipe read and drop
        // the shutdown line before QCoreApplication sees it.
      } catch (_) { /* the process may already be closing */ }
      // PyInstaller may spend a few seconds releasing QtCore and worker DLLs
      // after QCoreApplication.quit(). Give it time to exit normally before
      // falling back to an exact process-tree termination.
      await waitForExit(child, 5000);
      if (child.exitCode === null) terminateProcessTree(child, session.logger);
      await waitForExit(child, 2000);
    }
    if (session.documentTempDir) {
      const tempRoot = path.resolve(app.getPath('temp')) + path.sep;
      const documentTempDir = path.resolve(session.documentTempDir);
      if (documentTempDir.startsWith(tempRoot)) {
        try {
          fs.rmSync(documentTempDir, { recursive: true, force: true });
          session.logger.write('production_document_removed', { directory: documentTempDir });
        } catch (error) {
          session.logger.write('production_document_remove_failed', {
            directory: documentTempDir,
            error: error.message
          });
        }
      }
    }
    session.logger.write('session_closed');
  })();
  return session.stopPromise;
}

function requestQuit() {
  if (quitPromise) return;
  const session = activeSession;
  quitPromise = stopSession(session).finally(() => app.quit());
}

function createProductionWindow() {
  const logger = makeLogger();
  const uiDir = uiDirectory();
  const icon = applicationIcon();
  const window = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 640,
    minHeight: 480,
    show: false,
    autoHideMenuBar: true,
    title: PRODUCT_NAME,
    backgroundColor: '#16191F',
    ...(icon ? { icon } : {}),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'production-preload.js')
    }
  });
  const session = {
    window,
    logger,
    uiDir,
    pageReady: false,
    pendingPageMessages: [],
    sidecar: null,
    sidecarBuffer: '',
    pending: new Map(),
    activeJobId: '',
    bootstrapped: false,
    closed: false,
    dataDir: ''
  };
  activeSession = session;

  window.once('ready-to-show', () => window.show());
  window.webContents.on('did-finish-load', () => {
    session.pageReady = true;
    logger.write('page_ready', { ui_dir: uiDir });
    flushPageMessages(session);
    try {
      startSidecar(session);
    } catch (error) {
      logger.write('sidecar_start_failed', { error: error.message });
      sendToPage(session, { event: 'error', kind: 'startup', error: error.message });
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
    logger.write('console', {
      level,
      message: String(message || '').slice(0, 1000),
      line,
      sourceId: String(sourceId || '').slice(0, 240)
    });
  });
  window.on('closed', () => {
    if (!app.isQuitting) requestQuit();
  });

  const document = writeProductionDocument(uiDir);
  session.documentTempDir = document.tempDir;
  logger.write('production_document_written', { file: document.file });
  window.loadFile(document.file, { query: 'app=production' });
  return session;
}

ipcMain.handle('lecturepack-production:command', (_event, command, payload) => {
  if (!activeSession || activeSession.closed) {
    throw new Error('The LecturePack production session is not active.');
  }
  const normalizedPayload = payload && typeof payload === 'object' ? payload : {};
  return handleCommand(activeSession, String(command || ''), normalizedPayload);
});

ipcMain.handle('lecturepack-production:version', () => app.getVersion());

if (hasSingleInstanceLock) {
  app.on('second-instance', () => {
    const window = activeSession && activeSession.window;
    if (!window || window.isDestroyed()) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
    if (process.platform === 'win32') window.flashFrame(true);
  });

  app.whenReady().then(() => {
  // The production window is a focused desktop surface, not a browser shell.
  // Removing the application menu also prevents Alt from resurrecting the
  // default File/Edit/View/Window menu on Windows.
  Menu.setApplicationMenu(null);
  createProductionWindow();
  const quitAfter = Number(options['quit-after-seconds'] || 0);
  if (Number.isFinite(quitAfter) && quitAfter > 0) {
    setTimeout(() => requestQuit(), Math.min(quitAfter, 24 * 60 * 60) * 1000);
  }
});

  app.on('before-quit', (event) => {
    if (quitPromise || !activeSession || activeSession.closed) return;
    event.preventDefault();
    requestQuit();
  });
  app.on('window-all-closed', () => requestQuit());
} else {
  app.quit();
}

process.on('exit', () => {
  const child = activeSession && activeSession.sidecar;
  if (child && child.exitCode === null && child.pid && process.platform === 'win32') {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      windowsHide: true,
      shell: false,
      stdio: 'ignore'
    });
  }
});
