import io
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.auth import HASHER, create_user, update_user
from proofops.cli import main
from proofops.domain.common import utcnow
from proofops.storage.database import AuthSessionRow, LoginThrottleRow, UserRow
from proofops.storage.demo import reset_demo_data
from sqlalchemy import select, update

pytestmark = pytest.mark.integration

# Every registered route/method is accounted for, including framework documentation.
ENDPOINTS = [
    ("GET", "/healthz", 200, "public"),
    ("GET", "/api/v1/auth/login", 200, "public"),
    ("POST", "/api/v1/auth/login", 401, "login"),
    ("GET", "/api/v1/auth/session", 200, "read"),
    ("POST", "/api/v1/auth/logout", 200, "member"),
    ("GET", "/readyz", 200, "read"),
    ("GET", "/api/v1/replays", 200, "read"),
    ("POST", "/api/v1/bundles", 201, "write"),
    ("POST", "/api/v1/reviews", 202, "write"),
    ("GET", "/api/v1/reviews", 200, "read"),
    ("GET", "/api/v1/reviews/{review_id}", 200, "read"),
    ("GET", "/api/v1/reviews/{review_id}/bundle", 200, "read"),
    ("POST", "/api/v1/reviews/{review_id}/guard-drafts", 201, "write"),
    ("POST", "/api/v1/guard-drafts/{draft_id}/validate", 200, "write"),
    ("GET", "/api/v1/guard-drafts/{draft_id}/bundle", 200, "read"),
    ("POST", "/api/v1/reviews/{review_id}/outcomes", 201, "write"),
    ("GET", "/api/v1/analytics", 200, "read"),
    ("POST", "/api/v1/billing/import-sample", 201, "write"),
    ("POST", "/api/v1/admin/reset-demo-data", 200, "write"),
    ("GET", "/openapi.json", 200, "read"),
    ("HEAD", "/openapi.json", 200, "read"),
    ("GET", "/docs", 200, "read"),
    ("HEAD", "/docs", 200, "read"),
    ("GET", "/docs/oauth2-redirect", 200, "read"),
    ("HEAD", "/docs/oauth2-redirect", 200, "read"),
    ("GET", "/redoc", 200, "read"),
    ("HEAD", "/redoc", 200, "read"),
]
WRITES = [
    (method, path) for method, path, _, kind in ENDPOINTS if kind in {"write", "member", "login"}
]


@pytest.fixture
def prepared(db, auth_settings, login_user):
    app = create_app(auth_settings, factory=db)
    seeded = reset_demo_data(settings=auth_settings, factory=db)
    review_id = seeded["reviews"][1]["review_id"]
    with TestClient(app) as admin:
        login_user(admin)
        report = admin.get(f"/api/v1/reviews/{review_id}").json()
        draft = admin.post(
            f"/api/v1/reviews/{review_id}/guard-drafts", json={"ai_preference": "off"}
        )
        assert draft.status_code == 201
        draft_id = draft.json()["draft_id"]
        assert admin.post(f"/api/v1/guard-drafts/{draft_id}/validate").status_code == 200
        yield app, review_id, draft_id, report


def call(api, method, path, prepared, **kwargs):
    _, review_id, draft_id, report = prepared
    bodies = {
        "/api/v1/auth/login": {
            "username": "unknown-account",
            "password": secrets.token_urlsafe(32),
        },
        "/api/v1/bundles": {"replay": "valid-resize"},
        "/api/v1/reviews": {"bundle_id": report["job"]["bundle_id"]},
        "/api/v1/reviews/{review_id}/guard-drafts": {"ai_preference": "off"},
        "/api/v1/reviews/{review_id}/outcomes": {
            "candidate_commit": report["report"]["change"]["service_map"]["candidate_commit"],
            "disposition": "rejected",
            "origin": "synthetic_fixture",
            "reason": "Synthetic auth test.",
            "observed_start": utcnow().isoformat(),
            "observed_end": utcnow().isoformat(),
            "cost_basis": "not_measured",
            "evidence_ids": [],
        },
        "/api/v1/admin/reset-demo-data": {"confirm": True},
    }
    headers = {"Idempotency-Key": "auth-matrix", **kwargs.pop("headers", {})}
    return api.request(
        method,
        path.format(review_id=review_id, draft_id=draft_id),
        json=bodies.get(path) if method == "POST" else None,
        headers=headers,
        **kwargs,
    )


@pytest.mark.parametrize("method,path,status,kind", ENDPOINTS)
@pytest.mark.parametrize("role", [None, "viewer", "admin"], ids=["anonymous", "viewer", "admin"])
def test_every_endpoint_enforces_identity_and_role(
    prepared, login_user, role, method, path, status, kind
):
    app, *_ = prepared
    with TestClient(app) as api:
        if role:
            login_user(api, role)
        if kind == "login":
            api.headers["X-CSRF-Token"] = api.get("/api/v1/auth/login").json()["csrf_token"]
        expected = status
        if kind not in {"public", "login"}:
            if role is None:
                expected = 401
            elif kind == "write" and role == "viewer":
                expected = 403
        response = call(api, method, path, prepared)
        assert response.status_code == expected, response.text
        assert response.headers["cache-control"] == "no-store"
        if path == "/api/v1/admin/reset-demo-data" and expected == 200:
            assert api.get("/api/v1/auth/session").status_code == 200


