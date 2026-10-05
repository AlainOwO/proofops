"""Password identities, revocable server sessions and shared login limits.

The review engine has no dependency on this module. Secrets and raw session
tokens are never stored in the database or included in error messages.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert

from proofops.config import Settings
from proofops.domain.common import utcnow
from proofops.storage.database import AuthSessionRow, LoginThrottleRow, UserRow

HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2, type=Type.ID)
LOGIN_CSRF_TTL = 600
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "api", "testserver"}
AUTH_PRUNE_BATCH = 100


def prune_expired_auth(session, now: datetime, window: timedelta) -> None:
    """Bound maintenance work and never wait on another login's locked rows."""
    expired_sessions = (
        select(AuthSessionRow.token_hash)
        .where(AuthSessionRow.expires_at <= now)
        .order_by(AuthSessionRow.expires_at)
        .limit(AUTH_PRUNE_BATCH)
        .with_for_update(skip_locked=True)
    )
    session.execute(delete(AuthSessionRow).where(AuthSessionRow.token_hash.in_(expired_sessions)))
    expired_throttles = (
        select(LoginThrottleRow.key_hash)
        .where(
            LoginThrottleRow.window_start < now - window * 2,
            or_(LoginThrottleRow.blocked_until.is_(None), LoginThrottleRow.blocked_until <= now),
        )
        .order_by(LoginThrottleRow.window_start)
        .limit(AUTH_PRUNE_BATCH)
        .with_for_update(skip_locked=True)
    )
    session.execute(
        delete(LoginThrottleRow).where(LoginThrottleRow.key_hash.in_(expired_throttles))
    )


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", value):
        raise ValueError(
            "Username must contain 3–64 ASCII letters, digits, dots, dashes or underscores."
        )
    return value


def validate_password(password: str, username: str) -> None:
    compact = re.sub(r"[^a-z0-9]", "", password.lower())
    if (
        not 14 <= len(password) <= 128
        or len(set(password)) < 8
        or username.lower() in password.lower()
        or any(word in compact for word in ("password", "changeme", "replaceme", "yourpassword"))
        or compact in "abcdefghijklmnopqrstuvwxyz0123456789"
        or compact == "correcthorsebatterystaple"
    ):
        raise ValueError(
            "Use a unique password of 14–128 characters with at least 8 distinct characters; "
            "do not include the username, common passwords or setup placeholders."
        )


def strong_password_hash(value: str) -> bool:
    try:
        parameters = extract_parameters(value)
        return (
            parameters.type == Type.ID
            and parameters.version == 19
            and parameters.memory_cost >= 65_536
            and parameters.time_cost >= 3
            and parameters.hash_len >= 32
            and parameters.salt_len >= 16
        )
    except (InvalidHashError, ValueError):
        return False


def security_configuration(settings: Settings) -> tuple[set[str], list[str]]:
    secret = settings.secret_key.get_secret_value()
    if (
        len(secret) < 32
        or len(set(secret)) < 16
        or any(
            word in secret.lower() for word in ("change-me", "changeme", "replace", "your-secret")
        )
    ):
        raise ValueError(
            "SECRET_KEY must contain at least 32 random characters; generate it at setup."
        )
    origins = {item.strip() for item in settings.cors_origins.split(",") if item.strip()}
    hosts = [item.strip() for item in settings.allowed_hosts.split(",") if item.strip()]
    if (
        not origins
        or not hosts
        or any(not re.fullmatch(r"[A-Za-z0-9.-]+|::1", host) for host in hosts)
    ):
        raise ValueError("Configure explicit CORS_ORIGINS and ALLOWED_HOSTS without wildcards.")
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
        ):
            raise ValueError(
                "CORS_ORIGINS must contain exact HTTP(S) origins without paths or wildcards."
            )
        if settings.proofops_mode == "local" and parsed.hostname not in LOCAL_HOSTS:
            raise ValueError("Non-local origins require PROOFOPS_MODE=hosted.")
        if settings.proofops_mode == "hosted" and parsed.scheme != "https":
            raise ValueError("Hosted mode requires HTTPS origins and a TLS reverse proxy.")
    if settings.proofops_mode == "local" and any(host not in LOCAL_HOSTS for host in hosts):
        raise ValueError("Non-local hosts require PROOFOPS_MODE=hosted.")
    if settings.proofops_mode == "hosted" and not settings.session_cookie_secure:
        raise ValueError("Hosted mode requires SESSION_COOKIE_SECURE=true.")
    return origins, hosts


