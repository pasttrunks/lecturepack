"""Generate deterministic native Qt screenshots for the v1.2 Study handoff."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import hashlib
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from lecturepack.constants import STAGE_TRANSCRIBE
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services import study_service
from lecturepack.services.export_service import ExportService
from lecturepack.ui.main_window import MainWindow, PAGE_REVIEW, PAGE_STUDY, PAGE_TRANSCRIPT
from tests.test_ui_v11 import _make_job


def capture(widget, path: Path):
    QApplication.processEvents()
    if not widget.grab().save(str(path), "PNG"):
        raise RuntimeError(f"Could not save {path}")


def signature(path):
    stat = os.stat(path)
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {"sha256": digest, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def main():
    evidence_dir = Path("docs/evidence/v1.2.0/study_workspace").resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="lecturepack-study-evidence-") as tmp:
        data_dir, job = _make_job(Path(tmp))
        job.state["stages"][STAGE_TRANSCRIBE]["backend_used"] = "CPU AVX2 (loaded)"
        job.save()
        ExportService(job).align_and_export()
        candidates_path = os.path.join(job.paths["root"], "candidates.json")
        with open(candidates_path, encoding="utf-8") as handle:
            candidates = json.load(handle)
        first = next(c for c in candidates if c.get("decision") == "accepted")
        protected_paths = [
            os.path.join(job.paths["root"], "source.json"),
            candidates_path,
            os.path.join(job.paths["transcript"], "raw.json"),
        ] + [os.path.join(job.paths["candidates"], c["image_filename"])
             for c in candidates]
        protected_before = {os.path.relpath(path, job.paths["root"]): signature(path)
                            for path in protected_paths}
        study_service.set_slide_study(
            job, first, bookmarked=True,
            note="Revisit the relationship between the pyramid and plateau.")
        first_section = study_service.load_sections(job)[0]
        study_service.set_section_bookmark(job, first_section, True)
        study_service.save_position(job, page="review", timestamp_seconds=first["timestamp_seconds"])
        ExportService(job).align_and_export()
        protected_after = {os.path.relpath(path, job.paths["root"]): signature(path)
                           for path in protected_paths}

        window = MainWindow(ConfigManager(data_dir))
        window.resize(1400, 900)
        window._load_job(job.job_id, job.manifest["source"]["original_path"])
        window.show()
        app.processEvents()

        window.navigate_to(PAGE_STUDY)
        capture(window, evidence_dir / "study-overview.png")

        window.navigate_to(PAGE_REVIEW)
        window.review_page.splitter.setSizes([420, 500, 430])
        window.review_page.slides_view.setCurrentRow(0)
        app.processEvents()
        capture(window, evidence_dir / "review-bookmark-note.png")

        window.navigate_to(PAGE_TRANSCRIPT)
        window.transcript_page.tabs.setCurrentIndex(2)
        window.transcript_page.sections_table.setCurrentCell(0, 0)
        app.processEvents()
        capture(window, evidence_dir / "section-bookmark-jump.png")
        window.close()

        restarted = Job(data_dir, job_id=job.job_id)
        restarted_study = study_service.load_study_data(restarted)
        export_names = ("study-pack.html", "study-pack.pdf", "study-data.json")
        results = {
            "completed_landing_page": "Study",
            "loaded_backend": study_service.build_overview(restarted)["backend"],
            "restart_persistence": {
                "bookmarked_slide_count": len(restarted_study["bookmarked_slides"]),
                "bookmarked_section_count": len(restarted_study["bookmarked_sections"]),
                "last_position": restarted_study["last_position"],
            },
            "exports": {
                name: signature(os.path.join(job.paths["exports"], name))
                for name in export_names
            },
            "protected_artifacts_before": protected_before,
            "protected_artifacts_after": protected_after,
            "protected_artifacts_identical": protected_before == protected_after,
            "screenshots": [
                "study-overview.png", "review-bookmark-note.png",
                "section-bookmark-jump.png",
            ],
        }
        with open(evidence_dir / "results.json", "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
