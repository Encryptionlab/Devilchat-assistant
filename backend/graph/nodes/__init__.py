"""LangGraph node implementations — thin wrappers that bridge src/ logic into StateGraph."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from backend.graph.state import PipelineState
from backend.config import RS_PATH


# ============================================================
# Node 1: Message Understanding (LLM)
# ============================================================

async def message_understanding_node(state: PipelineState) -> dict:
    from src.message_understanding import MessageUnderstanding
    from backend.services.llm_service import LlmService
    from backend.config import load_api_key

    messages = state["messages"]
    mode = state.get("mode", "intervene")

    mu = MessageUnderstanding()
    llm = LlmService(api_key=load_api_key())

    if mode == "observe":
        recent = messages[-15:]
        user_prompt = mu.build_user_prompt_for_sequence(recent)
    else:
        her_msgs = [m for m in messages if m.get("role") == "她"]
        user_prompt = mu.build_user_prompt(her_msgs)

    result_text = await llm.chat(mu.system_prompt, user_prompt)
    try:
        ms = mu.parse_to_state(result_text)
    except (json.JSONDecodeError, KeyError, ValueError):
        # Retry once with explicit format reminder
        result_text = await llm.chat(
            mu.system_prompt + "\n\nCRITICAL: Output ONLY valid JSON, no markdown fences, no extra text.",
            user_prompt,
        )
        try:
            ms = mu.parse_to_state(result_text)
        except (json.JSONDecodeError, KeyError, ValueError):
            return _fallback_mu_state(messages, mode)

    return {
        "emotion": ms.emotion,
        "emotion_intensity": ms.emotion_intensity,
        "dominant_intent": ms.dominant_intent,
        "topic": ms.topic,
        "need_scores": ms.need_scores,
        "burst_pattern": ms.burst_pattern,
        "trajectory_note": ms.trajectory_note,
        "conversation_stage": ms.conversation_stage,
    }


# ============================================================
# Node 2: Need Recognition (rules)
# ============================================================

async def need_recognition_node(state: PipelineState) -> dict:
    from src.need_recognition import NeedRecognizer
    from src.message_understanding import MessageState

    rs_raw = _load_rs_raw()
    ms = MessageState(
        message="",
        surface_intent_scores={},
        emotion=state["emotion"],
        emotion_intensity=state["emotion_intensity"],
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
    )

    result = NeedRecognizer(rs_raw).prioritize(ms)
    return {
        "top_needs": result.get("top_needs", []),
        "dominant_need": result.get("dominant_need", ""),
    }


# ============================================================
# Node 3: Goal Planning (rules)
# ============================================================

async def goal_planning_node(state: PipelineState) -> dict:
    from src.goal_planner import GoalPlanner
    from src.message_understanding import MessageState

    rs_raw = _load_rs_raw()
    ms = MessageState(
        message="",
        surface_intent_scores={},
        emotion=state["emotion"],
        emotion_intensity=state.get("emotion_intensity", 0.5),
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
    )

    result = GoalPlanner(rs_raw).plan(ms, state.get("top_needs", []))
    return {
        "goal": result["goal"],
        "goal_zh": result.get("goal_zh", result["goal"]),
    }


# ============================================================
# Node 4: Conversation Engine (rules + conditional LLM summary)
# ============================================================

async def conversation_engine_node(state: PipelineState) -> dict:
    from src.conversation import ConversationManager
    from backend.config import CONV_PATH

    conv_mgr = ConversationManager(storage_path=CONV_PATH)
    messages = state["messages"]
    her_msg = " ".join(m.get("content", "") for m in messages if m.get("role") == "她")
    if not her_msg:
        her_msg = messages[-1].get("content", "") if messages else ""

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    prev_conv = conv_mgr.get_active_conversation()
    conv, switched = conv_mgr.process_message(
        her_msg, ts, state.get("goal"),
        topic_override=state.get("topic"),
    )

    return {
        "conversation_id": conv.id,
        "conversation_switched": switched,
        "closed_conversation": prev_conv.to_dict() if switched and prev_conv else None,
    }


# ============================================================
# Node 5a: Summarize + Extract Memories (LLM)
# ============================================================

async def summarize_and_extract_node(state: PipelineState) -> dict:
    from backend.services.llm_service import LlmService
    from backend.config import load_api_key

    closed = state.get("closed_conversation")
    if not closed:
        return {}

    llm = LlmService(api_key=load_api_key())
    msg_texts = []
    for m in closed.get("messages_log", [])[-50:]:
        role = m.get("role", "")
        content = m.get("content", "")
        msg_texts.append(f"{role}: {content}")

    conversation_text = "\n".join(msg_texts)
    topic = closed.get("topic", "daily")

    prompt = _build_summary_extract_prompt(conversation_text, topic)
    result_text = await llm.chat(prompt, "")

    try:
        parsed = json.loads(result_text)
    except json.JSONDecodeError:
        parsed = {"summary": result_text[:200], "memories": []}

    return {
        "closed_conversation": {
            **closed,
            "summary": parsed.get("summary", ""),
            "outcome": parsed.get("outcome", "neutral"),
            "key_points": parsed.get("key_points", []),
        },
        "_extracted_memories": parsed.get("memories", []),
    }


def _build_summary_extract_prompt(conversation_text: str, topic: str) -> str:
    return f"""你是一个关系记忆分析器。分析以下对话，输出 JSON。

