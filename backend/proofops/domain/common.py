import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Unsupported serialization type: {type(value).__name__}")


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=json_value,
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json(raw: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

    def bound(value: Any, depth: int = 0) -> None:
        if depth > 32:
            raise ValueError("JSON nesting exceeds 32 levels")
        if isinstance(value, dict):
            if len(value) > 1000:
                raise ValueError("Too many JSON object fields")
            for child in value.values():
                bound(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 10000:
                raise ValueError("Too many JSON array items")
            for child in value:
                bound(child, depth + 1)

    bound(result)
    return result
