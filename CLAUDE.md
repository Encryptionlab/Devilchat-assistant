# 魔鬼聊天 — AI Agent 速查

## 项目定位

AI 辅助微信聊天系统。核心流水线：收到对方消息 → LLM 分析情绪/意图/需求 → 选择策略卡 → 生成回复 → 表达增强。

## 技术栈速览

| 层 | 技术 |
|---|---|
| 流水线编排 | LangGraph StateGraph (MemorySaver) |
| 数据库 | SQLite (结构化) + ChromaDB (向量, all-MiniLM-L6-v2 384维) |
| LLM 调用 | OpenCode API, 同步 requests 通过 `run_in_executor` 桥接到 async |
| 入口 | `backend/main.py` (FastAPI) |

## 关键文件

```
backend/
├── graph/builder.py          # StateGraph 拓扑 (12节点+条件边)
├── graph/state.py            # PipelineState TypedDict
├── graph/nodes/__init__.py   # 全部节点实现 (~700行)
├── db.py                     # SQLite/ChromaDB 连接 + Schema DDL
├── config.py                 # API Key / 路径 / 常量
├── services/llm_service.py   # LLM 异步调用器
src/                          # 旧版核心模块 (新节点仍引用)
├── reply_generator.py        # Prompt构建 → LLM生成回复
├── expression_enhancer.py    # 回复润色
├── message_understanding.py  # MessageState 数据类
└── strategy_loader.py        # 策略卡 JSON 加载
```

## 流水线拓扑 (12节点)

```
message_understanding → need_recognition → goal_planning → conversation_engine
                                                              ↓
                              ┌─ 对话切换 ──────────────────→ summarize_and_extract → dedup_and_persist
                              │                                                              ↓
                              └─ 正常继续 ─────────────────────────────────────→ extract_memories
                                                                                       ↓
                                                                              retrieve_context
                                                                                       ↓
                                                                         ┌─ observe → END
                                                                         └─ intervene → strategy_select
                                                                                             ↓
                                                                                    reply_generate
                                                                                             ↓
                                                                                    enhance_reply
                                                                                             ↓
                                                                                    persist_result → END
```

## 关键设计决策

1. **observe 模式消息持久化**: `persist_result_node` 只在 intervene 模式执行，observe 模式需在入口层手动 INSERT
2. **记忆双写**: `_persist_memories` 必须同时写 SQLite(`memories_sql`) 和 ChromaDB(`memories` collection)，否则向量检索无效
3. **中文编码**: Windows 终端是 GBK，所有数据在 SQLite 中存 UTF-8。测试输出乱码不代表数据损坏
4. **记忆衰减**: 每次 extract 前自动调用 `apply_decay` (每 ~15 条消息)。TTL 到期自动删除 + 同步 ChromaDB，情绪/冲突类记录置信度定期减半。见 `backend/memory/store.py:_DECAY_CONFIG`

### 记忆衰减规则

| 类型 | TTL | 衰减 | 说明 |
|------|-----|------|------|
| emotional_moment | 30天 | 7天后每7天减半 | 情绪是瞬时的 |
| key_event | 60天 | 30天后减半 | 事件时效有限 |
| unresolved_issue | 90天 | 30天后减半 | 未解决冲突需较长时间 |
| preference | 180天 | 无 | 偏好相对稳定 |
| user_fact | 365天 | 无 | 事实长期不变 |
| shared_event | 365天 | 无 | 重要共享记忆 |

**触发点**: `extract_memories_node` 频率门通过后、LLM 提取前。best-effort，失败不阻塞流水线。
**去重**: preference/user_fact 用 ChromaDB 语义相似度合并（避免"要求情感对等"存 4 次），其他类型精确匹配。

---

## 已修复 Bug 清单 (2026-07-29)

以下 6 个 bug 是本项目特有的陷阱。任何 AI 接手时优先检查这些问题是否复现。

### Bug 1: LLM 输出值做分支判断 → 不可靠

**文件**: `src/reply_generator.py`, `src/expression_enhancer.py`
**现象**: 对方发了 30+ 条消息，生成的回复只有 2 句话
**根因**: 代码用 `burst_pattern in ("burst", "mixed")` 判断是否为复杂输入，但 LLM 实际返回 `"escalating"`（或其他值），永远匹配不上
**修复**: 改用确定性计算 `len(her_msgs) >= 5`，不依赖 LLM 字符串输出
**教训**: **不要在关键分支上依赖 LLM 的自由文本输出**。能用代码确定的事（消息数量、长度）就不要让 LLM 决定

### Bug 2: LangGraph 同一节点多条出边 = 并行执行

**文件**: `backend/graph/builder.py`
**现象**: `enhance_reply_node` 收到的 `reply_len=0`，增强后的回复只剩 30 字符（原文 500+）
**根因**: `strategy_select` 同时有两条出边：
- 直接边 → `reply_generate`
- 条件边 → `enhance_reply`

