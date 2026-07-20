# LecturePack Studio UI Fidelity Rebuild

## Overview

Complete pixel-level rebuild of the PySide6 LecturePack application to match the
`LecturePack Studio.dc.html` design comp at 1360×860 viewport. Every page was
torn down and rebuilt with correct Studio layouts, spacing, typography, and color
tokens — while preserving all existing business logic, signals, and the 38/38
test suite.

**Branch:** `v1.2-hybrid-study`
**Date:** July 2026
**Result:** 38/38 tests passing, app launches and runs cleanly

---

## What Changed

### 1. Theme System (`lecturepack/ui/theme.py`)

**Added `load_fonts()` function** — loads Space Grotesk (400–700) and JetBrains Mono (400–700) from the `fonts/` directory via `QFontDatabase.addApplicationFont`.

**Extended QSS generation** in `_qss(dark)`:
- Scrollbar styling (thin, themed thumb/track)
- Radio button and checkbox styling
- QLineEdit, QComboBox, QTextEdit input styling
- QPushButton base styling
- Nav button SVG icon color via `color` property

**Key constants (unchanged):**
| Token | Light | Dark |
|-------|-------|------|
| `--bg` | `#F3F0E8` | `#131519` |
| `--panel` | `#FFFFFF` | `#1B1E24` |
| `--ink` | `#1C1A16` | `#ECE7DB` |
| `--blue` | `#0E82C4` | `#38ADE8` |
| `--orange` | `#EF5A1E` | `#FF6C36` |
| `--green` | `#128A52` | `#3DDC97` |
| `--red` | `#D63A2C` | `#F06060` |

---

### 2. Sidebar SVG Icons (`lecturepack/ui/main_window.py`)

Replaced Unicode glyphs (⌂ ▶ ▦ ¶ ◇ ⇩ ⚙) with proper SVG icons matching the
Studio mockup exactly.

**Icon definitions** (`_NAV_SVG` dict):
| Page | Icon | SVG Source |
|------|------|-----------|
| Home | House with door | `<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>` |
| Process | Stacked layers (3 tiers) | 3-layer stack SVG |
| Review | Square split vertically | `<rect>` + `<path d="M12 3v18"/>` |
| Transcript | Three horizontal lines | 3 `<path>` elements |
| Study | Graduation cap | Mortarboard SVG |
| Exports | Download arrow + tray | Arrow + tray SVG |
| Settings | Gear with inner circle | Full gear path + `<circle>` |

**Helper function** `_nav_icon(name, dark)`:
- Replaces `currentColor` in SVG with theme-appropriate hex (`#1C1A16` light / `#ECE7DB` dark)
- Converts SVG bytes → `QImage` → `QPixmap` → `QIcon`
- Returns `QIcon` for the nav button

**Button creation** `_make_nav_btn()`:
- Uses `ToolButtonTextBesideIcon` style (icon left, text right)
- `setIconSize(QSize(19, 19))` — matches mockup
- `setFixedHeight(38)` — matches sidebar row height

**Theme integration**:
- `_refresh_nav_icons()` iterates all 7 nav buttons, detects dark mode via `palette().window().color().lightness() < 128`, and updates all icons
- Called after initial theme application in `__init__`
- Called in `_on_theme_changed()` on every theme toggle

---

### 3. Home Page (`lecturepack/ui/pages/home_page.py`)

**Before:** Simple `QVBoxLayout` with title, drop card, `QListWidget` for jobs.

**After (Studio layout):**
- **1140px max-width** centered content area
- **Hero section:** eyebrow text ("Local · Private · No account required"), 40px headline ("Turn lectures into study material"), 16px subtitle
- **Upload card:** Blue left accent bar (`4px solid var(--blue)`), video icon, "Drop a lecture video here" text, Browse button (blue bg, white text)
- **3-column job card grid:** Each card has thumbnail placeholder (118px), title, source filename, created date, status badge (Processing/Ready/Failed with colored dot)

**Preserved signals/attributes:**
- `video_chosen` signal, `job_selected` signal
- `refresh_jobs()` method
- `_JobCard` inner class with `job_id`, `source` properties

---

### 4. Process Page (`lecturepack/ui/pages/process_page.py`)

**Before:** `DropzoneHero` + `CollapsibleGroups` + splitter.

