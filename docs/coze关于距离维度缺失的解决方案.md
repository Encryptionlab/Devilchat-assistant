---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4021381275058560_0/project_7665906678516334848-files/docs/DISTANCE_DIMENSION_DESIGN.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4021381275058560#1784946073798
    ReservedCode2: ""
---
# 距离维度设计方案

> 基于《距离维度缺失分析》评估，提出最小侵入式解决方案
>
> Version: 1.0 | 2026-07-25
>
> 核心思路：
> - 两层上下文注入（LLM 自然推理）+ 一处策略过滤（显式规则）
> - 不引入新的决策链路，不制造错误放大
> - 与 v2 MVP 哲学一致：让 LLM 做推理，规则只做兜底

---

## 0. 背景

《距离维度缺失分析》指出：当前 `relationship_state.json` 只捕获了关系的**纵向深度**（stage: stranger → stable），完全缺失**横向空间距离维度**。同一恋爱阶段下，距离模式不同，回复策略应当不同。

分析文档准确识别了问题，影响面拆解也很细致。但其中 3.2 节提出的"need 调整因子表"方案存在风险：

```
need_recognition 硬编码距离因子（如 SECURITY += 0.1）
    ↓
goal_planner 拿到被调整后的 need
    ↓
如果因子设错 → goal 偏移 → 策略偏移 → 回复偏移
```

这正是 v1→v2 评审时反复强调的**错误放大链路**，只是换了一层皮。

本方案的核心判断是：**距离对语义理解的影响，LLM 天然能推理；距离对策略选择的约束，需要显式规则。** 因此方案聚焦于"注入上下文让 LLM 自己理解"而非"硬编码因子教 LLM 怎么算"。

---

## 1. 设计原则

1. **最小侵入**：不改现有模块签名，只在编排层（run.py）注入距离信息。
2. **LLM 优先推理**：距离对语义、需求、目标的影响交给 LLM 自然理解，不硬编码因子表。
3. **规则兜底约束**：策略卡适用性和表达语气，用显式规则约束——这些是工程判断，LLM 不如规则可靠。
4. **正交独立**：`distance_mode` 与 `stage` 独立维护，组合产生实际行为差异。
5. **手动维护优先**：距离模式变更暂不自动化，和 stage 一样手动维护。

---

## 2. 四种距离模式

| 模式 | 定义 | 见面频率 | 典型场景 |
|---|---|---|---|
| `same_city` | 同城 | 随时可约 | 同城恋爱、同校、同公司 |
| `short_separation` | 短期分离 | ≤30 天内恢复 | 出差、旅行、探亲、假期回家 |
| `long_distance` | 异地恋 | 偶尔见面（月/季度） | 不同城市、跨国 |
| `online_only` | 纯网恋 | 从未见面 | 社交 App 匹配、游戏 CP |

---

## 3. 核心方案：两层注入 + 一处过滤

### 3.1 第一层：Universal Context Injection（几乎零代码改动）

在所有调用 LLM 的模块的 user_prompt 中注入距离信息：

```
【距离模式：异地恋】
```

一行文字。注入到以下模块：

| 模块 | 注入方式 | 现有改动量 |
|---|---|---|
| `message_understanding.py` | user_prompt 增加 `【距离模式：{distance_mode}】` | 1 行 |
| `need_recognition.py` | user_prompt 增加 `【距离模式：{distance_mode}】` | 1 行 |
| `goal_planner.py` | user_prompt 增加 `【距离模式：{distance_mode}】` | 1 行 |
| `reply_generator.py` | user_prompt 增加 `【距离模式：{distance_mode}】` | 1 行 |

**为什么不需要 need 调整因子表：**

分析文档 3.1 节的表格恰恰证明了这一点——这些差异是**语义层面的**：

| 她说 | 同城 | 异地 |
|---|---|---|
| "我想你了" | 撒娇，今晚可约 | 真实思念 + 无力感 |
| "你在干嘛" | 闲聊/想你了 | 查岗/需要安全感 |
| "周末有空吗" | 日常邀约 | 重大事件 |

