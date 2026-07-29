# 问题分析与修复方案

## 问题 1：复杂消息的回复太短

### 根因

对方连续发 30+ 条消息（11 个具体问题 + 情绪爆发），系统最终只回了两句话。

追踪调用链：

```
她发了 30+ 条消息
  → message_understanding: 正确识别 emotion=angry, burst_pattern=mixed ✅
  → reply_generate_node: 构造 MessageState 时 message=last_msg（最后一句） ❌
  → ReplyGenerator._build_user_prompt:
      - chat_history 截断到 [-6:] ← 只能看到 6 轮对话 ❌
      - "她的最新消息" = ms.message = 只有最后一句 ❌
      - burst_pattern 分析结果没有传入 ❌
  → LLM 只看到一句话 → 生成短回复
  → ExpressionEnhancer: "太长的句子拆短" → 进一步压缩 ❌
```

核心矛盾：**message_understanding 做了完整的多消息分析，但 reply_generate 只用到了最后一条消息的文本**。

### 方案对比

**方案 A：消息拼接（直觉方案）**
- 把她的所有消息拼成一个长字符串，作为 ms.message 传入
- 优点：实现简单，2 行改动
- 缺点：长文本容易超出 LLM 上下文窗口；没有结构，LLM 抓不住重点；不解决 enhancer 压缩问题

**方案 B：两遍生成（高质量方案）**
- 第一遍 LLM：分析输入，提取出"需要回应的要点列表"
- 第二遍 LLM：逐一回应每个要点，拼接成完整回复
- 优点：回复质量最高，每个问题都能被覆盖
- 缺点：多 1 次 LLM 调用，延迟 +5~10s；成本翻倍

**方案 C：结构化上下文注入（推荐）**
- 在 reply_generate_node 中，利用 message_understanding 已有的分析结果（emotion, intent, need_scores, topic），构建一个"她表达了什么"的结构化摘要
- 把 burst_pattern 直接传给 prompt builder，当 burst 时告知 LLM"她连续发了多条消息，请确保回复覆盖所有要点"
- chat_history 从 [-6:] 扩大到按字符数截断（如最多 2000 字）
- enhancer 的"太长的句子拆短"改为条件规则：当原始回复 < 100 字时才拆短，> 200 字时保留信息密度
- 优点：不增加 LLM 调用；复用已有分析；延迟不变
- 缺点：依赖 message_understanding 的分析质量

**方案 D：规则分点 + 逐条回应**
- 用规则（非 LLM）扫描她的消息，识别问号、序号列表、关键词、换行分段
- 生成一个"待回应清单"，inject 到 prompt 里要求 LLM 逐条回应
- 优点：不需要额外 LLM 调用；对序号列表（如她的 1-11 条）特别有效
- 缺点：对隐含问题（非问号结尾）识别差

### 选择：方案 C + D 混合

| 改动位置 | 具体做法 |
|---------|---------|
| `reply_generate_node` | 构造结构化上下文：情绪 + 意图 + 话题 + `ms.message` 改为她的全部消息摘要 |
| `_build_user_prompt` | burst 模式时展开 chat_history；显式列出所有她的消息 |
| `enhance_reply_node` | enhancer 加"输入消息复杂度"判断，复杂场景下保留长度 |
| expression_enhancer prompt | 移除"太长的句子拆短"，改为"原始回复的信息密度保持不变" |

不改 graph 结构，不增加 LLM 调用。

---

## 问题 2：记忆提取不生效

### 根因

```
summarize_and_extract_node 只在 conversation_switched=true 时触发
  → 一个 LLM 调用同时承担 4 个任务：
      1. 对话总结 (summary)
      2. 结果判断 (outcome)
      3. 关键点提取 (key_points)
      4. 记忆提取 (memories)
  → LLM 注意力集中在 summary 上，memories 返回空数组
  → _extracted_memories = []
  → dedup_and_persist_node 没有新记忆可存
  → SQLite memories_sql 和 ChromaDB 都无新数据
```

