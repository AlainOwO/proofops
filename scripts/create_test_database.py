"""Create only the dedicated local proofops_test database, idempotently."""

import psycopg
from proofops.config import get_settings
from sqlalchemy.engine import make_url

url = make_url(get_settings().database_url)
if url.host not in {"127.0.0.1", "localhost", "db"} or url.database != "proofops":
    raise SystemExit(
        "Test-database setup requires the dedicated local ProofOps database configuration."
    )
with psycopg.connect(
    host=url.host,
    port=url.port or 5432,
    user=url.username,
    password=url.password,
    dbname="postgres",
    autocommit=True,
) as connection:
    exists = connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", ("proofops_test",)
    ).fetchone()
    if not exists:
        connection.execute("CREATE DATABASE proofops_test")
        print("Created local proofops_test database.")
    else:
        print("Local proofops_test database already exists.")
