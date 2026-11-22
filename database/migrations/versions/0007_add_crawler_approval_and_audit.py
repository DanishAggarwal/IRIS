"""Add change detection columns, crawler_scans, and document_approval_audits.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add change detection and approval tracking columns to discovered_documents
    op.add_column("discovered_documents", sa.Column("http_etag", sa.Text(), nullable=True))
    op.add_column("discovered_documents", sa.Column("http_last_modified", sa.Text(), nullable=True))
    op.add_column("discovered_documents", sa.Column("http_content_length", sa.BigInteger(), nullable=True))
    op.add_column("discovered_documents", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "discovered_documents",
        sa.Column("change_status", sa.Text(), nullable=False, server_default="unknown"),
    )
    op.add_column("discovered_documents", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("discovered_documents", sa.Column("approved_by", sa.Text(), nullable=True))
    op.add_column("discovered_documents", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_discovered_documents_change_status", "discovered_documents", ["change_status"])

    # 2. Create crawler_scans table for execution tracking and concurrency locking
    op.create_table(
        "crawler_scans",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),  # running | completed | failed
        sa.Column("total_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("potentially_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crawler_scans_status", "crawler_scans", ["status"])

    # 3. Create document_approval_audits table for immutable decision tracking
    op.create_table(
        "document_approval_audits",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovered_documents.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "admin_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("admin_email", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),  # approve | reject | reconsider
        sa.Column("previous_status", sa.Text(), nullable=False),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_document_approval_audits_doc_id", "document_approval_audits", ["document_id"])
    op.create_index("ix_document_approval_audits_admin", "document_approval_audits", ["admin_email"])


def downgrade() -> None:
    op.drop_index("ix_document_approval_audits_admin", table_name="document_approval_audits")
    op.drop_index("ix_document_approval_audits_doc_id", table_name="document_approval_audits")
    op.drop_table("document_approval_audits")

    op.drop_index("ix_crawler_scans_status", table_name="crawler_scans")
    op.drop_table("crawler_scans")

    op.drop_index("ix_discovered_documents_change_status", table_name="discovered_documents")
    op.drop_column("discovered_documents", "approved_at")
    op.drop_column("discovered_documents", "approved_by")
    op.drop_column("discovered_documents", "rejection_reason")
    op.drop_column("discovered_documents", "change_status")
    op.drop_column("discovered_documents", "last_checked_at")
    op.drop_column("discovered_documents", "http_content_length")
    op.drop_column("discovered_documents", "http_last_modified")
    op.drop_column("discovered_documents", "http_etag")
