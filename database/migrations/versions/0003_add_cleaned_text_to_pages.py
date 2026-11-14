"""Add cleaned_text and cleaning_version to pages.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("cleaned_text", sa.Text(), nullable=True))
    op.add_column("pages", sa.Column("cleaning_version", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "cleaning_version")
    op.drop_column("pages", "cleaned_text")
