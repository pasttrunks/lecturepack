# Transcription and Context Repair

Lecture Pack stores a transcript as **three separate layers**. Each layer is
kept independently so the pipeline is auditable and every automated change is
reversible. The implementation lives in
`lecturepack/services/transcript_service.py` and is pure standard library (no
PySide6, no OpenCV, no mandatory network access).

## Layer 1 — Raw (immutable)

The exact whisper.cpp output plus provenance metadata. `parse_raw_whisper_json`
accepts both the real `--output-json-full` payload (top-level `transcription`
with per-token `tokens`/`p`) and the reduced `result.transcription` shape.

For every segment it preserves the text, start/end offsets in milliseconds, and
per-token timing and probability when available. Segment confidence is the mean
probability of the non-special tokens; `min_token_p` exposes the lowest token
probability so a garbled word (often a misheard name) is visible even when the
segment's mean confidence looks fine.

`RawTranscript.content_hash()` returns a stable SHA-256 over the meaningful raw
content. Downstream stages record this hash and can re-check it at any time to
**prove the raw layer was never modified**. Raw output is never overwritten.

## Layer 2 — Normalized (deterministic, non-generative)

`normalize_transcript` produces a clean reading copy **without changing a single
word, name, number, or fact.** It is fully deterministic: the same raw input
always yields byte-identical normalized output. It only:

- collapses whitespace and fixes spacing before punctuation;
- collapses runs of repeated punctuation;
- collapses consecutive hallucination loops (e.g. `you you you you` → `you you`)
  via targeted substitution that leaves contractions like `today's` and tokens
  like `O(n)` untouched;
- merges *exact consecutive duplicate* segments, extending the time span and
  keeping every original segment id in `source_ids`;
- groups segments into paragraphs on long pauses or sentence boundaries (a
  purely structural annotation — segment text is not altered).

Segments are flagged (`low_confidence`, `loop_cleaned`, `dup_merged`) for the
review UI. Original segment ids and timestamps are always preserved.

## Layer 3 — Context Repair (optional, auditable, reversible)

Context Repair is an **opt-in** stage that proposes corrections to *likely
transcription mistakes* using a local LLM. The application is fully functional
with no provider configured.

### Provider

`OpenAICompatibleProvider(base_url, model, api_key=None)` targets any
OpenAI-compatible `/v1/chat/completions` endpoint — e.g. a local Qwen-class
model served by **LM Studio** or **Ollama**. Any object exposing
`complete(system, user) -> str` can be used, so the engine is fully testable
without a network.

### What it may use as context

Source filename, user-entered course/topic title, an approved names list, the
glossary, and the surrounding transcript segments (chunked with overlap).

### Safety guardrails

Every provider response passes through `ContextRepairEngine.parse_and_validate`,
which **rejects, safely and silently**, anything that:

- is not valid JSON in the expected shape;
- references an unknown segment id;
- is a no-op or an empty string;
- changes segment length beyond a sane band (0.4×–2.5×);
- drops below a similarity floor against the original (blocks rewrites/summaries).

A correction that introduces a proper-noun-like token **not** present in the
original text and **not** in the approved names/glossary is downgraded to
`needs_review` rather than silently proposed — so the model can never quietly
invent a name and force it into the transcript. If the whole response is
unparseable, or the provider errors, the pass yields no corrections and never
touches the transcript.

### Review workflow (reversible)

Corrections are collected in a `CorrectionSet`. Each carries the original text,
proposed text, reason, confidence, and a status
(`proposed` / `needs_review` / `accepted` / `rejected`). `reviewed_segments`
returns a **fresh** projection with only *accepted* corrections applied; the
normalized layer is never mutated, so rejecting a correction is a pure no-op and
the original text is always recoverable. Accept/reject is available per segment
and in bulk (`accept_all`, `reject_all`, optionally including `needs_review`).

## Context & Names

`propose_entity_candidates` deterministically suggests likely topic/proper-noun
terms from repeated capitalized transcript tokens and the source filename, with
the supporting evidence and count. These are **proposals** for the Context &
Names panel: they are shown for approval and never auto-applied. Approved terms
feed both the whisper prompt and Context Repair. `build_whisper_prompt` builds
the sanitized, length-limited initial prompt (mirroring `WhisperWrapper`
sanitization) from the approved title, names, and glossary — recording aliases
such as "King Tut" / "Tutankhamun".

## Persistence

Each layer serialises via `to_dict` / `from_dict`. Recommended on-disk layout
inside a job keeps the layers in separate files
(`transcript_raw.json`, `transcript_normalized.json`,
`transcript_corrections.json`) so the raw file can be written once and never
rewritten; a store implementation should refuse to overwrite raw content whose
hash differs (`RawTranscriptImmutableError`).

## Pipeline integration (v1.0)

The layered model is wired into the live pipeline. After the Transcribe stage
succeeds, `JobController._build_normalized_transcript` parses the real
`transcript/raw.json`, builds the normalized layer, and writes:

- `transcript/normalized.json` — Layer 2 output (segments, paragraphs, and the
  recorded `raw_content_hash`);
- `transcript/context_candidates.json` — deterministic Context & Names proposals.

This step is best-effort and never fails the pipeline — the raw transcript
remains the source of truth if anything goes wrong. `ExportService` then emits a
paragraph-grouped `transcript.normalized.txt` in modes that produce a transcript
(Study Pack, Transcript Only). This wiring is verified end-to-end by
`tests/test_product_modes.py::test_normalized_matches_service`, which asserts the
pipeline's `normalized.json` equals a direct `transcript_service` run over the
same raw JSON and that the recorded raw hash matches.

### Context Repair workspace (v1.0.1)

The interactive Context Repair workspace (`ui/context_repair_dialog.py`, opened
from the review view) shows, per proposal: the **raw** (Layer 1) segment, the
**normalized** (Layer 2) segment, the **proposed** correction (editable), the
changed words highlighted (proper-name changes in a distinct colour), the reason,
and the confidence. Actions: Accept, Reject, Edit, Accept-all-high-confidence,
Reject-all; filters: low confidence / proper names / numbers-dates / unresolved /
accepted / rejected. Accepted corrections are written to `corrected.json` (the
user-approved layer); `corrections.json` holds the reversible set. Raw and
normalized files are never rewritten.

The workspace uses a local OpenAI-compatible LLM if one is configured, otherwise
the deterministic `DeterministicNameProvider` (approved-name fuzzy matching),
which cannot invent a name.

### Real-media finding: prompting vs. Context Repair (v1.0.1)

On a real Egypt-lecture excerpt with base.en, the Whisper initial `--prompt` did
**not** correct "Mark Lainer" → *Mark Lehner* (a real Egyptologist) or "dolarite"
→ *dolerite*, **even when those correct spellings were in the prompt**. Post-hoc
Context Repair, with the same terms as approved names, proposed exactly those
corrections for review. Takeaway: the Whisper prompt is a weak decoder bias;
review-based Context Repair is more effective for specific names — and, crucially,
never applies a name change without the user accepting it. Automatic transcription
is not perfect and this workflow keeps the uncertainty visible and under user
control. Evidence: `docs/evidence/v1.0.1/`.

## Tests

`tests/test_transcript_layers.py` (19 tests, standard-library only) covers layer
parsing and confidence, deterministic normalization, loop/duplicate handling,
context-repair schema validation and guardrails, the invented-name protection,
reversibility, and proof that raw/normalized layers and the source payload are
never mutated.
