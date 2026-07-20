"""Phase 1 live slide-preview acceptance (headless, REAL backend + REAL data).

Boots the actual desktop MainWindow (real Backend, QWebChannel, lpasset asset
handler, LecturePackAdapter over ~/LecturePackData) into an offscreen
QWebEngineView with a real viewport, then drives the production UI to prove slide
thumbnails and the large preview render for real jobs, that job-switching clears
stale images, prev/next changes the preview, and a missing file shows the marker.

Emits a JSON report to the path given as argv[1]. Exit 0 iff all checks pass.
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

OUT = sys.argv[1] if len(sys.argv) > 1 else "live_slide_acceptance.json"

SHORT = "75432ce6-1c37-45a6-a70c-57746339356f"        # m2-res_1080p, 7 imgs
EGYPT = "egypt-live-fast-validation"                    # egyptA excerpt, 11 imgs
FULL = "454b0c62-76d5-4aaf-acb9-06ebe9c252ea"          # Mesopotamia, 167 imgs

report = {"checks": [], "ok": False}


def record(name, ok, detail):
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + str(detail))


register_asset_scheme()
app = QApplication(sys.argv)
win = dmain.MainWindow()
win.resize(1360, 860)
win.show()
adapter = win.backend._adapter
page = win.view.page()


def load_job(job_id):
    adapter.current_job = Job(adapter.config.data_dir, job_id=job_id)
    adapter._push_review_data()


def js(code, cb):
    page.runJavaScript(code, cb)


CHECK_JS = r"""
(function(){
  window.dispatchEvent(new KeyboardEvent('keydown',{key:'3'}));
  var thumbs = Array.prototype.slice.call(document.querySelectorAll('#slide-list img'));
  var loaded = thumbs.filter(function(i){return i.naturalWidth>0;}).length;
  var pv = document.querySelector('#slide-frame img');
  var frameLabel = (document.getElementById('slide-frame-meta')||{}).textContent||'';
  return JSON.stringify({
    slides: (window.LP&&LP.data&&LP.data.slides||[]).length,
    thumbTotal: thumbs.length, thumbLoaded: loaded,
    previewNat: pv?pv.naturalWidth:-1,
    previewSrc: pv?pv.getAttribute('src'):'',
    frameLabel: frameLabel
  });
})()
"""


# ---- step machine -------------------------------------------------------
steps = []


def step_check_job(job_id, label, min_slides):
    def run(nxt):
        load_job(job_id)
        def after(_):
            js(CHECK_JS, lambda r: (_val(r), nxt()))
        def _val(r):
            d = json.loads(r)
            record(f"{label}: slides listed", d["slides"] >= min_slides,
                   f'{d["slides"]} slides')
            record(f"{label}: all thumbnails render",
                   d["thumbTotal"] > 0 and d["thumbLoaded"] == d["thumbTotal"],
                   f'{d["thumbLoaded"]}/{d["thumbTotal"]} naturalWidth>0')
            record(f"{label}: large preview renders", d["previewNat"] > 0,
                   f'naturalWidth={d["previewNat"]} src={d["previewSrc"][:60]}')
            record(f"{label}: preview belongs to this job",
                   job_id in (d["previewSrc"] or ""), d["previewSrc"][:80])
        QTimer.singleShot(2600, lambda: after(None))
    return run


def step_stale(nxt):
    # After loading FULL (previous step), switch to SHORT and confirm the
    # preview image now points at SHORT, not the stale FULL job.
    load_job(SHORT)
    def after():
        js("var i=document.querySelector('#slide-frame img');i?i.getAttribute('src'):''",
           lambda src: (record("job switch clears stale image",
                               (SHORT in (src or "")) and (FULL not in (src or "")),
                               (src or "")[:80]), nxt()))
    QTimer.singleShot(1000, after)


def step_prevnext(nxt):
    load_job(FULL)
    def after():
        js("var i=document.querySelector('#slide-frame img');i?i.getAttribute('src'):''",
           lambda before: mid(before))
    def mid(before):
        js("document.getElementById('btn-next-slide').click();"
           "var i=document.querySelector('#slide-frame img');i?i.getAttribute('src'):''",
           lambda after_src: (record("next changes preview",
                                     bool(after_src) and after_src != before,
                                     f'{(before or "")[-24:]} -> {(after_src or "")[-24:]}'), nxt()))
    QTimer.singleShot(1000, after)


def step_missing(nxt):
    # Point the first slide at a bogus asset, then re-render via the real UI
    # click path (renderSlides is module-private) and confirm the onerror
    # fallback marker appears.
    inject = ("LP.data.slides[0].img='lpasset://job/%s/__does_not_exist__.png';"
              "document.querySelector('#slide-list [data-slide]').click();" % FULL)
    js(inject, lambda _: QTimer.singleShot(2200, chk))
    def chk():
        js("(function(){var ph=document.querySelector('#slide-frame .lp-img-ph');"
           "return ph?getComputedStyle(ph).display:'none';})()",
           lambda disp: (record("missing file shows explicit marker",
                                disp and disp != "none", f'placeholder display={disp}'), nxt()))


def step_open_job_via_ui(nxt):
    # End-to-end: click a job card on Home -> open_job bridge -> adapter ->
    # Review renders that job's slides (no direct adapter call).
    open_js = (
        "(function(){"
        "window.dispatchEvent(new KeyboardEvent('keydown',{key:'1'}));"
        "var c=document.querySelector('#jobs-grid [data-job=\"%s\"]');"
        "if(c){c.click();return 'clicked';}"
        "return 'no-card:'+ (window.LP&&LP.data&&LP.data.jobs?LP.data.jobs.length:'?');"
        "})()" % EGYPT)

    def after(clicked):
        def chk(r):
            d = json.loads(r)
            ok = (d["slides"] >= 5 and d["thumbTotal"] > 0
                  and d["thumbLoaded"] == d["thumbTotal"]
                  and EGYPT in (d["previewSrc"] or ""))
            record("open_job via Home card renders that job", ok,
                   f'clicked={clicked} slides={d["slides"]} '
                   f'thumbs={d["thumbLoaded"]}/{d["thumbTotal"]} src={d["previewSrc"][:50]}')
            nxt()
        QTimer.singleShot(2600, lambda: js(CHECK_JS, chk))

    js(open_js, after)


steps = [
    step_check_job(EGYPT, "egypt-excerpt", 5),
    step_check_job(FULL, "full(Mesopotamia)", 100),
    step_check_job(SHORT, "short(m2-1080p)", 5),
    step_prevnext,
    step_stale,
    step_open_job_via_ui,
    step_missing,
]


def run_steps(i=0):
    if i >= len(steps):
        report["ok"] = all(c["ok"] for c in report["checks"])
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print("ALL_OK" if report["ok"] else "SOME_FAILED")
        app.quit()
        return
    steps[i](lambda: run_steps(i + 1))


def on_load(ok):
    if not ok:
        record("index.html loaded", False, "loadFinished=false")
        app.quit()
        return
    QTimer.singleShot(1500, lambda: run_steps(0))  # let ui_ready settle


win.view.loadFinished.connect(on_load)
QTimer.singleShot(45000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
sys.exit(0 if report.get("ok") else 1)