LLM 天然理解"异地恋中的'我想你了'更真实"。你不需要用 `SECURITY += 0.1` 去教它。硬编码因子表反而会：
- 制造维护负担（每种距离模式 × 每个 need 类型 = 16 个因子）
- 引入新的错误放大链路
- 与 LLM 的自然推理能力冲突

**注入后的 prompt 效果示例：**

need_recognition.py 的 user_prompt 原本可能是：

```
分析以下消息的需求...
她：我想你了
```

注入后：

```
【距离模式：异地恋】

分析以下消息的需求...
她：我想你了
```

LLM 会自然将"异地恋"作为上下文因子纳入需求判断，无需任何代码逻辑改动。

### 3.2 第二层：Strategy Card Distance Filter（中改动，有独立价值）

策略卡是规则驱动的，距离过滤与现有 `apply_when` / `not_apply_when` 完全一致：

```json
{
  "id": "signal_escalation",
  "apply_when": {
    "relationship_stage": ["ambiguous"],
    "distance_mode": ["same_city", "short_separation"]
  },
  "not_apply_when": {
    "distance_mode": ["long_distance", "online_only"]
  }
}
```

这是唯一值得用硬编码规则的地方，因为策略卡的适用性是**工程判断**而非语义理解——"异地时释放信号无物理反馈"这种约束，需要显式声明，不能依赖 LLM 每次都推理对。

### 3.3 第三处：Expression Tone 映射（小改动）

`expression_enhancer.py` 的 `STAGE_TONE` 从 `stage → tone` 扩展为 `(stage, distance_mode) → tone`：

```python
STAGE_TONE = {
    # same_city
    ("stranger", "same_city"): "礼貌、友好，保持距离",
    ("acquaintance", "same_city"): "自然、轻松，可以适度幽默",
    ("friend", "same_city"): "亲切、自然，像真正的朋友",
    ("ambiguous", "same_city"): "暧昧、试探，带一点心动感",
    ("dating", "same_city"): "亲密、自然，可以适度表达喜欢",
    ("stable", "same_city"): "温暖、默契，日常但充满安全感",
    
    # long_distance
    ("stranger", "long_distance"): "礼貌但更需主动，距离感天然存在",
    ("acquaintance", "long_distance"): "自然、温和，需要更多文字温度",
    ("friend", "long_distance"): "亲切但需更多关心，文字是唯一载体",
    ("ambiguous", "long_distance"): "暧昧但更克制，过度推进有风险",
    ("dating", "long_distance"): "温暖但克制，每条消息承载更多分量，避免轻浮",
    ("stable", "long_distance"): "深情但需安全感锚点，道别更温暖",
    
    # online_only
    ("stranger", "online_only"): "礼貌、好奇，保持适度距离",
    ("acquaintance", "online_only"): "自然但温和，不过度亲密",
    ("friend", "online_only"): "亲切但尊重边界，不能施压",
    ("ambiguous", "online_only"): "暧昧但谨慎，未见面时过度亲密有风险",
    ("dating", "online_only"): "亲密但有分寸，适度表达但保持分寸感",
    ("stable", "online_only"): "深情但注重安全感，每条消息都需要分量",
    
    # short_separation（近似 same_city 但加点思念感）
    ("stranger", "short_separation"): "礼貌、友好，保持距离",
    ("acquaintance", "short_separation"): "自然、轻松，可以适度幽默",
    ("friend", "short_separation"): "亲切、自然，带一点关心分离期",
    ("ambiguous", "short_separation"): "暧昧、试探，带一点思念",
    ("dating", "short_separation"): "亲密、期待重聚，可以表达想念",
    ("stable", "short_separation"): "温暖、默契，带期待感",
}
```

默认 fallback 逻辑：如果 `(stage, distance_mode)` 未定义，回退到 `(stage, "same_city")`，再回退到原有 `stage → tone`。

---

## 4. 数据模型变更

### 4.1 relationship_state.json

```json
{
  "relationship_state": {
    "stage": "dating",
    "distance_mode": "long_distance",    // 新增
    "conflict": 0,
    ...
  }
}
```

新增字段：

