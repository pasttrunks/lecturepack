import os

APP_NAME = "Lecture Pack"
APP_VERSION = "0.4.0"

# Supported video file extensions (case-insensitive)
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.m4v', '.webm')

# Stages definitions
STAGE_INSPECT = "Inspect"
STAGE_EXTRACT_AUDIO = "Extract Audio"
STAGE_TRANSCRIBE = "Transcribe"
STAGE_DETECT_SLIDES = "Detect Slides"
STAGE_ALIGN = "Align"
STAGE_REVIEW_READY = "Review Ready"
STAGE_EXPORT = "Export"

STAGES = [
    STAGE_INSPECT,
    STAGE_EXTRACT_AUDIO,
    STAGE_TRANSCRIBE,
    STAGE_DETECT_SLIDES,
    STAGE_ALIGN,
    STAGE_REVIEW_READY,
    STAGE_EXPORT
]

# Default directories
DEFAULT_DATA_DIR = os.path.expanduser(os.path.join("~", "LecturePackData"))

# Adaptive Processing Presets (Conservative, Balanced, Detailed)
PRESETS = {
    "conservative": {
        "sample_fps": 1.0,
        "gaussian_blur_kernel": 3,
        "major_threshold": 0.18,
        "minor_threshold": 0.05,
        "stability_window_sec": 1.5,
        "stability_ssim": 0.98,
        "stability_max_wait_sec": 5.0,
        "min_time_between_slides": 8.0,
        "dedup_phash_threshold": 8,
    },
    "balanced": {
        "sample_fps": 1.0,
        "gaussian_blur_kernel": 3,
        "major_threshold": 0.12,
        "minor_threshold": 0.02,
        "stability_window_sec": 1.5,
        "stability_ssim": 0.97,
        "stability_max_wait_sec": 5.0,
        "min_time_between_slides": 5.0,
        "dedup_phash_threshold": 8,
    },
    "detailed": {
        "sample_fps": 2.0,
        "gaussian_blur_kernel": 3,
        "major_threshold": 0.08,
        "minor_threshold": 0.01,
        "stability_window_sec": 1.0,
        "stability_ssim": 0.96,
        "stability_max_wait_sec": 4.0,
        "min_time_between_slides": 2.0,
        "dedup_phash_threshold": 6,
    }
}
