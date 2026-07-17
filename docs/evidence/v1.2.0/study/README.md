# v1.2 Study workspace evidence

Generated on 2026-07-16 from the native PySide6 source application using Qt
widget captures. Browser automation and browser URL verification were not
used.

## Reproduction and observed behavior

1. Create/open a completed Study Pack job with accepted candidates, aligned
   transcript, normalized confidence, and a persisted `backend_used` value.
2. Open the job: the stack lands on Study and displays title, duration,
   accepted-slide/transcript counts, actual backend, review count,
   deterministic overview, topics, and key terms.
3. In Review select a slide, toggle Bookmark, enter a short note, and move to
   another page. Reopen the job: bookmark, note, and resume position persist.
4. In Transcript > Sections select a section, toggle Bookmark section, and use
   Jump to first slide. The section is marked with a star and the nearest
   Review slide is selected.
5. Export again. HTML, PDF, and JSON contain user data; source/raw/candidate
   signatures remain byte-for-byte and timestamp-for-timestamp identical.

## Visual evidence

- `study-overview.png`: completed-job landing, actual backend, deterministic
  overview/key terms, quick actions, bookmarks, and resume.
- `review-bookmark-note.png`: selected slide with bookmarked state and the
  persisted short note beneath the preview.
- `section-bookmark-jump.png`: chronological Sections table, visible bookmark,
  and jump action.

## Automated results

- Focused: `6 passed in 3.84s` (`focused_pytest_output.txt`).
- Full suite: `127 passed in 153.06s` (`full_pytest_output.txt`).
- `results.json` records the restart state, actual backend, Study export
  SHA-256/size/timestamps, and before/after protected-artifact signatures.
- Protected set: `source.json`, `candidates.json`, raw transcript JSON, and all
  four candidate PNGs. Every SHA-256, byte size, and nanosecond mtime matched;
  `protected_artifacts_identical` is `true`.

The evidence generator is `tests/generate_study_evidence.py` and operates on a
temporary per-run job so it does not modify user lectures.
