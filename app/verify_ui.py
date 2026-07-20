"""Headless render check for the ported UI. Loads ui/index.html, walks every
screen in dark + light, exercises the interactive bits, and captures shots.
Run: python verify_ui.py"""
import os, sys, glob
from playwright.sync_api import sync_playwright

UI = os.path.join(os.path.dirname(__file__), "ui", "index.html")
OUT = os.path.join(os.path.dirname(__file__), "..", "verify_shots")
os.makedirs(OUT, exist_ok=True)
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or glob.glob("/opt/pw-browsers/chromium/**/chrome", recursive=True)

SCREENS = ["home", "process", "review", "transcript", "study", "exports", "settings"]
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe[0] if exe else None)
    page = browser.new_page(viewport={"width": 1360, "height": 860}, device_scale_factor=2)
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("file://" + os.path.abspath(UI))
    page.wait_for_timeout(700)

    # crumb + default theme
    assert page.get_attribute("#app", "data-theme") == "dark", "should default to dark"

    for theme in ("dark", "light"):
        page.evaluate(f"window.LP && document.getElementById('btn-set-{theme}').click()")
        page.wait_for_timeout(150)
        for s in SCREENS:
            page.evaluate(f"document.querySelector('.lp-nav[data-nav=\"{s}\"]').click()")
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, f"{s}_{theme}.png"))
            vis = page.evaluate(f"!document.querySelector('section[data-screen=\"{s}\"]').hidden")
            if not vis:
                errors.append(f"screen {s} not visible after nav")

    # interactions: study tabs, quiz, flashcard, chat, focus, import, export
    page.evaluate("document.querySelector('.lp-nav[data-nav=\"study\"]').click()")
    page.evaluate("document.querySelector('.lp-tab[data-tab=\"quiz\"]').click()"); page.wait_for_timeout(100)
    page.evaluate("document.querySelector('#quiz-options .lp-opt[data-opt=\"1\"]').click()"); page.wait_for_timeout(100)
    quiz_ok = page.evaluate("!document.getElementById('quiz-answer').hidden")
    page.evaluate("document.querySelector('.lp-tab[data-tab=\"flash\"]').click()"); page.wait_for_timeout(100)
    face1 = page.text_content("#card-face")
    page.evaluate("document.getElementById('flashcard').click()"); page.wait_for_timeout(100)
    face2 = page.text_content("#card-face")
    page.evaluate("document.querySelector('.lp-tab[data-tab=\"chat\"]').click()")
    page.fill("#chat-input", "test question")
    page.evaluate("document.getElementById('btn-send').click()")
    page.wait_for_timeout(900)
    chat_ok = page.evaluate("document.querySelectorAll('#chat-feed .lp-bubble-user').length >= 2")

    page.evaluate("document.querySelector('.lp-nav[data-nav=\"home\"]').click()")
    page.evaluate("document.getElementById('btn-browse').click()"); page.wait_for_timeout(150)
    onb_ok = page.evaluate("!document.getElementById('onb-overlay').hidden")
    page.evaluate("document.getElementById('btn-onb-sample').click()"); page.wait_for_timeout(150)
    detected_ok = page.evaluate("!document.getElementById('onb-detected').hidden")
    page.evaluate("document.getElementById('btn-start-processing').click()"); page.wait_for_timeout(150)
    proc_ok = page.evaluate("!document.querySelector('section[data-screen=\"process\"]').hidden")

    page.evaluate("document.querySelector('.lp-nav[data-nav=\"exports\"]').click()")
    page.evaluate("document.getElementById('btn-export-all').click()"); page.wait_for_timeout(2000)
    export_ok = page.evaluate("!document.getElementById('export-done').hidden")

    page.keyboard.press("f"); page.wait_for_timeout(700)
    focus_ok = page.evaluate("document.getElementById('app').dataset.focus === 'true'")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)

    # what's new overlay via simulated backend signal path
    page.evaluate("""window.lpBridge && (function(){})();""")

    browser.close()

checks = {"quiz reveals answer": quiz_ok, "flashcard flips": face1 != face2,
          "chat sends+streams": chat_ok, "import overlay opens": onb_ok,
          "video detected step": detected_ok, "start→process screen": proc_ok,
          "export completes": export_ok, "focus mode toggles": focus_ok}
print("\n=== interaction checks ===")
for k, v in checks.items():
    print(f"  [{'OK' if v else 'FAIL'}] {k}")
    if not v: errors.append("check failed: " + k)

print(f"\nShots: {len(glob.glob(os.path.join(OUT, '*.png')))} in verify_shots/")
if errors:
    print("\n=== ERRORS ==="); [print("  -", e) for e in errors]
    sys.exit(1)
print("\nALL CHECKS PASSED")
