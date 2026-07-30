---
phase: 02-hard-setup-signed-repair
plan: 03
subsystem: runtime-repair
tags: [signed-repair, generation, bridge, rollback]
requires: [02-01, 02-02]
provides: [consent-gated repair offer, strict staged repair transaction, guarded desktop repair boundary]
affects: [setup-gate]
tech-stack:
  added: []
  patterns: [metadata-before-payload, operation-bound-offers, bounded-streaming, healthy-only-admission]
key-files:
  created: [lecturepack/services/runtime_repair.py, app/desktop/repair_worker.py]
  modified: [app/desktop/bridge.py, tests/test_runtime_repair.py]
decisions:
  - "Only the authenticated exact-version offer authorizes the fixed four archive URLs."
  - "The store-owned staged/post-pointer assess(trigger='repair') callback is the rollback-capable admission boundary."
metrics:
  tasks: 2
status: complete
---

# Phase 02 Plan 03: Signed Repair Service Summary

Completed the consent-bound signed repair consumer and desktop admission boundary.

## Delivered

- Metadata-only offers acquire exactly the authenticated manifest and signature before confirmation; the offer carries the exact version, fixed official source, friendly affected components, and checked four-archive byte total.
- Confirmed repair uses only fixed authenticated archive names/URLs, bounded chunk writes, archive SHA-256/size verification, strict component member sets, Windows path/ADS/device rejection, duplicate/case-collision rejection, special-entry rejection, streamed extraction, and complete canonical-inventory validation.
- Generation publication uses the existing transactional store with staged and post-activation canonical admission inside its rollback-capable callback. Download, validation, cancellation, permission, and admission failures retain the prior active generation.
- Repair events are ordered and JSON-safe, use one terminal result, classify offline exhaustion, and keep cancellation/idempotency operation-bound.
- The Qt worker registers an operation-scoped, thread-safe service event sink, so events reach the UI as each safe-boundary event occurs rather than being replayed after completion.
- The worker enriches the sole metadata-ready event; the bridge rejects concurrent confirmation, preserves cancellation routing until terminal delivery, filters stale/duplicate terminal events, and creates adapter/updater once only after canonical `HEALTHY` re-admission.
- The bridge consumes the final admission result established by the store callback; it no longer runs a second, unrollbackable post-commit assessment.
- Narrow copy/save diagnostic slots expose only the redacted service event report and confine saved reports to the application data directory.

## Coverage

- `tests/test_runtime_repair.py::test_offer_authenticates_only_manifest_and_signature_before_confirmation` — real trust offer is metadata-only and has the authenticated confirmation fields.
- `tests/test_runtime_repair.py::test_confirmed_repair_streams_exact_four_archives_and_admits_only_after_transaction` — exact four signed archives, canonical payload, event order, and admitted completion.
- `tests/test_runtime_repair.py::test_archive_rejection_preserves_the_prior_active_generation` — traversal, ADS, and case-collision rejection preserves prior pointer/content.
- `tests/test_runtime_repair.py::test_retry_exhaustion_is_offline_and_cancel_is_idempotent_without_archive_requests` — bounded retries, offline classification, no payload request, and one cancellation terminal result.
- `tests/test_runtime_repair.py::test_post_activation_admission_failure_rolls_back_before_terminal_failure` — store callback restores first-install pointer state after post-activation admission rejection.
- `tests/test_runtime_repair.py::test_worker_forwards_one_json_safe_ordered_offer_event` and `test_bridge_accepts_one_admitted_event_then_constructs_collaborators_once` — JSON-safe worker sequence and exactly-once healthy bridge construction.
- `tests/test_runtime_repair.py::test_cancel_at_streaming_extraction_and_activation_boundaries_preserves_selection` — cancellation at streaming, extraction, and activation boundaries preserves the prior selection.
- `tests/test_runtime_repair.py::test_archive_fault_matrix_rejects_special_duplicate_cross_component_and_size_bounds` — symlink, duplicate, cross-component ownership, and archive-bound rejection.
- `tests/test_runtime_repair.py::test_canonical_store_admission_failure_restores_pointer_and_bridge_never_constructs` — failed post-activation canonical admission restores the previous pointer and reaches one failed bridge terminal.
- `tests/test_runtime_repair.py::test_bridge_rejects_concurrent_start_and_ignores_repeat_cancel_and_out_of_order_terminal` — concurrent start, repeat cancel, and out-of-order terminal handling.
- `tests/test_runtime_repair.py::test_bridge_repair_diagnostics_are_redacted_copyable_and_confined` — sanitized copy/save diagnostics and traversal rejection.
- `tests/test_runtime_repair.py::test_worker_streams_started_and_progress_before_blocked_transport_completes` — live `started` and `progress` delivery before deliberately blocked metadata/payload transports are released, followed by exactly one terminal event.
- `tests/test_runtime_generation.py` remains the lower-layer matrix for streamed extraction bounds, links, hashes, pointer journal recovery, and byte-identical rollback.

## Corrections Incorporated

- Prior audit correction `4018fff` was retained: event forwarding, cancellation idempotency, concurrent-start rejection, and HEALTHY re-admission ordering.
- This completion pass removed the service's duplicate/manual extraction path in favor of `safe_extract_verified_archive`, added operation-terminal suppression/classification, and closed bridge cancellation/duplicate-confirmation races.

## Verification

```text
python -m pytest tests/test_runtime_repair.py tests/test_runtime_generation.py -q
28 passed, 1 warning in 2.17s

python -m pytest tests/test_runtime_repair.py tests/test_adapter_startup.py -q
27 passed, 1 warning in 1.91s

python -m pytest tests/test_runtime_repair.py tests/test_runtime_generation.py tests/test_adapter_startup.py -q
36 passed, 1 warning in 2.23s
```

The known cross-wave UI registration regression remains intentionally untouched: `python -m pytest tests/test_media_link_adapter.py -q` reports one failure because `repair_event` is declared by `app/desktop/bridge.py` but is absent from `app/ui/bridge.js`'s `SIGNALS` list. That file/test pair is Wave 3 ownership, so this plan does not claim the full suite is green.

## Task Commits

1. Initial Plan 02-03 implementation: `07de8b0`, `d939767`, `610b7dd`, `4de6546`, `6f4165b`.
2. Audit ordering correction: `4018fff`.
3. Completion hardening and expanded fault matrix: recorded by the follow-on commit for this summary.
4. Final audit closure (transactional canonical admission and repair diagnostics): recorded by the follow-on commit for this summary.
5. Live worker-event observability closure: recorded by the follow-on commit for this summary.
