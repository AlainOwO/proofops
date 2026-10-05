"""Explicit evaluation process. Labels are never passed into product/model calls."""

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proofops.config import Settings  # noqa: E402
from proofops.domain.common import (  # noqa: E402
    bytes_digest,
    canonical,
    digest,
    strict_json,
    utcnow,
)
from proofops.domain.engine import review  # noqa: E402
from proofops.domain.schemas import ReviewInput  # noqa: E402
from proofops.models.budget import load_price  # noqa: E402
from proofops.models.context import explanation_context  # noqa: E402
from proofops.models.explanations import template_explanation, validate_explanation  # noqa: E402
from proofops.models.router import ModelRouter  # noqa: E402
from proofops.policies.guards import (  # noqa: E402
    TrustedRevision,
    draft_from_approved,
    validate_proposal,
)

from evaluation.scoring import (  # noqa: E402
    annotation_key,
    score_deterministic,
    score_guard,
    semantic_score,
    summarize,
)


def evaluator_path(root, relative):
    path = (root / relative).resolve()
    if (
        not path.is_relative_to(root.resolve())
        or path.is_symlink()
        or path.stat().st_size > 10_000_000
    ):
        raise ValueError("evaluation artifact exceeds its path/size boundary")
    return path


def load_manifest(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT / "evaluation"):
        raise ValueError("evaluation manifests must be inside the application evaluation directory")
    manifest = strict_json(path.read_bytes())
    groups = {}
    for case in manifest["cases"]:
        if case["group"] in groups and groups[case["group"]] != case["split"]:
            raise ValueError("group leakage across evaluation splits")
        groups[case["group"]] = case["split"]
    counts = {
        split: sum(value == split for value in groups.values())
        for split in ("development", "calibration", "held_out")
    }
    if len(manifest["cases"]) != 60 or counts != {
        "development": 8,
        "calibration": 4,
        "held_out": 8,
    }:
        raise ValueError("the frozen corpus requires 60 cases in 8/4/8 groups")
    if len({case["case_id"] for case in manifest["cases"]}) != 60:
        raise ValueError("duplicate case IDs")
    if any(sum(item["group"] == group for item in manifest["cases"]) != 3 for group in groups):
        raise ValueError("each scenario group must have exactly three variants")
    labels_path = evaluator_path(path.parent, manifest["labels"])
    raw = labels_path.read_bytes()
    if bytes_digest(raw) != manifest["labels_sha256"]:
        raise ValueError("label hash changed after the reviewed manifest was frozen")
    return manifest, strict_json(raw)


