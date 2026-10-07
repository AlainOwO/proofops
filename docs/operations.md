# Operations and troubleshooting

Local Docker Compose runs PostgreSQL, migrations, API, worker and web, with published ports bound to loopback. The standalone `compose.hosted.yaml` runs a read-only public demo behind Caddy HTTPS, with a private database and restricted runtime credentials. A separate `compose.hosted-full.yaml` can add an authenticated, writable workspace through that same Caddy without changing public-demo permissions. See the hosted runbooks below and [security](security.md). No AWS or model key is required for readiness or replay. Private setup files contain generated secrets and must never be printed or committed.

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

## Hosted public demo

Use a dedicated demo host and workspace containing only the supplied synthetic fixtures. Point a real DNS hostname at that host and allow inbound TCP 80/443 for Caddy's HTTPS issuance, renewal and redirects. Docker, Compose v2.24 or newer, Git and Python 3 are required. The Vite development server is not used.

`compose.hosted.yaml` is **standalone**: do not merge it with `compose.yaml`, which publishes development ports. Only Caddy publishes ports. Web/API share an internal application network; PostgreSQL and the one-shot maintenance services use a separate internal database network. API, worker, web and migration containers have CPU/memory limits; the runtime filesystems are read-only and unnecessary capabilities are dropped. API/worker have no external network and receive no cloud/model credentials. The hosted file explicitly fixes `PROOFOPS_MODE=hosted`, `PROOFOPS_PUBLIC_DEMO=true`, Secure cookies and `AI_MODE=off`.

Run from the repository root, substituting your DNS hostname and ACME contact address:

```sh
python3 scripts/configure_hosted.py --domain reviews.example.com --email operator@example.com
hosted() { docker compose --env-file .env.hosted -f compose.hosted.yaml "$@"; }
hosted --profile worker --profile maintenance build --no-cache --pull
hosted up -d db
hosted run --rm migrate
hosted run --rm --no-deps api proofops users create --username workspace-admin --role admin
hosted run --rm --no-deps seed
hosted up -d --wait
hosted ps
```

The setup script creates `.env.hosted` with mode 0600 and independent random bootstrap, owner, runtime and session secrets. It preserves existing credentials; it is not a rotation command. Password prompts do not echo. The first admin is required by hosted startup even though public-demo HTTP login is disabled. `seed` creates exactly three completed AI-off reviews and explicit public membership; the API's artifact mount stays read-only. The worker is behind an opt-in profile and is not started by the final `up`; even if started, public-demo workers refuse to claim jobs.

The `roles` service alone receives PostgreSQL bootstrap credentials. It provisions `proofops_owner` and `proofops_runtime` using salted SCRAM verifiers. `migrate` connects as the owner and grants runtime access after Alembic completes. API and worker use only `proofops_runtime`: application CRUD, no superuser/role creation/database creation/schema ownership/DDL, read-only migration metadata, and SELECT/INSERT-only audit access. Hosted API/worker startup rejects elevated runtime privileges. The local Compose operator connection remains separate and is unsuitable for hosted runtime use.

The hosted database is digest-pinned PostgreSQL **18.6** in its own `hosted-db18` volume mounted at `/var/lib/postgresql`. Local Compose stays on patched **17.11** to preserve compatibility with existing 17.x volumes. Never attach a 17.x data directory to the hosted 18.x container; importing an existing workspace requires a separately backed-up dump/restore or reviewed PostgreSQL major-version migration. Both images retain the official initialization flow and use Alpine `su-exec` for the final UID/GID switch, replacing the stale bundled `gosu` binary. Fresh root-owned storage and non-root PostgreSQL operation have container regressions.

Caddy obtains and renews public certificates automatically and persists certificate state in `caddy-data`/`caddy-config`; protect these volumes as private key material. It proxies `/api/*`, readiness, health and disabled API-doc paths directly to the API, and serves the built frontend through unprivileged nginx on internal port 8080. HTTPS responses include `Strict-Transport-Security: max-age=31536000`; HSTS is deliberately set at this TLS endpoint, without `includeSubDomains` or preload. Preserve the certificate volumes across routine restarts. Caddy allows five seconds for request headers and ten seconds for request bodies. Backend docs/OpenAPI routes are absent in hosted mode. CSP, `X-Frame-Options: DENY` and `nosniff` cover successful responses, rejections and errors at the API and proxies.

Verify the deployed hostname:

