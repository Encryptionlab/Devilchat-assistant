# 策略卡结构说明

## Core Strategy / Meta Strategy

```json
{
  "id": "string",              // 唯一标识，snake_case
  "name": "string",            // 中文名称
  "type": "core_strategy | meta_strategy",
  "source": "string",          // 书中出处
  "goal": "string",            // 一句话目标
  "position": "string",        // [仅 meta_strategy] 在 pipeline 中的位置

  "apply_when": {
    "description": "string",              // 适用场景描述
    "trigger_signals": ["string"],        // 触发信号列表
    "relationship_stage": ["string"],     // 适用关系阶段
    "emotions": ["string"],               // [可选] 适用情绪
    "key_concept": "string"               // [可选] 关键概念
  },

  "not_apply_when": {
    "signals": ["string"],                // 不适用信号
    "emotions": ["string"],               // [可选] 不适用情绪
    "scenarios": ["string"]               // [可选] 不适用场景
  },

  "risk_level": "low | medium | high",
  "target_need": ["string"],              // 目标需求（对应 goal_libary.md）
  "expected_effect": {                    // 各维度效果评分 1-3
    "dimension_name": 3
  },

  "mechanism": "string",                  // 核心机制说明（为什么有效）

  "formula": {                            // 操作公式
    "step_1": {
      "name": "string",
      "purpose": "string",
      "pattern": "string",
      "branches": {                       // [可选] 分支决策
        "分支A": {
          "pattern": "string",
          "example": "string",
          "note": "string"
        },
        "分支B": { }
      }
    },
    "step_2": { }
  },

  "rules": ["string"],                    // 执行规则
  "anti_patterns": ["string"],            // 禁忌模式

  "examples": [
    {
      "context": "string",                // 场景描述
      "input": "string",                  // 对方的话
      "branch": "string",                 // [可选] 分支名
      "response": "string",               // 你的回复
      "why": "string"                     // 为什么对
    }
  ],

  "llm_instruction": "string",            // 给 LLM 的直接执行指令
  "success_metric": "string",             // 成功指标
  "related": ["strategy_id"]              // 关联策略
}
```

## Expression Booster

```json
{
  "id": "string",
  "name": "string",
  "type": "expression_booster",
  "source": "string",
  "goal": "string",
  "position": "string",                   // 在 pipeline 中的位置

  "apply_when": {
    "description": "string"
  },
  "not_apply_when": {
    "scenarios": ["string"]
  },
  "risk_level": "string",

  "definition": "string",                 // 一句话定义
  "elements": {                           // 构成要素
    "要素名": "string"
  },
  "why_it_works": "string",               // [可选] 为什么有效
  "source_theory": "string",              // [可选] 书中理论依据
  "safety_rule": "string",                // 安全法则
  "balance_note": "string",               // [可选] 平衡说明

  "examples": [
    {
      "strategy": "string",               // 使用的策略名
      "context": "string",                // [可选]
      "input": "string",                  // [可选] 对方的话
      "plain": "string",                  // 平淡版本
      "boosted": "string"                 // 增强后版本
    }
  ],

  "llm_instruction": "string",
  "effect_on": {                          // 各维度效果评分 1-3
    "dimension_name": 3
  },
  "related": ["strategy_id"]
}
```

## 两种卡的区别

| | Core Strategy | Expression Booster |
|---|---|---|
| 解决的问题 | **说什么** | **怎么说** |
| 核心字段 | `mechanism` + `formula` | `definition` + `elements` |
| 示例格式 | input → response | plain → boosted |
| 在 pipeline 中的位置 | 回复生成阶段 | 表达增强阶段 |