## 对话内容 (topic: {topic})
{conversation_text}

## 输出格式
{{
  "summary": "一段话总结这次对话（中文，50字以内）",
  "outcome": "resolved | unresolved | neutral",
  "key_points": ["关键点1", "关键点2"],
  "memories": [
    {{
      "memory_type": "emotional_moment|shared_event|recurring_topic|unresolved_issue|user_fact|preference",
      "content": "记忆内容（一句话）",
      "confidence": 0.0-1.0
    }}
  ]
}}

## 记忆类型说明
- emotional_moment: 关键的情绪时刻
- shared_event: 共同经历的事件
- recurring_topic: 反复出现的话题模式
- unresolved_issue: 未解决的问题
- user_fact: 关于她的个人信息
- preference: 她表达的好恶

仅输出 JSON，不要其他内容。"""


# ============================================================
# Node 5b: Deduplicate & Persist Memories
# ============================================================

async def dedup_and_persist_node(state: PipelineState) -> dict:
    """Check semantic dedup, persist new memories, handle conversation close."""
    extracted = state.get("_extracted_memories", [])
    closed = state.get("closed_conversation")
    contact_id = state.get("contact_id", "")

    if not closed:
        return {}

    # Persist conversation + messages
    await _persist_conversation(contact_id, closed)

    # Persist memories with dedup
    if extracted:
        await _persist_memories(contact_id, extracted)

    # Update relationship_state (conflict_level, recurring_topics etc.)
    await _update_relationship_from_conv(contact_id, closed)

    return {}


async def _persist_conversation(contact_id: str, conv: dict) -> None:
    from backend.db import _get_conn
    import uuid as _uuid

    def _parse_ts(val):
        if val is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(val, datetime):
            return val.isoformat()
        try:
            return datetime.fromisoformat(str(val)).isoformat()
        except (ValueError, TypeError):
            return datetime.now(timezone.utc).isoformat()

    conn = await _get_conn()
    conv_id = str(_uuid.uuid4())
    await conn.execute(
        """INSERT INTO conversations (id, contact_id, topic, status, goal, start_time, end_time, summary, outcome, key_points)
           VALUES (?, ?, ?, 'closed', ?, ?, ?, ?, ?, ?)""",
        (conv_id, contact_id, conv.get("topic", "daily"),
         conv.get("current_goal", ""),
         _parse_ts(conv.get("start_time")),
         _parse_ts(conv.get("end_time")),
         conv.get("summary", ""),
         conv.get("outcome", "neutral"),
         json.dumps(conv.get("key_points", []), ensure_ascii=False)),
    )
    for msg in conv.get("messages_log", []):
        await conn.execute(
            """INSERT INTO messages (id, conversation_id, contact_id, role, content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), conv_id, contact_id,
             msg.get("role", "她"), msg.get("content", ""),
             _parse_ts(msg.get("timestamp"))),
        )
    await conn.commit()