```sh
curl --fail --show-error https://reviews.example.com/readyz
curl --head https://reviews.example.com/
curl --head http://reviews.example.com/
curl --include --request POST https://reviews.example.com/api/v1/bundles --data '{}'
```

Expect ready/200, HTTPS security headers and HSTS, an HTTP-to-HTTPS redirect, and 403 for the POST. The UI must say `DEMO · READ-ONLY`, show only the three seeded reviews, and expose no login, billing or editing controls. `/docs`, `/redoc` and `/openapi.json` must return 403/404 without scripts or schemas. `hosted ps` must show published ports only on Caddy; a bare `5432/tcp` or `8080/tcp` is internal image metadata, not a host publication. Never print `hosted config` or private environment files; use `hosted config --quiet` for validation.

To reseed this dedicated demo, stop the public services, run the maintenance container, and restart:

```sh
hosted stop caddy api worker
hosted run --rm --no-deps seed
hosted up -d --wait
```

Reset preserves users, sessions, audit history and the documented accounting data; older artifact files remain. Only explicit, unchanged seed memberships are public. Keep encrypted backups and operator-controlled retention for database, artifacts and certificate volumes. Runtime credentials cannot edit/delete audit history, but owners and host operators still can; an external append-only sink and retention scheduler remain future work. Ordinary `hosted down` preserves volumes. Retain image/config versions and backups for rollback; never downgrade a PostgreSQL data directory in place.

Admission defaults apply to the **single API process** in this deployment: 16 concurrent requests, eight per connection peer, four per authenticated user, two concurrent logins, 600 requests per peer and 300 per principal per 60 seconds, 20 MiB of buffered payload bytes, and an absolute ten-second body deadline. Buffering follows authentication, role/demo checks and CSRF; ZIP/JSON parsing and import storage run in a thread pool. API/worker containers are limited to 1 CPU/512 MiB, database to 1 CPU/1 GiB, web to 0.5 CPU/128 MiB and Caddy to 0.5 CPU/256 MiB. Keep one API process; replicas require divided limits or shared admission. Do not trust arbitrary forwarded IP headers. Behind the proxy, clients share the peer bucket. Public-demo writes/login are disabled; these controls are not a distributed DoS defense or a writable-team recovery design.

