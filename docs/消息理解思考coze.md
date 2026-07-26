---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4021381275058560_0/project_7665906678516334848-files/docs/MESSAGE_UNDERSTANDING_BATCH_V2.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4021381275058560#1785057549683
    ReservedCode2: ""
---
# 消息理解批量化改造设计 v2

> 基于评审反馈修订，采用分两步走策略
>
> Version: 2.0 | 2026-07-26
>
> 核心变更：
> - 第一步只改输入格式（序列化），数据源不变，不引入循环依赖
> - 数据源切换到 ConversationManager.messages_log 后置到第二步
> - 明确语义漂移规则：以最新消息为主导
> - 消息条数从 15 条收为 8 条
> - 新增字段标注为展示用，不参与决策

---

## 0. 修订原因

v1 设计的核心思路（序列化输入替代硬拼接）是正确的，但存在一个架构隐患：

```
MessageUnderstanding 需要 ConversationManager.messages_log 作为数据源
ConversationManager 需要 MessageUnderstanding 的 topic 输出做边界检测
→ 循环依赖
```

ConversationManager 在当前 pipeline 中跑在 GoalPlanner 之后（需要 current_goal）。如果 MU 改为从 CM 取数据，就形成了鸡生蛋蛋生鸡。

v2 的解法：**分两步走。** 第一步只改输入格式，数据源保持不变，解决 80% 的问题。等 ConversationManager 稳定后再做数据源切换。

---

## 1. 问题陈述

### 1.1 Burst 消息被硬拼接

微信真实场景中对方经常连发多条消息，当前处理方式：

```python
her_msgs = [m for m in messages if m.get("role") == "她"]  # 滤掉我的消息
combined = " ".join(m["content"] for m in her_msgs[-3:])   # 硬拼接
```

三个问题：
1. 三条消息揉成一段文本，丢了消息边界和情绪递进
2. 滤掉了我的回复，LLM 看不到"她是在回复我的关心"这个关键上下文
3. 只取 3 条，上下文不足

### 1.2 数据源跨话题混合

按"最后 N 条"硬截，可能跨越话题边界，把两个不同话题的消息混在一起送给 LLM。

**注意：** 这个问题在第一步中不解决（数据源仍是 buffer），但由于第一步取 8 条而非 3 条、且包含双方消息，分析质量已大幅提升。跨话题混合问题在第二步切换到 messages_log 后彻底解决。

---

## 2. 方案总览：分两步走

```
第一步（本次实施）：
  输入格式：硬拼接 → 序列化输入（角色标签 + 逐条列出 + 包含双方消息）
  数据源：MessageBuffer（不变）
  消息条数：3 条 → 8 条
  新增字段：3 个（展示用）
  下游改动：无

第二步（ConversationManager 稳定后）：
  数据源：MessageBuffer → ConversationManager.messages_log
  循环依赖：拆分 CM 职责解决
  消息条数：8 条 → 视效果调整（上限 15）
```

---

## 3. 第一步：输入格式改造

### 3.1 输入格式变更

**当前（只取她的消息，硬拼接）：**
```
## 对话历史
她: 今天好累啊复习了一整天头都晕了
```

**改为（完整时间线，角色标签，逐条列出）：**
```
## 消息序列（时间顺序，共 5 条）

1. 她: 今天好累啊
2. 我: 怎么了宝宝
3. 她: 复习了一整天
4. 她: 头都晕了
5. 我: 这么拼啊

请分析她在以上序列中的消息（标记为"她"的条目），考虑整个交换的上下文，仅输出 JSON。
```

设计要点：
- **包含双方消息**：我的回复是她后续消息的"因"，LLM 需要看到才能判断她情绪的变化方向
- **明确角色标签**：每条消息带 `她:` / `我:` 前缀，LLM 能区分哪条待分析、哪条是上下文
- **逐条列出**：保留消息边界和递进关系，不再揉成一段
- **上限 8 条**：burst 场景通常 3-5 条，加上前序上下文 8 条足够，避免上下文过长分散 LLM 注意力

### 3.2 数据源（不变）

