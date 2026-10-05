"""Generate missing local secrets without printing them or replacing an existing database."""

import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def configure() -> None:
    target = ROOT / ".env"
    if target.is_symlink():
        raise SystemExit("Local configuration must be a regular file inside this repository.")
    content = target.read_text() if target.exists() else (ROOT / ".env.example").read_text()

    def get(name):
        match = re.search(rf"^{name}=(.*)$", content, flags=re.MULTILINE)
        return match.group(1).strip().strip("\"'") if match else ""

    def put(name, value):
        nonlocal content
        line = f"{name}={value}"
        pattern = rf"^{name}=.*$"
        content = (
            re.sub(pattern, lambda _: line, content, flags=re.MULTILINE)
            if re.search(pattern, content, flags=re.MULTILINE)
            else content.rstrip() + "\n" + line + "\n"
        )

    database_url = get("DATABASE_URL")
    password = get("POSTGRES_PASSWORD")
    if not password and database_url and "${" not in database_url:
        password = unquote(urlsplit(database_url).password or "")
    if not password:
        password = secrets.token_urlsafe(32)
    put("POSTGRES_PASSWORD", password)
    if not database_url or "${POSTGRES_PASSWORD}" in database_url:
        put(
            "DATABASE_URL",
            f"postgresql+psycopg://proofops:{quote(password, safe='')}@127.0.0.1:55432/proofops",
        )
    if not get("SECRET_KEY"):
        put("SECRET_KEY", secrets.token_urlsafe(48))
    if not get("SESSION_COOKIE_SECURE"):
        put("SESSION_COOKIE_SECURE", "false")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        if os.name == "posix":
            os.fchmod(output.fileno(), 0o600)
        output.write(content)
    print("Local .env configured; existing values preserved. Create users with the users CLI.")


if __name__ == "__main__":
    configure()