Rebuild and rescan before exposure and after dependency/image changes. [Security review](security_review.md#hosted-demo-image-scan) records both filtered and unfiltered HIGH/CRITICAL counts, including remaining Debian findings with no published distribution fix. A zero `--ignore-unfixed` result is not a clean scan. The local verification used an internal test certificate issuer; public DNS/ACME issuance and internet load resistance were not tested.

## Hosted full mode beside the public demo

This is a separate, writable **single workspace** for a small, trusted audience. Keep the public hostname and its synthetic database read-only. Point a second DNS hostname at the same host. [compose.hosted-full.yaml](../compose.hosted-full.yaml) is standalone, with project name `proofops-hosted-full`, a separate PostgreSQL 18 cluster, `full-db18`/`full-artifacts` volumes and independent credentials. Never merge it with either other stack. It fixes hosted mode, `PROOFOPS_PUBLIC_DEMO=false`, Secure cookies, AI off and the existing database login limits. Its worker starts by default; API/worker root filesystems remain read-only with a separate writable artifact volume.

[compose.hosted-gateway.yaml](../compose.hosted-gateway.yaml) is an overlay **only for the public stack**. It connects the existing Caddy to the full project's internal application network and imports both hostname routes. Only that Caddy publishes TCP 80/443. The public and full API/web services have distinct proxy aliases; their database networks and volumes are separate. Neither API nor worker has internet egress. Caddy never joins either database network.

First build the cached Caddy image used for offline password hashing, then configure both hostnames. Use the existing public hostname when extending an existing deployment:

```sh
docker build --pull --tag proofops-caddy deploy/caddy
python3 scripts/configure_hosted.py \
  --public-domain reviews.example.com \
  --full-domain workspace.example.com \
  --email operator@example.com

public() {
  docker compose --env-file .env.hosted --env-file .env.hosted-full \
    -f compose.hosted.yaml -f compose.hosted-gateway.yaml "$@"
}
full() {
  docker compose --env-file .env.hosted-full -f compose.hosted-full.yaml "$@"
}

public config --quiet
full config --quiet
full --profile maintenance build --no-cache --pull
public --profile worker --profile maintenance build --no-cache --pull
full up -d db
full run --rm migrate
public up -d db
public run --rm migrate
```

Configuration preserves existing credentials, including the public deployment's credentials. It generates missing full bootstrap, owner, runtime and session secrets plus a random gateway username/password and a bcrypt hash with cost 14. The two env files use separate credential names and mode 0600; keep both private. The hasher uses the cached image with networking disabled and passes the password over stdin. Its output is captured. The gateway password and hash are stored only in `.env.hosted-full`; only the username and hash enter Caddy's environment. Bcrypt's dollar signs are single-quoted for Compose. Do not remove those quotes, source the env files, print resolved configuration, or treat rerunning setup as password rotation. Import the gateway username/password into your password manager through a secure local-file workflow.

Create the full admin and viewer after migrations. This interactive operator snippet uses non-echoing prompts and passes each password directly to `--password-stdin`, without arguments, shell variables or stdout. Choose distinct strong passwords from your password manager. **Omit the public-admin row if the existing public demo already has its required admin.** Existing users are never overwritten.

```sh
python3 - <<'PY'
import getpass
import subprocess
import warnings

warnings.simplefilter("error", getpass.GetPassWarning)
accounts = [
    (".env.hosted", "compose.hosted.yaml", "public-admin", "admin"),
    (".env.hosted-full", "compose.hosted-full.yaml", "full-admin", "admin"),
    (".env.hosted-full", "compose.hosted-full.yaml", "full-viewer", "viewer"),
]
for env_file, compose_file, username, role in accounts:
    password = getpass.getpass(f"Unique password for {username}: ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match; no account changed for this entry.")
    subprocess.run(
        ["docker", "compose", "--env-file", env_file, "-f", compose_file,
         "run", "--rm", "--no-deps", "-T", "api", "proofops", "users", "create",
         "--username", username, "--role", role, "--password-stdin"],
        input=password + "\n", text=True, check=True,
    )
PY

full run --rm --no-deps seed
full up -d --wait
# Only for a fresh public database; omit when the public demo is already seeded:
public run --rm --no-deps seed
public up -d --wait
public ps
full ps
```

Start the full project before attaching the shared Caddy: it owns the `proofops-hosted-full_application` network. If deliberately using another full project name, set `FULL_PROXY_NETWORK` to that project's application network in the private full env file. The public project retains its original name and certificate volumes. After enabling the shared gateway, use the `public` wrapper above for public operations so the overlay remains loaded. Caddy restarts affect both hostnames; force-recreate only Caddy when changing mounted Caddyfiles, since its admin API is disabled.

Verify the deployed hostnames without credentials:

```sh
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --request POST https://reviews.example.com/api/v1/bundles --data '{}'
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  https://workspace.example.com/
```

Expect **403** on the public write and **401** with a Basic challenge on the full hostname. The full gate covers assets, health, login, API, documentation and every method; HTTP redirects to HTTPS. Supply the gateway credential in the browser, then expect **Sign in to ProofOps**. Sign in separately as the full admin to import/run an AI-off review; sign in as the viewer to inspect/export it with no write controls. Basic Auth does not grant an application role. Caddy removes the Basic Authorization header before proxying. Application sessions remain host-only, Secure/HttpOnly/SameSite cookies, and writes still require application authentication, admin role and CSRF.

The public hostname must still show only three seeded reviews and `DEMO · READ-ONLY`, with no sign-in or editing controls. A full-stack review or session cannot make it writable or public. Both `ps` listings must show host publications only on the public project's Caddy. The reproducible [two-stack HTTPS/browser checks](testing.md#two-stack-hosted-checks) verify these boundaries, actual runtime privileges, the default worker and login lockout.

Seeding is a reset, not an import into an active workspace. The initial full seed is optional; later reseeding discards that stack's reviews while preserving users, sessions, audit/accounting data and older artifacts. Stop that stack's API and worker first, and take a backup before resetting saved work:

```sh
full stop web api worker
full run --rm --no-deps seed
full up -d --wait
```

For public-only reseeding while retaining full-host availability, use `public stop web api worker`, run its seed service, then `public up -d --wait`. Leave Caddy running. Routine `stop`/`down` preserves data; do not add `--volumes`. To retire full mode, first recreate Caddy using just the original public Compose file, which removes the full route and detaches its network; then bring down the full project.

### Manual backup and recovery

Back up both workspaces independently, both private env files, the deployed revision/configuration, and Caddy's certificate state. This maintenance-window example requires an installed `age` binary and `HOSTED_BACKUP_RECIPIENT` set to the backup operator's **public** age recipient. Keep its decryption key off the application host. The commands stream directly into encrypted, owner-only files; no passwords are printed. Prevent concurrent CLI maintenance while taking the snapshots. Stopping Caddy pauses both hostnames.

```sh
(
  set -eu
  set -o pipefail
  command -v age >/dev/null
  : "${HOSTED_BACKUP_RECIPIENT:?Set the public age recipient for backups}"
  umask 077
  snapshot="artifacts/hosted-backups/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$snapshot"
  trap 'set +e; full up -d --wait; public up -d --wait' EXIT
  public stop caddy web api worker
  full stop web api worker

  full exec -T db pg_dump -U proofops_bootstrap -d proofops -Fc \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/full.dump.age"
  full run --rm --no-deps -T --entrypoint tar api -czf - -C /app/artifacts . \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/full-artifacts.tar.gz.age"
  public exec -T db pg_dump -U proofops_bootstrap -d proofops -Fc \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/public.dump.age"
  public run --rm --no-deps -T --entrypoint tar api -czf - -C /app/artifacts . \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/public-artifacts.tar.gz.age"
  public run --rm --no-deps -T --entrypoint tar caddy -czf - -C / data config \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/caddy.tar.gz.age"
  tar -czf - .env.hosted .env.hosted-full compose.hosted.yaml \
    compose.hosted-full.yaml compose.hosted-gateway.yaml deploy/Caddyfile deploy/Caddyfile.full \
    | age -r "$HOSTED_BACKUP_RECIPIENT" > "$snapshot/configuration.tar.gz.age"
  git rev-parse HEAD > "$snapshot/revision.txt"
)
```

Check every pipeline succeeded before transferring the encrypted set off-host. An incomplete set is not a recovery point. Rehearse decryption and restore into **new, isolated projects/volumes**, never over the running public demo: provision matching owner/runtime roles, restore each PostgreSQL dump as the bootstrap operator, run the owner migration/grants for the recorded app version, and restore its matching artifacts with UID 10001 ownership. Restore private env files as 0600 and retain the matching session/database credentials. Restore Caddy state separately before reconnecting DNS. Verify authentication, viewer restrictions, review/export hashes and public write rejection. Do not restore a full dump into the public project or attach an older PostgreSQL data directory to 18.x.

This manual procedure is not an automated backup, retention or disaster-recovery service. Encrypting/copying files does not establish a working restore; the operator must rehearse it and monitor future backups.

### Limits of full mode

This deployment is **not production-grade team hosting**. It has no MFA/SSO or self-service recovery, and every authenticated full user shares one workspace; there is no tenant or per-review isolation. A shared Basic password is an outer access gate, not a second factor or an individual audit identity. **SR-05 remains open:** five account failures can deny the correct password, and all users behind Caddy share the 60-attempt peer bucket per 15 minutes. Do not disable these limits or trust arbitrary forwarded IP headers.

Full mode additionally exposes imports, persistent jobs/artifacts, guard validation, billing and disposition writes. Admission bounds and container limits remain, but durable queue/storage quotas, automated retention, reviewed recovery, distributed edge limiting and external append-only audit storage are still absent. Full traffic can exhaust the shared host or Caddy; Caddy is trusted by both stacks and a shared availability dependency. Read the [full-mode attack-surface review](security_review.md#hosted-full-mode-attack-surface) and existing unresolved image findings before using real data. AI/cloud credentials and live calls remain disabled.

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
| REQUEST_BODY_TIMEOUT_SECONDS / REQUEST_MAX_BUFFERED_BYTES | Absolute body-read deadline (10 seconds) and aggregate buffered payload budget (20 MiB). |
| REQUEST_MAX_CONCURRENCY / REQUEST_MAX_PEER_CONCURRENCY / REQUEST_MAX_PRINCIPAL_CONCURRENCY / REQUEST_MAX_LOGIN_CONCURRENCY | Per-process concurrent admission defaults 16 / 8 / 4 / 2; no waiting queue. |
| REQUEST_QUOTA_WINDOW_SECONDS / REQUEST_PEER_QUOTA / REQUEST_PRINCIPAL_QUOTA / REQUEST_MAX_IDENTITIES | Window 60 seconds, request quotas 600 / 300, at most 2,048 tracked peer/principal identities per map. Idle expired entries are reused; exhaustion fails closed. |
| HOSTED_DOMAIN / ACME_EMAIL | DNS hostname and certificate contact in private `.env.hosted`; used by the standalone Caddy deployment. |
| FULL_DOMAIN / FULL_PROXY_NETWORK | Separate full hostname in `.env.hosted-full`; optional network override defaults to `proofops-hosted-full_application`. |
| FULL_POSTGRES_PASSWORD / FULL_OWNER_PASSWORD / FULL_RUNTIME_PASSWORD / FULL_SECRET_KEY | Independent full-stack bootstrap, owner, runtime and session credentials; never reuse public values. |
| FULL_BASIC_AUTH_USER / FULL_BASIC_AUTH_PASSWORD / FULL_BASIC_AUTH_HASH | Generated gateway credentials, stored only in private `.env.hosted-full`; Caddy receives only the username and bcrypt hash. |
| PROOFOPS_OWNER_PASSWORD / PROOFOPS_RUNTIME_PASSWORD | Independent hosted database credentials. API/worker receive only a runtime URL; bootstrap and owner credentials are confined to maintenance services. |
| ARTIFACT_DIR | Dedicated directory inside application `artifacts/`; rejects research, code, evaluator and trust directories. |
| AI_MODE | `off` by default; `live` enables only otherwise eligible configured calls. |
| AI_CACHE_ENABLED / AI_CACHE_TTL_SECONDS | Accepted-output cache on by default, TTL 300 seconds (1–3,600). Exact evidence/prompt/model/request keys and output validation remain required. |
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
| AWS_EVIDENCE_CACHE_TTL_SECONDS | 60 seconds by default; 0 disables reuse, maximum 3,600. Original collection/observation times and contract freshness checks are preserved; every hit verifies STS identity. |
| SEARCH_PROVIDER / SEARCH_API_KEY / SEARCH_ENGINE_ID | Optional operator research: `off` and empty credentials by default; `google` requires both private values. Supplied hosted stacks keep it off. See [tools](tools.md). |
| SEARCH_TIMEOUT_SECONDS / SEARCH_MAX_RESULTS / SEARCH_CACHE_TTL_SECONDS | Total provider deadline 5 seconds (at most 20), five results (1–10), cache TTL 300 seconds (0 disables, maximum 3,600). |
| CORS_ORIGINS | Exact trusted web origins, local by default. Unknown origins are rejected; credentialed CORS never accepts wildcards. Hosted mode requires HTTPS. |
| JOB_LEASE_SECONDS / JOB_TIMEOUT_SECONDS | Default 120-second lease, 180-second total job deadline. |
| WORKER_CONCURRENCY | One execution slot by default, maximum four; local `.env` or full stack `.env.hosted-full`. No unbounded Python task queue. |
| WORKER_POLL_MIN_SECONDS / WORKER_POLL_MAX_SECONDS | Idle queue polling backs off from 0.5 to 5 seconds, resetting after work; minimum 0.1–5, maximum up to 30 and not below the minimum. |
| OPERATION_LOGGING | True by default; bounded JSON operation timing/counters without SQL, credentials, queries or evidence text. False disables these records, not security audits. |
| MAX_BUNDLE_BYTES / MAX_ARTIFACT_BYTES / MAX_BUNDLE_FILES | Default 5 MiB total, 1 MiB per JSON artifact, 24 ZIP entries. |

Each input bundle carries its dated `rates.json`. The CLI can use an explicitly configured `RATE_CARD_PATH` or `--rate-card` override and records its hash; this is not a live AWS pricing discovery feature. The shipped environment leaves the override empty so evidence bundles retain their own rate basis.

## Diagnosis

| Symptom | Inspect / resolve |
|---|---|
| Backend is unavailable | `docker compose ps` and `docker compose logs --tail 100 api`; verify port 8000 is free. |
| API startup refuses auth configuration | Generate missing secrets, run migrations, and check hosted HTTPS/Secure/admin requirements. Do not disable the authentication boundary. |
| Login says invalid credentials or is rate limited | Use the configured account or rotate its password through the CLI. Wait for `Retry-After` after lockout; usernames receive generic errors. |
| Login succeeds but a session is missing | Local HTTP requires `SESSION_COOKIE_SECURE=false`; hosted mode requires TLS and true. Use the same browser/API hostname. |
| Request returns 401 / 403 | Sign in again for 401 outside demo mode. For 403, check role, demo mode, Origin and CSRF. Public-demo writes always return 403; hosted docs are disabled. |
| Request returns 408 / 429 / admission 503 | Complete uploads within the deadline and respect `Retry-After`; inspect active request/peer capacity. Do not remove quotas or trust forwarded identities to evade a shared proxy bucket. |
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

## Worker execution and lightweight measurements

The existing PostgreSQL queue remains the only queue. Each worker slot owns one
loop/router and claims with `SKIP LOCKED`; the executor holds only the configured
number of loops. The default stays one slot within the existing 1 CPU/512 MiB
container. More slots can overlap bounded I/O but do not create more CPU or
database capacity. The API/worker retain their connection pools and the hosted
runtime role's connection limit; profile actual demand before increasing slots.

Idle polling doubles from `WORKER_POLL_MIN_SECONDS` to
`WORKER_POLL_MAX_SECONDS`, then resets after a handled job. The default maximum
can add up to five seconds to an idle queue's pickup latency. This trades fewer
idle database queries for bounded startup delay; no throughput/CPU improvement is
claimed without a workload measurement. Public-demo workers still refuse work.
SIGTERM/interrupt stops idle loops and lets in-flight bounded work finish until
the container's stop deadline. A killed process retains normal lease recovery
and uncertain model reservations.

Jobs retain queued/running/completed/failed states and the three-claim recovery
limit. Exhaustion records `JOB_RECOVERY_LIMIT` with a final timestamp/audit event.
Stage deadlines are checked after review, explanation and export and again before
commit; timeout records `JOB_TIMEOUT`. Lost ownership cannot overwrite another
worker's result. Native deadlines are cooperative between bounded stages, not a
hard process kill; input limits, SDK/SQL timeouts and the existing container memory
limit remain necessary. There is no durable queue/storage quota or retention daemon.

`OPERATION_LOGGING=true` emits JSON records for HTTP requests, worker jobs/reviews,
model generation, AWS collection and optional research. Records include duration,
SQLAlchemy statement count/cursor duration, generated request/job ID, cache counts,
available model usage/cost and AWS call/source-failure counts. Worker records add
first-claim queue wait (or job age for recovery) and artifact bytes. HTTP records
include registered route templates, method, status and response bytes; liveness
probes are omitted. `X-Request-ID` is generated by the server and cannot be chosen
by a client. SQL text/parameters, private evidence, search queries, host/IP values,
passwords, headers and provider bodies are not part of these records.

Counters cover SQLAlchemy statements, not pool pings or every wire round trip;
cursor time excludes pool wait/transaction commit. Model tokens/cost reflect
reported new attempts, not duplicate charges for cached output. Input totals
include uncached input and provider cache reads/writes. Existing stored accounting
stays authoritative. Configure host log rotation; no monitoring service
or external telemetry collector is installed.

## Optimization migration and rollback

Migration `2a0c9f4b7e61` adds disposable tool observations, their expiry index, an
AI-cache expiry index and the job ordering index. Existing reviews, users,
artifacts, budgets and audits are preserved. Ordinary index creation can lock
writes on larger databases: back up, drain/stop the relevant API and worker, run
the owner migration and grants, then start the matching application images. Do
this separately for public and full projects; do not copy credentials or data
between them. Follow the same `migrate` services in the hosted runbooks; local
Compose runs Alembic before startup.

Rollback requires stopping the new application, downgrading to `f6a91d2e83b4` as
the owner, and starting the previous matching images/configuration. Downgrade
removes only the new disposable observations and indexes, not review/accounting
data. Re-run runtime grants after operator migration work. The upgrade/downgrade
regression uses only `proofops_test`; rehearse a full backup restore separately.

## Retention and recovery

Local data remains until the operator removes it. There is no production retention scheduler. Save needed sanitized review ZIPs before removing this app's volumes. `docker compose down` preserves volumes; `docker compose down --volumes` intentionally erases this app's database/artifact volumes. Research inputs are outside these volumes and must remain untouched.

API errors omit raw provider bodies and secret-bearing input values. Database operations use connection, pool, statement and lock timeouts. SDK automatic retries are disabled; the router accounts for at most two attempts. Model uncertainty never changes the deterministic outcome.

## Before team hosting

The supplied deployments cover a dedicated read-only synthetic demo and a separate gated full workspace. Production team hosting still needs reviewed recovery/edge limiting, secret delivery, operated encrypted backups, restore/retention procedures, monitoring and dependency maintenance. There is no tenant isolation, MFA/SSO, self-service recovery, separate approval role or external tamper-evident audit pipeline. Proxy peers share rate limits because forwarded headers are not trusted; SR-05 remains open. [Security](security.md) describes these boundaries; this is not a production security certification.
