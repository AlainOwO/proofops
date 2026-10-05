from dataclasses import dataclass
from typing import Any, Literal, Protocol

import anthropic
import httpx
import openai

from proofops.domain.common import strict_json


@dataclass
class ModelResult:
    terminal_status: Literal["completed", "refused", "truncated", "incomplete", "error"]
    output: dict | None
    usage: dict[str, int] | None
    provider_request_id: str | None = None
    error_class: str | None = None
    definitely_unbilled: bool = False


class Adapter(Protocol):
    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str,
        max_output_tokens: int,
        timeout: float,
    ) -> ModelResult: ...


def transport_schema(schema: dict, provider: str) -> dict:
    # Providers support different constraint subsets. The full Pydantic/domain
    # schema is always enforced after transport decoding; nothing is accepted on
    # the strength of this weaker generation grammar alone.
    unsupported = {
        "default",
        "$schema",
        "title",
        "examples",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
    }

    def transform(value):
        if isinstance(value, list):
            return [transform(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: transform(child) for key, child in value.items() if key not in unsupported}
        if "const" in result:
            result["enum"] = [result.pop("const")]
        if result.get("type") == "object":
            result["additionalProperties"] = False
            if provider == "openai":
                result["required"] = list(result.get("properties", {}))
        return result

    return transform(schema)


def provider_error(exc: Exception) -> ModelResult:
    if isinstance(exc, (openai.APITimeoutError, anthropic.APITimeoutError, httpx.TimeoutException)):
        return ModelResult("error", None, None, error_class="timeout_uncertain")
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    code = ""
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or "")
    # Never persist exception bodies: providers can echo input or credential data.
    if code in {"insufficient_quota", "billing_error", "credit_balance_too_low"}:
        return ModelResult(
            "error", None, None, error_class="permanent_quota", definitely_unbilled=True
        )
    if status in {401, 403}:
        return ModelResult(
            "error", None, None, error_class="authentication", definitely_unbilled=True
        )
    if status == 429:
        return ModelResult(
            "error", None, None, error_class="transient_throttle", definitely_unbilled=True
        )
    if status in {400, 404, 422}:
        return ModelResult(
            "error", None, None, error_class="unsupported_request", definitely_unbilled=True
        )
    return ModelResult("error", None, None, error_class="provider_execution_uncertain")


def parse_output(text: str) -> dict | None:
    if len(text.encode()) > 24_000:
        return None
    try:
        result = strict_json(text)
    except (ValueError, TypeError):
        return None
    return result if isinstance(result, dict) else None


class OpenAIAdapter:
    def __init__(self, api_key: str = "", *, client: Any = None):
        self.client = (
            client
            if client is not None
            else openai.OpenAI(api_key=api_key, max_retries=0, timeout=20)
        )

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str,
        max_output_tokens: int,
        timeout: float,
    ) -> ModelResult:
        try:
            response = self.client.responses.create(
                model=model,
                input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "proofops_result",
                        "strict": True,
                        "schema": transport_schema(schema, "openai"),
                    }
                },
                max_output_tokens=max_output_tokens,
                store=False,
                stream=False,
                timeout=timeout,
            )
        except (openai.APIError, httpx.HTTPError) as exc:
            return provider_error(exc)
        raw_usage = getattr(response, "usage", None)
        usage = None
        if raw_usage is not None:
            details = getattr(raw_usage, "input_tokens_details", None)
            cached = getattr(details, "cached_tokens", 0) or 0
            reasoning_details = getattr(raw_usage, "output_tokens_details", None)
            usage = {
                "input_uncached": raw_usage.input_tokens - cached,
                "cache_read": cached,
                "cache_write": 0,
                "output": raw_usage.output_tokens,
                "reasoning_included_in_output": getattr(reasoning_details, "reasoning_tokens", 0)
                or 0,
            }
        request_id = getattr(response, "_request_id", None) or getattr(response, "id", None)
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    return ModelResult("refused", None, usage, request_id)
        status = getattr(response, "status", None)
        if status != "completed":
            details = getattr(response, "incomplete_details", None)
            truncated = getattr(details, "reason", None) == "max_output_tokens"
            return ModelResult("truncated" if truncated else "incomplete", None, usage, request_id)
        return ModelResult("completed", parse_output(response.output_text), usage, request_id)


class AnthropicAdapter:
    def __init__(self, api_key: str = "", *, client: Any = None):
        self.client = (
            client
            if client is not None
            else anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=20)
        )

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str,
        max_output_tokens: int,
        timeout: float,
    ) -> ModelResult:
        try:
            response = self.client.messages.create(
                model=model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_output_tokens,
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": transport_schema(schema, "anthropic"),
                    }
                },
                stream=False,
                timeout=timeout,
            )
        except (anthropic.APIError, httpx.HTTPError) as exc:
            return provider_error(exc)
        raw_usage = getattr(response, "usage", None)
        usage = None
        if raw_usage is not None:
            usage = {
                "input_uncached": raw_usage.input_tokens,
                "cache_read": getattr(raw_usage, "cache_read_input_tokens", 0) or 0,
                "cache_write": getattr(raw_usage, "cache_creation_input_tokens", 0) or 0,
                "output": raw_usage.output_tokens,
                "reasoning_included_in_output": 0,
            }
        request_id = getattr(response, "_request_id", None) or getattr(response, "id", None)
        stop = getattr(response, "stop_reason", None)
        if stop == "refusal":
            return ModelResult("refused", None, usage, request_id)
        if stop != "end_turn":
            return ModelResult(
                "truncated" if stop == "max_tokens" else "incomplete", None, usage, request_id
            )
        text = "".join(
            getattr(block, "text", "") for block in response.content if block.type == "text"
        )
        return ModelResult("completed", parse_output(text), usage, request_id)
