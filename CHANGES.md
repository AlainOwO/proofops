# ProofOps Changes

## Date

2026-10-07. Optimization baseline: `54160de`. This log extends the existing
implementation and the adjacent full hosted deployment; historical results in
`CHANGELOG.md`, `docs/results/` and the published PDFs remain historical records.

## Baseline

Inspected the backend, frontend, tests, testing tools, infrastructure, deployment,
configuration, migrations, policies, scripts and documentation, including all
Compose files and the root implementation/plan/changelog documents.

Existing features retained as the foundation:

- FastAPI, PostgreSQL/Alembic and a separate worker with persisted jobs,
  `SKIP LOCKED` claims, heartbeats, three-claim recovery and idempotent submissions.
- Deterministic Terraform normalization, evidence freshness/coverage, Decimal
  task CPU/memory estimates, workload comparisons and four review outcomes.
- Three synthetic replays, reproducible report exports, constrained memory guard
  drafts/fixtures/exports, operator dispositions and idempotent FOCUS analytics.
- Optional OpenAI/Anthropic adapters, at most two cheap-first attempts, exact-fact
  validation, persistent spending reservations and accepted-output caching.
- Bounded STS/ECS/CloudWatch/Logs collection and an isolated local k6 runner.
- Argon2 admin/viewer login, expiring server sessions, CSRF, exact hosts/origins,
  persistent login limits, request admission/body bounds and actor-bound audits.
- Loopback local Compose; separate public/full hosted databases, volumes and
  credentials; one Caddy gateway; read-only public demo; full application login;
  restricted hosted database roles, Secure cookies, AI off and private API/DB ports.

The API inventory is unchanged by these optimizations:

| Method | Route | Existing purpose |
|---|---|---|
| GET | `/healthz`, `/readyz` | Liveness and authenticated migration readiness |
| GET / POST | `/api/v1/auth/login` | CSRF challenge / bounded password login |
| GET | `/api/v1/auth/session` | Current identity and CSRF token |
| POST | `/api/v1/auth/logout` | Revoke the current session |
| GET | `/api/v1/replays` | Supplied synthetic scenarios |
| POST | `/api/v1/bundles` | Bounded sanitized import |
| GET / POST | `/api/v1/reviews` | Paginated listing / idempotent job submission |
| GET | `/api/v1/reviews/{review_id}` | Job, immutable report and applicability |
| GET | `/api/v1/reviews/{review_id}/bundle` | Reproducible report export |
| POST | `/api/v1/reviews/{review_id}/guard-drafts` | Constrained draft |
| POST | `/api/v1/guard-drafts/{draft_id}/validate` | Trusted Conftest fixtures |
| GET | `/api/v1/guard-drafts/{draft_id}/bundle` | Tested, inactive guard export |
| POST | `/api/v1/reviews/{review_id}/outcomes` | Operator-reported disposition |
| GET | `/api/v1/analytics` | Review/model/accounting summaries |
| POST | `/api/v1/billing/import-sample` | Idempotent sample import |
| POST | `/api/v1/admin/reset-demo-data` | Explicit synthetic demo reset |
| GET / HEAD | `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json` | Authenticated local reference; absent in hosted mode |

Initial findings: expired AI cache rows cannot be refreshed because inserts ignore
conflicts; the cache key omits the output token limit; an idle worker polls twice
per second; listings/analytics load full report documents when only projections
are needed; detail loads the same trusted revision twice. AWS collection has no
TTL cache, and no optional research provider interface exists. Input, SQL, model
attempt, workload and container bounds already exist and should be preserved.

Resource analysis from code/configuration inspection:

