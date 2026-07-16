# Transcription engine benchmark — v1.1.0

Hardware: AMD Radeon RX Vega 56 8 GB (driver 31.0.21923.11000, Vulkan 1.3),
Windows 11. Audio: Egypt excerpt WAV (363.1 s, 16 kHz mono). Model:
`ggml-base.en.bin`, 8 threads, each binary's default decoding settings.

| Engine | Binary | Backend line reported | Wall time | Realtime factor |
|---|---|---|---|---|
| whispercpp-cpu (verified, ships since v0.2) | `bin/Release/whisper-cli.exe` | `no GPU found` → CPU | **48.7 s** | 7.5× |
| whispercpp-vulkan (new) | `bin/vulkan/whisper-cli.exe` | `using Vulkan0 backend` (Radeon RX Vega) | **33.3 s** | 10.9× |
| whispercpp-vulkan forced CPU (`-ng`) | `bin/vulkan/whisper-cli.exe -ng` | `no GPU found` | 81.4 s | 4.5× |

Notes:
* The Vulkan build (MinGW, single generic AVX2 CPU dll) is slower than the
  verified MSVC CPU build when forced to CPU — one more reason the verified
  CPU binary remains the CPU engine; the Vulkan binary is used only for GPU.
* **Speedup Vulkan vs verified CPU: 1.46×** on transcription. In the full
  pipeline (parallel scheduler) the excerpt went 156.2 s (v1.0.1) → 47.8 s
  (v1.1 parallel + Vulkan): **−69 %**.

## Accuracy examples (Vulkan vs verified CPU, same model)

Word-level similarity 92.3 % (1157 vs 1156 words). Differences are
punctuation/format and occasional homophones, in **both directions** — no
systematic quality loss on either backend:

| Vulkan | CPU (verified) | Better |
|---|---|---|
| "this **precision** is pretty incredible" | "this **position** is pretty incredible" | Vulkan |
| "aligned to the compass within **360 of a degree**" | "within **3/60 of a degree**" | CPU |
| "**4500** years ago" | "**forty-five hundred** years ago" | equivalent |
| "the hundred plus pyramid scattered" | "the hundred-plus pyramids scattered" | CPU |

## faster-whisper evaluation (Phase 7 optional engine — NOT adopted)

Researched (repo v1.2.1): CPU-only viability on this machine is poor — GPU
support is CUDA-only (unavailable on AMD), CPU int8 gains over whisper.cpp
are modest, and the dependency stack (ctranslate2, tokenizers, onnxruntime,
huggingface_hub + CT2-converted models) would add ≳150 MB to the portable ZIP
and new PyInstaller failure modes. With Vulkan already giving a measured GPU
win at zero Python-dependency cost, faster-whisper was not integrated. The
engine interface (`transcription_engines.py`) accommodates it later without
pipeline changes.
