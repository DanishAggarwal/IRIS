"""Chat question-answering endpoint exposing the IRIS RAG engine."""

import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, get_database_session
from api.schemas import ChatRequest, ChatResponse, CitationSchema, ErrorResponse
from database.models import Conversation, Message, User
from ingestion.embedding_provider import EmbeddingQuotaError
from rag.generator import GenerationQuotaError
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
        401: {"model": ErrorResponse, "description": "Authentication required."},
        404: {"model": ErrorResponse, "description": "Conversation thread not found or not owned by user."},
        422: {"model": ErrorResponse, "description": "Request validation error (empty query, too long, invalid top-k)."},
        500: {"model": ErrorResponse, "description": "Unexpected internal server error."},
        503: {"model": ErrorResponse, "description": "AI provider quota or rate limit temporarily exceeded."},
    },
    summary="Ask question grounded in institutional documents",
    description=(
        "Submits a natural language query to the IRIS RAG answer engine. Retrieves relevant document "
        "chunks using vector cosine similarity, synthesizes an evidence-grounded answer via Gemini, and "
        "reconciles source citations with exact page provenance.\n\n"
        "Persists the exchange in the user's conversation thread."
    ),
)
def chat_endpoint(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> ChatResponse:
    """Process a student's natural-language question through the grounded RAG pipeline.

    Executed synchronously in FastAPI's worker threadpool to prevent blocking the async event loop.
    Persists the exchange in the specified or newly created conversation thread.
    """
    logger.info(
        f"User {current_user.email} asked: '{payload.query[:60]}...' "
        f"(conv={payload.conversation_id}, top_k={payload.top_k})"
    )

    now = datetime.now(timezone.utc)

    # 1. Resolve or create conversation
    conversation: Conversation
    if payload.conversation_id:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == current_user.id,
            )
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation thread not found.",
            )
    else:
        # Generate title from query (up to 50 chars)
        derived_title = payload.query.strip()
        if len(derived_title) > 50:
            derived_title = derived_title[:47].rstrip() + "..."

        conversation = Conversation(
            user_id=current_user.id,
            title=derived_title or "New Conversation",
            created_at=now,
            updated_at=now,
        )
        db.add(conversation)
        db.flush()  # assign conversation.id

    # 2. Persist user question
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.query,
        created_at=now,
    )
    db.add(user_message)
    db.flush()

    # 3. Invoke the central M8 RAG pipeline
    try:
        rag_response: RAGResponse = answer_question(
            query=payload.query,
            top_k=payload.top_k or 5,
            session=db,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except (GenerationQuotaError, EmbeddingQuotaError) as exc:
        db.rollback()
        logger.warning(f"AI provider quota limit reached: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "IRIS is currently experiencing high demand and has temporarily reached its "
                "AI provider capacity limit. Please wait a moment and click 'Retry question'."
            ),
        )
    except Exception as exc:
        db.rollback()
        msg = str(exc).lower()
        if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
            logger.warning(f"AI provider rate limit / quota exhaustion detected: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "IRIS is currently experiencing high demand and has temporarily reached its "
                    "AI provider capacity limit. Please wait a moment and click 'Retry question'."
                ),
            )
        logger.error(f"Error processing question: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while processing the request.",
        )

    # 4. Convert dataclass Citations to Pydantic CitationSchema & JSON serializable dicts
    api_citations = []
    citations_data = []
    for c in rag_response.citations:
        c_schema = CitationSchema(
            document=c.document,
            pages=c.pages,
            section_title=c.section_title,
            page_spans=c.page_spans,
            claim=c.claim,
            is_valid=c.is_valid,
            claim_supported=c.claim_supported,
        )
        api_citations.append(c_schema)
        citations_data.append(c_schema.model_dump())

    # Enforce safe public status mapping
    public_status = AnswerStatus.to_public_status(rag_response.status)

    # 5. Persist assistant response
    assistant_now = datetime.now(timezone.utc)
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=rag_response.answer,
        status=public_status,
        citations=citations_data if citations_data else None,
        clarification_question=rag_response.clarification_question,
        handoff_recommendation=rag_response.handoff_recommendation,
        created_at=assistant_now,
    )
    db.add(assistant_message)

    # Update conversation updated_at
    conversation.updated_at = assistant_now
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        query=rag_response.query,
        status=public_status,
        answer=rag_response.answer,
        citations=api_citations,
        clarification_question=rag_response.clarification_question,
        limitations=rag_response.limitations,
        handoff_recommendation=rag_response.handoff_recommendation,
        retrieved_count=len(rag_response.retrieved_results),
        conversation_id=conversation.id,
        message_id=assistant_message.id,
    )
