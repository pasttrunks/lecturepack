'use strict';

const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  net,
  Notification,
  powerSaveBlocker,
  protocol,
  screen,
  shell,
  Tray
} = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn, spawnSync } = require('node:child_process');
const { validateLocalVideoPath, extractFileArguments } = require('./import-path');
const updaterModule = require('./updater');

const REPO_ROOT = path.resolve(__dirname, '..');
const packageInfo = require('./package.json');
const PRODUCT_NAME = packageInfo.productName || 'LecturePack';
const PRODUCT_VERSION = packageInfo.version || '2.0.0';
const APP_USER_MODEL_ID = 'LecturePack.LecturePack';
const STARTUP_DEADLINE_MS = 28000;
const MAX_SESSION_LOGS = 10;
const options = parseOptions(process.argv.slice(1));
const hasSingleInstanceLock = app.requestSingleInstanceLock();

app.setName(PRODUCT_NAME);
app.setVersion(PRODUCT_VERSION);
if (process.platform === 'win32') app.setAppUserModelId(APP_USER_MODEL_ID);

let activeSession = null;
let lastResultsDir = null;
let requestCounter = 0;
let quitPromise = null;

// ---- Feature 5: system-sleep prevention ----
// Real work (a running processing job, or a yt-dlp download in waiting/
// downloading state) keeps the system awake while the display may still
// sleep. Electron's 'prevent-app-suspension' blocks system sleep but allows
// the display to turn off, which is exactly the required behavior.
let powerSaveId = null;

// ---- Feature 2: tray + background after close ----
let tray = null;
let closeToTrayPreference = null; // null | 'background' | 'exit'
let quitToTray = false; // set when Quit is chosen from the tray

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
      #btn-show-empty, #btn-save {
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
  const oldLogs = fs.readdirSync(resultDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /^production-.*\.jsonl$/i.test(entry.name))
    .map((entry) => {
      const file = path.join(resultDir, entry.name);
      let modified = 0;
      try { modified = fs.statSync(file).mtimeMs; } catch (_) { /* pruned below if stale */ }
      return { file, modified };
    })
    .sort((left, right) => right.modified - left.modified || right.file.localeCompare(left.file));
  oldLogs.slice(MAX_SESSION_LOGS - 1).forEach((entry) => {
    try { fs.unlinkSync(entry.file); } catch (_) { /* log retention must never block startup */ }
  });
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

function startupDiagnostics(session) {
  const health = session && session.latestHealth && typeof session.latestHealth === 'object'
    ? session.latestHealth : {};
  const checks = Array.isArray(health.checks) ? health.checks.map((check) => ({
    id: String(check.id || ''),
    ok: check.ok === true,
    title: String(check.title || ''),
    detail: String(check.detail || ''),
    technical: String(check.technical || '')
  })) : [];
  return {
    lecturepack_version: PRODUCT_VERSION,
    windows_version: `${os.type()} ${os.release()}`,
    architecture: os.arch(),
    data_path: session && session.dataDir ? session.dataDir : dataDirectory(),
    startup_health: {
      passed: health.passed === true,
      startup_ok: health.startup_ok === true,
      checks
    },
    rust_study_core: checks.find((check) => check.id === 'study_core') || null,
    ffmpeg: checks.find((check) => check.id === 'ffmpeg') || null,
    whisper: checks.find((check) => check.id === 'whisper_smoke') || null,
    yt_dlp: checks.find((check) => check.id === 'yt_dlp') || null,
    recent_error: session && session.lastStartupError ? session.lastStartupError : null,
    log_file: session && session.logger ? session.logger.file : '',
    log_directory: session && session.logger ? session.logger.resultDir : ''
  };
}

function clearStartupDeadline(session) {
  if (session.startupDeadlineTimer) clearTimeout(session.startupDeadlineTimer);
  session.startupDeadlineTimer = null;
}

function reportStartupFailure(session, reason, detail, extra = {}) {
  if (!session || session.closed || session.startupFailure) return;
  clearStartupDeadline(session);
  const checks = Array.isArray(extra.checks) ? extra.checks : (
    session.latestHealth && Array.isArray(session.latestHealth.checks) ? session.latestHealth.checks : []
  );
  const failedCheck = extra.failedCheck || checks.find((check) => check && check.fatal_at_startup && check.ok !== true) || null;
  const failure = {
    reason: String(reason || 'startup_failed'),
    detail: String(detail || 'Processing service failed to start.'),
    failed_check: failedCheck,
    elapsed_ms: session.startupStartedAt ? Date.now() - session.startupStartedAt : 0,
    attempt: session.startupAttempt
  };
  session.startupFailure = failure;
  session.lastStartupError = failure;
  session.logger.write('startup_terminal_failure', failure);
  sendToPage(session, {
    event: 'startup_failure',
    title: "LecturePack couldn't start.",
    message: 'Processing service failed to start.',
    ...failure,
    checks,
    diagnostics: startupDiagnostics(session)
  });
}

function completeStartup(session) {
  clearStartupDeadline(session);
  session.startupComplete = true;
  session.startupFailure = null;
  // Reconcile the active-work counter so a restored job's transient
  // 'processing' flash cannot leave the power-save blocker or close-to-tray
  // intercepting a clean shutdown.
  resetActiveWork(session);
  session.logger.write('startup_complete', {
    elapsed_ms: Date.now() - session.startupStartedAt,
    attempt: session.startupAttempt
  });
  // U4: a non-blocking automatic update check runs no more than once per day
  // and only after startup is healthy. It must never delay startup readiness.
  if (updaterModule.shouldAutoCheck(app.getPath('userData'))) {
    setTimeout(() => {
      if (session.closed || !session.startupComplete) return;
      void checkForUpdates(session, false);
    }, 5000);
  }
}

function armStartupDeadline(session, attempt) {
  clearStartupDeadline(session);
  session.startupDeadlineTimer = setTimeout(() => {
    if (session.closed || session.startupComplete || attempt !== session.startupAttempt) return;
    reportStartupFailure(
      session,
      'startup_timeout',
      `The processing service did not become ready within ${STARTUP_DEADLINE_MS / 1000} seconds.`
    );
    if (session.sidecar && session.sidecar.exitCode === null) terminateProcessTree(session.sidecar, session.logger);
  }, STARTUP_DEADLINE_MS);
}

