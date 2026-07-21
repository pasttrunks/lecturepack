"""End-to-end quiz smoke (real WebEngine + real backend, TEMP job/data dir).

Drives the quiz UI: generate (AI off -> deterministic fallback) -> session ->
submit reveals correctness -> navigate -> finish -> summary score. Writes only to
a temp data dir (never real ~/LecturePackData).
"""
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
study_service.build_overview = lambda job: {"key_terms": [
    "Ziggurat", "Cuneiform", "Hammurabi", "Euphrates", "Babylon", "Tigris"]}

register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow(); win.resize(1360, 860); win.show()
adapter = win.backend._adapter
adapter.config = ConfigManager(tmp)          # temp data dir, no ollama
adapter.config.set("ollama", {})
adapter.current_job = Job(tmp, video_path="lecture.mp4")
page = win.view.page()
res = {}


def js(code, cb):
    page.runJavaScript(code, cb)


def step(seq, i=0):
    if i >= len(seq):
        ok = (res.get('setup') == 'generate-shown'
              and res.get('session', {}).get('hasQ')
              and res.get('afterSubmit', {}).get('revealed')
              and res.get('afterSubmit', {}).get('nextEnabled')
              and res.get('summary', {}).get('isSummary')
              and res.get('summary', {}).get('score') is not None)
        print("QUIZRES", json.dumps(res))
        print("QUIZ_OK" if ok else "QUIZ_FAIL")
        app.quit(); return
    key, code, wait = seq[i]
    def cb(v):
        try:
            res[key] = json.loads(v)
        except Exception:
            res[key] = v
        QTimer.singleShot(wait, lambda: step(seq, i + 1))
    js(code, cb)


GO_QUIZ = r"""
(function(){
  window.dispatchEvent(new KeyboardEvent('keydown',{key:'5'}));
  var t=document.querySelector('.lp-tab[data-tab=quiz]'); if(t)t.click();
  var gen=document.querySelector('#quiz-root [data-qact=generate]');
  return gen ? 'generate-shown' : 'no-generate';
})()
"""
GENERATE = "(function(){document.querySelector('#quiz-root [data-qact=generate]').click();return 'clicked';})()"
SESSION = r"""
(function(){
  var opts=document.querySelectorAll('#quiz-root [data-opt]');
  return JSON.stringify({hasQ:/Question 1 of/.test(document.getElementById('quiz-root').textContent), opts:opts.length});
})()
"""
PICK_SUBMIT = r"""
(function(){
  var o=document.querySelector('#quiz-root [data-opt]'); if(o)o.click();
  var sub=document.querySelector('#quiz-root [data-qact=submit]'); if(sub)sub.click();
  return 'done';
})()
"""
AFTER_SUBMIT = r"""
(function(){
  var txt=document.getElementById('quiz-root').textContent;
  var nx=document.querySelector('#quiz-root [data-qact=next]');
  return JSON.stringify({revealed:/Correct|Incorrect/.test(txt), nextEnabled: !!(nx && !nx.disabled)});
})()
"""
FINISH_ALL = r"""
(function(){
  // answer every remaining question then finish
  function answerAndAdvance(){
    var o=document.querySelector('#quiz-root [data-opt]:not([disabled])');
    if(o){ o.click(); var s=document.querySelector('#quiz-root [data-qact=submit]'); if(s)s.click(); }
    var nx=document.querySelector('#quiz-root [data-qact=next]');
    var fin=document.querySelector('#quiz-root [data-qact=finish]');
    if(fin){ fin.click(); return true; }
    if(nx && !nx.disabled){ nx.click(); return false; }
    return false;
  }
  for(var k=0;k<40;k++){ if(answerAndAdvance()) break; }
  return 'done';
})()
"""
SUMMARY = r"""
(function(){
  var txt=document.getElementById('quiz-root').textContent;
  var m=txt.match(/(\d+)\s*\/\s*(\d+)/);
  return JSON.stringify({isSummary:/Quiz complete/.test(txt), score: m?m[1]+'/'+m[2]:null});
})()
"""


def go():
    step([('setup', GO_QUIZ, 400), ('gen', GENERATE, 1200), ('session', SESSION, 200),
          ('pick', PICK_SUBMIT, 500), ('afterSubmit', AFTER_SUBMIT, 200),
          ('finishAll', FINISH_ALL, 800), ('summary', SUMMARY, 100)])


def on_load(ok):
    if not ok:
        print("LOAD_FAIL"); app.quit(); return
    QTimer.singleShot(1500, go)


win.view.loadFinished.connect(on_load)
QTimer.singleShot(40000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