```python
# pipeline_service.py
# 数据源仍为 MessageBuffer，只改格式化方式

recent = message_buffer.get_recent(8)  # 取最近 8 条，包含双方

# 格式化为序列
sequence_lines = []
for i, msg in enumerate(recent):
    role = "她" if msg["role"] == "她" else "我"
    sequence_lines.append(f"{i+1}. {role}: {msg['content']}")

sequence_text = "\n".join(sequence_lines)
```

兜底：如果 buffer 中不足 8 条，取全部可用消息。

### 3.3 语义规则：以最新消息为主导

v1 设计中字段名不变但语义从"单条"漂移到"序列"，这会导致下游模块拿到的值含义变化。v2 明确规则：

**主导情绪取值规则：**

```
默认：取最后一条"她"的消息的情绪作为主导情绪
例外：burst_pattern 为 venting 时（倾诉递进，情绪逐步加强），
      取峰值情绪（通常是最后一条，但不一定）
```

这样 reply_generator 拿到的 `ms.emotion` 始终对齐最新消息，不会因为序列中间有激烈情绪而导致回复语气错配。

**字段语义对照表：**

| 字段 | 取值规则 | 说明 |
|------|---------|------|
| `emotion` | 最新一条"她"消息的情绪（venting 时取峰值） | 下游直接用，不需改 |
| `emotion_intensity` | 最新一条"她"消息的强度（venting 时取峰值） | 下游直接用，不需改 |
| `need_scores` | 覆盖整个序列的综合需求 | 下游直接用，不需改 |
| `surface_intent_scores` | 以最新消息为主的复合意图 | 下游直接用，不需改 |
| `topic` | 整个序列的话题（通常一致） | 下游直接用，不需改 |

### 3.4 新增输出字段（展示用）

MessageState 现有 14 个字段全部保留。新增 3 个字段：

```python
burst_pattern: str       # burst 结构模式
emotional_peak: str      # burst 内最强情绪
trajectory_note: str     # 情绪/需求递进概括
```

**⚠️ 重要：这 3 个字段当前不参与任何下游决策。** 仅用于分析展示和未来可能的策略微调参考。NeedRecognizer、GoalPlanner、StrategySelector、ReplyGenerator 均不读取这 3 个字段。

#### burst_pattern 枚举

| 值 | 含义 | 示例 |
|----|------|------|
| `single` | 单条消息，无 burst | "在干嘛" |
| `venting` | 倾诉递进，情绪逐步加强 | "好累" → "复习了一天" → "头都晕了" |
| `escalating` | 情绪升级，可能转向冲突 | "你怎么又不回" → "算了每次都这样" |
| `question_chain` | 连续提问，可能有焦虑 | "你在哪" → "跟谁" → "什么时候回来" |
| `mixed` | 混合型，话题/情绪跳跃 | "今天好累。你中午吃的啥" |

#### emotional_peak

burst 中情绪最强烈的那条消息对应的情绪标签。

#### trajectory_note

一句话概括整个 burst 的情绪/需求递进轨迹，例如："从疲惫倾诉到寻求安慰"、"从不满到失望"。

### 3.5 System Prompt 改动

**任务描述改为：**

```
你的任务：接收她的一段消息序列（可能 1~5 条连发，含你的回复作为上下文），
分析整体的情绪基调、情绪递进轨迹、核心需求，输出结构化的分析结果。

分析原则：
1. 主导情绪取最后一条"她"的消息的情绪。
   例外：如果多条消息构成"倾诉递进"（如：累 → 越来越累 → 扛不住了），
   取峰值情绪作为主导情绪。
2. need_scores 要覆盖整个递进过程的综合需求，不只是最后一条。
3. 如果多条消息是"话题跳跃"（如：累 → 问你今天干嘛了），
   按最后一条确定主导方向和话题。
4. 如果只有一条消息，正常分析即可。
5. burst_pattern 判断标准：看消息之间的因果关系，而非时间顺序。
   - venting：后一条加深前一条的情绪
   - escalating：情绪从负面到更负面，有冲突升级趋势
   - question_chain：连续提问，每条都在寻求信息
   - mixed：话题之间无明显递进关系，各说各的
6. 请重点分析标记为"她"的消息，"我"的消息仅作上下文参考。
```

JSON 输出模板追加 3 个新字段。

### 3.6 parse_response 兜底

