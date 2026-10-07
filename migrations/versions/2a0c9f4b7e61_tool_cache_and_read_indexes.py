"""Add disposable tool observations and indexes for bounded reads/cleanup.

Revision ID: 2a0c9f4b7e61
Revises: f6a91d2e83b4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2a0c9f4b7e61"
down_revision = "f6a91d2e83b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tool_observation_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("namespace", sa.String(16), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tool_observation_cache_expires_at", "tool_observation_cache", ["expires_at"]
    )
    op.create_index("ix_accepted_output_cache_expires_at", "accepted_output_cache", ["expires_at"])
    op.create_index("ix_job_created_id", "review_jobs", ["created_at", "id"])


def downgrade():
    op.drop_index("ix_job_created_id", table_name="review_jobs")
    op.drop_index("ix_accepted_output_cache_expires_at", table_name="accepted_output_cache")
    op.drop_index("ix_tool_observation_cache_expires_at", table_name="tool_observation_cache")
    # Only disposable observations are lost; review and accounting data survive.
    op.drop_table("tool_observation_cache")
