# RELATIONSHIP_STATE_V2.md

# Relationship State 重构方案

Version: 2.0

---

# 背景

在实际测试中发现：

```yaml
relationship_state:

  relationship_stage
```

只能描述：

```text
关系发展到了什么阶段
```

例如：

```yaml
stranger
acquaintance
dating
relationship
```

---

但现实中的聊天差异远远不止于此。

例如：

```yaml
dating
```

可能是：

```text
同城恋爱
```

也可能是：

```text
异地恋
```

---

而聊天策略完全不同。

例如：

```text
我想你了
```

在同城环境下可能意味着：

```text
出来见面
```

而在异地环境下可能意味着：

```text
需要情感陪伴
```

---

因此：

```text
relationship_stage
无法完整描述关系状态
```

需要升级为多维关系画像。

---

# 设计目标

Relationship State 不再只回答：

```text
我们是什么关系？
```

而是同时回答：

```text
我们是什么关系？

我们怎么接触？

我们平时怎么互动？

关系是否健康？
```

---

# 新架构

```yaml
relationship_state:

  stage:

  connection_context:

  interaction_pattern:

  relationship_health:
```

---

# 第一层：关系阶段（Stage）

回答：

```text
我们是什么关系？
```

---

结构：

```yaml
stage:

  stranger

  acquaintance

  ambiguous

  dating

  relationship

  long_term
```

---

说明：

| 状态           | 含义    |
| ------------ | ----- |
| stranger     | 陌生人   |
| acquaintance | 刚认识   |
| ambiguous    | 暧昧期   |
| dating       | 已确定关系 |
| relationship | 稳定恋爱  |
| long_term    | 长期关系  |

---

示例：

```yaml
stage:
  dating
```

表示：

```text
双方已确定恋爱关系
```

---

# 第二层：连接环境（Connection Context）

回答：

```text
双方是如何接触的？
```

---

## distance_mode

地理距离。

```yaml
distance_mode:

  same_city

  short_distance

  long_distance

  online_only
```

---

说明：

| 状态             | 含义     |
| -------------- | ------ |
| same_city      | 同城     |
| short_distance | 可短期往返  |
| long_distance  | 异地     |
| online_only    | 从未线下见面 |

---

## meeting_availability

见面难度。

```yaml
meeting_availability:

  easy

  limited

  rare
```

---

说明：

| 状态      | 含义      |
| ------- | ------- |
| easy    | 随时可约    |
| limited | 需要提前安排  |
| rare    | 长时间无法见面 |

---

为什么需要这个字段？

因为：

```text
距离 ≠ 是否容易见面
```

例如：

```yaml
distance_mode:
  same_city

meeting_availability:
  rare
```

可能是：

```text
同城但封闭培训
```

---

又例如：

```yaml
distance_mode:
  long_distance

meeting_availability:
  easy
```

可能是：

```text
高铁一小时
每周都能见面
```

---

# 第三层：互动模式（Interaction Pattern）

回答：

```text
双方平时是怎么联系的？
```

---

## contact_frequency

联系频率。

```yaml
contact_frequency:

  daily

  regular

  sparse
```

---

说明：

| 状态      | 含义   |
| ------- | ---- |
| daily   | 每天联系 |
| regular | 定期联系 |
| sparse  | 很少联系 |

---

为什么重要？

因为：

```text
很多关系问题来自联系频率

而不是地理距离
```

例如：

```text
你最近怎么都不理我
```

本质是：

```text
联系频率下降
```

而非：

```text
异地
```

---

## initiative_balance

主动程度。

```yaml
initiative_balance:

  mostly_me

  balanced

  mostly_her
```

---

说明：

| 状态         | 含义    |
| ---------- | ----- |
| mostly_me  | 我更主动  |
| balanced   | 双方差不多 |
| mostly_her | 对方更主动 |

---

示例：

```yaml
initiative_balance:
  mostly_me
```

表示：

```text
大多数聊天由我发起
```

---

# 第四层：关系健康度（Relationship Health）

回答：

```text
关系目前是否稳定？
```

---

## intimacy_level

亲密程度。

```yaml
intimacy_level:

  0~1
```

---

示例：

```yaml
intimacy_level:
  0.8
```

表示：

```text
亲密度较高
```

---

## trust_level

信任程度。

```yaml
trust_level:

  0~1
```

---

示例：

```yaml
trust_level:
  0.9
```

表示：

```text
彼此比较信任
```

---

## tension_level

关系紧张度。

```yaml
tension_level:

  0~1
```

---

示例：

```yaml
tension_level:
  0.7
```

表示：

```text
近期存在明显矛盾
```

---

# 与 Message Understanding 的关系

一个重要原则：

```text
Relationship State 不参与消息理解
```

---

例如：

消息：

```text
今天加班
```

---

消息理解：

```yaml
need:

  support: 0.9
```

---

无论：

```yaml
same_city
```

还是：

```yaml
long_distance
```

都不应该改变。

---

原因：

```text
消息本身没有变化
```

---

# Relationship State 应影响什么？

影响：

```text
Goal Planner

Strategy Selector
```

（目标规划和策略选择）

---

例如：

消息：

```yaml
need:

  support: 0.9
```

---

关系状态：

```yaml
distance_mode:
  long_distance

contact_frequency:
  sparse
```

---

Goal Planner：

```yaml
goals:

  support: 0.9

  increase_security: 0.3
```

---

解释：

```text
除了安慰

额外增加安全感建设
```

---

# MVP（第一版）建议

不要一次实现全部。

第一版只保留：

```yaml
relationship_state:

  stage:

  distance_mode:

  contact_frequency:
```

---

示例：

```yaml
relationship_state:

  stage:
    dating

  distance_mode:
    long_distance

  contact_frequency:
    daily
```

---

原因：

这三个字段已经覆盖：

```text
同城恋爱

异地恋

高频联系

低频联系
```

的大部分场景。

---

# V2 逐步扩展

未来增加：

```yaml
meeting_availability

initiative_balance

intimacy_level

trust_level

tension_level
```

---

# 最终原则

Relationship State 应该回答三个问题：

```text
我们是什么关系？

我们怎么接触？

我们平时怎么互动？
```

而不是仅仅回答：

```text
我们发展到了哪一步？
```

---

# 最终结构

```yaml
relationship_state:

  stage:

  connection_context:

    distance_mode:

    meeting_availability:

  interaction_pattern:

    contact_frequency:

    initiative_balance:

  relationship_health:

    intimacy_level:

    trust_level:

    tension_level:
```

这样未来无论增加：

* 异地
* 同居
* 见面频率
* 主动程度
* 关系健康度

都能自然扩展，而不会让整个系统越来越混乱。