| Work | Existing cost or bound | Decision |
|---|---|---|
| Deterministic review | Small in the supplied warm replay measurements; normalization, policy and workload checks already run in the worker | Preserve the engine and instrument its duration; no CPU-allocation reduction |
| Imports and exports | ZIP/JSON validation and serialization allocate memory; existing 5 MiB bundle/24-file limits, admission quotas and container limits bound this work | Preserve these bounds and record artifact bytes |
| Authentication | Argon2 verification uses 64 MiB per verification and is deliberately expensive | Preserve login admission and rate limits; do not trade password security for throughput |
| Database reads and polling | Full report JSON was loaded for summaries; detail reread trusted policy; idle workers polled every 0.5 seconds | Use projections, one policy read and bounded idle backoff |
| AWS/model requests | Network observations and optional paid explanations can repeat for identical inputs | Reuse only validated, scoped, unexpired results; retain original evidence times and spending limits |
| Concurrent work | Existing persisted queue, leases, SQL/SDK deadlines and connection limits | Bound worker slots to 1–4; retain crash recovery and container memory limits |
| k6/browser tests | Separate workload runner/profile and browser dev dependency | Keep out of normal API traffic and runtime images; reject hosted workload execution |

Compose allocations remain unchanged: database 1 CPU/1 GiB, API and worker each
1 CPU/512 MiB, web 0.5 CPU/128 MiB, optional workload 1 CPU/256 MiB. The hosted
gateway keeps its existing separate bounds. No whole-server profile established
a safe basis for reducing these limits.

## Changes made

### Accepted AI cache and concurrent requests

- Files: `models/router.py`, `models/context.py`, `storage/coordination.py`,
  `config.py`, `.env.example`, `docs/models.md`, `tests/integration/test_model_cache.py`.
- Expired/invalid entries are replaced after validation. The key now includes the
  real prompt version, request version and output token limit. Configurable
  enablement/TTL defaults preserve the existing five-minute cache.
- A nonblocking PostgreSQL advisory lock prevents concurrent identical provider
  dispatches. A contender receives the existing deterministic template and an
  explicit AI-unavailable reason. Locks release on transaction/process loss;
  budget reservations and uncertain charges remain durable.
- Expected impact: fewer duplicate explanation calls. Deterministic outcomes,
  provider eligibility, two-attempt routing and budget limits are unchanged.

### AWS observations and database reads

- Files: `collectors/aws.py`, `storage/tool_cache.py`, `storage/database.py`,
  `storage/repository.py`, `storage/analytics.py`, `api/app.py`, migration
  `2a0c9f4b7e61`, `.env.example`, `docs/aws.md`, `docs/operations.md` and focused
  cache/read/migration tests.
- Added an optional 60-second observation cache in the existing PostgreSQL DB,
  capped at 128 entries/512 KiB each. Cache hits verify STS caller identity and
  retain the original observation/collection times. Failed/denied/pending/expired
  observations are never reused as fresh evidence; zero TTL disables reuse.
- List/analytics queries project only needed report fields. Detail loads the
  trusted revision once. Added one job ordering index and two expiry indexes for
  bounded cache cleanup. Existing pagination fields and public-demo allowlisting
  remain unchanged.
- Expected impact: fewer repeated AWS observations and less full-document
  materialization. The additive migration preserves existing records; rollback
  removes only disposable tool observations and the new indexes. Large databases
  need a maintenance window for ordinary index creation.

### Optional tools and public research

- Files: `tools/interfaces.py`, `tools/pricing.py`, `tools/research.py`, `cli.py`,
  `config.py`, `.env.example`, hosted Compose files, `docs/tools.md`, README and
  research/cache/CLI regression tests.
- Added provider protocols around existing normalized evidence and dated rates.
  The CLI rate override uses a bounded, hashed snapshot; all Decimal calculations,
  source/coverage assumptions and cost distinctions remain in the existing engine.
- Added an explicit `proofops research` CLI command with a provider-neutral search
  protocol and optional Google adapter. It is disabled by default, uses a fixed
  HTTPS endpoint, total async deadline, bounded result/body sizes, private output,
  source attribution and the existing small observation cache. Provider errors
  expose fixed codes only; result URLs are never fetched. Reflected configured
  credentials are rejected.
- Expected impact: repeated identical research can reuse cached results. Research
  remains untrusted context in a separate artifact, never an approval input or
  model/tool instruction. Hosted research stays explicitly off; no API route,
  service, frontend dependency or egress network is added.

### Worker bounds, observability and workload isolation

- Files: `workers/runner.py`, `storage/repository.py`, `observability.py`,
  `storage/database.py`, API boundaries, provider entry points, configuration,
  full Compose, `scripts/run_workload.py`, `testing/virtual_users.js` and focused tests.
