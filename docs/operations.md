# Operations and troubleshooting

Docker Compose runs PostgreSQL, migrations, API, worker and web, with published ports bound to loopback. Username/password sessions and server-side roles protect the workspace. Hosted mode requires explicit HTTPS/auth configuration and an operator-managed TLS proxy; see [security and setup](security.md). No AWS or model key is required for readiness or replay. `.env.example` contains placeholders only; local setup generates missing database/session secrets.

## Startup, ports and migrations

Install Docker with Compose v2, Git and Python 3, then work from the app root. On macOS/Linux:

```sh
python3 scripts/configure_local.py
docker compose up -d --build
docker compose ps
```

On Windows PowerShell:

```powershell
py scripts/configure_local.py
docker compose up -d --build
docker compose ps
```

The web UI is at `http://127.0.0.1:5173`, API at port 8000, PostgreSQL at 55432 and optional workload at 8080. The experiment runner owns temporary port 18080. Compose waits for PostgreSQL and runs `alembic upgrade head` before API/worker startup. Inspect `docker compose logs --tail 100 api worker` for actual stages/errors. `docker compose --profile workload down` stops the app while preserving named volumes.

Create an admin once with `docker compose exec api proofops users create --username workspace-admin --role admin`. Passwords are prompted, never supplied as arguments. Sign in through the web app. A viewer is created with the same command and `--role viewer`; no account is created by copying `.env.example`.

For native development, the README bootstraps Python 3.12 and uv 0.12.23, then `uv sync --frozen --group dev --group docs`. Start only `docker compose up -d db`, run `.venv/bin/alembic upgrade head`, and launch `.venv/bin/uvicorn proofops.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers`, `.venv/bin/proofops-worker` and frontend `npm run dev` in separate terminals. Use `.venv/bin/proofops users create` for native account setup. PowerShell uses `.venv\Scripts\` executables. Stop container API/worker/web before using the same native ports. [README](../README.md) contains exact fresh-setup, test, replay and cleanup commands.

## Environment variables

| Variable | Meaning / default |
|---|---|
| DATABASE_URL | PostgreSQL connection; host development uses port 55432. Compose replaces the host with `db`. |
| POSTGRES_PASSWORD | Required private, URL-safe database password for Compose; generated locally, no default. Existing volumes require a separate role-password rotation. |
| SECRET_KEY | Required random secret, at least 32 characters / 16 distinct characters; generated locally, no default. Rotating it invalidates sessions. |
| PROOFOPS_MODE | `local` by default. `hosted` requires HTTPS origins, Secure cookies and a strong active admin. |
| PROOFOPS_ADMIN_USERNAME / PROOFOPS_ADMIN_PASSWORD | Optional one-time admin bootstrap; both or neither. Prefer CLI creation, remove stale bootstrap variables before rotation. |
| SESSION_COOKIE_SECURE / SESSION_TTL_SECONDS | Secure defaults true in code, explicitly false for local HTTP in the template. Absolute session lifetime defaults 28,800 seconds. |
| ALLOWED_HOSTS | Exact allowed hostnames; local defaults `127.0.0.1,localhost,api`, no wildcards. |
| PROOFOPS_PUBLIC_DEMO | False by default; true allows anonymous reads of unchanged explicitly seeded results and denies every HTTP write. |
| LOGIN_WINDOW_SECONDS / LOGIN_MAX_FAILURES / LOGIN_MAX_IP_ATTEMPTS | Shared database login limits; default 900-second windows, five account failures and 60 peer attempts. |
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
| CORS_ORIGINS | Exact trusted web origins, local by default. Unknown origins are rejected; credentialed CORS never accepts wildcards. Hosted mode requires HTTPS. |
| JOB_LEASE_SECONDS / JOB_TIMEOUT_SECONDS | Default 120-second lease, 180-second total job deadline. |
| MAX_BUNDLE_BYTES / MAX_ARTIFACT_BYTES / MAX_BUNDLE_FILES | Default 5 MiB total, 1 MiB per JSON artifact, 24 ZIP entries. |

Each input bundle carries its dated `rates.json`. The CLI can use an explicitly configured `RATE_CARD_PATH` or `--rate-card` override and records its hash; this is not a live AWS pricing discovery feature. The shipped environment leaves the override empty so evidence bundles retain their own rate basis.

## Diagnosis

| Symptom | Inspect / resolve |
|---|---|
| Backend is unavailable | `docker compose ps` and `docker compose logs --tail 100 api`; verify port 8000 is free. |
| API startup refuses auth configuration | Generate missing secrets, run migrations, and check hosted HTTPS/Secure/admin requirements. Do not disable the authentication boundary. |
| Login says invalid credentials or is rate limited | Use the configured account or rotate its password through the CLI. Wait for `Retry-After` after lockout; usernames receive generic errors. |
| Login succeeds but a session is missing | Local HTTP requires `SESSION_COOKIE_SECURE=false`; hosted mode requires TLS and true. Use the same browser/API hostname. |
| Request returns 401 / 403 | Sign in again for 401. For 403, check the user's role, public-demo mode, configured Origin and session-bound CSRF header. `/readyz` and `/docs` require authentication. |
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

Basic authentication, viewer/admin authorization, session/CSRF controls and shared login limits are implemented. Hosting still requires an operator-managed TLS proxy, secure secret delivery, private database access, encrypted backups, restore/retention procedures, monitoring and a reviewed deployment workflow. There is no tenant isolation, MFA/SSO, self-service recovery, separate approval role or complete authentication audit pipeline. Behind a proxy, users share its connection-peer rate-limit bucket because forwarded headers are not trusted. [Security](security.md) describes the boundaries and exact hosted/demo configuration; do not treat these controls as a production security certification.
