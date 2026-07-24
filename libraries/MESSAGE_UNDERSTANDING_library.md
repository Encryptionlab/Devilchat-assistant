# MESSAGE_UNDERSTANDING_LIBRARY.md

# Relationship Copilot 消息理解层字段库

Version: 1.0

---

# 定位

```text
原始消息
    ↓
Message Understanding（本层）
    ↓
Structured State → Goal Planner → Strategy Selector → ...
```

消息理解层是 pipeline 的第一道加工环节。输入原始聊天文本，输出结构化 State。不做决策，只做解读。

后续所有模块只读取结构化 State，不得直接读取原始消息。

---

# 输出 Schema

```yaml
message_analysis:

  # === 原始 ===
  message:            # string   原始文本

  # === 意图与情绪 ===
  surface_intent:     # enum     表面意图
  emotion:            # enum     情绪类型
  emotion_intensity:  # 0.0~1.0  情绪强度

  # === 需求与信号 ===
  need:               # enum     她此刻需要什么（引用 need_library.md）
  relationship_signal:# enum     关系层面隐含信号

  # === 表达特征 ===
  expression_mode:    # enum     念头还是想法
  state_type:         # enum     纯状态还是带了感受
  suggest_direction:  # enum     暗示性语言的方向
  has_metaphor:       # bool     是否有比喻包装（形式层≠实质层）
  conflict_signal:    # enum     冲突是否由她主动发起

  # === 关系上下文（外部输入） ===
  relationship_context:# ref      本次解读依赖的关系状态快照

  # === 对话位置 ===
  conversation_stage: # enum     当前消息在对话中的阶段
  expected_response:  # enum     她期待什么类型的回应
```

---

# 字段定义

---

## message

```yaml
type: string
description: 原始消息文本，原样保留
```

---

## surface_intent

```yaml
type: enum
description: 消息表面在做什么动作
```

| 值 | 中文 | 说明 |
|---|---|---|
| `emotional_expression` | 情绪表达 | 表达感受或情绪状态 |
| `complaint` | 抱怨 | 吐槽、诉苦 |
| `sharing` | 分享 | 分享信息、经历、状态 |
| `question` | 提问 | 直接发问 |
| `relationship_test` | 关系测试 | 试探关系状态或你的态度 |
| `praise` | 赞美 | 对你表达正面评价 |
| `invitation` | 邀约 | 主动邀请你做某事 |
| `rejection` | 拒绝 | 拒绝你的提议或邀约 |
| `teasing` | 调侃 | 开玩笑、逗你 |
| `conflict` | 冲突 | 发起争论或表达不满 |

---

## emotion

```yaml
type: enum
description: 她当前的情绪状态
```

| 值 | 中文 |
|---|---|
| `happy` | 开心 |
| `excited` | 兴奋 |
| `sad` | 难过 |
| `disappointed` | 失望 |
| `angry` | 愤怒 |
| `anxious` | 焦虑 |
| `lonely` | 孤独 |
| `tired` | 疲惫 |
| `bored` | 无聊 |
| `embarrassed` | 尴尬 |
| `jealous` | 吃醋 |
| `hopeful` | 期待 |
| `grateful` | 感激 |
| `neutral` | 中性 |

---

## emotion_intensity

```yaml
type: float
range: 0.0 ~ 1.0
description: 情绪强度。0.0 为无情绪波动，1.0 为极端情绪
```

---

## need

```yaml
type: enum
description: 她此刻真正需要什么。引用 need_library.md，使用统一 Need ID
```

| 值 | 中文 |
|---|---|
| `ATTENTION` | 被关注 |
| `UNDERSTANDING` | 被理解 |
| `VALIDATION` | 认同感 |
| `SECURITY` | 安全感 |
| `RESPECT` | 被尊重 |
| `APPRECIATION` | 被欣赏 |
| `PARTICIPATION` | 参与感 |
| `ENTERTAINMENT` | 娱乐 |
| `COMPANIONSHIP` | 陪伴 |
| `INTIMACY` | 亲密感 |
| `EMOTIONAL_RELEASE` | 情绪释放 |
| `SUPPORT` | 支持 |

---

## relationship_signal

```yaml
type: enum
description: 她在向关系释放什么隐含信号。这是恋爱 Agent 区别于普通聊天 Agent 的核心字段
```

