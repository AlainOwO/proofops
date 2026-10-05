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


def configure(domain: str, email: str) -> None:
    if (
        len(domain) > 253
        or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain)
        or not re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", email)
    ):
        raise ValueError("Supply a DNS hostname and an ACME contact email, without URLs or ports.")
    target = ROOT / ".env.hosted"
    if target.is_symlink():
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
    for name in SECRET_NAMES:
        value = values.setdefault(name, secrets.token_urlsafe(48))
        if len(value) < 32 or len(set(value)) < 16 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Hosted credentials must be privately generated URL-safe values.")
    if len({values[name] for name in SECRET_NAMES}) != len(SECRET_NAMES):
        raise ValueError("Hosted services require separate credentials.")
    values.update(HOSTED_DOMAIN=domain, ACME_EMAIL=email)
    descriptor, temporary = tempfile.mkstemp(prefix=".env.hosted-", dir=ROOT)
    try:
        with os.fdopen(descriptor, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write("# Private hosted deployment configuration. Never commit or print.\n")
            output.write("".join(f"{key}={value}\n" for key, value in values.items()))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print("Private .env.hosted configured. Existing credentials preserved; no values printed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    try:
        configure(args.domain, args.email)
    except (ValueError, OSError):
        raise SystemExit(
            "Hosted setup failed; check the hostname, email and private configuration."
        ) from None


if __name__ == "__main__":
    main()