**After (Studio layout):**
- **Root: `QSplitter`** (horizontal) — satisfies `main_window.py` state save/restore
- **Left: `advanced_drawer`** (slides in/out, max-width 380px)
  - Transcription card: `transcription_mode_combo`, `profile_combo`, `engine_combo`, `vad_chk`
  - Slide detection card: `preset_combo`
  - Diagnostics card: `diag_lbl`
- **Right: main column**
  - Source card: `DropzoneHero`, `video_path_edit`, Browse button, metadata labels
  - Output mode card: `product_mode_combo`
  - Start/retranscribe/advanced-toggle buttons
  - Pipeline progress card: `StageRow` widgets
  - Live transcript: `TranscriptStreamView`
  - Live log card: collapsible log viewer

**Animation:** `set_advanced_open(True/False)` toggles drawer max-width between 0 and 380 with `QEasingCurve.OutCubic`.

**Test constraints satisfied:**
- Settings widgets are inside `advanced_drawer`
- `product_mode_combo`, `start_btn`, `video_path_edit` are NOT inside drawer
- `self.splitter` exists for main_window.py persistence

---

### 5. Review Page (`lecturepack/ui/pages/review_page.py`)

**Before:** `QSplitter` with `slides_view`, `preview_lbl`, `transcript_table`.

**After (Studio layout):**
- **3-column splitter:** 250px slides | flexible preview | 360px transcript
- **Slide list panel:** `SlideGridWidget` with grid/list mode toggle buttons
- **Preview panel:** Centered slide image with `slide_info_lbl` overlay
- **Transcript panel:** Search input, timestamps checkbox, copy format combo, `QTableWidget`
- Studio-styled split handles (3px wide, themed color)

**Preserved signals:**
- `status_message`, `selection_count_changed`, `open_context_repair`
- `study_data_changed`, `position_changed`

**Preserved attributes:**
- `splitter`, `slides_view`, `preview_lbl`, `slide_info_lbl`
- `transcript_table`, `search_input`, `timestamps_chk`, `copy_format_combo`

---

### 6. Transcript Page (`lecturepack/ui/pages/transcript_page.py`)

**Before:** Full-width with tabs.

**After (Studio layout):**
- **960px max-width** centered reading column
- **Studio toolbar:** Search input, format combo, copy all/selected buttons
- **4 tabs** (styled as Studio tabs):
  1. Full Transcript — `full_view` (QTextEdit)
  2. Segments — `seg_table` (QTableWidget) + `seg_editor` (QTextEdit)
  3. Sections — `sections_table` (QTableWidget)
  4. Context Repair — `ContextRepairPanel`
- Segment editor with Studio-styled action buttons (Accept/Reject/Reset)

**Preserved signals:**
- `seek_requested`, `status_message`, `study_data_changed`, `position_changed`

**Preserved attributes:**
- `tabs`, `seg_splitter`, `seg_table`, `sections_table`, `full_view`, `seg_editor`

---

### 7. Study Page (`lecturepack/ui/pages/study_page.py`)

**Before:** Splitter with `slides_grid` + `transcript_view`.

**After (Studio layout):**
- **1140px max-width** with 3-column layout
- **Left (200–260px):** Slide timeline header, `SlideGridWidget` in scroll area
- **Center (flexible):** Overview card (collapsible via `overview_toggle`/`overview_body`), transcript with `TranscriptStreamView`, Resume button
- **Right (200–280px):** Topics list, Slide bookmarks, Section bookmarks

**Bidirectional sync preserved:**
- Slide click → transcript seeks
- Transcript scroll → nearest slide highlighted
- Block click → slide selected without navigating
- `_programmatic_scroll` guard prevents feedback loops

**Preserved signals:**
- `navigate_requested`, `seek_requested`, `resume_requested`

---

### 8. Exports Page (`lecturepack/ui/pages/exports_page.py`)

**Before:** Checkbox card + table.

**After (Studio layout):**
- **960px max-width** centered content
- **Heading:** "Export study pack" with path pill (shows output directory)
- **2 export cards** side by side: PDF card + HTML card
- **4×2 format tile grid:** SRT, TXT, JSON, VTT, CSV, DOCX, TSV (+ PNG images)
- **Blue CTA banner:** Summary text + orange Export button
- **Artifacts table:** Lists previously exported files

