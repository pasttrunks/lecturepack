"""Unit tests for D-01 post-build Qt pruning and D-05 model-dedupe resolution.

Pure filesystem logic against synthetic ``tmp_path`` trees, plus a sandboxed
execution of ``lecturepack.spec``'s data-list seam (no real PyInstaller build,
no real onedir tree) -- per 01-04-PLAN.md Tasks 1-2. No test in this file
launches a real build.
"""

import importlib.util
import os
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD_PY = REPO / "app" / "packaging" / "build.py"
SPEC_PY = REPO / "app" / "packaging" / "lecturepack.spec"

_build_spec = importlib.util.spec_from_file_location("_lp_build_pruning", BUILD_PY)
build = importlib.util.module_from_spec(_build_spec)
_build_spec.loader.exec_module(build)

MEASURE_PY = REPO / "scripts" / "measure_package_footprint.py"
_measure_spec = importlib.util.spec_from_file_location("_lp_measure_pruning", MEASURE_PY)
measure = importlib.util.module_from_spec(_measure_spec)
_measure_spec.loader.exec_module(measure)

from lecturepack.infrastructure.runtime_inventory import canonical_inventory, resolve_inventory
from app.desktop import engine_adapter


# ---------------------------------------------------------------------------
# Task 1: prune_unused_qt_components / PRUNABLE_QT_COMPONENTS
# ---------------------------------------------------------------------------


def _make_pruning_fixture(root: Path) -> Path:
    """A synthetic onedir tree carrying all six D-01 targets plus survivors."""
    app = root / "LecturePack"
    pyside6 = app / "_internal" / "PySide6"
    (pyside6 / "translations").mkdir(parents=True)
    (pyside6 / "translations" / "qtwebengine_locales_en-US.pak").write_bytes(b"x" * 100)
    (pyside6 / "qml").mkdir(parents=True)
    (pyside6 / "qml" / "propertyGroups.json").write_text("{}")
    for dll in ("Qt6Qml.dll", "Qt6Quick.dll", "Qt6Quick3DRuntimeRender.dll", "Qt6Pdf.dll"):
        (pyside6 / dll).write_bytes(b"x" * 50)
    # Required keep (D-02).
    (pyside6 / "opengl32sw.dll").write_bytes(b"x" * 20)
    # Required-to-survive Qt components the app actually uses.
    for dll in ("Qt6WebEngineCore.dll", "Qt6WebEngineWidgets.dll", "Qt6Core.dll",
                "Qt6Gui.dll", "Qt6Widgets.dll"):
        (pyside6 / dll).write_bytes(b"x" * 30)
    # Canonical payload untouched by pruning.
    (app / "bin").mkdir(parents=True)
    (app / "models").mkdir(parents=True)
    (app / "smoke").mkdir(parents=True)
    (app / "bin" / "whisper-cli.exe").write_bytes(b"x")
    (app / "models" / "ggml-base.en.bin").write_bytes(b"x")
    (app / "smoke" / "runtime-smoke.wav").write_bytes(b"x")
    (app / "lecturepack.ico").write_bytes(b"x")
    (app / "_internal" / "base_library.zip").write_bytes(b"x")
    return app


def test_prunable_qt_components_has_exactly_six_targets():
    assert len(build.PRUNABLE_QT_COMPONENTS) == 6


