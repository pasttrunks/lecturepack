import os
import uuid
from datetime import datetime, timezone

from lecturepack.constants import (
    APP_VERSION, STAGES, STAGE_REVIEW_READY,
    PRODUCT_MODE_STUDY_PACK, PRODUCT_MODES, PRESETS,
)
from lecturepack.infrastructure.file_manager import FileManager


class Job:
    """Represents a single lecture processing job with persisted state."""

    def __init__(self, data_dir, job_id=None, video_path=None):
        self.data_dir = data_dir
        self.job_id = job_id or str(uuid.uuid4())

        self.manifest = {}
        self.source = {}
        self.settings = {}
        self.state = {}

        self.paths = FileManager.get_job_paths(data_dir, self.job_id)

        self.manifest_path = os.path.join(self.paths["root"], "manifest.json")
        self.source_path_json = os.path.join(self.paths["root"], "source.json")
        self.settings_path = os.path.join(self.paths["root"], "settings.json")
        self.state_path = os.path.join(self.paths["root"], "state.json")

        if video_path is not None:
            self.init_new(video_path)
        else:
            self.load()

    def init_new(self, video_path):
        self.paths = FileManager.init_job_dir(self.data_dir, self.job_id)
        self.manifest_path = os.path.join(self.paths["root"], "manifest.json")
        self.source_path_json = os.path.join(self.paths["root"], "source.json")
        self.settings_path = os.path.join(self.paths["root"], "settings.json")
        self.state_path = os.path.join(self.paths["root"], "state.json")

        now = datetime.now(timezone.utc).isoformat()
        filename = os.path.basename(video_path)
        stem = os.path.splitext(filename)[0]

        self.manifest = {
            "schema_version": 1,
            "job_id": self.job_id,
            "created_at": now,
            "app_version": APP_VERSION,
            "source": {
                "original_path": os.path.abspath(video_path),
                "filename": filename,
            },
            "title": stem,
        }

        self.source = {}

        self.settings = {
            "schema_version": 1,
            "preset": "balanced",
            "product_mode": PRODUCT_MODE_STUDY_PACK,
            "whisper": {
                "model": "ggml-base.en.bin",
                "language": "en",
                "glossary": "",
                "profile": "fast",
                "threads": 8,
                "vad_enabled": False,
                "vad_model": "",
                "vad_threshold": 0.50,
                "vad_min_speech_duration_ms": 250,
                "vad_min_silence_duration_ms": 100,
            },
            "slide_detection": {
                "crop_region": {"x": 0.0, "y": 0.0, "width": 1.1, "height": 1.1},
                "ignore_masks": [],
            },
        }

        self.state = {
            "schema_version": 1,
            "job_id": self.job_id,
            "overall_status": "pending",
            "last_updated": now,
            "stages": {stage: {"status": "pending"} for stage in STAGES},
        }

        self.save()

    def load(self):
        self.manifest = FileManager.read_json_safe(self.manifest_path, {})
        self.source = FileManager.read_json_safe(self.source_path_json, {})
        self.settings = FileManager.read_json_safe(self.settings_path, {})
        self.state = FileManager.read_json_safe(self.state_path, {})

        if not self.state.get("stages"):
            self.state["stages"] = {stage: {"status": "pending"} for stage in STAGES}
        if "overall_status" not in self.state:
            self.state["overall_status"] = "pending"
        if "schema_version" not in self.settings:
            self.settings["schema_version"] = 1
        if "whisper" not in self.settings:
            self.settings["whisper"] = {}
        if "slide_detection" not in self.settings:
            self.settings["slide_detection"] = {
                "crop_region": {"x": 0.0, "y": 0.0, "width": 1.1, "height": 1.1},
                "ignore_masks": [],
            }

    def save(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()

        FileManager.write_json_atomic(self.manifest_path, self.manifest)
        FileManager.write_json_atomic(self.source_path_json, self.source)
        FileManager.write_json_atomic(self.settings_path, self.settings)
        FileManager.write_json_atomic(self.state_path, self.state)

    def set_stage_status(self, stage, status, error=""):
        if stage not in self.state.get("stages", {}):
            self.state.setdefault("stages", {})[stage] = {}
        self.state["stages"][stage]["status"] = status
        if error:
            self.state["stages"][stage]["error"] = error

        all_statuses = [
            s.get("status", "pending")
            for name, s in self.state["stages"].items()
            if name != STAGE_REVIEW_READY
        ]
        if status == "failed":
            self.state["overall_status"] = "failed"
        elif status == "cancelled":
            self.state["overall_status"] = "cancelled"
        elif all(s == "completed" for s in all_statuses):
            self.state["overall_status"] = "completed"
        elif any(s == "running" for s in all_statuses):
            self.state["overall_status"] = "running"
        elif any(s == "failed" for s in all_statuses):
            self.state["overall_status"] = "failed"
        else:
            self.state["overall_status"] = "pending"

        self.save()

    def get_stage_status(self, stage):
        return self.state.get("stages", {}).get(stage, {}).get("status", "pending")

    def get_preset_settings(self):
        preset_name = self.settings.get("preset", "balanced")
        legacy_map = {
            "standard_lecture": "balanced",
            "webcam_lecture": "balanced",
            "whiteboard_lecture": "balanced",
            "software_demo": "balanced",
        }
        preset_name = legacy_map.get(preset_name, preset_name)
        return PRESETS.get(preset_name, PRESETS["balanced"])

    def get_product_mode(self):
        mode = self.settings.get("product_mode", PRODUCT_MODE_STUDY_PACK)
        return mode if mode in PRODUCT_MODES else PRODUCT_MODE_STUDY_PACK
