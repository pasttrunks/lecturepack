"""Downloaded videos reuse their published captions; local files do not.

Transcribing a video that already ships with a transcript is the slowest stage
of the pipeline redoing finished work. When a downloaded video brings captions,
they are converted into the exact file whisper.cpp writes and the Transcribe
stage is satisfied from them, so every later consumer -- transcript store,
editing, export, Study grounding -- works unchanged.

Two properties matter most and are tested hardest:

* SCOPING. Only the download path passes captions_dir, so a locally imported
  file cannot adopt captions. That is structural rather than a flag that could
  drift out of step.
* FAILSAFE. No captions, a malformed file, or too little text must leave the
  stage untouched so local transcription runs exactly as before.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lecturepack.services import source_captions as sc


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_PATH = ROOT / "electron-spike" / "python-sidecar.py"
SIDECAR_SRC = SIDECAR_PATH.read_text(encoding="utf-8")
MEDIA_FETCH = (ROOT / "lecturepack" / "services" / "media_fetch.py").read_text(encoding="utf-8")


def _sidecar(name: str):
    spec = importlib.util.spec_from_file_location(name, SIDECAR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Job:
    def __init__(self, transcript_dir: Path):
        self.job_id = "job-caps"
        self.paths = {"transcript": str(transcript_dir)}
        self.manifest: dict = {}
        self.stages: dict = {}
        self.saved = False

    def set_stage_status(self, stage, status, error=""):
        self.stages[stage] = status

    def save(self):
        self.saved = True


def _vtt(count: int = 12) -> str:
    return "WEBVTT\n\n" + "\n\n".join(
        f"00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000\n"
        f"This is caption line number {i} with enough text to count."
        for i in range(count))


# ------------------------------------------------------------------ parsing

def test_rolling_duplicate_lines_are_not_transcribed_twice():
    """Auto-captions repeat the previous line so the viewer sees them scroll.

    Passing those straight through doubles most of the transcript.
    """
    rolling = (
        "WEBVTT\nKind: captions\n\n"
        "00:00:00.120 --> 00:00:03.480 align:start position:0%\n"
        "Schliemann was a wealthy\n\n"
        "00:00:03.480 --> 00:00:06.900 align:start position:0%\n"
        "Schliemann was a wealthy\nbusinessman who excavated\n\n"
        "00:00:06.900 --> 00:00:10.200\n"
        "businessman who excavated\nthe site he believed was Troy\n"
    )
    joined = " ".join(s["text"] for s in sc.parse_vtt(rolling))
    assert joined.count("Schliemann was a wealthy") == 1
    assert joined.count("businessman who excavated") == 1
    assert "the site he believed was Troy" in joined


def test_karaoke_timing_tags_and_entities_are_removed():
    cue = ("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n"
           "hello<00:00:01.500><c> there</c> &amp; welcome\n")
    text = sc.parse_vtt(cue)[0]["text"]
    assert text == "hello there & welcome"


def test_srt_input_and_speaker_labels():
    srt = ("1\n00:00:01,000 --> 00:00:04,000\n[MUSIC] Publisher caption one.\n\n"
           "2\n00:00:04,000 --> 00:00:08,000\nSecond line.\n")
    parsed = sc.parse_vtt(srt)
    assert [p["text"] for p in parsed] == ["Publisher caption one.", "Second line."]
    assert parsed[0]["start"] == 1.0 and parsed[0]["end"] == 4.0


@pytest.mark.parametrize("junk", ["", "not a caption file", "WEBVTT\n\n\n", "\x00\x01"])
def test_a_malformed_file_yields_nothing_rather_than_raising(junk):
    assert sc.parse_vtt(junk) == []


def test_captions_are_written_in_whisper_cpp_shape():
    """Same file the transcriber writes, so nothing downstream needs to know."""
    raw = sc.to_whisper_raw([{"start": 1.5, "end": 2.25, "text": "hello"}])
    entry = raw["transcription"][0]
    assert entry["offsets"] == {"from": 1500, "to": 2250}
    assert entry["text"] == " hello"

    from lecturepack.services import transcript_store
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "raw.json").write_text(json.dumps(raw), encoding="utf-8")
        loaded = transcript_store.load_raw_segments({"transcript": d})
    assert loaded and loaded[0]["text"] == "hello"
    assert loaded[0]["start"] == 1.5 and loaded[0]["end"] == 2.25


def test_a_stub_transcript_is_not_accepted():
    assert not sc.is_usable([{"start": 0, "end": 1, "text": "Hi."}])
    assert sc.is_usable([{"start": i, "end": i + 1, "text": "x" * 80} for i in range(10)])


def test_publisher_captions_are_preferred_over_machine_generated(tmp_path):
    (tmp_path / "v.en-orig.vtt").write_text("x", encoding="utf-8")
    (tmp_path / "v.en.vtt").write_text("x", encoding="utf-8")
    assert Path(sc.find_caption_file(str(tmp_path))).name == "v.en.vtt"
    assert sc.find_caption_file(str(tmp_path / "nope")) == ""


# ------------------------------------------------------------------ adoption

def test_captions_complete_the_transcribe_stage(tmp_path):
    caps = tmp_path / "caps"; caps.mkdir()
    (caps / "video.en.vtt").write_text(_vtt(), encoding="utf-8")
    transcript = tmp_path / "transcript"; transcript.mkdir()
    job = _Job(transcript)

    module = _sidecar("lp_sidecar_adopt")
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._emit = lambda payload: None
    sidecar._adopt_source_captions(job, str(caps))

    assert (transcript / "raw.json").is_file()
    assert job.stages.get("Transcribe") == "completed"
    assert job.manifest.get("transcript_source") == "published_captions"
    assert job.saved


@pytest.mark.parametrize("content", [None, "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi.\n", "garbage"])
def test_unusable_captions_leave_local_transcription_to_run(tmp_path, content):
    caps = tmp_path / "caps"; caps.mkdir()
    if content is not None:
        (caps / "video.en.vtt").write_text(content, encoding="utf-8")
    transcript = tmp_path / "transcript"; transcript.mkdir()
    job = _Job(transcript)

    module = _sidecar("lp_sidecar_fallback")
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._emit = lambda payload: None
    sidecar._adopt_source_captions(job, str(caps))

    assert not (transcript / "raw.json").exists()
    assert job.stages.get("Transcribe") is None, "the stage must stay pending"


# ------------------------------------------------------------------ scoping

def test_only_the_download_path_can_adopt_captions():
    """A locally imported file must transcribe normally."""
    assert "captions_dir: str = \"\"" in SIDECAR_SRC
    guard = SIDECAR_SRC.split("self._generate_poster(job, source)", 1)[1][:600]
    assert "if captions_dir:" in guard, "adoption must be gated on the flag"
    # Exactly one caller supplies it: the URL download completion.
    assert SIDECAR_SRC.count('"captions_dir": d') == 1
    assert SIDECAR_SRC.count("captions_dir=str(payload.get") == 1


def test_the_downloader_asks_for_captions_without_requiring_them():
    download = MEDIA_FETCH.split("def download(", 1)[1].split("\ndef ", 1)[0]
    assert '"writesubtitles": True' in download
    assert '"writeautomaticsub": True' in download, "machine captions are a fallback"
    assert '"ignoreerrors": "only_download"' in download, (
        "a caption failure must never cost the download"
    )


@pytest.mark.parametrize("language,kept", [
    ("de", False),      # English track over German audio is a TRANSLATION
    ("fr", False),
    ("en", True),
    ("en-US", True),
    ("", True),         # extractor said nothing: trust the requested language
])
def test_translated_tracks_are_discarded_but_captions_are_kept(tmp_path, language, kept):
    """Subtitles may be a translation; captions are the original speech.

    Adopting a translation would produce a "transcript" matching no spoken
    word, so slide alignment and Study citations would both be wrong.
    """
    from lecturepack.services import media_fetch

    (tmp_path / "v.en.vtt").write_text("x", encoding="utf-8")
    (tmp_path / "v.mp4").write_bytes(b"video")
    media_fetch._discard_translated_captions(str(tmp_path), {"language": language})

    assert (tmp_path / "v.en.vtt").exists() is kept
    assert (tmp_path / "v.mp4").exists(), "the media must never be removed"


def test_sound_cues_are_not_treated_as_speech():
    """Study must not quote "[APPLAUSE]" back as something the lecturer said."""
    cue = ("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n"
           "[APPLAUSE] Welcome to the lecture.\n")
    assert sc.parse_vtt(cue)[0]["text"] == "Welcome to the lecture."


def test_the_caption_module_is_declared_as_a_hidden_import():
    """Declared because the caption pass swallows every exception.

    PyInstaller's modulegraph does follow function-level imports -- the build
    xref confirms it already collects this module, and several other lazily
    imported lecturepack modules ship without an entry -- so this is
    belt-and-braces rather than a fix. It earns its place because a missing
    module here would surface only as downloaded lectures quietly transcribing
    from scratch, with nothing in any log to say the feature had stopped.
    """
    spec = (ROOT / "electron-spike" / "sidecar.spec").read_text(encoding="utf-8")
    assert '"lecturepack.services.source_captions"' in spec


def test_a_caption_sidecar_can_never_be_mistaken_for_the_video():
    """Sidecars are written AFTER the media, so 'newest file wins' would break."""
    assert ".vtt" in MEDIA_FETCH.split("SIDECAR_SUFFIXES = (", 1)[1].split(")", 1)[0]
    newest = MEDIA_FETCH.split("def _newest_media(", 1)[1].split("\ndef ", 1)[0]
    assert "SIDECAR_SUFFIXES" in newest