function applicationIcon() {
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'lecturepack.ico')]
    : [path.join(REPO_ROOT, 'app', 'packaging', 'lecturepack.ico')];
  return candidates.find(pathExists) || undefined;
}

// The renderer requests job-card posters as lpasset://poster/<job_id>/poster
// (the historical Qt scheme). The sidecar writes poster.webp into each job
// directory at import time; this handler serves that file so thumbnails appear
// immediately. Any other lpasset:// path is rejected.
function registerAssetProtocol() {
  protocol.handle('lpasset', (request) => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'poster') return new Response('Not found', { status: 404 });
      const segments = url.pathname.split('/').filter(Boolean);
      if (segments.length !== 2 || segments[1] !== 'poster') {
        return new Response('Not found', { status: 404 });
      }
      const jobId = decodeURIComponent(segments[0]);
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(jobId)) {
        return new Response('Not found', { status: 404 });
      }
      const dataDir = dataDirectory();
      const candidates = [
        path.join(dataDir, 'jobs', jobId, 'poster.webp'),
        path.join(dataDir, 'jobs', jobId, 'poster.jpg')
      ];
      const found = candidates.find(pathExists);
      if (!found) return new Response('Not found', { status: 404 });
      const mime = found.endsWith('.webp') ? 'image/webp' : 'image/jpeg';
      return net.fetch(pathToFileURL(found).href, { bypassCustomProtocolHandlers: true })
        .then((response) => new Response(response.body, {
          status: 200,
          headers: { 'Content-Type': mime, 'Cache-Control': 'no-cache' }
        }))
        .catch(() => new Response('Not found', { status: 404 }));
    } catch (_) {
      return new Response('Not found', { status: 404 });
    }
  });
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

// Mirror the active processing job's progress on the Windows taskbar. Uses the
// exact job percent the sidecar already puts in status_changed (the same
// value driving the renderer's Home/Process progress), so no second progress
// calculation exists. Terminal labels clear the bar; a failed/error state
// flashes the taskbar red before clearing.
function updateTaskbarProgress(session, message) {
  const win = session.window;
  if (!win || win.isDestroyed()) return;
  const event = message.event || '';
  if (event === 'status_changed') {
    const label = String(message.label || '').toLowerCase();
    const pct = Number(message.pct);
    if (label === 'processing') {
      if (session.taskbarClearTimer) {
        clearTimeout(session.taskbarClearTimer);
        session.taskbarClearTimer = null;
      }
      session.taskbarProgressJob = String(message.job || session.activeJobId || '');
      win.setProgressBar(Math.max(0, Math.min(1, (pct || 0) / 100)));
    } else if (label === 'failed' || label === 'cancelled' || label === 'interrupted') {
      win.setProgressBar(0, { mode: 'error' });
      session.taskbarClearTimer = setTimeout(() => {
        session.taskbarClearTimer = null;
        if (!win.isDestroyed()) win.setProgressBar(-1);
      }, 1500);
    } else {
      session.taskbarProgressJob = '';
      win.setProgressBar(-1); // done / review-ready / idle -> clear
    }
  } else if (event === 'job_completed' || event === 'pipeline_changed') {
    // A pipeline event follows every live status update. The status payload's
    // overall job percentage is authoritative; only use indeterminate mode if
    // a pipeline became active before any status payload for that job arrived.
    if (event === 'pipeline_changed' && Array.isArray(message.stages)) {
      const active = message.stages.find((s) => s && (s.state === 'active' || s.state === 'running'));
      if (active && session.taskbarProgressJob !== String(message.job || session.activeJobId || '')) {
        win.setProgressBar(0.5, { mode: 'indeterminate' });
      }
    }
  }
}

function windowStatePath() {
  return path.join(app.getPath('userData'), 'window-state.json');
}

// ---- Feature 5: system-sleep prevention ----
// Real work (a running processing job, or a yt-dlp download in waiting/
// downloading state) keeps the system awake while the display may still
// sleep. Electron's 'prevent-app-suspension' blocks system sleep but allows
// the display to turn off, which is exactly the required behavior.
function refreshPowerSave(session) {
  const active = session && session.activeWorkCount > 0;
  if (active && powerSaveId === null) {
    powerSaveId = powerSaveBlocker.start('prevent-app-suspension');
    if (session) session.logger.write('power_save_acquired', { id: powerSaveId });
  } else if (!active && powerSaveId !== null) {
    const id = powerSaveId;
    powerSaveId = null;
    if (powerSaveBlocker.isStarted(id)) powerSaveBlocker.stop(id);
    if (session) session.logger.write('power_save_released', { id });
  }
}

// Reconcile the active-work counter to a known-good value after startup.
// Startup restores a job whose status may briefly flash 'processing' before
// settling to its terminal state, which could otherwise leave the counter
// stuck above zero and wrongly keep the power-save blocker on or intercept a
// clean close. After bootstrap the live event stream re-drives the counter.
function resetActiveWork(session) {
  if (!session) return;
  session.activeWorkCount = 0;
  if (session.activeWork) session.activeWork.clear();
  refreshPowerSave(session);
}

// ---- Feature 2: tray + background after close ----
function trayIconImage() {
  const iconPath = applicationIcon();
  if (!iconPath) return nativeImage.createEmpty();
  const image = nativeImage.createFromPath(iconPath);
  return image.isEmpty() ? nativeImage.createEmpty() : image;
}

function createTray(session) {
  if (tray) return tray;
  try {
    tray = new Tray(trayIconImage());
    tray.setToolTip(PRODUCT_NAME);
    tray.setContextMenu(Menu.buildFromTemplate([
      {
        label: 'Open LecturePack',
        click: () => {
          const window = activeSession && activeSession.window;
          if (window && !window.isDestroyed()) {
            if (window.isMinimized()) window.restore();
            window.show();
            window.focus();
          } else {
            requestQuit();
          }
        }
      },
      { type: 'separator' },
      {
        label: 'Quit LecturePack',
        click: () => {
          quitToTray = true;
          requestQuit();
        }
      }
    ]));
    tray.on('click', () => {
      const window = activeSession && activeSession.window;
      if (window && !window.isDestroyed()) {
        if (window.isMinimized()) window.restore();
        if (!window.isVisible()) window.show();
        window.focus();
      }
    });
    return tray;
  } catch (error) {
    if (session) session.logger.write('tray_creation_failed', { error: error.message });
    return null;
  }
}

