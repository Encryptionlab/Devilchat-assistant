---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4021381275058560_0/project_7665906678516334848-files/docs/STRESS_TEST_FIX_PLAN.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4021381275058560#1785032861255
    ReservedCode2: ""
---
# 压力测试修复方案

> 基于 100 条消息压力测试问题分析，制定逐项修复方案
>
> Version: 1.0 | 2026-07-26
>
> 测试基线：118 条消息，模拟 14 天，354 次 LLM 调用，0 失败
>
> 核心原则：每步修复后重跑压力测试验证，确认效果再进下一步

---

## 0. 问题总览

| 编号 | 问题 | 严重程度 | 当前表现 | 修复优先级 |
|------|------|---------|---------|-----------|
| P0 | 话题检测失效 | 致命 | 88% 归入 daily，6 话题中 3 个完全未检出 | 先修 |
| P1 | unresolved_topics 污染 | 高 | 15 条中大量误判，日常寒暄被记为未解决问题 | 次修 |
| P2 | 策略选择失衡 | 中 | 60% 选同一张卡，4/6 张卡极少触发 | 后修 |
| P3 | 2h-8h 边界空缺 | 低 | 该区间 fallthrough 为 continue | 顺手修 |

**依赖关系：** P0 修复后 conversation 边界才能正常 → 摘要质量提升 → P1 输入更准确。必须按顺序执行。

---

## 1. P0：话题检测修复

### 1.1 问题复述

当前 `TOPIC_KEYWORDS` 约 60 个关键词，覆盖率严重不足。118 条消息中 104 条（88%）归入 daily，conflict/dating/family 完全未检出。

### 1.2 方案：LLM 话题检测 + 关键词兜底

在 `message_understanding.py` 的 LLM 输出中增加 `topic` 字段，让 LLM 在理解消息的同时输出话题分类。`conversation.py` 的 `detect_topic()` 优先使用 LLM 结果，仅在 LLM 未返回有效值时回退到关键词匹配。

### 1.3 具体改动

#### 1.3.1 message_understanding.py

在 system prompt 中增加话题分类指令：

```
请在分析消息时，同时输出话题分类。

话题列表（只选一个）：
- work: 工作/职业相关
- exam: 考试/学习/备考
- family: 家庭/家人
- relationship: 恋爱关系本身（双方关系、感情、未来、异地）
- dating: 约会/出行/娱乐安排
- conflict: 冲突/争吵/不满/抱怨对方
- daily: 日常闲聊（无法归入以上类别时使用）

分类依据：消息的核心内容，而非单个词汇。
例如"你从来都不主动"是 conflict，不是 daily。
例如"你会等我吗"是 relationship，不是 daily。
```

输出格式增加 `topic` 字段：

```json
{
  "surface_intent": "...",
  "need_scores": { ... },
  "emotion": "...",
  "topic": "conflict"
}
```

#### 1.3.2 conversation.py

`detect_topic()` 改为优先使用 LLM 结果：

```python
def detect_topic(message_content: str, llm_topic: str | None = None) -> str:
    """
    话题检测：优先使用 LLM 结果，回退到关键词匹配。
    """
    # 优先使用 LLM 结果
    if llm_topic and llm_topic in VALID_TOPICS:
        return llm_topic
    
    # 回退：关键词匹配（保留现有逻辑作为兜底）
    content = message_content.lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(1 for kw in keywords if kw in content)
    
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "daily"
```

#### 1.3.3 run.py 编排层

将 message_understanding 输出的 `topic` 传递给 conversation.py：

```python
# run.py 中的伪代码
mu_result = message_understanding.process(message)
topic = mu_result.get("topic")  # 新增

conversation, switched = conversation_manager.process_message(
    message_content=message,
    timestamp=timestamp,
    current_goal=current_goal,
    topic=topic,  # 新增参数
)
```

### 1.4 关键词表补充（兜底用）

虽然 LLM 检测为主，关键词表仍需补充，作为 LLM 不可用时的兜底：

