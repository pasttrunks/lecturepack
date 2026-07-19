# Phase 2 Plan — "Premium Glassmorphic Dark" UI Overhaul

**Date:** 2026-07-19
**Branch:** `phase-2-ui-overhaul`
**Status:** Awaiting approval

---

## 1. Task Restatement (per AGENTS.md)

- **Authorized phase:** Phase 2 — Immersive UI Overhaul (visual/shell layer only)
- **Exact goal:** Replace the engineering-console look with a premium dark,
  glassmorphic experience: frameless window with custom title bar, spatial
  Study workspace (slides ⟷ transcript with bidirectional sync), Focus Mode,
  minimalist dropzone Process page, animated transitions, and a comprehensive
  QSS theme — without changing any backend, persistence, or pipeline behavior.
- **Files permitted to create/modify:** see §8 (strict list).
- **Required tests:** new `tests/test_ui_phase2.py` + full suite green
  (real pytest output per milestone, §10).
- **Non-goals:** no controller/service/infrastructure changes; no Review or
  Transcript page redesigns (they inherit the global theme only); no new
  third-party dependencies (fonts are OS-provided); no persistence-layer
  changes; no changes to `transcript_segment`/pipeline contracts from Phase 1.
- **Completion evidence:** per-milestone pytest output, updated
  `docs/DECISIONS.md` + `docs/HANDOFF_PHASE_V2_UI.md`, screenshots deferred
  to user acceptance.

## 2. Design Language

Catppuccin-Mocha-inspired palette (literal hex — QSS has no variables):

| Token | Hex | Use |
|---|---|---|
| Base | `#1E1E2E` | window background |
| Mantle | `#181825` | rails, bars, sunken areas |
| Surface0 | `#313244` | cards, blocks |
| Surface1 | `#45475A` | hover states, borders-strong |
| Text | `#CDD6F4` | primary text |
| Subtext | `#A6ADC8` | muted text |
| Accent | `#89B4FA` | neon blue: selection, primary, focus |
| AccentDeep | `#74A8F7` | accent hover |
| Green | `#A6E3A1` | success |
| Red | `#F38BA8` | danger |
| Yellow | `#F9E2AF` | warning |

- **Typography:** `Segoe UI Variable Text, Inter, Segoe UI, sans-serif`;
  13px base, 20px/600 page titles, 11px muted captions.
- **Geometry:** 10px card radius, 6px control radius, 1px `#45475A` borders.
- **Depth:** `QGraphicsDropShadowEffect` (blur 24, y-offset 3,
  `rgba(0,0,0,90)`) on cards — helper `theme.add_card_shadow(widget)`.
- **Theme mechanics:** `lecturepack/ui/theme.py` remains the single source of
  truth for constants consumed by widget code/tests (its `selection_visuals`
  API is unchanged). New: static `lecturepack/ui/themes/dark_theme.qss`
  (literal hexes) loaded and appended by `theme.apply_theme` when dark is
  active. The v1.2 `ACCENT` constant stays for API compatibility; the new QSS
  introduces the `#89B4FA` accent visually. (Packaging note: `.qss` must be
  added to the PyInstaller spec datas in Phase 5 — recorded as follow-up.)

## 3. New Custom Widget Classes

### 3.1 `TitleBarWidget` — `lecturepack/ui/widgets/title_bar.py`
- 40px `QFrame` (`objectName="AppTitleBar"`): app icon pixmap, title label,
  spacer, min / max-restore / close buttons (`titleBarMin`, `titleBarMax`,
  `titleBarClose` object names).
- **Drag:** `mousePressEvent` stores `event.globalPosition() -
  frameGeometry().topLeft()`; `mouseMoveEvent` moves the window (disabled
  while maximized); double-click toggles maximize/restore.
- Buttons emit `minimize_clicked`, `toggle_maximize_clicked`, `close_clicked`;
  MainWindow routes them (`showMinimized()`, `showNormal()/showMaximized()`,
  `self.close()` → existing `closeEvent` pipeline-cancel path unchanged).

### 3.2 `TranscriptBlockWidget` — `lecturepack/ui/widgets/transcript_block.py`
- `QFrame` (`objectName="TranscriptBlock"`) with `QVBoxLayout`: timestamp
  caption label (`HH:MM:SS`, muted, mono-ish) + word-wrap text label.
