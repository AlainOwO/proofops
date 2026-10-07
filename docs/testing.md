# Testing and measured evidence

A test compares observed behavior with an independently justified expected result, or oracle. Passing a test supports only its stated scope. The saved verification and workload tables in `docs/results/results.md` are generated from actual artifacts. The full machine record is `docs/results/verification.json`. Native logs and run manifests remain under `artifacts/`.

## Types of verification

Unit tests isolate decision/arithmetic/boundary behavior; property tests exercise many valid or invalid allocations. Integration tests use a real PostgreSQL database for transactions, idempotency, leases and concurrency. Policy tests execute actual Conftest/Rego, including healthy controls that make an always-deny implementation fail. SDK contract tests call mocked provider/AWS HTTP boundaries and verify parameters, completion states and accounting. They do not establish account access or model quality.

Browser tests exercise the real local UI/API/worker, including login/logout, viewer restrictions and all three review scenarios; explicitly mocked browser tests cover transport/empty states, expiry timing and demo presentation. Backend auth tests use PostgreSQL to cover every endpoint/method for anonymous, viewer and admin, CSRF on every write, current roles, session rotation/revocation, concurrent/persistent login limits, startup rejection and public-demo isolation. The endpoint inventory fails if a route is omitted. Load tests measure correct work and latency under offered demand. Fault injection proves a specific controlled failure and repair. Security/resilience tests also attempt traversal, malformed JSON, secret retention, prompt injection, cross-scope cache reuse and ambiguous worker recovery. AI evaluation scores independent labels and semantics separately from schema. Human usability requires an uncoached consenting engineer; it was not replaced by browser automation.

## Commands and prerequisites

From the app root, install the frozen development dependencies and pinned Conftest/k6 as in the README. Start Docker PostgreSQL and create the dedicated test database with `python scripts/create_test_database.py`. Integration fixtures run Alembic migrations and refuse any database name other than `proofops_test`.

```sh
.venv/bin/pytest tests/unit tests/policy tests/integration -q --junitxml=artifacts/checks/backend.xml
.venv/bin/ruff check backend scripts tests evaluation demo
.venv/bin/ruff format --check backend scripts tests evaluation demo
.venv/bin/mypy backend/proofops
.venv/bin/proofops guards test
.venv/bin/proofops evaluate --manifest evaluation/manifest.json --mode replay --output artifacts/evaluation
```

Browser checks require the local AI-off API, worker and web at ports 8000/5173, plus Chromium and generated test credentials. From the app root:

```sh
.venv/bin/python scripts/prepare_browser_auth.py
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

PowerShell uses `.venv\Scripts\pytest.exe`, `ruff.exe`, `mypy.exe`, `proofops.exe` and `python.exe` in place of `.venv/bin/...`. These exact PowerShell setup commands are documented but were not run on this macOS host. Backend JUnit and Playwright JSON are saved under `artifacts/checks/`; screenshots are under `artifacts/playwright/` and `artifacts/screenshots/`. Traces/videos are disabled because they can contain session cookies and passwords. The test setup creates synthetic users and saves random credentials only in owner-readable, ignored `artifacts/private/browser-auth.json`; an alternate file can be selected with `PROOFOPS_BROWSER_AUTH_FILE`. It never writes cookie state to disk. Do not upload the entire artifacts directory. The Starlette TestClient emits one upstream httpx compatibility warning; no test is skipped because of it.

After e2e, reset the demo and capture the three README screenshots with the existing script:

```sh
docker compose exec -T api proofops reset-demo-data --yes
cd frontend
npm run screenshots:demo
```

The capture authenticates with the prepared synthetic admin, verifies exact fixture hashes/template explanations and checks that no test username/password is visible. Both e2e and screenshot commands honor `PROOFOPS_WEB_URL` for an isolated loopback stack and `PROOFOPS_BROWSER_AUTH_FILE` for its generated credentials. Review the resulting PNGs before committing; preserve historical documentation images when capturing verification-only evidence. Authentication checks do not contact cloud/model APIs. PostgreSQL/Docker tests must run with local service access; sandbox connection failures are not a reason to weaken or skip them. Historical results in `docs/results/` and PDFs remain saved measurements; the current change's checks are recorded in `CHANGELOG.md`.

## Hosted container and HTTPS checks

Migration startup has a separate real-Compose regression suite:

```sh
.venv/bin/pytest tests/containers/test_compose_migrations.py -q \
  --junitxml=artifacts/checks/compose-migrations.xml
