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


# ---------------------------------------------------------------------------
# Plan 02-01, Task 1 (D-01/D-02): persist_runtime_health(exe_paths=...) seeds
# whisper_exe/ffmpeg_exe/ffprobe_exe from the resolved bootstrap inventory on
# a clean install, without ever overwriting a user-set path that is real.
# ---------------------------------------------------------------------------


def test_persist_runtime_health_seeds_exe_paths_from_empty_config(tmp_path):
    """(a) A clean-install config (empty exe keys) is populated on first boot."""
    from lecturepack.infrastructure.config_manager import ConfigManager

    cfg = ConfigManager(str(tmp_path / "profile"))
    assert cfg.get("whisper_exe", "") == ""
    assert cfg.get("ffmpeg_exe", "") == ""
    assert cfg.get("ffprobe_exe", "") == ""

    exe_paths = {
        "whisper_exe": str(tmp_path / "bin" / "whisper-cli.exe"),
        "ffmpeg_exe": str(tmp_path / "bin" / "ffmpeg.exe"),
        "ffprobe_exe": str(tmp_path / "bin" / "ffprobe.exe"),
    }
    cfg.persist_runtime_health(
        {"components": {"x": {"healthy": True}}},
        bundled_model=str(tmp_path / "models" / "ggml-base.en.bin"),
        exe_paths=exe_paths,
    )

    assert cfg.get("whisper_exe") == exe_paths["whisper_exe"]
    assert cfg.get("ffmpeg_exe") == exe_paths["ffmpeg_exe"]
    assert cfg.get("ffprobe_exe") == exe_paths["ffprobe_exe"]


def test_persist_runtime_health_never_overwrites_a_real_user_set_exe_path(tmp_path):
    """(b) A user-set path that os.path.isfile() confirms real is preserved."""
    from lecturepack.infrastructure.config_manager import ConfigManager

    user_whisper = tmp_path / "custom" / "my-whisper.exe"
    user_whisper.parent.mkdir(parents=True, exist_ok=True)
    user_whisper.write_bytes(b"user binary")

    cfg = ConfigManager(str(tmp_path / "profile"))
    cfg.settings["whisper_exe"] = str(user_whisper)

    bundled_whisper = tmp_path / "bin" / "whisper-cli.exe"
    cfg.persist_runtime_health(
        {"components": {"x": {"healthy": True}}},
        bundled_model=str(tmp_path / "models" / "ggml-base.en.bin"),
        exe_paths={"whisper_exe": str(bundled_whisper), "ffmpeg_exe": str(tmp_path / "ffmpeg.exe")},
    )

    assert cfg.get("whisper_exe") == str(user_whisper)
    # ffmpeg_exe had no prior real file, so it IS seeded.
    assert cfg.get("ffmpeg_exe") == str(tmp_path / "ffmpeg.exe")


def test_persist_runtime_health_exe_paths_none_is_backward_compatible(tmp_path):
    """(c) Existing callers passing no exe_paths keep working — no exe keys touched."""
    from lecturepack.infrastructure.config_manager import ConfigManager

    cfg = ConfigManager(str(tmp_path / "profile"))
    cfg.persist_runtime_health(
        {"components": {"x": {"healthy": True}}},
        bundled_model=str(tmp_path / "models" / "ggml-base.en.bin"),
    )

    assert cfg.get("whisper_exe", "") == ""
    assert cfg.get("ffmpeg_exe", "") == ""
    assert cfg.get("ffprobe_exe", "") == ""
    assert cfg.get("migration_versions")["runtime_contract"] == 1


def test_persist_runtime_health_second_call_never_reseeds_empty_exe_paths(tmp_path):
    """(d) Once the migration guard has run, a second call with empty exe
    values does not re-seed them — the migration block is skipped entirely."""
    from lecturepack.infrastructure.config_manager import ConfigManager

    cfg = ConfigManager(str(tmp_path / "profile"))
    cfg.persist_runtime_health(
        {"components": {"x": {"healthy": True}}},
        bundled_model=str(tmp_path / "models" / "ggml-base.en.bin"),
        exe_paths={"whisper_exe": str(tmp_path / "bin" / "whisper-cli.exe")},
    )
    assert cfg.get("whisper_exe") == str(tmp_path / "bin" / "whisper-cli.exe")

    # Simulate the user clearing the setting by hand between boots.
    cfg.settings["whisper_exe"] = ""
    cfg.persist_runtime_health(
        {"components": {"x": {"healthy": True}}},
        bundled_model=str(tmp_path / "models" / "ggml-base.en.bin"),
        exe_paths={"whisper_exe": str(tmp_path / "bin" / "whisper-cli.exe")},
    )

    assert cfg.get("whisper_exe") == ""


