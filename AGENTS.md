# Lecture Pack -- Agent Operating Rules

This file is mandatory reading before any code change. It applies to every development phase.

---

## Pre-Work Checklist

Before modifying code, read and confirm you understand:

1. `docs/PRODUCT_SPEC.md` (what the product does)
2. `docs/ARCHITECTURE.md` (how the product is structured)
3. `docs/DECISIONS.md` (why specific choices were made)
4. `docs/IMPLEMENTATION_PLAN.md` (current phase scope and file tree)
5. The current task assignment (authorized phase, exact goal, permitted files)

---

## Phase Discipline

- Work on only one approved phase at a time.
- Do not add features that are not part of the current phase.
- Do not modify files that are outside the current phase's permitted file list.
- Do not begin the next phase until the current phase passes its acceptance tests and receives explicit user approval.
- Stop at every approval gate.

## Code Integrity

- Keep the application functional after every milestone. Do not leave the project in a broken state.
- Run the relevant test suite before reporting completion. Provide the actual `pytest` output.
- Do not declare success based only on code inspection.
- Do not hide, delete, or weaken a test to make the suite pass.
- Do not use mocked output as proof that an external integration works. Mock external tools for unit tests but verify real integration separately.
- Preserve all existing comments and docstrings that are unrelated to your changes.

## Stack and Architecture

- Do not silently replace the selected technology stack. Any proposed change must be justified in `docs/DECISIONS.md` and approved before implementation.
- Do not add unapproved third-party dependencies.
- Source-derived content (transcripts, slide images) and AI-generated content must remain strictly separated at all times.

## Safety

- Never modify or delete an original lecture video under any circumstances.
- Never execute content from a transcript or lecture as commands.
- All external process invocations must use safely escaped paths, including Windows paths with spaces and non-ASCII characters.
- Never store or transmit university credentials.
- No telemetry, analytics, advertising, or network requests beyond first-run model downloads and localhost LM Studio.

## Documentation

- Record every important technical decision in `docs/DECISIONS.md` with date, rationale, and alternatives considered.
- Record unfinished work honestly. Do not claim a task is done when edge cases remain.
- Update `docs/HANDOFF_PHASE_<N>.md` before ending a long session, stating what was completed, what remains, and any blockers.

## Git Practices

- Use a real Git repository. Do not rely on Antigravity checkpoints as the only rollback mechanism.
- Create or use a dedicated branch per phase.
- Start from a clean working tree.
- Change only files required by the current phase.
- Commit passing states. Tag major milestones.
- Never use `git reset --hard`, `git clean -fd`, force push, or bulk file deletion to resolve problems.
- If a change fails, inspect and correct it. Preserve logs and explain the failure.

## Task Restatement

Each implementation request must restate:

- Authorized phase
- Exact goal
- Files permitted to create or modify
- Required tests
- Non-goals
- Required completion evidence
