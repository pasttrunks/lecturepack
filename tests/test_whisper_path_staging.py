from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lecturepack.infrastructure.whisper_path_staging import WhisperPathStaging


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_staging_uses_ascii_argv_preserves_unicode_inputs_and_publishes_outputs(tmp_path):
    source = tmp_path / "漢 model.bin"
    audio = tmp_path / "é audio.wav"
    destination = tmp_path / "結果 output" / "raw"
    source.write_bytes(b"model bytes")
    audio.write_bytes(b"audio bytes")
    before = (_digest(source), _digest(audio))
    staging = WhisperPathStaging(source, audio, destination)
    model, wav, prefix = staging.prepare()
    assert all(value.isascii() for value in (model, wav, prefix))
    assert (_digest(source), _digest(audio)) == before
    Path(f"{prefix}.json").write_text('{"segments": []}', encoding="utf-8")
    published = staging.publish_outputs()
    assert published == [Path(f"{destination}.json")]
    assert Path(f"{destination}.json").read_text(encoding="utf-8") == '{"segments": []}'
    root = staging.root
    staging.cleanup()
    assert root is not None and not root.exists()


def test_staging_cleanup_is_safe_after_prepare_failure(tmp_path):
    staging = WhisperPathStaging(tmp_path / "missing 漢.bin", tmp_path / "audio.wav", tmp_path / "out")
    with pytest.raises(FileNotFoundError):
        staging.prepare()
    staging.cleanup()
    assert staging.root is None
