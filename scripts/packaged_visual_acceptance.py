"""Small packaged-app visual acceptance gate for the beta release.

This is deliberately a single script, not a test framework.  It launches the
frozen executable with a disposable data/WebEngine profile, drives the existing
UI through the DevTools Protocol and Win32 file dialog, samples the real
top-level window, and writes one recording plus a compact JSON report.

Usage (Windows, from the repository root)::

    python scripts/packaged_visual_acceptance.py --idle-seconds 300 --runs 3

The default output is under ``%TEMP%``.  The script never points at the normal
LecturePackData directory and restores the saved LecturePack theme setting when
it exits.  ``QTWEBENGINE_CHROMIUM_FLAGS`` is used only to give each run a fresh
WebEngine storage directory; no GPU or renderer flags are changed.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.request

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - project requirements provide numpy via OpenCV
    raise SystemExit("packaged_visual_acceptance requires numpy") from exc

try:
    import cv2
except ImportError as exc:  # pragma: no cover - project requirements provide OpenCV
    raise SystemExit("packaged_visual_acceptance requires OpenCV") from exc

try:
    import mss
except ImportError:  # Pillow remains a supported capture fallback.
    mss = None

from PIL import Image, ImageGrab


if sys.platform != "win32":  # pragma: no cover - the gate is intentionally Windows-only
    raise SystemExit("packaged_visual_acceptance is Windows-only")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "app" / "dist" / "LecturePack" / "LecturePack.exe"
DEFAULT_VIDEO = ROOT / "app" / "assets" / "demo" / "demo_lecture.mp4"
APP_NAME = "LecturePack"


def current_git_commit() -> str:
    """Return the source revision recorded in the visual evidence report."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


VISUAL_BASELINE_COMMIT = current_git_commit()
WM_CLOSE = 0x0010
WM_SETTEXT = 0x000C
WM_COMMAND = 0x0111
WM_CHAR = 0x0102
BM_CLICK = 0x00F5
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_A = 0x41
VK_D = 0x44
VK_L = 0x4C
VK_MENU = 0x12
VK_O = 0x4F
IDOK = 1
FILENAME_EDIT_ID = 0x47C
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def _window_debug(hwnd: int) -> str:
    children = [
        f"{_class_name(child)}#{user32.GetDlgCtrlID(child)}:{_window_text(child)!r}"
        for child in _child_windows(hwnd)
        if user32.IsWindowVisible(child)
    ]
    return f"title={_window_text(hwnd)!r}, class={_class_name(hwnd)!r}, children={children[:40]!r}"


def _visible_windows_for_pid(pid: int) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> int:
        if not user32.IsWindowVisible(hwnd):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found


def _child_windows(parent: int) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> int:
        found.append(hwnd)
        return True

    user32.EnumChildWindows(parent, callback, 0)
    return found


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetWindowRect failed")
    return rect.left, rect.top, rect.right, rect.bottom


def _wait_for_window(pid: int, timeout: float = 60.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = _visible_windows_for_pid(pid)
        named = [hwnd for hwnd in windows if APP_NAME.lower() in _window_text(hwnd).lower()]
        if len(named) == 1:
            return named[0]
        if len(windows) == 1:
            return windows[0]
        if pid <= 0:
            break
        time.sleep(0.15)
    raise TimeoutError(f"packaged process {pid} did not expose one visible window")


def _activate(hwnd: int) -> None:
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


def _focus(hwnd: int) -> None:
    target_thread = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_thread))
    current_thread = kernel32.GetCurrentThreadId()
    attached = target_thread.value not in {0, current_thread}
    if attached:
        user32.AttachThreadInput(current_thread, target_thread.value, True)
    try:
        _activate(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread.value, False)


def _resize(hwnd: int, width: int, height: int) -> tuple[int, int, int, int]:
    left, top, _right, _bottom = _window_rect(hwnd)
    if not user32.SetWindowPos(
        hwnd,
        0,
        left,
        top,
        int(width),
        int(height),
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    ):
        raise OSError("SetWindowPos failed")
    _activate(hwnd)
    return _window_rect(hwnd)


def _post_close(hwnd: int, proc: subprocess.Popen[str], timeout: float = 20.0) -> int | None:
    if user32.IsWindow(hwnd):
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            return proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait(timeout=5)


def _press(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _chord(*vks: int) -> None:
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _type_unicode(text: str) -> None:
    for char in text:
        code = ord(char)
        user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
        user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)


