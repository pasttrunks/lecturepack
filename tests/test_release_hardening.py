"""Focused contracts for the supported-Windows release hardening pass."""
from __future__ import annotations

import builtins
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _ok(check_id: str) -> dict[str, object]:
    return {
        "id": check_id,
        "ok": True,
        "required": True,
        "fatal_at_startup": check_id not in {"study_core", "yt_dlp", "yt_dlp_ejs", "js_runtime"},
        "title": "ok",
        "detail": "ok",
        "technical": "",
    }


def test_packaged_health_contract_has_stable_required_checks(tmp_path, monkeypatch):
    from lecturepack.services import packaged_health

    monkeypatch.setattr(packaged_health, "data_directory_writable", lambda _path: {"writable": True, "detail": "ok"})
    monkeypatch.setattr(packaged_health, "_program_check", lambda check_id, *_args: _ok(check_id))
    monkeypatch.setattr(packaged_health, "_whisper_runtime_check", lambda *_args: _ok("whisper_runtime"))
    monkeypatch.setattr(packaged_health, "_whisper_smoke_check", lambda *_args: _ok("whisper_smoke"))
    monkeypatch.setattr(packaged_health, "_readable_file", lambda _path: (True, "readable"))

    result = packaged_health.run_packaged_health(
        runtime_root=tmp_path,
        data_dir=tmp_path / "data",
        controller=object(),
        study_core_info=lambda: {"available": True, "implementation": "rust", "version": "0.1.0"},
        media_available=lambda: True,
        media_version=lambda: "2026.08.01",
        youtube_support=lambda: {
            "yt_dlp": True, "ejs": True, "ejs_version": "0.8.0",
            "js_runtime": True, "js_runtime_version": "deno 2.9.5",
        },
    )

    assert [check["id"] for check in result["checks"]] == list(packaged_health.CHECK_ORDER)
    assert result["passed"] is True
    assert result["startup_ok"] is True
    assert [item["id"] for item in result["checklist"]] == [
        "windows_version", "ffmpeg_ffprobe", "whisper_runtime", "bundled_model", "data_directory",
    ]
    assert all(set(item) == {"id", "verdict", "detail"} for item in result["checklist"])


def test_source_sidecar_health_uses_checked_in_smoke_asset():
    sidecar = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
    assert 'self.repo_root / "app" / "packaging" / "assets" / "runtime-smoke.wav"' in sidecar
    assert "smoke_wav=smoke_wav" in sidecar


def test_optional_native_features_fail_release_but_allow_python_runtime_fallback(tmp_path, monkeypatch):
    from lecturepack.services import packaged_health

    monkeypatch.setattr(packaged_health, "data_directory_writable", lambda _path: {"writable": True, "detail": "ok"})
    monkeypatch.setattr(packaged_health, "_program_check", lambda check_id, *_args: _ok(check_id))
    monkeypatch.setattr(packaged_health, "_whisper_runtime_check", lambda *_args: _ok("whisper_runtime"))
    monkeypatch.setattr(packaged_health, "_whisper_smoke_check", lambda *_args: _ok("whisper_smoke"))
    monkeypatch.setattr(packaged_health, "_readable_file", lambda _path: (True, "readable"))

    result = packaged_health.run_packaged_health(
        runtime_root=tmp_path,
        data_dir=tmp_path / "data",
        controller=object(),
        study_core_info=lambda: {"available": False, "implementation": "python", "error": "OSError: missing DLL"},
        media_available=lambda: False,
        media_version=lambda: "",
        youtube_support=lambda: {"yt_dlp": False, "ejs": False, "js_runtime": False},
    )

    assert result["passed"] is False
    assert result["startup_ok"] is True
    # Losing the link importer degrades three optional checks but must never
    # stop LecturePack starting for local lecture files.
    assert {check["id"] for check in result["checks"] if not check["ok"]} == {
        "study_core", "yt_dlp", "yt_dlp_ejs", "js_runtime",
    }


def test_rust_native_load_errors_use_python_study_fallback(monkeypatch):
    from lecturepack.services import study_v2

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "lecturepack_study_core":
            raise OSError("dependent native DLL could not load")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    info = study_v2.study_core_info()
    assert info["available"] is False
    assert info["implementation"] == "python"
    assert "OSError" in info["error"]


