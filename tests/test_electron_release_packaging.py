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


def test_electron_release_zip_and_hashes(tmp_path):
    builder = load_builder()
    candidate = tmp_path / "LecturePack-win32-x64"
    (candidate / "resources").mkdir(parents=True)
    (candidate / "resources" / "LecturePackSidecar").mkdir()
    (candidate / "LecturePack.exe").write_bytes(b"portable executable fixture")
    (candidate / "resources" / "app.asar").write_bytes(b"asar fixture")
    (candidate / "resources" / "lecturepack.ico").write_bytes(b"icon fixture")
    (candidate / "resources" / "LecturePackSidecar" / "LecturePackSidecar.exe").write_bytes(b"sidecar fixture")

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
    candidate = tmp_path / "LecturePack-win32-x64"
    (candidate / "resources").mkdir(parents=True)
    (candidate / "resources" / "LecturePackSidecar").mkdir()
    (candidate / "LecturePack.exe").write_bytes(b"fixture")
    (candidate / "resources" / "app.asar").write_bytes(b"asar")
    (candidate / "resources" / "LecturePackSidecar" / "LecturePackSidecar.exe").write_bytes(b"sidecar")
    os.utime(candidate / "LecturePack.exe", (0, 0))

    portable = builder.make_portable_zip(candidate, tmp_path / "portable.zip")

    with zipfile.ZipFile(portable) as archive:
        assert archive.read("LecturePack-win32-x64/LecturePack.exe") == b"fixture"
