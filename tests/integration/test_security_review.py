import secrets
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.auth import AuthService
from proofops.domain.common import digest, utcnow
from proofops.storage.database import LoginThrottleRow
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def test_blocked_peer_does_not_allocate_more_account_state(db, auth_settings):
    auth_settings.login_max_ip_attempts = 10
    auth = AuthService(auth_settings, db)
    auth.initialize()
    for number in range(10):
        assert auth.login(f"unknown-{number}", secrets.token_urlsafe(32), "limited-peer") == (
            None,
            False,
        )
    with db() as session:
        before = session.scalar(select(func.count()).select_from(LoginThrottleRow))
    for number in range(4):
        assert auth.login(f"new-name-{number}", secrets.token_urlsafe(32), "limited-peer") == (
            None,
            True,
        )
    with db() as session:
        assert session.scalar(select(func.count()).select_from(LoginThrottleRow)) == before


def test_blocked_account_attempts_still_consume_peer_allowance(db, auth_settings):
    auth_settings.login_max_ip_attempts = 10
    auth = AuthService(auth_settings, db)
    auth.initialize()
    for _ in range(5):
        assert auth.login("unknown-account", secrets.token_urlsafe(32), "same-peer") == (
            None,
            False,
        )
    for _ in range(5):
        assert auth.login("unknown-account", secrets.token_urlsafe(32), "same-peer") == (
            None,
            True,
        )
    assert auth.login("different-account", secrets.token_urlsafe(32), "same-peer") == (None, True)


def test_login_cleanup_is_bounded_and_skips_locked_rows(db, auth_settings):
    auth = AuthService(auth_settings, db)
    auth.initialize()
    expired = utcnow() - timedelta(seconds=auth_settings.login_window_seconds * 3)
    keys = [digest({"expired_login": number}) for number in range(150)]
    with db.begin() as session:
        session.add_all(
            LoginThrottleRow(key_hash=key, window_start=expired, attempts=1) for key in keys
        )
    with db.begin() as locked:
        locked.scalar(
            select(LoginThrottleRow).where(LoginThrottleRow.key_hash == keys[0]).with_for_update()
        )
        assert auth.login("unknown-account", secrets.token_urlsafe(32), "new-peer") == (None, False)
        with db() as session:
            remaining = session.scalar(
                select(func.count())
                .select_from(LoginThrottleRow)
                .where(LoginThrottleRow.key_hash.in_(keys))
            )
            assert remaining == 50
            assert session.get(LoginThrottleRow, keys[0]) is not None


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/v1/bundles", "/api/v1/reviews", "/api/v1/future-write"])
def test_viewer_workspace_mutations_are_403(db, auth_settings, login_user, method, path):
    with TestClient(create_app(auth_settings, factory=db)) as api:
        login_user(api, "viewer")
        # A valid session CSRF token must not promote a viewer, even for future routes.
        assert api.request(method, path, json={}).status_code == 403
