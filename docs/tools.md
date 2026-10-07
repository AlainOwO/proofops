# Optional tools and normalized inputs

The deterministic engine consumes versioned `ReviewInput` records. Tools collect
or normalize data before a review; model explanations run after it. No tool can
authorize deployment or activate a guard. The API routes and frontend workflow
are unchanged.

`backend/proofops/tools/interfaces.py` defines small `EvidenceProvider`,
`PricingProvider` and `SearchProvider` protocols. The CLI uses the AWS/replay
evidence implementations and the bounded `FileRateCardProvider`. A pricing
snapshot contains the existing typed rate card and its exact content hash.
Region, resource platform, source, price/retrieval timestamps, billable dimensions
and assumptions remain explicit. `domain/costs.py` still computes Decimal amounts
and coverage from normalized rates and task-hours. No online pricing dependency
is introduced. Forecasts, workload observations and realized billing remain
separate; a task-cost estimate is never a realized saving.

The existing Terraform importer, fixed Conftest guard tool, isolated workload
runner and AI adapters already have bounded interfaces. They are retained; no
generic command executor, agent framework or dynamic tool registry is added.

## Optional public research

Research is an operator CLI command, disabled by default. It is not called by the
API, worker, deterministic engine or model adapters. It produces a new mode-0600
JSON artifact containing attributed, **untrusted** plain text, with source URLs,
provider, collection/retrieval timestamps and cache expiry. Standard output shows
only status, source count and cache state. Existing files are never overwritten.

```sh
# Safe with the default SEARCH_PROVIDER=off: writes a labelled disabled result.
.venv/bin/proofops research --query 'public ECS Fargate documentation' \
  --output artifacts/research-disabled.json
```

To explicitly enable the first provider in a suitable native/operator environment,
set `SEARCH_PROVIDER=google`, `SEARCH_API_KEY` and `SEARCH_ENGINE_ID` in private
server configuration. Supply a Google-compatible Custom Search key and configured
engine; account eligibility, quota and any charges are the operator's
responsibility. No live provider request or account validation was performed in
this change. The HTTP contract is tested with mocks. Do not search for secrets or
private evidence: the explicit query is sent to the configured provider.

| Variable | Default and limits |
|---|---|
| `SEARCH_PROVIDER` | `off`; implemented provider `google` |
| `SEARCH_API_KEY` | Empty secret; server/operator only |
| `SEARCH_ENGINE_ID` | Empty; required alongside the key |
| `SEARCH_TIMEOUT_SECONDS` | 5; positive, at most 20 seconds; total async provider deadline |
| `SEARCH_MAX_RESULTS` | 5; 1–10 |
| `SEARCH_CACHE_TTL_SECONDS` | 300; 0 disables caching, maximum 3,600 |

Missing configuration makes the optional tool explicitly `not_configured` and
performs no request. Timeout, malformed responses, transport/provider failures
and size violations return `unavailable`, with fixed error codes and no provider
body. An empty successful search is `empty`. Safe repeated complete/empty results
can reuse the bounded PostgreSQL observation cache. Keys include the exact trimmed
query, result limit, provider/parser version and credential/engine configuration
digest. Original collection times are retained; failures are never cached.

The Google adapter uses the fixed HTTPS endpoint
`www.googleapis.com/customsearch/v1`, sends its key in `X-Goog-Api-Key`, disables
redirects and environment proxies, requests uncompressed JSON and caps responses
at 256 KiB. It accepts at most ten sources, 300-character titles, 2,000-character
snippets and 8,000-character optional content per source. The first adapter
returns snippets; it **does not fetch result URLs**. A future implementation may
supply bounded content through the protocol, after the same validation.

Source URLs require HTTP(S) without user information; executable URL schemes are
rejected. Text can still contain misleading claims, markup or hostile
instructions. It remains data in JSON, is never rendered as HTML or executed,
and is never inserted into model instructions, SQL, shell commands, filesystem
paths or authorization decisions. Do not treat attribution or schema validation
as proof that a source is correct.

Both supplied hosted stacks explicitly set research off, have no research keys
and retain internal-only runtime networking. Enabling a native optional tool does
not add hosted egress, an API endpoint or a frontend control. No Redis/new service
is needed: the existing database provides the small disposable cache, and the
existing worker/budget/session mechanisms remain authoritative.
