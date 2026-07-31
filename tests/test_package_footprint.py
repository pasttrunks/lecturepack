"""Unit tests for scripts/measure_package_footprint.py.

Pure filesystem logic against synthetic trees — no real installer is ever
launched and no real build is required, per 01-01-PLAN.md Task 1.
"""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT_PY = REPO / "scripts" / "measure_package_footprint.py"

_spec = importlib.util.spec_from_file_location("_lp_measure_footprint", SCRIPT_PY)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def _make_pruned_tree(root: Path, *, include_cut_targets: bool, ggml_copies: int) -> Path:
    """A synthetic onedir tree for audit_pruned_tree tests."""
    app = root / "LecturePack"
    pyside6 = app / "_internal" / "PySide6"
    pyside6.mkdir(parents=True)
    (app / "bin").mkdir(parents=True)
    (app / "models").mkdir(parents=True)
    (app / "LecturePack.exe").write_bytes(b"x" * 10)

    # opengl32sw.dll is always present in this fixture — D-02 keep.
    (pyside6 / "opengl32sw.dll").write_bytes(b"x" * 20)
    # BUG-27: load-bearing for QtWebChannel/QtWebEngineCore — always present.
    for dll in ("Qt6Qml.dll", "Qt6Quick.dll"):
        (pyside6 / dll).write_bytes(b"x" * 30)

    if include_cut_targets:
        (pyside6 / "translations").mkdir()
        (pyside6 / "translations" / "qtbase_fr.qm").write_bytes(b"x" * 5)
        (pyside6 / "qml").mkdir()
        (pyside6 / "qml" / "propertyGroups.json").write_text("{}")
        for dll in ("Qt6Quick3DRuntimeRender.dll", "Qt6Pdf.dll"):
            (pyside6 / dll).write_bytes(b"x" * 30)

    for i in range(ggml_copies):
        dest_dir = app / "models" if i == 0 else app / "_internal" / "models"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "ggml-base.en.bin").write_bytes(b"m" * 40)

    return app


def test_tree_size_sums_known_files_and_ignores_dir_entries(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.bin").write_bytes(b"x" * 100)
    (tmp_path / "a" / "two.bin").write_bytes(b"x" * 250)
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "three.bin").write_bytes(b"x" * 50)

    assert measure.tree_size(tmp_path) == 400


def test_tree_size_missing_path_raises(tmp_path):
    missing = tmp_path / "does-not-exist"
    try:
        measure.tree_size(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("tree_size on a missing path must raise, not return 0")


def test_top_contributors_sorted_descending_and_limited(tmp_path):
    (tmp_path / "big").mkdir()
    (tmp_path / "big" / "f.bin").write_bytes(b"x" * 5_000_000)
    (tmp_path / "small").mkdir()
    (tmp_path / "small" / "f.bin").write_bytes(b"x" * 10)
    (tmp_path / "loose_large_file.bin").write_bytes(b"x" * 2_000_000)

    contributors = measure.top_contributors(tmp_path, limit=2)
    assert len(contributors) <= 2
    sizes = [c["bytes"] for c in contributors]
    assert sizes == sorted(sizes, reverse=True)
    names = {c["name"] for c in contributors}
    assert "big" in names


def test_audit_pruned_tree_reports_all_cut_targets_present(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=True, ggml_copies=1)
    audit = measure.audit_pruned_tree(app)
    assert audit["cut_targets_present_count"] == 4
    assert all(audit["cut_targets"].values())


def test_audit_pruned_tree_none_present_and_opengl_not_a_violation(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=False, ggml_copies=1)
    audit = measure.audit_pruned_tree(app)
    assert audit["cut_targets_present_count"] == 0
    assert not any(audit["cut_targets"].values())
    # D-02: present opengl32sw.dll must be reported as correct, not flagged.
    assert audit["opengl32sw_present"] is True
    assert "correct" in audit["opengl32sw_disposition"]


def test_audit_pruned_tree_counts_two_ggml_copies(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=False, ggml_copies=2)
    audit = measure.audit_pruned_tree(app)
    assert audit["ggml_base_en_bin_count"] == 2


def test_audit_pruned_tree_counts_one_ggml_copy(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=False, ggml_copies=1)
    audit = measure.audit_pruned_tree(app)
    assert audit["ggml_base_en_bin_count"] == 1


def test_render_footprint_markdown_has_distinct_installer_and_expanded_rows():
    record = {
        "installer_bytes": 800_000_000,
        "expanded_bytes": 900_000_000,
        "contributors": [{"name": "_internal/PySide6", "bytes": 500_000_000}],
    }
    markdown = measure.render_footprint_markdown(record)
    assert "Installer" in markdown and "800000000" in markdown
    assert "Expanded" in markdown and "900000000" in markdown
    assert "_internal/PySide6" in markdown and "500000000" in markdown


def test_compare_footprints_returns_deltas_not_average():
    before = {"tree_bytes": 1_900_000_000}
    after = {"tree_bytes": 1_500_000_000}
    result = measure.compare_footprints(before, after)
    assert result["deltas"]["tree_bytes"] == -400_000_000
    assert result["total_delta"] == -400_000_000
    # An averaged figure would be 1_700_000_000 — must not appear as the delta.
    assert result["total_delta"] != (before["tree_bytes"] + after["tree_bytes"]) / 2


def test_build_install_argv_is_an_argument_list_not_a_shell_string():
    argv = measure.build_install_argv(r"C:\out\Setup.exe", r"C:\scratch\dest")
    assert isinstance(argv, list)
    assert argv[0] == r"C:\out\Setup.exe"
    assert "/VERYSILENT" in argv
    assert any(part.startswith("/DIR=") for part in argv)


def test_build_uninstall_argv_is_an_argument_list():
    argv = measure.build_uninstall_argv(r"C:\scratch\dest\unins000.exe")
    assert isinstance(argv, list)
    assert argv == [r"C:\scratch\dest\unins000.exe", "/VERYSILENT"]


def test_expand_installer_refuses_existing_nonempty_directory(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "already-here.txt").write_text("residue")
    fake_installer = tmp_path / "Setup.exe"
    fake_installer.write_bytes(b"x")

    try:
        measure.expand_installer(fake_installer, dest)
    except RuntimeError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expand_installer must refuse an existing non-empty directory")


def test_no_shell_true_anywhere_in_module():
    """No actual call in the module passes shell=True (docstring mentions of
    the phrase, used to describe what NOT to do, are not code and don't count)."""
    tree = ast.parse(SCRIPT_PY.read_text(encoding="utf-8"))
    offending_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
    ]
    assert not offending_calls, "found a call with shell=True"


def test_cli_help_lists_all_required_flags():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for flag in (
        "--installer", "--expand-to", "--tree", "--assert-pruned",
        "--json", "--markdown", "--compare",
    ):
        assert flag in result.stdout, f"--help output missing {flag}"


def test_cli_tree_and_assert_pruned_fails_on_unpruned_synthetic_tree(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=True, ggml_copies=2)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "--tree", str(app), "--assert-pruned"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_cli_tree_and_assert_pruned_passes_on_pruned_synthetic_tree(tmp_path):
    app = _make_pruned_tree(tmp_path, include_cut_targets=False, ggml_copies=1)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "--tree", str(app), "--assert-pruned"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