- Worker polling backs off while idle and resets after work; concurrency is
  bounded/configurable (default one, maximum four) using the existing queue.
  Timeouts are checked before artifacts/commit, and exhausted recovery gets a
  final failed stage/timestamp/audit record. Existing uncertain-charge recovery,
  idempotency and public-demo refusal remain.
- Added JSON timings and counters for requests, SQL, worker/review stages,
  artifact sizes, queue wait, model usage, AWS calls and cache reuse. Logging
  excludes secrets, SQL/parameters and private content; no monitoring service.
  Input-token totals include provider cache reads/writes; reusing an accepted
  application cache entry does not recount provider tokens or charges.
- k6 refuses hosted/public-demo mode and unintended targets before running.
  Its existing smoke/full workload profiles and thresholds remain intact.
- Expected impact: fewer idle queue polls and better diagnosis. Maximum idle
  pickup delay increases to five seconds by default. CPU/memory limits are not
  reduced; no measured server-throughput or memory saving is claimed.

Redis is not justified at this scale: PostgreSQL already coordinates durable jobs,
idempotency, budgets and authentication. No new queue framework, service or
monitoring stack was added. Resource allocations were not lowered.

### Documentation and upgrade integration

- Files: README, `docs/operations.md`, `docs/testing.md`, `docs/models.md`,
  `docs/aws.md`, `docs/tools.md`, `docs/architecture.md`,
  `docs/module_reference.md`, `docs/security_review.md`, `CHANGELOG.md` and
  `IMPLEMENTATION_STATUS.md`.
- Recorded safe configuration defaults, tool trust boundaries, migration and
  rollback, worker tradeoffs, exact tests and measured limits. Preserved earlier
  changelog/status results and published PDFs. Documented restarting the local
  nginx proxy after API container replacement, confirmed during upgrade checks.
- Expected impact: reproducible local/hosted upgrades and clear operating limits;
  no automatic deployment or production-readiness claim.

## Frontend

Preserved `AppShell`, ReviewsPage/list/form, job/report/evidence/workload/guard
panels, OutcomesPage/billing, AuthGate/login and shared presentation components.
No frontend source, CSS, navigation, layout, color, typography, spacing, framework
or workflow changed. No UI adaptation was needed: existing API response fields,
hash routes, polling, loading/errors and downloads remain compatible.

The native and production-image builds retain `index-5CMvr3l3.js` and
`index-JeX5wiNX.css`. All local/hosted browser regressions passed, including
desktop/mobile projection styling, loading/error recovery and authentication.
All three seeded screenshot checks passed and the new captures were visually
inspected. The existing historical-evidence warning now appears because the
2026-10-05 fixtures are stale for a decision on 2026-10-07; it does not change the
recorded replay outcome. Tracked screenshots were restored byte-for-byte after
capture; new inspection images remain under ignored artifacts.

## Security

Deterministic outcomes remain authoritative; the domain engine, contracts,
policies, source fixtures and evaluator data are unchanged. No live AWS, model or
research API call was made. Secrets remain in private server configuration and
were never printed. Public-demo restrictions, full-host application login, login rate
limits, CSRF, restricted database roles and container/network hardening passed
the rebuilt-container checks. The full deployment added before this optimization
baseline remains a separate project/database/volume/credential set behind the
same Caddy. See the [security review](docs/security_review.md) for the new cache,
research, worker and logging surface and the open findings.

## Tests

Fresh baseline, before runtime changes:

- `AI_MODE=off OPENAI_API_KEY= ANTHROPIC_API_KEY= AWS_EC2_METADATA_DISABLED=true .venv/bin/pytest tests/unit tests/policy tests/integration -q --tb=short --junitxml=artifacts/optimization/baseline-backend.xml`
  — **445 passed**, no failures/errors/skips, 114.57 seconds. Existing upstream
  Starlette/httpx deprecation warning. Local test database access required sandbox
  permission; the suite used only `proofops_test`.
- `.venv/bin/ruff check backend scripts tests evaluation demo` and
  `.venv/bin/ruff format --check backend scripts tests evaluation demo` — passed.
