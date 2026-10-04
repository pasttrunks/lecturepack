"""Fail-closed build restoration tests; real runtime verification is separate."""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("restore_ci", ROOT / "scripts/restore_ci_runtime.py")
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


@pytest.fixture
def locked(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("payload/bin/tool.exe", b"test binary")
        z.writestr("payload/ui/app.js", b"must not be restored")
    import hashlib
    lock = {"source_release": "fixture", "archive_size": archive.stat().st_size,
            "archive_sha256": restore.sha256(archive), "files": {
                "bin/tool.exe": {"member": "payload/bin/tool.exe", "size": 11,
                                 "sha256": hashlib.sha256(b"test binary").hexdigest()}}}
    return archive, tmp_path / "restored", lock


def test_only_locked_runtime_members_are_restored(locked):
    archive, output, lock = locked
    report = restore.restore_runtime(archive, output, lock)
    assert (output / "bin/tool.exe").read_bytes() == b"test binary"
    assert sorted(str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()) == [str(Path("bin/tool.exe"))]
    assert report["files"]["bin/tool.exe"]["sha256"] == lock["files"]["bin/tool.exe"]["sha256"]


@pytest.mark.parametrize("failure", ["archive_hash", "member_hash", "missing_member", "size", "traversal", "existing"])
def test_restore_refuses_untrusted_or_existing_inputs_and_preserves_evidence(locked, failure):
    archive, output, lock = locked
    if failure == "archive_hash":
        lock["archive_sha256"] = "0" * 64
    elif failure == "member_hash":
        lock["files"]["bin/tool.exe"]["sha256"] = "0" * 64
    elif failure == "missing_member":
        lock["files"]["bin/tool.exe"]["member"] = "missing.exe"
    elif failure == "size":
        lock["files"]["bin/tool.exe"]["size"] = 12
    elif failure == "traversal":
        lock["files"]["../escape.exe"] = lock["files"].pop("bin/tool.exe")
    else:
        output.mkdir()
        (output / "sentinel").write_bytes(b"keep")
    with pytest.raises(ValueError):
        restore.restore_runtime(archive, output, lock)
    assert archive.exists()
    if failure == "member_hash":
        assert (output / "bin/tool.exe").read_bytes() == b"test binary"
    elif failure == "existing":
        assert (output / "sentinel").read_bytes() == b"keep"
    else:
        assert not output.exists()


def test_tampered_cache_is_rejected_without_silent_network_replacement(locked, monkeypatch):
    archive, output, lock = locked
    cache = output.parent / "cache"
    cache.mkdir()
    (cache / "runtime-source.zip").write_bytes(b"tampered")
    monkeypatch.setattr(restore.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not replace evidence"))
    with pytest.raises(ValueError):
        restore.fetch_archive(cache, lock)
    assert (cache / "runtime-source.zip").read_bytes() == b"tampered"


def test_committed_lock_matches_sidecar_deno_and_workflow_restores_before_build():
    lock = json.loads(restore.LOCK.read_text())
    sidecar = (ROOT / "electron-spike/sidecar.spec").read_text()
    assert lock["files"]["bin/deno.exe"]["sha256"] in sidecar
    assert {"bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/Release/whisper-cli.exe",
            "bin/Release/ggml-base.dll", "bin/Release/ggml.dll", "bin/Release/whisper.dll",
            "models/ggml-base.en.bin", "msvc/msvcp140.dll"} <= set(lock["files"])
    workflow = (ROOT / ".github/workflows/release-electron.yml").read_text()
    assert workflow.index("python scripts/restore_ci_runtime.py") < workflow.index("python scripts/build_electron_release.py")
    assert "LECTUREPACK_RUNTIME_ROOT=$runtimeRoot" in workflow
    assert "LECTUREPACK_MSVC_RUNTIME_DIR=" in workflow
    assert "runtime-restore-audit.json" in workflow
