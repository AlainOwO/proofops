# Recorded results

Generated from actual saved artifacts on 2026-10-05T01:42:22.103526+00:00. This table describes the supported local workflow; live/unrun work is listed separately. Full JSON and native workload summaries accompany it in docs/results/.

## Local verification

| Check | Observed result |
|---|---|
| Backend, policy and PostgreSQL integration | 94/94 passed; 0 failures; 0 skipped |
| Chromium browser workflows | 6 passed; 0 unexpected; 0 skipped |
| Fresh local checkout/runtime environment | Passed; frozen runtime install and keyless review/replay |
| Deterministic synthetic evaluation | 60/60 cases in 20 scenario groups |
| Terraform local validation | valid=True; 0 errors; 0 warnings; no plan/apply |
| Formatting/type/build/CI syntax | passed; exact commands and exits in verification.json |
| Research preservation | 384 files checked; 0 changed/missing |

## Template and provider evaluation

These are synthetic descriptive results, not independent real incidents or model quality parity. The deterministic outcome's safety counts are separate from semantic prose scoring.

| Task / policy | Observed count or status |
|---|---|
| Structured template explanations | 57/57 mechanically valid; 3 additional out-of-scope abstentions |
| Narrow authored explanation/coverage rubric | 60/60 correct; no live model prose scored |
| Applicable guard drafts | 54/54 correct |
| Inapplicable guard cases | 6/6 correctly returned no draft |
| Structured accepted-output coverage | 111/120 template tasks |
| Unsafe decision false negatives | 0/18 unsafe cases |
| Healthy decision false positives | 0/9 healthy cases |
| Correct evidence abstentions | 30/30 insufficient cases |
| Template incremental API spend | USD 0; zero provider calls |
| Template local processing latency | p50 0.235 ms; p95 0.284 ms; sequential runner, no API queue |
| cheap_only | 120 scheduled tasks unrun; live quality/cost/latency null |
| strong_only | 120 scheduled tasks unrun; live quality/cost/latency null |
| routed | 120 scheduled tasks unrun; live quality/cost/latency null |

## Measured local workload

Origin: local_observation, Linux ARM64 Docker on a shared development host. Baseline 2 CPUs / 512 MiB; candidate 1 CPU / 256 MiB. Same pinned local image/profile/dependencies, 100-request warmup, eight-minute full runs. No cloud cost or invoice measured. Each run/class is assessed separately; p95 values are not averaged.

| Run | Correct responses | p95 (ms) | HTTP failures | Contract result |
|---|---|---|---|---|
| baseline-smoke-01 | 20 | 3.100 | 0 | Smoke only; no capacity claim |
| baseline-calibration-01 | 20,399 | 5.942 | 1 | Passed |
| baseline-full-01 | 20,399 | 5.980 | 1 | Passed |
| candidate-full-01 | 20,399 | 5.481 | 1 | Passed |
| baseline-full-02 | 20,400 | 5.934 | 0 | Passed |
| candidate-full-02 | 20,399 | 6.166 | 0 | Passed |
| baseline-full-03 | 20,399 | 6.262 | 1 | Passed |
| candidate-full-03 | 20,399 | 6.190 | 1 | Passed |

Per-class p95 is checked independently against the same frozen 250 ms limit:

| Comparison run | Small p95 (ms) | Medium p95 (ms) | Large p95 (ms) |
|---|---|---|---|
| baseline-full-01 | 5.265 | 6.452 | 10.828 |
| candidate-full-01 | 4.955 | 5.868 | 9.299 |
| baseline-full-02 | 5.193 | 6.401 | 10.680 |
| candidate-full-02 | 5.397 | 6.701 | 10.966 |
| baseline-full-03 | 5.472 | 6.752 | 11.160 |
| candidate-full-03 | 5.394 | 6.710 | 11.127 |

Comparison complete: True; all six comparison runs passed: True. Actual bounded OOM plus repair confirmed: True. Inspect native summaries for every request class, failure count and dropped iteration. Frozen thresholds: at least 10,000 correct; p95 below 250 ms; HTTP failures below 1%; zero incorrect successes, dropped iterations or restarts.

The OOM experiment injected a 128 MiB startup allocation into a 64 MiB cgroup and then verified 20 correct responses at 256 MiB. This controlled failure does not establish a 2,048 MiB AWS memory bound. The local resize is a resource-allocation comparison, not measured cloud savings.

## Unrun prerequisites

Live AWS needs an exact authorized service/account and spending allowance. Paid model experiments need verified exact model IDs, credentials, current prices, positive budgets and independent semantic review. Remote CI needs a repository and protected workflow configuration. Windows commands need a Windows host. T24 needs a consenting uncoached peer; no feedback was fabricated.