- `.venv/bin/mypy backend/proofops` — passed (39 source files).
- `npm --prefix frontend run build` — passed, including TypeScript/browser types.
- `.venv/bin/proofops guards test --output artifacts/optimization/baseline-guards.json`
  — all ten trusted guard fixtures passed.
- `.venv/bin/proofops evaluate --mode replay --output artifacts/optimization/baseline-evaluation`
  — 60/60 deterministic cases, 120 template tasks; 360 provider tasks explicitly unrun.
- `.tools/bin/terraform -chdir=infra/aws-demo fmt -check` — passed; no plan/apply.
- `.venv/bin/pytest tests/containers tests/hosted tests/hosted_full -q --tb=short --junitxml=artifacts/optimization/baseline-hosted.xml`
  — **37 passed** in 12.61 seconds on the two isolated hosted projects.
- `.venv/bin/pytest tests/integration/test_optimization_measurements.py -q -o junit_family=legacy --junitxml=artifacts/optimization/baseline-measurements.xml`
  — three offline characterization checks passed. These tests save measured
  counters/timings as JUnit properties; provider responses are mocks.
- The credential-redacting hosted browser runner — **22 passed** in 16.4 seconds;
  saved separately in `artifacts/optimization/baseline-browser.txt`.

After the AI cache change, the cache/budget/recovery/measurement/context/adapter
selection passed **41 tests** in 2.65 seconds, with no failures/skips
(`artifacts/optimization/ai-cache.xml`). Full Ruff and backend mypy passed.

Observation cache, migration downgrade/upgrade, projections, API, public-demo,
runtime-role, AI-cache and AWS contract checks passed **94 tests** in 25.52 seconds
(`artifacts/optimization/tools-and-reads.xml`). An initial run exposed that new
cache provenance must fit the existing flat, twelve-field evidence metadata
schema; the adapter was corrected without loosening that schema or its tests.
Ruff and mypy passed.

Research/provider/cache/CLI/deployment/context checks passed **44 tests** using
mocked HTTP (`artifacts/optimization/research.xml`); no external search was run.
Ruff and mypy passed, including all new provider interfaces.

Worker, logging, budget/recovery, audit, HTTP boundaries and measurement checks
passed **58 tests** in 5.45 seconds. Ten actual k6-initialization/runner-isolation
checks passed in 0.32 seconds, sending no workload traffic. Evidence:
`workers-and-logging.xml` and `workload-isolation.xml` under `artifacts/optimization/`.

Final validation:

- `env AI_MODE=off OPENAI_API_KEY= ANTHROPIC_API_KEY= AWS_EC2_METADATA_DISABLED=true SEARCH_PROVIDER=off .venv/bin/pytest tests/unit tests/policy tests/integration -q --tb=short -o junit_family=legacy --junitxml=artifacts/optimization/backend-final.xml`
  — **517 passed**, no failures/errors/skips, 119.00 seconds. This includes all
  original unit/policy/API/PostgreSQL tests and 72 additional tests since the
  baseline. The existing upstream TestClient deprecation warning remains.
- `.venv/bin/ruff check backend scripts tests evaluation demo`,
  `.venv/bin/ruff format --check backend scripts tests evaluation demo` and
  `.venv/bin/mypy backend/proofops` — passed; 112 formatted Python files and
  46 backend source files checked.
- `npm --prefix frontend run build` and
  `docker build --no-cache --tag proofops-web frontend` — passed, including
  TypeScript/browser-test types and the unchanged production frontend assets.
  `docker build --no-cache --tag proofops-api --tag proofops-worker .` — passed
  for the final backend image, with frozen runtime dependencies and OS upgrades.
- `env AI_MODE=off OPENAI_API_KEY= ANTHROPIC_API_KEY= AWS_EC2_METADATA_DISABLED=true SEARCH_PROVIDER=off .venv/bin/pytest tests/containers tests/hosted tests/hosted_full -q --tb=short --junitxml=artifacts/optimization/hosted-final.xml`
  — **37 passed** on the final images. The original standalone public Caddy
  configuration also passed all **16** tests via `.venv/bin/pytest tests/hosted
  -q --tb=short --junitxml=artifacts/optimization/public-only.xml`, after which
  the shared gateway was restored.
