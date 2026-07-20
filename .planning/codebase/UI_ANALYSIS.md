# Studio UI Comprehensive Analysis

**Analysis Date:** 2026-07-19

## 1. Theme System (`lecturepack/ui/theme.py`)

### Color Tokens

**Shared Semantic Colors (498 lines total):**
- `PRIMARY = "#F15A24"` (orange), `PRIMARY_HOVER = "#D94812"`, `PRIMARY_SOFT_LIGHT = "#FBE2D5"`, `PRIMARY_SOFT_DARK = "#3B241A"`
- `SECONDARY = "#159EAE"` (teal), `SECONDARY_HOVER = "#0C7F8D"`, `SECONDARY_SOFT_LIGHT = "#DDF3F4"`, `SECONDARY_SOFT_DARK = "#15353A"`
- `DANGER = "#D63A2C"`, `SUCCESS = "#128A52"`, `WARNING = "#D99400"`
- `ACCENT = PRIMARY` (alias)

**Dark Palette (16 tokens):**
- `DARK_BG = "#121417"`, `DARK_PANEL = "#1B1F23"`, `DARK_PANEL2 = "#22272D"`, `DARK_SUNK = "#15191D"`
- `DARK_INK = "#F0E9DF"`, `DARK_MUTED = "#949BA5"`, `DARK_BORDER = "#090A0C"`, `DARK_LINE = "#30363D"`
- `DARK_PRIMARY = "#FF6B35"`, `DARK_PRIMARY_HOVER = "#FF8259"`, `DARK_PRIMARY_SOFT = "#3B241A"`, `DARK_PRIMARY_INK = "#FF9A76"`
- `DARK_SECONDARY = "#45C6D3"`, `DARK_SECONDARY_HOVER = "#69D7E0"`, `DARK_SECONDARY_SOFT = "#15353A"`, `DARK_SECONDARY_INK = "#A6EBEF"`
- `DARK_GREEN = "#4CCB86"`, `DARK_GREEN_SOFT = "#123020"`, `DARK_RED = "#FF6E5E"`, `DARK_RED_SOFT = "#361715"`
- `DARK_YELLOW = "#F2C24A"`, `DARK_YELLOW_SOFT = "#332810"`, `DARK_NAV_INK = "#AEB3BF"`

**Light Palette (16 tokens):**
- `LIGHT_BG = "#F4EFE6"`, `LIGHT_PANEL = "#FFFFFF"`, `LIGHT_PANEL2 = "#F9F5ED"`, `LIGHT_SUNK = "#EEE8DD"`
- `LIGHT_INK = "#1D1915"`, `LIGHT_MUTED = "#81786B"`, `LIGHT_BORDER = "#2A241E"`, `LIGHT_LINE = "#DDD3C4"`
- `LIGHT_PRIMARY = "#F15A24"`, `LIGHT_PRIMARY_HOVER = "#D94812"`, `LIGHT_PRIMARY_SOFT = "#FBE2D5"`, `LIGHT_PRIMARY_INK = "#B73A0B"`
- `LIGHT_SECONDARY = "#159EAE"`, `LIGHT_SECONDARY_HOVER = "#0C7F8D"`, `LIGHT_SECONDARY_SOFT = "#DDF3F4"`, `LIGHT_SECONDARY_INK = "#095F69"`
- `LIGHT_GREEN = "#128A52"`, `LIGHT_GREEN_SOFT = "#D3F0DF"`, `LIGHT_RED = "#D63A2C"`, `LIGHT_RED_SOFT = "#FADAD5"`
- `LIGHT_YELLOW = "#D99400"`, `LIGHT_YELLOW_SOFT = "#FBEDC6"`, `LIGHT_NAV_INK = "#4A4438"`

**Font Stacks:**
- `FONT_STACK = '"Space Grotesk", "Segoe UI", Inter, sans-serif'`
- `FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'`

### QSS Generation

The `_qss(dark)` function (line 172) generates QSS by:
1. Mapping token constants to local variables based on `dark` flag
2. Returning an f-string with ~230 lines of QSS covering: header, sidebar, job status card, footer, common elements, scroll bars, radio/checkbox, line edit, combo box, text edit, push button

### Font Sizes in QSS

| Selector | Font Size | Weight | Font |
|----------|-----------|--------|------|
| `QLabel#LogoDiamond` | 11px | — | — |
| `QLabel#AppBreadcrumb` | 13px | 500 | FONT_STACK |
| `QToolButton#ThemeToggleBtn` | 12px | 600 | FONT_MONO |
| `QToolButton#HeaderSaveBtn` | 13.5px | 600 | FONT_STACK |
| `QToolButton#HeaderExportBtn` | 13.5px | 600 | FONT_STACK |
| `QLabel#SidebarSectionLabel` | 10px | 500 | FONT_MONO |
| `QToolButton[navButton]` | 13.5px | 600 | FONT_STACK |
| `QLabel#JobCardTitle` | 13px | 700 | — |
| `QLabel#JobCardStatus` | 10px | 500 | FONT_MONO |
| `QLabel#FooterStage` | 11px | 600 | FONT_MONO |
| `QLabel#FooterElapsed` | 11px | 500 | FONT_MONO |
| `QLabel#FooterEngine` | 11px | 500 | FONT_MONO |
| `QLabel[h1]` | 18px | 700 | — |
| `QLabel[h2]` | 14px | 600 | — |
| `QPushButton[primary]` | — | 700 | — |
| `QPushButton[danger]` | — | 600 | — |
| `QLineEdit` | 13px | 500 | FONT_STACK |
| `QComboBox` | 13px | 500 | FONT_STACK |
| `QTextEdit/QPlainTextEdit` | 13px | 500 | FONT_STACK |
| `QPushButton` (default) | 13px | 600 | FONT_STACK |
| `QRadioButton` | 13px | — | — |
| `QCheckBox` | 13px | — | — |

