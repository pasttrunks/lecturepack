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

    @staticmethod
    def archive_job(data_dir, job_id):
        """Moves job from jobs/ to archive/ directory."""
        job_dir = os.path.join(data_dir, "jobs", job_id)
        archive_dir = os.path.join(data_dir, "archive", job_id)
        if not os.path.exists(job_dir):
            raise FileNotFoundError(f"Job directory not found: {job_dir}")
        os.makedirs(os.path.dirname(archive_dir), exist_ok=True)
        shutil.move(job_dir, archive_dir)

    @staticmethod
    def restore_job(data_dir, job_id):
        """Moves job from archive/ back to jobs/ directory."""
        archive_dir = os.path.join(data_dir, "archive", job_id)
        job_dir = os.path.join(data_dir, "jobs", job_id)
        if not os.path.exists(archive_dir):
            raise FileNotFoundError(f"Archived job directory not found: {archive_dir}")
        os.makedirs(os.path.dirname(job_dir), exist_ok=True)
        shutil.move(archive_dir, job_dir)

    @staticmethod
    def export_job_archive(job_dir, zip_filepath):
        """Zips the contents of job_dir into zip_filepath, excluding the source video by default."""
        import zipfile
        os.makedirs(os.path.dirname(zip_filepath), exist_ok=True)
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(job_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Relpath for inside the ZIP archive
                    arcname = os.path.relpath(file_path, job_dir)
                    zipf.write(file_path, arcname)

