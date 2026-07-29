"""Urgency Scorer —— 紧急度评估引擎（纯规则，非 LLM）。

评估「现在是否需要处理她的消息」，输出三级标签。

输入指标：
- 未读消息数量
- 距最后一条消息的时间间隔
- 她的当前情绪
- 是否有未解决的问题
- 冲突等级

输出:
    🟢 normal — 无需立即处理，例行查看
    🟡 attention — 建议有空时关注
    🔴 urgent — 情绪升级中，尽快处理
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# 高紧急度情绪（需要尽快回应）
HIGH_URGENCY_EMOTIONS = {"angry", "anxious", "disappointed", "sad", "lonely"}

# 中等紧急度情绪
MEDIUM_URGENCY_EMOTIONS = {"tired", "bored", "embarrassed", "jealous", "confused"}

# 低紧急度情绪
LOW_URGENCY_EMOTIONS = {"happy", "excited", "hopeful", "grateful", "neutral"}


class UrgencyScorer:
    """纯规则紧急度评估。不依赖 LLM，在消息流入时实时运行。"""

    def assess(
        self,
        pending_count: int,
        time_since_last_her: float,       # 秒
        time_since_last_me: float,         # 秒
        emotion: str = "neutral",
        conflict_level: int = 0,
        has_unresolved_topics: bool = False,
        is_night_time: bool = False,
    ) -> dict:
        """评估紧急度。

        Returns:
            {"level": "urgent|attention|normal", "score": int, "reasons": list[str]}
        """
        score = 0
        reasons: list[str] = []

        # 因子 1：消息堆积
        if pending_count >= 5:
            score += 3
            reasons.append(f"未读消息 {pending_count} 条，堆积较多")
        elif pending_count >= 3:
            score += 1
            reasons.append(f"未读消息 {pending_count} 条")

        # 因子 2：时间压力
        hours_since_her = time_since_last_her / 3600
        hours_since_me = time_since_last_me / 3600 if time_since_last_me != float("inf") else 999

        if hours_since_her > 8 and hours_since_me > 8:
            score += 3
            reasons.append(f"已 {hours_since_her:.0f} 小时未回复")
        elif hours_since_her > 4:
            score += 2
            reasons.append(f"距她最后消息 {hours_since_her:.0f} 小时")
        elif hours_since_her > 2:
            score += 1

        # 因子 3：情绪紧急度
        if emotion in HIGH_URGENCY_EMOTIONS:
            score += 4
            reasons.append(f"情绪: {emotion}（高紧急度）")
        elif emotion in MEDIUM_URGENCY_EMOTIONS:
            score += 2
            reasons.append(f"情绪: {emotion}（中紧急度）")

        # 因子 4：冲突状态
        if conflict_level >= 3:
            score += 3
            reasons.append(f"冲突等级 {conflict_level}/5，需要关注")
        elif conflict_level >= 2:
            score += 1

        # 因子 5：未解决问题
        if has_unresolved_topics:
            score += 2
            reasons.append("存在未解决的问题")

        # 因子 6：深夜降权
        if is_night_time:
            score = max(0, score - 2)
            reasons.append("当前为深夜时段，降低紧急度")

        # 判定
        if score >= 6:
            level = "urgent"
        elif score >= 3:
            level = "attention"
        else:
            level = "normal"

        return {
            "level": level,
            "score": score,
            "reasons": reasons,
            "label": {"urgent": "🔴 需要处理", "attention": "🟡 建议关注", "normal": "🟢 正常"}[level],
        }

    def is_night_time(self) -> bool:
        """判断当前是否深夜时段（00:00-07:00）。"""
        hour = datetime.now(timezone.utc).hour
        # 使用 UTC 可能导致偏差，MVP 阶段使用本地时间近似
        hour_local = datetime.now().hour
        return hour_local < 7 or hour_local >= 23
