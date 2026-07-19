# Full Egypt lecture — packaged run (v1.0.1)

One complete run of the 71.7-minute lecture through the **packaged** executable
(`LecturePack.exe --run-acceptance`), bundled ffmpeg + whisper-cli, model
`ggml-base.en.bin`. Study Pack mode. `ok: true`.

## Timings (packaged, real)

| Stage | Time |
|-------|------|
| Inspect | 0.09 s |
| Extract Audio | 3.14 s |
| Transcribe | 450.66 s (7.5 min) |
| Detect Slides | 378.11 s (6.3 min) |
| Align | 1.69 s |
| **Pipeline total** | **833.7 s (~13.9 min)** |

Source: 4300.4 s (71.7 min) video. Audio WAV 137 MB.

## Counts

- **Transcript segments:** 630 (json/jsonl/csv all parse with ordered timestamps).
- **Slide candidates:** 81 — `initial_frame` ×1, `major_change` ×79,
  `progressive_build` ×1. 80 accepted, 1 rejected (the re-export decision flip).
- **Context Repair proposals:** 27 real proposals (accept-one / reject-one
  exercised; reversible; raw hash `8422073e78a5…` preserved).

## Candidate distribution by 10-minute interval

| Interval | Candidates |
|----------|-----------|
| 0–10 min | 10 |
| 10–20 min | 11 |
| 20–30 min | 12 |
| 30–40 min | 16 |
| 40–50 min | 13 |
| 50–60 min | 14 |
| 60–70 min | 5 |

Even distribution; **only 2 adjacent candidate pairs are <8 s apart**. This is a
large improvement over the v0.2.0 finding (128 candidates with a 61-candidate
dense cluster in ~6 min): the v1.0 precision guards eliminated the cluster
explosion. No large fade/caption/pointer clusters.

## Visual review (begin / middle / end)

Contact sheets `detector/egypt_full_candidates_0.png` and `_1.png` show all 81
candidates. Every candidate is a distinct, meaningful state:

- **Begin (0–3 min):** course title, "EGYPT AND ARCHAEOLOGY", the **TODAY**
  agenda (which lists *Abu Simbel* and *Tutankhamun*), "WHAT IS ARCHAEOLOGY?".
- **Middle (11–28 min):** "THE GREAT PYRAMID", "BEFORE GIZA", step-pyramid
  evolution diagrams, Giza satellite maps, "TIMELINE OF EGYPTIAN DYNASTIES",
  Cheops/Khufu statue, pyramid cross-sections.
- **Later (29–35 min):** an embedded pyramid-construction **video** (map, pyramid
  animations, live presenter) — captured as distinct scene keyframes.

## Exports (sizes)

`slides.pdf` 48.8 MB · `study-pack.html` 65.3 MB · `transcript.txt` 68 KB ·
`.srt` 73 KB · `.json` 114 KB · `.md` 59 KB · `.jsonl` 84 KB · `.csv` 67 KB ·
`.vtt` 73 KB · `.normalized.txt` 48 KB · `.sections.md` 65 KB.

## Re-export

Flipped one slide decision and re-exported: audio, raw transcript, and candidate
PNGs all **unchanged** — audio extraction, Whisper, and slide detection did **not**
rerun (`no_rerun: true`).

## Notes / honesty

- Candidates were **not** all auto-accepted blindly by a human; the driver
  accepts detector output and exercises one accept + one reject in review. In real
  use you would curate the 81 candidates in the review UI.
- The `--names` argument was truncated by a PowerShell `Start-Process` quirk at the
  space in "Mark Lehner", so only `Egypt, Tutankhamun, Mark` registered as approved
  names for this run; it still produced 27 proposals. The app's `--names` parsing
  is correct (verified in the short run) — this was a shell-quoting artifact.
