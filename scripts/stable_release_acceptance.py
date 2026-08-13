"""Automation-first acceptance for the packaged LecturePack stable candidate.

The harness drives the real Electron renderer through Chrome DevTools while
all product actions cross the packaged preload/main/JSONL/sidecar boundary. It
uses only disposable data/profile directories and writes screenshots plus one
machine-readable result. It never points LecturePack at the normal user data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from electron_packaged_acceptance import detect_orphans, snapshot_processes
from packaged_visual_acceptance import (
    CDP,
    WM_CLOSE,
    _cdp_target,
    _resize,
    _wait_for_window,
    _window_rect,
    user32,
)


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DEMO_SHA256 = "24957e863c477cd7ad2ef9228f3bbe943f5038e5ccd18ef7ab92efefee13f55f"
MEDIA_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".m4v", ".webm", ".mpeg", ".mpg", ".wmv"}


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_records(log_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(log_dir.glob("production-*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                records.append({"event": "_unparseable", "line": line[:300]})
    return records


class SlowMediaServer:
    """Local deterministic HTTP source that keeps yt-dlp active long enough to crash-test."""

    def __init__(self, media: Path):
        source = media

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _headers(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(source.stat().st_size))
                self.end_headers()

            def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                self._headers()

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                self._headers()
                try:
                    with source.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(64 * 1024), b""):
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            time.sleep(0.10)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/lecture.mp4"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class PackagedApp:
    def __init__(self, exe: Path, profile: Path, data: Path, logs: Path, extra: list[str] | None = None):
        self.exe = exe
        self.profile = profile
        self.data = data
        self.logs = logs
        self.extra = list(extra or [])
        self.proc: subprocess.Popen[bytes] | None = None
        self.cdp: CDP | None = None
        self.hwnd = 0
        self.before: list[dict[str, Any]] = []

    def launch(self, *, expect_startup_failure: bool = False) -> None:
        for path in (self.profile, self.data, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        self.before = snapshot_processes()
        port = free_port()
        argv = [
            str(self.exe),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile}",
            f"--results={self.logs}",
            f"--data-dir={self.data}",
            *self.extra,
        ]
        self.proc = subprocess.Popen(argv, cwd=str(self.exe.parent), shell=False)
        self.hwnd = _wait_for_window(self.proc.pid, timeout=60)
        self.cdp = _cdp_target(port, timeout=60)
        self.cdp.call("Runtime.enable")
        self.wait_js(
            "document.readyState === 'complete' && window.lpBridge && lpBridge.connected()",
            "renderer bridge",
            timeout=60,
        )
        self.wait_js(
            "!!(window.LP && LP.state && document.querySelector('[data-nav=home]'))",
            "LecturePack application state",
            timeout=30,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            records = read_records(self.logs)
            if any(record.get("event") == "startup_complete" for record in records):
                if expect_startup_failure:
                    raise RuntimeError("startup succeeded while a failure was expected")
                break
            failure = next((record for record in records
                            if record.get("event") == "startup_terminal_failure"), None)
            if failure:
                if expect_startup_failure:
                    return
                raise RuntimeError(f"packaged startup failed: {failure}")
            time.sleep(0.25)
        else:
            raise TimeoutError("timed out waiting for packaged startup_complete")
        # Exercise the real first-run acknowledgement instead of driving the
        # app invisibly behind its modal.  A restored profile already has the
        # overlay hidden, while the startup-failure scenario below must keep
        # its actionable terminal screen visible.
        if not expect_startup_failure:
            setup_ready = self.evaluate(
                "(() => { const o=document.getElementById('runtime-setup-overlay'); "
                "const b=document.getElementById('btn-runtime-done'); "
                "return !!(o&&!o.hidden&&b&&!b.disabled); })()"
            )
            if setup_ready:
                self.click("#btn-runtime-done")
                self.wait_js(
                    "document.getElementById('runtime-setup-overlay').hidden",
                    "runtime setup acknowledgement",
                    timeout=20,
                )

    def evaluate(self, expression: str) -> Any:
        if self.cdp is None:
            raise RuntimeError("DevTools is not connected")
        return self.cdp.evaluate(expression)

    def wait_js(self, expression: str, label: str, timeout: float = 60) -> Any:
        deadline = time.monotonic() + timeout
        last: Any = None
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"LecturePack exited while waiting for {label}: {self.proc.returncode}")
            try:
                last = self.evaluate(expression)
                if last:
                    return last
            except Exception as exc:  # renderer may be between documents
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)
        raise TimeoutError(f"timed out waiting for {label}; last={last!r}")

    def request(self, command: str, payload: dict[str, Any] | None = None) -> Any:
        return self.evaluate(
            "window.lecturePackElectron.request("
            + json.dumps(command)
            + ","
            + json.dumps(payload or {})
            + ")"
        )

    def click(self, selector: str) -> None:
        found = self.evaluate(
            "(() => { const el=document.querySelector("
            + json.dumps(selector)
            + "); if(!el) return false; el.click(); return true; })()"
        )
        if found is not True:
            raise RuntimeError(f"element not found: {selector}")

    def screen(self, name: str) -> None:
        self.click(f"[data-nav='{name}']")
        self.wait_js(f"LP.state.screen === {json.dumps(name)}", f"{name} screen", timeout=15)

    def screenshot(self, destination: Path) -> None:
        if self.cdp is None:
            raise RuntimeError("DevTools is not connected")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        destination.write_bytes(base64.b64decode(result["data"]))
        if destination.stat().st_size < 1000:
            raise RuntimeError(f"empty screenshot: {destination}")

    def visible_blocking_dialogs(self) -> list[str]:
        """Return visible modal/dialog element ids for screenshot hygiene."""
        return self.evaluate(
            "Array.from(document.querySelectorAll('[role=dialog],.lp-scrim'))"
            ".filter(el=>!el.hidden&&getComputedStyle(el).display!=='none'&&"
            "el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0)"
            ".map(el=>el.id||el.getAttribute('aria-label')||el.className||el.tagName)"
        ) or []

    def resize(self, width: int, height: int) -> dict[str, Any]:
        """Resize the real native window and return renderer dimensions."""
        observed = _resize(self.hwnd, width, height)
        time.sleep(0.75)
        renderer = self.evaluate(
            "({innerWidth:window.innerWidth,innerHeight:window.innerHeight,"
            "devicePixelRatio:window.devicePixelRatio})"
        )
        return {"requested": [width, height], "observed": list(observed), "renderer": renderer}

    def layout_metrics(self) -> dict[str, Any]:
        """Collect horizontal clipping signals from the currently visible screen."""
        return self.evaluate(
            "(() => {"
            "const shown=el=>{if(!el||el.hidden)return false;const s=getComputedStyle(el),r=el.getBoundingClientRect();"
            "return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};"
            "const rect=el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};"
            "const header=document.querySelector('header.lp-chrome'),main=document.querySelector('main.lp-main'),"
            "footer=document.getElementById('status-footer'),active=document.querySelector('[data-screen]:not([hidden])');"
            "const headerIds=['btn-global-search','downloads-indicator','btn-focus','btn-theme','btn-export-top'];"
            "const controls=headerIds.map(id=>document.getElementById(id)).filter(shown);"
            "const clippedHeader=controls.filter(el=>{const r=el.getBoundingClientRect();return r.left<-1||r.right>window.innerWidth+1||r.width<30}).map(el=>el.id);"
            "const mr=main.getBoundingClientRect();"
            "const clippedScreen=active?Array.from(active.querySelectorAll('button,a,input,textarea,select,[role=button]')).filter(shown).filter(el=>{const r=el.getBoundingClientRect();return r.left<mr.left-2||r.right>mr.right+2}).map(el=>el.id||el.textContent.trim().slice(0,50)).slice(0,25):[];"
            "const screen=window.LP&&LP.state?LP.state.screen:'';"
            "const homeDemo=document.getElementById('home-demo'),homeEmpty=document.getElementById('home-empty'),"
            "demoCard=document.getElementById('glowing-demo-card');"
            "const jobsEmpty=!(window.LP&&LP.data&&(LP.data.jobs||[]).length);"
            "const homeNeedsDemoAction=screen==='home'&&jobsEmpty&&(shown(homeDemo)||shown(homeEmpty));"
            "const criticalIds=homeNeedsDemoAction&&window.innerWidth>=1000&&window.innerHeight>=650?"
            "[shown(demoCard)?'glowing-demo-card':'btn-load-jobs']:[];"
            "const visibleBottom=footer?footer.getBoundingClientRect().top:window.innerHeight;"
            "const criticalOutOfView=criticalIds.map(id=>document.getElementById(id)).filter(el=>{if(!shown(el))return true;const r=el.getBoundingClientRect();return r.top<mr.top-2||r.bottom>visibleBottom+2}).map(el=>el&&el.id||'missing');"
            "return {viewport:{width:window.innerWidth,height:window.innerHeight},screen:window.LP&&LP.state?LP.state.screen:'',"
            "document:{clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth},"
            "header:{clientWidth:header.clientWidth,scrollWidth:header.scrollWidth,rect:rect(header)},"
            "main:{clientWidth:main.clientWidth,scrollWidth:main.scrollWidth,rect:rect(main)},"
            "active:active?{clientWidth:active.clientWidth,scrollWidth:active.scrollWidth,rect:rect(active)}:null,"
            "footer:footer?{clientWidth:footer.clientWidth,scrollWidth:footer.scrollWidth,rect:rect(footer)}:null,"
            "clippedHeader:clippedHeader,clippedScreen:clippedScreen,criticalIds:criticalIds,criticalOutOfView:criticalOutOfView,dialogs:Array.from(document.querySelectorAll('[role=dialog],.lp-scrim')).filter(shown).map(el=>el.id||el.tagName)};"
            "})()"
        )

    def close(self, allow_hidden: bool = False) -> list[dict[str, Any]]:
        if self.cdp is not None:
            self.cdp.close()
            self.cdp = None
        if self.proc is not None and self.proc.poll() is None:
            if user32.IsWindow(self.hwnd):
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            try:
                self.proc.wait(timeout=5 if allow_hidden else 20)
            except subprocess.TimeoutExpired:
                if not allow_hidden:
                    # A failure may occur while close-to-tray is active. In
                    # that case WM_CLOSE correctly hides the app, so the test
                    # harness must terminate its entire disposable tree—not
                    # just Electron's parent and leave FFmpeg/Whisper behind.
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(self.proc.pid), "/T", "/F"],
                        check=False,
                        capture_output=True,
                    )
                    self.proc.wait(timeout=15)
        time.sleep(1)
        return detect_orphans(self.before, snapshot_processes())

    def crash(self) -> None:
        if self.cdp is not None:
            self.cdp.close()
            self.cdp = None
        if self.proc is not None and self.proc.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(self.proc.pid), "/T", "/F"],
                check=True,
                capture_output=True,
            )
            self.proc.wait(timeout=15)


def run(args: argparse.Namespace) -> dict[str, Any]:
    evidence = args.evidence.resolve()
    if evidence.exists() and any(evidence.iterdir()):
        raise RuntimeError(f"evidence directory must be empty: {evidence}")
    evidence.mkdir(parents=True, exist_ok=True)
    screenshots = evidence / "screenshots"
    workspace = evidence / "workspace"
    data = workspace / "LecturePack Data With Spaces Ω"
    profile = workspace / "Electron Profile"
    logs = evidence / "logs"
    for path in (screenshots, data, profile, logs):
        path.mkdir(parents=True, exist_ok=True)

    demo = args.demo.resolve()
    demo_hash = sha256(demo)
    if demo_hash != CANONICAL_DEMO_SHA256:
        raise RuntimeError(f"canonical demo hash mismatch: {demo_hash}")

    result: dict[str, Any] = {
        "schema_version": 1,
        "started_at": iso_now(),
        "status": "RUNNING",
        "human_manual_acceptance_required": False,
        "candidate": str(args.exe.resolve()),
        "demo": {
            "source": str(demo),
            "packaged_path": str(args.packaged_demo.resolve()),
            "sha256": demo_hash,
            "packaged_sha256": sha256(args.packaged_demo.resolve()),
            "duration_seconds": 10.005,
        },
        "checks": {},
        "screenshots": [],
        "failures": [],
    }

    def check(name: str, passed: bool, detail: Any = None) -> None:
        result["checks"][name] = {"passed": bool(passed), "detail": detail}
        if not passed:
            result["failures"].append(name)

    app = PackagedApp(args.exe.resolve(), profile, data, logs)
    job_id = ""
    try:
        app.launch()
        check("packaged_launch", True, {"pid": app.proc.pid if app.proc else None})
        app.screen("home")
        home = screenshots / "01-home.png"
        app.screenshot(home)
        result["screenshots"].append(str(home))
        first_run_rect = _window_rect(app.hwnd)
        first_run_size = [first_run_rect[2] - first_run_rect[0], first_run_rect[3] - first_run_rect[1]]
        app.resize(1024, 720)
        first_run_layout = app.layout_metrics()
        first_run_shot = screenshots / "01a-first-run-1024x720.png"
        app.screenshot(first_run_shot)
        result["screenshots"].append(str(first_run_shot))
        app.resize(*first_run_size)
        check(
            "first_run_demo_action_visible",
            bool(first_run_layout.get("criticalIds"))
            and not first_run_layout.get("criticalOutOfView"),
            first_run_layout,
        )

        # The rebuilt guided demo deliberately stops at Review Ready so the
        # student can keep/reject slides before exporting.  Prove that parked
        # handoff (including the automatic route to Review) and its cleanup
        # first; then import the same canonical bytes as a normal lecture for
        # the complete auto-export release workflow below.  Waiting for the
        # guided job to become ``done`` is an obsolete contract: with
        # auto_export=False it is supposed to remain reviewable.
        # Use the actual five-chapter screen and CTA.  Calling startDemoJob()
        # directly would bypass guidedDemo.starting(), so the identity-scoped
        # reducer would (correctly) reject later demo events and never route
        # Process -> Review.
        existing_job_ids = app.evaluate("LP.data.jobs.map(j=>j&&j.id).filter(Boolean)") or []
        app.click("#glowing-demo-card")
        app.wait_js("LP.state.screen === 'demo'", "guided demo screen", timeout=15)
        prebaked_demo = app.wait_js(
            "(() => { const d=window.LP_DEMO_DATA, hero=document.getElementById('demo-hero'),"
            "slides=Array.from(document.querySelectorAll('#demo-slides img'))," "lines=document.querySelectorAll('#demo-transcript .lp-demo-line'),"
            "opts=document.querySelectorAll('#demo-quiz-opts .lp-demo-opt'),"
            "fallback=document.querySelectorAll('[data-screen=demo] .lp-demo-fallback');"
            "const ok=d&&d.source&&Array.isArray(d.slides)&&d.slides.length>=2&&"
            "Array.isArray(d.lines)&&d.lines.length>=2&&d.card&&d.card.q&&d.quiz&&d.quiz.q&&"
            "Array.isArray(d.quiz.options)&&d.quiz.options.length>=2&&fallback.length===0&&"
            "hero&&hero.complete&&hero.naturalWidth>0&&slides.length===d.slides.length&&"
            "slides.every(img=>img.complete&&img.naturalWidth>0)&&lines.length===d.lines.length&&"
            "opts.length===d.quiz.options.length&&"
            "document.getElementById('demo-card-face').textContent.trim().length>0;"
            "return ok?{source:d.source.name,slides:slides.length,lines:lines.length,"
            "quiz_options:opts.length,hero_width:hero.naturalWidth,fallbacks:fallback.length}:null; })()",
            "complete pre-baked guided demo",
            timeout=15,
        )
        check("guided_demo_prebaked_content", True, prebaked_demo)
        for _chapter in range(4):
            app.click("#btn-demo-next")
        app.wait_js(
            "!document.querySelector('[data-screen=demo] [data-ch=\"5\"]').hidden",
            "guided demo final chapter",
            timeout=15,
        )
        app.click("#btn-demo-run")
        guided_identity = app.wait_js(
            "(() => { const before=" + json.dumps(existing_job_ids) + "; "
            "const j=LP.data.jobs.find(x=>x&&x.id&&!before.includes(x.id)); "
            "return j?{id:j.id,status:j.status,stage:j.stage}:null; })()",
            "guided demo job",
            timeout=45,
        )
        guided_job_id = str((guided_identity or {}).get("id") or "")
        check("guided_demo_started", bool(guided_job_id), guided_identity)
        guided_ready = app.wait_js(
            f"(() => {{ const j=LP.data.jobs.find(x=>x&&x.id==={json.dumps(guided_job_id)}); "
            "const footer=((document.getElementById('status-state')||{}).textContent||'').trim().toLowerCase(); "
            "return j && LP.state.screen==='review' && (LP.data.slides||[]).length>0 && "
            "(footer==='review ready'||footer==='ready to export') ? "
            "{status:j.status,stage:j.stage,pct:j.pct,screen:LP.state.screen,"
            "footer_state:(document.getElementById('status-state')||{}).textContent||'',"
            "footer_detail:(document.getElementById('status-detail')||{}).textContent||'',"
            "slides:(LP.data.slides||[]).length} : null; })()",
            "guided demo Review Ready handoff",
            timeout=300,
        )
        app.wait_js("LP.state.screen === 'review'", "guided demo Review screen", timeout=15)
        guided_ready["screen"] = app.evaluate("LP.state.screen")
        guided_ready["footer_state"] = app.evaluate(
            "(document.getElementById('status-state')||{}).textContent||''"
        )
        check(
            "guided_demo_review_ready",
            guided_ready.get("screen") == "review"
            and guided_ready.get("slides", 0) > 0
            and str(guided_ready.get("footer_state") or "").strip().lower()
            in {"review ready", "ready to export"},
            guided_ready,
        )
        guided_shot = screenshots / "01b-guided-review-ready.png"
        app.screenshot(guided_shot)
        result["screenshots"].append(str(guided_shot))
        app.screen("home")
        app.click("#glowing-demo-card")
        app.wait_js(
            f"!LP.data.jobs.some(j=>j&&j.id==={json.dumps(guided_job_id)})",
            "guided demo cleanup",
            timeout=45,
        )
        check("guided_demo_cleanup", True, {"job_id": guided_job_id})
        guided_footer = app.wait_js(
            "(() => { const state=(document.getElementById('status-state')||{}).textContent||'',"
            "right=(document.getElementById('status-right')||{}).textContent||'',"
            "job=document.getElementById('status-job');"
            "return state.trim().toLowerCase()==='idle'&&job&&job.hidden&&"
            "!/(processing|transcrib|detect|extract|prepar)/i.test(right)?"
            "{state:state.trim(),right:right.trim(),job_hidden:job.hidden}:null; })()",
            "settled footer after guided demo cleanup",
            timeout=15,
        )
        check("guided_demo_footer_settled", True, guided_footer)
        completed_empty_rect = _window_rect(app.hwnd)
        completed_empty_size = [completed_empty_rect[2] - completed_empty_rect[0], completed_empty_rect[3] - completed_empty_rect[1]]
        app.resize(1024, 720)
        completed_empty_layout = app.layout_metrics()
        completed_empty_shot = screenshots / "01c-completed-tour-empty-1024x720.png"
        app.screenshot(completed_empty_shot)
        result["screenshots"].append(str(completed_empty_shot))
        app.resize(*completed_empty_size)
        check(
            "completed_tour_demo_action_visible",
            bool(completed_empty_layout.get("criticalIds"))
            and not completed_empty_layout.get("criticalOutOfView"),
            completed_empty_layout,
        )

        imported = app.request("import_paths", {"paths": [str(demo)]})
        imported_jobs = (imported or {}).get("jobs") or []
        job_id = str((imported_jobs[0] if imported_jobs else {}).get("id") or "")
        # import_paths intentionally emits the same batch-setup UI event used
        # by a folder/drop import.  This harness starts the canonical job with
        # an explicit auto_export contract below, so close that real modal via
        # its user-facing control before continuing.  Leaving it open made the
        # old screenshots look "green" while obscuring Review and Study.
        app.wait_js(
            "!document.getElementById('batch-overlay').hidden",
            "canonical import setup dialog",
            timeout=15,
        )
        app.click("#batch-close")
        app.wait_js(
            "document.getElementById('batch-overlay').hidden",
            "canonical import setup dialog close",
            timeout=15,
        )
        started = app.request(
            "start_job",
            {"job_id": job_id, "mode": "study", "preset": "balanced", "auto_export": True},
        ) if job_id else None
        check("canonical_demo_started", bool(job_id) and bool(started)
              and started.get("ok") is not False, {"import": imported, "start": started})
        app.wait_js(
            f"LP.data.jobs.some(j => j && j.id === {json.dumps(job_id)} && (j.status === 'running' || j.status === 'processing'))",
            "demo processing",
            timeout=45,
        )
        check("canonical_import_dialog_closed", not app.visible_blocking_dialogs(), app.visible_blocking_dialogs())
        app.screen("process")
        processing = screenshots / "02-process-live-progress.png"
        app.screenshot(processing)
        result["screenshots"].append(str(processing))
        live = app.evaluate(
            f"(() => {{ const j=LP.data.jobs.find(x=>x&&x.id==={json.dumps(job_id)}); return j || null; }})()"
        )
        check("canonical_live_progress", bool(live) and float(live.get("pct") or 0) >= 0,
              {"status": live.get("status") if live else None, "pct": live.get("pct") if live else None,
               "eta": live.get("eta") if live else None})

        app.wait_js(
            f"LP.data.jobs.some(j => j && j.id === {json.dumps(job_id)} && (j.status === 'done' || j.status === 'completed'))",
            "canonical demo completion",
            timeout=300,
        )
        check("canonical_demo_completed", True, {"job_id": job_id})

        pages = [
            ("review", "03-review.png"),
            ("transcript", "04-transcript.png"),
        ]
        for screen, file_name in pages:
            app.screen(screen)
            check(f"{screen}_unobscured", not app.visible_blocking_dialogs(), app.visible_blocking_dialogs())
            shot = screenshots / file_name
            app.screenshot(shot)
            result["screenshots"].append(str(shot))

        transcript = app.request("get_transcript", {"job_id": job_id})
        slides = app.request("get_slides", {"job_id": job_id})
        # Media completion and Study AI completion are intentionally
        # independent. Wait on the real Study status/content contract before
        # capturing or interacting with Study instead of racing its worker.
        content = app.wait_js(
            "window.lecturePackElectron.request('study_v2_status',{job_id:"
            + json.dumps(job_id)
            + "}).then(r=>{const c=(r||{}).content||{};return "
            "c.study_status==='ready'&&(c.concepts||[]).length>0&&"
            "(c.flashcards||[]).length>0&&(c.quiz||[]).length>0?c:null;})",
            "Study AI readiness",
            timeout=240,
        )
        app.screen("study")
        check("study_unobscured", not app.visible_blocking_dialogs(), app.visible_blocking_dialogs())
        study_shot = screenshots / "05-study-overview.png"
        app.screenshot(study_shot)
        result["screenshots"].append(str(study_shot))
        check(
            "guided_demo_cleanup_stayed_final",
            not (data / "jobs" / guided_job_id).exists(),
            {"job_id": guided_job_id, "checked_after_study_ai_ready": True},
        )
        check("slides_transcript_study", bool((slides or {}).get("slides")) and bool((transcript or {}).get("transcript"))
              and bool(content.get("concepts")), {
                  "slides": len((slides or {}).get("slides") or []),
                  "concepts": len(content.get("concepts") or []),
              })
        check("grounded_sources", any((item or {}).get("sources") for item in content.get("concepts") or []),
              {"concepts": len(content.get("concepts") or [])})

        app.click("[data-study-mode='flashcards']")
        app.wait_js("!document.querySelector('#study-mode-flashcards').hidden", "flashcards", timeout=15)
        flash = screenshots / "06-flashcards.png"
        app.screenshot(flash)
        result["screenshots"].append(str(flash))
        check("flashcards", bool(content.get("flashcards")), {"count": len(content.get("flashcards") or [])})

        app.click("[data-study-mode='quiz']")
        questions = content.get("quiz") or []
        correct = int(questions[0].get("correct_index", 0)) if questions else 0
        app.wait_js("document.querySelectorAll('.study-quiz-opt').length > 0", "quiz options", timeout=15)
        app.click(f".study-quiz-opt[data-opt='{correct}']")
        quiz = screenshots / "07-quiz-correct.png"
        app.screenshot(quiz)
        result["screenshots"].append(str(quiz))
        feedback = app.evaluate("document.querySelector('#study-quiz-feedback').innerText")
        check("quiz_correct_answer", "correct" in str(feedback).lower(), feedback)

        app.click("[data-study-mode='overview']")
        app.click("#btn-study-quick")
        app.wait_js(
            "!document.querySelector('#study-mode-quick').hidden&&"
            "document.querySelector('#study-quick-root').innerText.includes('Quick Study')",
            "Quick Study",
            timeout=15,
        )
        quick = screenshots / "08-quick-study.png"
        app.screenshot(quick)
        result["screenshots"].append(str(quick))
        check("quick_study", True)

        # Exercise the actual BrowserWindow minimum plus two common compact
        # desktop sizes.  The renderer intentionally hides horizontal
        # overflow, so a screenshot alone can miss unreachable controls; pair
        # each image with DOM geometry and scroll-width checks.
        original_rect = _window_rect(app.hwnd)
        original_size = [original_rect[2] - original_rect[0], original_rect[3] - original_rect[1]]
        responsive: list[dict[str, Any]] = []
        for width, height in ((640, 480), (820, 600), (1024, 720)):
            size_result = app.resize(width, height)
            for screen in ("demo", "home", "review", "study"):
                if screen == "demo":
                    # Enter through the shipped replay control.  Renderer
                    # internals live inside an IIFE and are intentionally not
                    # a CDP/global API; exercising the real Settings action
                    # also verifies that a completed tour can be replayed.
                    app.screen("settings")
                    app.click("#btn-replay-tour")
                    app.wait_js("LP.state.screen === 'demo'", "responsive demo screen", timeout=15)
                    for _chapter in range(3):
                        app.click("#btn-demo-next")
                    app.wait_js(
                        "!document.querySelector('[data-screen=demo] [data-ch=\"4\"]').hidden",
                        "responsive demo Study chapter",
                        timeout=15,
                    )
                else:
                    app.screen(screen)
                time.sleep(0.25)
                metrics = app.layout_metrics()
                horizontal_ok = all(
                    not block or int(block.get("scrollWidth") or 0) <= int(block.get("clientWidth") or 0) + 2
                    for block in (
                        metrics.get("document"),
                        metrics.get("header"),
                        metrics.get("main"),
                        metrics.get("active"),
                        metrics.get("footer"),
                    )
                )
                item_ok = (
                    horizontal_ok
                    and not metrics.get("clippedHeader")
                    and not metrics.get("clippedScreen")
                    and not metrics.get("criticalOutOfView")
                    and not metrics.get("dialogs")
                )
                shot = screenshots / f"08-responsive-{width}x{height}-{screen}.png"
                app.screenshot(shot)
                result["screenshots"].append(str(shot))
                responsive.append({
                    "requested": [width, height],
                    "screen": screen,
                    "ok": item_ok,
                    "size": size_result,
                    "metrics": metrics,
                    "screenshot": str(shot),
                })
        app.resize(*original_size)
        check("responsive_window_matrix", all(item["ok"] for item in responsive), responsive)

        exports = data / "jobs" / job_id / "exports"
        exported = sorted(path.name for path in exports.rglob("*") if path.is_file()) if exports.is_dir() else []
        check("thirteen_file_export", len(exported) == 13, exported)

        # Folder/multi-file import through the packaged host: one real media
        # file, one duplicate path, and junk. Exact-path duplicates and junk
        # must not become additional media candidates.
        batch = workspace / "batch-drop"
        batch.mkdir(parents=True, exist_ok=True)
        batch_media = batch / "Polar Bears copy.mp4"
        shutil.copy2(demo, batch_media)
        (batch / "notes.txt").write_text("not media", encoding="utf-8")
        batch_result = app.request("import_paths", {"paths": [str(batch), str(batch_media), str(batch / "notes.txt")]})
        check("folder_multi_file_junk_duplicate", bool(batch_result) and batch_result.get("ok") is not False,
              batch_result)

        # Existing-instance Send To: a second process forwards the file and
        # exits because the first owns the single-instance lock.
        before_count = int(app.evaluate("LP.data.jobs.length") or 0)
        second = subprocess.run([str(args.exe.resolve()), f"--user-data-dir={profile}", str(args.secondary.resolve())],
                                cwd=str(args.exe.resolve().parent), timeout=30, check=False)
        app.wait_js(f"LP.data.jobs.length > {before_count}", "existing-instance Send To import", timeout=45)
        check("send_to_existing_instance", second.returncode == 0,
              {"second_exit": second.returncode, "jobs_before": before_count,
               "jobs_after": app.evaluate("LP.data.jobs.length")})

        # Continue state: visit transcript, persist, return Home, and require
        # the visible Continue card to route back to the same lecture/screen.
        app.screen("transcript")
        app.screen("home")
        app.wait_js("!document.querySelector('#continue-card').hidden", "Continue card", timeout=15)
        app.click("#btn-continue")
        check("continue_screen_mode_state", app.wait_js("LP.state.screen === 'transcript'", "Continue destination", 15) is True,
              {"screen": app.evaluate("LP.state.screen"), "job_id": app.evaluate("LP.state.jobId")})

        # Relaunch/restore on the same disposable data and Chromium profile.
        orphans_first = app.close()
        check("clean_shutdown_no_orphans", not orphans_first, orphans_first)
        (profile / "close-to-tray.json").write_text('{"choice":"background"}\n', encoding="utf-8")
        app = PackagedApp(args.exe.resolve(), profile, data, logs)
        app.launch()
        restored = app.wait_js(
            f"LP.data.jobs.some(j => j && j.id === {json.dumps(job_id)})",
            "session/job restore",
            timeout=60,
        )
        check("session_study_transcript_window_restore", bool(restored), {
            "screen": app.evaluate("LP.state.screen"),
            "job_id": app.evaluate("LP.state.jobId"),
            "window_state_exists": (profile / "window-state.json").is_file(),
        })

        # Long real workload: prove system-sleep prevention, close-to-tray,
        # existing-instance restore, cancellation, and blocker release.
        long_import = app.request("import_paths", {"paths": [str(args.long.resolve())]})
        long_jobs = (long_import or {}).get("jobs") or []
        secondary_job = str((long_jobs[0] if long_jobs else {}).get("id") or "")
        check("long_regression_media_imported", bool(secondary_job), {"job_id": secondary_job, "result": long_import})
        if secondary_job:
            started_long = app.request("start_job", {"job_id": secondary_job, "mode": "study", "preset": "balanced", "auto_export": False})
            app.wait_js(
                f"LP.data.jobs.some(j=>j&&j.id==={json.dumps(secondary_job)}&&(j.status==='running'||j.status==='processing'))",
                "secondary workload start",
                timeout=45,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not any(r.get("event") == "power_save_acquired" for r in read_records(logs)):
                time.sleep(0.25)
            check("power_save_blocker_active", any(r.get("event") == "power_save_acquired" for r in read_records(logs)), started_long)
            eta_detail = app.wait_js(
                f"(() => {{ const j=LP.data.jobs.find(x=>x&&x.id==={json.dumps(secondary_job)}); "
                "const el=document.getElementById('status-detail'); const label=el?el.textContent.trim():''; "
                "return j && Number(j.pct)>0 && /min left/i.test(label) ? "
                "{pct:j.pct,eta_label:label,stage:j.stage} : null; })()",
                "live progress and ETA on long workload",
                timeout=120,
            )
            check("live_background_progress_eta", bool(eta_detail), eta_detail)
            user32.PostMessageW(app.hwnd, WM_CLOSE, 0, 0)
            time.sleep(2)
            records = read_records(logs)
            check("tray_background_long_workload", app.proc is not None and app.proc.poll() is None
                  and any(r.get("event") == "close_to_tray" for r in records),
                  {"process_alive": app.proc.poll() is None if app.proc else False})
            restore_second = subprocess.run(
                [str(args.exe.resolve()), f"--user-data-dir={profile}"],
                cwd=str(args.exe.resolve().parent), timeout=30, check=False,
            )
            time.sleep(1)
            check("tray_restore_via_existing_instance", restore_second.returncode == 0, restore_second.returncode)
            app.request("cancel_job", {"job_id": secondary_job})
            app.wait_js(
                f"LP.data.jobs.some(j=>j&&j.id==={json.dumps(secondary_job)}&&(j.status==='cancelled'||j.status==='failed'||j.status==='interrupted'))",
                "long workload cancellation",
                timeout=60,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not any(r.get("event") == "power_save_released" for r in read_records(logs)):
                time.sleep(0.25)
            check("power_save_blocker_released", any(r.get("event") == "power_save_released" for r in read_records(logs)))

            # Retry the cancelled job and run a slow local download, then kill
            # the process tree. The next packaged launch must recover both.
            retry = app.request("resume_job", {"job_id": secondary_job})
            app.wait_js(
                f"LP.data.jobs.some(j=>j&&j.id==={json.dumps(secondary_job)}&&(j.status==='running'||j.status==='processing'||j.status==='queued'))",
                "job retry",
                timeout=45,
            )
            check("cancel_retry", bool(retry) and retry.get("ok") is not False, retry)
            media_server = SlowMediaServer(args.secondary.resolve())
            media_server.start()
            queued_download = app.request("import_media_url", {"items": [{"url": media_server.url, "title": "Recovery fixture"}]})
            download_id = str((((queued_download or {}).get("downloads") or [{}])[0]).get("id") or "")
            app.wait_js(
                "window.lecturePackElectron.request('get_media_downloads',{}).then(r => "
                + json.dumps(download_id)
                + " && (r.downloads||[]).some(d=>d.id==="
                + json.dumps(download_id)
                + " && (d.status==='waiting'||d.status==='running'||"
                + "d.legacy_status==='waiting'||d.legacy_status==='downloading')))",
                "active download before interruption",
                timeout=45,
            )
            app.crash()
            time.sleep(1)
            app = PackagedApp(args.exe.resolve(), profile, data, logs)
            app.launch()
            recovered_downloads = app.request("get_media_downloads", {})
            recovered_row = next((row for row in (recovered_downloads or {}).get("downloads", [])
                                  if row.get("id") == download_id), None)
            check("interrupted_download_recovery", bool(recovered_row)
                  and recovered_row.get("status") == "failed"
                  and "Retry" in str(recovered_row.get("error") or ""), recovered_row)
            job_recovered = app.wait_js(
                f"LP.data.jobs.some(j=>j&&j.id==={json.dumps(secondary_job)}&&(j.status==='running'||j.status==='processing'||j.status==='queued'||j.status==='interrupted'))",
                "interrupted job recovery",
                timeout=60,
            )
            check("interrupted_job_recovery", bool(job_recovered), {"job_id": secondary_job})
            app.click("#downloads-indicator")
            recovered_shot = screenshots / "09-downloads-recovery.png"
            app.screenshot(recovered_shot)
            result["screenshots"].append(str(recovered_shot))
            retried_download = app.request("retry_media_download", {"download_id": download_id})
            app.request("cancel_media_url", {"download_id": download_id})
            check("download_cancel_retry", bool(retried_download) and retried_download.get("retried") is True,
                  retried_download)
            media_server.close()

            # Visual updater state: updater lifecycle itself is exercised by
            # the controlled A-to-B module test; this drives the real packaged
            # renderer event and captures the user-visible available state.
            app.screen("settings")
            app.evaluate("lpBridge.emit('update_available', JSON.stringify({version:'2.1.0', notes:'Controlled acceptance update'}))")
            app.wait_js("!document.querySelector('#whatsnew-overlay').hidden", "update available overlay", timeout=15)
            update_shot = screenshots / "10-update-available.png"
            app.screenshot(update_shot)
            result["screenshots"].append(str(update_shot))
            check("update_available_visual", True)

        # A real packaged missing-sidecar launch must reach the actionable
        # terminal screen. Temporarily hold only the disposable candidate's
        # sidecar executable and restore it in a finally block.
        pre_failure_orphans = app.close()
        check("pre_failure_zero_orphans", not pre_failure_orphans, pre_failure_orphans)
        sidecar_exe = args.exe.resolve().parent / "resources" / "LecturePackSidecar" / "LecturePackSidecar.exe"
        held_sidecar = sidecar_exe.with_suffix(".exe.acceptance-held")
        sidecar_exe.replace(held_sidecar)
        try:
            app = PackagedApp(
                args.exe.resolve(), workspace / "Failure Profile", workspace / "Failure Data",
                evidence / "startup-failure-logs",
            )
            app.launch(expect_startup_failure=True)
            app.wait_js(
                "!document.querySelector('#runtime-setup-overlay').hidden && "
                "!document.querySelector('[data-runtime-state=startup_failed]').hidden",
                "startup failure screen",
                timeout=35,
            )
            failure_shot = screenshots / "11-startup-failure.png"
            app.screenshot(failure_shot)
            result["screenshots"].append(str(failure_shot))
            actions = app.evaluate(
                "['btn-startup-retry','btn-startup-copy','btn-startup-open-logs'].every(id=>{const e=document.getElementById(id);return e&&!e.hidden;})"
            )
            check("startup_failure_visual_actions", actions is True)
        finally:
            try:
                app.close()
            finally:
                if held_sidecar.is_file() and not sidecar_exe.exists():
                    held_sidecar.replace(sidecar_exe)
    except Exception as exc:
        result["failures"].append(f"exception:{type(exc).__name__}")
        result["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            final_orphans = app.close()
        except Exception as exc:
            final_orphans = [{"error": str(exc)}]
        check("final_zero_orphans", not final_orphans, final_orphans)
        result["ended_at"] = iso_now()
        result["status"] = "PASS" if not result["failures"] else "FAIL"
        result["logs"] = read_records(logs)
        (evidence / "stable-release-acceptance.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--packaged-demo", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--long", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    result = run(parse_args())
    print(json.dumps({"status": result["status"], "failures": result["failures"]}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