```python
TOPIC_KEYWORDS = {
    "work": ["老板", "同事", "加班", "工作", "项目", "开会", "上班", "辞职", "绩效", "汇报", "工资", "升职", "跳槽"],
    "exam": ["考试", "复习", "做题", "论文", "答辩", "开学", "成绩", "作业", "考研", "刷题", "模考", "备考", "上岸", "挂科"],
    "family": ["妈", "爸", "家里", "爸妈", "弟弟", "妹妹", "哥哥", "姐姐", "回家", "我妈", "我爸", "父母", "家里人", "催", "相亲"],
    "relationship": ["我们", "感情", "在一起", "分手", "喜欢你", "想你", "爱你", "异地", "等你", "未来", "以后", "会不会", "我们以后", "在一起吗", "等你考完"],
    "dating": ["约会", "看电影", "吃饭去", "周末", "出去玩", "旅游", "机票", "酒店", "电影", "逛街", "一起吃", "这周末", "出去走走"],
    "conflict": ["吵架", "生气", "你总是", "你从来不", "为什么你", "不想理你", "冷战", "不主动", "不想理", "根本不", "从来不", "每次都是", "你是不是不想", "你都不", "不在乎"],
    "daily": [],
}
```

### 1.5 验收标准

```
重跑 118 条测试，话题分布应接近：
  daily:       ≤ 40%（从 88% 下降）
  exam:        ≥ 15%
  relationship: ≥ 8%
  conflict:    ≥ 5%
  dating:      ≥ 5%
  family:      ≥ 5%
```

---

## 2. P1：unresolved_topics 污染修复

### 2.1 问题复述

118 条消息后 `unresolved_topics` 堆积 15 条，其中大量误判（"道晚安""询问复习""感叹一周过得快"都被记为未解决问题）。

根因：
1. Summarizer 的 outcome 判定偏松（非 resolved 即 unresolved，缺少 neutral）
2. key_points 提取太碎（日常寒暄也被提取为关键信息）
3. memory_updater 规则无过滤（outcome=unresolved 时把所有 key_points 倾倒进 unresolved_topics）

### 2.2 方案：三管齐下

#### 2.2.1 修正 outcome 定义（改 summarizer prompt）

在 conversation summary 的 LLM prompt 中明确三档定义：

```
请判断对话结果：

outcome 取值：
- resolved: 问题已解决 / 情绪已缓解 / 达成共识
- unresolved: 明确存在未解决的冲突、分歧或悬而未决的问题
- neutral: 无问题需要解决（日常聊天、道晚安、闲聊感慨等）

重要：大部分日常对话应该是 neutral，不是 unresolved。
只有真正存在"需要解决但没解决"的情况才标 unresolved。
```

#### 2.2.2 约束 key_points 提取（改 summarizer prompt）

```
key_points 提取规则：
- 只提取对未来对话有参考价值的信息
- 日常寒暄、结束语、闲聊感慨不提取
- 限制最多 3 条
- 每条 key_point 需标注类型：
  - type: "unresolved" — 未解决的问题/冲突
  - type: "info" — 客观信息（如"下周有考试"）
  - type: "emotion" — 情绪状态（如"对异地感到焦虑"）

输出格式：
"key_points": [
  {"text": "母亲催考研并施压", "type": "unresolved"},
  {"text": "下周三有模考", "type": "info"}
]
```

#### 2.2.3 修正 memory_updater 规则

```python
# 修正前（当前逻辑）
if outcome == "unresolved" and key_points:
    for point in key_points:
        unresolved_topics.append(point)  # 全部倾倒

# 修正后
if outcome == "unresolved":
    for point in key_points:
        # 只写入标注为 unresolved 类型的 key_points
        if isinstance(point, dict) and point.get("type") == "unresolved":
            text = point.get("text", "")
            if text and text not in unresolved_topics:
                unresolved_topics.append(text)
```

### 2.3 验收标准

