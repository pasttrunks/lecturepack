## Conflict Detection Report

### BLOCKERS (0)

No blockers detected.

---

### WARNINGS (1)

[WARNING] Pipeline stage count inconsistency across SPEC documents
  Found: docs/PRODUCT_SPEC.md Section 5 lists 8 stages (inspect, extract audio, transcribe, extract frames, detect slides, deduplicate, align, export)
  Found: docs/ARCHITECTURE.md Section 4 also lists 8 stages, but Section 12 (as-built addendum) states the shipped v1.0.1 has 7 stages (frame extraction, detection, and dedup collapsed into single "Detect Slides" stage; export is user-triggered not auto-run)
  Impact: Downstream roadmapper may plan phases against the 8-stage model when the codebase implements 7. The PRODUCT_SPEC has not been updated to match the as-built reality.
  -> Update PRODUCT_SPEC.md Section 5 to reflect the 7-stage as-built pipeline, or note the discrepancy explicitly before routing to phase planning.

---

### INFO (2)

[INFO] No LOCKED-vs-LOCKED ADR contradictions
  Note: The single ADR file (docs/DECISIONS.md) contains 13 decisions (AD-1 through AD-13), all with locked: true status. All 13 decisions are internally consistent and address distinct scopes. No precedence conflicts exist.

[INFO] ADR DECISIONS.md supersedes embedded decisions in DOC-type documents
  Note: docs/LecturePack_Project_History_Architecture_and_Roadmap.md and docs/PROJECT_HISTORY_AND_DECISIONS.md contain ADR-like decision entries (deterministic CV pipeline, out-of-process isolation, self-contained exports, state machine with atomic writes). These are historical narrative entries consistent with the locked ADR decisions in DECISIONS.md. The DOC entries do not contradict the ADR; they are lower-precedence historical descriptions of the same decisions.
