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
        make_url(get_settings().database_url)
        .set(database="proofops_test")
        .render_as_string(hide_password=False),
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


@pytest.fixture
def auth_settings(db):
    import secrets
    from uuid import uuid4

    from proofops.config import APP_ROOT, Settings

    return Settings(
        _env_file=None,
        database_url=db.kw["bind"].url.render_as_string(hide_password=False),
        artifact_dir=APP_ROOT / "artifacts/auth-tests" / uuid4().hex,
        secret_key=secrets.token_urlsafe(48),
        session_cookie_secure=False,
        allowed_hosts="testserver,127.0.0.1,localhost",
        cors_origins="http://testserver,http://127.0.0.1:5173",
        proofops_admin_username="",
        proofops_admin_password="",
        ai_mode="off",
    )


@pytest.fixture
def login_user(db):
    import secrets

    from proofops.auth import create_user

    def login(api, role="admin", *, username=None, password=None, create=True):
        username = username or f"{role}-{secrets.token_hex(4)}"
        password = password or secrets.token_urlsafe(32)
        if create:
            create_user(db, username, password, role)
        api.headers["Origin"] = str(api.base_url).rstrip("/")
        challenge = api.get("/api/v1/auth/login")
        assert challenge.status_code == 200
        response = api.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": challenge.json()["csrf_token"]},
        )
        assert response.status_code == 200
        api.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return username, password, response

    return login
