"""Run trusted engine/policy code on bounded candidate data; never execute a PR plan."""

import argparse
import re
import subprocess
from pathlib import Path

from proofops.cli import main as cli
from proofops.config import APP_ROOT
from proofops.storage.bundles import INPUT_FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch("[a-f0-9]{40,64}", args.source_revision):
        raise ValueError("source revision must be an exact commit hash")
    source = args.bundle.resolve()
    if any(part in {"evaluator_only", "evaluation", ".git"} for part in source.parts):
        raise ValueError("CI review accepts supported input artifacts, not evaluation labels")
    destination = APP_ROOT / "artifacts/ci-input"
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in sorted(INPUT_FILES | {"manifest.json"}):
        path = source / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
            raise ValueError("candidate input contains a missing, linked or oversized artifact")
        raw = path.read_bytes()
        total += len(raw)
        if total > 5_242_880:
            raise ValueError("candidate input exceeds its aggregate size cap")
        (destination / name).write_bytes(raw)
    result = cli(
        [
            "review",
            "--bundle",
            str(destination),
            "--trusted-policy",
            str(APP_ROOT / "policies/approved/reports-demo.json"),
            "--trusted-map",
            str(APP_ROOT / "fixtures/replays/valid-resize/service-map.json"),
            "--require-supported",
            "--output",
            str(APP_ROOT / "artifacts/ci-review"),
        ]
    )
    summary = APP_ROOT / "artifacts/ci-review/summary.md"
    if summary.is_file():
        trusted_revision = subprocess.run(
            ["git", "-C", str(APP_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        summary.write_text(
            summary.read_text()
            + f"\nCandidate repository revision: `{args.source_revision}`. Trusted engine revision: `{trusted_revision}`. The bundled infrastructure candidate is a labelled synthetic fixture, not this commit's deployed resources.\n"
        )
    # This job deliberately demonstrates recurrence below the approved floor.
    # A changed fixture must be reviewed; it cannot turn this known failure green.
    return 0 if result == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
