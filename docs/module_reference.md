# Module reference

Python module paths such as `domain/engine.py` are relative to `backend/proofops/`; fixture, frontend, script and documentation paths are relative to the app root. The API, CLI and CI share typed records and the same review function. Evaluation and experiment-runner scripts are explicitly invoked tools excluded from the runtime image; the separate workload fixture is packaged for the optional workload service. Test names below are executable references, not claims about live accounts.

## Contracts and configuration

**Files:** `domain/schemas.py`, `domain/common.py`, `config.py`, `contracts/reports-demo.json`.

Inputs are versioned JSON, environment settings and explicit UTC reference times. Pydantic validates types, record sizes, Decimal amounts, request counts and resource identities. Canonical serialization produces hashes used by reports, cache keys and exports. Outputs are typed records with distinct missing, unknown and zero values. Configuration limits artifacts to the app's artifact directory and prices to `config/`. Invalid records produce field errors rather than a favorable review. Tests: `test_strict_allocation_roundtrip`, `test_unsupported_numbers_stay_unknown`, `test_ambiguous_or_deep_json_is_validation_error`.

## Terraform normalization

**File:** `normalization/terraform.py`.

Inputs are `terraform show -json` bytes, an exact service map, repository and commit identities. The importer selects the mapped ECS task definition, preserves actions/unknown/sensitive paths, validates supported Linux x86_64 CPU/MiB combinations and hashes the non-resize configuration. It extracts only needed facts, then discards the raw plan. Outputs are a `ChangeSet` and explicit normalization findings. Unknown expressions, sensitivity, mixed images, changed application configuration and unsupported deployment shapes prevent a simple resize claim. Nothing in the imported repository is executed. Tests: `test_sensitive_plan_bytes_never_survive_import`, `test_computed_arn_change_is_not_a_workload_change`, `test_container_only_change_has_no_task_compute_saving`.

## Input bundles and replay artifacts

**Files:** `storage/bundles.py`, `storage/artifacts.py`.

Directory/ZIP inputs contain only allowlisted JSON records. Size, filename, duplicate-entry, symlink, expansion, nesting and finite-number checks run before typed validation. Outputs are sanitized content-addressed bundles with schemas, hashes, findings, source versions and the recorded reference time. Downloads use server-assigned artifact IDs. Replay verifies the saved result without AI or refreshing its approval. Historical ZIPs without `versions.json` remain readable; newly exported ZIPs include it. Tests: `test_archive_paths_never_extract`, `test_archive_symlink_duplicate_count_and_expansion_limits`, `test_cli_review_and_replay_share_outcomes`.

## AWS and replay collectors

**File:** `collectors/aws.py`.

The AWS input is a configured identity/scope and normal boto3 credentials. STS verifies the account before bounded ECS, CloudWatch and Logs calls. The collector checks task revision/platform/allocation, redacts bounded log examples and stops pending Logs Insights queries at the call cap. Output preserves collection state and observation provenance. Denied, empty, partial, failed and pending data never silently becomes zero. The replay adapter returns recorded observations without cloud access. The collector is a CLI path; it does not deploy or automatically repair evidence. Tests in `test_aws_collectors.py` use actual SDK Stubber contracts, including account mismatch and query cancellation. Live AWS remains unrun.

## Deterministic review and coverage

**File:** `domain/engine.py`.

Inputs are a validated `ReviewInput` and separately trusted revision. The engine checks identity, applicability, freshness, required sources, cost, workload and memory policy. An applicable known violation wins over missing evidence; otherwise missing evidence, supported passing evidence and unsupported scope map to the other three outcomes. Outputs are immutable findings, coverage and a report core. A model cannot overwrite the outcome. Tests: `test_three_report_paths`, `test_violation_precedes_missing`, `test_collection_states_do_not_become_zero`, `test_empty_stale_and_new_commit`.

## Dated task cost engine

**File:** `domain/costs.py`.

Inputs are matching region/architecture/OS/purchase-option rates and explicit baseline/candidate task-hours. Decimal arithmetic multiplies task-hours by vCPU and GiB rates; percentage is null for a zero baseline. Output identifies covered CPU/memory charges and excluded network, logs, storage, taxes and commitments. Different task-hours are recomputed; missing inputs stay null. Cost per correct request is emitted only when cost and request windows are comparable. Tests: `test_cost_null_zero_and_changed_hours`, `test_container_only_change_has_no_task_compute_saving` and frozen evaluation cost predicates.

## Workload comparator

**File:** `domain/performance.py`.