function closeToTrayStatePath() {
  return path.join(app.getPath('userData'), 'close-to-tray.json');
}

function loadCloseToTrayPreference() {
  try {
    const state = JSON.parse(fs.readFileSync(closeToTrayStatePath(), 'utf8'));
    closeToTrayPreference = state.choice === 'background' || state.choice === 'exit' ? state.choice : null;
  } catch (_) {
    closeToTrayPreference = null;
  }
}

function saveCloseToTrayPreference(choice, remember) {
  if (choice !== 'background' && choice !== 'exit') return;
  if (remember) {
    closeToTrayPreference = choice;
    try {
      fs.mkdirSync(path.dirname(closeToTrayStatePath()), { recursive: true });
      fs.writeFileSync(closeToTrayStatePath(), JSON.stringify({ choice }), 'utf8');
    } catch (_) { /* preference persistence must never block close */ }
  } else {
    closeToTrayPreference = null;
  }
}

// A window close is intercepted when real work would continue in the
// background. Returns 'keep' (hide to tray), 'exit' (really quit), or 'cancel'
// (abort the close entirely).
async function resolveCloseToTray(session) {
  if (quitToTray || app.isQuitting) return 'exit';
  if (closeToTrayPreference === 'background') return 'keep';
  if (closeToTrayPreference === 'exit') return 'exit';
  const window = session && session.window;
  const options = {
    type: 'question',
    title: PRODUCT_NAME,
    message: 'LecturePack is still working.',
    detail: 'Processing, downloads, or queued work will continue. Keep LecturePack working in the background, or exit and stop work?',
    buttons: ['Keep working in background', 'Exit and stop work'],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
    checkboxLabel: 'Remember my choice'
  };
  if (window && !window.isDestroyed()) {
    const result = await dialog.showMessageBox(window, options);
    saveCloseToTrayPreference(result.response === 0 ? 'background' : 'exit', !!result.checkboxChecked);
    return result.response === 0 ? 'keep' : 'exit';
  }
  const result = await dialog.showMessageBox(options);
  saveCloseToTrayPreference(result.response === 0 ? 'background' : 'exit', !!result.checkboxChecked);
  return result.response === 0 ? 'keep' : 'exit';
}

function visibleWindowBounds(bounds) {
  if (!bounds || !Number.isFinite(bounds.width) || !Number.isFinite(bounds.height) ||
      bounds.width < 640 || bounds.height < 480 || !Number.isFinite(bounds.x) || !Number.isFinite(bounds.y)) {
    return false;
  }
  return screen.getAllDisplays().some((display) => {
    const area = display.workArea;
    const width = Math.max(0, Math.min(bounds.x + bounds.width, area.x + area.width) - Math.max(bounds.x, area.x));
    const height = Math.max(0, Math.min(bounds.y + bounds.height, area.y + area.height) - Math.max(bounds.y, area.y));
    return width >= 120 && height >= 80;
  });
}

function loadWindowState() {
  try {
    const state = JSON.parse(fs.readFileSync(windowStatePath(), 'utf8'));
    return visibleWindowBounds(state.bounds) ? state : null;
  } catch (_) {
    return null;
  }
}

function saveWindowState(win) {
  if (!win || win.isDestroyed()) return;
  try {
    const bounds = win.isMaximized() && typeof win.getNormalBounds === 'function'
      ? win.getNormalBounds() : win.getBounds();
    const state = { bounds, maximized: win.isMaximized() };
    fs.mkdirSync(path.dirname(windowStatePath()), { recursive: true });
    fs.writeFileSync(windowStatePath(), JSON.stringify(state), 'utf8');
  } catch (_) { /* window restore must never block shutdown */ }
}

// Track whether real work is happening so the power-save blocker (Feature 5)
// and the close-to-tray decision (Feature 2) reflect actual activity. A
// running processing job or a waiting/downloading yt-dlp item counts as work.
// Workloads are tracked by key so overlapping jobs/downloads never double-count
// and are released exactly when the last one finishes.
function trackActiveWork(session, event, message) {
  if (!session) return;
  if (!session.activeWork) session.activeWork = new Set();
  const work = session.activeWork;
  if (event === 'status_changed') {
    const label = String(message.label || '').toLowerCase();
    const key = `job:${String(message.job || session.activeJobId || '')}`;
    if (label === 'processing' || label === 'downloading') {
      work.add(key);
    } else if (label === 'review ready' || label === 'failed' || label === 'cancelled' ||
               label === 'interrupted' || label === 'done' || label === 'idle') {
      work.delete(key);
    }
  } else if (event === 'downloads_changed') {
    const downloads = Array.isArray(message.downloads) ? message.downloads : [];
    const activeKeys = new Set(
      downloads.filter((d) => d && (d.status === 'waiting' || d.status === 'downloading' || d.status === 'running'))
        .map((d) => `download:${String(d.download_id || d.item_id || d.id || '')}`)
    );
    for (const key of work) {
      if (key.startsWith('download:') && !activeKeys.has(key)) work.delete(key);
    }
    for (const key of activeKeys) work.add(key);
  }
  session.activeWorkCount = work.size;
  refreshPowerSave(session);
}

function handleSidecarMessage(session, message) {
  if (!message || typeof message !== 'object') return;
  session.logger.write('sidecar_message', {
    event: message.event || '',
    command: message.command || '',
    response_to: message.response_to || ''
  });
  if (message.event === 'active_job') session.activeJobId = message.id || '';
  // Taskbar progress mirrors the active job's live status/pipeline events.
  updateTaskbarProgress(session, message);
  // Power-save tracking (Feature 5) keys off live status and download events.
  trackActiveWork(session, message.event || '', message);
  if (message.response_to) {
    settleResponse(session, message);
    if (message.event === 'error') sendToPage(session, message);
    return;
  }
  sendToPage(session, message);
  if (message.event === 'ready') void bootstrap(session, session.startupAttempt);
}

