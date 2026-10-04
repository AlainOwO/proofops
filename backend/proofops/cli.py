import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from proofops.config import APP_ROOT
from proofops.domain.common import canonical
from proofops.domain.engine import review
from proofops.models.explanations import template_explanation
from proofops.policies.guards import load_trusted
from proofops.storage.bundles import export_report, load_directory, replay_export

EXIT_CODES = {"request_review": 0, "revise_change": 2, "collect_evidence": 3, "out_of_scope": 0}


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
    replay_parser = commands.add_parser(
        "replay", help="Reproduce a saved report at its recorded time without model calls"
    )
    replay_parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            bundle = load_directory(args.bundle)
            trusted = load_trusted()
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
            print(canonical(report).decode())
            code = (
                3
                if args.require_supported and report.outcome == "out_of_scope"
                else EXIT_CODES[report.outcome]
            )
        else:
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
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "error": "validation_failed",
                    "details": exc.errors(include_input=False, include_url=False),
                }
            )
        )
        code = 1
    except (ValueError, OSError, OverflowError) as exc:
        print(json.dumps({"error": "input_or_execution_error", "detail": str(exc)}))
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
