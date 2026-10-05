import io
import zipfile
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from proofops.config import APP_ROOT, Settings, get_settings
from proofops.domain.common import bytes_digest, canonical, digest, strict_json, utcnow
from proofops.domain.schemas import Label, Origin, Record, ReviewReport
from proofops.models.router import ModelRouter
from proofops.policies.fixtures import fixture_suite, policy_data
from proofops.policies.guards import TrustedRevision, load_trusted, validate_proposal
from proofops.storage.analytics import billing_analytics, ingest_costs, review_analytics
from proofops.storage.artifacts import get_artifact
from proofops.storage.bundles import REPLAYS, import_zip, load_replay, redact_text
from proofops.storage.database import (
    ArtifactRow,
    AuditRow,
    BundleRow,
    GuardDraftRow,
    GuardRevisionRow,
    JobRow,
    OutcomeRow,
    ReportRow,
    session_factory,
)
from proofops.storage.repository import IdempotencyConflict, create_job, store_bundle


class ReviewRequest(Record):
    bundle_id: UUID
    mode: Literal["replay", "live"] = "replay"
    ai_preference: Literal["off", "auto"] = "off"


class GuardRequest(Record):
    ai_preference: Literal["off", "auto"] = "off"


class OutcomeRequest(Record):
    candidate_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40,64}$")]
    disposition: Literal["adopted", "rejected", "insufficient_evidence", "reverted"]
    origin: Origin
    observed_start: datetime
    observed_end: datetime
    reason: Label
    evidence_ids: list[Label] = Field(default_factory=list, max_length=20)
    cost_basis: Literal["not_measured", "compute_estimate", "observed_allocation", "billed"] = (
        "not_measured"
    )


class RequestBoundary:
    def __init__(self, app, *, maximum: int, origins: set[str]):
        self.app, self.maximum, self.origins = app, maximum, origins

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        origin = headers.get(b"origin", b"").decode("latin1")
        if origin and origin not in self.origins:
            await JSONResponse({"detail": "origin is not allowed"}, status_code=403)(
                scope, receive, send
            )
            return
        chunks = []
        total = 0
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                total += len(body)
                if total > self.maximum:
                    await JSONResponse(
                        {"detail": "request body exceeds configured limit"}, status_code=413
                    )(scope, receive, send)
                    return
                chunks.append(body)
                if not message.get("more_body", False):
                    break
            consumed = False
            original_receive = receive

            async def replay_receive():
                nonlocal consumed
                if consumed:
                    return await original_receive()
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

            receive = replay_receive

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
            await send(message)

        await self.app(scope, receive, safe_send)


def job_summary(job: JobRow, report: ReportRow | None = None) -> dict:
    return {
        "id": job.id,
        "bundle_id": job.bundle_id,
        "state": job.state,
        "stage": job.stage,
        "mode": job.mode,
        "outcome": report.outcome if report else None,
        "origin": report.core["origin"] if report else None,
        "service": report.core["change"]["service_map"]["scope"]["service"] if report else None,
        "candidate_commit": report.core["change"]["service_map"]["candidate_commit"]
        if report
        else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error_code": job.error_code,
    }


