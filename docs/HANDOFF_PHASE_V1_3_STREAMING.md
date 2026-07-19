# Handoff -- Phase v1.3: Incremental Transcript Streaming

**Date:** 2026-07-18
**Branch:** `phase-1-incremental-streaming`
**Status:** Complete, awaiting user acceptance + commit approval

---

## Completed

1. **Live segment streaming.** whisper.cpp stdout segment lines
   (`[HH:MM:SS.mmm --> HH:MM:SS.mmm] text`) are parsed incrementally and
   surface in the process page's new "Live transcript" pane while
   transcription runs. Signal chain:
   `WhisperWrapper.segment_ready` → `TranscriptionBackend.segment_ready` →
   `JobController.transcript_segment` → `ProcessPage.on_transcript_segment`.
2. **UI freeze fix.** Transcribe-stage log chunks are coalesced in
   `JobController` and flushed to `stage_log` on a 200 ms `QTimer` (plus a
   final flush before result handling). This removes the
   `QTextEdit.insertPlainText` relayout storm that froze the GUI during long
   transcriptions.
3. **Latency bugfix (included).** The old wrapper decoded each stdout chunk
   independently, mangling multi-byte UTF-8 split across reads. The new
   `LiveSegmentParser` buffers bytes and decodes complete lines only.
4. **Interface contract.** `BackendCapabilities.supports_live_segments`
   (local whisper.cpp: True, Groq online: False). The local adapter's relay
   is guarded with `getattr`, so wrappers without the signal still work.

## Files changed

- `lecturepack/infrastructure/whisper_wrapper.py` — `LiveSegmentParser`,
  `_segment_timestamp_to_ms`, `segment_ready` signal, end-of-process flush.
- `lecturepack/services/transcription_backends.py` — base signal, capability
  field, guarded relay.
- `lecturepack/controllers/job_controller.py` — `transcript_segment` relay,
  log throttle (`_flush_transcribe_log`).
- `lecturepack/ui/main_window.py` — one-line signal wiring.
- `lecturepack/ui/pages/process_page.py` — live transcript pane + slot.
- `tests/test_live_transcript_streaming.py` — 16 tests (parser, wrapper,
  backend, controller, end-to-end QProcess via streaming mock).
- `tests/fixtures/mock_whisper_streaming.py` — new streaming mock binary.
- `tests/test_transcription_backend_contract.py` — `FakeWhisperWrapper` gains
  `segment_ready` (strengthened, nothing weakened).
- `docs/DECISIONS.md` — AD-16 (incl. why JobController was NOT moved to a
  QThread). `docs/ARCHITECTURE.md` — v1.3 signal-flow note.

## Verification evidence

- Full suite: **174 passed, 0 failed** (126 s), including the 16 new tests.
  Command: `.venv\Scripts\python.exe -m pytest tests/` (pytest.ini collects
  only `test_*.py`).
- End-to-end proof: `test_end_to_end_live_segments_from_streaming_mock`
  drives the real QProcess path against a mock whisper binary that streams
  `\r`-polluted, UTF-8, unterminated segment lines.

## Explicitly not done (non-goals)

- True word-level streaming (requires whisper-stream engine swap — separate,
  risk-assessed phase).
- Groq online live segments (chunks merge at completion; capability flag
  says so).
- `JobController` thread move (rejected; rationale in AD-16).
- Commit: pending user approval.

## Remaining / follow-ups

- Manual smoke test with the real Vulkan whisper build is recommended
  (parser is regex-anchored to the classic format; unmatched lines degrade
  gracefully to log-only, as before).
- Optional: the one-time synchronous `--help` capability probe
  (`whisper_wrapper.get_supported_flags`, up to 5 s on cold cache) could be
  moved off the GUI thread in a future phase.
