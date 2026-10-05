"""Prepare isolated loopback HTTPS checks without changing deployment secrets.

Run from the repository root with `python3 -m scripts.prepare_hosted_checks`.
This only writes ignored test configuration; it does not start containers.
"""

import json
import os

from scripts import configure_hosted


def main() -> None:
    root = configure_hosted.ROOT
    private = root / "artifacts/hosted-security/private"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    try:
        configure_hosted.ROOT = private
        configure_hosted.configure("demo.localhost", "operator@example.com")
    finally:
        configure_hosted.ROOT = root
    images = {
        name: {"image": "proofops-" + image}
        for name, image in {
            "roles": "api",
            "migrate": "api",
            "api": "api",
            "worker": "worker",
            "seed": "api",
            "web": "web",
            "caddy": "caddy",
        }.items()
    }
    (private / "images.json").write_text(json.dumps({"services": images}) + "\n")
    (private / "ports.yaml").write_text(
        """services:
  caddy:
    ports: !override ["127.0.0.1:15080:80", "127.0.0.1:15443:443"]
    volumes:
      - ./artifacts/hosted-security/private/Caddyfile:/etc/caddy/Caddyfile:ro
"""
    )
    caddy = (
        (root / "deploy/Caddyfile")
        .read_text()
        .replace("{\n", "{\n\tlocal_certs\n\tskip_install_trust\n", 1)
    )
    (private / "Caddyfile").write_text(caddy)
    print("Isolated HTTPS test configuration prepared; no credentials printed.")


if __name__ == "__main__":
    main()