### CSS Variables

**Not used.** The QSS uses hex literal interpolation (`{variable}`) in f-strings. The test `test_qss_uses_literal_hex_not_css_variables` explicitly asserts `"var(" not in qss`.

### Helper Functions

- `selection_visuals(selected, focused, decision, dark)` (line 110): Returns dict with outline_color, outline_width, background, checkmark_visible, checkmark_bg, focus_ring_visible, focus_ring_color, decision_badge_color
- `add_card_shadow(widget, blur=14.0, y_offset=6.0, alpha=90)` (line 464): Attaches QGraphicsDropShadowEffect
- `load_fonts()` (line 475): Loads .ttf/.otf from `lecturepack/ui/fonts/` via QFontDatabase
- `load_qss(filename)` (line 451): Reads QSS file from `themes/` subdirectory
- `apply_theme(app, dark)` (line 485): Master theme application — loads fonts, sets Fusion style, applies palette, generates QSS, appends dark_theme.qss if dark
- `is_dark(app)` (line 496): Reads `lp_dark_theme` property from QApplication

---

## 2. Dark Theme QSS (`lecturepack/ui/themes/dark_theme.qss`)

### All Selectors (239 lines)

| Lines | Selector | Purpose |
|-------|----------|---------|
| 7-10 | `*` (global) | font-family, font-size: 13px |
| 11-17 | `QToolTip` | background, color, border, border-radius, padding |
| 20-48 | `QScrollBar:vertical`, `QScrollBar:vertical::handle`, `::add-line`, `::sub-line`, `::add-page`, `::sub-page`, `QScrollBar:horizontal` + variants | Scrollbar styling |
| 51-78 | `QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit` + `:focus` | Input styling |
| 63-78 | `QComboBox::drop-down`, `::down-arrow`, `QComboBox QAbstractItemView` | Combo box dropdown |
| 81-91 | `QPushButton` + `:hover`, `:pressed`, `:disabled` | Button styling |
| 93-97 | `QToolButton` | Transparent tool buttons |
| 100-117 | `QListWidget, QTreeView, QTableView` + `::item`, `::item:selected`, `::item:hover` | List/tree/table styling |
| 120-136 | `QGroupBox` + `::title` | Group box with uppercase mono title |
| 139-159 | `QTabWidget::pane`, `QTabBar::tab` + `:selected`, `:hover:!selected` | Tab styling |
| 162-172 | `QProgressBar` + `::chunk` | Progress bar |
| 175-177 | `QSplitter::handle` + `:horizontal`, `:vertical` | Splitter handles |
| 180-195 | `QCheckBox, QRadioButton` + `::indicator` + `:checked` | Checkbox/radio indicators |
| 198-208 | `QMenu` + `::item`, `::item:selected` | Context menu |
| 211-225 | `QToolButton[titleBarButton="true"]` + `:hover`, `#titleBarClose:hover` | Title bar buttons |
| 228-239 | `QPushButton#focusModeExitBtn` + `:hover` | Focus mode exit button |

### Overly Broad Selectors

| Selector | Issue | Risk |
|----------|-------|------|
| `*` (line 7) | Sets font-family and font-size: 13px for ALL widgets | Overrides any widget-specific font settings; may conflict with inline stylesheets |
| `QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit` (line 51) | Bare type selector — no object name or property qualifier | Applies to ALL input widgets globally, including those that may need different styling |
| `QListWidget, QTreeView, QTableView` (line 100) | Bare type selector | Applies to ALL list/tree/table views globally |
| `QPushButton` (line 81) | Bare type selector | Applies to ALL push buttons, may override `[primary="true"]` and `[danger="true"]` specificity |
| `QToolButton` (line 93) | Bare type selector | Transparent background for ALL tool buttons |
| `QCheckBox, QRadioButton` (line 180) | Bare type selector | Color set for ALL checkboxes/radios |

### Hardcoded Hex Values

All 239 lines use hex literals: `#1B1F23`, `#F0E9DF`, `#30363D`, `#15353A`, `#45C6D3`, `#FF6B35`, `#22272D`, `#15191D`, `#949BA5`, `#3D4450`, `#FF6E5E`, `#121417`

---

## 3. Main Window (`lecturepack/ui/main_window.py`)

### Shell Layout

