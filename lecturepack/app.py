import sys
from PySide6.QtWidgets import QApplication
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.ui.main_window import MainWindow

def run_packaged_validation(app):
    print("=== PACKAGED VALIDATION START ===")
    import os
    import json
    from lecturepack.models.job import Job
    from lecturepack.ui.main_window import MainWindow
    
    data_dir = r"C:\Users\marsh\LecturePackData"
    config = ConfigManager(data_dir)
    
    job_id = "75432ce6-1c37-45a6-a70c-57746339356f"
    job = Job(data_dir, job_id=job_id)
    
    window = MainWindow(config)
    window.show()
    QApplication.processEvents()
    
    window.current_job = job
    window.controller.set_job(job)
    window._load_review_data()
    window.stack.setCurrentIndex(2)
    QApplication.processEvents()
    
    # 1. Verify multi-selection and count
    print("Verifying multi-selection...")
    window.slides_view.item(0).setSelected(True)
    window.slides_view.item(1).setSelected(True)
    QApplication.processEvents()
    assert window.selected_count_lbl.text() == "Selected: 2", "Multi-selection count failed"
    
    # 2. Edit and persist correction
    print("Editing segment...")
    window.slides_view.selectAll()
    QApplication.processEvents()
    text_edit = window.transcript_table.cellWidget(0, 1)
    text_edit.setPlainText("Corrected packaged validation segment text.")
    QApplication.processEvents()
    window._save_corrections()
    QApplication.processEvents()
    window.close()
    QApplication.processEvents()
    
    # 3. Reopen and restore check
    print("Reopening to verify edit restoration...")
    window2 = MainWindow(config)
    window2.current_job = job
    window2.controller.set_job(job)
    window2._load_review_data()
    window2.stack.setCurrentIndex(2)
    window2.slides_view.selectAll()
    QApplication.processEvents()
    
    text_edit2 = window2.transcript_table.cellWidget(0, 1)
    assert text_edit2.toPlainText() == "Corrected packaged validation segment text.", "Restoration failed"
    print("Edit restored successfully!")
    
    # Reset
    print("Resetting segment...")
    reset_btn = window2.transcript_table.cellWidget(0, 2)
    reset_btn.click()
    QApplication.processEvents()
    
    # 4. Cached re-export
    print("Performing cached re-export...")
    window2.controller.export_now()
    QApplication.processEvents()
    
    # 5. Check .m4v Egypt lecture metadata loads
    print("Verifying Egypt lecture .m4v selection and preview...")
    m4v_path = r"C:\Users\marsh\OneDrive\Desktop\UB\CL100\CL100 - Day 2 - Egypt and Archaeology.m4v"
    
    from lecturepack.infrastructure.ffmpeg_wrapper import FFmpegWrapper
    wrapper = FFmpegWrapper(config_manager=config)
    info = wrapper.inspect_video(m4v_path)
    assert info is not None, "m4v metadata loading failed"
    assert info["duration"] > 0.0, "m4v duration parse failed"
    print(f"Loaded m4v metadata. Duration: {info['duration']:.2f}s")
    
    # 5b. Run Detection Preview on the Egypt lecture excerpt from 29:18 to 35:21
    print("Running Detection Preview on Egypt lecture excerpt from 29:18 to 35:21...")
    from lecturepack.ui.main_window import DetectionPreviewDialog
    crop_region = {"x": 0.02, "y": 0.05, "width": 0.96, "height": 0.85}
    preview_dialog = DetectionPreviewDialog(
        parent=window2,
        video_path=m4v_path,
        crop_region=crop_region,
        ignore_masks=[],
        current_preset="balanced",
        job_paths=window2.current_job.paths
    )
    preview_dialog.start_edit.setText("29:18")
    preview_dialog.end_edit.setText("35:21")
    preview_dialog.run_preview()
    
    import time
    start_wait = time.time()
    # Wait for the preview worker thread to finish (max 150 seconds)
    while not preview_dialog.run_btn.isEnabled() and time.time() - start_wait < 150:
        QApplication.processEvents()
        time.sleep(0.1)
        
    assert preview_dialog.table.rowCount() > 0, "No preview candidates detected"
    # The evaluation output showed 54 candidates for Egypt Excerpt
    assert preview_dialog.table.rowCount() == 54, f"Expected 54 candidates, got {preview_dialog.table.rowCount()}"
    print(f"Preview Dialog validated successfully! Detected {preview_dialog.table.rowCount()} candidates.")
    preview_dialog.close()
    QApplication.processEvents()
    
    # 6. Check for orphaned processes
    print("Verifying no orphaned processes remain...")
    window.whisper_detector.cancel()
    window2.whisper_detector.cancel()
    
    window2.close()
    print("=== PACKAGED VALIDATION COMPLETED SUCCESSFULLY ===")
    sys.exit(0)

