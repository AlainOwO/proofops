"""Reset only the local application's saved reviews using the three supplied replays."""

from pathlib import Path

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from proofops.config import APP_ROOT, Settings, get_settings
from proofops.domain.common import digest, strict_json, utcnow
from proofops.domain.engine import review
from proofops.models.explanations import template_explanation
from proofops.policies.guards import load_trusted
from proofops.storage.artifacts import put_artifact
from proofops.storage.bundles import export_report, load_replay
from proofops.storage.database import (
    ArtifactRow,
    AttemptRow,
    AuditRow,
    BundleRow,
    ChangeRow,
    DemoReviewRow,
    EvidenceRow,
    GuardDraftRow,
    JobRow,
    OutcomeRow,
    ReportRow,
    WorkloadRow,
    session_factory,
)
from proofops.storage.repository import create_job, store_bundle

DEMO_REPLAYS = ("valid-resize", "unsafe-resize", "incomplete-evidence")
PROTECTED_DIRECTORIES = {"evaluation", "research", "evaluator", "evaluator_only"}


def _local_database(url: str | URL) -> None:
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.host not in {"127.0.0.1", "localhost", "::1", "db"}
        or parsed.database not in {"proofops", "proofops_test"}
        or parsed.query
    ):
        raise ValueError(
            "Demo reset requires the local proofops (or dedicated proofops_test) "
            "PostgreSQL database, without connection query overrides."
        )


def _demo_paths(artifact_dir: Path) -> None:
    root = artifact_dir.resolve()
    if not root.is_relative_to(APP_ROOT / "artifacts") or any(
        part.lower() in PROTECTED_DIRECTORIES for part in root.relative_to(APP_ROOT).parts
    ):
        raise ValueError("Demo exports must stay in application artifacts, outside protected data.")
    # Check before put_artifact can create a directory or follow an existing link.
    if (root / "exports").is_symlink():
        raise ValueError("Demo exports cannot use a symlink.")
    sources = [
        APP_ROOT / "policies/approved/reports-demo.json",
        APP_ROOT / "policies/templates/ecs_task_memory_floor.rego",
        *(APP_ROOT / "fixtures/replays" / name for name in DEMO_REPLAYS),
    ]
    if any(source.resolve() != source for source in sources):
        raise ValueError("Demo inputs must use the supplied application paths without symlinks.")