```
QMainWindow (FramelessWindowHint)
└── central QWidget
    └── root QVBoxLayout (margins: 0, spacing: 0)
        ├── HeaderBarWidget (fixedHeight: 56)
        ├── body QWidget
        │   └── hb QHBoxLayout (margins: 0, spacing: 0)
        │       ├── sidebar QWidget (objectName: "NavSidebar", fixedWidth: 224)
        │       │   └── sl QVBoxLayout (margins: 12,14,12,14, spacing: 4)
        │       │       ├── _job_card QFrame (fixedHeight: 70, initially hidden)
        │       │       ├── "Library" QLabel (SidebarSectionLabel)
        │       │       ├── home_btn QToolButton
        │       │       ├── "Workspace" QLabel (SidebarSectionLabel)
        │       │       ├── process_btn, review_btn, transcript_btn, study_btn QToolButtons
        │       │       ├── "Output" QLabel (SidebarSectionLabel)
        │       │       ├── exports_btn QToolButton
        │       │       ├── stretch
        │       │       └── settings_btn QToolButton
        │       └── AnimatedStackedWidget (stretch: 1)
        │           ├── [0] HomePage
        │           ├── [1] ProcessPage
        │           ├── [2] ReviewPage
        │           ├── [3] TranscriptPage
        │           ├── [4] ExportsPage
        │           ├── [5] SettingsPage
        │           └── [6] StudyPage
        └── footer QFrame (objectName: "AppStatusFooter", fixedHeight: 34)
            └── fl QHBoxLayout (margins: 18,0,18,0, spacing: 15)
                ├── sb_stage QLabel ("Idle")
                ├── sb_progress QProgressBar (maxWidth: 200, maxHeight: 7)
                ├── sb_elapsed QLabel
                ├── stretch
                ├── sb_warn QLabel
                ├── sb_engine QLabel
                └── QSizeGrip
```

### SVG Icons

7 inline SVG icons in `_NAV_SVG` dict (lines 62-70), themed via `currentColor` replacement in `_nav_icon()`:
- Home: house icon
- Process: layers icon
- Review: grid icon
- Transcript: lines icon
- Study: book icon
- Exports: download icon
- Settings: gear icon

All SVGs: 19x19, stroke-only, stroke-width 2, linecap/linejoin round.

### Navigation

- `PAGES = ["Home", "Process", "Review", "Transcript", "Exports", "Settings", "Study"]`
- `NAV_PAGE_ORDER = [PAGE_HOME, PAGE_STUDY, PAGE_PROCESS, PAGE_REVIEW, PAGE_TRANSCRIPT, PAGE_EXPORTS, PAGE_SETTINGS]`
- Nav buttons: `QToolButton` with `setProperty("navButton", True)`, fixedHeight 38, checkable, text-beside-icon style
- Section groups: Library (Home), Workspace (Process, Review, Transcript, Study), Output (Exports), Settings (bottom)

### Footer

- Fixed height 34px
- Contains: stage label, progress bar (maxWidth 200, maxHeight 7), elapsed timer, engine info, warning text, QSizeGrip for frameless resize

---

## 4. All 7 Pages — Detailed Analysis

### 4.1 HomePage (`home_page.py`, 304 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QScrollArea (resizable, NoFrame, no horizontal scroll)
    └── container QWidget (margins: 44,36,44,52, AlignHCenter)
        └── wrapper QWidget (maxWidth: 1140)
            ├── eyebrow QLabel ("Local · Private · No account")
            ├── headline QLabel ("Turn lecture recordings into study packs.")
            ├── subtitle QLabel
            ├── drop_card QFrame (card=true, borderRadius: 16px)
            │   └── QHBoxLayout
            │       ├── accent_bar QFrame (fixedWidth: 5, orange)
            │       ├── icon_box QFrame (52x52, teal bg)
            │       ├── drop_info QVBoxLayout
            │       │   ├── drop_title QLabel
            │       │   └── drop_sub QLabel
            │       └── browse_btn QPushButton
            ├── jobs_header QHBoxLayout
            │   ├── "RECENT JOBS" QLabel
            │   ├── _jobs_count_lbl QLabel
            │   ├── archive_btn QPushButton
            │   ├── restore_btn QPushButton
            │   └── export_archive_btn QPushButton
            ├── _jobs_grid QGridLayout (spacing: 18)
            └── stretch
```

**Font Sizes Hardcoded:**
- Eyebrow: `"font: 500 11px monospace"` (line 144)
- Headline: `"font-size: 40px"` (line 152)
- Subtitle: `"font-size: 16px"` (line 162)
- Drop title: `"font-size: 18px"` (line 191)
- Drop sub: `"font: 500 12px monospace"` (line 194)
- Browse btn: `"font: 600 15px sans-serif"` (line 200)
- Jobs header: `"font: 500 12px monospace"` (line 214)
- Job card title: `"font-size: 16px"` (line 99)
- Job card meta: `"font: 500 11px monospace"` (line 105)
- Badge: `"font: 600 10px monospace"` (line 86)

**Color References:**
- Hardcoded hex: `#159EAE`, `#81786B`, `#F15A24`, `#D94812`, `#DDF3F4`, `#095F69`, `#FFF`, `#D3F0DF`, `#128A52`, `#FADAD5`, `#D63A2C`, `#FBE2D5`, `#B73A0B`, `#F9F5ED`
- Theme tokens: None used directly in inline styles

**Scroll Area:** Yes — wraps all content with `setWidgetResizable(True)` and `setFrameShape(NoFrame)`

**Empty State:** No explicit empty state — grid is simply empty when no jobs exist

**Clipping Risks:**
- `wrapper.setMaximumWidth(1140)` — content clips above 1140px viewport
- `headline.setMaximumWidth(680)` — headline clips
- `subtitle.setMaximumWidth(540)` — subtitle clips
- `_JobCard.setFixedHeight(210)` — may clip long titles
- `thumb.setFixedHeight(118)` — fixed thumbnail height

---

### 4.2 ProcessPage (`process_page.py`, 706 lines)

