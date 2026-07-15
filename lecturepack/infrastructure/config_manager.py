import os
from lecturepack.constants import DEFAULT_DATA_DIR
from lecturepack.infrastructure.file_manager import FileManager

class ConfigManager:
    def __init__(self, data_dir=DEFAULT_DATA_DIR):
        self.data_dir = data_dir
        self.config_path = os.path.join(data_dir, "config.json")
        self.settings = {
            "whisper_exe": "",
            "whisper_model": "",
            "ffmpeg_dir": "", # Optional user-specified FFmpeg directory
            "data_directory": data_dir
        }
        self.load()

    def load(self):
        """Loads configuration from file or creates default."""
        if os.path.exists(self.config_path):
            data = FileManager.read_json_safe(self.config_path)
            if isinstance(data, dict):
                self.settings.update(data)
        else:
            self.save()

    def save(self):
        """Saves current configuration atomically."""
        FileManager.write_json_atomic(self.config_path, self.settings)

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()
