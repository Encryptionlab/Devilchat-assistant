"""
消息理解层执行模块。

负责：
1. 加载 relationship_state.json（关系状态）
2. 根据 MESSAGE_UNDERSTANDING_library 构建分析 prompt
3. 将 LLM 输出解析为结构化 MessageState

不负责：
- LLM 调用本身（由调用方注入，保持模型无关）
- 更新关系状态（手动维护）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

ROOT_DIR = Path(__file__).parent.parent
LIBRARIES_DIR = ROOT_DIR / "libraries"
RELATIONSHIP_STATE_PATH = ROOT_DIR / "data" / "relationship_state.json"


# ============================================================
# 枚举定义（来源：libraries/MESSAGE_UNDERSTANDING_library.md）
# ============================================================

SURFACE_INTENT_VALUES = [
    "emotional_expression", "complaint", "sharing", "question",
    "relationship_test", "praise", "invitation", "rejection",
    "teasing", "conflict",
]

EMOTION_VALUES = [
    "happy", "excited", "sad", "disappointed", "angry",
    "anxious", "lonely", "tired", "bored", "embarrassed",
    "jealous", "hopeful", "grateful", "neutral",
]

NEED_VALUES = [
    "ATTENTION", "UNDERSTANDING", "VALIDATION", "SECURITY",
    "RESPECT", "APPRECIATION", "PARTICIPATION", "ENTERTAINMENT",
    "COMPANIONSHIP", "INTIMACY", "EMOTIONAL_RELEASE", "SUPPORT",
]

RELATIONSHIP_SIGNAL_VALUES = [
    "seeking_attention", "seeking_reassurance", "seeking_connection",
    "engagement", "withdrawing", "testing", "flirting", "conflicting",
]

EXPRESSION_MODE_VALUES = ["impulse", "intention"]
STATE_TYPE_VALUES = ["pure_state", "state_with_feeling"]
SUGGEST_DIRECTION_VALUES = ["positive", "negative", "null"]
CONFLICT_SIGNAL_VALUES = ["her_initiated", "none"]
CONVERSATION_STAGE_VALUES = ["opening", "elaborating", "escalating", "resolving", "closing"]
EXPECTED_RESPONSE_VALUES = [
    "empathy", "reassurance", "celebration", "curiosity",
    "support", "advice", "humor", "affection",
]
TOPIC_VALUES = ["work", "exam", "family", "relationship", "dating", "conflict", "daily"]
BURST_PATTERN_VALUES = ["single", "venting", "escalating", "question_chain", "mixed"]

# surface_intent 和 need 已改为打分模式，不在此校验
_FIELD_ENUMS: dict[str, frozenset] = {
    "emotion": frozenset(EMOTION_VALUES),
    "relationship_signal": frozenset(RELATIONSHIP_SIGNAL_VALUES),
    "expression_mode": frozenset(EXPRESSION_MODE_VALUES),
    "state_type": frozenset(STATE_TYPE_VALUES),
    "suggest_direction": frozenset(SUGGEST_DIRECTION_VALUES),
    "conflict_signal": frozenset(CONFLICT_SIGNAL_VALUES),
    "conversation_stage": frozenset(CONVERSATION_STAGE_VALUES),
    "expected_response": frozenset(EXPECTED_RESPONSE_VALUES),
    "burst_pattern": frozenset(BURST_PATTERN_VALUES),
    "emotional_peak": frozenset(EMOTION_VALUES),
}

_REQUIRED_FIELDS = [
    "message", "surface_intent_scores", "emotion", "emotion_intensity",
    "need_scores", "relationship_signal", "expression_mode", "state_type",
    "suggest_direction", "has_metaphor", "conflict_signal",
    "conversation_stage", "expected_response",
]

# 需要打分验证的字段
_SCORED_FIELDS = {
    "surface_intent_scores": SURFACE_INTENT_VALUES,
    "need_scores": NEED_VALUES,
}


# ============================================================
# MessageState —— 结构化消息分析结果
# ============================================================

@dataclass
class MessageState:
    """消息理解层的结构化输出。下游模块只读此结构，不直接读原始消息。"""

    message: str
    surface_intent_scores: dict[str, float]
    emotion: str
    emotion_intensity: float
    need_scores: dict[str, float]
    relationship_signal: str
    expression_mode: str
    state_type: str
    suggest_direction: str
    has_metaphor: bool
    conflict_signal: str
    conversation_stage: str
    expected_response: str
    topic: str = "daily"
    burst_pattern: str = "single"
    emotional_peak: str = "neutral"
    trajectory_note: str = ""
    relationship_context: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "MessageState":
        field_names = {f for f in cls.__dataclass_fields__ if f != "relationship_context"}
        kwargs = {k: data[k] for k in field_names if k in data}
        kwargs["relationship_context"] = data.get("relationship_context", {})
        return cls(**kwargs)

    def to_dict(self) -> dict:
        return asdict(self)

    # ---- 意图 ----

    @property
    def dominant_intent(self) -> str:
        return max(self.surface_intent_scores, key=self.surface_intent_scores.get)

    def intents_above(self, threshold: float = 0.5) -> list[str]:
        return [k for k, v in self.surface_intent_scores.items() if v >= threshold]

    # ---- 需求 ----

    @property
    def dominant_need(self) -> str:
        return max(self.need_scores, key=self.need_scores.get)

    def needs_above(self, threshold: float = 0.5) -> list[str]:
        return [k for k, v in self.need_scores.items() if v >= threshold]

    # ---- 便捷判断 ----

    @property
    def is_impulse(self) -> bool:
        return self.expression_mode == "impulse"

    @property
    def is_intention(self) -> bool:
        return self.expression_mode == "intention"

    @property
    def has_feeling(self) -> bool:
        return self.state_type == "state_with_feeling"

    @property
    def is_suggestive(self) -> bool:
        return self.suggest_direction != "null"

    @property
    def is_conflict_initiated_by_her(self) -> bool:
        return self.conflict_signal == "her_initiated"

    @property
    def emotion_is_positive(self) -> bool:
        return self.emotion in ("happy", "excited", "hopeful", "grateful")

    @property
    def emotion_is_negative(self) -> bool:
        return self.emotion in ("sad", "disappointed", "angry", "anxious",
                                "lonely", "jealous", "tired", "bored",
                                "embarrassed")


# ============================================================
# System Prompt 构建
# ============================================================

def _build_system_prompt() -> str:
    """构建消息理解的系统提示词。支持单条消息和批量消息序列分析。"""

    intent_items = "\n".join(f'        "{v}": 0.0,' for v in SURFACE_INTENT_VALUES)
    need_items = "\n".join(f'        "{v}": 0.0,' for v in NEED_VALUES)

    return f"""你是一个恋爱沟通分析专家，专门分析女性在聊天中发送的消息。

