"""Non-destructive Home smoke: grouped rendering + delete/group modals.

Boots the real MainWindow against real data but ONLY opens modals and clicks
Cancel — it never confirms a delete or a group change, so real jobs are untouched.
"""
import json
import os
import sys

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

register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow(); win.resize(1360, 860); win.show()
page = win.view.page()
res = {}


def js(code, cb):
    page.runJavaScript(code, cb)


STRUCT = r"""
(function(){
  window.dispatchEvent(new KeyboardEvent('keydown',{key:'1'}));
  var g=document.getElementById('jobs-grid');
  return JSON.stringify({
    cards: g.querySelectorAll('[data-job]').length,
    groupBtns: g.querySelectorAll('.lp-jobbtn[data-action=group]').length,
    delBtns: g.querySelectorAll('.lp-jobbtn[data-action=delete]').length,
    // group section headers = direct children with a header span
    sections: g.children.length
  });
})()
"""

OPEN_DEL = r"""
(function(){
  var b=document.querySelector('#jobs-grid .lp-jobbtn[data-action=delete]');
  if(!b) return 'no-btn';
  b.click();
  var ov=document.querySelector('.lp-modal-ov');
  return ov && /Delete this lecture/.test(ov.textContent) ? 'modal-open' : 'no-modal';
})()
"""

CANCEL = r"""
(function(){
  var ov=document.querySelector('.lp-modal-ov');
  if(!ov) return 'none';
  var btns=ov.querySelectorAll('button');
  for(var i=0;i<btns.length;i++){ if(btns[i].textContent==='Cancel'){ btns[i].click(); break; } }
  return document.querySelector('.lp-modal-ov') ? 'still-open' : 'closed';
})()
"""

OPEN_GROUP = r"""
(function(){
  var b=document.querySelector('#jobs-grid .lp-jobbtn[data-action=group]');
  if(!b) return 'no-btn';
  b.click();
  var inp=document.getElementById('lp-group-input');
  return inp ? 'group-modal-open' : 'no-modal';
})()
"""


def step(seq, i=0):
    if i >= len(seq):
        ok = (res.get('cards', 0) > 0 and res.get('groupBtns') == res.get('cards')
              and res.get('delBtns') == res.get('cards') and res.get('sections', 0) >= 1
              and res.get('del') == 'modal-open' and res.get('delCancel') == 'closed'
              and res.get('group') == 'group-modal-open' and res.get('groupCancel') == 'closed')
        print("STRUCT", json.dumps(res))
        print("HOME_OK" if ok else "HOME_FAIL")
        app.quit(); return
    key, code = seq[i]
    def cb(v):
        try:
            res[key] = json.loads(v) if key == 'struct' else v
            if key == 'struct':
                res.update(res.pop('struct'))
        except Exception:
            res[key] = v
        step(seq, i + 1)
    js(code, cb)


def go():
    step([('struct', STRUCT), ('del', OPEN_DEL), ('delCancel', CANCEL),
          ('group', OPEN_GROUP), ('groupCancel', CANCEL)])


def on_load(ok):
    if not ok:
        print("LOAD_FAIL"); app.quit(); return
    QTimer.singleShot(1500, go)


win.view.loadFinished.connect(on_load)
QTimer.singleShot(30000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
