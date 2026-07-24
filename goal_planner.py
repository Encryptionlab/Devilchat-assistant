"""
目标确定层 —— 将需求 + 对话阶段 + 关系状态 → 单一行动目标。

定位：需求识别（NeedRecognizer） → 目标确定（本模块） → 策略选择

设计原则（来自《需求和goal的理解》）：
- Need = 她想得到什么（她的视角）
- Goal = 我下一步该做什么（Agent 视角）
- Goal 必须唯一 —— Agent 最终只能做一个动作
- 同一 Need 在不同对话阶段 → 不同 Goal

纯规则引擎，不调 LLM。
"""

from __future__ import annotations

from typing import Optional

from message_understanding import MessageState, NEED_VALUES

# 来自 libraries/goal_libary.md
GOAL_DEFINITIONS: dict[str, str] = {
    "EXPRESS_MORE":           "让她继续表达、多说一点",
    "REDUCE_NEGATIVE":        "缓解她的负面情绪",
    "BUILD_SECURITY":         "建立安全感，消除不安",
    "INCREASE_PARTICIPATION": "制造参与感，带她互动",
    "AMPLIFY_POSITIVE":       "放大她的积极情绪",
    "INCREASE_INTIMACY":      "推进亲密度，拉近关系",
    "REPAIR_CONNECTION":      "修复关系连接",
    "DEESCALATE_CONFLICT":    "结束冲突，降级对抗",
}

# Need → 大类分组（用于决策）
NEED_CATEGORIES: dict[str, str] = {
    "UNDERSTANDING":    "emotional",
    "EMOTIONAL_RELEASE": "emotional",
    "COMPANIONSHIP":    "emotional",
    "VALIDATION":       "emotional",
    "SECURITY":         "security",
    "ATTENTION":        "engagement",
    "PARTICIPATION":    "engagement",
    "INTIMACY":         "intimacy",
    "APPRECIATION":     "intimacy",
    "SUPPORT":          "practical",
    "ENTERTAINMENT":    "entertainment",
    "RESPECT":          "respect",
}

# 阶段 → (类别 → Goal) 决策表
# opening 阶段大部分需要更多信息，优先 express_more
# elaborating/escalating 阶段信息够了，针对需求类型行动
# resolving/closing 阶段收束

STAGE_GOAL_MAP: dict[str, dict[str, str]] = {
    "opening": {
        "emotional":     "EXPRESS_MORE",
        "security":      "EXPRESS_MORE",
        "intimacy":      "EXPRESS_MORE",
        "engagement":    "INCREASE_PARTICIPATION",
        "practical":     "EXPRESS_MORE",
        "entertainment": "AMPLIFY_POSITIVE",
        "respect":       "EXPRESS_MORE",
    },
    "elaborating": {
        "emotional":     "REDUCE_NEGATIVE",
        "security":      "BUILD_SECURITY",
        "intimacy":      "INCREASE_INTIMACY",
        "engagement":    "INCREASE_PARTICIPATION",
        "practical":     "REDUCE_NEGATIVE",
        "entertainment": "AMPLIFY_POSITIVE",
        "respect":       "BUILD_SECURITY",
    },
    "escalating": {
        "emotional":     "REDUCE_NEGATIVE",
        "security":      "BUILD_SECURITY",
        "intimacy":      "INCREASE_INTIMACY",
        "engagement":    "INCREASE_PARTICIPATION",
        "practical":     "REDUCE_NEGATIVE",
        "entertainment": "AMPLIFY_POSITIVE",
        "respect":       "BUILD_SECURITY",
    },
    "resolving": {
        "emotional":     "REDUCE_NEGATIVE",
        "security":      "BUILD_SECURITY",
        "intimacy":      "EXPRESS_MORE",
        "engagement":    "EXPRESS_MORE",
        "practical":     "REDUCE_NEGATIVE",
        "entertainment": "AMPLIFY_POSITIVE",
        "respect":       "BUILD_SECURITY",
    },
    "closing": {
        "emotional":     "REDUCE_NEGATIVE",
        "security":      "BUILD_SECURITY",
        "intimacy":      "EXPRESS_MORE",
        "engagement":    "EXPRESS_MORE",
        "practical":     "REDUCE_NEGATIVE",
        "entertainment": "AMPLIFY_POSITIVE",
        "respect":       "BUILD_SECURITY",
    },
}


