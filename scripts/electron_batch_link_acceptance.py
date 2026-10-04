"""Opt-in real Electron UI batch download/import/restart gate (Windows).

Run alone: process snapshots are not reliable while another test launches tools.
Only explicitly supplied public URLs are fetched. Existing profiles/results are
refused, evidence is retained, and no processing or AI generation is started.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from electron_packaged_acceptance import (
    _close_app_window, data_dir_status, detect_orphans, poll_until, snapshot_processes,
)


def validate_batch(data_dir: Path, urls: list[str]) -> list[dict]:
    """Require one real, inspected, persisted job per completed download."""
    state = json.loads((data_dir / "downloads-state.json").read_text(encoding="utf-8"))
    downloads = state["downloads"]
    if [item["url"] for item in downloads] != urls:
        raise ValueError("download count/order differs from the pasted batch")
    manifests = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (data_dir / "jobs").glob("*/manifest.json")]
    if len(manifests) != len(urls):
        raise ValueError("not every download became a persisted lecture")
    evidence = []
    for item in downloads:
        if item["status"] not in ("complete", "completed") or item.get("error"):
            raise ValueError(f"download failed: {item['url']}: {item.get('error', '')}")
        path = Path(item["path"]).resolve()
        if not path.is_relative_to((data_dir / "downloads").resolve()):
            raise ValueError("download path escaped the disposable profile")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("downloaded recording is absent or empty")
        matches = [m for m in manifests if Path(m["source"]["original_path"]).resolve() == path]
        if len(matches) != 1:
            raise ValueError("recording must map to exactly one persisted job")
        job = matches[0]
        source = json.loads((data_dir / "jobs" / job["job_id"] / "source.json").read_text(encoding="utf-8"))
        if source.get("duration", 0) <= 0 or source.get("width", 0) <= 0:
            raise ValueError("recording has no successful media inspection")
        with path.open("rb") as recording:
            digest = hashlib.file_digest(recording, "sha256").hexdigest()
        evidence.append({"url": item["url"], "job_id": job["job_id"],
                         "title": job["title"], "bytes": path.stat().st_size,
                         "duration": source["duration"],
                         "sha256": digest})
    return evidence


def run(args: argparse.Namespace) -> dict:
    from packaged_visual_acceptance import _cdp_target

    data = Path(args.data_dir).resolve()
    results = Path(args.results_dir).resolve()
    allowed, reason = data_dir_status(data)
    if not allowed or data.exists() or results.exists():
        raise ValueError(reason or "use new disposable data and results directories")
    urls = list(dict.fromkeys(args.url))
    if len(urls) < 2 or any(not u.startswith(("https://", "http://")) or any(c.isspace() for c in u) for u in urls):
        raise ValueError("supply at least two distinct full public http(s) URLs")
    data.mkdir(parents=True)
    results.mkdir(parents=True)
    exe = Path(args.exe).resolve()
    env = os.environ.copy()
    env["LECTUREPACK_DATA_DIR"] = str(data)
    report = {"passed": False, "urls": urls, "launches": [], "errors": []}
    before = snapshot_processes()
    try:
        for launch in range(2):
            proc = subprocess.Popen([str(exe), "--data-dir", str(data), "--results", str(results),
                                     f"--remote-debugging-port={args.port}"],
                                    cwd=exe.parent, env=env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            cdp = None
            forced = False
            try:
                cdp = _cdp_target(args.port, args.timeout)

                def evaluate(expression):
                    return cdp.evaluate(expression)

                def click(label):
                    # Exact labels: a prefix 'Download' also matches 'Downloads'.
                    evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(b=>"
                             "b.offsetWidth&&!b.disabled&&b.textContent.trim()===" + json.dumps(label) +
                             ");if(!b)throw Error('Missing button');b.click();return true})()")

                if launch == 0:
                    poll_until(lambda: evaluate("!!document.querySelector('#btn-runtime-done')&&"
                                                "!document.querySelector('#btn-runtime-done').disabled"), args.timeout)
                    evaluate("document.querySelector('#btn-runtime-done').click()")
                    poll_until(lambda: evaluate("!document.querySelector('#btn-paste-link').disabled"), args.timeout)
                    evaluate("document.querySelector('#btn-paste-link').click()")
                    poll_until(lambda: evaluate("!!document.querySelector('#link-url')"), args.timeout)
                    # Mix whitespace and repeat the first URL to exercise deduplication.
                    evaluate("document.querySelector('#link-url').value=" + json.dumps(" \n".join(urls + [urls[0]])))
                    click("Check link")
                    poll_until(lambda: evaluate("!document.querySelector('#link-url')"), args.timeout)
                    (results / "confirmation.txt").write_text(evaluate("document.body.innerText"), encoding="utf-8")
                    click(f"Download {len(urls)}")
                    poll_until(lambda: _batch_ready(data, urls), args.timeout)
                    report["lectures"] = validate_batch(data, urls)
                ids = sorted(item["job_id"] for item in report["lectures"])
                poll_until(lambda: evaluate("JSON.stringify((window.LP?.data?.jobs||[]).map(j=>j.id).sort())") == json.dumps(ids, separators=(",", ":")), args.timeout)
                report["launches"].append({"restored_job_ids": ids})
                (results / f"launch-{launch}.txt").write_text(evaluate("document.body.innerText"), encoding="utf-8")
                (results / f"launch-{launch}.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot")["data"]))
            finally:
                if proc.poll() is None:
                    if not _close_app_window(proc.pid):
                        forced = True
                        proc.terminate()
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        forced = True
                        proc.kill()
                        proc.wait(timeout=10)
                if cdp:
                    cdp.close()
                if forced or proc.returncode != 0:
                    report["errors"].append(f"launch {launch}: forced={forced}, exit={proc.returncode}")
        if validate_batch(data, urls) != report["lectures"]:
            raise ValueError("download/job evidence changed across restart")
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        report["orphans"] = detect_orphans(before, snapshot_processes())
        report["passed"] = not report["errors"] and not report["orphans"] and len(report["launches"]) == 2
        (results / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _batch_ready(data: Path, urls: list[str]) -> bool:
    try:
        validate_batch(data, urls)
        return True
    except (OSError, ValueError, KeyError):
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("exe", "data-dir", "results-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--port", type=int, default=9321)
    parser.add_argument("--timeout", type=float, default=240)
    arguments = parser.parse_args()
    if sys.platform != "win32":
        parser.error("real packaged gate requires Windows")
    outcome = run(arguments)
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["passed"] else 1)
