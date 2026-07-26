"""
Evaluator Agent —— 策略效果评估器（蓝图第 8 层：长期学习）。

在下一轮对话开始时评估上一轮策略的实际效果。

原理（Section 8）：
    不要让系统学习「如何回复」。
    让系统学习「什么情绪 + 什么需求 + 什么策略最有效」。

工作方式：
    1. 收到她的新消息时 → 对比上一轮的策略 + 实际回应
    2. 对比前后情绪变化 + 关键信号变化
    3. 更新 strategy_effectiveness 统计
    4. 持久化到 relationship_state.json

用法：
    >>> evaluator = StrategyEvaluator()
    >>> result = evaluator.evaluate(
    ...     last_strategy="共情",
    ...     her_messages_before=["好累啊"],
    ...     her_messages_after=["嗯就是复习压力大"],
    ...     my_message="听起来今天真的很累，好好休息",
    ...     emotion_before="tired",
    ...     emotion_after="sad",
    ... )
    >>> print(result)  # {"success": True, "reason": "..."}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
RS_PATH = ROOT_DIR / "data" / "relationship_state.json"


# ============================================================
# 策略成功标准（来自蓝图 Section 2）
# ============================================================

STRATEGY_SUCCESS_CRITERIA: dict[str, dict] = {
    "共情": {
        "indicator": "继续倾诉",
        "checks": [
            "emotion_less_negative",      # 情绪不再恶化
            "continues_sharing",           # 继续表达（非一字回复）
            "no_deflection",               # 没有转移话题或冷处理
        ],
    },
    "倾听": {
        "indicator": "聊天内容增加",
        "checks": [
            "message_length_increased",
            "emotion_not_worse",
        ],
    },
    "开放式提问": {
        "indicator": "延长对话",
        "checks": [
            "continues_talking",
            "not_one_word_reply",
        ],
    },
    "赞美": {
        "indicator": "增强认同",
        "checks": [
            "emotion_improved",            # 情绪转正向
        ],
    },
    "安全感建设": {
        "indicator": "缓解焦虑",
        "checks": [
            "emotion_from_anxious_to_calm",  # 从焦虑 → 平静/正向
            "less_testing",                  # 减少关系试探
        ],
    },
    "调侃": {
        "indicator": "增加情绪波动",
        "checks": [
            "emotion_changed",             # 情绪有变化（正向）
        ],
    },
    "陪伴": {
        "indicator": "提供情绪支持",
        "checks": [
            "engagement_maintained",       # 参与度维持
        ],
    },
    "冲突缓和": {
        "indicator": "降低对抗",
        "checks": [
            "conflict_signal_reduced",     # 冲突信号降低
            "emotion_less_angry",          # 情绪从愤怒降级
        ],
    },
}

# 正向情绪集合
POSITIVE_EMOTIONS = {"happy", "excited", "hopeful", "grateful", "neutral"}
# 负向情绪集合
NEGATIVE_EMOTIONS = {"sad", "disappointed", "angry", "anxious", "lonely", "jealous", "embarrassed"}
# 冲突信号集合
CONFLICT_SIGNALS = {"conflicting", "withdrawing", "testing"}


@dataclass
class StrategyEvalResult:
    """单次策略评估结果。"""
    strategy: str
    success: bool
    partial: bool  # 部分有效（降级成功）
    reason: str
    indicators_met: list[str] = field(default_factory=list)
    indicators_missed: list[str] = field(default_factory=list)


class StrategyEvaluator:
    """策略效果评估器。不依赖 LLM，纯规则评估。"""

    def __init__(self, rs_path: Path | None = None):
        self._rs_path = rs_path or RS_PATH

    def evaluate(
        self,
        last_strategy: str,
        her_messages_before: list[str],
        her_messages_after: list[str],
        my_message: str,
        emotion_before: str,
        emotion_after: str,
        conflict_signal_before: str = "none",
        conflict_signal_after: str = "none",
    ) -> StrategyEvalResult:
        """评估上一轮策略的效果。

        Args:
            last_strategy: 上一轮使用的策略名称
            her_messages_before: 她在我回复之前的消息列表
            her_messages_after: 她在我回复之后的消息列表
            my_message: 我实际发送的消息（不是 AI 建议的原样，是用户实际发的）
            emotion_before: 回复前她的情绪
            emotion_after: 回复后她的情绪
            conflict_signal_before: 回复前冲突信号
            conflict_signal_after: 回复后冲突信号

        Returns:
            StrategyEvalResult 包含成功/失败/原因
        """
        criteria = STRATEGY_SUCCESS_CRITERIA.get(last_strategy)
        if not criteria:
            return StrategyEvalResult(
                strategy=last_strategy,
                success=False,
                partial=False,
                reason=f"未知策略 '{last_strategy}'，无法评估",
            )

        met: list[str] = []
        missed: list[str] = []

        for check in criteria["checks"]:
            passed = self._run_check(check, her_messages_before, her_messages_after,
                                     emotion_before, emotion_after,
                                     conflict_signal_before, conflict_signal_after)
            if passed:
                met.append(check)
            else:
                missed.append(check)

        # 判定：全部通过 = success，部分通过 = partial，全部失败 = fail
        total = len(criteria["checks"])
        met_count = len(met)

        if met_count == total:
            success = True
            partial = False
        elif met_count > 0:
            success = False
            partial = True
        else:
            success = False
            partial = False

        reason = self._build_reason(last_strategy, met, missed, partial)

        return StrategyEvalResult(
            strategy=last_strategy,
            success=success,
            partial=partial,
            reason=reason,
            indicators_met=met,
            indicators_missed=missed,
        )

    def _run_check(
        self,
        check: str,
        before: list[str],
        after: list[str],
        emo_before: str,
        emo_after: str,
        conflict_before: str,
        conflict_after: str,
    ) -> bool:
        """运行单个检查项。"""
        after_text = " ".join(after).strip()
        before_text = " ".join(before).strip()

        if check == "emotion_less_negative":
            # 情绪没有恶化到更负面
            if emo_before in NEGATIVE_EMOTIONS and emo_after in NEGATIVE_EMOTIONS:
                return True  # 都是负面，但没恶化
            if emo_before in POSITIVE_EMOTIONS and emo_after in NEGATIVE_EMOTIONS:
                return False  # 从正面变负面 = 恶化
            return True

        if check == "continues_sharing":
            return len(after_text) > 3

        if check == "no_deflection":
            return len(after_text) > 0

        if check == "message_length_increased":
            return len(after_text) >= len(before_text) * 0.5

        if check == "emotion_not_worse":
            if emo_after in {"angry", "disappointed"}:
                return False
            return True

        if check == "continues_talking":
            return len(after) > 0 and not all(len(m) <= 2 for m in after)

        if check == "not_one_word_reply":
            return not (len(after) == 1 and len(after[0]) <= 2)

        if check == "emotion_improved":
            return emo_after in POSITIVE_EMOTIONS

        if check == "emotion_from_anxious_to_calm":
            if emo_before == "anxious" and emo_after in POSITIVE_EMOTIONS:
                return True
            if emo_before == "anxious" and emo_after == "anxious":
                return False
            if emo_before != "anxious":
                return True  # 不是焦虑场景，不适用此检查
            return emo_after in POSITIVE_EMOTIONS

        if check == "less_testing":
            return conflict_after not in {"testing", "conflicting"}

        if check == "emotion_changed":
            return emo_before != emo_after

        if check == "engagement_maintained":
            return len(after) > 0 and len(after_text) > 0

        if check == "conflict_signal_reduced":
            if conflict_before in CONFLICT_SIGNALS and conflict_after == "none":
                return True
            if conflict_before == conflict_after:
                return False
            return conflict_after == "none"

        if check == "emotion_less_angry":
            if emo_before == "angry" and emo_after != "angry":
                return True
            if emo_before != "angry":
                return True
            return False

        return True  # 未知检查项默认通过

    def _build_reason(
        self,
        strategy: str,
        met: list[str],
        missed: list[str],
        partial: bool,
    ) -> str:
        indicator = STRATEGY_SUCCESS_CRITERIA.get(strategy, {}).get("indicator", strategy)
        if not missed:
            return f"✓ {indicator}"
        if partial:
            return f"△ {indicator}（部分满足）"
        return f"✗ 未达到 {indicator}"

    # ---- 持久化 ----

    def save_effectiveness(self, result: StrategyEvalResult) -> dict:
        """将评估结果写入 relationship_state.json 的 strategy_effectiveness 字段。"""
        if not self._rs_path.exists():
            return {}

        raw = json.loads(self._rs_path.read_text(encoding="utf-8"))
        inner = raw.get("relationship_state", raw)
        effectiveness = inner.get("strategy_effectiveness", {})

        entry = effectiveness.get(result.strategy, {
            "total_uses": 0,
            "successes": 0,
            "partials": 0,
            "failures": 0,
            "success_rate": 0.0,
            "last_used": "",
            "best_emotions": [],
            "worst_emotions": [],
        })

        entry["total_uses"] = entry.get("total_uses", 0) + 1
        if result.success:
            entry["successes"] = entry.get("successes", 0) + 1
        elif result.partial:
            entry["partials"] = entry.get("partials", 0) + 1
        else:
            entry["failures"] = entry.get("failures", 0) + 1

        entry["success_rate"] = round(
            entry["successes"] / entry["total_uses"], 3
        )
        entry["last_used"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        effectiveness[result.strategy] = entry
        inner["strategy_effectiveness"] = effectiveness
        raw["relationship_state"] = inner

        self._rs_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return entry


# ============================================================
# 便捷入口
# ============================================================

def evaluate_strategy(
    last_strategy: str,
    her_before: list[str],
    her_after: list[str],
    my_msg: str,
    emo_before: str,
    emo_after: str,
    conflict_before: str = "none",
    conflict_after: str = "none",
) -> StrategyEvalResult:
    """便捷函数：评估策略效果并持久化。"""
    evaluator = StrategyEvaluator()
    result = evaluator.evaluate(
        last_strategy=last_strategy,
        her_messages_before=her_before,
        her_messages_after=her_after,
        my_message=my_msg,
        emotion_before=emo_before,
        emotion_after=emo_after,
        conflict_signal_before=conflict_before,
        conflict_signal_after=conflict_after,
    )
    evaluator.save_effectiveness(result)
    return result
