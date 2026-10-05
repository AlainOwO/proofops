import asyncio
import secrets
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from proofops.api.app import create_app
from proofops.api.boundaries import SECURITY_HEADERS
from proofops.auth import Principal
from proofops.config import Settings
from sqlalchemy.exc import SQLAlchemyError


def make_app(monkeypatch, *, principal=True, **overrides):
    settings = Settings(
        _env_file=None,
        secret_key=secrets.token_urlsafe(48),
        allowed_hosts="testserver",
        cors_origins="http://testserver",
        session_cookie_secure=False,
        **overrides,
    )
    app = create_app(settings, factory=MagicMock())
    app.state.auth.initialized = True
    identity = Principal("synthetic-user-id", "synthetic-user", "admin", csrf_token="a" * 64)
    if principal is not True:
        identity = principal
    monkeypatch.setattr(app.state.auth, "authenticate", lambda _: identity)

    @app.post("/api/v1/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return app


async def invoke(
    app, path="/healthz", *, method="GET", peer="local-peer", headers=(), receive=None
):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": (peer, 1234),
        "server": ("testserver", 80),
    }
    messages = []

    async def empty():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    try:
        await app(scope, receive or empty, send)
    except RuntimeError:
        # ServerErrorMiddleware intentionally re-raises after sending its 500.
        if not messages or messages[0].get("status") != 500:
            raise
    start = messages[0] if messages else {}
    if start:
        actual = dict(start["headers"])
        assert all(actual.get(key) == value for key, value in SECURITY_HEADERS.items())
    return start.get("status"), messages


async def must_not_read():
    raise AssertionError("a rejected request must not consume its body")


@pytest.mark.parametrize("reason", ["anonymous", "viewer", "csrf", "demo", "unavailable"])
def test_rejections_authorize_before_any_body_read(monkeypatch, reason):
    app = make_app(monkeypatch, principal=None if reason == "anonymous" else True)
    expected = 403
    headers = [(b"content-length", b"999999999999999999999")]
    if reason == "anonymous":
        expected = 401
    if reason == "viewer":
        monkeypatch.setattr(
            app.state.auth, "authenticate", lambda _: Principal("viewer-id", "viewer", "viewer")
        )
    if reason == "demo":
        app.state.settings.proofops_public_demo = True
    if reason == "unavailable":
        app.state.auth.initialized = False
        expected = 503
    status, _ = asyncio.run(
        invoke(app, "/api/v1/echo", method="POST", headers=headers, receive=must_not_read)
    )
    assert status == expected
    assert app.state.admission.active == app.state.admission.buffered_bytes == 0


def test_login_csrf_is_checked_before_reading(monkeypatch):
    app = make_app(monkeypatch)
    status, _ = asyncio.run(invoke(app, "/api/v1/auth/login", method="POST", receive=must_not_read))
    assert status == 403


def test_login_has_a_separate_memory_bound_and_cancellation_releases_it(monkeypatch):
    app = make_app(monkeypatch, request_max_login_concurrency=1)
    monkeypatch.setattr(app.state.auth, "valid_login_csrf", lambda *_: True)

    async def scenario():
        entered = asyncio.Event()

        async def pending_body():
            entered.set()
            await asyncio.Event().wait()

        first = asyncio.create_task(
            invoke(app, "/api/v1/auth/login", method="POST", receive=pending_body)
        )
        await asyncio.wait_for(entered.wait(), 1)
        try:
            assert (
                await invoke(
                    app,
                    "/api/v1/auth/login",
                    method="POST",
                    peer="different-peer",
                    receive=must_not_read,
                )
            )[0] == 503
            assert (await invoke(app))[0] == 200
        finally:
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        assert app.state.admission.login_active == app.state.admission.active == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("chunked", [False, True])
def test_body_deadline_is_absolute_and_releases_capacity(monkeypatch, chunked):
    app = make_app(monkeypatch, request_body_timeout_seconds=0.03)
    reads = 0

    async def slow():
        nonlocal reads
        reads += 1
        await asyncio.sleep(0.01 if chunked else 1)
        return {"type": "http.request", "body": b"x", "more_body": True}

    async def scenario():
        status, _ = await invoke(
            app,
            "/api/v1/echo",
            method="POST",
            headers=[(b"x-csrf-token", b"a" * 64)],
            receive=slow,
        )
        assert status == 408
        assert (await invoke(app))[0] == 200

    asyncio.run(scenario())
    assert 1 <= reads < 10
    assert app.state.admission.active == app.state.admission.buffered_bytes == 0
    assert not any(usage.active for usage in app.state.admission.principals.values())