def create_app(settings: Settings | None = None, *, factory=None) -> FastAPI:
    settings = settings or get_settings()
    factory = factory or session_factory(settings.database_url)
    app = FastAPI(title="ProofOps", version="0.1.0")
    app.state.settings, app.state.factory = settings, factory
    origins = {item.strip() for item in settings.cors_origins.split(",") if item.strip()}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    app.add_middleware(RequestBoundary, maximum=settings.max_bundle_bytes, origins=origins)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "api"]
    )

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc):
        return JSONResponse(
            {
                "detail": [
                    {"loc": list(item["loc"]), "message": item["msg"], "type": item["type"]}
                    for item in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(OverflowError)
    async def size_handler(request: Request, exc):
        return JSONResponse(
            {"detail": "input exceeds configured size or count limit"}, status_code=413
        )

    @app.exception_handler(ValueError)
    async def value_handler(request: Request, exc):
        return JSONResponse({"detail": redact_text(str(exc))}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_handler(request: Request, exc):
        return JSONResponse(
            {"detail": "database is unavailable; check readiness and migrations"}, status_code=503
        )

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with factory() as session:
                version = session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                if version != "38268b7c5d67":
                    return JSONResponse(
                        {"status": "not_ready", "reason": "migrations required"}, status_code=503
                    )
        except SQLAlchemyError:
            return JSONResponse(
                {"status": "not_ready", "reason": "database or migrations unavailable"},
                status_code=503,
            )
        return {"status": "ready", "ai_required": False}

    @app.get("/api/v1/replays")
    def replays():
        labels = {
            "valid-resize": "Valid resize",
            "unsafe-resize": "Below the memory floor",
            "incomplete-evidence": "Missing candidate evidence",
        }
        return {
            "replays": [
                {"id": name, "label": labels[name], "origin": "synthetic_fixture"}
                for name in sorted(REPLAYS)
            ]
        }

    @app.post("/api/v1/bundles", status_code=201)
    async def import_bundle(request: Request):
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
        raw = await request.body()
        if content_type == "application/json":
            selection = strict_json(raw)
            if (
                not isinstance(selection, dict)
                or set(selection) != {"replay"}
                or not isinstance(selection["replay"], str)
            ):
                raise ValueError(
                    "JSON import expects a supplied replay ID; upload a ZIP for custom input"
                )
            bundle = load_replay(selection["replay"])
        elif content_type in {"application/zip", "application/octet-stream"}:
            bundle = import_zip(raw)
        else:
            raise HTTPException(
                415,
                "use application/json for a supplied replay or application/zip for an input bundle",
            )
        with factory.begin() as session:
            row, created = store_bundle(session, bundle)
            return {
                "bundle_id": row.id,
                "hashes": bundle.input_hashes,
                "origin": bundle.origin,
                "created": created,
                "validation": {
                    "sanitized": True,
                    "supported_shape": bundle.change.supported,
                    "unknown_paths": bundle.change.unknown_paths,
                    "sensitive_paths": bundle.change.sensitive_paths,
                },
            }

    @app.post("/api/v1/reviews", status_code=202)
    def queue_review(
        body: ReviewRequest,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
            ),
        ],
    ):
        with factory.begin() as session:
            bundle = session.get(BundleRow, str(body.bundle_id))
            if bundle is None:
                raise HTTPException(404, "bundle not found")
            try:
                job, created = create_job(
                    session,
                    bundle,
                    load_trusted(),
                    key=idempotency_key,
                    mode=body.mode,
                    ai_preference=body.ai_preference,
                )
            except IdempotencyConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            return {"review_id": job.id, "job_id": job.id, "state": job.state, "created": created}

    @app.get("/api/v1/reviews")
    def list_reviews(
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    ):
        with factory() as session:
            rows = session.execute(
                select(JobRow, ReportRow)
                .outerjoin(ReportRow, ReportRow.id == JobRow.id)
                .order_by(JobRow.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            total = session.scalar(select(func.count(JobRow.id)))
            return {
                "items": [job_summary(job, report) for job, report in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @app.get("/api/v1/reviews/{review_id}")
    def get_review(
        review_id: UUID,
        candidate_commit: Annotated[str | None, Query(pattern=r"^[a-f0-9]{40,64}$")] = None,
    ):
        with factory() as session:
            job = session.get(JobRow, str(review_id))
            if job is None:
                raise HTTPException(404, "review not found")
            report = session.get(ReportRow, job.id)
            result = {
                "job": job_summary(job, report),
                "report": report.core if report else None,
                "explanation": report.explanation if report else None,
            }
            if report:
                core = ReviewReport.model_validate(report.core)
                changed = (
                    candidate_commit is not None
                    and candidate_commit != core.change.service_map.candidate_commit
                )
                policy_changed = core.trusted_revision_hash != load_trusted().revision_hash
                age = (utcnow() - core.evaluation_reference_time).total_seconds()
                result["applicability"] = {
                    "candidate_changed": changed,
                    "policy_changed": policy_changed,
                    "stale_now": age
                    > load_trusted().contract.requirements.max_evidence_age_seconds,
                    "historical_snapshot": core.mode == "replay",
                    "deployment_approval": False,
                    "message": "Candidate changed; collect matching evidence and rerun."
                    if changed
                    else "This report is bound to its recorded candidate, policy and evaluation time.",
                }
                drafts = (
                    session.execute(
                        select(GuardDraftRow)
                        .where(GuardDraftRow.review_id == job.id)
                        .order_by(GuardDraftRow.created_at.desc())
                    )
                    .scalars()
                    .all()
                )
                result["guard_drafts"] = [
                    {
                        "id": draft.id,
                        "state": draft.state,
                        "spec": draft.spec,
                        "fixture_results": draft.fixture_results,
                    }
                    for draft in drafts
                ]
            return result

    @app.get("/api/v1/reviews/{review_id}/bundle")
    def download_bundle(review_id: UUID):
        with factory() as session:
            artifact = session.execute(
                select(ArtifactRow).where(ArtifactRow.review_id == str(review_id))
            ).scalar_one_or_none()
            if artifact is None:
                raise HTTPException(404, "completed report bundle not found")
            raw = get_artifact(settings.artifact_dir, artifact.id)
            return Response(
                raw,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="proofops-{review_id}.zip"'},
            )

    @app.post("/api/v1/reviews/{review_id}/guard-drafts", status_code=201)
    def create_guard_draft(review_id: UUID, body: GuardRequest):
        with factory() as session:
            report = session.get(ReportRow, str(review_id))
            if report is None:
                raise HTTPException(404, "completed review not found")
            if not report.core["coverage"].get("guard_applicable"):
                raise HTTPException(422, "the supported guard is not applicable to this review")
            record = session.get(GuardRevisionRow, report.core["trusted_revision_hash"])
            if record is None:
                raise HTTPException(422, "trusted revision is unavailable")
            trusted = TrustedRevision.model_validate(record.data)
            scope = report.scope
        model = ModelRouter(settings, factory=factory).guard(
            trusted,
            task_id=f"guard:{review_id}",
            review_id=str(review_id),
            ai_preference=body.ai_preference,
        )
        proposal = model["output"] or model["fallback"]["output"]
        validate_proposal(proposal, trusted)
        with factory.begin() as session:
            draft = GuardDraftRow(
                review_id=str(review_id),
                spec=proposal,
                state="draft",
                fixture_results={"status": "not_run"},
            )
            session.add(draft)
            session.flush()
            session.add(
                AuditRow(
                    scope=scope,
                    kind="guard_draft_created",
                    data={
                        "draft_id": draft.id,
                        "review_id": str(review_id),
                        "spec_hash": digest(proposal),
                    },
                )
            )
            return {
                "draft_id": draft.id,
                "state": draft.state,
                "spec": proposal,
                "model": model,
                "activation": "Requires a separately reviewed trusted source-control revision and protected CI.",
            }

    def draft_context(draft_id: UUID):
        with factory() as session:
            draft = session.get(GuardDraftRow, str(draft_id))
            if draft is None:
                raise HTTPException(404, "guard draft not found")
            report = session.get(ReportRow, draft.review_id)
            if report is None:
                raise HTTPException(422, "draft report is unavailable")
            revision = session.get(GuardRevisionRow, report.core["trusted_revision_hash"])
            if revision is None:
                raise HTTPException(422, "trusted revision is unavailable")
            trusted = TrustedRevision.model_validate(revision.data)
            if trusted.revision_hash != load_trusted().revision_hash:
                raise HTTPException(409, "trusted revision changed; create a new review and draft")
            validate_proposal(draft.spec, trusted)
            return draft, trusted, report.scope

    @app.post("/api/v1/guard-drafts/{draft_id}/validate")
    def validate_guard_draft(draft_id: UUID):
        original, trusted, scope = draft_context(draft_id)
        try:
            result = fixture_suite(trusted)
        except RuntimeError:
            return JSONResponse(
                {"detail": "pinned Conftest is unavailable or policy execution failed"},
                status_code=503,
            )
        result["spec_hash"] = digest(original.spec)
        result["template_hash"] = bytes_digest(
            (APP_ROOT / "policies/templates/ecs_task_memory_floor.rego").read_bytes()
        )
        result["fixtures_hash"] = bytes_digest(
            (APP_ROOT / "fixtures/negative_cases/memory-floor.json").read_bytes()
        )
        with factory.begin() as session:
            draft = session.get(GuardDraftRow, str(draft_id))
            assert draft is not None
            if digest(draft.spec) != result["spec_hash"]:
                raise HTTPException(409, "draft changed during validation; retry")
            draft.fixture_results = result
            draft.state = "fixtures_passed" if result["passed"] else "draft"
            session.add(
                AuditRow(
                    scope=scope,
                    kind="guard_draft_validated",
                    data={"draft_id": draft.id, "passed": result["passed"]},
                )
            )
            return {"draft_id": draft.id, "state": draft.state, **result, "active": False}

    @app.get("/api/v1/guard-drafts/{draft_id}/bundle")
    def download_guard_draft(draft_id: UUID):
        draft, trusted, _ = draft_context(draft_id)
        template = (APP_ROOT / "policies/templates/ecs_task_memory_floor.rego").read_bytes()
        fixtures = (APP_ROOT / "fixtures/negative_cases/memory-floor.json").read_bytes()
        if (
            draft.state != "fixtures_passed"
            or not draft.fixture_results.get("passed")
            or draft.fixture_results.get("spec_hash") != digest(draft.spec)
            or draft.fixture_results.get("template_hash") != bytes_digest(template)
            or draft.fixture_results.get("fixtures_hash") != bytes_digest(fixtures)
        ):
            raise HTTPException(
                409, "validate this draft against the current trusted fixtures first"
            )
        files = {
            "guard.json": canonical(draft.spec),
            "trusted_revision.json": canonical(trusted),
            "policy.rego": template,
            "policy_data.json": canonical(policy_data(trusted)),
            "fixtures/memory-floor.json": fixtures,
            "fixture_results.json": canonical(draft.fixture_results),
            "README.txt": (
                b"ProofOps guard draft. NOT ACTIVE.\n"
                b"Fixture validation checks only this scoped memory rule.\n"
                b"Activation requires a separately reviewed source-control revision and protected CI.\n"
                b"Reproduce in the matching ProofOps checkout with: proofops guards test\n"
            ),
        }
        files["manifest.json"] = canonical(
            {
                "schema_version": 1,
                "draft_id": str(draft_id),
                "active": False,
                "trusted_revision_hash": trusted.revision_hash,
                "files": {name: bytes_digest(raw) for name, raw in files.items()},
            }
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="proofops-guard-{draft_id}.zip"'
            },
        )

    @app.post("/api/v1/reviews/{review_id}/outcomes", status_code=201)
    def record_outcome(review_id: UUID, body: OutcomeRequest):
        with factory.begin() as session:
            report = session.get(ReportRow, str(review_id))
            if report is None:
                raise HTTPException(404, "completed review not found")
            if body.candidate_commit != report.core["change"]["service_map"]["candidate_commit"]:
                raise HTTPException(422, "outcome must reference this report's exact candidate")
            if body.observed_end < body.observed_start or body.observed_end > utcnow():
                raise HTTPException(
                    422, "outcome observation window must be ordered and not in the future"
                )
            if body.cost_basis != "not_measured" and not body.evidence_ids:
                raise HTTPException(
                    422, "a measured or estimated outcome requires evidence references"
                )
            value = body.model_dump(mode="json")
            value["reason"] = redact_text(body.reason)
            value["actor"] = "local-demo-operator"
            value["verification"] = "operator_reported"
            outcome = OutcomeRow(review_id=str(review_id), scope=report.scope, data=value)
            session.add(outcome)
            session.flush()
            session.add(
                AuditRow(
                    scope=report.scope,
                    kind="outcome_recorded",
                    data={"outcome_id": outcome.id, "review_id": str(review_id)},
                )
            )
            return {"outcome_id": outcome.id, **value}

    @app.get("/api/v1/analytics")
    def analytics():
        with factory() as session:
            return {**review_analytics(session), "billing": billing_analytics(session)}

    @app.post("/api/v1/billing/import-sample", status_code=201)
    def import_billing_sample():
        raw = (APP_ROOT / "fixtures/billing/focus_sample.csv").read_bytes()
        with factory.begin() as session:
            return ingest_costs(session, raw)

    return app


app = create_app()
