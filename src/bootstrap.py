"""
引导式初始化 —— 首次运行时通过对话让 LLM 推导初始关系画像。

B 路线：用户描述 → LLM 提取结构化字段 → 写入 relationship_state.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

ROOT_DIR = Path(__file__).parent.parent
RS_PATH = ROOT_DIR / "data" / "relationship_state.json"

LlmCallable = Callable[[str, str], str]

GUIDE_TEXT = """
欢迎使用魔鬼聊天。

在开始之前，先简单说说你们现在的关系吧。
比如：
  - 认识多久了？怎么认识的？
  - 现在是什么关系阶段？（刚认识 / 朋友 / 暧昧 / 恋爱 / 稳定）
  - 最近有什么重要的事情发生吗？
  - 你觉得她信任你吗？你们亲密吗？

不用拘束，像跟朋友聊天一样描述就好。
""".strip()

EXTRACTION_PROMPT = """你是一个关系状态分析助手。用户会用自然语言描述一段恋爱关系。
请从描述中提取以下字段，仅输出 JSON。

字段说明：
- stage: 关系阶段，从以下选项中选一个最匹配的：
  stranger（陌生人）/ acquaintance（刚认识）/ friend（普通朋友）/ ambiguous（暧昧）/ dating（恋爱）/ stable（长期稳定）
- temperature: 关系热度，从以下选项中选一个：
  hot（火热）/ warm（温暖）/ neutral（中性）/ cold（冷淡）
- attachment_style: 对方的依恋风格，从以下选项中选一个，不确定则为 null：
  secure（安全型）/ anxious（焦虑型）/ avoidant（回避型）/ fearful（恐惧型）
- trust_level: 信任程度，整数 0-100
- intimacy_level: 亲密程度，整数 0-100
- conflict_status: 冲突状态，从 none / mild / active 中选一个
- recent_events: 近期关键事件列表（字符串数组，最多 5 条）

输出格式：
{
  "stage": "ambiguous",
  "temperature": "warm",
  "attachment_style": null,
  "trust_level": 60,
  "intimacy_level": 40,
  "conflict_status": "none",
  "recent_events": ["明天她考试"]
}

仅输出 JSON，不要包含其他文字。"""


def bootstrap(llm_chat: LlmCallable) -> None:
    """交互式引导，调用 LLM 提取关系画像，写入 relationship_state.json。"""

    print(GUIDE_TEXT)
    print()

    user_input = input("> ").strip()
    while not user_input:
        user_input = input("请至少说几句，我好了解你们的情况: ").strip()

    print("\n正在分析你描述的关系...")

    llm_output = ""
    try:
        llm_output = llm_chat(EXTRACTION_PROMPT, user_input)
        data = json.loads(_strip_fence(llm_output))
    except Exception as e:
        print(f"[警告] LLM 解析失败: {e}")
        if llm_output:
            print(f"原始输出: {llm_output[:200]}")
        print("将使用最小默认值继续。")
        data = _minimal_default()

    # 确保必填字段存在
    data.setdefault("stage", "acquaintance")
    data.setdefault("temperature", "neutral")
    data.setdefault("attachment_style", None)
    data.setdefault("trust_level", 30)
    data.setdefault("intimacy_level", 20)
    data.setdefault("conflict_status", "none")
    data.setdefault("recent_events", [])

    # 写入文件（格式与现有 relationship_state.json 一致）
    rs_doc = {
        "说明": "此文件由引导式初始化自动生成。可手动修改。",
        "relationship_state": {
            "当前关系阶段": _stage_to_cn(data["stage"]),
            "关系热度": _temperature_to_cn(data["temperature"]),
            "对方依恋风格": data.get("attachment_style") or "",
            "信任程度_0到100": data["trust_level"],
            "亲密程度_0到100": data["intimacy_level"],
            "冲突状态": data["conflict_status"],
            "近期关键事件": data["recent_events"],
            "conflict_level": 0,
            "recurring_topics": [],
            "unresolved_topics": [],
            "future_events": [],
            "preferences": [],
            "personality_traits": [],
        },
        "更新日志": [{
            "日期": _today(),
            "修改字段": "初始化",
            "旧值": None,
            "新值": "bootstrap",
            "原因": "引导式初始化自动生成",
        }],
    }
    RS_PATH.write_text(json.dumps(rs_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"关系画像已生成 → {RS_PATH}")
    print(f"  stage={data['stage']}, trust={data['trust_level']}, intimacy={data['intimacy_level']}")


def _stage_to_cn(stage: str) -> str:
    mapping = {
        "stranger": "stranger 陌生人",
        "acquaintance": "acquaintance 刚认识",
        "friend": "friend 普通朋友",
        "ambiguous": "ambiguous 暧昧",
        "dating": "dating 恋爱",
        "stable": "stable 长期稳定",
    }
    return mapping.get(stage, f"{stage}")


def _temperature_to_cn(temp: str) -> str:
    mapping = {
        "hot": "hot 火热",
        "warm": "warm 温暖",
        "neutral": "neutral 中性",
        "cold": "cold 冷淡",
    }
    return mapping.get(temp, f"{temp}")


def _minimal_default() -> dict:
    return {
        "stage": "acquaintance",
        "temperature": "neutral",
        "attachment_style": None,
        "trust_level": 30,
        "intimacy_level": 20,
        "conflict_status": "none",
        "recent_events": [],
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


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
