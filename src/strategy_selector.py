"""
策略选择层 —— 将 Goal + Needs + 上下文 → 匹配的策略卡。

定位：目标确定（GoalPlanner） → 策略选择（本模块） → 回复生成

设计原则：
- 纯规则引擎，不调 LLM
- 阶段兼容性为硬门槛，需求匹配度为软排序
- 输出 primary + candidates，供上层选择
- 策略卡不完善是预期的，后续扩充时只需加卡，不用改选择器
"""

from __future__ import annotations

from typing import Optional

from .message_understanding import MessageState
from .strategy_loader import StrategyLoader, StrategyCard


# 英语 emotion → 中文情绪类别（用于 not_apply_when 匹配）
_EMOTION_TO_CN_CATEGORY: dict[str, list[str]] = {
    "sad":         ["悲伤", "严重悲伤", "难过"],
    "disappointed": ["悲伤", "难过"],
    "angry":       ["愤怒", "生气"],
    "anxious":     ["焦虑", "紧张"],
    "lonely":      ["悲伤"],
    "jealous":     ["愤怒"],
    "tired":       [],
    "bored":       [],
    "embarrassed": ["羞涩", "紧张"],
    "happy":       [],
    "excited":     ["开心", "兴奋"],
    "hopeful":     ["期待"],
    "grateful":    [],
    "neutral":     [],
}

RISK_PENALTY = {"low": 0.0, "medium": 0.05, "high": 0.12}


