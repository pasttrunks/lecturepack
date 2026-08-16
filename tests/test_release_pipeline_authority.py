"""Guard the release pipeline invariants for the LecturePack desktop app.

Two things must stay true:

1. Exactly one workflow may publish the desktop application assets. The
   retained legacy Qt/runtime-repair workflow historically built
   app/packaging/build.py (which runs Inno Setup) and uploaded its output as
   LecturePack-<version>-Setup.exe -- the same name the Electron release path
   uses. That made the published installer ambiguous, and must never recur.

2. The authoritative version surfaces must agree, and the checker must
   actually fail when they do not.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ELECTRON_RELEASE = WORKFLOWS / "release-electron.yml"
RUNTIME_REPAIR = WORKFLOWS / "release-runtime-repair.yml"

sys.path.insert(0, str(ROOT / "scripts"))

# The four assets only the canonical Electron release path may publish.
DESKTOP_ASSETS = (
    "Setup.exe",
    "Portable.zip",
    "SHA256SUMS.txt",
    "release-manifest.json",
)

# A hard import, deliberately not importorskip: this module is the guard on
# the P0 separation between the authoritative Electron desktop release and the
# legacy runtime-repair workflow. If PyYAML is missing the guard must fail
# loudly, not skip and report green. PyYAML is declared in requirements-dev.txt.
import yaml  # noqa: E402


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _uploaded_files(workflow: dict) -> list[str]:
    """Every path handed to a release-publishing action in a workflow."""
    uploaded: list[str] = []
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if not str(step.get("uses", "")).startswith("softprops/action-gh-release"):
                continue
            files = (step.get("with") or {}).get("files") or ""
            uploaded.extend(line.strip() for line in str(files).splitlines() if line.strip())
    return uploaded


def test_both_release_workflows_exist_and_the_old_ambiguous_name_is_gone():
    assert ELECTRON_RELEASE.is_file(), "the authoritative Electron release workflow is missing"
    assert RUNTIME_REPAIR.is_file(), "the runtime-repair workflow is missing"
    assert not (WORKFLOWS / "release.yml").exists(), (
        "release.yml was renamed so each workflow's purpose is unmistakable"
    )


@pytest.mark.parametrize("asset", DESKTOP_ASSETS)
def test_runtime_repair_workflow_never_publishes_desktop_assets(asset):
    for entry in _uploaded_files(_workflow(RUNTIME_REPAIR)):
        assert not entry.endswith(asset), (
            f"the runtime-repair workflow must never publish {asset}: {entry}"
        )


def test_runtime_repair_workflow_cannot_build_an_installer_at_all():
    text = RUNTIME_REPAIR.read_text(encoding="utf-8")
    # It may still build the runtime onedir, but only with Inno Setup skipped.
    assert "packaging/build.py --no-installer" in text, (
        "the runtime-repair workflow must build the onedir with --no-installer"
    )
    assert not re.search(r"^\s*run:\s*choco install innosetup", text, re.MULTILINE), (
        "the runtime-repair workflow must not install the Inno Setup compiler"
    )
    assert "Refuse to publish anything that looks like the desktop installer" in text, (
        "the runtime-repair workflow needs its fail-closed desktop-asset guard"
    )


@pytest.mark.parametrize("asset", DESKTOP_ASSETS)
def test_electron_workflow_publishes_every_desktop_asset(asset):
    uploaded = _uploaded_files(_workflow(ELECTRON_RELEASE))
    assert any(entry.endswith(asset) for entry in uploaded), (
        f"the authoritative Electron release must publish {asset}; got {uploaded}"
    )


def test_electron_workflow_publishes_exactly_the_four_desktop_assets():
    uploaded = _uploaded_files(_workflow(ELECTRON_RELEASE))
    assert len(uploaded) == len(DESKTOP_ASSETS), uploaded
    # No legacy Qt runtime ZIPs may ride along on the application release.
    assert not any("Runtime-" in entry for entry in uploaded), uploaded


def test_electron_workflow_uses_the_one_product_builder():
    text = ELECTRON_RELEASE.read_text(encoding="utf-8")
    assert "scripts/build_electron_release.py" in text
    assert "packaging/build.py" not in text, (
        "the Electron release must not invoke the legacy Qt builder"
    )


def test_electron_workflow_signs_before_generating_final_hashes():
    """Signing rewrites the installer bytes, so hashes must come afterwards."""
    text = ELECTRON_RELEASE.read_text(encoding="utf-8")
    sign_at = text.index("Authenticode sign the installer")
    hashes_at = text.index("Generate FINAL hashes and updater manifest")
    publish_at = text.index("Publish the stable desktop release")
    assert sign_at < hashes_at < publish_at, (
        "order must be build -> sign -> final hashes/manifest -> publish"
    )


def test_electron_workflow_records_when_signing_is_unavailable():
    assert "AUTHENTICODE SIGNING: NOT AVAILABLE" in ELECTRON_RELEASE.read_text(encoding="utf-8")


# ------------------------------------------------------------- versioning
def test_every_authoritative_version_surface_agrees():
    from verify_release_versions import verify

    ok, message = verify()
    assert ok, message


def test_version_check_fails_closed_when_a_surface_disagrees(tmp_path, monkeypatch):
    import verify_release_versions as vrv

    real = vrv.collect()
    disagreeing = dict(real)
    disagreeing["electron-spike/package.json"] = "9.9.9"
    monkeypatch.setattr(vrv, "collect", lambda: disagreeing)

    ok, message = vrv.verify()
    assert ok is False
    assert "disagree" in message


def test_version_check_fails_closed_when_the_tag_does_not_match():
    from verify_release_versions import verify

    ok, message = verify("99.0.0")
    assert ok is False
    assert "expected '99.0.0'" in message


def test_release_build_writes_the_published_sha256sums():
    """SHA256SUMS.txt is a published artifact; the call to produce it was once
    dropped, so the full build crashed with NameError AFTER compressing
    everything and never wrote the file."""
    source = (ROOT / "scripts" / "build_electron_release.py").read_text(encoding="utf-8")
    body = source[source.index("def main("):]
    assert "sums = write_sha256sums(version, output)" in body
    assert body.index("sums = write_sha256sums(version, output)") < body.index('"sha256sums": str(sums)')


def test_official_build_always_cleans_the_pyinstaller_cache():
    """A release must not inherit stale PyInstaller artifacts from a prior build."""
    source = (ROOT / "electron-spike" / "package-sidecar.mjs").read_text(encoding="utf-8")
    assert "LECTUREPACK_OFFICIAL_BUILD" in source
    assert "if (officialBuild || cleanRequested)" in source
