"""Prepare two isolated hosted projects and private synthetic test identities.

Run as a module from the repository root. --create-users provisions the test
projects after their migrations.
"""

import argparse
import json
import os
import secrets
import subprocess

from scripts import configure_hosted

ROOT = configure_hosted.ROOT
PRIVATE = ROOT / "artifacts/hosted-full/private"
PUBLIC_PROJECT = "proofops-hosted-check"
FULL_PROJECT = "proofops-hosted-full-check"


def compose(full: bool) -> list[str]:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(PRIVATE / ".env.hosted"),
        "--env-file",
        str(PRIVATE / ".env.hosted-full"),
        "-p",
        FULL_PROJECT if full else PUBLIC_PROJECT,
        "-f",
        str(ROOT / ("compose.hosted-full.yaml" if full else "compose.hosted.yaml")),
    ]
    if not full:
        command += ["-f", str(ROOT / "compose.hosted-gateway.yaml")]
    return command + [
        "-f",
        str(PRIVATE / ("images-full.json" if full else "images-public.json")),
        "-f",
        str(PRIVATE / ("full.yaml" if full else "gateway.yaml")),
    ]


def prepare() -> None:
    if any(path.is_symlink() for path in (PRIVATE, PRIVATE.parent, PRIVATE.parent.parent)):
        raise ValueError("Test configuration must stay in private application artifacts.")
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PRIVATE, 0o700)
    try:
        configure_hosted.ROOT = PRIVATE
        configure_hosted.configure_full("demo.localhost", "full.localhost", "operator@example.com")
    finally:
        configure_hosted.ROOT = ROOT
    identities = configure_hosted.read_private(PRIVATE / ".env.users")
    configure_hosted.fill_secrets(
        identities, ("PUBLIC_ADMIN_PASSWORD", "FULL_ADMIN_PASSWORD", "FULL_VIEWER_PASSWORD")
    )
    for name in ("PUBLIC_ADMIN", "FULL_ADMIN", "FULL_VIEWER"):
        identities.setdefault(
            name + "_USERNAME", name.lower().replace("_", "-") + "-" + secrets.token_hex(4)
        )
    configure_hosted.write_private(PRIVATE / ".env.users", identities)
    browser_auth = PRIVATE / "browser-auth.json"
    if browser_auth.is_symlink():
        raise ValueError("Browser credentials must be a regular private file.")
    descriptor = os.open(browser_auth, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(
            {
                role: {
                    "username": identities[f"FULL_{role.upper()}_USERNAME"],
                    "password": identities[f"FULL_{role.upper()}_PASSWORD"],
                }
                for role in ("admin", "viewer")
            },
            output,
        )
    images = {
        name: {"image": "proofops-" + image}
        for name, image in {
            "roles": "backend",
            "migrate": "backend",
            "api": "backend",
            "worker": "backend",
            "seed": "backend",
            "web": "web",
            "caddy": "caddy",
        }.items()
    }
    (PRIVATE / "images-public.json").write_text(json.dumps({"services": images}) + "\n")
    (PRIVATE / "images-full.json").write_text(
        json.dumps({"services": {name: value for name, value in images.items() if name != "caddy"}})
        + "\n"
    )
    public_caddy = (
        (ROOT / "deploy/Caddyfile")
        .read_text()
        .replace("{\n", "{\n\tlocal_certs\n\tskip_install_trust\n", 1)
    )
    (PRIVATE / "Caddyfile.public").write_text(public_caddy)
    (PRIVATE / "gateway.yaml").write_text(
        """services:
  caddy:
    ports: !override ["127.0.0.1:15080:80", "127.0.0.1:15443:443"]
    volumes:
      - ./artifacts/hosted-full/private/Caddyfile.public:/etc/caddy/Caddyfile.public:ro
networks:
  full_application:
    name: proofops-hosted-full-check_application
"""
    )
    (PRIVATE / "full.yaml").write_text(
        """services:
  api:
    environment:
      CORS_ORIGINS: https://full.localhost:15443
"""
    )
    print("Two isolated hosted test configurations prepared; credentials remain private.")


def create_users() -> None:
    identities = configure_hosted.read_private(PRIVATE / ".env.users")
    for full, name, role in (
        (False, "PUBLIC_ADMIN", "admin"),
        (True, "FULL_ADMIN", "admin"),
        (True, "FULL_VIEWER", "viewer"),
    ):
        result = subprocess.run(
            compose(full)
            + [
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "api",
                "proofops",
                "users",
                "create",
                "--username",
                identities[name + "_USERNAME"],
                "--role",
                role,
                "--password-stdin",
            ],
            input=identities[name + "_PASSWORD"] + "\n",
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode:
            raise ValueError(
                "Test account creation failed; check migrations and existing test users."
            )
    print("Synthetic admin/viewer accounts created through private stdin.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-users", action="store_true")
    args = parser.parse_args()
    try:
        create_users() if args.create_users else prepare()
    except (ValueError, OSError, subprocess.SubprocessError):
        raise SystemExit("Isolated hosted preparation failed; no private values printed.") from None


if __name__ == "__main__":
    main()
