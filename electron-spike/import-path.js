'use strict';

/* Shared native-path validation for the two import flows (drag-and-drop and
 * Browse for video). Both renderer entry points resolve to an absolute native
 * path, then cross this same gate before the sidecar's import_video command.
 *
 * Deliberately narrow: this module never reads file contents and exposes no
 * filesystem surface to the renderer. It only answers "is this path a real,
 * readable file?" and returns a stable error code the UI can translate.
 */

const fs = require('node:fs');
const path = require('node:path');

const IMPORT_CODES = {
  RESOLVE_FAILED: 'RESOLVE_FAILED',
  NOT_FOUND: 'NOT_FOUND',
  UNREADABLE: 'UNREADABLE',
  FFPROBE_FAILED: 'FFPROBE_FAILED'
};

function validateLocalVideoPath(rawPath) {
  const raw = typeof rawPath === 'string' ? rawPath.trim() : '';
  if (!raw) {
    return { ok: false, code: IMPORT_CODES.RESOLVE_FAILED, error: 'No file path was supplied.' };
  }
  let resolved;
  try {
    resolved = path.resolve(raw);
  } catch (_) {
    return { ok: false, code: IMPORT_CODES.RESOLVE_FAILED, error: `Could not resolve path: ${raw}` };
  }
  let exists = false;
  try { exists = fs.existsSync(resolved); } catch (_) { exists = false; }
  if (!exists) {
    return { ok: false, code: IMPORT_CODES.NOT_FOUND, error: `File not found: ${resolved}` };
  }
  let isFile = false;
  try { isFile = fs.statSync(resolved).isFile(); } catch (_) { isFile = false; }
  if (!isFile) {
    return { ok: false, code: IMPORT_CODES.NOT_FOUND, error: `Not a file: ${resolved}` };
  }
  try {
    fs.accessSync(resolved, fs.constants.R_OK);
  } catch (_) {
    return { ok: false, code: IMPORT_CODES.UNREADABLE, error: `File is not readable: ${resolved}` };
  }
  return { ok: true, path: resolved };
}

module.exports = { validateLocalVideoPath, IMPORT_CODES };
