"""Pydantic schemas for request and response validation."""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Request payload for student question-answering endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question to ask the IRIS RAG engine.",
        examples=["What are the course objectives of Cloud Computing?"],
    )
    top_k: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of evidence chunks to retrieve from the document database (1 to 20).",
        examples=[5],
    )

    @field_validator("query")
    @classmethod
    def validate_non_whitespace_query(cls, v: str) -> str:
        """Reject empty or whitespace-only queries."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query cannot be empty or contain only whitespace.")
        return stripped


class CitationSchema(BaseModel):
    """Grounded institutional document source citation with provenance."""

    document: str = Field(
        ...,
        description="Filename of the authoritative source document.",
        examples=["CSE_syllabus_24.pdf"],
    )
    pages: list[int] = Field(
        ...,
        description="Page number(s) within the document that contain the evidence.",
        examples=[[117]],
    )
    section_title: Optional[str] = Field(
        default=None,
        description="Section header or title associated with the cited chunk.",
        examples=["Unit 7"],
    )
    page_spans: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Exact page spans and character offsets for deep provenance.",
    )
    claim: Optional[str] = Field(
        default=None,
        description="Specific factual claim supported by this citation.",
        examples=["Cloud Computing course objectives"],
    )
    is_valid: bool = Field(
        default=True,
        description="Whether the citation passed existence and provenance validation.",
    )
    claim_supported: bool = Field(
        default=True,
        description="Whether the cited chunk text substantiated the factual claim.",
    )


class ChatResponse(BaseModel):
    """Complete structured response from the IRIS RAG engine."""

    query: str = Field(
        ...,
        description="The student query that was processed.",
    )
    status: str = Field(
        ...,
        description="Public answerability status ('answered', 'clarification_needed', or 'handoff_recommended').",
        examples=["answered"],
    )
    answer: str = Field(
        ...,
        description="Grounded answer text, clarification prompt, or handoff explanation.",
    )
    citations: list[CitationSchema] = Field(
        default_factory=list,
        description="List of verified citations supporting the answer.",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Single specific clarification question if status is 'clarification_needed'.",
    )
    limitations: Optional[str] = Field(
        default=None,
        description="Factual limitations, version cautions, or token budget warnings if any.",
    )
    handoff_recommendation: Optional[str] = Field(
        default=None,
        description="Institutional office recommendation if status is 'handoff_recommended'.",
    )
    retrieved_count: int = Field(
        default=0,
        description="Number of evidence chunks retrieved and considered.",
        examples=[5],
    )

    @field_validator("status")
    @classmethod
    def validate_public_status(cls, v: str) -> str:
        """Enforce that internal statuses like insufficient_evidence never escape."""
        allowed_public_statuses = {"answered", "clarification_needed", "handoff_recommended"}
        norm = v.strip().lower()
        if norm not in allowed_public_statuses:
            # Map any other status to handoff_recommended
            return "handoff_recommended"
        return norm


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = Field(default="ok", examples=["ok"])
    service: str = Field(default="IRIS API", examples=["IRIS API"])


class ReadinessResponse(BaseModel):
    """Readiness probe response verifying database and critical configuration."""

    status: str = Field(
        ...,
        description="'ready' when all dependencies are available, else 'unavailable'.",
        examples=["ready"],
    )
    service: str = Field(default="IRIS API", examples=["IRIS API"])
    database: str = Field(
        ...,
        description="Database connectivity status ('connected' or 'unavailable').",
        examples=["connected"],
    )
    configuration: str = Field(
        ...,
        description="API and Gemini key configuration status ('ready' or 'missing_api_key').",
        examples=["ready"],
    )
    detail: Optional[str] = Field(
        default=None,
        description="Diagnostic details in case of unreadiness (safe, no secrets).",
    )


class ErrorResponse(BaseModel):
    """Standardized API error response."""

    detail: str = Field(
        ...,
        description="Human-readable error description.",
        examples=["Invalid request parameter."],
    )