```python
distance_mode: str  # "same_city" | "short_separation" | "long_distance" | "online_only"
```

默认值：`"same_city"`（向后兼容，未设置时按同城处理）。

### 4.2 不新增独立文件

`distance_mode` 放在 `relationship_state.json` 内部，不单独维护。和 `stage` 一样手动维护。

---

## 5. 各模块改动详情

### 5.1 run.py（编排层）—— 主要改动点

在构建各模块 prompt 时，从 `relationship_state.json` 读取 `distance_mode`，注入到 user_prompt：

```python
# run.py 中的伪代码
distance_mode = relationship_state.get("distance_mode", "same_city")
distance_label = DISTANCE_LABELS.get(distance_mode, "同城")

# 注入到每个 LLM 模块的 user_prompt
mu_prompt = f"【距离模式：{distance_label}】\n\n{original_mu_prompt}"
need_prompt = f"【距离模式：{distance_label}】\n\n{original_need_prompt}"
goal_prompt = f"【距离模式：{distance_label}】\n\n{original_goal_prompt}"
reply_prompt = f"【距离模式：{distance_label}】\n\n{original_reply_prompt}"
```

距离标签映射：

```python
DISTANCE_LABELS = {
    "same_city": "同城",
    "short_separation": "短期分离",
    "long_distance": "异地恋",
    "online_only": "纯网恋（未见面）",
}
```

### 5.2 message_understanding.py

**改动：无代码逻辑改动，仅 prompt 上下文注入。**

效果：LLM 在理解消息时自然考虑距离因素。例如"我去洗澡了"在异地恋中可能不只是结束信号，也可能是回避——LLM 能自然判断。

### 5.3 need_recognition.py

**改动：无代码逻辑改动，仅 prompt 上下文注入。**

不新增 need 调整因子表。LLM 在分析需求时自然考虑距离背景：

- 异地恋中"你在干嘛" → 自然倾向识别为 SECURITY 需求
- 同城中"你在干嘛" → 自然倾向识别为日常闲聊

这是 LLM 的语义理解能力，不需要规则去教。

### 5.4 goal_planner.py

**改动：无代码逻辑改动，仅 prompt 上下文注入。**

Goal 优先级自然受距离影响：
- 异地恋中 SUPPORT 优先级可能自然高于 ENTERTAINMENT
- 同城中两者可能持平

不需要硬编码"距离感知的 goal 优先覆盖规则"。

### 5.5 strategy_selector.py

**改动：策略卡过滤逻辑增加距离维度。**

```python
def filter_strategies(strategies, relationship_state, conversation):
    stage = relationship_state["stage"]
    distance_mode = relationship_state.get("distance_mode", "same_city")
    
    filtered = []
    for strategy in strategies:
        apply_when = strategy.get("apply_when", {})
        not_apply_when = strategy.get("not_apply_when", {})
        
        # 现有 stage 过滤
        if "relationship_stage" in apply_when:
            if stage not in apply_when["relationship_stage"]:
                continue
        
        # 新增 distance_mode 过滤
        if "distance_mode" in apply_when:
            if distance_mode not in apply_when["distance_mode"]:
                continue
        if "distance_mode" in not_apply_when:
            if distance_mode in not_apply_when["distance_mode"]:
                continue
        
        filtered.append(strategy)
    
    return filtered
```

### 5.6 expression_enhancer.py

**改动：STAGE_TONE 表扩展为二维映射。**

```python
def get_tone(stage, distance_mode="same_city"):
    key = (stage, distance_mode)
    if key in STAGE_TONE:
        return STAGE_TONE[key]
    # fallback: 同城
    if (stage, "same_city") in STAGE_TONE:
        return STAGE_TONE[(stage, "same_city")]
    # 最终 fallback
    return "自然、温和"
```

### 5.7 reply_generator.py

**改动：无代码逻辑改动，仅 prompt 上下文注入。**

### 5.8 conversation.py

**改动：无。**

Conversation 引擎的话题检测和边界判断不依赖关系状态，距离维度对此模块无影响。

### 5.9 context_builder.py

**改动：将 distance_mode 加入 context 输出。**