**Preserved:**
- `export_requested` signal, `set_job()`, `refresh_artifacts()`
- All format checkboxes, `export_btn`

---

### 9. Settings Page (`lecturepack/ui/pages/settings_page.py`)

**Before:** Raw form rows.

**After (Studio layout):**
- **800px max-width** centered content
- **Studio cards grouped by category:**
  1. Whisper Model — model dropdown, path display
  2. Compute Engine — engine combo (Local/Groq)
  3. Local AI Endpoint — Ollama URL, model selector, test button
  4. Groq — API key input
  5. Appearance — Theme toggle (Light/Dark)
  6. Privacy — Blue accent card explaining local-only processing

**Preserved:**
- `theme_changed` signal, `settings_changed` signal
- `_load_settings()` method, all widget references

---

## Files Modified

| File | Lines | Key Changes |
|------|-------|-------------|
| `lecturepack/ui/theme.py` | 488 | `load_fonts()`, extended QSS (scrollbars, inputs, buttons) |
| `lecturepack/ui/main_window.py` | ~1445 | SVG icon system (`_NAV_SVG`, `_nav_icon()`, `_refresh_nav_icons()`) |
| `lecturepack/ui/pages/home_page.py` | 304 | Hero section, upload card, 3-column job grid |
| `lecturepack/ui/pages/process_page.py` | ~640 | Splitter layout, drawer, Studio cards |
| `lecturepack/ui/pages/review_page.py` | ~730 | 3-column splitter (250/flex/360) |
| `lecturepack/ui/pages/transcript_page.py` | ~855 | 960px centered, Studio toolbar, 4 tabs |
| `lecturepack/ui/pages/study_page.py` | ~500 | 3-column (topics/overview+transcript/bookmarks) |
| `lecturepack/ui/pages/exports_page.py` | ~220 | 960px, export cards, format grid, CTA banner |
| `lecturepack/ui/pages/settings_page.py` | ~470 | 800px, Studio cards by category |

---

## Design Token Reference

### Typography
| Role | Font | Weight | Size |
|------|------|--------|------|
| Headline | Space Grotesk | 700 | 40px |
| Card title | Space Grotesk | 700 | 16px |
| Body | Space Grotesk | 400 | 14px |
| Button | Space Grotesk | 600 | 13.5px |
| Section label | JetBrains Mono | 500 | 10px |
| Timestamp | JetBrains Mono | 400 | 12px |

### Spacing
| Element | Value |
|---------|-------|
| Header height | 56px |
| Sidebar width | 224px |
| Footer height | 34px |
| Card border-radius | 11px |
| Card padding | 16–20px |
| Nav button height | 38px |
| Card shadow | `0 2px 8px rgba(0,0,0,0.08)` |

### Layout Max-Widths
| Page | Max-Width |
|------|-----------|
| Home | 1140px |
| Process | No max (full splitter) |
| Review | No max (full splitter) |
| Transcript | 960px |
| Study | 1140px |
| Exports | 960px |
| Settings | 800px |

---

## Test Results

```
38 passed in ~11s — tests/test_ui_phase2.py

M1 (Theme): 6/6 passed
M2 (TranscriptBlock): 8/8 passed
M3 (TitleBar): 5/5 passed
M4 (StudyPage): 6/6 passed
M5 (ProcessPage): 5/5 passed
M6 (FocusMode): 3/3 passed
Main Window: 5/5 passed
```

No test dependencies were broken. All widget attributes, signals, and method
signatures referenced by tests are preserved.

---

## Bug Fixed During Rebuild

**`home_page.py:102` — `NameError: name 'source' is not defined`**

The `_build()` method referenced bare `source` instead of `self.source`. Fixed:
```python
# Before
source_name = os.path.basename(source) if source else ""
# After
source_name = os.path.basename(self.source) if self.source else ""
```

---

## What Was NOT Changed

- All business logic methods (unchanged line-for-line)
- All signal definitions and connections
- All widget attribute names referenced by `main_window.py` and tests
- `SlideGridWidget`, `TranscriptStreamView`, `ContextRepairPanel` widgets
- `FocusModeController`, `AnimatedStackedWidget`
- Job controller, file manager, constants
- `capture_screens.py`, `build_release.py`
- Any test files
