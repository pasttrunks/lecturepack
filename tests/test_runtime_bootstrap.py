"""Runtime bootstrap admission and persistence policy contracts."""

import sys
from pathlib import Path

from lecturepack.infrastructure.runtime_validation import RuntimeValidator


def test_bootstrap_persists_complete_facts_and_migrates_once(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    cfg.settings.update({"engine": "cuda", "whisper_model": "D:/models/old.bin"})
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    (tmp_path / "base.bin").write_bytes(b"x")
    calls = []

    service = RuntimeBootstrapService(
        cfg,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": tmp_path / "ffmpeg.exe", "models/ggml-base.en.bin": tmp_path / "base.bin"},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: calls.append(components) or {key: {"healthy": True} for key in components},
        runtime_root=tmp_path,
    )

    result = service.assess()

    assert result.state == "HEALTHY"
    assert result.validation_mode == "full"
    assert len(calls) == 1
    assert cfg.get("migration_versions")["runtime_contract"] == 1
    assert cfg.get("whisper_model") == str(tmp_path / "base.bin")
    assert cfg.get("known_whisper_models") == ["D:/models/old.bin"]
    assert cfg.get("runtime_health")["identity"] == "payload-v1"

    cfg.set("whisper_model", "D:/models/manual.bin")
    second = service.assess()
    assert second.validation_mode == "light"
    assert cfg.get("whisper_model") == "D:/models/manual.bin"


def test_bootstrap_never_persists_healthy_facts_on_validation_failure(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": tmp_path / "ffmpeg.exe"},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: {"bin/ffmpeg.exe": {"healthy": False, "reason": "failed"}},
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert cfg.get("runtime_health") is None
    assert cfg.get("migration_versions", {}).get("runtime_contract") is None


def test_incomplete_full_validation_cannot_become_healthy_state(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    (tmp_path / "ffprobe.exe").write_bytes(b"x")
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: {
            "bin/ffmpeg.exe": tmp_path / "ffmpeg.exe",
            "bin/ffprobe.exe": tmp_path / "ffprobe.exe",
        },
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: {"bin/ffmpeg.exe": {"healthy": True}},
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert cfg.get("runtime_health") is None


def test_optional_preference_is_resolved_only_after_cpu_admission(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    cfg.settings["engine"] = "cuda"
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    order = []
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: order.append("cpu") or {"bin/ffmpeg.exe": tmp_path / "ffmpeg.exe"},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: {"bin/ffmpeg.exe": {"healthy": True}},
        optional_resolver=lambda requested: order.append("optional") or ("whispercpp-cpu", "CUDA driver missing"),
    )

    result = service.assess()

    assert result.state == "HEALTHY"
    assert order == ["cpu", "optional"]
    assert result.fallback_notice == {"requested": "cuda", "resolved": "whispercpp-cpu", "reason": "CUDA driver missing"}
    assert cfg.get("engine") == "cpu"
    assert service.assess().fallback_notice is None


def test_healthy_custom_optional_preference_survives_cpu_admission(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    cfg.settings["engine"] = "custom-engine"
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": tmp_path / "ffmpeg.exe"},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: {"bin/ffmpeg.exe": {"healthy": True}},
        optional_resolver=lambda requested: (requested, "explicitly selected"),
    )

    result = service.assess()

    assert result.state == "HEALTHY"
    assert result.fallback_notice is None
    assert cfg.get("engine") == "custom-engine"


def test_optional_resolution_is_not_probed_when_cpu_admission_fails(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    probed = []
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/missing.exe": tmp_path / "missing.exe"},
        identity_provider=lambda root: "payload-v1",
        optional_resolver=lambda requested: probed.append(requested) or ("whispercpp-cpu", "unavailable"),
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert probed == []


def test_runner_captures_success_evidence_with_argument_array(tmp_path):
    script = tmp_path / "echo.py"
    script.write_text("print('backend model WAV processing')", encoding="utf-8")
    evidence = RuntimeValidator(timeout_ms=1_000).run(sys.executable, [str(script)])
    assert evidence.ok is True
    assert evidence.argv == [sys.executable, str(script)]
    assert evidence.exit_code == 0
    assert "processing" in evidence.stdout
    assert evidence.reason == "success"


def test_runner_captures_nonzero_evidence(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; print('failed', file=sys.stderr); sys.exit(7)", encoding="utf-8")
    evidence = RuntimeValidator(timeout_ms=1_000).run(sys.executable, [str(script)])
    assert evidence.ok is False
    assert evidence.exit_code == 7
    assert "failed" in evidence.stderr
    assert evidence.reason == "nonzero exit"


def test_runner_times_out_the_exact_hang_fixture():
    fixture = Path(__file__).parent / "fixtures" / "mock_runtime_hang.py"
    evidence = RuntimeValidator(timeout_ms=100).run(sys.executable, [str(fixture)])
    assert evidence.ok is False
    assert evidence.timed_out is True
    assert evidence.reason == "timeout"
    assert evidence.duration_ms >= 100
