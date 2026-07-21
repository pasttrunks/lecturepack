# Home job management — delete + grouping

## Delete (user-confirmed, recoverable)
- Each Home card has a trash button → confirmation modal ("Delete this lecture?
  … moved to the Recycle Bin … frees disk space") → `delete_job(job_id)`.
- Backend prefers `send2trash` (OS Recycle Bin — recoverable AND frees the data
  dir); hard `shutil.rmtree` only as a fallback. Guarded: safe job-id regex + the
  target must resolve directly under `jobs/` (traversal/absolute rejected). Never
  runs automatically — only from the explicit UI confirmation. Reports freed size.

## Grouping (by course / subject)
- Each card has a tag button → input modal to set the group; persisted in the job
  manifest (`group`). Blank reverts to a title-derived default
  (`"CL100 - Day 3 - …"` → `CL100`; `"Biology: cells"` → `Biology`).
- Home renders one section per group with a header + count (single group → no
  header). `_list_jobs` now emits `group` per job.

## Evidence
- Unit tests: `tests/test_webview_jobs.py` (12) — group derivation, list group,
  set/clear group, delete (recycle + hard-delete fallback), unknown-job failure,
  traversal-id rejection. send2trash monkeypatched to avoid touching the real
  Recycle Bin; all against a TEMP data dir, never real jobs.
- Non-destructive UI smoke (`home_jobs_smoke.py`) → HOME_OK: 17 cards, 3 course
  sections, delete + group modals open and Cancel closes them (nothing confirmed).

## Safety note
No real user job was deleted or modified during development/testing. send2trash
added to requirements.txt.
