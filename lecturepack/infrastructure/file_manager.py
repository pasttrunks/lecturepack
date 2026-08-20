import os
import json
import shutil
import tempfile

class FileManager:
    @staticmethod
    def write_json_atomic(filepath, data):
        """Writes JSON data to a file atomically using a temporary file and rename.

        The temporary file gets a unique name in the destination directory. A
        fixed ``filepath + ".tmp"`` made the *temp file itself* a shared
        resource: two writers racing on the same path (the sidecar and the UI
        process both persist job state) would interleave their partial writes
        into one buffer, and the loser's ``os.replace`` could publish the
        winner's half-written bytes. ``reset_service`` sweeps both this shape
        and the historical one.
        """
        directory = os.path.dirname(filepath) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temp_filepath = tempfile.mkstemp(
            prefix=f".{os.path.basename(filepath)}.", suffix=".tmp", dir=directory,
        )
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
                descriptor = -1
                json.dump(data, f, indent=4, ensure_ascii=False)
            # Atomic replace
            os.replace(temp_filepath, filepath)
        finally:
            if descriptor != -1:
                os.close(descriptor)
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except OSError:
                    pass

    @staticmethod
    def read_json_safe(filepath, default=None):
        """Safely reads a JSON file, returning a default value if missing or
        corrupt. utf-8-sig tolerates a UTF-8 BOM (files edited with Notepad or
        written by PowerShell 5.1 carry one)."""
        if not os.path.exists(filepath):
            return default
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
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

