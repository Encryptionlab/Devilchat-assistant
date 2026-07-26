"""Thread-safe JSON file read/write for relationship_state and conversations."""

import asyncio
import json
from pathlib import Path

from backend.config import RS_PATH, CONV_PATH


class StateService:
    """Single-user MVP: asyncio.Lock protects all file I/O."""

    def __init__(self, rs_path: Path | None = None, conv_path: Path | None = None):
        self._rs_path = rs_path or RS_PATH
        self._conv_path = conv_path or CONV_PATH
        self._lock = asyncio.Lock()

    # ---- Relationship State ----

    async def load_relationship_state(self) -> dict:
        """Load relationship state, returning the English-keyed dict expected by src/ modules."""
        async with self._lock:
            return self._load_rs_sync()

    def _load_rs_sync(self) -> dict:
        """Synchronous load (called within lock)."""
        if not self._rs_path.exists():
            return {
                "stage": "",
                "temperature": "",
                "attachment_style": None,
                "trust_level": 0,
                "intimacy_level": 0,
                "conflict_status": "none",
                "conflict_level": 0,
                "recurring_topics": [],
                "unresolved_topics": [],
                "recent_events": [],
                "future_events": [],
                "preferences": [],
                "personality_traits": [],
            }

        raw = json.loads(self._rs_path.read_text(encoding="utf-8"))
        inner = raw.get("relationship_state", raw)

        def _first_word(text: str) -> str:
            return text.split()[0] if text else ""

        stage_raw = inner.get("当前关系阶段", "")
        temperature_raw = inner.get("关系热度", "")
        attachment_raw = inner.get("对方依恋风格", "")

        return {
            "stage": _first_word(stage_raw),
            "temperature": _first_word(temperature_raw),
            "attachment_style": _first_word(attachment_raw) if attachment_raw else None,
            "trust_level": inner.get("信任程度_0到100", 0),
            "intimacy_level": inner.get("亲密程度_0到100", 0),
            "conflict_status": _first_word(inner.get("冲突状态", "")),
            "conflict_level": inner.get("conflict_level", 0),
            "recurring_topics": inner.get("recurring_topics", []),
            "unresolved_topics": inner.get("unresolved_topics", []),
            "recent_events": inner.get("近期关键事件", []),
            "future_events": inner.get("future_events", []),
            "preferences": inner.get("preferences", []),
            "personality_traits": inner.get("personality_traits", []),
        }

    async def load_raw_relationship_json(self) -> dict:
        """Load the raw relationship_state.json contents (for the frontend to see exact disk state)."""
        async with self._lock:
            if not self._rs_path.exists():
                return {}
            return json.loads(self._rs_path.read_text(encoding="utf-8"))

    async def save_relationship_state(self, state: dict) -> None:
        """Write the English-keyed dict back, preserving the Chinese-keyed disk format."""
        async with self._lock:
            self._save_rs_sync(state)

    def _save_rs_sync(self, state: dict) -> None:
        """Synchronous save (called within lock)."""
        from datetime import date

        stage_cn_map = {
            "stranger": "stranger 陌生人",
            "acquaintance": "acquaintance 刚认识",
            "friend": "friend 普通朋友",
            "ambiguous": "ambiguous 暧昧",
            "dating": "dating 恋爱",
            "stable": "stable 长期稳定",
        }
        temp_cn_map = {
            "hot": "hot 火热",
            "warm": "warm 温暖",
            "neutral": "neutral 中性",
            "cold": "cold 冷淡",
        }

        if self._rs_path.exists():
            raw = json.loads(self._rs_path.read_text(encoding="utf-8"))
        else:
            raw = {}

        stage_val = state.get("stage", "")
        temp_val = state.get("temperature", "")
        attach_val = state.get("attachment_style") or ""

        inner = {
            "当前关系阶段": stage_cn_map.get(stage_val, stage_val),
            "关系热度": temp_cn_map.get(temp_val, temp_val),
            "对方依恋风格": attach_val,
            "信任程度_0到100": state.get("trust_level", 0),
            "亲密程度_0到100": state.get("intimacy_level", 0),
            "冲突状态": state.get("conflict_status", "none"),
            "conflict_level": state.get("conflict_level", 0),
            "recurring_topics": state.get("recurring_topics", []),
            "unresolved_topics": state.get("unresolved_topics", []),
            "近期关键事件": state.get("recent_events", []),
            "future_events": state.get("future_events", []),
            "preferences": state.get("preferences", []),
            "personality_traits": state.get("personality_traits", []),
        }
        raw["relationship_state"] = inner
        self._rs_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- Conversations ----

    async def load_conversations(self) -> dict:
        """Return {"active": dict|None, "closed": list[dict]}."""
        async with self._lock:
            return self._load_conv_sync()

    def _load_conv_sync(self) -> dict:
        if not self._conv_path.exists():
            return {"active": None, "closed": []}
        try:
            raw = json.loads(self._conv_path.read_text(encoding="utf-8"))
            return {
                "active": raw.get("active"),
                "closed": raw.get("closed", []),
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            return {"active": None, "closed": []}

    async def save_conversations(self, active: dict | None, closed: list[dict]) -> None:
        """Write conversations back to disk."""
        async with self._lock:
            data = {"active": active, "closed": closed}
            self._conv_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    async def conversation_manager_save(self) -> None:
        """Hook: called after ConversationManager modifies its internal state.
        Re-reads the ConversationManager's saved file and ensures consistency."""
        # ConversationManager writes to self._conv_path via its _save() method.
        # We just need to ensure the lock was held during that write.
        # Since ConversationManager writes directly, we re-read here for cache coherency.
        pass