Inputs are baseline/candidate `WorkloadRun` records and the frozen service contract. The comparator binds image, configuration, profile, dependency, platform, environment and warmup, then checks each run and request class separately. Outputs expose correct/completed/offered counts, latency, failures, restarts and sufficiency. It never averages p95 values. An undersampled run cannot establish capacity; a known failure cannot hide behind a reduced correct count. Tests: `test_smoke_does_not_establish_capacity`, `test_failures_cannot_hide_breach_by_reducing_correct_count`, `test_local_arm_measurements_cannot_validate_x86_contract`, `test_p95_equality_fails_and_no_average`.

## Policy lifecycle and Conftest

**Files:** `policies/guards.py`, `policies/fixtures.py`, `policies/templates/ecs_task_memory_floor.rego`, `policies/approved/reports-demo.json`.

The one supported `ecs_task_memory_floor` specification binds exact service/workload scope, approved bound, incident/repair references, owner, reviewer, expiry and template hash. Drafting preserves those facts and leaves the state as draft. Fixture validation uses the fixed template and ten generated cases. Export checks the exact validated proposal, template and fixture hashes. Source-control review outside the app is required for activation. New commits/images/contracts or expired exceptions invalidate applicability. Tests: `test_actual_rego_fixture_suite`, `test_always_deny_fails_healthy_fixtures`, `test_trusted_policy_cannot_be_weakened_by_input`, `test_guard_draft_validation_export_and_tamper_rejection`.

## Model context and explanation validation

**Files:** `models/context.py`, `models/explanations.py`, `models/development/`.

Inputs are already-computed report facts, bounded evidence summaries and curated development cards/examples. Compact and bounded-flat variants serialize the same evidence facts and record omissions. Outputs are prompts and a strict explanation contract. Validation checks exact evidence IDs, finding codes, numeric facts and next step; it rejects unknown fields. Retrieval never reads evaluator labels or fault-bearing benchmark paths. Quoted log text grants no authority. These mechanical checks do not establish causal truth. Tests: `test_model_cannot_change_facts_or_action`, `test_injected_log_instructions_get_no_authority_or_label_access`, `test_valid_citations_do_not_validate_causal_inference`.

## Provider adapters and bounded router

**Files:** `models/adapters.py`, `models/router.py`, `config/model_prices.json`.

Adapters translate the shared request into OpenAI Responses or Anthropic Messages using official SDKs, closed schemas, explicit output limits and no tools. They normalize completion, refusal, truncation, quota, throttle, timeout and usage. The router first handles scope/missing-evidence/template cases, then permits at most two attempts with an overall task deadline. Permanent failures do not loop; transient retry uses the same two-attempt allowance. A routed mechanical failure can use the configured strong slot. Confidence never controls acceptance. Both providers failing leaves the deterministic report and a visible AI-unavailable state. Tests in `test_provider_adapters.py` exercise SDK HTTP boundaries; `test_routing_bounded_attempts_cache_and_scope`, `test_transient_retry_consumes_the_second_attempt` and `test_both_provider_results_unusable_preserves_deterministic_guard` use PostgreSQL.

## Budget ledger and accepted-output cache

**File:** `models/budget.py`; cache integration in `models/router.py`.

Inputs include positive overall/per-task limits, exact model/capability prices and a stable task identity. PostgreSQL transactions reserve conservative planned cost before dispatch and reconcile reported uncached/cache-read/cache-write/output usage afterward. Timeouts/crashes keep ambiguous amounts pending. Restarting does not reset spend. Actual cost exceeding a reservation is recorded, not concealed. Cache identity includes scope, inputs, policy, time basis, mode, prompt/schema, provider/model and price version; only complete validated outputs are cached for five minutes, retaining original usage. Tests: `test_atomic_budget_reservations_and_duplicate_dispatch`, `test_same_reservation_key_cannot_double_spend`, `test_nonretryable_and_uncertain_attempts`.

## PostgreSQL repository and migrations

**Files:** `storage/database.py`, `storage/repository.py`, `migrations/`.

SQLAlchemy maps normalized records and bounded JSONB data to PostgreSQL. Alembic creates/version-controls tables for jobs, reports, revisions, artifacts, outcomes, attempts, budgets, cache, billing and audit. Idempotent requests bind body and scope; conflicting reuse fails. Connection/pool/statement/lock timeouts bound operations. Tests run on `proofops_test`, never the operator database. Tests: `test_api_worker_report_and_download`, `test_same_reservation_key_cannot_double_spend`, `test_job_claims_and_expired_lease_recovery`.

## Persisted worker

**File:** `workers/runner.py`.

