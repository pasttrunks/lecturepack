"""
v1.1 UI tests (Phase 2 + 3 + 11): unmistakable slide selection (real visual
state, not just model data), Ctrl/Shift multi-select behaviour, the dedicated
transcript workspace (full view, segments grid, copy formats, search sync,
editing/split/merge/undo), and shell navigation with state persistence.
"""
import json
import os

import pytest
from PySide6.QtCore import Qt, QPoint

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.ui import theme
from lecturepack.ui.main_window import MainWindow, PAGE_REVIEW, PAGE_TRANSCRIPT

RAW_JSON = {"result": {"language": "en", "transcription": [
    {"offsets": {"from": 0, "to": 4000}, "text": " Welcome to the lecture on Egypt."},
    {"offsets": {"from": 4000, "to": 9000}, "text": " Today we cover the Great Pyramid of Giza."},
    {"offsets": {"from": 9000, "to": 15000}, "text": " Khufu commissioned it around 2560 BC."},
    {"offsets": {"from": 15000, "to": 21000}, "text": " The Sphinx guards the plateau."},
    {"offsets": {"from": 21000, "to": 27000}, "text": " Thank you for listening today."},
]}}


def _make_job(tmp_path, n_slides=4):
    data_dir = str(tmp_path / "data")
    job = Job(data_dir, video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    job.source.update({"duration": 30.0, "width": 640, "height": 480})
    candidates = []
    os.makedirs(job.paths["candidates"], exist_ok=True)
    import numpy as np
    import cv2
    for i in range(n_slides):
        t = 1.0 + i * 7.0
        name = f"slide_{i}_{int(t * 1000)}.png"
        img = np.full((120, 160, 3), 40 * (i + 1), dtype=np.uint8)
        cv2.imwrite(os.path.join(job.paths["candidates"], name), img)
        candidates.append({
            "frame_number": int(t * 25), "timestamp_seconds": t,
            "timestamp_formatted": f"00:00:{int(t):02d}.000",
            "decision": "accepted" if i != 2 else "rejected",
            "decision_reason": "test", "image_filename": name,
            "detector_path": "major_change", "combined_score": 0.5,
            "rolling_baseline_score": 0.02, "component_scores": {},
            "stability_result": "", "changed_area_ratio": 0.1,
        })
    FileManager.write_json_atomic(os.path.join(job.paths["root"], "candidates.json"), candidates)
    FileManager.write_json_atomic(os.path.join(job.paths["transcript"], "raw.json"), RAW_JSON)
    from lecturepack.services import transcript_service as ts
    raw = ts.parse_raw_whisper_json(RAW_JSON)
    FileManager.write_json_atomic(os.path.join(job.paths["transcript"], "normalized.json"),
                                  ts.normalize_transcript(raw).to_dict())
    for s in ["Inspect", "Extract Audio", "Transcribe", "Detect Slides", "Align", "Review Ready"]:
        job.set_stage_status(s, "completed")
    return data_dir, job


@pytest.fixture()
def window(qtbot, tmp_path):
    data_dir, job = _make_job(tmp_path)
    config = ConfigManager(data_dir)
    win = MainWindow(config)
    qtbot.addWidget(win)
    win.current_job = job
    win.controller.set_job(job)
    win._load_review_data()
    win.stack.setCurrentIndex(PAGE_REVIEW)
    win.show()
    qtbot.waitExposed(win)
    return win


# --------------------------------------------------------------------------- #
# Phase 2: selection visuals
# --------------------------------------------------------------------------- #

def test_selection_visuals_pure_state():
    """The delegate's visual contract: >=2px accent outline, contrasting
    background, checkmark, and focus ring for selected tiles in BOTH themes."""
    for dark in (False, True):
        vis = theme.selection_visuals(True, True, "accepted", dark)
        assert vis["outline_width"] >= 2
        assert vis["outline_color"].name() == theme.ACCENT
        assert vis["checkmark_visible"] is True
        assert vis["focus_ring_visible"] is True
        # selected background contrasts with the unselected one
        unsel = theme.selection_visuals(False, False, "accepted", dark)
        assert vis["background"].name() != unsel["background"].name()
        assert unsel["checkmark_visible"] is False
        assert unsel["outline_width"] == 0
        # rejected tiles keep a distinct badge colour
        rej = theme.selection_visuals(False, False, "rejected", dark)
        assert rej["decision_badge_color"].name() == theme.DANGER


def test_selected_tile_pixels_show_accent_outline(window, qtbot):
    """Pixel-level check: render the slide grid and verify accent-coloured
    pixels appear only when an item is selected."""
    view = window.slides_view
    view.clearSelection()
    qtbot.wait(50)
    img_before = view.viewport().grab().toImage()
    view.item(0).setSelected(True)
    view.setFocus()
    qtbot.wait(50)
    img_after = view.viewport().grab().toImage()

    def count_accent(img):
        accent = theme.ACCENT.lstrip("#")
        ar, ag, ab = (int(accent[i:i + 2], 16) for i in (0, 2, 4))
        n = 0
        for y in range(0, img.height(), 3):
            for x in range(0, img.width(), 3):
                c = img.pixelColor(x, y)
                if abs(c.red() - ar) < 30 and abs(c.green() - ag) < 30 and abs(c.blue() - ab) < 40:
                    n += 1
        return n

    assert count_accent(img_after) > count_accent(img_before) + 10, \
        "selected tile must paint a clearly visible accent outline/badge"


def test_click_and_ctrl_click_and_shift_click(window, qtbot):
    view = window.slides_view
    view.clearSelection()

    def click_item(row, modifier=Qt.KeyboardModifier.NoModifier):
        rect = view.visualItemRect(view.item(row))
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, modifier,
                         rect.center())

    click_item(0)
    assert [view.row(i) for i in view.selectedItems()] == [0]
    assert window.selected_count_lbl.text() == "Selected: 1"

    click_item(2, Qt.KeyboardModifier.ControlModifier)  # toggle on
    assert sorted(view.row(i) for i in view.selectedItems()) == [0, 2]
    assert window.selected_count_lbl.text() == "Selected: 2"

    click_item(2, Qt.KeyboardModifier.ControlModifier)  # toggle off
    assert [view.row(i) for i in view.selectedItems()] == [0]

    click_item(1)                                       # fresh anchor at 1
    click_item(3, Qt.KeyboardModifier.ShiftModifier)    # range 1..3
    assert sorted(view.row(i) for i in view.selectedItems()) == [1, 2, 3]
    assert window.selected_count_lbl.text() == "Selected: 3"

    # Synthetic modifier-clicks leave Qt's stored keyboardModifiers() sticky
    # for the whole process; send one unmodified event to normalize state so
    # later tests' programmatic selection behaves normally.
    qtbot.keyClick(view, Qt.Key_Escape, Qt.KeyboardModifier.NoModifier)


