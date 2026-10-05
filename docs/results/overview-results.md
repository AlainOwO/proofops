# Recorded results

Observed local verification, recorded 2026-10-05T01:42:22.103526+00:00. The technical guide and docs/results JSON contain complete commands, denominators and per-class measurements.

| Check | Observed result |
|---|---|
| Backend / policy / PostgreSQL | 94/94 passed |
| Real Chromium workflows | 6 passed |
| Fresh checkout and frozen runtime install | Passed; frozen runtime install and keyless review/replay |
| Deterministic synthetic evaluation | 60/60 cases, 20 groups, split 8/4/8 |
| Terraform local validation | 0 errors, 0 warnings; not deployed |
| Original research preservation | 384 files unchanged |

## Measured local workload

Three alternating eight-minute pairs used one pinned Linux ARM64 Docker image/profile/dependency state on a shared development host. Baseline: 2 CPUs / 512 MiB. Candidate: 1 CPU / 256 MiB. Thresholds were frozen before candidates. This is not AWS x86_64 operating-bound evidence or measured cloud savings.

| Run | Correct responses | p95 (ms) | HTTP failures |
|---|---|---|---|
| baseline-full-01 | 20,399 | 5.980 | 1 |
| candidate-full-01 | 20,399 | 5.481 | 1 |
| baseline-full-02 | 20,400 | 5.934 | 0 |
| candidate-full-02 | 20,399 | 6.166 | 0 |
| baseline-full-03 | 20,399 | 6.262 | 1 |
| candidate-full-03 | 20,399 | 6.190 | 1 |

All six comparison runs passed: True. Required: p95 below 250 ms and HTTP failures below 1%. Observed incorrect successes / dropped work / restarts: 0 / 0 / 0. Separate bounded OOM plus repair confirmed: True; 128 MiB pressure at a 64 MiB limit, then 20 correct responses at 256 MiB.

## Model evaluation status

The template run produced 57 structured explanations plus 3 coverage abstentions, and 54 applicable guard drafts plus 6 correctly inapplicable cases. These are narrow synthetic/template results. 360 paid-provider policy tasks are unrun; unrun quality/cost/latency stay null. Confidence or strong-model agreement never supplies truth.
