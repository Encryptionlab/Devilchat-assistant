"""Pipeline orchestrator — ports run.py's interactive loop to async service."""

import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from src.message_understanding import MessageUnderstanding, load_relationship_state as load_rs_from_file
from src.need_recognition import NeedRecognizer
from src.goal_planner import GoalPlanner
from src.strategy_selector import StrategySelector
from src.reply_generator import ReplyGenerator
from src.expression_enhancer import ExpressionEnhancer
from src.conversation import ConversationManager
from src.context_builder import ContextBuilder, build_context_from_file
from src.memory_updater import MemoryUpdater
from src.summarizer import summarize

from backend.config import RS_PATH, CONV_PATH
from backend.services.llm_service import LlmService
from backend.services.state_service import StateService


class PipelineService:
    """Async version of run.py's interactive pipeline. One instance per app lifetime."""

    def __init__(self, llm: LlmService, state: StateService):
        self.llm = llm
        self.state = state
        self._conv_mgr: ConversationManager | None = None
        self._strategy_cache: dict | None = None

    async def _get_conversation_manager(self) -> ConversationManager:
        """Get or create ConversationManager, ensuring it reads current disk state."""
        self._conv_mgr = ConversationManager(storage_path=CONV_PATH)
        return self._conv_mgr

    async def process_message(self, her_msg: str, chat_history: list[dict],
                              ms_override=None) -> dict:
        """Run the full pipeline and return a complete ChatResponse dict.

        If ms_override is provided (MessageState), skip MessageUnderstanding LLM call.
        """
        rs = await self.state.load_relationship_state()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # Step 1: Message Understanding (LLM #1)
        if ms_override is not None:
            ms = ms_override
        else:
            mu = MessageUnderstanding()
            llm_result = await self.llm.chat(mu.system_prompt, mu.build_user_prompt([{"role": "她", "content": her_msg}]))
            ms = mu.parse_to_state(llm_result)

        # Step 2: Need Recognition (rules)
        need_result = NeedRecognizer(rs).prioritize(ms)

        # Step 3: Goal Planning (rules)
        goal_result = GoalPlanner(rs).plan(ms, need_result["top_needs"])

        # Step 4: Conversation Engine (rules)
        conv_mgr = await self._get_conversation_manager()
        prev_conv = conv_mgr.get_active_conversation()
        conv, switched = conv_mgr.process_message(her_msg, timestamp, goal_result["goal"],
                                                    topic_override=ms.topic)

        # Step 5: On close hook (LLM #2 + rules)
        closed_conv_dict = None
        if switched and prev_conv is not None:
            closed_conv_dict = await self._handle_conversation_closed(
                prev_conv, chat_history, conv_mgr
            )

        # Step 6: Context Building (rules)
        rs_raw = json.loads(RS_PATH.read_text(encoding="utf-8")).get("relationship_state", rs) \
            if RS_PATH.exists() else rs
        cb = ContextBuilder(rs_raw, conv, chat_history + [{"role": "她", "content": her_msg}])
        ctx = cb.format_for_llm()

        # Step 7: Strategy Selection (rules)
        strategy_result = StrategySelector(relationship_state=rs).select(ms, goal_result, need_result)

        card = strategy_result.get("primary")
        if not card:
            return {
                "reply": "(无可用的策略)",
                "enhanced_reply": "(无可用的策略)",
                "strategy_name": "none",
                "goal": goal_result["goal"],
                "goal_zh": goal_result.get("goal_zh", goal_result["goal"]),
                "conversation_switched": switched,
                "closed_conversation": closed_conv_dict,
                "debug": self._debug_info(ms, need_result, goal_result),
            }

        # Step 8: Reply Generation (LLM #3)
        reply_result = ReplyGenerator(relationship_state=rs).generate(
            self.llm.as_callable(), ms, card, goal_result,
            chat_history=list(chat_history + [{"role": "她", "content": her_msg}]),
            conversation_context=ctx,
        )

        # Step 9: Expression Enhancement (LLM #4)
        enhanced = ExpressionEnhancer(relationship_state=rs).enhance(
            self.llm.as_callable(), reply_result["reply"], ms, card,
        )

        return {
            "reply": reply_result["reply"],
            "enhanced_reply": enhanced["enhanced_reply"],
            "strategy_name": card.name,
            "goal": goal_result["goal"],
            "goal_zh": goal_result.get("goal_zh", goal_result["goal"]),
            "conversation_switched": switched,
            "closed_conversation": closed_conv_dict,
            "debug": self._debug_info(ms, need_result, goal_result),
        }

    async def process_message_stream(
        self, her_msg: str, chat_history: list[dict]
    ) -> AsyncGenerator[str, None]:
        """Streaming variant of process_message. Yields SSE-formatted strings."""
        import asyncio

        rs = await self.state.load_relationship_state()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # Helper to emit SSE
        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def _put(queue: asyncio.Queue, event: str, data: dict):
            queue.put_nowait(_sse(event, data))

        queue: asyncio.Queue[str] = asyncio.Queue()

        async def _run():
            try:
                # Step 1: Message Understanding (LLM #1)
                _put(queue, "step", {"step": "message_understanding", "status": "running"})
                mu = MessageUnderstanding()
                llm_result = await self.llm.chat(mu.system_prompt, mu.build_user_prompt([{"role": "她", "content": her_msg}]))
                ms = mu.parse_to_state(llm_result)
                _put(queue, "step", {"step": "message_understanding", "status": "done",
                                      "emotion": ms.emotion, "topic": ms.topic})

                # Step 2: Need Recognition
                _put(queue, "step", {"step": "need_recognition", "status": "running"})
                need_result = NeedRecognizer(rs).prioritize(ms)
                _put(queue, "step", {"step": "need_recognition", "status": "done",
                                      "dominant_need": need_result["dominant_need"]})

                # Step 3: Goal Planning
                _put(queue, "step", {"step": "goal_planning", "status": "running"})
                goal_result = GoalPlanner(rs).plan(ms, need_result["top_needs"])
                _put(queue, "step", {"step": "goal_planning", "status": "done",
                                      "goal": goal_result["goal"],
                                      "goal_zh": goal_result.get("goal_zh", goal_result["goal"])})

                # Step 4: Conversation Engine
                _put(queue, "step", {"step": "conversation_engine", "status": "running"})
                conv_mgr = await self._get_conversation_manager()
                prev_conv = conv_mgr.get_active_conversation()
                conv, switched = conv_mgr.process_message(her_msg, timestamp, goal_result["goal"],
                                                            topic_override=ms.topic)
                _put(queue, "step", {"step": "conversation_engine", "status": "done",
                                      "switched": switched, "topic": conv.topic})

                # Step 5: Close hook
                closed_conv_dict = None
                if switched and prev_conv is not None:
                    _put(queue, "step", {"step": "summarizer", "status": "running"})
                    closed_conv_dict = await self._handle_conversation_closed(
                        prev_conv, chat_history, conv_mgr
                    )
                    _put(queue, "step", {"step": "summarizer", "status": "done",
                                          "outcome": closed_conv_dict.get("outcome") if closed_conv_dict else None})

                # Step 6-7: Context + Strategy (rules, fast)
                rs_raw = json.loads(RS_PATH.read_text(encoding="utf-8")).get("relationship_state", rs) \
                    if RS_PATH.exists() else rs
                all_msgs = chat_history + [{"role": "她", "content": her_msg}]
                cb = ContextBuilder(rs_raw, conv, all_msgs)
                ctx = cb.format_for_llm()

                strategy_result = StrategySelector(relationship_state=rs).select(ms, goal_result, need_result)
                card = strategy_result.get("primary")
                if not card:
                    _put(queue, "done", {"error": "no strategy", "conversation_switched": switched})
                    queue.put_nowait(None)
                    return

                _put(queue, "step", {"step": "strategy_selection", "status": "done",
                                      "strategy": card.name})

                # Step 8: Reply Generation (LLM #3, streaming)
                _put(queue, "step", {"step": "reply_generation", "status": "running"})
                reply_gen = ReplyGenerator(relationship_state=rs)
                reply_sys = reply_gen._build_system_prompt(card, goal_result)
                reply_usr = reply_gen._build_user_prompt(ms, all_msgs, None, ctx)

                full_reply = ""
                async for token in self.llm.chat_stream(reply_sys, reply_usr):
                    full_reply += token
                    _put(queue, "reply_chunk", {"text": token})
                _put(queue, "step", {"step": "reply_generation", "status": "done"})

                # Step 9: Expression Enhancement (LLM #4, streaming)
                _put(queue, "step", {"step": "expression_enhancement", "status": "running"})
                enhancer = ExpressionEnhancer(relationship_state=rs)
                enh_sys = enhancer._build_system_prompt(card)
                enh_usr = enhancer._build_user_prompt(full_reply, ms)

                full_enhanced = ""
                async for token in self.llm.chat_stream(enh_sys, enh_usr):
                    full_enhanced += token
                    _put(queue, "enhanced_chunk", {"text": token})
                _put(queue, "step", {"step": "expression_enhancement", "status": "done"})

                _put(queue, "done", {
                    "reply": full_reply,
                    "enhanced_reply": full_enhanced,
                    "strategy_name": card.name,
                    "goal": goal_result["goal"],
                    "goal_zh": goal_result.get("goal_zh", goal_result["goal"]),
                    "conversation_switched": switched,
                    "closed_conversation": closed_conv_dict,
                })
            except Exception as e:
                _put(queue, "error", {"error": str(e)})
            finally:
                queue.put_nowait(None)

        # Run pipeline in background task
        asyncio.create_task(_run())

        while True:
            sse_line = await queue.get()
            if sse_line is None:
                break
            yield sse_line

    async def _handle_conversation_closed(
        self, closed_conv, messages: list[dict], conv_mgr: ConversationManager
    ) -> dict | None:
        """Generate summary, update memory, persist — port of run.py's _on_conversation_closed."""
        msgs = closed_conv.messages_log if closed_conv.messages_log else messages
        if not msgs:
            return None
        try:
            result = summarize(self.llm.as_callable(), msgs, closed_conv.topic)
            closed_conv.summary = result["summary"]
            closed_conv.outcome = result["outcome"]
            closed_conv.key_points = result["key_points"]
        except Exception:
            closed_conv.outcome = "neutral"

        updater = MemoryUpdater()
        updater.update(closed_conv)
        for topic in ["work", "exam", "family", "relationship", "dating", "conflict"]:
            count = conv_mgr.count_topic_in_recent(topic, n=10)
            if count >= 3:
                updater.apply_recurring_topics({topic: count})
        updater.save()
        conv_mgr._save()

        return {
            "id": closed_conv.id,
            "topic": closed_conv.topic,
            "start_time": closed_conv.start_time,
            "end_time": closed_conv.end_time,
            "summary": closed_conv.summary,
            "outcome": closed_conv.outcome,
            "key_points": closed_conv.key_points,
        }

    # ---- Observation Track (WCF 持续监听) ----

    async def observe_messages(
        self, messages: list[dict], trigger_evaluator: bool = True
    ) -> dict:
        """观测模式：记录消息流，不绑定策略/目标。

        两阶段流程（解决 MU ↔ CM 循环依赖）：
        Phase 1: log_message — 轻量记录到 messages_log（关键词话题）
        Phase 2: MU — 从 messages_log 读取完整上下文做序列分析
        Phase 3: process_boundary — 使用 LLM 话题做边界检测
        """
        if not messages:
            return {"conversation": None, "had_closed": False, "closed_conv": None}

        rs = await self.state.load_relationship_state()
        her_msgs = [m for m in messages if m.get("role") == "她"]
        if not her_msgs:
            her_msgs = [messages[-1]]

        conv_mgr = await self._get_conversation_manager()

        # Phase 1: 轻量记录所有消息（不做边界检测）
        for msg in messages:
            role = msg.get("role", "她")
            content = msg.get("content", "")
            ts = msg.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
            conv_mgr.log_message(content, ts, role)

        # Phase 2: MU 从 messages_log 读取完整上下文
        active = conv_mgr.get_active_conversation()
        msg_log = active.messages_log if active else []
        mu = MessageUnderstanding()
        recent = msg_log[-15:]
        llm_result = await self.llm.chat(
            mu.system_prompt,
            mu.build_user_prompt_for_sequence(recent)
        )
        ms = mu.parse_to_state(llm_result)

        # Phase 3: 使用 LLM 话题做边界检测
        had_closed = False
        closed_conv_dict = None
        for msg in messages:
            role = msg.get("role", "她")
            ts = msg.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
            _, _, has_closed = conv_mgr.process_boundary(
                timestamp=ts,
                topic_override=ms.topic if role == "她" else None,
            )
            if has_closed:
                had_closed = True
                prev_conv = conv_mgr.get_recent_conversations(1)
                if prev_conv:
                    closed_conv = prev_conv[-1]
                    closed_conv_dict = await self._handle_conversation_closed(
                        closed_conv, closed_conv.messages_log, conv_mgr,
                    )

        evaluation = None
        if trigger_evaluator and her_msgs:
            evaluation = await self._run_evaluator(rs, ms, her_msgs, conv_mgr.get_active_conversation())

        active = conv_mgr.get_active_conversation()
        return {
            "conversation": active.to_dict() if active else None,
            "had_closed": had_closed,
            "closed_conv": closed_conv_dict,
            "emotion": ms.emotion,
            "topic": ms.topic,
            "evaluation": evaluation,
        }

    async def analyze_pending(
        self, pending_messages: list[dict], chat_history: list[dict] | None = None
    ) -> dict:
        """干预模式：分析待处理消息，生成策略 + 建议回复。"""
        if not pending_messages:
            return {
                "reply": "", "enhanced_reply": "", "strategy_name": "none",
                "goal": "", "goal_zh": "", "conversation_switched": False,
                "closed_conversation": None, "debug": {},
            }
        mu = MessageUnderstanding()
        history = chat_history or []
        pending_fmt = [
            {"role": m.get("role", "她"), "content": m.get("content", "")}
            for m in pending_messages
        ]
        all_msgs = (history + pending_fmt)[-15:]
        llm_result = await self.llm.chat(
            mu.system_prompt, mu.build_user_prompt_for_sequence(all_msgs)
        )
        ms = mu.parse_to_state(llm_result)

        combined_msg = " ".join(m.get("content", "") for m in pending_messages)
        return await self.process_message(combined_msg, history, ms_override=ms)

    async def _run_evaluator(
        self, rs: dict, ms, her_msgs: list[dict], active_conv=None
    ) -> dict | None:
        """评估上一轮策略的效果。从 messages_log 提取上下文填充评估数据。"""
        from src.evaluator import StrategyEvaluator
        effectiveness = rs.get("strategy_effectiveness", {})
        if not effectiveness:
            return None
        last_strategy = None
        last_time = ""
        for name, entry in effectiveness.items():
            if isinstance(entry, dict) and entry.get("last_used", "") > last_time:
                last_time = entry["last_used"]
                last_strategy = name
        if not last_strategy:
            return None

        my_message = ""
        her_messages_before: list[str] = []
        if active_conv is not None:
            msg_log = getattr(active_conv, "messages_log", []) or []
            last_me_idx = -1
            for i in range(len(msg_log) - 1, -1, -1):
                if msg_log[i].get("role") == "我":
                    last_me_idx = i
                    break
            if last_me_idx >= 0:
                my_message = msg_log[last_me_idx].get("content", "")
                her_messages_before = [
                    m.get("content", "") for m in msg_log[:last_me_idx]
                    if m.get("role") == "她"
                ]

        evaluator = StrategyEvaluator()
        result = evaluator.evaluate(
            last_strategy=last_strategy,
            her_messages_before=her_messages_before,
            her_messages_after=[m.get("content", "") for m in her_msgs],
            my_message=my_message,
            emotion_before="neutral",
            emotion_after=ms.emotion,
        )
        evaluator.save_effectiveness(result)
        return {
            "strategy": result.strategy,
            "success": result.success,
            "partial": result.partial,
            "reason": result.reason,
        }

    @staticmethod
    def _debug_info(ms, need_result, goal_result) -> dict:
        return {
            "emotion": ms.emotion,
            "emotion_intensity": ms.emotion_intensity,
            "dominant_intent": ms.dominant_intent,
            "dominant_need": need_result.get("dominant_need", ""),
            "top_needs": [{"need": n, "score": s} for n, s in need_result.get("top_needs", [])],
            "applied_rules": need_result.get("applied_rules", []),
            "goal_reasoning": goal_result.get("reasoning", ""),
        }
