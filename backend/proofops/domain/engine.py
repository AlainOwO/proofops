from datetime import datetime
from typing import Literal

from proofops.domain.common import digest, utcnow
from proofops.domain.costs import estimate_cost
from proofops.domain.performance import compare_workloads
from proofops.domain.schemas import Fact, Finding, Outcome, ReviewInput, ReviewReport
from proofops.policies.guards import TrustedRevision, applicability, valid_exception


def review(
    bundle: ReviewInput,
    trusted: TrustedRevision,
    *,
    review_id: str = "local-review",
    mode: Literal["replay", "live"] = "replay",
    reference: datetime | None = None,
) -> ReviewReport:
    reference = reference or (bundle.reference_time if mode == "replay" else utcnow())
    contract, change = trusted.contract, bundle.change
    findings: list[Finding] = []
    facts: list[Fact] = []
    source_states: dict = {}
    trusted_contract = digest(bundle.contract) == digest(contract)
    scoped = change.service_map.scope == contract.scope
    applicable = scoped and applicability(bundle, trusted)

    def add(
        code: str,
        severity: Literal["violation", "missing", "info", "unsupported"],
        message: str,
        ids: list[str] | None = None,
    ) -> None:
        findings.append(Finding(code=code, severity=severity, message=message, fact_ids=ids or []))

    for code in change.normalization_findings:
        severity: Literal["violation", "missing", "info", "unsupported"] = (
            "missing"
            if code == "TERRAFORM_VALUE_UNKNOWN"
            else "unsupported"
            if code.startswith("UNSUPPORTED")
            else "info"
        )
        add(
            code,
            severity,
            {
                "TERRAFORM_VALUE_UNKNOWN": "A required task allocation is unknown, sensitive or not a strictly supported numeric representation.",
                "UNSUPPORTED_RESOURCE_SHAPE": "This plan contains no supported like-for-like mapped task update for the declared platform.",
                "UNSUPPORTED_FARGATE_COMBINATION": "The CPU/memory pair is outside the versioned supported Linux Fargate table.",
                "SENSITIVE_FIELDS_REDACTED": "Sensitive fields were excluded before persistence and provider submission.",
                "TASK_ALLOCATION_UNCHANGED": "Task CPU and memory are unchanged; a container-only change creates no task allocation saving.",
            }.get(code, code),
        )
    if not trusted_contract:
        add(
            "CONTRACT_NOT_TRUSTED",
            "missing",
            "The imported contract differs from the trusted revision; it cannot replace the enforcing bound or scope.",
        )
    if scoped and change.applicable_resource and not applicable:
        add(
            "APPLICABILITY_CHANGED",
            "missing",
            "Image, configuration or workload applicability changed; collect evidence and obtain a separately reviewed contract revision.",
        )
    if mode == "live" and (
        bundle.origin != "aws_observation" or contract.origin == "synthetic_fixture"
    ):
        add(
            "LIVE_PROVENANCE_REQUIRED",
            "missing",
            "Synthetic/local evidence and fixture approvals cannot support a live AWS review.",
        )
    if applicable and trusted.guard.state in {"active", "approved_in_trusted_revision"}:
        exception = valid_exception(bundle, trusted, reference)
        after = change.after
        if after and after.memory_mib is not None:
            facts.extend(
                [
                    Fact(
                        fact_id="candidate.task_memory_mib",
                        value=after.memory_mib,
                        kind="configuration",
                    ),
                    Fact(
                        fact_id="approved.minimum_task_memory_mib",
                        value=trusted.guard.minimum_task_memory_mib,
                        kind="approved_constraint",
                    ),
                    Fact(
                        fact_id="incident.repair_verified",
                        value=trusted.guard.repair_reference,
                        kind="approved_incident_reference",
                    ),
                ]
            )
            if exception:
                add(
                    "SCOPED_EXCEPTION_ACTIVE",
                    "info",
                    f"Reviewed exception {exception.exception_id} applies until {exception.expires_at.isoformat()}.",
                )
            elif after.memory_mib < trusted.guard.minimum_task_memory_mib:
                add(
                    "APPROVED_MEMORY_FLOOR_BREACH",
                    "violation",
                    "The candidate is below the applicable approved task memory floor.",
                    ["candidate.task_memory_mib", "approved.minimum_task_memory_mib"],
                )
        else:
            add(
                "TERRAFORM_VALUE_UNKNOWN",
                "missing",
                "The scoped guard cannot evaluate unknown task memory.",
            )
    elif scoped and trusted.guard.state not in {"active", "approved_in_trusted_revision"}:
        add(
            "GUARD_NOT_APPROVED",
            "missing",
            "A draft or fixture-passed guard is not an approved enforcing revision.",
        )
    for kind in contract.requirements.required_sources:
        if kind == "terraform":
            source_states[kind] = {
                "collection": "complete",
                "freshness": "fresh",
                "coverage": "sufficient" if change.supported else "unsupported",
            }
            continue
        matching = [
            item for item in bundle.evidence if item.kind == kind and item.scope == contract.scope
        ]
        records = []
        sufficient = False
        for item in matching:
            age = (reference - item.observed_end).total_seconds()
            freshness = (
                "fresh"
                if 0 <= age <= contract.requirements.max_evidence_age_seconds
                else "stale"
                if age > 0
                else "unknown"
            )
            revision_matches = item.resource_revision == change.service_map.candidate_commit
            if item.source == "aws_ecs":
                baseline = change.before
                revision_matches = bool(
                    baseline
                    and baseline.task_definition_arn
                    and item.resource_revision == baseline.task_definition_arn
                    and item.metadata.get("cpu_units") == baseline.cpu_units
                    and item.metadata.get("memory_mib") == baseline.memory_mib
                    and item.metadata.get("image_digest") == baseline.image_digest
                    and item.metadata.get("architecture") == baseline.architecture
                    and item.metadata.get("os") == baseline.os
                    and item.metadata.get("requires_fargate") is True
                    and item.metadata.get("task_population_complete") is True
                )
            complete = (
                item.collection_status == "complete"
                and item.sample_count is not None
                and item.sample_count > 0
                and freshness == "fresh"
                and item.collected_at <= reference
                and revision_matches
                and item.population == "mapped_service"
                and item.units == "records"
            )
            if mode == "live" and item.origin != "aws_observation":
                complete = False
            sufficient |= complete
            records.append(
                {
                    "id": item.evidence_id,
                    "collection": item.collection_status,
                    "freshness": freshness,
                    "coverage": "sufficient" if complete else "insufficient",
                    "origin": item.origin.value,
                    "observed_end": item.observed_end.isoformat(),
                    "source": item.source,
                }
            )
            if freshness != "fresh":
                add(
                    "EVIDENCE_STALE" if freshness == "stale" else "EVIDENCE_TIME_INVALID",
                    "missing",
                    f"{kind}: source window does not meet the evaluation time basis.",
                )
        source_states[kind] = {
            "coverage": "sufficient" if sufficient else "insufficient",
            "records": records,
        }
        if not sufficient:
            add(
                "REQUIRED_EVIDENCE_MISSING",
                "missing",
                f"{kind}: require complete, nonempty, current evidence for the exact service and candidate.",
            )
    cost = estimate_cost(bundle, live=mode == "live") if change.applicable_resource else None
    if cost:
        add(
            "COST_COVERAGE_PARTIAL",
            "info",
            "The estimate covers task CPU/memory only; excluded charges and task-hours assumptions are shown separately.",
        )
        if not cost.complete:
            add(
                "REQUIRED_COST_INPUT_MISSING",
                "missing",
                "Compatible dated prices and explicit baseline/candidate billable task-hours are required.",
            )
        if cost.projected_difference is not None:
            facts.append(
                Fact(
                    fact_id="estimate.compute_difference",
                    value=str(cost.projected_difference),
                    kind="cost_estimate",
                )
            )
    performance, performance_findings = compare_workloads(bundle, contract, reference)
    findings.extend(performance_findings)
    # Keep arithmetic tied to the identical measured window and population. A
    # monthly projection is never divided by a short benchmark's request count.
    if cost and performance["passed"]:
        for role in ("baseline", "candidate"):
            runs = [run for run in bundle.workload_runs if run.role == role]
            matches = [
                run
                for run in runs
                if run.started_at == bundle.usage.window_start
                and run.ended_at == bundle.usage.window_end
            ]
            amount = cost.baseline_amount if role == "baseline" else cost.candidate_amount
            cost.cost_per_correct_request[role] = (
                str(amount / matches[0].correct)
                if len(matches) == 1 and amount is not None and matches[0].correct
                else None
            )
    if any(item.severity == "violation" for item in findings):
        outcome = Outcome.REVISE
    elif (
        not change.applicable_resource
        or not scoped
        or (
            not change.supported
            and not any(item.code == "TERRAFORM_VALUE_UNKNOWN" for item in findings)
        )
    ):
        outcome = Outcome.OUT
    elif any(item.severity == "missing" for item in findings):
        outcome = Outcome.COLLECT
    else:
        outcome = Outcome.REVIEW
    next_steps = {
        Outcome.REVISE: [
            "Revise the change to satisfy the applicable approved constraints and performance contract.",
            "Resolve the listed evidence gaps before requesting engineering review.",
        ],
        Outcome.COLLECT: [
            "Collect the listed compatible evidence and rerun this exact candidate against the trusted contract."
        ],
        Outcome.REVIEW: [
            "Request engineering review of this candidate and its evidence bundle; no deployment is authorized by this result."
        ],
        Outcome.OUT: [
            "Use a review method that supports this resource, platform and scope; this is a coverage result."
        ],
    }[outcome]
    facts.append(Fact(fact_id="review.outcome", value=outcome.value, kind="deterministic_finding"))
    required = [item.fact_id for item in facts]
    return ReviewReport(
        review_id=review_id,
        input_hashes=bundle.input_hashes,
        input_digest=digest(bundle),
        trusted_revision_hash=trusted.revision_hash,
        evaluation_reference_time=reference,
        mode=mode,
        origin=bundle.origin,
        outcome=outcome,
        findings=findings,
        coverage={
            "supported": change.supported and scoped,
            "trusted_contract": trusted_contract,
            "guard_applicable": applicable,
            "sources": source_states,
            "time_basis": "recorded_replay" if mode == "replay" else "current_time",
        },
        cost=cost,
        performance=performance,
        facts=facts,
        required_citations=required,
        next_steps=next_steps,
        change=change,
        contract_revision=contract.revision,
    )
