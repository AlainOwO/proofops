import pytest
from proofops.config import APP_ROOT
from proofops.domain.engine import review
from proofops.models.explanations import template_explanation, validate_explanation

from evaluation.run import load_manifest
from evaluation.scoring import annotation_key, semantic_score


def test_frozen_split_has_no_group_leakage():
    manifest, labels = load_manifest(APP_ROOT / "evaluation/manifest.json")
    assert len(labels) == 60
    assert manifest["group_counts"] == {"development": 8, "calibration": 4, "held_out": 8}


def test_valid_citations_do_not_validate_causal_inference(valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    output = template_explanation(report)["output"]
    output["summary"] = "The CPU measurements prove the database dependency caused the incident."
    validate_explanation(output, report)
    label = {
        "expected_outcome": "request_review",
        "required_codes": [],
        "rationale": "No causal experiment or dependency diagnosis was supplied.",
    }
    annotations = {
        annotation_key(output, report.input_digest): {
            "correct": False,
            "reviewer": "authored-negative-control",
            "rationale": label["rationale"],
        }
    }
    assert (
        semantic_score(
            output, label, source="model", input_hash=report.input_digest, annotations=annotations
        )["correct"]
        is False
    )
    assert (
        semantic_score(output, label, source="model", input_hash=report.input_digest)["correct"]
        is None
    )
    assert (
        semantic_score(
            output, label, source="model", input_hash="different-evidence", annotations=annotations
        )["correct"]
        is None
    )


def test_confident_wrong_answer_is_not_an_acceptance_signal(valid_bundle, trusted):
    report = review(valid_bundle, trusted)
    output = template_explanation(report)["output"]
    output["summary"] = (
        "I am completely certain the compute saving proves this service cannot fail."
    )
    validate_explanation(output, report)
    label = {
        "expected_outcome": "request_review",
        "required_codes": [],
        "rationale": "A projected cost difference does not prove reliability.",
    }
    score = semantic_score(
        output,
        label,
        source="model",
        input_hash=report.input_digest,
        annotations={
            annotation_key(output, report.input_digest): {
                "correct": False,
                "reviewer": "authored-negative-control",
                "rationale": label["rationale"],
            }
        },
    )
    assert score["correct"] is False


def test_annotation_score_must_be_boolean():
    annotations = {
        annotation_key({}, "input"): {
            "correct": "false",
            "reviewer": "test",
            "rationale": "bad type",
        }
    }
    with pytest.raises(ValueError, match="boolean"):
        semantic_score({}, {}, source="model", input_hash="input", annotations=annotations)


def test_replay_rescore_keeps_outputs_and_never_calls_a_provider(monkeypatch):
    import json
    from uuid import uuid4

    from evaluation.rescore import rescore
    from evaluation.run import evaluate

    def no_provider(*args, **kwargs):
        pytest.fail("replay/rescoring must not construct a provider router")

    monkeypatch.setattr("evaluation.run.ModelRouter", no_provider)
    directory = APP_ROOT / "artifacts/evaluation-tests" / uuid4().hex
    manifest = APP_ROOT / "evaluation/manifest.json"
    summary = evaluate(manifest, mode="replay", output=directory / "original")
    template = summary["policies"]["template"]
    assert summary["deterministic"]["correct"] == 60
    assert template["guard_correctness"]["applicable_drafts"] == 54
    assert template["guard_correctness"]["not_applicable"] == 6
    assert template["schema_citation_valid"]["denominator"] == 57
    assert summary["policies"]["routed"]["unrun_tasks"] == 120
    original = [
        json.loads(line) for line in (directory / "original/results.jsonl").read_text().splitlines()
    ]
    row = next(
        row for row in original if row["policy"] == "template" and row["task"] == "explain_review"
    )
    annotations = directory / "annotations.json"
    annotations.write_text(
        json.dumps(
            {
                row["annotation_key"]: {
                    "correct": False,
                    "reviewer": "test-control",
                    "rationale": "Intentional scoring control; not a real quality judgment.",
                }
            }
        )
    )
    result = rescore(directory / "original", annotations, directory / "rescored", manifest)
    assert result["new_provider_calls"] == 0
    rescored = [
        json.loads(line) for line in (directory / "rescored/results.jsonl").read_text().splitlines()
    ]
    assert [row["output"] for row in rescored] == [row["output"] for row in original]
    assert [row["actual_cost_usd"] for row in rescored] == [
        row["actual_cost_usd"] for row in original
    ]
    assert rescored[0]["scores"]["semantic"]["correct"] is False
