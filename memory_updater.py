"""
Memory Updater —— 在 Conversation 关闭时，用纯规则将关键信息写入长期记忆。

定位（来自 CONVERSATION_ENGINE_DESIGN_v2_MVP.md Section 7）：
    Conversation 关闭 → memory_updater.py（本模块）→ relationship_state.json

设计原则：
- 纯规则触发（次数 + outcome），不依赖置信度计算
- 保守写入：宁漏勿错
- 带衰减机制：30 天降权、60 天移除
- Pending memory 字段预留，MVP 不实现完整置信度计算

用法：
    >>> updater = MemoryUpdater(relationship_state_path="relationship_state.json")
    >>> updater.update(closed_conversation)
    >>> updater.save()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).parent
DEFAULT_RS_PATH = ROOT_DIR / "relationship_state.json"


class MemoryUpdater:
    """长期记忆自动更新器。在 Conversation 关闭时由 ConversationManager 调用。"""

    def __init__(self, relationship_state_path: Optional[Path] = None):
        self._rs_path = relationship_state_path or DEFAULT_RS_PATH
        self._rs: dict[str, Any] = {}
        self._load()

    # ---- 主入口 ----

    def update(self, closed_conversation: Any) -> dict[str, Any]:
        """处理一个已关闭的 Conversation，返回本轮的更新记录。

        Args:
            closed_conversation: 已关闭的 Conversation 对象（duck typing）

        Returns:
            {"applied_rules": [str], "changes": {...}}
        """
        rules_applied: list[str] = []
        changes: dict[str, Any] = {}

        # 提取 Conversation 信息
        topic = getattr(closed_conversation, "topic", "daily")
        outcome = getattr(closed_conversation, "outcome", None)
        key_points = getattr(closed_conversation, "key_points", []) or []
        summary = getattr(closed_conversation, "summary", "")

        # ---- 规则 1：同话题重复出现 ≥3 次 → recurring_topics ----
        # 注：此规则需要最近 10 个已关闭 Conversation 的上下文，
        # 由调用方通过计数器传入或从 conversations.json 读取。
        # 当前实现：提供一个独立的 apply_recurring_topics 方法

        # ---- 规则 2：outcome = unresolved → key_points 写入 unresolved_topics ----
        if outcome == "unresolved" and key_points:
            rules_applied.append("规则2: outcome=unresolved → unresolved_topics")
            unresolved = set(self._rs.get("unresolved_topics", []))
            for point in key_points:
                if point and point not in unresolved:
                    unresolved.add(point)
                    changes.setdefault("unresolved_topics", []).append(point)
            if changes.get("unresolved_topics"):
                self._rs["unresolved_topics"] = sorted(unresolved)

        # ---- 规则 3：conflict topic + unresolved → 冲突等级上调 ----
        if topic == "conflict" and outcome == "unresolved":
            rules_applied.append("规则3: conflict+unresolved → conflict_level +1")
            current = self._rs.get("conflict_level", 0)
            new_level = min(current + 1, 5)
            if new_level != current:
                self._rs["conflict_level"] = new_level
                changes["conflict_level"] = f"{current} → {new_level}"

        # ---- 规则 4：conflict topic + repaired → 冲突等级下调 ----
        if topic == "conflict" and outcome == "repaired":
            rules_applied.append("规则4: conflict+repaired → conflict_level -1")
            current = self._rs.get("conflict_level", 0)
            new_level = max(current - 1, 0)
            if new_level != current:
                self._rs["conflict_level"] = new_level
                changes["conflict_level"] = f"{current} → {new_level}"

            # 同时清理 unresolved_topics 中已解决的项
            if key_points:
                unresolved = set(self._rs.get("unresolved_topics", []))
                removed = []
                for point in key_points:
                    if point in unresolved:
                        unresolved.discard(point)
                        removed.append(point)
                if removed:
                    self._rs["unresolved_topics"] = sorted(unresolved)
                    changes.setdefault("resolved_topics", []).extend(removed)
                    rules_applied.append(f"规则4副作用: 清理已解决的 unresolved_topics: {removed}")

        return {
            "applied_rules": rules_applied,
            "changes": changes,
        }

    def apply_recurring_topics(
        self,
        topic_counts: dict[str, int],
    ) -> dict[str, Any]:
        """规则 1：同一 topic 在最近 10 个 Conversation 出现 ≥3 次 → recurring_topics。

        这个方法和 update() 分离，因为需要外部提供跨 Conversation 的计数上下文。

        Args:
            topic_counts: {topic: count} — 最近 N 个 Conversation 中各 topic 次数

        Returns:
            {"applied_rules": [str], "changes": {...}}
        """
        rules_applied: list[str] = []
        changes: dict[str, Any] = {}
        current_recurring = set(self._rs.get("recurring_topics", []))

        for topic, count in topic_counts.items():
            if count >= 3 and topic not in current_recurring:
                current_recurring.add(topic)
                changes.setdefault("recurring_topics", []).append(topic)
                rules_applied.append(f"规则1: topic={topic} 出现 {count} 次 → recurring_topics")

        if changes.get("recurring_topics"):
            self._rs["recurring_topics"] = sorted(current_recurring)

        return {
            "applied_rules": rules_applied,
            "changes": changes,
        }

    def apply_decay(self, conversation_ages: Optional[dict[str, int]] = None) -> dict[str, Any]:
        """衰减机制（Section 7.4）。

        - recurring_topics: 30 天未出现 → 降权（标记）；60 天 → 移除
        - 当前简化实现：基于 ages dict {topic: days_since_last_seen}

        Args:
            conversation_ages: {topic: 最近一次出现的距今天数}，None 则跳过

        Returns:
            {"applied_rules": [str], "changes": {...}}
        """
        if not conversation_ages:
            return {"applied_rules": [], "changes": {}}

        rules_applied: list[str] = []
        changes: dict[str, Any] = {}
        current_recurring = set(self._rs.get("recurring_topics", []))

        for topic in list(current_recurring):
            days = conversation_ages.get(topic, 0)
            if days > 60:
                current_recurring.discard(topic)
                changes.setdefault("recurring_topics_removed", []).append(topic)
                rules_applied.append(f"衰减: topic={topic} 超过 60 天未出现 → 移除")
            elif days > 30:
                # 降权：MVP 阶段只打日志，不实际改变数据结构
                rules_applied.append(f"衰减: topic={topic} 超过 30 天未出现 → 降权（注：MVP 仅记录）")

        if changes.get("recurring_topics_removed"):
            self._rs["recurring_topics"] = sorted(current_recurring)

        return {
            "applied_rules": rules_applied,
            "changes": changes,
        }

    # ---- 持久化 ----

    def _load(self) -> None:
        if self._rs_path.exists():
            raw = json.loads(self._rs_path.read_text(encoding="utf-8"))
            # 从 relationship_state 包裹中提取
            self._rs = raw.get("relationship_state", raw)
        else:
            self._rs = {}

    def save(self) -> None:
        """将更新写回 relationship_state.json，保留原有结构和顶层字段。"""
        if self._rs_path.exists():
            raw = json.loads(self._rs_path.read_text(encoding="utf-8"))
        else:
            raw = {}

        # 只更新 relationship_state 子对象，保留 更新日志 等顶层字段
        raw["relationship_state"] = self._rs
        self._rs_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def state(self) -> dict[str, Any]:
        """只读访问当前内存中的关系状态。"""
        return dict(self._rs)
