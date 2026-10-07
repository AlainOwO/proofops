"""Small JSON operation records, with no SQL, request bodies or provider text."""

import json
import logging
import math
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from time import perf_counter
from typing import ParamSpec, TypeVar
from uuid import UUID, uuid4

logger = logging.getLogger("proofops.operations")
current_operation: ContextVar["Operation | None"] = ContextVar("proofops_operation", default=None)
METRICS = {
    "db_queries",
    "db_duration_ms",
    "artifact_bytes",
    "response_bytes",
    "queue_wait_ms",
    "provider_calls",
    "attempts",
    "input_tokens",
    "output_tokens",
    "actual_cost_usd",
    "cache_hits",
    "cache_misses",
    "http_status",
    "source_failures",
    "job_age_ms",
}
P = ParamSpec("P")
R = TypeVar("R")


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass
class Operation:
    name: str
    job_id: str | None = None
    request_id: str | None = None
    status: str = "ok"
    metrics: dict = field(default_factory=lambda: {"db_queries": 0, "db_duration_ms": 0.0})
    parent: "Operation | None" = None
    route: str | None = None
    method: str | None = None
    lock: Lock = field(default_factory=Lock)

    def add(self, name: str, value: int | float) -> None:
        if name in METRICS and type(value) in {int, float} and math.isfinite(value) and value >= 0:
            with self.lock:
                self.metrics[name] = self.metrics.get(name, 0) + value

    def query(self, seconds: float) -> None:
        self.add("db_queries", 1)
        self.add("db_duration_ms", seconds * 1000)
        if self.parent:
            self.parent.query(seconds)


@contextmanager
def operation(name: str, *, job_id: str | None = None, request_id: str | None = None, enabled=True):
    parent = current_operation.get()
    value = Operation(
        name,
        job_id or (parent.job_id if parent else None),
        request_id or (parent.request_id if parent else None),
        parent=parent,
    )
    started = perf_counter()
    token = current_operation.set(value) if enabled else None
    try:
        yield value
    except BaseException:
        value.status = "failed"
        raise
    finally:
        if token is not None:
            current_operation.reset(token)
            record = {
                "operation": name,
                "status": value.status,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                **value.metrics,
            }
            if value.route is not None:
                record["route"], record["method"] = value.route, value.method
            for key, identity in (("job_id", value.job_id), ("request_id", value.request_id)):
                if identity:
                    try:
                        record[key] = str(UUID(identity))
                    except ValueError:
                        pass
            logger.info(json.dumps(record, separators=(",", ":"), allow_nan=False))


def measured(name: str):
    """Instrument provider operations without recording arguments or output text."""

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            instance = args[0] if args else None
            settings = getattr(instance, "settings", None)
            enabled = getattr(
                settings, "operation_logging", getattr(instance, "operation_logging", True)
            )
            with operation(name, enabled=enabled) as span:
                result = function(*args, **kwargs)
                status = (
                    result.get("status")
                    if isinstance(result, dict)
                    else getattr(result, "status", None)
                )
                if status in {"unavailable", "explanation_unavailable", "not_configured"}:
                    span.status = "unavailable"
                cache = (
                    result.get("cache", {}).get("state")
                    if isinstance(result, dict)
                    else getattr(result, "cache_state", None)
                )
                if status == "cached" or cache == "hit":
                    span.add("cache_hits", 1)
                elif cache == "miss" or (
                    status == "accepted" and getattr(settings, "ai_cache_enabled", True)
                ):
                    span.add("cache_misses", 1)
                if isinstance(result, dict):
                    failed_sources = sum(
                        item.get("status") in {"failed", "denied", "pending"}
                        for item in result.get("sources", [])
                    )
                    if failed_sources:
                        span.status = "incomplete"
                        span.add("source_failures", failed_sources)
                    if type(result.get("calls")) is int:
                        span.add("provider_calls", result["calls"])
                    attempts = result.get("attempts", [])
                    if attempts:
                        span.add("attempts", len(attempts))
                        for attempt in attempts:
                            usage = attempt.get("usage") or {}
                            for key, field_name in (
                                ("input_uncached", "input_tokens"),
                                ("output", "output_tokens"),
                            ):
                                if type(usage.get(key)) is int:
                                    span.add(field_name, usage[key])
                        if result.get("incremental_cost_usd") is not None:
                            span.add("actual_cost_usd", float(result["incremental_cost_usd"]))
                return result

        return wrapped

    return decorate


class RequestOperations:
    def __init__(self, app, *, enabled=True):
        self.app, self.enabled = app, enabled

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] != "http" or scope.get("path") == "/healthz":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        with operation("http.request", request_id=request_id) as span:
            span.method = (
                scope.get("method")
                if scope.get("method")
                in {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"}
                else "other"
            )

            async def measured_send(message):
                if message["type"] == "http.response.start":
                    span.add("http_status", message["status"])
                    if message["status"] >= 400:
                        span.status = "failed"
                    headers = [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"x-request-id"
                    ]
                    message = {
                        **message,
                        "headers": headers + [(b"x-request-id", request_id.encode())],
                    }
                elif message["type"] == "http.response.body":
                    span.add("response_bytes", len(message.get("body", b"")))
                await send(message)

            try:
                await self.app(scope, receive, measured_send)
            finally:
                # Registered templates only: never log a user URL or query.
                span.route = getattr(scope.get("route"), "path", "unmatched")
