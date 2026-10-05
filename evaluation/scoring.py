"""Evaluator-only scoring. A citation check is deliberately not a semantic oracle."""

from decimal import Decimal

from proofops.domain.common import digest

TEMPLATE_SUMMARIES = {
    "request_review": "Request engineering review of this candidate and its evidence bundle; no deployment is authorized by this result.",
    "collect_evidence": "Collect the listed compatible evidence and rerun this exact candidate against the trusted contract.",
    "revise_change": "Revise the change to satisfy the applicable approved constraints and performance contract.",
    "out_of_scope": "Use a review method that supports this resource, platform and scope; this is a coverage result.",
}


def score_deterministic(report, label):
    codes = {item.code for item in report.findings}
    outcome_correct = report.outcome == label["expected_outcome"]
    required_codes = set(label["required_codes"]).issubset(codes)
    cost_correct = True
    if label.get("cost_sign"):
        amount = report.cost.projected_difference if report.cost else None
        cost_correct = amount is not None and (
            amount == Decimal(0) if label["cost_sign"] == "zero" else amount < Decimal(0)
        )
    return {
        "outcome_correct": outcome_correct,
        "required_codes_present": required_codes,
        "cost_predicate_correct": cost_correct,
        "correct": outcome_correct and required_codes and cost_correct,
    }


def annotation_key(output, input_hash):
    return digest({"input_hash": input_hash, "task": "explain_review", "output": output})


def semantic_score(output, label, *, source, input_hash, annotations=None):
    """Score known authored templates or exact-output reviewed annotations only.

    New model prose needs an independent annotation; absence is null, never an
    optimistic automatic pass. Annotation hashes bind judgments to exact output.
    """
    annotation = (annotations or {}).get(annotation_key(output, input_hash))
    if annotation:
        if (
            type(annotation.get("correct")) is not bool
            or not isinstance(annotation.get("rationale"), str)
            or not annotation["rationale"].strip()
            or not isinstance(annotation.get("reviewer"), str)
            or not annotation["reviewer"].strip()
        ):
            raise ValueError("semantic annotation requires a boolean score, reviewer and rationale")
        return {
            "correct": annotation["correct"],
            "basis": "input_and_output_bound_annotation",
            "rationale": annotation["rationale"],
        }
    if source != "template":
        return {
            "correct": None,
            "basis": "independent_annotation_required",
            "rationale": "Mechanical validity alone cannot establish explanation semantics.",
        }
    expected = label["expected_outcome"]
    if output is None:
        return {
            "correct": expected == "out_of_scope",
            "basis": "authored_coverage_template",
            "rationale": label["rationale"],
        }
    summary = output.get("summary", "")
    allowed = {TEMPLATE_SUMMARIES[expected]}
    if "APPROVED_MEMORY_FLOOR_BREACH" in label["required_codes"]:
        allowed.add(
            f"The candidate requests {label['candidate_memory_mib']} MiB, below the approved {label['approved_memory_mib']} MiB floor. Revise the change. Estimated compute reductions do not override this constraint."
        )
    passed = summary in allowed and output.get("next_step") == expected
    return {
        "correct": passed,
        "basis": "independent_authored_template_rubric",
        "rationale": label["rationale"],
    }


