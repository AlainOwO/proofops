from proofops.domain.schemas import ReviewReport


def markdown_summary(report: ReviewReport) -> str:
    cost = report.cost
    lines = [
        "# ProofOps review",
        "",
        f"**Outcome: {report.outcome.value}**",
        "",
        report.next_steps[0],
        "",
        f"Evidence origin: `{report.origin.value}`. Mode: `{report.mode}`.",
        f"Evaluation time: `{report.evaluation_reference_time.isoformat()}`.",
        f"Candidate: `{report.change.service_map.candidate_commit}`.",
        f"Trusted revision: `{report.trusted_revision_hash}`.",
        "",
        "This is an advisory engineering review, not deployment approval.",
        "",
    ]
    if cost:
        lines += [
            "| Task CPU/memory estimate | Amount |",
            "|---|---:|",
            f"| Baseline | {cost.baseline_amount} {cost.currency} |",
            f"| Candidate | {cost.candidate_amount} {cost.currency} |",
            f"| Projected difference | {cost.projected_difference} {cost.currency} |",
            "",
            "These estimates exclude other AWS charges and are not billed or realized savings.",
            "",
        ]
    lines += ["Finding codes:", ""] + [
        f"- `{code}`" for code in sorted({item.code for item in report.findings})
    ]
    lines += ["", "Input hashes:", ""] + [
        f"- `{name}`: `{value}`" for name, value in sorted(report.input_hashes.items())
    ]
    return "\n".join(lines) + "\n"
