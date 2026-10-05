import pytest
from proofops.policies.guards import load_trusted
from proofops.storage.bundles import load_replay


@pytest.fixture
def valid_bundle():
    return load_replay("valid-resize")


@pytest.fixture
def trusted():
    return load_trusted()


@pytest.fixture(scope="session")
def postgres_factory():
    import os
    from unittest.mock import patch

    from alembic import command
    from alembic.config import Config
    from proofops.config import APP_ROOT, get_settings
    from proofops.storage.database import session_factory
    from sqlalchemy.engine import make_url

    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://proofops:proofops_local@127.0.0.1:55432/proofops_test",
    )
    if make_url(url).database != "proofops_test":
        pytest.fail("Integration tests may only use the dedicated proofops_test database")
    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(APP_ROOT / "migrations"))
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        get_settings.cache_clear()
        command.upgrade(config, "head")
    get_settings.cache_clear()
    factory = session_factory(url)
    yield factory
    factory.kw["bind"].dispose()


@pytest.fixture
def db(postgres_factory):
    from proofops.storage.database import Base
    from sqlalchemy import text

    names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
    with postgres_factory.begin() as session:
        session.execute(text("TRUNCATE TABLE " + names + " RESTART IDENTITY CASCADE"))
    return postgres_factory
