import os
import uuid
from datetime import datetime, timezone

from lecturepack.constants import (
    APP_VERSION, STAGES, STAGE_REVIEW_READY,
    PRODUCT_MODE_STUDY_PACK, PRODUCT_MODES, PRESETS,
)
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models import job_lifecycle


class Job:
    """Represents a single lecture processing job with persisted state."""

    def __init__(self, data_dir, job_id=None, video_path=None,
                 current_session_id=None):
        self.data_dir = data_dir
        self.job_id = job_id or str(uuid.uuid4())
        # Per-launch session id used to reconcile ownership of active jobs on
        # load. None (standalone/tests) => any active job is treated as a dead
        # session and reconciled to 'interrupted'.
        self._current_session_id = current_session_id

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
            # Authoritative beta.3 orchestration state (see job_lifecycle).
            "lifecycle": job_lifecycle.NEW,
            "session": {},
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

        # Reset orphaned running jobs — no backend process survives an app restart.
        # A job left in "running" state means the app was closed mid-job; treat
        # it as interrupted so the user can retry rather than seeing a frozen hang.
        if self.state.get("overall_status") == "running":
            self.state["overall_status"] = "interrupted"
            for stage_data in self.state.get("stages", {}).values():
                if stage_data.get("status") == "running":
                    stage_data["status"] = "interrupted"
            self.save()

        # beta.3 authoritative lifecycle: backfill for pre-beta.3 jobs, then
        # reconcile active states against session ownership. An active job
        # (running/pause_requested) survives load ONLY if the current session
        # owns it and its process is alive; otherwise its session is dead and
        # the job becomes 'interrupted' (artifacts preserved, resumable).
        _lifecycle_backfilled = "lifecycle" not in self.state
        if _lifecycle_backfilled:
            self.state["lifecycle"] = job_lifecycle.backfill_from_overall_status(
                self.state.get("overall_status", "pending"))
        owner = job_lifecycle.SessionOwner.from_dict(self.state.get("session"))
        reconciled = job_lifecycle.reconcile_on_load(
            self.state["lifecycle"], owner, self._current_session_id or "")
        _lifecycle_changed = reconciled != self.state["lifecycle"]
        if _lifecycle_backfilled or _lifecycle_changed:
            self.state["lifecycle"] = reconciled
            self.state["session"] = {}
            for stage_data in self.state.get("stages", {}).values():
                if stage_data.get("status") == "running":
                    stage_data["status"] = "interrupted"
            self.save()
        self.state.setdefault("session", {})
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

    # --- beta.3 authoritative lifecycle -------------------------------- #
    def get_lifecycle(self):
        return self.state.get("lifecycle", job_lifecycle.NEW)

    def set_lifecycle(self, new_state, owner=None):
        """Transition the authoritative lifecycle, validating the edge. Stamps
        session ownership when entering an active state and releases it when
        leaving one. Raises job_lifecycle.IllegalTransition on a bad edge."""
        current = self.get_lifecycle()
        if new_state == current:
            return
        job_lifecycle.assert_transition(current, new_state)
        self.state["lifecycle"] = new_state
        if new_state in job_lifecycle.ACTIVE_STATES:
            if owner is not None:
                self.state["session"] = owner.to_dict()
        else:
            # queued/scheduled/paused/terminal hold no execution slot.
            self.state["session"] = {}
        self.save()

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
