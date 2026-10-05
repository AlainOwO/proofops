# ProofOps

ProofOps reviews a proposed ECS Fargate cost change against a versioned operating contract. It combines a sanitized Terraform plan, dated task CPU/memory estimates, workload evidence and one scoped memory guard. Code determines the result; optional AI explains it and proposes a constrained guard draft.

The local workflow works without AWS credentials or API keys. The supplied reviews use **synthetic evidence, rates and approvals**. Local Docker load measurements are separate observations; they do not establish an AWS x86_64 memory bound or realized savings. See [implementation status](IMPLEMENTATION_STATUS.md), [test results](docs/testing.md) and [limitations](docs/decisions.md).

## Start with Docker

Prerequisites: Git and Docker Desktop / Docker Engine with Compose v2. Run commands from `proofops-app/`. Initial image/package downloads need Internet access. This is a separate Git repository inside the read-only research pack.

macOS/Linux:

```sh
test -f .env || cp .env.example .env
docker compose up -d --build
docker compose ps
```

Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

Open **http://127.0.0.1:5173**. Choose a replay and select **Run review**. The worker processes the persisted job; the page polls actual job state. Import, inspect findings, export a reproducible bundle, prepare a guard draft, run its fixtures, and record an operator disposition. Loading the FOCUS billing sample twice preserves exactly one import.

| Service | Local address | Purpose |
|---|---|---|
| Web | `http://127.0.0.1:5173` | Reviews, evidence detail and outcomes |
| API | `http://127.0.0.1:8000` | `/healthz`, `/readyz`, `/docs` and validated API |
| PostgreSQL | `127.0.0.1:55432` | Local database; container port 5432 |
| Reporting workload | `http://127.0.0.1:8080` | Optional `workload` Compose profile |
| Experiment target | `127.0.0.1:18080` | Temporary container owned by the workload runner |

Compose runs migrations before starting the API and worker. The API and worker use the `proofops` database; tests require the separate `proofops_test` database. Loopback binding and origin checks are local controls, not production authentication.

## Three-scenario walkthrough

Open **Reviews** at **http://127.0.0.1:5173/#/reviews** with the API and worker running. Keep the defaults: **Recorded replay time** and **Deterministic template · no AI call** under **Import or configure a review**. These scenarios use synthetic inputs and require no AWS or model API calls. Use **All reviews** between scenarios.

1. **Valid resize:** choose **Valid resize · 4 GiB → 2 GiB**, then **Run review**. Expect **Ready for engineering review** (`request_review`). Inspect **The proposed change**: the 2 GiB candidate meets the fixture's 2,048 MiB approved floor. **Workload comparison** shows the compatible runs passing their contract checks. The cost difference is an illustrative estimate; the result requests engineering review and grants no deployment permission.
2. **Unsafe resize:** choose **Below the floor · 4 GiB → 1 GiB**, then **Run review**. Expect **Revise the change** (`revise_change`). **What determines the result** explains the applicable memory-floor violation. Under **Keep the lesson**, select **Prepare guard draft**, then **Run guard fixtures** to inspect and export the tested rule. The draft remains **Not active**; revise the candidate before requesting another review.
3. **Incomplete evidence:** choose **Missing candidate evidence**, then **Run review**. Expect **Collect more evidence** (`collect_evidence`). Inspect **Evidence coverage** and **Workload comparison** for the missing candidate artifacts. A projected cost difference does not supply workload evidence. Collect compatible candidate evidence and rerun the review.

For any completed scenario, expand **Inspect cited facts and assumptions** and select **Export review bundle** to inspect the saved basis. A downloaded bundle can be reproduced with the replay command below. Historical or changed-revision notices describe current applicability separately from the saved result.

## Replay and guard commands

These commands also work inside the API container:

```sh
docker compose exec api proofops review --bundle fixtures/replays/valid-resize --ai off --output artifacts/review
docker compose exec api proofops replay artifacts/review
docker compose exec api proofops guards test
```

With the native environment below, omit `docker compose exec api` and use `.venv/bin/proofops` (PowerShell: `.venv\Scripts\proofops.exe`).

