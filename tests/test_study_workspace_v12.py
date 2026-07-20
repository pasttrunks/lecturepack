"""Focused acceptance tests for the v1.2 Study workspace phase."""
import hashlib
import json
import os

from PySide6.QtCore import Qt

from lecturepack.constants import STAGE_TRANSCRIBE
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services.export_service import ExportService
from lecturepack.services import study_service
from lecturepack.ui.main_window import MainWindow, PAGE_REVIEW, PAGE_STUDY
from lecturepack.ui.pages.review_page import ReviewPage
from lecturepack.ui.pages.study_page import StudyPage
from lecturepack.ui.pages.transcript_page import TranscriptPage
from tests.test_ui_v11 import _make_job


def _ready_job(tmp_path):
    data_dir, job = _make_job(tmp_path)
    job.state["stages"][STAGE_TRANSCRIBE]["backend_used"] = "CUDA (loaded)"
    job.save()
    ExportService(job).align_and_export()
    return data_dir, job


def _signature(path):
    stat = os.stat(path)
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return digest, stat.st_size, stat.st_mtime_ns


def test_deterministic_overview_uses_loaded_backend_and_old_job_empty_state(tmp_path):
    _, job = _ready_job(tmp_path)
    overview1 = study_service.build_overview(job)
    overview2 = study_service.build_overview(job)

    assert overview1["backend"] == "CUDA (loaded)"
    assert overview1["summary_source"] == "deterministic transcript extract"
    assert overview1["summary"] == overview2["summary"]
    assert overview1["key_terms"] == overview2["key_terms"]
    assert overview1["sections"]
    assert overview1["bookmarked_slides"] == {}
    assert not os.path.exists(study_service.study_path(job)), \
        "opening an old job must not create user data until the user changes it"


def test_slide_bookmark_note_and_resume_survive_restart(qtbot, tmp_path):
    data_dir, job = _ready_job(tmp_path)
    page = ReviewPage(ConfigManager(data_dir))
    qtbot.addWidget(page)
    page.set_job(job)
    page.load_review_data()
    page.slides_view.setCurrentRow(0)
    qtbot.wait(20)
    page.slide_bookmark_btn.click()
    page.slide_note_edit.setText("Compare this diagram with the final example.")
    page.slide_note_edit.editingFinished.emit()

    restarted = Job(data_dir, job_id=job.job_id)
    entry = study_service.get_slide_entry(
        restarted, page.slides_view.item(0).data(Qt.ItemDataRole.UserRole))
    assert entry["bookmarked"] is True
    assert entry["note"] == "Compare this diagram with the final example."
    assert study_service.load_study_data(restarted)["last_position"]["page"] == "review"

    second_page = ReviewPage(ConfigManager(data_dir))
    qtbot.addWidget(second_page)
    second_page.set_job(restarted)
    second_page.load_review_data()
    second_page.slides_view.setCurrentRow(0)
    qtbot.wait(20)
    assert second_page.slide_bookmark_btn.isChecked()
    assert second_page.slide_note_edit.text().startswith("Compare this diagram")


def test_section_bookmark_and_jump_are_persistent(qtbot, tmp_path):
    data_dir, job = _ready_job(tmp_path)
    page = TranscriptPage(ConfigManager(data_dir))
    qtbot.addWidget(page)
    page.load_job(job)
    assert page.sections_table.rowCount() > 0
    page.sections_table.setCurrentCell(0, 0)
    page.toggle_section_bookmark()

    jumps = []
    page.seek_requested.connect(jumps.append)
    page.jump_to_current_section()
    assert jumps == [page._sections[0]["start"]]

    restarted = Job(data_dir, job_id=job.job_id)
    saved = study_service.load_study_data(restarted)
    assert study_service.section_key(page._sections[0]) in saved["bookmarked_sections"]
    assert saved["last_position"]["page"] == "review"


