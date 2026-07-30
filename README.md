# 魔鬼聊天 (DevilChat)

AI 辅助微信聊天系统。实时分析对方消息的情绪/意图/需求，自动选择沟通策略并生成回复。

## 快速开始

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动 API 服务
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# E2E 测试
python scripts/e2e_test.py
```

## 架构

```
用户消息 → LangGraph 12节点流水线 → 生成回复
                       ↓
             SQLite + ChromaDB 双写记忆
```

### 流水线节点

```
message_understanding → need_recognition → goal_planning → conversation_engine
                                                                    ↓
                                        ┌─ 对话切换 → summarize → dedup → extract_memories
                                        └─ 正常 ───────────────────→ extract_memories
                                                                              ↓
                                                                     retrieve_context
                                                                              ↓
                                                              ┌─ observe → END
                                                              └─ intervene → strategy_select
                                                                                  ↓
                                                                         reply_generate
                                                                                  ↓
                                                                         enhance_reply → persist
```

### 技术栈

| 层 | 技术 |
|---|---|
| 编排 | LangGraph StateGraph |
| 数据库 | SQLite + ChromaDB (all-MiniLM-L6-v2) |
| LLM | OpenCode API (deepseek-v4-flash) |
| Web 面板 | FastAPI + SSE 流式 |

## 目录结构

```
├── backend/
│   ├── graph/              # LangGraph 流水线 (state, builder, 节点实现)
│   ├── memory/             # 记忆系统 (CRUD, 检索, 去重, 衰减)
│   ├── main.py             # FastAPI 入口
│   └── db.py               # SQLite + ChromaDB 连接管理
├── src/                    # 核心模块 (reply_generator, expression_enhancer, strategy_loader)
├── legacy/                 # 旧版代码 (JSON存储 + 同步调用)
├── scripts/                # 测试脚本
├── strategies/             # 策略卡 JSON
└── docs/                   # 架构文档
```

## 核心特性

### 记忆系统

从对话中自动提取 6 种结构化记忆，双写 SQLite + ChromaDB：

| 类型 | 说明 | 生命周期 |
|------|------|----------|
| emotional_moment | 关键情绪时刻 | 30天，7天后置信度衰减 |
| key_event | 重要生活事件 | 60天，30天后衰减 |
| unresolved_issue | 未解决冲突 | 90天，30天后衰减 |
| preference | 偏好/习惯 | 180天，语义去重合并 |
| user_fact | 用户事实 | 365天，语义去重合并 |
| shared_event | 共享经历 | 365天 |

### Burst 感知回复

对方连续发多条消息时自动检测，生成逐点回应的长回复而非一两句话敷衍。

### 表达增强

根据关系阶段（陌生→暧昧→稳定→冲突）自动调整回复语气，复杂输入跳过增强避免内容压缩。

### E2E 检查点

```
PASS  reply > 100 chars      # 复杂输入生成足量回复
PASS  enhanced keeps content  # 增强不破坏内容
PASS  memory extracted        # 记忆提取触发
```

## 配置

API Key 放在项目根目录 `ds.txt`（已 gitignore），或设置环境变量：

```bash
export OPENCODE_API_KEY=your-key
```

## 项目速查

新 AI 接手请先读 `CLAUDE.md`，包含完整的技术决策、已知陷阱和 7 个已修复 bug 的排查清单。

## License

Private