| 值 | 中文 | 说明 |
|---|---|---|
| `seeking_attention` | 寻求关注 | 想让你注意到她 |
| `seeking_reassurance` | 寻求确认 | 需要你确认关系或心意 |
| `seeking_connection` | 寻求连接 | 想拉近距离、建立共鸣 |
| `engagement` | 积极参与 | 主动投入对话、延伸话题 |
| `withdrawing` | 退缩 | 在拉开距离、减少投入 |
| `testing` | 测试 | 在试探你的反应或底线 |
| `flirting` | 调情 | 在释放暧昧信号 |
| `conflicting` | 冲突 | 在制造对抗或表达不满 |

---

## expression_mode

```yaml
type: enum
description: 她是在表达一时冲动的念头（可能自相矛盾），还是经过判断的稳定想法
source: 《魔鬼聊天术》Part 2 · 念头与想法
```

| 值 | 中文 | 说明 | 对下游的影响 |
|---|---|---|---|
| `impulse` | 念头 | 一时冲动、可能自相矛盾、不当真。女人在不开心时表达的多是念头 | 不要按字面执行，寻找背后的真实需求 |
| `intention` | 想法 | 经过判断的稳定意图、当真。重复表达或严肃表达时多为想法 | 按字面认真对待 |

> **示例**：她说"想一个人静静"→ `impulse`，实际可能需要陪伴。她说"我们以后不要联系了"（严肃、重复）→ `intention`。

---

## state_type

```yaml
type: enum
description: 她分享的内容是纯客观状态，还是附带了主观感受
source: 《魔鬼聊天术》Part 3 第6-7节 · 关心与关注
```

| 值 | 中文 | 说明 | 示例 |
|---|---|---|---|
| `pure_state` | 纯状态 | 只有客观事实，没有情绪词 | "周末要搬家" |
| `state_with_feeling` | 状态+感受 | 客观事实附带了主观情绪 | "周末要搬家，烦死了" |

> **对下游的影响**：`pure_state` + 普通朋友 → 只需关注；`state_with_feeling` + 任何关系 → 可以关心。这是 `care_vs_attention` 策略的前置触发条件。

---

## suggest_direction

```yaml
type: enum
description: 如果她使用了暗示性语言，肯定回答指向的方向暴露了她的真实意愿
source: 《魔鬼聊天术》Part 2 · 暗示性语言
```

| 值 | 中文 | 说明 | 示例 |
|---|---|---|---|
| `positive` | 积极暗示 | 肯定回答 = 她想要的结果 | "对你不晚吧？"→ 希望你说"不晚" |
| `negative` | 消极暗示 | 肯定回答 = 她不想要的结果 | "会不会太晚？"→ 希望你说"是有点晚" |
| `null` | 非暗示 | 直接表达，无暗示性 | — |

> **判断方法**：将问句转换为肯定陈述，看这个陈述是否符合她可能的愿望。符合 → `positive`，不符合 → `negative`。

---

## has_metaphor

```yaml
type: boolean
description: 她的请求是否使用了比喻包装，即存在"形式层"和"实质层"的分离
source: 《魔鬼聊天术》Part 2 第4节 · 幽默化解越级请求
```

| 值 | 说明 | 示例 |
|---|---|---|
| `true` | 存在双层结构——表面说的是A，实际要的是B | "你给报销吗？"（形式="报销"，实质="出钱"） |
| `false` | 直接表达，形式和实质一致 | — |

> **对下游的影响**：`has_metaphor = true` 时，`humorous_deflection` 策略可用——先否定形式层，再在比喻内部处理实质层。如果 `has_metaphor = false` 且是越级请求，使用 escalated_variant。

---

## conflict_signal

```yaml
type: enum
description: 她的消息中是否包含主动发起的调侃/质疑/否定——这是扩大冲突策略的触发条件
source: 《魔鬼聊天术》Part 1 第4节 · 扩大冲突
```

| 值 | 中文 | 说明 | 对下游的影响 |
|---|---|---|---|
| `her_initiated` | 她发起的 | 她主动调侃你、质疑你或轻度否定你——这是好感指标 | `escalating_conflict` 策略可用 |
| `none` | 无 | 无冲突信号 | 男方不可主动发起冲突 |

> **判断要点**：冲突必须由她先发起。她的调侃/质疑/否定 = 好感信号 = 可调情的许可。男方主动发起冲突（如"自大风趣法"）= 无礼。

---

## relationship_context

```yaml
type: reference
description: 本次消息解读所依赖的关系状态快照。由外部 Relationship State 输入，Message Understanding 本身不计算此值
source: RELATIONSHIP_STATE_library.md（手动维护）
```

