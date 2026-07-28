"""Private ASCII-only paths for the narrow whisper.cpp v1.9.1 argv boundary."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def _is_ascii_path(path: Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _staging_parent() -> Path:
    """Return an application-controlled, ASCII-only private staging parent."""
    candidate = Path(tempfile.gettempdir()) / "LecturePackWhisper"
    if not _is_ascii_path(candidate):
        drive = Path(tempfile.gettempdir()).drive or "C:"
        candidate = Path(f"{drive}\\LecturePackWhisper")
    if not _is_ascii_path(candidate):
        raise RuntimeError("unable to create an ASCII-only whisper staging path")
    candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
    return candidate


class WhisperPathStaging:
    """Copy native CLI inputs to a disposable ASCII directory and publish outputs."""

    def __init__(self, model_path: str | Path, audio_path: str | Path,
                 output_prefix: str | Path):
        self.model_path = Path(model_path)
        self.audio_path = Path(audio_path)
        self.output_prefix = Path(output_prefix)
        self.root: Path | None = None
        self.staged_model: Path | None = None
        self.staged_audio: Path | None = None
        self.staged_output_prefix: Path | None = None

    def prepare(self) -> tuple[str, str, str]:
        for source in (self.model_path, self.audio_path):
            if not source.is_file():
                raise FileNotFoundError(source)
        self.root = Path(tempfile.mkdtemp(prefix="lpws-", dir=_staging_parent()))
        inputs = self.root / "inputs"
        outputs = self.root / "outputs"
        inputs.mkdir(mode=0o700)
        outputs.mkdir(mode=0o700)
        self.staged_model = self._copy_input(self.model_path, inputs / "model.bin")
        self.staged_audio = self._copy_input(self.audio_path, inputs / "audio.wav")
        self.staged_output_prefix = outputs / "transcript"
        argv_paths = (str(self.staged_model), str(self.staged_audio), str(self.staged_output_prefix))
        if not all(_is_ascii_path(Path(value)) for value in argv_paths):
            self.cleanup()
            raise RuntimeError("whisper staging generated a non-ASCII argv path")
        return argv_paths

    @staticmethod
    def _copy_input(source: Path, destination: Path) -> Path:
        shutil.copyfile(source, destination)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            raise OSError(f"staged input did not preserve bytes: {source}")
        return destination

    def publish_outputs(self) -> list[Path]:
        if self.staged_output_prefix is None:
            return []
        self.output_prefix.parent.mkdir(parents=True, exist_ok=True)
        published: list[Path] = []
        for staged in self.staged_output_prefix.parent.glob(f"{self.staged_output_prefix.name}.*"):
            suffix = staged.name[len(self.staged_output_prefix.name):]
            target = Path(f"{self.output_prefix}{suffix}")
            os.replace(staged, target)
            published.append(target)
        return published

    def cleanup(self) -> None:
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = None
