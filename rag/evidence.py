"""Evidence assessment and diagnostic helpers for IRIS RAG."""

from dataclasses import dataclass
import re
from typing import Optional

from retrieval.result import RetrievalResult


@dataclass
class EvidenceSignal:
    """Summary metrics of retrieved evidence for decision support."""

    chunk_count: int
    min_cosine_distance: float
    max_cosine_distance: float
    mean_cosine_distance: float
    documents_represented: list[str]
    has_tables: bool
    potential_version_conflict: bool
    conflict_notes: Optional[str] = None


def assess_evidence_signal(results: list[RetrievalResult]) -> EvidenceSignal:
    """Compute aggregate signal metrics over retrieved chunks."""
    if not results:
        return EvidenceSignal(
            chunk_count=0,
            min_cosine_distance=2.0,
            max_cosine_distance=2.0,
            mean_cosine_distance=2.0,
            documents_represented=[],
            has_tables=False,
            potential_version_conflict=False,
        )

    distances = [r.cosine_distance for r in results]
    docs = sorted(list({r.document.filename for r in results}))
    has_tables = any(r.chunk.has_table for r in results)

    # Check for potential version conflicts (e.g. Ver 1_0 and Ver 2_0 both retrieved)
    ver1_present = any("Ver 1_0" in d for d in docs)
    ver2_present = any("Ver 2_0" in d for d in docs)
    conflict = ver1_present and ver2_present
    conflict_notes = (
        "Retrieved chunks span both Course Handout Ver 1_0 and Ver 2_0. "
        "Carefully verify whether policies or evaluation components differ."
        if conflict
        else None
    )

    return EvidenceSignal(
        chunk_count=len(results),
        min_cosine_distance=min(distances),
        max_cosine_distance=max(distances),
        mean_cosine_distance=sum(distances) / len(distances),
        documents_represented=docs,
        has_tables=has_tables,
        potential_version_conflict=conflict,
        conflict_notes=conflict_notes,
    )
