"""Dated pricing input; calculations stay in domain.costs with Decimal arithmetic."""

from pathlib import Path

from proofops.config import APP_ROOT
from proofops.domain.common import bytes_digest, strict_json
from proofops.domain.schemas import Hash, RateCard, Record


class RateCardSnapshot(Record):
    rates: RateCard
    content_hash: Hash


class FileRateCardProvider:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> RateCardSnapshot:
        path = self.path.resolve()
        if not path.is_relative_to(APP_ROOT) or any(
            part in {"evaluation", "evaluator_only", ".git"}
            for part in path.relative_to(APP_ROOT).parts
        ):
            raise ValueError("rate cards must stay inside application input storage")
        with path.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("rate card exceeds size bound")
        return RateCardSnapshot(
            rates=RateCard.model_validate(strict_json(raw)), content_hash=bytes_digest(raw)
        )
