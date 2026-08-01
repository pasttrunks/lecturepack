"""LecturePack desktop shell.

A QWebEngineView renders the pixel-exact web UI (app/ui) and talks to the
Python engine over QWebChannel. The existing LecturePack backend stays
untouched — it is plugged in through desktop/engine_adapter.py.

Run from source:  python -m desktop.main   (from the app/ directory)
Packaged:         LecturePack.exe          (see packaging/)
"""

from __future__ import annotations

import os
import sys
import json

if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    import site
    candidates = [
        os.path.join(sys.prefix, "Lib", "site-packages"),
        os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
    ]
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    for sp in candidates:
        pyside = os.path.join(sp, "PySide6")
        shiboken = os.path.join(sp, "shiboken6")
        if os.path.isdir(pyside):
            try:
                os.add_dll_directory(pyside)
            except Exception:
                pass
        if os.path.isdir(shiboken):
            try:
                os.add_dll_directory(shiboken)
            except Exception:
                pass

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from . import version
from .assets import AssetResolver, install_asset_handler, register_asset_scheme
from .bridge import Backend
from .paths import data_dir, ui_dir
from .single_instance import SingleInstanceGuard


# D-20/D-21: Windows associates a taskbar button with an installed app's
# identity via its Application User Model ID. No call to
# SetCurrentProcessExplicitAppUserModelID existed anywhere in app/ before
# this fix (confirmed by source search -- see 01-FINDINGS-icon.md). That
# finding also ruled out the setWindowIcon guard below as the cause of the
# owner's reported blank taskbar icon on the installed build, leaving the
# missing AUMID as the only remaining explanation, even though the symptom
# did not reproduce during diagnosis. Stable across versions -- changing
# this string later orphans a pinned taskbar/Start icon. Must match
# lecturepack.iss's AppUserModelID `[Icons]` parameter byte-for-byte.
APP_USER_MODEL_ID = "LecturePack.LecturePack"


def _set_app_user_model_id() -> None:
    """Declare a stable Windows taskbar identity before any window is shown.

    Follows win_integration.py's PowerRequester.set_awake() ctypes idiom:
    lazy import, win32-only, and a bare except that degrades to a silent
    no-op -- a shell-integration failure must never block startup.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass  # degrade silently


def _resolve_icon_path() -> str:
    """Frozen EXE: the .ico sits next to LecturePack.exe (bundle_engine()
    copies it there). Source run: resolve it from the packaging/ tree."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "lecturepack.ico")
    return os.path.join(os.path.dirname(__file__), "..", "packaging", "lecturepack.ico")


def _report_missing_icon(tag: str, path: str) -> None:
    """D-21: the previous `os.path.exists` guard had no else-branch, so a
    missing .ico disappeared without a trace. 01-FINDINGS-icon.md ruled this
    out as beta.7's actual cause of the reported blank icon, but the guard
    was still untested against a genuinely missing file -- a future
    packaging regression that stops shipping the .ico would otherwise fail
    silently again. Report, don't raise: a missing icon must never be
    fatal. No project logger exists in this codebase yet; mirror
    Backend.log_asset_error's own stderr sink so the message reaches the
    same place other silent-failure guards in this file already use.
    """
    print(f"[{tag}] icon not found at resolved path: {path}", file=sys.stderr)


