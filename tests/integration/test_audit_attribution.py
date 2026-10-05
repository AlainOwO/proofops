import json
import secrets

import pytest
from fastapi.testclient import TestClient
from proofops.api.app import create_app
from proofops.auth import AuthService, create_user, update_user
from proofops.storage.database import AuditRow, AuthSessionRow, JobRow, UserRow
from proofops.workers.runner import run_once
from sqlalchemy import select

pytestmark = pytest.mark.integration


def audit_events(db, *kinds):
    with db() as session:
        query = select(AuditRow).order_by(AuditRow.created_at)
        if kinds:
            query = query.where(AuditRow.kind.in_(kinds))
        return session.scalars(query).all()


def test_http_import_review_billing_and_reset_keep_the_authenticated_actor(
    db, auth_settings, login_user
):
    with TestClient(create_app(auth_settings, factory=db)) as api:
        username, _, _ = login_user(api)
        with db() as session:
            user_id = session.scalar(select(UserRow.id).where(UserRow.username == username))
        imported = api.post("/api/v1/bundles", json={"replay": "valid-resize"})
        assert imported.status_code == 201
        bundle_id = imported.json()["bundle_id"]
        queued = api.post(
            "/api/v1/reviews",
            json={"bundle_id": bundle_id},
            headers={"Idempotency-Key": "audit-review"},
        )
        assert queued.status_code == 202
        review_id = queued.json()["review_id"]
        assert run_once(factory=db, settings=auth_settings) == review_id
        billing = api.post("/api/v1/billing/import-sample")
        assert billing.status_code == 201
        assert api.post("/api/v1/billing/import-sample").json()["created"] is False
        kinds = {"bundle_imported", "review_queued", "review_completed", "billing_imported"}
        events = audit_events(db, *kinds)
        assert {event.kind for event in events} == kinds
        assert all(event.actor == user_id for event in events)
        assert {event.data["status"] for event in events if event.kind == "billing_imported"} == {
            "created",
            "existing",
        }
        with db() as session:
            assert session.get(JobRow, review_id).requested_by == user_id
        reset = api.post("/api/v1/admin/reset-demo-data", json={"confirm": True})
        assert reset.status_code == 200
        resets = audit_events(db, "demo_data_reset")
        assert len(resets) == 1 and resets[0].actor == user_id
        assert set(resets[0].data["review_ids"]) == {
            row["review_id"] for row in reset.json()["reviews"]
        }
        # Reset preserves old attribution and stamps all seeded import/job/completion events.
        assert all(event.actor == user_id for event in audit_events(db, *kinds, "demo_data_reset"))


def test_idempotent_resubmission_does_not_replace_the_original_job_actor(
    db, auth_settings, login_user
):
    with TestClient(create_app(auth_settings, factory=db)) as api:
        first_username, _, _ = login_user(api)
        bundle = api.post("/api/v1/bundles", json={"replay": "valid-resize"}).json()
        request = {"bundle_id": bundle["bundle_id"]}
        headers = {"Idempotency-Key": "shared-idempotency-key"}
        first = api.post("/api/v1/reviews", json=request, headers=headers).json()
        login_user(api)
        duplicate = api.post("/api/v1/reviews", json=request, headers=headers).json()
        assert duplicate["review_id"] == first["review_id"] and duplicate["created"] is False
        assert run_once(factory=db, settings=auth_settings) == first["review_id"]
        with db() as session:
            first_id = session.scalar(select(UserRow.id).where(UserRow.username == first_username))
            assert session.get(JobRow, first["review_id"]).requested_by == first_id
        assert all(
            event.actor == first_id
            for event in audit_events(db, "review_queued", "review_completed")
        )


def test_failed_review_retains_the_submitter(db, auth_settings, login_user, monkeypatch):
    with TestClient(create_app(auth_settings, factory=db)) as api:
        login_user(api)
        bundle = api.post("/api/v1/bundles", json={"replay": "valid-resize"}).json()
        queued = api.post(
            "/api/v1/reviews",
            json={"bundle_id": bundle["bundle_id"]},
            headers={"Idempotency-Key": "failed-audit"},
        ).json()

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("proofops.workers.runner.review", fail)
    assert run_once(factory=db, settings=auth_settings) == queued["review_id"]
    queued_event = audit_events(db, "review_queued")[0]
    failed = audit_events(db, "review_failed")
    assert len(failed) == 1 and failed[0].actor == queued_event.actor
    assert failed[0].data == {"review_id": queued["review_id"], "status": "REVIEW_EXECUTION_FAILED"}


def test_authentication_and_account_audits_contain_only_ids_and_status(db, auth_settings, capsys):
    password, wrong, replacement = (secrets.token_urlsafe(32) for _ in range(3))
    username = "audit-synthetic-user"
    user = create_user(db, username, password, "admin")
    auth = AuthService(auth_settings, db)
    auth.initialize()
    assert auth.login(username, wrong, "synthetic-peer") == (None, False)
    assert auth.login("unknown-synthetic-user", wrong, "synthetic-peer") == (None, False)
    token, limited = auth.login(username, password, "synthetic-peer")
    assert token and not limited
    auth.logout(token, actor=user.id)
    update_user(db, username, password=replacement)
    update_user(db, username, disable=True)
    events = audit_events(db)
    assert {event.kind for event in events} == {
        "account_created",
        "login_failed",
        "login_succeeded",
        "logout",
        "account_password_changed",
        "account_disabled",
    }
    assert all(set(event.data) == {"user_id", "status"} for event in events)
    assert all(event.data["user_id"] in {None, user.id} for event in events)
    for event in events:
        expected = (
            user.id
            if event.kind in {"login_succeeded", "logout"}
            else ("anonymous" if event.kind == "login_failed" else "host-operator")
        )
        assert event.actor == expected
    serialized = json.dumps(
        [{"kind": event.kind, "actor": event.actor, "data": event.data} for event in events]
    )
    output = capsys.readouterr()
    for secret in (
        password,
        wrong,
        replacement,
        token,
        user.password_hash,
        username,
        "synthetic-peer",
    ):
        assert bool(secret in serialized or secret in output.out or secret in output.err) is False
    with db() as session:
        assert session.scalar(select(AuthSessionRow)) is None


def test_rate_limited_logins_are_audited_without_account_identifiers(db, auth_settings):
    auth_settings.login_max_ip_attempts = 10
    auth = AuthService(auth_settings, db)
    auth.initialize()
    for _ in range(auth_settings.login_max_failures):
        assert auth.login("unknown-user", secrets.token_urlsafe(32), "same-peer") == (None, False)
    for _ in range(6):
        assert auth.login("unknown-user", secrets.token_urlsafe(32), "same-peer") == (None, True)
    events = audit_events(db, "login_failed")
    assert len(events) == 11
    assert {event.data["status"] for event in events} == {
        "invalid_credentials",
        "account_rate_limited",
        "peer_rate_limited",
    }
    assert all(event.actor == "anonymous" and event.data["user_id"] is None for event in events)


def test_bootstrap_creation_is_audited_once(db, auth_settings):
    from pydantic import SecretStr

    auth_settings.proofops_admin_username = "bootstrap-audit-admin"
    auth_settings.proofops_admin_password = SecretStr(secrets.token_urlsafe(32))
    AuthService(auth_settings, db).initialize()
    AuthService(auth_settings, db).initialize()
    events = audit_events(db, "account_created")
    assert len(events) == 1 and events[0].actor == "bootstrap"
    assert events[0].data["status"] == "active_admin"
