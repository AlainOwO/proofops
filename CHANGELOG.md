# Changelog

## UI polish — 2026-10-05

- Split the frontend entry point into an app shell, reviews/report/outcomes components, a workspace hook, and shared presentation helpers. The extraction preserves markup, API requests, hash routes, polling, form state and displayed review results.
- Assumptions: keep the existing local, single-service workflow and visual identity; use the supplied synthetic replays with recorded evaluation time and AI off. Review rules, outcomes, cost arithmetic, approved constraints and evidence requirements remain unchanged. Research files and evaluator data are outside this work; test outputs stay in ignored application artifacts.

## 0.1.0 — 2026-10-05

- Built a local Python/PostgreSQL/React application, persisted worker, shared CLI/CI review engine and three labelled replay paths. Added dated Decimal task-cost estimates, comparable workload checks, scoped Rego guards, draft validation/export, operator outcomes and idempotent FOCUS analytics.
- Implemented bounded AWS collectors and genuine OpenAI/Anthropic structured-output adapters, with explicit completion/failure states, a two-attempt router, atomic reservations, usage accounting and scoped accepted-output caching. Live integrations and model quality experiments remain unrun.
- Added a frozen 60-case/20-group evaluator, separate mechanical/semantic/guard scoring, split-specific denominators, explicit unrun provider results and input/output-bound rescoring that does not repeat paid calls.
- Recorded real local smoke/calibration/load and bounded OOM/repair experiments. Preserved native summaries and per-class results, froze thresholds before candidates and added separate experiment series to protect existing evidence.
- Added trusted-base CI examples, pinned action revisions and container base digests, validated optional zero-task AWS scaffolding, setup/operations/module/model/testing/learning references and reproducible searchable PDF tooling.

## Bug and security review improvements

- Reject duplicate/deep/non-finite JSON and oversized, duplicate, linked, encrypted or traversing ZIP entries; extract only supported plan facts and discard raw sensitive values. Bound configured rate-file reads and prevent any runtime path into evaluator/research data.
- Preserve an applicable known violation when failures reduce correct-request counts; do not average p95 or compare different architectures, images, populations, windows or dependency states. Keep missing costs and unavailable analytics distinct from zero.
- Require the exact trusted Rego template hash; validate and export the same proposal/spec/template/fixtures. Candidate policy or scope-map changes cannot replace the trusted revision. Replayed historical approval does not become current applicability.
- Retain uncertain charges after a dispatch/crash/timeout, use consistent lock ordering and idempotent attempt keys, and prevent duplicate redispatch or restart-based budget resets. Separate same-model retries from escalation statistics.
- Stop pending Logs Insights queries at the call cap; preserve denied/empty/pending states and redact log examples. No imported plan/repository code or model-supplied tool instruction is executed.
- Handle oversized model context without changing deterministic results. Reject invented citations/numeric facts mechanically; label valid-schema but unsupported causal/confident prose separately through independent semantic scoring.
- Prevent stale UI responses from replacing the selected review, show save success only after persistence, and display model-attempt latency/unit-cost limitations. Use loopback services, allowed hosts/origins, bounded request bodies and non-root API/worker containers.
- Verify exact selected rate hashes, with an empty-by-default environment override and explicit CLI flag precedence. Preserve original billing row identity, negative credits, null values and currencies.

This is a reviewed local demonstration, not a production security certification. Team identity/authorization, retention, protected deployment workflows and live account validation remain outside the implemented local scope.
