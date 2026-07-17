"""Native PySide6 reproduction for the stability-phase current-row defect.

Run from the repository root with either ``before`` or ``after``.  The script
shows the real MainWindow, builds an isolated throwaway job, retains row 0 in
the multi-selection, makes row 25 current, and records which slide is actually
previewed and scrolled into view.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QItemSelectionModel, QTimer
from PySide6.QtWidgets import QApplication

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.ui.main_window import MainWindow, PAGE_REVIEW


ROOT = Path(__file__).resolve().parent
LABEL = sys.argv[1] if len(sys.argv) > 1 else "before"


def build_job(data_dir: str) -> Job:
    job = Job(data_dir, video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    job.source.update({"duration": 300.0, "width": 640, "height": 480})
    candidates = []
    os.makedirs(job.paths["candidates"], exist_ok=True)
    for row in range(30):
        seconds = float(row * 10)
        name = f"slide_{row:02d}.png"
        image = np.full((120, 200, 3), (30 + row * 7) % 255, dtype=np.uint8)
        cv2.putText(image, f"Slide {row}", (18, 68), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(os.path.join(job.paths["candidates"], name), image)
        candidates.append({
            "frame_number": row * 250,
            "timestamp_seconds": seconds,
            "timestamp_formatted": f"00:{row // 6:02d}:{(row % 6) * 10:02d}.000",
            "decision": "accepted",
            "image_filename": name,
        })
    FileManager.write_json_atomic(
        os.path.join(job.paths["root"], "candidates.json"), candidates)
    FileManager.write_json_atomic(
        os.path.join(job.paths["transcript"], "raw.json"),
        {"transcription": [{"offsets": {"from": 0, "to": 300000},
                            "text": " Native stability reproduction."}]})
    job.save()
    return job


def capture() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    temp_root = tempfile.mkdtemp(prefix="lecturepack_stability_repro_")
    config = ConfigManager(temp_root)
    job = build_job(temp_root)
    window = MainWindow(config)
    window.resize(1500, 900)
    window.current_job = job
    window.controller.set_job(job)
    window._load_review_data()
    window.stack.setCurrentIndex(PAGE_REVIEW)
    window.show()

    def select_and_record() -> None:
        view = window.slides_view
        view.set_display_mode("list")
        view.clearSelection()
        view.setCurrentItem(view.item(0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
        view.setCurrentItem(view.item(25), QItemSelectionModel.SelectionFlag.Select)
        app.processEvents()
        current_rect = view.visualItemRect(view.currentItem())
        viewport_rect = view.viewport().rect()
        payload = {
            "label": LABEL,
            "selected_rows": sorted(view.row(item) for item in view.selectedItems()),
            "current_row": view.currentRow(),
            "preview_text": window.review_page.slide_info_lbl.text(),
            "scrollbar_value": view.verticalScrollBar().value(),
            "current_row_visible": viewport_rect.intersects(current_rect),
        }
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / f"selection_{LABEL}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        window.grab().save(str(ROOT / f"selection_{LABEL}.png"), "PNG")
        print(json.dumps(payload, indent=2), flush=True)
        window.close()
        app.quit()

    QTimer.singleShot(600, select_and_record)
    app.exec()


if __name__ == "__main__":
    capture()
