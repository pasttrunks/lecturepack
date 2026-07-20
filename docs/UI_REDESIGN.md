# LecturePack UI — Studio Redesign Changelog

## Overview

Redesigned the LecturePack desktop UI from "Premium Glassmorphic Dark" (Catppuccin Mocha) to a **refined neobrutalist "Studio"** style, matching the `LecturePack Studio.dc.html` mockup. Both light and dark themes are supported equally. The layout was restructured from a narrow nav rail to a full sidebar with section labels.

---

## Layout Changes

### Header Bar (replaces title bar + command bar)
- **56px height**, `AppHeaderBar` object name
- Left: 28x28 blue logo mark (square + white diamond) + "LecturePack" wordmark ("Pack" in accent blue)
- Vertical divider
- Breadcrumb label (e.g. "egypt_excerpt > Process") — updates on page change
- Theme toggle button (JetBrains Mono, uppercase label)
- Save button (panel style)
- Export button (orange CTA with orange-ink border)
- Right: min/max/close window controls (–, □, ×)
- 2px blue accent line at bottom edge
- Window dragging and double-click maximize preserved

### Sidebar (replaces 76px nav rail)
- **224px width**, `NavSidebar` object name
- **Job status card** at top (hidden when no job active): thumbnail frame + title + status text
- **Section labels** in JetBrains Mono, 10px, uppercase, letter-spacing 0.14em:
  - `Library` → Home
  - `Workspace` → Process, Review, Transcript, Study
  - `Output` → Exports
- Settings at bottom (before stretch)
- Nav buttons: full-width, 38px height, 1.5px transparent border, 9px border-radius, Space Grotesk 600 13.5px
  - Hover: panel2 background
  - Checked: accent-soft bg, accent-ink text, accent border, font-weight 700

### Status Footer (replaces native statusBar)
- **34px height**, `AppStatusFooter` object name
- Left: stage label (JetBrains Mono 600 11px, uppercase, orange) + progress bar (7px, accent color) + elapsed time
- Right: engine info label + warning label + QSizeGrip

---

## Color Tokens

### Dark Theme
| Token | Hex | Role |
|-------|-----|------|
| `DARK_BG` | `#131519` | Window background |
| `DARK_PANEL` | `#1B1E24` | Cards, sidebar, header |
| `DARK_PANEL2` | `#21252C` | Hover states, job card |
| `DARK_SUNK` | `#171A1F` | Sunken inputs, progress track |
| `DARK_INK` | `#ECE7DB` | Primary text |
| `DARK_MUTED` | `#8C93A2` | Secondary text |
| `DARK_BORDER` | `#000000` | Card/widget borders |
| `DARK_LINE` | `#2C313A` | Dividers, scrollbar handles |
| `DARK_BLUE` | `#38ADE8` | Primary accent (dark) |
| `DARK_BLUE_SOFT` | `#12303F` | Nav active bg, selection |
| `DARK_ORANGE` | `#FF6C36` | CTA buttons |
| `DARK_GREEN` | `#4CCB86` | Success states |
| `DARK_RED` | `#FF6E5E` | Danger/error |
| `DARK_YELLOW` | `#F2C24A` | Warning |
| `DARK_NAV_INK` | `#AEB3BF` | Nav button text |

### Light Theme
| Token | Hex | Role |
|-------|-----|------|
| `LIGHT_BG` | `#F3F0E8` | Window background |
| `LIGHT_PANEL` | `#FFFFFF` | Cards, sidebar, header |
| `LIGHT_PANEL2` | `#F7F4ED` | Hover states |
| `LIGHT_SUNK` | `#F0ECE2` | Sunken inputs |
| `LIGHT_INK` | `#1C1A16` | Primary text |
| `LIGHT_MUTED` | `#8A8173` | Secondary text |
| `LIGHT_BORDER` | `#241F19` | Card/widget borders |
| `LIGHT_LINE` | `#E3DCCD` | Dividers |
| `LIGHT_ACCENT` | `#EF5A1E` | Primary accent (light) |
| `LIGHT_BLUE` | `#0E82C4` | Secondary accent |
| `LIGHT_GREEN` | `#128A52` | Success |
| `LIGHT_RED` | `#D63A2C` | Danger |
| `LIGHT_YELLOW` | `#D99400` | Warning |
| `LIGHT_NAV_INK` | `#4A4438` | Nav button text |

