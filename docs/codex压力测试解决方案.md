# MESSAGE_UNDERSTANDING_V2.md

# 基于100条消息压力测试的系统改进方案

Version: 2.0

---

# 背景

本次压力测试共模拟：

```yaml
118条消息
14天聊天
354次LLM调用
0失败
```

测试覆盖：

* exam
* daily
* relationship
* conflict
* dating
* family

六类典型恋爱聊天场景。

---

# 核心结论

测试暴露的问题看似很多：

```text
Topic错误

Conversation异常

Memory污染

策略失衡
```

但实际上：

```text
大部分问题来自同一个源头
```

即：

```text
Message Understanding 信息质量不足
```

---

当前系统链路：

```text
Message

↓

Message Understanding

↓

Need

↓

Goal

↓

Conversation

↓

Summary

↓

Memory
```

---

当 Message Understanding 输出错误时：

```text
Topic错误

↓

Conversation无法切分

↓

Summary混乱

↓

Memory污染
```

形成级联故障。

---

因此：

```text
下一阶段重点不是优化策略

而是重构 Message Understanding
```

---

# 第一部分：Topic系统重构

---

# 当前问题

现有 Topic：

```yaml
daily
exam
relationship
conflict
dating
family
```

存在分类混乱。

例如：

```text
你从来都不主动
```

被归类：

```yaml
conflict
```

---

但：

```text
conflict并不是话题
```

而是：

```text
情绪状态
```

---

真实含义：

```yaml
topic:
  relationship

conflict_signal:
  strong
```

---

# 设计原则

Topic 只回答：

```text
在聊什么
```

---

Conflict 单独回答：

```text
是否存在矛盾
```

---

# 新结构

```yaml
topic:

  daily

  exam

  family

  relationship

  dating
```

---

新增：

```yaml
conflict_signal:

  none

  mild

  strong
```

---

示例：

```text
你从来都不主动
```

输出：

```yaml
topic:
  relationship

conflict_signal:
  strong
```

---

示例：

```text
我妈今天又催考研
```

输出：

```yaml
topic:
  exam

conflict_signal:
  none
```

---

# Topic识别方案

废弃：

```python
TOPIC_KEYWORDS
```

方案。

---

改为：

```text
LLM直接输出Topic
```

---

原因：

```text
已经存在LLM调用

增加一个字段几乎没有成本
```

---

同时避免：

```text
维护数百个关键词
```

的长期负担。

---

# 第二部分：Summary系统重构

---

# 当前问题

当前流程：

```text
Summary

↓

key_points

↓

unresolved_topics
```

---

存在逻辑错误：

```text
关键事件
≠
未解决问题
```

---

例如：

```text
今天是认识100天
```

属于：

```yaml
key_points
```

---

但不是：

```yaml
unresolved_topics
```

---

# 新结构

Summarizer输出：

```yaml
summary:

key_points:

unresolved_items:
```

---

示例：

```yaml
summary:
  双方聊到认识100天纪念日。

key_points:

  - 今天是认识100天

unresolved_items:

  - 用户忘记纪念日
```

---

MemoryUpdater：

```python
memory.unresolved_topics += unresolved_items
```

---

不再从：

```yaml
key_points
```

推导。

---

# Outcome重构

当前：

```yaml
resolved

unresolved
```

过于粗糙。

---

新增：

```yaml
resolved

neutral

unresolved
```

---

定义：

## resolved

问题解决。

例如：

```text
好多了
```

---

## unresolved

问题仍存在。

例如：

```text
还是很难受
```

---

## neutral

没有问题需要解决。

例如：

```text
晚安

吃饭了吗

今天下雨了
```

---

预计：

```text
70%以上Conversation
应为neutral
```

---

# 第三部分：Conversation Boundary重构

---

# 当前问题

依赖：

```text
30min

2h

8h
```

固定时间规则。

---

问题：

```text
时间不等于话题结束
```

---

例如：

```text
上午：
考研压力好大

↓

下午：
还是很焦虑
```

间隔6小时。

仍然是同一Conversation。

---

# 新方案

引入：

```yaml
boundary_score
```

---

结束信号：

```yaml
good_night

bye

sleep

go_work

topic_switch
```

---

每个信号增加分数：

```yaml
good_night:
  +0.8

topic_switch:
  +0.4

long_gap:
  +0.2
```

---

达到阈值：

```yaml
boundary_score >= 1.0
```

关闭Conversation。

---

原则：

```text
事件驱动

优于

时间驱动
```

---

# 第四部分：Strategy系统调整

---

# 当前现象

```text
逐级释放与反馈循环

占60%
```

---

# 判断

这并不一定是问题。

---

原因：

```text
策略

不是回复
```

---

同一个策略：

```yaml
emotional_support
```

可以生成：

```text
哈哈那也太惨了
```

也可以生成：

```text
让我看看是谁欺负我们家小朋友
```

---

# 建议

不要追求：

```text
策略均匀分布
```

---

应该监控：

```yaml
response_style
```

---

新增：

```yaml
response_style:

  playful

  warm

  teasing

  romantic

  serious
```

---

统计：

```text
回复风格分布
```

而不是：

```text
策略卡分布
```

---

# 第五部分：Relationship State优化

---

当前阶段：

保留：

```yaml
relationship_state:

  stage:

  interaction_context:
```

---

示例：

```yaml
relationship_state:

  stage:
    relationship

  interaction_context:
    long_distance
```

---

职责：

```text
约束策略

影响Goal

不参与消息理解
```

---

原则：

```text
Relationship State
是策略约束器

不是消息解释器
```

---

# 第六部分：开发优先级

---

## P0

重构 Topic

```yaml
topic

conflict_signal
```

改为LLM输出。

---

## P1

重构 Summary

新增：

```yaml
unresolved_items
neutral
```

---

## P2

Conversation Boundary

实现：

```yaml
boundary_score
```

机制。

---

## P3

Relationship State

加入：

```yaml
interaction_context
```

---

## P4

策略系统优化

监控：

```yaml
response_style
```

而不是策略命中率。

---

# 最终结论

本次压力测试证明：

```text
系统最大的瓶颈

不是策略卡

不是Goal

不是Memory
```

而是：

```text
Message Understanding
```

下一阶段应集中优化：

```yaml
topic

conflict_signal

need_scores

relationship_signal
```

这些基础字段。

只有当消息理解足够稳定：

```text
Conversation

Summary

Memory

Strategy
```

才会稳定。

---

# 一句话总结

```text
先修地基（Message Understanding）

再装修房子（Goal、Strategy、Memory）
```
