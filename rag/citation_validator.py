"""Citation validation and claim-support reconciliation for IRIS RAG.

Distinguishes three independent verification properties:
1. Citation existence — does the citation reference an actual retrieved chunk?
2. Citation provenance — are the document and page references correct?
3. Claim support — does the cited evidence actually establish the associated factual claim?
"""

import logging
import re
from typing import Any, Optional
import uuid

from rag.models import Citation
from retrieval.result import RetrievalResult

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "its", "itself", "me", "more", "most", "my", "myself", "no", "nor", "not", "of",
    "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "you", "your", "yours", "yourself",
}


def evaluate_claim_support(
    claim_text: Optional[str],
    chunk_text: str,
) -> tuple[bool, float, Optional[str]]:
    """Evaluate whether the cited chunk text actually supports the factual claim.

    Checks:
    - Numerical claims: numbers, percentages, and fractions in claim must exist in text.
    - Code claims: uppercase course codes (e.g. CSN 4002, CS 25261) must exist in text.
    - Lexical coverage: substantive terms in claim must be present in chunk text.

    Returns:
        (claim_supported, support_score, support_notes)
    """
    if not claim_text or not claim_text.strip():
        # If no explicit claim text is attached to citation, evaluate as neutral
        return True, 1.0, None

    claim = claim_text.strip()
    chunk_lower = chunk_text.lower()

    # 1. Numerical and percentage claim verification
    numbers_in_claim = re.findall(r"\b\d+(?:\.\d+)?%?", claim)
    for num in numbers_in_claim:
        if num.lower() not in chunk_lower:
            return (
                False,
                0.2,
                f"Numerical claim '{num}' not found in cited evidence.",
            )

    # 2. Course code verification (strictly uppercase prefixes like CSN 4002, CSE 25261)
    codes_in_claim = re.findall(r"\b[A-Z]{2,4}\s*\d{3,5}\b", claim)
    for code in codes_in_claim:
        norm_code = re.sub(r"\s+", "", code.lower())
        norm_chunk = re.sub(r"\s+", "", chunk_lower)
        if norm_code not in norm_chunk:
            return (
                False,
                0.3,
                f"Course code '{code}' not found in cited evidence.",
            )

    # 3. Substantive term overlap
    raw_tokens = re.findall(r"\b[A-Za-z0-9_-]{3,}\b", claim.lower())
    substantive_tokens = [t for t in raw_tokens if t not in STOPWORDS]

    if not substantive_tokens:
        return True, 1.0, None

    matched_tokens = [t for t in substantive_tokens if t in chunk_lower]
    overlap_score = len(matched_tokens) / len(substantive_tokens)

    # Require at least 40% substantive term coverage
    if overlap_score < 0.40:
        missing = [t for t in substantive_tokens if t not in chunk_lower][:3]
        return (
            False,
            round(overlap_score, 3),
            f"Insufficient term support in cited chunk (missing terms: {missing}).",
        )

    return True, round(overlap_score, 3), None


def _find_matching_chunk(
    doc_name: str,
    pages: list[int],
    retrieval_results: list[RetrievalResult],
    claim: Optional[str] = None,
) -> tuple[Optional[RetrievalResult], bool, bool]:
    """Find a retrieved chunk and evaluate existence and page provenance.

    If multiple chunks overlap with the cited page(s), selects the chunk
    that best supports the citation's factual claim.

    Returns:
        (matching_chunk, exists_in_retrieval, provenance_valid)
    """
    clean_target = doc_name.lower().replace(".pdf", "").strip()

    # 1. Search for document existence in retrieved results
    candidate_doc_chunks = []
    for res in retrieval_results:
        clean_doc = res.document.filename.lower().replace(".pdf", "").strip()
        if (
            res.document.filename == doc_name
            or clean_target == clean_doc
            or clean_target in clean_doc
            or clean_doc in clean_target
        ):
            candidate_doc_chunks.append(res)

    if not candidate_doc_chunks:
        return None, False, False

    # 2. Check page provenance across candidates
    if not pages:
        # Document exists, but no specific page cited
        return candidate_doc_chunks[0], True, True

    min_p = min(pages)
    max_p = max(pages)

    overlapping_chunks = []
    for res in candidate_doc_chunks:
        if max(res.chunk.start_page, min_p) <= min(res.chunk.end_page, max_p):
            overlapping_chunks.append(res)

    if overlapping_chunks:
        # If claim is provided, pick the candidate chunk with the best claim support
        if claim and len(overlapping_chunks) > 1:
            best_chunk = overlapping_chunks[0]
            best_score = -1.0
            for cand in overlapping_chunks:
                ok, score, _ = evaluate_claim_support(claim, cand.chunk.chunk_text)
                if ok and score > best_score:
                    best_score = score
                    best_chunk = cand
            return best_chunk, True, True

        return overlapping_chunks[0], True, True

    # Document was retrieved, but cited pages do not overlap with any chunk
    return candidate_doc_chunks[0], True, False


