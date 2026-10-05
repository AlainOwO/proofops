from proofops.domain.engine import review
from proofops.domain.schemas import WorkloadRun


def test_smoke_does_not_establish_capacity(valid_bundle, trusted):
    runs = []
    for original in valid_bundle.workload_runs:
        data = original.model_dump(mode="json")
        data.update(offered=20, completed=20, correct=20)
        for name, count in {"small": 16, "medium": 3, "large": 1}.items():
            data["request_classes"][name].update(completed=count, correct=count)
        runs.append(WorkloadRun.model_validate(data))
    result = review(valid_bundle.model_copy(update={"workload_runs": runs}), trusted)
    assert result.outcome == "collect_evidence"
    assert "INSUFFICIENT_REQUEST_SAMPLE" in {item.code for item in result.findings}


def test_failures_cannot_hide_breach_by_reducing_correct_count(valid_bundle, trusted):
    runs = list(valid_bundle.workload_runs)
    data = runs[-1].model_dump(mode="json")
    data.update(offered=10000, completed=10000, correct=9800, http_failures=200)
    for name, completed, correct in (
        ("small", 8000, 7800),
        ("medium", 1500, 1500),
        ("large", 500, 500),
    ):
        data["request_classes"][name].update(completed=completed, correct=correct)
    runs[-1] = WorkloadRun.model_validate(data)
    result = review(valid_bundle.model_copy(update={"workload_runs": runs}), trusted)
    assert result.outcome == "revise_change"
    assert any(
        item.code == "PERFORMANCE_CONTRACT_BREACH" and "HTTP failure rate" in item.message
        for item in result.findings
    )


def test_local_arm_measurements_cannot_validate_x86_contract(valid_bundle, trusted):
    runs = [
        WorkloadRun.model_validate(
            {
                **run.model_dump(mode="json"),
                "platform": "linux/arm64",
                "origin": "local_observation",
            }
        )
        for run in valid_bundle.workload_runs
    ]
    result = review(valid_bundle.model_copy(update={"workload_runs": runs}), trusted)
    assert result.outcome == "collect_evidence"
    assert not result.performance["comparable"]
