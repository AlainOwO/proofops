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
| Session, readiness, replays, list/detail, downloads, analytics, API docs | 401 | Allowed | Allowed |
| `POST /api/v1/auth/logout` | 401 | Session CSRF required | Session CSRF required |
| Import bundle, run review, create/validate guard draft | 401 | 403 | Session CSRF required |
| Record disposition, import billing sample, reset demo reviews | 401 | 403 | Session CSRF required |
| Future HTTP routes | Auth required | Safe reads only | Writes also require CSRF |

An outer authentication boundary protects routes even if a new handler omits a dependency. Only health and login are explicitly public in ordinary mode. Configured CORS preflights negotiate access without running an API handler. Tests enumerate every registered route and method, including framework docs/HEAD routes; adding an endpoint requires updating its role matrix. The frontend hides admin controls, but the API remains authoritative.

Reset through `POST /api/v1/admin/reset-demo-data` additionally needs `{"confirm": true}`. The existing local-database restriction and running-job protection still apply. The CLI reset remains an explicit host-operator action; a web viewer cannot invoke it. Users and sessions survive resets.

## Sessions, CSRF and brute-force limits

- Argon2id hashes use 64 MiB memory, three iterations, parallelism two and random salts. Password rotation/disabling revokes all of the user's sessions. Roles and active status are checked in storage on each request.
- A random opaque session token is carried only in an HttpOnly, SameSite=Lax, host-only cookie with Path=/, expiry and Max-Age. PostgreSQL stores a keyed digest, not the cookie value. Secure cookies use the `__Host-` prefix. The default absolute lifetime is eight hours; `SESSION_TTL_SECONDS` accepts 60–86,400 seconds. Login rotates the browser's prior session; logout revokes it. There is no sliding refresh.
- `GET /api/v1/auth/login` returns a CSRF token and sets a signed HttpOnly challenge cookie valid for ten minutes. Login must send both the cookie and `X-CSRF-Token`. After login, `GET /api/v1/auth/session` returns the session's CSRF token. Every subsequent unsafe request, including logout, must send it. Tokens are bound to the session; a different session's token is rejected. The frontend holds the CSRF token in memory and stores no bearer credentials in localStorage.
- Requests with an unconfigured Origin are rejected. CORS allows exact configured origins with credentials; wildcards are rejected at startup. CSRF validation also protects requests that omit Origin. Allow only origins controlled by the operator, and keep browser/API traffic under the same origin through the web proxy.
- PostgreSQL persists per-account failure counts and per-connection-peer attempts across restarts/workers. Defaults are five failed attempts per account and 60 attempts per peer per 15-minute window, with a 15-minute lockout when a limit is reached. Unknown and known users receive the same credential errors and throttling responses; unknown users still incur an Argon2 verification. Blocked responses include `Retry-After`. Limits are bounded configuration, not an in-memory per-process counter.
- The supplied Uvicorn commands disable proxy-header trust. Forged `X-Forwarded-For` headers cannot choose a new limiter identity. Behind Nginx or a TLS proxy, users share the proxy peer bucket; account limits still apply. A reviewed edge limiter can add real-client protections. Do not simply trust arbitrary forwarded headers to increase capacity.

API responses are marked `Cache-Control: no-store`. Backend errors do not return password inputs or raw database exceptions. Frontend 401 responses unmount cached workspace data, 403 responses show the server error and refresh identity, and absolute expiry returns to sign-in. Downloads use the same error handling. In-progress requests that completed before revocation are not retroactively cancelled.

## Hosted configuration

Use the built frontend and a TLS reverse proxy; the Vite development server is not a public web server. Configure private environment values before startup:

```dotenv
PROOFOPS_MODE=hosted
SECRET_KEY=<random value generated privately; at least 32 characters>
SESSION_COOKIE_SECURE=true
ALLOWED_HOSTS=reviews.example.com
CORS_ORIGINS=https://reviews.example.com
PROOFOPS_PUBLIC_DEMO=false
```

These are placeholders, not usable secrets. `SECRET_KEY` needs at least 16 distinct characters and rejects common placeholders. The local setup script generates a stronger random value suitable for reuse on a single deployment. Configure a strong database password as well; the supplied Compose URL interpolation expects URL-safe characters, as produced by the setup script. Do not commit the filled environment or print `docker compose config` into shared logs.