def _submit_file_dialog(dialog: int) -> None:
    buttons = [
        hwnd for hwnd in _child_windows(dialog)
        if _class_name(hwnd).lower() == "button"
        and "open" in _window_text(hwnd).lower()
    ]
    if buttons:
        button = buttons[0]
        user32.SendMessageW(button, BM_CLICK, 0, 0)
        if user32.IsWindow(dialog) and user32.IsWindowVisible(dialog):
            left, top, right, bottom = _window_rect(button)
            _activate(dialog)
            user32.SetCursorPos((left + right) // 2, (top + bottom) // 2)
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if not user32.IsWindow(dialog) or not user32.IsWindowVisible(dialog):
                return
        user32.SendMessageW(dialog, WM_COMMAND, IDOK, button)
    else:
        user32.SendMessageW(dialog, WM_COMMAND, IDOK, 0)
    _focus(dialog)
    _chord(VK_MENU, VK_O)
    _press(VK_RETURN)


def _filename_edit(dialog: int) -> int:
    for child in _child_windows(dialog):
        if (
            _class_name(child).lower() in {"edit", "qlineedit"}
            and user32.GetDlgCtrlID(child) == FILENAME_EDIT_ID
        ):
            return child
    return 0


def _set_edit_text(edit: int, value: str) -> None:
    user32.SendMessageW(edit, WM_SETTEXT, 0, "")
    for char in value:
        user32.SendMessageW(edit, WM_CHAR, ord(char), 0)


def _dialog_contains(dialog: int, value: str) -> bool:
    needle = value.lower()
    return any(needle in _window_text(child).lower() for child in _child_windows(dialog))


def _choose_file_dialog(pid: int, path: Path, timeout: float = 15.0) -> None:
    """Fill the native Qt file dialog without relying on pyautogui."""
    deadline = time.monotonic() + timeout
    dialog = 0
    while time.monotonic() < deadline:
        candidates = [
            hwnd
            for hwnd in _visible_windows_for_pid(pid)
            if "LecturePack" not in _window_text(hwnd)
        ]
        named_dialog = user32.FindWindowW(None, "Choose a lecture video")
        if named_dialog and user32.IsWindowVisible(named_dialog):
            candidates.insert(0, named_dialog)
        if candidates:
            dialog = candidates[0]
            break
        time.sleep(0.1)
    if not dialog:
        raise TimeoutError("file dialog did not appear after Browse")

    # Put the common dialog in the containing folder through its address bar.
    # Alt+D is the stable Windows shortcut; Ctrl+L is retained as a fallback
    # for builds that expose the newer Explorer location control.
    _focus(dialog)
    _chord(VK_MENU, VK_D)
    _chord(VK_CONTROL, VK_A)
    _type_unicode(str(path.parent))
    _press(VK_RETURN)
    time.sleep(0.7)
    if not _dialog_contains(dialog, str(path.parent)):
        _focus(dialog)
        _chord(VK_CONTROL, VK_L)
        _chord(VK_CONTROL, VK_A)
        _type_unicode(str(path.parent))
        _press(VK_RETURN)
        time.sleep(0.7)
    filename_edit = _filename_edit(dialog)
    if not filename_edit:
        edits = [
            hwnd for hwnd in _child_windows(dialog)
            if _class_name(hwnd).lower() in {"edit", "qlineedit"}
        ]
        empty_edits = [hwnd for hwnd in edits if not _window_text(hwnd)]
        filename_edit = (empty_edits or edits or [0])[0]
    if filename_edit:
        _set_edit_text(filename_edit, path.name)
        _submit_file_dialog(dialog)
    time.sleep(0.7)
    if user32.IsWindow(dialog) and user32.IsWindowVisible(dialog):
        raise RuntimeError(f"could not select video in file dialog: {path}; {_window_debug(dialog)}")


class CDPError(RuntimeError):
    pass


class CDP:
    """Minimal raw-WebSocket Chrome DevTools Protocol client."""

    def __init__(self, websocket_url: str, timeout: float = 12.0):
        from urllib.parse import urlsplit

        parsed = urlsplit(websocket_url)
        host, port = parsed.hostname, parsed.port
        if not host or not port:
            raise CDPError(f"invalid DevTools websocket URL: {websocket_url}")
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {parsed.path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("DevTools websocket closed during handshake")
            response += chunk
        if not response.startswith(b"HTTP/1.1 101"):
            raise CDPError(f"DevTools websocket handshake failed: {response[:120]!r}")
        self._next_id = 1
        self._lock = threading.Lock()

    def _send(self, payload: bytes) -> None:
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes((0x81, 0x80 | length))
        elif length < (1 << 16):
            header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", length)
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", length)
        body = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.sock.sendall(header + mask + body)

    def _recv_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        while size:
            chunk = self.sock.recv(size)
            if not chunk:
                raise CDPError("DevTools websocket closed")
            chunks.append(chunk)
            size -= len(chunk)
        return b"".join(chunks)

    def _recv(self) -> tuple[int, bytes]:
        first, second = self._recv_exact(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        masked = bool(second & 0x80)
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, payload

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            call_id = self._next_id
            self._next_id += 1
            self._send(json.dumps({"id": call_id, "method": method, "params": params or {}}).encode())
            while True:
                opcode, payload = self._recv()
                if opcode == 0x9:  # ping
                    self._send(payload)
                    continue
                if opcode == 0x8:
                    raise CDPError("DevTools websocket closed")
                if opcode != 0x1:
                    continue
                message = json.loads(payload.decode("utf-8"))
                if message.get("id") != call_id:
                    continue
                if "error" in message:
                    raise CDPError(f"{method}: {message['error']}")
                return message.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        if "exceptionDetails" in result:
            raise CDPError(f"JavaScript exception: {result['exceptionDetails']}")
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise CDPError(remote.get("description", "JavaScript evaluation failed"))
        return remote.get("value")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _cdp_target(port: int, timeout: float = 60.0) -> CDP:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as response:
                targets = json.loads(response.read().decode("utf-8"))
            pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
            if pages:
                return CDP(pages[0]["webSocketDebuggerUrl"])
        except Exception as exc:  # the renderer comes up after the native window
            last_error = str(exc)
        time.sleep(0.2)
    raise TimeoutError(f"DevTools page target did not appear on port {port}: {last_error}")


TELEMETRY_INSTALL = r"""
(() => {
  if (window.__lpVisual) return window.__lpVisual.snapshot();
  const state = {
    themeChanges: [], topLevelDomReplacements: 0, demoOverlayRemounts: 0,
    renderLikeWrites: 0, identicalDataWrites: 0, writesByTarget: {},
    identicalByTarget: {}, instrumentationErrors: []
  };
  const renderTargets = new Set([
    'pipeline-stages', 'proc-log', 'side-job-status', 'jobs-grid',
    'slide-list', 'timeline-ticks', 'tour-progress', 'guided-tour-overlay'
  ]);
  const demoIdentity = new Set([
    'guided-tour-overlay', 'guided-tour-card', 'tour-spotlight-box',
    'tour-arrow', 'demo-review-actions', 'demo-study-actions'
  ]);
  function targetName(target) { return target && (target.id || target.tagName || 'unknown'); }
  function noteWrite(target, property, before, value) {
    const id = targetName(target), next = String(value == null ? '' : value);
    if (renderTargets.has(id)) {
      state.renderLikeWrites += 1;
      state.writesByTarget[id] = (state.writesByTarget[id] || 0) + 1;
      if (String(before == null ? '' : before) === next) {
        state.identicalDataWrites += 1;
        state.identicalByTarget[id] = (state.identicalByTarget[id] || 0) + 1;
      }
    }
  }
  function patchSetter(proto, property) {
    try {
      const descriptor = Object.getOwnPropertyDescriptor(proto, property);
      if (!descriptor || !descriptor.set || !descriptor.get) return;
      Object.defineProperty(proto, property, {
        configurable: descriptor.configurable, enumerable: descriptor.enumerable,
        get: descriptor.get, set(value) {
          const before = descriptor.get.call(this);
          noteWrite(this, property, before, value);
          descriptor.set.call(this, value);
        }
      });
    } catch (error) { state.instrumentationErrors.push(String(error)); }
  }
  patchSetter(Element.prototype, 'innerHTML');
  patchSetter(Node.prototype, 'textContent');
  const themeObserver = new MutationObserver(records => records.forEach(record => {
    if (record.attributeName === 'data-theme') {
      state.themeChanges.push({at_ms: Date.now(), value: document.documentElement.dataset.theme || ''});
    }
  }));
  themeObserver.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  const bodyObserver = new MutationObserver(records => records.forEach(record => {
    if (record.type !== 'childList') return;
    if ((record.target === document.body || record.target === document.getElementById('app')) &&
        (record.addedNodes.length || record.removedNodes.length)) state.topLevelDomReplacements += 1;
    [...record.addedNodes, ...record.removedNodes].forEach(node => {
      if (node.nodeType === 1 && demoIdentity.has(node.id)) state.demoOverlayRemounts += 1;
    });
  }));
  bodyObserver.observe(document.body, {subtree: true, childList: true});
  window.__lpVisual = {
    snapshot() { return JSON.parse(JSON.stringify(state)); },
    dispose() { themeObserver.disconnect(); bodyObserver.disconnect(); delete window.__lpVisual; }
  };
  return window.__lpVisual.snapshot();
})()
"""


METRICS_JS = r"""
(() => {
  const visible = el => !!(el && !el.hidden && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const rect = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {left:r.left, top:r.top, right:r.right, bottom:r.bottom,
      width:r.width, height:r.height};
  };
  const screenNames = ['home','process','review','transcript','study','exports','settings'];
  const screens = {};
  screenNames.forEach(name => {
    const el = document.querySelector('[data-screen="' + name + '"]');
    screens[name] = !!(el && !el.hidden);
  });
  const overlay = document.getElementById('guided-tour-overlay');
  const runtime = document.getElementById('runtime-setup-overlay');
  const runtimeStates = ['gate','confirm','repairing','offline','failed','diagnostics','ready','checking','checklist'];
  const runtimeState = visible(runtime) && runtimeStates.find(name => {
    const panel = runtime && runtime.querySelector('[data-runtime-state="' + name + '"]');
    return !!(panel && !panel.hidden);
  }) || '';
  const onboarding = document.getElementById('onb-overlay');
  const label = document.getElementById('tour-step-label');
  const phase = label && label.textContent.toLowerCase().indexOf('demo') >= 0
    ? label.textContent.toLowerCase().replace(/^.*demo\s*[·.-]?\s*/, '').trim() : '';
  const targets = {import:'#dropzone', processing:'#pipeline-stages', review:'#demo-review-actions',
    study:'#demo-study-actions', exports:'#btn-export-all'};
  const target = targets[phase] ? document.querySelector(targets[phase]) : null;
  const nav = document.querySelector('.lp-nav-list');
  const completion = document.getElementById('proc-completion');
  const source = document.getElementById('proc-source-name');
  const overlayVisible = visible(overlay);
  return {
    readyState: document.readyState,
    theme: document.documentElement.dataset.theme || '',
    viewport: {width: window.innerWidth, height: window.innerHeight},
    screen: Object.keys(screens).find(name => screens[name]) || '',
    screens,
    processing: {complete: visible(completion), source: source ? source.textContent.trim() : ''},
    runtime: {visible: visible(runtime), state: runtimeState,
      checklist: visible(runtime && runtime.querySelector('[data-runtime-state="checklist"]')),
      text: visible(runtime) ? runtime.innerText.slice(0, 300) : ''},
    onboarding: {visible: visible(onboarding), detected: visible(onboarding && document.getElementById('onb-detected'))},
    sidebar: nav ? {visible: visible(nav), rect: rect(nav), clientWidth: nav.clientWidth,
      scrollWidth: nav.scrollWidth, navVisible: [...nav.querySelectorAll('.lp-nav')].filter(visible).length} : null,
    tour: {visible: overlayVisible, phase, label: label ? label.textContent.trim() : '',
      target: rect(target), spotlight: rect(document.getElementById('tour-spotlight-box')),
      arrow: rect(document.getElementById('tour-arrow')), arrowHidden: !!document.getElementById('tour-arrow')?.hidden}
  };
})()
"""


def _visible_metric(value: Any) -> bool:
    return bool(value and isinstance(value, dict) and value.get("width", 0) > 0 and value.get("height", 0) > 0)


@dataclass
class FrameObservation:
    timestamp: float
    frame: np.ndarray
    mode: str
    transition: str | None
    resize_active: bool


class FrameAnalyzer:
    """Compare real window pixels and preserve only evidence that needs review."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.flag_dir = output_dir / "flagged-frames"
        self.flag_dir.mkdir(parents=True, exist_ok=True)
        self.previous: np.ndarray | None = None
        self.post_transition_until = 0.0
        self.last_flag_at: dict[str, float] = {}
        self.flags: list[dict[str, Any]] = []
        self.frame_count = 0
        self.action_frames = 0
        self.slow_frames = 0
        self.last_frame: np.ndarray | None = None
        self.last_frame_lock = threading.Lock()

    @staticmethod
    def _black_white_fraction(frame: np.ndarray) -> tuple[float, float]:
        roi = frame[30:] if frame.shape[0] > 80 else frame
        black = float((np.max(roi, axis=2) <= 7).mean()) if roi.size else 0.0
        white = float((np.min(roi, axis=2) >= 249).mean()) if roi.size else 0.0
        return black, white

    @staticmethod
    def _difference(current: np.ndarray, previous: np.ndarray) -> tuple[float, float]:
        if current.shape != previous.shape:
            return 0.0, 0.0
        delta = np.abs(current.astype(np.int16) - previous.astype(np.int16))
        return float((delta.max(axis=2) > 35).mean()), float(delta.mean())

    def _save_frame(self, frame: np.ndarray, stamp: float, kind: str) -> str:
        name = f"{dt.datetime.fromtimestamp(stamp, dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}_{kind}.png"
        path = self.flag_dir / name
        Image.fromarray(frame[:, :, ::-1]).save(path)
        return str(path)

    def flag(self, kind: str, observation: FrameObservation | None, details: dict[str, Any], *, severity: str = "error") -> None:
        now = time.time()
        # Keep timestamps useful without producing hundreds of duplicate images
        # while a single blank surface persists.
        if now - self.last_flag_at.get(kind, 0.0) < 0.25:
            return
        self.last_flag_at[kind] = now
        frame_path = None
        if observation is not None:
            frame_path = self._save_frame(observation.frame, now, kind.replace(" ", "-"))
        self.flags.append({
            "kind": kind,
            "severity": severity,
            "timestamp": iso_now(),
            "frame": frame_path,
            "details": details,
        })

    def external_flag(self, kind: str, details: dict[str, Any], *, severity: str = "error") -> None:
        with self.last_frame_lock:
            frame = None if self.last_frame is None else self.last_frame.copy()
        observation = FrameObservation(time.time(), frame, "dom", None, False) if frame is not None else None
        self.flag(kind, observation, details, severity=severity)

    def consume(self, observation: FrameObservation) -> None:
        self.frame_count += 1
        if observation.mode == "action":
            self.action_frames += 1
        else:
            self.slow_frames += 1
        with self.last_frame_lock:
            self.last_frame = observation.frame.copy()

        black, white = self._black_white_fraction(observation.frame)
        intentional = observation.transition in {"navigation", "theme"}
        if black >= 0.97 and not intentional:
            self.flag("unexpected-black-frame", observation, {"black_fraction": round(black, 4), "resize": observation.resize_active})
        elif white >= 0.97 and not intentional:
            self.flag("unexpected-white-frame", observation, {"white_fraction": round(white, 4), "resize": observation.resize_active})

        if observation.transition:
            self.post_transition_until = observation.timestamp + 0.35
        if self.previous is not None and observation.timestamp >= self.post_transition_until and not observation.transition:
            changed, mean_delta = self._difference(observation.frame, self.previous)
            if changed >= 0.75 and mean_delta >= 40.0:
                self.flag(
                    "large-whole-window-change",
                    observation,
                    {"changed_fraction": round(changed, 4), "mean_delta": round(mean_delta, 2)},
                )
        self.previous = observation.frame.copy()


class WindowSampler:
    def __init__(self, hwnd: int, analyzer: FrameAnalyzer, fallback_writer: "SampledVideo | None" = None):
        self.hwnd = hwnd
        self.analyzer = analyzer
        self.fallback_writer = fallback_writer
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.mode = "slow"
        self.transition_until = 0.0
        self.transition_reason: str | None = None
        self.resize_active = False
        self.thread: threading.Thread | None = None

    def set_mode(self, mode: str) -> None:
        with self.state_lock:
            self.mode = "action" if mode == "action" else "slow"

    def expect_transition(self, reason: str, duration: float = 0.65) -> None:
        with self.state_lock:
            self.transition_until = max(self.transition_until, time.time() + duration)
            self.transition_reason = reason

    def set_resize_active(self, active: bool) -> None:
        with self.state_lock:
            self.resize_active = active

    def _capture(self, sct: Any = None) -> np.ndarray:
        left, top, right, bottom = _window_rect(self.hwnd)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise RuntimeError("LecturePack window has a non-positive size")
        if sct is not None:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            return np.asarray(shot, dtype=np.uint8)[:, :, :3].copy()
        image = ImageGrab.grab(bbox=(left, top, right, bottom), include_layered_windows=True)
        return np.asarray(image.convert("RGB"), dtype=np.uint8)[:, :, ::-1].copy()

    def _run(self) -> None:
        sct = mss.MSS() if mss is not None else None
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                with self.state_lock:
                    mode = self.mode
                    transition = self.transition_reason if time.time() < self.transition_until else None
                    resize_active = self.resize_active
                try:
                    frame = self._capture(sct)
                    observation = FrameObservation(time.time(), frame, mode, transition, resize_active)
                    if self.fallback_writer is not None:
                        self.fallback_writer.write(frame)
                    self.analyzer.consume(observation)
                except Exception as exc:
                    self.analyzer.external_flag("window-capture-error", {"error": str(exc)})
                interval = 0.1 if mode == "action" else 0.6
                delay = max(0.01, interval - (time.monotonic() - started))
                self.stop_event.wait(delay)
        finally:
            if sct is not None:
                sct.close()

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="lp-visual-sampler", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)


class SampledVideo:
    """Fallback recording when the bundled ffmpeg lacks gdigrab."""

    def __init__(self, path: Path):
        self.path = path
        self.writer: cv2.VideoWriter | None = None
        self.size: tuple[int, int] | None = None

    def write(self, frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        if self.writer is None:
            self.size = (width, height)
            self.writer = cv2.VideoWriter(
                str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, self.size
            )
            if not self.writer.isOpened():
                self.writer.release()
                self.writer = None
                raise RuntimeError("OpenCV could not open the fallback recording writer")
        if self.size != (width, height):
            frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
        self.writer.write(frame)

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None


class ScreenRecorder:
    def __init__(self, ffmpeg: Path | None, output: Path):
        self.ffmpeg = ffmpeg
        self.output = output
        self.process: subprocess.Popen[bytes] | None = None
        self.log_path = output.with_suffix(".ffmpeg.log")

    def start(self) -> bool:
        if self.ffmpeg is None or not self.ffmpeg.is_file():
            return False
        log = self.log_path.open("wb")
        command = [
            str(self.ffmpeg), "-y", "-loglevel", "error",
            "-f", "gdigrab", "-framerate", "10", "-draw_mouse", "1",
            "-i", "desktop", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(self.output),
        ]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            time.sleep(0.8)
            if self.process.poll() is not None:
                self.process = None
                log.close()
                return False
            return True
        except OSError:
            log.close()
            return False

    def stop(self) -> bool:
        if self.process is None:
            return False
        try:
            if self.process.stdin is not None:
                self.process.stdin.write(b"q\n")
                self.process.stdin.flush()
            self.process.wait(timeout=12)
        except Exception:
            self.process.terminate()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        return self.output.is_file() and self.output.stat().st_size > 0


def _set_saved_theme(value: str | None) -> None:
    """Set the app's QSettings theme; used only for the disposable gate."""
    from PySide6.QtCore import QSettings

    settings = QSettings(APP_NAME, APP_NAME)
    if value is None:
        settings.remove("theme")
    else:
        settings.setValue("theme", value)
    settings.sync()


def _read_saved_theme() -> str | None:
    from PySide6.QtCore import QSettings

    settings = QSettings(APP_NAME, APP_NAME)
    value = settings.value("theme", None)
    return str(value) if value in {"light", "dark"} else None


class VisualRun:
    def __init__(self, exe: Path, video: Path, output_dir: Path, idle_seconds: float, keep_profile: bool):
        self.exe = exe
        self.video = video
        self.output_dir = output_dir
        self.idle_seconds = idle_seconds
        self.keep_profile = keep_profile
        self.analyzer = FrameAnalyzer(output_dir)
        self.recording = ScreenRecorder(self._ffmpeg_path(), output_dir / "screen-recording.mp4")
        self.fallback_video = SampledVideo(output_dir / "screen-recording-fallback.mp4")
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.hwnd = 0
        self.cdp: CDP | None = None
        self.sampler: WindowSampler | None = None
        self.profile: Path | None = None
        self.port = 0
        self.dom_history: list[dict[str, Any]] = []
        self.launches: list[dict[str, Any]] = []
        self.resize_results: list[dict[str, Any]] = []
        self.intentional_theme_windows: list[tuple[float, float]] = []
        self.phase_transition_until = 0.0
        self.last_phase = ""
        self.processing_result: dict[str, Any] = {}
        self.last_metrics: dict[str, Any] | None = None
        self.stage = "initializing"

    @staticmethod
    def _ffmpeg_path() -> Path | None:
        candidates = [
            DEFAULT_EXE.parent / "bin" / "ffmpeg.exe",
            Path(shutil.which("ffmpeg") or ""),
        ]
        return next((path for path in candidates if str(path) and path.is_file()), None)

    def _new_port(self) -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def launch(self, label: str) -> None:
        if self.profile is None:
            self.profile = Path(tempfile.mkdtemp(prefix="lecturepack-visual-profile-"))
        self.port = self._new_port()
        self.log_handle = (self.output_dir / f"app-{len(self.launches) + 1}.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env["LECTUREPACK_DATA_DIR"] = str(self.profile)
        env["QTWEBENGINE_REMOTE_DEBUGGING"] = str(self.port)
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = f"--user-data-dir={self.profile / 'webengine'}"
        started = time.monotonic()
        self.proc = subprocess.Popen(
            [str(self.exe)], cwd=str(self.exe.parent), env=env,
            stdout=self.log_handle, stderr=subprocess.STDOUT,
        )
        try:
            self.hwnd = _wait_for_window(self.proc.pid)
            launch_seconds = time.monotonic() - started
            self.launches.append({
                "label": label,
                "started_at": iso_now(),
                "seconds_to_window": round(launch_seconds, 3),
                "pid": self.proc.pid,
            })
            if len(self.launches) == 1 and self.recording.start():
                fallback = None
            else:
                fallback = self.fallback_video
            self.analyzer.previous = None
            self.sampler = WindowSampler(self.hwnd, self.analyzer, fallback)
            self.sampler.start()
            self.cdp = _cdp_target(self.port)
            self.cdp.call("Runtime.enable")
            self.cdp.evaluate(TELEMETRY_INSTALL)
        except Exception:
            if self.proc is not None:
                _post_close(self.hwnd, self.proc, timeout=3)
            raise

    def _require_cdp(self) -> CDP:
        if self.cdp is None:
            raise RuntimeError("DevTools is not attached")
        return self.cdp

    def collect(self) -> dict[str, Any]:
        if self.hwnd and user32.IsHungAppWindow(self.hwnd):
            self.analyzer.external_flag("ui-stall", {"stage": self.stage, "reason": "IsHungAppWindow"})
        metrics = self._require_cdp().evaluate(METRICS_JS)
        telemetry = self._require_cdp().evaluate("window.__lpVisual ? window.__lpVisual.snapshot() : null")
        item = {"timestamp": iso_now(), "metrics": metrics, "telemetry": telemetry}
        self.dom_history.append(item)
        self.last_metrics = metrics
        self._inspect_metrics(metrics, telemetry)
        return metrics

    def _inspect_metrics(self, metrics: dict[str, Any] | None, telemetry: dict[str, Any] | None) -> None:
        if not isinstance(metrics, dict):
            return
        sidebar = metrics.get("sidebar")
        if not sidebar or not sidebar.get("visible") or not _visible_metric(sidebar.get("rect")):
            self.analyzer.external_flag("sidebar-disappeared", {"sidebar": sidebar})
        elif sidebar.get("scrollWidth", 0) > sidebar.get("clientWidth", 0) + 2:
            self.analyzer.external_flag("sidebar-overflow", {"sidebar": sidebar})
        elif sidebar.get("navVisible", 0) < 7:
            self.analyzer.external_flag("sidebar-navigation-missing", {"sidebar": sidebar})

        tour = metrics.get("tour") or {}
        phase = tour.get("phase", "")
        if phase != self.last_phase:
            self.last_phase = phase
            self.phase_transition_until = time.time() + 0.45
        if tour.get("visible") and phase in {"import", "processing", "review", "study", "exports"} and time.time() >= self.phase_transition_until:
            target, spotlight, arrow = tour.get("target"), tour.get("spotlight"), tour.get("arrow")
            aligned = (
                _visible_metric(target) and _visible_metric(spotlight) and _visible_metric(arrow)
                and not tour.get("arrowHidden", True)
                and spotlight["left"] <= target["left"] + 12
                and spotlight["top"] <= target["top"] + 12
                and spotlight["right"] + 12 >= target["right"]
                and spotlight["bottom"] + 12 >= target["bottom"]
            )
            if not aligned:
                self.analyzer.external_flag("demo-overlay-misaligned", {"phase": phase, "tour": tour})

        if telemetry:
            if telemetry.get("topLevelDomReplacements", 0) > 3:
                self.analyzer.external_flag("repeated-top-level-dom-replacement", telemetry, severity="diagnostic")
            if telemetry.get("demoOverlayRemounts", 0) > 0:
                self.analyzer.external_flag("demo-overlay-remount", telemetry, severity="diagnostic")

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], label: str, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"packaged process exited during {label}: {self.proc.returncode}")
            try:
                metrics = self.collect()
                if predicate(metrics):
                    return metrics
            except Exception as exc:
                last_error = str(exc)
                self.analyzer.external_flag("ui-stall", {"stage": self.stage, "during": label, "error": last_error})
            time.sleep(0.25)
        runtime = self.last_metrics.get("runtime") if isinstance(self.last_metrics, dict) else None
        raise TimeoutError(f"timed out waiting for {label}; last error: {last_error}; last runtime: {runtime}")

    def click(self, selector: str, *, reason: str = "navigation") -> None:
        if self.sampler is not None:
            self.sampler.set_mode("action")
            self.sampler.expect_transition(reason)
        expression = f"(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return false; el.click(); return true; }})()"
        try:
            found = self._require_cdp().evaluate(expression)
        except (TimeoutError, socket.timeout) as exc:
            self.analyzer.external_flag("ui-stall", {"stage": self.stage, "during": f"click {selector}", "error": str(exc)})
            raise
        if found is not True:
            raise RuntimeError(f"UI element not found: {selector}")
        time.sleep(0.08)

    def click_file_dialog(self, selector: str) -> None:
        """Open a native file dialog without waiting on its modal CDP call.

        Qt's file dialog blocks the WebEngine thread until the native dialog is
        dismissed. A synchronous Runtime.evaluate therefore looks like a
        renderer stall even when the app is behaving normally. Keep the CDP
        call on a worker while Win32 selects the file, then resume normal CDP
        collection after the dialog has closed.
        """
        if self.sampler is not None:
            self.sampler.set_mode("action")
            self.sampler.expect_transition("navigation")
        expression = f"(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return false; el.click(); return true; }})()"
        outcome: dict[str, Any] = {}

        def invoke() -> None:
            try:
                outcome["value"] = self._require_cdp().evaluate(expression)
            except Exception as exc:  # the native dialog can delay the reply past the socket timeout
                outcome["error"] = exc

        worker = threading.Thread(target=invoke, name="lp-open-file-dialog", daemon=True)
        worker.start()
        try:
            if self.proc is None:
                raise RuntimeError("no process for file dialog")
            _choose_file_dialog(self.proc.pid, self.video)
        finally:
            worker.join(timeout=15)
        error = outcome.get("error")
        if error is not None and not isinstance(error, (TimeoutError, socket.timeout)):
            raise error
        if outcome.get("value") is False:
            raise RuntimeError(f"UI element not found: {selector}")

    def mark_theme_intent(self, duration: float = 1.2) -> None:
        now = time.time() * 1000
        self.intentional_theme_windows.append((now, now + duration * 1000))
        if self.sampler is not None:
            self.sampler.set_mode("action")
            self.sampler.expect_transition("theme", duration)

    def set_theme_through_bridge(self, theme: str) -> None:
        self.mark_theme_intent()
        self._require_cdp().evaluate(f"lpBridge.call('set_setting', 'theme', {json.dumps(theme)})")
        self.wait_for(lambda m: m.get("theme") == theme, f"theme {theme}", timeout=8)

    def idle(self) -> None:
        if self.sampler is not None:
            self.sampler.set_mode("slow")
        deadline = time.monotonic() + self.idle_seconds
        while time.monotonic() < deadline:
            self.collect()
            time.sleep(min(1.0, max(0.1, deadline - time.monotonic())))

    def resize_matrix(self) -> None:
        if self.sampler is None:
            raise RuntimeError("sampler is not running")
        left, top, right, bottom = _window_rect(self.hwnd)
        normal_width, normal_height = right - left, bottom - top
        minimum_width, minimum_height = 480, max(560, normal_height)
        for cycle in range(1, 5):
            before_flags = len(self.analyzer.flags)
            self.sampler.set_mode("action")
            self.sampler.set_resize_active(True)
            minimum_rect = _resize(self.hwnd, minimum_width, minimum_height)
            time.sleep(0.65)
            minimum_metrics = self.collect()
            self.sampler.set_resize_active(False)
            normal_rect = _resize(self.hwnd, normal_width, normal_height)
            time.sleep(0.65)
            normal_metrics = self.collect()
            self.resize_results.append({
                "cycle": cycle,
                "requested_minimum": [minimum_width, minimum_height],
                "observed_minimum": list(minimum_rect),
                "observed_normal": list(normal_rect),
                "minimum_sidebar": minimum_metrics.get("sidebar"),
                "normal_sidebar": normal_metrics.get("sidebar"),
                "new_flags": len(self.analyzer.flags) - before_flags,
            })

    def import_and_process(self) -> None:
        self.sampler.set_mode("action") if self.sampler else None
        self.click(".lp-nav[data-nav='home']")
        self.wait_for(lambda m: m.get("screen") == "home", "Home before real import")
        self.click_file_dialog("#btn-browse")
        if self.proc is None:
            raise RuntimeError("no process for file dialog")
        self.wait_for(
            lambda m: m.get("onboarding", {}).get("detected")
            or m.get("processing", {}).get("source") not in {"", "No lecture loaded"},
            "real video import",
            timeout=30,
        )
        self.click("#btn-start-processing")
        self.wait_for(lambda m: m.get("screen") == "process", "processing screen", timeout=15)
        if self.sampler is not None:
            self.sampler.set_mode("slow")
        completion = self.wait_for(
            lambda m: bool(m.get("processing", {}).get("complete")),
            "real video processing completion",
            timeout=600,
        )
        jobs = list((self.profile / "jobs").glob("*/manifest.json")) if self.profile else []
        self.processing_result = {
            "ok": bool(completion.get("processing", {}).get("complete")) and bool(jobs),
            "source": completion.get("processing", {}).get("source", ""),
            "job_manifests": len(jobs),
        }

    def close_current(self) -> int | None:
        if self.sampler is not None and self.proc is not None:
            self.sampler.stop()
            self.sampler = None
            code = _post_close(self.hwnd, self.proc)
        else:
            code = None
        if self.cdp is not None:
            self.cdp.close()
            self.cdp = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self.proc = None
        self.hwnd = 0
        return code

    def finish(self) -> None:
        self.close_current()
        recording_ok = self.recording.stop()
        self.fallback_video.close()
        if not recording_ok and self.fallback_video.path.is_file():
            self.recording.output = self.fallback_video.path

    def cleanup_profile(self) -> None:
        if self.profile is not None and not self.keep_profile:
            shutil.rmtree(self.profile, ignore_errors=True)


def _run_demo(run: VisualRun) -> None:
    run.stage = "demo-prompt"
    try:
        run.wait_for(lambda m: m.get("tour", {}).get("visible") and "welcome" in m.get("tour", {}).get("label", "").lower(), "guided-tour prompt", 12)
        run.click("#btn-tour-start")
    except TimeoutError:
        # A Windows profile may retain the WebEngine localStorage tour-seen
        # bit outside the disposable LecturePack data directory.  Settings has
        # the supported Replay tour action, so use it rather than mutating DOM
        # state or relying on a hidden test hook.
        run.click(".lp-nav[data-nav='settings']")
        run.wait_for(lambda m: m.get("screen") == "settings", "Settings for tour replay", 12)
        run.click("#btn-replay-tour")
    run.wait_for(lambda m: m.get("tour", {}).get("phase") == "import", "guided-tour import highlight", 10)
    run.stage = "demo-processing"
    run.click("#glowing-demo-card")
    run.wait_for(lambda m: m.get("tour", {}).get("phase") == "review", "guided demo review highlight", 180)
    run.stage = "demo-review"
    run.click("#btn-keep")
    run.wait_for(lambda m: m.get("tour", {}).get("phase") == "study", "guided demo study highlight", 15)
    run.stage = "demo-study"
    run.click("#btn-tour-next")
    run.wait_for(lambda m: m.get("tour", {}).get("phase") == "exports", "guided demo exports highlight", 15)
    run.stage = "demo-exports"
    run.click("#btn-tour-next")
    run.wait_for(lambda m: not m.get("tour", {}).get("visible"), "guided demo close", 15)


def _run_navigation_matrix(run: VisualRun) -> None:
    # The current beta.9 labels are Review and Study; these are the existing
    # History and Study Packs destinations requested by the acceptance gate.
    destinations = (
        ("Home", "home"),
        ("Processing", "process"),
        ("History", "review"),
        ("Study Packs", "study"),
        ("Settings", "settings"),
    )
    run.stage = "navigation"
    for label, screen in destinations:
        run.click(f".lp-nav[data-nav='{screen}']")
        run.wait_for(lambda m, screen=screen: m.get("screen") == screen, f"navigate {label}", 12)


def _run_theme_matrix(run: VisualRun) -> None:
    run.stage = "theme-matrix"
    for theme in ("light", "dark", "light", "dark"):
        run.mark_theme_intent()
        run.click("#btn-theme", reason="theme")
        run.wait_for(lambda m, theme=theme: m.get("theme") == theme, f"toggle theme {theme}", 10)


def _theme_diagnostics(run: VisualRun) -> dict[str, Any]:
    all_changes: list[dict[str, Any]] = []
    seen_changes: set[tuple[Any, Any]] = set()
    render: dict[str, Any] = {
        "render_like_writes": 0,
        "identical_data_writes": 0,
        "top_level_dom_replacements": 0,
        "demo_overlay_remounts": 0,
        "writes_by_target": {},
        "identical_by_target": {},
        "instrumentation_errors": [],
    }
    for item in run.dom_history:
        telemetry = item.get("telemetry") or {}
        for change in telemetry.get("themeChanges", []):
            key = (change.get("at_ms"), change.get("value"))
            if key not in seen_changes:
                seen_changes.add(key)
                all_changes.append(change)
        for key in ("renderLikeWrites", "identicalDataWrites", "topLevelDomReplacements", "demoOverlayRemounts"):
            render_key = {
                "renderLikeWrites": "render_like_writes",
                "identicalDataWrites": "identical_data_writes",
                "topLevelDomReplacements": "top_level_dom_replacements",
                "demoOverlayRemounts": "demo_overlay_remounts",
            }[key]
            render[render_key] = max(render[render_key], int(telemetry.get(key, 0) or 0))
        for key in ("writesByTarget", "identicalByTarget"):
            output_key = "writes_by_target" if key == "writesByTarget" else "identical_by_target"
            for name, count in (telemetry.get(key) or {}).items():
                render[output_key][name] = max(render[output_key].get(name, 0), int(count))
        render["instrumentation_errors"].extend(telemetry.get("instrumentationErrors", []))

    all_changes.sort(key=lambda change: change.get("at_ms", 0))
    repeated = [
        change for previous, change in zip(all_changes, all_changes[1:])
        if change.get("value") == previous.get("value")
        and change.get("at_ms", 0) - previous.get("at_ms", 0) <= 250
    ]
    if repeated:
        run.analyzer.external_flag("repeated-theme-change", {"changes": repeated}, severity="diagnostic")
    unexpected = [
        change for change in all_changes
        if not any(start - 100 <= change.get("at_ms", 0) <= end + 100 for start, end in run.intentional_theme_windows)
    ]
    if unexpected:
        run.analyzer.external_flag("unexpected-theme-change", {"changes": unexpected})
    if render["identical_data_writes"] > 30:
        run.analyzer.external_flag("repeated-identical-render", render, severity="diagnostic")
    return {
        "theme_changes": all_changes,
        "repeated_theme_changes": repeated,
        "unexpected_theme_changes": unexpected,
        **render,
    }


def run_one(exe: Path, video: Path, output_dir: Path, idle_seconds: float, keep_profile: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    run = VisualRun(exe, video, output_dir, idle_seconds, keep_profile)
    result: dict[str, Any] = {
        "started_at": iso_now(),
        "baseline_commit": VISUAL_BASELINE_COMMIT,
        "executable": str(exe),
        "video": str(video),
        "ok": False,
    }
    try:
        run.stage = "cold-light"
        _set_saved_theme("light")
        run.launch("cold-light")
        light = run.wait_for(lambda m: m.get("readyState") == "complete", "cold light page", 60)
        result["cold_light"] = {"theme": light.get("theme"), "launch": run.launches[-1]}
        if light.get("theme") != "light":
            run.analyzer.external_flag("cold-light-theme-mismatch", light)

        run.close_current()
        # Runtime admission intentionally guards settings writes before setup
        # acknowledgement.  Set the disposable QSettings value between the
        # two cold launches instead of bypassing that admission gate.
        _set_saved_theme("dark")

        run.stage = "cold-dark"
        run.launch("cold-dark")
        dark = run.wait_for(lambda m: m.get("readyState") == "complete", "cold dark page", 60)
        result["cold_dark"] = {"theme": dark.get("theme"), "launch": run.launches[-1]}
        if dark.get("theme") != "dark":
            run.analyzer.external_flag("cold-dark-theme-mismatch", dark)

        run.stage = "first-run-setup"
        run.wait_for(lambda m: m.get("runtime", {}).get("checklist"), "first-run setup checklist", 90)
        # `#btn-runtime-continue` was removed by 4cd98da and this gate was never
        # updated, so every run died here with "UI element not found" -- the
        # release gate itself was dead, which is exactly the failure mode it
        # exists to catch. "Done" clears the checklist; "Confirm & repair"
        # stays disabled when the machine is already healthy.
        run.click("#btn-runtime-done")
        run.wait_for(lambda m: not m.get("runtime", {}).get("visible"), "first-run setup close", 15)
        _run_demo(run)
        _run_navigation_matrix(run)
        run.stage = "resize-matrix"
        run.resize_matrix()
        _run_theme_matrix(run)
        run.stage = "real-import-processing"
        run.import_and_process()
        result["processing"] = run.processing_result
        run.stage = "five-minute-idle"
        run.idle()
        result["idle_seconds"] = idle_seconds

        run.stage = "reopen"
        run.close_current()
        run.launch("reopen")
        run.wait_for(lambda m: m.get("readyState") == "complete", "reopen page", 60)
        reopened = run.wait_for(lambda m: not m.get("runtime", {}).get("visible"), "reopen without setup", 90)
        result["reopen"] = {
            "ok": not reopened.get("runtime", {}).get("visible") and bool(reopened.get("screen")),
            "theme": reopened.get("theme"),
            "screen": reopened.get("screen"),
            "launch": run.launches[-1],
        }
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["stage"] = run.stage
    finally:
        try:
            run.finish()
        finally:
            result["ended_at"] = iso_now()
            result["launches"] = run.launches
            result["launch_time"] = run.launches[0].get("started_at") if run.launches else None
            result["resize_results"] = run.resize_results
            result["last_runtime"] = (run.last_metrics or {}).get("runtime")
            result["flags"] = run.analyzer.flags
            result["render"] = _theme_diagnostics(run)
            result["frame_counts"] = {
                "total": run.analyzer.frame_count,
                "action_8_to_10_fps": run.analyzer.action_frames,
                "idle_or_processing_1_to_2_fps": run.analyzer.slow_frames,
            }
            result["recording"] = str(run.recording.output)
            result["recording_exists"] = run.recording.output.is_file() and run.recording.output.stat().st_size > 0
            result["profile"] = str(run.profile) if keep_profile else "disposed"
            result["error_flags"] = [flag for flag in run.analyzer.flags if flag.get("severity") != "diagnostic"]
            result["ok"] = (
                not result["error_flags"]
                and bool(result.get("processing", {}).get("ok"))
                and bool(result.get("reopen", {}).get("ok"))
                and bool(result["recording_exists"])
                and not result.get("error")
            )
            run.cleanup_profile()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the packaged LecturePack visual acceptance sequence")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--output", type=Path, default=None, help="Evidence directory; defaults to %%TEMP%%")
    parser.add_argument("--idle-seconds", type=float, default=300.0)
    parser.add_argument("--runs", type=int, default=1, help="Number of fresh consecutive runs (default: 1)")
    parser.add_argument("--keep-profile", action="store_true", help="Keep disposable data profiles for diagnosis")
    args = parser.parse_args()
    exe = args.exe.resolve()
    video = args.video.resolve()
    if not exe.is_file():
        parser.error(f"packaged executable not found: {exe}")
    if not video.is_file():
        parser.error(f"test video not found: {video}")
    if args.runs < 1 or args.idle_seconds < 0:
        parser.error("--runs must be >= 1 and --idle-seconds must be >= 0")

    output = args.output.resolve() if args.output else Path(tempfile.gettempdir()) / f"lecturepack-visual-acceptance-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"
    output.mkdir(parents=True, exist_ok=False)
    original_theme = _read_saved_theme()
    aggregate: dict[str, Any] = {
        "started_at": iso_now(),
        "baseline_commit": VISUAL_BASELINE_COMMIT,
        "requested_runs": args.runs,
        "idle_seconds": args.idle_seconds,
        "output": str(output),
        "runs": [],
    }
    try:
        for index in range(1, args.runs + 1):
            run_output = output / f"run-{index:02d}"
            print(f"[visual] run {index}/{args.runs}: {run_output}", flush=True)
            result = run_one(exe, video, run_output, args.idle_seconds, args.keep_profile)
            aggregate["runs"].append(result)
            (output / "result.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
            print(f"[visual] run {index}: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    finally:
        _set_saved_theme(original_theme)
    aggregate["ended_at"] = iso_now()
    aggregate["ok"] = len(aggregate["runs"]) == args.runs and all(item.get("ok") for item in aggregate["runs"])
    (output / "result.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps({"ok": aggregate["ok"], "result": str(output / 'result.json')}, indent=2), flush=True)
    return 0 if aggregate["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
