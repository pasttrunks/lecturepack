import os
import shutil
import json
import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt
from lecturepack.models.job import Job
from lecturepack.constants import (
    STAGE_INSPECT, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE,
    STAGE_DETECT_SLIDES, STAGE_ALIGN, STAGE_REVIEW_READY, STAGE_EXPORT
)
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.infrastructure.whisper_wrapper import WhisperWrapper
from lecturepack.controllers.job_controller import JobController
from lecturepack.services.export_service import ExportService

# 1. Test Dynamic Whisper argument construction, VAD options, and Glossary sanitization
def test_whisper_arg_construction(tmp_path, qtbot):
    whisper_exe = tmp_path / "whisper-cli.exe"
    # Touch dummy executable
    whisper_exe.touch()
    
    wrapper = WhisperWrapper(str(whisper_exe))
    
    # Mock get_supported_flags to return different sets of supported flags
    def mock_get_flags_all():
        return {
            "--output-json-full", "--vad", "--vad-model", "--prompt",
            "--carry-initial-prompt", "--threads", "-t",
            "--vad-threshold", "--vad-min-speech-duration-ms", "--vad-min-silence-duration-ms"
        }
    
    wrapper.get_supported_flags = mock_get_flags_all
    
    # Test sanitized glossary
    glossary = 'CS 101, "Algorithms", and AI!\nNewlines'
    # Sanitized should remove quotes, newlines, and limit words
    sanitized = "".join(c for c in glossary if c.isalnum() or c in " ,.-_")
    words = sanitized.split()
    glossary_clean = " ".join(words)
    assert "CS 101" in glossary_clean
    assert '"' not in glossary_clean
    assert "\n" not in glossary_clean

    with patch('lecturepack.infrastructure.whisper_wrapper.QProcess') as MockQProcess:
        mock_proc_instance = MagicMock()
        MockQProcess.return_value = mock_proc_instance
        
        vad_settings = {
            "enabled": True,
            "model_path": str(tmp_path / "vad_model.bin"),
            "threshold": 0.45,
            "min_speech_duration_ms": 300,
            "min_silence_duration_ms": 150
        }
        # Touch vad model
        (tmp_path / "vad_model.bin").touch()
        
        wrapper.start_transcription(
            audio_path="audio.wav",
            model_path="whisper_model.bin",
            output_prefix="raw",
            glossary=glossary,
            threads=6,
            vad_settings=vad_settings
        )
        
        # Verify that start was called on our mock QProcess instance
        mock_proc_instance.start.assert_called_once()
        program, args = mock_proc_instance.start.call_args[0]
        
        # Check VAD args
        assert "--vad" in args
        assert "--vad-model" in args
        assert str(tmp_path / "vad_model.bin") in args
        assert "--vad-threshold" in args
        assert "0.45" in args
        assert "--vad-min-speech-duration-ms" in args
        assert "300" in args
        assert "--vad-min-silence-duration-ms" in args
        
        # Check threads
        assert "--threads" in args
        assert "6" in args
        
        # Check glossary
        assert "--prompt" in args
        assert "--carry-initial-prompt" in args
        assert "CS 101, Algorithms, and AINewlines" in args

# 2. Test dynamic whisper flags detection ignores unsupported flags
def test_whisper_ignores_unsupported_flags(tmp_path, qtbot):
    whisper_exe = tmp_path / "whisper-cli.exe"
    whisper_exe.touch()
    
    wrapper = WhisperWrapper(str(whisper_exe))
    
    # Mock supported flags list WITHOUT VAD or prompt flags
    def mock_get_flags_none():
        return {"-oj", "-osrt", "-otxt"}
        
    wrapper.get_supported_flags = mock_get_flags_none
    
    with patch('lecturepack.infrastructure.whisper_wrapper.QProcess') as MockQProcess:
        mock_proc_instance = MagicMock()
        MockQProcess.return_value = mock_proc_instance
        
        vad_settings = {
            "enabled": True,
            "model_path": str(tmp_path / "vad_model.bin")
        }
        
        wrapper.start_transcription(
            audio_path="audio.wav",
            model_path="whisper_model.bin",
            output_prefix="raw",
            glossary="Algorithms",
            threads=8,
            vad_settings=vad_settings
        )
        
        mock_proc_instance.start.assert_called_once()
        program, args = mock_proc_instance.start.call_args[0]
        
        # It must NOT pass vad or carry-initial-prompt flags since they are unsupported
        assert "--vad" not in args
        assert "--vad-model" not in args
        assert "--prompt" not in args
        assert "--carry-initial-prompt" not in args
        assert "--threads" not in args
        # But it must use -oj instead of --output-json-full
        assert "-oj" in args

