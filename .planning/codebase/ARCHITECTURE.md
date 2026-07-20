# Architecture

**Analysis Date:** 2026-07-19

## System Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                     Frameless Window Shell                        │
│  MainWindow (QMainWindow, FramelessWindowHint)                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ HeaderBarWidget (56px) — logo, breadcrumb, theme, save,    │  │
│  │                          export, min/max/close              │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌──────────┬──────────────────────────────────────────────────┐ │
│  │ NavSidebar│  AnimatedStackedWidget (page stack)              │ │
│  │ (224px)   │                                                 │ │
│  │  JobCard  │  ┌──────┬────────┬────────┬────────┬─────────┐ │ │
│  │  Library  │  │ Home │Process │ Review │Transcript│ ...     │ │ │
│  │  Workspace│  │ (0)  │  (1)   │  (2)   │  (3)    │         │ │ │
│  │  Output   │  └──────┴────────┴────────┴────────┴─────────┘ │ │
│  │  Settings │                                                 │ │
│  └──────────┴──────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ AppStatusFooter (34px) — stage, progress, elapsed, engine  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| MainWindow | Application shell, page navigation, job lifecycle, controller wiring, shortcuts, focus mode | `lecturepack/ui/main_window.py` |
| HeaderBarWidget | Custom title bar: logo, breadcrumb, theme toggle, save/export, window controls, drag-to-move | `lecturepack/ui/widgets/title_bar.py` |
| AnimatedStackedWidget | Page stack with slide+fade transition (180ms) | `lecturepack/ui/widgets/animated_stacked.py` |
| FocusModeController | Hides shell chrome (sidebar, header, footer) for distraction-free study | `lecturepack/ui/widgets/focus_mode.py` |
| HomePage | Job browser grid, new-job drop zone, archive/restore actions | `lecturepack/ui/pages/home_page.py` |
| ProcessPage | Video source, transcription settings, slide detection, pipeline progress, live log/transcript | `lecturepack/ui/pages/process_page.py` |
| ReviewPage | Slide grid/preview, transcript editing, search, copy, decisions (keep/reject/restore) | `lecturepack/ui/pages/review_page.py` |
| TranscriptPage | Full transcript, segment editor, sections/topics, context repair tab | `lecturepack/ui/pages/transcript_page.py` |
| StudyPage | 3-column study workspace: slides, overview+transcript, bookmarks/topics | `lecturepack/ui/pages/study_page.py` |
| ExportsPage | Export format selection, artifacts table, export trigger | `lecturepack/ui/pages/exports_page.py` |
| SettingsPage | Whisper model, compute engine, Ollama AI, Groq, appearance, data directory | `lecturepack/ui/pages/settings_page.py` |
| SlideGridWidget | Slide timeline with grid/list modes, custom tile painting, thumbnail loading | `lecturepack/ui/widgets/slide_grid.py` |
| TranscriptStreamView | Lazily-materialized scrollable transcript column with smooth scrolling | `lecturepack/ui/widgets/transcript_block.py` |
| ContextRepairPanel | Deterministic + AI repair proposals, accept/reject/revert UI | `lecturepack/ui/widgets/context_repair_panel.py` |
| CropSelector | Video crop/ignore region drawing on a preview frame | `lecturepack/ui/widgets/crop_selector.py` |
| theme.py | Color tokens, QPalette builders, QSS generation, font loading, card shadow helper | `lecturepack/ui/theme.py` |
| dark_theme.qss | Dark-mode QSS overrides (239 lines) | `lecturepack/ui/themes/dark_theme.qss` |

## Pattern Overview

**Overall:** Single-window application with a custom frameless shell and animated page stack.

**Key Characteristics:**
- Frameless window with custom `HeaderBarWidget` title bar (56px) handling drag, double-click maximize, min/max/close
- Sidebar navigation rail (224px fixed) with SVG icon buttons, organized in Library/Workspace/Output/Settings sections
- Animated stacked widget for page transitions (180ms slide+fade)
- All pages use `QScrollArea` with `setWidgetResizable(True)` and max-width wrappers for content centering
- Focus mode hides all chrome (sidebar, header, footer) via opacity animation
- Theme system: `QPalette` + inline QSS + dark_theme.qss overlay; no CSS variables (all hex literals)
- Custom delegates (`SlideTileDelegate`) for grid painting with selection visuals
- Lazy materialization pattern (`TranscriptStreamView`) for long transcripts

## Layers

**Theme Layer:**
- Purpose: Centralized color tokens, QPalette construction, QSS generation, font loading
- Location: `lecturepack/ui/theme.py`, `lecturepack/ui/themes/dark_theme.qss`
- Contains: All color constants (light/dark), font stacks, QSS template function, `apply_theme()`, `load_fonts()`, `add_card_shadow()`, `selection_visuals()`
- Depends on: PySide6 (QColor, QFontDatabase, QPalette, QApplication, QGraphicsDropShadowEffect)
- Used by: Every UI widget and page

