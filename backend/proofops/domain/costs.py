from decimal import Decimal, localcontext

from proofops.domain.schemas import CostEstimate, ReviewInput

EXCLUDED = [
    "network",
    "load_balancer",
    "storage",
    "logs",
    "test_overhead",
    "tax",
    "commitment_effects",
]


def estimate_cost(bundle: ReviewInput, *, live: bool = False) -> CostEstimate:
    card, usage, change = bundle.rates, bundle.usage, bundle.change
    matching = bool(
        change.before
        and change.after
        and card.region == bundle.contract.scope.region
        and change.before.architecture == change.after.architecture == card.architecture
        and change.before.os == change.after.os == card.os
    )
    if live and (
        card.origin == "synthetic_fixture"
        or not card.source_url.startswith("https://aws.amazon.com/")
    ):
        matching = False
    amounts: list[Decimal | None] = []
    for config, hours in (
        (change.before, usage.baseline_task_hours),
        (change.after, usage.candidate_task_hours),
    ):
        if (
            not matching
            or config is None
            or config.cpu_units is None
            or config.memory_mib is None
            or hours is None
            or card.price_per_vcpu_hour is None
            or card.price_per_gib_hour is None
        ):
            amounts.append(None)
        else:
            with localcontext() as ctx:
                ctx.prec = 32
                value = hours * (
                    Decimal(config.cpu_units) / 1024 * card.price_per_vcpu_hour
                    + Decimal(config.memory_mib) / 1024 * card.price_per_gib_hour
                )
                amounts.append(value.quantize(Decimal("0.0000000000000001")))
    baseline, candidate = amounts
    complete = baseline is not None and candidate is not None
    difference = baseline - candidate if complete else None  # type: ignore[operator]
    fraction = difference / baseline if baseline and difference is not None else None
    assumptions = list(usage.assumptions) + [
        "Only requested task CPU and memory charges are estimated.",
        f"Billing: {card.billing_granularity_seconds}-second granularity with {card.billing_minimum_seconds}-second minimum per task; explicit task-hours must include billable runtime.",
        "This is not an invoice or realized whole-account savings.",
    ]
    if baseline == 0:
        assumptions.append("Reduction percentage is undefined because baseline cost is zero.")
    if usage.baseline_task_hours != usage.candidate_task_hours:
        assumptions.append(
            "Task-hours differ; the estimate uses each configuration's explicit usage."
        )
    return CostEstimate(
        currency=card.currency,
        rate_id=card.rate_id,
        price_date=card.price_date,
        source_url=card.source_url,
        basis=usage.basis,
        region=card.region,
        os=card.os,
        architecture=card.architecture,
        purchase_option=card.purchase_option,
        baseline_task_hours=usage.baseline_task_hours,
        candidate_task_hours=usage.candidate_task_hours,
        baseline_amount=baseline,
        candidate_amount=candidate,
        projected_difference=difference,
        projected_reduction_fraction=fraction,
        covered=["task_cpu", "task_memory"],
        excluded=EXCLUDED,
        assumptions=assumptions,
        complete=complete,
        origin=card.origin,
    )