def test_official_sidecar_build_fails_closed_for_rust_and_yt_dlp():
    spec = (ROOT / "electron-spike" / "sidecar.spec").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build_electron_release.py").read_text(encoding="utf-8")

    assert 'OFFICIAL_BUILD = os.environ.get("LECTUREPACK_OFFICIAL_BUILD") == "1"' in spec
    assert "Official LecturePack build requires lecturepack_study_core.pyd" in spec
    assert "Official LecturePack build requires importable yt-dlp" in spec
    assert "Official LecturePack build requires the app-local MSVC runtime" in spec
    assert 'runtime_datas.append((str(msvcp140), "."))' in spec
    assert 'environment["LECTUREPACK_OFFICIAL_BUILD"] = "1"' in build
    assert "validate_packaged_self_test(candidate)" in build


def test_support_diagnostics_reuse_authoritative_packaged_health():
    sidecar = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
    diagnostic = sidecar[sidecar.index("def _run_diagnostics"):sidecar.index("def _validate_vulkan")]
    assert 'diag["packaged_health"] = self._last_health or self._packaged_self_test' in diagnostic


def test_packaged_self_test_has_bounded_optional_feature_fault_injection():
    sidecar = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
    assert 'choices=("study_core", "yt_dlp", "js_runtime")' in sidecar
    assert 'fault = self.args.self_test_fault if self.args.self_test else ""' in sidecar
    assert 'elif fault == "yt_dlp":' in sidecar


def test_electron_startup_has_one_deadline_and_actionable_terminal_state():
    main = (ROOT / "electron-spike" / "production-main.js").read_text(encoding="utf-8")
    renderer = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "ui" / "index.html").read_text(encoding="utf-8")

    assert "const STARTUP_DEADLINE_MS = 28000;" in main
    assert "'startup_timeout'" in main
    assert "'sidecar_exit'" in main
    assert "if (command === 'retry_startup')" in main
    assert "lpBridge.on('startup_failure'" in renderer
    assert "lpBridge.on('exit'" in renderer
    for label in ("LecturePack couldn't start.", "Retry", "Copy diagnostics", "Open logs", "Technical details"):
        assert label in html


def test_release_diagnostics_and_log_retention_are_bounded_and_private_by_default():
    main = (ROOT / "electron-spike" / "production-main.js").read_text(encoding="utf-8")
    assert "const MAX_SESSION_LOGS = 10;" in main
    assert "oldLogs.slice(MAX_SESSION_LOGS - 1)" in main
    assert "lecturepack_version" in main
    assert "windows_version" in main
    assert "architecture" in main
    assert "startup_health" in main
    assert "recent_error" in main
    assert "transcript" not in main[main.index("function startupDiagnostics"):main.index("function clearStartupDeadline")]


