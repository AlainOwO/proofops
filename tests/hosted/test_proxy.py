"""Exercise the isolated hosted stack: demo.localhost, loopback 15080/15443.

Requires seeded Compose project proofops-hosted-check with Caddy's internal test
issuer. DNS is forced to loopback; this never contacts a public demo or ACME API.
"""

import json
import shutil
import subprocess
import time

import pytest


def request(path="/", *, method="GET", headers=(), tls=True):
    executable = shutil.which("curl")
    assert executable is not None
    port = 15443 if tls else 15080
    command = [
        executable,
        "--silent",
        "--show-error",
        "--insecure",
        "--max-time",
        "5",
        "--noproxy",
        "*",
        "--resolve",
        f"demo.localhost:{port}:127.0.0.1",
        "--dump-header",
        "-",
        "--request",
        method,
    ]
    for header in headers:
        command.extend(["--header", header])
    if method not in {"GET", "HEAD"}:
        command.extend(["--data", "{}"])
    command.append(f"{'https' if tls else 'http'}://demo.localhost:{port}{path}")
    response = subprocess.run(command, capture_output=True, text=True, check=False, timeout=8)  # noqa: S603
    assert response.returncode == 0, "The isolated TLS test endpoint must be reachable"
    head, _, body = response.stdout.partition("\n\n")
    lines = head.splitlines()
    status = int(lines[0].split()[1])
    actual = {
        key.lower(): value.strip()
        for line in lines[1:]
        if ":" in line
        for key, value in [line.split(":", 1)]
    }
    assert actual["x-frame-options"] == "DENY"
    assert actual["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in actual["content-security-policy"]
    if tls:
        assert actual["strict-transport-security"] == "max-age=31536000"
    return status, actual, body


def test_tls_public_demo_serves_only_seeded_results_and_read_only_identity():
    assert request("/readyz")[0] == 200
    status, _, body = request("/api/v1/auth/session")
    identity = json.loads(body)
    assert status == 200 and identity["public_demo"] and identity["role"] == "viewer"
    assert identity["username"] is None and identity["csrf_token"] is None
    status, _, body = request("/api/v1/reviews")
    listing = json.loads(body)
    assert status == 200 and listing["total"] == len(listing["items"]) == 3
    for item in listing["items"]:
        status, _, body = request(f"/api/v1/reviews/{item['id']}")
        detail = json.loads(body)
        assert status == 200 and detail["guard_drafts"] == []
        assert detail["report"]["origin"] == "synthetic_fixture"
    assert request("/")[0] == 200


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"])
def test_hosted_docs_are_unavailable_without_external_scripts(path):
    status, _, body = request(path)
    assert status in {403, 404} and "<script" not in body


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/bundles"),
        ("POST", "/api/v1/reviews"),
        ("POST", "/api/v1/billing/import-sample"),
        ("POST", "/api/v1/admin/reset-demo-data"),
        ("PUT", "/api/v1/future"),
        ("PATCH", "/api/v1/future"),
        ("DELETE", "/api/v1/future"),
    ],
)
def test_proxy_cannot_promote_public_demo_writes(method, path):
    status, _, _ = request(path, method=method, headers=("X-Forwarded-For: 198.51.100.42",))
    assert status == 403


def test_redirect_and_origin_and_host_rejections_keep_headers():
    status, headers, _ = request("/", tls=False)
    assert status == 308 and headers["location"] == "https://demo.localhost/"
    assert request("/api/v1/reviews", headers=("Origin: https://evil.invalid",))[0] == 403
    assert request("/healthz", headers=("Host: evil.invalid",))[0] == 400
    assert request("/", tls=False, headers=("Host: evil.invalid",))[0] == 400


def test_proxy_upstream_failure_retains_headers_and_hsts():
    executable = shutil.which("docker")
    assert executable is not None
    container = "proofops-hosted-check-api-1"

    def docker(*args):
        return subprocess.run(  # noqa: S603
            [executable, *args], capture_output=True, text=True, check=False, timeout=20
        )

    identity = docker(
        "inspect", "--format", '{{ index .Config.Labels "com.docker.compose.project" }}', container
    )
    assert identity.returncode == 0 and identity.stdout.strip() == "proofops-hosted-check"
    try:
        assert docker("stop", "--time", "2", container).returncode == 0
        assert request("/readyz")[0] == 502
    finally:
        assert docker("start", container).returncode == 0
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if request("/readyz")[0] == 200:
                break
            time.sleep(0.2)
        else:
            pytest.fail("The isolated API did not recover after the proxy-error check")
