from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    id: str
    role: str
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class SaveChatRequest(BaseModel):
    id: Optional[str] = None
    user_id: str = Field(..., description="Google Subject/User ID")
    user_email: Optional[str] = None
    title: str = Field(default="Conversation")
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None


class ChatSummary(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str] = None
    title: str
    message_count: int
    snippet: Optional[str] = None
    created_at: str
    updated_at: str


class ChatDetailResponse(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str] = None
    title: str
    messages: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    saved_to_cloud: Optional[bool] = False
