"""
Conversation 管理器 —— 话题检测 + 边界判断 + 对话生命周期管理。

定位（来自 CONVERSATION_ENGINE_DESIGN_v2_MVP.md Section 9.2）：
    goal_planner.py → conversation.py（本模块）→ context_builder.py

设计原则：
- Topic 为主键（客观话题），Goal 是内部属性（系统推理）
- 边界检测不依赖 Message Understanding，只用时间 + 关键词 + 结束信号
- 状态只有 active / closed
- MVP 不做 Goal Chain、Emotion Trajectory、复杂状态机

用法：
    >>> mgr = ConversationManager()
    >>> conv, switched = mgr.process_message("今天老板骂我了", "2026-07-24T14:00:00", "EXPRESS_MORE")
    >>> print(conv.topic)  # "work"
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
CONVERSATIONS_FILE = ROOT_DIR / "data" / "conversations.json"
MAX_STORED_CONVERSATIONS = 50


# ============================================================
# Topic 关键词表（Section 4.3）
# ============================================================

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "work": ["老板", "同事", "加班", "工作", "项目", "开会", "上班", "辞职", "绩效", "汇报",
             "领导", "客户", "出差", "工资", "年终奖", "跳槽", "面试", "入职"],
    "exam": ["考试", "复习", "做题", "论文", "答辩", "开学", "成绩", "作业", "考研",
             "备考", "模拟", "真题", "图书馆", "刷题"],
    "family": ["妈", "爸", "家里", "爸妈", "弟弟", "妹妹", "哥哥", "姐姐", "回家",
               "亲戚", "我妈", "我爸", "奶奶", "爷爷"],
    "relationship": ["我们", "感情", "在一起", "分手", "喜欢你", "想你", "爱你", "异地",
                     "吃醋", "在乎", "关系", "未来", "结婚"],
    "dating": ["约会", "看电影", "吃饭去", "周末", "出去玩", "旅游", "机票", "酒店",
               "见面", "一起", "约吗", "逛街"],
    "conflict": ["吵架", "生气", "你总是", "你从来不", "从来不听", "为什么你", "不想理你", "冷战",
                 "烦死了", "走开", "别理我", "随便吧", "你爱怎样", "不理我", "敷衍"],
    "daily": [],  # 兜底，不匹配其他时归入
    "other": [],
}


def detect_topic(message_content: str) -> str:
    """根据关键词匹配话题。不调 LLM，纯规则。

    Args:
        message_content: 用户（她）的消息文本

    Returns:
        topic 标签（work/exam/family/relationship/dating/conflict/daily/other）
    """
    content = message_content.lower()
    scores: dict[str, int] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        if topic == "daily" or topic == "other":
            continue
        scores[topic] = sum(1 for kw in keywords if kw in content)

    if not scores:
        return "daily"

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] > 0:
        return best
    return "daily"


# ============================================================
# 结束信号词表（Section 4.1）
# ============================================================

CLOSURE_SIGNALS = [
    "晚安", "睡了", "睡觉", "睡吧", "先睡了",
    "拜拜", "明天聊", "先这样吧", "好了我去忙了",
    "先去忙", "我去洗澡", "我去吃饭", "我吃饭去了",
    "嗯嗯不聊了", "下次再说", "回头再聊", "早点休息",
    "先下了", "改天聊", "我困了", "去洗澡了",
]


def detect_closure(message_content: str) -> bool:
    """检测是否包含明确的结束信号。"""
    content = message_content.strip().lower()
    return any(signal in content for signal in CLOSURE_SIGNALS)


# ============================================================
# 时间阈值（Section 4.2 + Section 5）
# ============================================================

# 边界判断用的时间间隔（秒）
SAME_CONVERSATION_SEC = 30 * 60           # 30 分钟：同一 Conversation
MAYBE_NEW_SEC = 2 * 60 * 60                # 30min ~ 2h：不确定
DEFINITELY_NEW_SEC = 8 * 60 * 60           # 2h ~ 8h：很可能新

# 超时兜底（秒）
TIMEOUT_BY_TOPIC: dict[str, int] = {
    "daily": 6 * 60 * 60,        # 6 小时
    "work": 12 * 60 * 60,        # 12 小时
    "exam": 12 * 60 * 60,        # 12 小时
    "family": 12 * 60 * 60,      # 12 小时
    "relationship": 24 * 60 * 60,  # 24 小时
    "dating": 24 * 60 * 60,     # 24 小时
    "conflict": 72 * 60 * 60,    # 72 小时
    "other": 12 * 60 * 60,       # 12 小时
}

# 跨天例外：深夜 23:00 ~ 01:00，间隔 ≤ 1 小时不算跨天
NIGHT_START_HOUR = 23
NIGHT_END_HOUR = 1
NIGHT_MAX_GAP_SEC = 60 * 60  # 1 小时


# ============================================================
# Conversation 数据结构（Section 3）
# ============================================================

@dataclass
class Conversation:
    """一次完整的话题对话。MVP 版只保留 11 个字段。"""

    id: str                              # conv_001
    topic: str                           # work/exam/family/relationship/daily/dating/conflict/other
    status: str                          # active | closed
    start_time: str                      # ISO8601
    end_time: str | None = None          # 关闭时填入
    last_message_time: str = ""          # 最后一条消息时间
    current_goal: str | None = None      # 当前 Goal（内部属性，不做边界判断）
    summary: str | None = None           # 关闭时 LLM 生成
    outcome: str | None = None           # repaired | unresolved | neutral
    message_ids: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)   # summary 携带的关键信息

    _pending_close: bool = field(default=False, repr=False)  # 结束信号已触发，等待确认

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ============================================================
# ConversationManager（Section 9.1）
# ============================================================

class ConversationManager:
    """对话生命周期管理器。

    负责：
    - 创建/恢复 Conversation
    - 边界检测（结束信号 / 时间间隔 / 话题切换）
    - 超时兜底
    - 持久化到 conversations.json

    不负责：
    - Summary 生成（由调用方注入 LLM）
    - Memory 更新（由 memory_updater.py 负责）
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage = storage_path or CONVERSATIONS_FILE
        self._active: Conversation | None = None
        self._closed: list[Conversation] = []
        self._load()

    # ---- 主入口 ----

    def process_message(
        self,
        message_content: str,
        timestamp: str,
        current_goal: str | None = None,
    ) -> tuple[Conversation, bool]:
        """处理一条新消息，返回 (当前 Conversation, 是否发生切换)。

        内部流程（Section 4.4 优先级裁决）：
        1. 检查超时 → 可能关闭旧 Conv
        2. 检查结束信号
        3. 检查时间间隔
        4. 检查话题切换
        5. 优先级裁决
        6. 如需关闭 → 生成 Summary → 触发 Memory 更新
        7. 如需新建 → 创建新 Conversation
        8. 更新 current_goal
        """
        topic = detect_topic(message_content)
        closure_detected = detect_closure(message_content)
        switched = False

        # ---- 无活跃 Conversation → 新建 ----
        if self._active is None:
            self._active = self._create(topic, timestamp, current_goal)
            self._save()
            return self._active, True  # True 表示"新 Conversation 开始"

        # ---- 检查超时兜底（Section 5）----
        timeout_reason = self._check_timeout(timestamp)
        if timeout_reason:
            self._active = self._close_active(reason=timeout_reason, timestamp=timestamp)
            switched = True

        # ---- 边界检测 ----
        decision = self._decide_boundary(
            topic=topic,
            closure_detected=closure_detected,
            timestamp=timestamp,
        )

        if decision == "close_and_new":
            self._active = self._close_active(reason="boundary_decision", timestamp=timestamp)
            self._active = self._create(topic, timestamp, current_goal)
            switched = True
        elif decision == "continue":
            # 更新现有 Conversation
            self._active.current_goal = current_goal
            self._active.last_message_time = timestamp
            self._active.message_ids.append(self._make_message_id())
        elif decision == "pending_close":
            # 结束信号触发，标记 pending_close，本轮继续
            self._active._pending_close = True
            self._active.current_goal = current_goal
            self._active.last_message_time = timestamp
        elif decision == "confirm_close":
            # 上轮 pending_close，本轮确认
            self._active = self._close_active(reason="closure_confirmed", timestamp=timestamp)
            self._active = self._create(topic, timestamp, current_goal)
            switched = True

        self._save()
        return self._active, switched

    def get_active_conversation(self) -> Conversation | None:
        """获取当前活跃 Conversation。"""
        return self._active

    def close_conversation(self, reason: str = "manual") -> Conversation | None:
        """手动关闭当前 Conversation。"""
        if self._active is None:
            return None
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        closed = self._close_active(reason=reason, timestamp=now)
        self._save()
        return closed

    # ---- 边界决策（Section 4.4）----

    def _decide_boundary(
        self,
        topic: str,
        closure_detected: bool,
        timestamp: str,
    ) -> str:
        """优先级裁决器。返回: close_and_new | continue | pending_close | confirm_close"""
        assert self._active is not None

        # ---- 信号 A：结束信号（最高优先级）----
        if closure_detected:
            # 如果上轮已经是 pending_close → 确认关闭
            if self._active._pending_close:
                return "confirm_close"
            # 否则标记 pending_close，等待下轮确认
            return "pending_close"

        # 本轮回合清掉 pending_close 标记（用户说了新内容）
        if self._active._pending_close:
            self._active._pending_close = False

        # ---- 信号 B：时间间隔 ----
        gap_sec = self._time_gap(timestamp)
        topic_switch = (topic != self._active.topic)

        # 跨天判断
        cross_day = self._is_cross_day(timestamp)

        # 规则 2：时间间隔 > 8h 或跨天 → 直接关闭
        if gap_sec > DEFINITELY_NEW_SEC or (cross_day and gap_sec > NIGHT_MAX_GAP_SEC):
            return "close_and_new"

        # 规则 3：30min ~ 2h 且话题切换 → 关闭
        if SAME_CONVERSATION_SEC < gap_sec <= MAYBE_NEW_SEC and topic_switch:
            return "close_and_new"

        # 规则 4：30min ~ 2h 且话题不变 → 继续
        if SAME_CONVERSATION_SEC < gap_sec <= MAYBE_NEW_SEC and not topic_switch:
            return "continue"

        # 规则 5：< 30min 且话题切换 → 保持 active（可能是插一句）
        # 注：MVP 不做"连续 3 条新话题"追踪，简化为直接继续
        if gap_sec <= SAME_CONVERSATION_SEC and topic_switch:
            return "continue"

        # 规则 6：< 30min 且话题不变 → 继续
        return "continue"

    def _check_timeout(self, timestamp: str) -> str | None:
        """检查超时。返回 reason 或 None。"""
        if self._active is None:
            return None
        gap_sec = self._time_gap(timestamp)
        threshold = TIMEOUT_BY_TOPIC.get(self._active.topic, 12 * 60 * 60)
        if gap_sec > threshold:
            return f"timeout: topic={self._active.topic}, gap={gap_sec}s > {threshold}s"
        return None

    # ---- 辅助方法 ----

    def _create(self, topic: str, timestamp: str, current_goal: str | None) -> Conversation:
        conv = Conversation(
            id=f"conv_{uuid.uuid4().hex[:8]}",
            topic=topic,
            status="active",
            start_time=timestamp,
            last_message_time=timestamp,
            current_goal=current_goal,
            message_ids=[self._make_message_id()],
        )
        return conv

    def _close_active(self, reason: str, timestamp: str) -> Conversation | None:
        """关闭当前活跃 Conversation。由调用方负责生成 summary 和 outcome。"""
        if self._active is None:
            return None
        conv = self._active
        conv.status = "closed"
        conv.end_time = timestamp
        conv.last_message_time = timestamp
        self._closed.append(conv)
        self._active = None

        # 保留最近 MAX_STORED_CONVERSATIONS 个
        if len(self._closed) > MAX_STORED_CONVERSATIONS:
            self._closed = self._closed[-MAX_STORED_CONVERSATIONS:]

        return conv

    def _time_gap(self, current_ts: str) -> float:
        """计算从 last_message_time 到 current_ts 的秒数。"""
        if self._active is None:
            return float("inf")
        try:
            last = datetime.fromisoformat(self._active.last_message_time)
            curr = datetime.fromisoformat(current_ts)
            return (curr - last).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    def _is_cross_day(self, timestamp: str) -> bool:
        """判断是否跨天（考虑深夜连续聊天例外）。"""
        if self._active is None:
            return False
        try:
            last = datetime.fromisoformat(self._active.last_message_time)
            curr = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            return False

        # 同一天 → 不跨天
        if last.date() == curr.date():
            return False

        # 跨天例外：23:00 ~ 01:00 且间隔 ≤ 1h
        gap = (curr - last).total_seconds()
        last_in_night = last.hour >= NIGHT_START_HOUR or last.hour < NIGHT_END_HOUR
        curr_in_night = curr.hour >= NIGHT_START_HOUR or curr.hour < NIGHT_END_HOUR
        if last_in_night and curr_in_night and gap <= NIGHT_MAX_GAP_SEC:
            return False

        return True

    @staticmethod
    def _make_message_id() -> str:
        return f"msg_{uuid.uuid4().hex[:8]}"

    # ---- 持久化 ----

    def _load(self) -> None:
        if not self._storage.exists():
            return
        try:
            raw = json.loads(self._storage.read_text(encoding="utf-8"))
            for conv_data in raw.get("closed", []):
                self._closed.append(Conversation.from_dict(conv_data))
            active_data = raw.get("active")
            if active_data:
                self._active = Conversation.from_dict(active_data)
        except (json.JSONDecodeError, KeyError, TypeError):
            self._closed = []
            self._active = None

    def _save(self) -> None:
        data = {
            "active": self._active.to_dict() if self._active else None,
            "closed": [c.to_dict() for c in self._closed],
        }
        self._storage.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 查询 ----

    def get_recent_conversations(self, n: int = 10) -> list[Conversation]:
        """获取最近 n 个已关闭的 Conversation。"""
        return self._closed[-n:]

    def count_topic_in_recent(self, topic: str, n: int = 10) -> int:
        """统计最近 n 个 Conversation 中指定 topic 的出现次数。"""
        recent = self._closed[-n:]
        return sum(1 for c in recent if c.topic == topic)


# ============================================================
# 单例便捷入口
# ============================================================

_default_manager: ConversationManager | None = None


def get_manager() -> ConversationManager:
    """获取全局 ConversationManager 单例。"""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConversationManager()
    return _default_manager
