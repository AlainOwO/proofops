from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from proofops.domain.common import digest, utcnow
from proofops.domain.engine import review
from proofops.models import context
from proofops.models.adapters import ModelResult
from proofops.models.explanations import template_explanation
from proofops.storage.database import AttemptRow, CacheRow
from sqlalchemy import func, select

from tests.integration.test_budget_jobs import setup_router

pytestmark = pytest.mark.integration


@pytest.fixture
def cached_router(db, valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    usage = {"input_uncached": 100, "cache_read": 0, "cache_write": 0, "output": 100}
    router, cheap, strong = setup_router(
        db, [ModelResult("completed", template_explanation(report)["output"], usage)]
    )
    return report, router, cheap, strong


def test_expired_cache_is_replaced_and_reused(db, cached_router):
    report, router, cheap, strong = cached_router
    first = router.explain(report, ai_preference="auto", task_id="first")
    assert first["status"] == "accepted"
    with db.begin() as session:
        session.get(CacheRow, first["cache_key"]).expires_at = utcnow() - timedelta(seconds=1)
    refreshed = router.explain(report, ai_preference="auto", task_id="refresh")
    reused = router.explain(report, ai_preference="auto", task_id="reuse")
    assert refreshed["status"] == "accepted"
    assert reused["status"] == "cached"
    assert reused["output"] == first["output"]
    assert reused["attempts"] == [] and reused["original_usage"] == refreshed["attempts"]
    assert reused["incremental_cost_usd"] == "0"
    assert cheap.calls == 2 and strong.calls == 0
    with db() as session:
        assert session.scalar(select(func.count(CacheRow.key))) == 1


@pytest.mark.parametrize("change", ["evidence", "prompt_version", "prompt", "tokens", "model"])
def test_changed_request_cannot_reuse_accepted_output(cached_router, monkeypatch, change):
    report, router, cheap, _ = cached_router
    first = router.explain(report, ai_preference="auto", task_id="first")
    if change == "evidence":
        report = report.model_copy(update={"input_digest": "f" * 64})
    elif change == "prompt_version":
        monkeypatch.setattr(context, "PROMPT_VERSION", "regression-new-prompt")
    elif change == "prompt":
        monkeypatch.setattr(context, "SYSTEM", context.SYSTEM + " Preserve the exact facts.")
    elif change == "tokens":
        router.settings.model_max_output_tokens += 1
    else:
        old = router.settings.cheap_model
        router.settings.cheap_model = "mock-cheap-next"
        router.prices[("openai", "mock-cheap-next")] = router.prices[("openai", old)].model_copy(
            update={"model": "mock-cheap-next"}
        )
    before = digest(report)
    second = router.explain(report, ai_preference="auto", task_id="second")
    assert second["status"] == "accepted" and cheap.calls == 2
    assert first["cache_key"] != second["cache_key"]
    assert digest(report) == before


def test_cache_can_be_disabled_without_disabling_validation(db, cached_router):
    report, router, cheap, _ = cached_router
    router.settings.ai_cache_enabled = False
    for task_id in ("first", "second"):
        assert router.explain(report, ai_preference="auto", task_id=task_id)["status"] == "accepted"
    assert cheap.calls == 2
    with db() as session:
        assert session.scalar(select(func.count(CacheRow.key))) == 0


def test_shorter_ttl_and_invalid_cached_output_force_fresh_validation(db, cached_router):
    report, router, cheap, _ = cached_router
    first = router.explain(report, ai_preference="auto", task_id="first")
    router.settings.ai_cache_ttl_seconds = 1
    with db.begin() as session:
        session.get(CacheRow, first["cache_key"]).created_at = utcnow() - timedelta(seconds=2)
    assert router.explain(report, ai_preference="auto", task_id="shorter")["status"] == "accepted"
    with db.begin() as session:
        row = session.get(CacheRow, first["cache_key"])
        row.data = {**row.data, "output": {"next_step": "deploy_now"}}
    fixed = router.explain(report, ai_preference="auto", task_id="invalid-cache")
    assert fixed["status"] == "accepted" and fixed["output"]["next_step"] == "request_review"
    assert cheap.calls == 3


def test_concurrent_identical_requests_do_not_duplicate_provider_dispatch(cached_router):
    report, router, cheap, _ = cached_router
    entered, release = Event(), Event()
    generate = cheap.generate_structured

    def blocked(**kwargs):
        entered.set()
        assert release.wait(5)
        return generate(**kwargs)

    cheap.generate_structured = blocked
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(router.explain, report, ai_preference="auto", task_id="first")
        assert entered.wait(5)
        try:
            second = pool.submit(
                router.explain, report, ai_preference="auto", task_id="second"
            ).result(3)
            assert second["status"] == "explanation_unavailable"
            assert (
                second["attempts"] == []
                and second["fallback"]["output"]["next_step"] == report.outcome
            )
        finally:
            release.set()
        assert first.result(5)["status"] == "accepted"
    assert router.explain(report, ai_preference="auto", task_id="third")["status"] == "cached"
    assert cheap.calls == 1


def test_budget_exhaustion_and_ai_off_do_not_dispatch_or_change_report(db, cached_router):
    report, router, cheap, strong = cached_router
    before = digest(report)
    router.settings.ai_budget_usd = "0"
    denied = router.explain(report, ai_preference="auto")
    assert denied["status"] == "explanation_unavailable"
    router.settings.ai_mode = "off"
    assert router.explain(report, ai_preference="auto")["status"] == "template"
    assert cheap.calls == strong.calls == 0 and digest(report) == before
    with db() as session:
        assert session.scalar(select(func.count(AttemptRow.id))) == 0
