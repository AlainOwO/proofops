"""Provision hosted database roles; only the one-shot bootstrap gets superuser access."""

import argparse
import os
import re

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from proofops.config import APP_ROOT, Settings, get_settings

OWNER_ROLE = "proofops_owner"
RUNTIME_ROLE = "proofops_runtime"


def _role(name: str) -> sql.Identifier:
    if not re.fullmatch(r"proofops_[a-z0-9_]{1,48}", name):
        raise ValueError("Database role name is outside the ProofOps namespace.")
    return sql.Identifier(name)


def bootstrap_roles(
    connection,
    owner_password: str,
    runtime_password: str,
    *,
    owner_role: str = OWNER_ROLE,
    runtime_role: str = RUNTIME_ROLE,
) -> None:
    database = connection.info.dbname
    if database not in {"proofops", "proofops_test"}:
        raise ValueError("Role setup requires a dedicated ProofOps database.")
    if owner_role == runtime_role or owner_password == runtime_password:
        raise ValueError("Owner and runtime database credentials must be separate.")
    for name, password in ((owner_role, owner_password), (runtime_role, runtime_password)):
        identifier = _role(name)
        # Reuse the hosted password policy, without constructing/printing a secret-bearing error.
        url = make_url(get_settings().database_url).set(username=name, password=password)
        Settings.model_construct(
            proofops_mode="hosted",
            database_url=url.render_as_string(hide_password=False),
        ).validate_database_security()
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(identifier))
        # Send only a salted SCRAM verifier in SQL, never a plaintext password.
        verifier = connection.pgconn.encrypt_password(
            password.encode(), name.encode(), b"scram-sha-256"
        )
        connection.execute(
            sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD {}"
            ).format(identifier, sql.Literal(verifier.decode("ascii")))
        )
        if connection.execute(
            "SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = %s)",
            (name,),
        ).fetchone():
            raise ValueError("Hosted database roles must not inherit other role memberships.")
    owner, runtime = _role(owner_role), _role(runtime_role)
    connection.execute(
        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(database), owner)
    )
    connection.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), runtime)
    )
    connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    connection.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(owner))
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(runtime))
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(owner, runtime)
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(owner, runtime)
    )


def grant_runtime(connection, *, runtime_role: str = RUNTIME_ROLE) -> None:
    runtime = _role(runtime_role)
    connection.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            runtime
        )
    )
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(runtime)
    )
    # Migrations belong to the owner; audit history is append-only to the app.
    for table in ("alembic_version", "audit_events"):
        connection.execute(
            sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(sql.Identifier(table), runtime)
        )
    connection.execute(sql.SQL("GRANT SELECT ON TABLE alembic_version TO {}").format(runtime))
    connection.execute(sql.SQL("GRANT SELECT, INSERT ON TABLE audit_events TO {}").format(runtime))


def assert_runtime_role(factory) -> None:
    with factory() as session:
        unsafe = session.execute(
            text(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
                "OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = pg_roles.oid) "
                "OR has_database_privilege(current_user, current_database(), 'CREATE') "
                "OR has_schema_privilege(current_user, 'public', 'CREATE') "
                "OR has_table_privilege(current_user, 'alembic_version', 'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') "
                "OR has_table_privilege(current_user, 'audit_events', 'UPDATE,DELETE,TRUNCATE,TRIGGER') "
                "OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relowner = pg_roles.oid AND n.nspname = 'public') "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).scalar_one()
    if unsafe:
        raise ValueError(
            "Hosted API and worker require a restricted runtime database role, "
            "without ownership, DDL, role administration or audit modification privileges."
        )


def _connect(settings: Settings):
    url = make_url(settings.database_url)
    return psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "migrate"))
    args = parser.parse_args()
    try:
        settings = get_settings()
        if args.action == "bootstrap":
            with _connect(settings) as connection:
                bootstrap_roles(
                    connection,
                    os.environ["PROOFOPS_OWNER_PASSWORD"],
                    os.environ["PROOFOPS_RUNTIME_PASSWORD"],
                )
        else:
            if make_url(settings.database_url).username != OWNER_ROLE:
                raise ValueError("Hosted migrations require the dedicated owner role.")
            config = Config(str(APP_ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(APP_ROOT / "migrations"))
            command.upgrade(config, "head")
            with _connect(settings) as connection:
                grant_runtime(connection)
    except Exception:
        # Connection/DDL errors may contain credentials or verifiers; never echo them.
        raise SystemExit(
            "Database role setup failed; check private configuration and database access."
        ) from None
    print("Hosted database role setup completed.")


if __name__ == "__main__":
    main()