Before starting the hosted API, create an admin with the CLI after migrations, or provide both strong bootstrap environment values. Startup rejects missing/weak secrets, absent strong active admins, non-HTTPS origins, wildcards and insecure cookies. This applies to hosted public demos too. Local mode rejects external hosts/origins, and still requires a strong session secret; it permits initial CLI account setup before the first admin exists.

Terminate HTTPS at an operator-managed proxy, forward the original Host and Origin, and proxy the web app and API under the same origin. Keep published API/PostgreSQL ports on loopback or a private network. The default Compose bindings remain `127.0.0.1`; do not expose them merely by replacing that address with `0.0.0.0`. Preserve `--no-proxy-headers` unless implementing and reviewing an explicit trusted-proxy policy. The repository does not provision certificates, DNS, a public listener or HSTS for your domain.

## Anonymous public demo

1. Use a dedicated demo database/workspace when possible. `proofops reset-demo-data --yes` replaces saved review data, preserving the documented unrelated accounting tables and files.
2. Run the reset before enabling public mode:

   ```sh
   docker compose exec -T api proofops reset-demo-data --yes
   ```

3. Set `PROOFOPS_PUBLIC_DEMO=true` in the private environment and recreate the API with `docker compose up -d --force-recreate api`. Stop the worker for a dedicated read-only presentation if it is no longer needed.

The UI opens directly with a viewer role and no sign-in/sign-out or admin controls. All unsafe HTTP methods return 403 regardless of an existing admin session. Only explicitly seeded membership rows, unchanged report/explanation hashes, the supplied replay hashes and original content-addressed exports are eligible for anonymous reading. Normal imported reviews are never included, even if they use synthetic inputs. Without a reset after the auth migration, the public listing is empty. Modified/unmarked results are omitted and their detail/export returns 404.

Anonymous analytics cover only those seeded results. Private guard drafts, billing, dispositions, model accounting, docs and arbitrary future paths are unavailable. Host operators can still manage accounts or reseed with the CLI. To restore login, unset the flag and recreate the API; existing unexpired sessions may resume because toggling demo mode does not revoke accounts.

## Upgrading and rotating credentials

Back up the database and exports, run migrations, generate missing configuration, then create an admin. Existing reviews/results are not rewritten. The new tables hold identities, sessions, login limits and explicit public-demo membership. An old unmarked review does not become public automatically.

`scripts/configure_local.py` preserves an existing database password from `.env` to avoid breaking a populated PostgreSQL volume. It does **not** rotate a previously used development password. Before hosting an upgraded database, rotate its role password with PostgreSQL's interactive `\password proofops` command and update private `POSTGRES_PASSWORD`/`DATABASE_URL` values together. Changing only `POSTGRES_PASSWORD` in Compose does not change a stored PostgreSQL role password.

```sh
docker compose exec api proofops users set-password --username workspace-admin
docker compose exec api proofops users disable --username workspace-viewer
```

Both operations revoke that user's sessions. Disabling the last admin makes the next hosted API startup fail until a strong active admin is created by a host operator. Changing `SECRET_KEY` invalidates all sessions and login challenges; deploy that change consistently to all API workers. There is no web password-recovery endpoint. Expired sessions and obsolete throttle rows are pruned during login; there is no independent retention scheduler.

## Verification and remaining limits

Run the complete backend and browser checks in [testing](testing.md). They use local PostgreSQL, synthetic accounts and AI-off replays; no cloud/model calls are needed. Browser credentials are generated into ignored, owner-readable `artifacts/private/browser-auth.json`; sessions stay in memory. Traces/videos are disabled because network traces can contain cookies and login bodies. Only the three synthetic result pages are captured into `docs/screenshots/`. Do not upload the entire artifacts directory.

This is a basic single-workspace auth system, not a production security certification. It does not supply tenant or per-review access isolation, MFA/SSO, self-service recovery, separate approver duties, complete tamper-evident authentication auditing, intrusion alerting, a distributed edge DoS defense, automated secret management, encrypted database/backups, restore testing, retention policy or a TLS deployment. A compromised application host/database or an admin intentionally importing sensitive material remains outside these controls. XSS prevention still matters because malicious same-origin code could act with a browser's session. Review your deployment, dependencies, trusted origins and operator access before exposing real data.
