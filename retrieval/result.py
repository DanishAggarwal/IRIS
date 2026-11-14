"""Data models representing semantic retrieval results."""

from dataclasses import asdict, dataclass
from typing import Any, Optional
import uuid


@dataclass
class DocumentInfo:
    """Document metadata associated with a retrieval result."""

    id: uuid.UUID
    filename: str
    overall_type: Optional[str] = None
    department: Optional[str] = None
    academic_year: Optional[str] = None
    version: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "overall_type": self.overall_type,
            "department": self.department,
            "academic_year": self.academic_year,
            "version": self.version,
            "metadata": self.metadata,
        }


@dataclass
class ChunkInfo:
    """Document chunk and provenance information."""

    id: uuid.UUID
    chunk_index: int
    chunk_text: str
    section_title: Optional[str]
    start_page: int
    end_page: int
    page_spans: list[dict[str, Any]]
    has_table: bool
    chunking_version: str
    char_count: int
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "chunk_index": self.chunk_index,
            "chunk_text": self.chunk_text,
            "section_title": self.section_title,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "page_spans": self.page_spans,
            "has_table": self.has_table,
            "chunking_version": self.chunking_version,
            "char_count": self.char_count,
            "token_count": self.token_count,
        }


@dataclass
class RetrievalResult:
    """A single ranked retrieval result."""

    rank: int
    cosine_distance: float
    similarity_score: float
    embedding_model: str
    embedding_dim: int
    document: DocumentInfo
    chunk: ChunkInfo

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "cosine_distance": round(self.cosine_distance, 6),
            "similarity_score": round(self.similarity_score, 6),
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "document": self.document.to_dict(),
            "chunk": self.chunk.to_dict(),
        }
