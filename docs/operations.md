# Operations and troubleshooting

The supported deployment is a local workspace bound to loopback. Docker Compose runs PostgreSQL, migrations, API, worker and web. No AWS or model key is required for readiness or replay. Database credentials in `.env.example` are disposable local defaults, not cloud/API secrets.

## Startup, ports and migrations

Install Docker with Compose v2 and Git, then work from the app root. On macOS/Linux:

```sh
test -f .env || cp .env.example .env
docker compose up -d --build
docker compose ps
```

On Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

The web UI is at `http://127.0.0.1:5173`, API at port 8000, PostgreSQL at 55432 and optional workload at 8080. The experiment runner owns temporary port 18080. Compose waits for PostgreSQL and runs `alembic upgrade head` before API/worker startup. Inspect `docker compose logs --tail 100 api worker` for actual stages/errors. `docker compose --profile workload down` stops the app while preserving named volumes.

For native development, the README bootstraps Python 3.12 and uv 0.12.23, then `uv sync --frozen --group dev --group docs`. Start only `docker compose up -d db`, run `.venv/bin/alembic upgrade head`, and launch `.venv/bin/uvicorn proofops.api.app:app --host 127.0.0.1 --port 8000`, `.venv/bin/proofops-worker` and frontend `npm run dev` in separate terminals. PowerShell uses `.venv\Scripts\` executables. Stop container API/worker/web before using the same native ports. [README](../README.md) contains exact fresh-setup, test, replay and cleanup commands.

## Environment variables

| Variable | Meaning / default |
|---|---|
| DATABASE_URL | PostgreSQL connection; host development uses port 55432. Compose replaces the host with `db`. |
| ARTIFACT_DIR | Dedicated directory inside application `artifacts/`; rejects research, code, evaluator and trust directories. |
| AI_MODE | `off` by default; `live` enables only otherwise eligible configured calls. |
| OPENAI_API_KEY / ANTHROPIC_API_KEY | Empty secret environment variables. Never committed or logged. |
| ALLOWED_PROVIDERS | Comma-separated explicit provider allowlist; empty blocks dispatch. |
| CHEAP_PROVIDER / CHEAP_MODEL | Configurable first attempt; default provider OpenAI, exact model ID unconfigured. |
| STRONG_PROVIDER / STRONG_MODEL | Configurable bounded escalation; default provider Anthropic, exact model ID unconfigured. |
| MODEL_PRICES_PATH | Exact model/capability/USD price records inside `config/`; current file has no live entries. |
| RATE_CARD_PATH | Optional CLI-only dated rate-card override inside the app; empty preserves bundle rates. Explicit `--rate-card` takes precedence. API imports always use the bundle's own rates. |
| AI_BUDGET_USD / AI_MAX_TASK_COST_USD | Positive explicit overall and per-task ceilings required for live dispatch. Defaults zero. |
| MODEL_TIMEOUT_SECONDS / MODEL_MAX_OUTPUT_TOKENS | Bounded SDK deadline/output; defaults 20 seconds / 1200 tokens. |
| AWS_ACCOUNT_ID / AWS_REGION | Expected STS account and region; no account configured, region defaults ap-south-1. |
| AWS_PROFILE / AWS_CLUSTER / AWS_SERVICE / AWS_LOG_GROUP | Optional normal credential-chain profile and exact collection scope. |
| AWS_LOOKBACK_SECONDS / AWS_MAX_CALLS | Default 3600-second lookback and 12 calls; code also caps pages, results and time. |
| CORS_ORIGINS | Only local web origins by default. Unknown origins are rejected. |
| JOB_LEASE_SECONDS / JOB_TIMEOUT_SECONDS | Default 120-second lease, 180-second total job deadline. |
| MAX_BUNDLE_BYTES / MAX_ARTIFACT_BYTES / MAX_BUNDLE_FILES | Default 5 MiB total, 1 MiB per JSON artifact, 24 ZIP entries. |

Each input bundle carries its dated `rates.json`. The CLI can use an explicitly configured `RATE_CARD_PATH` or `--rate-card` override and records its hash; this is not a live AWS pricing discovery feature. The shipped environment leaves the override empty so evidence bundles retain their own rate basis.

## Diagnosis

| Symptom | Inspect / resolve |
|---|---|
| Backend is unavailable | `docker compose ps` and `docker compose logs --tail 100 api`; verify port 8000 is free. |
| Readiness returns 503 | Start PostgreSQL and run `alembic upgrade head`; missing model keys do not affect readiness. |
| Review remains queued | Start the worker and inspect `docker compose logs --tail 100 worker`. A queued job has no fabricated report. |
| A worker died | Restart it. Expired leases are reclaimed up to three claims; dispatched charges stay uncertain. |
| PostgreSQL connection fails in a sandbox | Permit the specific local database test/command. Do not change to SQLite to bypass transaction checks. |
| Guard validation unavailable | Install pinned Conftest 0.71.0 or rebuild the API image. Both `0.71.0` and the official Docker `v0.71.0` display format are accepted. |
| Review collects evidence | Inspect source status, sample count, freshness, exact commit/image/config/profile/dependency hashes and populations. |
| Synthetic replay requested as live | Supply genuinely applicable recorded AWS observations and a separately approved live contract; fixture approvals do not become real approvals. |
| AI unavailable | Inspect the advanced trace: allowed provider/model, current price entry, keys, explicit budget, refusal/truncation or quota. Deterministic findings remain available. |
| Budget stays reserved | Reconcile the provider's actual usage for the exact attempt. Never refund an ambiguous timeout/crash merely to retry. |
| An old export no longer applies | Replay reproduces history. Request a new review for changed commits, policies or expired evidence. |
| Workload runner refuses an existing directory | It protects recorded evidence. Use a new series for a fresh experiment, or resume `compare` with matching frozen inputs. |

The budget ledger uses a fixed configured budget identity so restarting never resets spend. Lowering the environment limit is honored; increasing an existing ledger's limit requires a separately recorded operator/database maintenance decision. No unauthenticated public budget-reset endpoint exists. Reported usage may exceed a reservation if provider billing differs; this is recorded and blocks subsequent planned spending as appropriate.

## Retention and recovery

Local data remains until the operator removes it. There is no production retention scheduler. Save needed sanitized review ZIPs before removing this app's volumes. `docker compose down` preserves volumes; `docker compose down --volumes` intentionally erases this app's database/artifact volumes. Research inputs are outside these volumes and must remain untouched.

API errors omit raw provider bodies and secret-bearing input values. Database operations use connection, pool, statement and lock timeouts. SDK automatic retries are disabled; the router accounts for at most two attempts. Model uncertainty never changes the deterministic outcome.

## Before team hosting

This local application has no signup or user/tenant authorization. A team deployment would need authentication, role-specific approvals, account isolation, CSRF/session controls where applicable, secure secret delivery, encrypted storage, retention, observable operations and a reviewed deployment workflow. These are future deployment requirements, not implemented enterprise controls.
