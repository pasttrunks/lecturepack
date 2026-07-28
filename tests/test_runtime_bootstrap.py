"""Runtime bootstrap admission and persistence policy contracts."""

import sys
from pathlib import Path

import pytest

from lecturepack.infrastructure.runtime_validation import RuntimeValidator


def _complete_success_evidence(components):
    """Produce the persisted evidence shape required for light revalidation."""
    return {
        key: {
            "healthy": True,
            "reason": "success",
            "exit_code": 0,
            "argv": [key, "-version"],
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "timed_out": False,
        }
        for key in components
    }


def test_full_admission_rejects_nonempty_corrupt_model_with_real_smoke_evidence(tmp_path, monkeypatch):
    """Readability alone must not admit a canonical model as healthy."""
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap

    model = tmp_path / "models" / "ggml-base.en.bin"
    smoke = tmp_path / "smoke" / "runtime-smoke.wav"
    whisper = tmp_path / "bin" / "whisper-cli.exe"
    for path, content in ((model, b"corrupt but nonempty"), (smoke, b"RIFFfakeWAVE"), (whisper, b"cli")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    captured = []

    class RejectingValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            captured.append([program, *args])
            return SmokeEvidence([program, *args], 2, "", "invalid model", 12, "nonzero exit", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", RejectingValidator)
    evidence = RuntimeBootstrapService._validate_full({
        "bin/whisper-cli.exe": whisper,
        "models/ggml-base.en.bin": model,
        "smoke/runtime-smoke.wav": smoke,
    })

    assert captured and captured[-1][1:] == ["-m", captured[-1][2], "-f", captured[-1][4], "-t", "1", "-nt"]
    assert captured[-1][2].isascii() and captured[-1][4].isascii()
    assert evidence["models/ggml-base.en.bin"]["healthy"] is False
    assert evidence["smoke/runtime-smoke.wav"]["reason"] == "nonzero exit"
    assert evidence["models/ggml-base.en.bin"]["argv"] == captured[-1]


def test_full_admission_requires_complete_real_smoke_evidence(tmp_path):
    """A validator that omits canonical evidence cannot authorize persistence."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path / "profile"))
    model = tmp_path / "model.bin"
    smoke = tmp_path / "smoke.wav"
    model.write_bytes(b"model")
    smoke.write_bytes(b"wav")
    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {
            "models/ggml-base.en.bin": model,
            "smoke/runtime-smoke.wav": smoke,
        },
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda paths: {"models/ggml-base.en.bin": {"healthy": True}},
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert cfg.get("runtime_health") is None


def test_default_bootstrap_uses_the_canonical_active_generation_resolver(tmp_path):
    """Normal startup must admit the active writable generation, not the bundle."""
    from lecturepack.infrastructure.runtime_generation import RuntimeGenerationStore
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    bundle = tmp_path / "bundle"
    source = tmp_path / "source"
    for root, marker in ((bundle, b"bundle"), (source, b"generation")):
        for entry in canonical_inventory(("ggml-cpu-test.dll",)):
            path = root / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(marker + entry.encode("ascii"))
    profile = tmp_path / "profile"
    active = RuntimeGenerationStore(profile).publish_from_directory(
        {entry: source / entry for entry in canonical_inventory(("ggml-cpu-test.dll",))},
        admit=lambda root: True,
    )

    class Config:
        resource_dir = bundle

        def resolve_data_dir(self):
            return str(profile)

        def get(self, key, default=None):
            return default

        def persist_runtime_health(self, *args, **kwargs):
            pass

    service = RuntimeBootstrapService(
        Config(),
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": root / "bin" / "ffmpeg.exe"},
        identity_provider=lambda root: root.name,
        full_validator=lambda components: _complete_success_evidence(components),
        optional_resolver=lambda requested: ("whispercpp-cpu", "available"),
    )

    assert service.runtime_root == active.root
    assert service.assess(trigger="repair").state == "HEALTHY"


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
        full_validator=lambda components: calls.append(components) or _complete_success_evidence(components),
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


def test_same_identity_failed_evidence_requires_full_validation_and_stays_unhealthy(tmp_path):
    """A prior failed smoke cannot be upgraded by matching file presence alone."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"nonempty")
    cfg.settings["runtime_health"] = {
        "identity": "payload-v1",
        "components": {
            "bin/ffmpeg.exe": {"healthy": False, "reason": "prior smoke failed"},
        },
        "validation_mode": "full",
    }
    calls = []
    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": executable},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: calls.append(components) or {
            "bin/ffmpeg.exe": {"healthy": False, "reason": "still failing"},
        },
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert result.validation_mode == "full"
    assert len(calls) == 1
    assert cfg.get("runtime_health")["components"]["bin/ffmpeg.exe"]["healthy"] is False


def test_same_identity_healthy_only_evidence_requires_full_validation(tmp_path):
    """Positive persisted booleans without smoke evidence cannot take the light path."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"nonempty")
    cfg.settings["runtime_health"] = {
        "identity": "payload-v1",
        "components": {"bin/ffmpeg.exe": {"healthy": True}},
        "validation_mode": "full",
    }
    calls = []
    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": executable},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: calls.append(components) or {
            "bin/ffmpeg.exe": {"healthy": False, "reason": "smoke failed"},
        },
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert result.validation_mode == "full"
    assert len(calls) == 1
    assert cfg.get("runtime_health")["components"]["bin/ffmpeg.exe"] == {"healthy": True}


@pytest.mark.parametrize("trigger", ("update", "repair"))
def test_update_and_repair_force_failed_full_validation_without_overwriting_healthy_state(tmp_path, trigger):
    """Explicit update/repair checks must re-prove a healthy saved runtime."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"healthy before explicit revalidation")
    previous = {
        "identity": "payload-v1",
        "components": _complete_success_evidence({"bin/ffmpeg.exe": executable}),
        "validation_mode": "full",
    }
    cfg.settings["runtime_health"] = previous
    full_calls = []
    optional_calls = []
    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": executable},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: full_calls.append(components) or {
            "bin/ffmpeg.exe": {"healthy": False, "reason": "explicit revalidation failed"},
        },
        optional_resolver=lambda requested: optional_calls.append(requested) or ("whispercpp-cpu", "unavailable"),
    )

    result = service.assess(trigger=trigger)

    assert result.state == "SETUP_REQUIRED"
    assert result.validation_mode == "full"
    assert full_calls == [{"bin/ffmpeg.exe": executable}]
    assert optional_calls == []
    assert cfg.get("runtime_health") == previous


