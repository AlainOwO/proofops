from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from proofops.config import get_settings
from proofops.domain.common import utcnow

JSONType = JSON().with_variant(JSONB, "postgresql")


def identifier() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "auth_users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'viewer')", name="ck_auth_user_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_policy_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginThrottleRow(Base):
    __tablename__ = "auth_login_throttles"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DemoReviewRow(Base):
    __tablename__ = "public_demo_reviews"
    review_id: Mapped[str] = mapped_column(
        ForeignKey("review_reports.id", ondelete="CASCADE"), primary_key=True
    )
    scenario: Mapped[str] = mapped_column(String(40), unique=True)
    core_hash: Mapped[str] = mapped_column(String(64))
    explanation_hash: Mapped[str] = mapped_column(String(64))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact_manifests.id"))


class ContractRow(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeRow(Base):
    __tablename__ = "change_sets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)


class BundleRow(Base):
    __tablename__ = "bundles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"))
    change_id: Mapped[str] = mapped_column(ForeignKey("change_sets.id"))
    origin: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("bundles.id"), index=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)


class WorkloadRow(Base):
    __tablename__ = "workload_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("bundles.id"), index=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)


class JobRow(Base):
    __tablename__ = "review_jobs"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_review_idempotency"),
        Index("ix_job_claim", "state", "lease_until"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("bundles.id"), index=True)
    trusted_revision_hash: Mapped[str] = mapped_column(
        ForeignKey("guard_revisions.id", name="fk_jobs_trusted_revision")
    )
    scope: Mapped[str] = mapped_column(String(200), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    mode: Mapped[str] = mapped_column(String(12), default="replay")
    ai_preference: Mapped[str] = mapped_column(String(16), default="off")
    requested_by: Mapped[str] = mapped_column(String(80), default="host-operator")
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportRow(Base):
    __tablename__ = "review_reports"
    id: Mapped[str] = mapped_column(ForeignKey("review_jobs.id"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    core_hash: Mapped[str] = mapped_column(String(64))
    core: Mapped[dict] = mapped_column(JSONType)
    explanation: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GuardDraftRow(Base):
    __tablename__ = "guard_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    review_id: Mapped[str] = mapped_column(ForeignKey("review_reports.id"), index=True)
    spec: Mapped[dict] = mapped_column(JSONType)
    state: Mapped[str] = mapped_column(String(40), default="draft")
    fixture_results: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GuardRevisionRow(Base):
    __tablename__ = "guard_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"))
    data: Mapped[dict] = mapped_column(JSONType)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutcomeRow(Base):
    __tablename__ = "outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    review_id: Mapped[str] = mapped_column(ForeignKey("review_reports.id"), index=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactRow(Base):
    __tablename__ = "artifact_manifests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("review_reports.id"), index=True)
    manifest: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(80), default="local-demo-operator")
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BudgetRow(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("reserved >= 0 AND spent >= 0", name="ck_budget_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    limit: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    reserved: Mapped[Decimal] = mapped_column(Numeric(28, 12), default=Decimal("0"))
    spent: Mapped[Decimal] = mapped_column(Numeric(28, 12), default=Decimal("0"))


class AttemptRow(Base):
    __tablename__ = "model_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    task_key: Mapped[str] = mapped_column(String(100), unique=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"))
    review_id: Mapped[str | None] = mapped_column(ForeignKey("review_jobs.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="reserved")
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    reserved_cost: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LedgerRow(Base):
    __tablename__ = "budget_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("model_attempts.id"), index=True)
    event: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CacheRow(Base):
    __tablename__ = "accepted_output_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    data: Mapped[dict] = mapped_column(JSONType)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BillingImportRow(Base):
    __tablename__ = "billing_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(120))
    origin: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BillingRow(Base):
    __tablename__ = "billing_rows"
    __table_args__ = (UniqueConstraint("import_id", "position", name="uq_billing_row_position"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("billing_imports.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(120))
    service: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))
    billed: Mapped[Decimal | None] = mapped_column(Numeric(32, 16), nullable=True)
    effective: Mapped[Decimal | None] = mapped_column(Numeric(32, 16), nullable=True)
    raw_reference: Mapped[str] = mapped_column(Text)


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
    if not url.startswith("postgresql"):
        raise ValueError("ProofOps requires PostgreSQL for transaction and lease guarantees")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000",
        },
    )


@lru_cache
def session_factory(url: str | None = None):
    return sessionmaker(make_engine(url), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with session_factory()() as session:
        yield session
