"""Optional CUDA acceleration pack.

Downloads the official whisper.cpp cuBLAS build (pinned version + SHA256) and
installs the GPU ``whisper-cli.exe`` + its CUDA DLLs into ``bin/cuda/`` — the
same location the engine registry probes. Analogous to Smart Study, but for the
transcription binary. Pure helpers live here; the Qt orchestration (threads,
progress, cancel) is in engine_adapter.py.

The pack is large and NVIDIA-only, so it is never bundled in the installer — it
is fetched on demand only when the user asks for GPU acceleration.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from typing import Callable, Optional

# Pinned to the whisper.cpp release the app's other binaries come from (v1.9.1).
# The self-contained cuBLAS 12.4 build bundles cudart + cuBLAS (the 11.8 build
# does not, and silently falls back to CPU).
CUDA_PACK = {
    "whisper_version": "v1.9.1",
    "name": "whisper-cublas-12.4.0-bin-x64.zip",
    "url": ("https://github.com/ggml-org/whisper.cpp/releases/download/"
            "v1.9.1/whisper-cublas-12.4.0-bin-x64.zip"),
    "sha256": "106a2030eff8998e4ef320fe72e263a78449e9040386ee27c41ea80b001b601b",
    "size": 677887125,
    "size_label": "≈ 650 MB",
}


def bin_cuda_dir() -> str:
    """Install target for the pack — the per-user, always-writable CUDA dir the
    engine registry probes (works whether or not the install dir is writable)."""
    from lecturepack.infrastructure.transcription_engines import user_cuda_dir
    return user_cuda_dir()


def is_installed() -> bool:
    return os.path.isfile(os.path.join(bin_cuda_dir(), "whisper-cli.exe"))


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify(path: str, expected_hex: str = "") -> bool:
    expected = (expected_hex or CUDA_PACK["sha256"]).lower()
    return sha256_file(path).lower() == expected


def extract_pack(zip_path: str, dest_dir: str) -> int:
    """Extract only ``whisper-cli.exe`` + ``*.dll`` (flattened to basenames, so
    zip-slip is impossible) into ``dest_dir``. Returns the file count."""
    os.makedirs(dest_dir, exist_ok=True)
    copied = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            base = os.path.basename(info.filename)
            if not base:
                continue
            low = base.lower()
            if low == "whisper-cli.exe" or low.endswith(".dll"):
                with z.open(info) as src, open(os.path.join(dest_dir, base), "wb") as out:
                    shutil.copyfileobj(src, out)
                copied += 1
    return copied


def download(url: str, dest_path: str,
             on_progress: Optional[Callable[[float, int, int], None]] = None,
             cancel: Optional[Callable[[], bool]] = None,
             timeout: float = 60.0) -> None:
    """Stream ``url`` to ``dest_path`` (progress + cancel). Raises on error /
    cancellation; the partial file is removed by the caller."""
    req = urllib.request.Request(url, headers={"User-Agent": "LecturePack-CUDApack"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0) or 0)
        read = 0
        with open(dest_path, "wb") as fh:
            while True:
                if cancel is not None and cancel():
                    raise RuntimeError("__cancelled__")
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                read += len(chunk)
                if on_progress is not None:
                    on_progress((read / total * 100.0) if total else 0.0, read, total)
