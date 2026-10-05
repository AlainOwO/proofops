"""Validate the effective Compose model without resolving any private environment."""

import json
import shutil
import subprocess
from fnmatch import fnmatch

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