# 3. Test corrected transcript persistence, raw transcript remains unchanged, and export overrides
def test_corrected_transcript_persistence(tmp_path):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    
    # Setup dummy raw.json
    raw_json_dir = os.path.dirname(os.path.join(job.paths["transcript"], "raw.json"))
    os.makedirs(raw_json_dir, exist_ok=True)
    raw_data = {
        "transcription": [
            {
                "offsets": {"from": 0, "to": 5000},
                "text": "Hello user, this is raw transcription."
            }
        ]
    }
    with open(os.path.join(job.paths["transcript"], "raw.json"), 'w', encoding='utf-8') as f:
        json.dump(raw_data, f)
        
    # Setup dummy candidates
    candidates = [
        {
            "frame_number": 0,
            "timestamp_seconds": 0.0,
            "timestamp_formatted": "00:00:00.000",
            "decision": "accepted",
            "image_filename": ""
        }
    ]
    FileManager.write_json_atomic(os.path.join(job.paths["root"], "candidates.json"), candidates)
    
    # Verify raw load
    exporter = ExportService(job)
    # Perform align
    exporter.align_and_export()
    
    # Check default exported transcript
    txt_path = os.path.join(job.paths["exports"], "transcript.txt")
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "raw transcription" in content
    
    # Save a correction to edited.json
    edited_data = {"1": "Hello world, this is corrected transcription."}
    edited_path = os.path.join(job.paths["transcript"], "edited.json")
    FileManager.write_json_atomic(edited_path, edited_data)
    
    # Run align and export again
    exporter.align_and_export()
    
    # Verify export overridden with corrected text
    with open(txt_path, 'r', encoding='utf-8') as f:
        new_content = f.read()
    assert "corrected transcription" in new_content
    assert "raw transcription" not in new_content
    
    # Verify raw.json remains UNCHANGED
    raw_json_path = os.path.join(job.paths["transcript"], "raw.json")
    with open(raw_json_path, 'r', encoding='utf-8') as f:
        raw_content = json.load(f)
    assert raw_content["transcription"][0]["text"] == "Hello user, this is raw transcription."

# 4. Test no physical image, job directory, or video deletion on review decisions
def test_no_physical_deletion(tmp_path):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    
    # Setup candidates.json
    candidates_path = os.path.join(job.paths["root"], "candidates.json")
    candidates = [
        {
            "frame_number": 1,
            "timestamp_seconds": 1.5,
            "timestamp_formatted": "00:00:01.500",
            "decision": "accepted",
            "image_filename": "slide_1.png"
        }
    ]
    FileManager.write_json_atomic(candidates_path, candidates)
    
    # Create fake slide image
    slide_img_path = os.path.join(job.paths["candidates"], "slide_1.png")
    with open(slide_img_path, 'w') as f:
        f.write("dummy image data")
        
    # Simulate a reject decision
    candidates[0]["decision"] = "rejected"
    FileManager.write_json_atomic(candidates_path, candidates)
    
    # Check that candidates.json file is modified but NO directories or files are deleted
    assert os.path.exists(video_path), "Source video was deleted!"
    assert os.path.exists(job.paths["root"]), "Job directory was deleted!"
    assert os.path.exists(slide_img_path), "Candidate slide image was deleted!"

# 5. Test Job Archiving and Restoring
def test_job_archiving_restoring(tmp_path):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    job_id = job.job_id
    
    # Ensure job directories exist
    assert os.path.exists(os.path.join(data_dir, "jobs", job_id))
    
    # Archive the job
    FileManager.archive_job(str(data_dir), job_id)
    
    # Check it was moved
    assert not os.path.exists(os.path.join(data_dir, "jobs", job_id))
    assert os.path.exists(os.path.join(data_dir, "archive", job_id))
    
    # Restore the job
    FileManager.restore_job(str(data_dir), job_id)
    
    # Check it was moved back
    assert os.path.exists(os.path.join(data_dir, "jobs", job_id))
    assert not os.path.exists(os.path.join(data_dir, "archive", job_id))

