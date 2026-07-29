"""FastAPI dependency injection — singleton services created at startup."""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.services.llm_service import LlmService
from legacy.services.state_service import StateService
from backend.config import CONV_PATH, RS_PATH

_llm_service: LlmService | None = None
_state_service: StateService | None = None


def get_llm_service() -> LlmService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LlmService()
    return _llm_service


def get_state_service() -> StateService:
    global _state_service
    if _state_service is None:
        _state_service = StateService()
    return _state_service


def _run_startup_decay() -> None:
    """启动时对长期记忆执行衰减清理。

    - recurring_topics: 30 天降权，60 天移除
    - recent_events: FIFO 已保证 ≤10 条，额外清理超过 60 天未更新的残留
    """
    if not RS_PATH.exists():
        return
    try:
        from src.memory_updater import MemoryUpdater

        updater = MemoryUpdater(relationship_state_path=RS_PATH)
        recurring = updater.state.get("recurring_topics", [])
        if not recurring:
            return

        # 计算每个 recurring topic 的最近出现天数
        ages: dict[str, int] = {}
        today = datetime.now(timezone.utc).date()
        if CONV_PATH.exists():
            convs = json.loads(CONV_PATH.read_text(encoding="utf-8"))
            all_closed = convs.get("closed", [])
            for topic in recurring:
                last_date = None
                for c in reversed(all_closed):
                    if c.get("topic") == topic:
                        try:
                            end_ts = c.get("end_time", "") or c.get("start_time", "")
                            last_date = datetime.fromisoformat(end_ts).date()
                        except (ValueError, TypeError):
                            continue
                        break
                if last_date:
                    ages[topic] = (today - last_date).days
                else:
                    ages[topic] = 999  # 从未出现过 → 立即清理

        result = updater.apply_decay(ages)
        if result["applied_rules"]:
            updater.save()
            print(f"[startup] Memory decay applied: {result['applied_rules']}")
    except Exception as e:
        print(f"[startup] Memory decay skipped: {e}")


def init_services() -> None:
    global _llm_service, _state_service
    _llm_service = LlmService()
    _state_service = StateService()
    _run_startup_decay()
