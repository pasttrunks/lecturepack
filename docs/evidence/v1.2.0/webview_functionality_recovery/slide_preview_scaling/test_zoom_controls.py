"""Verify the preview zoom controls (Fit / 100% / zoom in / reset) work."""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "app")
sys.path.insert(0, APP_DIR)
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from desktop.assets import register_asset_scheme  # noqa: E402
from desktop import main as dmain  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402

JOB = "egypt-live-fast-validation"  # 1024x768
register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow(); win.resize(1360, 860); win.show()
adapter = win.backend._adapter; page = win.view.page()
results = {}


def imgw():
    return "document.querySelector('#preview-img').getBoundingClientRect().width"


def click(z):
    return "document.querySelector('#preview-zoom [data-z=\"%s\"]').click();" % z


def step(seq, i=0):
    if i >= len(seq):
        print("ZOOM_RESULT", json.dumps(results))
        ok = (results["fit"] and 380 < results["fit"] < 460
              and results["p100"] and 1000 < results["p100"] < 1050
              and results["zin"] > results["fit"] + 10
              and abs(results["reset"] - results["fit"]) < 3)
        print("ZOOM_OK" if ok else "ZOOM_FAIL")
        app.quit(); return
    name, js = seq[i]
    def cb(v):
        if name:
            results[name] = round(v) if isinstance(v, (int, float)) else v
        step(seq, i + 1)
    page.runJavaScript(js, cb)


def go():
    adapter.current_job = Job(adapter.config.data_dir, job_id=JOB)
    adapter._push_review_data()
    QTimer.singleShot(1500, lambda: page.runJavaScript(
        "window.dispatchEvent(new KeyboardEvent('keydown',{key:'3'}));", lambda _: None))
    QTimer.singleShot(3200, lambda: step([
        ("fit", imgw()),
        (None, click("100")),
        ("p100", imgw()),
        (None, click("in")),        # zoom in from 100
        ("zin", imgw()),
        (None, click("fit")),
        ("reset", imgw()),
    ]))


def on_load(ok):
    if not ok:
        print("LOAD_FAIL"); app.quit(); return
    QTimer.singleShot(1500, go)


win.view.loadFinished.connect(on_load)
QTimer.singleShot(30000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