@pytest.mark.parametrize("limit", ["global", "peer", "principal"])
def test_concurrency_limits_reject_instead_of_queueing(monkeypatch, limit):
    field = {
        "global": "request_max_concurrency",
        "peer": "request_max_peer_concurrency",
        "principal": "request_max_principal_concurrency",
    }[limit]
    app = make_app(monkeypatch, **{field: 1})

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        @app.get("/api/v1/held")
        async def held():
            entered.set()
            await release.wait()
            return {"ok": True}

        first = asyncio.create_task(invoke(app, "/api/v1/held"))
        await asyncio.wait_for(entered.wait(), 1)
        try:
            status, messages = await invoke(
                app,
                "/api/v1/echo",
                method="POST",
                peer="other-peer" if limit == "principal" else "local-peer",
                headers=[(b"x-csrf-token", b"a" * 64), (b"x-forwarded-for", b"new-peer")],
                receive=must_not_read,
            )
            assert status == (503 if limit == "global" else 429)
            assert b"retry-after" in dict(messages[0]["headers"])
        finally:
            release.set()
            assert (await first)[0] == 200
        assert (await invoke(app, "/api/v1/held"))[0] == 200

    asyncio.run(scenario())
    assert app.state.admission.active == 0


@pytest.mark.parametrize("quota", ["peer", "principal"])
def test_request_quotas_survive_completion_and_expire(monkeypatch, quota):
    app = make_app(monkeypatch, **{f"request_{quota}_quota": 1})
    clock = [100.0]
    monkeypatch.setattr("proofops.api.boundaries.monotonic", lambda: clock[0])

    async def scenario():
        assert (await invoke(app, "/api/v1/auth/session"))[0] == 200
        status, _ = await invoke(
            app,
            "/api/v1/echo",
            method="POST",
            peer="new-peer" if quota == "principal" else "local-peer",
            headers=[(b"x-csrf-token", b"a" * 64)],
            receive=must_not_read,
        )
        assert status == 429
        clock[0] += app.state.settings.request_quota_window_seconds + 1
        assert (await invoke(app, "/api/v1/auth/session"))[0] == 200

    asyncio.run(scenario())


def test_peer_identity_state_is_bounded_and_expired_entries_are_reused(monkeypatch):
    app = make_app(monkeypatch, request_max_identities=2)
    clock = [100.0]
    monkeypatch.setattr("proofops.api.boundaries.monotonic", lambda: clock[0])

    async def scenario():
        for peer in ("one", "two"):
            assert (await invoke(app, peer=peer))[0] == 200
        assert (await invoke(app, peer="three", receive=must_not_read))[0] == 503
        assert len(app.state.admission.peers) == 2
        clock[0] += app.state.settings.request_quota_window_seconds + 1
        assert (await invoke(app, peer="three"))[0] == 200

    asyncio.run(scenario())


