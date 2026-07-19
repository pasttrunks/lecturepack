"""
capture_screens.py — Capture screenshots of the LecturePack UI for README assets.

Usage:
    python capture_screens.py

Requirements:
    pip install mss Pillow pyautogui

This script launches LecturePack, waits for it to render, captures only the
main window as assets/hero.png, then navigates to the Study page with Focus
Mode and captures assets/focus_mode.png. Finally it kills the app process.

NOTE: This script must be run on a machine with a display. It will not work
in headless CI environments.
"""

import subprocess
import sys
import time
import os
import ctypes
import ctypes.wintypes

# ---------- Windows window-finding helpers ----------

EnumWindows = ctypes.windll.user32.EnumWindows
GetWindowTextW = ctypes.windll.user32.GetWindowTextW
GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowRect = ctypes.windll.user32.GetWindowRect
GetClassName = ctypes.windll.user32.GetClassNameW

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

def find_window_by_title(substr):
    """Find the first visible window whose title contains `substr`."""
    result = []

    def callback(hwnd, _):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buf, length + 1)
                if substr.lower() in buf.value.lower():
                    result.append(hwnd)
                    return False  # stop enumerating
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return result[0] if result else None

def get_window_rect(hwnd):
    """Return (left, top, right, bottom) for the given window handle."""
    rect = ctypes.wintypes.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


# ---------- Screenshot helpers ----------

def find_mss():
    try:
        import mss
        return mss
    except ImportError:
        return None

def mss_to_pil(sct, shot):
    """Convert an mss screen shot to a PIL Image (works with mss 10.x)."""
    from PIL import Image
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

def find_pillow():
    try:
        from PIL import Image, ImageGrab
        return Image, ImageGrab
    except ImportError:
        return None, None

def capture_window(hwnd, filename):
    """Capture only the given window and save to filename."""
    left, top, right, bottom = get_window_rect(hwnd)
    width = right - left
    height = bottom - top
    print(f"  Window rect: {left},{top} {width}x{height}")

    if width <= 0 or height <= 0:
        print("  ERROR: Window has zero size — is it minimized?")
        return False

    mss_mod = find_mss()
    if mss_mod:
        with mss_mod.MSS() as sct:
            monitor = {"left": left, "top": top, "width": width, "height": height}
            shot = sct.grab(monitor)
            img = mss_to_pil(sct, shot)
            os.makedirs("assets", exist_ok=True)
            img.save(filename)
            print(f"  Saved {filename}")
            return True

    _, ImageGrab = find_pillow()
    if ImageGrab:
        img = ImageGrab.grab(bbox=(left, top, right, bottom))
        os.makedirs("assets", exist_ok=True)
        img.save(filename)
        print(f"  Saved {filename}")
        return True

    print("  ERROR: No screenshot library available")
    return False


# ---------- Main ----------

def main():
    print("LecturePack Screenshot Capture")
    print("=" * 40)

    # Check dependencies
    mss = find_mss()
    pillow = find_pillow()
    print(f"  mss: {'installed' if mss else 'NOT INSTALLED'}")
    print(f"  Pillow: {'installed' if pillow[0] else 'NOT INSTALLED'}")

    if not mss and pillow == (None, None):
        print("\nERROR: Need at least mss or Pillow. Install with:")
        print("  pip install mss Pillow")
        sys.exit(1)

    # Launch LecturePack
    print("\nLaunching LecturePack...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "lecturepack.app"],
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
    )
    print(f"  PID: {proc.pid}")

    # Wait for app to launch and render
    print("Waiting 6 seconds for app to render...")
    time.sleep(6)

    # Find the LecturePack window
    print("\nLocating LecturePack window...")
    hwnd = find_window_by_title("Lecture Pack")
    if hwnd is None:
        # Try alternate title variations
        for title in ["LecturePack", "lecturepack", "Lecture"]:
            hwnd = find_window_by_title(title)
            if hwnd:
                break

    if hwnd is None:
        print("  ERROR: Could not find LecturePack window.")
        print("  Capturing full primary monitor as fallback...")
        mss_mod = find_mss()
        if mss_mod:
            with mss_mod.MSS() as sct:
                shot = sct.grab(sct.monitors[1])
                img = mss_to_pil(sct, shot)
                os.makedirs("assets", exist_ok=True)
                img.save("assets/hero.png")
                print("  Saved assets/hero.png (full screen fallback)")
        proc.terminate()
        proc.wait(timeout=5)
        sys.exit(1)

    print(f"  Found window handle: {hwnd:#x}")

    # Capture hero screenshot
    print("\nCapturing hero screenshot...")
    capture_window(hwnd, "assets/hero.png")

    # Capture focus mode (optional — requires pyautogui)
    print("\nAttempting focus mode capture...")
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        # Bring window to front
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)

        # Navigate to Study page: click 2nd nav item (Study is after Home)
        left, top, right, bottom = get_window_rect(hwnd)
        nav_x = left + 35       # nav rail center x
        study_y = top + 120     # approximate Study icon y
        pyautogui.click(nav_x, study_y)
        time.sleep(2)

        # Toggle Focus Mode (Ctrl+Shift+F)
        pyautogui.hotkey('ctrl', 'shift', 'f')
        time.sleep(1.5)

        capture_window(hwnd, "assets/focus_mode.png")

    except ImportError:
        print("  SKIPPED: pyautogui not installed (pip install pyautogui)")
    except Exception as e:
        print(f"  SKIPPED: {e}")

    # Kill the app
    print(f"\nKilling LecturePack (PID {proc.pid})...")
    try:
        proc.terminate()
        proc.wait(timeout=5)
        print("  Process terminated cleanly.")
    except subprocess.TimeoutExpired:
        proc.kill()
        print("  Process killed (force).")
    except Exception as e:
        print(f"  Kill error: {e}")

    print("\nDone! Check assets/ for screenshots.")

if __name__ == "__main__":
    main()