def test_endpoint_matrix_cannot_silently_omit_a_new_route(auth_settings, db):
    actual = {
        (method, route.path)
        for route in create_app(auth_settings, factory=db).routes
        for method in route.methods
    }
    assert actual == {(method, path) for method, path, _, _ in ENDPOINTS}


@pytest.mark.parametrize("method,path", WRITES)
@pytest.mark.parametrize("bad_csrf", [None, "incorrect", "0" * 64])
def test_all_writes_require_csrf_even_for_admin(prepared, login_user, method, path, bad_csrf):
    app, *_ = prepared
    with TestClient(app) as api:
        login_user(api)
        api.get("/api/v1/auth/login")
        api.headers.pop("X-CSRF-Token", None)
        headers = {} if bad_csrf is None else {"X-CSRF-Token": bad_csrf}
        assert call(api, method, path, prepared, headers=headers).status_code == 403


def test_csrf_cannot_be_copied_between_sessions(db, auth_settings, login_user):
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as one, TestClient(app) as two:
        login_user(one)
        login_user(two)
        assert (
            two.post(
                "/api/v1/bundles",
                json={"replay": "valid-resize"},
                headers={"X-CSRF-Token": one.headers["X-CSRF-Token"]},
            ).status_code
            == 403
        )


def test_new_routes_inherit_authentication_and_write_restrictions(db, auth_settings, login_user):
    app = create_app(auth_settings, factory=db)
    calls = []

    @app.post("/api/v1/future-write")
    def unannotated_write():
        calls.append(True)
        return {"ok": True}

    @app.get("/api/v1/future-read")
    def unannotated_read():
        return {"private": True}

    with TestClient(app) as api:
        assert api.get("/api/v1/future-read").status_code == 401
        assert api.post("/api/v1/future-write").status_code == 401
        login_user(api, "viewer")
        assert api.post("/api/v1/future-write").status_code == 403
        assert not calls
        login_user(api)
        assert api.post("/api/v1/future-write").status_code == 200
        assert calls == [True]


def test_session_cookies_expiry_logout_and_live_role_checks(db, auth_settings, login_user):
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as api:
        username, _, response = login_user(api)
        cookie = response.headers.get_list("set-cookie")[0]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=28800" in cookie
        assert "Domain=" not in cookie and "Secure" not in cookie
        token = api.cookies.get(app.state.auth.cookie_name)
        with db.begin() as session:
            saved = session.scalar(select(AuthSessionRow))
            assert saved.token_hash != token and len(saved.token_hash) == 64
            user = session.scalar(select(UserRow).where(UserRow.username == username))
            user.role = "viewer"
        assert api.get("/api/v1/auth/session").json()["role"] == "viewer"
        assert api.post("/api/v1/bundles", json={"replay": "valid-resize"}).status_code == 403
        assert api.post("/api/v1/auth/logout").status_code == 200
        api.cookies.set(app.state.auth.cookie_name, token)
        assert api.get("/api/v1/reviews").status_code == 401
        api.cookies.clear()
        login_user(api)
        with db.begin() as session:
            session.execute(
                update(AuthSessionRow).values(expires_at=utcnow() - timedelta(seconds=1))
            )
        assert api.get("/api/v1/reviews").status_code == 401


def test_secure_host_cookie_and_session_rotation(db, auth_settings, login_user):
    auth_settings.session_cookie_secure = True
    auth_settings.cors_origins = "https://testserver"
    app = create_app(auth_settings, factory=db)
    with TestClient(app, base_url="https://testserver") as api:
        username, password, response = login_user(api)
        cookie = response.headers.get_list("set-cookie")[0]
        assert (
            cookie.startswith("__Host-proofops_session=")
            and "Secure" in cookie
            and "Path=/" in cookie
        )
        before = api.cookies.get(app.state.auth.cookie_name)
        login_user(api, username=username, password=password, create=False)
        assert before != api.cookies.get(app.state.auth.cookie_name)
        assert app.state.auth.authenticate(before) is None
        api.cookies.clear()
        api.cookies.set(app.state.auth.cookie_name, secrets.token_urlsafe(32))
        assert api.get("/api/v1/reviews").status_code == 401


def test_password_rotation_and_disabling_revoke_sessions(db, auth_settings, login_user):
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as api:
        username, _, _ = login_user(api)
        replacement = secrets.token_urlsafe(32)
        update_user(db, username, password=replacement)
        assert api.get("/api/v1/reviews").status_code == 401
        login_user(api, username=username, password=replacement, create=False)
        update_user(db, username, disable=True)
        assert api.get("/api/v1/reviews").status_code == 401


