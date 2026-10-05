import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.storage.database import DemoReviewRow, ReportRow
from proofops.storage.demo import reset_demo_data
from proofops.workers.runner import run_once
from sqlalchemy import delete, select

pytestmark = pytest.mark.integration


@pytest.fixture
def public_workspace(db, auth_settings, login_user):
    seeded = reset_demo_data(settings=auth_settings, factory=db)
    seed_id = seeded["reviews"][0]["review_id"]
    with TestClient(create_app(auth_settings, factory=db)) as admin:
        login_user(admin)
        imported = admin.post("/api/v1/bundles", json={"replay": "valid-resize"}).json()
        queued = admin.post(
            "/api/v1/reviews",
            json={"bundle_id": imported["bundle_id"]},
            headers={"Idempotency-Key": "private-review"},
        ).json()
        private_id = queued["review_id"]
        assert run_once(factory=db, settings=auth_settings) == private_id
        assert admin.post("/api/v1/billing/import-sample").status_code == 201
        draft = admin.post(
            f"/api/v1/reviews/{seed_id}/guard-drafts", json={"ai_preference": "off"}
        ).json()
        assert admin.get("/api/v1/reviews").json()["total"] == 4
        demo_settings = auth_settings.model_copy(update={"proofops_public_demo": True})
        with TestClient(create_app(demo_settings, factory=db)) as demo:
            yield admin, demo, seed_id, private_id, draft["draft_id"]


@pytest.mark.parametrize("identity", ["anonymous", "viewer", "admin"])
def test_demo_only_serves_seeded_results_even_with_a_real_session(
    public_workspace, login_user, identity
):
    admin, demo, seed_id, private_id, draft_id = public_workspace
    if identity != "anonymous":
        login_user(admin, identity)
        demo.cookies.update(admin.cookies)
    session = demo.get("/api/v1/auth/session").json()
    assert session["role"] == "viewer" and session["public_demo"] and session["username"] is None
    listing = demo.get("/api/v1/reviews").json()
    assert listing["total"] == len(listing["items"]) == 3
    assert private_id not in {item["id"] for item in listing["items"]}
    assert demo.get(f"/api/v1/reviews/{seed_id}").json()["guard_drafts"] == []
    assert demo.get(f"/api/v1/reviews/{seed_id}/bundle").status_code == 200
    assert demo.get(f"/api/v1/reviews/{private_id}").status_code == 404
    assert demo.get(f"/api/v1/reviews/{private_id}/bundle").status_code == 404
    assert demo.get(f"/api/v1/guard-drafts/{draft_id}/bundle").status_code == 403
    assert demo.get("/docs").status_code == 403
    stats = demo.get("/api/v1/analytics").json()
    assert stats["review_count"] == 3 and len(stats["projected_comparisons"]) == 3
    assert stats["billing"]["totals"] == [] and stats["observed_outcomes"] == []
    assert stats["model"]["attempts"] == 0


@pytest.mark.parametrize("identity", ["anonymous", "viewer", "admin"])
@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/bundles"),
        ("POST", "/api/v1/reviews"),
        ("POST", "/api/v1/reviews/{seed_id}/guard-drafts"),
        ("POST", "/api/v1/guard-drafts/{draft_id}/validate"),
        ("POST", "/api/v1/reviews/{seed_id}/outcomes"),
        ("POST", "/api/v1/billing/import-sample"),
        ("POST", "/api/v1/admin/reset-demo-data"),
        ("PUT", "/api/v1/future-write"),
        ("PATCH", "/api/v1/reviews"),
        ("DELETE", "/api/v1/reviews"),
    ],
)
def test_demo_rejects_every_write_for_every_identity(
    public_workspace, login_user, identity, method, path
):
    admin, demo, seed_id, _, draft_id = public_workspace
    if identity != "anonymous":
        login_user(admin, identity)
        demo.cookies.update(admin.cookies)
        demo.headers["X-CSRF-Token"] = admin.headers["X-CSRF-Token"]
    response = demo.request(method, path.format(seed_id=seed_id, draft_id=draft_id), json={})
    assert response.status_code == 403 and response.json() == {
        "detail": "Public demo is read-only."
    }
    assert demo.get("/api/v1/reviews").json()["total"] == 3


def test_unmarked_or_modified_results_fail_closed(public_workspace, db):
    _, demo, seed_id, _, _ = public_workspace
    with db.begin() as session:
        row = session.get(ReportRow, seed_id)
        row.explanation = {**row.explanation, "summary": "private fixture annotation"}
    assert demo.get(f"/api/v1/reviews/{seed_id}").status_code == 404
    assert demo.get(f"/api/v1/reviews/{seed_id}/bundle").status_code == 404
    assert demo.get("/api/v1/reviews").json()["total"] == 2
    with db.begin() as session:
        session.execute(delete(DemoReviewRow))
        assert len(session.scalars(select(ReportRow)).all()) == 4
    assert demo.get("/api/v1/reviews").json()["total"] == 0
    assert demo.get("/api/v1/analytics").json()["review_count"] == 0
