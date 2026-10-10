# Implementation status

Updated 2026-10-07. This file records actual implementation and verification, not intended outcomes. Earlier handoff and UI results are preserved below.

## Optimization and hosted integration — 2026-10-07

The existing engine, API routes, frontend source/design, replay/export/guard
workflows and local Compose remain intact. The separate public/full hosted
deployments share one Caddy and retain independent databases, volumes and secrets;
public writes remain forbidden, while full mode requires application login.
Full admin/viewer setup, seeding, backups and limitations are
documented in [operations](docs/operations.md).

Implemented validated AI cache refresh/concurrency coordination, scoped AWS
observation caching, narrower report queries, optional provider-neutral research
and pricing interfaces, bounded worker concurrency/idle backoff, private operation
metrics and hosted k6 safeguards. No Redis, queue framework, monitoring service,
UI redesign or resource-limit reduction was introduced. Research is off by default;
the hosted stacks explicitly keep AI and research off.

- Verification: **517 backend tests**, **37 container/two-host HTTPS checks**,
  **16 standalone public HTTPS checks**, **22 hosted and 20 local Chromium tests**,
  and **three seeded screenshot checks** passed without skipped/weakened tests.
  Ruff, formatting, mypy (46 modules), TypeScript/Vite, production image builds,
  Terraform fmt/validate and all ten trusted guard fixtures passed. Replay still
  matches **60/60** decisions; 360 provider tasks remain explicitly unrun.
- Offline measurements: four repeated/expired AI requests use **2 instead of 3**
  mocked provider calls; two AWS collections use **6 instead of 10** mocked SDK
  calls. Ten-review summaries materialize no full report documents instead of
  100,530 bytes, with the same three SQL statements. Detail reads policy once
  instead of twice. No server latency/CPU/memory, provider-cost or AWS savings
  improvement is claimed.
- Migration `2a0c9f4b7e61` passed upgrade/downgrade checks. Both populated hosted
  test databases retained their existing rows during upgrade. The running original
  workspace was preserved; only isolated projects were used for current runtime
  verification. All 384 original research checksums remain unchanged.
- Limits: cooperative worker deadlines, no durable queue/storage quotas or
  automatic retention, no MFA/tenant isolation, SR-05 login recovery still open,
  and no live AWS/model/search or public ACME validation. Newly rebuilt images
  were not rescanned; earlier image findings are historical, not a current clean
  scan. Published PDFs and previous workload/evaluation measurements are unchanged.

Exact commands, file/module changes, measurements and evidence locations are in
[CHANGES.md](CHANGES.md).

## Original handoff — 2026-10-05

