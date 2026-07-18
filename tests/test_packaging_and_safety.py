"""Packaged-path resolution and no-deletion safety guarantees."""
import os

import pytest

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager


def test_release_version_has_single_authority():
    """Runtime and release-tool consumers use the package version authority."""
    import build_release
    import lecturepack
    from lecturepack import constants

    assert lecturepack.__version__ == "1.2.0"
    assert constants.APP_VERSION == lecturepack.__version__
    assert build_release.VERSION == lecturepack.__version__

    project_root = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(project_root, "lecturepack", "constants.py"), encoding="utf-8") as f:
        constants_source = f.read()
    with open(os.path.join(project_root, "build_release.py"), encoding="utf-8") as f:
        release_source = f.read()
    assert 'APP_VERSION = "1.2.0"' not in constants_source
    assert 'VERSION = "1.2.0"' not in release_source


def test_new_job_manifest_uses_release_version(tmp_path):
    """A newly persisted job manifest records the canonical release version."""
    from lecturepack.models.job import Job

    job = Job(str(tmp_path / "data"), video_path=str(tmp_path / "lecture.mp4"))
    persisted_manifest = FileManager.read_json_safe(job.manifest_path, {})

    assert persisted_manifest["app_version"] == "1.2.0"


def test_bundled_binary_resolution_next_to_exe(tmp_path):
    """ConfigManager finds a binary next to the 'executable' and in bin/."""
    app = tmp_path / "app"
    (app / "bin").mkdir(parents=True)
    (app / "whisper-cli.exe").write_text("x")
    (app / "bin" / "ffmpeg.exe").write_text("x")

    cfg = ConfigManager(str(tmp_path / "data"))
    cfg.app_dir = str(app)  # simulate frozen app_dir
    assert cfg._find_bundled_binary("whisper-cli.exe") == str(app / "whisper-cli.exe")
    assert cfg._find_bundled_binary("ffmpeg.exe") == str(app / "bin" / "ffmpeg.exe")
    assert cfg._find_bundled_binary("missing.exe") == ""


def test_autodetect_whisper_finds_sibling_model(tmp_path):
    app = tmp_path / "app"
    (app / "models").mkdir(parents=True)
    (app / "whisper-cli.exe").write_text("x")
    (app / "models" / "ggml-base.en.bin").write_text("x")
    cfg = ConfigManager(str(tmp_path / "data"))
    cfg.app_dir = str(app)
    exe, model = cfg.autodetect_whisper()
    assert exe.endswith("whisper-cli.exe")
    assert model.endswith("ggml-base.en.bin")


def _make_job_with_candidate(tmp_path):
    import cv2
    import numpy as np
    from lecturepack.models.job import Job
    job = Job(str(tmp_path / "data"), video_path=str(tmp_path / "v.mp4"))
    open(str(tmp_path / "v.mp4"), "wb").close()
    img = np.zeros((60, 60, 3), dtype=np.uint8)
    fn = "slide_0_0.png"
    cv2.imwrite(os.path.join(job.paths["candidates"], fn), img)
    FileManager.write_json_atomic(os.path.join(job.paths["root"], "candidates.json"), [{
        "frame_number": 0, "timestamp_seconds": 0.0, "timestamp_formatted": "00:00:00.000",
        "decision": "accepted", "image_filename": fn}])
    td = job.paths["transcript"]; os.makedirs(td, exist_ok=True)
    FileManager.write_json_atomic(os.path.join(td, "raw.json"),
        {"result": {"transcription": [{"offsets": {"from": 0, "to": 5000}, "text": "hello world"}]}})
    return job, fn


def test_export_and_reexport_never_delete_job_or_candidates(tmp_path):
    from lecturepack.services.export_service import ExportService
    job, fn = _make_job_with_candidate(tmp_path)
    cand_path = os.path.join(job.paths["candidates"], fn)
    job_root = job.paths["root"]

    ExportService(job).align_and_export()
    assert os.path.exists(cand_path), "candidate image deleted by export"
    assert os.path.isdir(job_root)

    # Flip decision and re-export -- still must not delete anything physical.
    candidates = FileManager.read_json_safe(os.path.join(job_root, "candidates.json"), [])
    candidates[0]["decision"] = "rejected"
    FileManager.write_json_atomic(os.path.join(job_root, "candidates.json"), candidates)
    ExportService(job).align_and_export()
    assert os.path.exists(cand_path), "candidate image deleted on re-export"
    assert os.path.isdir(job_root)


def test_context_names_feed_whisper_prompt():
    """Approved names produce a sanitized whisper initial prompt."""
    from lecturepack.services.transcript_service import build_whisper_prompt
    prompt = build_whisper_prompt(course_title="Ancient Egypt",
                                  names=["Tutankhamun", "Abu Simbel"], glossary="pharaoh")
    assert "Tutankhamun" in prompt and "Abu Simbel" in prompt and "Ancient Egypt" in prompt
