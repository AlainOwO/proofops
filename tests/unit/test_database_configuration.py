import secrets

import pytest
from proofops.auth import security_configuration
from proofops.config import Settings
from sqlalchemy.engine import URL


def database_url(password):
    return URL.create(
        "postgresql+psycopg",
        username="proofops",
        password=password,
        host="127.0.0.1",
        database="proofops",
    ).render_as_string(hide_password=False)


def hosted_values():
    return {
        "proofops_mode": "hosted",
        "secret_key": secrets.token_urlsafe(48),
        "cors_origins": "https://reviews.example",
        "allowed_hosts": "reviews.example",
    }


@pytest.mark.parametrize("kind", ["missing", "short", "repeated", "placeholder", "query"])
def test_hosted_settings_reject_unsafe_database_credentials(kind):
    password = {
        "missing": None,
        "short": secrets.token_urlsafe(8),
        "repeated": "x" * 48,
        "placeholder": "replace-with-a-generated-database-credential",
        "query": secrets.token_urlsafe(32),
    }[kind]
    url = database_url(password)
    if kind == "query":
        url += "?password=" + secrets.token_urlsafe(8)
    with pytest.raises(ValueError, match="Hosted database configuration") as error:
        Settings(_env_file=None, database_url=url, **hosted_values())
    # Keep credential values out of assertion failure diagnostics, too.
    assert bool(url in str(error.value)) is False
    if password:
        assert bool(password in str(error.value)) is False


def test_hosted_settings_accept_generated_database_credentials_and_hide_url_in_repr():
    url = database_url(secrets.token_urlsafe(32))
    settings = Settings(_env_file=None, database_url=url, **hosted_values())
    security_configuration(settings)
    assert bool(url in repr(settings)) is False


def test_auth_startup_rechecks_database_configuration_after_mode_change():
    settings = Settings(_env_file=None, database_url=database_url(None))
    for name, value in hosted_values().items():
        setattr(settings, name, value)
    with pytest.raises(ValueError, match="Hosted database configuration"):
        security_configuration(settings)


def test_malformed_hosted_database_url_is_rejected_without_echoing_input():
    canary = secrets.token_urlsafe(32)
    with pytest.raises(ValueError, match="Hosted database configuration") as error:
        Settings(_env_file=None, database_url=canary, **hosted_values())
    assert bool(canary in str(error.value)) is False


def test_local_operator_can_open_settings_to_repair_an_existing_database():
    settings = Settings(_env_file=None, database_url=database_url(None))
    assert settings.proofops_mode == "local"