function attachSidecar(session, child, command, attempt) {
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
    if (attempt === session.startupAttempt && !session.startupComplete) {
      reportStartupFailure(session, 'sidecar_spawn_failed', error.message);
    } else {
      sendToPage(session, { event: 'service_failure', reason: 'sidecar_spawn_failed', detail: error.message });
    }
  });
  child.on('close', (code, signal) => {
    session.logger.write('sidecar_exit', { code, signal });
    rejectPending(session, `Sidecar exited (${code ?? signal ?? 'unknown'}).`);
    sendToPage(session, { event: 'exit', code, signal });
    if (attempt !== session.startupAttempt || session.closed) return;
    const detail = `The processing service exited before it was ready (code ${code ?? signal ?? 'unknown'}).`;
    if (!session.startupComplete) {
      reportStartupFailure(session, 'sidecar_exit', detail);
    } else {
      session.startupComplete = false;
      session.startupFailure = null;
      reportStartupFailure(session, 'sidecar_exit', 'The processing service stopped unexpectedly.');
    }
  });
}

function startSidecar(session, attempt) {
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
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONUTF8: '1',
      LECTUREPACK_APP_VERSION: app.getVersion()
    },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    shell: false
  });
  attachSidecar(session, child, command, attempt);
}

async function bootstrap(session, attempt) {
  if (session.bootstrapped || session.closed || attempt !== session.startupAttempt) return;
  session.bootstrapped = true;
  try {
    const health = await sendCommand(session, 'health_check');
    if (attempt !== session.startupAttempt) return;
    session.latestHealth = health;
    if (health.startup_ok !== true) {
      const failedCheck = Array.isArray(health.checks)
        ? health.checks.find((check) => check && check.fatal_at_startup && check.ok !== true)
        : null;
      reportStartupFailure(
        session,
        'health_check_failed',
        failedCheck ? failedCheck.detail : (health.error || 'The packaged LecturePack engine failed its startup health check.'),
        { checks: health.checks, failedCheck }
      );
      return;
    }
    // Feature 6: after startup health passes, return crash-interrupted jobs to
    // the queue exactly once. This never runs before health is proven.
    let recovery = null;
    try {
      recovery = await sendCommand(session, 'recover_interrupted_jobs');
      if (attempt !== session.startupAttempt) return;
      const recovered = recovery && Number.isFinite(recovery.recovered) ? recovery.recovered : 0;
      if (recovered > 0) {
        sendToPage(session, { event: 'recovery_notice', recovered });
      }
    } catch (_) { /* recovery must not block startup */ }
    const listed = await sendCommand(session, 'list_jobs');
    if (attempt !== session.startupAttempt) return;
    const jobs = Array.isArray(listed.jobs) ? listed.jobs : [];
    const setupAcknowledged = health.startup_ok === true && health.setup_acknowledged === true;
    const checklist = Array.isArray(health.checklist) ? health.checklist : [];
    const guidedTour = listed.guided_tour || null;
    if (!jobs.length) {
      completeStartup(session);
      const bootstrapPayload = {
        event: 'bootstrap_complete',
        bootstrap_pending: false,
        runtime_health_state: 'HEALTHY',
        setup_acknowledged: setupAcknowledged,
        setup_complete: setupAcknowledged,
        healthy: true,
        checklist,
        guided_tour: guidedTour
      };
      session.latestBootstrap = bootstrapPayload;
      session.guidedTour = guidedTour;
      sendToPage(session, bootstrapPayload);
      return;
    }
    // The sidecar returns newest-first. Restore the newest completed job when
    // possible; interrupted/running jobs remain visible for an explicit retry.
    const preferred = jobs.find((job) => job.status === 'done') || jobs[0];
    await restoreJob(session, preferred);
    if (attempt !== session.startupAttempt) return;
    completeStartup(session);
    const bootstrapPayload = {
      event: 'bootstrap_complete',
      bootstrap_pending: false,
      runtime_health_state: 'HEALTHY',
      setup_acknowledged: setupAcknowledged,
      setup_complete: setupAcknowledged,
      healthy: true,
      checklist,
      guided_tour: guidedTour
    };
    session.latestBootstrap = bootstrapPayload;
    session.guidedTour = guidedTour;
    sendToPage(session, bootstrapPayload);
  } catch (error) {
    if (attempt !== session.startupAttempt) return;
    session.logger.write('bootstrap_failed', { error: error.message });
    reportStartupFailure(session, 'bootstrap_failed', error.message);
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
    title: 'Import lecture videos',
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: 'Lecture videos', extensions: ['mp4', 'mkv', 'mov', 'm4v', 'webm', 'avi'] },
      { name: 'All files', extensions: ['*'] }
    ]
  });
  if (result.canceled || !result.filePaths.length) return { ok: true, cancelled: true };
  if (result.filePaths.length === 1) return importLocalVideo(session, result.filePaths[0]);
  const paths = result.filePaths.filter((p) => importLocalVideoIsValid(p));
  if (!paths.length) return { ok: false, error: 'LecturePack could not access any of the selected files.' };
  return sendCommand(session, 'import_videos', { paths });
}

// Validate one path for a multi-file Browse import without importing it yet.
function importLocalVideoIsValid(rawPath) {
  const validated = validateLocalVideoPath(rawPath);
  return validated.ok;
}

// One shared import gate for both Browse and drag-and-drop. The renderer
// resolves dropped files through the preload's webUtils.getPathForFile and
// sends the absolute native path here; Browse arrives with the absolute path
// from the native dialog. Both normalize, prove existence/readability, and
// pass the same unchanged path to the sidecar's import_video command.
async function importLocalVideo(session, rawPath, extra) {
  const validated = validateLocalVideoPath(rawPath);
  if (!validated.ok) return validated;
  const payload = Object.assign({}, extra || {}, { path: validated.path });
  return sendCommand(session, 'import_video', payload);
}

