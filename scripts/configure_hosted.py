"""Create a private, separate hosted configuration; never print credentials."""

import argparse
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "PROOFOPS_OWNER_PASSWORD",
    "PROOFOPS_RUNTIME_PASSWORD",
    "SECRET_KEY",
)
FULL_SECRET_NAMES = (
    "FULL_POSTGRES_PASSWORD",
    "FULL_OWNER_PASSWORD",
    "FULL_RUNTIME_PASSWORD",
    "FULL_SECRET_KEY",
    "FULL_BASIC_AUTH_PASSWORD",
)
BCRYPT_PATTERN = r"\$2[aby]\$14\$[./A-Za-z0-9]{53}"


def validate_address(domain: str, email: str) -> None:
    if (
        len(domain) > 253
        or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain)
        or not re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", email)
    ):
        raise ValueError("Supply a DNS hostname and an ACME contact email, without URLs or ports.")


def read_private(target: Path) -> dict[str, str]:
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Hosted configuration must be a regular private file.")
    values = {}
    if target.exists():
        for line in target.read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key in values or not re.fullmatch(r"[A-Z_]+", key):
                raise ValueError("Existing hosted configuration is ambiguous; repair it privately.")
            # Compose single quotes keep the dollar signs in bcrypt hashes literal.
            if key == "FULL_BASIC_AUTH_HASH" and value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            values[key] = value
    return values


def fill_secrets(values: dict[str, str], names: tuple[str, ...]) -> None:
    for name in names:
        value = values.setdefault(name, secrets.token_urlsafe(48))
        if len(value) < 32 or len(set(value)) < 16 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Hosted credentials must be privately generated URL-safe values.")
    if len({values[name] for name in names}) != len(names):
        raise ValueError("Hosted services require separate credentials.")


def write_private(target: Path, values: dict[str, str]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + "-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write("# Private hosted deployment configuration. Never commit or print.\n")
            for key, value in values.items():
                rendered = f"'{value}'" if key == "FULL_BASIC_AUTH_HASH" else value
                output.write(f"{key}={rendered}\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def configure(domain: str, email: str) -> None:
    validate_address(domain, email)
    target = ROOT / ".env.hosted"
    values = read_private(target)
    fill_secrets(values, SECRET_NAMES)
    values.update(HOSTED_DOMAIN=domain, ACME_EMAIL=email)
    write_private(target, values)
    print("Private .env.hosted configured. Existing credentials preserved; no values printed.")


def bcrypt_hash(password: str) -> str:
    # Never pass plaintext in argv, an environment variable or a mounted file.
    # Caddy's binary has a NET_BIND_SERVICE file capability even for this command.
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "NET_BIND_SERVICE",
            "--security-opt",
            "no-new-privileges:true",
            "--entrypoint",
            "caddy",
            "proofops-caddy",
            "hash-password",
            "--algorithm",
            "bcrypt",
            "--bcrypt-cost",
            "14",
        ],
        input=password + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    hashed = result.stdout.strip()
    if result.returncode or not re.fullmatch(BCRYPT_PATTERN, hashed):
        raise ValueError(
            "Offline bcrypt hashing failed; first build deploy/caddy as proofops-caddy."
        )
    return hashed


def configure_full(public_domain: str, full_domain: str, email: str) -> None:
    validate_address(public_domain, email)
    validate_address(full_domain, email)
    if public_domain == full_domain:
        raise ValueError("Public and full deployments require different DNS hostnames.")
    public_target, full_target = ROOT / ".env.hosted", ROOT / ".env.hosted-full"
    public, full = read_private(public_target), read_private(full_target)
    # Refuse namespace collisions before combining these two env files in Compose.
    if any(key.startswith("FULL_") for key in public) or any(key in full for key in SECRET_NAMES):
        raise ValueError("Public and full credentials must use separate environment names.")
    if "FULL_BASIC_AUTH_HASH" in full and "FULL_BASIC_AUTH_PASSWORD" not in full:
        raise ValueError("Existing gateway credentials are incomplete; repair them privately.")
    fill_secrets(public, SECRET_NAMES)
    fill_secrets(full, FULL_SECRET_NAMES)
    all_secrets = [public[name] for name in SECRET_NAMES] + [
        full[name] for name in FULL_SECRET_NAMES
    ]
    if len(set(all_secrets)) != len(all_secrets):
        raise ValueError("Public, full and gateway credentials must be independent.")
    if len(full["FULL_BASIC_AUTH_PASSWORD"]) > 72:
        raise ValueError("Bcrypt passwords must fit within 72 bytes.")
    username = full.setdefault("FULL_BASIC_AUTH_USER", "full-" + secrets.token_hex(8))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", username):
        raise ValueError("The gateway username must be a single safe token.")
    if "FULL_BASIC_AUTH_HASH" not in full:
        full["FULL_BASIC_AUTH_HASH"] = bcrypt_hash(full["FULL_BASIC_AUTH_PASSWORD"])
    if not re.fullmatch(BCRYPT_PATTERN, full["FULL_BASIC_AUTH_HASH"]):
        raise ValueError("The gateway requires a private bcrypt hash with cost 14.")
    public.update(HOSTED_DOMAIN=public_domain, ACME_EMAIL=email)
    full.update(FULL_DOMAIN=full_domain)
    # Validate everything and finish hashing before changing either configuration.
    write_private(public_target, public)
    write_private(full_target, full)
    print("Private .env.hosted and .env.hosted-full configured; existing credentials preserved.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    domain = parser.add_mutually_exclusive_group(required=True)
    domain.add_argument("--domain", help="Configure only the read-only public demo")
    domain.add_argument("--public-domain", help="Configure both deployments behind one Caddy")
    parser.add_argument("--full-domain")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if bool(args.public_domain) != bool(args.full_domain):
        parser.error("--public-domain and --full-domain must be supplied together")
    try:
        if args.public_domain:
            configure_full(args.public_domain, args.full_domain, args.email)
        else:
            configure(args.domain, args.email)
    except (ValueError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Hosted setup failed; check hostnames, email, private files and the built proofops-caddy image."
        ) from None


if __name__ == "__main__":
    main()