class WebView(QWebEngineView):
    """Web view that forwards native file drops to the backend.

    Chromium sandboxes drag-and-drop file paths away from page JS, so
    "drop a lecture video anywhere" is handled here at the Qt layer and
    routed into the same import flow the UI's Browse button uses.
    """

    VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".webm"}

    def __init__(self, backend: Backend):
        super().__init__()
        self._backend = backend
        self.setAcceptDrops(True)

    def _video_path(self, mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and os.path.splitext(path)[1].lower() in self.VIDEO_EXTS:
                return path
        return None

    def dragEnterEvent(self, event):
        if self._video_path(event.mimeData()):
            event.acceptProposedAction()
            self._backend.notify_drag_over()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        path = self._video_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self._backend.import_video(path)
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(version.APP_NAME)
        self.setMinimumSize(480, 560)
        self.resize(1360, 860)

        icon_path = _resolve_icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            _report_missing_icon("window-icon", icon_path)

        self.backend = Backend(self)
        self.view = WebView(self.backend)

        # Match the Qt widget background to the saved theme so no white
        # bleeds through before the web page paints its first frame.
        self.backend.settings_changed.connect(self._sync_page_background)
        self._sync_page_background()

        self.channel = QWebChannel(self)
        self.channel.registerObject("backend", self.backend)
        self.view.page().setWebChannel(self.channel)

        # Serve job slide images through the central, security-checked asset
        # resolver (lpasset:// scheme) rather than raw file:// URLs.
        # ffmpeg is resolved lazily (callable) because the adapter configures the
        # binary paths after this point; poster extraction only needs it later.
        self._assets = AssetResolver(data_dir(), ffmpeg_exe=self._ffmpeg_exe)
        self._asset_handler = install_asset_handler(
            self.view.page().profile(),
            self._assets,
            logger=self.backend.log_asset_error,
        )
        # Generate card posters as soon as a job appears (import, restore, etc.)
        # rather than waiting for a card to request one and miss.
        self.backend.jobs_changed.connect(self._prewarm_posters)

        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        index = os.path.join(ui_dir(), "index.html")
        self._show_requested = False
        self._theme_ready = False
        self.view.loadFinished.connect(self._apply_initial_theme_before_show)
        self.setCentralWidget(self.view)
        self.view.load(QUrl.fromLocalFile(index))

        # Windows integration: a tray icon carries local notifications; the
        # window HWND drives taskbar progress. Both degrade to no-ops if the
        # tray/HWND is unavailable. (beta.3)
        #
        # This block MUST stay inside __init__. It was previously orphaned
        # below `_ffmpeg_exe`'s `return ""`, where it was unreachable — which
        # silently killed every tray notification and all taskbar progress,
        # because `self.tray` was never assigned and `attach_window` never ran.
        # Caught by the beta.4 pre-release review; see BUG-11.
        self.tray = None
        try:
            from PySide6.QtWidgets import QSystemTrayIcon
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray = QSystemTrayIcon(self)
                if os.path.exists(icon_path):
                    self.tray.setIcon(QIcon(icon_path))
                else:
                    _report_missing_icon("tray-icon", icon_path)
                self.tray.setToolTip(version.APP_NAME)
                self.tray.messageClicked.connect(self._on_notification_clicked)
                self.tray.show()
        except Exception:
            self.tray = None
        try:
            self.backend._adapter.attach_window(self, self.tray)
        except Exception:
            pass

    def show_when_ready(self) -> None:
        """Show only after the saved palette is installed, or a failed load settles."""
        self._show_requested = True
        if self._theme_ready:
            self.show()

    def _apply_initial_theme_before_show(self, loaded: bool) -> None:
        if not loaded:
            self._theme_ready = True
            if self._show_requested:
                self.show()
            return
        theme = json.dumps(self.backend.initial_theme())
        script = "document.documentElement.dataset.theme = " + theme + ";"
        self.view.page().runJavaScript(script, self._finish_initial_theme)

    def _finish_initial_theme(self, _result=None) -> None:
        self._theme_ready = True
        if self._show_requested:
            self.show()

    def _sync_page_background(self, _payload: str = "") -> None:
        """Keep the Qt compositor and native window brush on the DOM theme."""
        theme = self.backend.initial_theme()
        color = "#16191F" if theme == "dark" else "#F3F0E8"
        self.view.page().setBackgroundColor(QColor(color))
        self.setStyleSheet(f"QMainWindow{{background:{color};}}")

    def _prewarm_posters(self, payload: str) -> None:
        """Kick off poster generation for every job in a jobs_changed payload."""
        try:
            import json
            jobs = json.loads(payload or "[]")
            ids = [j.get("id") for j in jobs if isinstance(j, dict) and j.get("id")]
        except (ValueError, AttributeError, TypeError):
            return
        try:
            self._assets.prewarm_posters(ids)
        except Exception:
            pass          # posters are cosmetic; never break the job list

    def _ffmpeg_exe(self) -> str:
        """Current ffmpeg path, asked for lazily by the poster generator.

        Read through the adapter's ConfigManager at call time rather than
        captured at construction: binary detection runs after the window is
        built, so an eagerly-read value would be empty on first launch.
        """
        try:
            return self.backend._adapter.config.get("ffmpeg_exe", "") or ""
        except Exception:
            return ""

    def raise_and_focus(self) -> None:
        """Bring this window to the foreground and give it input focus.

        D-18: reused by both the tray-notification click handler below and
        the single-instance guard's raise signal in main(), so there is
        exactly one focus mechanism in this file, not two.
        """
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_notification_clicked(self):
        """A tray balloon was clicked: raise the window and route to the target
        the last notification pointed at (open job / error / update)."""
        try:
            route = self.backend._adapter.win.on_notification_clicked()
        except Exception:
            route = ""
        self.raise_and_focus()
        if route:
            self.backend.notification_navigate.emit(route)


def main() -> int:
    # D-20: must run before any window/UI is presented, so it precedes even
    # the custom URL scheme registration below.
    _set_app_user_model_id()

    # Custom URL schemes must be registered before the QApplication is created.
    register_asset_scheme()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(version.APP_NAME)
    app.setOrganizationName(version.ORG_NAME)
    app.setApplicationVersion(version.__version__)

    # D-18/D-19: probe for an already-running instance before constructing
    # MainWindow (and therefore before Backend.__init__ and its deferred
    # assess() worker). A guard placed after MainWindow() would let a
    # second process sit invisible for the whole pending-admission window,
    # which is the exact symptom D-19 exists to prevent. QLocalSocket needs
    # QCoreApplication machinery (01-RESEARCH.md Open Question 1), so this
    # runs right after QApplication(sys.argv) rather than before it.
    guard = SingleInstanceGuard()
    if guard.acquire() == "secondary":
        # Another instance owns the endpoint: ask it to raise and focus,
        # then exit immediately rather than silently -- silent exit is
        # indistinguishable from a failed launch (D-18).
        guard.signal_existing()
        return 0

    win = MainWindow()
    guard.set_raise_handler(win.raise_and_focus)
    win.show_when_ready()

    # Focus-gate notifications: only fire when the app is not the active window.
    def _on_app_state(state):
        try:
            win.backend._adapter.set_focused(state == Qt.ApplicationState.ApplicationActive)
        except Exception:
            pass
    app.applicationStateChanged.connect(_on_app_state)

    # Release keep-awake (and clear the taskbar) on quit.
    def _on_quit():
        try:
            win.backend._adapter.win.on_shutdown()
        except Exception:
            pass
        guard.release()
    app.aboutToQuit.connect(_on_quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