- **States** via dynamic properties + `style().unpolish/polish`:
  `selected="true"` → 3px left border `#89B4FA` + Surface0 bg;
  `:hover` → bg lightens Surface0→Surface1 (via `WA_Hover`, zero code).
- `activated = Signal(float)` (timestamp seconds) on mouse release.
- `set_live(bool)` — accent-tinted variant for the streaming pane.
- Fixed content margins (10/6/10/6), `sizePolicy` Preferred/Maximum so blocks
  stack compactly.

### 3.3 `AnimatedStackedWidget` — `lecturepack/ui/widgets/animated_stacked.py`
- `QStackedWidget` subclass; `setCurrentIndex` runs a 180ms
  `QEasingCurve.OutCubic` slide+fade: incoming page starts offset +8% width
  with `QGraphicsOpacityEffect` 0→1 and slides to 0 via two
  `QPropertyAnimation`s (`pos`, `opacity`) in a `QParallelAnimationGroup`.
- Re-entrancy guard: animation in progress → finish instantly, then switch
  (rapid nav never queues). `currentChanged` still fires normally (tests and
  `_on_page_changed` unaffected).

### 3.4 `FocusModeController` — `lecturepack/ui/widgets/focus_mode.py`
- Owns fade in/out of shell chrome: NavRail, CommandBar, QStatusBar via one
  `QGraphicsOpacityEffect` each + `QPropertyAnimation(b"opacity")` (250ms);
  hides widgets at opacity 0 (so the page reclaims the space), restores on
  exit.
- Floating "Exit Focus" `QPushButton` (semi-transparent, accent border) as a
  frameless child of the window, bottom-right with 24px margins; `Esc` also
  exits. Toggle entry point: command-bar button + `Ctrl+Shift+F`.

## 4. Page Redesigns

### 4.1 Study page → "Spatial Workspace"
`study_page.py` rebuilt around `QSplitter` (keeps `objectName="studySplitter"`):

- **Left (40%):** `SlideGridWidget` (existing `ui/widgets/slide_grid.py`,
  reused as-is — it already has thumbnails, delegate painting, shutdown).
- **Right (60%):** `TranscriptStreamView` (new in
  `widgets/transcript_block.py`): `QScrollArea` hosting
  `TranscriptBlockWidget`s fed from `transcript_store.load_working(job.paths)`.
- **Overview preservation:** current overview (summary, key terms, topics,
  bookmarks, resume) moves into a collapsible "Overview" card at the top of
  the transcript column. **All existing object names are kept**
  (`studyTitle`, `studyResumeButton`, `studyTopicsList`, `studySummary`, …)
  and `load_job()/refresh()` semantics + the three public signals stay
  identical, so `test_study_workspace_v12` keeps passing or is minimally
  updated (each touched assertion documented in the PR).
- **Bidirectional sync engine** (pure helpers in
  `widgets/transcript_block.py`, unit-testable without Qt):
  - `find_segment_index(segments, t)` — `bisect` on start times.
  - `find_slide_index(candidates, t)` — `bisect` on `timestamp_seconds`.
  - Slide click → index → `ensure_materialized(index)` → smooth-scroll:
    `QPropertyAnimation` on the scroll-area `verticalScrollBar().value`
    (300ms OutCubic) → block `selected`.
  - Transcript scroll → `QTimer` debounce (restart on each `valueChanged`,
    `singleShot`-style 50ms) → topmost visible block index → nearest slide →
    `setCurrentRow` on the grid. Guard flag `_programmatic_scroll` suppresses
    feedback loops while the animation runs.
- **Performance:** blocks are materialized lazily — first 120 rendered, then
  batches of 120 appended when the scroll position passes 80%, or when
  `ensure_materialized(i)` needs block `i`. A 2-hour lecture (~1,400
  segments) never pays the full widget cost up front.

