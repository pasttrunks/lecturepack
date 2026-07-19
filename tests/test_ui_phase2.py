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


# --------------------------------------------------------------------- M3 #
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget  # noqa: E402

from lecturepack.ui.widgets.animated_stacked import (  # noqa: E402
    AnimatedStackedWidget)
from lecturepack.ui.widgets.title_bar import TitleBarWidget  # noqa: E402


def test_title_bar_buttons_emit_signals(app, qtbot):
    bar = TitleBarWidget(title="Test")
    qtbot.addWidget(bar)
    fired = []
    bar.minimize_clicked.connect(lambda: fired.append("min"))
    bar.toggle_maximize_clicked.connect(lambda: fired.append("max"))
    bar.close_clicked.connect(lambda: fired.append("close"))
    qtbot.mouseClick(bar.min_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(bar.max_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(bar.close_btn, Qt.MouseButton.LeftButton)
    assert fired == ["min", "max", "close"]


def test_title_bar_double_click_toggles_maximize(app, qtbot):
    bar = TitleBarWidget()
    qtbot.addWidget(bar)
    fired = []
    bar.toggle_maximize_clicked.connect(lambda: fired.append(True))
    qtbot.mouseDClick(bar, Qt.MouseButton.LeftButton)
    assert fired == [True]


def test_title_bar_maximize_glyph_switches(app, qtbot):
    bar = TitleBarWidget()
    qtbot.addWidget(bar)
    assert bar.max_btn.text() == "□"
    bar.set_maximized(True)
    assert bar.max_btn.text() == "▣"
    bar.set_maximized(False)
    assert bar.max_btn.text() == "□"


def test_title_bar_drag_moves_host_window(app, qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = TitleBarWidget(title="Drag")
    layout.addWidget(bar)
    layout.addStretch(1)
    host.resize(400, 200)
    host.move(300, 300)
    host.show()
    qtbot.wait(30)
    start = host.pos()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(60, 15))
    QTest.mouseMove(bar, QPoint(160, 115))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(160, 115))
    delta = host.pos() - start
    assert delta.x() == 100
    assert delta.y() == 100


def test_animated_stack_switches_and_cleans_up(app, qtbot):
    stack = AnimatedStackedWidget()
    qtbot.addWidget(stack)
    pages = [QLabel(f"page {i}") for i in range(3)]
    for page in pages:
        stack.addWidget(page)
    stack.resize(600, 400)
    stack.show()
    qtbot.wait(30)
    stack.setCurrentIndex(1)
    assert stack.currentIndex() == 1
    qtbot.wait(260)
    assert pages[1].graphicsEffect() is None


def test_animated_stack_rapid_navigation_guard(app, qtbot):
    stack = AnimatedStackedWidget()
    qtbot.addWidget(stack)
    for i in range(3):
        stack.addWidget(QLabel(f"page {i}"))
    stack.resize(600, 400)
    stack.show()
    qtbot.wait(30)
    stack.setCurrentIndex(2)
    stack.setCurrentIndex(0)  # interrupt the in-flight transition
    qtbot.wait(260)
    assert stack.currentIndex() == 0
    assert stack.currentWidget().graphicsEffect() is None


def test_animated_stack_same_index_is_noop(app, qtbot):
    stack = AnimatedStackedWidget()
    qtbot.addWidget(stack)
    stack.addWidget(QLabel("only"))
    stack.setCurrentIndex(0)
    assert stack.currentIndex() == 0


def test_main_window_frameless_shell(app, qtbot, tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.ui.main_window import MainWindow, PAGE_SETTINGS
    window = MainWindow(ConfigManager(str(tmp_path / "data")))
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert isinstance(window.title_bar, TitleBarWidget)
    assert isinstance(window.stack, AnimatedStackedWidget)
    window.navigate_to(PAGE_SETTINGS)
    assert window.stack.currentIndex() == PAGE_SETTINGS
    window.close()


# --------------------------------------------------------------------- M4 #
def _ready_study_job(tmp_path):
    from tests.test_ui_v11 import _make_job
    from lecturepack.constants import STAGE_TRANSCRIBE
    from lecturepack.services.export_service import ExportService
    _data_dir, job = _make_job(tmp_path)
    job.state["stages"][STAGE_TRANSCRIBE]["backend_used"] = "CPU"
    job.save()
    ExportService(job).align_and_export()
    return job


def _make_study_page(qtbot, tmp_path):
    from lecturepack.ui.pages.study_page import StudyPage
    job = _ready_study_job(tmp_path)
    page = StudyPage()
    qtbot.addWidget(page)
    page.load_job(job)
    return page


def test_study_workspace_loads_slides_and_transcript(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    assert not page.content.isHidden()
    assert page.empty_lbl.isHidden()
    assert page.slides_grid.count() > 0
    assert page.transcript_view.segment_count() > 0
    assert page.summary_lbl.text().strip() != ""
    page.slides_grid.shutdown()


def test_study_slide_click_seeks_transcript(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    row = 1 if page.slides_grid.count() > 1 else 0
    timestamp = float(page._candidates[row]["timestamp_seconds"])
    expected = find_segment_index(page._segments, timestamp)
    page.slides_grid.setCurrentRow(row)
    qtbot.wait(20)
    assert page.transcript_view.selected_index() == expected
    assert page.transcript_view.block_at(expected).is_selected()
    page.slides_grid.shutdown()


def test_study_transcript_scroll_selects_nearest_slide(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    index = min(5, page.transcript_view.segment_count() - 1)
    expected = find_slide_index(
        page._candidates, float(page._segments[index]["start"]))
    page._on_transcript_viewed(index)
    assert page.slides_grid.currentRow() == expected
    page.slides_grid.shutdown()


def test_study_block_click_selects_slide_without_navigating(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    navigations = []
    page.navigate_requested.connect(navigations.append)
    timestamp = float(page._segments[min(3, len(page._segments) - 1)]["start"])
    page.transcript_view.block_activated.emit(timestamp)
    assert page.slides_grid.currentRow() == find_slide_index(
        page._candidates, timestamp)
    assert navigations == []
    page.slides_grid.shutdown()


def test_study_viewed_index_ignored_during_programmatic_scroll(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    page._programmatic_scroll = True
    page._on_transcript_viewed(0)
    assert page.slides_grid.currentRow() == -1  # guard held: no re-entry
    page.slides_grid.shutdown()


def test_study_overview_card_collapses(app, qtbot, tmp_path):
    page = _make_study_page(qtbot, tmp_path)
    assert not page.overview_body.isHidden()
    page.overview_toggle.click()
    assert page.overview_body.isHidden()
    page.overview_toggle.click()
    assert not page.overview_body.isHidden()
    page.slides_grid.shutdown()


def test_study_workspace_empty_state_clears_panes(app, qtbot):
    from lecturepack.ui.pages.study_page import StudyPage
    page = StudyPage()
    qtbot.addWidget(page)
    page.load_job(None)
    assert page.content.isHidden()
    assert page.slides_grid.count() == 0
    assert page.transcript_view.segment_count() == 0


# --------------------------------------------------------------------- M5 #
def _make_process_page(qtbot, tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.ui.pages.process_page import ProcessPage
    page = ProcessPage(ConfigManager(str(tmp_path / "data")))
    qtbot.addWidget(page)
    return page


def _ancestors(widget):
    chain = []
    current = widget.parentWidget()
    while current is not None:
        chain.append(current)
        current = current.parentWidget()
    return chain


def test_process_page_dropzone_accepts_and_emits(app, qtbot, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    page = _make_process_page(qtbot, tmp_path)
    path = "C:/lectures/week3.mp4"
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])

    enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    page.dropzone.dragEnterEvent(enter)
    assert enter.isAccepted()
    assert page.dropzone.property("dropActive") == "true"

    chosen = []
    page.video_chosen.connect(chosen.append)
    drop = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    page.dropzone.dropEvent(drop)
    assert chosen == [path]
    assert page.video_path_edit.text() == path
    assert page.dropzone.property("dropActive") == "false"


def test_process_page_dropzone_ignores_non_video(app, qtbot, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDropEvent
    page = _make_process_page(qtbot, tmp_path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/notes/readme.txt")])
    chosen = []
    page.video_chosen.connect(chosen.append)
    drop = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    page.dropzone.dropEvent(drop)
    assert chosen == []
    assert page.video_path_edit.text() == ""


def test_process_page_advanced_drawer_animates_open_and_closed(app, qtbot, tmp_path):
    page = _make_process_page(qtbot, tmp_path)
    assert page._advanced_open is False
    assert page.advanced_drawer.maximumWidth() == 0
    page.set_advanced_open(True)
    qtbot.waitUntil(lambda: page.advanced_drawer.maximumWidth() == 380,
                    timeout=1500)
    assert page._advanced_open is True
    assert not page.advanced_drawer.isHidden()
    page.set_advanced_open(False)
    qtbot.waitUntil(lambda: page.advanced_drawer.maximumWidth() == 0,
                    timeout=1500)
    qtbot.wait(60)  # allow the finished->hide connection to fire
    assert page.advanced_drawer.isHidden()


def test_process_page_settings_widgets_live_in_drawer(app, qtbot, tmp_path):
    page = _make_process_page(qtbot, tmp_path)
    for widget in (page.transcription_mode_combo, page.profile_combo,
                   page.engine_combo, page.vad_chk, page.preset_combo,
                   page.crop_selector, page.diag_lbl):
        assert page.advanced_drawer in _ancestors(widget), widget
    # Primary controls stay on the main page.
    assert page.advanced_drawer not in _ancestors(page.product_mode_combo)
    assert page.advanced_drawer not in _ancestors(page.start_btn)
    assert page.advanced_drawer not in _ancestors(page.video_path_edit)


def test_process_page_live_transcript_is_block_stream(app, qtbot, tmp_path):
    page = _make_process_page(qtbot, tmp_path)
    assert isinstance(page.live_transcript, TranscriptStreamView)
    page.on_transcript_segment({"start_ms": 5000, "end_ms": 8000,
                                "text": "hello lecture"})
    page.on_transcript_segment({"start_ms": 9000, "text": "   "})  # ignored
    assert page.live_transcript.segment_count() == 1
    block = page.live_transcript.block_at(0)
    assert block.text_lbl.text() == "hello lecture"
    assert block.property("live") is True
    page.reset_progress()
    assert page.live_transcript.segment_count() == 0
