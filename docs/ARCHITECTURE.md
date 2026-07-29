# 魔鬼聊天 — 项目架构文档

## 1. 项目概述

"魔鬼聊天"是一套 AI 辅助恋爱聊天系统。核心流程：接收对方消息 → LLM 分析情绪/意图/需求 → 选择策略 → 生成回复 → 表达增强。

当前项目处于 **双版本并存 + 微信接入** 阶段：
- **新版 (backend/)**：LangGraph 状态图 + SQLite + ChromaDB，支持双轨道（观测/干预）
- **旧版 (legacy/)**：顺序调用 + JSON 文件存储，功能完整但架构简单
- **微信接入 (backend/wcf/)**：通过 WeChatFerry DLL 注入，实时接收微信消息

仓库地址：本地 git 仓库，分支 `feature/langgraph-postgresql-upgrade`

---

## 2. 目录结构

```
D:\AIagent\魔鬼聊天\
├── backend/                          # 新版后端（LangGraph + SQLite + ChromaDB）
│   ├── main.py                       # 新版 API 入口 (FastAPI, port 8000)
│   ├── main_wcf.py                   # WCF 消息中继入口 (FastAPI, port 8000)
│   ├── config.py                     # 全局配置 (路径/API Key/常量)
│   ├── db.py                         # SQLite + ChromaDB 连接管理 + Schema DDL
│   ├── graph/                        # LangGraph 状态图
│   │   ├── state.py                  # PipelineState TypedDict 定义
│   │   ├── builder.py                # StateGraph 组装 (10节点+条件边)
│   │   └── nodes/__init__.py         # 10个节点实现 (~700行)
│   ├── memory/                       # 记忆子系统
│   │   ├── store.py                  # 记忆CRUD (双写 SQLite + ChromaDB)
│   │   ├── retrieval.py             # 混合检索 (ChromaDB语义 + SQLite关键词)
│   │   └── dedup.py                 # 语义去重 (ChromaDB相似度 + SQLite fallback)
│   ├── routing/                      # 模型路由
│   │   └── model_router.py          # 按任务复杂度路由不同LLM
│   ├── prompts/                      # Prompt工程
│   │   ├── __init__.py
│   │   └── assembler.py            # 动态Prompt组装
│   ├── routers/                      # HTTP API 路由
│   │   ├── graph.py                 # /api/graph/chat, /stream, /observe
│   │   └── wcf.py                   # /api/wcf/status, /messages, /reply, /events, /panel
│   ├── services/                     # 共享服务
│   │   └── llm_service.py           # 异步LLM调用器 (线程池桥接)
│   ├── wcf/                          # 微信消息接入 (WeChatFerry)
│   │   ├── client.py                # WeChatFerry SDK封装
│   │   └── relay.py                 # 消息中继 (轮询→管道→Web面板)
│   └── docs/                         # 旧文档备份
│
├── legacy/                           # 旧版后端（JSON + 同步）
│   ├── main.py                       # 旧版API入口 (FastAPI)
│   ├── dependencies.py              # 服务单例注入
│   ├── routers/                      # REST API
│   │   ├── chat.py                  # /api/chat
│   │   ├── conversations.py         # 对话历史
│   │   ├── relationship.py          # 关系状态CRUD
│   │   ├── bootstrap.py            # 引导初始化
│   │   └── observe.py              # 观测模式
│   ├── schemas/                      # Pydantic请求/响应模型
│   ├── services/                     # 业务逻辑
│   │   ├── pipeline_service.py     # 10步流水线编排
│   │   ├── state_service.py        # JSON文件读写
│   │   ├── message_buffer.py       # 消息缓冲器
│   │   └── urgency_scorer.py       # 紧急度评分
│   └── __init__.py
│
├── src/                              # 核心流水线模块（新旧版共享）
│   ├── message_understanding.py      # 步骤1: 消息理解 (LLM)
│   ├── need_recognition.py           # 步骤2: 需求识别 (LLM)
│   ├── goal_planner.py               # 步骤3: 目标规划 (LLM)
│   ├── conversation.py               # 步骤4: 对话引擎 (话题切换检测)
│   ├── summarizer.py                 # 步骤5: 对话摘要
│   ├── memory_updater.py             # 步骤6: 记忆更新
│   ├── context_builder.py            # 步骤7: 上下文构建
│   ├── strategy_selector.py          # 步骤8: 策略选择
│   ├── reply_generator.py            # 步骤9: 回复生成 (LLM)
│   ├── expression_enhancer.py        # 步骤10: 表达增强 (LLM)
│   ├── strategy_loader.py            # 策略JSON加载器
│   ├── bootstrap.py                  # 关系初始化引导
│   ├── evaluator.py                  # 策略效果评估
│   └── __init__.py
│
├── strategies/                       # 策略卡片（JSON配置文件）
│   ├── core_strategies/              # 核心策略
│   │   ├── validate_emotion_express_need.json
│   │   ├── eighty_twenty_rule.json
│   │   ├── humorous_deflection.json
│   │   ├── signal_escalation.json
│   │   ├── care_vs_attention.json
│   │   └── escalating_conflict.json
│   ├── archive/                      # 归档策略
│   │   ├── empathy.json, listening.json, banter.json ...
│   │   ├── strategy_matrix.json      # 策略矩阵
│   │   └── emotion_need_labels.json  # 情绪/需求标签
│   ├── expression_boosters/          # 表达增强规则
│   │   └── devils_fun_rule.json
│   └── README.md
│
├── web/                              # 前端
│   └── panel.html                    # WCF Web 面板 (纯HTML, 微信风格)
│
├── data/                             # 运行时数据
│   ├── conversations.json            # 旧版对话历史
│   ├── relationship_state.json       # 旧版关系状态
│   └── mock_wcf_story_3000.jsonl     # Mock测试数据 (3000条对话)
│
├── scripts/                          # 工具脚本（已清空，用完即删）
├── docs/                             # 项目文档
│   └── ARCHITECTURE.md              # 本文档
├── ds.txt                            # API Key文件 (第一行格式: key=xxx)
├── run.py                            # CLI入口 (旧版)
└── .gitignore
```

