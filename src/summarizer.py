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
  "summary": "2-3句话概括这段对话的内容和走向",
  "outcome": "resolved 或 unresolved 或 neutral",
  "key_points": ["关键信息点1", "关键信息点2"]
}

outcome 判断标准：
- resolved: 问题得到解决、情绪得到安抚、或达成了共识
- unresolved: 问题未解决、矛盾仍在、或情绪未平复
- neutral: 日常闲聊，无所谓解决不解决

key_points: 提取对话中值得记住的信息，例如"她提到想换工作"、"约定下周六见面"。没有特别信息则返回空数组。

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
