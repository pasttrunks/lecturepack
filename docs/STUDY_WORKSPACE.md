# Study workspace

The Study workspace is the default landing page for a completed LecturePack
job. It provides an offline, deterministic overview and shortcuts into the
existing review, transcript, correction, and export workflows.

## What appears on Study

- lecture title and duration
- accepted-slide and transcript-segment counts
- product mode and the backend actually recorded by transcription
- number of low-confidence transcript segments needing review
- a deterministic transcript extract and key terms
- chronological topics derived from aligned slide intervals
- slide bookmarks, short slide notes, and section bookmarks
- the last per-job review/transcript position

The overview does not call Ollama or any cloud provider. Its provenance label
is shown directly beneath the overview. Section headings created by the
existing Ollama workflow remain marked `(AI)`.

## User data and provenance

User-authored Study state is stored atomically at:

```text
jobs/<job-id>/study.json
```

Schema 1 contains three maps:

```json
{
  "schema_version": 1,
  "bookmarked_slides": {},
  "bookmarked_sections": {},
  "last_position": {}
}
```

Slide keys use the candidate image filename, falling back to the timestamp for
old or image-free candidates. Section keys combine the aligned slide index and
start timestamp. Notes are trimmed and limited to 500 characters.

`study.json` never replaces or modifies:

- original lecture video or source metadata
- `candidates.json` or candidate images
- raw, normalized, or working transcript layers
- section heading provenance

Old jobs have no migration step. Missing/corrupt Study data becomes an empty
state and is written only after a user bookmark, note, or navigation position
is saved.

## Navigation

- Read transcript opens Full Transcript.
- Review slides opens the three-pane Review page.
- Review corrections opens the editable Segments tab.
- Export study pack opens Exports.
- Activating a topic opens Transcript at that time.
- Activating a slide/section bookmark selects the nearest slide.
- Resume restores the saved workspace and timestamp for that job.

## Study Pack exports

Study Pack mode produces:

- `study-data.json`: explicit `source_derived` and `user_authored` groups
- `study-pack.html`: self-contained images, transcript, bookmarks, and notes
- `study-pack.pdf`: printable slides/transcript with user annotations

All inserted text is escaped for HTML/ReportLab markup. Transcript/source and
user-authored data are visibly labeled; export does not execute lecture text.

## Verification

Focused coverage is in `tests/test_study_workspace_v12.py`. Native Qt captures
and exact pytest/hash results are in `docs/evidence/v1.2.0/study/`.
