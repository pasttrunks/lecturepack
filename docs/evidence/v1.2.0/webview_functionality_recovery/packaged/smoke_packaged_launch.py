"""Phase 2 packaged smoke: launch the frozen exe from a path WITH SPACES and
confirm it starts without a frozen-path / scheme-registration crash.

We can't drive the packaged GUI's WebEngine from outside, so this verifies:
 - the onedir bundle can be copied to a spaces-containing path,
 - the exe boots offscreen and stays alive (no early crash),
 - it emits no fatal Python traceback on startup.
Interactive asset/settings/ollama/hover acceptance still needs a human.
"""
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "dist", "LecturePack")
DEST_PARENT = os.path.join(os.environ.get("TEMP", "/tmp"), "LP Packaged Test dir")
DEST = os.path.join(DEST_PARENT, "LecturePack")
EXE = os.path.join(DEST, "LecturePack.exe")

if not os.path.isdir(SRC):
    print("BLOCKER: no build at", SRC)
    sys.exit(2)

# Copy the onedir bundle to a clean path containing spaces.
if os.path.isdir(DEST_PARENT):
    shutil.rmtree(DEST_PARENT, ignore_errors=True)
os.makedirs(DEST_PARENT, exist_ok=True)
print("copying bundle to:", DEST)
t0 = time.time()
shutil.copytree(SRC, DEST)
print(f"copied in {time.time()-t0:.1f}s")
# PyInstaller 6 onedir bundles data under _internal/ (== sys._MEIPASS).
print("index.html @ _internal/ui:",
      os.path.isfile(os.path.join(DEST, "_internal", "ui", "index.html")))
print("app.js @ _internal/ui:",
      os.path.isfile(os.path.join(DEST, "_internal", "ui", "app.js")))

env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"

print("launching:", EXE)
proc = subprocess.Popen([EXE], cwd=DEST, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(12)  # let it boot + load index.html + register scheme
alive = proc.poll() is None
print("alive_after_12s:", alive, "exit_code:", proc.returncode)
if alive:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
else:
    out, _ = proc.communicate()

tail = "\n".join((out or "").splitlines()[-25:])
print("----- startup output tail -----")
print(tail)
print("----- end -----")

fatal = any(k in (out or "") for k in ("Traceback (most recent call last)",
                                       "ModuleNotFoundError", "ImportError",
                                       "Failed to execute script"))
ok = alive and not fatal
print("PACKAGED_SMOKE_OK" if ok else "PACKAGED_SMOKE_FAIL")
# Clean up the copied bundle.
shutil.rmtree(DEST_PARENT, ignore_errors=True)
sys.exit(0 if ok else 1)
