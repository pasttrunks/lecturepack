import os
import sys
import shutil
from lecturepack.constants import DEFAULT_DATA_DIR
from lecturepack.infrastructure.file_manager import FileManager


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
        "whisper_exe": "",
        "whisper_model": "",
        "ffmpeg_exe": "",
        "ffprobe_exe": "",
        "data_directory": DEFAULT_DATA_DIR,
    }

    def __init__(self, data_dir=None):
        app_dir = _app_dir()
        self.app_dir = app_dir
        self.resource_dir = _resource_dir()

        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        self.data_dir = data_dir
        self.config_path = os.path.join(data_dir, self.CONFIG_FILENAME)
        self.settings = dict(self.DEFAULT_SETTINGS)
        self.settings["data_directory"] = data_dir
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            data = FileManager.read_json_safe(self.config_path)
            if isinstance(data, dict):
                for k in self.DEFAULT_SETTINGS:
                    if k in data:
                        self.settings[k] = data[k]
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

    def resolve_data_dir(self):
        d = self.get("data_directory", DEFAULT_DATA_DIR)
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
