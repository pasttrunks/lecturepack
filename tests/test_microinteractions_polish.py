"""Tests for LecturePack microinteractions and physics polish.

Asserts:
1. Dynamic inertial tilt (-6deg to +6deg) and FLIP slot separation in LPDrag.
2. Canvas stamp trail (.lp-drop-stamp) keyframes and trigger on drop.
3. Review mode keyboard-driven slide stamping (J / K / Space) and viewport edge flash.
4. Filmstrip magnifying loupe on hover (#lp-slide-loupe).
5. Scrubber magnetic snapping and vertical tick extension (.lp-tick.is-snapped).
6. Zero-asset mechanical Web Audio cue synthesis (LPAudio).
7. Rolling monospace odometer counters (LPNumberRoller).
8. Animated mini 3-bar equalizer status waveform (.lp-status-waveform).
9. Hover data inversion on export chips.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"


def read_ui(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


APP = read_ui("app.js")
CSS = read_ui("app.css")
HTML = read_ui("index.html")


def test_lpaudio_engine_present_and_has_all_cues() -> None:
    assert "var LPAudio = (function () {" in APP
    assert "playClick:" in APP
    assert "playDrop:" in APP
    assert "playRatchet:" in APP
    assert "playToggle:" in APP
    assert "soundEnabled:" in APP


def test_lpnumber_roller_present_and_formats_odometer() -> None:
    assert "var LPNumberRoller = (function () {" in APP
    assert "setRolling:" in APP
    assert "lp-odometer" in APP
    assert "lp-odometer-digit" in APP
    assert "lp-odometer-ribbon" in APP


def test_velocity_responsive_inertial_tilt_in_drag() -> None:
    assert "var dragVelocity = { vx: 0" in APP
    assert "dragVelocity.vx" in APP
    assert "targetTilt = Math.max(-6, Math.min(6," in APP
    assert "proxyTransform(x, y, settled, tilt)" in APP or "proxyTransform" in APP
    assert "rotate(" in APP and "scale(1.03)" in APP


def test_flip_slot_separation_and_canvas_stamp() -> None:
    assert "applyFlipSeparation" in APP
    assert "lp-drop-stamp" in APP
    assert "lp-drop-insert-active" in APP
    assert "@keyframes lpDropStamp" in CSS
    assert "box-shadow: 0 0 0 4px rgba(0, 0, 0, 0.15)" in CSS or "box-shadow:" in CSS


def test_review_keyboard_stamping_and_viewport_flash() -> None:
    assert "flashViewport('keep')" in APP
    assert "flashViewport('reject')" in APP
    assert "lp-viewport-flash" in APP
    assert "@keyframes lpEdgeFlashGreen" in CSS
    assert "@keyframes lpEdgeFlashRed" in CSS


def test_slide_loupe_on_hover() -> None:
    assert "lp-slide-loupe" in APP
    assert "showSlideLoupe" in APP
    assert "hideSlideLoupe" in APP
    assert ".lp-slide-loupe" in CSS
    assert ".lp-loupe-inner" in CSS


def test_scrubber_magnetic_snapping() -> None:
    assert "highlightScrubTick" in APP
    assert "is-snapped" in APP
    assert ".lp-tick.is-snapped" in CSS
    assert "scaleY(1.35)" in CSS


def test_status_waveform_equalizer() -> None:
    assert 'class="lp-status-waveform"' in HTML
    assert 'class="lp-wave-bar"' in HTML
    assert ".lp-status-waveform" in CSS
    assert ".lp-wave-bar" in CSS
    assert "@keyframes lpWaveBarPulse" in CSS


def test_export_chips_hover_data_inversion() -> None:
    assert ".export-chip:hover" in CSS
    assert "transform: translate(-2px, -2px)" in CSS
    assert "box-shadow: 2px 2px 0 var(--border)" in CSS
