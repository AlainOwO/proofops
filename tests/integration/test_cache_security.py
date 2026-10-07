"""Offline cache boundaries and the documented source-permission TTL limitation."""

import json
from datetime import timedelta

import pytest
from botocore.exceptions import ClientError
from proofops.collectors import aws
from proofops.collectors.aws import AWSCollector
from proofops.observability import logger
from proofops.storage.database import ArtifactRow, ReportRow, ToolCacheRow
from proofops.storage.repository import create_job, review_summaries, store_bundle
from proofops.storage.tool_cache import ObservationCache
from proofops.workers.runner import run_once
from sqlalchemy import delete, select

from tests.integration.test_aws_cache import identity, sources
from tests.unit import test_aws_collectors as aws_tests

pytestmark = pytest.mark.integration
aws_clients = aws_tests.aws_clients
metric_stub = aws_tests.metric_stub


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "999988887777"),
        ("cluster", "isolated-cluster"),
        ("service", "isolated-service"),
        ("terraform_address", "module.isolated.aws_ecs_task_definition.service"),
        ("environment", "isolated-environment"),
    ],
)
def test_aws_cache_cannot_reuse_another_workload_scope(db, aws_clients, valid_bundle, field, value):
    clients, stubs = aws_clients
    scope = valid_bundle.contract.scope
    changed = scope.model_copy(update={field: value})
    collector = AWSCollector(clients, cache=ObservationCache(db))
    for current in (scope, changed):
        identity(stubs, current)
        sources(stubs, current, valid_bundle.contract.applicability.image_digest)
        result = collector.collect(current)
        assert result["cache"]["state"] == "miss"
        assert result["calls"] == 5
        assert result["scope"] == current.model_dump(mode="json")
    identity(stubs, scope)
    assert collector.collect(scope)["cache"]["state"] == "hit"
    with db() as session:
        assert len(session.scalars(select(ToolCacheRow)).all()) == 2


@pytest.mark.parametrize("field", ["Arn", "UserId"])
def test_aws_cache_keys_every_caller_identity_component(db, aws_clients, valid_bundle, field):
    clients, stubs = aws_clients
    scope = valid_bundle.contract.scope
    collector = AWSCollector(clients, cache=ObservationCache(db))
    identity(stubs, scope)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    assert collector.collect(scope)["cache"]["state"] == "miss"
    changed = {
        "Account": scope.account_id,
        "Arn": f"arn:aws:iam::{scope.account_id}:user/mock",
        "UserId": "mock",
    }
    changed[field] += "-other"
    stubs["sts"].add_response("get_caller_identity", changed)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    assert collector.collect(scope)["cache"]["state"] == "miss"


def test_aws_cache_and_operation_logs_omit_caller_identity_and_labelled_log_credentials(
    db, aws_clients, valid_bundle, monkeypatch
):
    clients, stubs = aws_clients
    scope = valid_bundle.contract.scope
    records = []
    monkeypatch.setattr(logger, "info", records.append)
    collector = AWSCollector(clients, cache=ObservationCache(db), log_group="/proofops/demo")
    caller = "synthetic-private-caller"
    marker = "synthetic-private-credential"
    identity(stubs, scope, caller)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    stubs["logs"].add_response("start_query", {"queryId": "synthetic-query"})
    stubs["logs"].add_response(
        "get_query_results",
        {
            "status": "Complete",
            "results": [[{"field": "@message", "value": f"api_key={marker}"}]],
        },
    )
    first = collector.collect(scope)
    identity(stubs, scope, caller)
    cached = collector.collect(scope)
    assert cached["cache"]["state"] == "hit"
    assert first["sources"][2]["data"]["rows"] == [{"@message": "[REDACTED]"}]
    with db() as session:
        row = session.scalar(select(ToolCacheRow))
        stored = json.dumps({"key": row.key, "data": row.data})
    for private in (caller, marker, "mock-only"):
        assert private not in stored
        assert private not in json.dumps(cached)
        assert private not in "".join(records)


def test_open_same_principal_permission_changes_are_only_seen_after_aws_cache_ttl(
    db, aws_clients, valid_bundle, monkeypatch
):
    """A cache hit verifies identity, not each source's current authorization."""
    clients, stubs = aws_clients
    scope, now = valid_bundle.contract.scope, valid_bundle.reference_time
    monkeypatch.setattr(aws, "utcnow", lambda: now)
    collector = AWSCollector(clients, cache=ObservationCache(db), cache_ttl_seconds=60)
    identity(stubs, scope)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    original = collector.collect(scope)
    denied_calls = []

    def denied(**kwargs):
        denied_calls.append(kwargs)
        raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "DescribeServices")

    monkeypatch.setattr(clients["ecs"], "describe_services", denied)
    monkeypatch.setattr(aws, "utcnow", lambda: now + timedelta(seconds=59))
    identity(stubs, scope)
    cached = collector.collect(scope)
    assert cached["cache"]["state"] == "hit"
    assert cached["sources"][0]["status"] == "complete"
    assert cached["observed_end"] == original["observed_end"]
    assert denied_calls == []
    monkeypatch.setattr(aws, "utcnow", lambda: now + timedelta(seconds=60))
    identity(stubs, scope)
    metric_stub(stubs)
    expired = collector.collect(scope)
    assert expired["cache"]["state"] == "miss"
    assert expired["sources"][0]["status"] == "denied"
    assert len(denied_calls) == 1


def test_review_projections_reflect_updates_and_deletion_without_stale_reuse(
    db, auth_settings, valid_bundle, trusted
):
    with db.begin() as session:
        bundle, _ = store_bundle(session, valid_bundle)
        job, _ = create_job(
            session, bundle, trusted, key="projection-freshness", mode="replay", ai_preference="off"
        )
        review_id = job.id
    with db() as session:
        pending = review_summaries(session, 100, 0)
        assert pending[0]["state"] == "queued" and pending[0]["outcome"] is None
    assert run_once(factory=db, settings=auth_settings) == review_id
    with db() as session:
        complete = review_summaries(session, 100, 0)
        assert complete[0]["state"] == "completed" and complete[0]["outcome"]
        assert "core" not in complete[0] and "explanation" not in complete[0]
    with db.begin() as session:
        session.execute(delete(ArtifactRow).where(ArtifactRow.review_id == review_id))
        session.execute(delete(ReportRow).where(ReportRow.id == review_id))
    with db() as session:
        removed = review_summaries(session, 100, 0)
        assert removed[0]["outcome"] is None and removed[0]["service"] is None
