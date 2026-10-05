import secrets

import pytest
from argon2.exceptions import VerifyMismatchError
from proofops.auth import (
    HASHER,
    AuthService,
    normalize_username,
    security_configuration,
    strong_password_hash,
    validate_password,
)
from proofops.config import Settings


def settings(**values):
    values.setdefault(
        "database_url",
        f"postgresql+psycopg://proofops:{secrets.token_urlsafe(32)}@127.0.0.1/proofops",
    )
    return Settings(_env_file=None, secret_key=secrets.token_urlsafe(48), **values)


def test_argon2id_hashes_are_salted_and_verify_only_the_password():
    password = secrets.token_urlsafe(32)
    one, two = HASHER.hash(password), HASHER.hash(password)
    assert one != two and password not in one
    assert strong_password_hash(one) and one.startswith("$argon2id$")
    assert HASHER.verify(one, password)
    with pytest.raises(VerifyMismatchError):
        HASHER.verify(one, secrets.token_urlsafe(32))
    assert not strong_password_hash("invalid")


@pytest.mark.parametrize(
    "password",
    [
        "",
        "change-me",
        "passwordpassword123",
        "abcdefghijklmn",
        "correct horse battery staple",
        "x" * 40,
    ],
)
def test_weak_passwords_are_rejected(password):
    with pytest.raises(ValueError, match="unique password"):
        validate_password(password, "admin")


def test_usernames_and_password_bounds():
    assert normalize_username("  Demo-Admin  ") == "demo-admin"
    for name in ("a", "bad name", "a" * 65, "../../admin"):
        with pytest.raises(ValueError):
            normalize_username(name)
    with pytest.raises(ValueError):
        validate_password(secrets.token_urlsafe(32) + "admin", "admin")
    with pytest.raises(ValueError):
        validate_password(secrets.token_urlsafe(128), "admin")


@pytest.mark.parametrize(
    "overrides",
    [
        {"secret_key": ""},
        {"secret_key": "a" * 48},
        {"cors_origins": "*"},
        {"allowed_hosts": "*"},
        {"cors_origins": "http://testserver/path"},
        {"cors_origins": "null"},
        {"cors_origins": "https://public.example"},
        {"allowed_hosts": "public.example"},
        {"proofops_mode": "hosted", "cors_origins": "http://public.example"},
        {
            "proofops_mode": "hosted",
            "cors_origins": "https://public.example",
            "session_cookie_secure": False,
        },
    ],
)
def test_unsafe_security_configuration_is_rejected(overrides):
    values = {**settings().model_dump(), **overrides}
    with pytest.raises(ValueError):
        security_configuration(Settings(_env_file=None, **values))


def test_hosted_configuration_requires_explicit_https_origins_and_hosts():
    origins, hosts = security_configuration(
        settings(
            proofops_mode="hosted",
            cors_origins="https://reviews.example",
            allowed_hosts="reviews.example,api",
        )
    )
    assert origins == {"https://reviews.example"} and hosts == ["reviews.example", "api"]


def test_login_csrf_is_bound_to_cookie_signature_and_expiry(monkeypatch):
    from datetime import timedelta

    from proofops.domain.common import utcnow

    auth = AuthService(settings(), None)
    cookie, token = auth.login_challenge()
    other_cookie, other_token = auth.login_challenge()
    assert auth.valid_login_csrf(cookie, token)
    assert not auth.valid_login_csrf(other_cookie, token)
    assert not auth.valid_login_csrf(cookie, other_token)
    assert not auth.valid_login_csrf(cookie + "x", token)
    assert not auth.valid_login_csrf(cookie, "é" * 64)
    later = utcnow() + timedelta(seconds=601)
    monkeypatch.setattr("proofops.auth.utcnow", lambda: later)
    assert not auth.valid_login_csrf(cookie, token)
