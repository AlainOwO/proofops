# Authentication, authorization and hosting

ProofOps has one shared workspace. Authenticated viewers can read its saved reviews, findings, outcomes and analytics; administrators can also write. Roles do not grant deployment access, activate policy, change deterministic findings, or isolate different teams' data.

## Local setup

From the repository root, generate missing local secrets, run migrations through Compose, and create an account:

```sh
python3 scripts/configure_local.py
docker compose up -d --build --wait
docker compose exec api proofops users create --username workspace-admin --role admin
docker compose exec api proofops users create --username workspace-viewer --role viewer
```

Choose your own usernames. Password prompts do not echo. Passwords must contain 14–128 characters and at least eight distinct characters, must not contain the username, and must not be obvious passwords or setup placeholders. Prefer a password manager's unique random password. There is no default password, signup endpoint or automatic demo account.

The stdlib-only setup script writes `.env` with mode 0600 on POSIX, creates missing random session/database secrets, preserves existing settings, and never prints passwords. Python 3 on Windows can run it with `py scripts/configure_local.py`; restrict the file's Windows ACL to the operator account. Windows execution has not been verified on this host. The script does not create a user. Sign in at `http://127.0.0.1:5173`; the local template explicitly sets `SESSION_COOKIE_SECURE=false` for HTTP. Do not use that setting for hosting.

Native equivalent after `.venv/bin/alembic upgrade head`:

