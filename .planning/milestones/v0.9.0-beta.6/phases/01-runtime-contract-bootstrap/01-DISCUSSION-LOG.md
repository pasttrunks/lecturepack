# Phase 1: Runtime Contract & Bootstrap - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents. Decisions are captured in `01-CONTEXT.md`.

**Date:** 2026-07-27
**Phase:** 01-runtime-contract-bootstrap
**Areas discussed:** milestone source of truth, release boundary, required setup behavior, runtime selection, validation cadence, signing trust, and release evidence

## Source of Truth

**Selected:** `v0.9.0-beta.5` at commit `459faf5` and current `app/` package; define a new beta-6 milestone.

**Alternatives considered:** continue the stale v1.2 roadmap; research only.

## Runtime Selection

**Selected:** preserve a healthy CUDA/custom engine with bundled CPU fallback; visibly fall back when optional acceleration breaks; reset the default model to bundled `ggml-base.en.bin` on upgrade.

**Alternatives considered:** reset all engines to CPU; block on an optional-engine failure; silently fall back; preserve a custom model as default.

## Validation Cadence

**Selected:** lightweight checks every launch and full CLI/DLL/model smoke after first launch, update, repair, or payload identity change.

**Alternatives considered:** full smoke every launch; package-build checks only.

## Repair Trust Contract

**Selected for the milestone:** exact-version official GitHub assets, project-signed manifest, SHA-256 per payload, and transactional rollback.

**Phase 1 constraint:** verifier/dependency and signing operations require an explicit ADR and approval before Phase 2 implementation; no third-party dependency is pre-approved.

## Evidence

**Selected:** targeted and full pytest evidence, real packaged subprocess/runtime smoke, disposable hostile-path profiles, and a final CPU-only/NVIDIA/AMD-Intel physical matrix.

## the agent's Discretion

- Internal symbol names and exact payload-identity fields.
- Bounded smoke timeout values after minimum-CPU calibration.

## Deferred Ideas

- All user-facing setup, repair, onboarding, visual cleanup, and final hardware-matrix execution remain in their roadmap phases.