async def _persist_memories(contact_id: str, memories: list[dict]) -> None:
    from backend.db import _get_conn
    from backend.memory.dedup import find_duplicates
    import uuid as _uuid

    _TTL_DAYS = {
        "emotional_moment": 30, "key_event": 60, "shared_event": 365,
        "unresolved_issue": 90, "preference": 180, "user_fact": 365,
        "recurring_topic": 90,
    }

    now = datetime.now(timezone.utc).isoformat()
    conn = await _get_conn()

    for mem in memories:
        content = mem.get("content", "")
        mem_type = mem.get("memory_type", "shared_event")
        confidence = mem.get("confidence", 0.5)

        # Semantic dedup for stable types (preference / user_fact — slight wording
        # variations should merge into one record instead of creating duplicates).
        if mem_type in ("preference", "user_fact"):
            dupes = await find_duplicates(content, contact_id, threshold=0.15)
            compatible = [d for d in dupes
                          if d.get("memory_type") in ("preference", "user_fact")]
            if compatible:
                await conn.execute(
                    """UPDATE memories_sql SET recall_count = recall_count + 1,
                       last_recalled_at = ?, confidence = MAX(confidence, ?)
                       WHERE id = ?""",
                    (now, confidence, compatible[0]["id"]),
                )
                continue
        else:
            # Exact match for event/emotion/issue types
            cursor = await conn.execute(
                """SELECT id FROM memories_sql WHERE contact_id = ? AND memory_type = ?
                   AND content = ? LIMIT 1""",
                (contact_id, mem_type, content),
            )
            existing = await cursor.fetchone()
            if existing:
                await conn.execute(
                    """UPDATE memories_sql SET recall_count = recall_count + 1,
                       last_recalled_at = ? WHERE id = ?""",
                    (now, existing["id"]),
                )
                continue

        mem_id = str(_uuid.uuid4())
        ttl_days = _TTL_DAYS.get(mem_type, 365)
        expires = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
        importance = 3 if mem_type in ("emotional_moment", "unresolved_issue") else 1

        await conn.execute(
            """INSERT INTO memories_sql (id, contact_id, memory_type, content, confidence,
               importance, created_at, last_recalled_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem_id, contact_id, mem_type, content, confidence,
             importance, now, now, expires),
        )
        # Also write to ChromaDB for vector search
        try:
            from backend.db import get_chroma_collection
            coll = await get_chroma_collection("memories")
            coll.add(
                ids=[mem_id],
                documents=[content],
                metadatas=[{
                    "contact_id": contact_id,
                    "memory_type": mem_type,
                    "confidence": confidence,
                    "importance": importance,
                }],
            )
        except Exception:
            pass
    await conn.commit()


async def _update_relationship_from_conv(contact_id: str, conv: dict) -> None:
    """Apply MemoryUpdater-like rules and write to relationship_state table."""
    from src.memory_updater import MemoryUpdater

    mu = MemoryUpdater()
    # Build a mock conversation object for the updater
    class ConvWrapper:
        topic = conv.get("topic", "daily")
        outcome = conv.get("outcome", "neutral")
        key_points = conv.get("key_points", [])
        summary = conv.get("summary", "")

    result = mu.update(ConvWrapper())
    mu.save()

    # Sync to SQLite
    from backend.db import _get_conn
    import uuid as _uuid
    rs = mu.state
    now = datetime.now(timezone.utc).isoformat()

    conn = await _get_conn()
    # Upsert: try update first, then insert if not found
    cursor = await conn.execute(
        "SELECT id FROM relationship_state WHERE contact_id = ?", (contact_id,)
    )
    existing = await cursor.fetchone()
    if existing:
        await conn.execute(
            """UPDATE relationship_state SET stage = ?, trust_level = ?, intimacy_level = ?,
               conflict_level = ?, warmth = ?, updated_at = ?
               WHERE contact_id = ?""",
            (rs.get("stage", "acquaintance"), rs.get("trust_level", 50),
             rs.get("intimacy_level", 30), rs.get("conflict_level", 0),
             rs.get("warmth", "neutral"), now, contact_id),
        )
    else:
        await conn.execute(
            """INSERT INTO relationship_state (id, contact_id, stage, trust_level, intimacy_level, conflict_level, warmth, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), contact_id, rs.get("stage", "acquaintance"),
             rs.get("trust_level", 50), rs.get("intimacy_level", 30),
             rs.get("conflict_level", 0), rs.get("warmth", "neutral"), now),
        )
    await conn.commit()


# ============================================================
# Node 5c: Extract Typed Memories (LLM, frequency-gated)
# ============================================================

