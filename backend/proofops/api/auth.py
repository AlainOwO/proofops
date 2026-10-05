"""A default-deny boundary outside route handlers, including docs and future routes."""

import hmac
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from proofops.auth import AuthService, Principal

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# GET login only issues a short-lived CSRF challenge; POST login verifies it.
PUBLIC_ROUTES = {("GET", "/healthz"), ("GET", "/api/v1/auth/login"), ("POST", "/api/v1/auth/login")}
DEMO_READ_PATHS = {
    "/healthz",
    "/readyz",
    "/api/v1/auth/login",
    "/api/v1/auth/session",
    "/api/v1/replays",
    "/api/v1/reviews",
    "/api/v1/analytics",
}


class AuthenticationBoundary(BaseHTTPMiddleware):
    def __init__(self, app, *, auth: AuthService):
        super().__init__(app)
        self.auth = auth

    async def dispatch(self, request: Request, call_next):
        path, method = request.url.path, request.method
        if (method, path) == ("GET", "/healthz"):
            return await call_next(request)
        if not self.auth.initialized:
            return JSONResponse({"detail": "Authentication is unavailable."}, status_code=503)
        if self.auth.settings.proofops_public_demo:
            if method not in {"GET", "HEAD"}:
                return JSONResponse({"detail": "Public demo is read-only."}, status_code=403)
            if path not in DEMO_READ_PATHS and not re.fullmatch(
                r"/api/v1/reviews/[a-fA-F0-9-]{36}(?:/bundle)?", path
            ):
                return JSONResponse({"detail": "Unavailable in the public demo."}, status_code=403)
            request.state.principal = Principal(None, None, "viewer", public_demo=True)
            return await call_next(request)
        if (method, path) in PUBLIC_ROUTES:
            if method == "POST" and not self.auth.valid_login_csrf(
                request.cookies.get(self.auth.login_cookie_name, ""),
                request.headers.get("X-CSRF-Token", ""),
            ):
                return JSONResponse({"detail": "Invalid CSRF token."}, status_code=403)
            return await call_next(request)
        token = request.cookies.get(self.auth.cookie_name, "")
        try:
            principal = await run_in_threadpool(self.auth.authenticate, token)
        except SQLAlchemyError:
            return JSONResponse({"detail": "Authentication is unavailable."}, status_code=503)
        if principal is None:
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        request.state.principal = principal
        if method not in SAFE_METHODS:
            # Logging out is the only member write; every other present or future write needs admin.
            if principal.role != "admin" and (method, path) != ("POST", "/api/v1/auth/logout"):
                return JSONResponse({"detail": "Administrator access required."}, status_code=403)
            supplied = request.headers.get("X-CSRF-Token", "")
            if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(
                supplied, principal.csrf_token or ""
            ):
                return JSONResponse({"detail": "Invalid CSRF token."}, status_code=403)
        return await call_next(request)
