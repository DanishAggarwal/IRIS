"""Create document_chunks table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("chunking_version", sa.Text(), nullable=False),
        # Nullable until M6 embedding stage
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunking_version",
            "chunk_index",
            name="uq_chunks_doc_ver_idx",
        ),
    )

    op.create_index(
        "ix_document_chunks_doc_ver",
        "document_chunks",
        ["document_id", "chunking_version"],
    )
    op.create_index(
        "ix_document_chunks_pages",
        "document_chunks",
        ["document_id", "start_page", "end_page"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_pages", table_name="document_chunks")
    op.drop_index("ix_document_chunks_doc_ver", table_name="document_chunks")
    op.drop_table("document_chunks")
