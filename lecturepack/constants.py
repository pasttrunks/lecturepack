import os

APP_NAME = "Lecture Pack"
APP_VERSION = "0.2.1"

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

# Processing Presets (From section 4 of IMPLEMENTATION_PLAN.md)
PRESETS = {
    "standard_lecture": {
        "sample_fps": 1.0,
        "dhash_reject": 2,
        "dhash_accept": 20,
        "ssim_reject": 0.98,
        "ssim_accept": 0.75,
        "hist_bhatt_accept": 0.04,
        "pixel_diff_accept": 0.008,
        "stability_window_sec": 1.5,
        "stability_ssim": 0.97,
        "stability_max_wait_sec": 5.0,
        "dedup_phash_threshold": 8,
        "build_spatial_threshold": 0.08,
        "temporal_median_frames": 5,
        "gaussian_blur_kernel": 3,
    },
    "webcam_lecture": {
        "sample_fps": 1.0,
        "dhash_reject": 2,
        "dhash_accept": 20,
        "ssim_reject": 0.98,
        "ssim_accept": 0.75,
        "hist_bhatt_accept": 0.04,
        "pixel_diff_accept": 0.008,
        "stability_window_sec": 1.5,
        "stability_ssim": 0.97,
        "stability_max_wait_sec": 5.0,
        "dedup_phash_threshold": 8,
        "build_spatial_threshold": 0.08,
        "temporal_median_frames": 5,
        "gaussian_blur_kernel": 3,
    },
    "whiteboard_lecture": {
        "sample_fps": 2.0,
        "dhash_reject": 2,
        "dhash_accept": 12,
        "ssim_reject": 0.95,
        "ssim_accept": 0.80,
        "hist_bhatt_accept": 0.15,
        "pixel_diff_accept": 0.08,
        "stability_window_sec": 2.0,
        "stability_ssim": 0.96,
        "stability_max_wait_sec": 8.0,
        "dedup_phash_threshold": 12,
        "build_spatial_threshold": 0.04,
        "temporal_median_frames": 3,
        "gaussian_blur_kernel": 3,
    },
    "software_demo": {
        "sample_fps": 3.0,
        "dhash_reject": 2,
        "dhash_accept": 8,
        "ssim_reject": 0.88,
        "ssim_accept": 0.82,
        "hist_bhatt_accept": 0.10,
        "pixel_diff_accept": 0.05,
        "stability_window_sec": 0.75,
        "stability_ssim": 0.95,
        "stability_max_wait_sec": 3.0,
        "dedup_phash_threshold": 6,
        "build_spatial_threshold": 0.02,
        "temporal_median_frames": 1,
        "gaussian_blur_kernel": 0,
    }
}
