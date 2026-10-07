from datetime import timedelta

import pytest
from proofops.collectors import aws
from proofops.collectors.aws import AWSCollector, task_evidence
from proofops.domain.engine import review
from proofops.storage.database import ToolCacheRow
from proofops.storage.tool_cache import ObservationCache
from sqlalchemy import select

from tests.unit import test_aws_collectors as aws_tests

pytestmark = pytest.mark.integration
aws_clients = aws_tests.aws_clients
metric_stub = aws_tests.metric_stub


def identity(stubs, scope, caller="mock"):
    stubs["sts"].add_response(
        "get_caller_identity",
        {
            "Account": scope.account_id,
            "UserId": caller,
            "Arn": f"arn:aws:iam::{scope.account_id}:user/{caller}",
        },
    )


def sources(stubs, scope, image):
    prefix = f"arn:aws:ecs:{scope.region}:{scope.account_id}:"
    task_arn = prefix + "task-definition/reports-demo:1"
    stubs["ecs"].add_response(
        "describe_services",
        {
            "services": [
                {
                    "serviceArn": prefix + f"service/{scope.cluster}/{scope.service}",
                    "serviceName": scope.service,
                    "clusterArn": prefix + f"cluster/{scope.cluster}",
                    "taskDefinition": task_arn,
                    "runningCount": 0,
                    "desiredCount": 0,
                }
            ]
        },
    )
    stubs["ecs"].add_response(
        "describe_task_definition",
        {
            "taskDefinition": {
                "taskDefinitionArn": task_arn,
                "cpu": "2048",
                "memory": "4096",
                "runtimePlatform": {"cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX"},
                "requiresCompatibilities": ["FARGATE"],
                "containerDefinitions": [
                    {"name": "reports-api", "image": "example.invalid/reports@" + image}
                ],
            }
        },
    )
    stubs["ecs"].add_response("list_tasks", {"taskArns": []})
    metric_stub(stubs)


def test_cached_aws_uses_only_sts_and_preserves_original_times(
    db, aws_clients, valid_bundle, trusted, monkeypatch, record_property
):
    clients, stubs = aws_clients
    scope, original_time = valid_bundle.contract.scope, valid_bundle.reference_time
    monkeypatch.setattr(aws, "utcnow", lambda: original_time)
    collector = AWSCollector(clients, cache=ObservationCache(db))
    identity(stubs, scope)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    first = collector.collect(scope)
    identity(stubs, scope)
    monkeypatch.setattr(aws, "utcnow", lambda: original_time + timedelta(seconds=10))
    second = collector.collect(scope)
    assert first["calls"] == 5 and second["calls"] == 1
    assert first["cache"]["state"] == "miss" and second["cache"]["state"] == "hit"
    assert second["collected_at"] == first["collected_at"]
    assert second["observed_end"] == first["observed_end"]
    assert second["cache"]["age_seconds"] == 10 and second["cache"]["expires_at"]
    # Being inside the cache TTL cannot bypass a stricter operating contract.
    valid_bundle.contract.requirements.max_evidence_age_seconds = 5
    trusted = trusted.model_copy(deep=True)
    trusted.contract = valid_bundle.contract
    evidence = task_evidence(second)
    valid_bundle.evidence = [
        item for item in valid_bundle.evidence if item.kind != "task_configuration"
    ] + [evidence]
    report = review(valid_bundle, trusted, reference=original_time + timedelta(seconds=10))
    records = report.coverage["sources"]["task_configuration"]["records"]
    assert records and all(item["freshness"] == "stale" for item in records)
    assert report.outcome == "collect_evidence"
    assert evidence.metadata["cache_state"] == "hit"
    record_property("aws_mock_sdk_calls_cold_then_hit", first["calls"] + second["calls"])


@pytest.mark.parametrize("change", ["expired", "caller", "lookback", "disabled"])
def test_changed_or_expired_aws_cache_requires_new_observations(
    db, aws_clients, valid_bundle, change, record_property
):
    clients, stubs = aws_clients
    scope = valid_bundle.contract.scope
    collector = AWSCollector(clients, cache=ObservationCache(db))
    identity(stubs, scope)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    first = collector.collect(scope)
    if change == "expired":
        with db.begin() as session:
            session.scalar(select(ToolCacheRow)).expires_at -= timedelta(seconds=120)
    elif change == "lookback":
        collector.lookback += 60
    elif change == "disabled":
        collector.cache_ttl = 0
    identity(stubs, scope, "other" if change == "caller" else "mock")
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    second = collector.collect(scope)
    assert second["calls"] == first["calls"] == 5
    assert second["cache"]["state"] != "hit"
    if change == "disabled":
        record_property("aws_mock_sdk_calls_without_reuse", first["calls"] + second["calls"])


@pytest.mark.parametrize(
    "error, state", [("AccessDeniedException", "denied"), ("ThrottlingException", "failed")]
)
def test_denied_collection_is_never_cached(db, aws_clients, valid_bundle, error, state):
    clients, stubs = aws_clients
    collector = AWSCollector(clients, cache=ObservationCache(db))
    scope = valid_bundle.contract.scope
    for _ in range(2):
        identity(stubs, scope)
        stubs["ecs"].add_client_error("describe_services", error)
        metric_stub(stubs)
        collection = collector.collect(scope)
        assert collection["sources"][0]["status"] == state
        assert collection["cache"]["state"] == "miss"
    with db() as session:
        assert session.scalar(select(ToolCacheRow)) is None


def test_incomplete_collection_is_never_cached(db, aws_clients, valid_bundle):
    clients, stubs = aws_clients
    collector = AWSCollector(clients, max_calls=1, cache=ObservationCache(db))
    identity(stubs, valid_bundle.contract.scope)
    collection = collector.collect(valid_bundle.contract.scope)
    assert collection["sources"][0]["status"] == "pending"
    with db() as session:
        assert session.scalar(select(ToolCacheRow)) is None


def test_sts_failure_does_not_return_cached_evidence(db, aws_clients, valid_bundle):
    clients, stubs = aws_clients
    collector = AWSCollector(clients, cache=ObservationCache(db))
    scope = valid_bundle.contract.scope
    identity(stubs, scope)
    sources(stubs, scope, valid_bundle.contract.applicability.image_digest)
    collector.collect(scope)
    stubs["sts"].add_client_error("get_caller_identity", "AccessDenied", "private provider body")
    with pytest.raises(ValueError, match="caller identity is unavailable") as failure:
        collector.collect(scope)
    assert "private provider body" not in str(failure.value)
