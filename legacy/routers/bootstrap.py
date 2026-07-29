"""POST /api/bootstrap — first-time relationship setup."""

import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from legacy.dependencies import get_llm_service, get_state_service
from backend.services.llm_service import LlmService
from legacy.services.state_service import StateService

from src.bootstrap import EXTRACTION_PROMPT, _strip_fence, _minimal_default, _stage_to_cn, _temperature_to_cn, _today


router = APIRouter(prefix="/api", tags=["bootstrap"])


class BootstrapRequest(BaseModel):
    description: str


@router.post("/bootstrap")
async def bootstrap(
    req: BootstrapRequest,
    llm: LlmService = Depends(get_llm_service),
    state: StateService = Depends(get_state_service),
):
    description = req.description.strip()
    if not description:
        return {"error": "请至少说几句，我好了解你们的情况"}

    try:
        llm_output = await llm.chat(EXTRACTION_PROMPT, description)
        data = json.loads(_strip_fence(llm_output))
    except Exception as e:
        data = _minimal_default()

    data.setdefault("stage", "acquaintance")
    data.setdefault("temperature", "neutral")
    data.setdefault("attachment_style", None)
    data.setdefault("trust_level", 30)
    data.setdefault("intimacy_level", 20)
    data.setdefault("conflict_status", "none")
    data.setdefault("recent_events", [])

    rs = {
        "stage": data["stage"],
        "temperature": data["temperature"],
        "attachment_style": data.get("attachment_style"),
        "trust_level": data["trust_level"],
        "intimacy_level": data["intimacy_level"],
        "conflict_status": data["conflict_status"],
        "conflict_level": 0,
        "recurring_topics": [],
        "unresolved_topics": [],
        "recent_events": data["recent_events"],
        "future_events": [],
        "preferences": [],
        "personality_traits": [],
    }
    await state.save_relationship_state(rs)

    return {
        "stage": data["stage"],
        "temperature": data["temperature"],
        "trust_level": data["trust_level"],
        "intimacy_level": data["intimacy_level"],
        "conflict_status": data["conflict_status"],
        "recent_events": data["recent_events"],
    }
