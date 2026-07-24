# §10 Dark-theme secondary palette

Dark mode had large bright-cyan filled controls with white text (jarring / poor
contrast). Fixed to deep-blue/navy surfaces with cyan text/border per spec.

## Tokens (app/ui/app.css)
Added `--secondary-*` in both themes. Dark (spec exact):
    --secondary-surface:#12303F; --secondary-surface-hover:#173C4C; --secondary-surface-active:#1B465A;
    --secondary-border:#2D7186; --secondary-text:#9DE8EE; --secondary-icon:#72D5DE; --secondary-muted:#4A8996;
Light: derived light-cyan surface (#DDF5F9) + ink text (#0C6675).

## Controls retargeted from bright-cyan fill → secondary surface + cyan text
- Appearance Light/Dark toggle (`.lp-theme-btn.active`)
- Compute-engine CPU/Vulkan toggle (index.html + `reflectEngine` in app.js)
- Review Grid/List toggle
- Process "Balanced" sensitivity toggle
- Transcript "TXT" format chip
- Quiz + flashcard "Next"/"Finish"/"Summary" buttons (×4)
- "Export HTML" button

## Kept
Orange remains primary/current (Submit, active tabs, user bubbles). Green/red/
yellow stay semantic. Small progress markers/badges (timeline ticks, progress
bars, storage bar) stay bright `--blue` per spec. `--blue-soft`/`--blue-ink`
surfaces in dark were already deep-navy + cyan and are left as-is.

## Removed
Inert "Accent" swatch row in Settings (never wired/persisted).

## Tests
`tests/test_webview_theme.py` (5): secondary tokens defined both themes, dark spec
values present, no `background:var(--blue);color:#fff` anywhere, theme-button
active uses secondary surface, accent swatches gone.
