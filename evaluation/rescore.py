"""Apply independent annotations to saved outputs, without rerunning models."""

import argparse
import json
from pathlib import Path

from proofops.config import APP_ROOT
from proofops.domain.common import bytes_digest, canonical, strict_json, utcnow

from evaluation.run import load_manifest
from evaluation.scoring import semantic_score, summarize


def rescore(results_dir: Path, annotations_path: Path, output: Path, manifest_path: Path):
    results_dir, output = results_dir.resolve(), output.resolve()
    base = APP_ROOT / "artifacts"
    if not results_dir.is_relative_to(base) or not output.is_relative_to(base):
        raise ValueError("saved evaluation results must stay under artifacts")
    if output.exists():
        raise ValueError("choose a new output directory to preserve the original run")
    manifest, labels = load_manifest(manifest_path)
    summary = strict_json((results_dir / "summary.json").read_bytes())
    if summary["manifest_hash"] != bytes_digest(manifest_path.read_bytes()):
        raise ValueError("saved run does not match this frozen manifest")
    annotations = strict_json(annotations_path.read_bytes())
    inputs = {case["case_id"]: case["sha256"] for case in manifest["cases"]}
    rows = [
        strict_json(line)
        for line in (results_dir / "results.jsonl").read_bytes().splitlines()
        if line
    ]
    for row in rows:
        if row["input_hash"] != inputs[row["case_id"]]:
            raise ValueError("saved row does not match its frozen input")
        if row["execution_status"] == "ran" and row["task"] == "explain_review":
            row["scores"]["semantic"] = semantic_score(
                row["output"],
                labels[row["case_id"]],
                source=row["semantic_source"],
                input_hash=row["input_hash"],
                annotations=annotations,
            )
    summary.update(
        policies=summarize(rows),
        policies_by_split={
            split: summarize([row for row in rows if row["split"] == split])
            for split in ("development", "calibration", "held_out")
        },
        rescored_at=utcnow().isoformat(),
        annotation_file_hash=bytes_digest(annotations_path.read_bytes()),
        rescore_note="Independent annotation only; original execution times, costs and outputs retained. No model calls.",
    )
    output.mkdir(parents=True)
    (output / "summary.json").write_bytes(canonical(summary))
    (output / "results.jsonl").write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
    for name in ("contexts.json", "deterministic.json"):
        (output / name).write_bytes((results_dir / name).read_bytes())
    return {"records": len(rows), "new_provider_calls": 0, "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=APP_ROOT / "evaluation/manifest.json")
    args = parser.parse_args()
    print(json.dumps(rescore(args.results_dir, args.annotations, args.output, args.manifest)))


if __name__ == "__main__":
    main()
