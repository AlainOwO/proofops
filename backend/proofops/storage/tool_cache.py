"""Bounded, disposable observations. A cache failure never creates fresh evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from proofops.domain.common import canonical, utcnow
from proofops.storage.coordination import try_work_lock
from proofops.storage.database import ToolCacheRow

MAX_CACHE_ENTRIES = 128
MAX_CACHE_BYTES = 524_288


@dataclass(frozen=True)
class CachedObservation:
    data: dict
    collected_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class CacheLookup:
    state: Literal["hit", "miss", "unavailable"]
    observation: CachedObservation | None = None


def prune_expired(session, table, now: datetime) -> None:
    expired = (
        select(table.key)
        .where(table.expires_at <= now)
        .order_by(table.expires_at)
        .limit(64)
        .with_for_update(skip_locked=True)
    )
    session.execute(delete(table).where(table.key.in_(expired)))


class ObservationCache:
    def __init__(self, factory):
        self.factory = factory

    def get(self, namespace: str, key: str, ttl: int, now: datetime | None = None) -> CacheLookup:
        now = now or utcnow()
        try:
            with self.factory() as session:
                row = session.scalar(
                    select(ToolCacheRow).where(
                        ToolCacheRow.key == key,
                        ToolCacheRow.namespace == namespace,
                        ToolCacheRow.expires_at > now,
                        ToolCacheRow.collected_at <= now,
                        ToolCacheRow.collected_at > now - timedelta(seconds=ttl),
                    )
                )
                if row:
                    return CacheLookup(
                        "hit",
                        CachedObservation(
                            row.data,
                            row.collected_at,
                            min(row.expires_at, row.collected_at + timedelta(seconds=ttl)),
                        ),
                    )
        except SQLAlchemyError:
            return CacheLookup("unavailable")
        return CacheLookup("miss")

    def put(self, namespace: str, key: str, data: dict, collected_at: datetime, ttl: int) -> bool:
        if not 1 <= ttl <= 3600 or len(canonical(data)) > MAX_CACHE_BYTES:
            return False
        try:
            # A single short capacity lock bounds concurrent insertions. No
            # network/provider work runs inside this transaction.
            with try_work_lock(self.factory, "tool-cache", "capacity") as acquired:
                if not acquired:
                    return False
                with self.factory.begin() as session:
                    prune_expired(session, ToolCacheRow, utcnow())
                    if session.get(ToolCacheRow, key) is None:
                        count = session.scalar(select(func.count(ToolCacheRow.key))) or 0
                        if count >= MAX_CACHE_ENTRIES:
                            return False
                    values = {
                        "namespace": namespace,
                        "data": data,
                        "collected_at": collected_at,
                        "expires_at": collected_at + timedelta(seconds=ttl),
                    }
                    session.execute(
                        insert(ToolCacheRow)
                        .values(key=key, **values)
                        .on_conflict_do_update(index_elements=[ToolCacheRow.key], set_=values)
                    )
            return True
        except SQLAlchemyError:
            return False
