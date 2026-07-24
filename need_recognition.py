"""
需求识别层 —— 在 need_scores 上叠加关系上下文，做乘法规则的过滤和优先级调整。

定位：消息理解（LLM） → 需求识别（规则引擎，本模块） → 目标确定 → 策略选择

设计原则：
- 乘法因子（非加减）：高分会受到更大绝对值影响，低分不受力，多因子自然收敛
- 软约束（非硬封顶）：不设上限，用惩罚因子压制，允许强信号穿透
- Top-K 输出：同时关注多个并存需求

不调 LLM，纯规则。每条规则输出 reason 方便调试。
"""

from __future__ import annotations

from typing import Optional

from message_understanding import MessageState, NEED_VALUES

TOP_K = 3


class NeedRecognizer:
    """需求识别器。用乘法因子调整 need_scores 的优先级。"""

    def __init__(self, relationship_state: Optional[dict] = None):
        self.rs = relationship_state or {}

    def prioritize(self, ms: MessageState) -> dict:
        """对 MessageState 中的 need_scores 做上下文调整。

        Returns:
            {
                "adjusted_scores": {need_id: adjusted_score, ...},  # 降序
                "raw_scores": {need_id: original_score, ...},
                "dominant_need": str,
                "top_needs": [(need_id, score), ...],  # Top-K
                "applied_rules": [str, ...],
            }
        """
        scores = {k: float(v) for k, v in ms.need_scores.items()}
        rules: list[str] = []

        # 1. 阶段惩罚/加成（乘法）
        scores, rules = _apply_stage_factors(scores, ms, self.rs, rules)

        # 2. 事件加成（乘法）
        scores, rules = _apply_event_factors(scores, ms, self.rs, rules)

        # 3. 情绪联动（乘法，受 impulse 阻尼）
        scores, rules = _apply_emotion_factors(scores, ms, rules)

        # 4. 收束到 0.0~1.0
        scores = {k: round(max(0.0, min(1.0, v)), 3) for k, v in scores.items()}

        # 排序
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        dominant = ranked[0][0]
        top_k = [(k, v) for k, v in ranked[:TOP_K] if v > 0.05]

        return {
            "adjusted_scores": dict(ranked),
            "raw_scores": ms.need_scores,
            "dominant_need": dominant,
            "top_needs": top_k,
            "applied_rules": rules,
        }


# ============================================================
# 规则函数
# ============================================================

def _add_rule(rules: list[str], rule_name: str, detail: str = "") -> list[str]:
    rules.append(f"[{rule_name}] {detail}".strip())
    return rules


def _mult(scores: dict[str, float], key: str, factor: float) -> dict[str, float]:
    """原地乘以 factor。只对 factor ≠ 1.0 做操作。
    如果 key 不在 dict 中，设为 0.0（0×factor=0，无影响）。
    """
    if factor != 1.0:
        if key not in scores:
            scores[key] = 0.0
        scores[key] = scores[key] * factor
    return scores


# ---- 阶段因子 ----

# 软惩罚因子（惩罚 ≠ 封顶，强信号可穿透）
STAGE_PENALTIES = {
    # (stage 条件, trust 条件, has_feeling 条件): {need: factor}
    ("acquaintance_low_trust",): {
        "INTIMACY": 0.70,   # 刚认识低信任，亲密感打折但不抹杀
        "SECURITY": 0.80,
    },
    ("acquaintance_pure_state",): {
        "SUPPORT": 0.80,    # 纯状态+刚认识，别越级关心但别完全不理
    },
    ("conflict_active",): {
        "ENTERTAINMENT": 0.70,  # 冲突中别逗，但不封死
    },
    ("acquaintance_soft",): {
        "INTIMACY": 0.75,   # 刚认识表达亲密，压制但不否决
    },
}

# 加成因子（>1.0）
STAGE_BOOSTS = {
    ("conflict_active",): {
        "UNDERSTANDING": 1.15,  # 冲突中先共情
        "RESPECT": 1.15,
    },
}


