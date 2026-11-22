"""Pydantic schemas for request and response validation."""

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        default=6,
        ge=1,
        le=20,
        description="Number of evidence chunks to retrieve from the document database (1 to 20).",
        examples=[6],
    )
    conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional conversation thread ID to append the question and answer to.",
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
    conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Conversation thread ID where this exchange was persisted.",
    )
    message_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Persistent ID of the assistant response message.",
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


# ==============================================================================
# Authentication & User Management Schemas
# ==============================================================================


class GoogleAuthRequest(BaseModel):
    """Request payload containing Google OpenID Connect ID token."""

    id_token: str = Field(
        ...,
        min_length=10,
        description="Raw JWT identity token received from Google Identity Services.",
    )


class UserResponse(BaseModel):
    """Authenticated user profile representation."""

    id: uuid.UUID
    email: str
    name: str
    profile_picture_url: Optional[str] = None
    role: str  # "user" | "admin"


class LogoutResponse(BaseModel):
    """Response confirming session revocation."""

    status: str = Field(default="logged_out", examples=["logged_out"])


# ==============================================================================
# Conversation History Schemas
# ==============================================================================


class ConversationCreateRequest(BaseModel):
    """Request payload to start a new named conversation."""

    title: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Optional title for the conversation. Defaults to 'New Conversation'.",
    )


class ConversationUpdateRequest(BaseModel):
    """Request payload to rename an existing conversation."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="New non-empty title for the conversation.",
    )

    @field_validator("title")
    @classmethod
    def validate_non_whitespace_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Conversation title cannot be empty or only whitespace.")
        return stripped


class MessageResponse(BaseModel):
    """Single question or answer message within a conversation."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str  # "user" | "assistant"
    content: str
    status: Optional[str] = None
    citations: Optional[list[CitationSchema]] = None
    clarification_question: Optional[str] = None
    handoff_recommendation: Optional[str] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    """Detailed conversation representation including chronological messages."""

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = Field(default_factory=list)


class ConversationSummaryResponse(BaseModel):
    """Summary of a conversation for list/sidebar view."""

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationListResponse(BaseModel):
    """Paginated collection of conversation summaries."""

    items: list[ConversationSummaryResponse] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Crawler & Document Acquisition Schemas (Phase 2)
# ---------------------------------------------------------------------------


class CrawlerSourceSchema(BaseModel):
    """Configured institutional source webpage."""

    id: uuid.UUID
    source_id: str
    name: str
    url: str
    category: str
    strategy: str
    enabled: bool
    config: Optional[dict[str, Any]] = None
    last_scanned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrawlerSourceUpdateSchema(BaseModel):
    """Optional update fields for a crawler source."""

    enabled: Optional[bool] = None
    name: Optional[str] = None
    category: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class DiscoveredDocumentSchema(BaseModel):
    """Discovered document catalogue item with change detection and approval state."""

    id: uuid.UUID
    source_id: str
    title: str
    source_page_url: str
    download_url: str
    category: str
    file_type: str
    publication_date: Optional[str] = None
    meeting_number: Optional[str] = None
    academic_year: Optional[str] = None
    status: str  # discovered | pending_approval | approved | rejected | ingesting | ingested | potentially_changed
    change_status: str  # unknown | unchanged | potentially_changed
    http_etag: Optional[str] = None
    http_last_modified: Optional[str] = None
    http_content_length: Optional[int] = None
    last_checked_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    local_filename: Optional[str] = None
    ingested_document_id: Optional[uuid.UUID] = None
    downloaded_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    error_message: Optional[str] = None
    sha256: Optional[str] = None
    first_discovered_at: datetime
    last_discovered_at: datetime
    last_scanned_at: datetime
    metadata: Optional[dict[str, Any]] = Field(default=None, alias="metadata_")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DiscoveredDocumentListResponse(BaseModel):
    """Paginated list of discovered documents with catalogue stats."""

    items: list[DiscoveredDocumentSchema]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: dict[str, int]


class DocumentRejectionRequest(BaseModel):
    """Payload for rejecting a candidate document."""

    reason: Optional[str] = Field(default=None, max_length=500, description="Optional rejection reason")


class DocumentAuditSchema(BaseModel):
    """Immutable audit trail record for approval/rejection decision."""

    id: uuid.UUID
    document_id: uuid.UUID
    admin_email: str
    action: str
    previous_status: str
    new_status: str
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrawlerScanTriggerRequest(BaseModel):
    """Optional payload to restrict scan to a single source."""

    source_id: Optional[str] = Field(default=None, description="Optional source_id slug to scan")


class CrawlerScanResponse(BaseModel):
    """Crawler scan execution progress and outcome record."""

    id: uuid.UUID
    source_id: Optional[str] = None
    status: str  # running | completed | failed
    total_sources: int
    total_discovered: int
    new_documents: int
    updated_documents: int
    potentially_changed: int
    error_message: Optional[str] = None
    initiated_by: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentIngestionStatusResponse(BaseModel):
    """Detailed acquisition and ingestion status for a discovered document."""

    id: uuid.UUID
    title: str
    download_url: str
    status: str
    change_status: str
    sha256: Optional[str] = None
    local_filename: Optional[str] = None
    ingested_document_id: Optional[uuid.UUID] = None
    downloaded_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



