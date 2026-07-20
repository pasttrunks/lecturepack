"""Measure the Review main-preview image size vs. its canvas (real backend).

Prints JSON: canvas rect, image rect, and the fraction of the canvas the slide
image occupies. Used for before/after evidence on the slide-preview-scaling fix.
"""
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

JOB = sys.argv[1] if len(sys.argv) > 1 else "egypt-live-fast-validation"

register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow()
win.resize(1360, 860)
win.show()
adapter = win.backend._adapter
page = win.view.page()

SHOW = "window.dispatchEvent(new KeyboardEvent('keydown',{key:'3'}));"

MEASURE = r"""
(function(){
  var frame=document.getElementById('slide-frame');
  var canvas=frame?frame.parentElement:null;
  var img=document.querySelector('#slide-frame img');
  function r(e){if(!e)return null;var b=e.getBoundingClientRect();return {w:Math.round(b.width),h:Math.round(b.height)};}
  var out={canvas:r(canvas),frame:r(frame),img:r(img)};
  if(img){out.natural={w:img.naturalWidth,h:img.naturalHeight};}
  if(out.canvas&&out.img){
    out.imgWidthPctOfCanvas=Math.round(out.img.w/out.canvas.w*100);
    out.imgAreaPctOfCanvas=Math.round((out.img.w*out.img.h)/(out.canvas.w*out.canvas.h)*100);
  }
  return JSON.stringify(out);
})()
"""


def go():
    adapter.current_job = Job(adapter.config.data_dir, job_id=JOB)
    adapter._push_review_data()
    # Switch to Review (so the panel has real layout), then measure after a beat.
    QTimer.singleShot(1500, lambda: page.runJavaScript(SHOW, lambda _: None))
    QTimer.singleShot(3200, lambda: page.runJavaScript(MEASURE, done))


def done(r):
    print("MEASURE", r)
    app.quit()


def on_load(ok):
    if not ok:
        print("LOAD_FAIL"); app.quit(); return
    QTimer.singleShot(1500, go)


win.view.loadFinished.connect(on_load)
QTimer.singleShot(30000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
