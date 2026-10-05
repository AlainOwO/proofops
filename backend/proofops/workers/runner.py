import argparse
import logging
import threading
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import select

from proofops.config import Settings, get_settings
from proofops.domain.common import digest, utcnow
from proofops.domain.engine import review
from proofops.domain.schemas import ReviewInput
from proofops.models.router import ModelRouter
from proofops.policies.guards import TrustedRevision
from proofops.storage.artifacts import put_artifact
from proofops.storage.bundles import export_report
from proofops.storage.database import (
    ArtifactRow,
    AuditRow,
    BundleRow,
    GuardRevisionRow,
    JobRow,
    ReportRow,
    session_factory,
)
from proofops.storage.repository import claim_job, heartbeat

logger = logging.getLogger(__name__)


def run_once(
    *, factory=None, settings: Settings | None = None, router: ModelRouter | None = None
) -> str | None:
    settings = settings or get_settings()
    if settings.proofops_public_demo:
        return None
    factory = factory or session_factory(settings.database_url)
    owner = str(uuid4())
    job_id = claim_job(factory, owner, settings.job_lease_seconds)
    if not job_id:
        return None
    stop = threading.Event()
    stage = ["normalize_and_review"]
    deadline = monotonic() + settings.job_timeout_seconds

    def check_deadline():
        if monotonic() >= deadline:
            raise TimeoutError("job stage deadline exceeded")

    def maintain_lease():
        while not stop.wait(settings.job_lease_seconds / 3):
            if monotonic() >= deadline:
                logger.error("Worker deadline exceeded; lease will expire for recovery")
                return
            try:
                if not heartbeat(factory, job_id, owner, stage[0], settings.job_lease_seconds):
                    return
            except Exception:
                logger.error("Worker lease renewal failed")
                return

    thread = threading.Thread(target=maintain_lease, daemon=True)
    thread.start()
    try:
        with factory() as session:
            job = session.get(JobRow, job_id)
            if job is None:
                return job_id
            source = session.get(BundleRow, job.bundle_id)
            revision = session.get(GuardRevisionRow, job.trusted_revision_hash)
            if source is None or revision is None:
                raise ValueError("persisted job dependencies are missing")
            bundle = ReviewInput.model_validate(source.data)
            trusted = TrustedRevision.model_validate(revision.data)
            mode, preference, scope = job.mode, job.ai_preference, job.scope
        if mode not in {"replay", "live"}:
            raise ValueError("invalid persisted execution mode")
        report = review(bundle, trusted, review_id=job_id, mode=mode)
        check_deadline()
        stage[0] = "explain"
        if not heartbeat(factory, job_id, owner, stage[0], settings.job_lease_seconds):
            return job_id
        router = router or ModelRouter(settings, factory=factory)
        explanation = router.explain(
            report, ai_preference=preference, task_id=job_id, review_id=job_id
        )
        check_deadline()
        stage[0] = "persist_report"
        if not heartbeat(factory, job_id, owner, stage[0], settings.job_lease_seconds):
            return job_id
        archive = export_report(bundle, report, explanation, trusted)
        artifact_hash = put_artifact(settings.artifact_dir, archive)
        with factory.begin() as session:
            job = session.execute(
                select(JobRow).where(JobRow.id == job_id).with_for_update()
            ).scalar_one()
            if job.owner != owner or job.state != "running":
                return job_id
            if session.get(ReportRow, job_id) is None:
                session.add(
                    ReportRow(
                        id=job_id,
                        scope=scope,
                        outcome=report.outcome.value,
                        core_hash=digest(report),
                        core=report.model_dump(mode="json"),
                        explanation=explanation,
                    )
                )
                session.flush()
                session.add(
                    ArtifactRow(
                        id=artifact_hash,
                        review_id=job_id,
                        manifest={"hash": artifact_hash, "bytes": len(archive), "sanitized": True},
                    )
                )
                session.add(
                    AuditRow(
                        scope=scope,
                        kind="review_completed",
                        actor=job.requested_by,
                        data={
                            "review_id": job_id,
                            "outcome": report.outcome.value,
                            "core_hash": digest(report),
                        },
                    )
                )
            job.state, job.stage, job.updated_at, job.lease_until = (
                "completed",
                "completed",
                utcnow(),
                None,
            )
    except Exception as exc:
        # Unexpected failures are job errors, never a fabricated successful review.
        # Provider exception bodies, raw plans and secrets are deliberately absent.
        logger.error("Review job failed (%s)", type(exc).__name__)
        with factory.begin() as session:
            job = session.execute(
                select(JobRow).where(JobRow.id == job_id).with_for_update()
            ).scalar_one()
            if job.owner == owner and job.state == "running":
                job.state, job.stage, job.error_code = "failed", "failed", "REVIEW_EXECUTION_FAILED"
                job.lease_until, job.updated_at = None, utcnow()
                session.add(
                    AuditRow(
                        scope=job.scope,
                        kind="review_failed",
                        actor=job.requested_by,
                        data={"review_id": job.id, "status": "REVIEW_EXECUTION_FAILED"},
                    )
                )
    finally:
        stop.set()
        thread.join(timeout=1)
    return job_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if settings.proofops_mode == "hosted":
        from proofops.storage.roles import assert_runtime_role

        assert_runtime_role(session_factory(settings.database_url))
    while True:
        try:
            handled = run_once()
        except Exception as exc:
            logger.error(
                "Worker unavailable (%s); retrying bounded local queue polling", type(exc).__name__
            )
            handled = None
        if args.once:
            return
        if handled is None:
            sleep(0.5)


if __name__ == "__main__":
    main()
