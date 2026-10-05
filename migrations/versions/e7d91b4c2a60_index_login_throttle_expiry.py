"""Index bounded login-throttle cleanup.

Revision ID: e7d91b4c2a60
Revises: c8429d7a6e10
"""

from alembic import op

revision = "e7d91b4c2a60"
down_revision = "c8429d7a6e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_auth_login_throttles_window_start", "auth_login_throttles", ["window_start"]
    )


def downgrade():
    op.drop_index("ix_auth_login_throttles_window_start", table_name="auth_login_throttles")
