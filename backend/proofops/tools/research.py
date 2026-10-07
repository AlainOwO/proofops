"""Optional bounded public research. Never used as approval or model instructions."""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import ConfigDict, Field, SecretStr, field_validator

from proofops.config import Settings
from proofops.domain.common import canonical, digest, strict_json, utcnow
from proofops.domain.schemas import Record
from proofops.observability import measured
from proofops.storage.bundles import redact_text
from proofops.storage.database import session_factory
from proofops.storage.tool_cache import ObservationCache
from proofops.tools.interfaces import SearchProvider

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
MAX_RESPONSE_BYTES = 262_144


class SearchHit(Record):
    model_config = ConfigDict(hide_input_in_errors=True)
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    snippet: Annotated[str, Field(max_length=2000)] = ""
    content: Annotated[str | None, Field(max_length=8000)] = None
    trusted: Literal[False] = False
    text_format: Literal["plain_text"] = "plain_text"

    @field_validator("url")
    @classmethod
    def attributed_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(character.isspace() or ord(character) < 32 for character in value)
        ):
            raise ValueError("research sources require an absolute HTTP(S) URL without credentials")
        return value

    @field_validator("title", "snippet", "content")
    @classmethod
    def untrusted_text(cls, value: str | None) -> str | None:
        return redact_text(value) if value is not None else None


class ResearchResult(Record):
    status: Literal["disabled", "not_configured", "complete", "empty", "unavailable"]
    provider: str
    sources: list[SearchHit] = Field(default_factory=list, max_length=10)
    collected_at: datetime | None = None
    retrieved_at: datetime
    expires_at: datetime | None = None
    cache_state: Literal["disabled", "hit", "miss", "unavailable"] = "disabled"
    error_code: (
        Literal["timeout", "provider_error", "invalid_response", "response_too_large"] | None
    ) = None
    use: Literal["untrusted_research_context_only"] = "untrusted_research_context_only"
    deployment_approval: Literal[False] = False


class SearchFailure(ValueError):
    def __init__(self, code: Literal["provider_error", "invalid_response", "response_too_large"]):
        super().__init__(code)
        self.code = code


