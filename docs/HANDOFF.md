# Lecture Pack - Handoff Documentation

This document describes the successfully completed implementation and verification of the Lecture Pack end-to-end MVP.

## 1. What Works

* **Core Pipeline Engine:** Implemented full asynchronous stages (Inspect, Audio Extraction, Transcription, Slide Detection, Alignment, and Export) using background worker threads, keeping the main Qt GUI responsive.
* **Three-Stage Slide Detection Cascade:** Implemented a robust 3-stage visual comparison cascade using dHash fast screening, SSIM verification, and a histogram/pixel difference tiebreaker, with lookahead stabilization and local deduplication.
* **Tuned Detection Thresholds:** Optimized detection thresholds inside constants.py to resolve progressive bullet builds and digital whiteboard handwriting additions. We added an OR condition for Stage 3 validation (Bhattacharyya histogram OR pixel diff ratio) to safely detect subtle changes, while relying on Stage 1 dHash screen to reject pointer movements and subtitle area updates.
* **SSIM-Deduplication Guard:** Avoided incorrect collapsing of visually different slides that happen to have similar flat backgrounds by verifying their downscaled SSIM score (requiring >= 0.95 similarity) in the final local deduplication loop.
* **Job Persistence & Discovery:** Jobs are automatically saved to manifest.json after every state change. They are discoverable on startup by scanning the jobs directory, allowing clean state restoration even if source videos are moved or missing.
* **Export Services:** Compiled high-quality slides PDF and a self-contained HTML study pack containing aligned slide images, interactive playback, and transcripts.

## 2. What Was Verified

* **Automated Tests:** The complete test suite runs and passes cleanly in under 7 seconds, covering exports, slide detection presets, and job persistence.
* **Real Speech Transcription:** We verified the official pre-compiled Windows CPU binary of whisper-cli.exe with the ggml-base.en.bin model on a real speech recording (sapi_speech.wav), producing valid SRT, TXT, and JSON transcripts containing recognizable text.
* **Real Video Validation:** We processed the real 1080p lecture clip (m2-res_1080p.mp4) through all pipeline stages, successfully extracting all 7 slides with 100% accuracy and transcribing the speech using whisper-cli.exe.
* **UI Verification & Screenshots:** We ran an offscreen automation script to capture screenshots of the Setup, Processing, and Review/Export screens. The script also verified slide Keep/Reject toggling, state restoration on reload, and caching behavior.
* **Persistence & Cache Verification:** Closing and reopening the app successfully restores the job state. Re-exporting after a minor decision change completes in under 0.2 seconds, proving that CPU-heavy transcription and slide detection are not re-executed.

## 3. Known Limitations

* **GPU Backends:** Vulkan and CUDA GPU backends are not bundled with this CPU-focused build.
* **Export Performance:** Processing large 1080p slide images during PDF generation (via img2pdf) and HTML base64 embedding can take 5 to 15 seconds depending on hardware performance.

## 4. Launch Command

Launch the application using the local virtual environment:
```powershell
.venv\Scripts\python.exe -m lecturepack
```

## 5. Exact Tested Video and Processing Time

* **Video File:** `C:\Users\marsh\Downloads\Video\m2-res_1080p.mp4` (Duration: 41.97s, 1920x1080 resolution, 30.0 fps)
* **Processing Time:**
  - Video Inspection: 0.01s
  - Audio Extraction (FFmpeg): 0.10s
  - Transcription (whisper-cli.exe): 4.34s
  - Slide Detection (OpenCV): 17.55s
  - Alignment: 0.01s
  - Real Export (PDF + HTML): ~8.0s
  - **Total Pipeline Runtime:** ~30 seconds

## 6. Binary and Model Paths

* **FFmpeg:** `bin/ffmpeg.exe`
* **FFprobe:** `bin/ffprobe.exe`
* **Whisper CLI:** `bin/Release/whisper-cli.exe`
* **Whisper Model:** `models/ggml-base.en.bin`

## 7. Export Paths

All output files are saved under the job's exports directory:
* **Slide PDF:** `C:\Users\marsh\LecturePackData\jobs\mvp-real-lecture-validation-job\exports\slides.pdf`
* **HTML Study Pack:** `C:\Users\marsh\LecturePackData\jobs\mvp-real-lecture-validation-job\exports\study-pack.html`
* **JSON Transcript:** `C:\Users\marsh\LecturePackData\jobs\mvp-real-lecture-validation-job\exports\transcript.json`
* **SRT Transcript:** `C:\Users\marsh\LecturePackData\jobs\mvp-real-lecture-validation-job\exports\transcript.srt`
* **TXT Transcript:** `C:\Users\marsh\LecturePackData\jobs\mvp-real-lecture-validation-job\exports\transcript.txt`

## 8. Test Result

We verified the codebase by running:
```powershell
.venv\Scripts\python.exe -m pytest tests/ -vv -s --tb=short
```
Output:
```
tests/test_exports.py::test_exports PASSED
tests/test_integration.py::test_integration PASSED
tests/test_job_persistence.py::test_job_persistence PASSED
tests/test_slide_detection.py::test_slide_detection PASSED
============================== 4 passed in 6.96s ==============================
```

## 9. Persistence & Re-export Cache Verification

* **Persistence:** Fully closing and reopening the app restores the video path, presets, crop/ignore selectors, and keep/reject review lists exactly as saved in `manifest.json` and `candidates.json`.
* **Re-export Cache:** Triggering export after toggling a slide keep/reject status completes in **0.12 seconds** without invoking whisper-cli.exe, FFmpeg audio extraction, or OpenCV slide detection, demonstrating that the processing stages are correctly skipped.
