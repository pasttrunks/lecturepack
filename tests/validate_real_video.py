import os
import sys
import time
import json
import subprocess
from lecturepack.infrastructure.ffmpeg_wrapper import FFmpegWrapper
from lecturepack.infrastructure.whisper_wrapper import WhisperWrapper
from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
from lecturepack.constants import PRESETS

def main():
    video_path = "C:/Users/marsh/Downloads/Video/m2-res_1080p.mp4"
    job_dir = "c:/Users/marsh/Documents/LecturePack/tests/fixtures/m2_job"
    os.makedirs(job_dir, exist_ok=True)
    
    job_paths = {
        "job_dir": job_dir,
        "audio": os.path.join(job_dir, "audio"),
        "transcript": os.path.join(job_dir, "transcript"),
        "candidates": os.path.join(job_dir, "candidates"),
        "exports": os.path.join(job_dir, "exports")
    }
    for k, v in job_paths.items():
        if k != "job_dir":
            os.makedirs(v, exist_ok=True)
            
    print("--- 1. Inspecting Video ---")
    ffmpeg = FFmpegWrapper()
    # Ensure it detects bin/
    ffmpeg.detect_binaries()
    print(f"FFmpeg path: {ffmpeg.ffmpeg_path}")
    print(f"FFprobe path: {ffmpeg.ffprobe_path}")
    
    meta = ffmpeg.inspect_video(video_path)
    print(f"Metadata: {meta}")
    
    print("\n--- 2. Extracting Audio ---")
    wav_path = os.path.join(job_paths["audio"], "lecture-16khz-mono.wav")
    start_time = time.time()
    
    # Run ffmpeg command synchronously for simplicity in validation script
    cmd = [
        ffmpeg.ffmpeg_path,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "16000",
        wav_path
    ]
    res = subprocess.run(cmd, capture_output=True)
    audio_extract_time = time.time() - start_time
    print(f"Audio extracted in {audio_extract_time:.2f}s. Exit code: {res.returncode}")
    
    print("\n--- 3. Real Transcription ---")
    whisper = WhisperWrapper()
    # Point to downloaded binary and model
    whisper.whisper_path = "c:/Users/marsh/Documents/LecturePack/bin/Release/whisper-cli.exe"
    whisper.model_path = "c:/Users/marsh/Documents/LecturePack/models/ggml-base.en.bin"
    print(f"Whisper path: {whisper.whisper_path}")
    print(f"Model path: {whisper.model_path}")
    
    start_time = time.time()
    raw_prefix = os.path.join(job_paths["transcript"], "raw")
    
    cmd_w = [
        whisper.whisper_path,
        "-m", whisper.model_path,
        "-f", wav_path,
        "-oj",
        "-osrt",
        "-otxt",
        "-of", raw_prefix
    ]
    res_w = subprocess.run(cmd_w, capture_output=True, text=True)
    transcription_time = time.time() - start_time
    print(f"Transcription finished in {transcription_time:.2f}s. Exit code: {res_w.returncode}")
    
    print("\n--- 4. Slide Detection ---")
    preset = PRESETS["balanced"]
    
    # Run slide detection
    worker = SlideDetectorWorker(
        video_path=video_path,
        crop_region=None,
        ignore_masks=[],
        preset_settings=preset,
        job_paths=job_paths
    )
    
    # Store candidates collected by signal
    candidates_list = []
    def on_finished(success, err, candidates):
        print(f"Finished. Success: {success}, Error: {err}")
        candidates_list.extend(candidates)
        
    worker.finished.connect(on_finished)
    worker.status_message.connect(print)
    
    start_time = time.time()
    worker.run()
    slide_detection_time = time.time() - start_time
    print(f"Slide detection finished in {slide_detection_time:.2f}s.")
    print(f"Accepted slide count: {len(candidates_list)}")
    print(f"Slides: {[c['timestamp_seconds'] for c in candidates_list]}")

if __name__ == "__main__":
    main()