// Supported media extensions, kept aligned with the sidecar's import rules.
const SUPPORTED_MEDIA_EXTENSIONS = new Set([
  '.mp4', '.avi', '.mkv', '.mov', '.m4v', '.webm', '.mpeg', '.mpg', '.wmv'
]);

// Feature 1: expand a mixed list of files and folders into a flat list of
// supported media files. Folders are scanned recursively within a sensible
// depth bound; unrelated files are ignored. Files pass the same readability
// gate as a normal import so a bad path is reported without failing the batch.
function expandImportPaths(paths) {
  const mediaFiles = [];
  const failures = [];
  const visited = new Set();
  const MAX_FOLDER_DEPTH = 6;
  const MAX_FOLDER_FILES = 2000;

  function isSupportedMedia(filePath) {
    try {
      return SUPPORTED_MEDIA_EXTENSIONS.has(path.extname(filePath).toLowerCase());
    } catch (_) {
      return false;
    }
  }

  function walk(filePath, depth) {
    let stat;
    try { stat = fs.statSync(filePath); } catch (_) { return; }
    if (stat.isFile()) {
      if (isSupportedMedia(filePath)) mediaFiles.push(filePath);
      return;
    }
    if (!stat.isDirectory()) return;
    if (depth > MAX_FOLDER_DEPTH) return;
    let entries;
    try { entries = fs.readdirSync(filePath, { withFileTypes: true }); } catch (_) { return; }
    if (mediaFiles.length >= MAX_FOLDER_FILES) return;
    for (const entry of entries) {
      if (mediaFiles.length >= MAX_FOLDER_FILES) break;
      const child = path.join(filePath, entry.name);
      if (visited.has(child)) continue;
      visited.add(child);
      if (entry.isFile()) {
        if (isSupportedMedia(child)) mediaFiles.push(child);
      } else if (entry.isDirectory()) {
        walk(child, depth + 1);
      }
    }
  }

  const raw = Array.isArray(paths) ? paths : [];
  for (const entry of raw) {
    const text = typeof entry === 'string' ? entry.trim() : '';
    if (!text) continue;
    const resolved = (() => { try { return path.resolve(text); } catch (_) { return text; } })();
    if (visited.has(resolved)) continue;
    visited.add(resolved);
    let stat;
    try { stat = fs.statSync(resolved); } catch (_) {
      failures.push({ path: text, code: 'NOT_FOUND', error: `Path not found: ${text}` });
      continue;
    }
    if (stat.isDirectory()) {
      walk(resolved, 0);
    } else if (stat.isFile()) {
      if (isSupportedMedia(resolved)) mediaFiles.push(resolved);
      else failures.push({ path: text, code: 'FFPROBE_FAILED', error: `Unsupported file type: ${text}` });
    }
  }
  return { mediaFiles, failures };
}