_EXTRACT_INTERVAL = 15  # messages between memory extraction calls

_MEMORY_EXTRACT_PROMPT = """你是一个关系记忆提取器。从以下对话中提取结构化记忆。

## 记忆类型
- emotional_moment: 关键的情绪时刻（冲突、深情、脆弱）
- preference: 她的喜好、厌恶、习惯
- user_fact: 关于她的个人信息（工作、家庭、计划）
- unresolved_issue: 未解决的问题或不满
- recurring_topic: 反复出现的话题模式
- key_event: 重要的生活事件

## 输出格式
{"memories": [{"memory_type": "...", "content": "一句话描述", "confidence": 0.0-1.0}]}

## 规则
- 只提取有明确证据的记忆，不要推测
- content 用中文，简洁明确
- confidence: 明确陈述=0.9+，暗示=0.5-0.7
- 每条记忆独立，不要重复
- 如果没有值得提取的记忆，返回 {"memories": []}

仅输出 JSON。"""


async def extract_memories_node(state: PipelineState) -> dict:
    """Frequency-gated memory extraction. Runs every _EXTRACT_INTERVAL messages.

    Extracts typed memories from recent messages, dedups, and persists
    to both SQLite (memories_sql) and ChromaDB (memories collection).
    """
    from backend.services.llm_service import LlmService
    from backend.config import load_api_key

    contact_id = state.get("contact_id", "")
    messages = state.get("messages", [])
    new_count = len(messages)

    # Frequency gate
    current_count = state.get("_msg_count_since_extract", 0) + new_count
    conversation_switched = state.get("conversation_switched", False)

    if current_count < _EXTRACT_INTERVAL and not conversation_switched:
        return {"_msg_count_since_extract": current_count}

    # Run memory decay before extraction (maintenance, best-effort)
    try:
        from backend.memory.store import apply_decay as _apply_decay
        await _apply_decay(contact_id)
    except Exception:
        pass

    # Build conversation text from recent messages
    her_msgs = [m for m in messages if m.get("role") == "她"]
    my_msgs = [m for m in messages if m.get("role") != "她"]
    lines = []
    for m in messages[-40:]:
        role = "她" if m.get("role") == "她" else "我"
        lines.append(f"{role}: {m.get('content', '')}")
    conversation_text = "\n".join(lines)

    # Call LLM for memory extraction
    llm = LlmService(api_key=load_api_key())
    memories = []
    try:
        result_text = await llm.chat(_MEMORY_EXTRACT_PROMPT, conversation_text)
        # LLM may wrap JSON in ``` fences or add trailing text
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        parsed = json.loads(result_text)
        memories = parsed.get("memories", [])
    except (json.JSONDecodeError, KeyError) as e:
        # Log the raw output so we can debug format drift
        import logging
        logging.warning(f"extract_memories JSON parse error: {e}")
        logging.warning(f"Raw LLM output (first 500 chars): {str(result_text)[:500]}")
    except Exception as e:
        import logging
        logging.warning(f"extract_memories unexpected error: {type(e).__name__}: {e}")

    # Persist new memories (dedup + dual-write)
    if memories:
        await _persist_memories(contact_id, memories)

    return {
        "_msg_count_since_extract": 0,  # reset counter
        "_extracted_memories": memories,
    }


# ============================================================
# Node 6: Retrieve Context (hybrid retrieval)
# ============================================================

async def retrieve_context_node(state: PipelineState) -> dict:
    from src.context_builder import ContextBuilder
    from src.conversation import ConversationManager
    from backend.config import CONV_PATH

    contact_id = state.get("contact_id", "")
    conv_mgr = ConversationManager(storage_path=CONV_PATH)
    active_conv = conv_mgr.get_active_conversation()

    rs_raw = _load_rs_raw()
    messages = state["messages"]

    # Retrieve relevant memories
    recalled = await _recall_memories(contact_id, state.get("topic", ""), limit=5)

    ctx_builder = ContextBuilder(rs_raw, active_conv, messages)
    llm_context = ctx_builder.format_for_llm()

    if recalled:
        memory_text = "\n".join(
            f"- [{m['memory_type']}] {m['content']}" for m in recalled
        )
        llm_context += f"\n\n## 相关历史记忆\n{memory_text}"

    return {
        "recalled_memories": recalled,
        "llm_context": llm_context,
    }


