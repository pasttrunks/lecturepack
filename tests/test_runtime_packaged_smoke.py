"""Blocking disposable onedir smoke evidence for the real bundled CPU payload."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import pytest

from app.packaging import build


def test_package_membership_uses_canonical_inventory():
    required = build.required_runtime_payload(Path("runtime-root"), cpu_dll_names=("ggml-cpu-test.dll",))
    assert required["smoke/runtime-smoke.wav"].name == "runtime-smoke.wav"
    assert required["bin/ggml-cpu-test.dll"].name == "ggml-cpu-test.dll"


def test_real_packaged_smoke_requires_a_clean_onedir_fixture(monkeypatch, tmp_path):
    """Fixture absence is an explicit failure, never a skipped integration test."""
    missing = tmp_path / "missing onedir"
    monkeypatch.setenv("LECTUREPACK_ONEDIR_FIXTURE", str(missing))
    with pytest.raises(AssertionError, match="clean onedir fixture"):
        build.run_disposable_runtime_smoke(timeout_ms=30_000)


def test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile(monkeypatch):
    fixture = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
    if not fixture:
        pytest.fail("clean onedir fixture is required: set LECTUREPACK_ONEDIR_FIXTURE to a verified packaged runtime")
    root = Path(fixture)
    if not root.is_dir():
        pytest.fail(f"clean onedir fixture is required but missing: {root}")
    with tempfile.TemporaryDirectory(prefix="LecturePack smoke é ") as workspace:
        copied = Path(workspace) / "runtime ü copy"
        shutil.copytree(root, copied)
        profile = Path(workspace) / "fresh profile"
        monkeypatch.setenv("LECTUREPACK_DATA_DIR", str(profile))
        evidence = build.run_disposable_runtime_smoke(copied, timeout_ms=30_000)
    assert evidence.ok, evidence
    assert evidence.duration_ms < 30_000
    assert evidence.argv[1:] == ["-m", str(copied / "models" / "ggml-base.en.bin"), "-f", str(copied / "smoke" / "runtime-smoke.wav"), "-t", "1", "-nt"]
    assert all(marker in evidence.stdout.lower() for marker in ("backend", "model", "wav", "processing"))
    assert not list(copied.rglob("*.txt"))
