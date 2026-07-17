"""Real child-tree fixture: writes its child PID, then both processes wait."""
from __future__ import annotations

import subprocess
import os
import sys
import time


pid_path = os.environ.get("LECTUREPACK_TREE_PID_FILE") or sys.argv[1]
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
with open(pid_path, "w", encoding="ascii") as handle:
    handle.write(str(child.pid))
    handle.flush()
time.sleep(60)
