# Milestone v0.9.0-beta.6 Learnings & Architecture Patterns

**Milestone:** v0.9.0-beta.6 — Clean-Machine Reliability and Onboarding  
**Date:** July 29, 2026  

---

## 1. Key Architectural Decisions

1. **Windows PySide6 DLL Path Resolution:**
   - Python 3.8+ on Windows 11 under GUI subsystems (`pythonw.exe` / PyInstaller `runw.exe`) requires calling `os.add_dll_directory` for `sys.prefix/Lib/site-packages/PySide6`, `shiboken6`, and `PATH` BEFORE importing `PySide6.QtCore`.
   - Eliminates `DLL load failed while importing QtCore` on fresh clean machines.

2. **Pointer Event Capture Isolation in Gate Overlays:**
   - Global event listeners (`pointerdown`, `wheel`, `keydown`) registered for modal gates (Phase 2 Repair) must evaluate `isBlocking() { return isOpen(); }`.
   - On healthy app boots when `#runtime-setup-overlay` is hidden, capture listeners must NEVER block mouse clicks on the underlying UI.

3. **Pure CSS Spotlight Overlay Pattern:**
   - Full-viewport SVG masks with cutouts can cause QtWebEngine hit-testing compositor barriers on Windows GPU acceleration backends.
   - Replacing SVG masks with a pure CSS spotlight box (`#tour-spotlight-box` using `box-shadow: 0 0 0 9999px rgba(8,10,14,0.65)`) with `pointer-events: none` preserves 100% clickability across the entire viewport.

4. **Ed25519 Signed Transactional Repair:**
   - Exact Ed25519 signature authentication over raw manifest bytes must occur BEFORE any archive acquisition or file parsing.
   - Atomic generation activation with immediate revalidation ensures that tampered, incomplete, or corrupted repairs safely roll back to the prior working generation.

---

## 2. Lessons Learned & Surprises

- **Lesson 1:** Always verify clickability and DOM pointer event interception on frozen PyInstaller executables in addition to source python runs.
- **Lesson 2:** Hostile non-ASCII Unicode paths (`LecturePack Testing Staging Ñº/`) must be included in automated subprocess smoke tests to guarantee path-escaping safety.
- **Lesson 3:** Keeping demo data strictly isolated from library state prevents sentinel-scoped temporary work from polluting normal user job history.
