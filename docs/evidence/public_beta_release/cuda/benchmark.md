# CUDA engine — live validation (2026-07-22)

Real NVIDIA GPU run confirming the CUDA transcription backend works end-to-end.

## Machine
- GPU: **NVIDIA GeForce RTX 3070** (8 GB, compute capability 8.6), driver 610.74
- CUDA whisper.cpp: **whisper.cpp v1.9.1** official `whisper-cublas-12.4.0-bin-x64`
  (self-contained — bundles cuBLAS 12.4 + cudart; the 11.8 build omits cuBLAS
  and silently fell back to CPU, so 12.4 is the correct shippable artifact).
- Installed to `bin/cuda/whisper-cli.exe` (+ ggml-cuda.dll, cublas64_12.dll,
  cublasLt64_12.dll, cudart64_12.dll, …). `bin/` is gitignored — the binary is
  a local artifact, not committed.

## Backend confirmation (from whisper stderr)
```
ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):
  Device 0: NVIDIA GeForce RTX 3070, compute capability 8.6, VMM: yes
whisper_backend_init_gpu: device 0: CUDA0 (type: 1)
```

## Benchmark — 60 s lecture clip, same input, CPU vs CUDA
| Model | CPU wall | CUDA wall | Speedup |
| --- | --- | --- | --- |
| ggml-base.en | 6.33 s | 3.29 s | ~1.9× |
| ggml-small.en | 15.56 s | 4.56 s | ~3.4× |

The gain grows with model size (the encoder dominates and parallelizes on the
GPU); larger models / longer lectures widen it further. Not a flat "10×", but a
solid, real speedup that scales with workload.

## Registry / selection (real config)
- `detect_engines()` → CUDA **available** (RTX 3070 + bin/cuda binary).
- `resolve('cuda')` → `whispercpp-cuda` (explicitly selected)
- `resolve('cpu')` → `whispercpp-cpu`, `resolve('vulkan')` → `whispercpp-vulkan`
  (fixed: short UI aliases now honour explicit selection instead of falling
  through to auto).
- `resolve('auto')` → `whispercpp-cuda` once `cuda_benchmark_ok=True`
  (auto order CUDA > Vulkan > CPU, each gated on a real benchmark).

## Packaging note
The self-contained CUDA runtime is ~1.5 GB unpacked. It is deliberately **not**
bundled into the default installer (would bloat it for non-NVIDIA users). The
recommended path is an optional "CUDA acceleration" download pack (like Smart
Study), fetched on demand into `bin/cuda/`. Works today in the source/dev app.