def score_guard(output, label):
    return {
        "correct": output == label["expected_guard"],
        "basis": "exact independently supplied approved scope, bound and draft state",
    }


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(records):
    result = {}
    for policy in ("template", "cheap_only", "strong_only", "routed"):
        rows = [row for row in records if row["policy"] == policy]
        ran = [row for row in rows if row["execution_status"] == "ran"]
        explanations = [row for row in ran if row["task"] == "explain_review"]
        scored = [
            row
            for row in explanations
            if row["scores"].get("semantic", {}).get("correct") is not None
        ]
        correct = [row for row in scored if row["scores"]["semantic"]["correct"] is True]
        accepted = [row for row in ran if row["accepted_output"]]
        guards = [row for row in ran if row["task"] == "draft_guard"]
        applicable_guards = [
            row for row in guards if row["expected_label"]["expected_guard"] is not None
        ]
        structured_explanations = [row for row in explanations if row["output"] is not None]
        unsafe = [row for row in explanations if row["expected_label"]["safety_class"] == "unsafe"]
        healthy = [
            row for row in explanations if row["expected_label"]["safety_class"] == "healthy"
        ]
        insufficient = [
            row for row in explanations if row["expected_label"]["safety_class"] == "insufficient"
        ]
        costs = [
            Decimal(row["actual_cost_usd"]) for row in ran if row["actual_cost_usd"] is not None
        ]
        uncertain = any(row["actual_cost_usd"] is None for row in ran)
        total = sum(costs, Decimal(0)) if ran and not uncertain else None
        result[policy] = {
            "scheduled_tasks": len(rows),
            "ran_tasks": len(ran),
            "unrun_tasks": len(rows) - len(ran),
            "provider_attempts": sum(row["provider_attempt_count"] for row in ran),
            "accepted_output_coverage": {"count": len(accepted), "denominator": len(ran)},
            "semantic_correctness": {
                "correct": len(correct),
                "scored_explanations": len(scored),
                "unscored_explanations": len(explanations) - len(scored),
            },
            "guard_correctness": {
                "correct": sum(
                    row["scores"]["guard"]["correct"] for row in ran if row["task"] == "draft_guard"
                ),
                "denominator": sum(row["task"] == "draft_guard" for row in ran),
                "applicable_drafts_correct": sum(
                    row["scores"]["guard"]["correct"] for row in applicable_guards
                ),
                "applicable_drafts": len(applicable_guards),
                "not_applicable_correct": sum(
                    row["scores"]["guard"]["correct"]
                    for row in guards
                    if row not in applicable_guards
                ),
                "not_applicable": len(guards) - len(applicable_guards),
            },
            "schema_citation_valid": {
                "count": sum(
                    row["scores"].get("mechanical_valid") is True for row in structured_explanations
                ),
                "denominator": len(structured_explanations),
                "coverage_abstentions": sum(
                    row["output"] is None and row["actual_outcome"] == "out_of_scope"
                    for row in explanations
                ),
            },
            "decision_metrics_basis": "The deterministic engine's outcome; not a measure of model prose safety. Semantic scores are separate.",
            "unsafe_false_negatives": {
                "count": sum(row["actual_outcome"] == "request_review" for row in unsafe),
                "denominator": len(unsafe),
            },
            "healthy_false_positives": {
                "count": sum(row["actual_outcome"] == "revise_change" for row in healthy),
                "denominator": len(healthy),
            },
            "correct_abstentions": {
                "count": sum(row["actual_outcome"] == "collect_evidence" for row in insufficient),
                "denominator": len(insufficient),
            },
            "total_actual_usd": str(total) if total is not None else None,
            "cost_per_executed_task_usd": str(total / len(ran))
            if total is not None and ran
            else None,
            "cost_per_correct_explanation_usd": str(
                sum(Decimal(row["actual_cost_usd"] or "0") for row in explanations) / len(correct)
            )
            if correct and not uncertain
            else None,
            "escalations": {
                "count": sum(
                    len(
                        {
                            (attempt.get("provider"), attempt.get("model"))
                            for attempt in row.get("result", {}).get("attempts", [])
                        }
                    )
                    > 1
                    for row in ran
                ),
                "denominator": len(ran),
            },
            "tasks_with_retry_or_escalation": sum(row["provider_attempt_count"] > 1 for row in ran),
            "p50_end_to_end_seconds": percentile([row["latency_seconds"] for row in ran], 0.5),
            "p95_end_to_end_seconds": percentile([row["latency_seconds"] for row in ran], 0.95),
            "groups": len({row["group"] for row in explanations}),
            "independence_note": "Three variants per group are correlated; group counts, not variant counts, describe scenario coverage.",
        }
    return result
