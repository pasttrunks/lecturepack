# Phase 1 Source Requirement Traceability

PREVALIDATION_STATUS: PASS
CURRENT_RUN_STATUS: GAP
OVERALL_STATUS: GAP

This pre-validation audit was performed against the actual bodies of the named
pytest nodes before collection. `STATUS: COVERED` means a concrete executable
assertion or the explicitly scheduled read-only audit covers the clause; it
does not claim that the current release run has passed. The current run
collected and passed every mapped pytest node, but the read-only architecture
audit found existing violations of the documented layer contract.

## REQ-core-conversion

- `REQ-core-conversion:C01` — The supported study-pack, transcript-only, and
  slides-only flows produce their mode-appropriate transcript/slide/study
  artifacts through the real controller pipeline. Mapping:
  `tests/test_integration.py::test_integration`,
  `tests/test_product_modes.py::test_transcript_only_mode`, and
  `tests/test_product_modes.py::test_slides_only_mode`. Assertion category:
  controller orchestration, persisted stage completion, and mode-specific
  artifact presence/absence. `STATUS: COVERED`
- `REQ-core-conversion:C02` — Core processing completes without a paid/cloud
  provider, account, telemetry, or usage service. Mapping: the same three nodes
  run the local controller path with local mock executable contracts and no
  provider configuration. Assertion category: private-local operational
  default. `STATUS: COVERED`
- `REQ-core-conversion:C03` — A local LLM remains optional rather than required
  for core conversion. Mapping: the same three nodes complete without LM Studio
  or another LLM endpoint. Assertion category: optional dependency absence.
  `STATUS: COVERED`

## REQ-privacy-safety

- `REQ-privacy-safety:C01` — P1, no telemetry or analytics. Mapping: targeted
  `PRIVACY_CHECK`. Assertion category: production import/source audit.
  `STATUS: COVERED`
- `REQ-privacy-safety:C02` — P2, network access is restricted to approved
  adapters. Mapping: targeted `PRIVACY_CHECK` plus
  `tests/test_groq_transcription.py::test_backend_requires_privacy_before_secret_or_upload`.
  Assertion category: network-client allowlist and consent-before-network.
  `STATUS: COVERED`
- `REQ-privacy-safety:C03` — P3, provider traffic contains audio/control fields,
  not video, slides, transcript text, or job metadata. Mapping:
  `tests/test_groq_transcription.py::test_http_client_retries_429_redacts_key_and_uses_audio_only`.
  Assertion category: captured localhost multipart request body. `STATUS: COVERED`
- `REQ-privacy-safety:C04` — P4, no university portal access or plaintext
  credential persistence. Mapping: targeted `PRIVACY_CHECK` and
  `tests/test_groq_transcription.py::test_http_client_retries_429_redacts_key_and_uses_audio_only`.
  Assertion category: prohibited-target/source audit and key redaction.
  `STATUS: COVERED`
- `REQ-privacy-safety:C05` — P5, export and re-export never delete the source job
  or candidate data. Mapping:
  `tests/test_packaging_and_safety.py::test_export_and_reexport_never_delete_job_or_candidates`.
  Assertion category: filesystem no-deletion invariant. `STATUS: COVERED`
- `REQ-privacy-safety:C06` — P6, transcript content is never executed through a
  shell. Mapping: targeted `PRIVACY_CHECK`. Assertion category: production
  `shell=True`/`os.system` prohibition audit. `STATUS: COVERED`
- `REQ-privacy-safety:C07` — P7, external process paths and arguments are passed
  separately, including Windows paths. Mapping:
  `tests/test_study_workflow.py::test_whisper_arg_construction`. Assertion
  category: QProcess program/argument-list construction. `STATUS: COVERED`
- `REQ-privacy-safety:C08` — All seven rules have executable evidence rather
  than a generic suite-pass inference. Mapping: C01-C07 nodes and targeted
  `PRIVACY_CHECK`. Assertion category: clause-level safety matrix.
  `STATUS: COVERED`

## REQ-transcription

- `REQ-transcription:C01` — Inspect/extract/transcribe produces canonical raw
  output with provider provenance and timestamped JSON/SRT/TXT behavior while
  retaining the established local pipeline. Mapping:
  `tests/test_integration.py::test_integration`,
  `tests/test_transcription_backend_contract.py::test_local_pipeline_keeps_canonical_raw_output_and_provider_provenance`, and
  `tests/test_transcript_formats.py::test_srt_vtt_shape`. Assertion category:
  real controller stages with mock CLI contracts, canonical output/provenance,
  and timestamp format shape. `STATUS: COVERED`