---

## 3. 核心架构

### 3.1 双版本并存

```
┌──────────────────────────────────────────────────┐
│                    魔鬼聊天                        │
├──────────────────────┬───────────────────────────┤
│   legacy/ (旧版)     │   backend/ (新版)           │
│                      │                            │
│   JSON 文件存储       │   PostgreSQL + pgvector    │
│   同步 requests 调用   │   异步 asyncpg + 线程池    │
│   线性流水线          │   LangGraph 状态图          │
│   单一模式 (干预)      │   双模式 (观测 + 干预)       │
│   REST API           │   REST API + SSE 流式       │
│                      │                            │
│   共享 src/ 模块      │   共享 src/ 模块            │
│   (LLM调用逻辑)       │   (LLM调用逻辑)             │
└──────────────────────┴───────────────────────────┘
```

### 3.2 LangGraph 流水线（新版核心）

10 个节点，3 个条件分支：

```
messages ──→ [message_understanding]  ① LLM: 情绪/意图/需求评分
                    │
            [need_recognition]        ② 基于评分识别主导需求
                    │
            [goal_planning]           ③ 需求→目标映射
                    │
            [conversation_engine]     ④ 话题切换/对话结束检测
                    │
            ┌───────┴────────┐
            │ 对话结束?        │
            ▼                ▼
   [summarize_and_extract]  [retrieve_context]   ⑦ 记忆召回 + LLM上下文
            │                        │
   [dedup_and_persist]        ┌──────┴────────┐
            │                 │ mode=observe?  │
            └─────→ [retrieve_context]   │
                              │              │
                       END ◄──┘              ▼
                                      [strategy_select]   ⑧ 策略匹配
                                             │
                                      [reply_generate]    ⑨ 生成回复 (LLM)
                                             │
                                      [enhance_reply]     ⑩ 表达增强 (LLM)
                                             │
                                      [persist_result]    保存消息+记忆
                                             │
                                            END
```