```

It builds the backend and PostgreSQL images and exercises both `compose.yaml`
and `compose.hosted.yaml`, once with a fresh database using `up --build` and once
starting at `f6a91d2e83b4`. The upgrade case first starts the previous migration image and
checks its readiness, then rebuilds **only API** and runs ordinary Compose
startup. Both cases require the actual migration container to exit zero, API
and migrate to use the same image, the API's own database connection to see the
current Alembic head, and the actual `/readyz` endpoint to return 200. The
upgrade also verifies the database container and an existing record survive.
No integration fixture upgrades the database on the test's behalf. Each case
configures a generated synthetic bootstrap admin; the local readiness request
authenticates through the normal HTTP login and CSRF flow. Hosted readiness
uses the public demo's existing anonymous read policy.

Docker/Compose 2.24.4+ and image-build network access are required; missing
prerequisites fail the tests. Each case generates its own project name and
private credentials, publishes no ports, and shuts down its containers while
**retaining all named volumes**. Commands and safe results are saved under
`artifacts/compose-migrations/<project>/`; its `private/` subdirectory contains
credentials and must not be uploaded. The `compose-migrations` CI job runs all
four cases independently of the ordinary backend fixture suite.

The normal backend suite includes admission/body-deadline/header tests, actor-bound audit tests, real-PostgreSQL runtime privilege tests and effective Compose checks. The following additional suites exercise the built nginx/PostgreSQL images and the actual Caddy TLS boundary. They need Docker, curl, Compose 2.24.4 or newer and free loopback ports 15080/15443. They use no public ACME or cloud/model API. Image/package/advisory downloads during builds and scans require network access.

From the app root, after local configuration and frozen test dependencies are installed:

```sh
docker compose build --no-cache --pull db
python3 -m scripts.prepare_hosted_checks
hosted_check() {
  docker compose --env-file artifacts/hosted-security/private/.env.hosted \
    -p proofops-hosted-check -f compose.hosted.yaml \
    -f artifacts/hosted-security/private/images.json \
    -f artifacts/hosted-security/private/ports.yaml "$@"
}
hosted_check --profile worker --profile maintenance build --no-cache --pull
hosted_check up -d db
hosted_check run --rm migrate
hosted_check run --rm --no-deps api proofops users create --username security-check-admin --role admin
hosted_check run --rm --no-deps seed
hosted_check up -d --wait
.venv/bin/pytest tests/containers -q --junitxml=artifacts/hosted-security/containers.xml
.venv/bin/pytest tests/hosted -q --junitxml=artifacts/hosted-security/tls-proxy.xml
hosted_check --profile worker --profile maintenance down --volumes --remove-orphans
```

Choose a unique generated admin password at the non-echoing prompt. The preparation helper writes only ignored test configuration, generates independent private credentials, derives a test Caddyfile with its internal issuer, and replaces the public port bindings with loopback bindings. It does not modify the root `.env.hosted` or start containers. The fixed project name is reserved for these synthetic tests; do not run concurrent checks or point it at an existing workspace.

Container tests use fresh labelled containers with no network, verify PostgreSQL 17/18 volume ownership and non-root operation, and start nginx read-only with all capabilities dropped. HTTPS checks force DNS to loopback and disable curl proxies. They verify seeded-only reads, read-only identity, every representative write rejection, disabled docs, Host/Origin rejections, redirect/HSTS/security headers and a controlled 502. The outage test verifies the project label before stopping and restarting only `proofops-hosted-check-api-1`. The final `down --volumes` removes only this disposable test project's data; it does not touch local `proofops` volumes.

These checks verify local TLS behavior, not public DNS, ACME issuance or internet load resistance. Run both filtered and unfiltered Trivy scans as shown in [the security review](security_review.md#hosted-demo-image-scan), record the actual image IDs/advisory timestamp, and retain unresolved findings. Do not treat a zero `--ignore-unfixed` count as a clean scan or publish the private artifacts directory.

## Two-stack hosted checks

Use this variant to test the public and full deployments together. It reuses the reserved `proofops-hosted-check` public project, adds `proofops-hosted-full-check`, and runs **all** the existing container/public HTTPS tests plus the full-mode checks. Do not run it concurrently with the single-host checks or reuse those names for a real workspace. Begin with both reserved projects and their volumes absent. It requires the cached images built above, Node/Chromium and the frozen Python/frontend test dependencies.

```sh
python3 -m scripts.prepare_hosted_full_checks
public_full_check() {
  docker compose --env-file artifacts/hosted-full/private/.env.hosted \
    --env-file artifacts/hosted-full/private/.env.hosted-full \
    -p proofops-hosted-check -f compose.hosted.yaml -f compose.hosted-gateway.yaml \
    -f artifacts/hosted-full/private/images-public.json \
    -f artifacts/hosted-full/private/gateway.yaml "$@"
}
full_check() {
  docker compose --env-file artifacts/hosted-full/private/.env.hosted-full \
    -p proofops-hosted-full-check -f compose.hosted-full.yaml \
    -f artifacts/hosted-full/private/images-full.json \
    -f artifacts/hosted-full/private/full.yaml "$@"
}
full_check up -d --no-build --pull never db
full_check run --rm migrate
public_full_check up -d --no-build --pull never db
public_full_check run --rm migrate
python3 -m scripts.prepare_hosted_full_checks --create-users
full_check run --rm --no-deps seed
public_full_check run --rm --no-deps seed
full_check up -d --wait --no-build --pull never
public_full_check up -d --wait --no-build --pull never
public_full_check cp caddy:/data/caddy/pki/authorities/local/root.crt \
  artifacts/hosted-full/private/root.crt