def test_select_all_and_keyboard_decisions(window, qtbot):
    view = window.slides_view
    view.setFocus()
    view.clearSelection()
    view.item(1).setSelected(True)
    # Delete rejects but never physically deletes
    files_before = set(os.listdir(window.current_job.paths["candidates"]))
    window._on_delete_shortcut()
    qtbot.wait(50)
    cands = FileManager.read_json_safe(
        os.path.join(window.current_job.paths["root"], "candidates.json"), [])
    assert any(c["decision"] == "rejected" and c["timestamp_seconds"] == 8.0 for c in cands)
    files_after = set(os.listdir(window.current_job.paths["candidates"]))
    assert files_before == files_after, "reject must never delete image files"
    # R restores
    view.setFocus()
    window.slides_view.item(1).setSelected(True)
    window._on_r_shortcut()
    qtbot.wait(50)
    cands = FileManager.read_json_safe(
        os.path.join(window.current_job.paths["root"], "candidates.json"), [])
    assert all(c["decision"] == "accepted" or c["timestamp_seconds"] == 15.0 for c in cands)
    # Ctrl+Z undoes the restore
    window._on_undo_shortcut()
    qtbot.wait(50)
    cands = FileManager.read_json_safe(
        os.path.join(window.current_job.paths["root"], "candidates.json"), [])
    assert any(c["decision"] == "rejected" and c["timestamp_seconds"] == 8.0 for c in cands)


def test_selection_syncs_preview_and_transcript(window, qtbot):
    view = window.slides_view
    view.clearSelection()
    view.item(1).setSelected(True)  # slide at 8s
    qtbot.wait(80)
    assert "00:00:08" in window.review_page.slide_info_lbl.text()
    assert window.transcript_table.rowCount() > 0
    texts = [window.transcript_table.cellWidget(r, 1).toPlainText()
             for r in range(window.transcript_table.rowCount())]
    assert any("Khufu" in t or "Giza" in t or "Sphinx" in t for t in texts)


# --------------------------------------------------------------------------- #
# Phase 3: transcript workspace
# --------------------------------------------------------------------------- #

def test_transcript_page_full_and_segment_views(window, qtbot):
    window.stack.setCurrentIndex(PAGE_TRANSCRIPT)
    tp = window.transcript_page
    assert len(tp.segments) == 5
    html = tp.full_view.toHtml()
    assert "Great Pyramid" in html
    tp.tabs.setCurrentIndex(1)
    assert tp.seg_table.rowCount() == 5
    assert tp.seg_table.item(0, 6).text().startswith("Welcome")


def test_transcript_copy_formats(window, qtbot, monkeypatch):
    # The real OS clipboard is contended on CI/Windows; capture writes instead.
    captured = {}

    class FakeClipboard:
        def setText(self, text):
            captured["text"] = text

        def setPixmap(self, pm):
            pass

    import lecturepack.ui.pages.transcript_page as tp_mod
    monkeypatch.setattr(tp_mod.QGuiApplication, "clipboard",
                        staticmethod(lambda: FakeClipboard()))
    tp = window.transcript_page
    window.stack.setCurrentIndex(PAGE_TRANSCRIPT)
    for fmt, marker in [("plain text", "Welcome to the lecture"),
                        ("markdown", "- **["), ("json", '"text"'),
                        ("jsonl", '"id"'), ("csv", "start_sec"),
                        ("srt", " --> "), ("vtt", "WEBVTT")]:
        tp.copy_format_combo.setCurrentText(fmt)
        tp.copy_full_transcript()
        clip = captured.get("text", "")
        assert marker in clip, f"format {fmt} missing marker: {clip[:80]}"