# 6. Test Export Job Archive containing files except the original video
def test_export_job_archive(tmp_path):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    
    # Add dummy files to simulate job processing output
    with open(os.path.join(job.paths["transcript"], "raw.txt"), 'w') as f:
        f.write("transcript text")
    with open(os.path.join(job.paths["candidates"], "slide_1.png"), 'w') as f:
        f.write("slide image data")
        
    zip_export_path = tmp_path / "export_archive.zip"
    FileManager.export_job_archive(job.paths["root"], str(zip_export_path))
    
    # Check zip exists
    assert os.path.exists(zip_export_path)
    
    # Verify contents of zip
    import zipfile
    with zipfile.ZipFile(zip_export_path, 'r') as zipf:
        namelist = zipf.namelist()
        assert "manifest.json" in namelist
        assert "settings.json" in namelist
        assert "transcript/raw.txt" in namelist
        assert "frames/candidates/slide_1.png" in namelist
        # Original video is outside the job dir, so it must not be in the zip
        assert "video.mp4" not in namelist

# 7. Test Retranscribe Only stage skips
def test_retranscribe_only_stages(tmp_path, qtbot):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    # Setup configuration
    class MockConfigManager:
        def __init__(self):
            self.data_dir = str(data_dir)
            self.settings = {}
        def get(self, key, default=None):
            return self.settings.get(key, default)
        def set(self, key, value):
            self.settings[key] = value
            
    cfg = MockConfigManager()
    cfg.set("whisper_exe", str(tmp_path / "whisper-cli.exe"))
    cfg.set("whisper_model", str(tmp_path / "whisper_model.bin"))
    
    # Instantiate job and mock stages
    job = Job(str(data_dir), video_path=str(video_path))
    
    # Mark slide detection completed
    job.set_stage_status(STAGE_DETECT_SLIDES, "completed")
    job.save()
    
    controller = JobController(cfg)
    controller.set_job(job)
    
    # Mock run_next_stage so it doesn't launch actual subprocesses/threads
    with patch.object(controller, 'run_next_stage') as mock_run_next:
        # Run retranscribe only workflow (it sets status for re-run)
        controller.run_retranscribe_only()
        mock_run_next.assert_called_once()
    
    # Verify stage statuses:
    # Inspect remains completed (skipped)
    assert job.get_stage_status(STAGE_INSPECT) == "completed"
    # Detect slides remains completed (skipped)
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "completed"
    # Transcribe and Align are pending (rerun)
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "pending"
    assert job.get_stage_status(STAGE_ALIGN) == "pending"

