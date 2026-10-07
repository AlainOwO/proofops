"""Repeatable offline measurements; JUnit properties hold the observed values.

These are characterization checks, not performance thresholds. Behavioral cache
and projection regressions live in the focused tests. No provider is contacted.
"""

import json
from datetime import timedelta
from statistics import median
from time import perf_counter
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.domain.common import canonical, digest, utcnow
from proofops.domain.engine import review
from proofops.models.adapters import ModelResult
from proofops.models.explanations import template_explanation
from proofops.storage.database import CacheRow, ReportRow
from proofops.storage.repository import create_job, store_bundle
from proofops.workers.runner import run_once
from sqlalchemy import event, select

from tests.integration.test_budget_jobs import setup_router

pytestmark = pytest.mark.integration


def test_measure_expired_cache_reuse(db, valid_bundle, trusted, record_property):
    report = review(valid_bundle, trusted)
    before = digest(report)
    output = template_explanation(report)["output"]
    usage = {"input_uncached": 100, "cache_read": 0, "cache_write": 0, "output": 100}
    router, cheap, strong = setup_router(db, [ModelResult("completed", output, usage)])
    states = []
    for index in range(4):
        if index == 2:
            with db.begin() as session:
                for row in session.scalars(select(CacheRow)):
                    row.expires_at = utcnow() - timedelta(seconds=1)
        result = router.explain(report, ai_preference="auto", task_id=f"measure-{index}")
        assert result["output"] == output
        states.append(result["status"])
    assert digest(report) == before
    assert strong.calls == 0
    record_property("offline_cache_states", json.dumps(states))
    record_property("mock_provider_calls_for_four_requests", cheap.calls)


def test_measure_review_reads(
    db, auth_settings, login_user, valid_bundle, trusted, record_property
):
    ids = []
    with db.begin() as session:
        bundle, _ = store_bundle(session, valid_bundle)
        for index in range(10):
            job, _ = create_job(
                session, bundle, trusted, key=f"measure-{index}", mode="replay", ai_preference="off"
            )
            ids.append(job.id)
    for _ in ids:
        assert run_once(factory=db, settings=auth_settings)
    app = create_app(auth_settings, factory=db)
    document_bytes, statements = [], []

    def loaded(session, instance):
        if isinstance(instance, ReportRow):
            document_bytes.append(
                len(canonical(instance.core)) + len(canonical(instance.explanation))
            )

    def executed(conn, cursor, statement, parameters, context, executemany):
        statements.append(1)

    with TestClient(app) as client:
        login_user(client)
        event.listen(db, "loaded_as_persistent", loaded)
        event.listen(db.kw["bind"], "after_cursor_execute", executed)
        try:
            listing = client.get("/api/v1/reviews?limit=10")
        finally:
            event.remove(db, "loaded_as_persistent", loaded)
            event.remove(db.kw["bind"], "after_cursor_execute", executed)
        assert listing.status_code == 200
        assert len(listing.json()["items"]) == 10
        assert {item["outcome"] for item in listing.json()["items"]} == {"request_review"}
        record_property("list_full_report_document_bytes_materialized", sum(document_bytes))
        record_property("list_sql_statements_including_auth", len(statements))
        from proofops.api import app as app_module

        with patch.object(app_module, "load_trusted", wraps=app_module.load_trusted) as load:
            detail = client.get(f"/api/v1/reviews/{ids[0]}")
        assert detail.status_code == 200
        record_property("detail_trusted_revision_reads", load.call_count)


def test_measure_deterministic_review(valid_bundle, trusted, record_property):
    durations = []
    hashes = set()
    for _ in range(30):
        start = perf_counter()
        report = review(valid_bundle, trusted, review_id="offline-measurement")
        durations.append((perf_counter() - start) * 1000)
        hashes.add(digest(report))
    assert len(hashes) == 1
    assert report.outcome == "request_review"
    record_property("engine_samples", len(durations))
    record_property("engine_median_ms", round(median(durations), 4))
    record_property("engine_p95_ms", round(sorted(durations)[28], 4))
