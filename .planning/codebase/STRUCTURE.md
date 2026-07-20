# Codebase Structure

**Analysis Date:** 2026-07-19

## Directory Layout

```
LecturePack/
├── lecturepack/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py                    # Application entry point
│   ├── constants.py              # STAGES, PRODUCT_MODES, PRESETS, etc.
│   ├── acceptance.py
│   ├── controllers/
│   │   └── job_controller.py     # Pipeline orchestration
│   ├── infrastructure/
│   │   ├── config_manager.py
│   │   ├── file_manager.py
│   │   ├── cv_engine.py          # Slide detection (OpenCV)
│   │   ├── whisper_detector.py
│   │   ├── transcription_engines.py
│   │   ├── ollama_client.py
│   │   ├── secret_store.py
│   │   └── groq_transcription.py
│   ├── models/
│   │   └── job.py
│   ├── services/
│   │   ├── transcript_store.py
│   │   ├── transcript_formats.py
│   │   ├── transcript_service.py
│   │   ├── export_service.py
│   │   └── study_service.py
│   └── ui/
│       ├── theme.py               # Color tokens, QSS generation, palettes
│       ├── main_window.py         # Application shell (1445 lines)
│       ├── context_repair_dialog.py
│       ├── fonts/                 # Bundled font files (empty - system fonts)
│       ├── themes/
│       │   └── dark_theme.qss     # Dark mode QSS overrides (239 lines)
│       ├── pages/
│       │   ├── home_page.py       # Job browser (304 lines)
│       │   ├── process_page.py    # Pipeline setup + live view (706 lines)
│       │   ├── review_page.py     # Slide review workspace (773 lines)
│       │   ├── transcript_page.py # Transcript editor (867 lines)
│       │   ├── study_page.py      # 3-column study workspace (456 lines)
│       │   ├── exports_page.py    # Export format selection (236 lines)
│       │   └── settings_page.py   # App settings (517 lines)
│       └── widgets/
│           ├── title_bar.py       # Custom header bar (183 lines)
│           ├── slide_grid.py      # Slide timeline grid/list (306 lines)
│           ├── transcript_block.py # Lazy transcript stream (309 lines)
│           ├── animated_stacked.py # Animated page stack (71 lines)
│           ├── focus_mode.py      # Focus mode controller (118 lines)
│           ├── context_repair_panel.py # AI repair UI (637 lines)
│           └── crop_selector.py   # Video crop region drawing (144 lines)
├── tests/
│   ├── test_ui_phase2.py          # UI tests (541 lines)
│   └── test_ui_v11.py
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   └── IMPLEMENTATION_PLAN.md
├── assets/
├── models/
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── AGENTS.md
```

## Directory Purposes

**`lecturepack/ui/`:**
- Purpose: All UI code — theme system, shell, pages, widgets
- Contains: `theme.py`, `main_window.py`, pages, widgets, themes, fonts
- Key files: `theme.py` (design tokens), `main_window.py` (shell), `pages/*.py` (7 page views), `widgets/*.py` (7 reusable widgets)

**`lecturepack/ui/pages/`:**
- Purpose: Full-page views, one per navigation item
- Contains: 7 page classes, each a `QWidget` subclass
- Key files: `home_page.py`, `process_page.py`, `review_page.py`, `transcript_page.py`, `study_page.py`, `exports_page.py`, `settings_page.py`

**`lecturepack/ui/widgets/`:**
- Purpose: Reusable visual components shared across pages
- Contains: 7 widget files
- Key files: `slide_grid.py` (custom delegate painting), `transcript_block.py` (lazy loading), `title_bar.py` (frameless title bar)

**`lecturepack/ui/themes/`:**
- Purpose: QSS files for theme overrides
- Contains: `dark_theme.qss` only (239 lines)
- Key files: `dark_theme.qss` (dark mode overrides, loaded after generated QSS)

**`lecturepack/ui/fonts/`:**
- Purpose: Bundled font files (Space Grotesk, JetBrains Mono)
- Contains: Empty directory (fonts loaded at runtime or installed system-wide)
- Key files: None present

**`tests/`:**
- Purpose: Test suite
- Contains: `test_ui_phase2.py` (541 lines, 30+ test functions), `test_ui_v11.py`
- Key files: `test_ui_phase2.py` (theme, transcript block, animated stack, focus mode, process page, study page tests)

## Key File Locations

**Entry Points:**
- `lecturepack/app.py`: Application entry point (creates QApplication, MainWindow)
- `lecturepack/__main__.py`: Module entry point

**Configuration:**
- `lecturepack/constants.py`: STAGES, PRODUCT_MODES, PRESETS, TRANSCRIPTION_MODE_LABELS
- `lecturepack/ui/theme.py`: All color tokens (60+ constants), font stacks, QSS generation
- `lecturepack/ui/themes/dark_theme.qss`: Dark mode QSS overrides

