"""FastAPI dependency injection — singleton services created at startup."""

from backend.services.llm_service import LlmService
from backend.services.state_service import StateService

_llm_service: LlmService | None = None
_state_service: StateService | None = None


def get_llm_service() -> LlmService:
    assert _llm_service is not None, "LlmService not initialized"
    return _llm_service


def get_state_service() -> StateService:
    assert _state_service is not None, "StateService not initialized"
    return _state_service


def init_services() -> None:
    global _llm_service, _state_service
    _llm_service = LlmService()
    _state_service = StateService()
