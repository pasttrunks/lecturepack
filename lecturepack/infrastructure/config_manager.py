import os
import sys
import shutil
import copy
from lecturepack.constants import DATA_DIR_ENV_VAR, DEFAULT_DATA_DIR
from lecturepack.infrastructure.file_manager import FileManager


def _env_data_dir():
    """``LECTUREPACK_DATA_DIR`` if set and non-empty, else None."""
    override = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return None


def _app_dir():
    """Return the application root directory, handling PyInstaller onedir."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resource_dir():
    """Return the bundled resources directory (same as app_dir for onedir)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ConfigManager:
    CONFIG_FILENAME = "config.json"

    DEFAULT_SETTINGS = {
        "schema_version": 1,
        "whisper_exe": "",
        "whisper_vulkan_exe": "",
        "whisper_model": "",
        "ffmpeg_exe": "",
        "ffprobe_exe": "",
        "data_directory": DEFAULT_DATA_DIR,
        "engine": "auto",
        "vulkan_benchmark_ok": False,
        "parallel_pipeline": True,
        "groq_concurrency": 2,
        "groq_max_upload_bytes": 23 * 1024 * 1024,
        "online_fallback_local": True,
        # Phase 2 (AD-17): the glassmorphic dark theme is the default
        # first-launch experience; users can switch to light in Settings.
        "dark_theme": True,
        "ollama": {},
    }

    def __init__(self, data_dir=None):
        app_dir = _app_dir()
        self.app_dir = app_dir
        self.resource_dir = _resource_dir()

        # Precedence: explicit argument > LECTUREPACK_DATA_DIR > default root.
        if data_dir is None:
            data_dir = _env_data_dir() or DEFAULT_DATA_DIR
        self.data_dir = data_dir
        self.config_path = os.path.join(data_dir, self.CONFIG_FILENAME)
        self.settings = copy.deepcopy(self.DEFAULT_SETTINGS)
        self.settings["data_directory"] = data_dir
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            data = FileManager.read_json_safe(self.config_path, {})
            if isinstance(data, dict):
                # Merge EVERY stored key (not only the historical defaults) so
                # v1.1 settings -- engine, vulkan_benchmark_ok,
                # parallel_pipeline, ollama, dark_theme -- survive restarts.
                for k, v in data.items():
                    self.settings[k] = v
                # Pre-engine configs called this choice "backend" (and some
                # builds nested it under whisper).  Migrate without discarding
                # unknown future keys.
                if "engine" not in data:
                    nested = data.get("whisper") if isinstance(data.get("whisper"), dict) else {}
                    legacy_engine = data.get("backend", nested.get("backend"))
                    if legacy_engine in ("auto", "cpu", "vulkan"):
                        self.settings["engine"] = legacy_engine
                if not isinstance(self.settings.get("ollama"), dict):
                    self.settings["ollama"] = {}
                self.settings["schema_version"] = 1
                # Canonicalize BOM/partial legacy files immediately so the
                # migrated values demonstrably survive the next restart.
                if self.settings != data:
                    self.save()
        else:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            self.save()

    def save(self):
        FileManager.write_json_atomic(self.config_path, self.settings)

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def persist_runtime_health(self, runtime_health, *, bundled_model):
        """Atomically persist a complete, validated runtime-health snapshot.

        The beta-6 migration is deliberately guarded by an explicit marker so
        later manual model choices are never overwritten on subsequent starts.
        """
        if not isinstance(runtime_health, dict) or not runtime_health.get("components"):
            raise ValueError("runtime health must contain complete component facts")

        migration_versions = self.settings.get("migration_versions")
        if not isinstance(migration_versions, dict):
            migration_versions = {}

        if migration_versions.get("runtime_contract") != 1:
            previous_model = self.settings.get("whisper_model", "")
            if previous_model and previous_model != bundled_model:
                known_models = self.settings.get("known_whisper_models")
                if not isinstance(known_models, list):
                    known_models = []
                if previous_model not in known_models:
                    known_models.append(previous_model)
                self.settings["known_whisper_models"] = known_models
            self.settings["whisper_model"] = bundled_model
            migration_versions["runtime_contract"] = 1

        self.settings["migration_versions"] = migration_versions
        self.settings["runtime_health"] = runtime_health
        self.save()

    def resolve_data_dir(self):
        # The env override outranks a persisted ``data_directory`` so a config
        # copied from a real profile cannot pull a test run back onto real jobs.
        d = _env_data_dir() or self.get("data_directory", DEFAULT_DATA_DIR)
        os.makedirs(d, exist_ok=True)
        return d

    def _find_bundled_binary(self, name):
        """Look for a binary next to the executable or in a bin/ subfolder."""
        app_dir = self.app_dir
        candidates = [
            os.path.join(app_dir, name),
            os.path.join(app_dir, "bin", name),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return ""

    def autodetect_ffmpeg(self):
        """Try to find ffmpeg/ffprobe and persist their paths."""
        saved_ff = self.get("ffmpeg_exe", "")
        saved_fp = self.get("ffprobe_exe", "")
        if saved_ff and os.path.isfile(saved_ff) and saved_fp and os.path.isfile(saved_fp):
            return saved_ff, saved_fp

        bundled_ff = self._find_bundled_binary("ffmpeg.exe")
        bundled_fp = self._find_bundled_binary("ffprobe.exe")
        if bundled_ff and bundled_fp:
            self.set("ffmpeg_exe", bundled_ff)
            self.set("ffprobe_exe", bundled_fp)
            return bundled_ff, bundled_fp

        sys_ff = shutil.which("ffmpeg")
        sys_fp = shutil.which("ffprobe")
        if sys_ff and sys_fp:
            self.set("ffmpeg_exe", sys_ff)
            self.set("ffprobe_exe", sys_fp)
            return sys_ff, sys_fp

        return saved_ff, saved_fp

    def autodetect_whisper(self):
        """Try to find whisper-cli.exe and a model, persisting their paths."""
        saved_exe = self.get("whisper_exe", "")
        saved_model = self.get("whisper_model", "")

        if saved_exe and os.path.isfile(saved_exe):
            if saved_model and os.path.isfile(saved_model):
                return saved_exe, saved_model
            elif saved_model:
                return saved_exe, saved_model

        bundled = self._find_bundled_binary("whisper-cli.exe")
        if bundled:
            self.set("whisper_exe", bundled)

        models_dir = os.path.join(self.app_dir, "models")
        if not os.path.isdir(models_dir):
            models_dir = os.path.join(os.path.dirname(self.app_dir), "models")
        if os.path.isdir(models_dir):
            for fn in os.listdir(models_dir):
                if fn.endswith(".bin") and not saved_model:
                    self.set("whisper_model", os.path.join(models_dir, fn))
                    break

        return self.get("whisper_exe", ""), self.get("whisper_model", "")

    def check_diagnostics(self):
        """Return a dict of dependency statuses for the diagnostics display."""
        ffmpeg, ffprobe = self.autodetect_ffmpeg()
        whisper, model = self.autodetect_whisper()

        return {
            "ffmpeg": {"path": ffmpeg, "valid": os.path.isfile(ffmpeg) if ffmpeg else False},
            "ffprobe": {"path": ffprobe, "valid": os.path.isfile(ffprobe) if ffprobe else False},
            "whisper_cli": {"path": whisper, "valid": os.path.isfile(whisper) if whisper else False},
            "whisper_model": {"path": model, "valid": os.path.isfile(model) if model else False},
            "data_dir": {"path": self.resolve_data_dir(), "valid": os.path.isdir(self.resolve_data_dir())},
        }
