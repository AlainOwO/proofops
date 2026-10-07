"""Validate the effective Compose model without resolving any private environment."""

import json
import shutil
import subprocess
from fnmatch import fnmatch

import pytest
from proofops.config import APP_ROOT


def compose_model(*filenames):
    docker = shutil.which("docker")
    assert docker is not None, "Docker Compose is required for deployment checks"
    result = subprocess.run(  # noqa: S603
        [
            docker,
            "compose",
            "--env-file",
            "/dev/null",
            *(argument for filename in filenames for argument in ("-f", str(APP_ROOT / filename))),
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
    model = json.loads(result.stdout)
    # Compose can serialize unresolved merged environments as KEY=value lists.
    for service in model["services"].values():
        if isinstance(service.get("environment"), list):
            service["environment"] = dict(value.split("=", 1) for value in service["environment"])
    return model


def test_compose_core_services_have_cpu_and_memory_limits():
    services = compose_model("compose.yaml")["services"]
    for name in ("db", "migrate", "api", "worker", "web"):
        assert 0 < float(services[name]["cpus"]) <= 1
        memory = str(services[name]["mem_limit"]).lower()
        units = {"k": 1024, "m": 1024**2, "g": 1024**3}
        count = int(memory[:-1]) * units[memory[-1]] if memory[-1] in units else int(memory)
        assert 0 < count <= 1_073_741_824


@pytest.mark.parametrize(
    "filename", ["compose.yaml", "compose.hosted.yaml", "compose.hosted-full.yaml"]
)
def test_migrate_and_api_share_image_and_verified_database_target(filename):
    services = compose_model(filename)["services"]
    api, migration = services["api"], services["migrate"]
    assert api["image"]
    for name in ("migrate", "worker", "roles", "seed"):
        if name in services:
            # Updating only the API image must also update the migration package.
            assert services[name]["image"] == api["image"]
            assert services[name]["build"] == api["build"]
    assert migration["environment"]["API_DATABASE_URL"] == api["environment"]["DATABASE_URL"]
    assert (
        migration["environment"]["DATABASE_URL"].split("@", 1)[1]
        == api["environment"]["DATABASE_URL"].split("@", 1)[1]
    )
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert (
        services["worker"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    )
    if filename == "compose.yaml":
        assert migration["command"] == ["python", "-m", "proofops.storage.migrate"]
        assert migration["environment"]["DATABASE_URL"] == api["environment"]["DATABASE_URL"]
    else:
        assert migration["command"] == ["python", "-m", "proofops.storage.roles", "migrate"]
        assert "proofops_owner:" in migration["environment"]["DATABASE_URL"]
        assert "proofops_runtime:" in migration["environment"]["API_DATABASE_URL"]


def test_hosted_compose_publishes_only_https_proxy_and_isolates_database():
    model = compose_model("compose.hosted.yaml")
    services = model["services"]
    assert {name for name, value in services.items() if value.get("ports")} == {"caddy"}
    assert {str(port["published"]) for port in services["caddy"]["ports"]} == {"80", "443"}
    assert model["networks"]["application"]["internal"] is True
    assert model["networks"]["database"]["internal"] is True
    assert set(services["db"]["networks"]) == {"database"}
    assert "database" not in services["web"]["networks"]
    assert "database" not in services["caddy"]["networks"]
    for name in ("api", "worker"):
        service = services[name]
        env = service["environment"]
        assert env["DATABASE_URL"].startswith("postgresql+psycopg://proofops_runtime:")
        assert env["PROOFOPS_MODE"] == "hosted" and env["PROOFOPS_PUBLIC_DEMO"] == "true"
        assert env["AI_MODE"] == "off" and env["ALLOWED_PROVIDERS"] == ""
        assert "POSTGRES_PASSWORD" not in env and "PROOFOPS_OWNER_PASSWORD" not in env
        assert service["read_only"] and "ALL" in service["cap_drop"]
        assert service["cpus"] and service["mem_limit"]
        assert all(volume.get("read_only") for volume in service["volumes"])
    assert services["migrate"]["environment"]["DATABASE_URL"].startswith(
        "postgresql+psycopg://proofops_owner:"
    )
    assert services["worker"]["profiles"] == ["worker"]
    assert "--no-proxy-headers" in services["api"]["command"]
    assert services["api"]["command"][services["api"]["command"].index("--workers") + 1] == "1"


@pytest.mark.parametrize("filename", ["compose.hosted.yaml", "compose.hosted-full.yaml"])
def test_shared_hosted_backend_preserves_privileges_mounts_and_research_off(filename):
    services = compose_model(filename)["services"]
    for name in ("roles", "migrate", "api", "worker", "seed"):
        service = services[name]
        assert service["image"] == services["api"]["image"]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] == 128
        assert not service.get("privileged")
        assert not service.get("ports")
        assert not service.get("network_mode")
        assert not service.get("devices")
        assert all(volume["type"] == "volume" for volume in service.get("volumes", []))
    for name in ("api", "worker", "seed"):
        environment = services[name]["environment"]
        assert environment["SEARCH_PROVIDER"] == "off"
        assert environment["SEARCH_API_KEY"] == ""
        assert environment["AI_MODE"] == "off"
        assert environment["AWS_EC2_METADATA_DISABLED"] == "true"


def test_full_stack_is_standalone_private_writable_and_uses_restricted_runtime_roles():
    model = compose_model("compose.hosted-full.yaml")
    public = compose_model("compose.hosted.yaml")
    services = model["services"]
    assert model["name"] == "proofops-hosted-full" != public["name"]
    assert not any(
        service.get("ports") or service.get("network_mode") for service in services.values()
    )
    assert set(model["volumes"]).isdisjoint(public["volumes"])
    assert all(
        network["internal"] and not network.get("external")
        for network in model["networks"].values()
    )
    assert set(services["db"]["networks"]) == set(services["worker"]["networks"]) == {"database"}
    assert set(services["web"]["networks"]) == {"application"}
    assert services["api"]["networks"]["application"]["aliases"] == ["full-api"]
    assert services["web"]["networks"]["application"]["aliases"] == ["full-web"]
    for name in ("api", "worker"):
        service = services[name]
        env = service["environment"]
        assert env["DATABASE_URL"].startswith(
            "postgresql+psycopg://proofops_runtime:${FULL_RUNTIME_PASSWORD:"
        )
        assert env["SECRET_KEY"].startswith("${FULL_SECRET_KEY:")
        assert env["PROOFOPS_MODE"] == "hosted" and env["PROOFOPS_PUBLIC_DEMO"] == "false"
        assert env["SESSION_COOKIE_SECURE"] == "true"
        assert env["AI_MODE"] == "off" and env["ALLOWED_PROVIDERS"] == ""
        assert env["OPENAI_API_KEY"] == env["ANTHROPIC_API_KEY"] == ""
        assert env["LOGIN_WINDOW_SECONDS"] == "900"
        assert env["LOGIN_MAX_FAILURES"] == "5" and env["LOGIN_MAX_IP_ATTEMPTS"] == "60"
        assert not any("PASSWORD" in key or "BASIC_AUTH" in key for key in env)
        assert service["read_only"] and service["cap_drop"] == ["ALL"]
        assert service["cpus"] and service["mem_limit"] and service["pids_limit"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert all(
            volume["type"] == "volume"
            and volume["source"] == "full-artifacts"
            and not volume.get("read_only")
            for volume in service["volumes"]
        )
        assert not service.get("profiles")
    assert services["worker"]["restart"] == "unless-stopped"
    assert services["migrate"]["environment"]["DATABASE_URL"].startswith(
        "postgresql+psycopg://proofops_owner:${FULL_OWNER_PASSWORD}"
    )
    assert services["roles"]["environment"]["DATABASE_URL"].startswith(
        "postgresql+psycopg://proofops_bootstrap:${FULL_POSTGRES_PASSWORD}"
    )
    assert "--no-proxy-headers" in services["api"]["command"]
    assert services["api"]["command"][services["api"]["command"].index("--workers") + 1] == "1"
    assert "/healthz" in " ".join(services["api"]["healthcheck"]["test"])
    assert (
        services["db"]["build"]["args"]["POSTGRES_BASE"]
        == public["services"]["db"]["build"]["args"]["POSTGRES_BASE"]
    )


def test_shared_gateway_preserves_public_controls_and_is_the_only_ingress():
    public = compose_model("compose.hosted.yaml")
    shared = compose_model("compose.hosted.yaml", "compose.hosted-gateway.yaml")
    assert shared["name"] == public["name"] and shared["volumes"] == public["volumes"]
    for name, service in public["services"].items():
        if name != "caddy":
            assert shared["services"][name] == service
    caddy = shared["services"]["caddy"]
    assert {name for name, service in shared["services"].items() if service.get("ports")} == {
        "caddy"
    }
    assert caddy["ports"] == public["services"]["caddy"]["ports"]
    assert set(caddy["networks"]) == {"edge", "application", "full_application"}
    assert shared["networks"]["full_application"]["external"]
    assert (
        shared["networks"]["full_application"]["name"]
        == "${FULL_PROXY_NETWORK:-proofops-hosted-full_application}"
    )
    assert set(caddy["environment"]) == {
        "HOSTED_DOMAIN",
        "ACME_EMAIL",
        "FULL_DOMAIN",
        "FULL_BASIC_AUTH_USER",
        "FULL_BASIC_AUTH_HASH",
    }
    mounts = {volume["target"]: volume for volume in caddy["volumes"]}
    assert mounts["/etc/caddy/Caddyfile"]["source"].endswith("deploy/Caddyfile.full")
    assert mounts["/etc/caddy/Caddyfile.public"]["source"].endswith("deploy/Caddyfile")
    assert (
        mounts["/etc/caddy/Caddyfile"]["read_only"]
        and mounts["/etc/caddy/Caddyfile.public"]["read_only"]
    )
    assert shared["services"]["api"]["networks"]["application"]["aliases"] == ["public-api"]
    assert shared["services"]["web"]["networks"]["application"]["aliases"] == ["public-web"]


def test_full_proxy_gates_every_path_before_proxying_and_strips_basic_credentials():
    public = (APP_ROOT / "deploy/Caddyfile").read_text()
    full = (APP_ROOT / "deploy/Caddyfile.full").read_text()
    assert "import /etc/caddy/Caddyfile.public" in full
    assert "https://{$FULL_DOMAIN}" in full and "http://{$FULL_DOMAIN}" in full
    assert "basic_auth {" in full and "{$FULL_BASIC_AUTH_USER} {$FULL_BASIC_AUTH_HASH}" in full
    assert full.index("route {") < full.index("basic_auth {") < full.index("handle @api {")
    assert "reverse_proxy full-api:8000" in full and "reverse_proxy full-web:8080" in full
    assert "reverse_proxy public-api:8000" in public and "reverse_proxy public-web:8080" in public
    assert full.count("header_up -Authorization") == full.count("reverse_proxy") == 2
    assert "FULL_BASIC_AUTH_PASSWORD" not in full
    assert 'Strict-Transport-Security "max-age=31536000"' in full
    assert "handle_errors" in full and "import security_headers" in full


def test_frontend_context_excludes_private_files_and_nginx_runs_unprivileged():
    patterns = (APP_ROOT / "frontend/.dockerignore").read_text().splitlines()
    for path in (
        ".env",
        ".env.production",
        "nested/.env.local",
        ".npmrc",
        "private.key",
        "server.pem",
    ):
        assert any(fnmatch(path, pattern) for pattern in patterns)
    dockerfile = (APP_ROOT / "frontend/Dockerfile").read_text()
    assert "USER nginx" in dockerfile and 'ENTRYPOINT ["nginx"]' in dockerfile
    nginx = (APP_ROOT / "frontend/nginx.conf").read_text()
    assert "listen 8080;" in nginx and "proxy_request_buffering off;" in nginx
    for header in (
        "X-Frame-Options DENY",
        "X-Content-Type-Options nosniff",
        "Content-Security-Policy",
    ):
        assert any(header in line and "always;" in line for line in nginx.splitlines())
    assert "pid /tmp/nginx.pid;" in (APP_ROOT / "frontend/nginx-main.conf").read_text()


def test_proxy_has_tls_hsts_timeouts_and_handles_docs_and_errors():
    config = (APP_ROOT / "deploy/Caddyfile").read_text()
    assert "https://{$HOSTED_DOMAIN}" in config and "http://{$HOSTED_DOMAIN}" in config
    assert 'Strict-Transport-Security "max-age=31536000"' in config
    assert "X-Frame-Options DENY" in config and "X-Content-Type-Options nosniff" in config
    assert "handle_errors" in config and "import security_headers" in config
    assert "read_header 5s" in config and "read_body 10s" in config
    assert "/docs /docs/* /redoc /openapi.json" in config


def test_runtime_images_upgrade_os_packages():
    backend = (APP_ROOT / "Dockerfile").read_text()
    frontend = (APP_ROOT / "frontend/Dockerfile").read_text().split("FROM nginx:", 1)[1]
    assert "apt-get update && apt-get upgrade -y" in backend
    assert "rm -rf /var/lib/apt/lists/*" in backend
    assert "apk upgrade --no-cache" in frontend
    assert "nginx>=1.28.3-r6" in frontend
    assert "apk del --no-cache nginx-module-acme" in frontend
    postgres = (APP_ROOT / "deploy/postgres/Dockerfile").read_text()
    assert "apk upgrade --no-cache" in postgres and "apk add --no-cache su-exec" in postgres
    assert "rm /usr/local/bin/gosu" in postgres and "exec su-exec postgres" in postgres
    hosted = compose_model("compose.hosted.yaml")["services"]["db"]
    assert hosted["build"]["args"]["POSTGRES_BASE"].startswith("postgres:18-alpine@sha256:")