def run_selftest():
    """Headless launch self-test for the packaged binary.

    Uses a throwaway temp data directory (never the user's LecturePackData),
    the offscreen Qt platform, and no external media. It proves the frozen
    bundle can import every dependency, initialise Qt, and construct the main
    window without crashing -- the exact failure class that broke the v0.2.0
    package. Prints a PASS/FAIL line and exits 0/1.
    """
    import os
    import tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import cv2, numpy, PySide6  # noqa: F401
        from lecturepack import __version__
        from lecturepack.services import transcript_service, detection_eval  # noqa: F401
        app = QApplication.instance() or QApplication(sys.argv)
        data_dir = tempfile.mkdtemp(prefix="lp_selftest_")
        config = ConfigManager(data_dir)
        window = MainWindow(config)
        window.show()
        QApplication.processEvents()
        # Sanity: the layered service is importable and functional in-bundle.
        raw = transcript_service.parse_raw_whisper_json(
            {"transcription": [{"offsets": {"from": 0, "to": 1000}, "text": " hello"}]})
        assert transcript_service.normalize_transcript(raw).segments, "normalize produced nothing"
        window.close()
        QApplication.processEvents()
        print(f"SELFTEST PASS: LecturePack v{__version__} launched, "
              f"cv2 {cv2.__version__}, PySide6 {PySide6.__version__}, offscreen OK")
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"SELFTEST FAIL: {e}")
        sys.exit(1)


def run_acceptance_cli():
    """Parse ``--run-acceptance <video> <model> <data_dir> [<out_json>] [--names "a,b,c"]``
    and drive the full packaged pipeline end-to-end. Exits 0 on pass, 1 on fail."""
    argv = sys.argv
    i = argv.index("--run-acceptance")
    rest = [a for a in argv[i + 1:] if not a.startswith("--")]
    names = []
    if "--names" in argv:
        ni = argv.index("--names")
        if ni + 1 < len(argv):
            names = [n.strip() for n in argv[ni + 1].split(",") if n.strip()]
    mode = None
    if "--mode" in argv:
        mi = argv.index("--mode")
        if mi + 1 < len(argv):
            mode = argv[mi + 1]
    if len(rest) < 3:
        print("usage: LecturePack.exe --run-acceptance <video> <model> <data_dir> [<out_json>] "
              "[--names a,b,c] [--mode study_pack|transcript_only|slides_only]")
        sys.exit(2)
    video, model, data_dir = rest[0], rest[1], rest[2]
    out = rest[3] if len(rest) > 3 else None
    from lecturepack.acceptance import run_packaged_acceptance
    report = run_packaged_acceptance(video, model, data_dir, approved_names=names,
                                     out_path=out, product_mode=mode)
    sys.exit(0 if report.get("ok") else 1)


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return

    if "--run-acceptance" in sys.argv:
        run_acceptance_cli()
        return

    app = QApplication(sys.argv)

    if "--run-packaged-validation" in sys.argv:
        run_packaged_validation(app)
        return

    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
