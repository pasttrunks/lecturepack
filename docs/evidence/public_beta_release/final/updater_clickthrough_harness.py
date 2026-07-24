"""Interactive updater click-through harness (SAFE, local fake feed).

Runs the PACKAGED LecturePack against a local fake GitHub release feed so a
human can perform the §4 update walkthrough. No real GitHub release is created
and no unsafe payload is executed by the app's verify step (the fake installer
is a tiny text file; on "Install Now" the app will try to launch it visibly —
just close/cancel the resulting Windows dialog).

Usage (from repo root):
    .venv\\Scripts\\python.exe docs\\evidence\\public_beta_release\\final\\updater_clickthrough_harness.py
    # add  --mismatch  to serve a WRONG checksum (verify must block install)

Then in the app window: Settings shows v0.9.0-beta.1; a banner offers
v0.9.0-beta.2. Click View Update -> check the overview fields -> try Remind Me
Later / Skip This Version -> Download and Install -> watch progress + Cancel ->
let it finish -> Update Ready (or, with --mismatch, a rejection message).
Press Ctrl+C here to stop the feed when done.
"""
import argparse
import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "app")
sys.path.insert(0, APP)
from PySide6.QtCore import QSettings  # noqa: E402
from desktop import version as V  # noqa: E402

EXE = os.path.join(APP, "dist", "LecturePack", "LecturePack.exe")
BYTES = b"LECTUREPACK-FAKE-INSTALLER" * 40
DIG = hashlib.sha256(BYTES).hexdigest()
SETUP = "LecturePack-0.9.0-beta.2-Setup.exe"
PORT_ZIP = "LecturePack-0.9.0-beta.2-Portable.zip"
SUMS = "LecturePack-0.9.0-beta.2-SHA256SUMS.txt"


def make_handler(mismatch):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            print("  feed <-", self.path)

        def do_GET(self):
            port = self.server.server_address[1]
            base = f"http://127.0.0.1:{port}"
            if self.path.startswith("/releases"):
                rel = {"tag_name": "v0.9.0-beta.2", "name": "LecturePack Public Beta 2",
                       "draft": False, "prerelease": True,
                       "published_at": "2026-07-25T09:00:00Z",
                       "html_url": "https://github.com/pasttrunks/lecturepack/releases",
                       "body": ("## Improvements\n- Faster slide detection\n- Clearer Study labels\n"
                                "## Fixes\n- Export layout fix\n## Known limitations\n- Beta\n"),
                       "assets": [
                           {"name": SETUP, "size": len(BYTES), "state": "uploaded",
                            "digest": f"sha256:{DIG}", "browser_download_url": f"{base}/dl/{SETUP}"},
                           {"name": PORT_ZIP, "size": len(BYTES), "state": "uploaded",
                            "browser_download_url": f"{base}/dl/{PORT_ZIP}"},
                           {"name": SUMS, "size": 200, "state": "uploaded",
                            "browser_download_url": f"{base}/dl/{SUMS}"}]}
                b = json.dumps([rel]).encode(); ct = "application/json"
            elif self.path.endswith(SUMS):
                d = ("0" * 64) if mismatch else DIG
                b = f"{d}  {SETUP}\n{d}  {PORT_ZIP}\n".encode(); ct = "text/plain"
            else:
                b = BYTES; ct = "application/octet-stream"
            self.send_response(200); self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(b))); self.end_headers()
            self.wfile.write(b)
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mismatch", action="store_true", help="serve a wrong checksum")
    args = ap.parse_args()
    if not os.path.exists(EXE):
        sys.exit(f"packaged exe not found: {EXE} (run app/packaging/build.py first)")

    s = QSettings(V.ORG_NAME, V.APP_NAME)
    s.setValue("auto_check_enabled", True); s.setValue("update_channel", "beta")
    s.setValue("last_check_at", "0"); s.setValue("skipped_version", ""); s.sync()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.mismatch))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    env = dict(os.environ)
    env["LECTUREPACK_UPDATE_FEED"] = f"http://127.0.0.1:{port}/releases"
    env["LECTUREPACK_UPDATE_HOSTS"] = "127.0.0.1"
    print(f"Fake feed on http://127.0.0.1:{port}/releases  (mismatch={args.mismatch})")
    print("Launching packaged LecturePack… close the app window or Ctrl+C to stop.")
    proc = subprocess.Popen([EXE], env=env)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    finally:
        srv.shutdown()
        s.setValue("last_check_at", "0"); s.sync()


if __name__ == "__main__":
    main()
