"""Provision synthetic local browser-test identities; never print or commit credentials."""

import json
import os
import secrets

from proofops.auth import create_user, update_user
from proofops.config import APP_ROOT, get_settings
from proofops.storage.database import UserRow, session_factory
from sqlalchemy import select
from sqlalchemy.engine import make_url


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if (
        settings.proofops_mode != "local"
        or settings.proofops_public_demo
        or settings.ai_mode != "off"
        or url.host not in {"127.0.0.1", "localhost", "db"}
        or url.database != "proofops"
        or url.query
    ):
        raise SystemExit("Browser setup requires the local, AI-off proofops workspace.")
    target = APP_ROOT / "artifacts/private/browser-auth.json"
    if target.is_symlink() or target.parent.is_symlink():
        raise SystemExit("Browser credentials must stay inside application artifacts.")
    factory = session_factory(settings.database_url)
    # Repeated setup revokes only the synthetic identities from this script's previous run.
    if target.exists():
        previous = json.loads(target.read_text())
        for role in ("admin", "viewer"):
            username = previous[role]["username"]
            if not username.startswith(f"browser-{role}-"):
                raise SystemExit("Unrecognized browser identity; refusing to replace it.")
            with factory() as session:
                exists = session.scalar(select(UserRow.id).where(UserRow.username == username))
            if exists:
                update_user(factory, username, disable=True)
    credentials = {}
    for role in ("admin", "viewer"):
        username, password = f"browser-{role}-{secrets.token_hex(4)}", secrets.token_urlsafe(32)
        create_user(factory, username, password, role)
        credentials[role] = {"username": username, "password": password}
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        if os.name == "posix":
            os.fchmod(output.fileno(), 0o600)
        json.dump(credentials, output)
    print("Synthetic browser identities saved in ignored artifacts/private/browser-auth.json.")


if __name__ == "__main__":
    main()