def test_transcript_search_selects_and_syncs_slide(window, qtbot):
    tp = window.transcript_page
    window.stack.setCurrentIndex(PAGE_TRANSCRIPT)
    tp.tabs.setCurrentIndex(1)
    seeks = []
    tp.seek_requested.connect(lambda t: seeks.append(t))
    tp.search_edit.setText("Sphinx")
    tp.search_next()
    assert seeks and abs(seeks[0] - 15.0) < 0.5
    # shell sync: the review page selects the slide containing that time
    window._on_transcript_seek(seeks[0])
    sel = window.slides_view.selectedItems()
    assert sel and abs(sel[0].data(Qt.ItemDataRole.UserRole + 0)["timestamp_seconds"] - 15.0) < 1.5


def test_segment_edit_split_merge_undo_and_raw_immutable(window, qtbot):
    tp = window.transcript_page
    window.stack.setCurrentIndex(PAGE_TRANSCRIPT)
    tp.tabs.setCurrentIndex(1)
    raw_path = os.path.join(window.current_job.paths["transcript"], "raw.json")
    raw_before = open(raw_path, encoding="utf-8").read()

    # edit
    tp.seg_table.selectRow(0)
    qtbot.wait(30)
    assert tp._active_seg_id == tp.segments[0]["id"], \
        "row selection must activate the segment editor"
    tp.seg_editor.setPlainText("Welcome to the lecture on ancient Egypt.")
    qtbot.wait(30)
    assert tp.segments[0]["text"].endswith("ancient Egypt."), \
        "editor change must reach the in-memory working layer"
    tp.save()
    working = FileManager.read_json_safe(
        os.path.join(window.current_job.paths["transcript"], "working.json"), {})
    assert working["segments"][0]["text"].endswith("ancient Egypt.")
    assert working["segments"][0]["edited"] is True
    # legacy mirror for old consumers
    edited = FileManager.read_json_safe(
        os.path.join(window.current_job.paths["transcript"], "edited.json"), {})
    assert edited.get("1", "").endswith("ancient Egypt.")

    # split segment 2 at a cursor position
    tp.seg_table.selectRow(1)
    n_before = len(tp.segments)
    cursor = tp.seg_editor.textCursor()
    cursor.setPosition(len("Today we cover"))
    tp.seg_editor.setTextCursor(cursor)
    tp.split_active_segment()
    assert len(tp.segments) == n_before + 1

    # undo the split
    tp.undo()
    assert len(tp.segments) == n_before

    # merge segments 4+5
    ids = [tp.segments[3]["id"], tp.segments[4]["id"]]
    tp.segments = __import__("lecturepack.services.transcript_store",
                             fromlist=["merge_segments"]).merge_segments(tp.segments, ids)
    assert len(tp.segments) == n_before - 1
    merged = tp.segments[-1]
    assert "Sphinx" in merged["text"] and "Thank you" in merged["text"]
    tp.save()

    # exports pick the working layer up, chronologically
    from lecturepack.services import transcript_store as store
    segs = store.load_working(window.current_job.paths)
    starts = [s["start"] for s in segs]
    assert starts == sorted(starts)

    # RAW is byte-identical
    assert open(raw_path, encoding="utf-8").read() == raw_before


def test_old_job_without_working_layer_loads(window, tmp_path):
    """Backward compatibility: v1.0 jobs (edited.json only) load unchanged."""
    from lecturepack.services import transcript_store as store
    job = window.current_job
    wp = os.path.join(job.paths["transcript"], "working.json")
    if os.path.exists(wp):
        os.remove(wp)
    FileManager.write_json_atomic(
        os.path.join(job.paths["transcript"], "edited.json"), {"2": "Edited old style."})
    segs = store.load_working(job.paths)
    assert [s["id"] for s in segs] == [1, 2, 3, 4, 5]
    assert segs[1]["text"] == "Edited old style."
    assert segs[1]["edited"] is True


def test_shell_navigation_and_persistence(window, qtbot):
    window.navigate_to(PAGE_TRANSCRIPT)
    assert window.stack.currentIndex() == PAGE_TRANSCRIPT
    assert window.nav_buttons[PAGE_TRANSCRIPT].isChecked()
    assert not window.nav_buttons[PAGE_REVIEW].isChecked()
    window.review_page._set_mode("list")
    window._persist_ui_state()
    assert window._settings.value("slideListMode") == "list"
    assert int(window._settings.value("lastPage")) == PAGE_TRANSCRIPT
