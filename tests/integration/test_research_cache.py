from datetime import timedelta

import pytest
from proofops.domain.common import digest
from proofops.storage.database import ToolCacheRow
from proofops.storage.tool_cache import ObservationCache
from proofops.tools.research import ResearchTool, SearchHit
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
