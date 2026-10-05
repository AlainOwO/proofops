# Implementation status

Updated 2026-10-05. This file records actual implementation and verification, not intended outcomes.

| Area | State | Evidence / remaining work |
|---|---|---|
| Plan and research boundaries | Implemented | `PLAN.md`, `docs/decisions.md`; no research files edited. |
| Local environment and domain engine | Implemented and tested | Locked Python/Node dependencies, pinned container bases, PostgreSQL migrations, four outcomes, sanitized Terraform normalization, Decimal costs and shared CLI. Fresh separate checkout installed 45 runtime packages and reproduced a keyless review. |
| Guard and performance | Implemented and tested | Fixed scoped Rego family; ten actual Conftest fixtures; exact template/spec/fixture binding; per-run/per-class comparison and current-applicability checks. |
| Collectors and model adapters | Implemented; mocked contract tests passed | Bounded STS/ECS/CloudWatch/Logs adapter and official OpenAI Responses/Anthropic Messages SDKs; failure/usage/citation tests. Live integrations remain unrun. |
| Routing, budget and recovery | Implemented and tested | At most two attempts, atomic PostgreSQL reservations, scoped complete-output cache, persistent leases and uncertain-charge recovery without duplicate dispatch. |
| API/worker/UI/CLI | Implemented and tested | Three views, real imports/jobs/reports/downloads, guard drafts/validation/export, outcomes and billing. Six Chromium workflows passed, including mobile and unavailable states. |
| CI and optional infrastructure | Implemented and locally checked | Trusted-base code/policy/map example, summary/export, pinned actions, valid workflow YAML; local known-bad recurrence rejects. Terraform init/fmt/validate passed with zero errors/warnings. Remote CI and AWS deployment unrun. |
| Automated verification | Passed | 94 Python tests across unit/property/policy/real-PostgreSQL integration; six browser tests; Ruff/mypy/TypeScript/Vite checks. One nonblocking upstream TestClient deprecation warning remains. Exact commands/results in `docs/results/verification.json`. |
| Workload and injected failure | Measured locally | Smoke, eight-minute calibration and three eight-minute baseline/candidate pairs. All six comparison runs passed frozen thresholds; p95 5.481–6.262 ms. Four comparison runs had one HTTP failure each, below 1%; zero incorrect successes/drops/restarts. Docker confirmed actual bounded OOM and repair. |
| Billing analytics | Implemented and tested with benchmark data | 1,000 FOCUS rows, 13 negative billed rows; BilledCost 20.52022672899 USD; EffectiveCost 14.97651418586 USD. Nulls/currencies/identical rows preserved and repeat import idempotent. Not the demo service's bill. |
| Frozen evaluation | Local replay completed | 60/60 deterministic cases, 20 groups split 8/4/8. 57 structured explanations plus three coverage abstentions; 54 applicable guard drafts plus six correctly inapplicable cases. 111 accepted structured template outputs across 120 tasks; 360 provider-policy tasks unrun. |
| Live AWS and paid model experiments | Unrun | No verified service/model configuration or spending budget supplied. |
| Human usability pilot | Unrun | Requires consenting peer participants. |
| Documentation and two PDFs | Generated, validated and visually inspected | README, architecture/decisions, module/model/tool inventory, T01–T24 matrix, operations, learning path, owner walkthrough and saved result extracts. PDFs contain searchable embedded-font text, links/bookmarks and vector diagrams; all 4 overview and 28 technical-guide pages visually reviewed by Codex. See `docs/pdf/layout_review.json`; this is not human usability feedback. |

Synthetic fixtures are explicitly labelled. Mocked adapters do not establish provider quality, and local workload observations do not establish an AWS operating bound.

## Remaining prerequisites and deliberately deferred scope

- Live AWS collection/measurements need a separately reviewed real account, region/service mapping, credentials, matching Linux x86_64 image/contract and an explicit spending allowance. No cloud resource was deployed.
- Live provider comparisons need exact verified model IDs, keys, official dated USD prices, positive budgets and independent semantic annotations. The default is AI off; prices, task costs and quality measurements remain null for both unconfigured slots. Context serialization is prepared; downstream quality/token-cost comparison is unrun.
- Remote GitHub Actions/protected enforcement need an authorized repository and protected workflow/policy review. Local workflow definition and regression results are not a remote run.
- T24 needs consenting uncoached engineers. Windows/PowerShell commands are documented but were not executed on this macOS host. No human feedback was invented.
- Production identity/authorization, tenant/account isolation, retention and secret operations; additional services/clouds; Kubernetes; arbitrary policies; trained routing; general diagnosis; autonomous changes/rollback and Infracost import remain deferred.

The supported local replay workflow is complete. Read `CHANGELOG.md` for the implemented bug/security improvements. All new files remain within `proofops-app/`; the preservation audit checks 384 unchanged original research files, and runtime containers contain no research/evaluator directories.
