# Languages, tools and concepts

A **model** is a remotely hosted learned function that generates an answer from input. An **SDK** is client code that sends requests to that service. A **framework** supplies application structure. A **database** persists/query-controls state. A **cloud service** supplies an external capability such as ECS compute or CloudWatch telemetry. Installing the OpenAI SDK does not configure a model, create access, or establish quality.

## Languages and formats

| Language / format | Actual files and purpose | Concepts to learn |
|---|---|---|
| Python | `backend/`, `scripts/`, `evaluation/`, `tests/`; domain, API, worker and tooling | Functions, modules, typing, exceptions, context managers, Decimal, UTC and tests |
| TypeScript / JavaScript | `frontend/src/`, `tests/e2e/`, `testing/virtual_users.js`; browser UI/automation and k6 | Types, async requests, React state/effects, event handlers and independent response oracles |
| SQL | SQLAlchemy-generated PostgreSQL operations and Alembic migrations | Keys, joins, transactions, row locks, isolation, JSONB and indexes |
| HTML / CSS | `frontend/index.html`, React markup, `frontend/src/styles.css` | Semantic elements, labels, layout, focus, responsive sizing and contrast |
| Terraform HCL | `infra/aws-demo/*.tf`; optional dedicated AWS resources | Providers, resources, variables, plan/apply/state and ownership |
| Rego | `policies/templates/ecs_task_memory_floor.rego`; fixed memory rule | Declarative predicates, input data, deny results, scope and exceptions |
| JSON / JSONL | Typed inputs, rates, manifests, inventories, result exports | Schemas, strict parsing, canonical hashes, null versus zero, newline records |
| YAML | `compose.yaml`, GitHub workflow | Declarative services/jobs, quoting, environment interpolation and trust boundaries |
| Shell / PowerShell | README run commands and CI steps | Working directory, quoting, exit codes, environment variables and process lifetime |

## Why these dependencies exist

FastAPI exposes the typed HTTP API; Uvicorn runs it. Pydantic and JSON Schema reject invalid contracts; pydantic-settings reads environment configuration. React renders UI state; Vite builds assets and TypeScript checks browser interfaces. SQLAlchemy manages database access, psycopg transports PostgreSQL queries, and Alembic tracks schema migrations. PostgreSQL provides real concurrent transactions rather than pretending SQLite has identical locks.

boto3 implements AWS request signing and service APIs. Official OpenAI and Anthropic SDKs implement their different structured-output contracts behind one app interface. HTTPX supports bounded HTTP calls and SDK-boundary mocks. The domain logic remains independent of these provider clients.

Docker/Compose packages local services; uv and npm lock application dependencies. Terraform and its locked AWS provider describe optional isolated cloud scaffolding. GitHub Actions runs the defined offline pipeline. Conftest executes OPA/Rego policies; k6 offers controlled load and preserves latency/error/generator metrics. pytest runs Python tests, Hypothesis supplies meaningful generated input cases, and Playwright drives Chromium through real UI workflows. Ruff checks/formats Python, mypy checks domain types, TypeScript builds the web contract, and Prettier formats browser/workflow source.

ReportLab creates selectable vector/text PDFs; PyMuPDF verifies text, fonts, links and page geometry; Pillow composes rendered-page contact sheets for visual review. These are documentation-only dependencies in the `docs` group. None is required to serve a review.

Actual installed/locked versions and required/optional roles are generated into `docs/software_inventory.json` and the PDF tool table. `uv.lock`, `frontend/package-lock.json`, `.terraform.lock.hcl` and the tool download checksums are authoritative for the corresponding dependencies. Host Node was 25.7.0; the Docker frontend and recommended development setup use Node 22 LTS. The actual host is macOS ARM64; containers run Linux.

LangGraph, Kubernetes, vector databases, a trained router and general multi-cloud discovery are deferred. No code silently depends on them.
