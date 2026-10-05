# ProofOps implementation plan

Started 2026-10-05. Authority: `../BUILD_PROOFOPS.md` (read in full), then the companion blueprint, data guide, failure register and testing playbook. All implementation files, generated documentation and local artifacts belong in this directory. Research inputs are read-only.

## Scope and assumptions

- One explicitly mapped Linux/on-demand ECS Fargate service, account and region; initially x86_64. The shipped replay uses synthetic `ap-south-1` rates, an approved-in-fixture 2,048 MiB floor and clearly labelled evidence. These are not live approvals or current AWS quotes.
- The host is macOS. Use an isolated Python 3.12 environment, Node and Docker Compose. Supply macOS/Linux and Windows/PowerShell instructions. The user's `./proofops-app/` instruction replaces the brief's Windows sibling directory.
- Initialize a separate Git repository here so commits, CI paths and releases contain only the application; do not stage the parent research pack.
- Build both genuine model adapters. Default `AI_MODE=off`, empty API keys and no live spending. Live AWS/provider experiments require verified account/model configuration and an explicit budget. Their absence does not prevent local implementation or adapter tests.
- Use a dated rate-card path first; Infracost import, optional AWS connectors, hosted infrastructure and visual extras can be deferred. Three functional UI views are required.
- A deterministic engine owns findings, costs and outcomes. AI cannot approve, change facts, execute tools or activate policy. The limit is two billable attempts per language task, including retries.
- Runtime never reads `../data/evaluator_only/`, the labelled RCAEval index, fault-bearing source paths or evaluation labels. Copy only licensed/attributed billing data and curated development material into allowlisted application paths. Tests/evaluation own independent labels.
- Calibration freezes thresholds before candidate comparison. The initial full workload requires >=10,000 correct responses, p95 <250 ms, HTTP failures <1%, no incorrect successes, dropped iterations or restarts, and three comparable repetitions. A 20-request smoke run only tests connectivity/correctness.
- Four domain outcomes: `revise_change` (known applicable violation wins), `collect_evidence`, `request_review` (engineering review, not deployment permission), `out_of_scope`. Malformed input/execution failure is a job error.
- A local UI records review intent; enforcement trust comes from separately reviewed policy/template/scope revisions. A changed commit, image, contract, evidence or policy invalidates applicability.
- Record assumptions/deviations in `docs/decisions.md`, actual capabilities in `IMPLEMENTATION_STATUS.md`, and review improvements in `CHANGELOG.md`.

## Milestones and small commits

1. **Foundation:** repository, locked dependencies, Compose/PostgreSQL/migrations, typed records, minimal reporting workload, replay generator and baseline instrumentation. Exit: validated synthetic input and a functioning workload endpoint.
2. **Deterministic review:** supported Terraform normalization, identity/sensitivity/unknown handling, dated Decimal costs, evidence state/freshness/coverage, shared engine and CLI, sanitized reproducible bundles. Exit: deterministic reports and defined unsupported/invalid behavior.
3. **Guard and performance:** scoped typed memory policy, fixed Rego, trusted fixtures, expiry/applicability, compatible per-run comparisons. Exit: valid, unsafe and incomplete replays end to end. Cut only optional scope if this path is delayed.
4. **AI and collection:** bounded ECS/CloudWatch/STS collectors, OpenAI/Anthropic structured adapters, compact context, mechanical validation, routing, atomic budget ledger, accepted-output cache and uncertain-charge recovery. Exit: mocked contract/failure tests; live runs only when configured.
5. **Product path:** durable worker, validated bundle import, idempotent API, reviews/detail/outcomes UI, guard-draft inspection/export, CLI/CI summary and report artifacts. Exit: browser workflow and model-free guard reproduction.
6. **Verification and evaluation:** T01–T24 matrix, focused unit/property/policy/PostgreSQL/integration/browser/security checks, smoke/full workload and controlled pressure/repair, idempotent FOCUS analytics, 60 cases/20 groups split 8 development/4 calibration/8 test, template/cheap/strong/routed runner with semantic labels separate from format checks. Exit: saved honest pass/fail/inconclusive/unrun results.
7. **Handoff:** fresh setup/replay, bug/security review, improvements/changelog, final README, architecture/module/model/testing/learning references, interview walkthrough, two searchable PDFs rebuilt from editable sources and inspected page by page. Exit: documented local workflow, exact check results and explicit remaining prerequisites.

Run relevant checks after each meaningful layer, fix failures before moving on, and commit coherent passing steps. Do not fabricate passing model quality, AWS observations, OOM diagnosis, usability feedback or realized savings. A failing measured candidate remains a failing candidate.

## Validation strategy

- Unit/property tests: strict contracts, CPU/MiB/Decimal arithmetic, threshold equality, outcome precedence, unknown versus zero, sensitivity, units, scope, freshness and cache keys.
- Real PostgreSQL integration: migrations, foreign keys, idempotency conflicts, concurrent reservations/job claims, leases and crash/timeout recovery.
- Policy tests: actual pinned Conftest syntax and known-bad/repaired/equal/larger/unrelated/unknown/changed-applicability/exception fixtures; always-deny must fail.
- AWS/provider SDK contract tests: Stubber or HTTP-boundary mocks; bounded queries/pagination, identity, denied/empty/pending states, quota/throttle/refusal/truncation/usage.
- API/security/browser: import caps, archive traversal/symlinks/expansion, path isolation, redaction, origins, prompt injection, three report paths and stale applicability.
- Workload: independent integer-cent oracle; smoke then full comparable runs; preserve per-class distributions and generator failures. Controlled pressure stays disabled by default and requires enforced container limits.
- Evaluation: group-frozen split, evaluator-only expected answers, independent semantic rubric, actual usage/cost and latency, accepted coverage and denominators. Live-unrun results must be explicit.
- Docs: generated from inventory/results, searchable text/link/page validation and rendered-page layout inspection.

## Progress

- [x] Read research brief and required companion documents; inspect supplied artifacts.
- [x] Record scope, known differences and milestone plan.
- [x] Foundation and reproducible environment.
- [x] Deterministic engine and replays.
- [x] Guard/performance workflow.
- [x] Collectors, adapters, routing and accounting.
- [x] API, worker, UI and CI.
- [x] Tests, workload experiments and evaluation.
- [x] Bug/security review, documentation/PDFs and final handoff.

## Completed experiment decisions

- Kept Linux x86_64 as the reviewed Fargate architecture and Linux ARM64 Docker as separately labelled local measurements. Local calibration froze a 2 CPU / 512 MiB baseline and 1 CPU / 256 MiB candidate before three alternating comparison pairs. The observed local OOM/repair does not approve the synthetic 2,048 MiB AWS guard.
- Left both exact live model IDs and all model-specific price/quality fields unconfigured/null because no verified account access, current price selection or spending allowance was supplied. Both genuine SDK contracts and failures were tested with mocks; 360 provider-policy evaluation tasks remain unrun.
- Preserved the 20-group 8/4/8 split. An explicit pre-first-run vocabulary erratum changed six development finding-code labels, without changing outcomes, predicates or the split. No human annotation or general parity is claimed.
- `RATE_CARD_PATH` is an optional bounded CLI override; it is empty by default. An explicit `--rate-card` wins, both record the selected rate hash, and API bundles retain their own rate basis. This prevents accidental global replacement of an imported bundle's rates.
- Added new `--series` output directories for repeat workload experiments; original measurements and frozen input hashes remain preserved.
