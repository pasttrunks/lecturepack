# Performance & Transcription Backends (v1.1)

## Why v1.1 is faster

Measured on the reference PC (AMD RX Vega 56, Windows 11) with the 6-minute
Egypt excerpt; v1.0.1 packaged baseline = **156.2 s** end-to-end.

| Configuration | Wall time | vs v1.0.1 |
|---|---|---|
| v1.1 staged, CPU engine | 113.3 s | −27 % |
| v1.1 parallel, CPU engine | 76.3 s | −51 % |
| v1.1 parallel, Vulkan engine | **47.8 s** | **−69 %** |

Evidence: `docs/evidence/v1.1.0/baseline_performance.json`,
`pipeline_scheduler_benchmark.json`.

### 1. Two-pass slide detection decode
v1.0 decoded a **full-resolution frame with a random seek** for every 1 fps
sample, every 0.25 s stability probe, and every persistence probe. On H.264
sources each seek re-decodes from the previous keyframe, so this dominated the
pipeline (98.5 s of 156 s on the excerpt).

v1.1 runs one FFmpeg process that decodes the video **once, sequentially**,
applying crop → downscale (480 px) → grayscale in-process and streaming raw
analysis frames over a pipe (`video_reader.AnalysisFrameStream`). A sliding
`FrameCursor` window serves the detector's look-ahead probes from memory.
Full-resolution frames are decoded only at the final accepted candidate
timestamps (tens of seeks instead of thousands).

The decision algorithm is unchanged and locked in by ground-truth tests
(`tests/test_detection_targets.py`, real-media calm-section P=R=1.0). If
FFmpeg is missing the detector transparently falls back to the v1.0 seek path.

### 2. Concurrent transcription + detection
After audio extraction the two heavy stages are independent; the v1.1
scheduler runs them concurrently, so wall time trends toward the slower
branch instead of the sum. Under CPU+CPU contention each branch slows ~20 %
but total time still drops ~33 % vs staged. Disable in *Settings →
Transcription engine & pipeline* if you need the machine responsive while
processing.

### 3. Optional Vulkan GPU engine
`bin/vulkan/whisper-cli.exe` is whisper.cpp **v1.9.1** built with the ggml
Vulkan backend (see `THIRD_PARTY_NOTICES.txt` and
`docs/evidence/v1.1.0/vulkan_binary_checksums.txt`). On the RX Vega 56 it
transcribed the excerpt in 33.3 s vs 48.7 s for the verified CPU binary
(1.46×), with 92 % word-identical output (differences are punctuation and
occasional homophones in both directions — see
`docs/evidence/v1.1.0/engine_benchmark.md`).

Engine selection (`Settings → Default engine`):

* **Auto** — uses Vulkan only when the binary is present, a Vulkan runtime
  (`vulkan-1.dll`) exists, AND the machine benchmark recorded Vulkan as
  faster (`vulkan_benchmark_ok`). Never assumes the GPU is faster.
* **CPU (verified)** — the binary that has shipped since v0.2; always the
  fallback.
* **Vulkan** — explicit; degrades to CPU with a visible reason when
  unavailable.

The status bar shows the **actually loaded** backend, parsed from
whisper.cpp's own output (`whisper_backend_init_gpu: using Vulkan0 backend`
vs `no GPU found`). Force-CPU on the Vulkan binary uses `-ng`.

### 4. Stage cache keys
Each completed stage records a fingerprint over its actual inputs:

| Stage | Cache key includes |
|---|---|
| Extract Audio | source path + size + mtime |
| Transcribe | source sig, model, engine, glossary, language, VAD settings |
| Detect Slides | source sig, preset, detector version, crop, ignore masks |

Re-running a job skips stages whose fingerprints match (shown as *Cached*)
and automatically re-runs stages whose inputs changed. Jobs from v1.0 have no
fingerprints and are trusted as-is (no forced reruns).

### 5. Perceived performance
Stage list with per-stage progress, elapsed and ETA; live logs drawer;
thumbnails decode off the GUI thread into a WebP cache
(`frames/thumbs/`); Cancel kills worker processes (terminate → kill
escalation) and never leaves orphaned ffmpeg/whisper processes.

## Model profiles

| Profile | Model file | Notes |
|---|---|---|
| Fast | `ggml-base.en.bin` (141 MB) | default, verified since v0.2 |
| Balanced | `ggml-small.en-q8_0.bin` (252 MB) | quantized small.en |
| Accurate | `ggml-small.en.bin` (465 MB) | full small.en |
| Custom | any user-selected `.bin` | |

Profiles resolve to the first matching file in `models/` (app dir, parent
dir, or `LecturePackData/models`). Official sources + SHA-256:
`docs/evidence/v1.1.0/model_checksums.txt`. Large models are **not** bundled
in the portable ZIP.

## Rebuilding the Vulkan engine

```
git clone --depth 1 --branch v1.9.1 https://github.com/ggml-org/whisper.cpp
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=1 \
      -DBUILD_SHARED_LIBS=ON -DGGML_BACKEND_DL=ON -DGGML_NATIVE=OFF
cmake --build build -j
```

Requires CMake, Ninja, a C++ compiler and the LunarG Vulkan SDK (for
`glslc`). Copy `build/bin/{whisper-cli.exe,libwhisper.dll,ggml*.dll}` plus the
compiler runtime DLLs into `bin/vulkan/`. With `GGML_BACKEND_DL`, deleting
`ggml-vulkan.dll` turns the same binary into a CPU-only build.