```sh
.venv/bin/proofops users create --username workspace-admin --role admin
.venv/bin/uvicorn proofops.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Automation may use `--password-stdin` with a secret supplied over standard input. Never put passwords in command arguments, checked-in scripts, shell history or screenshots. Optional initial bootstrap accepts `PROOFOPS_ADMIN_USERNAME` and `PROOFOPS_ADMIN_PASSWORD` together through a private environment. Existing accounts are never silently overwritten: mismatched bootstrap credentials stop startup. Remove the bootstrap variables after creating the account and before rotating its password.

## Server-side access rules

| Operation | Anonymous | Viewer | Admin |
|---|---|---|---|
| `GET /healthz` | Allowed | Allowed | Allowed |
| `GET /api/v1/auth/login` | CSRF challenge | CSRF challenge | CSRF challenge |
| `POST /api/v1/auth/login` | Password and login CSRF required | Same | Same |
| Session, readiness, replays, list/detail, downloads, analytics, local API reference | 401 | Allowed | Allowed |
| `POST /api/v1/auth/logout` | 401 | Session CSRF required | Session CSRF required |
| Import bundle, run review, create/validate guard draft | 401 | 403 | Session CSRF required |
| Record disposition, import billing sample, reset demo reviews | 401 | 403 | Session CSRF required |
| Future HTTP routes | Auth required | Safe reads only | Writes also require CSRF |

An outer authentication boundary protects routes even if a new handler omits a dependency. Only health and login are explicitly public in ordinary mode. Configured CORS preflights negotiate access without running an API handler. Tests enumerate every registered route and method, including framework docs/HEAD routes; adding an endpoint requires updating its role matrix. The frontend hides admin controls, but the API remains authoritative.

Hosted applications register no `/docs`, `/redoc`, `/docs/oauth2-redirect` or `/openapi.json` routes. Local documentation is an authenticated, self-contained HTML reference and schema download, with no third-party scripts. CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, no-store and referrer-policy headers wrap the entire API stack, including Host/origin/auth/size/quota rejections and unhandled 500 responses.

Reset through `POST /api/v1/admin/reset-demo-data` additionally needs `{"confirm": true}`. The existing local-database restriction and running-job protection still apply. The CLI reset remains an explicit host-operator action; a web viewer cannot invoke it. Users and sessions survive resets.

## Sessions, CSRF and brute-force limits

- Argon2id hashes use 64 MiB memory, three iterations, parallelism two and random salts. Password rotation/disabling revokes all of the user's sessions. Roles and active status are checked in storage on each request.
- A random opaque session token is carried only in an HttpOnly, SameSite=Lax, host-only cookie with Path=/, expiry and Max-Age. PostgreSQL stores a keyed digest, not the cookie value. Secure cookies use the `__Host-` prefix. The default absolute lifetime is eight hours; `SESSION_TTL_SECONDS` accepts 60–86,400 seconds. Login rotates the browser's prior session; logout revokes it. There is no sliding refresh.
- `GET /api/v1/auth/login` returns a CSRF token and sets a signed HttpOnly challenge cookie valid for ten minutes. Login must send both the cookie and `X-CSRF-Token`. After login, `GET /api/v1/auth/session` returns the session's CSRF token. Every subsequent unsafe request, including logout, must send it. Tokens are bound to the session; a different session's token is rejected. The frontend holds the CSRF token in memory and stores no bearer credentials in localStorage.
- Requests with an unconfigured Origin are rejected. CORS allows exact configured origins with credentials; wildcards are rejected at startup. CSRF validation also protects requests that omit Origin. Allow only origins controlled by the operator, and keep browser/API traffic under the same origin through the web proxy.
- PostgreSQL persists per-account failure counts and per-connection-peer attempts across restarts/workers. Defaults are five failed attempts per account and 60 attempts per peer per 15-minute window, with a 15-minute lockout when a limit is reached. Peer admission happens before account-state allocation, and attempts against a blocked account still consume the peer allowance. Unknown and known users receive the same credential errors and throttling responses; admitted unknown users still incur an Argon2 verification. Blocked responses include `Retry-After`. Limits are bounded configuration, not an in-memory per-process counter. Account-wide lockout also denies the correct password from other IPs; host operators retain the CLI, and hosted deployments need a separately reviewed recovery/edge-limiting strategy.
- The supplied Uvicorn commands disable proxy-header trust. Forged `X-Forwarded-For` headers cannot choose a new limiter identity. Behind Nginx or a TLS proxy, users share the proxy peer bucket; account limits still apply. A reviewed edge limiter can add real-client protections. Do not simply trust arbitrary forwarded headers to increase capacity.

API responses are marked `Cache-Control: no-store`. Backend errors do not return password inputs or raw database exceptions. Frontend 401 responses unmount cached workspace data, 403 responses show the server error and refresh identity, and absolute expiry returns to sign-in. Downloads use the same error handling. In-progress requests that completed before revocation are not retroactively cancelled.

HTTP admission precedes session lookup and password hashing. Per-process concurrency, peer/principal request quotas, a separate login concurrency bound, bounded identity maps and an aggregate body-byte budget reject excess work without a waiting queue. Protected bodies are buffered only after authentication, authorization, demo-mode and CSRF checks, with an absolute read deadline. Import parsing/storage run off the event loop. The supplied hosted deployment runs one API process with container CPU/memory limits; these are not distributed edge limits. Defaults and operator constraints are in [operations](operations.md#hosted-public-demo).

Imports, queued/completed/failed reviews, reset and billing events carry the authenticated user ID. Worker attribution is saved with the job, independently of its lease owner; migrated historical jobs are explicitly `legacy-unattributed`. Account creation/password changes/disabling, admitted login successes/failures and throttled attempts, session rotation and logout add events containing IDs and fixed status values, never usernames, passwords, password hashes, tokens or request bodies. CLI actions identify `host-operator`; bootstrap creation identifies `bootstrap`. Runtime database credentials can SELECT/INSERT audit records but cannot UPDATE/DELETE them. Host/database owners remain trusted, and external append-only export and retention scheduling are not implemented.

## Hosted configuration

For the requested read-only public demo, use the standalone [Hosted public demo runbook](operations.md#hosted-public-demo). It generates a separate `.env.hosted`, provisions bootstrap/owner/runtime database roles, seeds synthetic results, and starts Caddy automatic HTTPS. Only ports 80/443 are published; API, web and database stay internal. Do not merge the hosted file with local Compose. Its API/worker mounts are read-only, AI is off, provider credentials are absent, and the worker is not started by default.

For a separate writable workspace, use the [adjacent full-mode runbook](operations.md#hosted-full-mode-beside-the-public-demo). Its standalone project has independent PostgreSQL/artifact volumes and credentials, restricted runtime roles, hosted/Secure settings, AI off and a default-on worker. The public project's Caddy is the only ingress to both stacks. The full host is protected only by application authentication: anonymous visitors receive the login page with HTTP 200, and protected API calls return HTTP 401 with `Authentication required.`. Application roles, CSRF, database login limits, HTTPS/security headers and HSTS remain enforced. Public-demo settings and seeded-read boundaries remain unchanged.

The full workspace has no MFA or tenant isolation. Anyone who can reach the host can attempt application login; SR-05 account lockout and the shared proxy peer bucket still affect new logins. Full mode also exposes writable imports, queues/artifacts and guard/billing/disposition operations to authenticated users. Caddy is trusted by both workspaces and shares their availability risk. The [full-mode security review](security_review.md#hosted-full-mode-attack-surface) lists these exposures and the other open findings; this is not production-grade team hosting.

Custom public-demo deployments must preserve these settings and the restricted runtime database role:

```dotenv
PROOFOPS_MODE=hosted
SECRET_KEY=<random value generated privately; at least 32 characters>
SESSION_COOKIE_SECURE=true
ALLOWED_HOSTS=reviews.example.com
CORS_ORIGINS=https://reviews.example.com
PROOFOPS_PUBLIC_DEMO=true
```

These are placeholders, not usable secrets. `SECRET_KEY` needs at least 16 distinct characters and rejects common placeholders. Hosted setup generates independent random credentials. Hosted settings also require a PostgreSQL URL containing a privately generated password of at least 32 characters and 16 distinct characters; placeholders and credential query overrides are rejected before connecting. API/worker startup additionally rejects superusers, database/schema owners, role memberships, DDL privileges and migration/audit modification privileges. The migration service uses a separate owner URL. Compose interpolation expects URL-safe characters, as produced by setup. Never commit the filled environment or print resolved Compose configuration; use `config --quiet` for validation.

Before starting the hosted API, create an admin with the CLI after migrations, or provide both strong bootstrap environment values. Startup rejects missing/weak secrets, absent strong active admins, non-HTTPS origins, wildcards and insecure cookies. This applies to hosted public demos too. Local mode rejects external hosts/origins, and still requires a strong session secret; it permits initial CLI account setup before the first admin exists.

The supplied Caddy service obtains/renews certificates, redirects HTTP to HTTPS and sets HSTS (`max-age=31536000`) at the TLS boundary. Configure DNS and host firewall rules as described in the runbook, preserve the certificate volumes, and forward the original Host and Origin for same-origin web/API traffic. API/database ports are not published in hosted Compose. The local development file retains loopback publications; replacing `127.0.0.1` with `0.0.0.0` is not a hosted deployment. Preserve `--no-proxy-headers` unless implementing and reviewing explicit trusted-proxy admission. Actual public DNS and ACME issuance are operator deployment steps; local verification used an internal test issuer.

## Anonymous public demo

Use a dedicated demo database/workspace. In hosted Compose, run the separate `seed` maintenance service before starting the API; the hosted flag is already enabled and the API artifact volume is read-only. Follow the runbook for later reseeding. Outside that deployment, `proofops reset-demo-data --yes` remains an explicit host-operator action; seed before enabling `PROOFOPS_PUBLIC_DEMO=true` and recreate the API. Resets preserve the documented accounting tables/files and all audit history. Workers refuse to claim jobs whenever the public-demo flag is enabled.

The UI opens directly with a viewer role and no sign-in/sign-out or admin controls. All unsafe HTTP methods return 403 regardless of an existing admin session. Only explicitly seeded membership rows, unchanged report/explanation hashes, the supplied replay hashes and original content-addressed exports are eligible for anonymous reading. Normal imported reviews are never included, even if they use synthetic inputs. Without a reset after the auth migration, the public listing is empty. Modified/unmarked results are omitted and their detail/export returns 404.

Anonymous analytics cover only those seeded results. Private guard drafts, billing, dispositions, model accounting, docs and arbitrary future paths are unavailable. Host operators can still manage accounts or reseed with the CLI. Keep the supplied public stack's flag enabled; use the separate full stack for hosted login and writes. In custom deployments, toggling demo mode does not revoke accounts, so previously issued unexpired sessions can resume when that flag is removed.

## Upgrading and rotating credentials

Back up the database and exports, run migrations, generate missing configuration, then create an admin. Existing reviews/results are not rewritten. The new tables hold identities, sessions, login limits and explicit public-demo membership. An old unmarked review does not become public automatically.

`scripts/configure_local.py` preserves an existing database password from `.env` to avoid breaking a populated PostgreSQL volume. It does **not** rotate a previously used development password. Rotate an upgraded local database before hosting it. With the existing database running and native Python dependencies installed:

```sh
.venv/bin/python scripts/rotate_local_database_password.py
docker compose up -d --no-build --pull never --force-recreate db migrate api worker web
```

The rotation command reads only this repository's private `.env`, requires local mode and the loopback `proofops` database/role, and refuses ambiguous, mismatched or symlinked configuration. It generates a replacement without displaying either credential, prepares an owner-only `.env.database-rotation.pending` recovery file, sends a SCRAM verifier rather than a plaintext password in SQL, verifies new authentication and atomically replaces `.env`. Other settings and database contents are preserved. If interrupted, retain both private files and rerun the same command with `--resume`; concurrent edits require private reconciliation. Never paste either file into logs or an issue. Recreating the containers reloads their private environment while retaining database/artifact volumes; existing connections are not revoked by PostgreSQL password rotation alone. The command uses installed images without a download or rebuild, so deploy source changes separately.

For other deployments, use the operator's database credential-rotation procedure or PostgreSQL's interactive `\password proofops` command and update the private application configuration together. Changing only `POSTGRES_PASSWORD` in Compose does not change a stored PostgreSQL role password. A committed credential must be rotated in every deployment that reused it; deleting it from the latest revision is insufficient.

```sh
docker compose exec api proofops users set-password --username workspace-admin
docker compose exec api proofops users disable --username workspace-viewer
```

Both operations revoke that user's sessions. Disabling the last admin makes the next hosted API startup fail until a strong active admin is created by a host operator. Changing `SECRET_KEY` invalidates all sessions and login challenges; deploy that change consistently to all API workers. There is no web password-recovery endpoint. The first admitted attempt in each peer window prunes at most 100 expired sessions and 100 obsolete throttle rows using indexed lookups and skipping locked rows; blocked peers do not trigger cleanup. There is no independent retention scheduler.

## Verification and remaining limits

Run the complete backend and browser checks in [testing](testing.md). They use local PostgreSQL, synthetic accounts and AI-off replays; no cloud/model calls are needed. Browser credentials are generated into ignored, owner-readable `artifacts/private/browser-auth.json`; sessions stay in memory. Traces/videos are disabled because network traces can contain cookies and login bodies. Only the three synthetic result pages are captured into `docs/screenshots/`. Do not upload the entire artifacts directory.

This is a single-workspace demo deployment, not a production security certification. It does not supply tenant or per-review isolation, MFA/SSO, self-service recovery, separate approver duties, an external tamper-evident audit sink, intrusion alerting, distributed edge DoS defense, automated secret management, encrypted backups or a retention/restore program. Known image findings without published Debian fixes remain in [the security review](security_review.md#hosted-demo-image-scan); filtered scan results must not be called clean. A compromised host/database owner or an admin intentionally importing sensitive material remains outside these controls. XSS prevention still matters because malicious same-origin code could act with a browser's session. Review dependencies, operator access and deployment controls before exposing real data.