def validate_citations(
    raw_citations: list[dict[str, Any]],
    retrieval_results: list[RetrievalResult],
    status: str,
) -> tuple[list[Citation], list[str], bool]:
    """Validate and reconcile citations generated by the LLM.

    Evaluates:
      1. Citation existence (in retrieved chunks)
      2. Citation provenance (page interval overlap)
      3. Claim support (factual and numerical grounding in chunk text)

    Args:
        raw_citations: List of citation dictionaries from model output.
        retrieval_results: The actual RetrievalResult chunks provided in context.
        status: The answerability status ('answered', etc.).

    Returns:
        tuple of (validated_citations, warnings_list, all_claims_supported).
    """
    validated: list[Citation] = []
    warnings: list[str] = []
    all_claims_supported = True
    seen_keys = set()

    for item in raw_citations:
        doc_cited = str(item.get("document", "")).strip()
        raw_pages = item.get("pages", [])
        claim_str = item.get("claim")

        # Parse pages into integers
        parsed_pages: list[int] = []
        if isinstance(raw_pages, (list, tuple)):
            for p in raw_pages:
                try:
                    parsed_pages.append(int(p))
                except (ValueError, TypeError):
                    pass
        elif isinstance(raw_pages, (int, str)):
            try:
                parsed_pages.append(int(raw_pages))
            except (ValueError, TypeError):
                pass

        matching_chunk, exists_in_retrieval, provenance_valid = _find_matching_chunk(
            doc_name=doc_cited,
            pages=parsed_pages,
            retrieval_results=retrieval_results,
            claim=claim_str,
        )

        if not exists_in_retrieval:
            msg = f"Citation Existence Failed: Document '{doc_cited}' was not retrieved."
            logger.warning(msg)
            warnings.append(msg)
            all_claims_supported = False
            continue

        if not provenance_valid:
            msg = (
                f"Citation Provenance Failed: Document '{doc_cited}' cited pages {parsed_pages}, "
                f"which do not overlap with chunk page range {matching_chunk.chunk.start_page}–{matching_chunk.chunk.end_page}."
            )
            logger.warning(msg)
            warnings.append(msg)
            all_claims_supported = False
            continue

        # Evaluate claim support against the matching chunk text
        claim_ok, score, note = evaluate_claim_support(
            claim_text=claim_str,
            chunk_text=matching_chunk.chunk.chunk_text,
        )

        if not claim_ok:
            all_claims_supported = False
            msg = f"Claim Support Failed for '{doc_cited}' (pp. {parsed_pages}): {note}"
            logger.warning(msg)
            warnings.append(msg)

        c_doc = matching_chunk.document.filename
        c_pages = parsed_pages if parsed_pages else [matching_chunk.chunk.start_page, matching_chunk.chunk.end_page]
        key = (c_doc, tuple(sorted(c_pages)), matching_chunk.chunk.id)

        if key not in seen_keys:
            seen_keys.add(key)
            validated.append(
                Citation(
                    document=c_doc,
                    pages=c_pages,
                    chunk_id=matching_chunk.chunk.id,
                    section_title=matching_chunk.chunk.section_title,
                    page_spans=matching_chunk.chunk.page_spans,
                    claim=claim_str,
                    is_valid=(exists_in_retrieval and provenance_valid and claim_ok),
                    exists_in_retrieval=exists_in_retrieval,
                    provenance_valid=provenance_valid,
                    claim_supported=claim_ok,
                    support_score=score,
                    support_notes=note,
                )
            )

    # If answered but no valid citations survived, do not fabricate; record warning
    if status == "answered" and not validated:
        all_claims_supported = False
        if retrieval_results:
            top1 = retrieval_results[0]
            msg = f"No valid citations provided by model; top retrieved chunk is from {top1.document.filename} (page {top1.chunk.start_page})."
            warnings.append(msg)

    return validated, warnings, all_claims_supported