**Shell Layer:**
- Purpose: Application frame, navigation, status bar, window management
- Location: `lecturepack/ui/main_window.py`
- Contains: `MainWindow`, `RestoreDialog`, `DetectionPreviewDialog`, page constants, SVG icon data, navigation button factory
- Depends on: Theme, all pages, JobController, FileManager, Job model, ConfigManager
- Used by: Application entry point (`lecturepack/app.py`)

**Widget Layer:**
- Purpose: Reusable visual components used across pages
- Location: `lecturepack/ui/widgets/`
- Contains: `HeaderBarWidget`, `AnimatedStackedWidget`, `FocusModeController`, `SlideGridWidget`, `TranscriptStreamView`, `TranscriptBlockWidget`, `ContextRepairPanel`, `CropSelector`
- Depends on: Theme
- Used by: Pages, MainWindow

**Page Layer:**
- Purpose: Full-page views for each functional area
- Location: `lecturepack/ui/pages/`
- Contains: `HomePage`, `ProcessPage`, `ReviewPage`, `TranscriptPage`, `StudyPage`, `ExportsPage`, `SettingsPage`
- Depends on: Theme, Widgets, services, infrastructure
- Used by: MainWindow (stack widget)

## Data Flow

### Theme Application

1. `MainWindow.__init__` calls `theme.apply_theme(app, dark)` (`main_window.py:169`)
2. `apply_theme` loads fonts, sets Fusion style, builds QPalette, generates QSS (`theme.py:485-493`)
3. Dark mode appends `dark_theme.qss` content after the generated QSS (`theme.py:491`)
4. `_on_theme_changed` re-applies theme, updates nav icons, header bar (`main_window.py:615-620`)

### Page Navigation

1. Nav button clicked → `navigate_to(index)` → `stack.setCurrentIndex(index)` (`main_window.py:565-566`)
2. `stack.currentChanged` → `_on_page_changed(index)` updates button states, breadcrumb, lazy-loads data (`main_window.py:568-588`)
3. Page indices: 0=Home, 1=Process, 2=Review, 3=Transcript, 4=Exports, 5=Settings, 6=Study (`main_window.py:58`)

### Job Lifecycle

1. Video selected → `Job` created, controller set, process page populated (`main_window.py:661-700`)
2. Start processing → `_collect_job_settings()` → `controller.run_pipeline()` (`main_window.py:855-914`)
3. Pipeline stages → controller signals → process page updates stage rows (`main_window.py:979-1008`)
4. Pipeline complete → `_load_review_data()` → navigate to Study page (`main_window.py:1016-1022`)

### Bidirectional Study Sync

1. Slide clicked → `_on_slide_current_changed` → `_seek_transcript(timestamp)` (`study_page.py:395-429`)
2. Transcript scrolled → `_on_transcript_viewed(index)` → `_select_slide_near(timestamp)` (`study_page.py:402-407`)
3. Guards: `_sync_guard` prevents slide→transcript loop; `_programmatic_scroll` prevents transcript→slide loop (`study_page.py:55-56`)

## Key Abstractions

**Color Tokens (theme.py):**
- Purpose: Semantic color names that map to light/dark values
- Light: `LIGHT_BG`, `LIGHT_PANEL`, `LIGHT_INK`, `LIGHT_PRIMARY`, `LIGHT_SECONDARY`, etc.
- Dark: `DARK_BG`, `DARK_PANEL`, `DARK_INK`, `DARK_PRIMARY`, `DARK_SECONDARY`, etc.
- Shared: `PRIMARY`, `SECONDARY`, `DANGER`, `SUCCESS`, `WARNING`
- Pattern: Module-level constants; `_qss(dark)` function maps to local variables for QSS generation

**Card Pattern:**
- Purpose: Styled QFrame with shadow, used for visual grouping
- Factory: `_card()` helper in `process_page.py` (`process_page.py:41-59`)
- Manual: `QFrame` with `setProperty("card", True)` + `theme.add_card_shadow()` in other pages
- QSS: `QFrame[card="true"] { background: {card_bg}; border: 1.5px solid {border}; border-radius: 13px; }`

**Custom Title Bar:**
- Purpose: Replace native window chrome for frameless look
- Class: `HeaderBarWidget` (`title_bar.py`)
- Features: Logo (28x28 colored square + diamond), wordmark, breadcrumb, theme toggle, save/export buttons, min/max/close, drag-to-move, double-click maximize

**Lazy Transcript Loading:**
- Purpose: Handle long transcripts without materializing all widgets upfront
- Class: `TranscriptStreamView` (`transcript_block.py`)
- Pattern: Batch materialization (120 blocks default), scroll-triggered extension at 80%, optional live mode with max_blocks cap and auto-scroll

**Selection Visuals:**
- Purpose: Consistent, testable selection rendering across grid/list views
- Function: `theme.selection_visuals(selected, focused, decision, dark)` (`theme.py:110-131`)
- Returns: Dict with outline_color, outline_width, background, checkmark_visible, checkmark_bg, focus_ring_visible, focus_ring_color, decision_badge_color

