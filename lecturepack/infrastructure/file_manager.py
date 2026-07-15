import os
import json
import shutil

class FileManager:
    @staticmethod
    def write_json_atomic(filepath, data):
        """Writes JSON data to a file atomically using a temporary file and rename."""
        temp_filepath = filepath + ".tmp"
        # Ensure directories exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        # Atomic replace
        os.replace(temp_filepath, filepath)

    @staticmethod
    def read_json_safe(filepath, default=None):
        """Safely reads a JSON file, returning a default value if missing or corrupt."""
        if not os.path.exists(filepath):
            return default
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def init_job_dir(data_dir, job_id):
        """Initializes the job subdirectories and returns a dictionary of paths."""
        job_dir = os.path.join(data_dir, "jobs", job_id)
        
        paths = {
            "root": job_dir,
            "audio": os.path.join(job_dir, "audio"),
            "transcript": os.path.join(job_dir, "transcript"),
            "frames": os.path.join(job_dir, "frames"),
            "candidates": os.path.join(job_dir, "frames", "candidates"),
            "accepted": os.path.join(job_dir, "frames", "accepted"),
            "rejected": os.path.join(job_dir, "frames", "rejected"),
            "exports": os.path.join(job_dir, "exports"),
            "logs": os.path.join(job_dir, "logs")
        }
        
        for name, path in paths.items():
            os.makedirs(path, exist_ok=True)
            
        return paths

    @staticmethod
    def get_job_paths(data_dir, job_id):
        """Returns job subdirectories map without creating them."""
        job_dir = os.path.join(data_dir, "jobs", job_id)
        return {
            "root": job_dir,
            "audio": os.path.join(job_dir, "audio"),
            "transcript": os.path.join(job_dir, "transcript"),
            "frames": os.path.join(job_dir, "frames"),
            "candidates": os.path.join(job_dir, "frames", "candidates"),
            "accepted": os.path.join(job_dir, "frames", "accepted"),
            "rejected": os.path.join(job_dir, "frames", "rejected"),
            "exports": os.path.join(job_dir, "exports"),
            "logs": os.path.join(job_dir, "logs")
        }