```sh
.venv/bin/proofops review --bundle fixtures/replays/unsafe-resize --ai off --output artifacts/unsafe
.venv/bin/proofops review --bundle fixtures/replays/incomplete-evidence --ai off --output artifacts/incomplete
.venv/bin/proofops replay artifacts/unsafe
.venv/bin/proofops guards test --policy-dir policies/approved --fixtures fixtures/negative_cases
.venv/bin/proofops ingest-costs --file fixtures/billing/focus_sample.csv
.venv/bin/proofops evaluate --manifest evaluation/manifest.json --mode replay
```

`review` exits **0** for ready-for-review or labelled out-of-scope, **2** for revise, **3** for collect evidence, and **1** for input/execution failure. `--require-supported` changes out-of-scope to exit 3. `--format json` and the default human summary agree. `replay` exits 0 when the saved deterministic report is reproduced, including a correctly rejected change. A guard fixture command checks only the memory rule.

Output includes `report.json`, `explanation.json`, `summary.md` and `review.zip`. Exported inputs are normalized and sanitized; the original secret-bearing plan is discarded. Replay uses the recorded evaluation time and trusted snapshot. It does not refresh applicability or authorize deployment. Copy downloaded ZIPs under `artifacts/` before using the replay CLI.

## Native development and testing

Use Python 3.12, uv 0.12.23, Node 22 LTS and Docker for PostgreSQL. The host build was verified on macOS ARM64; Docker supplies Linux containers. PowerShell instructions are provided but were not executed on this host.

macOS/Linux (a Python 3 interpreter is enough to bootstrap uv):

```sh
python3 -m venv .bootstrap
.bootstrap/bin/python -m pip install uv==0.12.23
.bootstrap/bin/uv python install 3.12
.bootstrap/bin/uv sync --frozen --group dev --group docs
test -f .env || cp .env.example .env
docker compose up -d db
.venv/bin/alembic upgrade head
.venv/bin/python scripts/create_test_database.py
.venv/bin/python scripts/install_tools.py
```

PowerShell:

```powershell
py -3 -m venv .bootstrap
.bootstrap\Scripts\python.exe -m pip install uv==0.12.23
.bootstrap\Scripts\uv.exe python install 3.12
.bootstrap\Scripts\uv.exe sync --frozen --group dev --group docs
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d db
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\python.exe scripts/create_test_database.py
.venv\Scripts\python.exe scripts/install_tools.py
```

Choose Docker or native processes for the same ports. If switching to native development, stop the container API/worker/web with `docker compose stop api worker web`. In three terminals, from the app root:

```sh
.venv/bin/uvicorn proofops.api.app:app --host 127.0.0.1 --port 8000
```

```sh
.venv/bin/proofops-worker
```

```sh
cd frontend
npm ci
npm run dev
```

For the first two commands on PowerShell, use `.venv\Scripts\uvicorn.exe` and `.venv\Scripts\proofops-worker.exe`. The frontend commands are identical.

Run the checks from the app root:

```sh
.venv/bin/pytest tests/unit tests/policy tests/integration -q --junitxml=artifacts/checks/backend.xml
.venv/bin/ruff check backend scripts tests evaluation demo
.venv/bin/ruff format --check backend scripts tests evaluation demo
.venv/bin/mypy backend/proofops
.venv/bin/proofops evaluate --mode replay
```

Then, with the local API, worker and web running:

