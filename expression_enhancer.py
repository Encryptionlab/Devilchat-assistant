"""
表达增强层 —— 在不改变语义的前提下，优化回复的表达方式。

定位：回复生成（ReplyGenerator） → 表达增强（本模块） → 风险检查

设计原则：
- 只做语言层面的润色，不改语义、不改策略方向
- 根据关系阶段调整语气（刚认识多礼貌，暧昧期多温度）
- 轻量级，一次 LLM 调用
"""

from __future__ import annotations

from typing import Callable, Optional

from message_understanding import MessageState
from strategy_loader import StrategyCard

LlmCallable = Callable[[str, str], str]

# 关系阶段 → 语气指导
STAGE_TONE: dict[str, str] = {
    "stranger":      "礼貌、有分寸，不越界，像初次见面的陌生人",
    "acquaintance":  "友好但保持适当距离，不急于拉近关系",
    "ambiguous":     "温暖、略带暧昧，但不说透，留有余地",
    "dating":        "亲密、自然，可以适度表达喜欢",
    "stable":        "稳定、踏实，像老夫老妻的日常对话",
    "conflict":      "冷静、克制，不激化矛盾，给双方留台阶",
}


class ExpressionEnhancer:
    """表达增强器。润色回复文本，不改变语义。"""

    def __init__(self, relationship_state: Optional[dict] = None):
        self.rs = relationship_state or {}

    def enhance(
        self,
        llm_call: LlmCallable,
        raw_reply: str,
        ms: MessageState,
        card: Optional[StrategyCard] = None,
    ) -> dict:
        """润色回复表达。

        Args:
            llm_call: LLM 调用函数
            raw_reply: 原始回复文本
            ms: 消息理解结果
            card: 使用的策略卡（可选，用于了解风险约束）

        Returns:
            {"enhanced_reply": str}
        """
        system_prompt = self._build_system_prompt(card)
        user_prompt = self._build_user_prompt(raw_reply, ms)

        enhanced = llm_call(system_prompt, user_prompt)
        return {"enhanced_reply": enhanced.strip()}

    def _build_system_prompt(self, card: Optional[StrategyCard] = None) -> str:
        stage = self.rs.get("stage", "acquaintance")
        tone_guide = STAGE_TONE.get(stage, "自然、真诚")

        parts = [
            "你是一个文字润色助手，负责把生硬的回复改成自然的聊天语气。",
            "",
            "## 核心原则",
            "- 保持原意不变：不增删关键信息，不改策略方向",
            "- 去机器人感：去掉过于正式、书面化的表达",
            "- 像真人聊天：可以加适当的语气词，但不过度",
            "",
            f"## 当前关系阶段：{stage}",
            f"语气要求：{tone_guide}",
            "",
            "## 具体做法",
            "- 太长的句子拆短，太短的句子适当扩展",
            "- 过于书面化的词换成口语（如'确实如此'→'确实'）",
            "- 可以加适当的表情或语气词，但每句话不超过1个",
            "- 不要加[笑哭][捂脸]这类方括号表情（原始回复中已有的保留）",
            "- 不要改变人称和指代",
            "- 不要添加新的实质内容",
        ]

        if card and card.risk_level == "high":
            parts.append(f"- 注意：当前使用高风险策略（{card.name}），表达要留有退路，不能把话说死")

        parts.append("")
        parts.append("## 输出要求")
        parts.append("只输出润色后的回复文本，不要加引号、不要加说明。")

        return "\n".join(parts)

    def _build_user_prompt(self, raw_reply: str, ms: MessageState) -> str:
        parts = [
            f"## 她的消息\n{ms.message}",
            f"## 她的情绪\n{ms.emotion}（强度 {ms.emotion_intensity:.1f}）",
            "",
            f"## 原始回复（需要润色）\n{raw_reply}",
            "",
            "请输出润色后的回复：",
        ]
        return "\n".join(parts)
