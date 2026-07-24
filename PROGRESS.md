# 项目进度

最后更新: 2026-07-24

## 流水线

```
聊天记录 → 消息理解 → 需求识别 → 目标确定 → 策略选择 → 回复生成 → 表达增强 → 风险检查 → 回复评分 → 最终回复
```

| # | 模块 | 状态 | 说明 |
|---|---|---|---|
| 1 | 消息理解 | ✅ 完成 | surface_intent/need 改为打分模式，输出稳定 |
| 2 | 需求识别 | ✅ 完成 | 纯规则引擎，4 类规则（阶段门槛/事件加成/情绪联动/念头阻尼） |
| 3 | 目标确定 | ✅ 完成 | 阶段×需求类别→单一Goal，冲突/情绪优先覆盖 |
| 4 | 策略选择 | ✅ 完成 | 双维度过滤 + need 匹配 + 动态风险惩罚，通用 requirements 检查 |
| 5 | 回复生成 | ✅ 完成 | 策略卡 llm_instruction + 关系上下文 → LLM 生成回复 |
| 6 | 表达增强 | ✅ 完成 | 去机器人感 + 语气匹配关系阶段 + 拆句/口语化 |
| 7 | 风险检查 | ⬜ | |
| 8 | 回复评分 | ⬜ | |
| 9 | 编排脚本 | ⬜ | |

## 基础设施

| 内容 | 状态 | 说明 |
|---|---|---|
| 关系状态 (relationship_state.json) | ✅ | 手动维护，7 个维度 |
| 策略卡加载器 (strategy_loader.py) | ✅ | 6 张核心策略卡 |
| 统一 Need 库 (need_library.md) | ✅ | 12 个 needs，行为化描述 |
| 消息理解库 (MESSAGE_UNDERSTANDING_library.md) | ✅ | 13 字段 schema |
| 关系状态库 (RELATIONSHIP_STATE_library.md) | ✅ | 7 层 schema |
| 运行入口 (run.py) | ✅ | 全流水线：消息理解 → 需求识别 → 目标确定 → 策略选择 → 回复生成 |
| 策略选择器 (strategy_selector.py) | ✅ | 双维度过滤 + need/context 打分 + 动态风险衰减 |
| 回复生成器 (reply_generator.py) | ✅ | 策略卡指令 + 关系上下文 + 对话历史 → LLM prompt |
| 表达增强器 (expression_enhancer.py) | ✅ | 口语化 + 语气匹配 + 关系阶段感知 |

## 决策记录

- surface_intent/need 采用打分模式（非单选），解决标签不互斥和输出不稳定
- need 定义从心理学分类改为行为描述（"她希望你做什么"）
- LLM 通过 OpenCode API 调用，默认 deepseek-v4-flash
- 密钥从 ds.txt 读取，不设环境变量
