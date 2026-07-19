# Phase 1: Packaging & Release - Context

**Gathered:** 2026-07-18
**Status:** Ready for gap-closure planning

<domain>
## Phase Boundary

Close the two release-integrity gaps in `01-VERIFICATION.md`: make every shipped artifact identify v1.2.0 correctly, and make the documented release builder a safe, fail-closed, repeatable producer of the complete portable package. Rebuilding and reverifying the portable release are in scope. New product features, live Groq validation, and the 47 disclosed adjacent-layer violations remain out of scope; Phase 2 owns strict architecture remediation.

</domain>

<decisions>
## Implementation Decisions

### Missing-input and publication policy

- **D-01:** Before cleanup or PyInstaller starts, validate the complete required input set: `ffmpeg.exe`, `ffprobe.exe`, all CPU Whisper files represented by `WHISPER_BINS` and `WHISPER_CPU_DLLS`, and every shipped release document.
- **D-02:** Vulkan is optional. A wholly absent Vulkan directory is allowed; if any Vulkan component is present, every file in `VULKAN_BINS` must be present or the build fails before cleanup.
- **D-03:** Preflight reports all missing, incomplete, stale, empty, or unsafe inputs together, exits nonzero, and leaves existing build and release outputs untouched.
- **D-04:** The documented release builder has no force or allow-incomplete path. It must never produce an incomplete release ZIP.
- **D-05:** Every shipped release document must identify v1.2.0 correctly during preflight. Stale release headings or banners are blocking, not warnings.
- **D-06:** Required binary inputs must be regular, non-empty files and must not be reparse-point substitutions. Executability is proven by the existing post-build frozen self-tests rather than executing every input during preflight.
- **D-07:** Build into a dedicated staging target and replace `dist-release` only after all build, inventory, integrity, and frozen validation checks pass. A failed build preserves the prior release.
- **D-08:** After a failed staged build, retain a compact failure log, safely remove only the validated staging directory, and preserve the prior release artifacts.

### Cleanup safety

- **D-09:** If `dist-release` contains entries outside the release allowlist, move those unexpected entries into a timestamped repo-local `release-backups/` directory outside all cleanup targets. Continue only if every move succeeds; otherwise abort without cleanup.
- **D-10:** Any reparse point, junction, or symlink in a cleanup target or candidate entry blocks the build. The builder must never traverse, move through, or delete its target.
- **D-11:** Automatic cleanup or replacement is limited to exact resolved direct children of the repository from a hardcoded allowlist: `build`, `dist`, the dedicated staging directory, and `dist-release`. Configurable arbitrary cleanup paths and prefix matching are forbidden.

### the agent's Discretion

- Choose the internal helper names, exception/result structures, and test organization that best fit the existing Python conventions.
- Choose the exact v1.2 release-note wording and manifest presentation, provided every shipped label reports v1.2.0 and the verification report's checksum/runtime coverage gaps are fully closed.
- Choose the compact failure-log filename and format, provided it contains actionable preflight/build failure details without secrets or user data.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and verified gaps

- `.planning/ROADMAP.md` Phase 1 — fixed release goal, success criteria, and Phase 2 architecture boundary.
- `.planning/REQUIREMENTS.md` — `REQ-version-bump`, `REQ-packaged-build`, packaging safety, tests, and traceability obligations.
- `.planning/phases/01-packaging-release/01-VERIFICATION.md` — authoritative structured gap list and required closure evidence.
- `.planning/phases/01-packaging-release/01-REVIEW.md` — source-review findings behind the builder safety and checksum gaps.
- `AGENTS.md` — mandatory phase discipline, safety constraints, permitted workflow, test evidence, and Git rules.

### Release architecture and decisions

- `docs/DECISIONS.md` AD-14 — `lecturepack.__version__` is the sole executable version authority; human-facing labels remain synchronized.
- `docs/DECISIONS.md` AD-15 — Phase 1 permits no new architecture violations; strict adjacency debt remains Phase 2 work.
- `docs/ARCHITECTURE.md` — portable Windows/PyInstaller architecture, privacy boundaries, and strict layer target.
- `docs/WINDOWS_PORTABLE_INSTALL.md` — expected portable-package installation and runtime contents.

### Shipped release content

- `README-FIRST.txt` — first-run release identity and instructions that must report v1.2.0.
- `RELEASE_NOTES.md` — current release description that must be rewritten for v1.2.0.
- `THIRD_PARTY_NOTICES.txt` — required shipped legal/runtime documentation.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `build_release.py`: already defines canonical `VERSION`, `WHISPER_BINS`, `WHISPER_CPU_DLLS`, `FFMPEG_BINS`, `VULKAN_BINS`, `sha256_file`, ZIP creation, and manifest generation. Gap closure should strengthen this entry point rather than introduce a second release builder.
- `tests/test_packaging_and_safety.py`: existing packaging/version/inventory coverage and the natural home for deterministic preflight, cleanup-rejection, publication, and checksum-completeness tests.
- `docs/evidence/v1.2.0/release/`: established location and format for build output, inventory, digest, and frozen self-test evidence.

### Established Patterns

- `lecturepack.__version__` is the canonical runtime/build version authority; release labels are non-authoritative consumers that tests must keep synchronized.
- External process paths are passed as argument lists, never through `shell=True`; all path handling must remain safe for spaces and non-ASCII Windows paths.
- Release validation excludes models, secrets, config, jobs, transcripts, slides, and original media; this boundary is unchanged.
- Safety checks must occur before destructive operations, and tests must prove rejection paths leave existing outputs intact.

### Integration Points

- `build_release.main()` is the documented release entry point and must own preflight, safe staging, publication, cleanup, and manifest completeness.
- `LecturePack.spec` remains the PyInstaller input; its hidden-import and frozen self-test guarantees from Plan 01-01 must not regress.
- `dist-release/BUILD_MANIFEST.json` and `SHA256SUMS.txt` must cover the ZIP and complete required runtime inventory, including root-level CPU Whisper files.

</code_context>

<specifics>
## Specific Ideas

- Unexpected manually saved release files should be preserved automatically in timestamped `release-backups/`, not deleted or left to block every build.
- Publication should behave transactionally from the operator's perspective: the last known-good release remains available until a fully validated replacement is ready.
- Failure output should be compact and actionable rather than retaining a large incomplete staging tree.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 gap closure. The 47 adjacent-layer violations remain explicitly assigned to Phase 2.

</deferred>

---

*Phase: 01-packaging-release*
*Context gathered: 2026-07-18*