---

## Typography

| Usage | Font | Weight | Size |
|-------|------|--------|------|
| Body/UI | Space Grotesk | 400–700 | 13–18px |
| Monospace/labels | JetBrains Mono | 500–700 | 10–13px |
| Section labels | JetBrains Mono | 500 | 10px |
| Nav buttons | Space Grotesk | 600–700 | 13.5px |
| Headings (h1/h2) | Space Grotesk | 700/600 | 18px/14px |
| Log area | JetBrains Mono | 500 | 12px |

---

## Files Modified

### Core Theme
| File | Lines | Description |
|------|-------|-------------|
| `lecturepack/ui/theme.py` | ~280 | Color tokens, QPalette, QSS generation (header, sidebar, footer, nav, cards, inputs, buttons), `apply_theme()`, `selection_visuals()`, `add_card_shadow()` |
| `lecturepack/ui/themes/dark_theme.qss` | ~220 | Dark-only QSS: scrollbars, inputs, buttons, lists, tables, tabs, progress bars, splitters, menus, checkboxes, title bar buttons |

### Layout Shell
| File | Lines | Description |
|------|-------|-------------|
| `lecturepack/ui/widgets/title_bar.py` | ~170 | `HeaderBarWidget` class: 56px header with logo, wordmark, breadcrumb, theme toggle, save/export, window controls, drag |
| `lecturepack/ui/main_window.py` | ~1412 | `MainWindow._build_shell()`: header + 224px sidebar with sections + page stack + 34px footer. Compat aliases for tests. |

### Page Files (inline style updates)
| File | Changes |
|------|---------|
| `lecturepack/ui/pages/process_page.py` | Stage state colors → `theme.DARK_ACCENT`, `theme.SUCCESS`, etc. Dropzone icon color. Log area bg `#171A1F`, font from `theme.FONT_MONO`. Font-weight 600→700. |
| `lecturepack/ui/pages/review_page.py` | Selected count → `theme.ACCENT`. Preview label bg/border/color → dynamic theme. Edited segment border → `theme.SUCCESS`. |
| `lecturepack/ui/pages/transcript_page.py` | Empty text → `theme.DARK_MUTED/LIGHT_MUTED`. Link color → `theme.ACCENT`. AI tag, low-confidence, search highlight → theme tokens. |
| `lecturepack/ui/widgets/slide_grid.py` | Placeholder color → `theme.DARK_MUTED` / `theme.LIGHT_MUTED` |
| `lecturepack/ui/widgets/context_repair_panel.py` | Diff highlight colors uppercased. Status badge colors uppercased. |
| `lecturepack/services/export_service.py` | HTML export font → `Space Grotesk` |

### Tests
| File | Changes |
|------|---------|
| `tests/test_ui_phase2.py` | `TitleBarWidget` → `HeaderBarWidget` imports. Glyph assertions updated (□/▣ → \u25A1/\u25A3). Focus mode tests updated for sidebar/footer references. |

---

## Design Characteristics (Studio Refined Neobrutalism)

- **Borders**: 1.5px solid (not 1px, not 2px)
- **Border-radius**: 6–13px (rounded but not bubbly)
- **Shadows**: Soft multi-layer via `QGraphicsDropShadowEffect` (blur 14, yOffset 6, alpha 90)
- **No glassmorphism**: Opaque backgrounds, no rgba semi-transparency
- **Card hover**: `translateY(-2px)` + shadow elevation + blue border (CSS, not Qt-animated)
- **Status badges**: Colored dot + uppercase JetBrains Mono label in rounded pill
- **Nav active state**: Accent-soft background with accent border, full width

---

## Architecture Notes

- Frameless window preserved (custom title bar → header bar drag)
- Focus mode hides header + sidebar + footer
- Hidden `QComboBox` and `QLabel` instances for backward compatibility with tests referencing `recent_jobs_combo`, `mode_lbl`, `job_title_lbl`
- `_command_bar` set to `None` (removed in Studio layout)
- `_nav_rail` alias preserved for focus_mode (points to sidebar)