// Feature 1 + Feature 3: import a mixed list of files/folders through the
// normal import path. Folders are expanded to their media files; the flat
// list flows to the sidecar's import_videos command so every file reuses the
// existing import pipeline, duplicate detection, and clean-title behavior.
async function importMultiplePaths(session, paths) {
  if (!session || !paths || !paths.length) return { ok: true, imported: 0 };
  const { mediaFiles } = expandImportPaths(paths);
  if (!mediaFiles.length) {
    return { ok: false, error: 'LecturePack could not find any supported videos in that selection.' };
  }
  session.logger.write('import_paths', { paths: paths.length, media_files: mediaFiles.length });
  return sendCommand(session, 'import_videos', { paths: mediaFiles });
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

function resetUserDataFiles() {
  const root = path.resolve(app.getPath('userData'));
  const names = [
    'window-state.json',
    'close-to-tray.json',
    'updater.checkState.v1.json'
  ];
  const removed = [];
  const failed = [];
  for (const name of names) {
    const target = path.resolve(root, name);
    if (!target.startsWith(`${root}${path.sep}`)) {
      failed.push({ path: target, error: 'path escaped Electron userData' });
      continue;
    }
    try {
      let exists = false;
      try {
        fs.lstatSync(target);
        exists = true;
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      if (exists) {
        const stat = fs.lstatSync(target);
        if (stat.isSymbolicLink()) {
          const resolved = fs.realpathSync.native(target);
          if (!resolved.startsWith(`${root}${path.sep}`)) {
            throw new Error('refusing to remove a userData link outside its root');
          }
        }
        fs.unlinkSync(target);
        removed.push(name);
      }
    } catch (error) {
      failed.push({ path: target, error: error.message });
    }
  }
  return { ok: failed.length === 0, removed, failed };
}

async function clearRendererSession(session) {
  const webSession = session && session.window && session.window.webContents
    ? session.window.webContents.session : null;
  if (!webSession) return { ok: true, cleared: false };
  try {
    if (typeof webSession.clearStorageData === 'function') {
      await webSession.clearStorageData({ storages: [
        'appcache', 'cookies', 'filesystem', 'indexdb', 'localstorage',
        'shadercache', 'websql', 'serviceworkers', 'cachestorage'
      ] });
    }
    if (typeof webSession.clearCache === 'function') await webSession.clearCache();
    return { ok: true, cleared: true };
  } catch (error) {
    return { ok: false, error: error.message || String(error) };
  }
}

async function resetLecturePack(session) {
  const dataReset = await sendCommand(session, 'reset_lecturepack', {});
  if (!dataReset || dataReset.ok !== true) {
    return Object.assign({ ok: false, error: 'LecturePack data reset failed.' }, dataReset || {});
  }
  const userData = resetUserDataFiles();
  const rendererSession = await clearRendererSession(session);
  if (!userData.ok || !rendererSession.ok) {
    session.logger.write('reset_failed', { user_data: userData, renderer_session: rendererSession });
    return {
      ok: false,
      error: 'LecturePack reset could not clear every owned Electron session file.',
      data_reset: dataReset.reset || dataReset,
      user_data: userData,
      renderer_session: rendererSession
    };
  }
  session.resetting = true;
  session.logger.write('reset_complete', {
    data_dir: session.dataDir,
    user_data: userData.removed,
    relaunch: true
  });
  try {
    app.relaunch({ args: process.argv.slice(1) });
  } catch (error) {
    session.resetting = false;
    return { ok: false, error: `LecturePack reset completed but relaunch failed: ${error.message}` };
  }
  setTimeout(() => requestQuit(), 25);
  return {
    ok: true,
    reset: dataReset.reset || dataReset,
    user_data: userData,
    renderer_session: rendererSession,
    relaunch_scheduled: true,
    relaunching: true
  };
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

async function startStartupAttempt(session) {
  const previous = session.sidecar;
  session.startupAttempt += 1;
  const attempt = session.startupAttempt;
  clearStartupDeadline(session);
  session.startupStartedAt = Date.now();
  session.startupComplete = false;
  session.startupFailure = null;
  session.latestHealth = null;
  session.latestBootstrap = null;
  session.guidedTour = null;
  session.bootstrapped = false;
  session.sidecarBuffer = '';
  rejectPending(session, 'A new startup attempt began.');
  if (previous && previous.exitCode === null) {
    terminateProcessTree(previous, session.logger);
    await waitForExit(previous, 2000);
  }
  session.sidecar = null;
  armStartupDeadline(session, attempt);
  try {
    startSidecar(session, attempt);
    return { ok: true, attempt };
  } catch (error) {
    reportStartupFailure(
      session,
      /not found|missing/i.test(error.message) ? 'sidecar_missing' : 'sidecar_start_failed',
      error.message
    );
    return { ok: false, attempt, error: error.message };
  }
}

async function openLogsFolder(session) {
  const target = session.logger.resultDir;
  const error = await shell.openPath(target);
  if (error) throw new Error(error);
  return { ok: true, path: target };
}

// --------------------------------------------------------------------------- //
// Updater (Phase 6): stable GitHub update lifecycle in the Electron main.
// --------------------------------------------------------------------------- //
const UPDATER_REPO = 'pasttrunks/lecturepack';

function ensureUpdater(session) {
  if (session.updater) return session.updater;
  session.updater = updaterModule.createUpdater({
    version: PRODUCT_VERSION,
    repo: UPDATER_REPO,
    userDataDir: app.getPath('userData'),
    logger: session.logger,
    onState: (patch) => {
      Object.assign(session.updaterState || {}, patch);
      emitUpdaterState(session, patch);
    }
  });
  session.updaterState = { status: 'idle', version: PRODUCT_VERSION };
  return session.updater;
}

function emitUpdaterState(session, patch) {
  const state = session.updaterState || {};
  const phase = patch && patch.status ? patch.status : (state.status || 'idle');
  const payload = buildUpdaterStatePayload(session, Object.assign({}, state, patch || {}), phase);
  sendToPage(session, { event: 'update_state', payload: JSON.stringify(payload) });
}

function buildUpdaterStatePayload(session, state, phase) {
  const persisted = updaterModule.loadState(app.getPath('userData'));
  const base = {
    phase,
    version: PRODUCT_VERSION,
    // LecturePack 2 stable ships one channel. There is no channel selector.
    channel: 'stable',
    auto_check: persisted.autoCheck !== false,
    skipped_version: persisted.skippedVersion || null,
    release_url: (state && state.update && state.update.releaseUrl) || '',
    available_version: (state && state.update && state.update.version) || '',
    message: ''
  };
  if (phase === 'uptodate') base.message = "You're up to date";
  else if (phase === 'error') base.message = (state && state.error) || 'Update check failed.';
  // A refused update is never presented as "ready"; the user is told why and
  // can retry or go to GitHub.
  else if (phase === 'untrusted') base.message = (state && state.error) || 'This update could not be verified.';
  else if (phase === 'ready') base.message = 'Verified and ready to install.';
  else if (phase === 'downloaded') base.message = 'Update downloaded.';
  else if (phase === 'blocked') base.message = (state && state.message) || 'Update ready. Finish current processing, then install and restart.';
  return base;
}

async function getUpdaterState(session) {
  const state = session.updaterState || (session.updaterState = { status: 'idle', version: PRODUCT_VERSION });
  return JSON.stringify(buildUpdaterStatePayload(session, state, state.status || 'idle'));
}

async function checkForUpdates(session, manual) {
  // U4: never block startup; only check after the app is healthy.
  if (!session.startupComplete) {
    return { ok: false, error: 'LecturePack is still starting up.' };
  }
  const updater = ensureUpdater(session);
  session.updaterState = Object.assign({}, session.updaterState, { status: 'checking' });
  emitUpdaterState(session, { status: 'checking' });
  // Background checks honour "Skip this version"; an explicit check never does.
  const result = await updater.check({ respectSkip: !manual });
  session.updaterState = Object.assign({}, session.updaterState, result);
  if (result.status === 'available') {
    sendToPage(session, { event: 'update_available', payload: JSON.stringify({
      version: (result.update && result.update.version) || '',
      notes: (result.update && result.update.notes) || '',
      size: (result.update && result.update.size) || 0
    }) });
  } else if (result.status === 'uptodate') {
    emitUpdaterState(session, { status: 'uptodate' });
  } else if (result.status === 'untrusted') {
    emitUpdaterState(session, { status: 'untrusted', error: result.error });
  } else {
    emitUpdaterState(session, { status: 'error', error: result.error });
  }
  return { ok: true, status: result.status };
}

async function startUpdateDownload(session) {
  const updater = ensureUpdater(session);
  const state = session.updaterState || {};
  const update = (state && state.status === 'available' && state.update) || null;
  if (!update) {
    // No known update; run a check first, then download if one appears.
    const check = await checkForUpdates(session, false);
    return { ok: true, ...check };
  }
  session.updaterState = Object.assign({}, state, { status: 'downloading' });
  emitUpdaterState(session, { status: 'downloading' });
  try {
    const dest = await updater.download(update, (received, total) => {
      const pct = total > 0 ? Math.round((received / total) * 100) : 0;
      sendToPage(session, { event: 'update_progress', pct });
    });
    sendToPage(session, { event: 'update_ready' });
    session.updaterState = Object.assign({}, session.updaterState, { status: 'ready', installerPath: dest });
    emitUpdaterState(session, { status: 'ready' });
    return { ok: true, installer: dest };
  } catch (error) {
    if (error && error.cancelled) {
      // User cancelled: partial file already removed, offer the update again.
      session.updaterState = Object.assign({}, session.updaterState, { status: 'available', installerPath: null });
      emitUpdaterState(session, { status: 'available' });
      return { ok: true, cancelled: true };
    }
    session.updaterState = Object.assign({}, session.updaterState, { status: 'error', error: error.message });
    emitUpdaterState(session, { status: 'error', error: error.message });
    sendToPage(session, { event: 'update_error', message: error.message });
    return { ok: false, error: error.message };
  }
}

function cancelUpdateDownload(session) {
  const updater = session.updater;
  if (!updater || typeof updater.cancelDownload !== 'function' || !updater.cancelDownload()) {
    return { ok: true, cancelled: false };
  }
  session.logger.write('update_download_cancel_requested', {});
  return { ok: true, cancelled: true };
}

function skipUpdateVersion(session, payload) {
  const state = session.updaterState || {};
  const target = String(
    (payload && payload.version) || (state.update && state.update.version) || ''
  );
  if (!target) return { ok: false, error: 'There is no update to skip.' };
  const skipped = updaterModule.setSkippedVersion(app.getPath('userData'), target);
  session.logger.write('update_version_skipped', { version: skipped });
  session.updaterState = Object.assign({}, state, { status: 'idle' });
  emitUpdaterState(session, { status: 'idle' });
  return { ok: true, skipped_version: skipped };
}

function clearSkippedVersion(session) {
  updaterModule.setSkippedVersion(app.getPath('userData'), '');
  session.logger.write('update_skip_cleared', {});
  emitUpdaterState(session, {});
  return { ok: true, skipped_version: null };
}

// The renderer sends either { enabled: bool } or the bare string 'true'/'false'.
function setAutoUpdateCheck(session, payload) {
  const raw = (payload && typeof payload === 'object') ? payload.enabled : payload;
  const enabled = !(raw === false || raw === 'false' || raw === 0 || raw === '0');
  updaterModule.setAutoCheckEnabled(app.getPath('userData'), enabled);
  session.logger.write('update_auto_check_set', { enabled });
  emitUpdaterState(session, {});
  return { ok: true, auto_check: enabled };
}

// Open the release page in the user's real browser through the single trusted
// external-link path. Only the canonical releases host is ever opened.
function openReleasePage(session, payload) {
  const state = session.updaterState || {};
  const version = String(
    (payload && payload.version) || (state.update && state.update.version) || ''
  ).replace(/^v/i, '');
  const target = version
    ? `https://github.com/${UPDATER_REPO}/releases/tag/v${encodeURIComponent(version)}`
    : `https://github.com/${UPDATER_REPO}/releases/latest`;
  session.logger.write('update_release_page_opened', { url: target });
  shell.openExternal(target);
  return { ok: true, url: target };
}

async function installDownloadedUpdate(session) {
  // U5/U10: never install while real work is active; defer until idle.
  // There is no deferred auto-install: LecturePack never restarts itself when
  // background work finishes. The user comes back and installs explicitly.
  if (session.activeWorkCount > 0) {
    const message = 'Update ready. Finish current processing, then install and restart.';
    emitUpdaterState(session, { status: 'blocked', message });
    return { ok: false, blocked: true, error: message };
  }
  const state = session.updaterState || {};
  const installerPath = (state && state.installerPath) || null;
  if (!installerPath || !fs.existsSync(installerPath)) {
    return { ok: false, error: 'No verified update is ready to install.' };
  }
  const updater = ensureUpdater(session);
  try {
    updater.install(installerPath);
    session.logger.write('update_installer_launched', { file: installerPath });
    // Exit the running app cleanly so the installer can finish over the same
    // per-user installation; the installer relaunches LecturePack.
    quitToTray = true;
    requestQuit();
    return { ok: true };
  } catch (error) {
    session.logger.write('update_install_failed', { error: error.message });
    return { ok: false, error: error.message };
  }
}

async function handleCommand(session, command, payload) {
  if (command === 'retry_startup') return startStartupAttempt(session);
  if (command === 'open_logs') return openLogsFolder(session);
  if (command === 'get_startup_diagnostics') return startupDiagnostics(session);
  if (command === 'get_bootstrap') {
    return session.latestBootstrap || {
      bootstrap_pending: !session.startupComplete,
      runtime_health_state: session.latestHealth && session.latestHealth.startup_ok === true
        ? 'HEALTHY' : 'SETUP_REQUIRED',
      setup_acknowledged: !!(session.latestHealth && session.latestHealth.setup_acknowledged === true),
      setup_complete: !!(session.latestHealth && session.latestHealth.setup_acknowledged === true),
      healthy: !!(session.latestHealth && session.latestHealth.startup_ok === true),
      guided_tour: session.guidedTour || null,
      checklist: session.latestHealth && Array.isArray(session.latestHealth.checklist)
        ? session.latestHealth.checklist : []
    };
  }
  if (command === 'browse_video') return browseVideo(session);
  if (command === 'reset_lecturepack') return resetLecturePack(session);
  if (command === 'import_paths') {
    const paths = Array.isArray(payload.paths) ? payload.paths : (
      typeof payload.paths === 'string' ? [payload.paths] : []);
    if (!paths.length) return { ok: false, error: 'No files or folders were supplied.' };
    return importMultiplePaths(session, paths);
  }
  if (command === 'import_video' && !payload.bundled_demo && typeof payload.path === 'string' && payload.path) {
    return importLocalVideo(session, payload.path, payload);
  }
  if (command === 'open_job_folder' || command === 'open_export_folder') {
    return openJobFolder(session, command, payload);
  }
  if (command === 'test_notification') return testDesktopNotification();
  if (command === 'get_updater_state') return getUpdaterState(session);
  if (command === 'check_updates') return checkForUpdates(session, true);
  if (command === 'start_update_download') return startUpdateDownload(session);
  if (command === 'install_downloaded_update') return installDownloadedUpdate(session);
  if (command === 'cancel_update_download') return cancelUpdateDownload(session);
  if (command === 'skip_update_version') return skipUpdateVersion(session, payload);
  if (command === 'clear_skipped_version') return clearSkippedVersion(session);
  if (command === 'set_auto_check') return setAutoUpdateCheck(session, payload);
  if (command === 'open_release_page') return openReleasePage(session, payload);
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
    clearStartupDeadline(session);
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
  quitToTray = true;
  // Always release the system-sleep blocker before the app exits.
  if (powerSaveId !== null) {
    const id = powerSaveId;
    powerSaveId = null;
    if (powerSaveBlocker.isStarted(id)) powerSaveBlocker.stop(id);
  }
  if (tray) {
    try { tray.destroy(); } catch (_) { /* tray teardown must never block quit */ }
    tray = null;
  }
  const session = activeSession;
  quitPromise = stopSession(session).finally(() => app.quit());
}

function createProductionWindow() {
  const logger = makeLogger();
  const uiDir = uiDirectory();
  const icon = applicationIcon();
  const restoredWindow = loadWindowState();
  const window = new BrowserWindow({
    ...(restoredWindow ? restoredWindow.bounds : { width: 1360, height: 860 }),
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
    startupAttempt: 0,
    startupStartedAt: 0,
    startupDeadlineTimer: null,
    startupComplete: false,
    startupFailure: null,
    lastStartupError: null,
    latestHealth: null,
    latestBootstrap: null,
    guidedTour: null,
    activeWorkCount: 0,
    documentTempDir: null,
    closed: false,
    resetting: false,
    dataDir: ''
  };
  activeSession = session;

  window.once('ready-to-show', () => {
    if (restoredWindow && restoredWindow.maximized) window.maximize();
    window.show();
  });
  let windowSaveTimer = null;
  const scheduleWindowSave = () => {
    if (session.resetting) return;
    if (windowSaveTimer) clearTimeout(windowSaveTimer);
    windowSaveTimer = setTimeout(() => {
      windowSaveTimer = null;
      if (!session.resetting) saveWindowState(window);
    }, 250);
  };
  window.on('move', scheduleWindowSave);
  window.on('resize', scheduleWindowSave);
  window.on('maximize', scheduleWindowSave);
  window.on('unmaximize', scheduleWindowSave);
  window.on('close', () => {
    if (!session.resetting) saveWindowState(window);
  });
  window.on('close', (event) => {
    // Feature 2: when real work would continue, intercept the X button and
    // offer to keep working in the background via the tray. Explicit Quit
    // (tray menu, app.quit) bypasses this and always really quits.
    if (app.isQuitting || quitToTray || !session.activeWorkCount) return;
    event.preventDefault();
    void resolveCloseToTray(session).then((choice) => {
      if (session.closed || activeSession !== session) return;
      if (choice === 'keep') {
        createTray(session);
        session.window.hide();
        logger.write('close_to_tray', { activeWork: session.activeWorkCount });
      } else if (choice === 'exit') {
        quitToTray = true;
        requestQuit();
      }
      // choice === 'cancel' leaves the window open.
    });
  });
  window.webContents.on('did-finish-load', () => {
    session.pageReady = true;
    logger.write('page_ready', { ui_dir: uiDir });
    flushPageMessages(session);
    void startStartupAttempt(session);
  });
  window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    logger.write('page_load_failed', { errorCode, errorDescription, validatedURL });
  });
  // A dropped file must never navigate the window (the renderer prevents the
  // default drop action; this is the host-side guarantee that the browser
  // shell never opens a dragged file).
  window.webContents.on('will-navigate', (event) => {
    event.preventDefault();
  });
  // The renderer may never spawn a browser window of its own. Anything that
  // asks to open a window is denied; only https:// links are handed to the
  // user's real browser, and only through the one trusted external path.
  window.webContents.setWindowOpenHandler(({ url }) => {
    let parsed = null;
    try { parsed = new URL(String(url || '')); } catch (_) { parsed = null; }
    if (parsed && parsed.protocol === 'https:') {
      logger.write('external_link_opened', { url: parsed.href.slice(0, 500) });
      shell.openExternal(parsed.href);
    } else {
      logger.write('window_open_denied', { url: String(url || '').slice(0, 500) });
    }
    return { action: 'deny' };
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
    if (app.isQuitting || quitToTray) return;
    // A window that was closed without an explicit quit happens only when the
    // renderer crashed or the OS closed it. Do not silently keep working in
    // that case; quit cleanly.
    requestQuit();
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
  // Feature 3: Explorer "Send To LecturePack" and any second launch forward
  // file paths into the already-running instance. The second-instance event
  // carries the full command line; file paths are the non-flag arguments.
  app.on('second-instance', (_event, commandLine) => {
    const window = activeSession && activeSession.window;
    if (window && !window.isDestroyed()) {
      if (window.isMinimized()) window.restore();
      window.show();
      window.focus();
      if (process.platform === 'win32') window.flashFrame(true);
    }
    const paths = extractFileArguments(commandLine);
    if (paths.length && activeSession) {
      void importMultiplePaths(activeSession, paths);
    }
  });

  app.whenReady().then(() => {
  // The production window is a focused desktop surface, not a browser shell.
  // Removing the application menu also prevents Alt from resurrecting the
  // default File/Edit/View/Window menu on Windows.
  Menu.setApplicationMenu(null);
  registerAssetProtocol();
  loadCloseToTrayPreference();
  createProductionWindow();
  // First-launch file arguments (e.g. Windows "Send To" when no instance is
  // running) arrive in this process's own argv.
  const initialPaths = extractFileArguments(process.argv);
  if (initialPaths.length) {
    // Wait for the page and sidecar to be ready before importing.
    const window = activeSession && activeSession.window;
    if (window && !window.isDestroyed()) {
      window.webContents.once('did-finish-load', () => {
        // The sidecar needs a moment to become ready; the import itself is
        // queued by the sidecar once its startup completes.
        setTimeout(() => {
          if (activeSession) void importMultiplePaths(activeSession, initialPaths);
        }, 2500);
      });
    }
  }
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