def create_user(factory, username: str, password: str, role: str) -> UserRow:
    username = normalize_username(username)
    validate_password(password, username)
    if role not in {"admin", "viewer"}:
        raise ValueError("Role must be admin or viewer.")
    encoded = HASHER.hash(password)
    with factory.begin() as session:
        if session.scalar(select(UserRow.id).where(UserRow.username == username)):
            raise ValueError("User already exists; use users set-password to rotate credentials.")
        user = UserRow(username=username, password_hash=encoded, role=role)
        session.add(user)
        session.flush()
        return user


def update_user(factory, username: str, *, password: str | None = None, disable=False) -> None:
    username = normalize_username(username)
    if password is not None:
        validate_password(password, username)
    with factory.begin() as session:
        user = session.scalar(select(UserRow).where(UserRow.username == username).with_for_update())
        if user is None:
            raise ValueError("User not found.")
        if password is not None:
            user.password_hash = HASHER.hash(password)
            user.password_policy_version = 1
        if disable:
            user.active = False
        session.execute(delete(AuthSessionRow).where(AuthSessionRow.user_id == user.id))


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    username: str | None
    role: str
    csrf_token: str | None = None
    expires_at: datetime | None = None
    public_demo: bool = False

    def public(self) -> dict:
        return {
            "username": self.username,
            "role": self.role,
            "csrf_token": self.csrf_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "public_demo": self.public_demo,
        }