def test_installer_is_per_user_without_admin_override():
    installer = (ROOT / "app" / "packaging" / "lecturepack.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in installer
    assert "PrivilegesRequiredOverridesAllowed" not in installer


def test_packaged_source_has_no_personal_developer_paths():
    source = (ROOT / "lecturepack" / "app.py").read_text(encoding="utf-8")
    package_script = (ROOT / "electron-spike" / "package-win.mjs").read_text(encoding="utf-8")
    assert "C:\\Users\\marsh" not in source
    assert "OneDrive" not in source
    assert "const engine =" not in package_script
    assert "const sidecar =" not in package_script
    assert "const license = path.join(repoRoot, 'LICENSE');" in package_script
    assert "extraResource: [uiDir, packagedSidecar, demoAssets, icon, license]" in package_script
    assert "const productionAsarFiles = new Set([" in package_script
    assert "return !productionAsarFiles.has(relative);" in package_script


def test_release_packaging_prunes_only_unreachable_locale_and_headless_qt_payloads():
    sidecar_packager = (ROOT / "electron-spike" / "package-sidecar.mjs").read_text(encoding="utf-8")
    electron_packager = (ROOT / "electron-spike" / "package-win.mjs").read_text(encoding="utf-8")

    assert "PySide6', 'opengl32sw.dll'" in sidecar_packager
    assert "PySide6', 'translations'" in sidecar_packager
    assert "Qt6Core.dll" not in sidecar_packager
    assert "QtCore.pyd" not in sidecar_packager
    assert "retainedLocales = new Set(['en-US.pak', 'en-GB.pak'])" in electron_packager
    assert "LICENSES.chromium.html" not in electron_packager


def test_stable_release_gate_covers_new_guided_handoff_and_normal_auto_export():
    gate = (ROOT / "scripts" / "stable_release_acceptance.py").read_text(encoding="utf-8")

    assert 'self.click("#btn-runtime-done")' in gate
    assert 'app.click("#glowing-demo-card")' in gate
    assert 'app.click("#btn-demo-run")' in gate
    assert "guided_demo_review_ready" in gate
    assert 'LP.state.screen === \'review\'' in gate
    assert ": null; }})()" not in gate
    assert 'app.request("import_paths", {"paths": [str(demo)]})' in gate
    assert '"auto_export": True' in gate
    assert '"Study AI readiness"' in gate
    assert "c.study_status==='ready'" in gate
    assert '"guided_demo_cleanup_stayed_final"' in gate
    assert "document.querySelector('#study-quick-root').innerText.includes('Quick Study')" in gate
    assert "document.getElementById('status-detail')" in gate
    assert "document.getElementById('proc-strip-meta')" not in gate
    assert '["taskkill.exe", "/PID", str(self.proc.pid), "/T", "/F"]' in gate
    assert "d.status==='running'" in gate
    assert "d.legacy_status==='downloading'" in gate


def test_paste_link_remains_visible_and_disabled_when_yt_dlp_is_unavailable():
    html = (ROOT / "app" / "ui" / "index.html").read_text(encoding="utf-8")
    renderer = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
    button = html[html.index('id="btn-paste-link"'):html.index("</button>", html.index('id="btn-paste-link"'))]
    assert "hidden" not in button
    assert "disabled" in button
    handler = renderer[renderer.index("lpBridge.on('media_link_state'"):renderer.index("lpBridge.on('media_probe'")]
    assert "btn.hidden = false" in handler
    assert "btn.disabled = !mediaLink.available" in handler
    assert "bundled yt-dlp runtime could not load" in handler


def test_clean_machine_validator_has_no_development_runtime_dependency():
    validator = (ROOT / "scripts" / "clean_machine_validation.ps1").read_text(encoding="utf-8")
    for field in (
        "windows_edition", "architecture", "python_present", "node_present", "rust_present",
        "vc_runtime_registered", "vc_runtime_result", "startup_health_result", "ffmpeg_result", "ffprobe_result",
        "whisper_smoke_result", "model_result", "rust_study_core_result", "yt_dlp_result",
        "real_job_result", "study_result", "export_result", "shutdown_result", "orphan_process_result",
    ):
        assert field in validator
    assert "python -m" not in validator.lower()
    assert "node.exe" in validator  # presence is recorded, never required to run the gate
    assert "git.exe" not in validator
    assert "$imported = Invoke-SidecarRequest 'import_video' @{ path = $installedMedia }" in validator
    assert "path = $installedMedia; bundled_demo = $true" not in validator
    assert "function Stop-AcceptanceSidecar" in validator
    assert "'/PID', [string]$sidecarProcess.Id, '/T', '/F'" in validator
    assert "Stop-AcceptanceSidecar" in validator
    assert "[void](Remove-AcceptanceTestInstall $acceptanceInstallDir)" in validator


def test_slide_image_io_supports_unicode_windows_paths(tmp_path):
    import numpy as np

    from lecturepack.infrastructure.cv_engine import read_image_file, write_image_file

    image_path = tmp_path / "profile Ω 漢" / "slide_1.png"
    image_path.parent.mkdir()
    expected = np.zeros((12, 16, 3), dtype=np.uint8)
    expected[:, :, 1] = 173

    write_image_file(image_path, expected)
    actual = read_image_file(image_path)

    assert image_path.stat().st_size > 0
    assert actual is not None
    assert np.array_equal(actual, expected)
