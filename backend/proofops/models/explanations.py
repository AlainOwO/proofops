import re
from typing import Any

from pydantic import ValidationError

from proofops.domain.schemas import Explanation, ReviewReport


def legacy_outcome(value: str) -> str:
    mapping = {
        "reject": "revise_change",
        "needs_evidence": "collect_evidence",
        "eligible_for_review": "request_review",
    }
    if value not in mapping:
        raise ValueError("unknown legacy decision")
    return mapping[value]


def validate_explanation(output: dict[str, Any], report: ReviewReport) -> Explanation:
    try:
        parsed = Explanation.model_validate(output)
    except ValidationError as exc:
        raise ValueError("model response does not match the result schema") from exc
    if parsed.next_step != report.outcome:
        raise ValueError("model changed the deterministic next step")
    expected_codes = {finding.code for finding in report.findings}
    if set(parsed.finding_codes) != expected_codes or len(set(parsed.finding_codes)) != len(
        parsed.finding_codes
    ):
        raise ValueError("model changed the deterministic finding codes")
    facts = {fact.fact_id: fact.value for fact in report.facts}
    seen = set()
    for item in parsed.cited_facts:
        if item.fact_id in seen or item.fact_id not in facts:
            raise ValueError("duplicate or unknown citation")
        seen.add(item.fact_id)
        expected = facts[item.fact_id]
        if type(item.value) is not type(expected) or item.value != expected:
            raise ValueError("model changed a cited fact value or type")
    if not set(report.required_citations).issubset(seen):
        raise ValueError("model omitted required facts")
    if len(parsed.summary.split()) > 120:
        raise ValueError("model summary exceeds 120 words")
    supplied_numbers = {
        token
        for item in parsed.cited_facts
        for token in re.findall(r"\d+(?:\.\d+)?", str(item.value).replace(",", ""))
    }
    prose_numbers = set(re.findall(r"\d+(?:\.\d+)?", parsed.summary.replace(",", "")))
    if not prose_numbers.issubset(supplied_numbers):
        raise ValueError("model introduced an uncited numeric fact")
    if re.search(
        r"\b(?:deploy now|approved for deployment|delete the|send (?:the )?secret)\b",
        parsed.summary,
        re.I,
    ):
        raise ValueError("model crossed the action boundary")
    return parsed


def template_explanation(report: ReviewReport) -> dict:
    if report.outcome == "out_of_scope":
        return {
            "status": "template",
            "source": "deterministic",
            "output": None,
            "summary": report.next_steps[0],
            "attempts": [],
            "incremental_cost_usd": "0",
        }
    summary = report.next_steps[0]
    breach = next(
        (finding for finding in report.findings if finding.code == "APPROVED_MEMORY_FLOOR_BREACH"),
        None,
    )
    facts = {fact.fact_id: fact.value for fact in report.facts}
    if breach:
        summary = f"The candidate requests {facts['candidate.task_memory_mib']} MiB, below the approved {facts['approved.minimum_task_memory_mib']} MiB floor. Revise the change. Estimated compute reductions do not override this constraint."
    output = {
        "summary": summary,
        "finding_codes": sorted({finding.code for finding in report.findings}),
        "cited_facts": [{"fact_id": fact.fact_id, "value": fact.value} for fact in report.facts],
        "next_step": report.outcome.value,
        "limitations": [
            "Evidence origin and evaluation time limit where this result applies.",
            "Task CPU/memory estimates exclude other AWS charges and are not realized savings.",
            "Engineering review remains required before deployment.",
        ],
    }
    validate_explanation(output, report)
    return {
        "status": "template",
        "source": "deterministic",
        "output": output,
        "attempts": [],
        "incremental_cost_usd": "0",
        "semantic_verification": "template_from_deterministic_facts",
    }