**Widgets & Layout:**
```
QHBoxLayout (margins: 22,18,22,18)
└── QSplitter (Horizontal, handleWidth: 0)
    ├── advanced_drawer QFrame (initially hidden, maxWidth animated 0→380)
    │   └── QScrollArea (resizable, NoFrame)
    │       └── drawer_body QWidget
    │           ├── _card("Transcription") — transcription_mode_combo, profile_combo,
    │           │   engine_combo, threads_spin, groq_concurrency_spin, online_fallback_chk,
    │           │   vad_chk, vad_model_edit, vad_advanced, glossary_edit
    │           ├── _card("Slide sensitivity") — preset_combo, preview_btn,
    │           │   crop_selector, crop/ignore radio, clear_btn
    │           └── _card("System diagnostics") — diag_lbl
    └── main QWidget
        ├── _card("Source") — dropzone (DropzoneHero), video_path_edit, browse_btn, metadata_lbl
        ├── act_row QHBoxLayout — start_btn (primary), retranscribe_btn, advanced_toggle
        ├── _card("Output mode") — product_mode_combo
        ├── _card() — stage_lbl, stage_rows (StageRow per STAGE), progress_bar
        ├── "Live transcript" QLabel
        ├── live_transcript TranscriptStreamView (live=True, max_blocks=200)
        └── log_card QFrame — log_title, cancel_btn, log_toggle, log_text QTextEdit
```

**Font Sizes Hardcoded:**
- Card title labels: `"font:500 10px '{FONT_MONO}'"` (via `_card()` helper)
- Toggle button: `"font-size:13px"` (line 74)
- Dropzone hint: `"font-size:11px"` (line 443)
- Video path edit: `"font-size:12px"` (line 454)
- Browse btn: `"font-size:12px"` (line 460)
- Metadata lbl: `"font:500 11px 'JetBrains Mono'"` (line 469)
- Product mode combo: `"font-size:13px"` (line 499)
- Stage lbl: `"font-size:18px"` (line 507)
- Log title: `"font:500 10px '{FONT_MONO}'"` (line 549)
- Log text: `"font-size: 11px"` (line 577)

**Color References:**
- Hardcoded hex: `#FFFFFF`, `#2A241E`, `#81786B`, `#DDD3C4`, `#EEE8DD`, `#F15A24`, `#FBE2D5`
- Theme tokens: `theme.FONT_MONO`, `theme.FONT_STACK`, `theme.DARK_SUNK`/`theme.LIGHT_SUNK`, `theme.SUCCESS`, `theme.DARK_PRIMARY`/`theme.LIGHT_PRIMARY`, `theme.DARK_MUTED`/`theme.LIGHT_MUTED`, `theme.DANGER`, `theme.WARNING`

**Scroll Area:** Yes — advanced drawer wrapped in QScrollArea

**Empty State:** No explicit empty state — shows "No video loaded." metadata label

**Clipping Risks:**
- `DROPER_WIDTH = 380` constant for drawer max width
- `dropzone.setMinimumHeight(60).setMaximumHeight(80)` — fixed height range
- `live_transcript.setMinimumHeight(80).setMaximumHeight(150)` — clamped height
- `log_text.setMinimumHeight(120)` — minimum log height
- `browse_btn.setFixedWidth(62)` — fixed width
- `vad_browse.setFixedWidth(28)` — fixed width

---

### 4.3 ReviewPage (`review_page.py`, 773 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QSplitter (Horizontal)
    ├── left QWidget (minWidth: 250, maxWidth: 300)
    │   └── QVBoxLayout (margins: 14)
    │       ├── "Slides" QLabel (font-size: 16px)
    │       ├── selected_count_lbl QLabel
    │       ├── grid_mode_btn, list_mode_btn QToolButtons
    │       ├── slides_view SlideGridWidget
    │       └── actions QHBoxLayout — bulk_keep_btn, bulk_reject_btn (danger), bulk_restore_btn
    ├── center QWidget
    │   └── QVBoxLayout (margins: 14)
    │       ├── preview_lbl QLabel (minHeight: 240, styled bg+border)
    │       ├── nav QHBoxLayout — prev_btn, slide_info_lbl (font-size: 15px), next_btn
    │       └── study_row QHBoxLayout — slide_bookmark_btn, slide_note_edit
    └── right QWidget (minWidth: 320, maxWidth: 420)
        └── QVBoxLayout (margins: 14)
            ├── "Transcript for selection" QLabel (font-size: 16px)
            ├── search_layout — search_input, search_prev_btn, search_next_btn
            ├── copy_layout — "Copy as:" label, copy_format_combo, timestamps_chk,
            │   copy_current_btn, copy_selected_btn, copy_full_btn
            ├── transcript_table QTableWidget (3 columns)
            └── save_layout — save_corrections_btn (primary), context_repair_btn, transcript_status_lbl
```

**Font Sizes Hardcoded:**
- "Slides" title: `"font-size: 16px"` (line 82)
- Slide info: `"font-size: 15px"` (line 156)
- "Transcript for selection": `"font-size: 16px"` (line 196)
- Various buttons: `"font: 600 13px sans-serif"` (lines 113, 122, 150, 159, 173, 205, 228, 239, 266)
- Copy buttons: `"font: 600 12px sans-serif"` (lines 229, 233, 239)

**Color References:**
- Hardcoded hex: `#DDD3C4`, `#FFFFFF` (many buttons), `#81786B`
- Theme tokens: `theme.ACCENT` (selected_count_lbl), `theme.SUCCESS` (edited segment style), `theme.DARK_BORDER`/`theme.LIGHT_BORDER`, `theme.DARK_MUTED`/`theme.LIGHT_MUTED`, `theme.DARK_PANEL`/`theme.LIGHT_PANEL2`

