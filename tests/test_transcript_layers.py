"""Tests for the layered transcript service (Layer 1 raw / Layer 2 normalized /
Layer 3 context repair). Pure standard library -- no GUI, CV, or network."""

import os
import sys
import json
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lecturepack.services import transcript_service as ts


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _full_payload():
    """A whisper.cpp --output-json-full style payload with per-token probs."""
    return {
        "result": {"language": "en"},
        "transcription": [
            {
                "offsets": {"from": 0, "to": 4000},
                "text": " In today's session on King Tut.",
                "tokens": [
                    {"text": "[_BEG_]", "p": 0.01, "offsets": {"from": 0, "to": 0}},
                    {"text": " In", "p": 0.98, "offsets": {"from": 0, "to": 500}},
                    {"text": " today's", "p": 0.95, "offsets": {"from": 500, "to": 1200}},
                    {"text": " session", "p": 0.92, "offsets": {"from": 1200, "to": 2000}},
                    {"text": " on", "p": 0.9, "offsets": {"from": 2000, "to": 2300}},
                    {"text": " King", "p": 0.4, "offsets": {"from": 2300, "to": 3000}},
                    {"text": " Tut", "p": 0.3, "offsets": {"from": 3000, "to": 4000}},
                ],
            },
            {
                "offsets": {"from": 4000, "to": 6000},
                "text": " The the the runtime is O(n).",
                "tokens": [
                    {"text": " The", "p": 0.99, "offsets": {"from": 4000, "to": 4200}},
                ],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Layer 1 -- Raw
# --------------------------------------------------------------------------- #

def test_raw_parse_tokens_and_confidence():
    raw = ts.parse_raw_whisper_json(_full_payload(), meta={"model_name": "ggml-base.en"})
    assert raw.language == "en"
    assert len(raw.segments) == 2
    seg0 = raw.segments[0]
    # Special [_BEG_] token excluded from confidence.
    assert seg0.tokens[0].is_special()
    conf = seg0.confidence
    assert conf is not None and 0.3 < conf < 0.95
    assert raw.meta["model_name"] == "ggml-base.en"


def test_raw_parse_handles_reduced_shape_and_srt_timestamps():
    payload = {"transcription": [
        {"timestamps": {"from": "00:00:01,000", "to": "00:00:02,500"}, "text": " hi"}]}
    raw = ts.parse_raw_whisper_json(payload)
    assert raw.segments[0].t0_ms == 1000
    assert raw.segments[0].t1_ms == 2500


def test_raw_content_hash_stable_and_roundtrips():
    raw = ts.parse_raw_whisper_json(_full_payload())
    h = raw.content_hash()
    again = ts.RawTranscript.from_dict(raw.to_dict())
    assert again.content_hash() == h


# --------------------------------------------------------------------------- #
# Layer 2 -- Normalized (deterministic, non-destructive)
# --------------------------------------------------------------------------- #

def test_normalization_is_deterministic():
    raw = ts.parse_raw_whisper_json(_full_payload())
    a = ts.normalize_transcript(raw).to_dict()
    b = ts.normalize_transcript(raw).to_dict()
    assert a == b


def test_normalization_preserves_words_and_contractions():
    raw = ts.parse_raw_whisper_json(_full_payload())
    norm = ts.normalize_transcript(raw)
    assert "today's" in norm.segments[0].text
    assert "O(n)" in norm.segments[1].text
    # No spacing artifacts introduced around punctuation.
    assert " ' " not in norm.segments[0].text


def test_normalization_collapses_hallucination_loop():
    raw = ts.parse_raw_whisper_json(_full_payload())
    norm = ts.normalize_transcript(raw)
    # "The the the" -> "The the"
    assert norm.segments[1].text.lower().startswith("the the runtime")
    assert "loop_cleaned" in norm.segments[1].flags


def test_normalization_merges_exact_consecutive_duplicates():
    payload = {"transcription": [
        {"offsets": {"from": 0, "to": 1000}, "text": " Thank you."},
        {"offsets": {"from": 1000, "to": 2000}, "text": " Thank you."},
        {"offsets": {"from": 2000, "to": 3000}, "text": " Goodbye."},
    ]}
    raw = ts.parse_raw_whisper_json(payload)
    norm = ts.normalize_transcript(raw)
    assert len(norm.segments) == 2
    merged = norm.segments[0]
    assert merged.t1_ms == 2000            # time extended across the dup
    assert merged.source_ids == [0, 1]     # both original ids retained
    assert "dup_merged" in merged.flags


def test_normalization_flags_low_confidence():
    raw = ts.parse_raw_whisper_json(_full_payload())
    norm = ts.normalize_transcript(raw)
    assert "low_confidence" in norm.segments[0].flags  # min token p (Tut=0.30) < 0.40 floor


# --------------------------------------------------------------------------- #
# Layer 3 -- Context Repair: schema validation + guardrails
# --------------------------------------------------------------------------- #

class _Provider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.payload


def _norm():
    return ts.normalize_transcript(ts.parse_raw_whisper_json(_full_payload()))


def test_repair_rejects_invalid_json():
    eng = ts.ContextRepairEngine(provider=_Provider("not json {"))
    norm = _norm()
    idx = {s.id: s for s in norm.segments}
    assert eng.parse_and_validate("not json {", idx) == []


def test_repair_rejects_unknown_segment_and_noop():
    norm = _norm()
    idx = {s.id: s for s in norm.segments}
    eng = ts.ContextRepairEngine()
    # unknown id 99 and a no-op (identical text) both dropped
    resp = json.dumps({"corrections": [
        {"segment_id": 99, "corrected_text": "whatever", "reason": "x", "confidence": 0.9},
        {"segment_id": 0, "corrected_text": norm.segments[0].text, "reason": "noop", "confidence": 0.9},
    ]})
    assert eng.parse_and_validate(resp, idx) == []


def test_repair_similarity_guard_rejects_rewrite():
    norm = _norm()
    idx = {s.id: s for s in norm.segments}
    eng = ts.ContextRepairEngine()
    # A summary/rewrite that is nothing like the original must be rejected.
    resp = json.dumps({"corrections": [
        {"segment_id": 0, "corrected_text": "Completely different summary text here.",
         "reason": "summary", "confidence": 0.9}]})
    assert eng.parse_and_validate(resp, idx) == []


def test_repair_invented_name_needs_review_but_approved_is_proposed():
    norm = _norm()
    idx = {s.id: s for s in norm.segments}
    # Introduce a brand-new proper noun "Tutankhamun" not in the text.
    resp = json.dumps({"corrections": [
        {"segment_id": 0,
         "corrected_text": norm.segments[0].text.replace("King Tut", "Tutankhamun"),
         "reason": "expand name", "confidence": 0.8}]})

    without_approval = ts.ContextRepairEngine().parse_and_validate(resp, idx)
    assert without_approval and without_approval[0].status == "needs_review"

    with_approval = ts.ContextRepairEngine(
        approved_names=["Tutankhamun"]).parse_and_validate(resp, idx)
    assert with_approval and with_approval[0].status == "proposed"


def test_repair_accepts_plausible_homophone_fix():
    payload = {"transcription": [
        {"offsets": {"from": 0, "to": 2000}, "text": " We use a for loop hear."}]}
    norm = ts.normalize_transcript(ts.parse_raw_whisper_json(payload))
    idx = {s.id: s for s in norm.segments}
    resp = json.dumps({"corrections": [
        {"segment_id": 0, "corrected_text": "We use a for loop here.",
         "reason": "homophone hear->here", "confidence": 0.85}]})
    corr = ts.ContextRepairEngine().parse_and_validate(resp, idx)
    assert len(corr) == 1
    assert corr[0].status == "proposed"
    assert corr[0].corrected_text == "We use a for loop here."


# --------------------------------------------------------------------------- #
# Reversibility + raw immutability across the whole pipeline
# --------------------------------------------------------------------------- #

def test_corrections_are_reversible_and_do_not_mutate_layers():
    payload = _full_payload()
    payload_snapshot = copy.deepcopy(payload)
    raw = ts.parse_raw_whisper_json(payload)
    raw_hash = raw.content_hash()
    norm = ts.normalize_transcript(raw)
    norm_snapshot = norm.to_dict()

    resp = json.dumps({"corrections": [
        {"segment_id": 0,
         "corrected_text": norm.segments[0].text.replace("King Tut", "Tutankhamun"),
         "reason": "name", "confidence": 0.9}]})
    eng = ts.ContextRepairEngine(approved_names=["Tutankhamun"])
    cs = ts.CorrectionSet(eng.parse_and_validate(
        resp, {s.id: s for s in norm.segments}))

    # Before acceptance, reviewed view equals the normalized text.
    assert cs.reviewed_segments(norm)[0].text == norm.segments[0].text

    cs.accept(0)
    assert "Tutankhamun" in cs.reviewed_segments(norm)[0].text

    # Rejecting restores exactly -- fully reversible.
    cs.reject(0)
    assert cs.reviewed_segments(norm)[0].text == norm.segments[0].text

    # Neither raw, normalized, nor the source payload were mutated.
    assert raw.content_hash() == raw_hash
    assert norm.to_dict() == norm_snapshot
    assert payload == payload_snapshot


def test_propose_survives_provider_failure():
    class Boom:
        def complete(self, system, user):
            raise RuntimeError("endpoint down")
    norm = _norm()
    cs = ts.ContextRepairEngine(provider=Boom()).propose(norm)
    assert cs.corrections == []  # failure yields no corrections, no crash


def test_propose_requires_provider():
    import pytest
    with pytest.raises(RuntimeError):
        ts.ContextRepairEngine(provider=None).propose(_norm())


# --------------------------------------------------------------------------- #
# Context & Names + prompt building
# --------------------------------------------------------------------------- #

def test_entity_candidates_from_repetition_and_filename():
    payload = {"transcription": [
        {"offsets": {"from": 0, "to": 1000}, "text": " Egypt and the Nile."},
        {"offsets": {"from": 1000, "to": 2000}, "text": " Egypt again, the Nile flooded."},
    ]}
    norm = ts.normalize_transcript(ts.parse_raw_whisper_json(payload))
    cands = ts.propose_entity_candidates(norm, filename="CL100-Egypt-Archaeology.m4v")
    terms = {c.term for c in cands}
    assert "Egypt" in terms and "Nile" in terms
    egypt = next(c for c in cands if c.term == "Egypt")
    assert egypt.count >= 2 and "filename" in egypt.evidence


def test_whisper_prompt_sanitized_and_limited():
    prompt = ts.build_whisper_prompt(
        course_title="CL100 Egypt & Archaeology!!!",
        names=["Tutankhamun", "Howard Carter"],
        glossary="sarcophagus hieroglyph " + "word " * 400,
        max_words=20)
    assert "&" not in prompt
    assert len(prompt.split()) <= 20
    assert "Tutankhamun" in prompt


def test_correction_set_json_roundtrip():
    cs = ts.CorrectionSet([ts.Correction(1, "a", "b", "r", 0.5, "accepted")])
    again = ts.CorrectionSet.from_dict(json.loads(json.dumps(cs.to_dict())))
    assert again.corrections[0].corrected_text == "b"
    assert again.corrections[0].status == "accepted"
