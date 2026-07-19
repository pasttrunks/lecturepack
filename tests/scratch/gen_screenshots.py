"""Generate UI acceptance screenshots into docs/evidence/v1.0.1/screenshots/.

Runs offscreen; each screenshot is best-effort. Uses the real packaged m2 job
for the review view and a seeded Egypt job for the Context Repair workspace so
the proposals shown are genuine (Mark Lainer->Mark Lehner, dolarite->dolerite).
"""
import os
import sys
import json
import glob
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QFont

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.services import transcript_service as ts

OUT = os.path.join("docs", "evidence", "v1.0.1", "screenshots")
os.makedirs(OUT, exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv)

# Offscreen Qt ships no font DB; load a real Windows font so text is readable.
for fp in [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
           r"C:\Windows\Fonts\tahoma.ttf"]:
    if os.path.exists(fp):
        fid = QFontDatabase.addApplicationFont(fp)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            app.setFont(QFont(fams[0], 9))
            print("using font:", fams[0])
            break


def grab(widget, name, w=1400, h=900):
    widget.resize(w, h)
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()
    pix = widget.grab()
    path = os.path.join(OUT, name)
    pix.save(path)
    print(f"saved {path} ({pix.width()}x{pix.height()})")


# ---- 1. Main window: setup view (product modes) + review view -------------
from lecturepack.ui.main_window import MainWindow

M2_DATA = r"C:\Users\marsh\LecturePackData_validation\packaged_m2"
cfg = ConfigManager(M2_DATA)
win = MainWindow(cfg)
win.stack.setCurrentIndex(0)
grab(win, "01_setup_product_modes.png")

# Load the packaged m2 job into the review view.
try:
    jobs = glob.glob(os.path.join(M2_DATA, "jobs", "*"))
    job = Job(M2_DATA, job_id=os.path.basename(jobs[0]))
    win.current_job = job
    win.controller.set_job(job)
    win._load_review_data()
    win.stack.setCurrentIndex(2)
    QApplication.processEvents()
    # select a couple of slides to show multi-selection + bulk actions
    if win.slides_view.count() >= 2:
        win.slides_view.item(0).setSelected(True)
        win.slides_view.item(1).setSelected(True)
    win.search_input.setText("the")
    QApplication.processEvents()
    grab(win, "02_review_transcript_copy_search.png")
except Exception as e:
    print("review screenshot failed:", e)

# ---- 2. Context Repair workspace on a real Egypt transcript ---------------
try:
    from lecturepack.ui.context_repair_dialog import ContextRepairDialog
    EG = r"C:\Users\marsh\LecturePackData_validation\screenshot_egypt"
    if os.path.isdir(EG):
        shutil.rmtree(EG, ignore_errors=True)
    egypt_json = r"C:\Users\marsh\LecturePackData_validation\egypt_excerpts\egyptA_nocontext.json"
    vid = os.path.join(EG, "egypt.mp4")
    os.makedirs(EG, exist_ok=True)
    ejob = Job(EG, video_path=vid)
    ejob.settings["context_names"] = ["Mark Lehner", "dolerite", "Giza", "Nile", "Pythagoras"]
    ejob.save()
    td = ejob.paths["transcript"]
    os.makedirs(td, exist_ok=True)
    data = json.load(open(egypt_json, encoding="utf-8"))
    FileManager.write_json_atomic(os.path.join(td, "raw.json"), data)
    raw = ts.parse_raw_whisper_json(data)
    FileManager.write_json_atomic(os.path.join(td, "normalized.json"),
                                  ts.normalize_transcript(raw).to_dict())
    dlg = ContextRepairDialog(ejob, cfg)
    # accept the first proposal + mark one for evidence of states
    if dlg.correction_set.corrections:
        dlg.correction_set.accept(dlg.correction_set.corrections[0].segment_id)
        if len(dlg.correction_set.corrections) > 1:
            dlg.correction_set.reject(dlg.correction_set.corrections[-1].segment_id)
        dlg._refresh_table()
    grab(dlg, "03_context_repair_workspace.png", 1150, 720)

    # filter to proper names view
    idx = dlg.filter_combo.findText("proper names")
    if idx >= 0:
        dlg.filter_combo.setCurrentIndex(idx)
        QApplication.processEvents()
    grab(dlg, "04_context_repair_proper_names.png", 1150, 720)
except Exception as e:
    import traceback; traceback.print_exc()
    print("context repair screenshot failed:", e)

print("SCREENSHOTS DONE:", sorted(os.listdir(OUT)))