**Core Logic:**
- `lecturepack/ui/main_window.py`: Shell layout, page navigation, job lifecycle, controller wiring
- `lecturepack/ui/theme.py`: Theme system (`apply_theme()`, `_qss()`, `_dark_palette()`, `_light_palette()`)
- `lecturepack/ui/pages/process_page.py`: Pipeline configuration and live progress
- `lecturepack/ui/pages/review_page.py`: Slide review and transcript editing
- `lecturepack/ui/pages/study_page.py`: 3-column study workspace with bidirectional sync
- `lecturepack/ui/pages/transcript_page.py`: Full transcript editor with sections and context repair

**Testing:**
- `tests/test_ui_phase2.py`: Theme layer tests (M1), transcript block tests (M2), animated stack tests (M3), main window frameless tests (M4), study page tests (M5), process page tests (M6), focus mode tests (M6)

## Naming Conventions

**Files:**
- Pages: `{name}_page.py` (snake_case) — e.g., `home_page.py`, `process_page.py`
- Widgets: `{name}.py` (snake_case) — e.g., `slide_grid.py`, `title_bar.py`
- Theme: `theme.py` (singular), `dark_theme.qss` (snake_case with theme prefix)
- Tests: `test_ui_phase2.py` (test_ prefix, phase suffix)

**Classes:**
- Pages: `{Name}Page` (PascalCase) — e.g., `HomePage`, `ProcessPage`, `ReviewPage`
- Widgets: `{Name}Widget` or `{Name}Controller` — e.g., `SlideGridWidget`, `FocusModeController`, `TranscriptBlockWidget`
- Dialogs: `{Name}Dialog` — e.g., `RestoreDialog`, `DetectionPreviewDialog`
- Private widgets: `_JobCard` (underscore prefix for internal use)

**Object Names (setObjectName):**
- Header bar: `AppHeaderBar`, `LogoMark`, `LogoDiamond`, `AppBreadcrumb`, `ThemeToggleBtn`, `HeaderSaveBtn`, `HeaderExportBtn`
- Sidebar: `NavSidebar`, `SidebarSectionLabel`, `JobStatusCard`, `JobCardThumb`, `JobCardTitle`, `JobCardStatus`
- Footer: `AppStatusFooter`, `FooterStage`, `FooterElapsed`, `FooterEngine`, `FooterWarn`
- Cards: `[card="true"]` dynamic property
- Nav buttons: `[navButton="true"]` dynamic property

**Signals:**
- User actions: `{action}_requested` — e.g., `start_requested`, `cancel_requested`, `archive_requested`
- State changes: `{state}_changed` — e.g., `theme_changed`, `settings_changed`, `study_data_changed`
- Navigation: `{destination}_requested` — e.g., `navigate_requested`, `seek_requested`, `open_context_repair`
- Data: `{noun}_changed` — e.g., `selection_count_changed`, `position_changed`, `viewed_index_changed`

## Where to Add New Code

**New Page:**
- Implementation: `lecturepack/ui/pages/{name}_page.py`
- Import in: `lecturepack/ui/main_window.py` (add to imports, PAGES list, PAGE_ICONS, NAV_PAGE_ORDER, stack.addWidget)
- Tests: `tests/test_ui_{phase}.py`

**New Widget:**
- Implementation: `lecturepack/ui/widgets/{name}.py`
- Import in: page files or main_window.py as needed

**New Theme Token:**
- Add constant: `lecturepack/ui/theme.py` (module-level, UPPER_CASE)
- Use in QSS: Reference via local variable in `_qss()` function
- Document: Include in both light and dark palette sections

**New QSS Selector:**
- Light mode: Add to `_qss()` function in `theme.py` (f-string interpolation)
- Dark mode overrides: Add to `lecturepack/ui/themes/dark_theme.qss` (hex literals)
- Use object names or dynamic properties for specificity — avoid bare type selectors

**New Test:**
- Add to: `tests/test_ui_phase2.py` (for UI components)
- Pattern: `def test_{description}(app, qtbot):` with `app` fixture and `qtbot.addWidget()`

## Special Directories

**`lecturepack/ui/fonts/`:**
- Purpose: Bundled font files for Space Grotesk and JetBrains Mono
- Generated: No
- Committed: Yes (but currently empty — fonts loaded from system or bundled at build time)

**`lecturepack/ui/themes/`:**
- Purpose: QSS theme override files
- Generated: No
- Committed: Yes

**`lecturepack/ui/__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No (in .gitignore)

---

*Structure analysis: 2026-07-19*
