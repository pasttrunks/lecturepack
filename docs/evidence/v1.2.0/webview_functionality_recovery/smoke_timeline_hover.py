"""Headless check of the timeline hover popup placement (P1.7).

Loads the real UI (demo/browser mode, no backend), switches to Review, hovers
the timeline near the left edge, and reports the preview's rect so we can confirm
it is portaled to <body> and clamped within the viewport (not clipped).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "app", "ui", "index.html")

app = QApplication(sys.argv)
view = QWebEngineView()
view.resize(1360, 860)
view.show()  # gives a real layout viewport offscreen

result = {"code": 2}

JS = r"""
(function(){
  window.dispatchEvent(new KeyboardEvent('keydown',{key:'3'}));
  var strip=document.getElementById('timeline-strip');
  var r=strip.getBoundingClientRect();
  strip.dispatchEvent(new MouseEvent('mousemove',{clientX:r.left+2,clientY:r.top+10,bubbles:true}));
  var pv=document.getElementById('scrub-preview');
  var pr=pv.getBoundingClientRect();
  return JSON.stringify({
    parentBody: pv.parentNode===document.body,
    display: pv.style.display,
    vw: window.innerWidth, vh: window.innerHeight,
    left: Math.round(pr.left), top: Math.round(pr.top),
    right: Math.round(pr.right), bottom: Math.round(pr.bottom),
    stripTop: Math.round(r.top)
  });
})()
"""


def probe():
    view.page().runJavaScript(JS, done)


def done(payload):
    import json
    print("PROBE", payload)
    try:
        d = json.loads(payload)
        ok = (d["parentBody"] and d["display"] == "block"
              and d["left"] >= 0 and d["top"] >= 0
              and d["right"] <= d["vw"] and d["bottom"] <= d["vh"])
        print("HOVER_OK" if ok else "HOVER_FAIL")
        result["code"] = 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        print("PARSE_FAIL", exc)
        result["code"] = 1
    app.quit()


def on_load(ok):
    if not ok:
        print("PAGE_LOAD_FAILED")
        app.quit()
        return
    QTimer.singleShot(600, probe)


view.loadFinished.connect(on_load)
view.load(QUrl.fromLocalFile(UI))
QTimer.singleShot(9000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
sys.exit(result["code"])