**Scroll Area:** No explicit QScrollArea — content is in splitter panels

**Empty State:** "Select a slide to preview" text in preview_lbl; "Transcript for selection" header implies empty when no selection

**Clipping Risks:**
- `left.setMinimumWidth(250).setMaximumWidth(300)` — left panel clamped
- `right.setMinimumWidth(320).setMaximumWidth(420)` — right panel clamped
- `preview_lbl.setMinimumHeight(240)` — minimum preview height
- `text_edit.setMinimumHeight(40).setMaximumHeight(80)` (line 471-472) — transcript cell height clamped

---

### 4.4 TranscriptPage (`transcript_page.py`, 867 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QFrame (NoFrame) — acts as scroll container (NOT a QScrollArea!)
    └── sl_main QVBoxLayout (margins: 44,30,44,52, AlignHCenter)
        └── wrapper QWidget (maxWidth: 960)
            ├── "Transcript" QLabel (font-size: 28px)
            ├── toolbar QFrame (white bg, border, borderRadius: 10px)
            │   └── QHBoxLayout
            │       ├── search_edit QLineEdit
            │       ├── search_count_lbl QLabel
            │       ├── timestamps_chk QCheckBox
            │       ├── VLine separator
            │       ├── "Copy as:" label
            │       ├── copy_format_combo QComboBox
            │       ├── copy_selected_btn QPushButton
            │       └── copy_full_btn QPushButton (primary)
            └── QTabWidget (tabs)
                ├── Tab 0: "Full Transcript"
                │   └── full_view QTextBrowser
                ├── Tab 1: "Segments"
                │   ├── filt_row — "Show:" label, seg_filter_combo, seg_info_lbl
                │   ├── QSplitter (Vertical)
                │   │   ├── seg_table QTableWidget (7 columns)
                │   │   └── editor_w QWidget
                │   │       ├── ed_hdr — editor_lbl, Split/Merge/Reset/Undo/Redo/Save buttons
                │   │       └── seg_editor QPlainTextEdit
                ├── Tab 2: "Sections"
                │   ├── sec_actions — Rename/Copy/Bookmark/Jump/AI buttons
                │   └── sections_table QTableWidget (5 columns)
                └── Tab 3: "Context Repair"
                    └── repair_host QWidget → ContextRepairPanel
```

**Font Sizes Hardcoded:**
- Title: `"font-size: 28px"` (line 105)
- Search count: `"color: #81786B"` (line 123)
- Seg info: `"color: #81786B"` (line 176)
- Editor label: `"font-size: 14px"` (line 206)
- Action buttons: `"font: 600 12px sans-serif"` (line 217)

**Color References:**
- Hardcoded hex: `#FFFFFF`, `#DDD3C4`, `#81786B`, `#8E24AA` (AI heading marker)
- Theme tokens: `theme.ACCENT` (search highlight links), `theme.DARK_MUTED`/`theme.LIGHT_MUTED` (empty state), `theme.WARNING` (low confidence), `theme.DARK_INK`/`theme.LIGHT_INK` (highlight fg), `theme.is_dark()` for highlight bg

**Scroll Area:** **NO** — Uses `QFrame` (NoFrame) as a container, NOT a `QScrollArea`. Content will clip on smaller windows.

**Empty State:** "No transcript yet. Process a lecture or open a job." (line 355-356)

**Clipping Risks:**
- `wrapper.setMaximumWidth(960)` — content clips above 960px
- `split.setSizes([420, 140])` — fixed initial splitter ratio
- No scroll area means content can overflow vertically

---

### 4.5 StudyPage (`study_page.py`, 456 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QScrollArea (resizable, NoFrame, no horizontal scroll)
    └── container QWidget (margins: 44,30,44,52, AlignHCenter)
        └── wrapper QWidget (maxWidth: 1140)
            ├── title_row QHBoxLayout
            │   ├── title_lbl QLabel ("Study", font-size: 30px)
            │   └── resume_btn QPushButton (primary)
            ├── empty_lbl QLabel (initially visible)
            └── content QSplitter (Horizontal, objectName: "studySplitter")
                ├── slides_panel QWidget (minWidth: 200, maxWidth: 260)
                │   ├── "Slides" QLabel (font-size: 16px)
                │   └── slides_grid SlideGridWidget
                ├── center QWidget
                │   ├── overview_card QFrame (card=true)
                │   │   ├── overview_toggle QToolButton (font-size: 15px)
                │   │   └── overview_body QWidget
                │   │       ├── meta_lbl (font-size: 12px)
                │   │       ├── "Lecture overview" (font-size: 15px)
                │   │       ├── summary_lbl
                │   │       ├── summary_source_lbl (font-size: 12px)
                │   │       ├── "Key terms" (font-size: 15px)
                │   │       ├── terms_lbl
                │   │       ├── "Continue studying" (font-size: 15px)
                │   │       └── actions row — 4 navigation buttons
                │   ├── "Transcript" QLabel (font-size: 16px)
                │   └── transcript_view TranscriptStreamView
                └── right_panel QWidget (minWidth: 200, maxWidth: 280)
                    ├── "Topics" (font-size: 15px)
                    ├── topics_list QListWidget (maxHeight: 130)
                    ├── "Bookmarks" (font-size: 15px)
                    ├── "Slide bookmarks" (font-size: 12px)
                    ├── slide_bookmarks QListWidget (maxHeight: 80)
                    ├── "Section bookmarks" (font-size: 12px)
                    ├── section_bookmarks QListWidget (maxHeight: 80)
                    └── stretch