**状态定义** (`PipelineState`, TypedDict, 32 个字段)：
- 输入：messages, mode ("observe"|"intervene"), contact_id
- 中间产出：emotion, dominant_need, goal, strategy_name, ...
- 输出：reply, enhanced_reply

**LLM 调用**：通过 `src/` 模块 → OpenCode API (`deepseek-v4-flash`)

### 3.3 数据库设计 (SQLite + ChromaDB 混合存储)

**SQLite** (aiosqlite, 异步访问)：7 张表存储结构化数据。
**ChromaDB** (PersistentClient, 嵌入式)：memories 集合存储向量嵌入，支持语义搜索。

所有数据存储于 `data/` 目录，零配置，无需外部服务。

| 存储层 | 表/集合 | 用途 | 关键字段 |
|------|------|------|---------|
| SQLite | `contacts` | 联系人 | wxid, display_name |
| SQLite | `relationship_state` | 关系状态 | stage, trust_level, intimacy, conflict_level |
| SQLite | `memories_sql` | 记忆库（结构化） | memory_type, content, confidence, importance |
| ChromaDB | `memories` | 记忆库（向量） | content + embedding (all-MiniLM-L6-v2, 384维) |
| SQLite | `conversations` | 对话会话 | topic, status, goal, key_points |
| SQLite | `messages` | 消息记录 | role(我/她), content, emotion, intent |
| SQLite | `strategy_metrics` | 策略效果 | strategy_name, successes/failures, success_rate |
| SQLite | `checkpoints` | LangGraph 检查点 | thread_id, checkpoint(JSONB) |

**记忆写入策略**：主路径写入 SQLite (`memories_sql` 表)，同时 best-effort 写入 ChromaDB (`memories` 集合)。
**记忆检索策略**：优先 ChromaDB 语义搜索（cosine 距离），失败时 fallback 到 SQLite LIKE 关键词匹配。
**嵌入模型**：ChromaDB 自动下载 all-MiniLM-L6-v2（79MB，首次一次性），384 维向量。

数据库文件：
- `data/devilchat.db` — SQLite 主库 (WAL 模式)
- `data/chroma/` — ChromaDB 持久化目录

### 3.4 微信接入架构 (WCF)

```
微信 3.9.12.51 (小号)
    │
    │ WeChatFerry DLL 注入 (sdk.dll → spy.dll)
    │ protocol: gRPC + nanomsg, port 10086
    ▼
WcfClient (backend/wcf/client.py)
    │ 后台线程 drain 消息队列
    │ 过滤: sender == target_wxid 且 type == 1 (文本)
    ▼
WcfRelay (backend/wcf/relay.py)
    │ 轮询 → 批量 (5条或5秒) → 喂给 LangGraph observe 管道
    │ 缓冲区: deque(maxlen=200)
    │ 手动回复队列: _pending_replies
    ▼
┌─────────────────────────────────────┐
│ Web Panel (web/panel.html)           │
│ - 实时消息流 (轮询1.5s + SSE)         │
│ - 情绪/话题标签                       │
│ - 手动输入回复 → POST /api/wcf/reply  │
└─────────────────────────────────────┘
```

**关键配置**：
- 微信版本：3.9.12.51 (FileVersion), 内部构建 3.9.12.1000
- wcferry 版本：39.5.1.0 (pip安装, 必须匹配微信版本)
- 目标联系人：wxid_5qyz6dc2i4p322 (李彤彤)
- **注入参数：debug=True (必须！debug=False会导致注入失败)**

---

## 4. API 端点汇总

### 新版 (`backend/main.py`, port 8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 (含 SQLite 状态) |
| POST | `/api/graph/chat` | 完整流水线 (非流式) |
| POST | `/api/graph/chat/stream` | 完整流水线 (SSE流式) |
| POST | `/api/graph/observe` | 观测模式 (仅分析，不生成回复) |

