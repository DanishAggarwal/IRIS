"""Conversation management and chat history endpoints."""

import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, get_database_session
from api.schemas import (
    CitationSchema,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationSummaryResponse,
    ConversationUpdateRequest,
    ErrorResponse,
    MessageResponse,
)
from database.models import Conversation, Message, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations & History"])


@router.get(
    "",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List current user's conversations",
    description="Retrieves a paginated list of conversations belonging exclusively to the authenticated user, ordered by most recently updated.",
)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100, description="Max conversations to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> ConversationListResponse:
    """List conversations owned by the authenticated user."""
    # 1. Total count for user
    total = db.scalar(
        select(func.count(Conversation.id)).where(Conversation.user_id == current_user.id)
    ) or 0

    # 2. Query conversations with message counts
    stmt = (
        select(
            Conversation,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == current_user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    items = [
        ConversationSummaryResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        )
        for conv, msg_count in rows
    ]

    return ConversationListResponse(items=items, total=total)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
    description="Creates a new conversation thread owned exclusively by the authenticated user.",
)
def create_conversation(
    payload: Optional[ConversationCreateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> ConversationResponse:
    """Create a new conversation."""
    title = (payload.title.strip() if payload and payload.title else None) or "New Conversation"

    conversation = Conversation(
        user_id=current_user.id,
        title=title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[],
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": ConversationResponse, "description": "Conversation and chronological messages."},
        404: {"model": ErrorResponse, "description": "Conversation not found or not owned by user."},
    },
    summary="Retrieve conversation and messages",
    description="Retrieves an existing conversation and its chronological message history. Enforces strict ownership.",
)
def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> ConversationResponse:
    """Retrieve conversation and messages."""
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Format messages
    messages: list[MessageResponse] = []
    for msg in conversation.messages:
        citations_list = None
        if msg.citations:
            citations_list = [
                CitationSchema(**c) if isinstance(c, dict) else c
                for c in msg.citations
            ]

        messages.append(
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                status=msg.status,
                citations=citations_list,
                clarification_question=msg.clarification_question,
                handoff_recommendation=msg.handoff_recommendation,
                created_at=msg.created_at,
            )
        )

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": ConversationResponse, "description": "Conversation renamed."},
        404: {"model": ErrorResponse, "description": "Conversation not found or not owned by user."},
    },
    summary="Rename conversation",
    description="Updates the title of an existing conversation owned by the authenticated user.",
)
def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> ConversationResponse:
    """Rename a conversation."""
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    conversation.title = payload.title.strip()
    db.commit()
    db.refresh(conversation)

    return get_conversation(conversation_id=conversation_id, current_user=current_user, db=db)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Conversation successfully deleted."},
        404: {"model": ErrorResponse, "description": "Conversation not found or not owned by user."},
    },
    summary="Delete conversation",
    description="Permanently deletes a conversation and all its messages. Enforces ownership.",
)
def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database_session),
) -> dict[str, str]:
    """Delete a conversation."""
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    db.delete(conversation)
    db.commit()

    return {"status": "deleted", "id": str(conversation_id)}
