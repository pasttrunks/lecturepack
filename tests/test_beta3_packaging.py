"""Unit tests for the beta.3 packaging clean-state gate (build.check_clean_state).

Verifies a fresh-install onedir is flagged when it bundles job/dev data or is
missing engine payload, and that Qt's own _internal JSON assets are allowed.
Pure filesystem logic against synthetic trees — no real build required.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD_PY = REPO / "app" / "packaging" / "build.py"

_spec = importlib.util.spec_from_file_location("_lp_build", BUILD_PY)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def _make_clean_dist(root: Path) -> Path:
    """A minimal well-formed onedir that must pass the gate."""
    app = root / "LecturePack"
    (app / "bin").mkdir(parents=True)
    (app / "models").mkdir(parents=True)
    (app / "_internal" / "PySide6" / "qml").mkdir(parents=True)
    for rel in ["LecturePack.exe",
                "bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/whisper-cli.exe",
                "bin/whisper.dll", "bin/ggml.dll", "bin/ggml-base.dll",
                "bin/ggml-cpu-haswell.dll",
                "models/ggml-base.en.bin"]:
        (app / rel).write_bytes(b"x")
    # Qt's own JSON asset — must be allowed.
    (app / "_internal" / "PySide6" / "qml" / "propertyGroups.json").write_text("{}")
    return app


def test_clean_dist_passes(tmp_path):
    app = _make_clean_dist(tmp_path)
    assert build.check_clean_state(app) == []


def test_bundled_jobs_dir_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "jobs" / "abc").mkdir(parents=True)
    (app / "jobs" / "abc" / "state.json").write_text("{}")
    v = build.check_clean_state(app)
    assert any("jobs" in x for x in v)


def test_bundled_config_json_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "config.json").write_text("{}")
    v = build.check_clean_state(app)
    assert any("config.json" in x for x in v)


def test_stray_app_json_flagged_but_qt_json_allowed(tmp_path):
    app = _make_clean_dist(tmp_path)
    # a leaked manifest at app root (NOT under _internal)
    (app / "manifest.json").write_text("{}")
    v = build.check_clean_state(app)
    assert any("manifest.json" in x for x in v)
    # the Qt asset under _internal is not flagged
    assert not any("propertyGroups.json" in x for x in v)


def test_bundled_database_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "lecturepack.db").write_bytes(b"\x00")
    v = build.check_clean_state(app)
    assert any("lecturepack.db" in x for x in v)


def test_missing_engine_payload_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "bin" / "whisper-cli.exe").unlink()
    v = build.check_clean_state(app)
    assert any("whisper-cli.exe" in x for x in v)


def test_empty_required_file_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "models" / "ggml-base.en.bin").write_bytes(b"")
    v = build.check_clean_state(app)
    assert any("ggml-base.en.bin" in x for x in v)


def test_missing_cpu_backend_dlls_flagged(tmp_path):
    app = _make_clean_dist(tmp_path)
    (app / "bin" / "ggml-cpu-haswell.dll").unlink()
    v = build.check_clean_state(app)
    assert any("ggml-cpu" in x for x in v)