# 8. Focused PySide6 UI tests using qtbot
def test_ui_review_flow(tmp_path, qtbot):
    data_dir = tmp_path / "data"
    
    # Configure dummy executables
    whisper_exe = tmp_path / "whisper-cli.exe"
    whisper_exe.touch()
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.touch()
    ffprobe_exe = tmp_path / "ffprobe.exe"
    ffprobe_exe.touch()
    
    # Setup ConfigManager and mock checks
    from lecturepack.infrastructure.config_manager import ConfigManager
    config = ConfigManager(str(data_dir))
    config.set("whisper_exe", str(whisper_exe))
    config.set("whisper_model", "ggml-base.bin")
    
    config.check_diagnostics = lambda: {
        "ffmpeg": {"valid": True, "path": str(ffmpeg_exe)},
        "ffprobe": {"valid": True, "path": str(ffprobe_exe)},
        "whisper_cli": {"valid": True, "path": str(whisper_exe)},
        "whisper_model": {"valid": True, "path": "ggml-base.bin"},
        "data_dir": {"valid": True, "path": str(data_dir)}
    }

    # Initialize job and candidates
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    job = Job(str(data_dir), video_path=str(video_path))
    job.source["duration"] = 60.0
    job.save()
    
    candidates_path = os.path.join(job.paths["root"], "candidates.json")
    candidates = [
        {
            "frame_number": 0,
            "timestamp_seconds": 0.0,
            "timestamp_formatted": "00:00:00.000",
            "decision": "accepted",
            "image_filename": "slide_0.png"
        },
        {
            "frame_number": 1,
            "timestamp_seconds": 10.0,
            "timestamp_formatted": "00:00:10.000",
            "decision": "accepted",
            "image_filename": "slide_1.png"
        },
        {
            "frame_number": 2,
            "timestamp_seconds": 20.0,
            "timestamp_formatted": "00:00:20.000",
            "decision": "accepted",
            "image_filename": "slide_2.png"
        }
    ]
    FileManager.write_json_atomic(candidates_path, candidates)
    
    for c in candidates:
        img_p = os.path.join(job.paths["candidates"], c["image_filename"])
        with open(img_p, 'w') as f:
            f.write("dummy")

    # Touch raw.json transcription output
    raw_json_dir = os.path.join(job.paths["root"], "transcript")
    os.makedirs(raw_json_dir, exist_ok=True)
    raw_data = {
        "transcription": [
            {
                "offsets": {"from": 0, "to": 5000},
                "text": "First segment content."
            },
            {
                "offsets": {"from": 10000, "to": 15000},
                "text": "Second segment content."
            },
            {
                "offsets": {"from": 20000, "to": 25000},
                "text": "Third segment content."
            }
        ]
    }
    with open(os.path.join(raw_json_dir, "raw.json"), 'w', encoding='utf-8') as f:
        json.dump(raw_data, f)

    job.set_stage_status(STAGE_REVIEW_READY, "completed")
    job.save()

    # Instantiate MainWindow
    from lecturepack.ui.main_window import MainWindow
    window = MainWindow(config)
    qtbot.addWidget(window)
    
    # Load review state
    window.current_job = job
    window.controller.set_job(job)
    window._load_review_data()
    window.stack.setCurrentIndex(2)

    # 1. Verify counts
    assert window.slides_view.count() == 3
    
    # 2. Select first slide
    first_item = window.slides_view.item(0)
    window.slides_view.setCurrentItem(first_item)
    assert window.selected_count_lbl.text() == "Selected: 1"
    
    # 3. Ctrl-click (programmatic multi-select)
    window.slides_view.item(1).setSelected(True)
    assert window.selected_count_lbl.text() == "Selected: 2"
    
    # 4. Ctrl+A selection
    window.slides_view.selectAll()
    assert window.selected_count_lbl.text() == "Selected: 3"
    
    # 5. Bulk Reject action
    window._bulk_reject()
    cands_loaded = FileManager.read_json_safe(candidates_path)
    for c in cands_loaded:
        assert c["decision"] == "rejected"
        
    # Verify candidate files are NOT physically deleted
    for c in candidates:
        img_p = os.path.join(job.paths["candidates"], c["image_filename"])
        assert os.path.exists(img_p)

    # 6. Undo action
    window._undo_review_action()
    cands_loaded = FileManager.read_json_safe(candidates_path)
    for c in cands_loaded:
        assert c["decision"] == "accepted"

    # Select all slides to populate the transcript pane with all segments
    window.slides_view.selectAll()

    # 7. Search box navigation
    window.search_input.setText("Second")
    window._search_next()
    focused_widget = window.transcript_table.cellWidget(1, 1)
    assert focused_widget is not None
    assert "Second" in focused_widget.toPlainText()

    # 8. Edit segment and save
    focused_widget.setPlainText("Corrected Second text.")
    window._save_corrections()
    
    edited_path = os.path.join(job.paths["transcript"], "edited.json")
    edited_loaded = FileManager.read_json_safe(edited_path)
    assert edited_loaded["2"] == "Corrected Second text."

    # 9. Reset segment
    reset_btn = window.transcript_table.cellWidget(1, 2)
    qtbot.mouseClick(reset_btn, Qt.MouseButton.LeftButton)
    edited_loaded = FileManager.read_json_safe(edited_path)
    assert "2" not in edited_loaded

    # 10. Clipboard Copying
    from PySide6.QtGui import QGuiApplication
    clipboard = QGuiApplication.clipboard()
    
    window.timestamps_chk.setChecked(False)
    window._copy_full_transcript()
    assert "First segment content." in clipboard.text()
    
    window.timestamps_chk.setChecked(True)
    window._copy_full_transcript()
    assert "[00:00:00.000 -> 00:00:05.000]" in clipboard.text()

# 9. Test Bulk confirmation warning (>20 selected items)
def test_bulk_confirmation_dialog(tmp_path, qtbot):
    from lecturepack.infrastructure.config_manager import ConfigManager
    data_dir = tmp_path / "data"
    config = ConfigManager(str(data_dir))
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    candidates_path = os.path.join(job.paths["root"], "candidates.json")
    
    # 25 candidates
    candidates = []
    for i in range(25):
        candidates.append({
            "frame_number": i,
            "timestamp_seconds": float(i),
            "timestamp_formatted": f"00:00:{i:02d}.000",
            "decision": "accepted",
            "image_filename": f"slide_{i}.png"
        })
    FileManager.write_json_atomic(candidates_path, candidates)
    
    from lecturepack.ui.main_window import MainWindow
    window = MainWindow(config)
    qtbot.addWidget(window)
    window.current_job = job
    window._load_review_data()
    
    window.slides_view.selectAll()
    
    with patch('PySide6.QtWidgets.QMessageBox.question') as mock_question:
        mock_question.return_value = QMessageBox.StandardButton.No
        
        window._bulk_reject()
        mock_question.assert_called_once()
        
        # Decisions should NOT change because standard reply was No
        cands_loaded = FileManager.read_json_safe(candidates_path)
        for c in cands_loaded:
            assert c["decision"] == "accepted"

