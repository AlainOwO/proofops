from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from proofops.config import Settings
from proofops.domain.common import utcnow
from proofops.domain.engine import review
from proofops.models.adapters import ModelResult
from proofops.models.budget import BudgetLedger, BudgetUnavailable, Price
from proofops.models.explanations import template_explanation
from proofops.models.router import ModelRouter
from proofops.storage.database import AttemptRow, BudgetRow, JobRow
from proofops.storage.repository import claim_job, create_job, store_bundle
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def test_atomic_budget_reservations_and_duplicate_dispatch(db):
    ledger = BudgetLedger(db)

    def reserve(index):
        try:
            return ledger.reserve(
                budget_id="concurrent",
                limit=Decimal("1"),
                amount=Decimal(".4"),
                task_key=f"task-{index}",
                provider="openai",
                model="mock",
                input_hash="a" * 64,
            )
        except BudgetUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    accepted = [result for result in results if result is not None]
    assert len(accepted) == 2
    with db() as session:
        assert session.get(BudgetRow, "concurrent").reserved == Decimal(".8")
    first = accepted[0]
    assert ledger.dispatch(first.attempt_id)
    assert not ledger.dispatch(first.attempt_id)
    ledger.reconcile(first.attempt_id, None, {"error_class": "timeout_uncertain"}, "error")
    with db() as session:
        assert session.get(BudgetRow, "concurrent").reserved == Decimal(".8")
        assert session.get(AttemptRow, first.attempt_id).state == "uncertain"
    ledger.reconcile(first.attempt_id, Decimal(".1"), {"reconciled_from": "mock-usage"}, "error")
    ledger.reconcile(first.attempt_id, Decimal(".1"), {}, "error")
    with db() as session:
        row = session.get(BudgetRow, "concurrent")
        assert row.reserved == Decimal(".4") and row.spent == Decimal(".1")


def test_same_reservation_key_cannot_double_spend(db):
    ledger = BudgetLedger(db)
    arguments = dict(
        budget_id="same-key",
        limit=Decimal(1),
        amount=Decimal(".2"),
        task_key="same",
        provider="openai",
        model="mock",
        input_hash="a" * 64,
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ledger.reserve(**arguments), range(4)))
    assert sum(item.created for item in results) == 1
    assert len({item.attempt_id for item in results}) == 1


def test_job_claims_and_expired_lease_recovery(db, valid_bundle, trusted):
    with db.begin() as session:
        bundle, _ = store_bundle(session, valid_bundle)
        job, _ = create_job(
            session, bundle, trusted, key="claim-test", mode="replay", ai_preference="off"
        )
        job_id = job.id
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: claim_job(db, str(uuid4())), range(4)))
    assert [item for item in claimed if item] == [job_id]
    with db.begin() as session:
        session.get(JobRow, job_id).lease_until = utcnow() - timedelta(seconds=1)
    assert claim_job(db, "new-owner") == job_id
    with db() as session:
        assert session.get(JobRow, job_id).claimed_count == 2


class FakeAdapter:
    def __init__(self, results):
        self.results, self.calls = results, 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def setup_router(db, results, strong_results=None):
    settings = Settings(
        ai_mode="live",
        allowed_providers="openai,anthropic",
        cheap_model="mock-cheap",
        strong_model="mock-strong",
        ai_budget_usd="10",
        ai_max_task_cost_usd="1",
    )
    cheap = FakeAdapter(results)
    strong = FakeAdapter(strong_results or results)
    prices = {}
    for provider, model in [("openai", "mock-cheap"), ("anthropic", "mock-strong")]:
        prices[(provider, model)] = Price(
            provider=provider,
            model=model,
            as_of=utcnow(),
            source_url="https://developers.openai.com/api/docs/pricing",
            input_per_million=Decimal(".1"),
            cached_input_per_million=Decimal(".05"),
            cache_write_per_million=Decimal(".1"),
            output_per_million=Decimal(".5"),
            structured_outputs=True,
        )
    return (
        ModelRouter(
            settings,
            factory=db,
            adapters={"openai": cheap, "anthropic": strong},
            prices=prices,
            sleeper=lambda _: None,
        ),
        cheap,
        strong,
    )


def test_routing_bounded_attempts_cache_and_scope(db, valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    valid = template_explanation(report)["output"]
    usage = {"input_uncached": 100, "cache_read": 0, "cache_write": 0, "output": 100}
    router, cheap, strong = setup_router(
        db,
        [ModelResult("completed", {"bad": "schema"}, usage)],
        [ModelResult("completed", valid, usage)],
    )
    first = router.explain(report, ai_preference="auto", task_id="first")
    assert first["status"] == "accepted" and cheap.calls == strong.calls == 1
    assert len(first["attempts"]) == 2
    second = router.explain(report, ai_preference="auto", task_id="second", policy="strong_only")
    assert second["status"] == "cached" and second["incremental_cost_usd"] == "0"
    assert strong.calls == 1
    changed = report.model_copy(deep=True)
    changed.input_digest = "c" * 64
    changed.change.service_map.scope.account_id = "999988887777"
    third = router.explain(changed, ai_preference="auto", task_id="third", policy="strong_only")
    assert third["status"] == "accepted" and strong.calls == 2


@pytest.mark.parametrize("error", ["permanent_quota", "authentication", "timeout_uncertain"])
def test_nonretryable_and_uncertain_attempts(db, valid_bundle, trusted, error):
    report = review(valid_bundle, trusted)
    router, cheap, strong = setup_router(
        db,
        [
            ModelResult(
                "error",
                None,
                None,
                error_class=error,
                definitely_unbilled=error != "timeout_uncertain",
            )
        ],
    )
    result = router.explain(report, ai_preference="auto", task_id="permanent")
    assert cheap.calls == 1 and strong.calls == 0
    assert result["status"] == "explanation_unavailable"
    with db() as session:
        assert session.scalar(select(func.count(AttemptRow.id))) == 1
        if error == "timeout_uncertain":
            assert session.get(BudgetRow, "configured-local-USD").reserved > 0
