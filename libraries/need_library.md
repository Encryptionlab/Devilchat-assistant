# NEED_LIBRARY.md

# Relationship Copilot 统一需求库

Version: 1.0

---

# 说明

本文件定义了系统中所有「需求」（Need）的统一标识符。

Need 回答的问题是：

```text
她此刻真正需要的是什么？
```

Need 由 Message Understanding 层输出，被策略卡的 `target_need` 字段引用，用于 Strategy Selector 做匹配。

Need 与 Goal 的区别：

| 层 | 回答的问题 | 视角 |
|---|---|---|
| Need | 她需要什么 | 对方视角 |
| Goal | 我要达成什么 | 我方视角 |

---

# 统一 Need 枚举

系统内部统一使用英文 ID。中文名称仅用于文档和 UI 展示。

---

## ATTENTION

```yaml
id: ATTENTION
zh: 被关注
description: 希望被注意、被重视，不想被忽略
```

## UNDERSTANDING

```yaml
id: UNDERSTANDING
zh: 被理解
description: 希望被共情、被"懂"，而非被教育或被分析
```

## VALIDATION

```yaml
id: VALIDATION
zh: 认同感
description: 希望被认可、被肯定，自己的感受或选择被接受
```

## SECURITY

```yaml
id: SECURITY
zh: 安全感
description: 希望获得确定性和安心，对关系不焦虑
```

## RESPECT

```yaml
id: RESPECT
zh: 被尊重
description: 希望边界被尊重，不被越界、不被施压、不被利用
```

## APPRECIATION

```yaml
id: APPRECIATION
zh: 被欣赏
description: 希望被赞美、被看到优点，获得正面评价
```

## PARTICIPATION

```yaml
id: PARTICIPATION
zh: 参与感
description: 希望被带入话题、被邀请互动，不被动旁观
```

## ENTERTAINMENT

```yaml
id: ENTERTAINMENT
zh: 娱乐
description: 希望有趣、好玩、情绪刺激，不想无聊
```

## COMPANIONSHIP

```yaml
id: COMPANIONSHIP
zh: 陪伴
description: 希望有人在场、不孤独，需要情绪支持
```

## INTIMACY

```yaml
id: INTIMACY
zh: 亲密感
description: 希望关系更近、更深入、更私密
```

## EMOTIONAL_RELEASE

```yaml
id: EMOTIONAL_RELEASE
zh: 情绪释放
description: 需要宣泄、吐槽、发泄，把话说出来本身即是目的
```

## SUPPORT

```yaml
id: SUPPORT
zh: 支持
description: 需要实际帮助、建议或资源
```

---

# 与各来源的对照关系

## 策略卡 target_need 映射

| 原中文值 | 统一 ID | 涉及的策略卡 |
|---|---|---|
| 被关注 | ATTENTION | signal_escalation, escalating_conflict |
| 安全感 | SECURITY | signal_escalation, validate_emotion_express_need, eighty_twenty_rule, care_vs_attention |
| 认同感 | VALIDATION | signal_escalation |
| 被理解 | UNDERSTANDING | validate_emotion_express_need, care_vs_attention |
| 被尊重 | RESPECT | validate_emotion_express_need, humorous_deflection, eighty_twenty_rule, care_vs_attention |
| 娱乐 | ENTERTAINMENT | humorous_deflection |
| 情绪价值 | ENTERTAINMENT | escalating_conflict |
| 分享欲 | PARTICIPATION | escalating_conflict |

## design_archive/MESSAGE_UNDERSTANDING.md 映射

| 原枚举值 | 统一 ID |
|---|---|
| attention | ATTENTION |
| understanding | UNDERSTANDING |
| validation | VALIDATION |
| security | SECURITY |
| companionship | COMPANIONSHIP |
| participation | PARTICIPATION |
| entertainment | ENTERTAINMENT |
| advice | SUPPORT |
| appreciation | APPRECIATION |
| intimacy | INTIMACY |

## design/蓝图.md 核心需求库映射

| 原中文值 | 统一 ID |
|---|---|
| 被关注 | ATTENTION |
| 被理解 | UNDERSTANDING |
| 安全感 | SECURITY |
| 认同感 | VALIDATION |
| 情绪释放 | EMOTIONAL_RELEASE |
| 陪伴 | COMPANIONSHIP |
| 娱乐 | ENTERTAINMENT |
| 建议 | SUPPORT |
| 帮助 | SUPPORT |
| 归属感 | INTIMACY |

---

# 完整枚举速查

```yaml
NEED_ENUM:
  - ATTENTION          # 被关注
  - UNDERSTANDING      # 被理解
  - VALIDATION         # 认同感
  - SECURITY           # 安全感
  - RESPECT            # 被尊重
  - APPRECIATION       # 被欣赏
  - PARTICIPATION      # 参与感
  - ENTERTAINMENT      # 娱乐
  - COMPANIONSHIP      # 陪伴
  - INTIMACY           # 亲密感
  - EMOTIONAL_RELEASE  # 情绪释放
  - SUPPORT            # 支持
```
