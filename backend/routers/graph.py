"""Graph-based pipeline endpoints — LangGraph StateGraph execution."""

import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.graph.builder import get_graph

router = APIRouter(prefix="/api/graph", tags=["graph"])


class ChatRequest(BaseModel):
    message: str
    chat_history: list[dict] = []
    contact_id: str = "default"


class ObserveRequest(BaseModel):
    messages: list[dict]
    contact_id: str = "default"
    trigger_evaluator: bool = True


@router.post("/chat")
async def graph_chat(req: ChatRequest):
    """Run the full LangGraph pipeline (non-streaming)."""
    try:
        from backend.db import resolve_contact_id
        graph = get_graph()

        contact_id = await resolve_contact_id(req.contact_id)
        messages = list(req.chat_history) + [{"role": "她", "content": req.message}]
        initial_state = {
            "messages": messages,
            "mode": "intervene",
            "contact_id": contact_id,
        }

        config = {"configurable": {"thread_id": contact_id}}
        result = await graph.ainvoke(initial_state, config)

        return {
            "reply": result.get("reply", ""),
            "enhanced_reply": result.get("enhanced_reply", ""),
            "strategy_name": result.get("strategy_name", ""),
            "goal": result.get("goal", ""),
            "goal_zh": result.get("goal_zh", ""),
            "conversation_switched": result.get("conversation_switched", False),
            "closed_conversation": result.get("closed_conversation"),
            "debug": result.get("debug", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def graph_chat_stream(req: ChatRequest):
    """Run the full LangGraph pipeline with streaming SSE output."""
    from backend.db import resolve_contact_id
    graph = get_graph()

    contact_id = await resolve_contact_id(req.contact_id)
    messages = list(req.chat_history) + [{"role": "她", "content": req.message}]
    initial_state = {
        "messages": messages,
        "mode": "intervene",
        "contact_id": contact_id,
    }

    config = {"configurable": {"thread_id": contact_id}}

    async def _stream():
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def _run():
            try:
                async for event in graph.astream(initial_state, config):
                    node_name = list(event.keys())[0] if event else ""
                    node_data = event.get(node_name, {})

                    if node_name == "message_understanding":
                        queue.put_nowait(_sse("step", {"step": "message_understanding", "status": "done"}))
                    elif node_name == "strategy_select":
                        queue.put_nowait(_sse("step", {"step": "strategy_select", "status": "done",
                                                        "strategy": node_data.get("strategy_name", "")}))
                    elif node_name == "reply_generate":
                        reply = node_data.get("reply", "")
                        if reply:
                            queue.put_nowait(_sse("reply", {"text": reply}))
                    elif node_name == "enhance_reply":
                        enhanced = node_data.get("enhanced_reply", "")
                        if enhanced:
                            queue.put_nowait(_sse("enhanced_reply", {"text": enhanced}))
                    elif node_name == "persist_result":
                        queue.put_nowait(_sse("done", {
                            "reply": node_data.get("reply", ""),
                            "enhanced_reply": node_data.get("enhanced_reply", ""),
                            "strategy_name": node_data.get("strategy_name", ""),
                            "goal": node_data.get("goal", ""),
                            "goal_zh": node_data.get("goal_zh", ""),
                            "conversation_switched": node_data.get("conversation_switched", False),
                        }))
            except Exception as e:
                queue.put_nowait(_sse("error", {"error": str(e)}))
            finally:
                queue.put_nowait(None)

        asyncio.create_task(_run())

        while True:
            sse_line = await queue.get()
            if sse_line is None:
                break
            yield sse_line

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/observe")
async def graph_observe(req: ObserveRequest):
    """Run the observation track through the LangGraph pipeline."""
    try:
        from backend.db import resolve_contact_id
        graph = get_graph()

        contact_id = await resolve_contact_id(req.contact_id)
        initial_state = {
            "messages": req.messages,
            "mode": "observe",
            "contact_id": contact_id,
        }

        config = {"configurable": {"thread_id": contact_id}}
        result = await graph.ainvoke(initial_state, config)

        return {
            "conversation_switched": result.get("conversation_switched", False),
            "closed_conversation": result.get("closed_conversation"),
            "emotion": result.get("emotion", ""),
            "topic": result.get("topic", ""),
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
