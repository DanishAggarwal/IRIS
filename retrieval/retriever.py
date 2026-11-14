"""Semantic retrieval pipeline for IRIS.

Coordinates query embedding generation via the existing Gemini embedding provider
and nearest-neighbor search in PostgreSQL via pgvector cosine distance.
"""

import logging
from typing import Optional
import uuid

from google import genai
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    DEFAULT_EMBEDDING_DIM,
    MAX_TOP_K,
    search_similar_chunks,
)
from ingestion.embedding_provider import embed_query, get_embedding_config
from retrieval.result import ChunkInfo, DocumentInfo, RetrievalResult

logger = logging.getLogger(__name__)


def build_retrieval_result(
    rank: int,
    chunk: DocumentChunk,
    document: Document,
    distance: float,
    model: str,
    dimension: int,
) -> RetrievalResult:
    """Construct a clean, immutable RetrievalResult from ORM entities."""
    doc_meta = document.metadata_ or {}
    classification = doc_meta.get("classification", {})

    doc_info = DocumentInfo(
        id=document.id,
        filename=document.filename,
        overall_type=document.overall_type,
        department=classification.get("department"),
        academic_year=classification.get("academic_year"),
        version=classification.get("version"),
        metadata=doc_meta if doc_meta else None,
    )

    chunk_meta = chunk.metadata_ or {}
    chunk_info = ChunkInfo(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        chunk_text=chunk.chunk_text,
        section_title=chunk.section_title,
        start_page=chunk.start_page,
        end_page=chunk.end_page,
        page_spans=chunk_meta.get("page_spans", []),
        has_table=bool(chunk_meta.get("has_table", False)),
        chunking_version=chunking_version if (chunking_version := chunk.chunking_version) else "unknown",
        char_count=chunk.char_count,
        token_count=chunk.token_count,
    )

    similarity = 1.0 - distance

    return RetrievalResult(
        rank=rank,
        cosine_distance=distance,
        similarity_score=similarity,
        embedding_model=model,
        embedding_dim=dimension,
        document=doc_info,
        chunk=chunk_info,
    )


def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    session: Optional[Session] = None,
    client: Optional[genai.Client] = None,
    embedding_model: Optional[str] = None,
    embedding_dim: Optional[int] = None,
    document_id: Optional[uuid.UUID] = None,
) -> list[RetrievalResult]:
    """Retrieve top-K most semantically relevant chunks for a natural-language query.

    Args:
        query: Natural language query string (cannot be empty or whitespace).
        top_k: Number of nearest neighbors to retrieve (default: 5, max: 100).
        session: Optional active SQLAlchemy session. If None, a session is managed automatically.
        client: Optional preconfigured GenAI client (useful for testing/mocking).
        embedding_model: Model name filter. Defaults to configured GEMINI_EMBEDDING_MODEL.
        embedding_dim: Embedding dimension filter. Defaults to configured GEMINI_EMBEDDING_DIM.
        document_id: Optional UUID filter to restrict search to a single document.

    Returns:
        List of RetrievalResult objects ranked in ascending order of cosine distance (1..K).

    Raises:
        ValueError: If query is blank/invalid, top_k is out of range, or embedding is invalid.
        EnvironmentError: If GEMINI_API_KEY is not configured.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must be a non-empty string.")

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError(f"top_k must be a positive integer >= 1, got {top_k}.")
    if top_k > MAX_TOP_K:
        raise ValueError(f"top_k cannot exceed {MAX_TOP_K}, got {top_k}.")

    default_model, default_dim = get_embedding_config()
    model = embedding_model or default_model
    dim = embedding_dim or default_dim

    # 1. Generate query embedding using existing provider (task_type=RETRIEVAL_QUERY)
    query_vector = embed_query(query.strip(), client=client)

    # 2. Database search
    owns_session = session is None
    db = session or SessionLocal()
    try:
        raw_results = search_similar_chunks(
            session=db,
            query_vector=query_vector,
            top_k=top_k,
            embedding_model=model,
            embedding_dim=dim,
            document_id=document_id,
        )

        results: list[RetrievalResult] = []
        for i, (chunk, doc, dist) in enumerate(raw_results, start=1):
            res = build_retrieval_result(
                rank=i,
                chunk=chunk,
                document=doc,
                distance=dist,
                model=model,
                dimension=dim,
            )
            results.append(res)

        return results
    finally:
        if owns_session:
            db.close()