| Area | State | Evidence / remaining work |
|---|---|---|
| Plan and research boundaries | Implemented | `PLAN.md`, `docs/decisions.md`; no research files edited. |
| Local environment and domain engine | Implemented and tested | Locked Python/Node dependencies, pinned container bases, PostgreSQL migrations, four outcomes, sanitized Terraform normalization, Decimal costs and shared CLI. Fresh separate checkout installed 45 runtime packages and reproduced a keyless review. |
| Guard and performance | Implemented and tested | Fixed scoped Rego family; ten actual Conftest fixtures; exact template/spec/fixture binding; per-run/per-class comparison and current-applicability checks. |
| Collectors and model adapters | Implemented; mocked contract tests passed | Bounded STS/ECS/CloudWatch/Logs adapter and official OpenAI Responses/Anthropic Messages SDKs; failure/usage/citation tests. Live integrations remain unrun. |
| Routing, budget and recovery | Implemented and tested | At most two attempts, atomic PostgreSQL reservations, scoped complete-output cache, persistent leases and uncertain-charge recovery without duplicate dispatch. |
| API/worker/UI/CLI | Implemented and tested | Three views in focused React components, real imports/jobs/reports/downloads, guard drafts/validation/export, outcomes and billing. Confirmed local demo reset with exactly three completed replays and unchanged results. Twelve Chromium workflows and three seeded-result screenshot captures passed. |
| CI and optional infrastructure | Implemented and locally checked | Trusted-base code/policy/map example, summary/export, pinned actions, valid workflow YAML; local known-bad recurrence rejects. Terraform init/fmt/validate passed with zero errors/warnings. Remote CI and AWS deployment unrun. |
| Automated verification | Passed | 123 Python tests across unit/property/policy/real-PostgreSQL integration, including 29 reset tests; 12 browser workflows and three screenshot captures; native and Docker TypeScript/Vite builds; Ruff, mypy and screenshot-tool formatting checks. One nonblocking upstream TestClient deprecation warning remains. Demo and earlier UI verification are recorded below; original handoff checks remain in `docs/results/verification.json`. |
| Workload and injected failure | Measured locally | Smoke, eight-minute calibration and three eight-minute baseline/candidate pairs. All six comparison runs passed frozen thresholds; p95 5.481–6.262 ms. Four comparison runs had one HTTP failure each, below 1%; zero incorrect successes/drops/restarts. Docker confirmed actual bounded OOM and repair. |
| Billing analytics | Implemented and tested with benchmark data | 1,000 FOCUS rows, 13 negative billed rows; BilledCost 20.52022672899 USD; EffectiveCost 14.97651418586 USD. Nulls/currencies/identical rows preserved and repeat import idempotent. Not the demo service's bill. |
| Frozen evaluation | Local replay completed | 60/60 deterministic cases, 20 groups split 8/4/8. 57 structured explanations plus three coverage abstentions; 54 applicable guard drafts plus six correctly inapplicable cases. 111 accepted structured template outputs across 120 tasks; 360 provider-policy tasks unrun. |
| Live AWS and paid model experiments | Unrun | No verified service/model configuration or spending budget supplied. |
| Human usability pilot | Unrun | Requires consenting peer participants. |
| Documentation and two PDFs | Generated, validated and visually inspected | README, architecture/decisions, module/model/tool inventory, T01–T24 matrix, operations, learning path, owner walkthrough and saved result extracts. PDFs contain searchable embedded-font text, links/bookmarks and vector diagrams; all 4 overview and 28 technical-guide pages visually reviewed by Codex. See `docs/pdf/layout_review.json`; this is not human usability feedback. |

Synthetic fixtures are explicitly labelled. Mocked adapters do not establish provider quality, and local workload observations do not establish an AWS operating bound.

## Presentation demo verification — 2026-10-05

`proofops reset-demo-data` now asks for confirmation unless `--yes` is supplied. It replaces saved review data in one PostgreSQL transaction with completed valid-resize, unsafe-resize and incomplete-evidence replays. Reports use the existing engine and recorded fixture time, explanations use templates, and export bundles remain reproducible. Local database/path checks, running-job/concurrent-edit refusal and failure rollback protect the reset boundary. Billing, trusted policies, accounting, audit history and existing files are preserved; assumptions are recorded in `CHANGELOG.md`.

- Backend: `.venv/bin/pytest tests/unit tests/policy tests/integration -q --tb=short --basetemp=artifacts/demo-reset/pytest-full-temp --junitxml=artifacts/checks/demo-backend.xml` — **123 passed**, zero failures/skips. AI was forced off and AWS metadata access disabled; temporary files stayed under repository artifacts. One existing upstream TestClient deprecation warning remains.
- Frontend: `npm run build` — **passed**, including the screenshot tooling in TypeScript checks. The Docker API/worker/web rebuild and Compose `--wait` startup also passed, with AI explicitly off for the verification run.
- Browser: `npm run test:e2e` — **12 passed**, zero failures/skips, against the rebuilt local app. Saved report: `artifacts/checks/demo-e2e.json`.
- Screenshots: after `docker compose exec -T api proofops reset-demo-data --yes`, `npm run screenshots:demo` — **3 passed**, zero failures/skips. The capture checks the three fixture input hashes, completed replay state and template mode without submitting reviews. The three PNGs under `docs/screenshots/` are embedded in README and were visually inspected; they contain synthetic content, no keys/personal data and no PNG metadata. Saved report: `artifacts/checks/demo-screenshots.json`.
- Static checks: Ruff passed for `backend scripts tests demo`; mypy passed for all 34 backend source files; new Python files and Playwright tooling passed their formatting checks. README has exactly five Quick demo steps and three valid screenshot embeds.

