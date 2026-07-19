# Contributing to LecturePack

Thanks for your interest in contributing! This document covers everything you need to know before submitting a PR.

---

## Development Setup

```bash
git clone https://github.com/your-user/LecturePack.git
cd LecturePack
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Run the full test suite before submitting:

```bash
.venv\Scripts\python.exe -m pytest
```

---

## Project Structure

```
lecturepack/
  app.py                    # Entry point
  constants.py              # Version, stage names, paths
  controllers/              # JobController (state machine)
  services/                 # Transcription, slide detection, export, study
  infrastructure/           # FFmpeg, whisper, CV engine, config, secrets
  ui/
    main_window.py          # Shell (nav rail, pages)
    pages/                  # Home, Study, Process, Review, Transcript, Exports, Settings
    widgets/                # Reusable components (slide grid, title bar, focus mode, etc.)
    theme.py                # Dark/light palette, QSS loading
```

---

## Safety Rules (Non-Negotiable)

These rules exist to protect user data and trust. Violations will be rejected without review.

### 1. Never Delete `LecturePackData`

`~/LecturePackData` is the user's persistent data directory. Your code must **never** delete, move, or overwrite it. Jobs inside it must survive any operation. If you need to clean up, delete only temp files you created — never user data.

### 2. Never Modify or Delete Original Lecture Videos

The original video file is the user's source of truth. Your code must never write to, rename, move, or delete the original lecture file under any circumstances.

### 3. Preserve Layered Persistence

The transcript has four layers (Raw, Normalized, Context Proposals, User-Approved). Each layer is immutable once written. You must never modify or delete a layer's output after it is created. If you add a new layer, it must be additive — not destructive to existing layers.

### 4. No Silent Overwrites

Always use atomic writes (write to `.tmp`, then `os.replace()`). Never overwrite user-facing files without going through the layered pipeline.

### 5. Never Execute Transcript Content

Transcript text must never be used as shell commands, Python `eval()`, or any form of code execution. Always treat it as inert data.

### 6. Safe Path Handling

All external process invocations must safely handle:
- Paths with spaces
- Paths with non-ASCII characters (Windows Unicode paths)
- Paths with special shell characters

Use `shlex.quote()` or list-based argument passing where possible.

---

## Code Style

- Python 3.12
- PySide6 (Qt Widgets) for UI
- No `print()` in production code — use `logging`
- Type hints on public APIs
- Docstrings on public classes and methods
- Follow existing patterns in the file you're editing

---

## Commit Messages

Use conventional commits:

```
feat: add slide bookmark toggle
fix: prevent orphaned whisper process on cancel
docs: update architecture diagram
test: add edge case for empty transcript alignment
```

---

## Pull Request Guidelines

1. **Scope**: One logical change per PR. Don't bundle unrelated fixes.
2. **Tests**: Add or update tests for any behavior change. Run `pytest` before pushing.
3. **No secrets**: Never commit API keys, tokens, or credentials. The `SecretStore` uses Windows Credential Manager — follow that pattern.
4. **No telemetry**: LecturePack is local-first. Do not add network requests, analytics, or phone-home behavior.
5. **No new dependencies** without discussion in an issue first. Justify any new dependency.
6. **Documentation**: If you change user-facing behavior, update the relevant docs.

---

## Reporting Bugs

Use the [Bug Report template](https://github.com/your-user/LecturePack/issues/new?template=bug_report.md). Include:

- Steps to reproduce
- Expected vs actual behavior
- Log file contents (`~/LecturePackData/logs/app.log`)
- Your OS and GPU

---

## Requesting Features

Use the [Feature Request template](https://github.com/your-user/LecturePack/issues/new?template=feature_request.md). Describe the problem you're trying to solve, not just the solution you want.

---

## Code of Conduct

Be respectful. We're all here to build something useful. Constructive feedback is welcome; personal attacks are not.
