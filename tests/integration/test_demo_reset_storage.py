from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.cli import main
from proofops.config import APP_ROOT, Settings
from proofops.domain.common import digest, utcnow
from proofops.domain.engine import review
from proofops.models.explanations import template_explanation
from proofops.storage import demo
from proofops.storage.analytics import ingest_costs
from proofops.storage.bundles import load_replay, replay_export
from proofops.storage.database import (
    ArtifactRow,
    AttemptRow,
    AuditRow,
    BillingImportRow,
    BillingRow,
    BudgetRow,
    BundleRow,
    CacheRow,
    ContractRow,
    GuardDraftRow,
    GuardRevisionRow,
    JobRow,
    LedgerRow,
    OutcomeRow,
    ReportRow,
)
from proofops.storage.repository import create_job, store_bundle
from sqlalchemy import func, select, text

pytestmark = pytest.mark.integration


@pytest.fixture
def demo_settings(db, monkeypatch, auth_settings):
    settings = Settings(
        _env_file=None,
        database_url=db.kw["bind"].url.render_as_string(hide_password=False),
        artifact_dir=APP_ROOT / "artifacts/demo-reset-tests" / uuid4().hex,
        # Even a live preference in local configuration must never invoke a model.
        ai_mode="live",
        secret_key=auth_settings.secret_key,
        allowed_hosts=auth_settings.allowed_hosts,
        cors_origins=auth_settings.cors_origins,
        session_cookie_secure=False,
        proofops_admin_username="",
        proofops_admin_password="",
    )
    monkeypatch.setattr(demo, "get_settings", lambda: settings)
    monkeypatch.setattr(demo, "session_factory", lambda _: db)
    monkeypatch.setattr(
        "proofops.models.router.ModelRouter.explain",
        Mock(side_effect=AssertionError("reset must not use the model router")),
    )
    return settings


def snapshot(session, model):
    table = model.__table__
    return [
        dict(row) for row in session.execute(select(table).order_by(*table.primary_key)).mappings()
    ]


def test_reset_cleans_linked_data_and_preserves_accounting_and_files(
    db, demo_settings, trusted, monkeypatch, capsys
):
    first = demo.reset_demo_data()
    old_ids = [item["review_id"] for item in first["reviews"]]
    review_id = old_ids[0]
    protected = (
        BudgetRow,
        LedgerRow,
        CacheRow,
        BillingImportRow,
        BillingRow,
        ContractRow,
        GuardRevisionRow,
    )
    with db.begin() as session:
        scope = session.get(JobRow, review_id).scope
        session.add(GuardDraftRow(review_id=review_id, spec={"fixture": True}))
        session.add(OutcomeRow(review_id=review_id, scope=scope, data={"fixture": True}))
        session.add(BudgetRow(id="preserved", limit=10, reserved=2, spent=3))
        session.flush()
        for key, linked_id in (("linked-attempt", review_id), ("unrelated-attempt", None)):
            session.add(
                AttemptRow(
                    id=key,
                    task_key=key,
                    budget_id="preserved",
                    review_id=linked_id,
                    provider="fixture",
                    model="fixture",
                    input_hash="a" * 64,
                    state="uncertain",
                    reserved_cost=Decimal("1"),
                    metadata_json={"fixture": True},
                )
            )
            session.flush()
            session.add(LedgerRow(attempt_id=key, event="reserved", amount=Decimal("1")))
        session.add(CacheRow(key="b" * 64, scope=scope, data={"keep": True}, expires_at=utcnow()))
        ingest_costs(
            session,
            b"ProviderName,ServiceName,BillingCurrency,BilledCost,EffectiveCost\nFixture,CPU,USD,1,1\n",
            "keep-billing",
        )
        # Saved failed and queued jobs must also disappear.
        bundle, _ = store_bundle(session, load_replay("valid-resize"))
        for state in ("failed", "queued"):
            job, _ = create_job(
                session, bundle, trusted, key=state, mode="replay", ai_preference="off"
            )
            job.state = state
    with db() as session:
        before = {model: snapshot(session, model) for model in protected}
        attempts_before = snapshot(session, AttemptRow)
        audits_before = snapshot(session, AuditRow)

    # These are test-owned sentinels, never the real evaluation/research files.
    sentinels = []
    for name in ("evaluation", "research", "evaluator", "evaluator_only", "workload"):
        sentinel = demo_settings.artifact_dir / name / "keep.txt"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("preserve test-owned data")
        sentinels.append(sentinel)
    old_exports = {path: path.read_bytes() for path in demo_settings.artifact_dir.glob("exports/*")}
    original_open = Path.open

    def protected_open(path, *args, **kwargs):
        assert not demo.PROTECTED_DIRECTORIES.intersection(path.parts)
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "open", protected_open)
        assert main(["reset-demo-data", "--yes"]) == 0
    assert "Removed 5 saved reviews" in capsys.readouterr().out
    assert all(path.read_text() == "preserve test-owned data" for path in sentinels)
    assert all(path.read_bytes() == raw for path, raw in old_exports.items())
    with db() as session:
        assert {model: snapshot(session, model) for model in protected} == before
        assert session.scalar(select(func.count(JobRow.id))) == 3
        assert session.scalar(select(func.count(ReportRow.id))) == 3
        assert session.scalar(select(func.count(BundleRow.id))) == 3
        assert session.scalar(select(func.count(ArtifactRow.id))) == 3
        assert session.scalar(select(func.count(GuardDraftRow.id))) == 0
        assert session.scalar(select(func.count(OutcomeRow.id))) == 0
        assert not session.scalars(select(JobRow.id).where(JobRow.id.in_(old_ids))).all()
        attempts_after = snapshot(session, AttemptRow)
        assert attempts_after == [{**row, "review_id": None} for row in attempts_before]
        audits_after = snapshot(session, AuditRow)
        assert all(row in audits_after for row in audits_before)


