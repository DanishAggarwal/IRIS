"""Context builder for IRIS RAG answer engine.

Formats retrieved document chunks into evidence blocks respecting token budgets,
preserving provenance, and treating retrieved text strictly as untrusted data.
"""

import logging
from typing import Optional

from retrieval.result import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTEXT_TOKENS = 4000


def format_evidence_block(result: RetrievalResult, evidence_num: int) -> str:
    """Format a single retrieval result as an untrusted evidence block."""
    chunk = result.chunk
    doc = result.document

    if chunk.start_page == chunk.end_page:
        page_str = f"Page {chunk.start_page}"
    else:
        page_str = f"Pages {chunk.start_page}–{chunk.end_page}"

    sec_str = chunk.section_title or "None"
    table_str = "Yes" if chunk.has_table else "No"

    # Treat retrieved content as untrusted evidence data
    # Delimit clearly with boundary markers
    block = [
        f"--- EVIDENCE ITEM {evidence_num} ---",
        f"[DOCUMENT]: {doc.filename}",
        f"[PAGES]: {page_str}",
        f"[SECTION]: {sec_str}",
        f"[CHUNK_ID]: {chunk.id}",
        f"[HAS_TABLE]: {table_str}",
        f"[COSINE_DISTANCE]: {result.cosine_distance:.4f}",
        "[CONTENT]:",
        chunk.chunk_text.strip(),
        f"--- END EVIDENCE ITEM {evidence_num} ---",
    ]
    return "\n".join(block)


def build_rag_context(
    retrieval_results: list[RetrievalResult],
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> tuple[str, list[RetrievalResult], list[str]]:
    """Assemble retrieval results into a bounded evidence string.

    Args:
        retrieval_results: Ranked nearest-neighbor chunks from M7.
        max_tokens: Maximum token budget for the context block.

    Returns:
        tuple containing:
        - context_str: Combined evidence string.
        - included_results: List of RetrievalResult items that fit into the budget.
        - warnings: List of warning messages (e.g. if chunks were excluded due to budget).
    """
    if not retrieval_results:
        return "No retrieved evidence provided.", [], ["No documents retrieved."]

    included_results: list[RetrievalResult] = []
    blocks: list[str] = []
    warnings: list[str] = []
    current_tokens = 0
    seen_chunk_ids = set()

    for idx, res in enumerate(retrieval_results, start=1):
        if res.chunk.id in seen_chunk_ids:
            continue  # Avoid duplicate identical chunks

        doc_name = res.document.filename
        chunk_tokens = res.chunk.token_count or (len(res.chunk.chunk_text) // 4)
        # Overhead for metadata headers (~50 tokens)
        estimated_total = chunk_tokens + 50

        if current_tokens + estimated_total > max_tokens:
            msg = (
                f"Context budget reached ({current_tokens}/{max_tokens} tokens). "
                f"Excluded chunk {res.chunk.id} ({doc_name}) at rank {res.rank}."
            )
            logger.info(msg)
            warnings.append(msg)
            continue

        seen_chunk_ids.add(res.chunk.id)
        included_results.append(res)
        blocks.append(format_evidence_block(res, len(included_results)))
        current_tokens += estimated_total

    context_str = "\n\n".join(blocks)
    return context_str, included_results, warnings
