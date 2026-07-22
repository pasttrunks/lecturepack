"""Optional CUDA acceleration pack — verified download + safe extract + adapter.

No network: the download is monkeypatched to drop a small local zip, and the
install target is redirected to a temp dir (never the real bin/cuda).
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
import types
import zipfile

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import cuda_pack as cp  # noqa: E402
from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure import transcription_engines as te  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


def _make_pack_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Release/whisper-cli.exe", b"FAKE-CUDA-CLI")
        z.writestr("Release/ggml-cuda.dll", b"FAKE-DLL")
        z.writestr("Release/cublas64_12.dll", b"FAKE-CUBLAS")
        z.writestr("Release/readme.txt", b"ignore me")
        z.writestr("../evil.dll", b"zip-slip attempt")  # must be flattened, not escape


def test_extract_pack_flattens_filters_and_blocks_zip_slip(tmp_path):
    zp = tmp_path / "pack.zip"
    _make_pack_zip(str(zp))
    dest = tmp_path / "bincuda"
    n = cp.extract_pack(str(zp), str(dest))
    names = sorted(os.listdir(dest))
    # exe + 2 dlls copied (incl. the flattened "evil.dll"); readme.txt skipped.
    assert "whisper-cli.exe" in names
    assert "ggml-cuda.dll" in names and "cublas64_12.dll" in names
    assert "readme.txt" not in names
    # zip-slip entry landed as a plain basename inside dest, never a parent dir.
    assert not (tmp_path / "evil.dll").exists()
    assert all(os.sep not in x and "/" not in x for x in names)
    assert n == len(names)


def test_verify_matches_and_rejects(tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"hello cuda")
    digest = hashlib.sha256(b"hello cuda").hexdigest()
    assert cp.verify(str(f), digest) is True
    assert cp.verify(str(f), "0" * 64) is False


def test_pinned_pack_metadata_is_sane():
    assert cp.CUDA_PACK["url"].startswith("https://github.com/ggml-org/whisper.cpp/")
    assert len(cp.CUDA_PACK["sha256"]) == 64
    assert cp.CUDA_PACK["name"].endswith(".zip")


# --------------------------------------------------------------- adapter flow
class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, p):
        self.emissions.append(p)


class _FakeBackend:
    def __init__(self):
        for n in ("cuda_pack", "cuda_status", "log_line"):
            setattr(self, n, _Signal())


class _ImmediateThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._t = target

    def start(self):
        if self._t:
            self._t()


def _emissions(sig):
    import json
    return [json.loads(e) if isinstance(e, str) else e for e in sig.emissions]


def test_install_cuda_pack_downloads_verifies_extracts(tmp_path, monkeypatch):
    dest = tmp_path / "bincuda"
    src_zip = tmp_path / "src_pack.zip"
    _make_pack_zip(str(src_zip))

    monkeypatch.setattr(te, "nvidia_cuda_present", lambda: True)
    monkeypatch.setattr(cp, "bin_cuda_dir", lambda: str(dest))
    monkeypatch.setattr(cp, "verify", lambda p, e="": True)  # bytes are faked
    # "download" just copies our local fake zip to the requested destination.
    def fake_dl(url, dest_path, on_progress=None, cancel=None, timeout=60.0):
        import shutil
        if on_progress:
            on_progress(50.0, 1, 2)
        shutil.copyfile(str(src_zip), dest_path)
        if on_progress:
            on_progress(100.0, 2, 2)
    monkeypatch.setattr(cp, "download", fake_dl)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(ea, "threading",
                        types.SimpleNamespace(Thread=_ImmediateThread, Event=threading.Event))

    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path / "cfg"))
    a.backend = _FakeBackend()

    a.install_cuda_pack()

    states = [e.get("state") for e in _emissions(a.backend.cuda_pack)]
    assert "downloading" in states and "ready" in states
    assert os.path.isfile(str(dest / "whisper-cli.exe"))


def test_install_cuda_pack_blocks_without_gpu(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "nvidia_cuda_present", lambda: False)
    monkeypatch.setattr(ea, "threading",
                        types.SimpleNamespace(Thread=_ImmediateThread, Event=threading.Event))
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path / "cfg"))
    a.backend = _FakeBackend()
    a.install_cuda_pack()
    last = _emissions(a.backend.cuda_pack)[-1]
    assert last["state"] == "error" and "NVIDIA" in last["message"]
