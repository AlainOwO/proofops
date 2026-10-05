"""Freeze original synthetic scenario groups and independent constraint labels.

The expected outcomes below are authored from the contract, never obtained by
calling the review engine. Fixtures are exploratory and are not real incidents.
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proofops.domain.common import bytes_digest, canonical, digest  # noqa: E402
from proofops.domain.schemas import ServiceMap  # noqa: E402
from proofops.normalization.terraform import normalize  # noqa: E402
from proofops.policies.guards import TrustedRevision  # noqa: E402
from proofops.storage.bundles import import_files  # noqa: E402

from scripts.generate_fixtures import REFERENCE, base_documents  # noqa: E402

GROUPS = [
    (
        "g01",
        "development",
        "healthy_allocation",
        "request_review",
        "healthy",
        [],
        "All three allocations meet the approved bound with complete matching evidence.",
    ),
    (
        "g02",
        "development",
        "approved_bound_breach",
        "revise_change",
        "unsafe",
        ["APPROVED_MEMORY_FLOOR_BREACH"],
        "The explicit approved 4096 MiB bound exceeds each candidate allocation; missing evidence cannot override a known breach.",
    ),
    (
        "g03",
        "development",
        "missing_workload",
        "collect_evidence",
        "insufficient",
        ["REQUIRED_EVIDENCE_MISSING"],
        "Required baseline or candidate runs are absent. Low CPU context cannot supply latency or correctness evidence.",
    ),
    (
        "g04",
        "development",
        "insufficient_sample",
        "collect_evidence",
        "insufficient",
        ["INSUFFICIENT_REQUEST_SAMPLE"],
        "20, 200 or 2000 correct requests do not satisfy the frozen 10000-request minimum.",
    ),
    (
        "g05",
        "development",
        "collection_failure",
        "collect_evidence",
        "insufficient",
        ["REQUIRED_EVIDENCE_MISSING"],
        "Denied, pending and failed collections do not establish a complete task observation.",
    ),
    (
        "g06",
        "development",
        "unknown_allocation",
        "collect_evidence",
        "insufficient",
        ["TERRAFORM_VALUE_UNKNOWN"],
        "The proposed CPU, memory or both are unresolved Terraform values.",
    ),
    (
        "g07",
        "development",
        "unknown_task_hours",
        "collect_evidence",
        "insufficient",
        ["REQUIRED_COST_INPUT_MISSING"],
        "Missing baseline or candidate billable task-hours prevent the required compute comparison.",
    ),
    (
        "g08",
        "development",
        "missing_rate",
        "collect_evidence",
        "insufficient",
        ["REQUIRED_COST_INPUT_MISSING"],
        "An absent CPU/memory rate is unknown, not free infrastructure.",
    ),
    (
        "g09",
        "calibration",
        "healthy_peak_latency",
        "request_review",
        "healthy",
        [],
        "Candidate aggregate and class p95 remain strictly below the frozen latency bound.",
    ),
    (
        "g10",
        "calibration",
        "latency_boundary",
        "revise_change",
        "unsafe",
        ["PERFORMANCE_CONTRACT_BREACH"],
        "250 ms equality and larger p95 values fail the strict less-than requirement.",
    ),
    (
        "g11",
        "calibration",
        "incorrect_success",
        "revise_change",
        "unsafe",
        ["PERFORMANCE_CONTRACT_BREACH"],
        "At least one HTTP 200 result is incorrect; the allowed count is zero.",
    ),
    (
        "g12",
        "calibration",
        "stale_observation",
        "collect_evidence",
        "insufficient",
        ["EVIDENCE_STALE"],
        "Task observations predate the explicit one-day freshness window.",
    ),
    (
        "g13",
        "held_out",
        "changed_image",
        "collect_evidence",
        "insufficient",
        ["APPLICABILITY_CHANGED"],
        "The candidate image no longer matches the approved workload applicability.",
    ),
    (
        "g14",
        "held_out",
        "dependency_mismatch",
        "collect_evidence",
        "insufficient",
        ["INCOMPARABLE_WORKLOADS"],
        "Candidate runs have an incompatible dependency state, profile or platform.",
    ),
    (
        "g15",
        "held_out",
        "new_candidate_revision",
        "collect_evidence",
        "insufficient",
        ["REQUIRED_EVIDENCE_MISSING"],
        "The candidate commit changed after evidence was recorded; historical evidence does not follow it.",
    ),
    (
        "g16",
        "held_out",
        "http_failures",
        "revise_change",
        "unsafe",
        ["PERFORMANCE_CONTRACT_BREACH"],
        "A sufficiently large completed population exceeds the failure-rate limit, even when too few responses are correct.",
    ),
    (
        "g17",
        "held_out",
        "dropped_demand",
        "revise_change",
        "unsafe",
        ["PERFORMANCE_CONTRACT_BREACH"],
        "Offered demand includes dropped iterations; the contract allows none.",
    ),
    (
        "g18",
        "held_out",
        "restarted_candidate",
        "revise_change",
        "unsafe",
        ["PERFORMANCE_CONTRACT_BREACH"],
        "Observed restarts violate the explicit zero-restart requirement.",
    ),
    (
        "g19",
        "held_out",
        "unrelated_service",
        "out_of_scope",
        "out_of_scope",
        [],
        "The scoped guard has no authority over the different named service; the result is a coverage statement.",
    ),
    (
        "g20",
        "held_out",
        "no_compute_benefit",
        "request_review",
        "healthy",
        [],
        "All operating checks pass, but increased task-hours yield zero or negative projected compute benefit.",
    ),
]


def create_case(group, variant):
    gid, split, scenario, expected, safety, codes, rationale = group
    seed = digest({"group": gid, "fixture_version": 1})
    docs = copy.deepcopy(base_documents())
    mapping = docs["service-map.json"]
    scope = mapping["scope"]
    scope.update(
        service="reports-" + seed[:8],
        cluster="cluster-" + seed[8:16],
        terraform_address='module.reporting.aws_ecs_task_definition.main["api"]',
    )
    mapping.update(
        base_commit=digest({"base": seed})[:40],
        candidate_commit=digest({"candidate": seed, "variant": variant})[:40],
    )
    contract = docs["contract.json"]
    contract.update(
        contract_id="contract-" + seed[:12], approval_reference="SYNTHETIC-" + seed[:12]
    )
    image = "sha256:" + digest({"image": seed})
    contract["applicability"]["image_digest"] = image
    plan = docs["plan.json"]
    plan["resource_changes"][0]["address"] = scope["terraform_address"]
    change = plan["resource_changes"][0]["change"]
    for config in (change["before"], change["after"]):
        config["family"] = "task-" + seed[:8]
        containers = json.loads(config["container_definitions"])
        containers[0].update(name=scope["service"], image="example.invalid/report@" + image)
        config["container_definitions"] = json.dumps(containers, sort_keys=True)
    if scenario == "healthy_allocation":
        change["after"]["memory"] = str([2048, 3072, 4096][variant])
    if scenario == "approved_bound_breach":
        contract["minimum_task_memory_mib"] = 4096
        change["after"].update(
            cpu="512" if variant == 0 else "1024", memory=str([1024, 2048, 3072][variant])
        )
    baseline = normalize(plan, ServiceMap.model_validate(mapping), digest(plan))
    contract["applicability"]["non_resize_config_hash"] = baseline.before.non_resize_config_hash
    if scenario == "unknown_allocation":
        for field in (["memory"], ["cpu"], ["memory", "cpu"])[variant]:
            change["after"][field] = None
            change["after_unknown"][field] = True
    if scenario == "changed_image":
        containers = json.loads(change["after"]["container_definitions"])
        containers[0]["image"] = "example.invalid/report@sha256:" + digest(
            {"other-image": seed, "variant": variant}
        )
        change["after"]["container_definitions"] = json.dumps(containers, sort_keys=True)
    normalized = normalize(plan, ServiceMap.model_validate(mapping), digest(plan))
    for index, record in enumerate(docs["evidence.json"]):
        record.update(
            evidence_id="observation-" + digest({"seed": seed, "index": index})[:12],
            scope=copy.deepcopy(scope),
            resource_revision=mapping["candidate_commit"],
        )
    for index, run in enumerate(docs["workloads.json"]):
        config = normalized.before if run["role"] == "baseline" else normalized.after
        run.update(
            run_id="run-" + digest({"seed": seed, "variant": variant, "index": index})[:12],
            scope=copy.deepcopy(scope),
            image_digest=image,
            config_hash=config.config_hash,
            non_resize_config_hash=config.non_resize_config_hash,
        )
    candidate = [run for run in docs["workloads.json"] if run["role"] == "candidate"]
    if scenario == "missing_workload":
        missing = "baseline" if variant == 1 else "candidate"
        docs["workloads.json"] = [run for run in docs["workloads.json"] if run["role"] != missing]
        record = next(
            record for record in docs["evidence.json"] if record["kind"] == "workload_" + missing
        )
        record.update(collection_status="not_requested", sample_count=None)
        record["metadata"]["reason"] = (
            "Low service-average CPU alone does not establish request correctness or latency."
        )
    if scenario == "approved_bound_breach" and variant == 2:
        docs["workloads.json"] = [
            run for run in docs["workloads.json"] if run["role"] == "baseline"
        ]
        docs["evidence.json"][-1].update(collection_status="pending", sample_count=None)
    if scenario == "insufficient_sample":
        count = [20, 200, 2000][variant]
        for run in candidate:
            run.update(offered=count, completed=count, correct=count)
            for name, numerator in (("small", 16), ("medium", 3), ("large", 1)):
                run["request_classes"][name].update(
                    completed=count * numerator // 20, correct=count * numerator // 20
                )
    if scenario == "collection_failure":
        docs["evidence.json"][0].update(
            collection_status=["denied", "pending", "failed"][variant], sample_count=None
        )
    if scenario == "stale_observation":
        docs["evidence.json"][0].update(
            observed_start=f"2026-10-0{1 + variant}T08:00:00Z",
            observed_end=f"2026-10-0{1 + variant}T09:00:00Z",
            collected_at=f"2026-10-0{1 + variant}T09:01:00Z",
        )
    if scenario == "unknown_task_hours":
        for key in (
            ["baseline_task_hours"],
            ["candidate_task_hours"],
            ["baseline_task_hours", "candidate_task_hours"],
        )[variant]:
            docs["usage.json"][key] = None
    if scenario == "missing_rate":
        for key in (
            ["price_per_vcpu_hour"],
            ["price_per_gib_hour"],
            ["price_per_vcpu_hour", "price_per_gib_hour"],
        )[variant]:
            docs["rates.json"][key] = None
    if scenario in {"healthy_peak_latency", "latency_boundary"}:
        p95 = ([200, 210, 249] if scenario == "healthy_peak_latency" else [250, 300, 900])[variant]
        candidate[-1]["p95_latency_ms"] = str(p95)
        candidate[-1]["request_classes"]["large"]["p95_latency_ms"] = str(p95)
    if scenario in {"incorrect_success", "http_failures"}:
        bad = [1, 3, 7][variant] if scenario == "incorrect_success" else [500, 1000, 12000][variant]
        run = candidate[-1]
        run[
            "incorrect_successful_responses" if scenario == "incorrect_success" else "http_failures"
        ] = bad
        run["correct"] -= bad
        run["request_classes"]["small"]["correct"] -= bad
    if scenario == "dependency_mismatch":
        key = ["dependency_hash", "profile_hash", "platform"][variant]
        candidate[-1][key] = "linux/arm64" if key == "platform" else digest({"different": seed})
    if scenario == "new_candidate_revision":
        mapping["candidate_commit"] = digest({"later-candidate": seed, "variant": variant})[:40]
    if scenario == "dropped_demand":
        candidate[-1]["dropped_iterations"] = [1, 10, 100][variant]
        candidate[-1]["offered"] += candidate[-1]["dropped_iterations"]
    if scenario == "restarted_candidate":
        candidate[-1]["restarts"] = variant + 1
    if scenario == "unrelated_service":
        mapping["scope"] = {**scope, "service": "other-" + seed[:8]}
    if scenario == "no_compute_benefit":
        docs["usage.json"]["candidate_task_hours"] = ["5840", "8760", "11680"][variant]
    files = {name: canonical(value) for name, value in docs.items()}
    files["manifest.json"] = canonical(
        {
            "schema_version": 1,
            "origin": "synthetic_fixture",
            "reference_time": REFERENCE,
            "files": {name: bytes_digest(raw) for name, raw in files.items()},
        }
    )
    bundle = import_files(files)
    guard = {
        "schema_version": 1,
        "guard_id": "guard-" + seed[:12],
        "revision": 1,
        "kind": "ecs_task_memory_floor",
        "service_contract_id": contract["contract_id"],
        "minimum_task_memory_mib": contract["minimum_task_memory_mib"],
        "incident_id": "incident-" + seed[:12],
        "repair_reference": "SYNTHETIC-REPAIR-" + seed[:8],
        "approved_bound_fact_id": "approved.minimum_task_memory_mib",
        "rationale_fact_ids": ["incident.repair_verified"],
        "owner": "fixture-author",
        "reviewer": "synthetic-example-only",
        "state": "approved_in_trusted_revision",
        "approval_reference": contract["approval_reference"],
        "contract_hash": digest(bundle.contract),
    }
    trusted = TrustedRevision.model_validate({"contract": bundle.contract, "guard": guard})
    label = {
        "expected_outcome": expected,
        "safety_class": safety,
        "required_codes": codes,
        "rationale": rationale,
        "label_basis": "independently authored explicit synthetic constraints; no human pilot or model answer used",
        "approved_memory_mib": contract["minimum_task_memory_mib"],
        "candidate_memory_mib": bundle.change.after.memory_mib,
        "expected_guard": {**guard, "state": "draft"}
        if scenario not in {"changed_image", "unrelated_service"}
        else None,
        "cost_sign": ("zero" if variant == 0 else "negative")
        if scenario == "no_compute_benefit"
        else None,
    }
    return {
        "bundle": bundle.model_dump(mode="json"),
        "trusted": trusted.model_dump(mode="json"),
    }, label


def main():
    root = ROOT / "evaluation"
    if (root / "manifest.json").exists():
        raise SystemExit(
            "The split is frozen. Create a reviewed new corpus version instead of overwriting it."
        )
    (root / "inputs").mkdir(exist_ok=True)
    (root / "evaluator_only").mkdir(exist_ok=True)
    cases, labels = [], {}
    for group in GROUPS:
        for variant in range(3):
            case_id = group[0] + f"-v{variant + 1}"
            payload, label = create_case(group, variant)
            neutral = digest({"case": case_id, "seed": 42017})[:20] + ".json"
            raw = canonical(payload)
            (root / "inputs" / neutral).write_bytes(raw)
            cases.append(
                {
                    "case_id": case_id,
                    "group": group[0],
                    "split": group[1],
                    "input": "inputs/" + neutral,
                    "sha256": bytes_digest(raw),
                }
            )
            labels[case_id] = label
    label_raw = canonical(labels)
    (root / "evaluator_only/labels.json").write_bytes(label_raw)
    manifest = {
        "schema_version": 1,
        "corpus_version": "synthetic-60-v1",
        "frozen_on": "2026-10-05",
        "seed": 42017,
        "origin": "synthetic_fixture",
        "cases": cases,
        "labels": "evaluator_only/labels.json",
        "labels_sha256": bytes_digest(label_raw),
        "group_counts": {"development": 8, "calibration": 4, "held_out": 8},
        "limitations": "Original synthetic regression scenarios sharing one policy family; variants are correlated. No real-incident quality or parity claim.",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Frozen 60 synthetic cases in 20 groups: 8 development, 4 calibration, 8 held out.")


if __name__ == "__main__":
    main()
