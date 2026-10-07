import csv
import io
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from proofops.domain.common import bytes_digest, digest
from proofops.storage.database import (
    AttemptRow,
    AuditRow,
    BillingImportRow,
    BillingRow,
    OutcomeRow,
    ReportRow,
)


def parse_amount(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid billing decimal") from exc
    if (
        not amount.is_finite()
        or abs(amount) >= Decimal("1e15")
        or int(amount.as_tuple().exponent) < -16
    ):
        raise ValueError("billing decimal exceeds supported precision/range")
    return amount


def ingest_costs(
    session, raw: bytes, dataset: str = "focus-sample", *, actor: str = "host-operator"
) -> dict:
    if not 1 <= len(dataset) <= 120:
        raise ValueError("billing dataset label must contain 1 to 120 characters")
    if len(raw) > 5_242_880:
        raise OverflowError("billing file exceeds 5 MiB")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"ProviderName", "ServiceName", "BillingCurrency", "BilledCost", "EffectiveCost"}
    if (
        not reader.fieldnames
        or not required.issubset(reader.fieldnames)
        or len(set(reader.fieldnames)) != len(reader.fieldnames)
    ):
        raise ValueError("billing CSV requires unique FOCUS accounting columns")
    import_id = digest({"dataset": dataset, "file_hash": bytes_digest(raw)})
    rows = []
    for position, row in enumerate(reader):
        if position >= 10_000:
            raise OverflowError("billing import exceeds 10,000 rows")
        currency = row["BillingCurrency"]
        if not re.fullmatch(r"[A-Z]{3}", currency or ""):
            raise ValueError("invalid billing currency")
        provider, service = row["ProviderName"], row["ServiceName"]
        if not provider or not service or len(provider) > 120 or len(service) > 200:
            raise ValueError("invalid billing provider/service label")
        rows.append(
            {
                "id": digest({"import": import_id, "position": position}),
                "import_id": import_id,
                "position": position,
                "provider": provider,
                "service": service,
                "currency": currency,
                "billed": parse_amount(row["BilledCost"]),
                "effective": parse_amount(row["EffectiveCost"]),
                "raw_reference": f"{import_id}:{position}",
            }
        )
    added = session.execute(
        insert(BillingImportRow)
        .values(id=import_id, dataset=dataset, origin="benchmark")
        .on_conflict_do_nothing(index_elements=[BillingImportRow.id])
        .returning(BillingImportRow.id)
    ).scalar_one_or_none()
    if added and rows:
        session.execute(insert(BillingRow), rows)
    session.add(
        AuditRow(
            scope="billing",
            kind="billing_imported",
            actor=actor,
            data={"import_id": import_id, "status": "created" if added else "existing"},
        )
    )
    return {
        "import_id": import_id,
        "rows": len(rows),
        "created": bool(added),
        "origin": "benchmark",
    }


def billing_analytics(session) -> dict:
    def amount(value):
        return str(value) if value is not None else None

    groups = session.execute(
        select(
            BillingRow.provider,
            BillingRow.service,
            BillingRow.currency,
            func.count(BillingRow.id),
            func.sum(BillingRow.billed),
            func.sum(BillingRow.effective),
            func.count(BillingRow.billed),
            func.count(BillingRow.effective),
        )
        .group_by(BillingRow.provider, BillingRow.service, BillingRow.currency)
        .order_by(BillingRow.currency, BillingRow.provider, BillingRow.service)
    ).all()
    totals = session.execute(
        select(
            BillingRow.currency,
            func.count(BillingRow.id),
            func.sum(BillingRow.billed),
            func.sum(BillingRow.effective),
            func.count().filter(BillingRow.billed < 0),
        )
        .group_by(BillingRow.currency)
        .order_by(BillingRow.currency)
    ).all()
    return {
        "basis": "sample_billing_rows",
        "origin": "benchmark",
        "not_demo_service_bill": True,
        "totals": [
            {
                "currency": row[0],
                "rows": row[1],
                "billed": amount(row[2]),
                "effective": amount(row[3]),
                "negative_billed_rows": row[4],
            }
            for row in totals
        ],
        "groups": [
            {
                "provider": row[0],
                "service": row[1],
                "currency": row[2],
                "rows": row[3],
                "billed": amount(row[4]),
                "effective": amount(row[5]),
                "billed_nulls": row[3] - row[6],
                "effective_nulls": row[3] - row[7],
            }
            for row in groups
        ],
        "note": "BilledCost and EffectiveCost are separate accounting measures; their difference is not savings.",
    }


def review_analytics(session) -> dict:
    counts = dict(
        session.execute(
            select(ReportRow.outcome, func.count(ReportRow.id)).group_by(ReportRow.outcome)
        ).all()
    )
    reports = session.execute(
        select(
            ReportRow.id,
            ReportRow.outcome,
            ReportRow.core["origin"].as_string().label("origin"),
            ReportRow.core["cost"].label("cost"),
            ReportRow.core["evaluation_reference_time"].as_string().label("evaluated_at"),
        )
        .order_by(ReportRow.created_at.desc())
        .limit(100)
    ).all()
    outcomes = (
        session.execute(select(OutcomeRow).order_by(OutcomeRow.created_at.desc()).limit(100))
        .scalars()
        .all()
    )
    attempts = (
        session.execute(select(AttemptRow).order_by(AttemptRow.created_at.desc()).limit(1000))
        .scalars()
        .all()
    )
    actual = sum(
        (item.actual_cost for item in attempts if item.actual_cost is not None), Decimal(0)
    )
    pending = sum((item.reserved_cost for item in attempts if item.actual_cost is None), Decimal(0))
    latencies = sorted(
        float(item.metadata_json["latency_seconds"])
        for item in attempts
        if "latency_seconds" in item.metadata_json
    )

    def quantile(fraction):
        return (
            latencies[min(int((len(latencies) - 1) * fraction), len(latencies) - 1)]
            if latencies
            else None
        )

    return {
        "review_counts": counts,
        "review_count": sum(counts.values()),
        "projected_comparisons": [
            {
                "review_id": item.id,
                "origin": item.origin,
                "outcome": item.outcome,
                "cost": item.cost,
                "evaluated_at": item.evaluated_at,
            }
            for item in reports
        ],
        "observed_outcomes": [
            {"id": item.id, "review_id": item.review_id, **item.data} for item in outcomes
        ],
        "model": {
            "attempts": len(attempts),
            "actual_usd": str(actual),
            "pending_reserved_usd": str(pending),
            "p50_seconds": quantile(0.5),
            "p95_seconds": quantile(0.95),
            "basis": "latest 1000 recorded attempts, including failures; empty is unrun",
        },
        "bounds": "Latest 100 review comparisons and outcomes. Projected differences are alternatives and are not summed into realized savings.",
    }
