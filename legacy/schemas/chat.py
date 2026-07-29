"""Pydantic schemas for chat API."""

from pydantic import BaseModel, Field
from typing import Optional


class ChatMessage(BaseModel):
    role: str = Field(..., description="'她' or '我'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="她的最新消息")
    chat_history: list[ChatMessage] = Field(default_factory=list)


class ClosedConversationOut(BaseModel):
    id: str
    topic: str
    start_time: str
    end_time: Optional[str] = None
    summary: Optional[str] = None
    outcome: Optional[str] = None
    key_points: list = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    enhanced_reply: str
    strategy_name: str
    goal: str
    goal_zh: str
    conversation_switched: bool
    closed_conversation: Optional[ClosedConversationOut] = None
    debug: Optional[dict] = None
