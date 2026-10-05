"""Validate the effective Compose model without resolving any private environment."""

import json
import shutil
import subprocess

from proofops.config import APP_ROOT


def compose_model(filename):
    docker = shutil.which("docker")
    assert docker is not None, "Docker Compose is required for deployment checks"
    result = subprocess.run(  # noqa: S603
        [
            docker,
            "compose",
            "--env-file",
            "/dev/null",
            "-f",
            str(APP_ROOT / filename),
            "config",
            "--no-interpolate",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, "Compose configuration must validate"
    return json.loads(result.stdout)


def test_compose_core_services_have_cpu_and_memory_limits():
    services = compose_model("compose.yaml")["services"]
    for name in ("db", "migrate", "api", "worker", "web"):
        assert 0 < float(services[name]["cpus"]) <= 1
        memory = str(services[name]["mem_limit"]).lower()
        units = {"k": 1024, "m": 1024**2, "g": 1024**3}
        count = int(memory[:-1]) * units[memory[-1]] if memory[-1] in units else int(memory)
        assert 0 < count <= 1_073_741_824