```python
context = {
    "relationship_memory": {
        ...
        "distance_mode": relationship_state.get("distance_mode", "same_city"),  # 新增
    },
    ...
}
```

### 5.10 memory_updater.py

**改动：无（MVP 阶段）。**

距离模式变更暂不自动写入记忆。如果后续需要自动检测距离变化（如对话中出现"我搬到 XX 了"），可在 P2+ 阶段扩展。

---

## 6. 策略卡改动

### 6.1 现有策略卡距离适配

| 策略卡 | apply_when 距离约束 | not_apply_when 距离约束 | 原因 |
|---|---|---|---|
| `signal_escalation` | `["same_city", "short_separation"]` | `["long_distance", "online_only"]` | 异地时释放信号无物理反馈，需更保守 |
| `care_vs_attention` | 无限制 | 无限制 | 逻辑不变，但 LLM 通过上下文注入自然调整"关注"和"关心"的权重 |
| `eighty_twenty_rule` | 无限制 | 无限制 | 比例由 LLM 通过上下文自然调整 |
| `humorous_deflection` | `["same_city", "short_separation"]` | `["long_distance"]` | 异地时用幽默转移可能被解读为不在乎 |
| `validate_emotion_express_need` | 无限制 | 无限制 | 适用所有场景，力度由 LLM 自然调整 |
| `escalating_conflict` | 无限制 | `["long_distance", "online_only"]` | 异地冲突无法当面和解，需特殊处理 |

**注意：** 只对真正有距离约束的策略卡加过滤。通用策略卡（如 `care_vs_attention`、`eighty_twenty_rule`）不加过滤，让 LLM 通过上下文注入自然调整执行力度。过度过滤反而会限制 LLM 的灵活性。

### 6.2 可能新增的策略卡（P2+，暂不实现）

| 策略卡 | apply_when | 策略描述 |
|---|---|---|
| `distance_security_anchor` | `distance_mode in ["long_distance", "online_only"]` | 在回复中植入安全感锚点（如"我一直都在"、"下次见面..."） |
| `reunion_warmup` | `distance_mode == "short_separation"` | 分离期尾声主动预热重聚情绪 |

这些新卡属于 P2+，MVP 阶段先用现有卡的距离过滤 + 上下文注入覆盖核心场景。

---

## 7. 距离模式生命周期

### 7.1 状态转换

```
same_city → short_separation    用户手动修改（出差、旅行）
short_separation → same_city    用户手动修改（回来后）
same_city → long_distance       用户手动修改（异地恋开始）
long_distance → same_city       用户手动修改（结束异地）
any → online_only               用户手动修改（网恋阶段）
online_only → same_city         用户手动修改（奔现）
```

### 7.2 short_separation 恢复机制

MVP 阶段：手动恢复。

后续（P2+）可基于对话事件自动检测：
- 对话中出现"我回来了""到家了""回来了"等关键词 → 提示用户确认恢复
- 或在 Memory Updater 中增加距离模式恢复规则

### 7.3 不做的转换

- 不做 distance_mode → stage 的反向调整（距离模式不自动修改关系阶段）
- 不做"见面倒计时"等时间敏感功能
- `online_only` → `same_city` 的过渡（奔现）暂不做专项处理

---

## 8. 与原分析方案的对比

| 维度 | 原分析方案 | 本方案 | 差异原因 |
|---|---|---|---|
| relationship_state.json | 新增 distance_mode | 同 ✅ | — |
| message_understanding.py | 上下文注入 | 同 ✅ | — |
| need_recognition.py | **4 种距离 × need 因子表** | **仅注入上下文** | 避免错误放大链路，LLM 天然能推理 |
| goal_planner.py | **距离感知 goal 覆盖规则** | **仅注入上下文** | 同上，goal 优先级交给 LLM 自然判断 |
| strategy_selector.py | 过滤 + 打分 | 过滤（不加打分调整） | 打分调整与因子表同理，交给 LLM |
| expression_enhancer.py | 语气映射 | 同 ✅ | — |
| reply_generator.py | 上下文注入 | 同 ✅ | — |
| 策略卡 JSON | 增加距离字段 | 同 ✅ | — |
| 可能新增策略卡 | 2 张新卡 | 后置到 P2+ | MVP 先用现有卡覆盖 |
| 总改动量 | 中（需实现因子表 + 覆盖规则） | **小（4 处注入 + 1 处过滤 + 1 处映射）** | 核心差异 |