- `.venv/bin/python -m scripts.run_hosted_full_browser_checks` — **22 passed**
  through the full HTTPS hostname, including both gateway tests. The original
  **20 Chromium tests passed** against the isolated local Compose project at
  loopback port 25173. All three seeded screenshot checks also passed and were
  visually inspected. No frontend test assertion or timeout was weakened.
- Local browser commands used the existing configs with
  `PROOFOPS_WEB_URL=http://127.0.0.1:25173` and a private
  `PROOFOPS_BROWSER_AUTH_FILE`, invoking `node node_modules/@playwright/test/cli.js
  test --config playwright.config.ts --reporter=list` from `frontend/` (and
  `playwright.demo.config.ts` for screenshots). The ignored helper
  `.venv/bin/python artifacts/optimization/check_local_compose.py` was invoked
  with `start`, `browser` and `screenshots` actions. It generated independent
  secrets, used project `proofops-local-optimization`,
  remapped only loopback ports and redacted output. It never used the original
  workspace environment or reset its database. Tracked screenshots were restored.
- `.venv/bin/proofops guards test --output artifacts/optimization/final-guards.json`
  — **10/10** actual trusted Conftest fixtures passed.
  `.venv/bin/proofops evaluate --mode replay --output artifacts/optimization/final-evaluation`
  — **60/60** deterministic cases; 120 template tasks ran, 360 provider tasks
  explicitly unrun. AI/model keys were disabled in both environments.
- For each supplied replay, `.venv/bin/proofops review --bundle
  fixtures/replays/<scenario> --ai off --output artifacts/optimization/final-cli/<scenario>`
  produced the expected exit/result (valid 0/request_review, unsafe
  2/revise_change, incomplete 3/collect_evidence). Each subsequent
  `.venv/bin/proofops replay artifacts/optimization/final-cli/<scenario>` exited
  zero. All report/explanation/Markdown/ZIP artifacts were present, with template
  explanations. Browser checks additionally exercised real guard exports,
  dispositions, repeated billing import, viewer permissions and login/logout.
- `.venv/bin/pytest tests/integration/test_optimization_measurements.py tests/integration/test_aws_cache.py -q -o junit_family=legacy --junitxml=artifacts/optimization/measurements.xml`
  — **12 passed**, using only the dedicated test DB and mocked SDKs/providers.
- `.tools/bin/terraform -chdir=infra/aws-demo fmt -check` and
  `.tools/bin/terraform -chdir=infra/aws-demo validate` — passed. Validation used
  installed plugins, disabled AWS credentials/metadata and no plan/apply.
- Temporary network-disabled runtime containers confirmed the final API source,
  default-disabled research and the absence of pytest/Playwright/k6 in the API
  image and Node/Playwright/k6 in the web image. The 384 original research-file
  checksums passed `.venv/bin/python scripts/check_research.py` unchanged.
- Markdown file-link validation passed for 23 documents. A comparison of ten
  current private configuration/account files against all 357 tracked/proposed
  files found no credential matches; all ten private files had mode 0600.
  No resolved environment, password or provider secret was printed.

Failures found and resolved without skipping tests:

- Network-disabled Docker build attempts could not retrieve missing dependency
  layers. Authorized uncached builds with package downloads passed; existing
  pins were preserved, and no AWS/model/search API was called.
- Final logging review found that input-token counters omitted provider cache
  reads/writes. The corrected totals and no-double-count behavior passed four
  focused logging tests and the final 517-test suite.
- Recreating only local API/worker containers with `--no-deps` left nginx using
  the previous API address: an additional browser run had 19 failures/one pass
  with 502 responses. Direct API health and the original workspace stayed 200.
  Restarting only that disposable `web` container refreshed DNS; all unchanged
  20 tests then passed in 18.5 seconds. The upgrade runbook now requires this
  proxy restart; no application, proxy or test assertion was relaxed.
- The initial Terraform plugin check could not execute inside the sandbox;
  approved local validation passed. JUnit measurement runs now use the legacy
  format so recorded properties do not generate xunit2 compatibility warnings.

