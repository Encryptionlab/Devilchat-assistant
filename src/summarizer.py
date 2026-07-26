"""
Conversation 摘要器 —— Conversation 关闭时调用 LLM 生成摘要。

由交互循环在 Conversation 关闭钩子中调用。
"""

from __future__ import annotations

import json
from typing import Callable

LlmCallable = Callable[[str, str], str]

SYSTEM_PROMPT = """你是一个对话分析助手。以下是一段已结束的对话。

请分析并仅输出 JSON：

{
  "summary": "1-2句话概括这段对话的核心内容和走向",
  "outcome": "resolved 或 unresolved 或 neutral",
  "key_points": []
}

outcome 判断标准（严格）：
- resolved: 问题得到解决、情绪得到安抚、达成共识
- unresolved: 明确存在未解决的冲突、分歧、或悬而未决的问题
- neutral: 无问题需要解决（日常闲聊、道晚安、关心问候、一般分享等都属于此类）

重要：绝大多数对话应该是 neutral。只有真正存在"需要解决但目前没解决"的情况才标 unresolved。

key_points 提取规则：
- 只提取对未来对话有参考价值的信息，避免碎片化
- 日常寒暄、结束语（晚安、拜拜）、闲聊感慨、一般问候 都不提取
- 最多 3 条
- 每条包含 type 字段：
  - "unresolved": 未解决的问题/冲突
  - "info": 客观信息（如"下周有考试"、"约定周末见面"）
  - "emotion": 重要的情绪状态（如"对异地感到焦虑"）

示例：
"key_points": [
  {"text": "母亲催考研并施压", "type": "unresolved"},
  {"text": "约定周六下午去咖啡厅", "type": "info"}
]

仅输出 JSON，不要包含其他文字。"""


def summarize(llm_chat: LlmCallable, messages: list[dict], topic: str = "") -> dict:
    """生成 Conversation 摘要。

    Args:
        llm_chat: LLM 调用函数
        messages: 对话消息列表 [{"role": "她/我", "content": "..."}]
        topic: Conversation 的话题标签

    Returns:
        {"summary": str, "outcome": str, "key_points": list[str]}
    """
    user_prompt_parts = [f"话题: {topic}", ""]
    for m in messages:
        role = "她" if m["role"] == "她" else "我"
        user_prompt_parts.append(f"{role}: {m['content']}")
    user_prompt = "\n".join(user_prompt_parts)

    try:
        raw = llm_chat(SYSTEM_PROMPT, user_prompt)
        result = json.loads(_strip_fence(raw))
        return {
            "summary": result.get("summary", ""),
            "outcome": result.get("outcome", "neutral"),
            "key_points": result.get("key_points", []),
        }
    except (json.JSONDecodeError, Exception):
        return {
            "summary": "",
            "outcome": "neutral",
            "key_points": [],
        }


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    return text