def test_bootstrap_assess_passes_exe_paths_through_to_persist_runtime_health(tmp_path, monkeypatch):
    """assess() constructs exe_paths from the resolved inventory and forwards
    them to persist_runtime_health — end-to-end wiring for D-01."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path / "profile"))
    whisper = tmp_path / "bin" / "whisper-cli.exe"
    ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    ffprobe = tmp_path / "bin" / "ffprobe.exe"
    for p in (whisper, ffmpeg, ffprobe):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")

    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {
            "bin/whisper-cli.exe": whisper,
            "bin/ffmpeg.exe": ffmpeg,
            "bin/ffprobe.exe": ffprobe,
        },
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: _complete_success_evidence(components),
    )

    result = service.assess()

    assert result.state == "HEALTHY"
    assert cfg.get("whisper_exe") == str(whisper)
    assert cfg.get("ffmpeg_exe") == str(ffmpeg)
    assert cfg.get("ffprobe_exe") == str(ffprobe)


def test_bootstrap_assess_missing_inventory_entry_does_not_crash(tmp_path):
    """A missing inventory entry (e.g. no ffprobe key resolved) must not crash
    the whole assessment — the guarded .get()-style lookup skips it."""
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    cfg = ConfigManager(str(tmp_path / "profile"))
    whisper = tmp_path / "bin" / "whisper-cli.exe"
    whisper.parent.mkdir(parents=True, exist_ok=True)
    whisper.write_bytes(b"x")

    service = RuntimeBootstrapService(
        cfg,
        runtime_root=tmp_path,
        inventory_resolver=lambda root: {"bin/whisper-cli.exe": whisper},
        identity_provider=lambda root: "payload-v1",
        full_validator=lambda components: _complete_success_evidence(components),
    )

    result = service.assess()

    assert result.state == "HEALTHY"
    assert cfg.get("whisper_exe") == str(whisper)
    assert cfg.get("ffmpeg_exe", "") == ""


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


# ---------------------------------------------------------------------------
# Task 3: parallelized `_validate_full` (D-10) — three independent probes run
# concurrently in a bounded thread pool, with every evidence field, the real
# staged whisper-cli transcription, and the 30s-per-probe bound unchanged.
# ---------------------------------------------------------------------------


def _write_dummy_payload(tmp_path, *, with_ffmpeg=True):
    model = tmp_path / "models" / "ggml-base.en.bin"
    smoke = tmp_path / "smoke" / "runtime-smoke.wav"
    whisper = tmp_path / "bin" / "whisper-cli.exe"
    ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    ffprobe = tmp_path / "bin" / "ffprobe.exe"
    files = [model, smoke, whisper] + ([ffmpeg, ffprobe] if with_ffmpeg else [])
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"dummy payload")
    paths = {
        "bin/whisper-cli.exe": whisper,
        "models/ggml-base.en.bin": model,
        "smoke/runtime-smoke.wav": smoke,
    }
    if with_ffmpeg:
        paths["bin/ffmpeg.exe"] = ffmpeg
        paths["bin/ffprobe.exe"] = ffprobe
    return paths


def test_validate_full_uses_bounded_thread_pool_of_three():
    import inspect

    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    source = inspect.getsource(RuntimeBootstrapService._validate_full)
    assert "ThreadPoolExecutor(max_workers=3)" in source


def test_validate_full_shares_one_validator_with_default_thirty_second_bound(tmp_path, monkeypatch):
    """Exactly one RuntimeValidator() is constructed (shared, not per-worker), with no
    args overriding the default 30s timeout_ms bound."""
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=False)
    construction_calls = []

    class RecordingValidator:
        def __init__(self, *args, **kwargs):
            construction_calls.append((args, kwargs))

        def run(self, program, args):
            return SmokeEvidence([program, *args], 0, "", "", 1, "success", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", RecordingValidator)

    RuntimeBootstrapService._validate_full(paths)

    assert construction_calls == [((), {})]


def test_validate_full_probes_overlap_and_bound_peak_concurrency(tmp_path, monkeypatch):
    """A fake validator that records call order and sleeps proves real overlap:
    elapsed time is materially below the serial sum, and peak concurrency
    never exceeds 3."""
    import threading
    import time as time_module

    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=True)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}
    sleep_s = 0.2

    class SlowValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time_module.sleep(sleep_s)
            with lock:
                state["active"] -= 1
            return SmokeEvidence([program, *args], 0, "", "", int(sleep_s * 1000), "success", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", SlowValidator)

    started = time_module.monotonic()
    results = RuntimeBootstrapService._validate_full(paths)
    elapsed = time_module.monotonic() - started

    assert elapsed < sleep_s * 3 * 0.75  # materially below the serial sum of 3 sleeps
    assert 2 <= state["peak"] <= 3  # real overlap happened, and pool is bounded at 3
    assert set(results) == set(paths)


def test_validate_full_version_probe_worker_exception_propagates(tmp_path, monkeypatch):
    """An exception raised inside a worker propagates out of `_validate_full`
    via `future.result()` rather than vanishing into an unexamined future."""
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=True)
    ffmpeg_str = str(paths["bin/ffmpeg.exe"])

    class ExplodingValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            if program == ffmpeg_str:
                raise RuntimeError("ffmpeg worker exploded")
            return SmokeEvidence([program, *args], 0, "", "", 1, "success", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", ExplodingValidator)

    with pytest.raises(RuntimeError, match="ffmpeg worker exploded"):
        RuntimeBootstrapService._validate_full(paths)


def test_validate_full_cleanup_runs_when_whisper_probe_raises(tmp_path, monkeypatch):
    """`staging.cleanup()` runs exactly once even when the whisper probe itself
    raises, and the caught exception still synthesizes complete failed evidence."""
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=False)
    cleanup_calls = []
    real_staging_cls = runtime_bootstrap.WhisperPathStaging

    class TrackingStaging(real_staging_cls):
        def cleanup(self):
            cleanup_calls.append(True)
            super().cleanup()

    class RaisingValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            raise RuntimeError("whisper probe exploded")

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", RaisingValidator)
    monkeypatch.setattr(runtime_bootstrap, "WhisperPathStaging", TrackingStaging)

    results = RuntimeBootstrapService._validate_full(paths)

    assert cleanup_calls == [True]
    assert results["models/ggml-base.en.bin"]["healthy"] is False
    assert results["models/ggml-base.en.bin"]["reason"] == "admission preparation failed"
    assert results["smoke/runtime-smoke.wav"]["reason"] == "admission preparation failed"


def test_validate_full_ffprobe_failure_reason_preserved_verbatim(tmp_path, monkeypatch):
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=True)
    ffprobe_str = str(paths["bin/ffprobe.exe"])

    class MixedValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            if program == ffprobe_str:
                return SmokeEvidence([program, *args], 3, "", "ffprobe broke", 5, "nonzero exit", False)
            return SmokeEvidence([program, *args], 0, "", "", 5, "success", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", MixedValidator)

    results = RuntimeBootstrapService._validate_full(paths)

    assert results["bin/ffprobe.exe"]["healthy"] is False
    assert results["bin/ffprobe.exe"]["reason"] == "nonzero exit"
    assert results["bin/ffprobe.exe"]["stderr"] == "ffprobe broke"
    assert results["bin/ffmpeg.exe"]["healthy"] is True


def test_validate_full_returns_complete_evidence_fields_and_real_transcription_argv(tmp_path, monkeypatch):
    """Every returned component carries all eight `_FULL_SUCCESS_EVIDENCE_FIELDS`
    keys, and the whisper probe argv is the real staged transcription — model
    flag, file flag, thread count, and no-timestamps flag — never a lighter
    liveness check (D-10)."""
    import lecturepack.services.runtime_bootstrap as runtime_bootstrap
    from lecturepack.infrastructure.runtime_validation import SmokeEvidence
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService

    paths = _write_dummy_payload(tmp_path, with_ffmpeg=True)
    whisper_str = str(paths["bin/whisper-cli.exe"])
    captured_whisper_argv = []

    class RecordingValidator:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, program, args):
            argv = [program, *args]
            if program == whisper_str:
                captured_whisper_argv.append(argv)
            return SmokeEvidence(argv, 0, "", "", 5, "success", False)

    monkeypatch.setattr(runtime_bootstrap, "RuntimeValidator", RecordingValidator)

    results = RuntimeBootstrapService._validate_full(paths)

    for record in results.values():
        assert RuntimeBootstrapService._FULL_SUCCESS_EVIDENCE_FIELDS <= record.keys()
    assert set(results) == set(paths)

    assert captured_whisper_argv, "whisper probe never ran"
    whisper_argv = captured_whisper_argv[0]
    assert "-m" in whisper_argv
    assert "-f" in whisper_argv
    assert "-t" in whisper_argv and "1" in whisper_argv
    assert "-nt" in whisper_argv
