# LecturePack 0.9.0-beta.4

**Import from a link, accessibility, and interface polish**

Beta.4 keeps the bundled zero-setup local engine — transcription, slides,
transcript, exports, and built-in quizzes/flashcards still work immediately
after installation with no account, API key, GPU, or Ollama.

## New
- **Import a lecture from a link.** Paste a URL, confirm what was found, and
  LecturePack downloads it and starts a job. Three steps, with progress and
  cancel. Only fetch recordings you have the right to download.
- **Storage usage in the sidebar.** Shows what LecturePack is actually using
  and how much room is left. It stays hidden if the figure cannot be measured —
  it will never show a made-up number.
- **Poster thumbnails** on job cards and in the sidebar, generated from a real
  frame of your lecture.
- **Multi-select on Home** — pick several lectures and group or delete them in
  one go.

## Fixed
- **Import from a link never actually worked.** A threading fault meant the
  "Looking it up…" step hung forever, with no error shown. The whole feature
  was dead in every previous build; it now works end to end.
- **Workspace screens could show a different lecture's data.** With nothing
  loaded, Process/Review/Transcript/Study kept showing the last lecture's
  content. Screens now belong to a lecture, and a slow update arriving from a
  previous lecture can no longer paint over the current one.
- **Fresh installs showed a fake in-progress job** and an invented storage
  figure. Both are gone.
- Keyboard shortcuts no longer fire through an open dialog, and Tab no longer
  escapes behind it.
- The scheduler no longer accepts a time in the past.
- The Review screen's three-column layout now reflows instead of becoming
  unreachable on smaller windows.

## Accessibility
- **Text contrast now meets WCAG AA across the whole interface, in both
  themes.** This was a systemic fix, not a touch-up: white text on coloured
  buttons failed in five places, and the light theme had eleven failing
  colour pairs including every status badge.
- **Keyboard focus is now visible.** There were previously no focus styles at
  all, which made keyboard navigation effectively invisible.
- Icons on coloured buttons were also corrected — several were unreadable in
  dark mode.

## Interface
- Buttons and cards now respond to being pressed.
- Switching screens fades instead of cutting.
- Numbers that update in place (durations, percentages, sizes) no longer make
  the text around them shift.
- The transcript no longer re-animates every time it updates while a lecture
  is being transcribed.
- Reduced-motion preferences are respected throughout.

## Notes
- Windows only. No cloud processing, no account, no telemetry.
- Link import needs the optional `yt-dlp` component, which is included in this
  build. The button is hidden in builds without it.
- Everything still runs locally. Keep copies of important source videos and
  exports, and please report issues.
