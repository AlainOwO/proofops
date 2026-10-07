from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from proofops.config import APP_ROOT, get_settings
from proofops.domain.common import digest, utcnow
from proofops.storage import tool_cache
from proofops.storage.database import BundleRow, JobRow, ToolCacheRow
from proofops.storage.repository import create_job, store_bundle
from proofops.storage.tool_cache import ObservationCache
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.integration


def test_observation_cache_hit_scope_expiry_and_replacement(db):
    cache = ObservationCache(db)
    now, key = utcnow(), digest({"synthetic": "scope-a"})
    assert cache.get("aws", key, 60).state == "miss"
    assert cache.put("aws", key, {"count": 2}, now, 60)
    value = cache.get("aws", key, 60, now + timedelta(seconds=10))
    assert value.state == "hit" and value.observation.data == {"count": 2}
    assert value.observation.collected_at == now
    assert cache.get("search", key, 60).state == "miss"
    assert cache.get("aws", digest({"synthetic": "scope-b"}), 60).state == "miss"
    assert cache.get("aws", key, 5, now + timedelta(seconds=10)).state == "miss"
    assert cache.get("aws", key, 60, now - timedelta(seconds=1)).state == "miss"
    assert cache.get("aws", key, 60, now + timedelta(seconds=60)).state == "miss"
    assert cache.put("aws", key, {"count": 3}, now, 60)
    assert cache.get("aws", key, 60).observation.data == {"count": 3}


def test_cache_capacity_size_and_expired_cleanup_are_bounded(db, monkeypatch):
    cache, now = ObservationCache(db), utcnow()
    monkeypatch.setattr(tool_cache, "MAX_CACHE_ENTRIES", 2)
    assert cache.put("search", digest(1), {"value": 1}, now, 60)
    assert cache.put("aws", digest(2), {"value": 2}, now, 60)
    assert not cache.put("aws", digest(3), {"value": 3}, now, 60)
    assert not cache.put("aws", digest(4), {"value": "x" * 524_289}, now, 60)
    assert not cache.put("aws", digest(4), {}, now, 0)
    assert cache.put("aws", digest(2), {"value": 4}, now, 60)
    with db.begin() as session:
        session.get(ToolCacheRow, digest(1)).expires_at = now - timedelta(seconds=1)
    assert cache.put("aws", digest(3), {"value": 3}, now, 60)
    with db() as session:
        assert session.scalar(select(func.count(ToolCacheRow.key))) == 2
        assert session.get(ToolCacheRow, digest(1)) is None


def test_cache_storage_failure_is_explicit_and_has_no_payload_output(db):
    class Unavailable:
        def __call__(self):
            raise OperationalError(None, None, RuntimeError())

        begin = __call__

    cache = ObservationCache(Unavailable())
    assert cache.get("aws", digest(1), 60).state == "unavailable"
    assert not cache.put("aws", digest(1), {"private": "observation"}, utcnow(), 60)


def test_additive_migration_and_rollback_preserve_existing_jobs(
    db, valid_bundle, trusted, monkeypatch
):
    with db.begin() as session:
        bundle, _ = store_bundle(session, valid_bundle)
        job, _ = create_job(
            session, bundle, trusted, key="upgrade", mode="replay", ai_preference="off"
        )
        identity, bundle_id = job.id, bundle.id
        original = digest(bundle.data)
    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(APP_ROOT / "migrations"))
    monkeypatch.setenv("DATABASE_URL", db.kw["bind"].url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        command.downgrade(config, "f6a91d2e83b4")
        assert "tool_observation_cache" not in inspect(db.kw["bind"]).get_table_names()
        command.upgrade(config, "head")
        assert "tool_observation_cache" in inspect(db.kw["bind"]).get_table_names()
        indexes = {item["name"] for item in inspect(db.kw["bind"]).get_indexes("review_jobs")}
        assert "ix_job_created_id" in indexes
        with db() as session:
            assert session.get(JobRow, identity).requested_by == "host-operator"
            assert digest(session.get(BundleRow, bundle_id).data) == original
    finally:
        command.upgrade(config, "head")
        get_settings.cache_clear()
