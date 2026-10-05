from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from proofops.domain.common import canonical, strict_json, utcnow
from proofops.domain.schemas import Nonnegative, Record
from proofops.storage.database import AttemptRow, BudgetRow, LedgerRow, identifier, session_factory

ZERO = Decimal("0")


class BudgetUnavailable(ValueError):
    pass


class Price(Record):
    provider: str
    model: str
    currency: str = "USD"
    as_of: datetime
    source_url: str
    input_per_million: Nonnegative
    cached_input_per_million: Nonnegative
    cache_write_per_million: Nonnegative
    output_per_million: Nonnegative
    structured_outputs: bool
    max_input_bytes: int = Field(default=24000, ge=1024, le=64000)


def load_price(path, provider: str, model: str) -> Price:
    records = strict_json(path.read_bytes())
    matches = [
        item
        for item in records.get("models", [])
        if item.get("provider") == provider and item.get("model") == model
    ]
    if len(matches) != 1:
        raise BudgetUnavailable("an exact dated model price entry is required")
    price = Price.model_validate(matches[0])
    official = (
        ("https://developers.openai.com/", "https://platform.openai.com/")
        if provider == "openai"
        else ("https://platform.claude.com/",)
    )
    if (
        price.currency != "USD"
        or not price.structured_outputs
        or not price.source_url.startswith(official)
    ):
        raise BudgetUnavailable("unsupported pricing currency, capability or source")
    age = (utcnow() - price.as_of).total_seconds()
    if age < 0 or age > 31 * 86400:
        raise BudgetUnavailable("model price table is future-dated or older than 31 days")
    return price


def maximum_cost(price: Price, system: str, user: str, schema: dict, max_output: int) -> Decimal:
    size = len(system.encode()) + len(user.encode()) + len(canonical(schema))
    if size > price.max_input_bytes:
        raise BudgetUnavailable("prepared context exceeds the priced input cap")
    # UTF-8 bytes conservatively bound byte-tokenized input; include framing/schema
    # overhead. No hosted tools, cache writes or unbounded reasoning are enabled.
    tokens = size + 4096
    rate = max(
        price.input_per_million, price.cached_input_per_million, price.cache_write_per_million
    )
    return ((tokens * rate + max_output * price.output_per_million) / 1_000_000).quantize(
        Decimal(".000000000001"), rounding=ROUND_CEILING
    )


def actual_cost(price: Price, usage: dict[str, int] | None) -> Decimal | None:
    if usage is None:
        return None
    required = {"input_uncached", "cache_read", "cache_write", "output"}
    if not required.issubset(usage) or any(
        type(usage[key]) is not int or usage[key] < 0 for key in required
    ):
        return None
    amount = (
        usage["input_uncached"] * price.input_per_million
        + usage["cache_read"] * price.cached_input_per_million
        + usage["cache_write"] * price.cache_write_per_million
        + usage["output"] * price.output_per_million
    ) / 1_000_000
    return amount.quantize(Decimal(".000000000001"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class Reservation:
    attempt_id: str
    created: bool
    state: str
    amount: Decimal


class BudgetLedger:
    def __init__(self, factory=None):
        self.factory = factory or session_factory()

    def reserve(
        self,
        *,
        budget_id: str,
        limit: Decimal,
        amount: Decimal,
        task_key: str,
        provider: str,
        model: str,
        input_hash: str,
        review_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Reservation:
        if not limit.is_finite() or not amount.is_finite() or limit <= 0 or amount < 0:
            raise BudgetUnavailable("a finite positive explicit budget is required")
        with self.factory.begin() as session:
            session.execute(
                insert(BudgetRow)
                .values(id=budget_id, limit=limit, reserved=ZERO, spent=ZERO)
                .on_conflict_do_nothing(index_elements=[BudgetRow.id])
            )
            budget = session.execute(
                select(BudgetRow).where(BudgetRow.id == budget_id).with_for_update()
            ).scalar_one()
            existing = session.execute(
                select(AttemptRow).where(AttemptRow.task_key == task_key)
            ).scalar_one_or_none()
            if existing:
                if (existing.input_hash, existing.provider, existing.model, existing.budget_id) != (
                    input_hash,
                    provider,
                    model,
                    budget_id,
                ):
                    raise ValueError("attempt idempotency key conflicts with different input")
                return Reservation(existing.id, False, existing.state, existing.reserved_cost)
            # The configured limit may decrease; a restart never silently increases
            # an existing budget or resets already spent/reserved money.
            permitted = min(budget.limit, limit)
            if budget.spent + budget.reserved + amount > permitted:
                raise BudgetUnavailable("remaining reserved budget is insufficient")
            attempt_id = identifier()
            session.add(
                AttemptRow(
                    id=attempt_id,
                    task_key=task_key,
                    budget_id=budget_id,
                    review_id=review_id,
                    state="reserved",
                    provider=provider,
                    model=model,
                    input_hash=input_hash,
                    reserved_cost=amount,
                    metadata_json=metadata or {},
                )
            )
            budget.reserved += amount
            session.flush()
            session.add(LedgerRow(attempt_id=attempt_id, event="reserve", amount=amount))
            return Reservation(attempt_id, True, "reserved", amount)

    def dispatch(self, attempt_id: str) -> bool:
        with self.factory.begin() as session:
            attempt = session.execute(
                select(AttemptRow).where(AttemptRow.id == attempt_id).with_for_update()
            ).scalar_one()
            if attempt.state != "reserved":
                return False
            attempt.state = "dispatched"
            session.add(LedgerRow(attempt_id=attempt_id, event="dispatch", amount=ZERO))
            return True

    def reconcile(
        self, attempt_id: str, cost: Decimal | None, metadata: dict, terminal: str
    ) -> None:
        with self.factory.begin() as session:
            identity = session.get(AttemptRow, attempt_id)
            if identity is None:
                raise ValueError("unknown model attempt")
            # Use the same budget -> attempt lock order as reservation.
            budget = session.execute(
                select(BudgetRow).where(BudgetRow.id == identity.budget_id).with_for_update()
            ).scalar_one()
            attempt = session.execute(
                select(AttemptRow).where(AttemptRow.id == attempt_id).with_for_update()
            ).scalar_one()
            if attempt.actual_cost is not None:
                if attempt.actual_cost != cost:
                    raise ValueError("completed attempt cannot be reconciled to a different cost")
                return
            attempt.metadata_json = {
                **attempt.metadata_json,
                **metadata,
                "terminal_status": terminal,
            }
            if cost is None:
                attempt.state = "uncertain"
                session.add(
                    LedgerRow(
                        attempt_id=attempt_id,
                        event="uncertain_pending",
                        amount=attempt.reserved_cost,
                    )
                )
                return
            if not cost.is_finite() or cost < 0:
                raise ValueError("actual cost must be finite and nonnegative")
            budget.reserved -= attempt.reserved_cost
            budget.spent += cost
            attempt.actual_cost = cost
            attempt.state = "reconciled"
            attempt.completed_at = utcnow()
            attempt.metadata_json = {
                **attempt.metadata_json,
                "reservation_exceeded": cost > attempt.reserved_cost,
            }
            session.add(LedgerRow(attempt_id=attempt_id, event="reconcile", amount=cost))
