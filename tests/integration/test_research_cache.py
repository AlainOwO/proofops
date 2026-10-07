import secrets
from datetime import timedelta

import httpx
import pytest
from proofops.domain.common import canonical, digest
from proofops.storage.database import ToolCacheRow
from proofops.storage.tool_cache import ObservationCache
from proofops.tools.research import GoogleSearchProvider, ResearchTool, SearchHit
from sqlalchemy import select

from tests.unit.test_research_tool import settings

pytestmark = pytest.mark.integration


class Provider:
    name, cache_identity = "mock", "configuration-1"
    calls = 0

    async def search(self, query, **kwargs):
        self.calls += 1
        return [SearchHit(url="https://example.org/public", title="Public source", snippet=query)]


def test_research_cache_hit_expiry_query_and_configuration(db):
    provider = Provider()
    configuration = settings(search_cache_ttl_seconds=60)
    tool = ResearchTool(configuration, provider, cache=ObservationCache(db))
    first = tool.search("public docs")
    second = tool.search("public docs")
    assert first.status == second.status == "complete" and provider.calls == 1
    assert first.expires_at and second.cache_state == "hit"
    assert second.collected_at == first.collected_at and second.sources == first.sources
    with db.begin() as session:
        session.scalar(select(ToolCacheRow)).expires_at -= timedelta(seconds=120)
    assert tool.search("public docs").cache_state == "miss" and provider.calls == 2
    assert tool.search("public docs").cache_state == "hit" and provider.calls == 2
    assert tool.search("different public docs").cache_state == "miss" and provider.calls == 3
    provider.cache_identity = digest("new configuration")
    assert tool.search("public docs").cache_state == "miss" and provider.calls == 4
    configuration.search_max_results = 2
    assert tool.search("public docs").cache_state == "miss" and provider.calls == 5


def test_failed_research_is_not_cached(db):
    class Failed(Provider):
        async def search(self, query, **kwargs):
            raise RuntimeError("untrusted provider body")

    tool = ResearchTool(settings(search_cache_ttl_seconds=60), Failed(), cache=ObservationCache(db))
    result = tool.search("public docs")
    assert result.status == "unavailable" and result.error_code == "provider_error"
    with db() as session:
        assert session.scalar(select(ToolCacheRow)) is None


@pytest.mark.parametrize("suffix", ["?access_token=", "#token=", "?X-Amz-Signature="])
def test_open_research_source_url_credentials_are_retained_in_cache(db, suffix):
    """Characterize the open URL-redaction finding, using only generated canaries."""
    marker = secrets.token_urlsafe(24)
    configuration = settings(search_cache_ttl_seconds=60)
    provider = GoogleSearchProvider(
        configuration.search_api_key,
        configuration.search_engine_id,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "link": "https://example.org/document" + suffix + marker,
                            "title": "Public source",
                            "snippet": "access_token=" + marker,
                        }
                    ]
                },
            )
        ),
    )
    tool = ResearchTool(configuration, provider, cache=ObservationCache(db))
    result = tool.search("public documentation")
    assert result.status == "complete"
    assert result.sources[0].snippet == "[REDACTED]"
    assert marker in result.sources[0].url
    with db() as session:
        row = session.scalar(select(ToolCacheRow))
        assert row is not None and marker in canonical(row.data).decode()
    cached = tool.search("public documentation")
    assert cached.cache_state == "hit" and marker in cached.sources[0].url


def test_open_research_cache_is_shared_across_operator_account_contexts(db):
    """Public CLI research currently has configuration scope, not account/user scope."""
    first_settings = settings(search_cache_ttl_seconds=60, aws_account_id="111122223333")
    second_settings = first_settings.model_copy(update={"aws_account_id": "444455556666"})
    first_provider, second_provider = Provider(), Provider()
    cache = ObservationCache(db)
    first = ResearchTool(first_settings, first_provider, cache=cache).search("public docs")
    second = ResearchTool(second_settings, second_provider, cache=cache).search("public docs")
    assert first.status == second.status == "complete"
    assert second.cache_state == "hit" and second.sources == first.sources
    assert first_provider.calls == 1 and second_provider.calls == 0


def test_demo_and_disabled_research_cannot_read_existing_cache(db):
    configuration = settings(search_cache_ttl_seconds=60)
    cache = ObservationCache(db)
    provider = Provider()
    assert (
        ResearchTool(configuration, provider, cache=cache).search("public docs").status
        == "complete"
    )

    class ForbiddenCache:
        def get(self, *args, **kwargs):
            raise AssertionError("disabled research attempted a cache read")

        def put(self, *args, **kwargs):
            raise AssertionError("disabled research attempted a cache write")

    for changes in ({"proofops_public_demo": True}, {"search_provider": "off"}):
        disabled = ResearchTool(
            configuration.model_copy(update=changes), provider, cache=ForbiddenCache()
        ).search("public docs")
        assert disabled.status == "disabled" and disabled.sources == []
    assert provider.calls == 1