核心矛盾：**记忆提取（需要持续积累）被捆绑在对话结束（偶尔触发）上，且一个 prompt 任务太多**。

### 方案对比

**方案 A：拆分 summarizer 的 LLM 调用（最小改动）**
- 把 `summarize_and_extract_node` 的一个 LLM 调用拆成两个：先 summary，再 memory extraction
- 两个调用都在 conversation close 时执行
- 优点：改动小；memory prompt 更聚焦
- 缺点：仍只在对话结束时提取，日常聊天不产生记忆

**方案 B：新增独立记忆提取节点（推荐）**
- 在 graph 中新增 `extract_memories` 节点
- 不捆绑 conversation close，每次 pipeline 运行都可触发
- 用计数器控制频率：每积累 20 条新消息或对话切换时触发
- 独立的、聚焦的 LLM prompt：只提取 6 种类型记忆
- 提取后立即 dedup + 双写（SQLite + ChromaDB）
- 优点：记忆持续积累；向量库实时更新；prompt 聚焦效果好
- 缺点：多 1 次 LLM 调用，observe 延迟 +5~10s

**方案 C：规则 + LLM 混合提取**
- 简单记忆用规则从 message_understanding 输出派生（如 "emotion=angry, topic=conflict" → emotional_moment）
- 复杂记忆（preference, user_fact）才用 LLM
- 优点：减少 LLM 调用次数
- 缺点：规则提取的记忆质量差，容易产生噪音

**方案 D：ChromaDB 增量更新**
- 不新增 LLM 调用，而是把每条 MESSAGE 本身 embed 存入 ChromaDB
- 需要搜索时直接语义搜索 raw messages
- 优点：零额外成本；所有消息都可被搜索
- 缺点：messages 不是结构化记忆，没有 memory_type 标签；噪音大

### 选择：方案 B（独立记忆提取节点）

| 改动位置 | 具体做法 |
|---------|---------|
| `builder.py` | 在 `retrieve_context` 前插入 `extract_memories` 节点 |
| 新增 `extract_memories_node` | 频率门控（每 20 条触发），独立 LLM 调用，只提取 typed memories |
| prompt 设计 | 聚焦 6 种记忆类型，输入是最新 N 条消息，输出是记忆列表 JSON |
| `dedup_and_persist_node` | 改为同时处理"对话关闭记忆"和"增量记忆"两种来源 |

频率门控逻辑：
```
if message_count_since_last_extraction >= 20 or conversation_switched:
    执行 extract_memories → dedup → 写入 SQLite + ChromaDB
else:
    跳过
```

---

## 改动总览

| 文件 | 改动 | 新增 LLM 调用 |
|------|------|:---:|
| `reply_generator.py` | 结构化上下文注入 + burst 感知 | 0 |
| `expression_enhancer.py` | 条件长度规则 | 0 |
| `graph/nodes/__init__.py` | 新增 `extract_memories_node` + 修改 `reply_generate_node` + `enhance_reply_node` | +1（按频率） |
| `graph/builder.py` | 插入 `extract_memories` 节点 + 条件边 | 0 |

净增 LLM 调用：每 20 条消息 1 次（记忆提取），实际场景约每 10-30 分钟 1 次。

---

## 预期效果

修复后同样输入（83 条消息，含 11 个问题和情绪爆发）：

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 回复长度 | 2 句话 | 逐点回应，5-8 句 |
| 问题覆盖 | 0/11 | 8+/11 |
| 记忆提取 | 0 条 | 5-15 条 typed memories |
| ChromaDB 向量 | 1（不变） | 6-16 |
| observe 延迟 | ~53s | ~60s（+1 次记忆 LLM） |
| intervene 延迟 | ~82s | ~90s |

---

*文档时间：2026-07-29*