def test_global_body_byte_quota_is_shared_and_released(monkeypatch):
    app = make_app(monkeypatch, request_max_buffered_bytes=1024)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        reads = 0

        async def held_body():
            nonlocal reads
            reads += 1
            if reads == 1:
                return {"type": "http.request", "body": b"x" * 800, "more_body": True}
            entered.set()
            await release.wait()
            return {"type": "http.disconnect"}

        async def another_body():
            return {"type": "http.request", "body": b"y" * 800, "more_body": False}

        first = asyncio.create_task(
            invoke(
                app,
                "/api/v1/echo",
                method="POST",
                headers=[(b"x-csrf-token", b"a" * 64)],
                receive=held_body,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        try:
            status, _ = await invoke(
                app,
                "/api/v1/echo",
                method="POST",
                headers=[(b"x-csrf-token", b"a" * 64)],
                receive=another_body,
            )
            assert status == 503 and app.state.admission.buffered_bytes == 800
        finally:
            release.set()
            await first
        assert app.state.admission.buffered_bytes == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", ["host", "origin", "length", "size", "validation", "database", "unhandled"]
)
def test_security_headers_cover_error_paths(monkeypatch, failure):
    app = make_app(monkeypatch, max_bundle_bytes=1024)
    headers = [(b"x-csrf-token", b"a" * 64)]
    path = "/api/v1/echo"
    expected = {
        "host": 400,
        "origin": 403,
        "length": 400,
        "size": 413,
        "validation": 422,
        "database": 503,
        "unhandled": 500,
    }[failure]
    if failure == "host":
        # Multiple Host values are covered separately by the ASGI server; replace
        # the default through a new scope wrapper here.
        original = app

        async def changed_host(scope, receive, send):
            scope["headers"][0] = (b"host", b"evil.invalid")
            await original(scope, receive, send)

        target = changed_host
    else:
        target = app
    if failure == "origin":
        headers.append((b"origin", b"https://evil.invalid"))
    elif failure == "length":
        headers.append((b"content-length", b"invalid"))
    elif failure == "size":
        headers.append((b"content-length", b"1025"))
    elif failure == "validation":
        path = "/api/v1/reviews"
    elif failure in {"database", "unhandled"}:

        @app.post("/api/v1/failure")
        def fails():
            if failure == "database":
                raise SQLAlchemyError("synthetic database failure")
            raise RuntimeError("synthetic unhandled failure")

        path = "/api/v1/failure"
    assert asyncio.run(invoke(target, path, method="POST", headers=headers))[0] == expected


def test_blocking_import_parsing_and_storage_do_not_block_health(monkeypatch, valid_bundle):
    app = make_app(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    loop_thread = threading.get_ident()
    workers = []

    def parse(_):
        workers.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return valid_bundle

    def store(*args, **kwargs):
        workers.append(threading.get_ident())
        return SimpleNamespace(id="bundle-id"), True

    monkeypatch.setattr("proofops.api.app.load_replay", parse)
    monkeypatch.setattr("proofops.api.app.store_bundle", store)

    async def body():
        return {"type": "http.request", "body": b'{"replay":"valid-resize"}', "more_body": False}

    async def scenario():
        upload = asyncio.create_task(
            invoke(
                app,
                "/api/v1/bundles",
                method="POST",
                headers=[(b"x-csrf-token", b"a" * 64), (b"content-type", b"application/json")],
                receive=body,
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert (await asyncio.wait_for(invoke(app), 0.5))[0] == 200
        finally:
            release.set()
        assert (await upload)[0] == 201

    asyncio.run(scenario())
    assert len(workers) == 2 and all(worker != loop_thread for worker in workers)


@pytest.mark.parametrize("public_demo", [False, True])
def test_hosted_documentation_is_not_registered_or_served(monkeypatch, public_demo):
    app = make_app(monkeypatch)
    settings = app.state.settings.model_copy(
        update={"proofops_mode": "hosted", "proofops_public_demo": public_demo}
    )
    app = create_app(settings, factory=MagicMock())
    app.state.auth.initialized = True
    monkeypatch.setattr(
        app.state.auth, "authenticate", lambda _: Principal("admin-id", "admin", "admin")
    )
    paths = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    assert not paths.intersection(route.path for route in app.routes)
    for path in paths:
        status, messages = asyncio.run(invoke(app, path))
        assert status == (403 if public_demo else 404)
        assert b"<script" not in b"".join(message.get("body", b"") for message in messages)


def test_local_documentation_stays_authenticated_and_has_no_scripts(monkeypatch):
    app = make_app(monkeypatch)
    for path in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        status, messages = asyncio.run(invoke(app, path))
        assert status == 200
        body = b"".join(message.get("body", b"") for message in messages)
        assert b"/openapi.json" in body and b"<script" not in body
        assert b"https://" not in body
    monkeypatch.setattr(app.state.auth, "authenticate", lambda _: None)
    assert asyncio.run(invoke(app, "/docs", receive=must_not_read))[0] == 401
