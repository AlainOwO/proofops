"""Create a private, separate hosted configuration; never print credentials."""

import argparse
import os
import re
import secrets
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
)


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
                output.write(f"{key}={value}\n")
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
    fill_secrets(public, SECRET_NAMES)
    fill_secrets(full, FULL_SECRET_NAMES)
    all_secrets = [public[name] for name in SECRET_NAMES] + [
        full[name] for name in FULL_SECRET_NAMES
    ]
    if len(set(all_secrets)) != len(all_secrets):
        raise ValueError("Public and full credentials must be independent.")
    public.update(HOSTED_DOMAIN=public_domain, ACME_EMAIL=email)
    full.update(FULL_DOMAIN=full_domain)
    # Validate active credentials before changing either configuration; retain unused entries.
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
    except (ValueError, OSError):
        raise SystemExit("Hosted setup failed; check hostnames, email and private files.") from None


if __name__ == "__main__":
    main()