class StrategySelector:
    """策略选择器。根据 Goal + Needs + 上下文匹配最佳策略卡。"""

    def __init__(
        self,
        loader: Optional[StrategyLoader] = None,
        relationship_state: Optional[dict] = None,
    ):
        self.loader = loader or StrategyLoader()
        self.rs = relationship_state or {}

    def select(
        self,
        ms: MessageState,
        goal_result: dict,
        need_result: Optional[dict] = None,
    ) -> dict:
        """选择最佳策略卡。

        Args:
            ms: 消息理解结果
            goal_result: GoalPlanner.plan() 的输出
            need_result: NeedRecognizer.prioritize() 的输出（可选）

        Returns:
            {
                "goal": str,
                "goal_zh": str,
                "primary": StrategyCard | None,
                "candidates": [(StrategyCard, score, reasons), ...],
                "filtered_out": [(strategy_id, reason), ...],
            }
        """
        goal = goal_result["goal"]
        top_needs = need_result.get("top_needs", []) if need_result else []
        stage = self.rs.get("stage", "acquaintance")

        # 暂存供 _context_match 使用
        self._ms_emotion = ms.emotion

        candidates: list[tuple[StrategyCard, float, list[str]]] = []
        filtered: list[tuple[str, str]] = []

        for card in self.loader.list_strategies():
            # Phase 1: 硬过滤
            reject_reason = self._check_hard_filter(card, ms, stage)
            if reject_reason:
                filtered.append((card.id, reject_reason))
                continue

            # Phase 2: 打分
            score, reasons = self._score(card, top_needs)
            candidates.append((card, round(score, 3), reasons))

        # 降序排列
        candidates.sort(key=lambda x: -x[1])
        primary = candidates[0][0] if candidates else None

        return {
            "goal": goal,
            "goal_zh": goal_result.get("goal_zh", goal),
            "primary": primary,
            "candidates": candidates[:5],
            "filtered_out": filtered,
        }

    # ============================================================
    # Hard filters
    # ============================================================

    def _check_hard_filter(
        self, card: StrategyCard, ms: MessageState, stage: str
    ) -> Optional[str]:
        """返回拒绝原因，None 表示通过。"""

        # 1. 关系阶段不兼容（长期关系维度）
        allowed_stages = card.apply_when.get("relationship_stage", [])
        if allowed_stages and stage not in allowed_stages:
            return f"关系阶段不兼容: stage={stage} not in {allowed_stages}"

        # 2. 对话阶段不兼容（当前对话维度）
        allowed_conv_stages = card.apply_when.get("conversation_stage", [])
        if allowed_conv_stages and ms.conversation_stage not in allowed_conv_stages:
            return f"对话阶段不兼容: {ms.conversation_stage} not in {allowed_conv_stages}"

        # 3. not_apply_when 的关系阶段排除
        excluded_stages = card.not_apply_when.get("relationship_stage", [])
        if excluded_stages and stage in excluded_stages:
            return f"关系阶段被排除: stage={stage} in excluded {excluded_stages}"

        # 4. not_apply_when 的情绪排除
        excluded_emotions = card.not_apply_when.get("emotions", [])
        if excluded_emotions:
            cn_tags = _EMOTION_TO_CN_CATEGORY.get(ms.emotion, [])
            for tag in cn_tags:
                if tag in excluded_emotions:
                    return f"情绪被排除: emotion={ms.emotion} → {tag} in {excluded_emotions}"

        # 5. 策略声明的 requirements 检查（通用）
        if card.requirements:
            if not self._check_requirements(card, ms):
                desc = card.requirements.get("description", "requirements not met")
                return f"{desc}"

        return None

    # ============================================================
    # Generic requirement checker
    # ============================================================

    def _check_requirements(self, card: StrategyCard, ms: MessageState) -> bool:
        """检查策略卡声明的 requirements。

        支持两种逻辑:
        - "any": 至少一个 condition 通过
        - "all": 所有 condition 通过
        """
        reqs = card.requirements
        if "any" in reqs:
            return any(self._eval_condition(c, ms) for c in reqs["any"])
        if "all" in reqs:
            return all(self._eval_condition(c, ms) for c in reqs["all"])
        return True

    def _eval_condition(self, cond: dict, ms: MessageState) -> bool:
        """评估单个条件。支持 op: eq, gt, gte, lt, lte, in"""
        value = self._resolve_field(ms, cond["field"])
        op = cond["op"]
        if op == "eq":
            return value == cond["value"]
        elif op == "gt":
            return value is not None and value > cond["value"]
        elif op == "gte":
            return value is not None and value >= cond["value"]
        elif op == "lt":
            return value is not None and value < cond["value"]
        elif op == "lte":
            return value is not None and value <= cond["value"]
        elif op == "in":
            return value in cond["values"]
        return False

    @staticmethod
    def _resolve_field(ms: MessageState, field_path: str):
        """解析点号分隔的字段路径。支持嵌套 dict 和 dataclass 属性。

        例: "surface_intent_scores.teasing" → ms.surface_intent_scores["teasing"]
        """
        parts = field_path.split(".")
        value = ms
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
        return value

    # ============================================================
    # Scoring
    # ============================================================

    def _score(
        self,
        card: StrategyCard,
        top_needs: list[tuple[str, float]],
    ) -> tuple[float, list[str]]:
        """计算策略卡的匹配分数。

        三维度 + 动态风险惩罚：
        - need_match:    主分，策略 target_need 与当前 top_needs 的重叠度
        - context_match: 当前情绪/上下文是否匹配策略偏好
        - risk_penalty:  风险惩罚 × 信任衰减（高信任→惩罚衰减，低信任→惩罚放大）
        """
        reasons: list[str] = []

        need_score, need_reason = self._need_match(card, top_needs)
        reasons.append(need_reason)

        context_score, context_reason = self._context_match(card)
        if context_reason:
            reasons.append(context_reason)

        base_pen = RISK_PENALTY.get(card.risk_level, 0.05)
        trust = self.rs.get("trust_level", 50)
        risk_pen = round(base_pen * (1.0 - trust / 100.0), 3)
        if risk_pen > 0:
            reasons.append(f"risk={card.risk_level} base={base_pen:.2f} × trust_decay({trust}) → -{risk_pen:.2f}")

        total = need_score + context_score - risk_pen
        return max(0.0, total), reasons

    # ---- 子维度 ----

    def _need_match(
        self, card: StrategyCard, top_needs: list[tuple[str, float]]
    ) -> tuple[float, str]:
        """need 匹配度：target_need 与 top_needs 的重叠度。

        每个 target_need 如果在 top_needs 中出现，贡献其分数；
        未出现用 0.05 兜底（不是 0，避免 target_need 多的卡被平均值惩罚过重）。
        """
        target = card.target_need
        if not target:
            return 0.15, "need: 无 target_need，兜底 0.15"

        need_map = dict(top_needs)
        matched = 0.0
        details: list[str] = []

        for need_id in target:
            score = need_map.get(need_id, 0.05)
            if need_id in need_map:
                details.append(f"{need_id}={score:.2f}")
            else:
                details.append(f"{need_id}=miss")
            matched += score

        avg = round(matched / len(target), 3)
        return avg, f"need: {' + '.join(details)} → {avg:.2f}"

    def _context_match(self, card: StrategyCard) -> tuple[float, str]:
        """上下文匹配度：情绪、表达模式等。

        检查 card.apply_when.emotions 是否包含当前情绪类别。
        """
        preferred_emotions = card.apply_when.get("emotions", [])
        if not preferred_emotions:
            return 0.0, ""

        cn_tags = _EMOTION_TO_CN_CATEGORY.get(getattr(self, "_ms_emotion", ""), [])
        for tag in cn_tags:
            if tag in preferred_emotions:
                return 0.05, f"context: emotion={self._ms_emotion} ({tag}) matched → +0.05"

        return 0.0, ""