---

## 9. 开发计划

### Phase 1：最小集成（P1，与 Conversation v2 MVP 同期）

| 步骤 | 内容 | 改动量 | 验收标准 |
|------|------|--------|---------|
| 1 | `relationship_state.json` 新增 `distance_mode` 字段 | 极小 | 默认 `same_city`，向后兼容 |
| 2 | `run.py` 注入距离标签到 4 个 LLM 模块 prompt | 小 | 各模块 prompt 中出现 `【距离模式：XX】` |
| 3 | `expression_enhancer.py` 扩展 STAGE_TONE 为二维映射 | 小 | 不同距离下语气有差异 |
| 4 | `strategy_selector.py` 增加距离过滤逻辑 | 小 | 距离不适用的策略卡被过滤 |
| 5 | 3 张策略卡增加 distance_mode 字段 | 小 | signal_escalation / humorous_deflection / escalating_conflict 正确过滤 |
| 6 | `context_builder.py` 输出 distance_mode | 极小 | context 中包含距离信息 |

### Phase 2：策略细化（P2）

| 步骤 | 内容 | 验收标准 |
|------|------|---------|
| 1 | 用真实对话验证 LLM 在距离上下文下的理解质量 | "我想你了"在异地恋中正确识别为更深层思念 |
| 2 | 补充策略卡距离字段（视实际效果决定） | 不过度过滤，保留 LLM 灵活性 |
| 3 | 新增 `distance_security_anchor` 策略卡 | 异地恋回复中自然出现安全感锚点 |

### Phase 3：自动化（P3，暂不实现）

| 步骤 | 内容 | 验收标准 |
|------|------|---------|
| 1 | 对话事件触发距离模式变更（"我回来了"→恢复 same_city） | 准确率 > 80% |
| 2 | short_separation 自动超时恢复 | 30 天后自动回 same_city |
| 3 | 新增 `reunion_warmup` 策略卡 | 分离尾声自然预热重聚情绪 |

---

## 10. 降级策略

```
distance_mode 字段缺失 → 默认 same_city，系统正常工作
distance_mode 值无效 → 默认 same_city，记录告警
STAGE_TONE 二维映射未覆盖 → fallback 到 (stage, "same_city")
策略卡无 distance_mode 字段 → 视为无距离限制，正常通过
```

所有降级路径都回退到 `same_city`，确保系统不会因为距离维度引入而崩溃。

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| LLM 忽略距离上下文注入 | 中 | 中 | 通过实际对话验证；必要时在 prompt 中增加距离影响示例 |
| 策略卡过度过滤导致回复单调 | 低 | 中 | 只对真正有约束的卡加过滤；通用卡不加 |
| 用户忘记手动修改 distance_mode | 高 | 低 | MVP 阶段可接受；P3 自动化后解决 |
| short_separation 长期不恢复 | 中 | 低 | P3 自动超时恢复；MVP 阶段提示用户 |

---

## 12. 总结

```
距离维度核心思路：

  语义理解层（message_understanding / need_recognition / goal_planner / reply_generator）
    → 上下文注入一行【距离模式：XX】
    → LLM 自然推理，不硬编码因子
    → 零决策链路风险

  策略约束层（strategy_selector）
    → 策略卡增加 distance_mode 过滤
    → 显式规则，工程判断

  表达层（expression_enhancer）
    → STAGE_TONE 扩展为 (stage, distance_mode) → tone
    → 直接控制语气温度

  数据层（relationship_state.json）
    → 新增 distance_mode 字段
    → 手动维护，与 stage 正交

  改动量：4 处 prompt 注入（各 1 行）+ 1 处策略过滤 + 1 处语气映射
  新增模块：无
  新增决策链路：无
  错误放大风险：无
```

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
