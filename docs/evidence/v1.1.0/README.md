# v1.1.0 evidence index

All timings on the target PC (AMD RX Vega 56, Windows 11), packaged executable
unless noted.

| File | What it proves |
|---|---|
| `baseline_performance.json` | v1.0.1 packaged baselines (m2, excerpt) + v1.0.1 full-lecture reference + bottleneck analysis |
| `final_performance.json` | v1.1.0 packaged results for all four media + acceptance-target checklist |
| `pipeline_scheduler_benchmark.json` | staged CPU vs parallel CPU vs parallel Vulkan on the excerpt (source mode) |
| `engine_benchmark.md` | CPU vs Vulkan transcription speed + accuracy examples; faster-whisper verdict |
| `vulkan_binary_checksums.txt` | SHA-256 of every shipped bin/vulkan artifact |
| `model_checksums.txt` | Official whisper model sources + SHA-256 (profiles) |
| `ollama_model_benchmark.json` | qwen3:1.7b vs qwen3.5:4b vs qwen3.5:9b repair accuracy/speed (default choice) |
| `context_repair_failure_tests.txt` | 16 fault-isolation tests, all passing |
| `final_m2.json`, `final_egypt_calm.json`, `final_egypt_videoheavy.json`, `final_egypt_full.json` | full packaged acceptance reports (stage times, artifacts, re-export no-rerun proof, layered-transcript checks) |
| `screenshots/` | every page, light + dark, real Windows platform |

Detector quality: the piped decoder scores P=R=1.0 on the real-media calm
ground truth (`tests/fixtures/ground_truth/egypt_excerptB_0500_0700.json`) —
identical to the legacy decoder — and the synthetic ground-truth suite
(`tests/test_detection_targets.py`) passes on the shipped path.
