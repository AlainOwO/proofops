from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from proofops.domain.common import utcnow
from proofops.storage.database import AuditRow, JobRow, ReportRow
from proofops.storage.repository import claim_job, create_job, store_bundle
from proofops.workers import runner
from sqlalchemy import select

pytestmark = pytest.mark.integration


def queue(db, bundle, trusted, name):
    with db.begin() as session:
        stored, _ = store_bundle(session, bundle)
        job, created = create_job(
            session, stored, trusted, key=name, mode="replay", ai_preference="off"
        )
        return job.id, created


def test_four_worker_slots_claim_each_job_once(db, auth_settings, valid_bundle, trusted):
    ids = {queue(db, valid_bundle, trusted, str(index))[0] for index in range(8)}
    assert not queue(db, valid_bundle, trusted, "0")[1]
    with ThreadPoolExecutor(max_workers=4) as pool:
        handled = list(
            pool.map(lambda _: runner.run_once(factory=db, settings=auth_settings), range(8))
        )
    assert set(handled) == ids
    with db() as session:
        assert all(
            job.state == "completed" and job.claimed_count == 1
            for job in session.scalars(select(JobRow))
        )
        assert len(session.scalars(select(ReportRow)).all()) == 8


@pytest.mark.parametrize("stage", ["review", "export_report"])
def test_deadline_prevents_late_result_or_artifact_persistence(
    db, auth_settings, valid_bundle, trusted, monkeypatch, stage
):
    identity, _ = queue(db, valid_bundle, trusted, "long-running")
    clock = [0.0]
    auth_settings.job_timeout_seconds = 30
    monkeypatch.setattr(runner, "monotonic", lambda: clock[0])
    original = getattr(runner, stage)
    artifacts = []

    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] += 31
        return result

    monkeypatch.setattr(runner, stage, slow)
    monkeypatch.setattr(runner, "put_artifact", lambda *args: artifacts.append(args))
    assert runner.run_once(factory=db, settings=auth_settings) == identity
    with db() as session:
        job = session.get(JobRow, identity)
        assert job.state == job.stage == "failed" and job.error_code == "JOB_TIMEOUT"
        assert session.get(ReportRow, identity) is None
        failures = session.scalars(select(AuditRow).where(AuditRow.kind == "review_failed")).all()
        assert len(failures) == 1 and failures[0].data["status"] == "JOB_TIMEOUT"
    assert not artifacts


def test_exhausted_lease_recovery_has_terminal_state_timestamp_and_audit(db, valid_bundle, trusted):
    identity, _ = queue(db, valid_bundle, trusted, "recover")
    for index in range(3):
        assert claim_job(db, f"owner-{index}") == identity
        with db.begin() as session:
            session.get(JobRow, identity).lease_until = utcnow() - timedelta(seconds=1)
    before = utcnow()
    assert claim_job(db, "fourth-owner") is None
    with db() as session:
        job = session.get(JobRow, identity)
        assert job.state == job.stage == "failed" and job.claimed_count == 3
        assert job.error_code == "JOB_RECOVERY_LIMIT" and job.updated_at >= before
        failures = session.scalars(select(AuditRow).where(AuditRow.kind == "review_failed")).all()
        assert len(failures) == 1 and failures[0].data["status"] == "JOB_RECOVERY_LIMIT"
