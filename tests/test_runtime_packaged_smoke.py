"""Blocking disposable onedir smoke evidence for the real bundled CPU payload."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import pytest

from app.packaging import build

SMOKE_RELATIVE_PATH = Path("smoke") / "runtime-smoke.wav"


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
    fixture_smoke = root / SMOKE_RELATIVE_PATH
    if not fixture_smoke.is_file() or fixture_smoke.stat().st_size == 0:
        pytest.fail("clean onedir fixture must include a nonempty smoke/runtime-smoke.wav")
    with tempfile.TemporaryDirectory(prefix="LecturePack smoke ") as workspace:
        copied = Path(workspace) / "runtime 漢 copy"
        shutil.copytree(root, copied)
        copied_smoke = copied / SMOKE_RELATIVE_PATH
        assert copied_smoke.is_file() and copied_smoke.stat().st_size == fixture_smoke.stat().st_size
        profile = Path(workspace) / "fresh profile"
        monkeypatch.setenv("LECTUREPACK_DATA_DIR", str(profile))
        evidence = build.run_disposable_runtime_smoke(copied, timeout_ms=30_000)
        assert not (copied / "smoke-output").exists()
    assert evidence.ok, evidence
    assert evidence.duration_ms < 30_000
    assert evidence.argv[1] == "-m"
    assert evidence.argv[3] == "-f"
    assert evidence.argv[5:] == ["-t", "1", "-nt"]
    assert evidence.argv[2].isascii() and evidence.argv[4].isascii()
    output = f"{evidence.stdout}\n{evidence.stderr}".lower()
    assert all(marker in output for marker in ("backend", "model", "wav", "processing"))
