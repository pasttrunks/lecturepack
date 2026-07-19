# LecturePack -- Synthesis Report

**Generated:** 2026-07-17
**Mode:** new (no existing context)
**Precedence:** ADR > SPEC > PRD > DOC

---

## Document Counts by Type

| Type | Count | Source Files |
|------|-------|-------------|
| ADR | 1 | docs/DECISIONS.md (locked, contains 13 decisions AD-1 through AD-13) |
| SPEC | 4 | docs/ARCHITECTURE.md, docs/IMPLEMENTATION_PLAN.md, docs/PRODUCT_SPEC.md, docs/TEST_PLAN.md |
| PRD | 0 | (none) |
| DOC | 20 | All handoff files, OLLAMA_SETUP, PERFORMANCE_AND_BACKENDS, PRIVACY_AND_DATA, PROJECT_HISTORY_AND_DECISIONS, LecturePack_Project_History_Architecture_and_Roadmap, RISK_REGISTER, SLIDE_DETECTION_EVALUATION, STUDY_WORKSPACE, TRANSCRIPTION_AND_CONTEXT_REPAIR, TROUBLESHOOTING, WINDOWS_PORTABLE_INSTALL, WINDOWS_RUN_HANDOFF |
| UNKNOWN | 0 | (none) |

**Total:** 25 documents consumed

---

## Decisions Locked

**Count:** 13 decisions, all locked (Accepted status)

| ID | Title | Scope |
|----|-------|-------|
| AD-1 | QProcess + QThreading model | Process isolation |
| AD-2 | Per-stage state machine with atomic writes | Crash recovery |
| AD-3 | Plain files and JSON manifests (no database) | Data persistence |
| AD-4 | Application-relative binary paths | Packaging |
| AD-5 | Deterministic CV pipeline (no LLM) | Slide detection |
| AD-6 | ReportLab + img2pdf for PDFs | PDF generation |
| AD-7 | Self-contained HTML with base64 images | Offline export |
| AD-8 | PyInstaller over Nuitka | Windows packaging |
| AD-9 | Adaptive baseline + two-path slide detection | v0.4 enhancement |
| AD-10 | Non-blocking UI shutdown + PID-scoped process trees | v1.2 stability |
| AD-11 | Separate user study data from source artifacts | v1.2 study workspace |
| AD-12 | Provider-neutral transcription seam | v1.2 transcription architecture |
| AD-13 | Opt-in Groq transcription with Credential Manager | v1.2 online transcription |

All decisions extracted from: docs/DECISIONS.md

---

## Requirements Extracted

**Count:** 10 requirements

| ID | Source | Scope |
|----|--------|-------|
| REQ-core-conversion | PRODUCT_SPEC.md | Core product purpose |
| REQ-privacy-safety | PRODUCT_SPEC.md | Privacy rules P1-P7 |
| REQ-transcription | PRODUCT_SPEC.md | 12 transcription requirements |
| REQ-slide-extraction | PRODUCT_SPEC.md | CV pipeline, cascade, dedup |
| REQ-alignment | PRODUCT_SPEC.md | Timestamp overlap alignment |
| REQ-export-formats | PRODUCT_SPEC.md | 7 export formats |
| REQ-job-lifecycle | PRODUCT_SPEC.md | Cancel, resume, crash recovery |
| REQ-architecture-layers | ARCHITECTURE.md | 4-layer enforcement |
| REQ-implementation-phases | IMPLEMENTATION_PLAN.md | 6 development phases |
| REQ-test-framework | TEST_PLAN.md | pytest, fixtures, 9 assertion categories |

---

## Constraints

**Count:** 13 constraints

| Type | Count |
|------|-------|
| protocol | 5 |
| schema | 5 |
| nfr | 2 |
| (untyped) | 1 |

Key constraints include: 4-layer architecture enforcement, threading model (QProcess + QThread), 7-stage pipeline (as-built), state persistence (atomic writes), binary resolution (app-relative), whisper backend selection algorithm, data layout, source fingerprint, dependency matrix, JSON schemas, slide detection algorithm, privacy requirements (P1-P7), target hardware (i7-9700F + Vega 56), test execution rules.

---

## Context Topics

**Count:** 17 topic areas

1. Project history and milestones (v0.1 through v1.2)
2. Critical safety incident (destructive cleanup)
3. MVP verification results
4. Phase 0 decisions
5. v1.2 baseline profiling
6. v1.2 provider-neutral seam
7. v1.2 Groq architecture
8. v1.2 Groq live validation
9. v1.2 stability fixes
10. v1.2 study workspace
11. Ollama / local AI integration
12. Performance and backends
13. Privacy and data storage
14. Slide detection evaluation
15. Transcription and context repair
16. Troubleshooting
17. Windows portable install and risk register

---

## Conflicts

- **0 blockers**
- **1 competing-variant warning** (pipeline stage count discrepancy between PRODUCT_SPEC and ARCHITECTURE as-built addendum)
- **2 informational notes** (no LOCKED-vs-LOCKED contradictions; DOC narrative entries consistent with locked ADR)

Full detail: `C:\Users\marsh\Documents\LecturePack\.planning\INGEST-CONFLICTS.md`

---

## Intel Files

| File | Contents |
|------|----------|
| `decisions.md` | 13 locked ADR decisions with source, status, decision statement, scope |
| `requirements.md` | 10 user-facing requirements with source, description, acceptance criteria, scope |
| `constraints.md` | 13 technical constraints with source, type, content |
| `context.md` | 17 topic-indexed context notes with source attribution |

---

## Key Project Facts

- Windows-only desktop app (PySide6/Python 3.11)
- Converts lecture videos to slides, transcripts, and study packs
- Local-first with optional Ollama LLM and opt-in Groq Cloud transcription
- 4-layer architecture: UI -> Controller -> Service -> Infrastructure
- Version 1.1.0 published; v1.2 features on branch v1.2-hybrid-study (never packaged)
- 13 ADRs recorded, all locked
- Built for personal university lecture workflow, not commercial
- No telemetry, accounts, databases, or cloud by default
- 151 tests reported on v1.2-hybrid-study branch
