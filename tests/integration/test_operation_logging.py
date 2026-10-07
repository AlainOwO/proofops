import json
import secrets
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.observability import logger, operation
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_operation_sql_metrics_exclude_statements_and_private_values(db, monkeypatch):
    records = []
    monkeypatch.setattr(logger, "info", records.append)
    marker = secrets.token_urlsafe(32)
    identity = str(uuid4())
    with operation("test.query", job_id=identity):
        with db() as session:
            assert (
                session.scalar(text("SELECT :private_marker"), {"private_marker": marker}) == marker
            )
    event = json.loads(records[0])
    assert event["db_queries"] == 1 and event["db_duration_ms"] >= 0 and event["duration_ms"] >= 0
    assert event["job_id"] == identity
    assert (
        marker not in records[0]
        and "SELECT" not in records[0]
        and "private_marker" not in records[0]
    )


def test_request_logs_have_generated_correlation_and_no_credentials(
    db, auth_settings, login_user, monkeypatch
):
    records = []
    monkeypatch.setattr(logger, "info", records.append)
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as client:
        username, password, _ = login_user(client)
        records.clear()
        response = client.get(
            "/api/v1/reviews?private=do-not-log", headers={"X-Request-ID": "untrusted-correlation"}
        )
    event = json.loads(records[-1])
    assert event["operation"] == "http.request" and event["route"] == "/api/v1/reviews"
    assert event["http_status"] == 200 and event["db_queries"] >= 3
    assert event["request_id"] == response.headers["X-Request-ID"]
    UUID(event["request_id"])
    for private in (username, password, "do-not-log", "untrusted-correlation"):
        assert private not in "".join(records)


def test_disabled_operation_logging_leaves_api_behavior_intact(
    db, auth_settings, login_user, monkeypatch
):
    records = []
    monkeypatch.setattr(logger, "info", records.append)
    auth_settings.operation_logging = False
    with TestClient(create_app(auth_settings, factory=db)) as client:
        login_user(client)
        assert client.get("/api/v1/reviews").status_code == 200
    assert not records
