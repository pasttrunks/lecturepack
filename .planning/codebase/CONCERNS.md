# Codebase Concerns

**Analysis Date:** 2026-07-17

Scope: full repo at `C:\Users\marsh\Documents\LecturePack`, branch `v1.2-hybrid-study` @ `9d8d8f0`. Documented history in `docs/LecturePack_Project_History_Architecture_and_Roadmap.md` (cited as "History doc") is treated as evidence; code is the primary source of truth.

## Tech Debt

**Version strings are stale at 1.1.0 across all v1.2 work:**
- Issue: Three independent version constants were never bumped for the v1.2 phases, so artifacts written today carry wrong provenance.
- Files: `lecturepack/__init__.py:2` (`__version__ = "1.1.0"`), `lecturepack/constants.py:4` (`APP_VERSION = "1.1.0"`, written into every new job manifest at `lecturepack/models/job.py:40`), `build_release.py:28` (`VERSION = "1.1.0"`), `LecturePack.spec:2` (header comment says "v0.2.0").
- Impact: v1.2-created jobs and any future v1.2 build misreport themselves; support/acceptance evidence becomes ambiguous.
- Fix approach: introduce one version source (e.g. `__init__.__version__` imported everywhere else) and bump it per phase checkpoint.

**Packaging spec and build script lag the v1.1/v1.2 module tree:**
- Issue: `LecturePack.spec:21-53` hiddenimports predate `lecturepack/ui/pages/*`, `lecturepack/ui/widgets/slide_grid.py`, `lecturepack/ui/widgets/context_repair_panel.py`, `lecturepack/services/transcription_backends.py`, `lecturepack/services/groq_transcription.py`, `lecturepack/services/study_service.py`, `lecturepack/services/ai_repair_service.py`, `lecturepack/services/transcript_store.py`, `lecturepack/infrastructure/{secret_store,process_tree,video_reader,ollama_client,transcription_engines,whisper_detector}.py`. These currently resolve via the static import graph, but the spec has not been re-audited since v1.1 and v1.2 has never been packaged (History doc §14). `optimize=1` (`LecturePack.spec:62`) strips `assert` statements, silently neutering the selftest sanity check at `lecturepack/app.py:146`.
- Files: `LecturePack.spec`, `build_release.py`.
- Impact: The v0.2.0 incident class (startup crash from bad exclusions, History doc §9) is exactly what an un-audited spec reproduces at v1.2 packaging time.
- Fix approach: during the packaging phase, regenerate/audit hiddenimports against the current tree, drop `optimize=1` or remove asserts from validation paths, and run the packaged EXE on real media per the release gates in History doc §16.

**`run_packaged_validation` mutates real user data with hardcoded dev paths:**
- Issue: `lecturepack/app.py:13-118` hardcodes `C:\Users\marsh\LecturePackData` (line 13), a fixed job UUID (line 16), and an owner OneDrive path (line 75). It writes "Corrected packaged validation segment text" into that real job's edited layer (lines 40-44), clicks Reset, and triggers an export (line 70). The flag ships in the frozen EXE via `main()` (line 198).
- Files: `lecturepack/app.py`.
- Impact: Same hazard class as the recorded destructive-cleanup incident (History doc §9): an agent running `--run-packaged-validation` writes into live user jobs.
- Fix approach: point it at an isolated `LecturePackData_validation` dir or move it under `tests/`; never default to the real data dir.