async def _recall_memories(contact_id: str, topic: str, limit: int = 5) -> list[dict]:
    """Retrieve top memories filtered by time, sorted by importance > confidence > recall_count."""
    from backend.memory.store import recall_memories
    return await recall_memories(contact_id, days=30, limit=limit)


# ============================================================
# Node 7: Strategy Selection (rules + effectiveness weighting)
# ============================================================

async def strategy_select_node(state: PipelineState) -> dict:
    from src.strategy_selector import StrategySelector
    from src.message_understanding import MessageState

    rs_raw = _load_rs_raw()
    ms = MessageState(
        message="",
        surface_intent_scores={},
        emotion=state["emotion"],
        emotion_intensity=state.get("emotion_intensity", 0.5),
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
    )

    goal_result = {"goal": state["goal"], "goal_zh": state.get("goal_zh", state["goal"])}
    need_result = {
        "top_needs": state.get("top_needs", []),
        "dominant_need": state.get("dominant_need", ""),
        "applied_rules": [],
    }

    selector = StrategySelector(relationship_state=rs_raw)
    result = selector.select(ms, goal_result, need_result)

    card = result.get("primary")
    if not card:
        return {"error": "no strategy available", "reply": "(无可用的策略)", "enhanced_reply": "(无可用的策略)"}

    return {
        "strategy_name": card.name,
        "strategy_card": {
            "id": card.id, "name": card.name,
            "goal": card.goal, "risk_level": card.risk_level,
        },
    }


# ============================================================
# Node 8: Reply Generation (LLM, streaming-capable)
# ============================================================

async def reply_generate_node(state: PipelineState) -> dict:
    from src.reply_generator import ReplyGenerator
    from src.strategy_loader import StrategyLoader, StrategyCard
    from src.message_understanding import MessageState
    from backend.services.llm_service import LlmService
    from backend.config import load_api_key

    rs_raw = _load_rs_raw()
    card_data = state.get("strategy_card", {})
    card = StrategyCard({"id": card_data.get("id", ""), "name": card_data.get("name", ""),
                         "goal": card_data.get("goal", ""), "risk_level": card_data.get("risk_level", "low")})

    her_msgs = [m.get("content", "") for m in state["messages"] if m.get("role") == "她"]
    last_msg = her_msgs[-1] if her_msgs else ""

    ms = MessageState(
        message=last_msg,
        surface_intent_scores={},
        emotion=state["emotion"],
        emotion_intensity=state.get("emotion_intensity", 0.5),
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
        burst_pattern=state.get("burst_pattern", "single"),
    )

    goal_result = {"goal": state["goal"], "goal_zh": state.get("goal_zh", state["goal"])}

    # Build burst analysis for the reply generator
    burst_analysis = {
        "pattern": state.get("burst_pattern", "single"),
        "msg_count": len(her_msgs),
        "her_msgs": her_msgs,
    }

    reply_gen = ReplyGenerator(relationship_state=rs_raw)
    llm = LlmService(api_key=load_api_key())
    result = reply_gen.generate(
        llm.as_callable(), ms, card, goal_result,
        chat_history=list(state["messages"]),
        conversation_context=state.get("llm_context", ""),
        burst_analysis=burst_analysis,
    )

    return {"reply": result.get("reply", "")}


# ============================================================
# Node 9: Expression Enhancement (LLM)
# ============================================================

