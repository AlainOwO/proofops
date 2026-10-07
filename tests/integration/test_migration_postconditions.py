from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.config import APP_ROOT, get_settings
from proofops.storage.database import SCHEMA_REVISION
from proofops.storage.migrate import MigrationError, upgrade_database
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration
PREVIOUS_REVISION = "f6a91d2e83b4"


@pytest.fixture
def previous_database(db):
    engine = db.kw["bind"]
    url = engine.url.render_as_string(hide_password=False)
    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(APP_ROOT / "migrations"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, PREVIOUS_REVISION)
        yield url
    finally:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")


def revision(db):
    with db() as session:
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_noop_upgrade_cannot_report_success_or_make_api_ready(
    db, previous_database, auth_settings, login_user
):
    with TestClient(create_app(auth_settings, factory=db)) as api:
        login_user(api)
        assert api.get("/readyz").status_code == 503
        with patch("proofops.storage.migrate.command.upgrade"):
            with pytest.raises(MigrationError, match="not at the packaged Alembic head"):
                upgrade_database(previous_database, previous_database)
        assert revision(db) == PREVIOUS_REVISION
        assert api.get("/readyz").status_code == 503
        upgrade_database(previous_database, previous_database)
        assert revision(db) == SCHEMA_REVISION
        assert api.get("/readyz").status_code == 200


def test_explicit_migration_connection_wins_over_settings(db, previous_database, monkeypatch):
    # The supplied API/owner URL is authoritative even with a stale native .env
    # or a different cached Settings value; never connect to this other target.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://wrong@127.0.0.1:1/wrong")
    get_settings.cache_clear()
    try:
        upgrade_database(previous_database, previous_database)
        assert revision(db) == SCHEMA_REVISION
        assert "tool_observation_cache" in inspect(db.kw["bind"]).get_table_names()
    finally:
        get_settings.cache_clear()


def test_grant_failure_rolls_back_schema_and_version(db, previous_database):
    with patch("proofops.storage.roles.grant_runtime", side_effect=RuntimeError("grant failed")):
        with pytest.raises(RuntimeError, match="grant failed"):
            upgrade_database(previous_database, previous_database, hosted=True)
    assert revision(db) == PREVIOUS_REVISION
    assert "tool_observation_cache" not in inspect(db.kw["bind"]).get_table_names()