### WCF Panel (`backend/main_wcf.py`, port 8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 中继状态 |
| GET | `/api/wcf/status` | WCF 健康+统计 |
| GET | `/api/wcf/messages?n=50` | 最近N条缓冲消息 |
| POST | `/api/wcf/reply` | 向目标发送文本 |
| POST | `/api/wcf/reply/{wxid}` | 向指定wxid发送文本 |
| GET | `/api/wcf/contacts` | 微信通讯录 |
| GET | `/api/wcf/events` | SSE实时消息推送 |
| GET | `/api/wcf/panel` | Web面板 HTML页面 |

### 旧版 (`legacy/main.py`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | 聊天 (非流式) |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/relationship` | 关系状态 |
| PUT | `/api/relationship` | 修改关系状态 |
| POST | `/api/bootstrap` | 关系引导初始化 |
| POST | `/api/observe` | 观测模式 |

---

## 5. 已完成功能

### 后端核心
- [x] LangGraph 10节点流水线 (StateGraph + MemorySaver)
- [x] SQLite + ChromaDB 混合存储 (7张SQLite表 + 向量集合)
- [x] 异步数据库访问 (aiosqlite)
- [x] 记忆系统 (CRUD / 语义检索 / 去重 / 衰减)
- [x] 双轨道模式：observe (观测) + intervene (干预)
- [x] 条件分支：对话结束→摘要→记忆持久化
- [x] SSE 流式输出 (graph/chat/stream)
- [x] 策略矩阵 (6个核心策略 + 归档策略)
- [x] 表达增强规则
- [x] 模型路由 (按任务复杂度选择不同LLM)
- [x] UUID/WXID 自动解析 (resolve_contact_id)
- [x] 时间戳安全转换 (_parse_ts)
- [x] LLM JSON解析失败重试 + fallback
- [x] 全局异常处理 + traceback
- [x] 数据库零配置启动 (无需安装 PostgreSQL)

### 微信接入
- [x] WeChatFerry SDK 封装 (WcfClient)
- [x] 消息中继 (WcfRelay: 轮询→管道→面板)
- [x] 联系人过滤 (仅目标wxid)
- [x] REST API + SSE实时推送
- [x] Web 面板 (微信风格, 轮询+SSE双通道)
- [x] 手动回复功能

### 项目整理
- [x] 新旧版本分离 (legacy/ vs backend/)
- [x] 共享模块保持 (src/)
- [x] 文档分类归档

---

## 6. 未完成 / 待推进

### 高优先级
- [ ] **微信消息实测** — WCF注入已成功，但完整流程（消息→管道→面板→回复）尚未端到端测试
- [ ] **LangGraph + WCF 集成测试** — observe管道是否能正确处理真实微信消息
- [ ] **SQLite 持久化确认** — 检查 WCF 消息是否正确写入 messages 表
- [ ] **Web 面板优化** — 情绪/话题标签目前来自管道，需验证显示效果
- [ ] **wecferry 版本最终确认** — 当前使用 39.5.1.0，需验证长期稳定性；39.5.2.0 会导致微信崩溃

### 中优先级
- [ ] **前端重构** — 当前仅有 Web 面板 (panel.html)，计划中的 Next.js 前端未开始
- [ ] **PWA 移动端支持** — 计划中，未实施
- [ ] **LangGraph checkpointer 升级** — 当前 MemorySaver，应换成 PostgresSaver 实现持久化
- [ ] **策略效果自动评估** — strategy_metrics 表已建，evaluator.py 已写，但未与管道集成
- [ ] **自动回复模式** — 当前仅手动回复，若加自动回复需接入 urgency_scorer

### 低优先级
- [ ] **多联系人支持** — 当前设计支持多 contact_id，但UI/体验未适配
- [ ] **旧版废弃** — legacy/ 保留了完整的旧版功能，新版稳定后可删除
- [ ] **CI/CD** — 无
- [ ] **Docker 化** — 无容器化，但 SQLite + ChromaDB 的零配置特性使部署极简
- [ ] **测试覆盖率** — 仅有功能验证脚本 (7个测试用例)

