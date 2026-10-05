"""Offline checks of built images. Run after both Compose image builds; no pulls."""

import secrets
import shutil
import subprocess
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest


def docker(*arguments):
    executable = shutil.which("docker")
    assert executable is not None, "Docker is required for container checks"
    return subprocess.run(  # noqa: S603
        [executable, *arguments], capture_output=True, text=True, check=False, timeout=35
    )


@contextmanager
def container(image, *arguments):
    name = "proofops-image-check-" + uuid4().hex
    try:
        result = docker(
            "run",
            "--pull",
            "never",
            "--detach",
            "--rm",
            "--name",
            name,
            "--label",
            "proofops.security-check=true",
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "1",
            *arguments,
            image,
        )
        assert result.returncode == 0, "Build the required image before running container checks"
        yield name
    finally:
        docker("rm", "--force", "--volumes", name)


@pytest.mark.parametrize(
    "major,target", [(17, "/var/lib/postgresql/data"), (18, "/var/lib/postgresql")]
)
def test_postgres_initializes_root_owned_storage_and_drops_to_postgres(tmp_path, major, target):
    secret_file = tmp_path / "postgres.env"
    password = secrets.token_urlsafe(48)
    secret_file.write_text(f"POSTGRES_PASSWORD={password}\nPOSTGRES_DB=proofops\n")
    secret_file.chmod(0o600)
    # A new root-owned tmpfs exercises ownership initialization. There is no
    # network or published port, and no existing database/volume is mounted.
    with container(
        f"proofops-db{major}", "--env-file", str(secret_file), "--tmpfs", f"{target}:rw,size=256m"
    ) as name:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            ready = docker("exec", name, "cat", "/proc/1/comm")
            if ready.returncode == 0 and ready.stdout.strip() == "postgres":
                query = docker(
                    "exec", name, "psql", "-U", "postgres", "-d", "proofops", "-tAc", "SELECT 1"
                )
                if query.returncode == 0 and query.stdout.strip() == "1":
                    break
            time.sleep(0.2)
        else:
            pytest.fail("PostgreSQL initialization did not complete")
        uid = docker("exec", name, "id", "-u", "postgres").stdout.strip()
        status = docker("exec", name, "cat", "/proc/1/status").stdout
        process_uids = next(
            line for line in status.splitlines() if line.startswith("Uid:")
        ).split()[1:]
        assert uid != "0" and set(process_uids) == {uid}
        data = "/var/lib/postgresql/data" if major == 17 else "/var/lib/postgresql/18/docker"
        assert docker("exec", name, "stat", "-c", "%u", data).stdout.strip() == uid
        assert docker("exec", name, "test", "!", "-e", "/usr/local/bin/gosu").returncode == 0
        entrypoint = docker("exec", name, "cat", "/usr/local/bin/docker-entrypoint.sh").stdout
        assert "exec su-exec postgres" in entrypoint and "exec gosu postgres" not in entrypoint
        logs = docker("logs", name)
        assert bool(password in logs.stdout or password in logs.stderr) is False


def test_nginx_runs_without_root_or_capabilities_and_headers_cover_proxy_errors():
    with container(
        "proofops-web",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,size=32m,mode=1777",
        "--add-host",
        "api:127.0.0.1",
    ) as name:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            response = docker(
                "exec",
                name,
                "curl",
                "--silent",
                "--show-error",
                "--max-time",
                "2",
                "--dump-header",
                "-",
                "--output",
                "/dev/null",
                "http://127.0.0.1:8080/",
            )
            if response.returncode == 0 and "HTTP/1.1 200" in response.stdout:
                break
            time.sleep(0.2)
        else:
            pytest.fail("Unprivileged nginx did not start")
        uid = docker("exec", name, "id", "-u").stdout.strip()
        assert uid and uid != "0"
        status = docker("exec", name, "cat", "/proc/1/status").stdout
        assert set(
            next(line for line in status.splitlines() if line.startswith("Uid:")).split()[1:]
        ) == {uid}
        assert "CapEff:\t0000000000000000" in status
        assert "HTTP/1.1 200" in response.stdout
        failure = docker(
            "exec",
            name,
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "2",
            "--dump-header",
            "-",
            "--output",
            "/dev/null",
            "http://127.0.0.1:8080/api/v1/reviews",
        )
        assert "HTTP/1.1 502" in failure.stdout
        for headers in (response.stdout.lower(), failure.stdout.lower()):
            assert "x-frame-options: deny" in headers
            assert "x-content-type-options: nosniff" in headers
            assert "content-security-policy:" in headers and "frame-ancestors 'none'" in headers
