"""
回复生成层 —— 将策略卡 + 上下文 → LLM 生成回复。

定位：策略选择（StrategySelector） → 回复生成（本模块） → 表达增强

设计原则：
- 用策略卡的 llm_instruction 作为核心行为指导
- 注入关系上下文和对话历史
- 单一 LLM 调用，返回回复文本 + 调试信息
"""

from __future__ import annotations

from typing import Callable, Optional

from .message_understanding import MessageState
from .strategy_loader import StrategyCard

LlmCallable = Callable[[str, str], str]


class ReplyGenerator:
    """回复生成器。根据策略卡和上下文构建 prompt，调用 LLM 生成回复。"""

    def __init__(self, relationship_state: Optional[dict] = None):
        self.rs = relationship_state or {}

    def generate(
        self,
        llm_call: LlmCallable,
        ms: MessageState,
        card: StrategyCard,
        goal_result: dict,
        chat_history: Optional[list[dict]] = None,
        my_last_message: Optional[str] = None,
        conversation_context: Optional[str] = None,
    ) -> dict:
        """生成回复。

        Args:
            llm_call: LLM 调用函数 (system_prompt, user_prompt) -> str
            ms: 消息理解结果
            card: 选中的策略卡
            goal_result: GoalPlanner.plan() 的输出
            chat_history: 对话历史 [{"role": "她/我", "content": "..."}]
            my_last_message: 我上一条发的消息

        Returns:
            {"reply": str, "strategy_used": str, "goal": str}
        """
        system_prompt = self._build_system_prompt(card, goal_result)
        user_prompt = self._build_user_prompt(ms, chat_history, my_last_message, conversation_context)

        reply = llm_call(system_prompt, user_prompt)
        return {
            "reply": reply.strip(),
            "strategy_used": card.name,
            "goal": goal_result["goal"],
        }

    # ============================================================
    # Prompt 构建
    # ============================================================

    def _build_system_prompt(self, card: StrategyCard, goal_result: dict) -> str:
        """构建系统提示词：角色 + 策略规则 + 示例。"""
        parts = []

        parts.append("你是一个恋爱沟通助手，正在帮用户回复女方的消息。")
        parts.append("你的目标不是讨好对方，而是建立健康、平等的互动关系。")
        parts.append("回复要自然、真诚，不要像机器人，不要过度使用'呢''哦''呀'等语气词。")
        parts.append("")

        # 当前目标
        goal_zh = goal_result.get("goal_zh", goal_result["goal"])
        parts.append(f"## 当前目标：{goal_zh}")
        parts.append("")

        # 策略机制
        if card.mechanism:
            parts.append(f"## 策略原理\n{card.mechanism}")
            parts.append("")

        # 策略规则
        if card.rules:
            parts.append("## 执行规则")
            for r in card.rules:
                parts.append(f"- {r}")
            parts.append("")

        # 反模式
        if card.anti_patterns:
            parts.append("## 绝对不能做的事")
            for a in card.anti_patterns:
                parts.append(f"- {a}")
            parts.append("")

        # LLM 指令（策略卡的核心）
        if card.llm_instruction:
            parts.append(f"## 核心指令\n{card.llm_instruction}")
            parts.append("")

        # 示例（最多 2 个）
        examples = card.examples[:2] if card.examples else []
        if examples:
            parts.append("## 参考示例")
            for i, ex in enumerate(examples, 1):
                inp = ex.get("input", "")
                resp = ex.get("response", "")
                parts.append(f"### 示例 {i}")
                parts.append(f"对方: {inp}")
                parts.append(f"回复: {resp}")
                if ex.get("why"):
                    parts.append(f"解析: {ex['why']}")
                parts.append("")

        parts.append("## 输出要求")
        parts.append("只输出你的回复文本，不要加引号、不要加说明、不要加'回复：'前缀。")
        parts.append("就像你真的在微信里打字一样自然。")

        return "\n".join(parts)

    def _build_user_prompt(
        self,
        ms: MessageState,
        chat_history: Optional[list[dict]],
        my_last_message: Optional[str],
        conversation_context: Optional[str] = None,
    ) -> str:
        """构建用户提示词：关系上下文 + 对话上下文 + 对话历史 + 她的消息。"""
        parts = []

        # 三层对话上下文（来自 context_builder.py）
        if conversation_context:
            parts.append(conversation_context)
            parts.append("")

        # 关系上下文
        parts.append("## 当前关系状态")
        parts.append(f"- 关系阶段: {self.rs.get('stage', '')}")
        parts.append(f"- 信任程度: {self.rs.get('trust_level', 0)}/100")
        parts.append(f"- 亲密程度: {self.rs.get('intimacy_level', 0)}/100")
        if self.rs.get("conflict_status", "none") != "none":
            parts.append(f"- 冲突状态: {self.rs['conflict_status']}（注意处理）")
        if self.rs.get("recent_events"):
            parts.append(f"- 近期事件: {', '.join(self.rs['recent_events'])}")
        parts.append("")

        # 我的上一条消息
        if my_last_message:
            parts.append(f"## 我上一条发的消息\n{my_last_message}")
            parts.append("")

        # 对话历史
        if chat_history:
            parts.append("## 对话历史（时间顺序）")
            for m in chat_history[-6:]:  # 最多 6 轮
                role = "她" if m["role"] == "她" else "我"
                parts.append(f"{role}: {m['content']}")
            parts.append("")

        # 她的消息 + 分析（供参考）
        parts.append("## 她的最新消息")
        parts.append(ms.message)
        parts.append("")
        parts.append("## 消息分析（供参考）")
        parts.append(f"- 表面意图: {', '.join(ms.intents_above(0.4))}")
        parts.append(f"- 情绪: {ms.emotion}（强度 {ms.emotion_intensity:.1f}）")
        top_needs = ms.needs_above(0.4)
        if top_needs:
            parts.append(f"- 需求信号: {', '.join(top_needs)}")
        parts.append(f"- 表达模式: {'一时冲动' if ms.is_impulse else '认真表达'}")
        parts.append("")

        parts.append("请生成回复：")

        return "\n".join(parts)
