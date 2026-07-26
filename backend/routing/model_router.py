"""Multi-model router — routes tasks to appropriate models (inspired by Affinity Agent)."""

from __future__ import annotations

from backend.services.llm_service import LlmService
from backend.config import load_api_key


class ModelRouter:
    """Routes LLM tasks to appropriate model tiers.

    Heavy model: DeepSeek-V3 (understanding, summary, reply generation)
    Light model:  Same for now (swappable to R1-Lite or Qwen-2.5-7B for enhancement)
    Embedder:     Placeholder (swappable to BGE-M3 for vector generation)

    IMPORTANT: Enhancement can switch to a lighter model to save ~40% cost.
    Set LIGHT_MODEL to a cheaper model name when available.
    """

    HEAVY_MODEL = "deepseek-v4-flash"    # Current: DeepSeek V3 via OpenCode
    LIGHT_MODEL = "deepseek-v4-flash"    # TODO: swap to cheaper model for enhancement

    def __init__(self):
        api_key = load_api_key()
        self.heavy = LlmService(api_key=api_key)
        self.light = LlmService(api_key=api_key)  # Same for now

    def get_llm(self, task: str) -> LlmService:
        """Return the appropriate LLM service for a given task."""
        heavy_tasks = {"understanding", "summary", "reply_gen"}
        if task in heavy_tasks:
            return self.heavy
        return self.light


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