你的任务：接收她的一段消息序列（可能 1~5 条连发，标记为"她"的消息），以及你（标记为"我"）的回复作为上下文，分析整体的情绪基调、情绪递进轨迹、核心需求，输出结构化的分析结果。

## 分析原则

1. **主导情绪取最后一条"她"的消息的情绪**。
   例外：如果多条消息构成"倾诉递进"（如：累 → 越来越累 → 扛不住了），取峰值情绪作为主导情绪。

2. **need_scores 要覆盖整个递进过程**的综合需求，不只是最后一条消息的需求。

3. 如果多条消息是"话题跳跃"（如：累 → 问你今天干嘛了），按最后一条确定主导方向和话题。

4. 如果只有一条"她"的消息，正常分析即可。

5. **请重点分析标记为"她"的消息**，"我"的消息仅作上下文参考——你的回复会影响她后续消息的情绪走向。

6. 结合关系上下文解读消息——同一个词在不同关系中含义完全不同。

7. 优先识别需求而非情绪——情绪是表象，需求才是驱动力。

8. 关注关系信号——她可能是外表说A、实际在表达B。

9. 只做分析，不做建议——不要生成回复，只输出分析结果。

## 输出字段

### surface_intent_scores (object)
对整个消息序列中她表达的表面意图打分（0.0~1.0），以最新消息为主。
允许同时有多个高分——一条消息可以同时"抱怨""情绪表达""分享"。

{_format_scored_keys(SURFACE_INTENT_VALUES)}

### need_scores (object)
对每种可能的回应需求打分（0.0~1.0），覆盖整个递进过程。
判断方法：不是分析"她有什么心理需求"，而是问自己"她现在最想让我做什么"。

{_format_need_keys()}

### emotion (string)
她整个序列的主导情绪。规则：取最新一条"她"消息的情绪，venting 时取峰值。
可选值：
{_format_enum_list(EMOTION_VALUES)}

