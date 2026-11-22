"""Add partial unique index on crawler_scans to enforce at most one running scan.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index ensuring at most one scan can have status='running' concurrently
    op.create_index(
        "uq_crawler_scans_single_running",
        "crawler_scans",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_crawler_scans_single_running",
        table_name="crawler_scans",
    )