```sh
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

On Linux, `npx playwright install --with-deps chromium` installs browser system dependencies. On PowerShell, replace Python executable paths with `.venv\Scripts\pytest.exe`, `ruff.exe`, `mypy.exe` and `proofops.exe`. Test scripts may read evaluator data; API/worker/model runtime never reads `evaluation/`, research `data/evaluator_only/`, or the RCAEval label index. Integration tests refuse any database name other than `proofops_test`.

## Workload and injected failure

The workload endpoint is `POST /v1/reports/summary`; it sums bounded integer-cent amounts. k6 independently checks the response ID, currency, count and total, including incorrect HTTP 200 responses. The full profile is eight minutes, with an 80/15/5 small/medium/large mix and 5–100 offered requests/second.

```sh
docker compose --profile workload up -d --build workload
.venv/bin/python scripts/run_workload.py all
```

The runner performs a 20-request smoke check, isolated bounded memory pressure/recovery, an eight-minute calibration baseline, then three alternating full baseline/candidate pairs. Allow about **57 minutes**. It records exact image, configuration, profile and dependency hashes, per-class results, dropped work and Docker termination state under `artifacts/workload/`. It removes only containers it created with its ownership label. Pressure stays disabled in the app and ordinary workload service.

Existing run directories are preserved. `scripts/run_workload.py compare` resumes missing comparison runs only when the frozen inputs still match. For another experiment, keep the original evidence and use the documented series option in [testing](docs/testing.md). Do not lower thresholds after observing a candidate failure.

## Configuration and boundaries

`.env.example` contains empty API keys and `AI_MODE=off`. Never commit a populated `.env`, Terraform state, private plans or API keys. No provider/model ID or price is fabricated. [Model inventory](docs/model_inventory.json) records the unconfigured roles, SDK contracts and unrun live measurements.

Live AI requires `AI_MODE=live`, an allowed provider, a verified exact model ID, its environment key, a current USD price entry in `config/model_prices.json`, and positive `AI_BUDGET_USD` and `AI_MAX_TASK_COST_USD`. Replay remains available with missing keys. The router allows at most two attempts per task, counts failed-call spend, and retains uncertain reservations after timeouts/crashes. AI cannot change a deterministic finding or activate policy. See [provider contracts](docs/provider_contracts.md) and [operations](docs/operations.md).

The optional collector uses the normal boto3 credential chain, validates the STS account and reads only a configured service. `proofops collect --mode live` requires scope configuration matching a separately reviewed contract. It is not needed for replay. [AWS setup and IAM](docs/aws.md) describes exact actions and costs; [the optional Terraform demo](infra/aws-demo/) was formatted and validated locally, **not deployed**.

The [offline CI workflow](.github/workflows/offline.yml) runs without cloud/model secrets. Its trusted-policy example loads code, policy and mapping from the base revision and reads bounded candidate data. Local equivalents were tested; no remote GitHub workflow or protected deployment check was configured. See [CI trust](docs/ci.md).

## Documentation and cleanup

- [Project overview PDF](docs/pdf/ProofOps_Project_Overview.pdf)
- [Technical and learning guide PDF](docs/pdf/ProofOps_Technical_and_Learning_Guide.pdf)
- [Architecture](docs/architecture.md), [module reference](docs/module_reference.md), [testing](docs/testing.md), [learning path](docs/learning_path.md), [interview walkthrough](docs/interview_walkthrough.md)
- [Changes and security improvements](CHANGELOG.md), [source attribution](docs/data_sources.md), [implementation status](IMPLEMENTATION_STATUS.md)

Rebuild and validate both searchable PDFs from editable local sources:

```sh
.venv/bin/python scripts/build_docs.py
.venv/bin/python scripts/validate_docs.py
```

The committed `docs/results/` extracts make PDF rebuilding independent of live services or a new load experiment. After deliberately rerunning the local checks and full workload, `python scripts/record_results.py` refreshes those extracts from `artifacts/`; it does not invent missing measurements. The model inventory preserves null live values with reasons. Saved PDF checks are in `docs/pdf/validation.json`.

Only when the original research pack is still the app's parent folder, run `.venv/bin/python scripts/check_research.py` to audit preservation. It is not an application dependency and intentionally reports missing research inputs in a standalone checkout. Generated runtime artifacts stay under `artifacts/`; generated PDF page previews stay under `docs/pdf/rendered/`.

```sh
docker compose --profile workload down
```

This stops/removes the application's containers and network while preserving its named database/artifact volumes. Native processes stop with Ctrl+C. To erase only this app's local database and artifact volumes, use `docker compose --profile workload down --volumes` after saving needed exports. Do not delete or modify the parent research files.