def test_light_validation_blocks_when_previously_healthy_payload_disappears(tmp_path):
    """A light launch must fail closed when a required payload vanishes."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"healthy before payload loss")
    previous = {
        "identity": "payload-v1",
        "components": _complete_success_evidence({"bin/ffmpeg.exe": executable}),
        "validation_mode": "full",
    }
    cfg.settings["runtime_health"] = previous
    executable.unlink()
    full_calls = []
    optional_calls = []
    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        # Return the canonical key with its now-missing path: no ACL behavior is
        # involved, and a previously healthy light-path payload is unavailable.
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": executable},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: full_calls.append(components) or _complete_success_evidence(components),
        optional_resolver=lambda requested: optional_calls.append(requested) or ("whispercpp-cpu", "unavailable"),
    )

    result = service.assess()

    assert result.state == "SETUP_REQUIRED"
    assert result.validation_mode == "light"
    assert result.components["bin/ffmpeg.exe"]["healthy"] is False
    assert full_calls == []
    assert optional_calls == []
    assert cfg.get("runtime_health") == previous


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


def test_runner_captures_os_launch_failure_as_failed_evidence(monkeypatch):
    import lecturepack.infrastructure.runtime_validation as runtime_validation

    def blocked(*args, **kwargs):
        raise OSError("blocked executable")

    monkeypatch.setattr(runtime_validation.subprocess, "Popen", blocked)
    evidence = RuntimeValidator(timeout_ms=1_000).run("blocked.exe", ["--help"])

    assert evidence.argv == ["blocked.exe", "--help"]
    assert evidence.exit_code is None
    assert evidence.reason == "launch failed"
    assert evidence.timed_out is False
    assert "blocked executable" in evidence.stderr
    assert evidence.duration_ms >= 0


def test_unexpected_full_validator_failure_stays_setup_required_without_persistence(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path))
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"x")
    optional_calls = []
    service = RuntimeBootstrapService(
        cfg, runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/ffmpeg.exe": executable},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: (_ for _ in ()).throw(RuntimeError("validator exploded")),
        optional_resolver=lambda requested: optional_calls.append(requested) or ("whispercpp-cpu", "unavailable"),
    )

    for _ in range(2):
        result = service.assess()
        assert result.state == "SETUP_REQUIRED"
        assert result.validation_mode == "full"
        assert result.components["bin/ffmpeg.exe"]["healthy"] is False
        assert "validator exploded" in result.components["bin/ffmpeg.exe"]["reason"]

    assert cfg.get("runtime_health") is None
    assert cfg.get("migration_versions", {}).get("runtime_contract") is None
    assert optional_calls == []


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
