"""Migration failures must stop startup without exposing connection credentials."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from proofops.config import APP_ROOT
from proofops.storage import migrate
from proofops.storage.database import SCHEMA_REVISION

OWNER_URL = "postgresql+psycopg://proofops_owner:owner-secret@db:5432/proofops"
RUNTIME_URL = "postgresql+psycopg://proofops_runtime:runtime-secret@db:5432/proofops"


@pytest.mark.parametrize(
    "api_url",
    [
        "",
        RUNTIME_URL.replace("@db:", "@other-db:"),
        RUNTIME_URL.replace(":5432/", ":5433/"),
        RUNTIME_URL.replace("/proofops", "/other_database"),
        RUNTIME_URL + "?host=other-db",
        RUNTIME_URL + "?options=-csearch_path%3Dother_schema",
    ],
)
def test_migration_rejects_different_api_target_before_connecting(monkeypatch, api_url):
    connect = Mock(side_effect=AssertionError("A mismatched target must never be contacted"))
    upgrade = Mock()
    monkeypatch.setattr(migrate, "make_engine", connect)
    monkeypatch.setattr(migrate.command, "upgrade", upgrade)

    with pytest.raises(migrate.MigrationError, match="database targets must match") as failure:
        migrate.upgrade_database(OWNER_URL, api_url, hosted=True)

    assert "owner-secret" not in str(failure.value)
    assert "runtime-secret" not in str(failure.value)
    connect.assert_not_called()
    upgrade.assert_not_called()


def test_packaged_migration_head_matches_api_schema_revision():
    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(APP_ROOT / "migrations"))
    assert ScriptDirectory.from_config(config).get_heads() == [SCHEMA_REVISION]


def test_inconsistent_packaged_head_stops_before_database_changes(monkeypatch):
    monkeypatch.setattr(migrate, "SCHEMA_REVISION", "stale-api-revision")
    connect = Mock(side_effect=AssertionError("An inconsistent package must not connect"))
    upgrade = Mock()
    monkeypatch.setattr(migrate, "make_engine", connect)
    monkeypatch.setattr(migrate.command, "upgrade", upgrade)

    with pytest.raises(migrate.MigrationError, match="Packaged Alembic head"):
        migrate.upgrade_database(OWNER_URL, RUNTIME_URL, hosted=True)

    connect.assert_not_called()
    upgrade.assert_not_called()


def test_migration_cli_requires_explicit_api_verification_target(monkeypatch, capsys):
    monkeypatch.delenv("API_DATABASE_URL", raising=False)
    monkeypatch.setattr(migrate, "get_settings", lambda: SimpleNamespace(database_url=OWNER_URL))
    upgrade = Mock()
    monkeypatch.setattr(migrate, "upgrade_database", upgrade)

    with pytest.raises(SystemExit) as failure:
        migrate.main()

    assert failure.value.code and "API_DATABASE_URL" in str(failure.value.code)
    assert "owner-secret" not in str(failure.value.code)
    upgrade.assert_not_called()
    assert "completed" not in capsys.readouterr().out


def test_migration_cli_hides_driver_credentials_and_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setenv("API_DATABASE_URL", RUNTIME_URL)
    monkeypatch.setattr(migrate, "get_settings", lambda: SimpleNamespace(database_url=OWNER_URL))
    monkeypatch.setattr(migrate, "make_engine", Mock(side_effect=RuntimeError(OWNER_URL)))

    with pytest.raises(SystemExit) as failure:
        migrate.main()

    assert failure.value.code
    assert "owner-secret" not in str(failure.value.code)
    assert "runtime-secret" not in str(failure.value.code)
    assert "completed" not in capsys.readouterr().out


def test_failed_api_verification_makes_cli_exit_nonzero(monkeypatch, capsys):
    monkeypatch.setenv("API_DATABASE_URL", RUNTIME_URL)
    monkeypatch.setattr(migrate, "get_settings", lambda: SimpleNamespace(database_url=OWNER_URL))
    monkeypatch.setattr(
        migrate,
        "upgrade_database",
        Mock(
            side_effect=migrate.MigrationError("API database is not at the packaged Alembic head")
        ),
    )

    with pytest.raises(
        SystemExit, match="API database is not at the packaged Alembic head"
    ) as failure:
        migrate.main()

    assert failure.value.code
    assert "completed" not in capsys.readouterr().out
