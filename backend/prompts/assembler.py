"""Layered prompt assembler — modular prompt blocks (inspired by AI-GF-python)."""

from __future__ import annotations

from datetime import datetime


class PromptAssembler:
    """Assembles prompts from reusable blocks. Each block is independently
    maintainable and can be included/excluded per LLM call."""

    def __init__(self, relationship_state: dict | None = None):
        self.rs = relationship_state or {}

    # ---- Public API ----

    def assemble_understanding(self, messages_text: str) -> str:
        return "\n\n".join([
            self._persona(),
            self._relationship(),
            self._time_context(),
            messages_text,
        ])

    def assemble_reply(self, strategy_block: str, evidence_block: str, context: str) -> str:
        parts = [
            self._persona(),
            self._relationship(),
            self._time_context(),
            strategy_block,
        ]
        if evidence_block:
            parts.append(evidence_block)
        parts.append(context)
        return "\n\n".join(parts)

    def assemble_summary(self, conversation_text: str) -> str:
        return "\n\n".join([
            self._persona(),
            self._relationship(),
            conversation_text,
        ])

    # ---- Reusable Blocks ----

    def _persona(self) -> str:
        stage = self.rs.get("stage", "acquaintance")
        stage_guide = {
            "acquaintance": "保持礼貌和适度距离，不越界",
            "ambiguous": "可以适度暧昧但不过度表白",
            "intimate": "可以表达亲密感和承诺",
        }
        guide = stage_guide.get(stage, stage_guide["acquaintance"])
        return f"""## 角色设定
你是一个情感陪伴助手，帮助用户分析对话并提供回复建议。
当前关系阶段：{stage}。行为准则：{guide}。"""

    def _relationship(self) -> str:
        trust = self.rs.get("trust_level", 50)
        intimacy = self.rs.get("intimacy_level", 30)
        conflict = self.rs.get("conflict_level", 0)
        events = self.rs.get("近期关键事件", [])
        events_text = "\n".join(f"- {e}" for e in events[-5:]) if events else "无"
        return f"""## 关系状态
- 信任度: {trust}/100
- 亲密程度: {intimacy}/100
- 冲突等级: {conflict}/5（0=无冲突，5=严重冲突）
- 近期关键事件:
{events_text}"""

    def _time_context(self) -> str:
        hour = datetime.now().hour
        if 23 <= hour or hour < 5:
            guide = "当前是深夜。对方可能希望轻松或温暖的收尾。避免深入讨论沉重话题。"
        elif 5 <= hour < 9:
            guide = "当前是早晨。适合简短问候和一天的轻松开场。"
        elif 9 <= hour < 18:
            guide = "当前是白天。适合正常对话节奏。"
        else:
            guide = "当前是晚间。对方可能结束一天后比较疲惫，适合关心和倾诉。"
        return f"## 时间上下文\n{guide}"

    def _strategy(self, card: dict | None) -> str:
        if not card:
            return ""
        return f"""## 当前策略
- 策略名称: {card.get('name', '')}
- 策略目标: {card.get('goal', '')}
- 风险等级: {card.get('risk_level', 'low')}"""

    def _evidence(self, memories: list[dict] | None) -> str:
        if not memories:
            return ""
        lines = [f"- [{m.get('memory_type', '')}] {m.get('content', '')} (置信度: {m.get('confidence', 0):.0%})"
                 for m in memories[:5]]
        return "## 相关记忆\n" + "\n".join(lines)
