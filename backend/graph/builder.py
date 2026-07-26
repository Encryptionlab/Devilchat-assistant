"""LangGraph StateGraph builder — assembles the 10-node pipeline with conditional edges."""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.state import PipelineState
from backend.graph.nodes import (
    message_understanding_node,
    need_recognition_node,
    goal_planning_node,
    conversation_engine_node,
    summarize_and_extract_node,
    dedup_and_persist_node,
    retrieve_context_node,
    strategy_select_node,
    reply_generate_node,
    enhance_reply_node,
    persist_result_node,
)


def build_graph() -> StateGraph:
    """Build and compile the pipeline StateGraph."""

    builder = StateGraph(PipelineState)

    # Add all nodes
    builder.add_node("message_understanding", message_understanding_node)
    builder.add_node("need_recognition", need_recognition_node)
    builder.add_node("goal_planning", goal_planning_node)
    builder.add_node("conversation_engine", conversation_engine_node)
    builder.add_node("summarize_and_extract", summarize_and_extract_node)
    builder.add_node("dedup_and_persist", dedup_and_persist_node)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("strategy_select", strategy_select_node)
    builder.add_node("reply_generate", reply_generate_node)
    builder.add_node("enhance_reply", enhance_reply_node)
    builder.add_node("persist_result", persist_result_node)

    # Entry point
    builder.set_entry_point("message_understanding")

    # Linear edges for the first 4 steps
    builder.add_edge("message_understanding", "need_recognition")
    builder.add_edge("need_recognition", "goal_planning")
    builder.add_edge("goal_planning", "conversation_engine")

    # Conditional: conversation closed?
    def _should_summarize(state: PipelineState) -> str:
        if state.get("conversation_switched") and state.get("closed_conversation"):
            return "summarize_and_extract"
        return "retrieve_context"

    builder.add_conditional_edges(
        "conversation_engine",
        _should_summarize,
        {
            "summarize_and_extract": "summarize_and_extract",
            "retrieve_context": "retrieve_context",
        }
    )

    # Summarize → dedup → context
    builder.add_edge("summarize_and_extract", "dedup_and_persist")
    builder.add_edge("dedup_and_persist", "retrieve_context")

    # Conditional: observe mode skips reply generation
    def _should_intervene(state: PipelineState) -> str:
        if state.get("error"):
            return END
        if state.get("mode") == "observe":
            return END
        return "strategy_select"

    builder.add_conditional_edges(
        "retrieve_context",
        _should_intervene,
        {
            "strategy_select": "strategy_select",
            END: END,
        }
    )

    # Intervention path
    builder.add_edge("strategy_select", "reply_generate")

    # Conditional: if strategy_select set an error, skip to end
    def _after_strategy(state: PipelineState) -> str:
        if state.get("error"):
            return END
        return "enhance_reply"

    builder.add_conditional_edges(
        "strategy_select",
        _after_strategy,
        {"enhance_reply": "enhance_reply", END: END},
    )

    builder.add_edge("enhance_reply", "persist_result")
    builder.add_edge("persist_result", END)

    # Compile with in-memory checkpointer (swap to PostgresSaver for production)
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# Singleton graph instance
_graph: StateGraph | None = None


def get_graph() -> StateGraph:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
