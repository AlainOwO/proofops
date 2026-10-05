import json

import anthropic
import httpx
import openai
import pytest
from proofops.domain.engine import review
from proofops.domain.schemas import Explanation
from proofops.models.adapters import AnthropicAdapter, OpenAIAdapter, transport_schema
from proofops.models.explanations import template_explanation, validate_explanation


def openai_body(output, *, status="completed", refusal=False):
    content = (
        [{"type": "refusal", "refusal": "Mock refusal"}]
        if refusal
        else [{"type": "output_text", "text": json.dumps(output), "annotations": []}]
    )
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 1,
        "model": "mock-model",
        "status": status,
        "error": None,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [
            {
                "type": "message",
                "id": "msg_mock",
                "status": "completed",
                "role": "assistant",
                "content": content,
            }
        ],
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 30,
            "output_tokens_details": {"reasoning_tokens": 10},
            "total_tokens": 130,
        },
    }


def test_openai_actual_sdk_request_and_usage(valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    output = template_explanation(report)["output"]
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json=openai_body(output), headers={"x-request-id": "mock-openai-request"}
        )

    client = openai.OpenAI(
        api_key="mock-only",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = OpenAIAdapter(client=client).generate_structured(
        system="system",
        user="facts",
        schema=Explanation.model_json_schema(),
        model="mock-model",
        max_output_tokens=1200,
        timeout=1,
    )
    assert result.terminal_status == "completed"
    validate_explanation(result.output, report)
    assert result.usage == {
        "input_uncached": 80,
        "cache_read": 20,
        "cache_write": 0,
        "output": 30,
        "reasoning_included_in_output": 10,
    }
    assert requests[0]["text"]["format"]["type"] == "json_schema"
    assert requests[0]["store"] is False and requests[0]["stream"] is False
    assert "tools" not in requests[0]


@pytest.mark.parametrize(
    ("status", "refusal", "expected"),
    [
        ("incomplete", False, "truncated"),
        ("in_progress", False, "incomplete"),
        ("completed", True, "refused"),
    ],
)
def test_openai_terminal_states(status, refusal, expected):
    client = openai.OpenAI(
        api_key="mock-only",
        max_retries=0,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json=openai_body({}, status=status, refusal=refusal)
                )
            )
        ),
    )
    result = OpenAIAdapter(client=client).generate_structured(
        system="", user="", schema={}, model="mock", max_output_tokens=200, timeout=1
    )
    assert result.terminal_status == expected and result.output is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [("insufficient_quota", "permanent_quota"), ("rate_limit_exceeded", "transient_throttle")],
)
def test_quota_and_throttle_are_distinct_and_sdk_does_not_retry(code, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429, json={"error": {"code": code, "message": "secret=must-not-escape", "type": code}}
        )

    client = openai.OpenAI(
        api_key="mock-only",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = OpenAIAdapter(client=client).generate_structured(
        system="", user="", schema={}, model="mock", max_output_tokens=200, timeout=1
    )
    assert result.error_class == expected and result.definitely_unbilled
    assert len(calls) == 1
    assert "must-not-escape" not in repr(result)


@pytest.mark.parametrize(
    ("stop", "expected"),
    [
        ("end_turn", "completed"),
        ("max_tokens", "truncated"),
        ("refusal", "refused"),
        ("pause_turn", "incomplete"),
    ],
)
def test_anthropic_actual_sdk_mapping_and_terminal_states(stop, expected):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_mock",
                "type": "message",
                "role": "assistant",
                "model": "mock-model",
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "cache_creation_input_tokens": 20,
                    "cache_read_input_tokens": 50,
                },
            },
        )

    client = anthropic.Anthropic(
        api_key="mock-only",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = AnthropicAdapter(client=client).generate_structured(
        system="system",
        user="facts",
        schema=Explanation.model_json_schema(),
        model="mock-model",
        max_output_tokens=1200,
        timeout=1,
    )
    assert result.terminal_status == expected
    assert requests[0]["system"] == "system"
    assert requests[0]["output_config"]["format"]["type"] == "json_schema"
    assert (
        result.usage["input_uncached"] == 100
        and result.usage["cache_read"] == 50
        and result.usage["cache_write"] == 20
    )
    assert "tools" not in requests[0]


def test_transport_grammar_does_not_replace_application_validation():
    schema = Explanation.model_json_schema()
    transformed = transport_schema(schema, "openai")
    assert "maxLength" not in transformed["properties"]["summary"]
    assert schema["properties"]["summary"]["maxLength"] == 1400