def test_origins_cors_and_health_are_explicit(db, auth_settings):
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as api:
        assert api.get("/healthz").status_code == 200
        assert api.post("/healthz").status_code == 401
        assert api.get("/readyz").status_code == 401
        assert (
            api.get("/api/v1/reviews", headers={"Origin": "https://evil.invalid"}).status_code
            == 403
        )
        assert api.get("/healthz", headers={"Host": "evil.invalid"}).status_code == 400
        cors = api.options(
            "/api/v1/bundles",
            headers={
                "Origin": "http://testserver",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token",
            },
        )
        assert cors.status_code == 200
        assert cors.headers["access-control-allow-origin"] == "http://testserver"
        assert cors.headers["access-control-allow-credentials"] == "true"
        assert api.post("/api/v1/bundles").status_code == 401


@pytest.mark.parametrize("existing", [True, False], ids=["known", "unknown"])
def test_login_lockout_is_generic_persistent_and_expires(db, auth_settings, existing, monkeypatch):
    username, password = "synthetic-user", secrets.token_urlsafe(32)
    if existing:
        create_user(db, username, password, "viewer")
    app = create_app(auth_settings, factory=db)
    with TestClient(app) as api:
        challenge = api.get("/api/v1/auth/login").json()["csrf_token"]
        for _ in range(auth_settings.login_max_failures):
            failed = api.post(
                "/api/v1/auth/login",
                json={"username": username, "password": secrets.token_urlsafe(32)},
                headers={"X-CSRF-Token": challenge},
            )
            assert failed.status_code == 401 and failed.json() == {
                "detail": "Invalid username or password."
            }
    # A new app process shares the same counters; forged forwarding headers do not evade them.
    with TestClient(create_app(auth_settings, factory=db)) as api:
        challenge = api.get("/api/v1/auth/login").json()["csrf_token"]
        blocked = api.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": challenge, "X-Forwarded-For": "198.51.100.12"},
        )
        assert blocked.status_code == 429 and blocked.json() == {
            "detail": "Unable to sign in. Try again later."
        }
        later = utcnow() + timedelta(seconds=auth_settings.login_window_seconds + 1)
        monkeypatch.setattr("proofops.auth.utcnow", lambda: later)
        challenge = api.get("/api/v1/auth/login").json()["csrf_token"]
        response = api.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": challenge},
        )
        assert response.status_code == (200 if existing else 401)


def test_ip_limits_cover_password_spraying_and_concurrent_attempts(db, auth_settings):
    auth_settings.login_max_ip_attempts = 10
    app = create_app(auth_settings, factory=db)
    with TestClient(app):
        auth = app.state.auth
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(
                    lambda i: auth.login(f"unknown-{i}", secrets.token_urlsafe(32), "same-peer"),
                    range(14),
                )
            )
        assert sum(limited for _, limited in results) == 4
        assert not any(token for token, _ in results)
        with db() as session:
            rows = session.scalars(select(LoginThrottleRow)).all()
            assert all(
                "unknown" not in row.key_hash and "same-peer" not in row.key_hash for row in rows
            )


@pytest.mark.parametrize(
    "failure", ["missing_secret", "weak_secret", "missing_admin", "weak_admin", "half_admin"]
)
def test_hosted_startup_refuses_incomplete_or_weak_auth(db, auth_settings, failure):
    from pydantic import SecretStr

    auth_settings.proofops_mode = "hosted"
    auth_settings.session_cookie_secure = True
    auth_settings.allowed_hosts = "reviews.example"
    auth_settings.cors_origins = "https://reviews.example"
    if failure in {"missing_secret", "weak_secret"}:
        auth_settings.secret_key = SecretStr("" if failure == "missing_secret" else "x" * 48)
    elif failure in {"weak_admin", "half_admin"}:
        auth_settings.proofops_admin_username = "setup-admin"
        auth_settings.proofops_admin_password = SecretStr(
            "short" if failure == "weak_admin" else ""
        )
    with pytest.raises(ValueError), TestClient(create_app(auth_settings, factory=db)):
        pass


def test_environment_bootstrap_and_cli_users_never_print_passwords(
    db, auth_settings, monkeypatch, capsys
):
    from proofops.storage import database
    from pydantic import SecretStr

    password = secrets.token_urlsafe(32)
    auth_settings.proofops_admin_username = "setup-admin"
    auth_settings.proofops_admin_password = SecretStr(password)
    app = create_app(auth_settings, factory=db)
    with TestClient(app):
        with db() as session:
            user = session.scalar(select(UserRow).where(UserRow.username == "setup-admin"))
            assert user.role == "admin" and HASHER.verify(user.password_hash, password)
    monkeypatch.setattr(database, "session_factory", lambda: db)
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    assert (
        main(
            [
                "users",
                "create",
                "--username",
                "synthetic-viewer",
                "--role",
                "viewer",
                "--password-stdin",
            ]
        )
        == 0
    )
    assert password not in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO(secrets.token_urlsafe(32) + "\n"))
    assert (
        main(["users", "set-password", "--username", "synthetic-viewer", "--password-stdin"]) == 0
    )
    assert main(["users", "disable", "--username", "synthetic-viewer"]) == 0
