"""
capture_screens.py — Capture screenshots of the LecturePack UI for README assets.

Usage:
    python capture_screens.py

Requirements:
    pip install mss Pillow pyautogui

This script launches LecturePack, waits for it to render, captures the main
window as assets/hero.png, then navigates to the Study page with Focus Mode
and captures assets/focus_mode.png. Finally it kills the app process.

NOTE: This script must be run on a machine with a display. It will not work
in headless CI environments.
"""

import subprocess
import sys
import time
import os

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

def capture_hero():
    """Capture the main window as assets/hero.png after app launches."""
    mss_mod = find_mss()
    if mss_mod is None:
        print("WARN: mss not installed, falling back to Pillow")
        _, ImageGrab = find_pillow()
        if ImageGrab is None:
            print("ERROR: Neither mss nor Pillow is available. Install with: pip install mss Pillow")
            return False
        img = ImageGrab.grab()
        os.makedirs("assets", exist_ok=True)
        img.save("assets/hero.png")
        print("Saved assets/hero.png via Pillow ImageGrab")
        return True

    with mss_mod.MSS() as sct:
        monitor = sct.monitors[1]  # primary monitor
        screenshot = sct.grab(monitor)
        img = mss_to_pil(sct, screenshot)
        os.makedirs("assets", exist_ok=True)
        img.save("assets/hero.png")
        print("Saved assets/hero.png via mss")
        return True

def capture_focus_mode():
    """Try to navigate to Study page and toggle Focus Mode, then capture."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        # Give app time to settle
        time.sleep(1)

        # Try clicking the Study nav item (approximately 2nd item in nav rail)
        # The nav rail is on the left side; Study is typically the first item after Home
        screen_w, screen_h = pyautogui.size()

        # Nav rail is roughly 60px wide on the left. Study icon is ~120px from top
        nav_x = 35
        study_y = 120  # approximate position of Study nav item

        pyautogui.click(nav_x, study_y)
        time.sleep(2)

        # Try to activate Focus Mode (Ctrl+Shift+F or via menu)
        # Focus mode hides nav rail — try the keyboard shortcut
        pyautogui.hotkey('ctrl', 'shift', 'f')
        time.sleep(1.5)

        mss_mod = find_mss()
        if mss_mod:
            with mss_mod.MSS() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = mss_to_pil(sct, screenshot)
                img.save("assets/focus_mode.png")
                print("Saved assets/focus_mode.png via mss")
                return True
        else:
            _, ImageGrab = find_pillow()
            if ImageGrab:
                img = ImageGrab.grab()
                img.save("assets/focus_mode.png")
                print("Saved assets/focus_mode.png via Pillow")
                return True
    except ImportError:
        print("WARN: pyautogui not installed, skipping focus mode capture")
        print("  Install with: pip install pyautogui")
    except Exception as e:
        print(f"WARN: Could not capture focus mode: {e}")
    return False

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
    print("Waiting 5 seconds for app to render...")
    time.sleep(5)

    # Capture hero screenshot
    print("\nCapturing hero screenshot...")
    capture_hero()

    # Capture focus mode (optional)
    print("\nAttempting focus mode capture...")
    try:
        capture_focus_mode()
    except Exception as e:
        print(f"  Focus mode capture skipped: {e}")

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
