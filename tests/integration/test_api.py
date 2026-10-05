from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.config import APP_ROOT
from proofops.storage.analytics import billing_analytics, ingest_costs
from proofops.storage.bundles import replay_export
from proofops.workers.runner import run_once

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db, auth_settings, login_user):
    settings = auth_settings
    with TestClient(create_app(settings, factory=db)) as client:
        login_user(client)
        yield client, settings


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("valid-resize", "request_review"),
        ("unsafe-resize", "revise_change"),
        ("incomplete-evidence", "collect_evidence"),
    ],
)
def test_api_worker_report_and_download(db, client, name, expected):
    api, settings = client
    assert api.get("/readyz").status_code == 200
    imported = api.post("/api/v1/bundles", json={"replay": name})
    assert imported.status_code == 201, imported.text
    body = {"bundle_id": imported.json()["bundle_id"], "mode": "replay", "ai_preference": "off"}
    headers = {"Idempotency-Key": "same-key"}
    queued = api.post("/api/v1/reviews", json=body, headers=headers)
    assert queued.status_code == 202, queued.text
    identifier = queued.json()["review_id"]
    assert api.post("/api/v1/reviews", json=body, headers=headers).json()["review_id"] == identifier
    assert (
        api.post(
            "/api/v1/reviews", json={**body, "ai_preference": "auto"}, headers=headers
        ).status_code
        == 409
    )
    before = api.get(f"/api/v1/reviews/{identifier}").json()
    assert before["report"] is None and before["job"]["state"] == "queued"
    assert run_once(factory=db, settings=settings) == identifier
    result = api.get(f"/api/v1/reviews/{identifier}").json()
    assert result["job"]["state"] == "completed", result
    assert result["report"]["outcome"] == expected
    assert result["explanation"]["status"] == "template"
    raw = api.get(f"/api/v1/reviews/{identifier}/bundle")
    assert raw.status_code == 200 and replay_export(raw.content)[1]
    changed = api.get(f"/api/v1/reviews/{identifier}", params={"candidate_commit": "c" * 40}).json()
    assert changed["applicability"]["candidate_changed"]
    assert not changed["applicability"]["deployment_approval"]


def test_origins_paths_validation_and_unknown_ids(client):
    api, _ = client
    assert (
        api.post("/api/v1/bundles", json={"replay": "../../data/evaluator_only"}).status_code == 422
    )
    assert (
        api.post(
            "/api/v1/bundles",
            json={"replay": "valid-resize"},
            headers={"Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )
    assert api.get(f"/api/v1/reviews/{uuid4()}").status_code == 404
    assert api.get("/api/v1/reviews/not-an-id").status_code == 422
    assert (
        api.post(
            "/api/v1/bundles", content="secret=do-not-echo", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )


def test_focus_ingestion_is_idempotent_and_reconciles(db):
    raw = (APP_ROOT / "fixtures/billing/focus_sample.csv").read_bytes()
    with db.begin() as session:
        first = ingest_costs(session, raw)
    with db.begin() as session:
        second = ingest_costs(session, raw)
        result = billing_analytics(session)
    assert first["created"] and not second["created"]
    assert result["totals"][0]["rows"] == 1000
    assert result["totals"][0]["negative_billed_rows"] == 13
    from decimal import Decimal

    assert Decimal(result["totals"][0]["billed"]) == Decimal("20.52022672899")
    assert Decimal(result["totals"][0]["effective"]) == Decimal("14.97651418586")


def test_guard_draft_validation_export_and_tamper_rejection(db, client):
    import io
    import json
    import zipfile

    from proofops.storage.database import GuardDraftRow

    api, settings = client
    imported = api.post("/api/v1/bundles", json={"replay": "unsafe-resize"}).json()
    queued = api.post(
        "/api/v1/reviews",
        json={"bundle_id": imported["bundle_id"]},
        headers={"Idempotency-Key": "guard-review"},
    ).json()
    review_id = queued["review_id"]
    run_once(factory=db, settings=settings)
    response = api.post(f"/api/v1/reviews/{review_id}/guard-drafts", json={"ai_preference": "off"})
    assert response.status_code == 201, response.text
    draft_id = response.json()["draft_id"]
    assert api.get(f"/api/v1/guard-drafts/{draft_id}/bundle").status_code == 409
    validated = api.post(f"/api/v1/guard-drafts/{draft_id}/validate")
    assert validated.status_code == 200, validated.text
    assert validated.json()["passed"] and not validated.json()["active"]
    exported = api.get(f"/api/v1/guard-drafts/{draft_id}/bundle")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert json.loads(archive.read("guard.json"))["minimum_task_memory_mib"] == 2048
        assert not json.loads(archive.read("manifest.json"))["active"]
    with db.begin() as session:
        draft = session.get(GuardDraftRow, draft_id)
        draft.spec = {**draft.spec, "minimum_task_memory_mib": 512}
    assert api.post(f"/api/v1/guard-drafts/{draft_id}/validate").status_code == 422
    assert api.get(f"/api/v1/guard-drafts/{draft_id}/bundle").status_code == 422


def test_billing_endpoint_and_mixed_currency_null_duplicate_rows(db, client):
    from decimal import Decimal

    api, _ = client
    assert api.post("/api/v1/billing/import-sample").json()["created"]
    assert not api.post("/api/v1/billing/import-sample").json()["created"]
    raw = b"ProviderName,ServiceName,BillingCurrency,BilledCost,EffectiveCost\nTest,CPU,EUR,1.25,\nTest,CPU,EUR,1.25,\nTest,CPU,EUR,-0.50,0\nTest,CPU,JPY,,\n"
    with db.begin() as session:
        result = ingest_costs(session, raw, "mixed-fixture")
        data = billing_analytics(session)
    assert result["rows"] == 4
    totals = {item["currency"]: item for item in data["totals"]}
    assert totals["EUR"]["rows"] == 3 and Decimal(totals["EUR"]["billed"]) == Decimal("2")
    assert totals["JPY"]["billed"] is None and totals["JPY"]["effective"] is None
    assert Decimal(totals["USD"]["billed"]) == Decimal("20.52022672899")