```

**Font Sizes Hardcoded:**
- Title: `"font-size: 30px"` (line 82)
- Empty state: `"font-size: 15px"` (line 96)
- Slides title: `"font-size: 16px"` (line 113)
- Overview toggle: `"font-size: 15px"` (line 140)
- Meta/source labels: `"font-size: 12px"` (lines 152, 165)
- Section titles (Lecture overview, Key terms, Continue studying): `"font-size: 15px"` (lines 156, 169, 177)
- Transcript title: `"font-size: 16px"` (line 202)
- Topics/Bookmarks titles: `"font-size: 15px"` (lines 217, 225)
- Bookmark sub-labels: `"font-size: 12px"` (lines 230, 239)
- Action buttons: `"font: 600 13px sans-serif"` (line 190)

**Color References:**
- Hardcoded hex: `#DDD3C4`, `#81786B`, `#FFFFFF`
- Theme tokens: None used directly in inline styles

**Scroll Area:** Yes — wraps all content with `setWidgetResizable(True)` and `setFrameShape(NoFrame)`

**Empty State:** Yes — `empty_lbl` with "No completed lecture is open..." message, toggled via `_set_empty(True/False)`

**Clipping Risks:**
- `wrapper.setMaximumWidth(1140)` — clips above 1140px
- `slides_panel.setMinimumWidth(200).setMaximumWidth(260)` — left panel clamped
- `right_panel.setMinimumWidth(200).setMaximumWidth(280)` — right panel clamped
- `topics_list.setMaximumHeight(130)` — topics list height capped
- `slide_bookmarks.setMaximumHeight(80)` — bookmarks list height capped
- `section_bookmarks.setMaximumHeight(80)` — section bookmarks height capped

---

