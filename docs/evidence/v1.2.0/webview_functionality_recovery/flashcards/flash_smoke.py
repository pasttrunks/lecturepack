"""End-to-end flashcard smoke (real WebEngine + backend, TEMP data dir)."""
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "app", "desktop")):
        break
    _d = os.path.dirname(_d)
sys.path.insert(0, os.path.join(_d, "app"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from desktop.assets import register_asset_scheme  # noqa: E402
from desktop import main as dmain  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402
from lecturepack.services import study_service  # noqa: E402

tmp = tempfile.mkdtemp()
study_service.build_overview = lambda job: {"key_terms": ["Ziggurat", "Cuneiform", "Hammurabi", "Euphrates", "Babylon"]}
register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow(); win.resize(1360, 860); win.show()
adapter = win.backend._adapter
adapter.config = ConfigManager(tmp); adapter.config.set("ollama", {})
adapter.current_job = Job(tmp, video_path="lecture.mp4")
page = win.view.page()
res = {}


def js(code, cb):
    page.runJavaScript(code, cb)


def step(seq, i=0):
    if i >= len(seq):
        ok = (res.get("setup") == "generate-shown"
              and res.get("session", {}).get("hasCard")
              and res.get("afterFlip", {}).get("flipped")
              and res.get("summary", {}).get("isSummary"))
        print("FLASHRES", json.dumps(res))
        print("FLASH_OK" if ok else "FLASH_FAIL")
        app.quit(); return
    key, code, wait = seq[i]
    def cb(v):
        try:
            res[key] = json.loads(v)
        except Exception:
            res[key] = v
        QTimer.singleShot(wait, lambda: step(seq, i + 1))
    js(code, cb)


GO = r"""
(function(){window.dispatchEvent(new KeyboardEvent('keydown',{key:'5'}));
var t=document.querySelector('.lp-tab[data-tab=flash]'); if(t)t.click();
return document.querySelector('#flash-root [data-fact=generate]')?'generate-shown':'no-generate';})()
"""
GEN = "(function(){document.querySelector('#flash-root [data-fact=generate]').click();return 'clicked';})()"
SESSION = r"""(function(){return JSON.stringify({hasCard:/Card 1 of/.test(document.getElementById('flash-root').textContent),
front:/Term/.test(document.getElementById('flash-root').textContent)});})()"""
FLIP = r"""(function(){var c=document.querySelector('#flash-root [data-fact=flip]'); if(c)c.click();
return JSON.stringify({flipped:/Definition/.test(document.getElementById('flash-root').textContent)});})()"""
FINISH = r"""(function(){
for(var k=0;k<60;k++){
  var kn=document.querySelector('#flash-root [data-fact=known]'); if(kn)kn.click();
  var fin=document.querySelector('#flash-root [data-fact=finish]');
  var nx=document.querySelector('#flash-root [data-fact=next]');
  if(fin){fin.click();break;} if(nx){nx.click();} else break;
}
return 'done';})()"""
SUMMARY = r"""(function(){return JSON.stringify({isSummary:/Deck complete/.test(document.getElementById('flash-root').textContent)});})()"""


def go():
    step([("setup", GO, 400), ("gen", GEN, 1000), ("session", SESSION, 150),
          ("afterFlip", FLIP, 200), ("finishAll", FINISH, 600), ("summary", SUMMARY, 100)])


def on_load(ok):
    if not ok:
        print("LOAD_FAIL"); app.quit(); return
    QTimer.singleShot(1500, go)


win.view.loadFinished.connect(on_load)
QTimer.singleShot(40000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
