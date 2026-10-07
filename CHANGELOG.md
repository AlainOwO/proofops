# Changelog

## Repository optimization and full-host integration — 2026-10-07

- Added the adjacent full hosted workspace behind the public stack's shared
  Caddy, with independent private credentials/database/volumes, bcrypt Basic
  Auth, application login, a default worker and restricted runtime DB roles.
  Public writes remain forbidden; only Caddy publishes hosted ports. The
  operations runbook covers both stacks, stdin account creation, seeding and
  backups; MFA, tenant isolation and SR-05 limitations remain explicit.
- Repaired expired AI cache replacement and coordinated identical dispatches;
  added scoped TTL observation caching while preserving original AWS timestamps.
  Reduced report document reads without changing API response fields or any
  deterministic outcomes. Existing cheap-first routing and budgets remain.
- Added optional bounded research and normalized tool/pricing interfaces,
  configurable worker slots/idle backoff, private JSON operation counters and
  hosted workload-runner safeguards. Search is disabled by default, remains
  untrusted context and never determines an approval. No new service or UI change.
- Verification: 517 backend tests, 37 container/shared-HTTPS checks, 16 standalone
  public checks, 22 hosted and 20 local browser tests, three screenshot checks,
  builds, lint/typechecking, ten guard fixtures and 60/60 replay decisions passed.
  No tests were skipped or weakened and no live AWS/model/search calls were made.
  Existing local workspace data and all original research files were preserved.
- Offline repeated-call/read reductions, migration/rollback instructions, exact
  test commands and remaining limitations are in [CHANGES.md](CHANGES.md).
  No production latency, CPU/RAM, provider-cost or realized savings improvement
  is claimed. The earlier Trivy counts below describe the 2026-10-06 images;
  rebuilt 2026-10-07 API/worker/web images were not rescanned.

## Hosted public demo hardening — 2026-10-06

