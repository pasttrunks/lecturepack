from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_electron_release.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("electron_release_builder", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_candidate(root: Path, executable: bytes = b"portable executable fixture") -> Path:
    """Create the complete minimum candidate required by the release contract."""
    files = {
        "LecturePack.exe": executable,
        "resources/app.asar": b"asar fixture",
        "resources/lecturepack.ico": b"icon fixture",
        "resources/LecturePackSidecar/LecturePackSidecar.exe": b"sidecar fixture",
        "resources/ui/index.html": b"<!doctype html>",
        "resources/ui/app.js": b"void 0;",
        "resources/assets/demo-lecture.mp4": b"demo video fixture",
        "resources/assets/demo/demo.data.js": b"window.LP_DEMO_DATA = {};",
        "resources/assets/demo/hero.png": b"hero fixture",
        "resources/assets/demo/slide_01.png": b"slide one fixture",
        "resources/assets/demo/slide_02.png": b"slide two fixture",
        "resources/LICENSE": b"license fixture",
    }
    for relative, payload in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return root


def test_electron_release_zip_and_hashes(tmp_path):
    builder = load_builder()
    candidate = make_candidate(tmp_path / "LecturePack-win32-x64")

    output = tmp_path / "release"
    portable = builder.make_portable_zip(candidate, output / "LecturePack-2.0.0-Portable.zip")
    checksums = builder.write_sha256sums("2.0.0", output)

    assert portable.is_file()
    with zipfile.ZipFile(portable) as archive:
        assert "LecturePack-win32-x64/LecturePack.exe" in archive.namelist()
        assert "LecturePack-win32-x64/resources/app.asar" in archive.namelist()

    expected = hashlib.sha256(portable.read_bytes()).hexdigest()
    assert f"{expected}  {portable.name}" in checksums.read_text(encoding="utf-8")


def test_electron_release_zip_clamps_pre_1980_timestamps(tmp_path):
    builder = load_builder()
    candidate = make_candidate(tmp_path / "LecturePack-win32-x64", executable=b"fixture")
    os.utime(candidate / "LecturePack.exe", (0, 0))

    portable = builder.make_portable_zip(candidate, tmp_path / "portable.zip")

    with zipfile.ZipFile(portable) as archive:
        assert archive.read("LecturePack-win32-x64/LecturePack.exe") == b"fixture"