def test_seeded_reports_are_exact_engine_results_downloadable_and_repeatable(
    db, demo_settings, trusted, login_user
):
    previous_ids = set()
    with TestClient(create_app(demo_settings, factory=db)) as api:
        login_user(api)
        for deleted in (0, 3):
            result = demo.reset_demo_data()
            assert result["deleted_reviews"] == deleted
            assert [(item["scenario"], item["outcome"]) for item in result["reviews"]] == [
                ("valid-resize", "request_review"),
                ("unsafe-resize", "revise_change"),
                ("incomplete-evidence", "collect_evidence"),
            ]
            listing = api.get("/api/v1/reviews").json()
            assert listing["total"] == len(listing["items"]) == 3
            ids = {item["review_id"] for item in result["reviews"]}
            assert not ids.intersection(previous_ids)
            previous_ids = ids
            for item in result["reviews"]:
                identifier = item["review_id"]
                bundle = load_replay(item["scenario"])
                expected = review(bundle, trusted, review_id=identifier, mode="replay")
                response = api.get(f"/api/v1/reviews/{identifier}").json()
                assert response["job"]["state"] == "completed"
                assert response["report"] == expected.model_dump(mode="json")
                assert response["explanation"] == template_explanation(expected)
                assert response["report"]["evaluation_reference_time"] == (
                    bundle.reference_time.isoformat().replace("+00:00", "Z")
                )
                assert response["guard_drafts"] == []
                assert not response["applicability"]["deployment_approval"]
                archive = api.get(f"/api/v1/reviews/{identifier}/bundle")
                assert archive.status_code == 200
                replayed, matches = replay_export(archive.content)
                assert matches and replayed == expected
                with db() as session:
                    job = session.get(JobRow, identifier)
                    assert (job.mode, job.ai_preference) == ("replay", "off")
                    assert session.get(ReportRow, identifier).core_hash == digest(expected)


def test_export_failure_rolls_back_deleted_reviews_and_partial_seeds(
    db, demo_settings, monkeypatch, capsys
):
    demo.reset_demo_data()
    with db() as session:
        before = {
            model: snapshot(session, model)
            for model in (JobRow, ReportRow, ArtifactRow, BundleRow, AuditRow)
        }
    put = demo.put_artifact
    calls = 0

    def fail_second_export(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("test export failure")
        return put(*args)

    monkeypatch.setattr(demo, "put_artifact", fail_second_export)
    assert main(["reset-demo-data", "--yes"]) == 1
    assert calls == 2
    assert "test export failure" in capsys.readouterr().out
    with db() as session:
        assert {model: snapshot(session, model) for model in before} == before


def test_bad_fixture_preserves_saved_reviews(db, demo_settings, monkeypatch):
    demo.reset_demo_data()
    with db() as session:
        before = snapshot(session, JobRow)
    load = demo.load_replay

    def fail_third_fixture(name):
        if name == "incomplete-evidence":
            raise ValueError("test fixture failure")
        return load(name)

    monkeypatch.setattr(demo, "load_replay", fail_third_fixture)
    with pytest.raises(ValueError, match="test fixture failure"):
        demo.reset_demo_data()
    with db() as session:
        assert snapshot(session, JobRow) == before


def test_running_job_blocks_reset_without_changes(db, demo_settings):
    first = demo.reset_demo_data()
    with db.begin() as session:
        session.get(JobRow, first["reviews"][0]["review_id"]).state = "running"
    with db() as session:
        before = snapshot(session, JobRow)
    with pytest.raises(RuntimeError, match="A review is running"):
        demo.reset_demo_data()
    with db() as session:
        assert snapshot(session, JobRow) == before


def test_concurrent_edits_block_reset_without_leaking_database_errors(db, demo_settings, capsys):
    demo.reset_demo_data()
    with db.begin() as session:
        before = snapshot(session, JobRow)
        session.execute(text("LOCK TABLE review_jobs IN ROW EXCLUSIVE MODE"))
        assert main(["reset-demo-data", "--yes"]) == 1
        output = capsys.readouterr().out
        assert "saved reviews were preserved" in output
        assert "psycopg" not in output and "LOCK TABLE" not in output
        assert snapshot(session, JobRow) == before


def test_symlinked_export_directory_is_rejected_without_writes(demo_settings):
    target = demo_settings.artifact_dir / "research"
    target.mkdir(parents=True)
    (demo_settings.artifact_dir / "exports").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot use a symlink"):
        demo.reset_demo_data()
    assert list(target.iterdir()) == []
