import json
from pathlib import Path
from typing import Optional

STRATEGIES_DIR = Path(__file__).parent / "strategies"


class StrategyCard:
    """核心策略卡：决定'该说什么'"""
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.type: str = data.get("type", "core_strategy")
        self.goal: str = data.get("goal", "")
        self.source: str = data.get("source", "")

        self.apply_when: dict = data.get("apply_when", {})
        self.not_apply_when: dict = data.get("not_apply_when", {})
        self.requirements: dict = data.get("requirements", {})
        self.risk_level: str = data.get("risk_level", "medium")
        self.target_need: list[str] = data.get("target_need", [])
        self.expected_effect: dict = data.get("expected_effect", {})

        self.mechanism: str = data.get("mechanism", "")
        self.formula: dict = data.get("formula", {})
        self.rules: list[str] = data.get("rules", [])
        self.anti_patterns: list[str] = data.get("anti_patterns", [])
        self.examples: list[dict] = data.get("examples", [])
        self.llm_instruction: str = data.get("llm_instruction", "")
        self.success_metric: str = data.get("success_metric", "")
        self.related: list[str] = data.get("related", [])

    def __repr__(self):
        return f"StrategyCard(id={self.id}, name={self.name}, type={self.type})"


class ExpressionBooster:
    """表达增强器：决定'怎么说'"""
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.type: str = data.get("type", "expression_booster")
        self.goal: str = data.get("goal", "")
        self.source: str = data.get("source", "")
        self.position: str = data.get("position", "")

        self.apply_when: dict = data.get("apply_when", {})
        self.not_apply_when: dict = data.get("not_apply_when", {})
        self.risk_level: str = data.get("risk_level", "low")

        self.definition: str = data.get("definition", "")
        self.elements: dict = data.get("elements", {})
        self.safety_rule: str = data.get("safety_rule", "")
        self.examples: list[dict] = data.get("examples", [])
        self.llm_instruction: str = data.get("llm_instruction", "")
        self.effect_on: dict = data.get("effect_on", {})
        self.related: list[str] = data.get("related", [])

    def __repr__(self):
        return f"ExpressionBooster(id={self.id}, name={self.name})"


class StrategyLoader:
    def __init__(self, strategies_dir: str = None):
        self.dir = Path(strategies_dir) if strategies_dir else STRATEGIES_DIR
        self._strategies: dict[str, StrategyCard] = {}
        self._boosters: dict[str, ExpressionBooster] = {}
        self._load_all()

    def _load_all(self):
        core_dir = self.dir / "core_strategies"
        if core_dir.exists():
            for f in sorted(core_dir.glob("*.json")):
                card = StrategyCard(json.loads(f.read_text(encoding="utf-8")))
                self._strategies[card.id] = card

        booster_dir = self.dir / "expression_boosters"
        if booster_dir.exists():
            for f in sorted(booster_dir.glob("*.json")):
                booster = ExpressionBooster(json.loads(f.read_text(encoding="utf-8")))
                self._boosters[booster.id] = booster

    # --- Strategy ---

    def get_strategy(self, strategy_id: str) -> Optional[StrategyCard]:
        return self._strategies.get(strategy_id)

    def list_strategies(self) -> list[StrategyCard]:
        return list(self._strategies.values())

    def list_strategy_ids(self) -> list[str]:
        return list(self._strategies.keys())

    # --- Booster ---

    def get_booster(self, booster_id: str) -> Optional[ExpressionBooster]:
        return self._boosters.get(booster_id)

    def list_boosters(self) -> list[ExpressionBooster]:
        return list(self._boosters.values())

    def list_booster_ids(self) -> list[str]:
        return list(self._boosters.keys())
