"""Run bounded local experiments. Never creates AWS resources or calls a model."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from proofops.domain.common import bytes_digest, digest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "artifacts/workload"
THRESHOLDS = {
    "min_correct_requests_per_run": 10000,
    "max_p95_latency_ms_exclusive": 250,
    "max_http_failure_rate_exclusive": 0.01,
    "max_incorrect_successful_responses": 0,
    "max_dropped_iterations": 0,
    "max_restarts": 0,
    "required_repetitions": 3,
}
ALLOCATIONS = {
    "baseline": {"cpus": "2.0", "memory_mib": 512},
    "candidate": {"cpus": "1.0", "memory_mib": 256},
}


def now():
    return datetime.now(UTC).isoformat()


def experiment_directory(series):
    base = ROOT / "artifacts/workload"
    if series is None:
        return base
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", series):
        raise ValueError("series must be 1–64 letters, digits, underscores or hyphens")
    destination = base / series
    if not destination.resolve().is_relative_to(base.resolve()):
        raise ValueError("series must stay inside the workload artifact directory")
    return destination


def command(args, *, timeout=30, check=True, **kwargs):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        creationflags=0x08000000 if sys.platform == "win32" else 0,
        **kwargs,
    )


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def image_info():
    value = json.loads(command(["docker", "image", "inspect", "proofops-workload:latest"]).stdout)[
        0
    ]
    return {"id": value["Id"], "platform": f"{value['Os']}/{value['Architecture']}"}


def pins(image):
    return {
        "image_digest": image["id"],
        "image_digest_kind": "local_image_config_digest",
        "platform": image["platform"],
        "profile_hash": bytes_digest((ROOT / "testing/virtual_users.js").read_bytes()),
        "dependency_hash": bytes_digest((ROOT / "uv.lock").read_bytes()),
        "server_hash": bytes_digest((ROOT / "demo/reporting_api/server.py").read_bytes()),
        "warmup_policy": "100 sequential requests with 80/15/5 class mix, outside measured window",
        "non_resize_config_hash": digest(
            {
                "command": ["python", "demo/reporting_api/server.py"],
                "environment": {"WORKLOAD_HOST": "0.0.0.0"},  # noqa: S104 - container-only; published on loopback
                "network": "loopback-only",
                "pressure": "disabled",
            }
        ),
    }


def container_start(image_id, role, memory=None, pressure=False):
    allocation = ALLOCATIONS.get(role, {"cpus": "1.0", "memory_mib": memory})
    memory = memory or allocation["memory_mib"]
    name = f"proofops-experiment-{uuid4().hex[:12]}"
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "proofops.owned=workload-experiment",
        "--memory",
        f"{memory}m",
        "--memory-swap",
        f"{memory}m",
        "--cpus",
        allocation["cpus"],
        "-p",
        "127.0.0.1:18080:8080",
        "-e",
        "WORKLOAD_HOST=0.0.0.0",
    ]
    if pressure:
        args += [
            "-e",
            "PROOFOPS_ENABLE_PRESSURE=I_UNDERSTAND_ISOLATED_CONTAINER",
            "-e",
            "PRESSURE_MIB=128",
        ]
    args += [image_id, "python", "demo/reporting_api/server.py"]
    return command(args).stdout.strip()


def container_state(identifier):
    value = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
    return {
        "state": value["State"],
        "restart_count": value["RestartCount"],
        "memory_bytes": value["HostConfig"]["Memory"],
        "nano_cpus": value["HostConfig"]["NanoCpus"],
        "image": value["Image"],
        "labels": value["Config"].get("Labels", {}),
    }


def cleanup(identifier):
    state = container_state(identifier)
    if state["labels"].get("proofops.owned") != "workload-experiment":
        raise ValueError("refusing to remove a container without this runner's ownership label")
    command(["docker", "rm", "-f", identifier])


def ready(client):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            if client.get("/healthz").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("isolated workload did not become ready within 35 seconds")


def warmup(client, count=100):
    for index in range(count):
        size = 50 if index % 20 < 16 else 300 if index % 20 < 19 else 1500
        items = [
            {"item_id": f"item-{i}", "amount_cents": ((i * 37 + index % 100) % 20000) - 1000}
            for i in range(size)
        ]
        body = {"request_id": f"warmup-{index}", "currency": "USD", "items": items}
        response = client.post("/v1/reports/summary", json=body)
        if response.status_code != 200 or response.json() != {
            "request_id": body["request_id"],
            "currency": "USD",
            "item_count": size,
            "total_cents": sum(item["amount_cents"] for item in items),
        }:
            raise RuntimeError("independent warmup response oracle failed")


def metric(summary, name, field="count", default=0):
    return summary["k6"]["metrics"].get(name, {}).get("values", {}).get(field, default)


def run_one(image, role, run_id, profile):
    directory = RESULTS / run_id
    if directory.exists():
        raise ValueError(f"run {run_id} already exists; use an unused run ID to preserve evidence")
    directory.mkdir(parents=True)
    identifier = container_start(image["id"], role)
    print(f"{run_id}: warming the isolated {role} container", flush=True)
    try:
        with httpx.Client(base_url="http://127.0.0.1:18080", timeout=10) as client:
            ready(client)
            warmup(client)
        before = container_state(identifier)
        started = now()
        executable = ROOT / ".tools/bin" / ("k6.exe" if sys.platform == "win32" else "k6")
        executable = str(executable) if executable.exists() else "k6"
        environment = {
            **os.environ,
            "TARGET_URL": "http://127.0.0.1:18080",
            "RUN_ID": run_id,
            "PROFILE": profile,
            "K6_NO_USAGE_REPORT": "true",
            "K6_NO_COLOR": "true",
        }
        print(f"{run_id}: measured {profile} profile started at {started}", flush=True)
        result = command(
            [executable, "run", "--quiet", str(ROOT / "testing/virtual_users.js")],
            timeout=550,
            check=False,
            cwd=directory,
            env=environment,
        )
        ended = now()
        (directory / "k6.log").write_text(result.stdout + result.stderr)
        after = container_state(identifier)
        summary_path = directory / f"{run_id}.k6-summary.json"
        if not summary_path.is_file():
            save(
                directory / "failure.json",
                {
                    "run_id": run_id,
                    "exit_code": result.returncode,
                    "state": after,
                    "started_at": started,
                    "ended_at": ended,
                    "status": "execution_failed",
                },
            )
            raise RuntimeError("k6 produced no summary; inspect the saved execution failure")
        summary = json.loads(summary_path.read_text())
        dropped = int(metric(summary, "dropped_iterations"))
        complete = int(metric(summary, "reports_completed"))
        offered = int(metric(summary, "reports_started")) + dropped
        correct = int(metric(summary, "successful_reports"))
        terminal = (
            "completed"
            if result.returncode in {0, 99} and offered == complete + dropped
            else "interrupted"
        )
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "role": role,
            "origin": "local_observation",
            "environment": "isolated-local-docker",
            **pins(image),
            "allocation": ALLOCATIONS[role],
            "config_hash": digest({"pins": pins(image), "allocation": ALLOCATIONS[role]}),
            "profile": profile,
            "started_at": started,
            "ended_at": ended,
            "offered": offered,
            "expected_scheduled_full_requests_approx": 20400 if profile == "full" else 20,
            "completed": complete,
            "correct": correct,
            "http_failures": int(metric(summary, "reports_http_failures")),
            "incorrect_successful_responses": int(metric(summary, "wrong_successful_results")),
            "dropped_iterations": dropped,
            "unfinished_requests": offered - complete - dropped,
            "restarts": after["restart_count"] - before["restart_count"],
            "p95_latency_ms": metric(summary, "http_req_duration", "p(95)", None),
            "request_classes": {
                name: {
                    "completed": int(metric(summary, f"reports_completed_{name}")),
                    "correct": int(metric(summary, f"reports_correct_{name}")),
                    "p95_latency_ms": metric(summary, f"report_latency_{name}", "p(95)", None),
                }
                for name in ("small", "medium", "large")
            },
            "terminal_status": terminal,
            "k6_exit_code": result.returncode,
            "thresholds_failed": summary["thresholds_failed"],
            "contract_passed": profile == "full"
            and not summary["thresholds_failed"]
            and terminal == "completed"
            and after["state"]["Running"]
            and after["restart_count"] == before["restart_count"],
            "smoke_passed": profile == "smoke"
            and correct == 20
            and not summary["thresholds_failed"],
            "container_before": before,
            "container_after": after,
            "summary_hash": bytes_digest(summary_path.read_bytes()),
            "limitations": [
                "Local ARM/Docker measurements are not AWS x86_64 operating-bound evidence.",
                "No invoice, cloud savings or cross-run averaged p95 is reported.",
            ],
        }
        save(directory / "manifest.json", run)
        print(
            f"{run_id}: correct={correct}; p95={run['p95_latency_ms']:.2f} ms; dropped={dropped}; contract={run['contract_passed']}",
            flush=True,
        )
        return run
    finally:
        cleanup(identifier)


def pressure_experiment(image):
    if (RESULTS / "pressure-repair.json").exists():
        raise ValueError("pressure evidence already exists; choose a new --series")
    results = []
    for role, memory in (("failure", 64), ("repair", 256)):
        identifier = container_start(image["id"], "pressure", memory=memory, pressure=True)
        observation = {
            "role": role,
            "memory_mib": memory,
            "injected_pressure_mib": 128,
            "started_at": now(),
        }
        try:
            if role == "failure":
                try:
                    waited = command(["docker", "wait", identifier], timeout=35)
                    observation["wait_exit_code"] = int(waited.stdout.strip())
                except subprocess.TimeoutExpired:
                    observation["wait_timed_out"] = True
            else:
                with httpx.Client(base_url="http://127.0.0.1:18080", timeout=5) as client:
                    ready(client)
                    warmup(client, 20)
                observation["independently_verified_correct_responses"] = 20
            observation["container"] = container_state(identifier)
            observation["ended_at"] = now()
            observation["oom_confirmed_by_docker"] = observation["container"]["state"]["OOMKilled"]
            results.append(observation)
        finally:
            cleanup(identifier)
    value = {
        "schema_version": 1,
        "origin": "local_observation",
        "injected": True,
        **pins(image),
        "observations": results,
        "confirmed_failure_and_repair": results[0]["oom_confirmed_by_docker"]
        and results[1].get("independently_verified_correct_responses") == 20,
        "scope": "128 MiB startup allocation in isolated cgroup-limited containers; not an AWS approved bound.",
    }
    save(RESULTS / "pressure-repair.json", value)
    print(
        json.dumps({"pressure_repair_confirmed": value["confirmed_failure_and_repair"]}), flush=True
    )
    return value


def main():
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["smoke", "calibrate", "compare", "pressure", "all"])
    parser.add_argument(
        "--series", help="New experiment subdirectory; omit to resume the original series"
    )
    args = parser.parse_args()
    RESULTS = experiment_directory(args.series)
    image = image_info()
    if args.mode in {"smoke", "all"}:
        smoke = run_one(image, "baseline", "baseline-smoke-01", "smoke")
        if not smoke["smoke_passed"]:
            return 1
    if args.mode in {"pressure", "all"}:
        if not pressure_experiment(image)["confirmed_failure_and_repair"]:
            return 1
    if args.mode in {"calibrate", "all"}:
        baseline = run_one(image, "baseline", "baseline-calibration-01", "full")
        if not baseline["contract_passed"]:
            print(
                "Calibration baseline failed; thresholds remain unchanged and comparison is unrun.",
                flush=True,
            )
            return 1
        save(
            RESULTS / "frozen-contract.json",
            {
                "schema_version": 1,
                "frozen_at": now(),
                "thresholds": THRESHOLDS,
                "allocations": ALLOCATIONS,
                "pins": pins(image),
                "calibration_run": baseline["run_id"],
                "origin": "local_observation",
            },
        )
    if args.mode in {"compare", "all"}:
        frozen = json.loads((RESULTS / "frozen-contract.json").read_text())
        if (
            frozen["pins"] != pins(image)
            or frozen["thresholds"] != THRESHOLDS
            or frozen["allocations"] != ALLOCATIONS
        ):
            raise ValueError(
                "frozen comparison inputs changed; do not compare against this calibration"
            )
        runs = []
        for repetition in range(1, 4):
            for role in ("baseline", "candidate"):
                run_id = f"{role}-full-{repetition:02d}"
                saved = RESULTS / run_id / "manifest.json"
                run = (
                    json.loads(saved.read_text())
                    if saved.is_file()
                    else run_one(image, role, run_id, "full")
                )
                if any(run[key] != value for key, value in frozen["pins"].items()):
                    raise ValueError("existing run does not match frozen inputs")
                runs.append(run)
                save(
                    RESULTS / "comparison.json",
                    {
                        "schema_version": 1,
                        "origin": "local_observation",
                        "frozen_contract": frozen,
                        "runs": runs,
                        "complete": len(runs) == 6,
                        "passed": len(runs) == 6 and all(item["contract_passed"] for item in runs),
                        "aggregation": "Each run and request class assessed separately; p95 values are never averaged.",
                        "cost_basis": "No cloud/invoice cost measured; local resource allocations only.",
                    },
                )
        return 0 if all(item["contract_passed"] for item in runs) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