---

## 7. 已知问题与注意事项

### 微信相关
1. **WeChatFerry 已归档** — lich0821/WeChatFerry 已于 2026-07-10 归档，不再维护
2. **微信版本严格锁定** — 必须 3.9.12.51，新版微信 4.x 不兼容
3. **WxInitSDK 必须 debug=True** — 这是关键发现，debug=False 会导致注入失败（错误码5）或微信崩溃
4. **微信与主号共存** — 当前小号 (3.9.12.51) 和主号 (4.x) 装在同一系统，同时运行需 Sandboxie
5. **DLL注入需要管理员权限** — wcferry 的 spy.dll 注入需要 Administrator 权限
6. **封号风险** — WeChatFerry issue #126 有封号讨论，使用非官方 hook 工具存在账号风险

### 技术债务
7. **LLM JSON 解析不稳定** — message_understanding 有时返回格式错误的JSON，已加重试+fallback
8. **MessageState @dataclass** — nodes/__init__.py 中有大量字段填充代码，结构不够优雅
9. **checkpointer 是内存模式** — 服务重启后 LangGraph 状态丢失（checkpoints 表已有 SQLite 持久化但未接入 SqliteSaver）
10. **src/ 模块同步阻塞** — LLM 调用通过 requests (同步) + 线程池桥接 asyncio
11. **无认证机制** — API 无鉴权，局域网内任何人可访问
12. **ChromaDB 嵌入模型大** — all-MiniLM-L6-v2 首次下载 79MB，离线环境需预下载

---

## 8. 运行命令

### 启动新版 API（不含微信）
```bash
cd D:\AIagent\魔鬼聊天
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
前提：无外部依赖，SQLite + ChromaDB 自动初始化（首次启动 ChromaDB 会下载嵌入模型 ~79MB）

### 启动 WCF 消息中继（含微信）
```bash
cd D:\AIagent\魔鬼聊天
python -m backend.main_wcf --target wxid_5qyz6dc2i4p322
```
前提：
1. 微信 3.9.12.51 已登录小号
2. wcferry 39.5.1.0 已安装
3. 以**管理员权限**运行终端
4. Web 面板：http://localhost:8000/api/wcf/panel

### 启动旧版 API
```bash
cd D:\AIagent\魔鬼聊天
python -m uvicorn legacy.main:app --host 0.0.0.0 --port 8001
```

---

## 9. 依赖清单

### Python 包
```
fastapi, uvicorn[standard], langgraph, pydantic
aiosqlite         (SQLite 异步访问, 纯 Python)
chromadb          (向量数据库, 嵌入式, 自动下载嵌入模型)
wcferry==39.5.1.0 (微信注入, 必须此版本)
pynng, protobuf, grpcio-tools (wcferry 依赖)
requests           (LLM HTTP调用)
```

### 外部服务
- **微信 3.9.12.51** (PC客户端, 小号登录, 仅 WCF 模式需要)
- **OpenCode API** (LLM, base_url: https://opencode.ai/zen/go/v1/chat/completions)
- **API Key** 存放于 `ds.txt`
- **无需 PostgreSQL 或其他外部数据库**

---

## 10. 下一步推进建议

1. **立即**：启动 WCF 中继，用真实微信消息跑通完整流程
2. **短期**：将 checkpointer 从 MemorySaver 换成 SqliteSaver，实现状态持久化（checkpoints 表已建）
3. **短期**：添加消息持久化确认日志，验证每条微信消息都正确写入 messages 表
4. **中期**：重构前端 (Next.js PWA)，替代 panel.html
5. **中期**：集成 evaluator.py 实现策略效果自动评估
6. **长期**：关注 WeChatFerry 社区 fork，寻找微信 4.x 的替代注入方案

---

*文档更新时间：2026-07-29 | 分支：feature/langgraph-postgresql-upgrade*
*本次更新：PostgreSQL + pgvector → SQLite + ChromaDB 混合存储迁移*