class AuthService:
    def __init__(self, settings: Settings, factory):
        self.settings, self.factory = settings, factory
        self.key = settings.secret_key.get_secret_value().encode()
        prefix = "__Host-" if settings.session_cookie_secure else ""
        self.cookie_name = prefix + "proofops_session"
        self.login_cookie_name = prefix + "proofops_login_csrf"
        self.initialized = False
        self.dummy_hash = ""

    def mac(self, purpose: str, value: str) -> str:
        return hmac.new(self.key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

    def initialize(self) -> None:
        security_configuration(self.settings)
        username = self.settings.proofops_admin_username
        password = self.settings.proofops_admin_password.get_secret_value()
        if bool(username) != bool(password):
            raise ValueError("Supply both admin setup variables, or create an admin with the CLI.")
        if username:
            username = normalize_username(username)
            validate_password(password, username)
            with self.factory.begin() as session:
                session.execute(
                    insert(UserRow)
                    .values(username=username, password_hash=HASHER.hash(password), role="admin")
                    .on_conflict_do_nothing(index_elements=[UserRow.username])
                )
                admin = session.scalar(select(UserRow).where(UserRow.username == username))
                if admin is None or not admin.active or admin.role != "admin":
                    raise ValueError(
                        "Configured bootstrap admin is unavailable; use the users CLI."
                    )
                try:
                    HASHER.verify(admin.password_hash, password)
                except (VerificationError, InvalidHashError) as exc:
                    raise ValueError(
                        "Admin setup credentials disagree with storage; remove stale setup variables."
                    ) from exc
        with self.factory() as session:
            admins = session.scalars(
                select(UserRow).where(UserRow.role == "admin", UserRow.active)
            ).all()
            if self.settings.proofops_mode == "hosted" and not any(
                user.password_policy_version >= 1 and strong_password_hash(user.password_hash)
                for user in admins
            ):
                raise ValueError(
                    "Hosted mode requires an active admin created with strong credentials."
                )
        self.dummy_hash = HASHER.hash(secrets.token_urlsafe(32))
        self.initialized = True

    def login_challenge(self) -> tuple[str, str]:
        value = f"{int(utcnow().timestamp())}.{secrets.token_urlsafe(32)}"
        cookie = f"{value}.{self.mac('login-cookie', value)}"
        return cookie, self.mac("login-csrf", cookie)

    def valid_login_csrf(self, cookie: str, header: str) -> bool:
        if len(cookie) > 180 or not header or len(header) != 64:
            return False
        try:
            timestamp, nonce, signature = cookie.split(".")
            age = utcnow().timestamp() - int(timestamp)
            return (
                0 <= age <= LOGIN_CSRF_TTL
                and bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce))
                and hmac.compare_digest(signature, self.mac("login-cookie", f"{timestamp}.{nonce}"))
                and hmac.compare_digest(header, self.mac("login-csrf", cookie))
            )
        except (ValueError, TypeError):
            return False

    def authenticate(self, token: str) -> Principal | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        with self.factory() as session:
            found = session.execute(
                select(AuthSessionRow, UserRow)
                .join(UserRow, UserRow.id == AuthSessionRow.user_id)
                .where(AuthSessionRow.token_hash == self.mac("session", token))
            ).first()
            if found is None:
                return None
            saved, user = found
            if (
                saved.expires_at <= utcnow()
                or not user.active
                or user.role not in {"admin", "viewer"}
            ):
                return None
            return Principal(
                user.id, user.username, user.role, self.mac("csrf", token), saved.expires_at
            )

    def login(self, username: str, password: str, peer: str) -> tuple[str | None, bool]:
        """Atomic per-account failures and per-peer attempts, shared across workers.

        Limits exist for unknown accounts too. Forwarded headers are deliberately
        not used as identity. A failed attempt never discloses account existence.
        """
        now = utcnow()
        window = timedelta(seconds=self.settings.login_window_seconds)
        username = username.strip().lower()
        with self.factory.begin() as session:

            def available_counter(key: str, maximum: int) -> LoginThrottleRow | None:
                session.execute(
                    insert(LoginThrottleRow)
                    .values(key_hash=key, attempts=0, window_start=now)
                    .on_conflict_do_nothing(index_elements=[LoginThrottleRow.key_hash])
                )
                counter = session.scalars(
                    select(LoginThrottleRow)
                    .where(LoginThrottleRow.key_hash == key)
                    .with_for_update()
                ).one()
                if counter.blocked_until and counter.blocked_until > now:
                    return None
                if counter.window_start + window <= now or counter.blocked_until is not None:
                    counter.attempts, counter.window_start, counter.blocked_until = 0, now, None
                if counter.attempts >= maximum:
                    counter.blocked_until = now + window
                    return None
                return counter

            # Every process locks peer -> account -> user, in that order. A blocked
            # peer cannot allocate arbitrary username rows or trigger maintenance.
            peer_counter = available_counter(
                self.mac("login-peer", peer), self.settings.login_max_ip_attempts
            )
            if peer_counter is None:
                return None, True
            if peer_counter.attempts == 0:
                prune_expired_auth(session, now, window)
            peer_counter.attempts += 1
            if peer_counter.attempts >= self.settings.login_max_ip_attempts:
                peer_counter.blocked_until = now + window
            account_counter = available_counter(
                self.mac("login-user", username), self.settings.login_max_failures
            )
            if account_counter is None:
                return None, True
            account_counter.attempts += 1
            user = session.scalar(
                select(UserRow).where(UserRow.username == username).with_for_update()
            )
            valid = False
            try:
                valid = HASHER.verify(user.password_hash if user else self.dummy_hash, password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                pass
            if not valid or user is None or not user.active:
                if account_counter.attempts >= self.settings.login_max_failures:
                    account_counter.blocked_until = now + window
                return None, False
            account_counter.attempts, account_counter.blocked_until = 0, None
            if HASHER.check_needs_rehash(user.password_hash):
                user.password_hash = HASHER.hash(password)
            token = secrets.token_urlsafe(32)
            session.add(
                AuthSessionRow(
                    token_hash=self.mac("session", token),
                    user_id=user.id,
                    expires_at=now + timedelta(seconds=self.settings.session_ttl_seconds),
                )
            )
            return token, False

    def logout(self, token: str) -> None:
        with self.factory.begin() as session:
            session.execute(
                delete(AuthSessionRow).where(
                    AuthSessionRow.token_hash == self.mac("session", token)
                )
            )
