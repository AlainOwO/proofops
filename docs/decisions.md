# Implementation decisions

## D001 — Research remains read-only; application owns its repository

The user's current instruction overrides the brief's Windows sibling-directory example. Build inside `proofops-app/` on macOS, use configurable paths, and initialize a nested standalone Git repository. No research generation scripts are run in their source directory. Attribution accompanies copied fixtures.

## D002 — Flagged document differences

The blueprint's day-4 exit condition requires real provider responses; BUILD sections 1, 10 and 15 explicitly permit local/mocked verification with live checks unrun until prerequisites exist. Implement both genuine adapters and distinguish mocked, replay and live results. The research findings call the UI optional; BUILD requires three views, so all three are in scope. The user was told these differences before authorizing the build.

## D003 — Review contracts and legacy fixtures

Use BUILD's canonical four outcomes. Migrate the development vocabulary explicitly: `reject -> revise_change`, `needs_evidence -> collect_evidence`, `eligible_for_review -> request_review`. No model call for out-of-scope reviews. Preserve applicable original finding codes in migrated examples; the engine uses versioned canonical codes.

## D004 — Local trust and data boundary

Bind public-facing development ports to loopback, allow only configured local origins and use server-assigned artifact IDs. Bundle policy claims cannot replace the server's trusted contract/policy revision. Runtime has no research or evaluator path setting. Evaluation labels and manifests are not mounted into runtime containers. Raw RCAEval index fields and fault-bearing paths are label sources too, so exclude them from model inputs.

## D005 — Measurements and optional live work

Default to synthetic replay and AI off. Linux x86_64 is the initial reviewed Fargate architecture; local arm64/Docker measurements remain local observations and cannot establish AWS thresholds. Use exact image/config/profile/dependency hashes and compare only declared resize changes. Record failed/unavailable live, pressure or human tests honestly. No deployment, repository publication, PR message or paid call is implied by local setup.
