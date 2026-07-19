"""Phase 2 "Premium Glassmorphic Dark" UI overhaul tests.

M1: theme layer (QSS file, palette, shadow helper).
"""
from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QFrame

from lecturepack.ui import theme


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    if existing is not None:
        yield existing
    else:
        application = QApplication([])
        yield application


# --------------------------------------------------------------------- M1 #
def test_dark_palette_uses_mocha_colors(app):
    theme.apply_theme(app, dark=True)
    palette = app.palette()
    assert palette.color(QPalette.Window).name() == "#1e1e2e"
    assert palette.color(QPalette.Base).name() == "#181825"
    assert palette.color(QPalette.Text).name() == "#cdd6f4"
    assert palette.color(QPalette.Highlight).name() == "#89b4fa"


def test_dark_qss_file_loaded_only_when_dark(app):
    theme.apply_theme(app, dark=True)
    assert "#1e1e2e" in app.styleSheet().lower()
    assert "#89b4fa" in app.styleSheet().lower()
    theme.apply_theme(app, dark=False)
    assert "#1e1e2e" not in app.styleSheet().lower()
    theme.apply_theme(app, dark=True)  # leave the app dark for other tests


def test_qss_uses_literal_hex_not_css_variables():
    qss = theme.load_qss("dark_theme.qss")
    assert qss.strip(), "dark_theme.qss must exist and be non-empty"
    assert "var(" not in qss
    assert "#1E1E2E" in qss
    assert "#89B4FA" in qss


def test_load_qss_missing_file_returns_empty_string():
    assert theme.load_qss("does_not_exist.qss") == ""


def test_selection_visuals_api_unchanged():
    # v1.1 contract relied on by test_ui_v11 and the slide delegate.
    vis = theme.selection_visuals(True, True, "accepted", True)
    assert vis["outline_color"].name() == theme.ACCENT
    assert vis["outline_width"] >= 2


def test_add_card_shadow_attaches_effect(app):
    frame = QFrame()
    effect = theme.add_card_shadow(frame)
    assert frame.graphicsEffect() is effect
    assert effect.blurRadius() == 24.0
    assert effect.yOffset() == 3.0
    assert effect.color().alpha() == 90


# --------------------------------------------------------------------- M2 #
from PySide6.QtCore import Qt  # noqa: E402

from lecturepack.ui.widgets.transcript_block import (  # noqa: E402
    TranscriptBlockWidget, TranscriptStreamView, find_segment_index,
    find_slide_index,
)


def _segments(n, step=5.0):
    return [{"start": i * step, "end": i * step + step,
             "text": f"segment {i}"} for i in range(n)]


def test_find_segment_index_floor_matching():
    segs = _segments(4)  # starts 0, 5, 10, 15
    assert find_segment_index(segs, 0) == 0
    assert find_segment_index(segs, 7.2) == 1
    assert find_segment_index(segs, -3) == 0
    assert find_segment_index(segs, 999) == 3
    assert find_segment_index([], 5) == -1


def test_find_slide_index_nearest_matching():
    slides = [{"timestamp_seconds": t} for t in (0.0, 10.0, 20.0)]
    assert find_slide_index(slides, 0) == 0
    assert find_slide_index(slides, 6) == 1
    assert find_slide_index(slides, 13) == 1
    assert find_slide_index(slides, 16) == 2
    assert find_slide_index(slides, 999) == 2
    assert find_slide_index([], 1) == -1


def test_block_displays_timestamp_text_and_activates(app, qtbot):
    block = TranscriptBlockWidget(75.0, "hello world")
    qtbot.addWidget(block)
    assert block.time_lbl.text() == "0:01:15"
    assert block.text_lbl.text() == "hello world"
    captured = []
    block.activated.connect(captured.append)
    qtbot.mouseClick(block, Qt.MouseButton.LeftButton)
    assert captured == [75.0]


def test_block_selected_state_toggles_dynamic_property(app, qtbot):
    block = TranscriptBlockWidget(0.0, "x")
    qtbot.addWidget(block)
    assert not block.is_selected()
    block.set_selected(True)
    assert block.is_selected()
    assert block.property("selected") == "true"
    block.set_selected(False)
    assert not block.is_selected()
    assert block.property("selected") == "false"


def test_stream_view_lazy_materialization(app, qtbot):
    view = TranscriptStreamView(animate_scroll=False)
    qtbot.addWidget(view)
    view.set_segments(_segments(250))
    assert view.segment_count() == 250
    assert view.materialized_count() == 120
    view.ensure_materialized(200)
    assert view.materialized_count() >= 201
    assert view.block_at(200) is not None
    assert view.block_at(250) is None


def test_stream_view_select_and_scroll(app, qtbot):
    view = TranscriptStreamView(animate_scroll=False)
    qtbot.addWidget(view)
    view.resize(400, 240)
    view.set_segments(_segments(60, 30.0))
    view.show()
    qtbot.wait(20)
    view.select_index(40)
    assert view.selected_index() == 40
    assert view.block_at(40).is_selected()
    view.scroll_to_index(40, smooth=False)
    qtbot.wait(20)
    assert view.verticalScrollBar().value() > 0
    assert abs(view.top_visible_index() - 40) <= 2


def test_stream_view_live_cap_trims_oldest(app, qtbot):
    view = TranscriptStreamView(live=True, max_blocks=5, animate_scroll=False)
    qtbot.addWidget(view)
    for i in range(8):
        view.append_segment(i * 5.0, i * 5.0 + 5, f"segment {i}")
    assert view.materialized_count() == 5
    assert view.segment_count() == 5
    assert view.block_at(0).text_lbl.text() == "segment 3"


def test_stream_view_emits_viewed_index_after_scroll_debounce(app, qtbot):
    view = TranscriptStreamView(animate_scroll=False)
    qtbot.addWidget(view)
    view.resize(400, 240)
    view.set_segments(_segments(120, 30.0))
    view.show()
    qtbot.wait(20)
    view.verticalScrollBar().setValue(0)
    with qtbot.waitSignal(view.viewed_index_changed, timeout=2000) as blocker:
        view.verticalScrollBar().setValue(300)
    assert blocker.args[0] >= 0


def test_stream_view_clear_resets(app, qtbot):
    view = TranscriptStreamView()
    qtbot.addWidget(view)
    view.set_segments(_segments(10))
    view.clear()
    assert view.segment_count() == 0
    assert view.materialized_count() == 0