```python
# 新增字段设默认值，LLM 未返回时不崩溃
result["burst_pattern"] = result.get("burst_pattern", "single")
result["emotional_peak"] = result.get("emotional_peak", "neutral")
result["trajectory_note"] = result.get("trajectory_note", "")

# burst_pattern 校验
if result["burst_pattern"] not in VALID_BURST_PATTERNS:
    result["burst_pattern"] = "single"
```

---

## 4. 第二步：数据源切换（后置）

### 4.1 触发条件

满足以下条件后执行：
- 压力测试 P0 修复（话题检测 LLM 化）完成并验证
- ConversationManager 边界检测稳定（重跑压力测试无巨型对话）
- 第一步改造已上线运行，序列化输入效果已验证

### 4.2 循环依赖解决方案

拆分 ConversationManager 的职责为两个阶段：

```python
class ConversationManager:
    
    def log_message(self, message: Message):
        """阶段 1：轻量记录，只 append 到 messages_log，不做边界检测"""
        if self.active_conversation:
            self.active_conversation.message_ids.append(message.id)
            self.active_conversation.last_message_time = message.timestamp
    
    def process_boundary(self, topic: str, current_goal: str) -> tuple[Conversation, bool]:
        """阶段 2：边界检测，使用 MU 的 topic 输出"""
        # 检查超时、结束信号、时间间隔、话题切换
        # 可能关闭旧 Conversation，创建新的
        ...
```

### 4.3 新的 pipeline 顺序

```
消息进来
  → ConversationManager.log_message(message)    ← 阶段 1：只记录
  → MessageUnderstanding（从 CM.active_conversation.messages_log 取最近 8 条）
  → NeedRecognition
  → GoalPlanner（输出 current_goal）
  → ConversationManager.process_boundary(topic, current_goal)    ← 阶段 2：边界检测
  → ContextBuilder
  → StrategySelector
  → ReplyGenerator
  → ExpressionEnhancer
```

这样 MU 取 messages_log 时，当前消息已经写入了。边界检测虽然在 MU 之后，但：
- burst 内的消息必然属于同一对话，边界未判定不影响分析
- 跨话题的混合问题只在间隔较大时出现，此时 buffer 和 messages_log 差异不大

### 4.4 消息条数调整

切换到 messages_log 后，可考虑将上限从 8 条提高到 12-15 条。messages_log 天然按话题切分，不会跨 Conversation 混入无关消息，上下文更干净。

具体条数根据第一步的效果数据决定。

---

## 5. 改动范围

### 5.1 第一步改动

| 文件 | 改动内容 | 改动量 |
|------|---------|--------|
| `src/message_understanding.py` | MessageState 加 3 字段；`_build_system_prompt()` 重写任务描述（序列分析 + 语义规则 + burst 定义）；`_REQUIRED_FIELDS` 新增字段；`parse_response()` 兜底校验 | ~50 行 |
| `backend/services/pipeline_service.py` | `observe_messages()` 从 `her_msgs[-3:]` 拼接改为取 `message_buffer.get_recent(8)` 序列化格式化 | ~10 行 |
| `backend/services/pipeline_service.py` | `analyze_pending()` 同上调整 | ~5 行 |

### 5.2 不需要改的

| 模块 | 原因 |
|------|------|
| `need_recognition.py` | 读 `ms.emotion` / `ms.need_scores`，字段名和语义不变 |
| `goal_planner.py` | 读 `ms.emotion` / `need_result` |
| `strategy_selector.py` | 读 `ms` 和 `need_result` |
| `reply_generator.py` | 读 `ms.emotion` / `ms.dominant_intent` |
| `expression_enhancer.py` | 读 `ms.emotion` |
| `conversation.py` | 不感知 MU 的输入格式变化 |
| `context_builder.py` | 不感知 MU 的输入格式变化 |
| `memory_updater.py` | 不感知 MU 的输入格式变化 |
| 前端 | 只展示 `emotion` / `topic` / `dominantNeed`，不感知 burst 字段 |

### 5.3 第二步改动（后置）