Machine evidence is under ignored `artifacts/optimization/`, including
`backend-final.xml`, `hosted-final.xml`, `public-only.xml`, `measurements.xml`,
`hosted-upgrade.json`, `final-images.json`, `runtime-boundaries.json`, `final-cli/`
and redacted browser records. Private test identities remain in owner-only
`private/` directories and must not be published. The published PDFs and older
measurement artifacts were not regenerated.

After verification, only `proofops-hosted-check`, `proofops-hosted-full-check`
and `proofops-local-optimization` were removed with their synthetic volumes and
networks. The original `proofops` container identities were unchanged, and its
API and web `/healthz` responses remained 200. Cleanup and private-audit results
are recorded in `cleanup.json` and `private-audit.json` under the same directory.

## Performance

Measured improvements are limited to the offline call/read experiments below.
Production frontend assets remain 274.95 kB JavaScript and 28.88 kB CSS with the
same content hashes. Test suite runtime is verification timing, not an
application latency benchmark. No end-user latency, cloud cost, CPU, memory or
realized savings improvement is claimed.

Baseline measurements: four identical eligible AI requests, with forced cache
expiry before request three, made **three mocked provider calls** (accepted,
cached, accepted, accepted). A ten-review API listing materialized **100,530
bytes** of full report/explanation JSON and executed **three SQL statements**
including authentication. A report-detail request read trusted policy files
**twice**. Thirty warm synthetic engine runs had a median of **0.1980 ms** and
p95 of **0.2335 ms** on this host. These are narrow local measurements, not a
production benchmark or evidence of cloud cost savings.

After the cache repair, the identical four-request experiment made **two mocked
provider calls**: accepted, cached, accepted, cached. This is a measured call-count
reduction for that offline expiry scenario, not a measured provider cost/latency
improvement.

With the revised queries, the ten-review listing materializes **zero full report
documents** instead of 100,530 bytes, while still executing three SQL statements
including authentication and returning the same summaries. Detail reads the
trusted revision **once**, down from twice. This measures document materialization,
not total PostgreSQL wire bytes. Two mocked AWS collections use **six SDK calls**
with reuse (five cold, one STS verification) versus **ten** without reuse. No live
AWS latency/cost or whole-server CPU/memory reduction was measured.

The final dedicated thirty-run engine sample measured median **0.2056 ms** and
p95 **0.2424 ms**, versus baseline 0.1980/0.2335 ms. These small local samples do
not demonstrate a latency improvement; the engine code is unchanged. All counts
and durations above are recorded in `artifacts/optimization/baseline-measurements.xml`
and `measurements.xml`; AWS call-count comparisons use mocked SDK clients.

## Compatibility

Existing API response fields and all three review/export flows are preserved.
Native checks, an isolated local Compose project, both hosted stacks together
and the standalone public proxy were exercised. Existing source/UI contracts and
the original local Compose bindings are unchanged; no new service is required.

Migration `2a0c9f4b7e61` was tested in both directions against the existing schema.
The two populated hosted test databases were upgraded without reseeding: hashes
and counts of existing users, reports, jobs, artifacts, billing, audit and
accounting tables matched before/after. Empty accounting tables in those hosted
fixtures are not a substitute for the populated budget/recovery integration
tests, which also pass. Deployment requires the matching owner migration and
runtime grants before the new images start; rollback instructions are in
[operations](docs/operations.md#optimization-migration-and-rollback).

## Known limitations

No live provider quality/cost, Google account/HTTP-contract validation or AWS
savings measurements. Research currently returns snippets and does not fetch
result pages. Worker stage deadlines are cooperative; no hard process timeout,
durable queue/storage quota or automatic retention service was added. More worker
slots still share the existing CPU/memory/database limits; default idle backoff
can add up to five seconds before pickup.

No MFA/SSO, tenant isolation, self-service recovery, operated backup/restore or
distributed edge limiting. SR-05 login availability remains open. A shared Basic
password is not MFA. Public DNS/ACME, disaster recovery and remote CI were not
exercised. API/worker/web were rebuilt using existing pins and OS updates; the
earlier Trivy findings are historical and these rebuilt images were not rescanned.
Current image IDs are recorded separately under `artifacts/optimization/`.
Published PDFs and earlier workload/evaluation records remain historical.
No production-readiness claim is made.
