"""LangGraph StateGraph definition — maps the 9-step pipeline to graph nodes."""

from __future__ import annotations

from typing import TypedDict, Optional


class PipelineState(TypedDict, total=False):
    # Input
    messages: list[dict]
    mode: str  # "observe" | "intervene"
    contact_id: str

    # Message Understanding output
    emotion: str
    emotion_intensity: float
    dominant_intent: str
    topic: str
    need_scores: dict
    burst_pattern: str
    trajectory_note: str
    conversation_stage: str

    # Need Recognition output
    top_needs: list
    dominant_need: str

    # Goal Planning output
    goal: str
    goal_zh: str

    # Conversation Engine output
    conversation_id: Optional[str]
    conversation_switched: bool
    closed_conversation: Optional[dict]

    # Context retrieval
    recalled_memories: list
    llm_context: str

    # Strategy Selection output
    strategy_name: str
    strategy_card: dict

    # Reply Generation output
    reply: str
    enhanced_reply: str

    # Debug / error
    debug: dict
    error: Optional[str]
