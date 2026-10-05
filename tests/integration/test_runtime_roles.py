import secrets
from uuid import uuid4

import pytest
from proofops.auth import AuthService
from proofops.storage.database import AuditRow
from proofops.storage.roles import assert_runtime_role, bootstrap_roles, grant_runtime
from psycopg import sql
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration


def set_role(connection, role):
    connection.exec_driver_sql(
        sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)).as_string()
    )


@pytest.fixture
def restricted(db):
    # All role/database/schema privilege changes roll back with this transaction.
    # No persistent changes to the local operator's cluster or test database ACL.
    engine = db.kw["bind"]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT 1"))
            raw = connection.connection.driver_connection
            owner = "proofops_owner_" + uuid4().hex
            runtime = "proofops_runtime_" + uuid4().hex
            bootstrap_roles(
                raw,
                secrets.token_urlsafe(48),
                secrets.token_urlsafe(48),
                owner_role=owner,
                runtime_role=runtime,
            )
            grant_runtime(raw, runtime_role=runtime)
            set_role(connection, owner)
            # Created AFTER provisioning to verify the owner's default privileges.
            connection.exec_driver_sql(
                "CREATE TABLE public.runtime_probe (id integer PRIMARY KEY, value text)"
            )
            # SET ROLE alone retains the superuser session identity's ability to
            # assume other roles. Drop that identity for the actual privilege checks.
            connection.exec_driver_sql(
                sql.SQL("SET LOCAL SESSION AUTHORIZATION {}")
                .format(sql.Identifier(runtime))
                .as_string()
            )
            yield connection, owner, runtime
        finally:
            transaction.rollback()


def test_runtime_crud_works_without_owner_or_cluster_privileges(restricted):
    connection, _, _ = restricted
    connection.exec_driver_sql("INSERT INTO runtime_probe VALUES (1, 'synthetic')")
    assert (
        connection.exec_driver_sql("SELECT value FROM runtime_probe WHERE id = 1").scalar_one()
        == "synthetic"
    )
    connection.exec_driver_sql("UPDATE runtime_probe SET value = 'changed' WHERE id = 1")
    assert (
        connection.exec_driver_sql("SELECT value FROM runtime_probe WHERE id = 1").scalar_one()
        == "changed"
    )
    connection.exec_driver_sql("DELETE FROM runtime_probe WHERE id = 1")
    assert connection.exec_driver_sql("SELECT count(*) FROM runtime_probe").scalar_one() == 0
    assert_runtime_role(sessionmaker(bind=connection))
    flags = connection.exec_driver_sql(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).one()
    assert not any(flags)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.forbidden (id integer)",
        "CREATE TEMP TABLE forbidden (id integer)",
        "CREATE SCHEMA forbidden",
        "CREATE ROLE proofops_forbidden",
        "ALTER TABLE runtime_probe ADD COLUMN forbidden integer",
        "DROP TABLE runtime_probe",
        "TRUNCATE runtime_probe",
        "UPDATE alembic_version SET version_num = 'forbidden'",
        "DELETE FROM audit_events",
        "UPDATE audit_events SET actor = 'forbidden'",
    ],
)
def test_runtime_cannot_perform_ddl_or_modify_migrations_or_audit(restricted, statement):
    connection, _, _ = restricted
    with pytest.raises(DBAPIError) as error, connection.begin_nested():
        connection.exec_driver_sql(statement)
    assert error.value.orig.sqlstate == "42501"


def test_runtime_cannot_assume_owner_but_can_append_audit(restricted):
    connection, owner, _ = restricted
    with pytest.raises(DBAPIError) as error, connection.begin_nested():
        set_role(connection, owner)
    assert error.value.orig.sqlstate == "42501"
    connection.execute(
        insert(AuditRow).values(
            scope="synthetic", kind="test", actor="test-id", data={"status": "recorded"}
        )
    )
    assert connection.exec_driver_sql("SELECT count(*) FROM audit_events").scalar_one() == 1
    assert (
        connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        == "f6a91d2e83b4"
    )


def test_hosted_auth_rejects_an_owner_or_superuser_runtime(db, auth_settings):
    auth_settings.proofops_mode = "hosted"
    auth_settings.session_cookie_secure = True
    auth_settings.cors_origins = "https://testserver"
    with pytest.raises(ValueError, match="restricted runtime database role"):
        AuthService(auth_settings, db).initialize()


def test_hosted_public_demo_worker_cannot_claim_jobs(db, auth_settings, monkeypatch):
    from proofops.workers.runner import run_once

    auth_settings.proofops_public_demo = True

    def forbidden(*args, **kwargs):
        raise AssertionError("public-demo workers must not claim or process work")

    monkeypatch.setattr("proofops.workers.runner.claim_job", forbidden)
    assert run_once(factory=db, settings=auth_settings) is None
