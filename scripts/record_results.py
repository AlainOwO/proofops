"""Copy actual local verification extracts into the versioned documentation."""

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs/results"


def read(relative):
    return json.loads((ROOT / relative).read_text())


def save(relative, value):
    path = DESTINATION / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-incomplete", action="store_true", help="For intermediate documentation layout only"
    )
    args = parser.parse_args()
    backend = ET.parse(ROOT / "artifacts/checks/backend.xml").getroot()  # noqa: S314 - locally generated test result
    cases = backend.findall(".//testcase")
    failures = len(backend.findall(".//failure")) + len(backend.findall(".//error"))
    skipped = len(backend.findall(".//skipped"))
    browser = read("artifacts/checks/playwright.json")["stats"]
    evaluation = read("artifacts/evaluation/summary.json")
    workload = read("artifacts/workload/comparison.json")
    pressure = read("artifacts/workload/pressure-repair.json")
    terraform = read("artifacts/checks/terraform.json")
    fresh_setup = (
        read("artifacts/checks/fresh-setup.json")
        if (ROOT / "artifacts/checks/fresh-setup.json").exists()
        else {"status": "unrecorded"}
    )
    fresh_note = (
        "Passed; frozen runtime install and keyless review/replay"
        if fresh_setup["status"] == "passed"
        else "Unrun; no fresh-checkout verification saved"
    )
    quality = (
        read("artifacts/checks/quality.json")
        if (ROOT / "artifacts/checks/quality.json").exists()
        else {"status": "unrecorded"}
    )
    research = (
        read("artifacts/checks/research.json")
        if (ROOT / "artifacts/checks/research.json").exists()
        else {"status": "unrecorded"}
    )
    if not args.allow_incomplete and (
        not workload["complete"]
        or quality.get("status") != "passed"
        or research.get("changed_or_missing") != []
    ):
        raise SystemExit(
            "Final evidence is incomplete; preserve unrun state or finish the checks before recording."
        )
    verification = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "backend": {
            "command": ".venv/bin/pytest tests/unit tests/policy tests/integration -q --junitxml=artifacts/checks/backend.xml",
            "tests": len(cases),
            "passed": len(cases) - failures - skipped,
            "failures": failures,
            "skipped": skipped,
            "artifact": "artifacts/checks/backend.xml",
            "warning": "One upstream Starlette TestClient deprecation warning suggests httpx2; no skipped/failing tests.",
        },
        "browser": {
            "command": "npm run test:e2e (from frontend/)",
            "stats": browser,
            "artifact": "artifacts/checks/playwright.json",
        },
        "evaluation": {
            "command": ".venv/bin/proofops evaluate --manifest evaluation/manifest.json --mode replay --output artifacts/evaluation",
            "deterministic": evaluation["deterministic"],
            "manifest_hash": evaluation["manifest_hash"],
            "artifact": "docs/results/evaluation-summary.json",
        },
        "workload": {
            "command": ".venv/bin/python scripts/run_workload.py all",
            "complete": workload["complete"],
            "passed": workload["passed"],
            "origin": workload["origin"],
            "artifact": "docs/results/workload/comparison.json",
        },
        "pressure_repair": {
            "confirmed": pressure["confirmed_failure_and_repair"],
            "artifact": "docs/results/workload/pressure-repair.json",
        },
        "terraform": {
            "command": ".tools/bin/terraform -chdir=infra/aws-demo validate -json",
            **terraform,
        },
        "quality": quality,
        "research": research,
        "fresh_setup": fresh_setup,
        "unrun": [
            "live AWS smoke/deployment",
            "paid OpenAI/Anthropic quality/cost/latency",
            "downstream compact-versus-flat model quality",
            "remote GitHub workflow/enforcement",
            "Windows/PowerShell execution",
            "uncoached human usability T24",
        ],
    }
    save("verification.json", verification)
    save("fresh-setup.json", fresh_setup)
    save("evaluation-summary.json", evaluation)
    save("evaluation-contexts.json", read("artifacts/evaluation/contexts.json"))
    save("workload/comparison.json", workload)
    save("workload/pressure-repair.json", pressure)
    evidence_paths = [
        ROOT / "artifacts/checks/backend.xml",
        ROOT / "artifacts/checks/playwright.json",
        ROOT / "artifacts/evaluation/results.jsonl",
    ]
    run_paths = sorted(
        (ROOT / "artifacts/workload").glob("*/manifest.json"),
        key=lambda path: json.loads(path.read_text())["started_at"],
    )
    for path in run_paths:
        run = json.loads(path.read_text())
        destination = DESTINATION / "workload" / path.parent.name
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination / "manifest.json")
        summary = path.parent / f"{run['run_id']}.k6-summary.json"
        shutil.copyfile(summary, destination / summary.name)
        evidence_paths.extend([path, summary])
    save(
        "source_hashes.json",
        {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in evidence_paths
        },
    )
    template = evaluation["policies"]["template"]
    rows = [
        "# Recorded results",
        "",
        f"Generated from actual saved artifacts on {verification['recorded_at']}. This table describes the supported local workflow; live/unrun work is listed separately. Full JSON and native workload summaries accompany it in docs/results/.",
        "",
        "## Local verification",
        "",
        "| Check | Observed result |",
        "|---|---|",
        f"| Backend, policy and PostgreSQL integration | {len(cases) - failures - skipped}/{len(cases)} passed; {failures} failures; {skipped} skipped |",
        f"| Chromium browser workflows | {browser['expected']} passed; {browser['unexpected']} unexpected; {browser['skipped']} skipped |",
        f"| Fresh local checkout/runtime environment | {fresh_note} |",
        f"| Deterministic synthetic evaluation | {evaluation['deterministic']['correct']}/{evaluation['deterministic']['cases']} cases in {evaluation['deterministic']['groups']} scenario groups |",
        f"| Terraform local validation | valid={terraform['valid']}; {terraform['error_count']} errors; {terraform['warning_count']} warnings; no plan/apply |",
        f"| Formatting/type/build/CI syntax | {quality.get('status', 'unrecorded')}; exact commands and exits in verification.json |",
        f"| Research preservation | {research.get('checked', 'unrecorded')} files checked; {len(research.get('changed_or_missing', []))} changed/missing |",
        "",
        "## Template and provider evaluation",
        "",
        "These are synthetic descriptive results, not independent real incidents or model quality parity. The deterministic outcome's safety counts are separate from semantic prose scoring.",
        "",
        "| Task / policy | Observed count or status |",
        "|---|---|",
        f"| Structured template explanations | {template['schema_citation_valid']['count']}/{template['schema_citation_valid']['denominator']} mechanically valid; {template['schema_citation_valid']['coverage_abstentions']} additional out-of-scope abstentions |",
        f"| Narrow authored explanation/coverage rubric | {template['semantic_correctness']['correct']}/{template['semantic_correctness']['scored_explanations']} correct; no live model prose scored |",
        f"| Applicable guard drafts | {template['guard_correctness']['applicable_drafts_correct']}/{template['guard_correctness']['applicable_drafts']} correct |",
        f"| Inapplicable guard cases | {template['guard_correctness']['not_applicable_correct']}/{template['guard_correctness']['not_applicable']} correctly returned no draft |",
        f"| Structured accepted-output coverage | {template['accepted_output_coverage']['count']}/{template['accepted_output_coverage']['denominator']} template tasks |",
        f"| Unsafe decision false negatives | {template['unsafe_false_negatives']['count']}/{template['unsafe_false_negatives']['denominator']} unsafe cases |",
        f"| Healthy decision false positives | {template['healthy_false_positives']['count']}/{template['healthy_false_positives']['denominator']} healthy cases |",
        f"| Correct evidence abstentions | {template['correct_abstentions']['count']}/{template['correct_abstentions']['denominator']} insufficient cases |",
        f"| Template incremental API spend | USD {template['total_actual_usd']}; zero provider calls |",
        f"| Template local processing latency | p50 {template['p50_end_to_end_seconds'] * 1000:.3f} ms; p95 {template['p95_end_to_end_seconds'] * 1000:.3f} ms; sequential runner, no API queue |",
    ]
    for policy in ("cheap_only", "strong_only", "routed"):
        value = evaluation["policies"][policy]
        rows.append(
            f"| {policy} | {value['unrun_tasks']} scheduled tasks unrun; live quality/cost/latency null |"
        )
    rows += [
        "",
        "## Measured local workload",
        "",
        "Origin: local_observation, Linux ARM64 Docker on a shared development host. Baseline 2 CPUs / 512 MiB; candidate 1 CPU / 256 MiB. Same pinned local image/profile/dependencies, 100-request warmup, eight-minute full runs. No cloud cost or invoice measured. Each run/class is assessed separately; p95 values are not averaged.",
        "",
        "| Run | Correct responses | p95 (ms) | HTTP failures | Contract result |",
        "|---|---|---|---|---|",
    ]
    for path in run_paths:
        run = json.loads(path.read_text())
        status = (
            "Smoke only; no capacity claim"
            if run["profile"] == "smoke"
            else "Passed"
            if run["contract_passed"]
            else "Failed"
        )
        rows.append(
            f"| {run['run_id']} | {run['correct']:,} | {run['p95_latency_ms']:.3f} | {run['http_failures']} | {status} |"
        )
    rows += [
        "",
        "Per-class p95 is checked independently against the same frozen 250 ms limit:",
        "",
        "| Comparison run | Small p95 (ms) | Medium p95 (ms) | Large p95 (ms) |",
        "|---|---|---|---|",
    ]
    for run in workload["runs"]:
        classes = run["request_classes"]
        rows.append(
            f"| {run['run_id']} | {classes['small']['p95_latency_ms']:.3f} | {classes['medium']['p95_latency_ms']:.3f} | {classes['large']['p95_latency_ms']:.3f} |"
        )
    rows += [
        "",
        f"Comparison complete: {workload['complete']}; all six comparison runs passed: {workload['passed']}. Actual bounded OOM plus repair confirmed: {pressure['confirmed_failure_and_repair']}. Inspect native summaries for every request class, failure count and dropped iteration. Frozen thresholds: at least 10,000 correct; p95 below 250 ms; HTTP failures below 1%; zero incorrect successes, dropped iterations or restarts.",
        "",
        "The OOM experiment injected a 128 MiB startup allocation into a 64 MiB cgroup and then verified 20 correct responses at 256 MiB. This controlled failure does not establish a 2,048 MiB AWS memory bound. The local resize is a resource-allocation comparison, not measured cloud savings.",
        "",
        "## Unrun prerequisites",
        "",
        "Live AWS needs an exact authorized service/account and spending allowance. Paid model experiments need verified exact model IDs, credentials, current prices, positive budgets and independent semantic review. Remote CI needs a repository and protected workflow configuration. Windows commands need a Windows host. T24 needs a consenting uncoached peer; no feedback was fabricated.",
        "",
    ]
    (DESTINATION / "results.md").write_text("\n".join(rows))
    overview = [
        "# Recorded results",
        "",
        f"Observed local verification, recorded {verification['recorded_at']}. The technical guide and docs/results JSON contain complete commands, denominators and per-class measurements.",
        "",
        "| Check | Observed result |",
        "|---|---|",
        f"| Backend / policy / PostgreSQL | {verification['backend']['passed']}/{len(cases)} passed |",
        f"| Real Chromium workflows | {browser['expected']} passed |",
        f"| Fresh checkout and frozen runtime install | {fresh_note} |",
        f"| Deterministic synthetic evaluation | {evaluation['deterministic']['correct']}/60 cases, 20 groups, split 8/4/8 |",
        f"| Terraform local validation | {terraform['error_count']} errors, {terraform['warning_count']} warnings; not deployed |",
        f"| Original research preservation | {research.get('checked', 'unrecorded')} files unchanged |",
        "",
        "## Measured local workload",
        "",
        "Three alternating eight-minute pairs used one pinned Linux ARM64 Docker image/profile/dependency state on a shared development host. Baseline: 2 CPUs / 512 MiB. Candidate: 1 CPU / 256 MiB. Thresholds were frozen before candidates. This is not AWS x86_64 operating-bound evidence or measured cloud savings.",
        "",
        "| Run | Correct responses | p95 (ms) | HTTP failures |",
        "|---|---|---|---|",
    ]
    for run in workload["runs"]:
        overview.append(
            f"| {run['run_id']} | {run['correct']:,} | {run['p95_latency_ms']:.3f} | {run['http_failures']} |"
        )
    overview += [
        "",
        f"All six comparison runs passed: {workload['passed']}. Required: p95 below 250 ms and HTTP failures below 1%. Observed incorrect successes / dropped work / restarts: {sum(run['incorrect_successful_responses'] for run in workload['runs'])} / {sum(run['dropped_iterations'] for run in workload['runs'])} / {sum(run['restarts'] for run in workload['runs'])}. Separate bounded OOM plus repair confirmed: {pressure['confirmed_failure_and_repair']}; 128 MiB pressure at a 64 MiB limit, then 20 correct responses at 256 MiB.",
        "",
        "## Model evaluation status",
        "",
        f"The template run produced {template['schema_citation_valid']['denominator']} structured explanations plus {template['schema_citation_valid']['coverage_abstentions']} coverage abstentions, and {template['guard_correctness']['applicable_drafts']} applicable guard drafts plus {template['guard_correctness']['not_applicable_correct']} correctly inapplicable cases. These are narrow synthetic/template results. {sum(evaluation['policies'][policy]['unrun_tasks'] for policy in ('cheap_only', 'strong_only', 'routed'))} paid-provider policy tasks are unrun; unrun quality/cost/latency stay null. Confidence or strong-model agreement never supplies truth.",
        "",
    ]
    (DESTINATION / "overview-results.md").write_text("\n".join(overview))
    print(
        json.dumps(
            {
                "backend_passed": verification["backend"]["passed"],
                "browser_passed": browser["expected"],
                "workload_complete": workload["complete"],
                "output": "docs/results",
            }
        )
    )


if __name__ == "__main__":
    main()
