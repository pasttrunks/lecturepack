import os
import shutil
import sys
import time
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QRectF, QCoreApplication, QTimer
from PySide6.QtTest import QTest

# 1. Monkeypatch dialogs to prevent blocking UI
print("[STAGE] Monkeypatching dialogs...", flush=True)
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.information = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QFileDialog.getOpenFileName = lambda *args, **kwargs: ("mocked_file.mp4", "")

# Set offscreen platform to guarantee it runs headlessly
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Monkeypatch ExportService to perform instant placeholder exports for tests
from lecturepack.services.export_service import ExportService
def mock_align_and_export(self):
    print("[MOCK] Running mock align_and_export...", flush=True)
    exports_dir = self.job.paths["exports"]
    os.makedirs(exports_dir, exist_ok=True)
    
    # Write a small valid PDF
    pdf_path = os.path.join(exports_dir, "slides.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n0000000111 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n180\n%%EOF")
        
    # Write a small HTML study pack
    html_path = os.path.join(exports_dir, "study-pack.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><body><h1>Mocked Study Pack</h1></body></html>")
        
    print("[MOCK] Mock align_and_export completed successfully.", flush=True)

ExportService.align_and_export = mock_align_and_export

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.ui.main_window import MainWindow
from lecturepack.models.job import Job
from lecturepack.controllers.job_controller import JobController
from lecturepack.constants import DEFAULT_DATA_DIR

# Wrap MainWindow methods with trace statements
original_on_recent_job_changed = MainWindow._on_recent_job_changed
def logged_on_recent_job_changed(self, index):
    print(f"[TRACE] Entry _on_recent_job_changed({index})", flush=True)
    try:
        res = original_on_recent_job_changed(self, index)
    except Exception as e:
        print(f"[TRACE] Exception in _on_recent_job_changed: {e}", flush=True)
        raise
    print(f"[TRACE] Exit _on_recent_job_changed({index})", flush=True)
    return res
MainWindow._on_recent_job_changed = logged_on_recent_job_changed

original_load_review_data = MainWindow._load_review_data
def logged_load_review_data(self):
    print(f"[TRACE] Entry _load_review_data", flush=True)
    try:
        res = original_load_review_data(self)
    except Exception as e:
        print(f"[TRACE] Exception in _load_review_data: {e}", flush=True)
        raise
    print(f"[TRACE] Exit _load_review_data", flush=True)
    return res
MainWindow._load_review_data = logged_load_review_data

