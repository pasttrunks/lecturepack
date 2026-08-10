"""Blocking disposable onedir smoke evidence for the real bundled CPU payload."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import pytest

from app.packaging import build
from lecturepack.infrastructure.runtime_validation import SmokeEvidence

from runtime_payload import (  # noqa: E402  test-only skip guards
    requires_demo_model, requires_ffprobe, requires_onedir_fixture,
    requires_rust_study_core,
)

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


def test_packaged_smoke_rejects_default_whisper_output_and_cleans_staging(monkeypatch, tmp_path):
    """A Whisper default output must remain visible long enough to fail smoke."""
    root = tmp_path / "runtime"
    for path in build.required_runtime_payload(root, cpu_dll_names=("ggml-cpu-test.dll",)).values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime")

    staging_instances = []
    original_staging = build.WhisperPathStaging

    class TrackingStaging(original_staging):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            staging_instances.append(self)

    class DefaultOutputValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            if Path(program).name == "whisper-cli.exe":
                Path(args[3]).with_suffix(".txt").write_text("unexpected transcript", encoding="utf-8")
            return SmokeEvidence([program, *args], 0, "ok", "", 1, "success", False)

    monkeypatch.setattr(build, "WhisperPathStaging", TrackingStaging)
    monkeypatch.setattr(build, "RuntimeValidator", DefaultOutputValidator)

    with pytest.raises(AssertionError, match=r"unexpected output artifacts: .*audio.txt"):
        build.run_disposable_runtime_smoke(root)

    assert len(staging_instances) == 1
    assert staging_instances[0].root is None


@requires_onedir_fixture
def test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile(monkeypatch):
    fixture = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
    root = Path(fixture)
    assert root.is_dir(), f"clean onedir fixture is required but missing: {root}"
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
        from lecturepack.infrastructure.config_manager import ConfigManager
        from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

        admission = RuntimeBootstrapService(ConfigManager(str(profile)), runtime_root=copied).assess()
        assert not (copied / "smoke-output").exists()
    assert evidence.ok, evidence
    assert admission.state == "HEALTHY"
    for name in ("bin/whisper-cli.exe", "models/ggml-base.en.bin", "smoke/runtime-smoke.wav"):
        component = admission.components[name]
        assert component["healthy"] is True
        assert set(("argv", "exit_code", "duration_ms", "stdout", "stderr", "reason")) <= component.keys()
    assert evidence.duration_ms < 30_000
    assert evidence.argv[1] == "-m"
    assert evidence.argv[3] == "-f"
    assert evidence.argv[5:] == ["-t", "1", "-nt"]
    assert evidence.argv[2].isascii() and evidence.argv[4].isascii()
    output = f"{evidence.stdout}\n{evidence.stderr}".lower()
    assert all(marker in output for marker in ("backend", "model", "wav", "processing"))
