# Handoff — Phase 2: "Premium Glassmorphic Dark" UI Overhaul

**Date:** 2026-07-19 · **Branch:** `phase-2-ui-overhaul` · **Status:** COMPLETE (pending user acceptance)

---

## What was built

Six milestones, each gated on the full pytest suite (209 passed, 0 failed):

| M | Deliverable | Commit |
|---|---|---|
| M1 | `ui/themes/dark_theme.qss` (Catppuccin Mocha, literal hex), Mocha palette + `MOCHA_*` constants + `load_qss` + `add_card_shadow` in `ui/theme.py` | `117d4a1` |
| M2 | `TranscriptBlockWidget` + `TranscriptStreamView` (lazy 120-block batches, capped live mode) + pure `bisect` sync helpers | `8e240df` |
| M3 | Frameless shell: `TitleBarWidget`, `AnimatedStackedWidget`, `QSizeGrip` | `970403b` |
| M4 | Spatial Study workspace: slides ⟷ transcript bidirectional sync, collapsible overview card, all v1.2 attributes/tests preserved | `16a4e51` |
| M5 | Process page: dropzone hero with drag glow, animated Advanced Settings drawer, block-based live transcript | `9631434` |
| M6 | Focus Mode (fades rail/bar/status, floating exit button, `Esc`/`Ctrl+Shift+F`) + docs | this commit |

Plan doc: `docs/PLAN_PHASE_2_UI.md` (`e9d4a6d`). Decisions: `docs/DECISIONS.md` AD-17.

## Evidence

- `tests/test_ui_phase2.py` — 38 new tests across M1–M6 (theme, blocks,
  lazy batching, sync helpers, title bar, animated stack, study sync,
  dropzone, drawer, focus mode).
- Full suite: **209 passed, 0 failed** (~149 s) after M5 and again before
  this handoff — includes all pre-existing suites unchanged
  (`test_ui_v11`, `test_study_workspace_v12`, pipeline/integration tests).

## Deliberately unchanged

- Controllers, services, infrastructure, persistence layers, Phase 1
  streaming contracts.
- Review/Transcript pages (they inherit the new dark theme automatically).
- `dark_theme` config default (dark stays opt-in via Settings — flipping it
  was outside the approved phase scope).
- All v1.2 Study-page object names, signals, and `meta_lbl` text format.

## Known tradeoffs (accepted in AD-17)

- Frameless window loses Windows 11 snap layouts and the native drop shadow.
- Study workspace shows accepted slides only.
- Live transcript is ephemeral view data (never persisted).

## Follow-ups for later phases

1. **Packaging:** add `lecturepack/ui/themes/*.qss` to the PyInstaller spec
   `datas` (Phase 5) — `theme.load_qss` degrades gracefully (logs, returns
   "") if the file is missing, so nothing crashes.
2. Consider making the dark theme the default for new installs (one-line
   config change; needs explicit approval).
3. Manual visual pass on a real machine: check glyph rendering (◆ ⇩ ◔ ◍ □ ▣),
   focus-mode geometry on multi-monitor DPI scales, and sync smoothness on a
   long (2 h+) lecture.
4. Optional: hide the review-decision context menu on the Study page's
   read-only slide grid.
