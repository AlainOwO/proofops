from datetime import datetime
from decimal import Decimal
from typing import Any

from proofops.domain.schemas import Finding, ReviewInput, ServiceContract


def compare_workloads(
    bundle: ReviewInput, contract: ServiceContract, reference: datetime
) -> tuple[dict[str, Any], list[Finding]]:
    findings: list[Finding] = []
    requirements = contract.requirements
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    roles: dict[str, int] = {"baseline": 0, "candidate": 0}
    platforms = {run.platform for run in bundle.workload_runs}
    warmups = {run.warmup_policy for run in bundle.workload_runs}
    for run in bundle.workload_runs:
        role_config = bundle.change.before if run.role == "baseline" else bundle.change.after
        age = (reference - run.ended_at).total_seconds()
        compatible = bool(
            role_config
            and run.scope == contract.scope
            and run.environment == contract.scope.environment
            and run.image_digest == role_config.image_digest == contract.applicability.image_digest
            and run.config_hash == role_config.config_hash
            and run.non_resize_config_hash
            == role_config.non_resize_config_hash
            == contract.applicability.non_resize_config_hash
            and run.profile_hash == contract.applicability.workload_profile_hash
            and run.dependency_hash == contract.applicability.dependency_state_hash
            and len(platforms) == 1
            and len(warmups) == 1
        )
        reasons: list[str] = []
        if run.run_id in seen:
            reasons.append("duplicate run ID")
            compatible = False
        seen.add(run.run_id)
        if not compatible:
            findings.append(
                Finding(
                    code="INCOMPARABLE_WORKLOADS",
                    severity="missing",
                    message=f"{run.run_id}: image, configuration, profile, dependency, environment or population does not match.",
                )
            )
            reasons.append("incompatible workload")
        fresh = 0 <= age <= requirements.max_evidence_age_seconds
        if not fresh:
            findings.append(
                Finding(
                    code="EVIDENCE_STALE" if age > 0 else "EVIDENCE_TIME_INVALID",
                    severity="missing",
                    message=f"{run.run_id}: workload evidence is stale or later than the evaluation time.",
                )
            )
            reasons.append("invalid time basis")
        sufficient = (
            run.correct >= requirements.min_correct_requests_per_run
            and run.terminal_status == "completed"
            and run.offered == run.completed + run.dropped_iterations
        )
        if not sufficient:
            findings.append(
                Finding(
                    code="INSUFFICIENT_REQUEST_SAMPLE",
                    severity="missing",
                    message=f"{run.run_id}: requires {requirements.min_correct_requests_per_run} correct responses and completed offered work.",
                )
            )
            reasons.append("insufficient completed work")
        if (
            set(run.request_classes) != {"small", "medium", "large"}
            or any(
                item.completed == 0 or item.p95_latency_ms is None
                for item in run.request_classes.values()
            )
            or run.p95_latency_ms is None
        ):
            findings.append(
                Finding(
                    code="REQUIRED_EVIDENCE_MISSING",
                    severity="missing",
                    message=f"{run.run_id}: latency distributions and all request classes are required.",
                )
            )
            sufficient = False
        violated: list[str] = []
        if compatible and fresh:
            if run.incorrect_successful_responses > requirements.max_incorrect_successful_responses:
                violated.append("incorrect successful responses")
            if run.dropped_iterations > requirements.max_dropped_iterations:
                violated.append("dropped iterations")
            if run.restarts > requirements.max_restarts:
                violated.append("restarts")
            if sufficient:
                if (
                    run.p95_latency_ms is not None
                    and run.p95_latency_ms >= requirements.max_p95_latency_ms
                ):
                    violated.append("p95 latency")
                if any(
                    item.p95_latency_ms is not None
                    and item.p95_latency_ms >= requirements.max_p95_latency_ms
                    for item in run.request_classes.values()
                ):
                    violated.append("request-class p95 latency")
                if (
                    run.completed
                    and Decimal(run.http_failures) / run.completed
                    >= requirements.max_http_failure_rate_exclusive
                ):
                    violated.append("HTTP failure rate")
            if violated:
                findings.append(
                    Finding(
                        code="PERFORMANCE_CONTRACT_BREACH",
                        severity="violation",
                        message=f"{run.run_id}: breached {', '.join(violated)}.",
                    )
                )
        valid = compatible and fresh and sufficient
        if valid:
            roles[run.role] += 1
        results.append(
            {
                "run_id": run.run_id,
                "role": run.role,
                "valid_evidence": valid,
                "passed": valid and not violated,
                "reasons": reasons + violated,
                "correct": run.correct,
                "completed": run.completed,
                "offered": run.offered,
                "p95_latency_ms": str(run.p95_latency_ms)
                if run.p95_latency_ms is not None
                else None,
                "http_failures": run.http_failures,
                "dropped_iterations": run.dropped_iterations,
                "restarts": run.restarts,
                "origin": run.origin.value,
                "request_classes": {
                    key: value.model_dump(mode="json") for key, value in run.request_classes.items()
                },
            }
        )
    for role, count in roles.items():
        if count < requirements.required_repetitions:
            findings.append(
                Finding(
                    code="REQUIRED_EVIDENCE_MISSING",
                    severity="missing",
                    message=f"{role}: {count} valid repetitions; {requirements.required_repetitions} required.",
                )
            )
    return {
        "comparable": not any(f.code == "INCOMPARABLE_WORKLOADS" for f in findings),
        "complete": not any(f.severity == "missing" for f in findings),
        "passed": not findings,
        "valid_repetitions": roles,
        "runs": results,
        "aggregation": "Per-run and per-class checks; p95 values are never averaged.",
    }, findings
