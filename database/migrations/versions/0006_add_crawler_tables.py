"""Add crawler_sources and discovered_documents tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. crawler_sources table
    op.create_table(
        "crawler_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_id", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False, server_default="generic_link"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_crawler_sources_source_id", "crawler_sources", ["source_id"])

    # 2. discovered_documents table
    op.create_table(
        "discovered_documents",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("crawler_sources.source_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_page_url", sa.Text(), nullable=False),
        sa.Column("download_url", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False, server_default="pdf"),
        sa.Column("publication_date", sa.Text(), nullable=True),
        sa.Column("meeting_number", sa.Text(), nullable=True),
        sa.Column("academic_year", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="discovered"),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "first_discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_scanned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", "download_url", name="uq_discovered_source_download"),
    )
    op.create_index("ix_discovered_documents_source_id", "discovered_documents", ["source_id"])
    op.create_index("ix_discovered_documents_status", "discovered_documents", ["status"])
    op.create_index("ix_discovered_documents_sha256", "discovered_documents", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_discovered_documents_sha256", table_name="discovered_documents")
    op.drop_index("ix_discovered_documents_status", table_name="discovered_documents")
    op.drop_index("ix_discovered_documents_source_id", table_name="discovered_documents")
    op.drop_table("discovered_documents")
    op.drop_index("ix_crawler_sources_source_id", table_name="crawler_sources")
    op.drop_table("crawler_sources")