def reset_demo_data(
    *, settings: Settings | None = None, factory: sessionmaker[Session] | None = None
) -> dict:
    """Replace saved review data atomically; never clear files or accounting tables.

    This deliberately bypasses the model router and worker queue. The shared
    engine, recorded replay time, template explanation and export format are
    identical to an ordinary AI-off review. Files already on disk are preserved,
    including an export written before a later transaction failure.
    """
    settings = settings or get_settings()
    _local_database(settings.database_url)
    _demo_paths(settings.artifact_dir)
    trusted = load_trusted()
    bundles = [(name, load_replay(name)) for name in DEMO_REPLAYS]
    factory = factory or session_factory(settings.database_url)
    # Also check an injected factory's actual destination before connecting.
    _local_database(factory.kw["bind"].url)
    results = []
    try:
        with factory.begin() as session:
            # Explicit app tables only: no schema-wide TRUNCATE/CASCADE. Block
            # worker claims and concurrent edits for the duration of the reset.
            session.execute(
                text(
                    "LOCK TABLE review_jobs, review_reports, guard_drafts, outcomes, "
                    "artifact_manifests, evidence, workload_runs, bundles, change_sets "
                    "IN EXCLUSIVE MODE NOWAIT"
                )
            )
            if session.scalar(select(JobRow.id).where(JobRow.state == "running").limit(1)):
                raise RuntimeError("A review is running. Let it finish before resetting demo data.")
            deleted = session.scalar(select(func.count(JobRow.id)))
            # Keep all spend, reservations, ledgers and unrelated/evaluator
            # attempts. Only detach the FK for attempts belonging to old jobs.
            session.execute(
                update(AttemptRow)
                .where(AttemptRow.review_id.in_(select(JobRow.id)))
                .values(review_id=None)
            )
            for model in (
                DemoReviewRow,
                GuardDraftRow,
                OutcomeRow,
                ArtifactRow,
                ReportRow,
                JobRow,
                EvidenceRow,
                WorkloadRow,
                BundleRow,
                ChangeRow,
            ):
                session.execute(delete(model))
            for name, bundle in bundles:
                source, _ = store_bundle(session, bundle)
                job, _ = create_job(
                    session, source, trusted, key=f"demo:{name}", mode="replay", ai_preference="off"
                )
                report = review(bundle, trusted, review_id=job.id, mode="replay")
                explanation = template_explanation(report)
                archive = export_report(bundle, report, explanation, trusted)
                artifact_hash = put_artifact(settings.artifact_dir, archive)
                core_hash = digest(report)
                session.add(
                    ReportRow(
                        id=job.id,
                        scope=job.scope,
                        outcome=report.outcome.value,
                        core_hash=core_hash,
                        core=report.model_dump(mode="json"),
                        explanation=explanation,
                    )
                )
                session.flush()
                session.add(
                    ArtifactRow(
                        id=artifact_hash,
                        review_id=job.id,
                        manifest={"hash": artifact_hash, "bytes": len(archive), "sanitized": True},
                    )
                )
                session.flush()
                session.add(
                    DemoReviewRow(
                        review_id=job.id,
                        scenario=name,
                        core_hash=core_hash,
                        explanation_hash=digest(explanation),
                        artifact_id=artifact_hash,
                    )
                )
                session.add(
                    AuditRow(
                        scope=job.scope,
                        kind="review_completed",
                        data={
                            "review_id": job.id,
                            "outcome": report.outcome.value,
                            "core_hash": core_hash,
                        },
                    )
                )
                job.state, job.stage, job.updated_at = "completed", "completed", utcnow()
                results.append(
                    {"scenario": name, "review_id": job.id, "outcome": report.outcome.value}
                )
    except SQLAlchemyError as exc:
        # SQLAlchemy errors can include connection details and bound input data.
        raise RuntimeError(
            "Demo reset could not commit; saved reviews were preserved. "
            "Check the local database and migrations, and let active requests finish before retrying."
        ) from exc
    return {"deleted_reviews": deleted, "reviews": results}


def public_demo_reports(session):
    """Only explicitly seeded, unchanged fixture results can be served anonymously.

    An ordinary imported review cannot publish itself by claiming a synthetic
    origin. Existing billing, drafts, dispositions and model accounting stay private.
    """
    rows = session.execute(
        select(DemoReviewRow, JobRow, ReportRow)
        .join(JobRow, JobRow.id == DemoReviewRow.review_id)
        .join(ReportRow, ReportRow.id == DemoReviewRow.review_id)
        .order_by(JobRow.created_at.desc())
    ).all()
    visible = []
    for marker, job, report in rows:
        if marker.scenario not in DEMO_REPLAYS:
            continue
        manifest = strict_json(
            (APP_ROOT / "fixtures/replays" / marker.scenario / "manifest.json").read_bytes()
        )
        if (
            job.state == "completed"
            and job.mode == "replay"
            and job.ai_preference == "off"
            and report.core.get("origin") == "synthetic_fixture"
            and report.core.get("input_hashes") == manifest["files"]
            and report.explanation.get("status") == "template"
            and digest(report.core) == marker.core_hash
            and digest(report.explanation) == marker.explanation_hash
        ):
            visible.append((marker, job, report))
    return visible


def public_demo_analytics(session) -> dict:
    reports = [report for _, _, report in public_demo_reports(session)]
    counts = {
        outcome: sum(report.outcome == outcome for report in reports)
        for outcome in {report.outcome for report in reports}
    }
    return {
        "review_counts": counts,
        "review_count": len(reports),
        "projected_comparisons": [
            {
                "review_id": report.id,
                "origin": report.core["origin"],
                "outcome": report.outcome,
                "cost": report.core.get("cost"),
                "evaluated_at": report.core["evaluation_reference_time"],
            }
            for report in reports
        ],
        "observed_outcomes": [],
        "model": {
            "attempts": 0,
            "actual_usd": "0",
            "pending_reserved_usd": "0",
            "p50_seconds": None,
            "p95_seconds": None,
            "basis": "Seeded template results only; no model calls in the public demo.",
        },
        "billing": {
            "totals": [],
            "groups": [],
            "note": "Workspace billing is not part of the public demo.",
        },
        "bounds": "Only explicitly seeded synthetic reviews are public. Projections are separate alternatives, not realized savings.",
    }