```
重跑 118 条测试：
  unresolved_topics 条数：≤ 5（从 15 下降）
  误判率（非 unresolved 的条目占比）：≤ 20%
  "道晚安""询问复习""感叹"等不应出现在 unresolved_topics 中
```

---

## 3. P2：策略选择失衡修复

### 3.1 问题复述

```
逐级释放与反馈循环    71  60%  ← 万能兜底
关心vs关注            27  23%
认可情绪+表达需求      14  12%
大小二八原则           5   4%
扩大冲突               1   1%   ← 几乎不触发
```

根因：
1. "逐级释放"条件最宽松，成了 default
2. "扩大冲突"条件过于严苛，需要精确匹配特定 need + emotion + intent 组合
3. 6 张卡中有 4 张极少被选中

### 3.2 方案：放宽策略卡条件 + 引入 conversation_stage 维度

#### 3.2.1 逐张审查策略卡条件

对每张策略卡的 `apply_when` / `not_apply_when` 做以下检查：

**检查清单：**
```
□ apply_when 条件是否过于具体？（如要求同时匹配 need + emotion + intent 三个维度）
□ 是否有合理的 fallback？（当条件不匹配时是否总是 fallback 到同一张卡？）
□ 同一场景下有几张卡能竞争？（目标：至少 2-3 张）
```

**预期调整方向：**

| 策略卡 | 当前问题 | 调整方向 |
|--------|---------|---------|
| 逐级释放与反馈循环 | 条件过宽，成 default | 增加 not_apply_when，在 conflict 场景下排除 |
| 扩大冲突 | 条件过严 | 放宽：conflict 话题 + complaint/accusation intent 即可触发，不要求精确 need 匹配 |
| 认可情绪+表达需求 | 条件适中 | 微调：降低 emotion 阈值要求 |
| 大小二八原则 | 条件适中 | 保持 |
| 关心vs关注 | 条件适中 | 保持 |
| humorous_deflection | 未提及触发情况 | 检查是否条件遗漏 |

#### 3.2.2 引入 conversation_stage 维度

message_understanding 已输出 `conversation_stage`（opening / elaborating / closing），但策略卡未使用。增加此维度可以让策略在对话不同阶段自然切换：

```json
{
  "id": "care_vs_attention",
  "apply_when": {
    "conversation_stage": ["opening", "closing"]
  }
}
```

```json
{
  "id": "escalating_conflict",
  "apply_when": {
    "conversation_stage": ["elaborating"]
  }
}
```

**注意：** conversation_stage 只是加分项，不应成为硬过滤条件。策略选择流程保持 score → sort → filter，conversation_stage 作为 scoring 的一个因子而非 filter 条件。

#### 3.2.3 策略选择流程确认

按之前评审确认的流程：

```
策略评分（scoring）
    ↓
策略排序（sort）
    ↓
上下文过滤（filter：apply_when / not_apply_when / applicable_context）
    ↓
最终选择（取过滤后得分最高的）
    ↓
fallback：如果过滤后为空，取未过滤的最高分卡
```

**关键：filter 后为空时的 fallback 逻辑必须有。** 否则会出现"无策略可选"的情况。

### 3.3 验收标准

```
重跑 118 条测试：
  单张策略卡占比：≤ 40%（从 60% 下降）
  每张卡至少触发：≥ 3 次
  conflict 场景下"扩大冲突"触发率：≥ 30%
```

---

## 4. P3：2h-8h 边界空缺修复

### 4.1 问题复述

当前边界规则在 2h-8h 区间 fallthrough 为 `continue`，可能导致巨型对话。

### 4.2 方案：补一条规则

```python
# conversation.py 边界检测优先级裁决中增加

# 规则 2.5（新增）：
# 时间间隔 > 2h（不论话题是否切换）
# → 关闭旧 Conversation，创建新的
if gap > 2 * 60 * 60:  # > 2h
    return "new"
```

更新后的优先级裁决：

