"""Chat question-answering endpoint exposing the IRIS RAG engine."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.dependencies import get_database_session
from api.schemas import ChatRequest, ChatResponse, CitationSchema, ErrorResponse
from rag.models import AnswerStatus, RAGResponse
from rag.pipeline import answer_question

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Question Answering"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "model": ChatResponse,
            "description": (
                "Successful RAG response. Note that legitimate clarification pauses "
                "and safe handoff recommendations are returned with HTTP 200 and their respective status."
            ),
        },
        422: {"model": ErrorResponse, "description": "Request validation error (empty query, too long, invalid top-k)."},
        500: {"model": ErrorResponse, "description": "Unexpected internal server error."},
    },
    summary="Ask question grounded in institutional documents",
    description=(
        "Submits a natural language query to the IRIS RAG answer engine. Retrieves relevant document "
        "chunks using vector cosine similarity, synthesizes an evidence-grounded answer via Gemini, and "
        "reconciles source citations with exact page provenance.\n\n"
        "**Possible Response Statuses:**\n"
        "- `answered`: The question is clear and completely supported by retrieved document evidence.\n"
        "- `clarification_needed`: The question is ambiguous regarding which course or document is meant; "
        "returns a specific `clarification_question`.\n"
        "- `handoff_recommended`: The question cannot be authoritatively answered from available evidence, "
        "concerns an administrative exception or waiver, or asks for information outside the document corpus. "
        "Includes a safe `handoff_recommendation` directing the student to the appropriate authority."
    ),
)
def chat_endpoint(
    payload: ChatRequest,
    db: Session = Depends(get_database_session),
) -> ChatResponse:
    """Process a student's natural-language question through the grounded RAG pipeline.

    Executed synchronously in FastAPI's worker threadpool to prevent blocking the async event loop.
    """
    logger.info(f"Received chat question: '{payload.query[:60]}...' (top_k={payload.top_k})")

    try:
        # Invoke the central M8 RAG pipeline
        rag_response: RAGResponse = answer_question(
            query=payload.query,
            top_k=payload.top_k or 5,
            session=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Error processing question: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while processing the request.",
        )

    # Convert dataclass Citations to Pydantic CitationSchema
    api_citations = []
    for c in rag_response.citations:
        api_citations.append(
            CitationSchema(
                document=c.document,
                pages=c.pages,
                section_title=c.section_title,
                page_spans=c.page_spans,
                claim=c.claim,
                is_valid=c.is_valid,
                claim_supported=c.claim_supported,
            )
        )

    # Enforce safe public status mapping
    public_status = AnswerStatus.to_public_status(rag_response.status)

    return ChatResponse(
        query=rag_response.query,
        status=public_status,
        answer=rag_response.answer,
        citations=api_citations,
        clarification_question=rag_response.clarification_question,
        limitations=rag_response.limitations,
        handoff_recommendation=rag_response.handoff_recommendation,
        retrieved_count=len(rag_response.retrieved_results),
    )