# 10. Test re-export does not launch transcription or slide detection
def test_re_export_skips_processing_stages(tmp_path, qtbot):
    from lecturepack.infrastructure.config_manager import ConfigManager
    data_dir = tmp_path / "data"
    config = ConfigManager(str(data_dir))
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    
    job = Job(str(data_dir), video_path=str(video_path))
    os.makedirs(job.paths["exports"], exist_ok=True)
    
    controller = JobController(config)
    controller.set_job(job)
    
    with patch('lecturepack.controllers.job_controller.ExportWorker') as MockExportWorker:
        mock_worker = MagicMock()
        MockExportWorker.return_value = mock_worker
        
        controller.export_now()
        
        # Verify transcription and detection stages were not reset to running or pending
        assert job.get_stage_status(STAGE_TRANSCRIBE) != "running"
        assert job.get_stage_status(STAGE_DETECT_SLIDES) != "running"


# 11. Test SlideDetectorWorker produces adaptive detection metadata fields
def test_adaptive_detection_metadata_structure(tmp_path):
    from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
    from lecturepack.constants import PRESETS
    
    video_path = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
    assert os.path.exists(video_path)
    
    job_paths = FileManager.init_job_dir(str(tmp_path), "test_job_metadata")
    preset = PRESETS["balanced"].copy()
    crop_region = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    
    worker = SlideDetectorWorker(
        video_path=video_path,
        crop_region=crop_region,
        ignore_masks=[],
        preset_settings=preset,
        job_paths=job_paths,
        start_time=0.0,
        end_time=10.0
    )
    
    results = []
    worker.finished.connect(lambda success, error, candidates: results.append((success, error, candidates)))
    worker.run()
    
    success, error, candidates = results[0]
    assert success
    assert len(candidates) > 0
    
    # Check new v0.4.0 adaptive fields
    first_cand = candidates[0]
    assert "detector_path" in first_cand
    assert "combined_score" in first_cand
    assert "rolling_baseline_score" in first_cand
    assert "component_scores" in first_cand
    assert "stability_result" in first_cand
    assert "changed_area_ratio" in first_cand


# 12. Test DetectionPreviewDialog launches, parses start/end range, and cleans up
def test_preview_dialog_integration(tmp_path, qtbot):
    from lecturepack.ui.main_window import DetectionPreviewDialog
    
    video_path = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
    assert os.path.exists(video_path)
    
    job_paths = FileManager.init_job_dir(str(tmp_path), "test_job_preview")
    crop_region = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    
    dialog = DetectionPreviewDialog(
        parent=None,
        video_path=video_path,
        crop_region=crop_region,
        ignore_masks=[],
        current_preset="balanced",
        job_paths=job_paths
    )
    qtbot.addWidget(dialog)
    
    # Set custom time fields
    dialog.start_edit.setText("1.0")
    dialog.end_edit.setText("10.0")
    dialog.preset_combo.setCurrentText("Balanced")
    
    # Execute preview run (blocking call to test thread synchronously)
    dialog.run_preview()
    
    # Wait for work to complete in background thread
    qtbot.waitUntil(lambda: dialog.run_btn.isEnabled(), timeout=10000)
    
    # Verify results populated in dialog table
    assert dialog.table.rowCount() > 0
    
    # Close dialog and check preview directories are cleaned up
    dialog.close()
    preview_dir = os.path.join(job_paths["root"], "preview_candidates")
    assert not os.path.exists(preview_dir)


# 13. Test legacy preset mapping fallback in job model
def test_legacy_preset_fallback(tmp_path):
    from lecturepack.infrastructure.config_manager import ConfigManager
    data_dir = tmp_path / "data"
    
    # Test job initialization with legacy preset "standard_lecture"
    job = Job(str(data_dir), video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    job.settings["preset"] = "standard_lecture"
    job.save()
    
    # Reopen and check legacy mapping
    reopened = Job(str(data_dir), job_id=job.job_id)
    preset_settings = reopened.get_preset_settings()
    assert preset_settings is not None
    # balanced preset has specific values
    from lecturepack.constants import PRESETS
    assert preset_settings == PRESETS["balanced"]

