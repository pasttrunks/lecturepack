# Lecture Pack -- Risk Register

**Last updated:** 2026-07-15 (Phase 0)

---

## Top 5 Highest-Risk Technical Assumptions

| # | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R1 | Vulkan build of whisper.cpp is unstable on AMD Radeon RX Vega 56. The GGML Vulkan backend requires Vulkan 1.3 driver conformance, and the Vega 56 is an older GPU. Driver bugs or incomplete conformance could cause crashes or incorrect output. | Medium | Medium | CPU fallback is the primary path and is always available. Vulkan is an optional accelerator. The diagnostics screen tests Vulkan with a 5-second probe before production use. If the probe fails, the app silently defaults to CPU. | Phase 2 | Open |
| R2 | Slide detection thresholds do not generalize across real-world lecture recording styles. The algorithm was designed with synthetic test data. Real lectures have varying recording quality, encoding settings, slide designs, and presentation styles. | High | Medium | Four presets provide different threshold sets. All thresholds are configurable in `settings.json`. Full decision metadata is recorded per frame for post-hoc analysis and threshold tuning. The slide review screen lets users manually correct errors. | Phase 3 | Open |
| R3 | whisper.cpp CPU transcription of a 1-hour lecture with the recommended model takes too long (>2 hours) on the i7-9700F. RTF estimates are from community benchmarks, not the exact target hardware. | Medium | High | Phase 2 includes a mandatory benchmark on the target hardware with at least 4 models. If `small.en` is too slow, `base.en` provides a faster fallback. Users choose their accuracy/speed preference. Quantized `large-v3-turbo-q8_0` may offer better accuracy at similar speed to `small.en`. | Phase 2 | Open |
| R4 | PyInstaller packaging breaks with the full dependency set (PySide6 + OpenCV-headless + scikit-image + ReportLab). Complex native dependencies sometimes produce packages that crash on clean machines. | Medium | High | Phase 5 includes a mandatory clean-machine test. Use `opencv-python-headless` to avoid Qt conflicts. Build in a clean venv. Standalone directory mode (not one-file) enables straightforward debugging. Nuitka is the tested fallback if PyInstaller fails. | Phase 5 | Open |
| R5 | ReportLab cannot produce acceptable PDF quality for the study pack (poor image scaling, bad page breaks, ugly typography). ReportLab gives full control but requires manual layout work. | Low-Medium | Medium | ReportLab's Platypus layout engine handles page breaks automatically. A dedicated PDF template with tested styles (fonts, margins, image scaling) will be developed during Phase 5 with visual review. WeasyPrint (with bundled GTK runtime) is a fallback, though it adds packaging complexity. | Phase 5 | Open |

---

## Additional Risks

| # | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R6 | FFmpeg LGPL compliance: accidental use of GPL-only features would require open-sourcing the app. | Low | High | Use the "essentials" LGPL build from gyan.dev. Document the exact build in `DECISIONS.md`. Never enable `--enable-gpl` components. Include LGPL text in `THIRD_PARTY_LICENSES.txt`. | Phase 1 | Open |
| R7 | Whisper model download fails (network issues, HuggingFace downtime). | Low | Medium | Downloads are resumable via HTTP Range headers. The app explains the error and offers retry. Offline use works once models are downloaded. Multiple mirror URLs could be added later. | Phase 2 | Open |
| R8 | scikit-image adds significant package size by pulling NumPy + SciPy as transitive dependencies. | Low | Low | NumPy and SciPy are already transitive dependencies of OpenCV. Marginal size increase is small. SSIM could be reimplemented using only OpenCV primitives if size becomes critical. | Phase 5 | Open |
| R9 | Temporal median filter is too slow for high-FPS presets (software demo at 3 fps). | Low | Low | Buffer is only 3-5 frames at 480px width. NumPy median on a stack of 5 small grayscale images is negligible computation. | Phase 3 | Open |
| R10 | Long continuous transcript segments overflow ReportLab page layouts. | Medium | Low | Platypus `Paragraph` flowable handles wrapping and pagination natively. Segments longer than ~2000 characters are split at sentence boundaries before passing to ReportLab. | Phase 5 | Open |