| 文件 | 改动内容 | 改动量 |
|------|---------|--------|
| `conversation.py` | 拆分 `log_message()` 和 `process_boundary()` | ~20 行 |
| `backend/services/pipeline_service.py` | 数据源从 `message_buffer.get_recent(8)` 改为 `conv_mgr.get_active_conversation().messages_log[-8:]` | ~5 行 |

---

## 6. 成本分析

| 方案 | LLM 调用/burst | 优势 | 劣势 |
|------|----------------|------|------|
| 逐条分析 | N 次 | 每条精细 | 成本 × N，分析割裂 |
| 拼接成一段（改造前） | 1 次 | 便宜 | 丢消息边界，递进丢失，滤掉我的消息 |
| 序列化输入（第一步） | 1 次 | 便宜 + 保留递进 + 含上下文 | 数据源仍可能跨话题（第二步解决） |
| 序列化 + messages_log（第二步） | 1 次 | 便宜 + 保留递进 + 话题隔离 | 需要 CM 拆分职责 |

8 条中文消息（含角色标签和序号）约 300-500 tokens，占一次 LLM 调用总 token 的 3-5%，可忽略。

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 语义漂移导致下游行为变化 | 中 | 中 | 明确规则：以最新消息为主导，venting 时取峰值 |
| LLM 忽略序列格式，仍按单条分析 | 低 | 中 | prompt 中强调"分析整个序列"，加示例 |
| buffer 仍跨话题混合（第一步未解决） | 中 | 低 | 第一步取 8 条比 3 条好；第二步彻底解决 |
| 新增字段 LLM 未返回 | 中 | 极低 | parse_response 设默认值 |
| 8 条上下文分散 LLM 注意力 | 低 | 低 | 监控分析质量，必要时降到 5 条 |
| 第二步循环依赖 | 高 | 高 | CM 拆分 log_message 和 process_boundary |

---

## 8. 与压力测试修复的关系

```
执行顺序：

1. 压力测试 P0 修复（话题检测 LLM 化）  ← 先做
2. 本改造第一步（序列化输入）          ← 可与 P0 并行
3. 压力测试 P1-P3 修复
4. 本改造第二步（数据源切换）            ← 等 CM 稳定后做
```

第一步和压力测试 P0 修复可以并行，因为：
- P0 修复改的是 MU 的输出（加 topic 字段）
- 第一步改的是 MU 的输入（序列化格式）
- 两者不冲突，改的是不同部分

但第二步必须在 P0 修复完成且 ConversationManager 稳定后才能做。

---

## 9. 验收标准

### 第一步验收

```
重跑 118 条压力测试，对比改造前后：

1. 情绪判断准确率：
   - burst 场景（连发 2+ 条）的情绪判断应更准确
   - 单条消息场景不应有回归

2. need_scores 质量：
   - burst 场景的 need 覆盖更完整（不只取最后一条的 need）
   - 单条消息场景不应有回归

3. 新增字段完整性：
   - burst_pattern 在 burst 场景下正确分类
   - 单条消息场景 burst_pattern = "single"

4. 性能：
   - LLM 调用次数不变（仍为 1 次/burst）
   - 响应时间无明显增加（< +10%）
```

### 第二步验收

```
1. 数据源切换后：
   - 不再出现跨话题混合
   - Conversation 边界检测结果一致

2. 循环依赖：
   - log_message 和 process_boundary 顺序正确
   - 新 Conversation 的第一条消息能正常分析（messages_log 只有 1 条时不报错）
```

---

## 10. 总结

```
改造核心：

  第一步（现在做）：
    输入格式：硬拼接 → 序列化（角色标签 + 逐条列出 + 含双方消息）
    数据源：不变（MessageBuffer）
    条数：3 → 8
    新增 3 字段（展示用，不参与决策）
    语义规则：以最新消息为主导，venting 时取峰值
    下游改动：无
    解决问题：burst 消息递进丢失、我的回复被滤掉

  第二步（CM 稳定后）：
    数据源：MessageBuffer → ConversationManager.messages_log
    CM 拆分：log_message（轻量记录）+ process_boundary（边界检测）
    解决问题：跨话题混合、循环依赖

  执行顺序：
    压力测试 P0 修复 ← 先做
    本改造第一步     ← 可与 P0 并行
    压力测试 P1-P3
    本改造第二步     ← 等 CM 稳定
```

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