### 4.6 ExportsPage (`exports_page.py`, 236 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QScrollArea (resizable, NoFrame, no horizontal scroll)
    └── container QWidget (margins: 44,34,44,52, AlignHCenter)
        └── wrapper QWidget (maxWidth: 960)
            ├── title QLabel ("Export study pack", font-size: 30px)
            ├── path_pill QLabel (font-size: 15px, RichText)
            ├── cards_grid QHBoxLayout
            │   ├── pdf_card QFrame (card=true)
            │   │   ├── pdf_icon QFrame (46x46, orange bg)
            │   │   └── pdf_info — title (font-size: 16px), desc (font-size: 13px)
            │   └── html_card QFrame (card=true)
            │       ├── html_icon QFrame (46x46, teal bg)
            │       └── html_info — title (font-size: 16px), desc (font-size: 13px)
            ├── formats_card QFrame (card=true)
            │   ├── fc_title QLabel ("Transcript formats", font-size: 16px)
            │   ├── fc_hint QLabel ("select to include", font-size: 11px)
            │   └── formats_grid QGridLayout — 9 checkboxes
            ├── cta_card QFrame (manual bg: #F9F5ED)
            │   ├── cta_title QLabel ("Export everything", font-size: 16px)
            │   ├── cta_sub QLabel ("PDF + HTML + transcript formats", font-size: 12px)
            │   └── export_btn QPushButton ("Export all", font-size: 15px)
            ├── artifacts_title QLabel ("Artifacts", font-size: 18px)
            └── artifacts_table QTableWidget (3 columns)
```

**Font Sizes Hardcoded:**
- Title: `"font-size: 30px"` (line 53)
- Path pill: `"font-size: 15px"` (line 61)
- Card titles: `"font-size: 16px"` (lines 79, 101, 121, 168)
- Card descriptions: `"font-size: 13px"` (lines 83, 105)
- Hint: `"font: 500 11px monospace"` (line 125)
- CTA sub: `"font: 500 12px monospace"` (line 171)
- Export btn: `"font: 700 15px sans-serif"` (line 176)
- Artifacts title: `"font-size: 18px"` (line 185)

**Color References:**
- Hardcoded hex: `#EEE8DD`, `#DDD3C4`, `#81786B`, `#FBE2D5`, `#DDF3F4`, `#F9F5ED`, `#1D1915`, `#F15A24`, `#D94812`
- Theme tokens: None used directly in inline styles

**Scroll Area:** Yes — wraps all content with `setWidgetResizable(True)` and `setFrameShape(NoFrame)`

**Empty State:** No explicit empty state — artifacts table is simply empty when no job is loaded

**Clipping Risks:**
- `wrapper.setMaximumWidth(960)` — clips above 960px
- No scroll area issues (content is scrollable)

---

### 4.7 SettingsPage (`settings_page.py`, 517 lines)

**Widgets & Layout:**
```
QVBoxLayout (margins: 0)
└── QScrollArea (resizable, NoFrame, no horizontal scroll)
    └── container QWidget (margins: 44,34,44,52, AlignHCenter)
        └── wrapper QWidget (maxWidth: 800)
            ├── title QLabel ("Settings", font-size: 30px)
            ├── _card("Whisper model")
            │   ├── wm_path QLineEdit (ReadOnly)
            │   ├── wm_browse QPushButton
            │   └── diag_lbl QLabel (font-size: 12px)
            ├── _card("Compute engine")
            │   ├── engine_combo QComboBox
            │   ├── engines_status_lbl (font-size: 12px)
            │   ├── vulkan_ok_chk QCheckBox
            │   ├── parallel_chk QCheckBox
            │   └── profiles_lbl (font-size: 12px)
            ├── _card("Local AI endpoint")
            │   ├── ollama_status_lbl
            │   ├── ollama_url_edit QLineEdit
            │   ├── test_model_btn QPushButton
            │   ├── ollama_model_combo QComboBox (editable)
            │   ├── refresh_models_btn QPushButton
            │   ├── ollama_enabled_chk QCheckBox
            │   ├── keep_alive_combo QComboBox
            │   └── note QLabel (muted)
            ├── _card("Groq online transcription")
            │   ├── groq_status_lbl
            │   ├── groq_set_btn, groq_test_btn, groq_remove_btn
            │   └── groq_note QLabel (font-size: 12px)
            ├── _card("Appearance")
            │   ├── theme_combo QComboBox ("Light", "Dark")
            │   └── data_dir_lbl QLabel
            ├── privacy_card QFrame (teal bg: #DDF3F4)
            │   └── QHBoxLayout — checkmark (font-size: 22px), privacy text (font-size: 13px)
            ├── save_row — save_btn QPushButton (primary, font-size: 14px)
            └── stretch
```

**Font Sizes Hardcoded:**
- Title: `"font-size: 30px"` (line 78)
- Card titles: `"font-size: 16px"` (line 52, via `_card()`)
- Diagnostics: `"font-size: 12px"` (lines 95, 111, 120, 186)
- Privacy checkmark: `"font-size: 22px"` (line 213)
- Privacy text: `"font-size: 13px"` (line 221)
- Save btn: `"font: 700 14px sans-serif"` (line 236)

**Color References:**
- Hardcoded hex: `#81786B`, `#095F69`, `#DDF3F4`, `#159EAE`, `#F15A24`, `#D94812`
- Theme tokens: None used directly in inline styles

**Scroll Area:** Yes — wraps all content with `setWidgetResizable(True)` and `setFrameShape(NoFrame)`

**Empty State:** No explicit empty state

**Clipping Risks:**
- `wrapper.setMaximumWidth(800)` — clips above 800px (most restrictive wrapper)
- `names_grp.setMaximumWidth(330)` (in ContextRepairPanel, but relevant for Settings) — left panel clamped

---

## 5. Widgets — Detailed Analysis

### 5.1 TitleBarWidget (`title_bar.py`, 183 lines)

- Fixed height: 56px (`HEIGHT = 56`)
- Logo: 28x28 colored square (`LogoMark`) with diamond character (`LogoDiamond`)
- Wordmark: RichText HTML with `<span style="font-weight:700;font-size:16px;">` — hardcoded font-size 16px
- Theme toggle: `QToolButton` with objectName `ThemeToggleBtn`
- Save/Export buttons: `QToolButton` with objectNames `HeaderSaveBtn`, `HeaderExportBtn`
- Window controls: Min (`–`), Max (`□`/`▣`), Close (`×`) — `QToolButton` with `setFixedSize(40, 28)`
- Drag-to-move: `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` handle window dragging
- Double-click maximize: `mouseDoubleClickEvent` emits `toggle_maximize_clicked`

### 5.2 SlideGridWidget (`slide_grid.py`, 306 lines)

- Extends `QListWidget` with custom `SlideTileDelegate`
- Two modes: Grid (icon mode, wrapping) and List (list mode, no wrapping)
- Grid tile size: `QSize(196, 158)` — hardcoded
- List tile size: `QSize(0, 64)` — height hardcoded
- Thumbnail loading: `ThumbnailLoader` QThread, caches as WebP in `frames/thumbs/`
- Selection: ExtendedSelection mode, custom painting via `theme.selection_visuals()`
- Context menu: Keep, Reject, Restore, Export selected, Copy image, Open source timestamp
- Key bindings: Delete → reject, R → restore, Enter → activate preview

### 5.3 TranscriptStreamView (`transcript_block.py`, 309 lines)

- Extends `QScrollArea` with lazy materialization
- Default batch size: 120 blocks (`BATCH_SIZE = 120`)
- Scroll debounce: 50ms (`SCROLL_DEBOUNCE_MS = 50`)
- Container: `QWidget` with `QVBoxLayout` (margins: 8, spacing: 4)
- Auto-extends when scrolled past 80% of content
- Live mode: `max_blocks` cap, auto-scroll to bottom when new segments arrive
- Smooth scrolling: `QPropertyAnimation` on scrollbar value (300ms, OutCubic)
- `TranscriptBlockWidget`: QFrame with time label (`blockTime` property) and text label (`blockText` property), selectable via dynamic `selected` property

### 5.4 AnimatedStackedWidget (`animated_stacked.py`, 71 lines)

- Extends `QStackedWidget`
- Transition: 180ms, 8% width offset slide from right + opacity fade
- Uses `QParallelAnimationGroup` with `QPropertyAnimation` on `pos` and `opacity`
- Guard: Rapid navigation kills in-flight animation instantly
- Cleanup: Removes `QGraphicsOpacityEffect` after transition completes

### 5.5 FocusModeController (`focus_mode.py`, 118 lines)

- Fades shell chrome (sidebar, header, footer) to opacity 0 over 250ms
- Hides widgets only after fade completes
- Shows floating "Exit Focus" `QPushButton` in bottom-right corner
- Exit button: objectName `FocusExitButton`, styled in dark_theme.qss
- Repositions on window resize via `eventFilter`
- Triggered by `Ctrl+Shift+F` shortcut or `Esc` to exit

### 5.6 ContextRepairPanel (`context_repair_panel.py`, 637 lines)

- Two-column layout: Left (names editor, max 330px) + Right (proposals table)
- Left: `QGroupBox` with `QListWidget` for approved names, add/remove input, deterministic/AI generate buttons, progress bar
- Right: `QTableWidget` (9 columns: Seg, Time, Original, Proposed, Changes, Why, Conf, Source, Status)
- Error bar: `QFrame` with retry/settings/copy diagnostics buttons
- AI generation: Always via `AiRepairWorker` QThread (never on GUI thread)
- Deterministic generation: Synchronous (pure CPU)
- Undo stack: Max 50 entries

### 5.7 CropSelector (`crop_selector.py`, 144 lines)

- Custom `QWidget` with `paintEvent` for drawing crop/ignore regions
- Stores regions as normalized `QRectF` (0.0 to 1.0)
- Max 3 ignore rectangles
- Draw modes: "crop" (green) and "ignore" (red)
- Loads video preview frame as `QPixmap`

---

## 6. Tests (`tests/test_ui_phase2.py`, 541 lines)

### Test Functions (30 tests across 6 milestones)

**M1 — Theme Layer (6 tests):**
1. `test_dark_palette_uses_neobrutalist_colors` — Verifies dark palette Window=#121417, Base=#1b1f23, Text=#f0e9df, Highlight=#ff6b35
2. `test_dark_qss_file_loaded_only_when_dark` — Asserts dark_theme.qss content present when dark, absent when light
3. `test_qss_uses_literal_hex_not_css_variables` — Asserts no `var(` in QSS, presence of #121417 and #FF6B35
4. `test_load_qss_missing_file_returns_empty_string` — Returns "" for missing file
5. `test_selection_visuals_api_unchanged` — Returns correct outline_color and outline_width
6. `test_add_card_shadow_attaches_effect` — blurRadius=14.0, yOffset=6.0, xOffset=0.0, alpha=90

**M2 — Transcript Block (6 tests):**
7. `test_find_segment_index_floor_matching` — Floor matching at 0, 7.2, -3, 999, empty
8. `test_find_slide_index_nearest_matching` — Nearest matching at 0, 6, 13, 16, 999, empty
9. `test_block_displays_timestamp_text_and_activates` — time_lbl="0:01:15", text_lbl="hello world", click emits 75.0
10. `test_block_selected_state_toggles_dynamic_property` — selected property toggles "true"/"false"
11. `test_stream_view_lazy_materialization` — 250 segments → 120 materialized; ensure_materialized(200) → ≥201
12. `test_stream_view_select_and_scroll` — select_index(40) → selected_index()==40, block_at(40).is_selected()

**M3 — Animated Stack + Title Bar + MainWindow (9 tests):**
13. `test_stream_view_live_cap_trims_oldest` — 8 segments with max_blocks=5 → materialized=5, first="segment 3"
14. `test_stream_view_emits_viewed_index_after_scroll_debounce` — Scroll triggers viewed_index_changed
15. `test_stream_view_clear_resets` — segment_count=0, materialized_count=0 after clear
16. `test_title_bar_buttons_emit_signals` — min/max/close emit correct signals
17. `test_title_bar_double_click_toggles_maximize` — Double-click emits toggle_maximize_clicked
18. `test_title_bar_maximize_glyph_switches` — □ → ▣ → □
19. `test_title_bar_drag_moves_host_window` — Drag moves window by correct delta
20. `test_animated_stack_switches_and_cleans_up` — Index changes, graphicsEffect cleared
21. `test_animated_stack_rapid_navigation_guard` — Interrupting transition works correctly
22. `test_animated_stack_same_index_is_noop` — Setting same index does nothing
23. `test_main_window_frameless_shell` — FramelessWindowHint set, header_bar is HeaderBarWidget, stack is AnimatedStackedWidget

**M4 — Study Page (6 tests):**
24. `test_study_workspace_loads_slides_and_transcript` — content visible, empty_lbl hidden, slides/transcript populated
25. `test_study_slide_click_seeks_transcript` — Slide click selects correct transcript block
26. `test_study_transcript_scroll_selects_nearest_slide` — Transcript scroll selects nearest slide
27. `test_study_block_click_selects_slide_without_navigating` — Block click doesn't emit navigate_requested
28. `test_study_viewed_index_ignored_during_programmatic_scroll` — Guard prevents re-entry
29. `test_study_overview_card_collapses` — Toggle shows/hides overview_body
30. `test_study_workspace_empty_state_clears_panes` — load_job(None) hides content, clears grids

**M5 — Process Page (5 tests):**
31. `test_process_page_dropzone_accepts_and_emits` — Drag enter sets dropActive="true", drop emits video_chosen
32. `test_process_page_dropzone_ignores_non_video` — Non-video drop ignored
33. `test_process_page_advanced_drawer_animates_open_and_closed` — Drawer maxWidth 0→380→0
34. `test_process_page_settings_widgets_live_in_drawer` — Transcription/vad/preset/crop widgets in drawer
35. `test_process_page_live_transcript_is_block_stream` — TranscriptStreamView with live=True

**M6 — Focus Mode + MainWindow (3 tests):**
36. `test_focus_mode_hides_and_restores_shell_chrome` — enter() hides nav/header/footer, exit() restores
37. `test_focus_mode_escape_exits` — _on_escape() exits focus mode
38. `test_focus_mode_toggle_button_and_shortcut_registered` — Ctrl+Shift+F registered, toggle works

---

*Studio UI comprehensive analysis: 2026-07-19*
