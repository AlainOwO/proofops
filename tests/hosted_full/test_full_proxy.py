"""Actual two-host HTTPS checks. All HTTP/DNS traffic is forced to loopback.

Use scripts.prepare_hosted_full_checks and the reserved disposable projects.
Secrets and session cookies stay in private files or memory, never test output.
"""

import json
import secrets
import shutil
import socket
import ssl
import subprocess
import time
from uuid import uuid4

import httpx
import pytest

from scripts.configure_hosted import read_private
from scripts.prepare_hosted_full_checks import FULL_PROJECT, PRIVATE, PUBLIC_PROJECT

FULL_URL = "https://full.localhost:15443"
PUBLIC_URL = "https://demo.localhost:15443"


def require_private(condition, message):
    if not condition:
        pytest.fail(message, pytrace=False)


class PrivateConfiguration:
    def __init__(self):
        self.full = read_private(PRIVATE / ".env.hosted-full")
        self.users = read_private(PRIVATE / ".env.users")

    def client(self, *, gateway=True, public=False):
        auth = None
        if gateway and not public:
            auth = httpx.BasicAuth(
                self.full["FULL_BASIC_AUTH_USER"], self.full["FULL_BASIC_AUTH_PASSWORD"]
            )
        return httpx.Client(
            base_url=PUBLIC_URL if public else FULL_URL,
            auth=auth,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "root.crt")),
            trust_env=False,
            timeout=15,
        )


@pytest.fixture
def private():
    return PrivateConfiguration()


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    original = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        require_private(
            name in {"full.localhost", "demo.localhost"}, "Hosted HTTP tests must stay on loopback"
        )
        return original("127.0.0.1", port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def security_headers(response):
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def login(client, private, role="admin"):
    challenge = client.get("/api/v1/auth/login")
    assert challenge.status_code == 200 and challenge.json()["public_demo"] is False
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": private.users[f"FULL_{role.upper()}_USERNAME"],
            "password": private.users[f"FULL_{role.upper()}_PASSWORD"],
        },
        headers={"X-CSRF-Token": challenge.json()["csrf_token"], "Origin": FULL_URL},
    )
    assert response.status_code == 200
    session = response.json()
    assert session["role"] == role and session["public_demo"] is False
    require_private(bool(session["csrf_token"]), "Application login must return session CSRF")
    client.headers.update({"X-CSRF-Token": session["csrf_token"], "Origin": FULL_URL})
    return session


def docker(*args, input=None):
    executable = shutil.which("docker")
    assert executable is not None
    result = subprocess.run(  # noqa: S603
        [executable, *args],
        input=input,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    require_private(result.returncode == 0, "Isolated Docker check must succeed")
    return result.stdout


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/"),
        ("HEAD", "/"),
        ("GET", "/assets/missing.js"),
        ("GET", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/openapi.json"),
        ("POST", "/api/v1/bundles"),
        ("PUT", "/api/v1/future"),
        ("PATCH", "/api/v1/future"),
        ("DELETE", "/api/v1/future"),
        ("OPTIONS", "/api/v1/reviews"),
    ],
)
def test_full_host_requires_basic_auth_on_every_path_and_method(private, method, path):
    with private.client(gateway=False) as client:
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"].startswith("Basic ")
        security_headers(response)


def test_gateway_and_application_login_are_independent(private):
    with private.client() as client:
        wrong = client.get(
            "/", auth=(private.full["FULL_BASIC_AUTH_USER"], secrets.token_urlsafe(48))
        )
        assert wrong.status_code == 401
        security_headers(wrong)
        page = client.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        security_headers(page)
        assert client.get("/api/v1/reviews").status_code == 401
        assert client.get("/api/v1/auth/login").status_code == 200
        login(client, private)
        assert client.get("/readyz").status_code == 200
        cookies = list(client.cookies.jar)
        session = next(cookie for cookie in cookies if cookie.name == "__Host-proofops_session")
        require_private(
            session.secure and session.path == "/" and not session.domain_specified,
            "Hosted sessions must be Secure and host-only",
        )
        require_private(
            session.has_nonstandard_attr("HttpOnly")
            and session.get_nonstandard_attr("SameSite").lower() == "lax",
            "Hosted sessions must retain HttpOnly/SameSite",
        )
        with private.client(gateway=False) as outside:
            outside.cookies.update(client.cookies)
            response = outside.get("/api/v1/reviews")
            assert response.status_code == 401 and "www-authenticate" in response.headers


