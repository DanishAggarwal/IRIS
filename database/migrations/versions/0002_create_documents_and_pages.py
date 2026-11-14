"""Create documents and pages tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0002"
down_revision = "0001_enable_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False, unique=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("overall_type", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        # status: pending | extracting | complete | failed
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        # hash of the OCR config used, so re-runs with new settings force re-extraction
        sa.Column("ocr_config_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "document_id", UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 1-indexed to match human/PDF page numbering
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        # extraction_method: digital | gemini_ocr
        sa.Column("extraction_method", sa.Text(), nullable=True),
        # which model was used (None for digital pages)
        sa.Column("extraction_model", sa.Text(), nullable=True),
        # version string to track prompt/pipeline changes
        sa.Column("extraction_version", sa.Text(), nullable=True),
        # status: pending | success | failed
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_doc_page"),
    )

    # Index for fast "get pending pages for a document" queries
    op.create_index("ix_pages_document_id_status", "pages", ["document_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_pages_document_id_status", table_name="pages")
    op.drop_table("pages")
    op.drop_table("documents")