- Added authentication/authorization before protected body reads, absolute read deadlines, bounded concurrent/peer/principal admission and buffered payload quotas. Import parsing/storage runs off the event loop. Hosted docs/OpenAPI are disabled; API and proxy security headers cover rejection/error paths.
- Preserved authenticated actors through imports, reviews/workers, billing and resets; added ID/status-only authentication/account audit events. Hosted PostgreSQL now separates bootstrap, migration owner and restricted runtime roles, with startup privilege checks and append-only runtime audit access.
- Added standalone `compose.hosted.yaml`, private setup and a [Hosted public demo runbook](docs/operations.md#hosted-public-demo). Caddy provides automatic HTTPS/HSTS and is the only service publishing ports (80/443); internal API/worker run AI-off/read-only with restricted credentials and container limits. nginx runs unprivileged, and its build context excludes private environment/credential files.
- Revalidated requested digest pins, upgraded final-stage OS packages and rebuilt images without cache with pulls. Hosted PostgreSQL advances to 18.6 in a separate volume; local PostgreSQL stays on 17.11. Patched nginx packages and replaced the stale PostgreSQL gosu helper while preserving tested volume initialization. Trivy found zero fixable HIGH/CRITICAL records in six final images, but **API and worker each retain 53 HIGH and 2 CRITICAL records without a published Debian fix**. This is not a clean scan; exact IDs, vendor statuses and counts are in [the security review](docs/security_review.md#hosted-demo-image-scan).
- Verification: 426 backend tests, frontend build, 20 Chromium e2e tests, three screenshot-script checks, three built-image container checks and 16 local HTTPS proxy checks passed, with no skipped/weakened tests. Ruff and mypy passed. Review logic/scoring/evaluator data and tracked screenshots are unchanged; the existing local workspace was preserved. No public deployment, public ACME or live AWS/model calls are claimed.

## Workspace authentication and authorization — 2026-10-06

- Added Argon2id user credentials, revocable expiring server sessions, login/logout, persistent account/peer login limits, and a default-deny API authentication boundary. Every write requires an admin and CSRF validation, except that viewers may log out of their own session. Health and the CSRF-protected login flow are the only public routes in ordinary mode; readiness and API documentation require a session.
- Added CLI user creation, password rotation and disabling, with optional environment bootstrap. There are no default user passwords. API startup requires a strong `SECRET_KEY`; hosted mode also requires a strong active admin, Secure cookies and explicit HTTPS origins/hosts. Session cookies are HttpOnly, SameSite=Lax, host-only and gain the `__Host-` prefix when Secure.
- Public demo mode is an explicit exception: anonymous viewers can read only the three unchanged results marked by the demo reset. Imports cannot publish themselves by claiming a synthetic origin. All HTTP writes return 403, including login/logout; workspace billing, dispositions, guard drafts and model accounting are withheld.
- Added a login page, protected workspace, role badges and logout. Viewer sessions hide imports, review submission, guard writes, billing imports and disposition controls; authenticated downloads also handle 401/403. Session expiry clears the workspace, and denied writes refresh the current role. The projected-compute eligibility display and all three review scenarios remain unchanged.
- Browser verification: frontend build and all 20 Playwright tests passed, preserving the original 12 tests and adding eight authentication/presentation checks. Browser accounts use generated synthetic credentials, cookie state stays in memory, and traces/videos are disabled to avoid credential capture.
- Added placeholder-only configuration, private local secret generation, CLI/hosted/demo setup documentation and ephemeral CI credentials. Docker/native Uvicorn disables proxy-header trust; all supplied service bindings stay on loopback. Existing database passwords are preserved during setup and must be rotated separately before hosting. No live model/AWS calls or new paid services were used.
- Assumptions: one shared workspace, with all authenticated users able to read its reviews and results; host/CLI operators remain trusted database administrators. Admin access permits advisory operations, not deployment or policy activation. Existing review logic, scoring, findings, fixture/evaluator data and research files are unchanged. Reset preserves users and sessions. Anonymous demo access requires reseeding after this migration.
- Backend verification: all 310 unit, policy and integration tests passed against local PostgreSQL with approved access, including every route/method for anonymous, viewer and admin, all write CSRF checks, session revocation, concurrent throttling, demo isolation and safe local configuration. Backend typing, lint and formatting checks passed; the existing upstream TestClient deprecation warning remains. Compose/workflow YAML and documentation file links were also checked; no remote CI or public TLS deployment is claimed.
- Regenerated all three `docs/screenshots/` PNGs with the existing `npm run screenshots:demo` script after the final e2e run and demo reset. All three capture checks passed; visual inspection confirmed synthetic fixture content and generic role labels without keys or personal data. PNG metadata is empty. The local workspace is left with exactly three completed AI-off seeded results.

## Review projection eligibility — 2026-10-05

- On review detail pages, `revise_change` labels the projected compute difference “Not eligible: resolve findings first”; `collect_evidence` uses “Not eligible: evidence incomplete”. Both cards use neutral greys and a smaller projected amount, keeping the difference, percentage, baseline and candidate estimates visible. `request_review` retains its existing appearance.
- Extended the existing three Playwright replay scenarios to check the exact estimates, percentage, eligibility label, colours and projected amount size on desktop and at 390 px. The ready scenario explicitly retains its green styling and existing desktop/mobile type sizes; imports, worker execution, evidence inspection and downloads remain covered.
- Assumptions: eligibility copy follows the saved review outcome; it does not re-evaluate findings or current applicability. Existing number formatting, cost arithmetic, review logic, scoring, findings and backend results remain unchanged. Validation and screenshots use local synthetic replays with template explanations and no live AWS/model calls; research files and evaluator data are outside the change.
- Regenerated all three `docs/screenshots/` PNGs with the existing `npm run screenshots:demo` script after resetting the local demo. The ready screenshot is byte-for-byte identical to its previous version; only the two ineligible screenshots have changed. Visual inspection confirmed synthetic fixture content and generic workspace labels with no keys or personal data; all three PNGs have no metadata.
- Verification: all 123 backend tests, the native frontend build, Docker web build, 12 Playwright e2e tests and three screenshot captures passed. Database and browser checks ran outside the sandbox with approved local service access. The existing upstream TestClient deprecation warning remains. The local app is left with exactly three completed, AI-off demo reviews.

## Presentation-ready demo — 2026-10-05

- Added `proofops reset-demo-data` with default-no confirmation and `--yes`. It atomically replaces saved reviews and their drafts, dispositions and imported bundle records with exactly the three supplied replay scenarios. The shared review engine, recorded evidence time, template explanation and export format determine every result; the reset never invokes a model or AWS collector.
- Limited reset to the local application/test PostgreSQL databases and explicit review tables, with concurrency checks and rollback on failure. Preserved billing, trusted contracts/revisions, budgets, reservations, ledgers, caches, audit history and pre-existing files. Model attempts linked to deleted reviews retain their accounting with only the review foreign key detached; unrelated attempts are unchanged. No evaluation, research or evaluator directories are read or cleared by reset.
- Assumptions: this remains a local, single-service demo using the existing synthetic fixtures and approved policy. Reset removes all saved reviews, including failed/queued jobs and manually imported review inputs; let running reviews finish first. Export archives remain on disk, including any created before a failed database transaction. No review rules, outcomes, costs, fixtures or research files change.
- Added 29 reset tests covering confirmation/EOF/interruption, protected database/path boundaries, linked-record cleanup, accounting/file preservation, repeated reset, exact engine-result parity, downloadable replay, running/concurrent jobs and rollback. All 29 passed against the dedicated PostgreSQL test database; the existing upstream TestClient deprecation warning remains.
- Added a five-step Docker quick demo at the top of README, using this repository's configured clone URL and a one-command reset shortcut. Added a separate screenshot capture command using the existing Playwright configuration; it reads only the three seeded fixture results, verifies their input hashes/template mode, and leaves the demo at exactly three reviews.
- Saved and embedded full-page PNGs for valid resize, unsafe resize and incomplete evidence under `docs/screenshots/`. All three were visually inspected: only synthetic fixture content and generic local-workspace labels appear, with no keys, personal data or PNG metadata.
- Verification: all 123 backend tests, the native frontend build, Docker API/worker/web rebuild/startup, 12 e2e tests and three screenshot captures passed. Ruff, mypy and changed-file formatting checks passed. Reset was exercised in the API container after e2e, leaving exactly three completed reviews at `http://127.0.0.1:5173`. No live AWS/model calls were made; source fixtures, evaluation/research data and published PDFs were unchanged. Current check records are listed in `IMPLEMENTATION_STATUS.md`.

## UI polish — 2026-10-05

- Split the frontend entry point into an app shell, reviews/report/outcomes components, a workspace hook, and shared presentation helpers. The extraction preserves markup, API requests, hash routes, polling, form state and displayed review results.
- Added explicit loading, empty, filtered and unavailable states, accurate backend status, and retry controls that reload saved data without submitting another review. Added a short “How this works” panel, mobile review cards and form-first ordering, visible focus, a skip link, and keyboard-accessible scrolling for wide tables.
- Extended browser coverage for all three report paths on narrow screens, 320/390/768 px reviews layouts, unavailable/empty analytics, retry polling, filter/setup persistence and stale response protection. The frontend build now includes the actual browser-test directory in TypeScript checks.
- Assumptions: keep the existing local, single-service workflow and visual identity; use the supplied synthetic replays with recorded evaluation time and AI off. Review rules, outcomes, cost arithmetic, approved constraints and evidence requirements remain unchanged. Research files and evaluator data are outside this work; test outputs stay in ignored application artifacts.
- Verification: 94 backend tests and 12 Chromium tests passed; native TypeScript/Vite and Docker frontend builds passed. Browser checks ran against the rebuilt local web container, with screenshots inspected on desktop and narrow layouts. Formatting and unused-symbol checks passed. No live AWS or model calls were made; the existing upstream TestClient deprecation warning remains.
- Added a README walkthrough for valid resize, unsafe resize and incomplete evidence, with expected results and inspection steps. Updated the module reference and implementation status to document the component boundaries and this verification run; historical workload/evaluation results and PDFs were preserved.

## 0.1.0 — 2026-10-05

- Built a local Python/PostgreSQL/React application, persisted worker, shared CLI/CI review engine and three labelled replay paths. Added dated Decimal task-cost estimates, comparable workload checks, scoped Rego guards, draft validation/export, operator outcomes and idempotent FOCUS analytics.
- Implemented bounded AWS collectors and genuine OpenAI/Anthropic structured-output adapters, with explicit completion/failure states, a two-attempt router, atomic reservations, usage accounting and scoped accepted-output caching. Live integrations and model quality experiments remain unrun.
- Added a frozen 60-case/20-group evaluator, separate mechanical/semantic/guard scoring, split-specific denominators, explicit unrun provider results and input/output-bound rescoring that does not repeat paid calls.
- Recorded real local smoke/calibration/load and bounded OOM/repair experiments. Preserved native summaries and per-class results, froze thresholds before candidates and added separate experiment series to protect existing evidence.
- Added trusted-base CI examples, pinned action revisions and container base digests, validated optional zero-task AWS scaffolding, setup/operations/module/model/testing/learning references and reproducible searchable PDF tooling.

## Bug and security review improvements

- Reject duplicate/deep/non-finite JSON and oversized, duplicate, linked, encrypted or traversing ZIP entries; extract only supported plan facts and discard raw sensitive values. Bound configured rate-file reads and prevent any runtime path into evaluator/research data.
- Preserve an applicable known violation when failures reduce correct-request counts; do not average p95 or compare different architectures, images, populations, windows or dependency states. Keep missing costs and unavailable analytics distinct from zero.
- Require the exact trusted Rego template hash; validate and export the same proposal/spec/template/fixtures. Candidate policy or scope-map changes cannot replace the trusted revision. Replayed historical approval does not become current applicability.
- Retain uncertain charges after a dispatch/crash/timeout, use consistent lock ordering and idempotent attempt keys, and prevent duplicate redispatch or restart-based budget resets. Separate same-model retries from escalation statistics.
- Stop pending Logs Insights queries at the call cap; preserve denied/empty/pending states and redact log examples. No imported plan/repository code or model-supplied tool instruction is executed.
- Handle oversized model context without changing deterministic results. Reject invented citations/numeric facts mechanically; label valid-schema but unsupported causal/confident prose separately through independent semantic scoring.
- Prevent stale UI responses from replacing the selected review, show save success only after persistence, and display model-attempt latency/unit-cost limitations. Use loopback services, allowed hosts/origins, bounded request bodies and non-root API/worker containers.
- Verify exact selected rate hashes, with an empty-by-default environment override and explicit CLI flag precedence. Preserve original billing row identity, negative credits, null values and currencies.

This is a reviewed local demonstration, not a production security certification. Team identity/authorization, retention, protected deployment workflows and live account validation remain outside the implemented local scope.
