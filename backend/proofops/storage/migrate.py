"""Upgrade with the owner connection, then verify the committed API database."""

import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url

from proofops.config import APP_ROOT, get_settings
from proofops.storage.database import SCHEMA_REVISION, make_engine


class MigrationError(RuntimeError):
    """A safe, credential-free explanation of a migration invariant failure."""


def _target(database_url: str) -> tuple:
    url = make_url(database_url)
    return (url.get_backend_name(), url.host, url.port or 5432, url.database, url.query)


def _identity(connection) -> tuple:
    return tuple(
        connection.execute(
            text(
                "SELECT current_database(), current_schema(), inet_server_addr(), inet_server_port()"
            )
        ).one()
    )


def upgrade_database(database_url: str, api_database_url: str, *, hosted: bool = False) -> None:
    # Different roles are intentional in hosted mode; different destinations or
    # connection overrides are not. Never include either secret-bearing URL in errors.
    if not api_database_url or _target(database_url) != _target(api_database_url):
        raise MigrationError("Migration and API database targets must match.")

    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(APP_ROOT / "migrations"))
    if ScriptDirectory.from_config(config).get_heads() != [SCHEMA_REVISION]:
        raise MigrationError("Packaged Alembic head does not match the API schema revision.")

    engine = make_engine(database_url)
    try:
        # Give Alembic the explicit connection, not a second Settings/environment
        # lookup. This transaction commits schema, version and grants together.
        with engine.begin() as connection:
            identity = _identity(connection)
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            if hosted:
                from proofops.storage.roles import grant_runtime

                grant_runtime(connection.connection.driver_connection)
    finally:
        engine.dispose()

    api_engine = make_engine(api_database_url)
    try:
        # A separate connection using the API's credentials proves that changes
        # committed and that its role/search_path can read the same schema.
        with api_engine.connect() as connection:
            if _identity(connection) != identity:
                raise MigrationError("Migration and API database/schema identities must match.")
            revisions = (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
            if revisions != [SCHEMA_REVISION]:
                raise MigrationError(
                    "API database is not at the packaged Alembic head after upgrade."
                )
    finally:
        api_engine.dispose()
    print(f"Database migrations completed; API database verified at {SCHEMA_REVISION}.")


def main() -> None:
    try:
        upgrade_database(get_settings().database_url, os.environ["API_DATABASE_URL"])
    except MigrationError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        # Driver and validation exceptions can contain connection credentials.
        raise SystemExit(
            "Database migration failed; check private configuration, API_DATABASE_URL and database access."
        ) from None


if __name__ == "__main__":
    main()