- `REQ-transcription:C02` — The TEST_PLAN transcription acceptance surface is
  exercised by current source tests. Mapping: the same three nodes. Assertion
  category: stage completion, non-empty canonical segments, runtime metadata,
  and ordered timestamp serialization. `STATUS: COVERED`

## REQ-slide-extraction

- `REQ-slide-extraction:C01` — The deterministic CV detector handles slide
  changes, progressive builds, distractors, transitions, and deduplication
  without an LLM. Mapping: `tests/test_slide_detection.py::test_slide_detection`,
  `tests/test_detection_targets.py::test_balanced_meets_targets`, and
  `tests/test_detection_targets.py::test_no_fade_or_caption_false_positive`.
  Assertion category: real CV worker, ground-truth precision/recall, and
  transition/caption false-positive guards. `STATUS: COVERED`
- `REQ-slide-extraction:C02` — TEST_PLAN slide-detection assertions meet the
  release target. Mapping: the same three nodes. Assertion category: detected
  event timing, target metrics, and distractor rejection. `STATUS: COVERED`

## REQ-alignment

- `REQ-alignment:C01` — A segment is assigned to the slide with greatest
  positive temporal overlap. Mapping:
  `tests/test_alignment.py::test_alignment_assigns_segment_to_greatest_overlap`.
  Assertion category: unequal adjacent-interval overlap through public
  `ExportService.align_and_export`. `STATUS: COVERED`
- `REQ-alignment:C02` — Exact equal overlap resolves to the earlier
  chronological slide. Mapping:
  `tests/test_alignment.py::test_alignment_equal_overlap_tie_goes_to_earlier_slide`.
  Assertion category: exact boundary tie through public export/alignment.
  `STATUS: COVERED`
- `REQ-alignment:C03` — Every slide receives at least one segment, using the
  established `id == -1` placeholder when no dialogue overlaps. Mapping:
  `tests/test_alignment.py::test_alignment_gives_every_slide_a_segment`.
  Assertion category: uncovered-slide placeholder and non-empty alignment.
  `STATUS: COVERED`
- `REQ-alignment:C04` — Every source segment maps to exactly one slide. Mapping:
  `tests/test_alignment.py::test_alignment_maps_every_source_segment_exactly_once`.
  Assertion category: flattened non-placeholder source-ID multiset.
  `STATUS: COVERED`

## REQ-export-formats

- `REQ-export-formats:C01` — PDF/HTML/TXT/SRT/JSON and registered transcript
  formats are emitted from source-derived data, with Study annotations escaped
  and provenance preserved. Mapping: `tests/test_exports.py::test_exports`,
  `tests/test_transcript_formats.py::test_serialize_registry_all_formats`, and
  `tests/test_study_workspace_v12.py::test_study_exports_include_user_data_without_mutating_sources`.
  Assertion category: artifact/signature checks, serializer registry, escaped
  HTML/PDF/JSON Study output, and source immutability. `STATUS: COVERED`
- `REQ-export-formats:C02` — TEST_PLAN export assertions pass. Mapping: the same
  three nodes. Assertion category: valid PDF header, embedded offline HTML,
  transcript formats, and safe re-export. `STATUS: COVERED`

## REQ-job-lifecycle

- `REQ-job-lifecycle:C01` — Jobs cancel safely and completed work can be reused.
  Mapping: `tests/test_scheduler_and_engines.py::test_cancellation_stops_both_branches`
  and `tests/test_scheduler_and_engines.py::test_stage_cache_reused_when_settings_unchanged`.
  Assertion category: terminal branch state, worker completion, and unchanged
  cached transcript signature. `STATUS: COVERED`
- `REQ-job-lifecycle:C02` — Per-stage state persists across reopen. Mapping:
  `tests/test_job_persistence.py::test_job_persistence`. Assertion category:
  atomic manifest/settings/state round-trip. `STATUS: COVERED`
- `REQ-job-lifecycle:C03` — Repeated export preserves job and candidate data.
  Mapping:
  `tests/test_packaging_and_safety.py::test_export_and_reexport_never_delete_job_or_candidates`.
  Assertion category: filesystem preservation after export/re-export.
  `STATUS: COVERED`