async def enhance_reply_node(state: PipelineState) -> dict:
    from src.expression_enhancer import ExpressionEnhancer
    from src.strategy_loader import StrategyLoader, StrategyCard
    from src.message_understanding import MessageState
    from backend.services.llm_service import LlmService
    from backend.config import load_api_key

    rs_raw = _load_rs_raw()
    card_data = state.get("strategy_card", {})
    card = StrategyCard({"id": card_data.get("id", ""), "name": card_data.get("name", ""),
                         "goal": card_data.get("goal", ""), "risk_level": card_data.get("risk_level", "low")})

    her_msgs = [m.get("content", "") for m in state["messages"] if m.get("role") == "她"]
    last_msg = her_msgs[-1] if her_msgs else ""

    ms = MessageState(
        message=last_msg,
        surface_intent_scores={},
        emotion=state["emotion"],
        emotion_intensity=state.get("emotion_intensity", 0.5),
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
    )

    reply = state.get("reply", "")
    is_complex = len(her_msgs) >= 5
    # Skip enhancer for long replies to complex inputs — the LLM tends to
    # summarise instead of polish, destroying information density.
    if is_complex and len(reply) >= 200:
        return {"enhanced_reply": reply}

    enhancer = ExpressionEnhancer(relationship_state=rs_raw)
    llm = LlmService(api_key=load_api_key())
    result = enhancer.enhance(
        llm.as_callable(), reply, ms, card,
        input_complexity={
            "her_msg_count": len(her_msgs),
            "burst_pattern": state.get("burst_pattern", "single"),
        },
    )
    enhanced = result.get("enhanced_reply", reply)
    # Safety net: if enhancer destroyed content, fall back to raw reply
    if is_complex and len(enhanced) < len(reply) * 0.5:
        enhanced = reply

    return {"enhanced_reply": enhanced}


# ============================================================
# Node 10: Persist Result
# ============================================================

async def persist_result_node(state: PipelineState) -> dict:
    contact_id = state.get("contact_id", "")

    # Update strategy metrics
    strategy_name = state.get("strategy_name", "")
    if strategy_name:
        await _update_strategy_metrics(contact_id, strategy_name)

    return {
        "debug": {
            "emotion": state.get("emotion", ""),
            "emotion_intensity": state.get("emotion_intensity", 0),
            "dominant_intent": state.get("dominant_intent", ""),
            "dominant_need": state.get("dominant_need", ""),
            "top_needs": state.get("top_needs", []),
        }
    }


async def _update_strategy_metrics(contact_id: str, strategy_name: str) -> None:
    from backend.db import _get_conn
    import uuid as _uuid
    now = datetime.now(timezone.utc).isoformat()

    conn = await _get_conn()
    cursor = await conn.execute(
        "SELECT id, total_uses FROM strategy_metrics WHERE contact_id = ? AND strategy_name = ?",
        (contact_id, strategy_name),
    )
    existing = await cursor.fetchone()
    if existing:
        await conn.execute(
            "UPDATE strategy_metrics SET total_uses = total_uses + 1, last_used = ? WHERE id = ?",
            (now, existing["id"]),
        )
    else:
        await conn.execute(
            """INSERT INTO strategy_metrics (id, contact_id, strategy_name, total_uses, last_used)
               VALUES (?, ?, ?, 1, ?)""",
            (str(_uuid.uuid4()), contact_id, strategy_name, now),
        )
    await conn.commit()


# ============================================================
# Helpers
# ============================================================

def _load_rs_raw() -> dict:
    if RS_PATH.exists():
        raw = json.loads(RS_PATH.read_text(encoding="utf-8"))
        return raw.get("relationship_state", raw)
    return {}


def _fallback_mu_state(messages: list[dict], mode: str) -> dict:
    """Fallback when LLM returns unparseable JSON — use simple heuristics."""
    her_msgs = [m.get("content", "") for m in messages if m.get("role") == "她"]
    last_msg = her_msgs[-1] if her_msgs else ""
    return {
        "emotion": "neutral",
        "emotion_intensity": 0.3,
        "dominant_intent": "sharing",
        "topic": "daily",
        "need_scores": {"ATTENTION": 0.5, "COMPANIONSHIP": 0.3},
        "burst_pattern": "burst" if len(her_msgs) >= 3 else "single",
        "trajectory_note": "",
        "conversation_stage": "deepening",
    }


def _make_message_state(state: PipelineState):
    """Build a MessageState from pipeline state for backward compatibility."""
    from src.message_understanding import MessageState
    return MessageState(
        message="",
        surface_intent_scores={},
        emotion=state.get("emotion", "neutral"),
        emotion_intensity=state.get("emotion_intensity", 0.5),
        need_scores=state.get("need_scores", {}),
        relationship_signal="",
        expression_mode="text",
        state_type="conversation",
        suggest_direction="continue",
        has_metaphor=False,
        conflict_signal="none",
        conversation_stage=state.get("conversation_stage", "deepening"),
        expected_response="text",
        topic=state.get("topic", "daily"),
        burst_pattern=state.get("burst_pattern", "single"),
        trajectory_note=state.get("trajectory_note", ""),
    )
