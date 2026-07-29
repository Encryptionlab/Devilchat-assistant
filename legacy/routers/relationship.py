"""GET /api/relationship and PUT /api/relationship"""

from fastapi import APIRouter, Depends
from legacy.dependencies import get_state_service
from legacy.services.state_service import StateService
from legacy.schemas.relationship import RelationshipStateOut, RelationshipStateUpdate

router = APIRouter(prefix="/api", tags=["relationship"])


@router.get("/relationship", response_model=RelationshipStateOut)
async def get_relationship(state: StateService = Depends(get_state_service)):
    rs = await state.load_relationship_state()
    return RelationshipStateOut(**rs)


@router.put("/relationship", response_model=RelationshipStateOut)
async def update_relationship(
    update: RelationshipStateUpdate,
    state: StateService = Depends(get_state_service),
):
    rs = await state.load_relationship_state()
    if update.stage is not None:
        rs["stage"] = update.stage
    if update.temperature is not None:
        rs["temperature"] = update.temperature
    if update.trust_level is not None:
        rs["trust_level"] = update.trust_level
    if update.intimacy_level is not None:
        rs["intimacy_level"] = update.intimacy_level
    await state.save_relationship_state(rs)
    return RelationshipStateOut(**rs)
