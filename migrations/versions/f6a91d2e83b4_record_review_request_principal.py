"""Persist the review submitter independently of worker leases.

Revision ID: f6a91d2e83b4
Revises: e7d91b4c2a60
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a91d2e83b4"
down_revision = "e7d91b4c2a60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "review_jobs",
        sa.Column(
            "requested_by", sa.String(80), nullable=False, server_default="legacy-unattributed"
        ),
    )
    op.alter_column("review_jobs", "requested_by", server_default=None)


def downgrade():
    op.drop_column("review_jobs", "requested_by")
