"""Focused contracts for the Beta 15 Electron/UI audit defects.

These checks stay at the renderer/host boundary.  They deliberately do not
exercise the Python sidecar or the processing engine, which are owned by the
parallel bridge workstream.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
APP = UI / "app.js"
HTML = UI / "index.html"
MAIN = ROOT / "electron-spike" / "production-main.js"
PRELOAD = ROOT / "electron-spike" / "production-preload.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_d01_zero_jobs_renders_all_first_run_surfaces() -> None:
    app = read(APP)
    html = read(HTML)
    production = read(MAIN)
    jobs = block(app, "function renderJobs()", "// renderPipeline is called")
    assert "setJobsEmpty(empty);" in jobs
    assert 'id="home-empty"' in html
    assert 'id="home-demo"' in html
    assert 'id="dropzone"' in html
    assert "demoHome.hidden = !(demoAdmissionAvailable && tourEligibilityAllowsOffer())" in app
    assert "#home-demo" not in production.split("const productionScope", 1)[1].split("</style>", 1)[0]


def test_d02_demo_uses_repaired_command_and_is_click_idempotent() -> None:
    app = read(APP)
    demo = block(app, "function runDemoForReal()", "function bindDemoScreen")
    assert "lpBridge.startDemoJob()" in demo
    assert "current.status === 'starting' || current.active" in demo
    assert "Could not start the demo lecture." in demo
    assert "guidedDemo.isCurrentAttempt(attempt)" in demo
    assert "card.disabled =" in block(app, "function renderDemoCard()", "function hideModelTooltip")


def test_d03_paste_link_restored_when_packaged_runtime_available() -> None:
    app = read(APP)
    html = read(HTML)
    main = read(MAIN)
    # Link importing stays visible and explains a packaged provider failure.
    assert not re.search(r'id="btn-paste-link"[^>]*\bhidden\b', html)
    assert re.search(r'id="btn-paste-link"[^>]*\bdisabled\b', html)
    assert "btn.hidden = false;" in app
    assert "btn.disabled = !mediaLink.available;" in app
    assert "lpBridge.call('media_link_support')" in app
    # The production scope must not hide the control unconditionally.
    scope = main.split("const productionScope", 1)[1].split("</style>", 1)[0]
    assert "#btn-paste-link" not in scope


def test_d04_production_window_has_no_electron_menu() -> None:
    main = read(MAIN)
    assert "Menu.setApplicationMenu(null);" in main
    assert "autoHideMenuBar: true" in main


def test_d05_version_comes_from_preload_metadata() -> None:
    app = read(APP)
    assert "getAppVersion()" in read(PRELOAD)
    assert "lecturepack-production:version" in read(MAIN)
    assert "loadAppVersion();" in app
    assert "version: '0.0.0'" not in app
    assert "version === '0.0.0'" in app


def test_d06_update_check_settles_unavailable_and_failure_paths() -> None:
    app = read(APP)
    click = block(app, "$('btn-check-updates').addEventListener", "// Smart Study setup")
    events = block(app, "lpBridge.on('update_state'", "lpBridge.on('whatsnew'")
    assert "Checking…" in click
    assert "Updates are not available in this build." in click
    assert "Update check failed:" in click
    assert "phase === 'unavailable'" in events


def test_d07_compute_has_a_ready_cpu_fallback() -> None:
    app = read(APP)
    html = read(HTML)
    assert "CPU · AVX2 ready" in html
    assert "function setComputeReadyFallback()" in app
    # F-36: this fallback used to fire at 1500ms and overwrite a still-
    # pending Vulkan check with a line that says nothing about Vulkan.
    # It is a last resort, so it must wait well past a real detection and
    # must not claim a check was made.
    assert "setTimeout(setComputeReadyFallback, 15000);" in app
    assert "Vulkan check did not answer" in app
    assert "Checking compute backend…" in block(app, "$('btn-validate-vulkan').addEventListener", "$('btn-cuda-pack-install')")


def test_d08_whisper_path_is_only_in_advanced_details() -> None:
    html = read(HTML)
    app = read(APP)
    details = block(html, 'id="setting-model-details"', "</details>")
    assert 'id="setting-model-name"' in html
    assert 'id="setting-model-path"' in details
    assert "function setWhisperModelPath(value)" in app
    assert "Whisper Base English model" in app


def test_d09_cuda_offer_requires_explicit_installation_capability() -> None:
    app = read(APP)
    cuda = block(app, "lpBridge.on('cuda_pack'", "lpBridge.on('ai_status'")
    assert "installation_available === true" in cuda
    assert "install_available === true" in cuda
    assert "can_install === true" in cuda
    assert "var show = installationAvailable && d.gpu_present" in cuda


def test_d10_endpoint_test_has_success_failure_and_unavailable_feedback() -> None:
    app = read(APP)
    html = read(HTML)
    click = block(app, "$('btn-test-endpoint').addEventListener", "// Compute engine")
    assert 'id="endpoint-test-status"' in html
    assert "Endpoint test succeeded." in click
    assert "Endpoint test failed:" in click
    assert "Endpoint testing is unavailable in this build." in click


def test_d11_smart_study_message_never_falls_back_to_blank() -> None:
    app = read(APP)
    html = read(HTML)
    render = block(app, "function renderSmartStudy(d)", "function ssInstall")
    assert "Smart Study is optional; Built-in Study is ready." in html
    assert "Built-in Study is ready." in render
    assert "Install the optional local AI engine" in render
    assert "Smart Study setup is unavailable in this build." in app


def test_d12_runtime_gate_never_leaves_hidden_default_gate_after_bootstrap() -> None:
    app = read(APP)
    gate = block(app, "var RuntimeSetupGate = (function ()", "/* Clears the design-time")
    assert "eventModel.bootstrap({ bootstrap_pending: true, validation_path: 'full' });" in gate
    assert "restoreHealthy: function ()" in block(app, "function RuntimeSetupGateModel()", "var RuntimeSetupGate")
    assert "runtime_health_state === 'SETUP_REQUIRED'" in gate
    assert "closeOverlay(); return;" in gate


def test_d13_zero_job_action_bar_is_hidden() -> None:
    app = read(APP)
    html = read(HTML)
    assert 'id="jobs-actionbar"' in html
    assert "actionBar.hidden = !!empty;" in app
    # Archive/Restore used to sit in this bar as permanently-disabled controls.
    # They had no handler and no backend command, so they only advertised two
    # dead buttons -- and their tooltips still said "Beta 15" in 2.0.1. The bar
    # now carries only controls that do something.
    assert 'id="btn-archive"' not in html and 'id="btn-restore"' not in html
    assert 'id="btn-select-mode"' in html


def test_d14_global_save_is_hidden_but_specific_save_remains() -> None:
    html = read(HTML)
    main = read(MAIN)
    assert re.search(r'id="btn-save"[^>]*\bhidden\b', html)
    assert "#btn-save" in main
    assert 'id="btn-save-corrections"' in html
    # The transcript copy control was split into the two explicit actions.
    assert 'id="btn-copy-text"' in html
    assert 'id="btn-copy-stamped"' in html


def test_d15_notification_is_an_electron_action_with_in_app_feedback() -> None:
    app = read(APP)
    main = read(MAIN)
    html = read(HTML)
    assert "new Notification" in main
    assert "command === 'test_notification'" in main
    assert "lpBridge.call('test_notification')" in app
    assert 'id="notification-test-status"' in html
    assert "Test notification sent." in app
    assert "Desktop notifications are unavailable in this build." in app


def test_d16_breadcrumb_uses_the_friendly_job_name() -> None:
    app = read(APP)
    active = block(app, "lpBridge.on('active_job'", "lpBridge.on('pipeline_changed'")
    chrome = block(app, "function renderJobChrome()", "/* The sidebar chip")
    assert "function friendlyJobName(value)" in app
    # The active job is followed through selectJob, which resolves the job
    # name from the list; setActiveJob still falls back to friendlyJobName so
    # a raw job id can never reach the breadcrumb.
    assert "selectJob(a.id, { silent: true })" in active
    assert "friendlyJobName(id)" in block(app, "function setActiveJob", "function ownsPayload")
    # F-01/F-08: the lecture segment has ONE writer, setCrumbJob, which also
    # hides the segment (and its separator) when no lecture is loaded so the
    # trail cannot render "Home > Home".
    assert "setCrumbJob(" in chrome
    assert "crumb-job" in block(app, "function setCrumbJob", "function renderJobChrome")
    assert "looksLikeJobId" in app


def test_d17_visible_processing_labels_are_friendly_and_logs_keep_raw_text() -> None:
    app = read(APP)
    helper = "function normalizedProcessingText(value)" + block(app, "function normalizedProcessingText(value)", "function looksLikeJobId")
    renderer = block(app, "function renderProcessingStatus()", "// Main slide preview")
    assert "friendlyProcessingLabel" in renderer
    assert "document.createTextNode(' ' + (entry.text || ''))" in block(app, "function renderPipelineLog", "function renderPipeline")
    node_program = helper + """
console.log(JSON.stringify([
  friendlyProcessingLabel('detector decode: piped'),
  friendlyProcessingLabel('whisper running'),
  friendlyProcessingLabel('export'),
  friendlyProcessingLabel('done')
]));
"""
    node = subprocess.run(
        ["node", "-e", node_program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(node.stdout) == [
        "Detecting slides",
        "Transcribing audio",
        "Building Study Pack",
        "Complete",
    ]
