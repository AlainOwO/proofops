from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert

from proofops.domain.common import digest, utcnow
from proofops.domain.schemas import ReviewInput
from proofops.policies.guards import TrustedRevision
from proofops.storage.database import (
    AuditRow,
    BundleRow,
    ChangeRow,
    ContractRow,
    EvidenceRow,
    GuardRevisionRow,
    JobRow,
    WorkloadRow,
    identifier,
)


class IdempotencyConflict(ValueError):
    pass


def store_trusted(session, trusted: TrustedRevision) -> None:
    contract_id = digest(trusted.contract)
    session.execute(
        insert(ContractRow)
        .values(
            id=contract_id,
            scope=digest(trusted.contract.scope),
            data=trusted.contract.model_dump(mode="json"),
        )
        .on_conflict_do_nothing(index_elements=[ContractRow.id])
    )
    session.execute(
        insert(GuardRevisionRow)
        .values(
            id=trusted.revision_hash, contract_id=contract_id, data=trusted.model_dump(mode="json")
        )
        .on_conflict_do_nothing(index_elements=[GuardRevisionRow.id])
    )


def store_bundle(session, bundle: ReviewInput) -> tuple[BundleRow, bool]:
    scope = digest(bundle.change.service_map.scope)
    contract_id, change_id = digest(bundle.contract), digest(bundle.change)
    session.execute(
        insert(ContractRow)
        .values(id=contract_id, scope=scope, data=bundle.contract.model_dump(mode="json"))
        .on_conflict_do_nothing(index_elements=[ContractRow.id])
    )
    session.execute(
        insert(ChangeRow)
        .values(id=change_id, scope=scope, data=bundle.change.model_dump(mode="json"))
        .on_conflict_do_nothing(index_elements=[ChangeRow.id])
    )
    content_hash = digest(bundle)
    bundle_id = identifier()
    added = session.execute(
        insert(BundleRow)
        .values(
            id=bundle_id,
            scope=scope,
            content_hash=content_hash,
            contract_id=contract_id,
            change_id=change_id,
            origin=bundle.origin.value,
            data=bundle.model_dump(mode="json"),
        )
        .on_conflict_do_nothing(index_elements=[BundleRow.content_hash])
        .returning(BundleRow.id)
    ).scalar_one_or_none()
    if not added:
        return session.execute(
            select(BundleRow).where(BundleRow.content_hash == content_hash)
        ).scalar_one(), False
    for evidence in bundle.evidence:
        session.add(
            EvidenceRow(
                id=digest({"bundle": bundle_id, "evidence": evidence}),
                bundle_id=bundle_id,
                scope=scope,
                data=evidence.model_dump(mode="json"),
            )
        )
    for run in bundle.workload_runs:
        session.add(
            WorkloadRow(
                id=digest({"bundle": bundle_id, "run": run}),
                bundle_id=bundle_id,
                scope=scope,
                data=run.model_dump(mode="json"),
            )
        )
    session.add(
        AuditRow(
            scope=scope,
            kind="bundle_imported",
            data={
                "bundle_id": bundle_id,
                "content_hash": content_hash,
                "origin": bundle.origin.value,
            },
        )
    )
    row = session.get(BundleRow, bundle_id)
    assert row is not None
    return row, True


def create_job(
    session, bundle: BundleRow, trusted: TrustedRevision, *, key: str, mode: str, ai_preference: str
) -> tuple[JobRow, bool]:
    store_trusted(session, trusted)
    request_hash = digest(
        {
            "bundle_id": bundle.id,
            "mode": mode,
            "ai_preference": ai_preference,
            "trusted_revision": trusted.revision_hash,
        }
    )
    job_id = identifier()
    added = session.execute(
        insert(JobRow)
        .values(
            id=job_id,
            bundle_id=bundle.id,
            scope=bundle.scope,
            trusted_revision_hash=trusted.revision_hash,
            idempotency_key=key,
            request_hash=request_hash,
            mode=mode,
            ai_preference=ai_preference,
        )
        .on_conflict_do_nothing(constraint="uq_review_idempotency")
        .returning(JobRow.id)
    ).scalar_one_or_none()
    row = session.execute(
        select(JobRow).where(JobRow.scope == bundle.scope, JobRow.idempotency_key == key)
    ).scalar_one()
    if row.request_hash != request_hash:
        raise IdempotencyConflict("Idempotency-Key is already bound to a different request")
    if added:
        session.add(
            AuditRow(
                scope=bundle.scope,
                kind="review_queued",
                data={"review_id": job_id, "trusted_revision_hash": trusted.revision_hash},
            )
        )
    return row, bool(added)


def claim_job(factory, owner: str, lease_seconds: int = 120) -> str | None:
    now = utcnow()
    with factory.begin() as session:
        job = session.execute(
            select(JobRow)
            .where(
                or_(
                    JobRow.state == "queued",
                    (JobRow.state == "running") & (JobRow.lease_until < now),
                )
            )
            .order_by(JobRow.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if not job:
            return None
        if job.claimed_count >= 3:
            job.state, job.error_code = "failed", "JOB_RECOVERY_LIMIT"
            job.lease_until = None
            return None
        job.state, job.owner, job.stage = "running", owner, "normalize_and_review"
        job.claimed_count += 1
        job.lease_until = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at, job.updated_at = now, now
        return job.id


def heartbeat(factory, job_id: str, owner: str, stage: str, lease_seconds: int) -> bool:
    now = utcnow()
    with factory.begin() as session:
        result = session.execute(
            update(JobRow)
            .where(JobRow.id == job_id, JobRow.owner == owner, JobRow.state == "running")
            .values(
                heartbeat_at=now,
                lease_until=now + timedelta(seconds=lease_seconds),
                updated_at=now,
                stage=stage,
            )
        )
        return result.rowcount == 1
