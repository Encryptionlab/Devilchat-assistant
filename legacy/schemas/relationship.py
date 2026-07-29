"""Pydantic schemas for relationship state API."""

from pydantic import BaseModel, Field
from typing import Optional


class RelationshipStateOut(BaseModel):
    stage: str = ""
    temperature: str = ""
    attachment_style: Optional[str] = None
    trust_level: int = 0
    intimacy_level: int = 0
    conflict_status: str = "none"
    conflict_level: int = 0
    recurring_topics: list[str] = Field(default_factory=list)
    unresolved_topics: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    future_events: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    personality_traits: list[str] = Field(default_factory=list)


class RelationshipStateUpdate(BaseModel):
    stage: Optional[str] = None
    temperature: Optional[str] = None
    trust_level: Optional[int] = None
    intimacy_level: Optional[int] = None
