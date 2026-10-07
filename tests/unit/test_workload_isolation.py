import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from proofops.config import APP_ROOT

from scripts import run_workload


@pytest.mark.parametrize("mode, public", [("hosted", False), ("hosted", True), ("local", True)])
def test_workload_runner_refuses_hosted_before_creating_containers(monkeypatch, mode, public):
    monkeypatch.setattr(
        run_workload,
        "get_settings",
        lambda: SimpleNamespace(proofops_mode=mode, proofops_public_demo=public),
    )
    monkeypatch.setattr(
        run_workload, "command", lambda *a, **kw: pytest.fail("hosted runner reached Docker")
    )
    with pytest.raises(ValueError, match="local mode"):
        run_workload.container_start("unused", "baseline")


def inspect_k6(tmp_path, *environment):
    configuration = tmp_path / "k6.json"
    configuration.write_text("{}")
    executable = APP_ROOT / ".tools/bin" / ("k6.exe" if os.name == "nt" else "k6")
    command = [str(executable), "--config", str(configuration), "inspect"]
    for value in environment:
        command += ["--env", value]
    command.append(str(APP_ROOT / "testing/virtual_users.js"))
    # inspect executes initialization only; no virtual user or HTTP request runs.
    return subprocess.run(  # noqa: S603 - pinned local test tool, fixed script and test inputs
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env={"PATH": os.environ.get("PATH", ""), "K6_NO_USAGE_REPORT": "true"},
    )


@pytest.mark.parametrize(
    "configuration",
    [
        "PROOFOPS_MODE=hosted",
        "PROOFOPS_PUBLIC_DEMO=true",
        "TARGET_URL=https://production.example.com",
        "TARGET_URL=http://127.0.0.1:8000",
        "TARGET_URL=http://api:8000",
    ],
)
def test_k6_initialization_rejects_non_test_targets(tmp_path, configuration):
    result = inspect_k6(tmp_path, configuration)
    assert result.returncode != 0
    assert (
        "restricted to the dedicated local target" in result.stderr
        or "disabled in hosted/public-demo" in result.stderr
    )


@pytest.mark.parametrize("profile", ["smoke", "full"])
def test_k6_preserves_existing_profiles_and_thresholds(tmp_path, profile):
    result = inspect_k6(tmp_path, f"PROFILE={profile}", "TARGET_URL=http://127.0.0.1:18080")
    assert result.returncode == 0
    options = json.loads(result.stdout)
    if profile == "smoke":
        assert options["scenarios"]["smoke"]["iterations"] == 20
    else:
        assert len(options["scenarios"]["workday_and_peak"]["stages"]) == 4
        assert options["scenarios"]["workday_and_peak"]["maxVUs"] == 200
    assert "successful_reports" in options["thresholds"]
