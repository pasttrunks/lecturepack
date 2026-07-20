"""Headless smoke test: does a file:// page load an lpasset:// <img>?

Validates the custom-scheme flags/wiring end-to-end in QtWebEngine, which the
pure resolver tests can't cover. Exits 0 with 'ASSET_OK w=<n>' on success.
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "app")
sys.path.insert(0, APP_DIR)

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: E402

from desktop.assets import (  # noqa: E402
    AssetResolver, asset_url, install_asset_handler, register_asset_scheme,
)

# Build a temp job with one 1x1 PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1b0000000049454e44ae426082")
tmp = tempfile.mkdtemp()
cand = os.path.join(tmp, "jobs", "job1", "frames", "candidates")
os.makedirs(cand)
with open(os.path.join(cand, "slide_1.png"), "wb") as f:
    f.write(PNG)

register_asset_scheme()
app = QApplication(sys.argv)
view = QWebEngineView()
view.settings().setAttribute(
    QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
install_asset_handler(view.page().profile(), AssetResolver(tmp),
                      logger=lambda *a: print("LOG", a))

url = asset_url("job1", "slide_1.png")
html = f'<!doctype html><body><img id="i" src="{url}"></body>'
index = os.path.join(tmp, "index.html")
with open(index, "w") as f:
    f.write(html)

result = {"code": 2}


def check():
    view.page().runJavaScript(
        "var i=document.getElementById('i');i?i.naturalWidth:-1", cb)


def cb(width):
    if width and width > 0:
        print(f"ASSET_OK w={width}")
        result["code"] = 0
    else:
        print(f"ASSET_FAIL naturalWidth={width}")
        result["code"] = 1
    app.quit()


def on_load(ok):
    if not ok:
        print("PAGE_LOAD_FAILED")
        result["code"] = 1
        app.quit()
        return
    QTimer.singleShot(400, check)


view.loadFinished.connect(on_load)
view.load(QUrl.fromLocalFile(index))
QTimer.singleShot(8000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
sys.exit(result["code"])
