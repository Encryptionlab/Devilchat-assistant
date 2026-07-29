"""Pydantic schemas for conversation API."""

from pydantic import BaseModel
from typing import Optional


class ConversationOut(BaseModel):
    id: str
    topic: str
    status: str
    start_time: str
    end_time: Optional[str] = None
    last_message_time: str = ""
    current_goal: Optional[str] = None
    summary: Optional[str] = None
    outcome: Optional[str] = None
    message_ids: list[str] = []
    key_points: list = []


class ConversationListOut(BaseModel):
    active: Optional[ConversationOut] = None
    closed: list[ConversationOut] = []
