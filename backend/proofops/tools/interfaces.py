from typing import TYPE_CHECKING, Protocol

from proofops.domain.schemas import Scope

if TYPE_CHECKING:
    from proofops.tools.pricing import RateCardSnapshot
    from proofops.tools.research import SearchHit


class EvidenceProvider(Protocol):
    def collect(self, scope: Scope) -> dict: ...


class PricingProvider(Protocol):
    def load(self) -> "RateCardSnapshot": ...


class SearchProvider(Protocol):
    name: str
    cache_identity: str

    async def search(self, query: str, *, limit: int, timeout: float) -> list["SearchHit"]: ...
