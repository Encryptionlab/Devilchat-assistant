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
        burst_analysis: Optional[dict] = None,
    ) -> dict:
        """生成回复。

        Args:
            llm_call: LLM 调用函数 (system_prompt, user_prompt) -> str
            ms: 消息理解结果
            card: 选中的策略卡
            goal_result: GoalPlanner.plan() 的输出
            chat_history: 对话历史 [{"role": "她/我", "content": "..."}]
            my_last_message: 我上一条发的消息
            burst_analysis: burst 分析 {"pattern": "burst|single|mixed", "msg_count": int, "her_msgs": [str]}

        Returns:
            {"reply": str, "strategy_used": str, "goal": str}
        """
        system_prompt = self._build_system_prompt(card, goal_result, burst_analysis)
        user_prompt = self._build_user_prompt(ms, chat_history, my_last_message, conversation_context, burst_analysis)

        reply = llm_call(system_prompt, user_prompt)
        return {
            "reply": reply.strip(),
            "strategy_used": card.name,
            "goal": goal_result["goal"],
        }

    # ============================================================
    # Prompt 构建
    # ============================================================

    def _build_system_prompt(self, card: StrategyCard, goal_result: dict, burst_analysis: dict | None = None) -> str:
        """构建系统提示词：角色 + 策略规则 + 示例。"""
        parts = []

        # 身份：你是用户本人，不是一个助手
        parts.append("你就是「我」本人，正在用微信回复女朋友的消息。")
        parts.append("你不是助手、不是客服、不是心理医生。你就是她男朋友。")
        parts.append("用你自己的口吻说话，不要像在完成任务，不要像在写作文。")
        parts.append("")
        parts.append("## 微信聊天铁律（刻在脑子里）")
        parts.append("- 打字分段用换行，不要用标点符号刻意断句。句号能省则省")
        parts.append("- 可以只说半句话，可以加「...」，可以空格代替标点")
        parts.append("- 绝对禁止：首先/其次/最后/第一/第二/综上所述/总的来说")
        parts.append("- 绝对禁止：你说得对/我理解你的感受/我认真听了/我记住了（太假了）")
        parts.append("- 不要复述她刚才说过的话，直接回应，她知道自己说了什么")
        parts.append("- 不要给她的话贴标签（「你这个想法很成熟」「你这样说很有道理」）")
        parts.append("- 不要在回复里发明她没说过的事实或绰号")
        parts.append("- 她愤怒的时候不要冷静分析，她累的时候不要写小作文")
        parts.append("- 像真人在打字：想到哪说到哪，不用把每个话题都照顾得整整齐齐")
        parts.append("- 不要过度使用'呢''哦''呀'，但也不要完全去掉，用在该用的地方")
        parts.append("")
        parts.append("## 你的真实说话风格（必须模仿）")
        parts.append("以下是你在微信里真实的说话方式，你的回复必须和这些消息的风格一致：")
        parts.append("")
        parts.append("你的真实消息示例：")
        parts.append("- 休息了")
        parts.append("- 赶紧洗个澡")
        parts.append("- 这儿也降温了")
        parts.append("- 稍微")
        parts.append("- 哈哈哈哈")
        parts.append("- 包上班的啊")
        parts.append("- 我人在村里，你要退只能晚上")
        parts.append("- 小酌")
        parts.append("- 今天上午家里躺了")
        parts.append("- 等你来了咱们喝😄")
        parts.append("- 抓小猫不优雅的样子")
        parts.append("- 了解大概什么时间吗，感觉积累很久了")
        parts.append("")
        parts.append("你的风格特征（从上面 59 条真实消息中提取）：")
        parts.append("- 极其简短，平均 6 个字。你不是爱打字的性格")
        parts.append("- 很少用句号逗号，想到什么打什么")
        parts.append("- 口语化，直接，不绕弯子。「包上班的」不说「当然要上班」")
        parts.append("- 会用 emoji 和「哈哈哈哈」这类自然的语气")
        parts.append("- 不总结、不分析、不贴标签、不说教")
        parts.append("")
        parts.append("关键：如果你发的回复读起来不像上面那些示例，那就不是你。重写。")

        # Burst awareness: when she sends many messages, reply must match the depth
        if burst_analysis:
            msg_count = burst_analysis.get("msg_count", 0)
            if msg_count >= 5:
                parts.append(f"重要：她连续发了 {msg_count} 条消息，不是一句随意的话。")
                parts.append("每个关键话题都要回应到，但还是用你的短句风格。")
                parts.append("你可以多发几句（每句还是短的），但不要写成一段长文。")
                parts.append("用换行分开不同话题，不要用「第一」「第二」这种结构词。")
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
        parts.append("直接输出回复文本。不要引号，不要「回复：」前缀。")
        parts.append("语气参照你俩之前的聊天记录——你们的亲密度、你的说话风格。")
        parts.append("最关键的：读一遍你写的回复，如果感觉像个客服或者Siri说出来的，重写。")

        return "\n".join(parts)

    def _build_user_prompt(
        self,
        ms: MessageState,
        chat_history: Optional[list[dict]],
        my_last_message: Optional[str],
        conversation_context: Optional[str] = None,
        burst_analysis: Optional[dict] = None,
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

        # 对话历史 — burst 模式下扩大窗口
        if chat_history:
            max_rounds = 20 if (burst_analysis and burst_analysis.get("msg_count", 0) >= 5) else 6
            parts.append("## 对话历史（时间顺序）")
            for m in chat_history[-max_rounds:]:
                role = "她" if m["role"] == "她" else "我"
                parts.append(f"{role}: {m['content']}")
            parts.append("")

        # Burst 模式：逐条展示她的所有消息，让 LLM 看到完整内容
        if burst_analysis and burst_analysis.get("msg_count", 0) >= 5:
            her_msgs = burst_analysis.get("her_msgs", [])
            if len(her_msgs) >= 3:
                parts.append("## 她的全部消息（请逐一回应每个关键点）")
                for i, msg in enumerate(her_msgs, 1):
                    parts.append(f"{i}. {msg}")
                parts.append("")

        # 她的最新消息 + 分析（供参考）
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