- `REQ-job-lifecycle:C04` — The TEST_PLAN lifecycle acceptance surface has
  current executable coverage. Mapping: all four nodes above. Assertion
  category: persistence, cancellation, resume/cache skip, and no-deletion.
  `STATUS: COVERED`

## REQ-study-workspace

- `REQ-study-workspace:C01` — The deterministic overview supports old-job empty
  state, atomic bookmark/note/resume persistence, completed-job Study landing,
  navigation, and escaped exports without source mutation. Mapping:
  `tests/test_study_workspace_v12.py::test_deterministic_overview_uses_loaded_backend_and_old_job_empty_state`,
  `tests/test_study_workspace_v12.py::test_slide_bookmark_note_and_resume_survive_restart`,
  `tests/test_study_workspace_v12.py::test_completed_job_lands_on_study_and_quick_navigation_works`, and
  `tests/test_study_workspace_v12.py::test_study_exports_include_user_data_without_mutating_sources`.
  Assertion category: deterministic derivation, old-job compatibility, atomic
  user state, UI routing, escaping, and source signatures. `STATUS: COVERED`
- `REQ-study-workspace:C02` — Study workspace tests pass and old jobs open
  without creating `study.json`. Mapping: the same four nodes. Assertion
  category: persistent workspace acceptance and lazy empty state.
  `STATUS: COVERED`

## REQ-provider-neutral-transcription

- `REQ-provider-neutral-transcription:C01` — The QObject backend contract,
  capabilities, controller injection seam, canonical raw outputs, cache
  identity, fail-closed local default, and provider metadata remain explicit.
  Mapping:
  `tests/test_transcription_backend_contract.py::test_capability_contract_is_explicit_and_json_safe`,
  `tests/test_transcription_backend_contract.py::test_controller_accepts_injected_backend_without_provider_logic`,
  `tests/test_transcription_backend_contract.py::test_local_pipeline_keeps_canonical_raw_output_and_provider_provenance`, and
  `tests/test_transcription_backend_contract.py::test_old_job_defaults_to_local_and_controller_records_provider_metadata`.
  Assertion category: JSON-safe capabilities, provider-neutral controller,
  canonical artifacts/provenance, and private-local fallback. `STATUS: COVERED`
- `REQ-provider-neutral-transcription:C02` — Unknown provider selection fails
  closed to Private Local and the contract tests pass. Mapping: the same four
  nodes, with fail-closed behavior exercised by the old-job/controller path.
  Assertion category: provider resolution and metadata persistence.
  `STATUS: COVERED`

## REQ-groq-transcription

- `REQ-groq-transcription:C01` — Size-aware overlapping chunks, ordered merge,
  overlap deduplication, resumable fake-server caching, secret hygiene, and
  isolated local fallback are executable. Mapping:
  `tests/test_groq_transcription.py::test_size_aware_chunk_plan_has_overlap_and_stays_in_order`,
  `tests/test_groq_transcription.py::test_merge_offsets_sorts_and_deduplicates_overlap`,
  `tests/test_groq_transcription.py::test_backend_mock_integration_resume_and_no_secret_persistence`, and
  `tests/test_groq_transcription.py::test_controller_online_failure_falls_back_without_stopping_slide_branch`.
  Assertion category: 23-MiB-aware planning, timestamp merge/dedup, resumable
  localhost fake provider, no secret persistence, and branch isolation.
  `STATUS: COVERED`
- `REQ-groq-transcription:C02` — Contract/fake-server validation passes without
  being mislabeled as live provider validation. Mapping: the same four nodes.
  Assertion category: deterministic provider contract. `STATUS: COVERED`
- `REQ-groq-transcription:C03` — Live Groq validation remains explicitly
  deferred because no production key is authorized. Mapping: release evidence
  scope assertion plus the fake-server nodes above. Assertion category:
  truthful validation provenance; no live claim. `STATUS: COVERED`

## REQ-stability

- `REQ-stability:C01` — Context Repair and application close remain
  non-blocking, close routes through controller cancellation, owned process
  trees terminate without killing unrelated processes, and runtime backend
  metadata persists. Mapping:
  `tests/test_stability_phase.py::test_context_repair_detach_is_nonblocking`,
  `tests/test_stability_phase.py::test_main_window_close_cancels_pipeline_and_repair_nonblocking`,
  `tests/test_stability_phase.py::test_owned_process_tree_terminated_but_unrelated_process_survives`, and
  `tests/test_stability_phase.py::test_backend_actual_value_persists_and_reloads`.
  Assertion category: close latency, controller cancel, PID-scoped termination,
  and state reload. `STATUS: COVERED`