def test_completed_job_lands_on_study_and_quick_navigation_works(qtbot, tmp_path):
    data_dir, job = _ready_job(tmp_path)
    window = MainWindow(ConfigManager(data_dir))
    qtbot.addWidget(window)
    window._load_job(job.job_id, job.manifest["source"]["original_path"])
    assert window.stack.currentIndex() == PAGE_STUDY
    assert window.nav_buttons[PAGE_STUDY].isChecked()
    assert "Loaded backend: CUDA (loaded)" in window.study_page.meta_lbl.text()

    window.study_page.navigate_requested.emit("review")
    assert window.stack.currentIndex() == PAGE_REVIEW
    study_service.save_position(job, page="review", timestamp_seconds=15.0)
    window.study_page.refresh()
    window.study_page.resume_btn.click()
    assert window.stack.currentIndex() == PAGE_REVIEW
    assert window.review_page.slides_view.currentRow() >= 0


def test_study_page_empty_state(qtbot, tmp_path):
    page = StudyPage(ConfigManager(str(tmp_path / "data")))
    qtbot.addWidget(page)
    page.load_job(None)
    assert page.empty_lbl.isVisible() is False or page.empty_lbl.text().startswith("No completed")
    assert page.content.isHidden()


def test_study_exports_include_user_data_without_mutating_sources(qtbot, tmp_path):
    _, job = _ready_job(tmp_path)
    candidates_path = os.path.join(job.paths["root"], "candidates.json")
    raw_path = os.path.join(job.paths["transcript"], "raw.json")
    image_path = next(
        os.path.join(job.paths["candidates"], name)
        for name in os.listdir(job.paths["candidates"]) if name.endswith(".png"))
    before = {path: _signature(path) for path in (candidates_path, raw_path, image_path)}

    candidate = json.load(open(candidates_path, encoding="utf-8"))[0]
    study_service.set_slide_study(
        job, candidate, bookmarked=True,
        note="User note <script>alert('never execute')</script>")
    ExportService(job).align_and_export()

    exports = job.paths["exports"]
    for name in ("study-pack.html", "study-pack.pdf", "study-data.json"):
        path = os.path.join(exports, name)
        assert os.path.exists(path) and os.path.getsize(path) > 20
    with open(os.path.join(exports, "study-data.json"), encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["user_authored"]["bookmarked_slides"]
    with open(os.path.join(exports, "study-pack.html"), encoding="utf-8") as handle:
        html_text = handle.read()
    assert "Your study bookmarks and notes" in html_text
    assert "&lt;script&gt;" in html_text
    assert "<script>alert" not in html_text
    assert open(os.path.join(exports, "study-pack.pdf"), "rb").read(4) == b"%PDF"
    assert {path: _signature(path) for path in before} == before


def test_study_copy_full_transcript_works(qtbot, tmp_path):
    from PySide6.QtGui import QGuiApplication
    data_dir, job = _ready_job(tmp_path)
    page = TranscriptPage(ConfigManager(data_dir))
    qtbot.addWidget(page)
    page.load_job(job)

    clipboard = QGuiApplication.clipboard()
    clipboard.clear()
    page.copy_format_combo.setCurrentText("plain text")
    page.timestamps_chk.setChecked(False)
    page.copy_full_transcript()
    # Since mock job has segments like "Welcome to the lecture on Egypt"
    txt = clipboard.text()
    assert txt.strip() != ""
    assert "pyramid" in txt.lower()


def test_timestamp_links_navigate_correctly(qtbot, tmp_path):
    data_dir, job = _ready_job(tmp_path)
    page = StudyPage(ConfigManager(data_dir))
    qtbot.addWidget(page)
    page.load_job(job)

    navs = []
    seeks = []
    page.navigate_requested.connect(navs.append)
    page.seek_requested.connect(seeks.append)

    assert page.topics_list.count() > 0
    item = page.topics_list.item(0)
    page.topics_list.itemActivated.emit(item)
    assert navs == ["transcript"]
    assert len(seeks) == 1
    assert seeks[0] == item.data(Qt.ItemDataRole.UserRole)


def test_keyboard_navigation_on_study_page(qtbot, tmp_path):
    data_dir, job = _ready_job(tmp_path)
    page = StudyPage(ConfigManager(data_dir))
    qtbot.addWidget(page)
    page.load_job(job)

    page.topics_list.setFocus()
    page.topics_list.setCurrentRow(0)

    navs = []
    page.navigate_requested.connect(navs.append)
    qtbot.keyClick(page.topics_list, Qt.Key.Key_Return)
    assert "transcript" in navs