### 4.2 Process page → "Minimalist Dropzone"
- **Hero dropzone** (`QFrame` `objectName="DropzoneHero"`, accepts drops,
  forwards to the existing `_on_video_selected` path): dashed `#45475A`
  border; on `dragEnterEvent` set dynamic property `dropActive="true"` → QSS
  swaps to 3px `#89B4FA` border + accent `QGraphicsDropShadowEffect`; a
  `QPropertyAnimation` pulses shadow `blurRadius` 18→30 while active.
  Main-window drag/drop continues to work unchanged.
- **"Advanced Settings" slide-out drawer:** the current settings groups
  (Transcription grid, VAD, Slide detection + crop, Diagnostics) move —
  widgets **unmodified, same object names** — into a right-docked `QFrame`
  whose `maximumWidth` animates 0↔380 (220ms OutCubic). Default page shows
  only: dropzone (or video summary line when loaded), product-mode combo,
  Start/Retranscribe, stage rows, progress bar.
- **Live transcript:** Phase 1's `QTextEdit` pane is replaced by a
  `TranscriptStreamView` in live mode fed by the existing
  `on_transcript_segment` slot (cap 200 blocks, oldest trimmed, auto-scroll).
  `log_text`, `live_transcript` alias and every existing attribute/test hook
  (`start_btn`, `video_path_edit`, `stage_rows`, …) remain addressable.

### 4.3 Shell (`main_window.py`)
- `setWindowFlags(Qt.Window | Qt.FramelessWindowHint)`; `TitleBarWidget`
  inserted above the command bar; `QSizeGrip` in the status-bar corner for
  resizing. QSettings geometry persistence unchanged.
- `self.stack` becomes `AnimatedStackedWidget` (same API).
- Card shadow helper applied to `QFrame[card="true"]` instances on the
  touched pages.
- Focus mode wiring (`Ctrl+Shift+F` + button).
- **Preserved:** nav rail object names, all compatibility aliases,
  `_connect_controller`, shortcuts, close behavior.

## 5. Risk Register

| Risk | Mitigation |
|---|---|
| Frameless loses Win11 snap/shadow | Accepted tradeoff (documented); `QSizeGrip` resize; title-bar double-click maximize |
| 1,000+ transcript widgets lag | Lazy batching (120/block batches) + `ensure_materialized` |
| Scroll-sync feedback loops | `_programmatic_scroll` guard + 50ms debounce |
| Existing UI tests depend on layout | Object-name inventory above; suite run per milestone; intentional test edits documented |
| QSS parse errors break styling silently | `theme.load_qss()` logs file/size; smoke test asserts the app stylesheet contains `#1E1E2E` |
| Opacity effects on many widgets cost | Focus mode animates exactly 3 shell widgets; cards use static shadows |

## 6. Execution Milestones (green-suite gate each)

1. **M1 Theme:** `dark_theme.qss`, loader, constants, shadow helper.
2. **M2 Widgets:** `TranscriptBlockWidget` + `TranscriptStreamView` + unit tests.
3. **M3 Shell:** title bar, frameless, `AnimatedStackedWidget`, shadows.
4. **M4 Study workspace:** splitter, reuse `SlideGridWidget`, sync engine.
5. **M5 Process page:** dropzone, settings drawer, live `TranscriptStreamView`.
6. **M6 Focus mode + polish + docs** (`DECISIONS.md`, `HANDOFF_PHASE_V2_UI.md`).

## 7. Files

**Create:** `lecturepack/ui/themes/dark_theme.qss`,
`lecturepack/ui/widgets/title_bar.py`, `lecturepack/ui/widgets/transcript_block.py`,
`lecturepack/ui/widgets/animated_stacked.py`, `lecturepack/ui/widgets/focus_mode.py`,
`tests/test_ui_phase2.py`, `docs/HANDOFF_PHASE_V2_UI.md` (M6)

**Modify:** `lecturepack/ui/theme.py`, `lecturepack/ui/main_window.py`,
`lecturepack/ui/pages/study_page.py`, `lecturepack/ui/pages/process_page.py`,
`docs/DECISIONS.md`, possibly `tests/test_study_workspace_v12.py`
(documented, intentional-only), `docs/ARCHITECTURE.md` (M6)

**Explicitly untouched:** controllers, services, infrastructure, models,
`review_page.py`, `transcript_page.py`, `slide_grid.py` (reuse only),
`settings_page.py`, all Phase 1 streaming code paths.