LangGraph 将其视为并行分支，`enhance_reply` 在 `reply_generate` 写入结果之前就启动了，拿到空 state
**修复**: 改为串行拓扑：
```
strategy_select → [条件] → reply_generate → enhance_reply → persist_result
```
三条全是顺序边，不再有并行分支
**教训**: **LangGraph 中同一节点出发的多条边 = 并行执行**。需要串行依赖时，必须把目标节点串成链，不能从同一源分叉

### Bug 3: 条件边返回值不在映射表中

**文件**: `backend/graph/builder.py`
**现象**: `KeyError: 'retrieve_context'`，流水线直接崩溃
**根因**: `_should_summarize` 函数返回 `"retrieve_context"`，但条件边的映射表里只有 `"summarize_and_extract"` 和 `"extract_memories"` 两个 key
**修复**: 改返回值为 `"extract_memories"`，使两个分支都经过记忆提取节点
**教训**: **添加/修改条件边时，确保函数的返回值集合 ⊆ 映射表 key 集合**。改了函数返回值就要同步改映射表

### Bug 4: 复杂回复被 Enhancer 压缩成一句话

**文件**: `backend/graph/nodes/__init__.py` (`enhance_reply_node`), `src/expression_enhancer.py`
**现象**: 500+ 字符的批量回复，enhancer 输出只剩 30 字符
**根因**: LLM 把"润色"理解为"总结"。Prompt 写了"保持长度"但模型不听。对复杂输入的多话题回复，enhancer 本身就是多余的——reply_generator 的输出已经足够口语化
**修复**: 两层防护：
1. 复杂输入 (`her_msgs >= 5`) 且回复已 ≥200 字符时，直接跳过 enhancer
2. 安全网：如果 enhancer 输出不到原文 50%，回退到原始回复
**教训**: **LLM 润色长文本时天然有压缩倾向**。不要指望 prompt 约束能完全防止。复杂回复直接跳过增强器是最安全的做法

### Bug 5: 记忆提取只写 SQLite，ChromaDB 为空

**文件**: `backend/graph/nodes/__init__.py` (`_persist_memories`)
**现象**: SQLite `memories_sql` 有数据，ChromaDB `memories` collection 为 0
**根因**: `_persist_memories` 只做了 `conn.execute(INSERT INTO memories_sql ...)`，缺少 ChromaDB 的 `coll.add()`
**修复**: INSERT 之后追加 ChromaDB 写入:
```python
coll = await get_chroma_collection("memories")
coll.add(ids=[mem_id], documents=[content], metadatas=[{...}])
```
**教训**: **双写逻辑必须显式验证两端都有数据**。写一个检查脚本定期对比 `COUNT(*)` from SQLite vs `coll.count()` from ChromaDB

### Bug 6: 记忆提取静默失败 — JSON 解析无容错

**文件**: `backend/graph/nodes/__init__.py` (`extract_memories_node`)
**现象**: 同批消息，上次提取 8 条，下次 0 条。`msg_count_since_extract=0` 证明 gate 开了，但 LLM 返回不能被解析
**根因**: `json.loads()` 不带容错。LLM 经常在 JSON 外包 ``` 代码块标记、或末尾加废话。`try/except` 只捕获 `(json.JSONDecodeError, KeyError)`，静默丢弃无日志
**修复**:
1. 解析前剥离 ``` 代码块标记
2. 加 `logging.warning` 打印解析失败时的原始 LLM 输出
3. `except Exception` 兜底防止未知异常崩溃节点
**教训**: **LLM 输出 JSON 不可靠，必须做 defensive parsing**。至少处理代码块包裹、末尾多余文本、字段缺失三种情况。失败必须有日志，否则排查时一脸茫然

### Bug 7: 回复中的 LLM 幻觉 — 发明不存在的信息

**文件**: 流水线 reply_generate 环节（非代码缺陷，是 LLM 行为）
**现象**: 对方说「小猪包那边闹别扭」「合作人」，系统回复加了「巨婴合作人」这个标签。原文无此表述
**根因**: LLM 在生成回复时会对模糊信息做推断和标签化，尤其在共情时容易追加自己的理解作为事实陈述
**当前策略**: 暂无代码级修复。Prompt 层可加约束：「不要给人物贴标签，不要说对方没说过的话」
**教训**: **每轮测试都应该检查回复中是否有原文未出现的信息**。这是 LLM 的固有问题，需要在 prompt 层面持续迭代约束

---

## 测试

```bash
# E2E 测试 (完整流水线, ~2分钟)
python scripts/e2e_test.py

# 检查点:
# - reply > 100 chars (复杂输入必须生成足量回复)
# - enhanced >= reply * 0.4 (增强器不能破坏内容)
# - extracted_memories > 0 (记忆提取必须触发)
# - SQLite + ChromaDB 双端行数一致
```

## 提交规范

- 分支: `feature/langgraph-postgresql-upgrade`
- 主分支: `main`
- 提交信息用中文，格式: `类型: 简述`
