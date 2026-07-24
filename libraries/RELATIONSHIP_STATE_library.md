# RELATIONSHIP_STATE_LIBRARY.md

# Relationship Copilot 关系状态库

Version: 1.0

---

# 定位

```text
Relationship State（持久、手动维护）
        │
        ├──→ Message Understanding（消歧输入）
        │
        ├──→ Strategy Selector（过滤可用策略）
        │
        └──→ 本轮结束后 ← 手动更新回写
```

Relationship State 是长期累积的上下文，跨轮次持久化。目前由人工手动维护，系统自动更新机制后续再做。

---

# Schema

```yaml
relationship_state:

  stage:              # enum   关系阶段
  temperature:        # enum   关系热度
  attachment_style:   # enum   对方依恋风格
  trust_level:        # 0~100  信任程度
  intimacy_level:     # 0~100  亲密程度
  recent_events:      # list   近期关键事件
  conflict_status:    # enum   冲突状态
```

---

# 字段定义

---

## stage

```yaml
type: enum
description: 当前关系所处阶段。决定哪些策略允许使用、哪些行为被禁止
```

| 值 | 中文 | 说明 | 对策略选择的影响 |
|---|---|---|---|
| `stranger` | 陌生人 | 尚未建立联系 | 几乎全部策略不可用，仅可释放最低级信号 |
| `acquaintance` | 刚认识 | 搭讪后、刚加微信，有过初步互动 | 不可调情、不可高亲密度表达 |
| `friend` | 普通朋友 | 有基本联系，但无男女之意 | 可关注不可越级关心，邀约需满足前置条件 |
| `ambiguous` | 暧昧 | 互有好感，在往前推进 | 扩大冲突可用、调情可用 |
| `dating` | 恋爱 | 已确认情侣关系 | 大部分策略可用，关心和关注可自由切换 |
| `stable` | 长期稳定 | 深入交往、彼此了解 | 策略限制最少，重点是维持和深化 |
| `conflict` | 冲突期 | 正在矛盾或争吵中 | 调情策略禁用，优先降级冲突 |
| `breakup_recovery` | 分手恢复期 | 刚分手或濒临分手 | 极端保守，避免任何压力行为 |

---

## temperature

```yaml
type: enum
description: 当前关系热度。决定回复应保守还是主动
```

| 值 | 中文 | 说明 |
|---|---|---|
| `hot` | 火热 | 热恋期，高频互动，情绪投入高 |
| `warm` | 温暖 | 关系良好，互动自然 |
| `neutral` | 中性 | 不冷不热，维持中 |
| `cold` | 冷淡 | 开始疏远，回应减少 |
| `freezing` | 冰冻 | 接近断联，基本不回 |

---

## attachment_style

```yaml
type: enum
description: 对方的依恋风格。同一句话在不同依恋风格下含义不同
```

| 值 | 中文 | 特点 |
|---|---|---|
| `secure` | 安全型 | 情绪稳定，能健康处理亲密关系 |
| `anxious` | 焦虑型 | 容易缺乏安全感，经常确认关系 |
| `avoidant` | 回避型 | 重视独立空间，不喜欢被追问 |
| `fearful` | 恐惧型 | 既渴望亲密又害怕受伤 |

> **消歧示例**：「你是不是不爱我了」
> - 焦虑型 → need = SECURITY，需要安抚
> - 回避型 → need = RESPECT，需要空间，可能是在找借口拉开距离

---

## trust_level

```yaml
type: integer
range: 0 ~ 100
description: 她愿意向你暴露多少真实想法
```

| 范围 | 含义 |
|---|---|
| 0 ~ 30 | 低信任——礼貌聊天，不说真实想法 |
| 30 ~ 60 | 一般信任——开始分享，但有所保留 |
| 60 ~ 80 | 较高信任——真实表达，偶尔倾诉 |
| 80 ~ 100 | 高度信任——什么都愿意说 |

---

## intimacy_level

```yaml
type: integer
range: 0 ~ 100
description: 双方关系有多近。决定允许使用哪些表达方式
```

| 范围 | 含义 | 允许 | 禁止 |
|---|---|---|---|
| 0 ~ 20 | 几乎陌生 | 礼貌表达 | 亲密昵称、调情、性张力 |
| 20 ~ 40 | 朋友 | 关注、轻度赞美 | 暧昧表达、身体接触话题 |
| 40 ~ 60 | 暧昧 | 调情、扩大冲突、暗示 | 直白性表达 |
| 60 ~ 80 | 情侣 | 亲密称呼、深情表达 | — |
| 80 ~ 100 | 深度亲密 | 自由表达 | — |

---

## recent_events

```yaml
type: list[string]
description: 近期重要事件的简要记录。用于消息消歧
```

**示例**：
```yaml
recent_events:
  - 昨天吵架
  - 周末约会
  - 今天她考试
  - 她工作压力大
```

> **消歧示例**：她回「哦」
> - 无最近事件 → neutral，正常回应
> - recent_events 有「昨天吵架」→ 可能是被动攻击信号

---

## conflict_status

```yaml
type: enum
description: 当前是否处于矛盾阶段。决定 Goal Planner 优先级
```

| 值 | 中文 | 说明 |
|---|---|---|
| `none` | 无冲突 | 关系正常 |
| `mild` | 轻微矛盾 | 有小摩擦，但基调仍好 |
| `active` | 正在争吵 | 正在冲突中，需要降温 |
| `severe` | 严重冲突 | 濒临分手，需要修复 |

> **消歧示例**：「随你吧」
> - `none` → 可能就是让你决定
> - `active` → 是冷战信号，Goal 应该是 deescalate

---

# 策略卡 relationship_stage 映射

| 原中文值 | 统一 ID |
|---|---|
| 初识 | `acquaintance` |
| 暧昧 | `ambiguous` |
| 热恋 | `dating` |
| 稳定 | `stable` |
| 普通朋友 | `friend` |
| 冷战 | `conflict` |

---

# 完整枚举速查

```yaml
stage:
  - stranger           # 陌生人
  - acquaintance       # 刚认识
  - friend             # 普通朋友
  - ambiguous          # 暧昧
  - dating             # 恋爱
  - stable             # 长期稳定
  - conflict           # 冲突期
  - breakup_recovery   # 分手恢复期

temperature:
  - hot        # 火热
  - warm       # 温暖
  - neutral    # 中性
  - cold       # 冷淡
  - freezing   # 冰冻

attachment_style:
  - secure     # 安全型
  - anxious    # 焦虑型
  - avoidant   # 回避型
  - fearful    # 恐惧型

trust_level:     0 ~ 100
intimacy_level:  0 ~ 100

conflict_status:
  - none       # 无冲突
  - mild       # 轻微矛盾
  - active     # 正在争吵
  - severe     # 严重冲突

recent_events:   [string]
```
