"""Data models for IRIS RAG answer engine."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid

from retrieval.result import RetrievalResult


class AnswerStatus(str, Enum):
    """Answerability statuses for IRIS RAG.

    Public / Student-Facing Statuses:
      - ANSWERED: Complete, directly evidence-supported answer with verified citations.
      - CLARIFICATION_NEEDED: Ambiguous query where student can specify the course/context.
      - HANDOFF_RECOMMENDED: Mandatory safe fallback whenever an evidence-grounded answer
        cannot be confidently provided.

    Internal Diagnostic Status:
      - INSUFFICIENT_EVIDENCE: Diagnostic status indicating absent or incomplete evidence.
        Centrally mapped to HANDOFF_RECOMMENDED at the public response layer.
    """

    ANSWERED = "answered"
    CLARIFICATION_NEEDED = "clarification_needed"
    HANDOFF_RECOMMENDED = "handoff_recommended"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

    @classmethod
    def to_public_status(cls, status: str) -> str:
        """Map internal or model status to one of the three authorized student-facing statuses."""
        s = str(status).strip().lower()
        if s == cls.ANSWERED.value:
            return cls.ANSWERED.value
        if s == cls.CLARIFICATION_NEEDED.value:
            return cls.CLARIFICATION_NEEDED.value
        # All other statuses (including insufficient_evidence) map to handoff_recommended
        return cls.HANDOFF_RECOMMENDED.value


@dataclass
class Citation:
    """A verified source citation referencing retrieved document evidence."""

    document: str
    pages: list[int]
    chunk_id: Optional[uuid.UUID] = None
    section_title: Optional[str] = None
    page_spans: list[dict[str, Any]] = field(default_factory=list)
    claim: Optional[str] = None
    is_valid: bool = True
    exists_in_retrieval: bool = True
    provenance_valid: bool = True
    claim_supported: bool = True
    support_score: float = 1.0
    support_notes: Optional[str] = None

    def format_citation(self) -> str:
        """Format human-readable citation string."""
        if not self.pages:
            page_str = "unspecified page"
        elif len(self.pages) == 1 or self.pages[0] == self.pages[-1]:
            page_str = f"page {self.pages[0]}"
        else:
            page_str = f"pages {self.pages[0]}–{self.pages[-1]}"

        sec_str = f" ({self.section_title})" if self.section_title else ""
        return f"[Source: {self.document}, {page_str}{sec_str}]"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "pages": self.pages,
            "chunk_id": str(self.chunk_id) if self.chunk_id else None,
            "section_title": self.section_title,
            "page_spans": self.page_spans,
            "claim": self.claim,
            "is_valid": self.is_valid,
            "exists_in_retrieval": self.exists_in_retrieval,
            "provenance_valid": self.provenance_valid,
            "claim_supported": self.claim_supported,
            "support_score": round(self.support_score, 3),
            "support_notes": self.support_notes,
        }


@dataclass
class RAGResponse:
    """The complete structured response from the RAG answer engine."""

    query: str
    status: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    clarification_question: Optional[str] = None
    limitations: Optional[str] = None
    handoff_recommendation: Optional[str] = None
    retrieved_results: list[RetrievalResult] = field(default_factory=list)
    internal_status: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "internal_status": self.internal_status or self.status,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "clarification_question": self.clarification_question,
            "limitations": self.limitations,
            "handoff_recommendation": self.handoff_recommendation,
            "retrieved_count": len(self.retrieved_results),
        }

    def to_human_readable(self) -> str:
        lines = []
        lines.append(f"Status: {self.status}\n")

        if self.answer:
            lines.append("Answer / Explanation:")
            lines.append(f"  {self.answer.strip()}")
            lines.append("")

        if self.clarification_question:
            lines.append("Clarification Needed:")
            lines.append(f"  {self.clarification_question.strip()}")
            lines.append("")

        if self.handoff_recommendation:
            lines.append("Handoff Recommendation:")
            lines.append(f"  {self.handoff_recommendation.strip()}")
            lines.append("")

        if self.limitations:
            lines.append("Limitations:")
            lines.append(f"  {self.limitations.strip()}")
            lines.append("")

        if self.citations:
            lines.append("Sources:")
            for c in self.citations:
                lines.append(f"  - {c.format_citation()}")

        return "\n".join(lines).strip()