.venv/bin/pytest tests/containers tests/hosted tests/hosted_full -q --tb=short \
  --junitxml=artifacts/hosted-full/containers-https.xml
.venv/bin/python -m scripts.run_hosted_full_browser_checks
public_full_check --profile worker --profile maintenance down --volumes --remove-orphans
full_check --profile maintenance down --volumes --remove-orphans
```

Preparation generates independent mode-0600 env files and synthetic account credentials under the ignored, mode-0700 `artifacts/hosted-full/private/` directory, preserving them on reruns. It briefly invokes the cached, network-disabled Caddy hasher; it does not start either application. `--create-users` creates the public bootstrap admin and full admin/viewer through `--password-stdin` after migrations, without credential arguments or stdout. It refuses duplicate accounts instead of changing their passwords. The root deployment env files and local workspace are not used.

The only host publications are Caddy's loopback 15080/15443. Full-mode HTTPS clients verify the copied internal test CA and force both hostnames to loopback with proxies disabled. The original public suite retains its assertions, including stopped-upstream recovery. New checks cover every full-host path/method's Basic challenge, incorrect credentials, the independent application login, Secure cookies, CSRF and viewer rejection, full worker completion, cross-stack data/session separation, actual container ports/networks/volumes and restricted database roles. A separate synthetic account proves five failures still lock out the correct password despite forged forwarded IPs; no limiter is disabled or raised.

The browser runner executes the original 20 Chromium tests through the full HTTPS hostname plus two shared-gateway tests. Its config adds gateway credentials only for the full origin. Explicitly anonymous test contexts clear inherited credentials. A Node DNS preload and Chromium resolver rules keep both names on loopback without editing host DNS. Browser TLS ignores the disposable issuer's trust error; the Python full-host checks verify that issuer. Traces/videos stay off and sessions stay in memory. The runner redacts raw and encoded credentials from console output and `artifacts/hosted-full/browser.txt`. Account JSON is private; do not upload the entire artifact directory.

The final cleanup removes only these disposable projects, with the Caddy project first so it releases the full application's network. The normal backend command still runs the complete unit/policy/PostgreSQL suite, including private setup and both effective Compose models. These tests do not exercise public ACME, internet DoS resistance, MFA, backup decryption or a disaster-recovery rehearsal.


## T01–T24 acceptance matrix

For a focused Python row, run `.venv/bin/pytest <path>::<test_name> -q`. All listed Python tests also belong to the full backend command above and its JUnit artifact. The common input root is `fixtures/replays/`; policy cases derive from the trusted fixture specification, and negative semantic labels live only under `evaluation/evaluator_only/`.

| ID | Executable evidence / fixture | Result and scope |
|---|---|---|
| T01 | `scripts/run_workload.py all`; `testing/virtual_users.js`; `artifacts/workload/comparison.json` | Measured local normal/peak traffic; per-run and per-class results retained. This is not AWS evidence. |
| T02 | `tests/unit/test_review.py::test_three_report_paths`; `valid-resize/`; API/browser equivalents | Valid synthetic candidate requests engineering review only after its contract passes. Local candidate experiment reported separately. |
| T03 | `tests/unit/test_review.py::test_violation_precedes_missing`; `unsafe-resize/`; policy fixtures | 1,024 MiB below the synthetic approved 2,048 MiB floor always revises; cost/AI cannot override. |
| T04 | `scripts/run_workload.py pressure`; `artifacts/workload/pressure-repair.json` | Actual Docker-confirmed OOM under a 64 MiB limit with 128 MiB pressure, followed by verified repair at 256 MiB. |
| T05 | `tests/unit/test_performance_boundaries.py::test_smoke_does_not_establish_capacity`; `incomplete-evidence/` | A 20-request smoke run collects evidence under a 10,000-request contract. |
| T06 | `tests/unit/test_review.py::test_collection_states_do_not_become_zero`; `test_empty_stale_and_new_commit`; `tests/unit/test_aws_collectors.py` | Denied/pending/empty/stale states preserved; mocked SDK collection plus deterministic checks. Live CloudWatch unrun. |
| T07 | `tests/unit/test_aws_collectors.py::test_sensitive_plan_bytes_never_survive_import`; `tests/unit/test_review.py::test_unsupported_numbers_stay_unknown` | Unknown/sensitive values remain unresolved and secrets do not survive import. |
| T08 | `tests/unit/test_review.py::test_container_only_change_has_no_task_compute_saving` | Container-limit-only edits do not reduce task CPU/memory charges. |
| T09 | `tests/unit/test_review.py::test_cost_null_zero_and_changed_hours`; frozen cost scenarios | Missing hours stay null; supported changed hours are recalculated. |
| T10 | `tests/integration/test_api.py::test_focus_ingestion_is_idempotent_and_reconciles`; `test_billing_endpoint_and_mixed_currency_null_duplicate_rows`; `fixtures/billing/focus_sample.csv` | Real PostgreSQL ingestion verifies credits, nulls, currencies, identical rows and repeated imports. |
| T11 | `tests/unit/test_review.py::test_low_cpu_without_demand_evidence_does_not_justify_resize` | Unit regression requires relevant demand/latency evidence; no live dependency-stall experiment claimed. |
| T12 | `tests/policy/test_memory_guard.py::test_actual_rego_fixture_suite`; unrelated-service case | Exact named-service policy leaves another service alone; scope coverage stays explicit. |
| T13 | `tests/unit/test_review.py::test_trusted_policy_cannot_be_weakened_by_input`; `tests/unit/test_cli.py::test_cli_trusted_map_cannot_be_changed_by_input`; `scripts/ci_review.py` | Trusted revision/map used despite candidate self-weakening. Local CI regression passes; remote enforcement unconfigured. |
| T14 | `tests/unit/test_review.py::test_empty_stale_and_new_commit`; guard fixture cases; browser changed-commit test | Commit/image/config/expiry changes invalidate applicability while old replay remains reproducible. |
| T15 | `tests/unit/test_review.py::test_model_cannot_change_facts_or_action` | Invented citation or numeric/action mutation is mechanically rejected. |
| T16 | `tests/unit/test_evaluation.py::test_valid_citations_do_not_validate_causal_inference` | Authored unsupported-causality control passes mechanics but fails semantic annotation. |
| T17 | `tests/unit/test_provider_adapters.py::test_quota_and_throttle_are_distinct_and_sdk_does_not_retry`; `tests/integration/test_budget_jobs.py::test_transient_retry_consumes_the_second_attempt` | Mocked permanent failures do not loop; transient retry consumes the bounded attempt allowance. |
| T18 | `tests/unit/test_provider_adapters.py::test_openai_terminal_states`; `test_anthropic_actual_sdk_mapping_and_terminal_states` | Refusal/truncation/nonterminal output is not a successful cached explanation. |
| T19 | `tests/integration/test_budget_jobs.py::test_atomic_budget_reservations_and_duplicate_dispatch`; `test_worker_crash_after_dispatch_keeps_charge_pending_and_does_not_retry` | Real PostgreSQL concurrency/recovery; uncertain spend remains reserved and undispatched twice. |
| T20 | `tests/unit/test_import_security.py::test_injected_log_instructions_get_no_authority_or_label_access` | Injected approval/deletion/disclosure instructions gain no tools or authority; runtime label boundary holds. |
| T21 | `tests/unit/test_evaluation.py::test_confident_wrong_answer_is_not_an_acceptance_signal` | Authored confidently wrong control remains a semantic failure. No live cheap-model quality claim. |
| T22 | `tests/unit/test_review.py::test_mismatched_population_inconclusive`; `tests/unit/test_performance_boundaries.py::test_local_arm_measurements_cannot_validate_x86_contract` | Incompatible units/timing/population/platform cannot establish improvement. |
| T23 | `tests/integration/test_budget_jobs.py::test_both_provider_results_unusable_preserves_deterministic_guard` | Mocked failure of both providers leaves deterministic findings and visible AI unavailability. |
| T24 | Manual uncoached workflow from `docs/interview_walkthrough.md` | **Unrun:** needs consenting engineer. Record completion, elapsed time, errors and help; no fabricated feedback. |

## Workload method and repeatability

The full k6 profile lasts eight minutes with an 80/15/5 small/medium/large mix. An open arrival-rate schedule offers 5–100 requests/second, allocating virtual users up to a cap. A virtual user is an execution slot, not an independent human. Offered rate and service latency jointly determine required concurrency. Dropped iterations reveal when the generator cannot begin scheduled work; slowing a closed loop would conceal this demand.

Warmup sends 100 verified requests before the measured window. The HTTP body carries a request ID, currency and bounded integer-cent items. The independent k6 oracle checks response ID/currency/count/total; a wrong HTTP 200 is an incorrect success, never useful work. p95 is a percentile of sampled latencies, not an average. Small/medium/large p95 and each repetition must meet the same limit; percentiles are not averaged across runs.

The frozen full contract requires at least 10,000 correct responses per run, p95 strictly below 250 ms, HTTP failures strictly below 1%, no incorrect successes, no dropped iterations and no restarts. Equality fails the two strict limits. Calibration uses a baseline before any candidate result. Three alternating baseline/candidate pairs use the same local image, profile and dependency hashes; baseline is 2 CPUs / 512 MiB and candidate 1 CPU / 256 MiB. These allocations are local cgroup settings, not Fargate task sizes or a cloud cost estimate.

```sh
docker compose --profile workload up -d --build workload
.venv/bin/python scripts/run_workload.py all
```

The first series is preserved under `artifacts/workload/`. To run a new independent series without overwriting it:

```sh
.venv/bin/python scripts/run_workload.py all --series repeat-01
```

To resume missing comparison runs after calibration, use `compare` with the same optional `--series`; frozen inputs must still match. Do not rebuild/change the workload image, server, profile or dependency lock mid-series. Full `all` takes about 57 minutes. Pressure uses only a newly owned labelled local container, never the API, database or AWS. A failed candidate remains failed; a missing summary is an execution failure, not a zero-latency pass.

## Interpretation and unrun checks

The optimization regressions additionally exercise cache expiry/replacement,
changed evidence/prompt/model settings, concurrent AI dispatch, caller-bound AWS
reuse and stale evidence, optional research failures/untrusted content, bounded
worker polling/concurrency/deadlines, migration rollback and secret-free operation
logs. All provider calls in these checks are mocked. k6 isolation tests execute
`k6 inspect` (initialization only) against the pinned local tool; they send no
workload requests and preserve smoke/full scenario thresholds. The runner refuses
hosted/public-demo mode, and the JS target allowlist is limited to dedicated local
8080/18080 targets. API/worker images contain neither k6 nor Playwright tooling.

For repeatable offline call/read measurements:

```sh
AI_MODE=off AWS_EC2_METADATA_DISABLED=true .venv/bin/pytest \
  tests/integration/test_optimization_measurements.py tests/integration/test_aws_cache.py \
  -q -o junit_family=legacy --junitxml=artifacts/optimization/measurements.xml
```

JUnit properties record mocked provider call counts, full-document materialization,
trusted-file reads and a small warm deterministic-engine timing sample. These are
not production latency, cloud cost, CPU/RAM or realized-savings benchmarks.

Passing means the stated checks passed for the exact supplied inputs. A known breach is a failure. Insufficient/incompatible measurements are inconclusive, even if the code correctly chooses `collect_evidence`. Unrun means prerequisites were absent. Local Linux ARM64 Docker measurements cannot validate the synthetic Linux x86_64 AWS approval. No cloud invoice or realized savings was measured.

The FOCUS file is a separate 1,000-row sample: 13 negative billed rows, BilledCost `20.52022672899` USD and EffectiveCost `14.97651418586` USD. Tests derive those totals from the actual pinned input. They are not production dashboard constants.

Live AWS smoke, paid OpenAI/Anthropic quality/latency/cost, a downstream compact-versus-flat model comparison, remote GitHub Actions, Windows execution and human usability remain unrun. Their next prerequisites are documented configuration/account access and budgets, an authorized repository workflow, a Windows host, or a consenting peer as applicable. None blocks the supported local replay workflow.
