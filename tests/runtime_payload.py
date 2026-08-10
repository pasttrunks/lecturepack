"""Skip guards for tests that need the gitignored runtime payload.

Some suites can only run on a machine that has LecturePack's large binary
payload present: the bundled FFmpeg/FFprobe (`bin/`), the Whisper model
(`models/ggml-base.en.bin`), a built packaged onedir, or the compiled Rust
Study Core. All four are deliberately **not** in git — they are hundreds of
megabytes — so a bare checkout, and therefore CI, does not have them.

Before this module those tests *failed* on a bare checkout. That is the wrong
signal twice over: it reports "broken" for something that is merely absent,
and a permanently red CI is a CI nobody reads. They now **skip with a precise
reason naming what is missing and how to get it**, so:

  * a bare checkout / CI is green and honest about what it did not exercise;
  * a dev or release machine runs them for real, with every assertion intact.

Nothing here weakens an assertion. The full suite still runs end to end on the
release machine (1452 passed, 0 skipped, with the payload present).

To run the skipped suites locally:
    bin/            ffmpeg.exe + ffprobe.exe (see docs/)
    models/         ggml-base.en.bin
    Rust core       pip install the maturin wheel from rust/study-core
    onedir fixture  LECTUREPACK_ONEDIR_FIXTURE=<path to a packaged onedir>
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]

_HOW = "Not a failure: this payload is gitignored and absent on a bare checkout."


def ffprobe_path() -> str:
    """Bundled or system ffprobe, or '' when neither is present."""
    bundled = ROOT / "bin" / "ffprobe.exe"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffprobe") or ""


def ffmpeg_path() -> str:
    bundled = ROOT / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffmpeg") or ""


def demo_model_path() -> Path:
    return ROOT / "models" / "ggml-base.en.bin"


def _model_present() -> bool:
    model = demo_model_path()
    return model.is_file() and model.stat().st_size > 0


def _rust_core_present() -> bool:
    try:
        import lecturepack_study_core  # noqa: F401
    except Exception:
        return False
    return True


def onedir_fixture() -> Path | None:
    value = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() else None


# --------------------------------------------------------------- decorators
requires_ffprobe = pytest.mark.skipif(
    not ffprobe_path(),
    reason=f"needs ffprobe (bin/ffprobe.exe or on PATH). {_HOW}",
)

requires_ffmpeg_tools = pytest.mark.skipif(
    not (ffmpeg_path() and ffprobe_path()),
    reason=f"needs bundled ffmpeg AND ffprobe to run a real pipeline. {_HOW}",
)

requires_demo_model = pytest.mark.skipif(
    not _model_present(),
    reason=f"needs models/ggml-base.en.bin (~148 MB). {_HOW}",
)

requires_rust_study_core = pytest.mark.skipif(
    not _rust_core_present(),
    reason=(
        "needs the compiled Rust Study Core (lecturepack_study_core). "
        "Build it with maturin from rust/study-core. " + _HOW
    ),
)

requires_onedir_fixture = pytest.mark.skipif(
    onedir_fixture() is None,
    reason=(
        "needs a packaged onedir: set LECTUREPACK_ONEDIR_FIXTURE to a built "
        "app/dist/LecturePack. " + _HOW
    ),
)