- `REQ-stability:C02` — Stability acceptance requires sub-50-ms close behavior,
  owned-PID termination, unrelated-process survival, and persisted runtime
  backend. Mapping: the same four nodes. Assertion category: measured latency,
  process existence, and persisted JSON. `STATUS: COVERED`

## REQ-architecture-layers

- `REQ-architecture-layers:C01` — Production modules remain classified into
  UI, controller, service, and infrastructure layers. Mapping: targeted
  `ARCHITECTURE_CHECK`. Assertion category: whole-tree AST import
  classification. The audit parsed 42 production modules but found 47 imports
  that violate the documented adjacent-layer contract. `STATUS: GAP`
- `REQ-architecture-layers:C02` — Dependency direction is UI to Controller to
  Service to Infrastructure with no reverse dependency. Mapping: targeted
  `ARCHITECTURE_CHECK`. Assertion category: AST direction audit.
  Controllers currently bypass services to import infrastructure, and UI
  modules currently bypass controllers to import services/infrastructure.
  `STATUS: GAP`
- `REQ-architecture-layers:C03` — The controller accepts an injected backend
  without provider-specific logic. Mapping:
  `tests/test_transcription_backend_contract.py::test_controller_accepts_injected_backend_without_provider_logic`.
  Assertion category: provider-neutral controller seam. `STATUS: COVERED`
- `REQ-architecture-layers:C04` — UI does not directly import infrastructure
  and services do not import UI widgets. Mapping: targeted
  `ARCHITECTURE_CHECK`. Assertion category: forbidden layer-edge audit.
  The audit found direct UI-to-infrastructure and UI-to-service imports.
  `STATUS: GAP`
- `REQ-architecture-layers:C05` — Architecture constraints have executable
  enforcement rather than code-review-only inference. Mapping: targeted
  `ARCHITECTURE_CHECK` plus the injected-backend node. Assertion category:
  automated architecture gate. The gate executed and correctly failed on 47
  violations; the architecture contract is not currently satisfied.
  `STATUS: GAP`

## REQ-test-framework

- `REQ-test-framework:C01` — pytest/pytest-qt collects controller integration,
  the real deterministic CV worker, and native pixel-level UI assertions using
  the established fixture patterns. Mapping: `tests/test_integration.py::test_integration`,
  `tests/test_slide_detection.py::test_slide_detection`, and
  `tests/test_ui_v11.py::test_selected_tile_pixels_show_accent_outline`.
  Assertion category: Qt controller integration, real CV execution, and rendered
  pixel comparison. `STATUS: COVERED`
- `REQ-test-framework:C02` — The full suite and established TESTING.md patterns
  remain the release gate. Mapping: the same three representative nodes plus
  Task 2 collection and Task 3 full-suite commands. Assertion category:
  framework collection/execution. `STATUS: COVERED`

## Current-run verification

- All 37 mapped pytest node IDs were present in collection and reported
  `PASSED` in the full run (`MISSING_COLLECTION: none`, `MISSING_PASS: none`).
- The full suite passed: `158 passed in 113.56s (0:01:53)`.
- The development self-test passed within the 120-second timeout and reported
  LecturePack v1.2.0, cv2 5.0.0, PySide6 6.11.1, and offscreen Qt OK.
- `PRIVACY_CHECK: PASS` with zero privacy violations.
- `ARCHITECTURE_CHECK: FAIL` with 47 layer-edge violations.

The missing contract is strict adjacent-layer dependency direction: UI must
route through controllers, and controllers must route through services before
infrastructure. Repair requires a broad production architecture refactor that
is outside Plan 01-02's evidence-only authorization. No source files were
changed to hide or narrow this gap.

## Pre-validation conclusion

All thirteen inherited requirement rows have concrete executable mappings.
The only missing acceptance nodes were the four REQ-alignment behaviors, now
implemented in `tests/test_alignment.py`. No production source or unrelated
test file was changed. Pre-validation therefore passed as a mapping audit, but
the current release gate is `GAP` because the architecture audit failed.