class GoalPlanner:
    """目标确定器。输入需求+上下文，输出单一行动目标。"""

    def __init__(self, relationship_state: Optional[dict] = None):
        self.rs = relationship_state or {}

    def plan(
        self,
        ms: MessageState,
        top_needs: Optional[list[tuple[str, float]]] = None,
    ) -> dict:
        """确定当前对话的单一目标。

        Args:
            ms: 消息理解结果
            top_needs: 需求识别后的 Top-K 需求 [(need, score), ...]
                       如果为 None，直接在 ms.need_scores 上计算

        Returns:
            {
                "goal": str,           # 目标 ID
                "goal_zh": str,        # 中文说明
                "reasoning": str,      # 为什么选这个目标
                "alternatives": [...], # 备选目标
            }
        """
        needs = top_needs or sorted(ms.need_scores.items(), key=lambda x: -x[1])
        stage = ms.conversation_stage
        conflict = self.rs.get("conflict_status", "none")
        events = " ".join(str(e) for e in self.rs.get("recent_events", []))

        # ---- Phase 1: 危机/冲突优先 ----
        goal = _check_conflict(conflict, ms.conflict_signal, events)
        if goal:
            return self._result(goal, "冲突状态优先覆盖", needs)

        # ---- Phase 2: 情绪优先 ----
        goal = _check_emotion_priority(ms)
        if goal:
            return self._result(goal, f"情绪优先: emotion={ms.emotion}", needs)

        # ---- Phase 3: 阶段 × 需求类别 → Goal ----
        goal, reason = _stage_need_to_goal(needs, stage)
        return self._result(goal, reason, needs)

    def _result(self, goal: str, reasoning: str, needs: list) -> dict:
        alt = [g for g in GOAL_DEFINITIONS if g != goal]
        return {
            "goal": goal,
            "goal_zh": GOAL_DEFINITIONS.get(goal, goal),
            "reasoning": reasoning,
            "alternatives": alt[:3],
        }


# ============================================================
# 决策函数
# ============================================================

def _check_conflict(conflict_status: str, conflict_signal: str, events_text: str) -> Optional[str]:
    """Phase 1: 冲突/危机覆盖。"""
    if conflict_status in ("active", "severe"):
        fight_kw = ["吵架", "冷战", "矛盾", "生气"]
        if any(kw in events_text for kw in fight_kw):
            return "REPAIR_CONNECTION"
        if conflict_signal == "her_initiated":
            return "DEESCALATE_CONFLICT"
        return "DEESCALATE_CONFLICT"
    return None


def _check_emotion_priority(ms: MessageState) -> Optional[str]:
    """Phase 2: 情绪状态优先路由。"""
    if ms.emotion_is_positive:
        return "AMPLIFY_POSITIVE"
    if ms.emotion == "anxious":
        return "BUILD_SECURITY"
    return None


def _stage_need_to_goal(
    needs: list[tuple[str, float]], stage: str
) -> tuple[str, str]:
    """Phase 3: 根据主导需求的类别和对话阶段，查表确定 Goal。

    决策逻辑：
    1. 取 Top-1 需求（调整后最高分）
    2. 查该需求的大类
    3. 查当前阶段的类别→Goal 映射表
    4. 如果 top need 分数不够高（<0.3），回退到 EXPRESS_MORE
    """
    if not needs:
        return "EXPRESS_MORE", "无需求信号，默认引导表达"

    top_need, top_score = needs[0]
    category = NEED_CATEGORIES.get(top_need, "emotional")

    stage_map = STAGE_GOAL_MAP.get(stage, STAGE_GOAL_MAP["opening"])
    goal = stage_map.get(category, "EXPRESS_MORE")

    # 需求信号太弱 → 保守策略
    if top_score < 0.3:
        goal = "EXPRESS_MORE"
        return goal, f"需求信号弱 (top={top_need} {top_score:.2f})，保守引导表达"

    return goal, (
        f"主导需求={top_need}({category}, {top_score:.2f}) "
        f"× 阶段={stage} "
        f"→ {goal}"
    )
