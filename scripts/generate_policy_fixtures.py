import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from proofops.policies.guards import load_trusted

ROOT = Path(__file__).resolve().parents[1]
trusted = load_trusted()
contract = trusted.contract
reference = datetime(2026, 10, 5, 12, tzinfo=UTC).timestamp()
base = {
    "scope": contract.scope.model_dump(mode="json"),
    "image_digest": contract.applicability.image_digest,
    "profile_hash": contract.applicability.workload_profile_hash,
    "dependency_hash": contract.applicability.dependency_state_hash,
    "non_resize_config_hash": contract.applicability.non_resize_config_hash,
    "memory_mib": 2048,
    "candidate_commit": "b" * 40,
    "reference_epoch": reference,
}
cases = []
for name, memory, expected in [
    ("known-failure", 1024, "deny"),
    ("repaired", 4096, "pass"),
    ("exact-bound", 2048, "pass"),
    ("larger", 8192, "pass"),
    ("unrelated", 1024, "pass"),
    ("unknown", None, "unresolved"),
    ("changed-applicability", 1024, "unresolved"),
    ("valid-exception", 1024, "pass"),
    ("expired-exception", 1024, "deny"),
    ("wrong-scope-exception", 1024, "deny"),
]:
    value = copy.deepcopy(base)
    value["memory_mib"] = memory
    if name == "unrelated":
        value["scope"]["service"] = "another-service"
    if name == "changed-applicability":
        value["image_digest"] = "sha256:" + "c" * 64
    case = {"id": name, "origin": "synthetic_fixture", "input": value, "expected": expected}
    if name.endswith("exception"):
        exception = {
            "scope": copy.deepcopy(base["scope"]),
            "candidate_commit": base["candidate_commit"],
            "guard_revision": trusted.guard.revision,
            "expires_epoch": reference + 3600,
        }
        if name == "expired-exception":
            exception["expires_epoch"] = reference
        if name == "wrong-scope-exception":
            exception["scope"]["service"] = "another-service"
        case["fixture_exception"] = exception
    cases.append(case)
path = ROOT / "fixtures/negative_cases/memory-floor.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(cases, indent=2) + "\n")
print("Generated ten original guard regression fixtures.")
