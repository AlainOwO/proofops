# Learning path

The build order assumes an already comfortable Python/Docker developer. A beginner should use the stages below at their own pace; seven build days are not seven days to master the stack. Start with the deterministic replay, then learn the optional live boundaries.

| Stage | Learn and why | Exercise and completion check |
|---|---|---|
| 1. Files, terminal and Git | Paths, processes, environment variables, diffs and small commits explain where state lives. | Run `git status` inside the app, locate the three replays, and explain why a populated `.env` is ignored. Do not edit research. |
| 2. Python and types | Functions, exceptions, modules, dictionaries and Pydantic turn raw JSON into explicit contracts. | In a new scratch test under the app, construct an invalid CPU/MiB pair. Confirm validation rejects it without coercing it to zero. |
| 3. HTTP and structured data | Requests, status codes, JSON, schemas, UTC and Decimal distinguish transport success from business correctness. | Send a valid integer-cent report request, then an invalid body. Explain why an HTTP 200 with a wrong total fails the workload oracle. |
| 4. Domain reasoning | Pure functions, invariants and precedence make decisions reproducible without an LLM. | Run all three replay commands. Explain why a missing source cannot cancel a known memory violation and why `request_review` is not deployment approval. |
| 5. SQL and transactions | Tables, foreign keys, JSONB, locks and isolation protect jobs and money across processes. | Run the reservation/concurrency tests on `proofops_test`. Explain why two workers cannot spend the same reservation. |
| 6. Web UI | TypeScript, React state, effects, accessibility and CSS connect visible state to persisted backend results. | Inspect evidence and record a disposition. Simulate an unavailable API and confirm the page does not display an invented zero or saved state. |
| 7. Infrastructure as code | HCL, plan JSON, Fargate task sizes, IAM and container digests bind a proposed change to a resource. | Inspect the unsafe plan and service map, then run Conftest fixtures. Explain why another service is not rejected by this service's memory guard. |
| 8. Performance experiments | Arrival rate, virtual users, p95, warmup, sample size and compatible populations define what a test can show. | Compare one baseline and candidate manifest. Identify offered/completed/correct/dropped work and explain why local ARM64 is not an AWS x86_64 bound. |
| 9. Optional LLM inference | Hosted model requests, structured output, tokens, pricing, mechanical versus semantic validation and fallback. | Run the mocked adapter and false-causality tests. Describe a response that passes schema/citations but is still wrong. No paid key is needed. |
| 10. Evaluation and operations | Group splits, independent labels, accounting uncertainty, CI trust, logs, migrations and retention. | Reproduce offline evaluation, inspect the 8/4/8 groups and null live metrics, rebuild PDFs and recover a test worker lease. Explain one remaining production prerequisite. |

## Official starting points

- [Python tutorial](https://docs.python.org/3/tutorial/) and [venv](https://docs.python.org/3/library/venv.html)
- [Git book](https://git-scm.com/book/en/v2) and [PowerShell introduction](https://learn.microsoft.com/en-us/powershell/scripting/overview)
- [HTTP overview](https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview), [JSON](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON), [TypeScript handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
- [Pydantic concepts](https://docs.pydantic.dev/latest/concepts/models/), [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/), [SQLAlchemy tutorial](https://docs.sqlalchemy.org/en/20/tutorial/)
- [PostgreSQL tutorial](https://www.postgresql.org/docs/17/tutorial.html) and [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [React learn](https://react.dev/learn), [Vite guide](https://vite.dev/guide/), [MDN CSS](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics)
- [Docker getting started](https://docs.docker.com/get-started/), [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials), [ECS guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html)
- [Conftest](https://www.conftest.dev/), [Rego introduction](https://www.openpolicyagent.org/docs/policy-language), [k6 testing](https://grafana.com/docs/k6/latest/testing-guides/)
- [pytest getting started](https://docs.pytest.org/en/stable/getting-started.html), [Playwright introduction](https://playwright.dev/docs/intro), [GitHub Actions](https://docs.github.com/en/actions)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)

Follow the [authentication boundary and setup](security.md) to study Argon2id, sessions, CSRF, role enforcement and shared login limits. Later topics include MFA/SSO and tenant isolation, managed secret delivery, retention and observability, broader AWS coverage and larger independently reviewed model evaluations. Kubernetes, LangGraph and vector databases are deferred, not hidden prerequisites.