## Entry Points

**Application Start:**
- Location: `lecturepack/app.py`
- Creates: `QApplication`, applies theme, creates `MainWindow`, shows window

**Main Window Construction:**
- Location: `lecturepack/ui/main_window.py:146-183`
- Triggers: `MainWindow.__init__`
- Responsibilities: Build shell, init shortcuts, connect controller, restore UI state, refresh diagnostics

## Architectural Constraints

- **Frameless window:** Uses `Qt.FramelessWindowHint`; all window management (drag, resize, minimize, maximize, close) handled by custom code and `QSizeGrip`
- **Single-threaded GUI:** All Ollama/Groq interactions run in `QThread` workers; GUI thread never blocks on I/O
- **No CSS variables:** All QSS uses hex literal interpolation from Python f-strings; `dark_theme.qss` also uses hex literals only
- **Font loading:** `QFontDatabase.addApplicationFont` from bundled `lecturepack/ui/fonts/` directory (currently empty - fonts may be installed at system level)
- **QSettings persistence:** Window geometry, splitter positions, last page, slide list mode stored via `QSettings("LecturePack", "LecturePack")`
- **Page index contract:** Review stays at index 2 for backward compatibility with tests/tools (`main_window.py:13`)
- **Compatibility aliases:** `MainWindow` exposes v1.0 test attributes as `@property` aliases (e.g., `slides_view`, `transcript_table`, `start_btn`) (`main_window.py:391-500`)

## Anti-Patterns

### Hardcoded Colors in Page Code

**What happens:** Many pages set inline stylesheets with hardcoded hex colors (e.g., `#FFFFFF`, `#DDD3C4`, `#81786B`, `#F15A24`) instead of using theme tokens
**Why it's wrong:** Dark mode breaks for these widgets because the hardcoded colors don't change with the theme. Examples: `process_page.py:47`, `review_page.py:113-115`, `study_page.py:103`, `exports_page.py:161`
**Do this instead:** Use `theme.is_dark()` ternary or use `setProperty()` with QSS selectors that reference theme variables. Prefer the `[card="true"]` pattern with `theme.add_card_shadow()`.

### Missing ScrollArea Wrapping

**What happens:** `TranscriptPage` uses a plain `QFrame` as scroll container instead of `QScrollArea` (`transcript_page.py:92-93`)
**Why it's wrong:** Content can clip on smaller windows. `HomePage`, `StudyPage`, `ExportsPage`, and `SettingsPage` all use `QScrollArea` correctly.
**Do this instead:** Wrap content in `QScrollArea` with `setWidgetResizable(True)` and `setFrameShape(QFrame.Shape.NoFrame)`.

### Inconsistent Card Styling

**What happens:** Cards are styled in three different ways: (1) `setProperty("card", True)` + `add_card_shadow()`, (2) `_card()` factory with explicit `QFrame{...}` stylesheet, (3) manual inline `setStyleSheet()` with hardcoded colors
**Why it's wrong:** Inconsistent visual appearance and dark mode breakage for method (3)
**Do this instead:** Standardize on the `[card="true"]` QSS selector + `add_card_shadow()` pattern. Remove all manual card border/background stylesheets.

### Sidebar Fixed Width Without Responsive Behavior

**What happens:** Sidebar is `setFixedWidth(224)` (`main_window.py:213`)
**Why it's wrong:** On narrow screens (< 900px) the sidebar consumes too much space; no collapse mechanism
**Do this instead:** Consider making sidebar collapsible or using a minimum width instead of fixed width.

## Error Handling

**Strategy:** QMessageBox dialogs for user-facing errors; inline error bars for recoverable errors; status bar for transient messages

**Patterns:**
- `QMessageBox.critical()` for fatal errors (pipeline failure, video inspection failure) (`main_window.py:686,1028,1048`)
- `QMessageBox.warning()` for validation failures (missing video, missing model) (`main_window.py:857-908`)
- Inline error bar in `ContextRepairPanel` with Retry/Settings/Copy actions (`context_repair_panel.py:155-175`)
- `self.statusBar().showMessage(msg, 4000)` for transient status (`main_window.py:629`)
- Per-page `status_message` Signal for cross-component status display

## Cross-Cutting Concerns

**Logging:** Python `logging` module used sparingly; theme.py uses `logging.getLogger(__name__).warning()` for missing theme files (`theme.py:460`)

**Validation:** Pre-processing validation in `_start_processing()` checks for video path, whisper executable, model path, VAD model, Groq credentials (`main_window.py:856-908`)

**Theme/Dark Mode:** Two-theme system (light/dark) toggled at runtime; `_on_theme_changed` re-applies palette + QSS + updates nav icons + header wordmark color (`main_window.py:615-620`)

**Font System:** Two font families: Space Grotesk (UI text) and JetBrains Mono (code/monospace). Loaded from `lecturepack/ui/fonts/` directory. QSS font stacks include system fallbacks (`theme.py:106-107`)

---

*Architecture analysis: 2026-07-19*
