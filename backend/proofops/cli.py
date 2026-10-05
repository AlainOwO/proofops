import argparse
import json
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

from proofops.config import APP_ROOT, get_settings
from proofops.domain.common import bytes_digest, canonical, strict_json
from proofops.domain.engine import review
from proofops.domain.schemas import RateCard, ServiceMap
from proofops.domain.summaries import markdown_summary
from proofops.models.explanations import template_explanation
from proofops.policies.fixtures import fixture_suite
from proofops.policies.guards import load_trusted
from proofops.storage.bundles import export_report, load_directory, redact_text, replay_export

EXIT_CODES = {"request_review": 0, "revise_change": 2, "collect_evidence": 3, "out_of_scope": 0}


def owned_path(path: Path, *, output=False) -> Path:
    target = path.resolve()
    if not target.is_relative_to(APP_ROOT) or any(
        part in {"evaluation", "evaluator_only", ".git"}
        for part in target.relative_to(APP_ROOT).parts
    ):
        raise ValueError(
            "runtime paths must stay inside the application and outside evaluator storage"
        )
    if output and not target.is_relative_to(APP_ROOT / "artifacts"):
        raise ValueError("generated output must stay inside the application's artifacts directory")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proofops")
    commands = parser.add_subparsers(dest="command", required=True)
    review_parser = commands.add_parser(
        "review", help="Review a sanitized input bundle with the shared deterministic engine"
    )
    review_parser.add_argument("--bundle", type=Path, required=True)
    review_parser.add_argument("--ai", choices=["off"], default="off")
    review_parser.add_argument("--output", type=Path, default=Path("artifacts/review"))
    review_parser.add_argument("--require-supported", action="store_true")
    review_parser.add_argument("--format", choices=["json", "human"], default="human")
    review_parser.add_argument(
        "--trusted-policy", type=Path, default=APP_ROOT / "policies/approved/reports-demo.json"
    )
    review_parser.add_argument(
        "--trusted-map",
        type=Path,
        help="Require the imported identity mapping to match this trusted mapping",
    )
    review_parser.add_argument(
        "--rate-card", type=Path, help="Explicit dated rate-card override; its hash is recorded"
    )
    replay_parser = commands.add_parser(
        "replay", help="Reproduce a saved report at its recorded time without model calls"
    )
    replay_parser.add_argument("bundle", type=Path)
    guards_parser = commands.add_parser(
        "guards", help="Guard-only fixtures; does not assess performance or cost"
    )
    guard_commands = guards_parser.add_subparsers(dest="guard_command", required=True)
    guard_test = guard_commands.add_parser("test")
    guard_test.add_argument("--policy-dir", type=Path, default=APP_ROOT / "policies/approved")
    guard_test.add_argument("--fixtures", type=Path, default=APP_ROOT / "fixtures/negative_cases")
    guard_test.add_argument("--output", type=Path, default=APP_ROOT / "artifacts/guards.json")
    ingest_parser = commands.add_parser(
        "ingest-costs", help="Idempotently ingest scoped FOCUS accounting rows"
    )
    ingest_parser.add_argument("--file", type=Path, required=True)
    ingest_parser.add_argument("--dataset", default="focus-sample")
    collect_parser = commands.add_parser(
        "collect", help="Read scoped ECS/CloudWatch evidence; no deployment operations"
    )
    collect_parser.add_argument("--mode", choices=["live", "replay"], required=True)
    collect_parser.add_argument("--recording", type=Path)
    collect_parser.add_argument(
        "--output", type=Path, default=APP_ROOT / "artifacts/aws-collection.json"
    )
    evaluate_parser = commands.add_parser(
        "evaluate", help="Explicit evaluator-only entry point; never used by API or worker"
    )
    evaluate_parser.add_argument(
        "--manifest", type=Path, default=APP_ROOT / "evaluation/manifest.json"
    )
    evaluate_parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    evaluate_parser.add_argument("--output", type=Path, default=APP_ROOT / "artifacts/evaluation")
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            bundle = load_directory(args.bundle)
            trusted = load_trusted(args.trusted_policy)
            if args.trusted_map:
                mapping = ServiceMap.model_validate(
                    strict_json(owned_path(args.trusted_map).read_bytes())
                )
                if (
                    mapping.scope != trusted.contract.scope
                    or mapping.scope != bundle.change.service_map.scope
                    or mapping.repository != bundle.change.service_map.repository
                ):
                    raise ValueError(
                        "imported service identity differs from the trusted service map"
                    )
            if args.rate_card:
                raw = owned_path(args.rate_card).read_bytes()
                if len(raw) > 1_048_576:
                    raise ValueError("rate card exceeds size bound")
                bundle.rates = RateCard.model_validate(strict_json(raw))
                bundle.input_hashes = {
                    **bundle.input_hashes,
                    "configured-rates.json": bytes_digest(raw),
                }
            report = review(bundle, trusted)
            explanation = template_explanation(report)
            target = args.output.resolve()
            if not target.is_relative_to(APP_ROOT / "artifacts"):
                raise ValueError(
                    "report output must be inside the application's artifacts directory"
                )
            target.mkdir(parents=True, exist_ok=True)
            (target / "report.json").write_bytes(canonical(report))
            (target / "explanation.json").write_bytes(canonical(explanation))
            (target / "review.zip").write_bytes(export_report(bundle, report, explanation, trusted))
            (target / "summary.md").write_text(markdown_summary(report))
            print(canonical(report).decode() if args.format == "json" else markdown_summary(report))
            code = (
                3
                if args.require_supported and report.outcome == "out_of_scope"
                else EXIT_CODES[report.outcome]
            )
        elif args.command == "replay":
            path = args.bundle / "review.zip" if args.bundle.is_dir() else args.bundle
            if not path.resolve().is_relative_to(APP_ROOT / "artifacts") or path.is_symlink():
                raise ValueError(
                    "replay exports must be inside the application artifacts directory"
                )
            if path.stat().st_size > 5_242_880:
                raise ValueError("replay archive exceeds size limit")
            report, matches = replay_export(path.read_bytes())
            print(
                json.dumps(
                    {
                        "reproduced": matches,
                        "outcome": report.outcome,
                        "evaluation_reference_time": report.evaluation_reference_time.isoformat(),
                        "trust": "recorded snapshot; not a fresh deployment approval",
                    }
                )
            )
            code = 0 if matches else 1
        elif args.command == "guards":
            result = fixture_suite(
                load_trusted(owned_path(args.policy_dir) / "reports-demo.json"),
                fixtures=owned_path(args.fixtures),
            )
            target = owned_path(args.output, output=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical(result))
            print(json.dumps(result))
            code = 0 if result["passed"] else 2
        elif args.command == "ingest-costs":
            from proofops.storage.analytics import billing_analytics, ingest_costs
            from proofops.storage.database import session_factory

            path = owned_path(args.file)
            if path.stat().st_size > 5_242_880 or not 1 <= len(args.dataset) <= 120:
                raise ValueError("billing input or dataset label exceeds its limit")
            with session_factory().begin() as session:
                imported = ingest_costs(session, path.read_bytes(), args.dataset)
                print(json.dumps({"import": imported, "analytics": billing_analytics(session)}))
            code = 0
        elif args.command == "collect":
            from proofops.collectors.aws import AWSCollector, ReplayCollector

            settings = get_settings()
            scope = load_trusted().contract.scope
            if args.mode == "live":
                if (
                    settings.aws_account_id,
                    settings.aws_region,
                    settings.aws_cluster,
                    settings.aws_service,
                ) != (scope.account_id, scope.region, scope.cluster, scope.service):
                    raise ValueError(
                        "AWS configuration must match the separately reviewed service scope"
                    )
                result = AWSCollector.from_settings(settings).collect(scope)
            else:
                if not args.recording:
                    raise ValueError("collector replay requires --recording")
                path = owned_path(args.recording)
                if path.stat().st_size > 1_048_576:
                    raise ValueError("collector recording exceeds size bound")
                result = ReplayCollector(strict_json(path.read_bytes())).collect(scope)
            target = owned_path(args.output, output=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical(result))
            print(
                json.dumps(
                    {
                        "mode": result["mode"],
                        "origin": result["origin"],
                        "sources": [
                            {"source": item["source"], "status": item["status"]}
                            for item in result["sources"]
                        ],
                    }
                )
            )
            code = 0
        else:
            # Only this explicitly invoked evaluation command can load evaluator
            # files. The API, worker and model context have no such capability.
            code = subprocess.run(  # noqa: S603 - fixed local evaluator program
                [
                    sys.executable,
                    str(APP_ROOT / "evaluation/run.py"),
                    "--manifest",
                    str(args.manifest),
                    "--mode",
                    args.mode,
                    "--output",
                    str(args.output),
                ],
                check=False,
                timeout=3600,
            ).returncode
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "error": "validation_failed",
                    "details": [
                        {"loc": list(item["loc"]), "message": item["msg"], "type": item["type"]}
                        for item in exc.errors()
                    ],
                }
            )
        )
        code = 1
    except (ValueError, OSError, OverflowError, RuntimeError) as exc:
        print(json.dumps({"error": "input_or_execution_error", "detail": redact_text(str(exc))}))
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
