# Provider contracts verified 2026-10-05

The implementation uses the official installed SDKs pinned in `uv.lock`. These references were fetched before adapter implementation:

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): Responses API `text.format` with a named strict JSON Schema; `max_output_tokens`, `store=false`, complete non-streaming responses. Refusal, incomplete state and token truncation remain explicit. Reported output tokens include reasoning where applicable; reasoning details are not charged twice.
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs): Messages API uses separate `system`, user `messages`, `max_tokens` and `output_config.format`. `end_turn` is required; `refusal`, `max_tokens` and other stop reasons are separate states. Input, cache-read and cache-creation usage are distinct billing categories.

Provider grammar constraints are a subset of application validation. The transport schema drops unsupported bounds and requires closed objects; the original typed schema, exact citations, finding codes, numeric facts and action boundary are checked after completion. No stream is accepted, and both SDK clients disable automatic retries. The router owns the total limit of two billable attempts.

No model is configured for paid use by default. Exact model IDs, allowed providers, credentials, dated official rates (including cache rates), capability declaration and positive overall/per-task budgets are required. A missing/stale price entry blocks dispatch. SDK mocks prove the adapter contract, not model quality or account access. Schemas/citations do not establish semantic correctness.