def _apply_stage_factors(
    scores: dict[str, float], ms: MessageState, rs: dict, rules: list[str]
) -> tuple[dict[str, float], list[str]]:
    stage = rs.get("stage", "")
    trust = rs.get("trust_level", 50)
    conflict = rs.get("conflict_status", "none")

    # -- 惩罚条件 --
    is_low_trust_early = stage in ("stranger", "acquaintance") and trust < 40
    is_pure_state_early = is_low_trust_early and not ms.has_feeling
    is_conflict = conflict in ("active", "severe")
    is_acquaintance = stage in ("stranger", "acquaintance")

    # 刚认识低信任：INTIMACY, SECURITY 软罚
    if is_low_trust_early:
        for need, factor in STAGE_PENALTIES[("acquaintance_low_trust",)].items():
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            rules = _add_rule(rules, "stage", f"{need} {old:.2f}→{new:.2f} (×{factor}, 刚认识+低信任)")

    # 纯状态+刚认识：SUPPORT 软罚
    if is_pure_state_early:
        for need, factor in STAGE_PENALTIES[("acquaintance_pure_state",)].items():
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            rules = _add_rule(rules, "stage", f"{need} {old:.2f}→{new:.2f} (×{factor}, 纯状态+刚认识)")

    # 冲突：娱乐罚，共情/尊重加成
    if is_conflict:
        for need, factor in STAGE_PENALTIES[("conflict_active",)].items():
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            rules = _add_rule(rules, "stage", f"{need} {old:.2f}→{new:.2f} (×{factor}, 冲突中)")

        for need, factor in STAGE_BOOSTS[("conflict_active",)].items():
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            rules = _add_rule(rules, "stage", f"{need} {old:.2f}→{new:.2f} (×{factor}, 冲突中)")

    # 刚认识全局 INTIMACY 软罚
    if is_acquaintance:
        for need, factor in STAGE_PENALTIES[("acquaintance_soft",)].items():
            old = scores.get(need, 0)
            # 只对显著分数才打规则日志
            if old > 0.2:
                _mult(scores, need, factor)
                new = round(scores[need], 3)
                rules = _add_rule(rules, "stage", f"{need} {old:.2f}→{new:.2f} (×{factor}, 刚认识阶段约束)")
            else:
                _mult(scores, need, factor)

    return scores, rules


# ---- 事件因子 ----

EVENT_FACTORS = {
    "high_stress": {"SUPPORT": 1.25},
    "fight": {"SECURITY": 1.20, "UNDERSTANDING": 1.20},
    "date": {"INTIMACY": 1.15},  # 仅 ambiguous+
}

EVENT_KEYWORDS = {
    "high_stress": ["考试", "面试", "重要", "压力", "加班"],
    "fight": ["吵架", "冷战", "矛盾", "生气", "不开心"],
    "date": ["约会", "见面", "出去玩", "周末"],
}


def _apply_event_factors(
    scores: dict[str, float], ms: MessageState, rs: dict, rules: list[str]
) -> tuple[dict[str, float], list[str]]:
    events = rs.get("recent_events", [])
    if not events:
        return scores, rules

    event_text = " ".join(str(e) for e in events)
    stage = rs.get("stage", "")

    matched = []
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(kw in event_text for kw in keywords):
            matched.append(event_type)

    for event_type in matched:
        factors = EVENT_FACTORS[event_type]
        for need, factor in factors.items():
            # date 加成仅限暧昧+
            if event_type == "date" and stage not in ("ambiguous", "dating", "stable"):
                continue
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            rules = _add_rule(rules, "event", f"{need} {old:.2f}→{new:.2f} (×{factor}, {event_type})")

    return scores, rules


# ---- 情绪联动因子 ----

EMOTION_FACTORS = {
    "negative": {"UNDERSTANDING": 1.08, "SUPPORT": 0.95},
    "positive": {"ENTERTAINMENT": 1.10},
    "anxious": {"SECURITY": 1.10},
}


def _apply_emotion_factors(
    scores: dict[str, float], ms: MessageState, rules: list[str]
) -> tuple[dict[str, float], list[str]]:
    """情绪联动：根据情绪类型微调需求。
    impulse（念头）时因子向 1.0 收缩一半，不当真。
    """
    # impulse 阻尼：将因子向 1.0 方向拉一半
    damp = 0.5 if ms.is_impulse else 0.0

    applied = False

    # 负面情绪
    if ms.emotion_is_negative:
        for need, raw_factor in EMOTION_FACTORS["negative"].items():
            factor = _damp(factor=raw_factor, toward=1.0, strength=damp)
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            tag = f"(念头阻尼 ×{factor:.3f})" if damp > 0 else ""
            rules = _add_rule(rules, "emotion", f"{need} {old:.2f}→{new:.2f} (×{factor:.2f}, 负面情绪) {tag}")
            applied = True

    # 积极情绪
    if ms.emotion_is_positive:
        for need, raw_factor in EMOTION_FACTORS["positive"].items():
            factor = _damp(raw_factor, 1.0, damp)
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            tag = f"(念头阻尼 ×{factor:.3f})" if damp > 0 else ""
            rules = _add_rule(rules, "emotion", f"{need} {old:.2f}→{new:.2f} (×{factor:.2f}, 积极情绪) {tag}")
            applied = True

    # 焦虑
    if ms.emotion == "anxious":
        for need, raw_factor in EMOTION_FACTORS["anxious"].items():
            factor = _damp(raw_factor, 1.0, damp)
            old = scores.get(need, 0)
            _mult(scores, need, factor)
            new = round(scores[need], 3)
            tag = f"(念头阻尼 ×{factor:.3f})" if damp > 0 else ""
            rules = _add_rule(rules, "emotion", f"{need} {old:.2f}→{new:.2f} (×{factor:.2f}, 焦虑) {tag}")
            applied = True

    if applied and damp > 0:
        rules = _add_rule(rules, "impulse-damping", "念头表达，情绪因子向 1.0 收敛 50%")

    return scores, rules


def _damp(factor: float, toward: float, strength: float) -> float:
    """将 factor 向 toward 方向收缩 strength 比例。"""
    if strength <= 0:
        return factor
    return round(factor + (toward - factor) * strength, 4)