class GoogleSearchProvider:
    name = "google"

    def __init__(self, api_key: SecretStr, engine_id: str, *, transport=None):
        self._key, self._engine, self._transport = api_key, engine_id, transport
        self.cache_identity = digest(
            {
                "adapter": "google-search-v1",
                "engine": engine_id,
                "credential": api_key.get_secret_value(),
            }
        )

    async def search(self, query: str, *, limit: int, timeout: float) -> list[SearchHit]:
        # Fixed endpoint, no redirects, proxy environment or result-URL fetches.
        # Keep the Google system-parameter key in a header, never in the URL.
        async with httpx.AsyncClient(
            transport=self._transport, timeout=timeout, follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(
                "GET",
                SEARCH_URL,
                params={"q": query, "cx": self._engine, "num": limit},
                headers={
                    "X-Goog-Api-Key": self._key.get_secret_value(),
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if response.status_code != 200:
                    raise SearchFailure("provider_error")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise SearchFailure("invalid_response")
                length = response.headers.get("content-length")
                if length and (not length.isdecimal() or int(length) > MAX_RESPONSE_BYTES):
                    raise SearchFailure("response_too_large")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise SearchFailure("response_too_large")
                    raw.extend(chunk)
        payload = strict_json(bytes(raw))
        if (
            self._key.get_secret_value()
            and self._key.get_secret_value() in canonical(payload).decode()
        ):
            raise SearchFailure("invalid_response")
        if not isinstance(payload, dict) or "error" in payload:
            raise SearchFailure("invalid_response")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise SearchFailure("invalid_response")
        return [
            SearchHit(url=item["link"], title=item["title"], snippet=item.get("snippet", ""))
            for item in items[:limit]
        ]


class ResearchTool:
    def __init__(
        self,
        settings: Settings,
        provider: SearchProvider | None = None,
        *,
        cache: ObservationCache | None = None,
    ):
        self.settings, self.provider, self.cache = settings, provider, cache

    @classmethod
    def from_settings(cls, settings: Settings):
        if settings.search_provider == "off" or settings.proofops_public_demo:
            return cls(settings)
        if not settings.search_api_key.get_secret_value() or not settings.search_engine_id:
            return cls(settings)
        provider = GoogleSearchProvider(settings.search_api_key, settings.search_engine_id)
        cache = (
            ObservationCache(session_factory(settings.database_url))
            if settings.search_cache_ttl_seconds
            else None
        )
        return cls(settings, provider, cache=cache)

    @measured("research.search")
    def search(self, query: str) -> ResearchResult:
        now, settings = utcnow(), self.settings
        base = ResearchResult(
            status="disabled", provider=settings.search_provider, retrieved_at=now
        )
        if settings.search_provider == "off" or settings.proofops_public_demo:
            return base
        if self.provider is None:
            return base.model_copy(update={"status": "not_configured"})
        query = query.strip()
        if not query or len(query) > 500:
            raise ValueError("research queries must contain 1–500 characters")
        key = digest(
            {
                "task": "public-research-v1",
                "query": query,
                "limit": settings.search_max_results,
                "provider": self.provider.name,
                "configuration": self.provider.cache_identity,
            }
        )
        base.provider = self.provider.name
        if self.cache and settings.search_cache_ttl_seconds:
            lookup = self.cache.get("search", key, settings.search_cache_ttl_seconds, now)
            base.cache_state = lookup.state
            if lookup.observation:
                try:
                    cached = ResearchResult.model_validate(lookup.observation.data)
                    if (
                        cached.status in {"complete", "empty"}
                        and cached.provider == self.provider.name
                        and cached.collected_at == lookup.observation.collected_at
                        and len(cached.sources) <= settings.search_max_results
                    ):
                        return cached.model_copy(
                            update={
                                "cache_state": "hit",
                                "retrieved_at": now,
                                "expires_at": lookup.observation.expires_at,
                            }
                        )
                except ValueError:
                    pass
                base.cache_state = "miss"

        async def bounded_search():
            async with asyncio.timeout(settings.search_timeout_seconds):
                assert self.provider is not None
                return await self.provider.search(
                    query,
                    limit=settings.search_max_results,
                    timeout=settings.search_timeout_seconds,
                )

        try:
            raw_sources = asyncio.run(bounded_search())
            if not isinstance(raw_sources, list) or len(raw_sources) > settings.search_max_results:
                raise SearchFailure("invalid_response")
            sources = [
                SearchHit.model_validate(item.model_dump() if isinstance(item, SearchHit) else item)
                for item in raw_sources
            ]
            if len(canonical(sources)) > MAX_RESPONSE_BYTES:
                raise SearchFailure("response_too_large")
        except (TimeoutError, httpx.TimeoutException):
            return base.model_copy(update={"status": "unavailable", "error_code": "timeout"})
        except SearchFailure as exc:
            return base.model_copy(update={"status": "unavailable", "error_code": exc.code})
        except (ValueError, KeyError, TypeError):
            return base.model_copy(
                update={"status": "unavailable", "error_code": "invalid_response"}
            )
        except Exception:
            # Optional providers cannot expose response bodies or stop a review.
            return base.model_copy(update={"status": "unavailable", "error_code": "provider_error"})
        base.status = "complete" if sources else "empty"
        base.sources, base.collected_at = sources, utcnow()
        base.retrieved_at = base.collected_at
        if self.cache and settings.search_cache_ttl_seconds and base.cache_state != "unavailable":
            if self.cache.put(
                "search",
                key,
                base.model_dump(mode="json"),
                base.collected_at,
                settings.search_cache_ttl_seconds,
            ):
                base.expires_at = base.collected_at + timedelta(
                    seconds=settings.search_cache_ttl_seconds
                )
        return base
