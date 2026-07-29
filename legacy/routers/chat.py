"""POST /api/chat and POST /api/chat/stream"""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from legacy.dependencies import get_llm_service, get_state_service
from legacy.schemas.chat import ChatRequest, ChatResponse
from legacy.services.pipeline_service import PipelineService

router = APIRouter(prefix="/api", tags=["chat"])


def _get_pipeline() -> PipelineService:
    from legacy.dependencies import get_llm_service, get_state_service
    return PipelineService(get_llm_service(), get_state_service())


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Non-streaming chat: full pipeline, returns complete response."""
    pipeline = _get_pipeline()
    chat_history = [{"role": m.role, "content": m.content} for m in req.chat_history]
    result = await pipeline.process_message(req.message, chat_history)
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat: SSE events for each pipeline step + token-by-token reply."""
    pipeline = _get_pipeline()
    chat_history = [{"role": m.role, "content": m.content} for m in req.chat_history]

    return StreamingResponse(
        pipeline.process_message_stream(req.message, chat_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