def test_prune_removes_all_six_targets(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    pyside6 = app / "_internal" / "PySide6"
    result = build.prune_unused_qt_components(app)

    assert not (pyside6 / "translations").exists()
    assert not (pyside6 / "qml").exists()
    for dll in ("Qt6Qml.dll", "Qt6Quick.dll", "Qt6Quick3DRuntimeRender.dll", "Qt6Pdf.dll"):
        assert not (pyside6 / dll).exists()
    assert len(result["removed"]) == 6
    assert result["reclaimed_bytes"] > 0


def test_prune_keeps_opengl32sw_dll_per_d02(tmp_path):
    """D-02: the software GL fallback must survive pruning."""
    app = _make_pruning_fixture(tmp_path)
    build.prune_unused_qt_components(app)
    assert (app / "_internal" / "PySide6" / "opengl32sw.dll").exists()


def test_prune_is_idempotent_when_targets_already_absent(tmp_path):
    app = tmp_path / "LecturePack"
    pyside6 = app / "_internal" / "PySide6"
    pyside6.mkdir(parents=True)
    (pyside6 / "opengl32sw.dll").write_bytes(b"x")
    result = build.prune_unused_qt_components(app)
    assert result["removed"] == {}
    assert result["reclaimed_bytes"] == 0


def test_prune_second_run_reports_zero_removals(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    first = build.prune_unused_qt_components(app)
    assert len(first["removed"]) == 6
    second = build.prune_unused_qt_components(app)
    assert second["removed"] == {}
    assert second["reclaimed_bytes"] == 0


def test_prune_does_not_touch_files_outside_pyside6(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    build.prune_unused_qt_components(app)
    assert (app / "bin" / "whisper-cli.exe").exists()
    assert (app / "models" / "ggml-base.en.bin").exists()
    assert (app / "smoke" / "runtime-smoke.wav").exists()
    assert (app / "lecturepack.ico").exists()
    assert (app / "_internal" / "base_library.zip").exists()


def test_prune_does_not_remove_required_qt_components(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    build.prune_unused_qt_components(app)
    pyside6 = app / "_internal" / "PySide6"
    for dll in ("Qt6WebEngineCore.dll", "Qt6WebEngineWidgets.dll", "Qt6Core.dll",
                "Qt6Gui.dll", "Qt6Widgets.dll"):
        assert (pyside6 / dll).exists()


def test_prune_target_names_disjoint_from_canonical_inventory():
    inventory = set(canonical_inventory(("ggml-cpu-haswell.dll",)))
    assert set(build.PRUNABLE_QT_COMPONENTS.keys()).isdisjoint(inventory)


def test_prune_returns_inspectable_record(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    result = build.prune_unused_qt_components(app)
    assert isinstance(result, dict)
    assert "removed" in result and "reclaimed_bytes" in result
    assert set(result["removed"].keys()) == set(build.PRUNABLE_QT_COMPONENTS.keys())


def test_main_calls_prune_between_bundle_engine_and_validate_clean_state():
    """Source-order assertion: prune_unused_qt_components() must run after
    bundle_engine() and before validate_clean_state() inside main()."""
    source = BUILD_PY.read_text(encoding="utf-8")
    main_body = source[source.index("def main() -> None:"):]
    bundle_idx = main_body.index("bundle_engine()")
    prune_idx = main_body.index("prune_unused_qt_components(")
    validate_idx = main_body.index("validate_clean_state()")
    assert bundle_idx < prune_idx < validate_idx


def test_spec_excludes_list_unchanged_by_pruning_mechanism():
    """01-RESEARCH.md proves excludes cannot remove the six D-01 targets --
    pruning must not add them to the excludes list as a (non-working) fix."""
    text = SPEC_PY.read_text(encoding="utf-8")
    excludes_line = next(line for line in text.splitlines() if "excludes=[" in line or "excludes=[" in line.strip())
    for target in build.PRUNABLE_QT_COMPONENTS:
        assert target not in excludes_line


# ---------------------------------------------------------------------------
# D-24: torch / transformers excludes
# ---------------------------------------------------------------------------


def test_spec_excludes_torch_and_transformers():
    text = SPEC_PY.read_text(encoding="utf-8")
    assert '"torch"' in text
    assert '"transformers"' in text


# ---------------------------------------------------------------------------
# Task 2: model dedupe (spec datas) + D-05 resolution proof
# ---------------------------------------------------------------------------


def _run_lecturepack_spec(monkeypatch):
    """Execute lecturepack.spec's data-list seam without a real PyInstaller build."""
    captured = {}
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda _name: []
    hooks.collect_submodules = lambda _name: []
    pyinstaller = ModuleType("PyInstaller")
    utils = ModuleType("PyInstaller.utils")
    pyinstaller.utils = utils
    utils.hooks = hooks

    class _Analysis:
        def __init__(self, _scripts, **kwargs):
            captured["datas"] = kwargs["datas"]
            captured["excludes"] = kwargs.get("excludes", [])
            self.pure = []
            self.zipped_data = []
            self.scripts = []
            self.binaries = []
            self.zipfiles = []
            self.datas = []

    monkeypatch.setitem(sys.modules, "PyInstaller", pyinstaller)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", utils)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    monkeypatch.setattr("PyInstaller.utils.hooks.collect_data_files", hooks.collect_data_files)
    monkeypatch.setattr("PyInstaller.utils.hooks.collect_submodules", hooks.collect_submodules)
    runpy.run_path(str(SPEC_PY), init_globals={
        "SPECPATH": str(SPEC_PY.parent), "Analysis": _Analysis,
        "PYZ": lambda *_a, **_k: object(), "EXE": lambda *_a, **_k: object(),
        "COLLECT": lambda *_a, **_k: object(),
    })
    return captured


def test_spec_no_longer_duplicates_demo_model_in_datas(monkeypatch):
    captured = _run_lecturepack_spec(monkeypatch)
    model = REPO / "models" / "ggml-base.en.bin"
    assert (str(model), "models") not in captured["datas"]


def test_spec_excludes_captured_include_torch_and_transformers(monkeypatch):
    captured = _run_lecturepack_spec(monkeypatch)
    assert "torch" in captured["excludes"]
    assert "transformers" in captured["excludes"]


def test_spec_still_raises_when_demo_model_source_missing(monkeypatch):
    """The build-time guard survives the datas-entry removal (bundle_engine()
    still needs the source file present to copy from)."""
    model = REPO / "models" / "ggml-base.en.bin"
    real_isfile = os.path.isfile

    def fake_isfile(path):
        if os.fspath(path) == str(model):
            return False
        return real_isfile(path)

    monkeypatch.setattr(os.path, "isfile", fake_isfile)
    with pytest.raises(RuntimeError, match="guided-demo Whisper model"):
        _run_lecturepack_spec(monkeypatch)


def _make_frozen_meipass(tmp_path: Path) -> Path:
    meipass = tmp_path / "_internal"
    (meipass / "ui").mkdir(parents=True)
    return meipass


def test_d05_bundled_demo_model_resolves_to_canonical_when_only_survivor_exists(monkeypatch, tmp_path):
    """D-05: with the removed _internal/models/ duplicate absent, the frozen
    fallback chain must still reach the surviving top-level copy."""
    meipass = _make_frozen_meipass(tmp_path)
    resource_root = tmp_path
    canonical_model = resource_root / "models" / "ggml-base.en.bin"
    canonical_model.parent.mkdir(parents=True)
    canonical_model.write_bytes(b"survivor")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    adapter = engine_adapter.LecturePackAdapter.__new__(engine_adapter.LecturePackAdapter)
    adapter.config = SimpleNamespace(resource_dir=str(resource_root))
    assert adapter._bundled_demo_model_path(adapter.config) == str(canonical_model)


def test_bundled_demo_model_resolves_when_both_copies_still_present(monkeypatch, tmp_path):
    """Behavior is unchanged for anyone on an old, not-yet-rebuilt onedir."""
    meipass = _make_frozen_meipass(tmp_path)
    duplicate_model = meipass / "models" / "ggml-base.en.bin"
    duplicate_model.parent.mkdir(parents=True)
    duplicate_model.write_bytes(b"duplicate (pre-dedupe build)")
    resource_root = tmp_path
    canonical_model = resource_root / "models" / "ggml-base.en.bin"
    canonical_model.parent.mkdir(parents=True, exist_ok=True)
    canonical_model.write_bytes(b"survivor")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    adapter = engine_adapter.LecturePackAdapter.__new__(engine_adapter.LecturePackAdapter)
    adapter.config = SimpleNamespace(resource_dir=str(resource_root))
    result = adapter._bundled_demo_model_path(adapter.config)
    assert result and os.path.isfile(result)


def test_bundled_demo_model_returns_empty_string_when_neither_copy_exists(monkeypatch, tmp_path):
    """Existing contract preserved: no candidate found -> empty string, no raise."""
    meipass = _make_frozen_meipass(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    adapter = engine_adapter.LecturePackAdapter.__new__(engine_adapter.LecturePackAdapter)
    adapter.config = SimpleNamespace(resource_dir=str(tmp_path / "nowhere"))
    assert adapter._bundled_demo_model_path(adapter.config) == ""


def test_resolve_inventory_still_resolves_deduped_model(tmp_path):
    root = tmp_path / "LecturePack"
    (root / "bin").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    (root / "smoke").mkdir(parents=True)
    for rel in ["bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/whisper-cli.exe",
                "bin/whisper.dll", "bin/ggml.dll", "bin/ggml-base.dll",
                "bin/ggml-cpu-haswell.dll", "models/ggml-base.en.bin",
                "smoke/runtime-smoke.wav"]:
        (root / rel).write_bytes(b"x")
    resolved = resolve_inventory(root)
    assert resolved["models/ggml-base.en.bin"] == (root / "models" / "ggml-base.en.bin").resolve()


def test_audit_pruned_tree_reports_single_model_copy_post_dedupe(tmp_path):
    root = tmp_path / "LecturePack"
    (root / "models").mkdir(parents=True)
    (root / "models" / "ggml-base.en.bin").write_bytes(b"x")
    (root / "_internal" / "PySide6").mkdir(parents=True)
    (root / "_internal" / "PySide6" / "opengl32sw.dll").write_bytes(b"x")
    audit = measure.audit_pruned_tree(root)
    assert audit["ggml_base_en_bin_count"] == 1
    assert audit["opengl32sw_present"] is True
