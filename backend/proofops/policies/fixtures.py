import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from proofops.config import APP_ROOT
from proofops.domain.common import canonical, strict_json
from proofops.policies.guards import TrustedRevision

PINNED_CONFTEST = "0.71.0"
REQUIRED = {
    "known-failure",
    "repaired",
    "exact-bound",
    "larger",
    "unrelated",
    "unknown",
    "changed-applicability",
    "valid-exception",
    "expired-exception",
    "wrong-scope-exception",
}


def policy_data(trusted: TrustedRevision) -> dict:
    contract = trusted.contract
    return {
        "proofops": {
            "scope": contract.scope.model_dump(mode="json"),
            "image_digest": contract.applicability.image_digest,
            "profile_hash": contract.applicability.workload_profile_hash,
            "dependency_hash": contract.applicability.dependency_state_hash,
            "non_resize_config_hash": contract.applicability.non_resize_config_hash,
            "minimum_task_memory_mib": trusted.guard.minimum_task_memory_mib,
            "guard_revision": trusted.guard.revision,
            "exceptions": [
                {
                    "scope": item.scope.model_dump(mode="json"),
                    "candidate_commit": item.candidate_commit,
                    "guard_revision": item.guard_revision,
                    "expires_epoch": item.expires_at.timestamp(),
                }
                for item in trusted.exceptions
            ],
        }
    }


def conftest_binary() -> str:
    local = APP_ROOT / ".tools/bin/conftest"
    binary = str(local) if local.is_file() else shutil.which("conftest")
    if not binary:
        raise RuntimeError("Conftest is unavailable; run python scripts/install_tools.py")
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, timeout=10, check=True
    )
    if f"Conftest: {PINNED_CONFTEST}" not in version.stdout:
        raise RuntimeError(f"Conftest {PINNED_CONFTEST} is required")
    return binary


def fixture_suite(
    trusted: TrustedRevision, *, fixtures: Path | None = None, template: Path | None = None
) -> dict:
    binary = conftest_binary()
    fixtures = fixtures or APP_ROOT / "fixtures/negative_cases"
    template = template or APP_ROOT / "policies/templates/ecs_task_memory_floor.rego"
    cases = strict_json((fixtures / "memory-floor.json").read_bytes())
    if {case["id"] for case in cases} != REQUIRED or len(cases) != len(REQUIRED):
        raise ValueError("trusted guard fixture set is incomplete or duplicated")
    results = []
    with tempfile.TemporaryDirectory(prefix="proofops-policy-") as directory:
        root = Path(directory)
        policy = root / "policy.rego"
        policy.write_bytes(template.read_bytes())
        for case in cases:
            data = policy_data(trusted)
            # Exception fixtures are reviewed test data, never read from an imported
            # change. Runtime guard enforcement uses trusted.exceptions only.
            if "fixture_exception" in case:
                data["proofops"]["exceptions"] = [case["fixture_exception"]]
            (root / "data.json").write_bytes(canonical(data))
            (root / "input.json").write_bytes(canonical(case["input"]))
            result = subprocess.run(
                [
                    binary,
                    "test",
                    str(root / "input.json"),
                    "--policy",
                    str(policy),
                    "--data",
                    str(root / "data.json"),
                    "--namespace",
                    "proofops",
                    "--output",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode not in {0, 1}:
                raise RuntimeError("Conftest could not execute the trusted policy")
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Conftest returned invalid result JSON") from exc
            failures = [
                finding["msg"] for record in output for finding in record.get("failures", [])
            ]
            warnings = [
                finding["msg"] for record in output for finding in record.get("warnings", [])
            ]
            actual = "deny" if failures else "unresolved" if warnings else "pass"
            results.append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "actual": actual,
                    "passed": actual == case["expected"],
                    "failures": failures,
                    "warnings": warnings,
                }
            )
    return {
        "passed": all(item["passed"] for item in results),
        "template_version": "ecs_task_memory_floor-v1",
        "conftest_version": PINNED_CONFTEST,
        "trusted_revision_hash": trusted.revision_hash,
        "fixtures": results,
        "scope": "Guard-only fixture validation; this does not establish performance or cost approval.",
    }