The Docker reset command was exercised successfully before and after e2e testing. The local app was left with exactly three completed reviews at `http://127.0.0.1:5173`. No review logic, result arithmetic, source fixtures, evaluation data, research files or published PDFs were modified. No live AWS/model calls were made.

## UI polish verification — 2026-10-05

`frontend/src/main.tsx` is now a 10-line entry point. App composition, workspace requests/polling, shared presentation helpers and individual review/report/outcomes sections live under `frontend/src/`. The UI now distinguishes loading, empty and unavailable data, provides read-only retry controls, explains the review workflow and adapts forms/tables for narrow screens. Review rules, result arithmetic and source evidence are unchanged. Assumptions are recorded in `CHANGELOG.md`; the README includes all three replay walkthroughs.

- Backend: `env AI_MODE=off AWS_EC2_METADATA_DISABLED=true .venv/bin/pytest tests/unit tests/policy tests/integration -q --tb=short --basetemp=artifacts/ui-polish/pytest-temp --junitxml=artifacts/checks/ui-polish-backend.xml` — **94 passed**, zero failures/skips; one existing TestClient deprecation warning.
- Frontend, from `frontend/`: `npm run build` — **passed**. The production Docker web build also passed and the updated web container was restored on port 5173. Prettier and TypeScript unused-local/parameter checks passed.
- Browser, from `frontend/`: `npm run test:e2e` — **12 passed**, zero failures/skips, against the rebuilt web container. Coverage includes real imports, worker results, downloads, guard fixtures, dispositions and billing; 320/390/768 px layouts; keyboard table scrolling; loading/error recovery; preserved form state; and late responses after navigation.

Local check outputs are `artifacts/checks/ui-polish-backend.xml` and `artifacts/checks/ui-polish-playwright.json`; screenshots are under `artifacts/screenshots/`. Desktop and mobile screenshots were visually inspected. No live AWS or model calls were made, and no research files or evaluator data were edited. Original workload/evaluation measurements and published PDF artifacts were not regenerated by this UI pass.

## Remaining prerequisites and deliberately deferred scope

- Live AWS collection/measurements need a separately reviewed real account, region/service mapping, credentials, matching Linux x86_64 image/contract and an explicit spending allowance. No cloud resource was deployed.
- Live provider comparisons need exact verified model IDs, keys, official dated USD prices, positive budgets and independent semantic annotations. The default is AI off; prices, task costs and quality measurements remain null for both unconfigured slots. Context serialization is prepared; downstream quality/token-cost comparison is unrun.
- Remote GitHub Actions/protected enforcement need an authorized repository and protected workflow/policy review. Local workflow definition and regression results are not a remote run.
- T24 needs consenting uncoached engineers. Windows/PowerShell commands are documented but were not executed on this macOS host. No human feedback was invented.
- Basic admin/viewer authentication, expiring sessions, CSRF, actor-bound audit events and persistent login limits are implemented; see [security and hosting](docs/security.md). MFA/SSO, tenant/account isolation, external audit retention, managed secret operations and a publicly validated production TLS deployment remain deferred, along with additional services/clouds, Kubernetes, arbitrary policies, trained routing, general diagnosis, autonomous changes/rollback and Infracost import.

The supported local replay workflow is complete. Read `CHANGELOG.md` for the implemented bug/security improvements. All new files remain within `proofops-app/`; the preservation audit checks 384 unchanged original research files, and runtime containers contain no research/evaluator directories.
