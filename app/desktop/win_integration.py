"""Windows OS integration for LecturePack (beta.3): keep-awake, taskbar
progress, and local notifications.

Design: every OS call lives behind a small injectable seam — ``PowerRequester``
(SetThreadExecutionState), ``TaskbarButton`` (ITaskbarList3), ``Notifier``
(QSystemTrayIcon). The ``WindowsIntegration`` facade holds the seams plus the
pure policy (focus-gating, duplicate suppression, click routing, lifecycle ->
taskbar-state mapping). The facade has NO Qt / ctypes imports at module scope,
so it imports anywhere and is fully unit-testable by injecting fakes. Real seams
import their OS deps lazily and degrade to a silent no-op off Windows or when a
subsystem is unavailable — a COM/tray failure must never break the frozen EXE.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# Taskbar states (decoupled from lifecycle strings so callers map explicitly).
TB_NONE = "none"
TB_NORMAL = "normal"
TB_PAUSED = "paused"
TB_ERROR = "error"

# Notification kinds.
N_COMPLETE = "completed"
N_FAILED = "failed"
N_UPDATE = "update"
N_SMART_STUDY = "smart_study"

# Pref key -> default. Mirrors the Settings -> Notifications UI (Phase 5).
DEFAULT_PREFS = {
    "notify_complete": True,
    "notify_failed": True,
    "notify_update": True,
    "notify_smart_study": False,
    "play_sound": False,
    "only_when_unfocused": True,
}

# kind -> pref key that gates it.
_KIND_PREF = {
    N_COMPLETE: "notify_complete",
    N_FAILED: "notify_failed",
    N_UPDATE: "notify_update",
    N_SMART_STUDY: "notify_smart_study",
}


@dataclass
class Notification:
    kind: str
    title: str
    message: str
    route: str = ""          # e.g. "job:<id>", "error:<id>", "update"
    sound: bool = False


# --- seams (fakeable) ------------------------------------------------------ #
class PowerRequester:
    """Keep the system awake during processing. ES_CONTINUOUS alone never
    blocks a *manual* sleep/shutdown; we deliberately omit ES_DISPLAY_REQUIRED
    so the display may still sleep."""

    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):
        self._active = False

    def set_awake(self, on: bool) -> None:
        # Idempotent; safe to call repeatedly.
        if on == self._active:
            return
        self._active = on
        if sys.platform != "win32":
            return
        try:
            import ctypes
            flags = self._ES_CONTINUOUS | (self._ES_SYSTEM_REQUIRED if on else 0)
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass  # degrade silently

    @property
    def active(self) -> bool:
        return self._active


class TaskbarButton:
    """Windows taskbar progress via ITaskbarList3, hand-rolled with ctypes so
    there is NO new dependency (QtWinExtras was removed in Qt6; comtypes/pywin32
    are PyInstaller hazards). Any failure degrades to a silent no-op."""

    # ITaskbarList3 TBPFLAG values.
    _TBPF = {TB_NONE: 0x0, TB_NORMAL: 0x2, TB_ERROR: 0x4, TB_PAUSED: 0x8}

    def __init__(self, hwnd: Optional[int] = None):
        self._hwnd = hwnd
        self._itl = None
        self._state = TB_NONE

    def _ensure(self):
        if self._itl is not None or sys.platform != "win32" or not self._hwnd:
            return
        try:  # pragma: no cover - requires real Windows COM + HWND
            import comtypes.client  # optional; only if present
            self._itl = comtypes.client.CreateObject(
                "{56FDF344-FD6D-11d0-958A-006097C9A090}",
                interface=None)
        except Exception:
            self._itl = None

    def set_state(self, state: str, progress: int = 0) -> None:
        self._state = state
        self._ensure()
        if self._itl is None:  # no-op when unavailable / off-Windows
            return
        try:  # pragma: no cover
            self._itl.SetProgressState(self._hwnd, self._TBPF.get(state, 0))
            if state == TB_NORMAL:
                self._itl.SetProgressValue(self._hwnd, int(progress), 100)
        except Exception:
            pass

    @property
    def state(self) -> str:
        return self._state


class Notifier:
    """Local notifications via QSystemTrayIcon. No cloud push; only works while
    the app is open/minimized. Degrades to no-op if the tray is unavailable."""

    def __init__(self, tray=None):
        self._tray = tray  # a QSystemTrayIcon, injected by main.py

    def available(self) -> bool:
        if self._tray is None:
            return False
        try:  # pragma: no cover - requires Qt tray
            from PySide6.QtWidgets import QSystemTrayIcon
            return bool(QSystemTrayIcon.isSystemTrayAvailable())
        except Exception:
            return False

    def show(self, note: Notification) -> bool:
        if not self.available():
            return False
        try:  # pragma: no cover
            self._tray.showMessage(note.title, note.message)
            return True
        except Exception:
            return False


# --- facade (pure policy, fully testable) ---------------------------------- #
class WindowsIntegration:
    """Coordinates the seams and owns the notification policy. The engine
    adapter calls the high-level ``on_*`` hooks; this class decides which OS
    calls happen (keep-awake acquire/release, taskbar mapping, notify with
    focus-gating + dedup) and records the click route."""

    def __init__(self, power: PowerRequester = None, taskbar: TaskbarButton = None,
                 notifier: Notifier = None, prefs: dict = None,
                 clock: Callable[[], float] = time.monotonic,
                 dedup_window: float = 3.0):
        self.power = power or PowerRequester()
        self.taskbar = taskbar or TaskbarButton()
        self.notifier = notifier or Notifier()
        self.prefs = dict(DEFAULT_PREFS)
        if prefs:
            self.set_prefs(prefs)
        self._clock = clock
        self._dedup_window = dedup_window
        self._focused = True
        self._recent = {}          # (kind, route) -> last-shown monotonic ts
        self.pending_route = ""     # set on notification click
        self.shown_count = 0        # notifications actually delivered

    # -- config / state -- #
    def set_prefs(self, prefs: dict) -> None:
        for k, v in (prefs or {}).items():
            if k in DEFAULT_PREFS:
                self.prefs[k] = bool(v)

    def set_focused(self, focused: bool) -> None:
        self._focused = bool(focused)

    # -- lifecycle hooks (called by engine_adapter) -- #
    def on_job_started(self) -> None:
        self.power.set_awake(True)
        self.taskbar.set_state(TB_NORMAL, 0)

    def on_progress(self, percent: int) -> None:
        self.taskbar.set_state(TB_NORMAL, max(0, min(100, int(percent))))

    def on_pause_requested(self) -> None:
        self.taskbar.set_state(TB_PAUSED)

    def on_paused(self) -> None:
        # Paused holds no execution slot -> release keep-awake, keep paused bar.
        self.power.set_awake(False)
        self.taskbar.set_state(TB_PAUSED)

    def on_completed(self, job_id: str, title: str = "") -> bool:
        self.power.set_awake(False)
        self.taskbar.set_state(TB_NONE)
        return self._notify(N_COMPLETE, "Processing complete",
                            title or "Your lecture is ready.", route=f"job:{job_id}")

    def on_failed(self, job_id: str, error: str = "") -> bool:
        self.power.set_awake(False)
        self.taskbar.set_state(TB_ERROR)
        return self._notify(N_FAILED, "Processing failed",
                            error or "A stage failed. Open details.",
                            route=f"error:{job_id}")

    def on_cancelled(self) -> None:
        self.power.set_awake(False)
        self.taskbar.set_state(TB_NONE)

    def on_idle(self) -> None:
        self.power.set_awake(False)
        self.taskbar.set_state(TB_NONE)

    def on_update_available(self, version: str = "") -> bool:
        return self._notify(N_UPDATE, "Update available",
                            f"LecturePack {version} is available.".strip(),
                            route="update", ignore_focus=True)

    def on_smart_study_done(self, job_id: str) -> bool:
        return self._notify(N_SMART_STUDY, "Smart Study ready",
                            "Study materials are ready.", route=f"job:{job_id}")

    def on_shutdown(self) -> None:
        self.power.set_awake(False)
        self.taskbar.set_state(TB_NONE)

    # -- click routing (wired from tray.messageClicked) -- #
    def on_notification_clicked(self) -> str:
        """Return the route for the most-recent notification (tray balloons only
        surface the latest). Caller navigates + raises the window."""
        return self.pending_route

    # -- internal notify policy -- #
    def _notify(self, kind: str, title: str, message: str, route: str,
                ignore_focus: bool = False) -> bool:
        pref_key = _KIND_PREF.get(kind)
        if pref_key and not self.prefs.get(pref_key, False):
            return False
        if (not ignore_focus) and self.prefs.get("only_when_unfocused", True) \
                and self._focused:
            return False
        now = self._clock()
        last = self._recent.get((kind, route))
        if last is not None and (now - last) < self._dedup_window:
            return False  # duplicate suppression
        self._recent[(kind, route)] = now
        note = Notification(kind=kind, title=title, message=message, route=route,
                            sound=self.prefs.get("play_sound", False))
        ok = self.notifier.show(note)
        if ok:
            self.shown_count += 1
            self.pending_route = route
        return ok

    def test_notification(self) -> bool:
        """Fire a one-off test notification (bypasses prefs/focus/dedup) for the
        Settings 'Test Notification' button."""
        note = Notification(kind="test", title="LecturePack",
                            message="Notifications are working.",
                            route="", sound=self.prefs.get("play_sound", False))
        ok = self.notifier.show(note)
        if ok:
            self.shown_count += 1
        return ok
