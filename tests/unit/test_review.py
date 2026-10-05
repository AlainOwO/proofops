from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from proofops.domain.common import canonical
from proofops.domain.costs import estimate_cost
from proofops.domain.engine import review
from proofops.models.explanations import legacy_outcome, template_explanation, validate_explanation
from proofops.normalization.terraform import allocation
from proofops.storage.bundles import export_report, load_replay, replay_export


@pytest.mark.parametrize(
    ("name", "outcome"),
    [
        ("valid-resize", "request_review"),
        ("unsafe-resize", "revise_change"),
        ("incomplete-evidence", "collect_evidence"),
    ],
)
def test_three_report_paths(name, outcome, trusted):
    bundle = load_replay(name)
    report = review(bundle, trusted)
    assert report.outcome == outcome
    assert report.origin == "synthetic_fixture"
    assert report.cost.projected_reduction_fraction == (
        Decimal(".75") if name == "unsafe-resize" else Decimal(".5")
    )
    exported = export_report(bundle, report, template_explanation(report), trusted)
    reproduced, matches = replay_export(exported)
    assert matches and reproduced == report


def test_violation_precedes_missing(trusted):
    bundle = load_replay("unsafe-resize")
    bundle.workload_runs = []
    report = review(bundle, trusted)
    assert report.outcome == "revise_change"
    assert {f.severity for f in report.findings} >= {"violation", "missing"}


@pytest.mark.parametrize(
    "state", ["denied", "pending", "failed", "not_configured", "not_requested"]
)
def test_collection_states_do_not_become_zero(valid_bundle, trusted, state):
    valid_bundle.evidence[0].collection_status = state
    result = review(valid_bundle, trusted)
    assert result.outcome == "collect_evidence"
    assert result.coverage["sources"]["task_configuration"]["records"][0]["collection"] == state


def test_empty_stale_and_new_commit(valid_bundle, trusted):
    valid_bundle.evidence[0].sample_count = 0
    assert review(valid_bundle, trusted).outcome == "collect_evidence"
    result = review(
        load_replay("valid-resize"),
        trusted,
        reference=valid_bundle.reference_time + timedelta(days=2),
    )
    assert result.outcome == "collect_evidence"
    assert "EVIDENCE_STALE" in {f.code for f in result.findings}
    valid_bundle.change.service_map.candidate_commit = "c" * 40
    assert review(valid_bundle, trusted).outcome == "collect_evidence"


def test_cost_null_zero_and_changed_hours(valid_bundle):
    valid_bundle.usage.baseline_task_hours = Decimal(0)
    result = estimate_cost(valid_bundle)
    assert result.baseline_amount == 0 and result.projected_reduction_fraction is None
    valid_bundle.usage.candidate_task_hours = None
    assert estimate_cost(valid_bundle).candidate_amount is None


@given(st.integers(min_value=1, max_value=1_000_000))
def test_strict_allocation_roundtrip(value):
    assert allocation(str(value)) == value


@pytest.mark.parametrize(
    "value", [True, False, 0, "0", "2 GB", "1 vCPU", "1.0", 1.0, " 1024", "${var.memory}", None]
)
def test_unsupported_numbers_stay_unknown(value):
    assert allocation(value) is None


def test_p95_equality_fails_and_no_average(valid_bundle, trusted):
    valid_bundle.workload_runs[-1].p95_latency_ms = Decimal("250")
    result = review(valid_bundle, trusted)
    assert result.outcome == "revise_change"
    assert sum(not run["passed"] for run in result.performance["runs"]) == 1


def test_mismatched_population_inconclusive(valid_bundle, trusted):
    valid_bundle.workload_runs[-1].profile_hash = "0" * 64
    result = review(valid_bundle, trusted)
    assert result.outcome == "collect_evidence"
    assert not result.performance["comparable"]
    assert not result.cost.cost_per_correct_request


def test_trusted_policy_cannot_be_weakened_by_input(valid_bundle, trusted):
    valid_bundle.contract.minimum_task_memory_mib = 512
    result = review(valid_bundle, trusted)
    assert result.outcome == "collect_evidence"
    assert not result.coverage["trusted_contract"]
    unsafe = load_replay("unsafe-resize")
    unsafe.contract.minimum_task_memory_mib = 512
    assert review(unsafe, trusted).outcome == "revise_change"


def test_model_cannot_change_facts_or_action(valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    output = template_explanation(report)["output"]
    output["cited_facts"][0]["value"] = 17
    with pytest.raises(ValueError, match="fact value"):
        validate_explanation(output, report)
    output = template_explanation(report)["output"]
    output["summary"] = "This reduces all AWS costs by 999 percent."
    with pytest.raises(ValueError, match="numeric"):
        validate_explanation(output, report)
    assert b"api_key" not in canonical(report)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("reject", "revise_change"),
        ("needs_evidence", "collect_evidence"),
        ("eligible_for_review", "request_review"),
    ],
)
def test_legacy_migration(old, new):
    assert legacy_outcome(old) == new


def test_container_only_change_has_no_task_compute_saving(valid_bundle, trusted):
    import json
    from proofops.config import APP_ROOT
    from proofops.domain.common import digest
    from proofops.normalization.terraform import normalize

    plan = json.loads((APP_ROOT / "fixtures/replays/valid-resize/plan.json").read_text())
    change = plan["resource_changes"][0]["change"]
    change["after"].update(cpu=change["before"]["cpu"], memory=change["before"]["memory"])
    containers = json.loads(change["after"]["container_definitions"])
    containers[0]["memory"] = 512
    change["after"]["container_definitions"] = json.dumps(containers)
    valid_bundle.change = normalize(plan, valid_bundle.change.service_map, digest(plan))
    result = review(valid_bundle, trusted)
    assert result.cost.projected_difference == 0
    assert "TASK_ALLOCATION_UNCHANGED" in {item.code for item in result.findings}


def test_low_cpu_without_demand_evidence_does_not_justify_resize(valid_bundle, trusted):
    valid_bundle.evidence[0].metadata = {"reason": "CPU 5 percent while requests wait on a dependency."}
    valid_bundle.workload_runs = []
    result = review(valid_bundle, trusted)
    assert result.outcome == "collect_evidence"
    assert not result.performance["passed"]
