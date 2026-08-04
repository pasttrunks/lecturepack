# Multi-Agent Project Context & Communication Log

> **IMPORTANT FOR ALL AI AGENTS (Claude Desktop, ChatGPT / Codex, Cline / DeepSeek):**
> Read this file at the start of every session. All models working on this codebase MUST log their decisions, plans, edits, and test results into this file to maintain full context across sessions.

---

## 1. System Operating Rules for AI Agents

1. **Role Division**:
   - **Architect Agents (Claude Desktop / ChatGPT)**: High-level architectural planning, UI design specs, task breakdown, and code review.
   - **Executor Agents (Cline / DeepSeek / Codex)**: Code generation, file editing, terminal command execution, and test verification.

2. **Handoff Protocol**:
   - Before ending a session, the active agent MUST update **Section 4 (Execution Log & Code Modifications)** and **Section 6 (Pending Handoff & Next Steps)**.
   - Every code modification MUST be accompanied by verification results from running `pytest` or play-testing.

3. **Codebase Constraints**:
   - Work strictly within `C:\Users\marsh\Documents\LecturePack`.
   - Never break working tests or leave the codebase in an uncompilable state.
   - Do not replace technology stack without explicit user consent.

---

## 2. Current Project Phase & Goal

- **Project Name**: LecturePack
- **Current Phase**: Phase 6 - Engine Wiring & Desktop App Integration
- **Primary Goal**: Wire the existing Python processing engine into the PySide6 + WebEngine desktop UI shell.

---

## 3. High-Level Architecture & Plan (Architect Agent Output)

*Logged by Claude Desktop / ChatGPT*

### Active Architectural Plan:
- UI Layer: PySide6 + QWebEngineView rendering `app/ui/index.html`.
- Bridge Layer: `app/desktop/bridge.py` communicating via QWebChannel (`bridge.js`).
- Engine Layer: `app/desktop/engine_adapter.py` mapping UI events to `lecturepack/` core processing algorithms.

---

## 4. Execution Log & Code Modifications (Executor Agent Output)

*Logged by Cline / DeepSeek*

| Timestamp | Agent Name | File Modified | Action / Change Summary | Test Status |
| :--- | :--- | :--- | :--- | :--- |
| Initial | Setup | `MULTI_AGENT_CONTEXT.md` | Initialized multi-agent communication log | PASSED |
| 2026-08-03 | Codex | `electron-spike/`, `tests/test_renderer_spike.py`, `docs/DECISIONS.md` | Added isolated Electron renderer spike with static, mocked, and gated Python-sidecar modes; no Qt shell or engine rewrite | PASSED: packaged Static/Mocked smoke; Python engine handshake |

---

## 5. Verification & Test Evidence

- **PyTest Command**: `pytest tests/`
- **Playwright / Headless Check**: `python app/verify_ui.py`
- **Last Verification Result**: `npm run validate` passed; `pytest -q tests/test_renderer_spike.py` passed (8 passed); packaged Static and Mocked smoke passed with no page-load failure, no renderer-unresponsive event, and zero remaining Electron processes; packaged Python mode imported `lecturepack.controllers.job_controller.JobController` and answered a ping.

---

## 6. Pending Handoff & Next Steps

### Next Task for Executor Agent (Cline / DeepSeek):
1. Run the unversioned packaged spike on the affected laptop; leave Mode 2 open for ten minutes and retain the local JSONL evidence.
2. Use the decision table in `electron-spike/README.md` to determine whether an Electron shell migration is warranted.
3. Do not wire real lecture-processing commands into Mode 3 until the affected-laptop Mode 2 gate passes and the user explicitly approves that next step.
