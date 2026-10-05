"""Rotate the dedicated local database credential without displaying either value.

The owner-only pending configuration is durable before ALTER ROLE. If interrupted,
rerun with --resume; recovery tries the prepared credential before the original.
Only this repository's literal, loopback .env configuration is used.
"""

import argparse
import io
import os
import re
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]


class RotationError(Exception):
    """Safe operator-facing error with no connection or credential details."""


@dataclass
class LocalConfiguration:
    content: str = field(repr=False)
    url: URL = field(repr=False)


def _pattern(name: str) -> str:
    return rf"^[ \t]*(?:export[ \t]+)?{name}[ \t]*=.*$"


def _read_private(target: Path) -> str:
    try:
        descriptor = os.open(
            target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(descriptor, "r") as source:
            metadata = os.fstat(source.fileno())
            if (
                target.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size > 65_536
                or (
                    os.name == "posix"
                    and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077)
                )
            ):
                raise RotationError("Configuration must be a private, owner-only regular file.")
            return source.read()
    except RotationError:
        raise
    except Exception:
        raise RotationError("Cannot read a private regular configuration file.") from None


def _load(target: Path) -> LocalConfiguration:
    content = _read_private(target)
    values = dotenv_values(stream=io.StringIO(content), interpolate=False)
    try:
        url = make_url(values.get("DATABASE_URL") or "")
        valid = (
            values.get("PROOFOPS_MODE", "local") == "local"
            and url.drivername in {"postgresql", "postgresql+psycopg"}
            and url.host in {"127.0.0.1", "localhost", "::1"}
            and url.username == "proofops"
            and url.database == "proofops"
            and not url.query
            and bool(url.password)
            and url.password == values.get("POSTGRES_PASSWORD")
            and "${" not in (values.get("DATABASE_URL") or "")
            and all(
                len(re.findall(_pattern(name), content, flags=re.MULTILINE)) == 1
                for name in ("DATABASE_URL", "POSTGRES_PASSWORD")
            )
            and len(re.findall(_pattern("PROOFOPS_MODE"), content, flags=re.MULTILINE)) <= 1
        )
    except (ArgumentError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RotationError(
            "Rotation requires local mode, the loopback proofops database/role, and matching "
            "literal DATABASE_URL/POSTGRES_PASSWORD values without query overrides."
        ) from None
    return LocalConfiguration(content, url)


def _render(current: LocalConfiguration, password: str) -> str:
    content = current.content
    values = {
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": current.url.set(password=password).render_as_string(hide_password=False),
    }
    for name, value in values.items():
        content = re.sub(
            _pattern(name), lambda _, line=f"{name}={value}": line, content, flags=re.MULTILINE
        )
    return content


def _sync_directory(directory: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _prepare(pending: Path, content: str) -> None:
    try:
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RotationError("A pending rotation exists; rerun with --resume.") from None
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        _sync_directory(pending.parent)
    except Exception:
        pending.unlink(missing_ok=True)
        raise RotationError(
            "Could not prepare private recovery configuration; no change made."
        ) from None


def _connect(url: URL):
    return psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    )


def _verify(url: URL) -> None:
    with _connect(url) as connection:
        if connection.execute("SELECT 1").fetchone() != (1,):
            raise RotationError("Database verification failed.")


def rotate(target: Path | None = None, *, resume: bool = False) -> None:
    target = target or ROOT / ".env"
    current = _load(target)
    pending = target.with_name(target.name + ".database-rotation.pending")
    already_changed = False
    if resume:
        prepared = _load(pending)
        if (
            not prepared.url.password
            or len(prepared.url.password) < 32
            or len(set(prepared.url.password)) < 16
            or prepared.url.password == current.url.password
            or _render(current, prepared.url.password) != prepared.content
        ):
            raise RotationError("Pending configuration does not match; reconcile it privately.")
        try:
            _verify(prepared.url)
            already_changed = True
        except Exception:
            # Either original or prepared credentials may be current after an interruption.
            already_changed = False
    else:
        password = secrets.token_urlsafe(32)
        prepared = LocalConfiguration(
            _render(current, password), current.url.set(password=password)
        )
        _prepare(pending, prepared.content)

    if not already_changed:
        try:
            with _connect(current.url) as connection:
                verifier = connection.pgconn.encrypt_password(
                    prepared.url.password.encode(), current.url.username.encode(), b"scram-sha-256"
                )
                connection.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier(current.url.username), sql.Literal(verifier.decode("ascii"))
                    )
                )
        except Exception:
            raise RotationError(
                "Database rotation did not finish. Private recovery configuration retained; "
                "resolve local database access and rerun with --resume."
            ) from None
    try:
        _verify(prepared.url)
        if _read_private(target) != current.content:
            raise RotationError("Configuration changed during rotation.")
        os.replace(pending, target)
        _sync_directory(target.parent)
    except Exception:
        raise RotationError(
            "Database rotation requires configuration recovery. Keep both private files; "
            "rerun with --resume after resolving file access or concurrent configuration edits."
        ) from None
    print("Local database credential rotated and private configuration synchronized.")
    print(
        "Recreate the database, API, worker and migration containers to reload their environment."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Recover a prepared local rotation")
    args = parser.parse_args()
    try:
        rotate(resume=args.resume)
    except RotationError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit(
            "Rotation failed; inspect private configuration locally without printing it."
        ) from None


if __name__ == "__main__":
    main()
