"""Persist users, expiring sessions, login limits and explicit public demo membership.

Revision ID: c8429d7a6e10
Revises: 38268b7c5d67
"""

import sqlalchemy as sa
from alembic import op

revision = "c8429d7a6e10"
down_revision = "38268b7c5d67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("password_policy_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'viewer')", name="ck_auth_user_role"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("auth_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_login_throttles",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "public_demo_reviews",
        sa.Column(
            "review_id",
            sa.String(36),
            sa.ForeignKey("review_reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scenario", sa.String(40), nullable=False, unique=True),
        sa.Column("core_hash", sa.String(64), nullable=False),
        sa.Column("explanation_hash", sa.String(64), nullable=False),
        sa.Column(
            "artifact_id", sa.String(64), sa.ForeignKey("artifact_manifests.id"), nullable=False
        ),
    )


def downgrade():
    op.drop_table("public_demo_reviews")
    op.drop_table("auth_login_throttles")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