The worker claims a queued or expired job with `FOR UPDATE SKIP LOCKED`, renews its lease, runs bounded stages and persists the deterministic result before optional prose. A maximum claim count prevents endless recovery. Reclaiming a dispatched model attempt preserves uncertain charges and never blindly redispatches it. Outputs are persisted stage, report/artifact IDs and sanitized errors. Tests: `test_job_claims_and_expired_lease_recovery`, `test_worker_crash_after_dispatch_keeps_charge_pending_and_does_not_retry`.

## API and command line

**Files:** `api/app.py`, `cli.py`, `domain/summaries.py`.

FastAPI handles imports, review creation/list/detail, bundle downloads, draft/validate/export, outcomes and billing analytics. `proofops.auth` owns Argon2id identities, server sessions and persistent login limits; `api/auth.py` applies default-deny authentication, admin write restrictions and CSRF to every route. Health is public; readiness and docs require authentication. Request byte caps, exact host/origin checks and typed IDs bound the interface. The CLI exposes host-operator `users create/set-password/disable`, `reset-demo-data`, `review`, `replay`, `guards test`, `collect`, `ingest-costs` and explicit `evaluate`; review summaries share the engine's outcomes and exit codes. Evaluation launches a separate program rather than adding labels to runtime imports. Tests include the complete endpoint/role matrix in `test_auth.py`, `test_public_demo.py`, `test_origins_paths_validation_and_unknown_ids`, `test_cli_evaluator_paths_rejected_without_reading` and `test_cli_trusted_map_cannot_be_changed_by_input`.

## UI and analytics

**Files:** `frontend/src/main.tsx` mounts the app; `App.tsx` composes routes and actions; `hooks/useWorkspace.ts` owns requests, polling and workspace/form state. `features/reviews/`, `features/review/` and `features/outcomes/` contain the three views; `components/` and `lib/` provide shared presentation, formatting and outcome labels. `api.ts`, `types.ts`, `styles.css` and backend `storage/analytics.py` retain their focused roles.

React renders persisted reviews, evidence detail and outcomes. Users can compare costs/coverage/classes, inspect citations and attempt accounting, export a validated draft, detect changed-commit applicability and record a disposition. Stale responses cannot replace newly selected detail. Save success is shown only after the API succeeds; unavailable analytics stays unavailable. FOCUS ingestion preserves Decimal values, negative credits, nulls, currencies and row position; repeated file imports are idempotent. The sample is never attributed to the demo service's invoice. Tests: browser scenarios in `tests/e2e/reviews.spec.ts`, `test_focus_ingestion_is_idempotent_and_reconciles`, `test_billing_endpoint_and_mixed_currency_null_duplicate_rows`.

The reviews page includes a short workflow guide and puts the replay form before history on narrow screens. Shared state panels distinguish loading, empty and unavailable data; retry controls reload saved data. Wide report tables support keyboard scrolling. `tests/e2e/ui-states.spec.ts` covers loading/error recovery, empty analytics, setup persistence and late-response protection alongside the real replay workflows.

## Workload fixture and experiment runner

**Files:** `demo/reporting_api/server.py`, `testing/virtual_users.js`, `scripts/run_workload.py`.

The separate HTTP service sums bounded integer-cent items. k6 supplies an independent oracle and an open arrival-rate schedule with small/medium/large classes. The runner starts only labelled, cgroup-limited local containers, performs warmup, captures Docker state, freezes calibration and alternates three comparison pairs. A deliberately oversized startup allocation tests actual OOM and repair; pressure is opt-in. It preserves native summaries, logs, hashes and terminal states. These local Linux ARM64 measurements cannot validate the AWS x86_64 contract. See the recorded workload table and commands in `docs/testing.md`.

## Evaluation, CI, infrastructure and documentation

**Files:** `evaluation/`, `.github/workflows/offline.yml`, `scripts/ci_review.py`, `infra/aws-demo/`, `scripts/build_docs.py`, `scripts/validate_docs.py`.

The frozen 60-case evaluator keeps labels outside prompts, scores deterministic/explanation/guard tasks separately and marks unavailable provider work unrun. Rescoring saved outputs binds independent annotations to input and output without another call. CI runs offline tests and a recurrence example using base-revision code/policy/map against bounded candidate data; production enforcement still needs protected workflow settings. Optional Terraform validates dedicated, zero-task AWS scaffolding but was not deployed. Documentation builds embedded-font searchable PDFs from Markdown, inventories and saved results; validation renders every page and checks text, fonts and links. Tests: `test_frozen_split_has_no_group_leakage`, `test_replay_rescore_keeps_outputs_and_never_calls_a_provider`, local CI regression, Terraform validate, and the PDF validation artifact.
