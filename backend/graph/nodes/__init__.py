"""LangGraph node implementations — thin wrappers that bridge src/ logic into StateGraph."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
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
    ms = mu.parse_to_state(result_text)

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
    from backend.db import get_pool

    def _parse_ts(val):
        if val is None:
            return datetime.now(timezone.utc)
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)

    pool = await get_pool()
    async with pool.acquire() as conn:
        conv_id = await conn.fetchval(
            """INSERT INTO conversations (contact_id, topic, status, goal, start_time, end_time, summary, outcome, key_points)
               VALUES ($1, $2, 'closed', $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            contact_id, conv.get("topic", "daily"),
            conv.get("current_goal", ""),
            _parse_ts(conv.get("start_time")),
            _parse_ts(conv.get("end_time")),
            conv.get("summary", ""),
            conv.get("outcome", "neutral"),
            json.dumps(conv.get("key_points", []), ensure_ascii=False),
        )
        for msg in conv.get("messages_log", []):
            await conn.execute(
                """INSERT INTO messages (conversation_id, contact_id, role, content, timestamp)
                   VALUES ($1, $2, $3, $4, $5)""",
                conv_id, contact_id,
                msg.get("role", "她"), msg.get("content", ""),
                _parse_ts(msg.get("timestamp")),
            )


async def _persist_memories(contact_id: str, memories: list[dict]) -> None:
    from backend.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        for mem in memories:
            content = mem.get("content", "")
            mem_type = mem.get("memory_type", "shared_event")
            confidence = mem.get("confidence", 0.5)

            # Dedup: check existing similar memories
            existing = await conn.fetchrow(
                """SELECT id FROM memories WHERE contact_id = $1 AND memory_type = $2
                   AND content = $3 LIMIT 1""",
                contact_id, mem_type, content,
            )
            if existing:
                await conn.execute(
                    "UPDATE memories SET recall_count = recall_count + 1, last_recalled_at = now() WHERE id = $1",
                    existing["id"],
                )
                continue

            await conn.execute(
                """INSERT INTO memories (contact_id, memory_type, content, confidence, importance)
                   VALUES ($1, $2, $3, $4, $5)""",
                contact_id, mem_type, content, confidence,
                3 if mem_type in ("emotional_moment", "unresolved_issue") else 1,
            )


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

    # Sync to PostgreSQL
    from backend.db import get_pool
    pool = await get_pool()
    rs = mu.state
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO relationship_state (contact_id, stage, trust_level, intimacy_level, conflict_level, warmth)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (contact_id) DO UPDATE SET
                 stage = EXCLUDED.stage,
                 trust_level = EXCLUDED.trust_level,
                 intimacy_level = EXCLUDED.intimacy_level,
                 conflict_level = EXCLUDED.conflict_level,
                 warmth = EXCLUDED.warmth,
                 updated_at = now()""",
            contact_id,
            rs.get("stage", "acquaintance"),
            rs.get("trust_level", 50),
            rs.get("intimacy_level", 30),
            rs.get("conflict_level", 0),
            rs.get("warmth", "neutral"),
        )


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
    from backend.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT memory_type, content, confidence FROM memories
               WHERE contact_id = $1
               ORDER BY importance DESC, recall_count DESC, created_at DESC
               LIMIT $2""",
            contact_id, limit * 2,
        )
        return [
            {"memory_type": r["memory_type"], "content": r["content"], "confidence": r["confidence"]}
            for r in rows
        ][:limit]


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
    )

    goal_result = {"goal": state["goal"], "goal_zh": state.get("goal_zh", state["goal"])}

    reply_gen = ReplyGenerator(relationship_state=rs_raw)
    llm = LlmService(api_key=load_api_key())
    result = reply_gen.generate(
        llm.as_callable(), ms, card, goal_result,
        chat_history=list(state["messages"]),
        conversation_context=state.get("llm_context", ""),
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

    enhancer = ExpressionEnhancer(relationship_state=rs_raw)
    llm = LlmService(api_key=load_api_key())
    result = enhancer.enhance(llm.as_callable(), state.get("reply", ""), ms, card)

    return {"enhanced_reply": result.get("enhanced_reply", state.get("reply", ""))}


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
    from backend.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO strategy_metrics (contact_id, strategy_name, total_uses, last_used)
               VALUES ($1, $2, 1, now())
               ON CONFLICT (contact_id, strategy_name) DO UPDATE SET
                 total_uses = strategy_metrics.total_uses + 1,
                 last_used = now()""",
            contact_id, strategy_name,
        )


# ============================================================
# Helpers
# ============================================================

def _load_rs_raw() -> dict:
    if RS_PATH.exists():
        raw = json.loads(RS_PATH.read_text(encoding="utf-8"))
        return raw.get("relationship_state", raw)
    return {}


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
