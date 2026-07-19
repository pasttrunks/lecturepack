# v1.2 Study workspace evidence

Generated on 2026-07-17 from the native PySide6 source application using Qt widget captures. Browser automation was not used.

## Reproduction and observed behavior

1. Create or open a completed Study Pack job with accepted candidates, aligned transcript, normalized confidence, and a persisted `backend_used` value.
2. Open the job: the application automatically lands on the Study workspace page by default. It displays the lecture title, duration, accepted-slide/transcript counts, actual backend, review count, deterministic overview, topics, and key terms.
3. Click "Review slides": it navigates to the slide review screen. Selecting a slide, toggling Bookmark (star icon), entering a short personal note in the edit box, and moving to another page preserves this user state in `study.json`. Reopening the job restores the bookmark and note.
4. Click "Read transcript" and go to the "Sections" tab: selecting a section, toggling "Bookmark section", and clicking "Jump to first slide" updates the state. The section is marked with a star in the table and the nearest slide is selected in the review page.
5. Export again. The HTML study pack (`study-pack.html`), study-pack PDF (`study-pack.pdf`), and study-data JSON (`study-data.json`) all contain user annotations clearly labeled, while source/raw/candidate signatures remain byte-for-byte and timestamp-for-timestamp identical.

## Visual evidence

- `study-overview.png`: completed-job landing page showing the resizable three-column layout, actual backend, deterministic overview/key terms, quick actions, bookmarks list, and last study position resume button.
- `review-bookmark-note.png`: selected slide with bookmarked state and the persisted personal note beneath the preview area.
- `section-bookmark-jump.png`: chronological Sections table, visible bookmark status, and jump-to-first-slide action.

## Automated results

- Focused: `9 passed in 4.14s` (`focused_pytest_output.txt`).
- Full suite: verified passing in `full_pytest_output.txt`.
- `results.json` records the restart state, actual backend, Study export signatures, and before/after protected-artifact signatures.
- Protected set: `source.json`, `candidates.json`, raw transcript JSON, and all candidate PNGs. Every SHA-256, byte size, and nanosecond modification time matched; `protected_artifacts_identical` is `true`.

## Old-job compatibility result
Opening an old job with missing or absent `study.json` materializes a clean empty state without throwing migration failures. No database modifications are performed, and `study.json` is only written when a bookmark, note, or position is saved by the user.

## Persistence result
All personal study data (bookmarks, slide notes, section notes, last viewed position) are persisted in `study.json` separately from the raw transcript and candidate images, ensuring that source-derived content remains 100% immutable.
