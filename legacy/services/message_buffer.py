"""Message Buffer — 消息聚合器，管理 WCF 实时消息流。

职责：
- 接收 WCF 消息（她的 + 你的）
- 按对话窗口聚合
- 跟踪未读/已处理状态
- 提供「待处理消息」视图供仪表盘使用

不负责：
- 持久化（ConversationManager 负责）
- 消息分析（PipelineService 负责）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BufferedMessage:
    """缓冲中的单条消息。"""
    id: str
    role: str           # '她' 或 '我'
    content: str
    timestamp: str
    is_emoji: bool = False
    is_image: bool = False
    emoji_desc: str = ""  # 表情/图片的文字描述

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_emoji": self.is_emoji,
            "is_image": self.is_image,
            "emoji_desc": self.emoji_desc,
        }


class MessageBuffer:
    """消息缓冲区。管理未处理消息队列 + 已处理历史。"""

    def __init__(self, max_buffer: int = 500):
        self._pending: list[BufferedMessage] = []   # 她的未处理消息
        self._my_recent: list[BufferedMessage] = []  # 我最近的消息
        self._all: list[BufferedMessage] = []         # 完整历史（已处理）
        self._max = max_buffer
        self._last_analysis_time: str = ""            # 上次触发分析的时间
        self._last_my_message: BufferedMessage | None = None  # 我最后一条消息

    # ---- 写入 ----

    def push(self, role: str, content: str, timestamp: str | None = None,
             is_emoji: bool = False, is_image: bool = False,
             emoji_desc: str = "") -> BufferedMessage:
        """接收一条新消息。"""
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        msg = BufferedMessage(
            id=f"buf_{len(self._all)}_{ts}",
            role=role,
            content=content,
            timestamp=ts,
            is_emoji=is_emoji,
            is_image=is_image,
            emoji_desc=emoji_desc,
        )

        self._all.append(msg)
        if len(self._all) > self._max:
            self._all = self._all[-self._max:]

        if role == "她":
            self._pending.append(msg)
        else:
            self._my_recent.append(msg)
            self._last_my_message = msg
            if len(self._my_recent) > 50:
                self._my_recent = self._my_recent[-50:]

        return msg

    # ---- 读取 ----

    def get_pending(self) -> list[BufferedMessage]:
        """获取她的未处理消息列表。"""
        return list(self._pending)

    def get_pending_count(self) -> int:
        """未处理消息数。"""
        return len(self._pending)

    def get_my_recent(self, n: int = 10) -> list[BufferedMessage]:
        """获取我最近发送的消息。"""
        return self._my_recent[-n:]

    def get_last_my_message(self) -> BufferedMessage | None:
        """我最后一条消息。"""
        return self._last_my_message

    def get_conversation_context(self, n: int = 20) -> list[dict]:
        """获取最近 N 条消息的上下文（她 + 我混合）。"""
        recent = [m for m in self._all[-n:] if m.role in ("她", "我")]
        return [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in recent]

    def time_since_last_her_message(self) -> float:
        """距离她最后一条消息过去多少秒。"""
        if not self._pending and not self._all:
            return 0.0
        # 找最后一条她的消息
        for msg in reversed(self._all):
            if msg.role == "她":
                try:
                    last_ts = datetime.fromisoformat(msg.timestamp)
                    now = datetime.now(timezone.utc)
                    return (now - last_ts).total_seconds()
                except (ValueError, TypeError):
                    return 0.0
        return 0.0

    def time_since_last_my_message(self) -> float:
        """距离我最后一条消息过去多少秒。"""
        if not self._last_my_message:
            return float("inf")
        try:
            last_ts = datetime.fromisoformat(self._last_my_message.timestamp)
            now = datetime.now(timezone.utc)
            return (now - last_ts).total_seconds()
        except (ValueError, TypeError):
            return float("inf")

    # ---- 标记 ----

    def mark_processed(self) -> list[BufferedMessage]:
        """将所有待处理消息标记为已处理，返回被处理的列表。"""
        processed = list(self._pending)
        self._pending = []
        self._last_analysis_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return processed

    def is_empty(self) -> bool:
        return len(self._pending) == 0

    # ---- 状态 ----

    def get_stats(self) -> dict:
        """返回缓冲区统计信息。"""
        pending = self.get_pending()
        return {
            "pending_count": len(pending),
            "pending_since": pending[0].timestamp if pending else None,
            "last_her_message": pending[-1].timestamp if pending else None,
            "last_my_message": self._last_my_message.timestamp if self._last_my_message else None,
            "time_since_her": self.time_since_last_her_message(),
            "time_since_me": self.time_since_last_my_message(),
            "total_buffered": len(self._all),
        }