### emotion_intensity (number, 0.0~1.0)
主导情绪的强度。0.0=无波动，1.0=极端情绪。取最新"她"消息的强度，venting 时取峰值。

### relationship_signal (string)
她向关系释放的隐含信号。可选值：
{_format_enum_list(RELATIONSHIP_SIGNAL_VALUES)}

### expression_mode (string)
她是在表达一时冲动的念头（impulse），还是经过判断的稳定想法（intention）。
可选值：{_format_enum_list(EXPRESSION_MODE_VALUES)}

### state_type (string)
她分享的是纯客观状态还是附带了主观感受。
可选值：{_format_enum_list(STATE_TYPE_VALUES)}

### suggest_direction (string)
如果是暗示性语言，肯定回答指向的方向暴露了她的真实意愿。
可选值：{_format_enum_list(SUGGEST_DIRECTION_VALUES)}

### has_metaphor (boolean)
她的请求是否用了比喻包装（形式层≠实质层）。

### conflict_signal (string)
可选值：{_format_enum_list(CONFLICT_SIGNAL_VALUES)}

### conversation_stage (string)
当前消息序列在整段对话中的位置。请结合对话历史判断。
可选值：{_format_enum_list(CONVERSATION_STAGE_VALUES)}

### expected_response (string)
她期待什么类型的回应。
可选值：{_format_enum_list(EXPECTED_RESPONSE_VALUES)}

### topic (string)
她正在聊的话题。根据消息序列的核心内容判断，而非单个词汇。
可选值：{_format_enum_list(TOPIC_VALUES)}

分类依据：
- work: 工作/职业/职场
- exam: 考试/学习/备考
- family: 家庭/家人
- relationship: 恋爱关系本身（感情、未来、异地、对方的态度等）
- dating: 约会/出行/娱乐安排
- conflict: 冲突/争吵/不满/指责对方（即使话题涉及关系，如果核心是表达不满，归 conflict）
- daily: 日常闲聊（无法归入以上类别时使用）

### burst_pattern (string) — 展示用，不参与策略决策
消息序列的结构模式。可选值：
- single: 单条消息，无 burst
- venting: 倾诉递进，情绪逐步加强（后一条加深前一条的情绪）
- escalating: 情绪升级，可能转向冲突（情绪从负面到更负面）
- question_chain: 连续提问，每条都在寻求信息
- mixed: 混合型，话题/情绪跳跃，无明显递进关系

### emotional_peak (string) — 展示用，不参与策略决策
整个序列中情绪最强烈的那条消息对应的情绪标签。可选值同 emotion 字段。

### trajectory_note (string) — 展示用，不参与策略决策
一句话概括整个 burst 的情绪/需求递进轨迹。
例如："从疲惫倾诉到寻求安慰"、"从不满到失望"、"从分享到邀约"。
单条消息时为空字符串。

## 输出格式

仅输出一个 JSON 对象，不要包含任何其他文字：