def test_full_worker_completes_admin_write_without_promoting_public_demo(private):
    with (
        private.client() as admin,
        private.client() as viewer,
        private.client(public=True) as public,
    ):
        login(admin, private)
        login(viewer, private, "viewer")
        assert (
            admin.post(
                "/api/v1/bundles", json={"replay": "valid-resize"}, headers={"X-CSRF-Token": ""}
            ).status_code
            == 403
        )
        imported = admin.post("/api/v1/bundles", json={"replay": "valid-resize"})
        assert imported.status_code == 201
        queued = admin.post(
            "/api/v1/reviews",
            json={"bundle_id": imported.json()["bundle_id"], "ai_preference": "off"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert queued.status_code == 202
        identifier = queued.json()["review_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            detail = admin.get(f"/api/v1/reviews/{identifier}")
            assert detail.status_code == 200
            if detail.json()["job"]["state"] == "completed":
                break
            time.sleep(0.2)
        else:
            pytest.fail("The default full-mode worker must complete the submitted AI-off review")
        assert viewer.get(f"/api/v1/reviews/{identifier}").status_code == 200
        assert viewer.post("/api/v1/bundles", json={"replay": "valid-resize"}).status_code == 403
        listing = public.get("/api/v1/reviews")
        assert listing.status_code == 200 and listing.json()["total"] == 3
        assert public.get(f"/api/v1/reviews/{identifier}").status_code == 404
        # Even a deliberately copied full admin cookie cannot enable public writes.
        session = next(
            cookie for cookie in admin.cookies.jar if cookie.name == "__Host-proofops_session"
        )
        rejected = public.post(
            "/api/v1/bundles",
            json={"replay": "valid-resize"},
            headers={"Cookie": f"{session.name}={session.value}"},
        )
        assert rejected.status_code == 403
        assert public.post("/api/v1/auth/login", json={}).status_code == 403
        identity = public.get("/api/v1/auth/session").json()
        assert identity["public_demo"] and identity["role"] == "viewer"


def test_forwarded_headers_cannot_bypass_hostname_gate_and_origins_remain_exact(private):
    with private.client(gateway=False) as outside, private.client() as client:
        response = outside.get(
            "/api/v1/auth/login",
            headers={"X-Forwarded-Host": "demo.localhost", "X-Forwarded-For": "198.51.100.9"},
        )
        assert response.status_code == 401 and "www-authenticate" in response.headers
        assert client.get("/api/v1/auth/login", headers={"Origin": PUBLIC_URL}).status_code == 403
        assert client.get("/", headers={"Host": "unknown.invalid"}).status_code == 400
        redirect = client.get("http://full.localhost:15080/")
        assert (
            redirect.status_code == 308
            and redirect.headers["location"] == "https://full.localhost/"
        )
        login(client, private)
        for path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"):
            response = client.get(path)
            assert response.status_code == 404 and "<script" not in response.text
            security_headers(response)


def test_full_login_lockout_remains_on_despite_forged_client_ips(private):
    username, password = "lockout-check-" + secrets.token_hex(6), secrets.token_urlsafe(48)
    docker(
        "exec",
        "-i",
        FULL_PROJECT + "-api-1",
        "proofops",
        "users",
        "create",
        "--username",
        username,
        "--role",
        "viewer",
        "--password-stdin",
        input=password + "\n",
    )
    with private.client() as client:
        token = client.get("/api/v1/auth/login").json()["csrf_token"]
        for attempt in range(5):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": secrets.token_urlsafe(48)},
                headers={
                    "X-CSRF-Token": token,
                    "Origin": FULL_URL,
                    "X-Forwarded-For": f"198.51.100.{attempt + 1}",
                },
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": token, "Origin": FULL_URL, "X-Forwarded-For": "203.0.113.9"},
        )
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_running_stacks_publish_only_caddy_and_keep_storage_networks_and_credentials_separate(
    private,
):
    containers = []
    for project in (PUBLIC_PROJECT, FULL_PROJECT):
        identifiers = docker(
            "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project
        ).split()
        assert identifiers
        containers.extend(json.loads(docker("inspect", *identifiers)))
    volumes = {PUBLIC_PROJECT: set(), FULL_PROJECT: set()}
    for container in containers:
        labels = container["Config"]["Labels"]
        project, service = (
            labels["com.docker.compose.project"],
            labels["com.docker.compose.service"],
        )
        bindings = container["HostConfig"]["PortBindings"] or {}
        if service == "caddy":
            assert project == PUBLIC_PROJECT and set(bindings) == {"80/tcp", "443/tcp"}
            assert all(
                binding["HostIp"] == "127.0.0.1"
                for published in bindings.values()
                for binding in published
            )
            assert not any(
                name.endswith("_database") for name in container["NetworkSettings"]["Networks"]
            )
        else:
            assert not bindings
            assert not set(container["NetworkSettings"]["Networks"]) - {
                project + "_application",
                project + "_database",
            }
        volumes[project].update(
            mount["Name"] for mount in container["Mounts"] if mount["Type"] == "volume"
        )
        env = dict(value.split("=", 1) for value in container["Config"]["Env"])
        require_private(
            "FULL_BASIC_AUTH_PASSWORD" not in env,
            "No container may receive plaintext gateway credentials",
        )
        if service == "caddy":
            require_private(
                env["FULL_BASIC_AUTH_HASH"] == private.full["FULL_BASIC_AUTH_HASH"],
                "Caddy must receive the exact generated bcrypt hash",
            )
            require_private(
                not any("PASSWORD" in key or "DATABASE_URL" == key for key in env),
                "Caddy must not receive database passwords",
            )
        if service in {"api", "worker"}:
            assert env["PROOFOPS_MODE"] == "hosted" and env["AI_MODE"] == "off"
            assert env["SESSION_COOKIE_SECURE"] == "true"
            assert env["PROOFOPS_PUBLIC_DEMO"] == ("false" if project == FULL_PROJECT else "true")
            require_private(
                env["DATABASE_URL"].startswith("postgresql+psycopg://proofops_runtime:"),
                "API/worker must use runtime credentials",
            )
            docker(
                "exec",
                container["Id"],
                "python",
                "-c",
                "from proofops.storage.roles import assert_runtime_role; from proofops.storage.database import session_factory; assert_runtime_role(session_factory())",
            )
    assert (
        volumes[PUBLIC_PROJECT]
        and volumes[FULL_PROJECT]
        and volumes[PUBLIC_PROJECT].isdisjoint(volumes[FULL_PROJECT])
    )
    full_worker = next(
        container
        for container in containers
        if container["Name"] == "/" + FULL_PROJECT + "-worker-1"
    )
    assert full_worker["State"]["Running"]
    for project in (PUBLIC_PROJECT, FULL_PROJECT):
        for network in ("application", "database"):
            assert json.loads(docker("network", "inspect", project + "_" + network))[0]["Internal"]
