"""Exercise log privacy and the absence of a remotely readable metrics route."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from proofops.observability import logger

from tests.unit.test_http_boundaries import invoke, make_app


@pytest.mark.parametrize("path", ["/metrics", "/api/v1/metrics", "/api/v1/operations"])
@pytest.mark.parametrize("access", ["anonymous", "member", "public_demo"])
def test_operation_metrics_have_no_http_surface(monkeypatch, path, access):
    app = make_app(monkeypatch, principal=True if access == "member" else None)
    app.state.settings.proofops_public_demo = access == "public_demo"
    assert not any(getattr(route, "path", None) == path for route in app.routes)
    status, _ = asyncio.run(invoke(app, path))
    assert status == {"anonymous": 401, "member": 404, "public_demo": 403}[access]


@pytest.mark.parametrize("response", ["success", "exception", "unmatched", "denied"])
def test_operation_labels_never_use_request_or_exception_text(monkeypatch, response):
    records = []
    monkeypatch.setattr(logger, "info", records.append)
    marker = "synthetic-private-" + uuid4().hex
    app = make_app(monkeypatch, principal=None if response == "denied" else True)

    @app.get("/private-test/{resource}")
    async def private_endpoint(resource: str, request: Request):
        assert resource == marker
        if response == "exception":
            raise RuntimeError(marker)
        return {"status": "ok"}

    path = f"/private-test/{marker}"
    if response == "unmatched":
        path = f"/unmatched/{marker}"
    status, messages = asyncio.run(
        invoke(
            app,
            path,
            peer=marker,
            headers=[
                (b"authorization", f"Bearer {marker}".encode()),
                (b"cookie", f"unrelated={marker}".encode()),
                (b"x-request-id", marker.encode()),
            ],
        )
    )
    assert status == {"success": 200, "exception": 500, "unmatched": 404, "denied": 401}[response]
    event = json.loads(records[-1])
    assert event["operation"] == "http.request"
    assert event["route"] == (
        "unmatched" if response in {"unmatched", "denied"} else "/private-test/{resource}"
    )
    UUID(event["request_id"])
    assert dict(messages[0]["headers"])[b"x-request-id"].decode() == event["request_id"]
    assert marker not in "".join(records)
