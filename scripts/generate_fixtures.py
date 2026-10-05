"""Create original labelled development fixtures inside this application only."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from proofops.domain.common import bytes_digest, digest
from proofops.domain.schemas import ServiceMap
from proofops.normalization.terraform import normalize

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = datetime(2026, 10, 5, 12, tzinfo=UTC)


def write(path: Path, value) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, ensure_ascii=False).encode() + b"\n"
    path.write_bytes(raw)
    return raw


def base_documents() -> dict:
    scope = {
        "schema_version": 1,
        "account_id": "111122223333",
        "region": "ap-south-1",
        "cluster": "proofops-demo",
        "service": "reports-api",
        "terraform_address": "aws_ecs_task_definition.reports",
        "environment": "isolated-demo",
    }
    image = "sha256:" + digest("proofops-original-synthetic-image-v1")
    profile = digest("workday-and-peak-v1:80/15/5")
    dependency = digest("synthetic-no-external-dependency-v1")
    before = {
        "cpu": "2048",
        "memory": "4096",
        "family": "reports-demo",
        "requires_compatibilities": ["FARGATE"],
        "network_mode": "awsvpc",
        "runtime_platform": [{"operating_system_family": "LINUX", "cpu_architecture": "X86_64"}],
        "container_definitions": json.dumps(
            [
                {
                    "name": "reports-api",
                    "image": "example.invalid/reports@" + image,
                    "essential": True,
                    "portMappings": [{"containerPort": 8080}],
                }
            ],
            sort_keys=True,
        ),
    }
    after = copy.deepcopy(before)
    after.update(cpu="1024", memory="2048")
    plan = {
        "format_version": "1.2",
        "terraform_version": "1.10.5",
        "resource_changes": [
            {
                "address": scope["terraform_address"],
                "mode": "managed",
                "type": "aws_ecs_task_definition",
                "name": "reports",
                "change": {
                    "actions": ["update"],
                    "before": before,
                    "after": after,
                    "after_unknown": {},
                    "before_sensitive": {},
                    "after_sensitive": {},
                },
            }
        ],
    }
    service_map = {
        "schema_version": 1,
        "scope": scope,
        "repository": "local/proofops-demo",
        "base_commit": "a" * 40,
        "candidate_commit": "b" * 40,
    }
    normalized = normalize(plan, ServiceMap.model_validate(service_map), digest(plan))
    contract = {
        "schema_version": 1,
        "contract_id": "reports-demo-v1",
        "owner": "local-demo-operator",
        "revision": 1,
        "scope": scope,
        "applicability": {
            "schema_version": 1,
            "image_digest": image,
            "workload_profile_hash": profile,
            "dependency_state_hash": dependency,
            "non_resize_config_hash": normalized.after.non_resize_config_hash,
        },
        "minimum_task_memory_mib": 2048,
        "approval_reference": "SYNTHETIC-APPROVAL-001",
        "origin": "synthetic_fixture",
        "requirements": {
            "schema_version": 1,
            "min_correct_requests_per_run": 10000,
            "max_p95_latency_ms": "250",
            "max_http_failure_rate_exclusive": "0.01",
            "max_incorrect_successful_responses": 0,
            "max_dropped_iterations": 0,
            "max_restarts": 0,
            "required_repetitions": 3,
            "max_evidence_age_seconds": 86400,
            "required_sources": [
                "terraform",
                "task_configuration",
                "workload_baseline",
                "workload_candidate",
            ],
        },
    }
    rates = {
        "schema_version": 1,
        "rate_id": "synthetic-linux-x86-2026-10",
        "currency": "USD",
        "price_date": "2026-10-01T00:00:00Z",
        "retrieved_at": "2026-10-01T00:00:00Z",
        "source_url": "https://aws.amazon.com/fargate/pricing/",
        "region": "ap-south-1",
        "architecture": "X86_64",
        "os": "LINUX",
        "purchase_option": "on_demand",
        "price_per_vcpu_hour": "0.04",
        "price_per_gib_hour": "0.004",
        "origin": "synthetic_fixture",
        "billing_minimum_seconds": 60,
        "billing_granularity_seconds": 1,
    }
    usage = {
        "schema_version": 1,
        "baseline_task_hours": "2920",
        "candidate_task_hours": "2920",
        "basis": "explicit_projection",
        "window_start": "2026-10-01T00:00:00Z",
        "window_end": "2026-10-31T10:00:00Z",
        "assumptions": [
            "Synthetic rates, not a current AWS quote.",
            "Illustrative four tasks for 730 billable hours each.",
        ],
    }
    evidence = []
    for kind in ("task_configuration", "workload_baseline", "workload_candidate"):
        evidence.append(
            {
                "schema_version": 1,
                "evidence_id": "fixture-" + kind,
                "kind": kind,
                "source": "original-labelled-replay",
                "scope": scope,
                "resource_revision": "b" * 40,
                "observed_start": "2026-10-05T09:00:00Z",
                "observed_end": "2026-10-05T11:30:00Z",
                "collected_at": "2026-10-05T11:31:00Z",
                "collection_status": "complete",
                "units": "records",
                "population": "mapped_service",
                "sample_count": 3,
                "content_hash": digest({"synthetic": kind}),
                "redaction_state": "allowlisted",
                "origin": "synthetic_fixture",
                "metadata": {
                    "reason": "Synthetic fixture; no AWS query or workload run produced this record."
                },
            }
        )
    runs = []
    for index in range(3):
        for role in ("baseline", "candidate"):
            config = normalized.before if role == "baseline" else normalized.after
            started = REFERENCE - timedelta(
                hours=2, minutes=-index * 20 - (10 if role == "candidate" else 0)
            )
            runs.append(
                {
                    "schema_version": 1,
                    "run_id": f"synthetic-{role}-{index + 1}",
                    "role": role,
                    "scope": scope,
                    "image_digest": image,
                    "config_hash": config.config_hash,
                    "non_resize_config_hash": config.non_resize_config_hash,
                    "profile_hash": profile,
                    "dependency_hash": dependency,
                    "environment": "isolated-demo",
                    "platform": "synthetic-linux-x86_64",
                    "started_at": started.isoformat(),
                    "ended_at": (started + timedelta(minutes=8)).isoformat(),
                    "warmup_policy": "included-consistently-v1",
                    "offered": 20100,
                    "completed": 20100,
                    "correct": 20100,
                    "http_failures": 0,
                    "incorrect_successful_responses": 0,
                    "dropped_iterations": 0,
                    "restarts": 0,
                    "p95_latency_ms": "92" if role == "baseline" else "118",
                    "request_classes": {
                        "small": {"completed": 16080, "correct": 16080, "p95_latency_ms": "50"},
                        "medium": {"completed": 3015, "correct": 3015, "p95_latency_ms": "110"},
                        "large": {"completed": 1005, "correct": 1005, "p95_latency_ms": "180"},
                    },
                    "terminal_status": "completed",
                    "origin": "synthetic_fixture",
                }
            )
    return {
        "plan.json": plan,
        "service-map.json": service_map,
        "contract.json": contract,
        "rates.json": rates,
        "usage.json": usage,
        "evidence.json": evidence,
        "workloads.json": runs,
    }


def save_bundle(name: str, documents: dict) -> None:
    directory = ROOT / "fixtures/replays" / name
    hashes = {key: bytes_digest(write(directory / key, value)) for key, value in documents.items()}
    write(
        directory / "manifest.json",
        {
            "schema_version": 1,
            "origin": "synthetic_fixture",
            "reference_time": REFERENCE.isoformat(),
            "files": hashes,
        },
    )


def main():
    documents = base_documents()
    save_bundle("valid-resize", documents)
    unsafe = copy.deepcopy(documents)
    unsafe["plan.json"]["resource_changes"][0]["change"]["after"].update(cpu="512", memory="1024")
    normalized = normalize(
        unsafe["plan.json"],
        ServiceMap.model_validate(unsafe["service-map.json"]),
        digest(unsafe["plan.json"]),
    )
    for run in unsafe["workloads.json"]:
        if run["role"] == "candidate":
            run["config_hash"] = normalized.after.config_hash
    save_bundle("unsafe-resize", unsafe)
    incomplete = copy.deepcopy(documents)
    incomplete["workloads.json"] = [
        run for run in incomplete["workloads.json"] if run["role"] == "baseline"
    ]
    incomplete["evidence.json"][-1].update(collection_status="not_requested", sample_count=None)
    save_bundle("incomplete-evidence", incomplete)
    from proofops.domain.schemas import ServiceContract

    contract = ServiceContract.model_validate(documents["contract.json"])
    guard = {
        "schema_version": 1,
        "guard_id": "reports-memory-floor",
        "revision": 1,
        "kind": "ecs_task_memory_floor",
        "service_contract_id": contract.contract_id,
        "minimum_task_memory_mib": 2048,
        "incident_id": "INC-DEMO-017",
        "repair_reference": "SYNTHETIC-REPAIR-001",
        "approved_bound_fact_id": "approved.minimum_task_memory_mib",
        "rationale_fact_ids": ["incident.repair_verified"],
        "owner": "local-demo-operator",
        "reviewer": "synthetic-example-reviewer",
        "state": "approved_in_trusted_revision",
        "approval_reference": contract.approval_reference,
        "contract_hash": digest(contract),
    }
    write(ROOT / "contracts/reports-demo.json", contract.model_dump(mode="json"))
    write(
        ROOT / "policies/approved/reports-demo.json",
        {
            "schema_version": 1,
            "contract": contract.model_dump(mode="json"),
            "guard": guard,
            "exceptions": [],
            "template_hash": bytes_digest(
                (ROOT / "policies/templates/ecs_task_memory_floor.rego").read_bytes()
            ),
        },
    )
    write(
        ROOT / "config/model_prices.json",
        {
            "schema_version": 1,
            "date": "2026-10-05",
            "models": [],
            "note": "Live dispatch is disabled until exact models, dated official prices and an explicit budget are configured.",
        },
    )
    print(
        "Generated three labelled replay bundles and the synthetic trusted revision inside proofops-app."
    )


if __name__ == "__main__":
    main()
