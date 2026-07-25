"""LECTUREPACK_DATA_DIR override — lets packaged-GUI acceptance and upgrade
tests run against a disposable profile instead of the user's real jobs.

Precedence contract: explicit argument > LECTUREPACK_DATA_DIR > default root.
"""

import importlib
import os

import pytest

from app.desktop import paths
from lecturepack import constants
from lecturepack.infrastructure import config_manager as cm


ENV = "LECTUREPACK_DATA_DIR"


def test_env_var_name_agrees_across_layers():
    """paths.py duplicates the name to stay import-light — keep them equal."""
    assert paths.DATA_DIR_ENV_VAR == constants.DATA_DIR_ENV_VAR == ENV


def test_paths_data_dir_defaults_to_home(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert paths.data_dir() == os.path.join(os.path.expanduser("~"), "LecturePackData")


def test_paths_data_dir_honours_override_and_creates_it(monkeypatch, tmp_path):
    target = tmp_path / "throwaway"
    monkeypatch.setenv(ENV, str(target))
    assert paths.data_dir() == str(target)
    assert target.is_dir()


def test_paths_data_dir_expands_user_and_absolutizes(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(ENV, os.path.join("~", "lp-test-profile"))
    resolved = paths.data_dir()
    assert os.path.isabs(resolved)
    assert "~" not in resolved
    assert resolved == str(tmp_path / "lp-test-profile")


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_override_is_ignored(monkeypatch, blank):
    """An empty/whitespace value must not resolve the data root to cwd."""
    monkeypatch.setenv(ENV, blank)
    home_default = os.path.join(os.path.expanduser("~"), "LecturePackData")
    assert paths.data_dir() == home_default
    assert constants.resolve_default_data_dir() == home_default
    assert cm._env_data_dir() is None


def test_resolve_default_data_dir_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, str(tmp_path / "engine-root"))
    assert constants.resolve_default_data_dir() == str(tmp_path / "engine-root")


def test_default_data_dir_constant_picks_up_override_on_import(monkeypatch, tmp_path):
    """Frozen app reads the env at import — reload proves the constant follows."""
    monkeypatch.setenv(ENV, str(tmp_path / "frozen-root"))
    try:
        reloaded = importlib.reload(constants)
        assert reloaded.DEFAULT_DATA_DIR == str(tmp_path / "frozen-root")
    finally:
        monkeypatch.delenv(ENV, raising=False)
        importlib.reload(constants)


def test_config_manager_uses_override_when_no_arg(monkeypatch, tmp_path):
    target = tmp_path / "cfg-profile"
    monkeypatch.setenv(ENV, str(target))
    config = cm.ConfigManager()
    assert config.data_dir == str(target)
    assert config.config_path == os.path.join(str(target), cm.ConfigManager.CONFIG_FILENAME)
    assert config.get("data_directory") == str(target)


def test_explicit_arg_outranks_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, str(tmp_path / "ignored"))
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    config = cm.ConfigManager(str(explicit))
    assert config.data_dir == str(explicit)


def test_override_outranks_persisted_data_directory(monkeypatch, tmp_path):
    """A config.json copied from a real profile must not win over the override."""
    real_looking = tmp_path / "real-profile"
    throwaway = tmp_path / "throwaway"
    throwaway.mkdir()
    config = cm.ConfigManager(str(throwaway))
    config.set("data_directory", str(real_looking))

    monkeypatch.setenv(ENV, str(throwaway))
    assert config.resolve_data_dir() == str(throwaway)
    assert not real_looking.exists()


def test_resolve_data_dir_falls_back_to_persisted_without_override(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    stored = tmp_path / "stored"
    config = cm.ConfigManager(str(tmp_path / "home"))
    config.set("data_directory", str(stored))
    assert config.resolve_data_dir() == str(stored)
    assert stored.is_dir()