| 子字段 | 类型 | 说明 |
|---|---|---|
| `stage` | enum | 当前关系阶段，用于消歧和策略过滤 |
| `temperature` | enum | 当前关系热度，影响回复基调 |
| `attachment_style` | enum | 对方依恋风格，影响同一条消息的解读方向 |
| `trust_level` | integer | 信任度 0~100 |
| `intimacy_level` | integer | 亲密度 0~100 |
| `conflict_status` | enum | 是否正处于冲突中 |
| `recent_events` | list | 近期关键事件摘要 |

> **注意**：此字段是引用快照，不是 Message Understanding 的输出。由调用方在发起消息理解时注入当前关系状态。

---

## conversation_stage

```yaml
type: enum
description: 当前消息在整段对话中的位置
```

| 值 | 中文 | 说明 |
|---|---|---|
| `opening` | 开场 | 对话刚开始，抛出话题 |
| `elaborating` | 展开 | 在深入话题，提供更多细节 |
| `escalating` | 升温 | 情绪在升级，关系在拉近 |
| `resolving` | 收束 | 话题在收尾，情绪在回落 |
| `closing` | 结束 | 对话即将结束 |

---

## expected_response

```yaml
type: enum
description: 她期待你用什么类型的回应
```

| 值 | 中文 | 说明 |
|---|---|---|
| `empathy` | 共情 | 理解她的感受 |
| `reassurance` | 安抚 | 给她确定性和安全感 |
| `celebration` | 庆祝 | 一起开心，放大积极情绪 |
| `curiosity` | 好奇 | 追问细节，表示兴趣 |
| `support` | 支持 | 提供实际帮助或建议 |
| `advice` | 建议 | 给她出主意 |
| `humor` | 幽默 | 逗她开心，制造趣味 |
| `affection` | 亲密 | 表达喜欢或亲密感 |

---

# 完整示例

输入：

```text
今天好烦
```

输出：

```yaml
message_analysis:

  message:              "今天好烦"

  surface_intent:        emotional_expression
  emotion:               disappointed
  emotion_intensity:     0.7

  need:                  UNDERSTANDING
  relationship_signal:   seeking_connection

  expression_mode:       impulse
  state_type:            state_with_feeling
  suggest_direction:     null
  has_metaphor:          false
  conflict_signal:       none

  relationship_context:
    stage:               acquaintance
    temperature:         neutral
    attachment_style:    null
    trust_level:         25
    intimacy_level:      15
    conflict_status:     none
    recent_events:       []

  conversation_stage:    opening
  expected_response:     empathy
```

---

# 字段速查

```yaml
# 所有枚举值一览

surface_intent:
  - emotional_expression  # 情绪表达
  - complaint             # 抱怨
  - sharing               # 分享
  - question              # 提问
  - relationship_test     # 关系测试
  - praise                # 赞美
  - invitation            # 邀约
  - rejection             # 拒绝
  - teasing               # 调侃
  - conflict              # 冲突

emotion:
  - happy         # 开心
  - excited       # 兴奋
  - sad           # 难过
  - disappointed  # 失望
  - angry         # 愤怒
  - anxious       # 焦虑
  - lonely        # 孤独
  - tired         # 疲惫
  - bored         # 无聊
  - embarrassed   # 尴尬
  - jealous       # 吃醋
  - hopeful       # 期待
  - grateful      # 感激
  - neutral       # 中性

need:              # 详见 need_library.md
  - ATTENTION
  - UNDERSTANDING
  - VALIDATION
  - SECURITY
  - RESPECT
  - APPRECIATION
  - PARTICIPATION
  - ENTERTAINMENT
  - COMPANIONSHIP
  - INTIMACY
  - EMOTIONAL_RELEASE
  - SUPPORT

relationship_signal:
  - seeking_attention     # 寻求关注
  - seeking_reassurance   # 寻求确认
  - seeking_connection    # 寻求连接
  - engagement            # 积极参与
  - withdrawing           # 退缩
  - testing               # 测试
  - flirting              # 调情
  - conflicting           # 冲突

expression_mode:
  - impulse     # 念头
  - intention   # 想法

state_type:
  - pure_state           # 纯状态
  - state_with_feeling   # 状态+感受

suggest_direction:
  - positive   # 积极暗示
  - negative   # 消极暗示
  - null       # 非暗示

has_metaphor:
  - true
  - false

conflict_signal:
  - her_initiated   # 她发起的
  - none            # 无

conversation_stage:
  - opening       # 开场
  - elaborating   # 展开
  - escalating    # 升温
  - resolving     # 收束
  - closing       # 结束

expected_response:
  - empathy       # 共情
  - reassurance   # 安抚
  - celebration   # 庆祝
  - curiosity     # 好奇
  - support       # 支持
  - advice        # 建议
  - humor         # 幽默
  - affection     # 亲密
```
