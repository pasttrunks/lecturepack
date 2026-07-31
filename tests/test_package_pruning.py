"""Unit tests for D-01 post-build Qt pruning and D-05 model-dedupe resolution.

Pure filesystem logic against synthetic ``tmp_path`` trees, plus a sandboxed
execution of ``lecturepack.spec``'s data-list seam (no real PyInstaller build,
no real onedir tree) -- per 01-04-PLAN.md Tasks 1-2. No test in this file
launches a real build.
"""

import importlib.util
import os
import re
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
    """A synthetic onedir tree carrying the D-01 targets plus survivors."""
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



def test_qml_and_quick_dlls_are_never_prunable():
    """Regression guard for the 2026-07-31 startup break.

    Pruning these two produced a build that died before showing a window:
    `DLL load failed while importing QtWebChannel` then `... QtWebEngineCore`.
    Their absence is invisible to every unit test and to the packaged runtime
    smoke (which exercises ffmpeg/ffprobe/whisper-cli, not the Qt import chain),
    so it is pinned by name here as well as structurally below.
    """
    assert "Qt6Qml.dll" not in build.PRUNABLE_QT_COMPONENTS
    assert "Qt6Quick.dll" not in build.PRUNABLE_QT_COMPONENTS


def test_prune_removes_all_four_targets(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    pyside6 = app / "_internal" / "PySide6"
    result = build.prune_unused_qt_components(app)

    assert not (pyside6 / "translations").exists()
    assert not (pyside6 / "qml").exists()
    for dll in ("Qt6Quick3DRuntimeRender.dll", "Qt6Pdf.dll"):
        assert not (pyside6 / dll).exists()
    # Load-bearing: must survive pruning.
    for dll in ("Qt6Qml.dll", "Qt6Quick.dll"):
        assert (pyside6 / dll).exists()
    assert len(result["removed"]) == 4
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
    assert len(first["removed"]) == 4
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


def _qt_dll_dependency_names(dll_path: Path) -> set[str]:
    """Return the Qt6*.dll names referenced inside a PE binary.

    Scans the raw bytes for `Qt6<Name>.dll` rather than parsing the PE import
    directory. That over-approximates (a name in any string table counts), which
    is the safe direction for this guard: it can only ever be too cautious about
    deleting something, never too permissive.
    """
    raw = dll_path.read_bytes()
    text = raw.decode("ascii", errors="ignore")
    return set(re.findall(r"Qt6[A-Za-z0-9]+\.dll", text))


@pytest.mark.skipif(
    not (Path(os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "")) / "_internal" / "PySide6").is_dir(),
    reason="needs a real packaged tree: set LECTUREPACK_ONEDIR_FIXTURE",
)
def test_pruned_components_are_not_imported_by_surviving_qt_dlls():
    """No pruned DLL may appear in a surviving Qt DLL's dependency list.

    This is the structural lesson of the 2026-07-31 startup break. The pre-existing
    `test_prune_does_not_remove_required_qt_components` passed throughout, because it
    compared against a hand-written idea of which DLLs are "required" — and that list
    did not mention Qt6Qml.dll or Qt6Quick.dll. Meanwhile the binaries themselves said
    plainly that Qt6WebChannel.dll imports Qt6Qml.dll and Qt6WebEngineCore.dll imports
    both Qt6Qml.dll and Qt6Quick.dll.

    So this test asks the binaries instead of asking a human's list. Any future entry
    added to PRUNABLE_QT_COMPONENTS that something still links against fails here.

    The check is a transitive closure from what `app/desktop/main.py` actually imports,
    not a flat scan of every DLL present. A flat scan is wrong in a way worth recording:
    `Qt6PdfQuick.dll` references `Qt6Pdf.dll`, and five `Qt6Quick3D*.dll` reference
    `Qt6Quick3DRuntimeRender.dll` -- yet pruning both those targets is fine, because
    nothing the app loads ever reaches those referencing DLLs. Only reachability from
    the real entry points distinguishes "genuinely unused" from "load-bearing".
    """
    pyside6 = Path(os.environ["LECTUREPACK_ONEDIR_FIXTURE"]) / "_internal" / "PySide6"
    prunable_dlls = {
        name for name in build.PRUNABLE_QT_COMPONENTS if name.lower().endswith(".dll")
    }

    # The Qt modules app/desktop/main.py imports (QtCore, QtGui, QtWidgets,
    # QtWebEngineCore, QtWebEngineWidgets, QtWebChannel), as DLL names.
    entry_points = [
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
        "Qt6Network.dll",
        "Qt6WebChannel.dll",
        "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll",
    ]

    reachable: set[str] = set()
    frontier = [n for n in entry_points if (pyside6 / n).is_file()]
    assert frontier, f"no Qt entry-point DLLs found in {pyside6} — wrong fixture?"
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        path = pyside6 / current
        if not path.is_file():
            continue
        for dep in _qt_dll_dependency_names(path):
            if dep not in reachable:
                frontier.append(dep)

    violations = sorted(reachable & prunable_dlls)
    assert not violations, (
        "PRUNABLE_QT_COMPONENTS lists DLLs reachable from the app's own Qt imports. "
        "Pruning these yields a build that cannot start:\n  "
        + "\n  ".join(violations)
        + f"\n\nReachable closure was {len(reachable)} DLLs from entry points "
        + ", ".join(entry_points)
    )




def test_assert_pruned_flags_missing_webengine_deps():
    """A tree with the cuts done but Qt6Qml missing must FAIL the audit."""
    audit = {
        "cut_targets": {"_internal/PySide6/qml": False},
        "cut_targets_present_count": 0,
        "opengl32sw_present": True,
        "ggml_base_en_bin_count": 1,
        "required_webengine_deps": {"_internal/PySide6/Qt6Qml.dll": False},
        "required_webengine_deps_missing": ["_internal/PySide6/Qt6Qml.dll"],
    }
    violations = measure._assert_pruned(audit)
    assert any("MISSING REQUIRED" in v and "Qt6Qml.dll" in v for v in violations), violations


def test_prune_target_names_disjoint_from_canonical_inventory():
    inventory = set(canonical_inventory(("ggml-cpu-haswell.dll",)))
    assert set(build.PRUNABLE_QT_COMPONENTS).isdisjoint(inventory)


def test_prune_returns_inspectable_record(tmp_path):
    app = _make_pruning_fixture(tmp_path)
    result = build.prune_unused_qt_components(app)
    assert isinstance(result, dict)
    assert "removed" in result and "reclaimed_bytes" in result
    assert set(result["removed"].keys()) == set(build.PRUNABLE_QT_COMPONENTS)


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
