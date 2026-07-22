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

# Smooth, GPU-accelerated rendering. Must be set before Qt loads.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist",
)

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from . import version
from .assets import AssetResolver, install_asset_handler, register_asset_scheme
from .bridge import Backend
from .paths import data_dir, ui_dir


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
        self.setMinimumSize(1080, 680)
        self.resize(1360, 860)

        icon_path = os.path.join(os.path.dirname(__file__), "..", "packaging", "lecturepack.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.backend = Backend(self)
        self.view = WebView(self.backend)
        self.channel = QWebChannel(self)
        self.channel.registerObject("backend", self.backend)
        self.view.page().setWebChannel(self.channel)

        # Serve job slide images through the central, security-checked asset
        # resolver (lpasset:// scheme) rather than raw file:// URLs.
        self._asset_handler = install_asset_handler(
            self.view.page().profile(),
            AssetResolver(data_dir()),
            logger=self.backend.log_asset_error,
        )

        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        index = os.path.join(ui_dir(), "index.html")
        self.view.load(QUrl.fromLocalFile(index))
        self.setCentralWidget(self.view)


def main() -> int:
    # Custom URL schemes must be registered before the QApplication is created.
    register_asset_scheme()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(version.APP_NAME)
    app.setOrganizationName(version.ORG_NAME)
    app.setApplicationVersion(version.__version__)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
