"""Bound HTTP work before authentication/storage and bodies after authorization.

Admission is per API process. The hosted deployment runs one bounded API process;
adding replicas requires dividing these budgets or a shared edge admission service.
Connection peers come from ASGI, never client-supplied forwarding headers.
"""

import asyncio
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from proofops.config import Settings
from proofops.observability import RequestOperations

SECURITY_HEADERS = {
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    b"x-frame-options": b"DENY",
    b"x-content-type-options": b"nosniff",
    b"cache-control": b"no-store",
    b"referrer-policy": b"no-referrer",
}


class SecurityHeadersBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def safe_send(message):
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in SECURITY_HEADERS
                ]
                message = {**message, "headers": headers + list(SECURITY_HEADERS.items())}
            await send(message)

        await self.app(scope, receive, safe_send)


class SecureFastAPI(FastAPI):
    def build_middleware_stack(self):
        # Starlette's ServerErrorMiddleware is outside add_middleware(). Wrap it
        # too, so unhandled 500s and every middleware rejection get the headers.
        return SecurityHeadersBoundary(
            RequestOperations(
                super().build_middleware_stack(),
                enabled=getattr(self.state, "operation_logging", True),
            )
        )


class OriginBoundary:
    def __init__(self, app, *, origins: set[str]):
        self.app, self.origins = app, origins

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            origin = Request(scope).headers.get("origin")
            if origin and origin not in self.origins:
                await JSONResponse({"detail": "origin is not allowed"}, status_code=403)(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


@dataclass
class Usage:
    started: float
    requests: int = 0
    active: int = 0


class AdmissionController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = Lock()
        self.active = 0
        self.login_active = 0
        self.buffered_bytes = 0
        self.peers: dict[str, Usage] = {}
        self.principals: dict[str, Usage] = {}

    def _acquire(self, entries: dict[str, Usage], key: str, concurrency: int, quota: int) -> int:
        now = monotonic()
        window = self.settings.request_quota_window_seconds
        # Bounded identity state, including rotating peers and invalid sessions.
        if key not in entries:
            expired = [
                value
                for value, usage in entries.items()
                if not usage.active and usage.started + window <= now
            ]
            for value in expired:
                del entries[value]
            if len(entries) >= self.settings.request_max_identities:
                return 503
            entries[key] = Usage(started=now)
        usage = entries[key]
        if usage.started + window <= now:
            usage.started, usage.requests = now, 0
        if usage.active >= concurrency or usage.requests >= quota:
            return 429
        usage.requests += 1
        usage.active += 1
        return 0

    def acquire_peer(self, peer: str) -> int:
        with self.lock:
            if self.active >= self.settings.request_max_concurrency:
                return 503
            status = self._acquire(
                self.peers,
                peer,
                self.settings.request_max_peer_concurrency,
                self.settings.request_peer_quota,
            )
            if not status:
                self.active += 1
            return status

    def release_peer(self, peer: str) -> None:
        with self.lock:
            self.active -= 1
            self.peers[peer].active -= 1

    def acquire_principal(self, principal: str) -> int:
        with self.lock:
            return self._acquire(
                self.principals,
                principal,
                self.settings.request_max_principal_concurrency,
                self.settings.request_principal_quota,
            )

    def release_principal(self, principal: str) -> None:
        with self.lock:
            self.principals[principal].active -= 1

    def reserve_bytes(self, count: int) -> bool:
        with self.lock:
            if self.buffered_bytes + count > self.settings.request_max_buffered_bytes:
                return False
            self.buffered_bytes += count
            return True

    def acquire_login(self) -> bool:
        with self.lock:
            if self.login_active >= self.settings.request_max_login_concurrency:
                return False
            self.login_active += 1
            return True

    def release_login(self) -> None:
        with self.lock:
            self.login_active -= 1

    def release_bytes(self, count: int) -> None:
        with self.lock:
            self.buffered_bytes -= count


def admission_rejection(status: int, settings: Settings) -> JSONResponse:
    return JSONResponse(
        {"detail": "Request capacity exceeded. Try again later."},
        status_code=status,
        headers={"Retry-After": str(settings.request_quota_window_seconds)},
    )


class AdmissionBoundary:
    """No waiting queue: reject excess work before even session lookup/hashing."""

    def __init__(self, app, *, admission: AdmissionController):
        self.app, self.admission = app, admission

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        peer = (scope.get("client") or ("unknown", 0))[0]
        status = self.admission.acquire_peer(peer)
        if status:
            await admission_rejection(status, self.admission.settings)(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self.admission.release_peer(peer)


class BodyBoundary:
    """Only reached after authorization, including roles, demo mode and CSRF."""

    def __init__(self, app, *, admission: AdmissionController):
        self.app, self.admission = app, admission

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        principal = scope.get("state", {}).get("principal")
        user_id = principal.user_id if principal else None
        if user_id:
            status = self.admission.acquire_principal(user_id)
            if status:
                await admission_rejection(status, self.admission.settings)(scope, receive, send)
                return
        login = (scope["method"], scope["path"]) == ("POST", "/api/v1/auth/login")
        if login and not self.admission.acquire_login():
            if user_id:
                self.admission.release_principal(user_id)
            await admission_rejection(503, self.admission.settings)(scope, receive, send)
            return
        try:
            await self.buffer(scope, receive, send)
        finally:
            if login:
                self.admission.release_login()
            if user_id:
                self.admission.release_principal(user_id)

    async def buffer(self, scope, receive, send):
        settings = self.admission.settings
        maximum = settings.max_bundle_bytes
        if scope["path"] == "/api/v1/auth/login":
            maximum = min(maximum, 4096)
        lengths = Request(scope).headers.getlist("content-length")
        if lengths and (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()):
            await JSONResponse({"detail": "invalid content length"}, status_code=400)(
                scope, receive, send
            )
            return
        if lengths and (len(lengths[0]) > 12 or int(lengths[0]) > maximum):
            await JSONResponse(
                {"detail": "request body exceeds configured limit"}, status_code=413
            )(scope, receive, send)
            return
        body = bytearray()
        reserved = 0
        try:
            try:
                # Absolute deadline: sending tiny chunks cannot restart the clock.
                async with asyncio.timeout(settings.request_body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > maximum:
                            await JSONResponse(
                                {"detail": "request body exceeds configured limit"}, status_code=413
                            )(scope, receive, send)
                            return
                        if not self.admission.reserve_bytes(len(chunk)):
                            await admission_rejection(503, settings)(scope, receive, send)
                            return
                        reserved += len(chunk)
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await JSONResponse({"detail": "request body read timed out"}, status_code=408)(
                    scope, receive, send
                )
                return
            consumed = False

            async def replay_receive():
                nonlocal consumed
                if consumed:
                    return await receive()
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay_receive, send)
        finally:
            self.admission.release_bytes(reserved)