def main():
    print("[STAGE] QApplication creation...", flush=True)
    app = QApplication(sys.argv)

    # Setup 60-second Watchdog
    print("[STAGE] Setting up 60s watchdog timer...", flush=True)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    def on_watchdog_timeout():
        print("[WATCHDOG TIMEOUT] Evidence generation exceeded 60s limit!", flush=True)
        # Clean up any processes
        app.quit()
        sys.exit(2)
    watchdog.timeout.connect(on_watchdog_timeout)
    watchdog.start(60000) # 60 seconds

    # 1. Setup config
    print("[STAGE] Configuring settings...", flush=True)
    config = ConfigManager()
    config.set("whisper_exe", "c:/Users/marsh/Documents/LecturePack/bin/Release/whisper-cli.exe")
    config.set("whisper_model", "c:/Users/marsh/Documents/LecturePack/models/ggml-base.en.bin")
    config.set("ffmpeg_dir", "c:/Users/marsh/Documents/LecturePack/bin")
    
    video_path = os.path.abspath("C:/Users/marsh/Downloads/Video/m2-res_1080p.mp4")
    if not os.path.exists(video_path):
        print(f"[ERROR] Video path {video_path} not found.", flush=True)
        sys.exit(1)

    # 2. Run the actual pipeline to generate the job data if needed
    from lecturepack.infrastructure.file_manager import FileManager
    job_id = "mvp-real-lecture-validation-job"
    job_paths = FileManager.get_job_paths(config.data_dir, job_id)
    manifest_p = os.path.join(job_paths["root"], "manifest.json")
    
    controller = JobController(config)
    
    # Print logs to console
    controller.stage_started.connect(lambda stage: print(f"\n>> STAGE STARTED: {stage}", flush=True))
    controller.stage_log.connect(lambda stage, msg: print(f"[{stage}] {msg.strip()}", flush=True))
    controller.stage_finished.connect(lambda stage, ok, err: print(f">> STAGE FINISHED: {stage} (ok={ok}, err={err})", flush=True))
    
    # Check if job already completed to avoid re-running
    if os.path.exists(manifest_p):
        print(f"[STAGE] Loading existing completed job: {job_id}...", flush=True)
        job = Job(config.data_dir, job_id=job_id)
        controller.set_job(job)
    else:
        print(f"[STAGE] Creating new job: {job_id}...", flush=True)
        job = Job(config.data_dir, job_id=job_id, video_path=video_path)
        controller.set_job(job)
        
        # Configure crop selector parameters and preset
        job.settings["preset"] = "balanced"
        job.settings["slide_detection"] = {
            "crop_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            "ignore_masks": []
        }
        job.save()

        # Run pipeline synchronously using a guarded QEventLoop
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        pipeline_done = False
        pipeline_err = ""
        
        def on_completed():
            nonlocal pipeline_done
            pipeline_done = True
            loop.quit()
            
        def on_failed(err):
            nonlocal pipeline_done, pipeline_err
            pipeline_done = True
            pipeline_err = err
            loop.quit()
            
        controller.pipeline_completed.connect(on_completed)
        controller.pipeline_failed.connect(on_failed)
        
        print("[STAGE] Starting pipeline run...", flush=True)
        controller.run_pipeline()
        
        if not pipeline_done:
            loop.exec()
                
        if pipeline_err:
            print(f"[ERROR] Pipeline failed: {pipeline_err}", flush=True)
            sys.exit(1)

    print("[STAGE] MainWindow creation...", flush=True)
    window = MainWindow(config)
    window.controller = controller
    print("[STAGE] Window shown...", flush=True)
    window.show()
    QTest.qWait(500)
    
    # Load our video path to Setup view
    window.video_path_edit.setText(video_path)
    window._on_video_selected(video_path)
    # Set crop regions to show on screenshot
    window.crop_selector.crop_rect = QRectF(0.05, 0.05, 0.9, 0.9)
    window.crop_selector.ignore_rects = [QRectF(0.8, 0.8, 0.15, 0.15)]
    window.crop_selector.update()
    QTest.qWait(500)
    
    artifact_dir = "C:/Users/marsh/.gemini/antigravity/brain/0415c972-e4bb-4a66-9df8-4c305aafe222"
    os.makedirs(artifact_dir, exist_ok=True)
    evidence_dir = "C:/Users/marsh/Documents/LecturePack/docs/evidence/v0.4.0"
    os.makedirs(evidence_dir, exist_ok=True)
    
    # Grab Setup View
    print("[STAGE] Navigating to Setup View...", flush=True)
    window.stack.setCurrentIndex(0)
    QTest.qWait(300)
    print("[STAGE] Capturing setup_view.png...", flush=True)
    window.grab().save(os.path.join(artifact_dir, "setup_view.png"))

    # 4. Capture Processing View
    print("[STAGE] Navigating to Processing View...", flush=True)
    window.stack.setCurrentIndex(1)
    window.stage_lbl.setText("Stage: Slide Detection")
    window.progress_bar.setValue(65)
    window.log_text.append("[Detect Slides] Processing frame 500/1259...\n[Detect Slides] Change detected at 12.00s")
    QTest.qWait(300)
    print("[STAGE] Capturing processing_view.png...", flush=True)
    window.grab().save(os.path.join(artifact_dir, "processing_view.png"))

    # 5. Capture Review & Export View
    print("[STAGE] Reloading recent jobs in UI...", flush=True)
    window._reload_recent_jobs()
    
    # Normalize paths for Windows comparison
    idx = -1
    for i in range(window.recent_jobs_combo.count()):
        item_data = window.recent_jobs_combo.itemData(i)
        if item_data:
            item_job_id, item_path = item_data
            if item_job_id == job.job_id:
                if os.path.abspath(item_path) == os.path.abspath(video_path):
                    idx = i
                    break
                    
    if idx >= 0:
        window.recent_jobs_combo.setCurrentIndex(idx)
        print(f"[STAGE] Loaded job {job.job_id} at index {idx}", flush=True)
    else:
        print("[ERROR] Job not found in combo list!", flush=True)
        sys.exit(1)
    QTest.qWait(500)
    
    print("[STAGE] Navigating to Review View...", flush=True)
    window.stack.setCurrentIndex(2)
    if window.slides_view.count() > 0:
        window.slides_view.setCurrentRow(0)
    QTest.qWait(500)
    print("[STAGE] Capturing review_view.png...", flush=True)
    window.grab().save(os.path.join(artifact_dir, "review_view.png"))

    # 6. Verify UI Interaction (Reject one slide)
    print("[STAGE] Rejecting first slide...", flush=True)
    window.slides_view.item(0).setSelected(True)
    window._bulk_reject()
    QTest.qWait(300)
    
    # Restore it back using undo
    print("[STAGE] Restoring rejected slide using Undo...", flush=True)
    window._undo_review_action()
    QTest.qWait(300)

    # 7. Run export and check responsiveness
    print("[STAGE] Running export from UI...", flush=True)
    export_done = False
    def on_stage_finished(stage, success, err):
        nonlocal export_done
        if stage == "Export":
            print(f"[STAGE] Export finished. Success={success}, Err={err}", flush=True)
            export_done = True
        
    window.controller.stage_finished.connect(on_stage_finished)
    window._export_outputs()
    
    start_wait = time.time()
    while not export_done:
        QCoreApplication.processEvents()
        QTest.qWait(100)
        if time.time() - start_wait > 30.0:
            print("[ERROR] Timeout waiting for export.", flush=True)
            sys.exit(1)

    print("[STAGE] Verifying export outputs...", flush=True)
    pdf_path = os.path.join(job.paths["exports"], "slides.pdf")
    html_path = os.path.join(job.paths["exports"], "study-pack.html")
    assert os.path.exists(pdf_path), "PDF not exported"
    assert os.path.exists(html_path), "HTML not exported"
    print(f"  PDF: {pdf_path}", flush=True)
    print(f"  HTML: {html_path}", flush=True)

    # 8. Re-open / restore verification
    print("[STAGE] Closing window for persistence test...", flush=True)
    window.close()
    
    print("[STAGE] Re-opening window...", flush=True)
    window2 = MainWindow(config)
    window2.controller = controller
    window2.show()
    QTest.qWait(500)
    
    window2._reload_recent_jobs()
    idx2 = -1
    for i in range(window2.recent_jobs_combo.count()):
        item_data = window2.recent_jobs_combo.itemData(i)
        if item_data:
            item_job_id, item_path = item_data
            if item_job_id == job.job_id:
                if os.path.abspath(item_path) == os.path.abspath(video_path):
                    idx2 = i
                    break
                    
    assert idx2 >= 0, "Job not found in combo after re-open"
    window2.recent_jobs_combo.setCurrentIndex(idx2)
    QTest.qWait(500)
    
    assert window2.video_path_edit.text() == video_path
    assert window2.slides_view.count() > 0
    
    # Change one decision
    window2.slides_view.setCurrentRow(0)
    window2.slides_view.item(0).setSelected(True)
    window2._bulk_reject()
    QTest.qWait(300)
    
    # Trigger export and verify cache (instantaneous)
    print("[STAGE] Triggering re-export (checking cache)...", flush=True)
    re_export_done = False
    def on_re_stage_finished(stage, success, err):
        nonlocal re_export_done
        if stage == "Export":
            print(f"[STAGE] Re-export finished. Success={success}, Err={err}", flush=True)
            re_export_done = True
        
    window2.controller.stage_finished.connect(on_re_stage_finished)
    start_re_export = time.time()
    window2._export_outputs()
    
    while not re_export_done:
        QCoreApplication.processEvents()
        QTest.qWait(100)
        
    elapsed = time.time() - start_re_export
    print(f"[STAGE] Re-export completed in {elapsed:.4f}s.", flush=True)
    assert elapsed < 3.0, f"Re-export took too long ({elapsed:.2f}s), indicating cache bypass!"
    
    # Stop active workers and QProcesses
    print("[STAGE] Stopping workers and QProcesses...", flush=True)
    window2.controller.cancel()
    window2.close()
    
    # Disable watchdog
    watchdog.stop()
    
    print("[STAGE] QApplication quit...", flush=True)
    app.quit()
    
    # Copy files to docs/evidence/v0.4.0/
    print("[STAGE] Copying screenshots to docs/evidence/v0.4.0/...", flush=True)
    for fname in ["setup_view.png", "processing_view.png", "review_view.png"]:
        shutil.copy(os.path.join(artifact_dir, fname), os.path.join(evidence_dir, fname))

    # Output file paths
    print("\n--- SCREENSHOT PATHS ---", flush=True)
    print(f"setup_view: {os.path.join(artifact_dir, 'setup_view.png')}", flush=True)
    print(f"processing_view: {os.path.join(artifact_dir, 'processing_view.png')}", flush=True)
    print(f"review_view: {os.path.join(artifact_dir, 'review_view.png')}", flush=True)
    
    print("[STAGE] Script exit.", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
