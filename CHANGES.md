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
  credentials; one Caddy gateway; read-only public demo; gated full hostname;
  restricted hosted database roles, Secure cookies, AI off and private API/DB ports.

The API inventory is unchanged by the planned optimizations:

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

Redis is not justified at this scale: PostgreSQL already coordinates durable jobs,
idempotency, budgets and authentication. No new queue framework, service or
monitoring stack is planned. Resource allocations will not be lowered.

## Frontend

Preserve `AppShell`, ReviewsPage/list/form, job/report/evidence/workload/guard
panels, OutcomesPage/billing, AuthGate/login and shared presentation components.
Keep hash routes, polling states, loading/errors, downloads, responsive layouts,
navigation, CSS, typography, colors and spacing. No visual redesign is planned.

## Security

Deterministic outcomes remain authoritative. Provider tests use mocks; no live
AWS, model or research API calls are authorized. Secrets stay server-side and are
never printed. Public-demo restrictions, full-host Basic Auth, login rate limits,
CSRF, restricted database roles and container/network hardening remain required.

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

## Performance

No performance gain is claimed yet. Baseline production frontend assets are
274.95 kB JavaScript (84.44 kB gzip) and 28.88 kB CSS (7.05 kB gzip). Test suite
runtime is verification timing, not an application latency benchmark. Local
measurements will distinguish call/query counts from end-user latency and from
unmeasured cloud costs, CPU or memory savings.

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

## Compatibility

Keep existing API response fields and all three review/export flows. Native,
local Docker and both hosted configurations remain supported. Proper forward and
rollback-tested migrations will accompany any new tables/indexes; existing
reports, users, budgets, audit history and credentials must survive upgrades.

## Known limitations

No live provider quality/cost or AWS savings measurements. No MFA/SSO, tenant
isolation, self-service recovery, automated retention/backup/restore or distributed
edge limiting. SR-05 login availability and the previously recorded image findings
remain open. A shared Basic password is not MFA. No production-readiness claim.