```json
{{
  "message": "序列中最后一条她的消息文本",
  "surface_intent_scores": {{
{intent_items}
  }},
  "emotion": "...",
  "emotion_intensity": 0.0,
  "need_scores": {{
{need_items}
  }},
  "relationship_signal": "...",
  "expression_mode": "...",
  "state_type": "...",
  "suggest_direction": "...",
  "has_metaphor": false,
  "conflict_signal": "...",
  "conversation_stage": "...",
  "expected_response": "...",
  "topic": "daily",
  "burst_pattern": "single",
  "emotional_peak": "neutral",
  "trajectory_note": ""
}}
```"""


def _format_enum_list(values: list[str]) -> str:
    return ", ".join(f"`{v}`" for v in values)


def _format_scored_keys(values: list[str]) -> str:
    """生成打分模式的 key 列表，带简短中文说明。"""
    labels = {
        "emotional_expression": "情绪表达",
        "complaint": "抱怨",
        "sharing": "分享",
        "question": "提问",
        "relationship_test": "关系测试",
        "praise": "赞美",
        "invitation": "邀约",
        "rejection": "拒绝",
        "teasing": "调侃",
        "conflict": "冲突",
    }
    return "\n".join(f"- `{v}` = {labels.get(v, v)}" for v in values)


def _format_need_keys() -> str:
    """生成 need 打分模式 key 列表，带行为描述。"""
    descriptions = {
        "EMOTIONAL_RELEASE": "当树洞，听她吐槽发泄，别打断别说教",
        "UNDERSTANDING": "先共情，说'确实很累''我懂'，别讲道理",
        "ATTENTION": "注意到她，主动问她怎么了，表示你在乎",
        "SUPPORT": "给实际帮助，出主意、给建议、解决问题",
        "VALIDATION": "肯定她的感受，'换我也会这样'",
        "COMPANIONSHIP": "陪着她，人在就行，不用解决问题",
        "SECURITY": "给她确定感，让她知道你在、你不会走",
        "ENTERTAINMENT": "逗她开心，让她笑，转移注意力",
        "APPRECIATION": "夸她、赞美她，看到她的优点和用心",
        "INTIMACY": "拉近关系，表达喜欢或暧昧",
        "RESPECT": "尊重边界，别越界、别施压、别勉强",
        "PARTICIPATION": "带她互动，邀请她参与话题",
    }
    return "\n".join(f"- `{v}` = {descriptions.get(v, v)}" for v in NEED_VALUES)


# ============================================================
# 关系状态加载
# ============================================================

def _default_state() -> dict:
    return {
        "stage": "",
        "temperature": "",
        "attachment_style": None,
        "trust_level": 0,
        "intimacy_level": 0,
        "conflict_status": "none",
        "recent_events": [],
    }


def load_relationship_state(path: Optional[Path] = None) -> dict:
    filepath = path or RELATIONSHIP_STATE_PATH
    if not filepath.exists():
        return _default_state()

    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)

    state = raw.get("relationship_state", raw)

    stage_raw = state.get("当前关系阶段", "")
    temperature_raw = state.get("关系热度", "")
    attachment_raw = state.get("对方依恋风格", "")

    return {
        "stage": _extract_first_word(stage_raw),
        "temperature": _extract_first_word(temperature_raw),
        "attachment_style": _extract_first_word(attachment_raw) if attachment_raw else None,
        "trust_level": state.get("信任程度_0到100", 0),
        "intimacy_level": state.get("亲密程度_0到100", 0),
        "conflict_status": _extract_first_word(state.get("冲突状态", "")),
        "recent_events": state.get("近期关键事件", []),
    }


def _extract_first_word(text: str) -> str:
    return text.split()[0] if text else ""


# ============================================================
# 主类
# ============================================================

LlmCallable = Callable[[str, str], str]


class MessageUnderstanding:
    """消息理解器。构建 prompt 并解析 LLM 输出。"""

    def __init__(self, relationship_state_path: Optional[Path] = None):
        self.system_prompt = _build_system_prompt()
        self.relationship_state = load_relationship_state(relationship_state_path)

    def __repr__(self) -> str:
        rs = self.relationship_state
        return (
            f"MessageUnderstanding("
            f"stage={rs['stage']}, "
            f"temperature={rs['temperature']}, "
            f"trust={rs['trust_level']}, "
            f"intimacy={rs['intimacy_level']})"
        )

    def build_user_prompt(
        self, messages: list[dict], my_last_message: Optional[str] = None
    ) -> str:
        context_parts = []

        rs = self.relationship_state
        context_parts.append("## 当前关系状态")
        context_parts.append(f"- 关系阶段: {rs['stage']}")
        context_parts.append(f"- 关系热度: {rs['temperature']}")
        if rs.get("attachment_style"):
            context_parts.append(f"- 对方依恋风格: {rs['attachment_style']}")
        context_parts.append(f"- 信任程度: {rs['trust_level']}/100")
        context_parts.append(f"- 亲密程度: {rs['intimacy_level']}/100")
        context_parts.append(f"- 冲突状态: {rs['conflict_status']}")
        if rs.get("recent_events"):
            context_parts.append(f"- 近期事件: {', '.join(rs['recent_events'])}")

        if my_last_message:
            context_parts.append(f"\n## 我上一条发的消息\n{my_last_message}")

        if messages:
            context_parts.append("\n## 对话历史（时间顺序）")
            for m in messages:
                role = "她" if m["role"] == "她" else "我"
                context_parts.append(f"{role}: {m['content']}")

        context_parts.append("\n请分析她的最新消息，仅输出 JSON。")

        return "\n".join(context_parts)

    def build_user_prompt_for_sequence(
        self, messages: list[dict], my_last_message: Optional[str] = None
    ) -> str:
        """构建批量消息序列的 user prompt。输入为最近 N 条混合消息（她+我）。

        与 build_user_prompt 的区别：
        - 消息格式化为带序号的序列，而非角色标签的对话历史
        - 指示 LLM 分析整个序列，而非单条消息
        """
        context_parts = []

        rs = self.relationship_state
        context_parts.append("## 当前关系状态")
        context_parts.append(f"- 关系阶段: {rs['stage']}")
        context_parts.append(f"- 关系热度: {rs['temperature']}")
        if rs.get("attachment_style"):
            context_parts.append(f"- 对方依恋风格: {rs['attachment_style']}")
        context_parts.append(f"- 信任程度: {rs['trust_level']}/100")
        context_parts.append(f"- 亲密程度: {rs['intimacy_level']}/100")
        context_parts.append(f"- 冲突状态: {rs['conflict_status']}")
        if rs.get("recent_events"):
            context_parts.append(f"- 近期事件: {', '.join(rs['recent_events'])}")

        if my_last_message:
            context_parts.append(f"\n## 我上一条发的消息\n{my_last_message}")

        if messages:
            context_parts.append(f"\n## 消息序列（时间顺序，共 {len(messages)} 条）\n")
            for i, m in enumerate(messages):
                role = "她" if m.get("role") == "她" else "我"
                content = m.get("content", "")
                context_parts.append(f"{i+1}. {role}: {content}")

        context_parts.append(
            '\n请分析她在以上序列中的消息（标记为"她"的条目），'
            '考虑整个交换的上下文，仅输出 JSON。'
        )

        return "\n".join(context_parts)

    def parse_response(self, llm_output: str) -> dict:
        text = self._strip_markdown_fence(llm_output)
        result = json.loads(text)

        for field in _REQUIRED_FIELDS:
            if field not in result:
                raise ValueError(f"LLM 输出缺少必填字段: {field}")

        # 验证打分字段
        for field_name, keys in _SCORED_FIELDS.items():
            scores = result[field_name]
            if not isinstance(scores, dict):
                raise ValueError(f"{field_name} 必须是 object，实际: {type(scores)}")
            for key in keys:
                if key not in scores:
                    raise ValueError(f"{field_name} 缺少 key: {key}")
                v = scores[key]
                if not isinstance(v, (int, float)) or not (0.0 <= v <= 1.0):
                    raise ValueError(f"{field_name}.{key} = {v}，应在 0.0~1.0")

        # 验证枚举字段
        for field, allowed in _FIELD_ENUMS.items():
            value = result[field]
            if value is None and "null" in allowed:
                value = "null"
                result[field] = "null"
            if value not in allowed:
                raise ValueError(
                    f"字段 '{field}' 的值 '{value}' 不在合法枚举中。"
                    f"合法值: {sorted(allowed)}"
                )

        # topic 可选，默认 "daily"
        if "topic" not in result or result["topic"] not in TOPIC_VALUES:
            result["topic"] = "daily"

        # 新增字段兜底：LLM 未返回时不崩溃
        result.setdefault("burst_pattern", "single")
        result.setdefault("emotional_peak", result.get("emotion", "neutral"))
        result.setdefault("trajectory_note", "")

        result["relationship_context"] = dict(self.relationship_state)
        return result

    def parse_to_state(self, llm_output: str) -> MessageState:
        return MessageState.from_dict(self.parse_response(llm_output))

    def analyze(
        self, llm_call: LlmCallable, messages: list[dict],
        my_last_message: Optional[str] = None,
    ) -> MessageState:
        user_prompt = self.build_user_prompt(messages, my_last_message)
        llm_output = llm_call(self.system_prompt, user_prompt)
        return self.parse_to_state(llm_output)

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines)
        return text


# ============================================================
# 便捷函数
# ============================================================

def build_prompt_for_message(
    her_message: str,
    chat_history: Optional[list[dict]] = None,
    my_last_message: Optional[str] = None,
    relationship_state_path: Optional[Path] = None,
) -> tuple[str, str]:
    mu = MessageUnderstanding(relationship_state_path)
    messages = chat_history or []
    user_prompt = mu.build_user_prompt(messages, my_last_message)
    return mu.system_prompt, user_prompt


def parse_llm_output(llm_output: str) -> dict:
    mu = MessageUnderstanding()
    return mu.parse_response(llm_output)


def parse_llm_output_to_state(llm_output: str) -> MessageState:
    mu = MessageUnderstanding()
    return mu.parse_to_state(llm_output)
