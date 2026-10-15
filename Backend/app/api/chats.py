import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.chat import (
    SaveChatRequest,
    ChatSummary,
    ChatDetailResponse
)
from app.services.chat_history_service import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["Chat History & Search"])


@router.get("", response_model=List[ChatSummary])
def list_chats(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    search: Optional[str] = Query(None, description="Search query across titles and messages")
):
    """
    Search and retrieve chat sessions for the authenticated user.
    """
    chats = chat_service.get_user_chats(
        user_id=user_id,
        user_email=user_email,
        search_query=search
    )

    summaries = []
    for c in chats:
        msgs = c.get("messages", [])
        # Extract snippet from first assistant answer or last message
        snippet = ""
        for m in msgs:
            if isinstance(m, dict):
                if m.get("role") == "assistant" and isinstance(m.get("data"), dict):
                    snippet = m.get("data", {}).get("answer") or m.get("data", {}).get("lead") or ""
                    if snippet:
                        break
                elif m.get("text"):
                    snippet = m.get("text")

        summaries.append(
            ChatSummary(
                id=c.get("id"),
                user_id=c.get("user_id", ""),
                user_email=c.get("user_email"),
                title=c.get("title") or "Conversation",
                message_count=len(msgs),
                snippet=snippet[:180] + ("..." if len(snippet) > 180 else "") if snippet else None,
                created_at=c.get("created_at", ""),
                updated_at=c.get("updated_at", "")
            )
        )

    return summaries


@router.get("/{chat_id}", response_model=ChatDetailResponse)
def get_chat(chat_id: str):
    """
    Fetch full chat transcript by ID.
    """
    chat = chat_service.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat conversation not found."
        )
    return ChatDetailResponse(
        id=chat.get("id"),
        user_id=chat.get("user_id", ""),
        user_email=chat.get("user_email"),
        title=chat.get("title") or "Conversation",
        messages=chat.get("messages", []),
        created_at=chat.get("created_at", ""),
        updated_at=chat.get("updated_at", ""),
        saved_to_cloud=chat.get("saved_to_cloud", False)
    )


@router.post("", response_model=ChatDetailResponse)
def save_chat(payload: SaveChatRequest):
    """
    Save or update a conversation session in Supabase cloud storage (with local caching).
    """
    record = chat_service.save_chat(payload.model_dump())
    return ChatDetailResponse(
        id=record.get("id"),
        user_id=record.get("user_id", ""),
        user_email=record.get("user_email"),
        title=record.get("title", ""),
        messages=record.get("messages", []),
        created_at=record.get("created_at", ""),
        updated_at=record.get("updated_at", ""),
        saved_to_cloud=record.get("saved_to_cloud", False)
    )


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, user_id: Optional[str] = Query(None)):
    """
    Delete a specific chat conversation.
    """
    success = chat_service.delete_chat(chat_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat conversation not found or already deleted."
        )
    return {"success": True, "message": "Chat conversation successfully deleted."}


@router.post("/clear")
def clear_chats(user_id: str = Query(..., description="User ID to clear chats for")):
    """
    Clear all saved chats for a user.
    """
    chat_service.clear_user_chats(user_id)
    return {"success": True, "message": "All conversations cleared."}
