"""Protect hosted candidate/release build wiring and publication boundaries."""
from pathlib import Path
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))


def test_candidate_is_read_only_pr_validation_and_cannot_publish_a_release():
    job = workflow("ci.yml")["jobs"]["electron-candidate"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["permissions"] == {"contents": "read"}
    steps = job["steps"]
    assert not any("action-gh-release" in step.get("uses", "") for step in steps)
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "gh release" not in commands and "git tag" not in commands
    assert "secrets." not in str(job)
    evidence = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert evidence["if"] == "always()"
    paths = evidence["with"]["path"]
    assert "runtime-restore-audit.json" in paths and "electron-candidate-build.log" in paths
    assert "*.exe" not in paths and "*.zip" not in paths


def test_both_builds_install_the_same_python_extension_before_sidecar_packaging():
    candidate = workflow("ci.yml")["jobs"]["electron-candidate"]["steps"]
    release = workflow("release-electron.yml")["jobs"]["desktop-release"]["steps"]
    wheel_steps = []
    for steps in (candidate, release):
        wheel = next(s for s in steps if s.get("name") == "Build and install the Rust Python extension")
        wheel_steps.append(wheel["run"])
        assert "maturin build --release --locked" in wheel["run"]
        assert "--interpreter python" in wheel["run"]
        assert "pip install --no-deps" in wheel["run"]
        assert "import lecturepack_study_core" in wheel["run"]
        assert steps.index(wheel) < next(i for i, s in enumerate(steps) if "python scripts/build_electron_release.py" in s.get("run", ""))
    assert wheel_steps[0] == wheel_steps[1]


def test_candidate_uses_pinned_runtime_and_official_builder_health_and_installer():
    steps = workflow("ci.yml")["jobs"]["electron-candidate"]["steps"]
    commands = "\n".join(s.get("run", "") for s in steps)
    assert commands.index("restore_ci_runtime.py") < commands.index("build_electron_release.py")
    assert "requirements-release.txt" in commands and "npm ci" in commands
    assert "LECTUREPACK_RUNTIME_ROOT=$runtimeRoot" in commands
    assert "LECTUREPACK_MSVC_RUNTIME_DIR=" in commands and "LECTUREPACK_BUILD_ROOT=" in commands
    assert "Get-Command pyinstaller" in commands
    assert "choco install innosetup" in commands
    assert "--skip-sidecar" not in commands and "--skip-installer" not in commands
    assert "packaged_launch_smoke.py" in commands
    cache = next(s for s in steps if s.get("uses") == "actions/cache@v4")
    assert "hashFiles('scripts/ci-runtime-lock.json')" in cache["with"]["key"]


def test_rust_lock_matches_selected_crate_and_is_not_ignored():
    crate = ROOT / "rust/study-core"
    manifest = tomllib.loads((crate / "Cargo.toml").read_text())
    lock = tomllib.loads((crate / "Cargo.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == manifest["package"]["name"])
    assert package["version"] == manifest["package"]["version"]
    pyo3 = next(p for p in lock["package"] if p["name"] == "pyo3")
    assert pyo3["version"].startswith(manifest["dependencies"]["pyo3"]["version"] + ".")
    assert "Cargo.lock" not in (crate / ".gitignore").read_text()
