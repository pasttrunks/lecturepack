# LecturePack v1.2.0 Evidence

## Phase 0 baseline and safety

The signed v1.1.0 package was run cold against the exact 4,479.9-second
Mesopotamia lecture from a fresh extraction path containing spaces. The run
used an isolated data directory, the same `ggml-small.en-q8_0.bin` model as the
user's current job, auto-selected Vulkan, and concurrent transcription/slide
detection.

| Artifact | Purpose |
|---|---|
| `baseline_performance.json` | Consolidated baseline, safety evidence, measured values, and explicit v1.1 telemetry gaps |
| `baseline_acceptance_v1.1.0.json` | Raw packaged acceptance result |
| `baseline_monitoring_summary.json` | External process-tree resource and source-integrity summary |
| `baseline_performance_samples.jsonl` | Two-second CPU/RAM samples and ten-second GPU samples |
| `baseline_acceptance_stdout.log` | Packaged driver's terminal result |
| `baseline_pytest_output.txt` | Authoritative complete suite: 106 passed |
| `baseline_pytest_output_timeout_120s.txt` | Preserved first runner attempt that hit the shell timeout at 87% |

Key result: required pipeline wall time was **619.31 seconds**. Transcription
was the critical branch at **605.41 seconds**, while slide detection took
**523.47 seconds** concurrently. The original video's full SHA-256 was unchanged
and no observed LecturePack child process remained.