```
1. 结束信号 → 等待 1 轮确认 → 关闭
2. 跨天 → 直接关闭
3. 时间间隔 > 2h → 直接关闭（新增）
4. 时间间隔 30min ~ 2h 且话题切换 → 关闭旧，创建新的
5. 时间间隔 30min ~ 2h 且话题不变 → 保持 active
6. 时间间隔 < 30min 且话题切换 → 保持 active，连续 3 条新话题才切换
7. 其他 → 保持 active
```

### 4.3 验收标准

```
重跑 118 条测试：
  最长 Conversation 持续时间：≤ 8h（从 250h 下降）
  Conversation 总数：增加（从过少变为合理数量）
  无巨型对话（> 24h 的 active Conversation）
```

---

## 5. 执行计划

### 5.1 执行顺序（严格按依赖关系）

```
Step 1: 修话题检测（P0）
    ↓ 重跑测试验证话题分布
Step 2: 修 outcome + key_points（P1）
    ↓ 重跑测试验证 unresolved_topics
Step 3: 修策略卡条件（P2）
    ↓ 重跑测试验证策略分布
Step 4: 补 2h 边界规则（P3）
    ↓ 重跑测试验证对话边界
```

### 5.2 每步验证流程

每步修复完成后，执行以下验证：

```bash
# 1. 重跑压力测试
python test_output/test_pipeline.py

# 2. 检查关键指标
# - 话题分布（P0 验收标准）
# - unresolved_topics 条数和内容（P1 验收标准）
# - 策略选择分布（P2 验收标准）
# - 对话边界分布（P3 验收标准）

# 3. 对比修复前后
# - 检查是否有回归（修复一个问题导致另一个问题恶化）
```

### 5.3 预估工时

| 步骤 | 内容 | 预估工时 |
|------|------|---------|
| P0 | message_understanding prompt + conversation.py + run.py + 补充关键词表 | 1.5h |
| P1 | summarizer prompt + memory_updater 规则修正 | 1h |
| P2 | 逐张审查策略卡条件 + 引入 conversation_stage | 2-3h |
| P3 | 补 1 条边界规则 | 10min |
| 测试 | 4 轮重跑测试 + 对比分析 | 2h |
| **合计** | | **约 7-8h** |

---

## 6. 回归风险

| 修复项 | 可能引入的回归 | 缓解措施 |
|--------|-------------|---------|
| P0 LLM 话题检测 | LLM 返回异常 topic 值 | 保留关键词兜底 + VALID_TOPICS 校验 |
| P0 增加 topic 字段 | message_understanding 输出解析失败 | topic 字段缺失时 fallback 到关键词 |
| P1 修改 summarizer prompt | 摘要质量变化 | 对比修复前后摘要内容 |
| P1 修改 memory_updater 规则 | 漏掉真正的 unresolved 问题 | 对比修复前后 unresolved_topics 内容 |
| P2 放宽策略卡条件 | 某些卡在不该触发的场景触发 | 检查每张卡的实际触发场景 |
| P3 2h 边界 | 过度切割对话 | 检查 Conversation 总数是否合理 |

---

## 7. 不做的事项

- 不新增策略卡（现有 6 张调好再考虑加）
- 不引入随机扰动（破坏可测试性）
- 不去掉策略卡机制（与架构哲学冲突）
- 不做话题 embedding 相似度（P3 特性）
- 不做距离维度（独立迭代，不影响本次修复）

---

## 8. 总结

```
修复顺序：P0 → P1 → P2 → P3（严格按依赖关系）
每步验证：修复后重跑 118 条测试，对比关键指标
核心改动：
  P0: message_understanding 输出 topic 字段 + conversation.py 优先用 LLM 结果
  P1: summarizer 三档 outcome + key_points 带 type + memory_updater 只写入 unresolved 类型
  P2: 逐张审查策略卡条件 + 引入 conversation_stage 维度 + filter 后 fallback
  P3: 补 1 条 > 2h 直接关闭规则
总工时：约 7-8h
```

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
