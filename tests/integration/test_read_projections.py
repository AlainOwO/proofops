import pytest
from proofops.api.app import job_summary
from proofops.storage.analytics import review_analytics
from proofops.storage.database import JobRow, ReportRow
from proofops.storage.repository import create_job, review_summaries, store_bundle
from proofops.workers.runner import run_once
from sqlalchemy import event, select

pytestmark = pytest.mark.integration


def test_summary_projection_preserves_complete_and_pending_jobs(
    db, auth_settings, valid_bundle, trusted
):
    with db.begin() as session:
        bundle, _ = store_bundle(session, valid_bundle)
        for name in ("complete", "pending"):
            create_job(session, bundle, trusted, key=name, mode="replay", ai_preference="off")
    assert run_once(factory=db, settings=auth_settings)
    with db() as session:
        rows = session.execute(
            select(JobRow, ReportRow)
            .outerjoin(ReportRow, ReportRow.id == JobRow.id)
            .order_by(JobRow.created_at.desc(), JobRow.id.desc())
        ).all()
        expected = [job_summary(job, report) for job, report in rows]
        assert review_summaries(session, 100, 0) == expected
        assert review_summaries(session, 1, 1) == expected[1:2]
        assert review_summaries(session, 100, 2) == []
    loaded = []

    def capture(session, instance):
        if isinstance(instance, ReportRow):
            loaded.append(instance)

    event.listen(db, "loaded_as_persistent", capture)
    try:
        with db() as session:
            assert review_summaries(session, 100, 0) == expected
            stats = review_analytics(session)
    finally:
        event.remove(db, "loaded_as_persistent", capture)
    assert not loaded
    assert stats["review_count"] == 1
    completed = next(report for _, report in rows if report)
    assert stats["projected_comparisons"] == [
        {
            "review_id": completed.id,
            "origin": completed.core["origin"],
            "outcome": completed.outcome,
            "cost": completed.core["cost"],
            "evaluated_at": completed.core["evaluation_reference_time"],
        }
    ]