def evaluate(manifest_path, *, mode, output, annotations_path=None):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("evaluation results must stay under application artifacts")
    output.mkdir(parents=True, exist_ok=True)
    manifest, labels = load_manifest(manifest_path)
    root = manifest_path.resolve().parent
    annotations = strict_json(annotations_path.read_bytes()) if annotations_path else {}
    settings = Settings()
    available = {}
    for policy in ("cheap_only", "strong_only", "routed"):
        slots = (
            [(settings.cheap_provider, settings.cheap_model)]
            if policy == "cheap_only"
            else [(settings.strong_provider, settings.strong_model)]
            if policy == "strong_only"
            else [
                (settings.cheap_provider, settings.cheap_model),
                (settings.strong_provider, settings.strong_model),
            ]
        )
        try:
            if (
                settings.ai_mode != "live"
                or Decimal(settings.ai_budget_usd) <= 0
                or Decimal(settings.ai_max_task_cost_usd) <= 0
            ):
                raise ValueError("live mode and positive budgets required")
            for provider, model in slots:
                if (
                    not model
                    or provider not in settings.providers
                    or not getattr(settings, provider + "_api_key").get_secret_value()
                ):
                    raise ValueError("model access is unconfigured")
                load_price(settings.model_prices_path, provider, model)
            available[policy] = True
        except (ValueError, OSError, ArithmeticError):
            available[policy] = False
    run_id = str(uuid4())
    router = ModelRouter(settings) if mode == "live" else None
    records, deterministic, contexts = [], [], []
    for case in manifest["cases"]:
        raw = evaluator_path(root, case["input"]).read_bytes()
        if bytes_digest(raw) != case["sha256"]:
            raise ValueError("case input hash differs from its frozen manifest")
        data = strict_json(raw)
        bundle = ReviewInput.model_validate(data["bundle"])
        trusted = TrustedRevision.model_validate(data["trusted"])
        started = time.perf_counter()
        report = review(bundle, trusted, review_id="evaluation-snapshot")
        engine_seconds = time.perf_counter() - started
        # The independent label is only consumed for scoring, never context.
        label = labels[case["case_id"]]
        deterministic.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "split": case["split"],
                "input_hash": case["sha256"],
                "outcome": report.outcome.value,
                "scores": score_deterministic(report, label),
                "rationale": label["rationale"],
            }
        )
        for compact in (True, False):
            try:
                system, user, metadata = explanation_context(report, compact=compact)
                context = {
                    **metadata,
                    "context_hash": digest({"system": system, "user": user}),
                    "status": "prepared",
                }
            except ValueError:
                context = {
                    "representation": "compact" if compact else "bounded_flat",
                    "status": "excluded_input_cap",
                    "input_bytes": None,
                }
            contexts.append(
                {
                    "case_id": case["case_id"],
                    "group": case["group"],
                    "split": case["split"],
                    **context,
                    "quality_comparison": "unrun without live calls plus independent semantic annotations",
                    "billing_tokens": None,
                    "billing_note": "Serialization bytes are not provider-billed tokens.",
                }
            )
        for policy in ("template", "cheap_only", "strong_only", "routed"):
            for task in ("explain_review", "draft_guard"):
                start = time.perf_counter()
                record = {
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "group": case["group"],
                    "split": case["split"],
                    "input_hash": case["sha256"],
                    "task": task,
                    "policy": policy,
                    "mode": mode,
                    "expected_label": label,
                    "actual_outcome": report.outcome.value,
                    "execution_status": "ran",
                    "origin": "synthetic_fixture",
                    "accepted_output": False,
                    "actual_cost_usd": "0",
                    "provider_attempt_count": 0,
                    "output": None,
                    "scores": {},
                    "model": None,
                    "prompt_version": "explanation-v1" if task == "explain_review" else "guard-v1",
                    "schema_version": 1,
                    "price_version": None,
                }
                if policy != "template" and (mode == "replay" or not available[policy]):
                    record.update(
                        execution_status="unrun",
                        reason="Live provider evaluation requires configured model IDs, keys, dated prices and an authorized positive budget.",
                        actual_cost_usd=None,
                        latency_seconds=None,
                        route="unrun",
                    )
                    records.append(record)
                    continue
                if task == "explain_review":
                    result = (
                        template_explanation(report)
                        if policy == "template"
                        else router.explain(
                            report,
                            ai_preference="auto",
                            policy=policy,
                            task_id=f"{run_id}:{case['case_id']}:{policy}:explain",
                        )
                    )
                    proposal = result.get("output")
                    mechanical = report.outcome == "out_of_scope" and proposal is None
                    if proposal is not None:
                        try:
                            validate_explanation(proposal, report)
                            mechanical = True
                        except ValueError:
                            mechanical = False
                    source = "template" if result.get("source") == "deterministic" else "model"
                    record["scores"] = {
                        "mechanical_valid": mechanical,
                        "semantic": semantic_score(
                            proposal,
                            label,
                            source=source,
                            input_hash=case["sha256"],
                            annotations=annotations,
                        ),
                    }
                    record["semantic_source"] = source
                    record["annotation_key"] = annotation_key(proposal, case["sha256"])
                else:
                    if not report.coverage["guard_applicable"]:
                        result = {
                            "status": "not_applicable",
                            "output": None,
                            "incremental_cost_usd": "0",
                            "attempts": [],
                        }
                    elif policy == "template":
                        result = {
                            "status": "template",
                            "output": draft_from_approved(trusted).model_dump(mode="json"),
                            "incremental_cost_usd": "0",
                            "attempts": [],
                        }
                    else:
                        result = router.guard(
                            trusted,
                            task_id=f"{run_id}:{case['case_id']}:{policy}:guard",
                            ai_preference="auto",
                            policy=policy,
                        )
                    proposal = result.get("output")
                    if proposal is not None:
                        validate_proposal(proposal, trusted)
                    record["scores"] = {"guard": score_guard(proposal, label)}
                attempts = result.get("attempts", [])
                uncertain = Decimal(result.get("pending_reserved_usd", "0")) > 0
                record.update(
                    output=proposal,
                    output_hash=digest(proposal),
                    result=result,
                    accepted_output=proposal is not None
                    and result["status"] in {"template", "accepted", "cached"},
                    provider_attempt_count=len(attempts),
                    actual_cost_usd=None if uncertain else result.get("incremental_cost_usd", "0"),
                    latency_seconds=time.perf_counter() - start + engine_seconds,
                    route=result.get("reason") or result.get("route_reason") or result["status"],
                    model=result.get("model"),
                    semantic_limitation="Model confidence and stronger-model agreement are not correctness labels.",
                )
                record["provider"] = result.get("provider") or (
                    attempts[-1].get("provider") if attempts else None
                )
                record["model"] = record["model"] or (
                    attempts[-1].get("model") if attempts else None
                )
                record["price_version"] = attempts[-1].get("price_version") if attempts else None
                record["usage"] = [attempt.get("usage") for attempt in attempts]
                record["original_usage"] = result.get("original_usage", [])
                records.append(record)
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "recorded_at": utcnow().isoformat(),
        "mode": mode,
        "manifest_hash": bytes_digest(manifest_path.read_bytes()),
        "corpus_version": manifest["corpus_version"],
        "deterministic": {
            "correct": sum(item["scores"]["correct"] for item in deterministic),
            "cases": len(deterministic),
            "groups": 20,
        },
        "policies": summarize(records),
        "policies_by_split": {
            split: summarize([row for row in records if row["split"] == split])
            for split in ("development", "calibration", "held_out")
        },
        "latency_basis": "Local sequential evaluation: deterministic engine plus context/retrieval and router/SDK processing, no API queue. UI jobs expose queue timestamps separately.",
        "uncertainty": {
            "variants_per_group": 3,
            "held_out_groups": 8,
            "zero_error_independent_30_upper95": 1 - 0.05 ** (1 / 30),
            "zero_error_independent_300_upper95": 1 - 0.05 ** (1 / 300),
            "note": "The bound examples are hypothetical independent trials; they are not confidence bounds for this synthetic correlated corpus.",
        },
        "limitations": [
            manifest["limitations"],
            "Mocked adapter tests do not measure model quality.",
            "Template semantics use a narrow independently authored rubric. New model prose requires output-bound independent annotations.",
            "No live model quality, parity, context-quality preservation or realized savings is claimed.",
        ],
    }
    for name, value in (
        ("summary.json", summary),
        ("deterministic.json", deterministic),
        ("contexts.json", contexts),
    ):
        (output / name).write_text(json.dumps(value, indent=2) + "\n")
    (output / "results.jsonl").write_bytes(b"\n".join(canonical(item) for item in records) + b"\n")
    print(
        json.dumps(
            {
                "deterministic": summary["deterministic"],
                "mode": mode,
                "executed_template_tasks": summary["policies"]["template"]["ran_tasks"],
                "unrun_provider_tasks": sum(
                    summary["policies"][policy]["unrun_tasks"]
                    for policy in ("cheap_only", "strong_only", "routed")
                ),
            }
        )
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation/manifest.json")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation")
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.manifest, mode=args.mode, output=args.output, annotations_path=args.annotations
    )
    return 0 if result["deterministic"]["correct"] == result["deterministic"]["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
