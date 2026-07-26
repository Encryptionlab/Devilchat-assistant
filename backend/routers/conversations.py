"""GET /api/conversations and GET /api/conversations/{id}"""

from fastapi import APIRouter, Depends
from backend.dependencies import get_state_service
from backend.services.state_service import StateService

router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations")
async def list_conversations(state: StateService = Depends(get_state_service)):
    data = await state.load_conversations()
    return data


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, state: StateService = Depends(get_state_service)):
    data = await state.load_conversations()
    active = data.get("active")
    if active and active.get("id") == conv_id:
        return active
    for c in data.get("closed", []):
        if c.get("id") == conv_id:
            return c
    return {"error": "not found"}
