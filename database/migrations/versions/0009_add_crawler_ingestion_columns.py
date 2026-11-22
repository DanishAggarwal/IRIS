"""Add ingestion provenance columns to discovered_documents.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("discovered_documents", sa.Column("local_filename", sa.Text(), nullable=True))
    op.add_column(
        "discovered_documents",
        sa.Column(
            "ingested_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("discovered_documents", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("discovered_documents", sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "ix_discovered_documents_ingested_document_id",
        "discovered_documents",
        ["ingested_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discovered_documents_ingested_document_id",
        table_name="discovered_documents",
    )
    op.drop_column("discovered_documents", "ingested_at")
    op.drop_column("discovered_documents", "downloaded_at")
    op.drop_column("discovered_documents", "ingested_document_id")
    op.drop_column("discovered_documents", "local_filename")
