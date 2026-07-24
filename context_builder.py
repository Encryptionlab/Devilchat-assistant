"""
上下文构建器 —— 将长期记忆 + 当前对话 + 最近消息组装为 LLM 上下文。

定位（来自 CONVERSATION_ENGINE_DESIGN_v2_MVP.md Section 8）：
    conversation.py → context_builder.py（本模块）→ strategy_selector / reply_generator

设计原则：
- 三层精选：Relationship Memory + Current Conversation + Latest Messages
- Token 预算 ~2000（Memory 600 + Conversation 200 + Messages 1200）
- 不替代任何模块，只做组装

用法：
    >>> builder = ContextBuilder(relationship_state, conversation, messages)
    >>> ctx = builder.build()
    >>> formatted = builder.format_for_llm(ctx)
"""

from __future__ import annotations

from typing import Any, Optional


class ContextBuilder:
    """三层上下文构建器。

    输入：长期记忆（relationship_state.json）+ 当前 Conversation + 最近消息
    输出：结构化的 LLM 上下文 dict + 格式化的 prompt 字符串
    """

    def __init__(
        self,
        relationship_state: dict[str, Any],
        conversation: Any | None = None,   # Conversation | None，避免循环导入
        recent_messages: list[dict] | None = None,
    ):
        self._rs = relationship_state
        self._conv = conversation
        self._messages = recent_messages or []

    def build(self) -> dict[str, Any]:
        """构建三层上下文 dict。

        Returns:
            {
                "relationship_memory": {...},   # 长期关系状态
                "current_conversation": {...} | None,  # 当前对话（如果有活跃的）
                "latest_messages": [...],       # 最近 6 条消息
            }
        """
        return {
            "relationship_memory": self._build_memory(),
            "current_conversation": self._build_conversation(),
            "latest_messages": self._messages[-6:],
        }

    def format_for_llm(self, ctx: dict[str, Any] | None = None) -> str:
        """将上下文格式化为 LLM prompt 友好的字符串。

        Args:
            ctx: build() 的输出。None 则内部调 build()。

        Returns:
            可直接拼入 user_prompt 的文本块。
        """
        if ctx is None:
            ctx = self.build()

        parts: list[str] = []

        # ---- Layer 1: 长期关系记忆 ----
        memory = ctx.get("relationship_memory", {})
        if memory:
            parts.append("## 长期关系记忆（Relationship Memory）")
            stage = memory.get("stage", "")
            temperature = memory.get("temperature", "")
            if stage:
                parts.append(f"- 关系阶段: {stage}")
            if temperature:
                parts.append(f"- 关系热度: {temperature}")
            if memory.get("attachment_style"):
                parts.append(f"- 对方依恋风格: {memory['attachment_style']}")
            if memory.get("trust_level") is not None:
                parts.append(f"- 信任程度: {memory['trust_level']}/100")
            if memory.get("intimacy_level") is not None:
                parts.append(f"- 亲密程度: {memory['intimacy_level']}/100")
            if memory.get("conflict_status") and memory["conflict_status"] != "none":
                parts.append(f"- 冲突状态: {memory['conflict_status']}")

            recurring = memory.get("recurring_topics", [])
            if recurring:
                parts.append(f"- 反复出现的话题: {', '.join(recurring)}")

            unresolved = memory.get("unresolved_topics", [])
            if unresolved:
                parts.append(f"- 未解决的问题: {', '.join(unresolved)}")

            events = memory.get("recent_events", [])
            if events:
                parts.append(f"- 近期关键事件: {', '.join(events)}")

            parts.append("")

        # ---- Layer 2: 当前对话 ----
        conv = ctx.get("current_conversation")
        if conv:
            parts.append("## 当前对话（Current Conversation）")
            if conv.get("topic"):
                parts.append(f"- 话题: {conv['topic']}")
            if conv.get("current_goal"):
                parts.append(f"- 当前目标: {conv['current_goal']}")
            if conv.get("summary"):
                parts.append(f"- 前情摘要: {conv['summary']}")
            parts.append("")

        # ---- Layer 3: 最近消息 ----
        messages = ctx.get("latest_messages", [])
        if messages:
            parts.append("## 最近消息（Latest Messages）")
            for m in messages:
                role = "她" if m.get("role") == "她" else "我"
                parts.append(f"{role}: {m['content']}")
            parts.append("")

        return "\n".join(parts)

    # ---- 内部构建方法 ----

    def _build_memory(self) -> dict[str, Any]:
        """从 relationship_state 提取长期记忆。"""
        return {
            "stage": self._rs.get("stage", ""),
            "temperature": self._rs.get("temperature", ""),
            "attachment_style": self._rs.get("attachment_style"),
            "trust_level": self._rs.get("trust_level"),
            "intimacy_level": self._rs.get("intimacy_level"),
            "conflict_status": self._rs.get("conflict_status", "none"),
            "recurring_topics": self._rs.get("recurring_topics", []),
            "unresolved_topics": self._rs.get("unresolved_topics", []),
            "recent_events": self._rs.get("recent_events", []),
            "personality_traits": self._rs.get("personality_traits", []),
            "preferences": self._rs.get("preferences", []),
            "future_events": self._rs.get("future_events", []),
        }

    def _build_conversation(self) -> dict[str, Any] | None:
        """从当前 Conversation 提取上下文（仅 active 状态）。"""
        if self._conv is None:
            return None

        # 检查是否活跃（duck typing：避免导入 Conversation 类）
        if hasattr(self._conv, "status") and getattr(self._conv, "status") != "active":
            return None

        return {
            "topic": getattr(self._conv, "topic", None),
            "current_goal": getattr(self._conv, "current_goal", None),
            "summary": getattr(self._conv, "summary", None),
            "start_time": getattr(self._conv, "start_time", None),
        }


# ============================================================
# 便捷函数：从 file 路径加载 relationship_state 并构建上下文
# ============================================================

def build_context_from_file(
    relationship_state_path: str,
    conversation: Any | None = None,
    messages: list[dict] | None = None,
) -> ContextBuilder:
    """从 relationship_state.json 文件路径创建 ContextBuilder。

    Args:
        relationship_state_path: relationship_state.json 的路径
        conversation: 当前 Conversation 对象
        messages: 最近消息列表

    Returns:
        已初始化的 ContextBuilder 实例
    """
    import json
    from pathlib import Path

    path = Path(relationship_state_path)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        rs = raw.get("relationship_state", raw)
    else:
        rs = {}

    return ContextBuilder(rs, conversation, messages)
