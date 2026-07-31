"""Measure and audit LecturePack's packaged footprint.

Exposes pure, unit-testable functions that walk a filesystem tree and return
plain data structures — no printing, no process launching — mirroring the
pure-predicate style of ``check_clean_state()`` in ``app/packaging/build.py``.
A thin CLI wraps those functions behind explicit flags for the impure work
(measuring a real installer, expanding it into a throwaway directory).

Two numbers this script is deliberately careful never to conflate:
  - an installer's own byte size (the ``Setup.exe`` file itself), and
  - the byte size of the tree that installer expands to on disk.
These are always reported as two distinct rows/fields, never averaged.

Usage (from repo root):
    python scripts/measure_package_footprint.py --installer <Setup.exe> --json out.json
    python scripts/measure_package_footprint.py --tree app/dist/LecturePack --json out.json --markdown out.md
    python scripts/measure_package_footprint.py --installer <Setup.exe> --expand-to <scratch-dir> --json out.json
    python scripts/measure_package_footprint.py --tree app/dist/LecturePack --assert-pruned
    python scripts/measure_package_footprint.py --compare before.json after.json

No function in this module invokes ``subprocess`` with ``shell=True``. The
installer/uninstaller invocations are built as explicit argument lists by
``build_install_argv`` / ``build_uninstall_argv`` (pure, testable) and handed
to ``subprocess.run`` unmodified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Individual files at or above this size are reported as standalone
# contributors (in addition to immediate subdirectory rollups).
LARGE_FILE_THRESHOLD_BYTES = 1_000_000  # 1 MB

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

# Single source of truth, shared with app/packaging/build.py. These were duplicated
# in both files and drifted, so a correct build failed its own audit (BUG-27).
from lecturepack.infrastructure.runtime_inventory import (  # noqa: E402
    OPENGL_SOFTWARE_FALLBACK,
    PRUNABLE_QT_COMPONENTS,
    REQUIRED_QT_WEBENGINE_DEPS,
)

PYSIDE6_DIR = ("_internal", "PySide6")


def _pyside6_targets(names):
    """Map bare PySide6 names to {tree-relative label: path parts}."""
    return {"/".join(PYSIDE6_DIR + (n,)): PYSIDE6_DIR + (n,) for n in names}


GGML_MODEL_FILENAME = "ggml-base.en.bin"


# ---------------------------------------------------------------------------
# Pure measurement functions
# ---------------------------------------------------------------------------


def tree_size(path) -> int:
    """Return the summed byte size of every regular file under ``path``.

    Directory entries themselves contribute zero bytes. Raises
    ``FileNotFoundError`` if ``path`` does not exist rather than silently
    returning 0, so a typo'd path cannot be mistaken for an empty tree.

    Walks with ``followlinks=False`` and skips symlinked entries entirely
    (T-01-01-03: a symlink loop must not cause unbounded recursion).
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"tree_size: path does not exist: {root}")
    if root.is_file():
        return root.stat().st_size
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            if file_path.is_symlink():
                continue
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def top_contributors(path, limit: int = 12) -> list:
    """Return up to ``limit`` largest contributors under ``path``.

    Covers immediate subdirectories of the tree root, immediate
    subdirectories of ``_internal/PySide6/`` (where the mass lives per
    CONTEXT.md's measured baseline), and individual files at or above
    ``LARGE_FILE_THRESHOLD_BYTES``. Each entry is
    ``{"name": <root-relative path, forward-slash>, "bytes": <int>}``,
    sorted descending by bytes.
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"top_contributors: path does not exist: {root}")

    contributors: dict[str, int] = {}

    def _add_immediate_subdirs(directory: Path) -> None:
        if not directory.is_dir():
            return
        for child in sorted(directory.iterdir()):
            if child.is_symlink() or not child.is_dir():
                continue
            rel = child.relative_to(root)
            contributors[str(rel).replace("\\", "/")] = tree_size(child)

    _add_immediate_subdirs(root)
    _add_immediate_subdirs(root / "_internal" / "PySide6")

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            if file_path.is_symlink():
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            if size >= LARGE_FILE_THRESHOLD_BYTES:
                rel = file_path.relative_to(root)
                contributors[str(rel).replace("\\", "/")] = size

    ranked = sorted(contributors.items(), key=lambda kv: kv[1], reverse=True)
    return [{"name": name, "bytes": size} for name, size in ranked[:limit]]


def audit_pruned_tree(dist_app) -> dict:
    """Audit a packaged onedir tree for the D-01 cut targets and D-02 keep.

    Returns a dict reporting, per target, whether it is still present; the
    count of still-present targets; whether `opengl32sw.dll` is present
    (D-02: present is correct, reported separately from the cut targets so
    it is never mistaken for a violation); and how many copies of
    `ggml-base.en.bin` exist anywhere in the tree.
    """
    root = Path(dist_app)
    if not root.exists():
        raise FileNotFoundError(f"audit_pruned_tree: path does not exist: {root}")

    cut_targets_present = {
        name: root.joinpath(*parts).exists()
        for name, parts in _pyside6_targets(PRUNABLE_QT_COMPONENTS).items()
    }
    cut_targets_present_count = sum(1 for present in cut_targets_present.values() if present)

    opengl_present = root.joinpath(*PYSIDE6_DIR, OPENGL_SOFTWARE_FALLBACK).exists()

    # BUG-27: absence here means the app cannot start at all.
    webengine_deps_present = {
        name: root.joinpath(*parts).exists()
        for name, parts in _pyside6_targets(REQUIRED_QT_WEBENGINE_DEPS).items()
    }
    webengine_deps_missing = sorted(
        name for name, present in webengine_deps_present.items() if not present
    )

    ggml_count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            if filename == GGML_MODEL_FILENAME:
                ggml_count += 1

    return {
        "cut_targets": cut_targets_present,
        "cut_targets_present_count": cut_targets_present_count,
        # D-02: a present opengl32sw.dll is correct, not a violation.
        "opengl32sw_present": opengl_present,
        "opengl32sw_disposition": (
            "expected-and-correct (D-02 software GL fallback kept)"
            if opengl_present
            else "absent"
        ),
        "ggml_base_en_bin_count": ggml_count,
        # BUG-27: these must be present; missing means the packaged app cannot start.
        "required_webengine_deps": webengine_deps_present,
        "required_webengine_deps_missing": webengine_deps_missing,
    }


def render_footprint_markdown(record: dict) -> str:
    """Render a measurement record as a markdown table.

    ``record`` may carry any of ``installer_bytes``, ``expanded_bytes``,
    ``tree_bytes`` and ``contributors`` (a list of ``{"name", "bytes"}``
    dicts). The installer's own size and the expanded-tree size are always
    emitted as two separate rows when both are present — this function
    never averages or merges them.
    """
    lines = ["| Item | Bytes |", "|---|---|"]
    if record.get("installer_bytes") is not None:
        lines.append(f"| Installer (own size) | {record['installer_bytes']} |")
    if record.get("expanded_bytes") is not None:
        lines.append(f"| Expanded tree (what Setup.exe installs) | {record['expanded_bytes']} |")
    if record.get("tree_bytes") is not None:
        lines.append(f"| Measured tree | {record['tree_bytes']} |")
    for contributor in record.get("contributors") or []:
        lines.append(f"| {contributor['name']} | {contributor['bytes']} |")
    return "\n".join(lines) + "\n"


def compare_footprints(before: dict, after: dict) -> dict:
    """Return per-entry byte deltas and a total delta between two records.

    Only numeric top-level entries are compared. Deltas are ``after - before``
    per key; the two inputs are never averaged, summed into one figure, or
    otherwise blended — each stays a distinct, attributable number.
    """
    keys = set(before.keys()) | set(after.keys())
    deltas: dict[str, float] = {}
    total_before = 0.0
    total_after = 0.0
    for key in sorted(keys):
        b = before.get(key)
        a = after.get(key)
        if not isinstance(b, (int, float)) and not isinstance(a, (int, float)):
            continue
        b = b if isinstance(b, (int, float)) else 0
        a = a if isinstance(a, (int, float)) else 0
        deltas[key] = a - b
        total_before += b
        total_after += a
    return {
        "deltas": deltas,
        "total_before": total_before,
        "total_after": total_after,
        "total_delta": total_after - total_before,
    }


# ---------------------------------------------------------------------------
# Pure argv builders (kept separate from process launching so tests never
# need to spawn a real installer to verify the invocation shape).
# ---------------------------------------------------------------------------


def build_install_argv(installer_path, dest_dir) -> list:
    """Return the silent-install invocation as an explicit argument list."""
    return [
        str(installer_path),
        "/VERYSILENT",
        "/SP-",
        "/NORESTART",
        "/NOICONS",
        f"/DIR={dest_dir}",
    ]


def build_uninstall_argv(uninstaller_path) -> list:
    """Return the silent-uninstall invocation as an explicit argument list."""
    return [str(uninstaller_path), "/VERYSILENT"]


# ---------------------------------------------------------------------------
# Impure orchestration — guarded behind explicit CLI flags.
# ---------------------------------------------------------------------------


def expand_installer(installer_path, dest_dir, timeout_s: int = 1800) -> dict:
    """Run ``installer_path`` silently into ``dest_dir``, measure, clean up.

    Refuses to run if ``dest_dir`` already exists and is non-empty — a
    throwaway install must never be mistaken for or overwrite a real one
    (T-01-01-01). Always invoked as an argument list, never ``shell=True``
    (T-01-01-02). After measuring, runs ``unins000.exe /VERYSILENT`` inside
    ``dest_dir`` to clean up, and reports if the uninstaller was absent.
    """
    import subprocess

    installer_path = Path(installer_path)
    dest_dir = Path(dest_dir)
    if dest_dir.exists() and any(dest_dir.iterdir()):
        raise RuntimeError(
            f"refusing to install into existing non-empty directory: {dest_dir}"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)

    argv = build_install_argv(installer_path, dest_dir)
    subprocess.run(argv, check=True, timeout=timeout_s)

    expanded_bytes = tree_size(dest_dir)
    contributors = top_contributors(dest_dir)

    uninstaller = dest_dir / "unins000.exe"
    uninstaller_found = uninstaller.exists()
    if uninstaller_found:
        subprocess.run(build_uninstall_argv(uninstaller), check=False, timeout=timeout_s)

    return {
        "expanded_bytes": expanded_bytes,
        "contributors": contributors,
        "uninstaller_found": uninstaller_found,
    }


def _assert_pruned(audit: dict) -> list:
    """Return a list of violation strings for a post-cut tree; empty means clean."""
    violations = []
    for name, present in audit["cut_targets"].items():
        if present:
            violations.append(f"still present: {name}")
    if not audit["opengl32sw_present"]:
        violations.append("opengl32sw.dll missing — D-02 requires it stay")
    if audit["ggml_base_en_bin_count"] != 1:
        violations.append(
            f"ggml-base.en.bin count is {audit['ggml_base_en_bin_count']}, expected exactly 1"
        )
    # BUG-27: the packaged app cannot start without these. Reported as a violation
    # so a measurement run catches it, rather than a user discovering it on launch.
    for name in audit.get("required_webengine_deps_missing", []):
        violations.append(
            f"MISSING REQUIRED {name} — QtWebChannel/QtWebEngineCore link against it; "
            "the packaged app will fail to start (BUG-27)"
        )
    return violations


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure and audit LecturePack's packaged footprint."
    )
    parser.add_argument("--installer", help="Path to a Setup.exe; records its own byte size.")
    parser.add_argument(
        "--expand-to",
        help="Silently install --installer into this (must-not-exist-or-be-empty) directory, "
        "measure the result, then uninstall.",
    )
    parser.add_argument("--tree", help="Path to an already-built tree to measure and audit.")
    parser.add_argument(
        "--assert-pruned",
        action="store_true",
        help="Exit non-zero if any D-01 cut target is present, opengl32sw.dll is absent, "
        "or the ggml-base.en.bin count is not exactly 1. Requires --tree.",
    )
    parser.add_argument("--json", help="Write the measurement record as JSON to this path.")
    parser.add_argument("--markdown", help="Write the measurement record as markdown to this path.")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE_JSON", "AFTER_JSON"),
        help="Print the per-entry and total byte deltas between two previously written JSON records.",
    )
    return parser


def main(argv=None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.compare:
        before_path, after_path = args.compare
        before = json.loads(Path(before_path).read_text(encoding="utf-8"))
        after = json.loads(Path(after_path).read_text(encoding="utf-8"))
        result = compare_footprints(before, after)
        print(json.dumps(result, indent=2))
        return 0

    record: dict = {}

    if args.installer:
        record["installer_bytes"] = tree_size(args.installer)

    if args.expand_to:
        if not args.installer:
            parser.error("--expand-to requires --installer")
        expansion = expand_installer(args.installer, args.expand_to)
        record["expanded_bytes"] = expansion["expanded_bytes"]
        record["contributors"] = expansion["contributors"]
        record["uninstaller_found"] = expansion["uninstaller_found"]
        if not expansion["uninstaller_found"]:
            print(f"WARNING: no uninstaller found in {args.expand_to}", file=sys.stderr)

    exit_code = 0
    if args.tree:
        record["tree_bytes"] = tree_size(args.tree)
        record.setdefault("contributors", top_contributors(args.tree))
        audit = audit_pruned_tree(args.tree)
        record["audit"] = audit
        if args.assert_pruned:
            violations = _assert_pruned(audit)
            if violations:
                for violation in violations:
                    print(f"PRUNE AUDIT FAILED — {violation}", file=sys.stderr)
                exit_code = 1
    elif args.assert_pruned:
        parser.error("--assert-pruned requires --tree")

    if args.json:
        Path(args.json).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")

    if args.markdown:
        Path(args.markdown).write_text(render_footprint_markdown(record), encoding="utf-8")
        print(f"Wrote {args.markdown}")

    if not args.json and not args.markdown:
        print(json.dumps(record, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
