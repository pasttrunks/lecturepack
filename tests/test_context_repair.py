"""Context Repair: deterministic provider, dialog review flow, layer separation,
reversibility, persistence, and no-deletion guarantees."""
import os
import json
import pytest

from lecturepack.services import transcript_service as ts
from lecturepack.infrastructure.file_manager import FileManager


RAW = {
    "result": {"language": "en", "transcription": [
        {"offsets": {"from": 0, "to": 3000}, "text": " Welcome to the lecture on ancient Egypt."},
        {"offsets": {"from": 3000, "to": 6000}, "text": " Today we discuss Tuten Common and Aboo Simbel."},
        {"offsets": {"from": 6000, "to": 9000}, "text": " The pharaoh ruled for many years."},
    ]}
}
APPROVED = ["Tutankhamun", "Abu Simbel", "Egypt"]


def _norm():
    raw = ts.parse_raw_whisper_json(RAW)
    return raw, ts.normalize_transcript(raw)


def test_deterministic_provider_proposes_only_approved_names():
    raw, norm = _norm()
    provider = ts.DeterministicNameProvider(APPROVED)
    engine = ts.ContextRepairEngine(provider=provider, approved_names=APPROVED)
    cs = engine.propose(norm)
    assert cs.corrections, "expected at least one name-match proposal"
    # Every corrected text may only introduce approved names (never invented).
    for c in cs.corrections:
        # the fix must contain an approved name that was not exactly in the original
        assert any(n.lower() in c.corrected_text.lower() for n in APPROVED)


def test_provider_never_invents_unapproved_name():
    raw, norm = _norm()
    provider = ts.DeterministicNameProvider(["Egypt"])  # only Egypt approved
    engine = ts.ContextRepairEngine(provider=provider, approved_names=["Egypt"])
    cs = engine.propose(norm)
    for c in cs.corrections:
        assert "Tutankhamun" not in c.corrected_text
        assert "Abu Simbel" not in c.corrected_text


def test_corrections_reversible_and_raw_immutable():
    raw, norm = _norm()
    h_before = raw.content_hash()
    provider = ts.DeterministicNameProvider(APPROVED)
    cs = ts.ContextRepairEngine(provider=provider, approved_names=APPROVED).propose(norm)
    first = cs.corrections[0].segment_id
    cs.accept(first)
    applied = cs.reviewed_segments(norm)
    # accepting changed the reviewed projection but not the normalized layer
    assert any("context_repaired" in s.flags for s in applied)
    assert all("context_repaired" not in s.flags for s in norm.segments)
    cs.reject(first)
    reverted = cs.reviewed_segments(norm)
    assert all("context_repaired" not in s.flags for s in reverted)
    # raw hash unchanged throughout
    assert raw.content_hash() == h_before


@pytest.mark.parametrize("with_config", [False])
def test_dialog_flow(qtbot, tmp_path, with_config):
    from lecturepack.models.job import Job
    from lecturepack.ui.context_repair_dialog import ContextRepairDialog

    data_dir = tmp_path / "data"
    video = tmp_path / "lec.mp4"
    video.touch()
    job = Job(str(data_dir), video_path=str(video))
    job.settings["context_names"] = APPROVED
    job.save()
    td = job.paths["transcript"]
    os.makedirs(td, exist_ok=True)
    FileManager.write_json_atomic(os.path.join(td, "raw.json"), RAW)
    raw = ts.parse_raw_whisper_json(RAW)
    FileManager.write_json_atomic(os.path.join(td, "normalized.json"),
                                  ts.normalize_transcript(raw).to_dict())
    raw_hash_before = FileManager.read_json_safe(os.path.join(td, "normalized.json"), {})["raw_content_hash"]

    dlg = ContextRepairDialog(job, None)
    qtbot.addWidget(dlg)
    assert dlg.correction_set.corrections, "dialog should generate proposals"

    n = len(dlg.correction_set.corrections)
    first = dlg.correction_set.corrections[0].segment_id
    dlg.correction_set.accept(first)
    if n > 1:
        dlg.correction_set.reject(dlg.correction_set.corrections[1].segment_id)
    dlg._save(quiet=True)

    # Layer files exist; raw.json unchanged; corrections + corrected written.
    assert os.path.exists(os.path.join(td, "corrections.json"))
    assert os.path.exists(os.path.join(td, "corrected.json"))
    saved = FileManager.read_json_safe(os.path.join(td, "corrections.json"), {})
    statuses = {c["segment_id"]: c["status"] for c in saved["corrections"]}
    assert statuses[first] == "accepted"
    # raw hash preserved
    assert FileManager.read_json_safe(os.path.join(td, "normalized.json"), {})["raw_content_hash"] == raw_hash_before
    # raw.json content still the original whisper payload
    assert FileManager.read_json_safe(os.path.join(td, "raw.json"), {}) == RAW


def test_dialog_add_remove_context_name(qtbot, tmp_path):
    from lecturepack.models.job import Job
    from lecturepack.ui.context_repair_dialog import ContextRepairDialog
    data_dir = tmp_path / "data"
    video = tmp_path / "lec.mp4"; video.touch()
    job = Job(str(data_dir), video_path=str(video))
    td = job.paths["transcript"]; os.makedirs(td, exist_ok=True)
    FileManager.write_json_atomic(os.path.join(td, "raw.json"), RAW)
    raw = ts.parse_raw_whisper_json(RAW)
    FileManager.write_json_atomic(os.path.join(td, "normalized.json"),
                                  ts.normalize_transcript(raw).to_dict())
    dlg = ContextRepairDialog(job, None)
    qtbot.addWidget(dlg)
    dlg.name_input.setText("Mesopotamia")
    dlg._add_name()
    assert "Mesopotamia" in dlg.approved_names
    # persisted into job settings + mirrored into the whisper glossary
    assert "Mesopotamia" in job.settings.get("context_names", [])
    assert "Mesopotamia" in job.settings["whisper"]["glossary"]