**Stale validation script using removed API:**
- Issue: `tests/validate_real_video.py:59-60` sets `whisper.whisper_path` / `whisper.model_path`, attributes that no longer exist on `WhisperWrapper` (current attribute is `whisper_exe_path`, model is a per-call argument — see `lecturepack/infrastructure/whisper_wrapper.py:14,53`). Not pytest-collected (filename doesn't match `test_*.py`), so the bitrot is invisible.
- Files: `tests/validate_real_video.py`.
- Fix approach: rewrite against the current wrapper/backend API or delete; `lecturepack/acceptance.py` already covers real-media validation properly.

**Detector decision logic is duplicated ~400 lines across piped and legacy paths:**
- Issue: `lecturepack/infrastructure/cv_engine.py` `_run_piped` (lines 136-572) and `_run_legacy` (lines 577-986) carry near-identical cascade logic. They have already diverged: the deferred-acceptance `pending` mechanism (piped-only, lines 199, 461-481) does not exist in legacy, which still discards at the min-time gate (lines 899-904) — the exact timestamp-drift bug the piped path fixed.
- Files: `lecturepack/infrastructure/cv_engine.py`.
- Impact: any threshold/behavior change must be mirrored by hand; a missed mirror ships two different detectors.
- Fix approach: extract the per-sample decision/stability/persistence logic into shared functions called by both decode strategies.

**`QThread.terminate()` still used for align/export workers, contradicting AD-10:**
- Issue: `lecturepack/controllers/job_controller.py:171` and `:174` call `self.align_worker.terminate()` / `self.export_worker.terminate()` on cancel. `docs/DECISIONS.md` AD-10 explicitly rejected `QThread.terminate()` for Context Repair "because asynchronous thread termination can interrupt Python/Qt state at an unsafe point" — the same reasoning applies to `AlignWorker` (`job_controller.py:30-44`) and `ExportWorker` (`lecturepack/services/export_service.py:500-515`), which perform atomic JSON writes and PDF/HTML generation.
- Files: `lecturepack/controllers/job_controller.py`, `lecturepack/services/export_service.py`.
- Impact: terminating mid-write can strand `<file>.tmp` artifacts (`file_manager.py:9`) in job dirs and leaves Qt/Python state at an undefined point; the failure mode is rare but silent.
- Fix approach: add a cooperative cancel flag checked inside `ExportService.align_and_export()` (same pattern as `AiRepairWorker.cancel_event`), or detach-and-let-finish like `ai_repair_service.detach_and_stop()`.

**Synchronous subprocess runs on the GUI thread:**
- Issue: `FFmpegWrapper.inspect_video` (`lecturepack/infrastructure/ffmpeg_wrapper.py:73`) is `subprocess.run` with **no timeout**, invoked from GUI-thread call sites (`lecturepack/ui/main_window.py:499` on video select; `lecturepack/controllers/job_controller.py:411` for the INSPECT stage). `WhisperWrapper.get_supported_flags` (`lecturepack/infrastructure/whisper_wrapper.py:42-44`) runs `whisper-cli --help` synchronously with a 5 s timeout when the capability cache is cold (e.g. Vulkan engine path never probed by the async detector).
- Files: as above.
- Impact: a stalled ffprobe (OneDrive hydration, network drive) freezes the entire UI with no cancel affordance — this already happened once (History doc §9, OneDrive placeholder stall).
- Fix approach: move INSPECT into a QThread worker with a timeout; route flag probing exclusively through the async `WhisperCapabilityDetector` (`lecturepack/infrastructure/whisper_detector.py`).

**Groq chunk cache is unbounded and busted by no-op glossary changes:**
- Issue: `_GroqWorker` writes `groq-cache/<fingerprint>/audio/chunk-*.flac` + `responses/*.json` under the job transcript dir (`lecturepack/services/transcription_backends.py:263-268`) with no eviction. The fingerprint includes `request.prompt` (`lecturepack/services/groq_transcription.py:323-328`), but the Groq upload hardcodes `prompt=""` (`transcription_backends.py:305`) — so editing the glossary re-encodes and re-uploads every chunk for byte-identical requests, multiplying disk use. The local stage fingerprint in `job_controller._stage_fingerprint` (`lecturepack/controllers/job_controller.py:231`) likewise keys on glossary for all backends.
- Impact: ~5-6 MB FLAC per 10-minute chunk, duplicated per no-op setting change; a full lecture ≈ 50 MB per fingerprint, never cleaned.
- Fix approach: drop `prompt` from the Groq fingerprint (capabilities declare `supports_prompt=False`), add a cache-size cap/eviction, and disclose cache location in the privacy UI.

**Exports are built entirely in memory:**
- Issue: `export_service.py:248-253` base64-encodes every accepted full-res PNG into a single HTML string; `img2pdf.convert(image_paths)` (line 152) buffers the whole PDF. `docs/HANDOFF.md` §3 already records 5-15 s export times on 1080p slides.
- Files: `lecturepack/services/export_service.py`.
- Impact: an 80-slide 1080p job produces a >100 MB HTML string and a large in-memory PDF in one spike; scales linearly with lecture length.
- Fix approach: stream file writes, and emit downscaled JPEG/WebP for HTML instead of full PNG (thumbnails already exist at `frames/thumbs/`).

**Atomic JSON writes lack fsync:**
- Issue: `FileManager.write_json_atomic` (`lecturepack/infrastructure/file_manager.py:7-15`) does temp-write + `os.replace` but no `flush`/`fsync`, while the Groq output writer `_write_text_atomic` (`lecturepack/services/groq_transcription.py:313-320`) does fsync. State files (state.json, candidates.json) are therefore less crash-durable than transcript outputs.
- Fix approach: add `f.flush(); os.fsync(f.fileno())` before `os.replace` in `FileManager`.

**Re-selecting the same video always creates a new job:**
- Issue: `main_window._on_video_selected` (`lecturepack/ui/main_window.py:492`) constructs a fresh `Job` UUID per selection; no dedupe by source path. Job list accumulates duplicates of the same lecture.
- Fix approach: scan existing manifests for a matching `source.original_path` and offer "open existing" instead.

**Owner-machine paths baked into product/test code:**
- Issue: `lecturepack/app.py:13,75`, `tests/test_video_extensions.py:10` (OneDrive path in a tautological string assert), `tests/validate_real_video.py:12-13,59-60`. The suite and packaged CLI are coupled to `C:\Users\marsh`.
- Fix approach: parameterize via env vars or fixtures; keep the collected tests hermetic.

**Heavy per-selection work on the Review GUI thread:**
- Issue: `review_page._update_transcript_for_selected_slides` (`lecturepack/ui/pages/review_page.py:397-428`) re-reads `edited.json` from disk and constructs one `QTextEdit` + `QPushButton` per matched segment on every selection change; `_show_slide_preview` (line 287) decodes a full-resolution `QPixmap` synchronously per click.
- Impact: select-all on a 600+ segment lecture creates hundreds of cell widgets; preview decode stutters on 1080p+ PNGs.
- Fix approach: virtualize/paginate the table, cache edited overrides in memory, and decode preview images via the existing `ThumbnailLoader` pattern at capped resolution.

**Implementation plan document describes a tree that does not exist:**
- Issue: `docs/IMPLEMENTATION_PLAN.md` §1 lists `home_screen.py`, `job_queue.py`, `llm_service.py`, etc. — none exist; the real structure is pages/widgets/services under `lecturepack/`. Planners reading it will be misled.
- Fix approach: regenerate or annotate as superseded (the History doc §5 is the accurate as-built record).

## Known Bugs

**Piped detector can emit candidates whose image file was never written:**
- Symptoms: In pass 2, if `capture_native_frames` returns no frame for an accepted timestamp (cv2 seek/decode failure), the candidate remains in the finished list with an `image_filename` that does not exist on disk. Review shows "Image missing."; exports silently skip it; nothing logs the miss.
- Files: `lecturepack/infrastructure/cv_engine.py:556-568` (`if native is None: continue` writes nothing but keeps the candidate), `lecturepack/infrastructure/video_reader.py:220-244` (silent skip on failed seek), symptom surface at `lecturepack/ui/pages/review_page.py:291-292`.
- Trigger: any video cv2 can probe but not seek accurately (VFR, damaged index).
- Workaround: none in-app; fix by dropping or flagging image-less candidates and emitting a status line.

**Groq Online Accurate omits quiet intro audio:**
- Symptoms: Recorded in `docs/HANDOFF_PHASE_V1_2_GROQ_LIVE.md` (lines 35-36, 64): `whisper-large-v3` skipped the first ~20 s of the Egypt excerpt that Local and Fast transcribed. The merge layer only dedupes overlaps (`lecturepack/services/groq_transcription.py:257-283`); no client-side coverage check detects provider-side omissions.
- Files: `lecturepack/services/groq_transcription.py`, `lecturepack/services/transcription_backends.py`.
- Trigger: low-volume/noisy intros with Online Accurate.
- Workaround: use Online Fast or Private Local for such material; add a merged-duration vs source-duration sanity check that warns when coverage is short.

**`datetime_from_seconds` wraps at 24 hours:**
- Symptoms: `lecturepack/infrastructure/cv_engine.py:997-1004` formats from `td.seconds` only, discarding `td.days`; timestamps ≥ 24 h display as 00:00:00. Only cosmetic for realistic lectures.
- Fix approach: include days in the hour field (`td.days * 24 + hrs`).

**Capability probe over-reports Vulkan:**
- Symptoms: `whisper_detector._parse_help_text` (`lecturepack/infrastructure/whisper_detector.py:136-142`) classifies the binary backend as "Vulkan" if the string "Vulkan" appears anywhere in `--help` output (e.g. a flag description on the CPU build). Only affects the status-bar label until a real run overwrites it with the runtime-probed backend (AD-10 persistence at `job_controller.py:135-142`).
- Fix approach: require the exact `loaded Vulkan backend` phrase and drop the bare-substring clause.

**Claimed vs collected test counts drift:**
- Symptoms: handoffs record 151 passing tests (`docs/HANDOFF_PHASE_V1_2_GROQ_LIVE.md` line 58); the current tree collects 149 `test_*` functions under `tests/`. No record of which two were removed/renamed.
- Fix approach: re-run the full suite, record the actual count in the next handoff (History doc §16 "Honest reporting" gate).

## Security Considerations

**Groq API-key handling (by design solid; residual risks listed):**
- Risk: redaction is exact-string replacement plus a Bearer regex (`lecturepack/services/groq_transcription.py:92-97`). A provider error echoing the key in encoded/split form would survive. Tests prove the plain-401 case only (`tests/test_groq_transcription.py` `test_provider_error_redacts_secret`).
- Files: `lecturepack/services/groq_transcription.py`, `lecturepack/infrastructure/secret_store.py`, `lecturepack/services/transcription_backends.py`.
- Current mitigation: keys live only in Windows Credential Manager (`secret_store.py`), never in config/job JSON/logs; consent is per-job (`main_window._start_processing` lines 709-725); `_safe_error` strips local paths (`transcription_backends.py:117-124`); worker clears its key reference before merge (`transcription_backends.py:326`).
- Recommendations: also redact URL-encoded/base64 forms of the key; avoid `has_secret()` decrypting the full blob just to test existence (`secret_store.py:112-113` calls `get()` on every Settings refresh via `settings_page.refresh_groq_status`) — use `CredReadW` success without decoding; consider the audited `keyring` library instead of hand-rolled ctypes structs (`secret_store.py:23-38`), whose layout mistakes would be memory-unsafe and which has no OS-level automated test (all tests use fakes).

**Shell-open of manifest-recorded paths:**
- Risk: `os.startfile(video)` (`lecturepack/ui/pages/review_page.py:707`), `os.startfile(exports_dir)` (`main_window.py:1110`, `lecturepack/ui/pages/exports_page.py:114`) ShellExecute paths read from job manifests. A tampered manifest could point at arbitrary UNC/protocol targets.
- Current mitigation: manifests are local user data; threat model is low. Recommendation: restrict to `os.path.isfile` existing local paths before startfile.

**Transcript text in HTML/ReportLab exports:**
- Risk: injection of lecture/LLM text into generated markup.
- Current mitigation: `html.escape` applied throughout (`export_service.py:261,291-299,451-491`); `changed_words_html` escapes (`context_repair_panel.py:48-49`); AGENTS.md "never execute transcript content" holds. No gap found.

**Secrets in repo:** none detected (no `.env*`; `bin/`/`models/` git-ignored; evidence screenshots contain no keys). The `test_key` flow sends the key only to `https://api.groq.com` over TLS (`groq_transcription.py:131-146`).

## Performance Bottlenecks

**Unexplained benchmark-vs-real-world gap (no telemetry):**
- Problem: packaged validation reported 369.8 s for the 71.7-min lecture, while the owner observes ~10 min for a 4,479 s lecture (History doc §7.1, §14). Roadmap item 23 (per-job timing telemetry) is not implemented; per-stage times exist only in the acceptance report (`lecturepack/acceptance.py:104-105`) and are not persisted per job in normal use.
- Files: `lecturepack/controllers/job_controller.py` (no timing capture), `lecturepack/ui/pages/process_page.py` (display-only timers).
- Improvement path: record per-stage wall times + backend into `state.json` on every run; compare same-media across backends before further optimization.

**Legacy cv2-seek detector fallback is ~2× slower and still reachable:**
- Problem: `_run_legacy` random-seek decode was measured at 98.5 s of a 156 s pipeline (`lecturepack/infrastructure/video_reader.py` docstring; `docs/PERFORMANCE_AND_BACKENDS.md` §1). It activates whenever the ffmpeg path is missing, a mock, or not `.exe` (`lecturepack/infrastructure/cv_engine.py:79-94`).
- Cause: one full-res decode per sample/probe vs. one sequential piped decode.
- Improvement path: prefer the piped path via the bundled ffmpeg in all real deployments; warn in the UI when legacy engages (currently only a log line).

**Detector still requires cv2 to open the video (codec portability gap):**
- Problem: `_probe()` (`cv_engine.py:100-114`) and pass-2 `capture_native_frames` (`video_reader.py:230-243`) use `cv2.VideoCapture`. A codec the bundled ffmpeg decodes but cv2's Windows backend cannot (e.g. HEVC without OS codec pack) fails the whole DETECT stage — piped mode never gets a chance.
- Improvement path: probe via ffprobe (already bundled) instead of cv2, and run pass-2 capture through ffmpeg `-ss` extraction rather than cv2 seeks.

**Cold whisper.cpp startup per job:**
- Problem: every transcription spawns a fresh `whisper-cli` QProcess and reloads the model (`lecturepack/infrastructure/whisper_wrapper.py:161`); History doc §7.3 lists a persistent warm worker as future work. On short files, startup dominates.
- Improvement path: persistent ASR worker / model residency (roadmap item 20).

**GUI-thread full-res image decodes and per-refresh JSON scans:**
- Problem: preview decode per selection (`review_page.py:287`); `home_page.refresh_jobs` (`lecturepack/ui/pages/home_page.py:87-115`) and `main_window._reload_recent_jobs` (`main_window.py:517-534`) read every job's manifest+state synchronously; `study_service.build_overview` (`lecturepack/services/study_service.py:181-213`) re-reads five JSON files on every page switch (`main_window.py:422-423`); `transcript_page._render_full` rebuilds whole-document HTML per render.
- Improvement path: memoize per job with mtime-based invalidation; background the job-list scan once job counts grow.

## Fragile Areas

**Process-tree kill logic (`process_tree.py`):**
- Files: `lecturepack/infrastructure/process_tree.py`, consumers `ffmpeg_wrapper.py:145`, `whisper_wrapper.py:166`, `groq_transcription.py:231,245`.
- Why fragile: `taskkill /PID <pid> /T /F` is correct and tested (`tests/test_stability_phase.py` proves unrelated-process survival; evidence in `docs/evidence/v1.2.0/stability/`), but (a) there is an inherent PID-reuse race between process exit and taskkill invocation — a recycled PID could retarget the kill; (b) the piped decoder's ffmpeg (`video_reader.AnalysisFrameStream`, `video_reader.py:149-165`) is *not* wrapped in the owned-tree helper — only plain terminate/kill — and is not covered by the cancel report, so a hard app crash relies on pipe closure to reap it; (c) `QThread.terminate()` for align/export (see Tech Debt) bypasses the graceful contract entirely.
- Safe modification: never reintroduce name-based killing; keep kills scoped to PIDs returned by the owning QProcess/Popen; route any new child process through `terminate_qprocess_tree`/`terminate_owned_subprocess_tree`.
- Test coverage: good for QProcess/Popen paths; the `AnalysisFrameStream` orphan case and PID-reuse window are untested.

**Path handling with spaces and non-ASCII:**
- Files: all subprocess launches correctly use argv arrays (`ffmpeg_wrapper.py:67-73`, `video_reader.py:107-119`, `groq_transcription.py:217-228`, `whisper_wrapper.py:147-161`) — the recorded PowerShell concatenation incident (History doc §9) has no echo in product code.
- Why fragile: OpenCV image I/O uses narrow paths on Windows and its return values are unchecked: `cv2.imwrite(img_path, ...)` at `cv_engine.py:568` and `cv_engine.py:909`, `cv2.imwrite(out_path, frame)` at `main_window.py:114` (returns `True` regardless), `cv2.imread` at `cv_engine.py:959-960`. A job/data dir or video path containing non-ASCII characters can silently produce missing candidate PNGs (see Known Bugs) — and AGENTS.md explicitly demands non-ASCII-safe path handling.
- Safe modification: replace `cv2.imwrite` with `cv2.imencode` + binary `open().write()`, and check return values; add a non-ASCII path fixture to `tests/`.

**Settings migration (`config_manager.py`):**
- Files: `lecturepack/infrastructure/config_manager.py:57-83`, `lecturepack/infrastructure/file_manager.py:18-28`.
- Why fragile: currently the strongest-tested area (BOM via `utf-8-sig`, legacy `backend`→`engine` migration, unknown-key preservation, canonical rewrite — `tests/test_stability_phase.py`; History doc §9 records the original settings-loss incident). Residual: `load()` rewrites the config during load (line 80), so any future schema bump must keep that write atomic and idempotent; `EngineRegistry._cpu_exe` rejects configured paths containing the substring "vulkan" (`transcription_engines.py:104`) — a user path like `C:\tools\vulkan-build\whisper-cli.exe` (CPU build) would be misrouted to the Vulkan engine.
- Test coverage: good for migration; engine-path substring edge untested.

**OneDrive / cloud-placeholder media (documented lesson, NOT implemented in code):**
- Files: no implementation — grep finds placeholder awareness only in `docs/TROUBLESHOOTING.md:15-19` and History doc line 350 ("detect placeholders in UI" listed as the permanent control). Code paths that stall today: `ffmpeg_wrapper.inspect_video` (no timeout, `ffmpeg_wrapper.py:73`), audio extraction QProcess (no stall watchdog), `cv2.VideoCapture` open in `cv_engine._probe`.
- Why fragile: the exact incident (packaged run appearing hung on a sparse/reparse-point file, History doc §9) can recur with zero user-facing explanation.
- Safe modification: check `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` / `FILE_ATTRIBUTE_SPARSE_FILE` via `GetFileAttributesW` before processing, refuse with a hydration message, and add a timeout to `inspect_video`.

**Stage fingerprint invalidation:**
- Files: `lecturepack/controllers/job_controller.py:213-287`.
- Why fragile: source signature uses `int(st.st_mtime)` (1-second granularity, line 219) — a same-second same-size source replacement won't invalidate caches; jobs predating v1.1 have no fingerprints and are trusted unconditionally (lines 285-286); the local-backend cache key is deliberately frozen for compatibility (lines 238-251), so any future change to local invocation must bump `DETECTOR_VERSION`-style keys consciously.
- Test coverage: cache invalidation covered in scheduler tests; mtime granularity edge untested.

**Main-window compatibility alias surface:**
- Files: `lecturepack/ui/main_window.py:301-406` (property aliases onto page internals), consumers `lecturepack/app.py:31-65` and v1.0-era tests.
- Why fragile: aliases raise `AttributeError` at runtime if a page renames a widget; the packaged-validation driver depends on them.
- Safe modification: when refactoring pages, keep the alias block in the same commit; run `tests/test_ui_v11.py` first.

## Scaling Limits

**Job library:**
- Current capacity: dozens of jobs fine; `_reload_recent_jobs`/`refresh_jobs` read 2 JSON files per job per refresh.
- Limit: hundreds of jobs → multi-second startup/refresh stalls (synchronous scan).
- Scaling path: index file or lazy scan; archive old jobs (existing archive flow in `file_manager.py:69-86`).

**Transcript length / review widgets:**
- Current capacity: 630-segment lecture validated.
- Limit: review transcript table builds one widget pair per matched segment; multi-hour courses degrade selection responsiveness.
- Scaling path: virtualized list or paged segments.

**Groq online modes:**
- Current capacity: chunking handles arbitrary length (`plan_audio_chunks`, `groq_transcription.py:58-76`); concurrency capped at 4 (`transcription_backends.py:256-258`).
- Limit: account-specific Groq quotas (free tier 25 MB/upload and daily audio-seconds, per AD-13 sources) — full-lecture live benchmark was skipped because the media file was absent (`HANDOFF_PHASE_V1_2_GROQ_LIVE.md` line 45), so real quota behavior on long lectures is unmeasured.
- Scaling path: surface quota errors distinctly (already typed `rate_limit`/`quota`), measure a full lecture before promoting online modes (History doc §15.1).

**Slide candidates on video-heavy content:**
- Current capacity: ~1 keyframe/28 s on embedded video (documented, `docs/SLIDE_DETECTION_EVALUATION.md`).
- Limit: `detailed` preset at 2 fps on animation-heavy lectures grows candidate count; dedup only collapses adjacent near-duplicates within 10 s (`cv_engine.py:543`).
- Scaling path: adaptive sampling (roadmap item 22) and crop/ignore masks (existing UI).

## Dependencies at Risk

**Bundled whisper.cpp binaries (CPU build provenance):**
- Risk: the CPU engine in `bin/Release/` has shipped since v0.2 with checksums recorded in `docs/evidence/v1.1.0/model_checksums.txt`; Vulkan build is whisper.cpp v1.9.1 (`docs/PERFORMANCE_AND_BACKENDS.md` §3). There is no automated update path; model downloads depend on HuggingFace availability (open risk R7, `docs/RISK_REGISTER.md`).
- Impact: security/bug-fix uptake is manual; a HuggingFace outage blocks first-run model download.
- Migration plan: keep CPU binary as permanent fallback (already policy); document rebuild steps (exist for Vulkan) for the CPU build too.

**Unpinned `>=` requirements:**
- Risk: `requirements.txt` uses lower bounds only (`PySide6>=6.7.0`, `opencv-python-headless>=4.8.0`, `scikit-image>=0.22.0`, etc.); the packaged build pins reality, but dev envs can drift to untested majors. Pixel-level selection tests (`tests/test_ui_v11.py`, `lecturepack/ui/theme.py`) are Qt-version-sensitive.
- Impact: dev/packaged divergence of the class that caused the v0.2.0 crash.
- Migration plan: pin exact versions in a `constraints.txt` used by `build_release.py`.

**scikit-image for one function:**
- Risk: entire SciPy stack is pulled in for `structural_similarity` only (`cv_engine.py:26`); R8 (`docs/RISK_REGISTER.md`) already flags size; SciPy was the transitive dep behind the v0.2.0 exclusion crash.
- Impact: bundle size + packaging fragility.
- Migration plan: reimplement SSIM with cv2/numpy primitives and drop scikit-image.

**Groq API mutability:**
- Risk: models `whisper-large-v3(-turbo)` (`groq_transcription.py:29-30`), limits, and pricing are provider-mutable (acknowledged in AD-13, `docs/DECISIONS.md`).
- Impact: online modes degrade without code changes.
- Migration plan: `BackendRegistry.resolve` fails closed to Private Local (`transcription_backends.py:431-437`); keep model IDs configurable via config keys rather than constants.

**cv2/MSMF codec coverage:**
- Risk: `opencv-python-headless` on Windows relies on OS media codecs; HEVC and some MKV content fails to open (see Fragile Areas → codec gap) while bundled ffmpeg succeeds.
- Impact: DETECT stage fails on otherwise-supported files.
- Migration plan: move probe + native capture from cv2 to ffprobe/ffmpeg entirely.

## Missing Critical Features

**OneDrive placeholder detection:** documented as the permanent control for the stall incident (History doc line 350) but no code exists — see Fragile Areas. Blocks safe processing of cloud-synced lecture folders.

**Per-job timing telemetry:** required to diagnose the 6.2-min validation vs ~10-min user observation divergence (History doc §7.3 item 23, §14). Nothing persists per-stage timings in normal runs.

**v1.2 packaging and release:** stability, Study, and Groq phases are unshipped; the published release remains v1.1.0 (History doc §14). `LecturePack.spec`/`build_release.py` are unvalidated against the current tree (see Tech Debt).

**Provider-omission guard:** no coverage validation on merged Groq output (see Known Bugs — Accurate intro skip).

**Incremental results during processing:** transcript segments/slides are not published until stage completion (History doc §7.3 item 19); perceived-latency issue remains open.

**VAD real-media validation:** VAD flags are plumbed (`whisper_wrapper.py:100-127`, `process_page.py` VAD controls) but History doc Appendix A still records "VAD not fully real-tested" — the feature ships without evidence it preserves speech.

## Test Coverage Gaps

**Live Groq path:**
- What's not tested: real provider latency, quota, timestamp quality, and the Online Accurate omission behavior. All automated coverage is fake-server/monkeypatched (`tests/test_groq_transcription.py` uses `ThreadingHTTPServer` on 127.0.0.1 and patched `urlopen`; `tests/test_transcription_backend_contract.py` is contract-level). Live validation exists only as a manual handoff (`docs/HANDOFF_PHASE_V1_2_GROQ_LIVE.md`) whose full-lecture leg was skipped.
- Risk: provider-side regressions reach users first.
- Priority: High (blocks the promote/keep/remove decision in History doc §15.1).

**Codec-fallback asymmetry:**
- What's not tested: cv2-fails-but-ffmpeg-succeeds media (HEVC etc.); mocks only cover the reverse (ffmpeg absent → legacy, `cv_engine.py:79-94`, `tests/fixtures/mock_ffmpeg.py`).
- Risk: DETECT stage hard-fails on valid input.
- Priority: High.

**Non-ASCII / spaces-in-path image I/O:**
- What's not tested: candidate PNG writing/reading under non-ASCII job or video paths; `cv2.imwrite` returns are unchecked (`cv_engine.py:568`).
- Risk: silent missing images; violates the AGENTS.md non-ASCII requirement.
- Priority: High.

**Windows Credential Manager integration:**
- What's not tested: real `CredWriteW`/`CredReadW` round-trip — all coverage uses injected fakes (`transcription_backends.BackendRegistry(secret_store=...)`); evidence is a manual screenshot (`docs/evidence/v1.2.0/groq_backends/credential-manager-settings.png`).
- Risk: ctypes struct bug ships undetected (memory-unsafe).
- Priority: Medium (manual validation recorded; automate a Windows-only round-trip test).

**Cancel during Align/Export:**
- What's not tested: `QThread.terminate()` mid-export (`job_controller.py:171,174`) — no test exercises cancellation of `ExportWorker`/`AlignWorker`; the 13-artifact re-export proof covers only the success path.
- Risk: stranded `.tmp` files / undefined Qt state.
- Priority: Medium.

**GUI-thread stall guards:**
- What's not tested: `inspect_video` without timeout, `--help` probe with 5 s timeout, `DetectionPreviewDialog.closeEvent` unbounded `worker.wait()` (`main_window.py:1253`), `SlideGridWidget` loader `wait(2000)` (`slide_grid.py:215,240`), `GroqTranscriptionBackend.cancel()` `wait(750)` (`transcription_backends.py:396`).
- Risk: UI freezes under stall conditions; no regression alarm exists.
- Priority: Medium.

**Review-page scale:**
- What's not tested: select-all on a full-length job (600+ segments) widget build cost in `review_page.py:397-428`.
- Risk: multi-second selection stalls on real lectures.
- Priority: Low.

**Suite-count drift:** 149 collected vs 151 recorded at the last handoff — identify the two removed/renamed tests before the next checkpoint (see Known Bugs).

---

*Concerns audit: 2026-07-17*
