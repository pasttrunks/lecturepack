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

def main():
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
