import os

from lecturepack import __version__

APP_NAME = "Lecture Pack"
APP_VERSION = __version__

# Provider-level transcription backend. Local whisper.cpp remains the private,
# dependency-free default; online adapters are registered only when their
# explicitly approved implementation is present and selected.
TRANSCRIPTION_BACKEND_LOCAL = "local-whispercpp"
TRANSCRIPTION_BACKEND_GROQ_FAST = "groq-fast"
TRANSCRIPTION_BACKEND_GROQ_ACCURATE = "groq-accurate"

TRANSCRIPTION_MODE_LABELS = {
    TRANSCRIPTION_BACKEND_LOCAL: "Private Local",
    TRANSCRIPTION_BACKEND_GROQ_FAST: "Online Fast (Groq)",
    TRANSCRIPTION_BACKEND_GROQ_ACCURATE: "Online Accurate (Groq)",
}

# Supported video file extensions (case-insensitive)
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.m4v', '.webm')

# Product modes -- what the user wants out of a lecture. These gate which
# processing stages run and which export artifacts are produced.
PRODUCT_MODE_STUDY_PACK = "study_pack"        # slides + transcript + study pack (default)
PRODUCT_MODE_TRANSCRIPT_ONLY = "transcript_only"  # audio + transcript only
PRODUCT_MODE_SLIDES_ONLY = "slides_only"      # slide deck only, no audio/transcript
PRODUCT_MODES = [
    PRODUCT_MODE_STUDY_PACK,
    PRODUCT_MODE_TRANSCRIPT_ONLY,
    PRODUCT_MODE_SLIDES_ONLY,
]
PRODUCT_MODE_LABELS = {
    PRODUCT_MODE_STUDY_PACK: "Study Pack (slides + transcript)",
    PRODUCT_MODE_TRANSCRIPT_ONLY: "Transcript Only",
    PRODUCT_MODE_SLIDES_ONLY: "Slides Only",
}

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
#
# Precision guards added in v1.0 (all preset-gated; cv_engine falls back to the
# pre-v1.0 behaviour when a key is absent):
#   overlay_band_reject / overlay_band_frac  -- drop progressive-build changes
#       confined to the bottom caption/subtitle band (live captions, burnt-in subs).
#   major_persistence_ssim                   -- reject a "major change" whose
#       captured frame is not still present ~1s later (fade / dissolve transitions
#       momentarily stabilise mid-blend). Calibrated on the ground-truth fixture:
#       real slides persist at SSIM >= 0.975, a mid-fade frame at 0.778.
#   build_persistence_ssim                   -- same persistence gate for
#       progressive builds (was hard-coded 0.96 pre-v1.0).
_COMMON_GUARDS = {
    "overlay_band_reject": True,
    "overlay_band_frac": 0.15,
    "build_persistence_ssim": 0.96,
    "major_persistence_ssim": 0.90,
    "persistence_look_ahead_sec": 1.0,
}

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
        **_COMMON_GUARDS,
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
        **_COMMON_GUARDS,
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
        **_COMMON_GUARDS,
    }
}
