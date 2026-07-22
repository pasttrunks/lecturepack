"""Content hygiene guard.

The product must ship no inappropriate bundled demo/sample content. This test
scans tracked product and demo files (UI, desktop shell, engine, and text
fixtures) and fails if a known-inappropriate string reappears — a regression
tripwire so demo seeds, mock transcripts, screenshot fixtures, etc. stay clean.

Real user data under ~/LecturePackData is never touched.
"""
from __future__ import annotations

import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories whose *tracked* text files are product/demo surfaces.
SCAN_PREFIXES = ("app/", "lecturepack/", "assets/")
# Plus specific demo/fixture text files under tests/ (never the binaries).
SCAN_TEST_SUFFIXES = (".json", ".srt", ".vtt", ".txt", ".md")

TEXT_EXTS = {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt",
             ".srt", ".vtt", ".qss", ".ini", ".cfg", ".toml"}

# Exact substrings that must never appear (case-insensitive).
BANNED_SUBSTRINGS = ("dashcam", "vulgar")
# Generic profanity/NSFW, matched as whole words to avoid false positives
# (e.g. "shell", "Essex", "assess").
BANNED_WORDS = ("fuck", "shit", "porn", "nsfw", "bitch", "cunt")

_word_re = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.IGNORECASE)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _should_scan(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    ext = os.path.splitext(rel)[1].lower()
    if ext not in TEXT_EXTS:
        return False
    if rel.startswith(SCAN_PREFIXES):
        return True
    if rel.startswith("tests/") and ext in SCAN_TEST_SUFFIXES:
        # Only the demo/fixture data, not the test source that names banned
        # words on purpose (this file, and any future hygiene tests).
        return "test_content_hygiene" not in rel
    return False


def test_no_inappropriate_bundled_content():
    offenders: list[str] = []
    for rel in _tracked_files():
        if not _should_scan(rel):
            continue
        path = os.path.join(ROOT, rel)
        try:
            with open(path, "r", encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable — not a text surface
        low = text.lower()
        for sub in BANNED_SUBSTRINGS:
            if sub in low:
                offenders.append(f"{rel}: contains '{sub}'")
        m = _word_re.search(text)
        if m:
            offenders.append(f"{rel}: contains '{m.group(0)}'")
    assert not offenders, "Inappropriate content found:\n" + "\n".join(offenders)


def test_scanner_actually_covers_product_files():
    # Guard against the scan silently matching nothing (e.g. glob regressions).
    scanned = [r for r in _tracked_files() if _should_scan(r)]
    assert any(r.replace("\\", "/").startswith("app/ui/") for r in scanned)
    assert len(scanned) > 20
